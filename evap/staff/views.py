from django.contrib import messages
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.forms.models import inlineformset_factory, modelformset_factory
from django.shortcuts import get_object_or_404, redirect, render
from collections import OrderedDict
from django.utils.translation import ugettext as _
from django.utils.translation import get_language
from django.http import HttpResponse

from evap.evaluation.auth import staff_required
from evap.evaluation.models import Contribution, Course, Question, Questionnaire, Semester, \
                                   TextAnswer, UserProfile, FaqSection, FaqQuestion, EmailTemplate
from evap.evaluation.tools import questionnaires_and_contributions, STATES_ORDERED, user_publish_notifications
from evap.staff.forms import ContributionForm, AtLeastOneFormSet, ReviewTextAnswerForm, CourseForm, \
                           CourseEmailForm, EmailTemplateForm, IdLessQuestionFormSet, ImportForm, \
                           LotteryForm, QuestionForm, QuestionnaireForm, QuestionnairesAssignForm, \
                           SelectCourseForm, SemesterForm, UserForm, ContributionFormSet, \
                           FaqSectionForm, FaqQuestionForm, UserImportForm
from evap.staff.importers import EnrollmentImporter, UserImporter
from evap.staff.tools import custom_redirect
from evap.student.views import vote_preview
from evap.student.forms import QuestionsForm

from evap.rewards.models import SemesterActivation
from evap.rewards.tools import is_semester_activated

import random


def get_tab(request):
    return request.GET.get('tab', '1') if request.GET else request.POST.get('tab', '1')


@staff_required
def index(request):
    template_data = dict(semesters=Semester.objects.all(),
                         questionnaires_courses=Questionnaire.objects.filter(obsolete=False,is_for_contributors=False),
                         questionnaire_contributors=Questionnaire.objects.filter(obsolete=False,is_for_contributors=True),
                         templates=EmailTemplate.objects.all(),
                         sections=FaqSection.objects.all(),
                         disable_breadcrumb_staff=True)
    return render(request, "staff_index.html", template_data)


