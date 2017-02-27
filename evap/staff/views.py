import csv
import datetime
import random
from collections import OrderedDict, defaultdict

from django.contrib import messages
from django.core.exceptions import PermissionDenied, SuspiciousOperation
from django.db import transaction, IntegrityError
from django.db.models import Max, Count, Q, BooleanField, ExpressionWrapper, Sum, Case, When, IntegerField
from django.forms.models import inlineformset_factory, modelformset_factory
from django.forms import formset_factory
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import ugettext as _
from django.utils.translation import ungettext, get_language
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.db.models import Prefetch
from django.views.decorators.http import require_POST

from evap.evaluation.auth import reviewer_required, staff_required
from evap.evaluation.models import Contribution, Course, Question, Questionnaire, Semester, \
                                   TextAnswer, UserProfile, FaqSection, FaqQuestion, EmailTemplate, Degree, CourseType
from evap.evaluation.tools import STATES_ORDERED, questionnaires_and_contributions, send_publish_notifications, \
                                  sort_formset
from evap.staff.forms import ContributionForm, AtLeastOneFormSet, CourseForm, CourseEmailForm, EmailTemplateForm, \
                             ImportForm, LotteryForm, QuestionForm, QuestionnaireForm, QuestionnairesAssignForm, \
                             SemesterForm, UserForm, ContributionFormSet, FaqSectionForm, FaqQuestionForm, \
                             UserImportForm, TextAnswerForm, DegreeForm, SingleResultForm, ExportSheetForm, \
                             UserMergeSelectionForm, CourseTypeForm, UserBulkDeleteForm, CourseTypeMergeSelectionForm, \
                             CourseParticipantCopyForm
from evap.staff.importers import EnrollmentImporter, UserImporter
from evap.staff.tools import custom_redirect, delete_navbar_cache, merge_users, bulk_delete_users, save_import_file, \
                             get_import_file_content_or_raise, delete_import_file, import_file_exists, forward_messages
from evap.student.views import vote_preview
from evap.student.forms import QuestionsForm
from evap.grades.tools import are_grades_activated
from evap.results.exporters import ExcelExporter
from evap.results.tools import get_textanswers, calculate_average_grades_and_deviation, CommentSection, TextResult
from evap.rewards.models import RewardPointGranting
from evap.rewards.tools import is_semester_activated, can_user_use_reward_points


def raise_permission_denied_if_archived(archiveable):
    if archiveable.is_archived:
        raise PermissionDenied


@staff_required
def index(request):
    template_data = dict(semesters=Semester.objects.all(),
                         templates=EmailTemplate.objects.all(),
                         sections=FaqSection.objects.all(),
                         disable_breadcrumb_staff=True)
    return render(request, "staff_index.html", template_data)


def get_courses_with_prefetched_data(semester):
    courses = semester.course_set.prefetch_related(
        Prefetch("contributions", queryset=Contribution.objects.filter(responsible=True).select_related("contributor"), to_attr="responsible_contribution"),
        Prefetch("contributions", queryset=Contribution.objects.filter(contributor=None), to_attr="general_contribution"),
        "degrees")
    participant_counts = semester.course_set.annotate(num_participants=Count("participants")).values_list("num_participants", flat=True)
    voter_counts = semester.course_set.annotate(num_voters=Count("voters")).values_list("num_voters", flat=True)
    textanswer_counts = semester.course_set.annotate(num_textanswers=Count("contributions__textanswer_set")).values_list("num_textanswers", flat=True)

    for course, participant_count, voter_count, textanswer_count in zip(courses, participant_counts, voter_counts, textanswer_counts):
        course.general_contribution = course.general_contribution[0]
        course.responsible_contributor = course.responsible_contribution[0].contributor
        course.num_textanswers = textanswer_count
        if course._participant_count is None:
            course.num_voters = voter_count
            course.num_participants = participant_count
    return courses