@staff_required
def semester_view(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    try:
        tab = int(get_tab(request))
    except ValueError:
        tab = 1

    rewards_active = is_semester_activated(semester)

    courses = semester.course_set.all()
    courses_by_state = []
    for state in STATES_ORDERED.keys():
        this_courses = [course for course in courses if course.state == state]
        courses_by_state.append((state, this_courses))

    template_data = dict(semester=semester, courses_by_state=courses_by_state, disable_breadcrumb_semester=True, tab=tab, rewards_active=rewards_active)
    return render(request, "staff_semester_view.html", template_data)


@staff_required
def semester_create(request):
    form = SemesterForm(request.POST or None)

    if form.is_valid():
        semester = form.save()

        messages.success(request, _("Successfully created semester."))
        return redirect('evap.staff.views.semester_view', semester.id)
    else:
        return render(request, "staff_semester_form.html", dict(form=form))


@staff_required
def semester_edit(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    form = SemesterForm(request.POST or None, instance=semester)

    if form.is_valid():
        semester = form.save()

        messages.success(request, _("Successfully updated semester."))
        return redirect('evap.staff.views.semester_view', semester.id)
    else:
        return render(request, "staff_semester_form.html", dict(semester=semester, form=form))


@staff_required
def semester_delete(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)

    if semester.can_staff_delete:
        if request.method == 'POST':
            semester.delete()
            messages.success(request, _("Successfully deleted semester."))
            return redirect('staff_root')
        else:
            return render(request, "staff_semester_delete.html", dict(semester=semester))
    else:
        messages.warning(request, _("The semester '%s' cannot be deleted, because it is still in use.") % semester.name)
        return redirect('evap.staff.views.semester_view', semester.id)


@staff_required
def semester_publish(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    courses = semester.course_set.filter(state="reviewed").all()

    forms = helper_create_grouped_course_selection_forms(courses, None, request)

    valid = helper_are_course_selection_forms_valid(forms)

    for form in forms:
        for course_id, field in form.fields.items():
            course = Course.objects.get(pk=course_id)
            field.label += " (graded)" if course.is_graded else " (not graded)" 

    if valid:
        selected_courses = []
        for form in forms:
            for course in form.selected_courses:
                course.publish()
                course.save()
                selected_courses.append(course)
        messages.success(request, _("Successfully published %d courses.") % (len(selected_courses)))

        for user, courses in user_publish_notifications(selected_courses).iteritems():
            try:
                EmailTemplate.get_publish_template().send_to_user(user, courses=list(courses))
            except Exception:
                messages.error(request, _("Could not send notification email to ") + user.username)
        
        return redirect('evap.staff.views.semester_view', semester_id)
    else:
        return render(request, "staff_semester_publish.html", dict(semester=semester, forms=forms))


@staff_required
def semester_import(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    form = ImportForm(request.POST or None, request.FILES or None)
    operation = request.POST.get('operation')

    if form.is_valid():
        if operation not in ('test', 'import'):
            raise PermissionDenied

        # extract data from form
        excel_file = form.cleaned_data['excel_file']
        vote_start_date = form.cleaned_data['vote_start_date']
        vote_end_date = form.cleaned_data['vote_end_date']

        test_run = operation == 'test'

        # parse table
        EnrollmentImporter.process(request, excel_file, semester, vote_start_date, vote_end_date, test_run)
        if test_run:
            return render(request, "staff_import.html", dict(semester=semester, form=form))
        return redirect('evap.staff.views.semester_view', semester_id)
    else:
        return render(request, "staff_import.html", dict(semester=semester, form=form))


@staff_required
def semester_assign_questionnaires(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    courses = semester.course_set.filter(state='new')
    kinds = courses.values_list('kind', flat=True).order_by().distinct()
    form = QuestionnairesAssignForm(request.POST or None, semester=semester, kinds=kinds)

    if form.is_valid():
        for course in courses:
            if form.cleaned_data[course.kind]:
                course.general_contribution.questionnaires = form.cleaned_data[course.kind]
            if form.cleaned_data['Responsible contributor']:
                course.contributions.get(responsible=True).questionnaires = form.cleaned_data['Responsible contributor']
            course.save()

        messages.success(request, _("Successfully assigned questionnaires."))
        return redirect('evap.staff.views.semester_view', semester_id)
    else:
        return render(request, "staff_semester_assign_questionnaires.html", dict(semester=semester, form=form))


@staff_required
def semester_revert_to_new(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    courses = semester.course_set.filter(state__in=['prepared']).all()

    forms = helper_create_grouped_course_selection_forms(courses, lambda course: not course.warnings(), request)

    valid = helper_are_course_selection_forms_valid(forms)

    if valid:
        count = 0
        for form in forms:
            for course in form.selected_courses:
                course.revert_to_new()
                course.save()
            count += len(form.selected_courses)

        messages.success(request, _("Successfully reverted %d courses to New.") % (count))
        return redirect('evap.staff.views.semester_view', semester_id)
    else:
        return render(request, "staff_semester_revert_to_new.html", dict(semester=semester, forms=forms))


@staff_required
def semester_approve(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    courses = semester.course_set.filter(state__in=['new', 'prepared', 'lecturerApproved']).all()

    forms = helper_create_grouped_course_selection_forms(courses, lambda course: not course.warnings(), request)

    valid = helper_are_course_selection_forms_valid(forms)

    if valid:
        count = 0
        for form in forms:
            for course in form.selected_courses:
                course.staff_approve()
                course.save()
            count += len(form.selected_courses)
        messages.success(request, _("Successfully approved %d courses.") % (count))
        return redirect('evap.staff.views.semester_view', semester_id)
    else:
        return render(request, "staff_semester_approve.html", dict(semester=semester, forms=forms))


@staff_required
def semester_contributor_ready(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    courses = semester.course_set.filter(state__in=['new', 'lecturerApproved']).all()

    forms = helper_create_grouped_course_selection_forms(courses, lambda course: not course.warnings(), request)

    valid = helper_are_course_selection_forms_valid(forms)

    if valid:
        selected_courses = []
        for form in forms:
            for course in form.selected_courses:
                course.ready_for_contributors()
                course.save()
                selected_courses.append(course)

        EmailTemplate.get_review_template().send_to_users_in_courses(selected_courses, ['editors'])

        messages.success(request, _("Successfully marked %d courses as ready for lecturer review.") % (len(selected_courses)))
        return redirect('evap.staff.views.semester_view', semester_id)
    else:
        return render(request, "staff_semester_contributor_ready.html", dict(semester=semester, forms=forms))


@staff_required
def semester_lottery(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)

    form = LotteryForm(request.POST or None)

    if form.is_valid():
        eligible = []

        # find all users who have voted on all of their courses
        for user in UserProfile.objects.all():
            courses = user.course_set.filter(semester=semester,  state__in=['inEvaluation', 'evaluated', 'reviewed', 'published'])
            if not courses.exists():
                # user was not participating in any course in this semester
                continue
            if not courses.exclude(voters=user).exists():
                eligible.append(user)

        winners = random.sample(eligible, min([form.cleaned_data['number_of_winners'], len(eligible)]))
    else:
        eligible = None
        winners = None

    template_data =dict(semester=semester, form=form, eligible=eligible, winners=winners)
    return render(request, "staff_semester_lottery.html", template_data)


@staff_required
def course_create(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    course = Course(semester=semester)
    ContributionFormset = inlineformset_factory(Course, Contribution, formset=ContributionFormSet, form=ContributionForm, extra=1, exclude=('course',))

    form = CourseForm(request.POST or None, instance=course)
    formset = ContributionFormset(request.POST or None, instance=course)

    if form.is_valid() and formset.is_valid():
        form.save(user=request.user)
        formset.save()

        messages.success(request, _("Successfully created course."))
        return redirect('evap.staff.views.semester_view', semester_id)
    else:
        return render(request, "staff_course_form.html", dict(semester=semester, form=form, formset=formset, staff=True))


@staff_required
def course_edit(request, semester_id, course_id):
    semester = get_object_or_404(Semester, id=semester_id)
    course = get_object_or_404(Course, id=course_id)
    ContributionFormset = inlineformset_factory(Course, Contribution, formset=ContributionFormSet, form=ContributionForm, extra=1, exclude=('course',))

    # check course state
    if not course.can_staff_edit():
        messages.warning(request, _("Editing not possible in current state."))
        return redirect('evap.staff.views.semester_view', semester_id)

    form = CourseForm(request.POST or None, instance=course)
    formset = ContributionFormset(request.POST or None, instance=course, queryset=course.contributions.exclude(contributor=None))

    if form.is_valid() and formset.is_valid():
        form.save(user=request.user)
        formset.save()

        messages.success(request, _("Successfully updated course."))
        return custom_redirect('evap.staff.views.semester_view', semester_id, tab=get_tab(request))
    else:
        template_data = dict(semester=semester, course=course, form=form, formset=formset, staff=True)
        return render(request, "staff_course_form.html", template_data)


@staff_required
def course_delete(request, semester_id, course_id):
    semester = get_object_or_404(Semester, id=semester_id)
    course = get_object_or_404(Course, id=course_id)

    # check course state
    if not course.can_staff_delete():
        messages.warning(request, _("The course '%s' cannot be deleted, because it is still in use.") % course.name)
        return redirect('evap.staff.views.semester_view', semester_id)

    if request.method == 'POST':
        course.delete()
        messages.success(request, _("Successfully deleted course."))
        return custom_redirect('evap.staff.views.semester_view', semester_id, tab=get_tab(request))
    else:
        return render(request, "staff_course_delete.html", dict(semester=semester, course=course))


@staff_required
def course_review(request, semester_id, course_id):
    semester = get_object_or_404(Semester, id=semester_id)
    course = get_object_or_404(Course, id=course_id)

    # check course state
    if not course.can_staff_review():
        messages.warning(request, _("Reviewing not possible in current state."))
        return redirect('evap.staff.views.semester_view', semester_id)

    review_formset = modelformset_factory(TextAnswer, form=ReviewTextAnswerForm, can_order=False, can_delete=False, extra=0)

    skipped_answers = request.POST.get("skipped_answers", "") if request.POST else request.GET.get("skipped_answers", "")
    skipped_answer_ids = [int(x) for x in skipped_answers.split(';')] if skipped_answers else []

    # compute form queryset
    form_queryset = course.textanswer_set \
        .filter(checked=False) \
        .exclude(pk__in=skipped_answer_ids) \
        .order_by('id')[:TextAnswer.elements_per_page]

    # create formset from sliced queryset
    formset = review_formset(request.POST or None, queryset=form_queryset)

    if formset.is_valid():
        count = 0
        for form in formset:
            form.instance.save()
            if form.instance.checked:
                count += 1
            else:
                skipped_answer_ids.append(form.instance.id)

        if course.state == "evaluated" and course.is_fully_checked():
            messages.success(request, _("Successfully reviewed {count} course answers for {course}. {course} is now fully reviewed.").format(count=count, course=course.name))
            course.review_finished()
            course.save()
            return custom_redirect('evap.staff.views.semester_view', semester_id, tab=get_tab(request))
        else:
            messages.success(request, _("Successfully reviewed {count} course answers for {course}.").format(count=count, course=course.name))
            operation = request.POST.get('operation')

            if operation == 'save_and_next' and not course.is_fully_checked_except(skipped_answer_ids):
                skipped_answers = ';'.join(str(x) for x in skipped_answer_ids)
                return custom_redirect('evap.staff.views.course_review', semester_id, course_id, tab=get_tab(request), skipped_answers=skipped_answers)
            else:
                return custom_redirect('evap.staff.views.semester_view', semester_id, tab=get_tab(request))
    else:
        skipped_answers = ';'.join(str(x) for x in skipped_answer_ids)
        template_data = dict(semester=semester, course=course, formset=formset, TextAnswer=TextAnswer, skipped_answers=skipped_answers, tab=get_tab(request))
        return render(request, "staff_course_review.html", template_data)


@staff_required
def course_email(request, semester_id, course_id):
    semester = get_object_or_404(Semester, id=semester_id)
    course = get_object_or_404(Course, id=course_id)
    form = CourseEmailForm(request.POST or None, instance=course)

    if form.is_valid():
        form.send()

        if form.all_recepients_reachable():
            messages.success(request, _("Successfully sent emails for '%s'.") % course.name)
        else:
            messages.warning(request, _("Successfully sent some emails for '{course}', but {count} could not be reached as they do not have an email address.").format(course=course.name, count=form.missing_email_addresses()))
        return custom_redirect('evap.staff.views.semester_view', semester_id, tab=get_tab(request))
    else:
        return render(request, "staff_course_email.html", dict(semester=semester, course=course, form=form))


@staff_required
def course_unpublish(request, semester_id, course_id):
    semester = get_object_or_404(Semester, id=semester_id)
    course = get_object_or_404(Course, id=course_id)

    # check course state
    if not course.state == "published":
        messages.warning(request, _("The course '%s' cannot be unpublished, because it is not published.") % course.name)
        return custom_redirect('evap.staff.views.semester_view', semester_id, tab=get_tab(request))

    if request.method == 'POST':
        course.revoke()
        course.save()
        return custom_redirect('evap.staff.views.semester_view', semester_id, tab=get_tab(request))
    else:
        return render(request, "staff_course_unpublish.html", dict(semester=semester, course=course))


@staff_required
def course_comments(request, semester_id, course_id):
    semester = get_object_or_404(Semester, id=semester_id)
    course = get_object_or_404(Course, id=course_id)

    textanswers = course.textanswer_set.filter(checked=True)

    textanswers_by_question = []
    for question_id in textanswers.values_list("question", flat=True).distinct():
        textanswers_by_question.append((Question.objects.get(id=question_id), textanswers.filter(question=question_id)))

    template_data = dict(semester=semester, course=course, textanswers_by_question=textanswers_by_question)
    return render(request, "staff_course_comments.html", template_data)


@staff_required
def course_preview(request, semester_id, course_id):
    semester = get_object_or_404(Semester, id=semester_id)
    course = get_object_or_404(Course, id=course_id)

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
    QuestionFormset = inlineformset_factory(Questionnaire, Question, formset=AtLeastOneFormSet, form=QuestionForm, extra=1, exclude=('questionnaire',))

    form = QuestionnaireForm(request.POST or None, instance=questionnaire)
    formset = QuestionFormset(request.POST or None, instance=questionnaire)

    if form.is_valid() and formset.is_valid():
        form.save()
        formset.save()

        messages.success(request, _("Successfully created questionnaire."))
        return redirect('evap.staff.views.questionnaire_index')
    else:
        return render(request, "staff_questionnaire_form.html", dict(form=form, formset=formset))


@staff_required
def questionnaire_edit(request, questionnaire_id):
    questionnaire = get_object_or_404(Questionnaire, id=questionnaire_id)
    QuestionFormset = inlineformset_factory(Questionnaire, Question, formset=AtLeastOneFormSet, form=QuestionForm, extra=1, exclude=('questionnaire',))

    form = QuestionnaireForm(request.POST or None, instance=questionnaire)
    formset = QuestionFormset(request.POST or None, instance=questionnaire)

    if questionnaire.obsolete:
        messages.info(request, _("Obsolete questionnaires cannot be edited."))
        return redirect('evap.staff.views.questionnaire_index')

    if form.is_valid() and formset.is_valid():
        form.save()
        formset.save()

        messages.success(request, _("Successfully updated questionnaire."))
        return redirect('evap.staff.views.questionnaire_index')
    else:
        template_data = dict(questionnaire=questionnaire, form=form, formset=formset)
        return render(request, "staff_questionnaire_form.html", template_data)


@staff_required
def questionnaire_copy(request, questionnaire_id):
    if request.method == "POST":
        questionnaire = Questionnaire()
        QuestionFormset = inlineformset_factory(Questionnaire, Question, formset=AtLeastOneFormSet, form=QuestionForm, extra=1, exclude=('questionnaire',))

        form = QuestionnaireForm(request.POST, instance=questionnaire)
        formset = QuestionFormset(request.POST.copy(), instance=questionnaire, save_as_new=True)

        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()

            messages.success(request, _("Successfully created questionnaire."))
            return redirect('evap.staff.views.questionnaire_index')
        else:
            return render(request, "staff_questionnaire_form.html", dict(form=form, formset=formset))
    else:
        questionnaire = get_object_or_404(Questionnaire, id=questionnaire_id)
        QuestionFormset = inlineformset_factory(Questionnaire, Question, formset=IdLessQuestionFormSet, form=QuestionForm, extra=1, exclude=('questionnaire',))

        form = QuestionnaireForm(instance=questionnaire)
        formset = QuestionFormset(instance=Questionnaire(), queryset=questionnaire.question_set.all())

        return render(request, "staff_questionnaire_form.html", dict(form=form, formset=formset))


@staff_required
def questionnaire_delete(request, questionnaire_id):
    questionnaire = get_object_or_404(Questionnaire, id=questionnaire_id)

    if questionnaire.can_staff_delete:
        if request.method == 'POST':
            questionnaire.delete()
            messages.success(request, _("Successfully deleted questionnaire."))
            return redirect('evap.staff.views.questionnaire_index')
        else:
            return render(request, "staff_questionnaire_delete.html", dict(questionnaire=questionnaire))
    else:
        messages.warning(request, _("The questionnaire '%s' cannot be deleted, because it is still in use.") % questionnaire.name)
        return redirect('evap.staff.views.questionnaire_index')


@staff_required
def user_index(request):
    users = UserProfile.objects.order_by("last_name", "first_name", "username").prefetch_related('contributions', 'groups')

    return render(request, "staff_user_index.html", dict(users=users))


@staff_required
def user_create(request):
    form = UserForm(request.POST or None, instance=UserProfile())

    if form.is_valid():
        form.save()
        messages.success(request, _("Successfully created user."))
        return redirect('evap.staff.views.user_index')
    else:
        return render(request, "staff_user_form.html", dict(form=form))


@staff_required
def user_import(request):
    form = UserImportForm(request.POST or None, request.FILES or None)
    operation = request.POST.get('operation')

    if form.is_valid():
        if operation not in ('test', 'import'):
            raise PermissionDenied

        test_run = operation == 'test'
        excel_file = form.cleaned_data['excel_file']
        UserImporter.process(request, excel_file, test_run)
        if test_run:
            return render(request, "staff_user_import.html", dict(form=form))
        return redirect('evap.staff.views.user_index')       
    else:
        return render(request, "staff_user_import.html", dict(form=form))


@staff_required
def user_edit(request, user_id):
    user = get_object_or_404(UserProfile, id=user_id)
    form = UserForm(request.POST or None, request.FILES or None, instance=user)

    courses_contributing_to = Course.objects.filter(semester=Semester.active_semester, contributions__contributor=user)

    if form.is_valid():
        form.save()
        messages.success(request, _("Successfully updated user."))
        return redirect('evap.staff.views.user_index')
    else:
        return render(request, "staff_user_form.html", dict(form=form, object=user, courses_contributing_to=courses_contributing_to))


@staff_required
def user_delete(request, user_id):
    user = get_object_or_404(UserProfile, id=user_id)

    if user.can_staff_delete:
        if request.method == 'POST':
            user.delete()
            messages.success(request, _("Successfully deleted user."))
            return redirect('evap.staff.views.user_index')
        else:
            return render(request, "staff_user_delete.html", dict(user_to_delete=user))
    else:
        messages.warning(request, _("The user '%s' cannot be deleted, because he lectures courses.") % user.full_name)
        return redirect('evap.staff.views.user_index')


@staff_required
def template_edit(request, template_id):
    template = get_object_or_404(EmailTemplate, id=template_id)
    form = EmailTemplateForm(request.POST or None, request.FILES or None, instance=template)

    if form.is_valid():
        form.save()

        messages.success(request, _("Successfully updated template."))
        return redirect('staff_root')
    else:
        return render(request, "staff_template_form.html", dict(form=form, template=template))


@staff_required
def faq_index(request):
    sections = FaqSection.objects.all()

    sectionFS = modelformset_factory(FaqSection, form=FaqSectionForm, can_order=False, can_delete=True, extra=1)
    formset = sectionFS(request.POST or None, queryset=sections)

    if formset.is_valid():
        formset.save()

        messages.success(request, _("Successfully updated the FAQ sections."))
        return custom_redirect('evap.staff.views.faq_index')
    else:
        return render(request, "staff_faq_index.html", dict(formset=formset, sections=sections))


@staff_required
def faq_section(request, section_id):
    section = get_object_or_404(FaqSection, id=section_id)
    questions = FaqQuestion.objects.filter(section=section)

    questionFS = inlineformset_factory(FaqSection, FaqQuestion, form=FaqQuestionForm, can_order=False, can_delete=True, extra=1, exclude=('section',))
    formset = questionFS(request.POST or None, queryset=questions, instance=section)

    if formset.is_valid():
        formset.save()

        messages.success(request, _("Successfully updated the FAQ questions."))
        return custom_redirect('evap.staff.views.faq_index')
    else:
        template_data = dict(formset=formset, section=section, questions=questions)
        return render(request, "staff_faq_section.html", template_data)


def helper_create_grouped_course_selection_forms(courses, filter_func, request):
    if filter_func:
        courses = filter(filter_func, courses)
    grouped_courses = {}
    for course in courses:
        degree = course.degree
        if degree not in grouped_courses:
            grouped_courses[degree] = []
        grouped_courses[degree].append(course)

    forms = []
    for degree, degree_courses in grouped_courses.items():
        form = SelectCourseForm(degree_courses, request.POST or None)
        forms.append(form)

    return forms


def helper_are_course_selection_forms_valid(forms):
    valid = True
    for form in forms:
        if not form.is_valid():
            valid = False
    return valid