@reviewer_required
def semester_view(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    rewards_active = is_semester_activated(semester)
    grades_downloadable = are_grades_activated(semester)

    courses = get_courses_with_prefetched_data(semester)
    courses = sorted(courses, key=lambda cr: cr.name)

    courses_by_state = []
    for state in STATES_ORDERED.keys():
        this_courses = [course for course in courses if course.state == state]
        courses_by_state.append((state, this_courses))

    # semester statistics (per degree)
    class Stats:
        def __init__(self):
            self.num_enrollments_in_evaluation = 0
            self.num_votes = 0
            self.num_courses_evaluated = 0
            self.num_courses = 0
            self.num_comments = 0
            self.num_comments_reviewed = 0
            self.first_start = datetime.date(9999, 1, 1)
            self.last_end = datetime.date(2000, 1, 1)

    degree_stats = defaultdict(Stats)
    total_stats = Stats()
    for course in courses:
        if course.is_single_result:
            continue
        degrees = course.degrees.all()
        stats_objects = [degree_stats[degree] for degree in degrees]
        stats_objects += [total_stats]
        for stats in stats_objects:
            if course.state in ['in_evaluation', 'evaluated', 'reviewed', 'published']:
                stats.num_enrollments_in_evaluation += course.num_participants
                stats.num_votes += course.num_voters
                stats.num_comments += course.num_textanswers
                stats.num_comments_reviewed += course.num_reviewed_textanswers
            if course.state in ['evaluated', 'reviewed', 'published']:
                stats.num_courses_evaluated += 1
            stats.num_courses += 1
            stats.first_start = min(stats.first_start, course.vote_start_date)
            stats.last_end = max(stats.last_end, course.vote_end_date)
    degree_stats = OrderedDict(sorted(degree_stats.items(), key=lambda x: x[0].order))
    degree_stats['total'] = total_stats

    template_data = dict(
        semester=semester,
        courses_by_state=courses_by_state,
        disable_breadcrumb_semester=True,
        disable_if_archived="disabled" if semester.is_archived else "",
        rewards_active=rewards_active,
        grades_downloadable=grades_downloadable,
        num_courses=len(courses),
        degree_stats=degree_stats
    )
    return render(request, "staff_semester_view.html", template_data)


@staff_required
def semester_course_operation(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    raise_permission_denied_if_archived(semester)

    operation = request.GET.get('operation')
    if operation not in ['revertToNew', 'prepare', 'reenableEditorReview', 'approve', 'startEvaluation', 'publish', 'unpublish']:
        messages.error(request, _("Unsupported operation: ") + str(operation))
        return custom_redirect('staff:semester_view', semester_id)

    if request.method == 'POST':
        course_ids = request.POST.getlist('course_ids')
        courses = Course.objects.filter(id__in=course_ids)

        # If checkbox is not checked, set template to None
        if request.POST.get('send_email') == 'on':
            template = EmailTemplate(subject=request.POST["email_subject"], body=request.POST["email_body"])
        else:
            template = None

        if operation == 'revertToNew':
            helper_semester_course_operation_revert(request, courses)
        elif operation == 'prepare' or operation == 'reenableEditorReview':
            helper_semester_course_operation_prepare(request, courses, template)
        elif operation == 'approve':
            helper_semester_course_operation_approve(request, courses)
        elif operation == 'startEvaluation':
            helper_semester_course_operation_start(request, courses, template)
        elif operation == 'publish':
            helper_semester_course_operation_publish(request, courses, template)
        elif operation == 'unpublish':
            helper_semester_course_operation_unpublish(request, courses)

        return custom_redirect('staff:semester_view', semester_id)

    course_ids = request.GET.getlist('course')
    courses = Course.objects.filter(id__in=course_ids)

    # Set new state, and set email template for possible editing.
    email_template = None
    if courses:
        current_state_name = STATES_ORDERED[courses[0].state]
        if operation == 'revertToNew':
            new_state_name = STATES_ORDERED['new']

        elif operation == 'prepare' or operation == 'reenableEditorReview':
            new_state_name = STATES_ORDERED['prepared']
            email_template = EmailTemplate.objects.get(name=EmailTemplate.EDITOR_REVIEW_NOTICE)

        elif operation == 'approve':
            new_state_name = STATES_ORDERED['approved']
            # remove courses without enough questionnaires
            courses_with_enough_questionnaires = [course for course in courses if course.has_enough_questionnaires]
            difference = len(courses) - len(courses_with_enough_questionnaires)
            if difference:
                courses = courses_with_enough_questionnaires
                messages.warning(request, ungettext("%(courses)d course can not be approved, because it has not enough questionnaires assigned. It was removed from the selection.",
                    "%(courses)d courses can not be approved, because they have not enough questionnaires assigned. They were removed from the selection.",
                    difference) % {'courses': difference})

        elif operation == 'startEvaluation':
            new_state_name = STATES_ORDERED['in_evaluation']
            # remove courses with vote_end_date in the past
            courses_end_in_future = [course for course in courses if course.vote_end_date >= datetime.date.today()]
            difference = len(courses) - len(courses_end_in_future)
            if difference:
                courses = courses_end_in_future
                messages.warning(request, ungettext("%(courses)d course can not be approved, because it's evaluation end date lies in the past. It was removed from the selection.",
                    "%(courses)d courses can not be approved, because their evaluation end dates lie in the past. They were removed from the selection.",
                    difference) % {'courses': difference})
            email_template = EmailTemplate.objects.get(name=EmailTemplate.EVALUATION_STARTED)

        elif operation == 'publish':
            new_state_name = STATES_ORDERED['published']
            email_template = EmailTemplate.objects.get(name=EmailTemplate.PUBLISHING_NOTICE)

        elif operation == 'unpublish':
            new_state_name = STATES_ORDERED['reviewed']

    if not courses:
        messages.warning(request, _("Please select at least one course."))
        return custom_redirect('staff:semester_view', semester_id)

    template_data = dict(
        semester=semester,
        courses=courses,
        operation=operation,
        current_state_name=current_state_name,
        new_state_name=new_state_name,
        email_template=email_template,
        show_email_checkbox=email_template is not None
    )

    return render(request, "staff_course_operation.html", template_data)


def helper_semester_course_operation_revert(request, courses):
    for course in courses:
        course.revert_to_new()
        course.save()
    messages.success(request, ungettext("Successfully reverted %(courses)d course to new.",
        "Successfully reverted %(courses)d courses to new.", len(courses)) % {'courses': len(courses)})


def helper_semester_course_operation_prepare(request, courses, template):
    for course in courses:
        course.ready_for_editors()
        course.save()
    messages.success(request, ungettext("Successfully enabled %(courses)d course for editor review.",
        "Successfully enabled %(courses)d courses for editor review.", len(courses)) % {'courses': len(courses)})
    if template:
        EmailTemplate.send_to_users_in_courses(template, courses, [EmailTemplate.EDITORS], use_cc=True, request=request)


def helper_semester_course_operation_approve(request, courses):
    for course in courses:
        course.staff_approve()
        course.save()
    messages.success(request, ungettext("Successfully approved %(courses)d course.",
        "Successfully approved %(courses)d courses.", len(courses)) % {'courses': len(courses)})


def helper_semester_course_operation_start(request, courses, template):
    for course in courses:
        course.vote_start_date = datetime.date.today()
        course.evaluation_begin()
        course.save()
    messages.success(request, ungettext("Successfully started evaluation for %(courses)d course.",
        "Successfully started evaluation for %(courses)d courses.", len(courses)) % {'courses': len(courses)})
    if template:
        EmailTemplate.send_to_users_in_courses(template, courses, [EmailTemplate.ALL_PARTICIPANTS], use_cc=False, request=request)


def helper_semester_course_operation_publish(request, courses, template):
    for course in courses:
        course.publish()
        course.save()
    messages.success(request, ungettext("Successfully published %(courses)d course.",
        "Successfully published %(courses)d courses.", len(courses)) % {'courses': len(courses)})
    if template:
        send_publish_notifications(courses, template)


def helper_semester_course_operation_unpublish(request, courses):
    for course in courses:
        course.unpublish()
        course.save()
    messages.success(request, ungettext("Successfully unpublished %(courses)d course.",
        "Successfully unpublished %(courses)d courses.", len(courses)) % {'courses': len(courses)})


@staff_required
def semester_create(request):
    form = SemesterForm(request.POST or None)

    if form.is_valid():
        semester = form.save()
        delete_navbar_cache()

        messages.success(request, _("Successfully created semester."))
        return redirect('staff:semester_view', semester.id)
    else:
        return render(request, "staff_semester_form.html", dict(form=form))


@staff_required
def semester_edit(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    form = SemesterForm(request.POST or None, instance=semester)

    if form.is_valid():
        semester = form.save()

        messages.success(request, _("Successfully updated semester."))
        return redirect('staff:semester_view', semester.id)
    else:
        return render(request, "staff_semester_form.html", dict(semester=semester, form=form))


@require_POST
@staff_required
def semester_delete(request):
    semester_id = request.POST.get("semester_id")
    semester = get_object_or_404(Semester, id=semester_id)

    if not semester.can_staff_delete:
        raise SuspiciousOperation("Deleting semester not allowed")
    semester.delete()
    delete_navbar_cache()
    return HttpResponse()  # 200 OK


@staff_required
def semester_import(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    raise_permission_denied_if_archived(semester)

    excel_form = ImportForm(request.POST or None, request.FILES or None)

    errors = []
    warnings = {}
    success_messages = []

    if request.method == "POST":
        operation = request.POST.get('operation')
        if operation not in ('test', 'import'):
            raise SuspiciousOperation("Invalid POST operation")

        test_run = operation == 'test'
        import_run = operation == 'import'

        if test_run:
            delete_import_file(request.user.id)  # remove old file if still exists
            excel_form.excel_file_required = True
            if excel_form.is_valid():
                excel_file = excel_form.cleaned_data['excel_file']
                file_content = excel_file.read()
                success_messages, warnings, errors = EnrollmentImporter.process(file_content, semester, None, None, test_run)
                if not errors:
                    save_import_file(excel_file, request.user.id)

        elif import_run:
            file_content = get_import_file_content_or_raise(request.user.id)
            excel_form.vote_dates_required = True
            if excel_form.is_valid():
                vote_start_date = excel_form.cleaned_data['vote_start_date']
                vote_end_date = excel_form.cleaned_data['vote_end_date']
                success_messages, warnings, __ = EnrollmentImporter.process(file_content, semester, vote_start_date, vote_end_date, test_run)
                forward_messages(request, success_messages, warnings)
                delete_import_file(request.user.id)
                return redirect('staff:semester_view', semester_id)

    test_passed = import_file_exists(request.user.id)
    # casting warnings to a normal dict is necessary for the template to iterate over it.
    return render(request, "staff_semester_import.html", dict(semester=semester,
        success_messages=success_messages, errors=errors, warnings=dict(warnings),
        excel_form=excel_form, test_passed=test_passed))


@staff_required
def semester_export(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)

    ExportSheetFormset = formset_factory(form=ExportSheetForm, can_delete=True, extra=0, min_num=1, validate_min=True)
    formset = ExportSheetFormset(request.POST or None, form_kwargs={'semester': semester})

    if formset.is_valid():
        include_not_enough_answers = request.POST.get('include_not_enough_answers') == 'on'
        include_unpublished = request.POST.get('include_unpublished') == 'on'
        course_types_list = []
        for form in formset:
            if 'selected_course_types' in form.cleaned_data:
                course_types_list.append(form.cleaned_data['selected_course_types'])

        filename = "Evaluation-{}-{}.xls".format(semester.name, get_language())
        response = HttpResponse(content_type="application/vnd.ms-excel")
        response["Content-Disposition"] = "attachment; filename=\"{}\"".format(filename)
        ExcelExporter(semester).export(response, course_types_list, include_not_enough_answers, include_unpublished)
        return response
    else:
        return render(request, "staff_semester_export.html", dict(semester=semester, formset=formset))


@staff_required
def semester_raw_export(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)

    filename = "Evaluation-{}-{}_raw.csv".format(semester.name, get_language())
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = "attachment; filename=\"{}\"".format(filename)

    writer = csv.writer(response, delimiter=";")
    writer.writerow([_('Name'), _('Degrees'), _('Type'), _('Single result'), _('State'), _('#Voters'),
        _('#Participants'), _('#Comments'), _('Average grade')])
    for course in semester.course_set.all():
        degrees = ", ".join([degree.name for degree in course.degrees.all()])
        course.avg_grade, course.avg_deviation = calculate_average_grades_and_deviation(course)
        if course.state in ['evaluated', 'reviewed', 'published'] and course.avg_grade is not None:
            avg_grade = "{:.1f}".format(course.avg_grade)
        else:
            avg_grade = ""
        writer.writerow([course.name, degrees, course.type.name, course.is_single_result, course.state,
            course.num_voters, course.num_participants, course.textanswer_set.count(), avg_grade])

    return response


@staff_required
def semester_participation_export(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    participants = UserProfile.objects.filter(courses_participating_in__semester=semester).distinct().order_by("username")

    filename = "Evaluation-{}-{}_participation.csv".format(semester.name, get_language())
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = "attachment; filename=\"{}\"".format(filename)

    writer = csv.writer(response, delimiter=";")
    writer.writerow([_('Username'), _('Can use reward points'), _('#Required courses voted for'),
        _('#Required courses'), _('#Optional courses voted for'), _('#Optional courses'), _('Earned reward points')])
    for participant in participants:
        number_of_required_courses = semester.course_set.filter(participants=participant, is_required_for_reward=True).count()
        number_of_required_courses_voted_for = semester.course_set.filter(voters=participant, is_required_for_reward=True).count()
        number_of_optional_courses = semester.course_set.filter(participants=participant, is_required_for_reward=False).count()
        number_of_optional_courses_voted_for = semester.course_set.filter(voters=participant, is_required_for_reward=False).count()
        earned_reward_points = RewardPointGranting.objects.filter(semester=semester, user_profile=participant).exists()
        writer.writerow([
            participant.username, can_user_use_reward_points(participant), number_of_required_courses_voted_for,
            number_of_required_courses, number_of_optional_courses_voted_for, number_of_optional_courses,
            earned_reward_points
        ])

    return response


@staff_required
def semester_questionnaire_assign(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    raise_permission_denied_if_archived(semester)
    courses = semester.course_set.filter(state='new')
    course_types = CourseType.objects.filter(courses__in=courses)
    form = QuestionnairesAssignForm(request.POST or None, course_types=course_types)

    if form.is_valid():
        for course in courses:
            if form.cleaned_data[course.type.name]:
                course.general_contribution.questionnaires.set(form.cleaned_data[course.type.name])
            if form.cleaned_data['Responsible contributor']:
                course.contributions.get(responsible=True).questionnaires = form.cleaned_data['Responsible contributor']
            course.save()

        messages.success(request, _("Successfully assigned questionnaires."))
        return redirect('staff:semester_view', semester_id)
    else:
        return render(request, "staff_semester_questionnaire_assign_form.html", dict(semester=semester, form=form))


@staff_required
def semester_lottery(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)

    form = LotteryForm(request.POST or None)

    if form.is_valid():
        eligible = []

        # find all users who have voted on all of their courses
        for user in UserProfile.objects.all():
            courses = user.courses_participating_in.filter(semester=semester, state__in=['in_evaluation', 'evaluated', 'reviewed', 'published'])
            if not courses.exists():
                # user was not participating in any course in this semester
                continue
            if not courses.exclude(voters=user).exists():
                eligible.append(user)

        winners = random.sample(eligible, min([form.cleaned_data['number_of_winners'], len(eligible)]))
    else:
        eligible = None
        winners = None

    template_data = dict(semester=semester, form=form, eligible=eligible, winners=winners)
    return render(request, "staff_semester_lottery.html", template_data)


@staff_required
def semester_todo(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)

    courses = semester.course_set.filter(state__in=['prepared', 'editor_approved']).all().prefetch_related("degrees")

    prepared_courses = semester.course_set.filter(state__in=['prepared']).all()
    responsibles = (course.responsible_contributor for course in prepared_courses)
    responsibles = list(set(responsibles))
    responsibles.sort(key=lambda responsible: (responsible.last_name, responsible.first_name))

    responsible_list = [(responsible, [course for course in courses if course.responsible_contributor.id == responsible.id], responsible.delegates.all()) for responsible in responsibles]

    template_data = dict(semester=semester, responsible_list=responsible_list)
    return render(request, "staff_semester_todo.html", template_data)


@require_POST
@staff_required
def semester_archive(request):
    semester_id = request.POST.get("semester_id")
    semester = get_object_or_404(Semester, id=semester_id)

    if not semester.is_archiveable:
        raise SuspiciousOperation("Archiving semester not allowed")
    semester.archive()
    return HttpResponse()  # 200 OK


@staff_required
def course_create(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    raise_permission_denied_if_archived(semester)

    course = Course(semester=semester)
    InlineContributionFormset = inlineformset_factory(Course, Contribution, formset=ContributionFormSet, form=ContributionForm, extra=1)

    form = CourseForm(request.POST or None, instance=course)
    formset = InlineContributionFormset(request.POST or None, instance=course, form_kwargs={'course': course})

    if form.is_valid() and formset.is_valid():
        form.save(user=request.user)
        formset.save()

        messages.success(request, _("Successfully created course."))
        return redirect('staff:semester_view', semester_id)
    else:
        return render(request, "staff_course_form.html", dict(semester=semester, form=form, formset=formset, staff=True, editable=True, state=""))


@staff_required
def single_result_create(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    raise_permission_denied_if_archived(semester)

    course = Course(semester=semester)

    form = SingleResultForm(request.POST or None, instance=course)

    if form.is_valid():
        form.save(user=request.user)

        messages.success(request, _("Successfully created single result."))
        return redirect('staff:semester_view', semester_id)
    else:
        return render(request, "staff_single_result_form.html", dict(semester=semester, form=form))


@staff_required
def course_edit(request, semester_id, course_id):
    semester = get_object_or_404(Semester, id=semester_id)
    course = get_object_or_404(Course, id=course_id, semester=semester)

    if course.is_single_result:
        return helper_single_result_edit(request, semester, course)
    else:
        return helper_course_edit(request, semester, course)


@staff_required
def helper_course_edit(request, semester, course):
    InlineContributionFormset = inlineformset_factory(Course, Contribution, formset=ContributionFormSet, form=ContributionForm, extra=1)

    form = CourseForm(request.POST or None, instance=course)
    formset = InlineContributionFormset(request.POST or None, instance=course, form_kwargs={'course': course})
    editable = course.can_staff_edit

    operation = request.POST.get('operation')

    if form.is_valid() and formset.is_valid():
        if operation not in ('save', 'approve'):
            raise SuspiciousOperation("Invalid POST operation")

        if not course.can_staff_edit or course.is_archived:
            raise SuspiciousOperation("Modifying this course is not allowed.")

        if course.state in ['evaluated', 'reviewed'] and course.is_in_evaluation_period:
            course.reopen_evaluation()
        form.save(user=request.user)
        formset.save()

        if operation == 'approve':
            # approve course
            course.staff_approve()
            course.save()
            messages.success(request, _("Successfully updated and approved course."))
        else:
            messages.success(request, _("Successfully updated course."))

        return custom_redirect('staff:semester_view', semester.id)
    else:
        if form.errors or formset.errors:
            messages.error(request, _("The form was not saved. Please resolve the errors shown below."))
        sort_formset(request, formset)
        template_data = dict(course=course, semester=semester, form=form, formset=formset, staff=True, state=course.state, editable=editable)
        return render(request, "staff_course_form.html", template_data)


@staff_required
def helper_single_result_edit(request, semester, course):
    form = SingleResultForm(request.POST or None, instance=course)

    if form.is_valid():
        if not course.can_staff_edit or course.is_archived:
            raise SuspiciousOperation("Modifying this course is not allowed.")

        form.save(user=request.user)

        messages.success(request, _("Successfully created single result."))
        return redirect('staff:semester_view', semester.id)
    else:
        return render(request, "staff_single_result_form.html", dict(semester=semester, form=form))


@require_POST
@staff_required
def course_delete(request):
    course_id = request.POST.get("course_id")
    course = get_object_or_404(Course, id=course_id)

    if not course.can_staff_delete:
        raise SuspiciousOperation("Deleting course not allowed")
    course.delete()
    return HttpResponse()  # 200 OK


@staff_required
def course_email(request, semester_id, course_id):
    semester = get_object_or_404(Semester, id=semester_id)
    course = get_object_or_404(Course, id=course_id, semester=semester)
    form = CourseEmailForm(request.POST or None, instance=course, export='export' in request.POST)

    if form.is_valid():
        if form.export:
            email_addresses = '; '.join(form.email_addresses())
            messages.info(request, _('Recipients: ') + '\n' + email_addresses)
            return render(request, "staff_course_email.html", dict(semester=semester, course=course, form=form))
        form.send(request)
        messages.success(request, _("Successfully sent emails for '%s'.") % course.name)
        return custom_redirect('staff:semester_view', semester_id)
    else:
        return render(request, "staff_course_email.html", dict(semester=semester, course=course, form=form))


@staff_required
def course_participant_import(request, semester_id, course_id):
    semester = get_object_or_404(Semester, id=semester_id)
    course = get_object_or_404(Course, id=course_id, semester=semester)
    raise_permission_denied_if_archived(course)

    excel_form = UserImportForm(request.POST or None, request.FILES or None)
    copy_form = CourseParticipantCopyForm(request.POST or None)

    errors = []
    warnings = {}
    success_messages = []

    if request.method == "POST":
        operation = request.POST.get('operation')

        if operation not in ('test', 'import', 'copy'):
            raise SuspiciousOperation("Invalid POST operation")

        test_run = operation == 'test'
        import_run = operation == 'import'
        copy_run = operation == 'copy'

        if test_run:
            delete_import_file(request.user.id)  # remove old file if still exists
            excel_form.excel_file_required = True
            if excel_form.is_valid():
                excel_file = excel_form.cleaned_data['excel_file']
                file_content = excel_file.read()
                # if on a test run, the process method will not return a list of users that would be
                # imported so there is currently no way to show how many users would be imported.
                __, success_messages, warnings, errors = UserImporter.process(file_content, test_run)
                if not errors:
                    save_import_file(excel_file, request.user.id)

        elif import_run:
            file_content = get_import_file_content_or_raise(request.user.id)
            imported_users, success_messages, warnings, __ = UserImporter.process(file_content, test_run)
            delete_import_file(request.user.id)
            course.participants.add(*imported_users)
            success_messages.append(("{} Participants added to course {}").format(len(imported_users), course.name))
            forward_messages(request, success_messages, warnings)
            return redirect('staff:semester_view', semester_id)

        elif copy_run:
            copy_form.course_selection_required = True
            if copy_form.is_valid():
                import_course = copy_form.cleaned_data['course']
                imported_users = import_course.participants.all()
                course.participants.add(*imported_users)
                messages.success(request, "%d Participants added to course %s" % (len(imported_users), course.name))
                return redirect('staff:semester_view', semester_id)

    test_passed = import_file_exists(request.user.id)
    # casting warnings to a normal dict is necessary for the template to iterate over it.
    return render(request, "staff_course_participant_import.html", dict(semester=semester, course=course,
        excel_form=excel_form, copy_form=copy_form, success_messages=success_messages,
        warnings=dict(warnings), errors=errors, participant_test_passed=test_passed))


@reviewer_required
def course_comments(request, semester_id, course_id):
    semester = get_object_or_404(Semester, id=semester_id)
    course = get_object_or_404(Course, id=course_id, semester=semester)

    filter = request.GET.get('filter', None)
    if filter is None:  # if no parameter is given take session value
        filter = request.session.get('filter_comments', False)  # defaults to False if no session value exists
    else:
        filter = {'true': True, 'false': False}.get(filter.lower())  # convert parameter to boolean
    request.session['filter_comments'] = filter  # store value for session

    filter_states = [TextAnswer.NOT_REVIEWED] if filter else None

    course_sections = []
    contributor_sections = []
    for questionnaire, contribution in questionnaires_and_contributions(course):
        text_results = []
        for question in questionnaire.text_questions:
            answers = get_textanswers(contribution, question, filter_states)
            if answers:
                text_results.append(TextResult(question=question, answers=answers))
        if not text_results:
            continue
        section_list = course_sections if contribution.is_general else contributor_sections
        section_list.append(CommentSection(questionnaire, contribution.contributor, contribution.label, contribution.responsible, text_results))

    template_data = dict(semester=semester, course=course, course_sections=course_sections, contributor_sections=contributor_sections, filter=filter)
    return render(request, "staff_course_comments.html", template_data)


@require_POST
@reviewer_required
def course_comments_update_publish(request):
    comment_id = request.POST["id"]
    action = request.POST["action"]
    course_id = request.POST["course_id"]

    course = Course.objects.get(pk=course_id)
    answer = TextAnswer.objects.get(pk=comment_id)

    if action == 'publish':
        answer.publish()
    elif action == 'make_private':
        answer.make_private()
    elif action == 'hide':
        answer.hide()
    elif action == 'unreview':
        answer.unreview()
    else:
        return HttpResponse(status=400)  # 400 Bad Request
    answer.save()

    if course.state == "evaluated" and course.is_fully_reviewed:
        course.review_finished()
        course.save()
    if course.state == "reviewed" and not course.is_fully_reviewed:
        course.reopen_review()
        course.save()

    return HttpResponse()  # 200 OK


@reviewer_required
def course_comment_edit(request, semester_id, course_id, text_answer_id):
    semester = get_object_or_404(Semester, id=semester_id)
    course = get_object_or_404(Course, id=course_id, semester=semester)
    text_answer = get_object_or_404(TextAnswer, id=text_answer_id, contribution__course=course)
    reviewed_answer = text_answer.reviewed_answer
    if reviewed_answer is None:
        reviewed_answer = text_answer.original_answer
    form = TextAnswerForm(request.POST or None, instance=text_answer, initial={'reviewed_answer': reviewed_answer})

    if form.is_valid():
        form.save()
        # jump to edited answer
        url = reverse('staff:course_comments', args=[semester_id, course_id]) + '#' + str(text_answer.id)
        return HttpResponseRedirect(url)

    template_data = dict(semester=semester, course=course, form=form, text_answer=text_answer)
    return render(request, "staff_course_comment_edit.html", template_data)


@staff_required
def course_preview(request, semester_id, course_id):
    semester = get_object_or_404(Semester, id=semester_id)
    course = get_object_or_404(Course, id=course_id, semester=semester)

    return vote_preview(request, course)


@staff_required
def questionnaire_index(request):
    questionnaires = Questionnaire.objects.all()
    course_questionnaires = questionnaires.filter(is_for_contributors=False)
    contributor_questionnaires = questionnaires.filter(is_for_contributors=True)
    template_data = dict(course_questionnaires=course_questionnaires, contributor_questionnaires=contributor_questionnaires)
    return render(request, "staff_questionnaire_index.html", template_data)


@staff_required
def questionnaire_view(request, questionnaire_id):
    questionnaire = get_object_or_404(Questionnaire, id=questionnaire_id)

    # build forms
    contribution = Contribution(contributor=request.user)
    form = QuestionsForm(request.POST or None, contribution=contribution, questionnaire=questionnaire)

    return render(request, "staff_questionnaire_view.html", dict(forms=[form], questionnaire=questionnaire))


@staff_required
def questionnaire_create(request):
    questionnaire = Questionnaire()
    InlineQuestionFormset = inlineformset_factory(Questionnaire, Question, formset=AtLeastOneFormSet, form=QuestionForm, extra=1, exclude=('questionnaire',))

    form = QuestionnaireForm(request.POST or None, instance=questionnaire)
    formset = InlineQuestionFormset(request.POST or None, instance=questionnaire)

    if form.is_valid() and formset.is_valid():
        new_questionnaire = form.save(commit=False)
        # set index according to existing questionnaires
        new_questionnaire.index = Questionnaire.objects.all().aggregate(Max('index'))['index__max'] + 1
        new_questionnaire.save()
        form.save_m2m()

        formset.save()

        messages.success(request, _("Successfully created questionnaire."))
        return redirect('staff:questionnaire_index')
    else:
        return render(request, "staff_questionnaire_form.html", dict(form=form, formset=formset, editable=True))


def make_questionnaire_edit_forms(request, questionnaire, editable):
    if editable:
        InlineQuestionFormset = inlineformset_factory(Questionnaire, Question, formset=AtLeastOneFormSet, form=QuestionForm, extra=1, exclude=('questionnaire',))
    else:
        question_count = questionnaire.question_set.count()
        InlineQuestionFormset = inlineformset_factory(Questionnaire, Question, formset=AtLeastOneFormSet, form=QuestionForm, extra=0, exclude=('questionnaire',),
                                                      can_delete=False, max_num=question_count, validate_max=True, min_num=question_count, validate_min=True)

    form = QuestionnaireForm(request.POST or None, instance=questionnaire)
    formset = InlineQuestionFormset(request.POST or None, instance=questionnaire)

    if not editable:
        editable_fields = ['staff_only', 'obsolete', 'name_de', 'name_en', 'description_de', 'description_en']
        for name, field in form.fields.items():
            if name not in editable_fields:
                field.disabled = True
        for question_form in formset.forms:
            for name, field in question_form.fields.items():
                if name is not 'id':
                    field.disabled = True

    return form, formset


@staff_required
def questionnaire_edit(request, questionnaire_id):
    questionnaire = get_object_or_404(Questionnaire, id=questionnaire_id)
    editable = questionnaire.can_staff_edit

    form, formset = make_questionnaire_edit_forms(request, questionnaire, editable)

    if form.is_valid() and formset.is_valid():
        form.save()
        if editable:
            formset.save()

        messages.success(request, _("Successfully updated questionnaire."))
        return redirect('staff:questionnaire_index')
    else:
        if not editable:
            messages.info(request, _("Some fields are disabled as this questionnaire is already in use."))
        template_data = dict(questionnaire=questionnaire, form=form, formset=formset, editable=editable)
        return render(request, "staff_questionnaire_form.html", template_data)


def get_identical_form_and_formset(questionnaire):
    """
    Generates a Questionnaire creation form and formset filled out like the already exisiting Questionnaire
    specified in questionnaire_id. Used for copying and creating of new versions.
    """
    inline_question_formset = inlineformset_factory(Questionnaire, Question, formset=AtLeastOneFormSet, form=QuestionForm, extra=1, exclude=('questionnaire',))

    form = QuestionnaireForm(instance=questionnaire)
    return form, inline_question_formset(instance=questionnaire, queryset=questionnaire.question_set.all())


@staff_required
def questionnaire_copy(request, questionnaire_id):
    copied_questionnaire = get_object_or_404(Questionnaire, id=questionnaire_id)

    if request.method == "POST":
        questionnaire = Questionnaire()
        InlineQuestionFormset = inlineformset_factory(Questionnaire, Question, formset=AtLeastOneFormSet, form=QuestionForm, extra=1, exclude=('questionnaire',))

        form = QuestionnaireForm(request.POST, instance=questionnaire)
        formset = InlineQuestionFormset(request.POST.copy(), instance=questionnaire, save_as_new=True)

        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()

            messages.success(request, _("Successfully created questionnaire."))
            return redirect('staff:questionnaire_index')
        else:
            return render(request, "staff_questionnaire_form.html", dict(form=form, formset=formset, editable=True))
    else:
        form, formset = get_identical_form_and_formset(copied_questionnaire)
        return render(request, "staff_questionnaire_form.html", dict(form=form, formset=formset, editable=True))


@staff_required
def questionnaire_new_version(request, questionnaire_id):
    old_questionnaire = get_object_or_404(Questionnaire, id=questionnaire_id)

    if old_questionnaire.obsolete:
        raise PermissionDenied

    # Check if we can use the old name with the current time stamp.
    timestamp = datetime.date.today()
    new_name_de = '{} (until {})'.format(old_questionnaire.name_de, str(timestamp))
    new_name_en = '{} (until {})'.format(old_questionnaire.name_en, str(timestamp))

    # If not, redirect back and suggest to edit the already created version.
    if Questionnaire.objects.filter(Q(name_de=new_name_de) | Q(name_en=new_name_en)):
        messages.error(request, _("Questionnaire creation aborted. A new version was already created today."))
        return redirect('staff:questionnaire_index')

    if request.method == "POST":
        questionnaire = Questionnaire()
        InlineQuestionFormset = inlineformset_factory(Questionnaire, Question, formset=AtLeastOneFormSet,
                                                      form=QuestionForm, extra=1, exclude=('questionnaire',))

        form = QuestionnaireForm(request.POST, instance=questionnaire)
        formset = InlineQuestionFormset(request.POST.copy(), instance=questionnaire, save_as_new=True)

        try:
            with transaction.atomic():
                # Change old name before checking Form.
                old_questionnaire.name_de = new_name_de
                old_questionnaire.name_en = new_name_en
                old_questionnaire.obsolete = True
                old_questionnaire.save()

                if form.is_valid() and formset.is_valid():
                    form.save()
                    formset.save()
                    messages.success(request, _("Successfully created questionnaire."))
                    return redirect('staff:questionnaire_index')
                else:
                    raise IntegrityError
        except IntegrityError:
            return render(request, "staff_questionnaire_form.html", dict(form=form, formset=formset, editable=True))
    else:
        form, formset = get_identical_form_and_formset(old_questionnaire)
        return render(request, "staff_questionnaire_form.html", dict(form=form, formset=formset, editable=True))


@require_POST
@staff_required
def questionnaire_delete(request):
    questionnaire_id = request.POST.get("questionnaire_id")
    questionnaire = get_object_or_404(Questionnaire, id=questionnaire_id)

    if not questionnaire.can_staff_delete:
        raise SuspiciousOperation("Deleting questionnaire not allowed")
    questionnaire.delete()
    return HttpResponse()  # 200 OK


@require_POST
@staff_required
def questionnaire_update_indices(request):
    updated_indices = request.POST
    for questionnaire_id, new_index in updated_indices.items():
        questionnaire = Questionnaire.objects.get(pk=questionnaire_id)
        questionnaire.index = new_index
        questionnaire.save()
    return HttpResponse()


@staff_required
def degree_index(request):
    degrees = Degree.objects.all()

    DegreeFormset = modelformset_factory(Degree, form=DegreeForm, can_delete=True, extra=1)
    formset = DegreeFormset(request.POST or None, queryset=degrees)

    if formset.is_valid():
        formset.save()

        messages.success(request, _("Successfully updated the degrees."))
        return custom_redirect('staff:degree_index')
    else:
        return render(request, "staff_degree_index.html", dict(formset=formset, degrees=degrees))


@staff_required
def course_type_index(request):
    course_types = CourseType.objects.all()

    CourseTypeFormset = modelformset_factory(CourseType, form=CourseTypeForm, can_delete=True, extra=1)
    formset = CourseTypeFormset(request.POST or None, queryset=course_types)

    if formset.is_valid():
        formset.save()

        messages.success(request, _("Successfully updated the course types."))
        return custom_redirect('staff:course_type_index')
    else:
        return render(request, "staff_course_type_index.html", dict(formset=formset))


@staff_required
def course_type_merge_selection(request):
    form = CourseTypeMergeSelectionForm(request.POST or None)

    if form.is_valid():
        main_type = form.cleaned_data['main_type']
        other_type = form.cleaned_data['other_type']
        return redirect('staff:course_type_merge', main_type.id, other_type.id)
    else:
        return render(request, "staff_course_type_merge_selection.html", dict(form=form))


@staff_required
def course_type_merge(request, main_type_id, other_type_id):
    main_type = get_object_or_404(CourseType, id=main_type_id)
    other_type = get_object_or_404(CourseType, id=other_type_id)

    if request.method == 'POST':
        Course.objects.filter(type=other_type).update(type=main_type)
        other_type.delete()
        messages.success(request, _("Successfully merged course types."))
        return redirect('staff:course_type_index')
    else:
        courses_with_other_type = Course.objects.filter(type=other_type).order_by('semester__created_at', 'name_de')
        return render(request, "staff_course_type_merge.html",
            dict(main_type=main_type, other_type=other_type, courses_with_other_type=courses_with_other_type))


@staff_required
def user_index(request):
    users = (UserProfile.objects.all()
        # the following six annotations basically add two bools indicating whether each user is part of a group or not.
        .annotate(staff_group_count=Sum(Case(When(groups__name="Staff", then=1), output_field=IntegerField())))
        .annotate(is_staff=ExpressionWrapper(Q(staff_group_count__exact=1), output_field=BooleanField()))
        .annotate(reviewer_group_count=Sum(Case(When(groups__name="Reviewer", then=1), output_field=IntegerField())))
        .annotate(is_reviewer=ExpressionWrapper(Q(reviewer_group_count__exact=1), output_field=BooleanField()))
        .annotate(grade_publisher_group_count=Sum(Case(When(groups__name="Grade publisher", then=1), output_field=IntegerField())))
        .annotate(is_grade_publisher=ExpressionWrapper(Q(grade_publisher_group_count__exact=1), output_field=BooleanField()))
        .prefetch_related('contributions', 'courses_participating_in', 'courses_participating_in__semester', 'represented_users', 'ccing_users'))

    return render(request, "staff_user_index.html", dict(users=users))


@staff_required
def user_create(request):
    form = UserForm(request.POST or None, instance=UserProfile())

    if form.is_valid():
        form.save()
        messages.success(request, _("Successfully created user."))
        return redirect('staff:user_index')
    else:
        return render(request, "staff_user_form.html", dict(form=form))


@staff_required
def user_import(request):
    excel_form = UserImportForm(request.POST or None, request.FILES or None)

    errors = []
    warnings = {}
    success_messages = []

    if request.method == "POST":
        operation = request.POST.get('operation')
        if operation not in ('test', 'import'):
            raise SuspiciousOperation("Invalid POST operation")

        test_run = operation == 'test'
        import_run = operation == 'import'

        if test_run:
            delete_import_file(request.user.id)  # remove old file if still exists
            excel_form.excel_file_required = True
            if excel_form.is_valid():
                excel_file = excel_form.cleaned_data['excel_file']
                file_content = excel_file.read()
                __, success_messages, warnings, errors = UserImporter.process(file_content, test_run)
                if not errors:
                    save_import_file(excel_file, request.user.id)

        elif import_run:
            file_content = get_import_file_content_or_raise(request.user.id)
            __, success_messages, warnings, __ = UserImporter.process(file_content, test_run)
            forward_messages(request, success_messages, warnings)
            delete_import_file(request.user.id)
            return redirect('staff:user_index')

    test_passed = import_file_exists(request.user.id)
    # casting warnings to a normal dict is necessary for the template to iterate over it.
    return render(request, "staff_user_import.html", dict(excel_form=excel_form,
        success_messages=success_messages, warnings=dict(warnings), errors=errors, test_passed=test_passed))


@staff_required
def user_edit(request, user_id):
    user = get_object_or_404(UserProfile, id=user_id)
    form = UserForm(request.POST or None, request.FILES or None, instance=user)

    courses_contributing_to = Course.objects.filter(semester=Semester.active_semester(), contributions__contributor=user)

    if form.is_valid():
        form.save()
        messages.success(request, _("Successfully updated user."))
        return redirect('staff:user_index')
    else:
        return render(request, "staff_user_form.html", dict(form=form, courses_contributing_to=courses_contributing_to))


@require_POST
@staff_required
def user_delete(request):
    user_id = request.POST.get("user_id")
    user = get_object_or_404(UserProfile, id=user_id)

    if not user.can_staff_delete:
        raise SuspiciousOperation("Deleting user not allowed")
    user.delete()
    return HttpResponse()  # 200 OK


@staff_required
def user_bulk_delete(request):
    form = UserBulkDeleteForm(request.POST or None, request.FILES or None)
    operation = request.POST.get('operation')

    if form.is_valid():
        if operation not in ('test', 'bulk_delete'):
            raise SuspiciousOperation("Invalid POST operation")

        test_run = operation == 'test'
        username_file = form.cleaned_data['username_file']
        bulk_delete_users(request, username_file, test_run)

        if test_run:
            return render(request, "staff_user_bulk_delete.html", dict(form=form))
        return redirect('staff:user_index')
    else:
        return render(request, "staff_user_bulk_delete.html", dict(form=form))


@staff_required
def user_merge_selection(request):
    form = UserMergeSelectionForm(request.POST or None)

    if form.is_valid():
        main_user = form.cleaned_data['main_user']
        other_user = form.cleaned_data['other_user']
        return redirect('staff:user_merge', main_user.id, other_user.id)
    else:
        return render(request, "staff_user_merge_selection.html", dict(form=form))


@staff_required
def user_merge(request, main_user_id, other_user_id):
    main_user = get_object_or_404(UserProfile, id=main_user_id)
    other_user = get_object_or_404(UserProfile, id=other_user_id)

    if request.method == 'POST':
        merged_user, errors, warnings = merge_users(main_user, other_user)
        if not errors:
            messages.success(request, _("Successfully merged users."))
        else:
            messages.error(request, _("Merging the users failed. No data was changed."))
        return redirect('staff:user_index')
    else:
        merged_user, errors, warnings = merge_users(main_user, other_user, preview=True)
        return render(request, "staff_user_merge.html", dict(main_user=main_user, other_user=other_user, merged_user=merged_user, errors=errors, warnings=warnings))


@staff_required
def template_edit(request, template_id):
    template = get_object_or_404(EmailTemplate, id=template_id)
    form = EmailTemplateForm(request.POST or None, request.FILES or None, instance=template)

    if form.is_valid():
        form.save()

        messages.success(request, _("Successfully updated template."))
        return redirect('staff:index')
    else:
        return render(request, "staff_template_form.html", dict(form=form, template=template))


@staff_required
def faq_index(request):
    sections = FaqSection.objects.all()

    SectionFormset = modelformset_factory(FaqSection, form=FaqSectionForm, can_delete=True, extra=1)
    formset = SectionFormset(request.POST or None, queryset=sections)

    if formset.is_valid():
        formset.save()

        messages.success(request, _("Successfully updated the FAQ sections."))
        return custom_redirect('staff:faq_index')
    else:
        return render(request, "staff_faq_index.html", dict(formset=formset, sections=sections))


@staff_required
def faq_section(request, section_id):
    section = get_object_or_404(FaqSection, id=section_id)
    questions = FaqQuestion.objects.filter(section=section)

    InlineQuestionFormset = inlineformset_factory(FaqSection, FaqQuestion, form=FaqQuestionForm, can_delete=True, extra=1, exclude=('section',))
    formset = InlineQuestionFormset(request.POST or None, queryset=questions, instance=section)

    if formset.is_valid():
        formset.save()

        messages.success(request, _("Successfully updated the FAQ questions."))
        return custom_redirect('staff:faq_index')
    else:
        template_data = dict(formset=formset, section=section, questions=questions)
        return render(request, "staff_faq_section.html", template_data)
