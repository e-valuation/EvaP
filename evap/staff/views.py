import csv
from dataclasses import dataclass
from datetime import datetime, date
from collections import OrderedDict, defaultdict, namedtuple
from xlrd import open_workbook
from xlutils.copy import copy as copy_workbook

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied, SuspiciousOperation
from django.dispatch import receiver
from django.db import IntegrityError, transaction
from django.db.models import BooleanField, Case, Count, ExpressionWrapper, IntegerField, Prefetch, Q, Sum, When
from django.forms import formset_factory
from django.forms.models import inlineformset_factory, modelformset_factory
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _, gettext_lazy
from django.utils.translation import get_language, ngettext
from django.views.decorators.http import require_POST
from evap.contributor.views import export_contributor_results
from evap.evaluation.auth import reviewer_required, manager_required
from evap.evaluation.models import (Contribution, Course, CourseType, Degree, EmailTemplate, Evaluation, FaqQuestion,
                                    FaqSection, Question, Questionnaire, RatingAnswerCounter, Semester, TextAnswer,
                                    UserProfile)
from evap.evaluation.tools import get_parameter_from_url_or_session, sort_formset, FileResponse
from evap.grades.models import GradeDocument
from evap.results.exporters import ExcelExporter
from evap.results.tools import calculate_average_distribution, distribution_to_grade, TextResult
from evap.results.views import update_template_cache_of_published_evaluations_in_course
from evap.rewards.models import RewardPointGranting
from evap.rewards.tools import can_reward_points_be_used_by, is_semester_activated
from evap.staff.forms import (AtLeastOneFormSet, ContributionForm, ContributionFormSet, CourseForm, CourseTypeForm,
                              CourseTypeMergeSelectionForm, DegreeForm, EmailTemplateForm, EvaluationEmailForm,
                              EvaluationForm, EvaluationParticipantCopyForm, ExportSheetForm, FaqQuestionForm,
                              FaqSectionForm, ImportForm, QuestionForm, QuestionnaireForm, QuestionnairesAssignForm,
                              RemindResponsibleForm, SemesterForm, SingleResultForm, TextAnswerForm, UserBulkUpdateForm,
                              UserForm, UserImportForm, UserMergeSelectionForm)
from evap.staff.importers import EnrollmentImporter, UserImporter, PersonImporter
from evap.staff.tools import (bulk_update_users, delete_import_file, delete_navbar_cache_for_users,
                              forward_messages, get_import_file_content_or_raise, import_file_exists, merge_users,
                              save_import_file, find_next_unreviewed_evaluation, ImportType)
from evap.student.forms import QuestionnaireVotingForm
from evap.student.views import get_valid_form_groups_or_render_vote_page


@manager_required
def index(request):
    template_data = dict(semesters=Semester.objects.all(),
                         templates=EmailTemplate.objects.all().order_by("id"),
                         sections=FaqSection.objects.all(),
                         disable_breadcrumb_manager=True)
    return render(request, "staff_index.html", template_data)


def annotate_evaluations_with_grade_document_counts(evaluations):
    return evaluations.annotate(
        midterm_grade_documents_count=Count("course__grade_documents", filter=Q(course__grade_documents__type=GradeDocument.Type.MIDTERM_GRADES), distinct=True),
        final_grade_documents_count=Count("course__grade_documents", filter=Q(course__grade_documents__type=GradeDocument.Type.FINAL_GRADES), distinct=True)
    )


def get_evaluations_with_prefetched_data(semester):
    evaluations = (semester.evaluations
        .select_related('course__type')
        .prefetch_related(
            Prefetch("contributions", queryset=Contribution.objects.filter(contributor=None), to_attr="general_contribution"),
            "course__degrees",
            "course__responsibles"
        ).annotate(
            num_contributors=Count("contributions", filter=~Q(contributions__contributor=None), distinct=True),
            num_textanswers=Count("contributions__textanswer_set", filter=Q(contributions__evaluation__can_publish_text_results=True), distinct=True),
            num_reviewed_textanswers=Count("contributions__textanswer_set", filter=~Q(contributions__textanswer_set__state=TextAnswer.State.NOT_REVIEWED), distinct=True),
            num_course_evaluations=Count("course__evaluations", distinct=True),
        )
    ).order_by('pk')
    evaluations = annotate_evaluations_with_grade_document_counts(evaluations)

    # these could be done with an annotation like this:
    # num_voters_annotated=Count("voters", distinct=True), or more completely
    # evaluations.annotate(num_voters=Case(When(_voter_count=None, then=Count('voters', distinct=True)), default=F('_voter_count')))
    # but that was prohibitively slow.
    participant_counts = semester.evaluations.annotate(num_participants=Count("participants")).order_by('pk').values_list("num_participants", flat=True)
    voter_counts = semester.evaluations.annotate(num_voters=Count("voters")).order_by('pk').values_list("num_voters", flat=True)

    for evaluation, participant_count, voter_count in zip(evaluations, participant_counts, voter_counts):
        evaluation.general_contribution = evaluation.general_contribution[0]
        if evaluation._participant_count is None:
            evaluation.num_participants = participant_count
            evaluation.num_voters = voter_count

    return evaluations


@reviewer_required
def semester_view(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    if semester.results_are_archived and not request.user.is_manager:
        raise PermissionDenied
    rewards_active = is_semester_activated(semester)

    evaluations = get_evaluations_with_prefetched_data(semester)
    evaluations = sorted(evaluations, key=lambda cr: cr.full_name)
    courses = Course.objects.filter(semester=semester)

    # semester statistics (per degree)
    @dataclass
    class Stats:
        # pylint: disable=too-many-instance-attributes
        num_enrollments_in_evaluation: int = 0
        num_votes: int = 0
        num_evaluations_evaluated: int = 0
        num_evaluations: int = 0
        num_textanswers: int = 0
        num_textanswers_reviewed: int = 0
        first_start: datetime = datetime(9999, 1, 1)
        last_end: date = date(2000, 1, 1)

    degree_stats = defaultdict(Stats)
    total_stats = Stats()
    for evaluation in evaluations:
        if evaluation.is_single_result:
            continue
        degrees = evaluation.course.degrees.all()
        stats_objects = [degree_stats[degree] for degree in degrees]
        stats_objects += [total_stats]
        for stats in stats_objects:
            if evaluation.state in ['in_evaluation', 'evaluated', 'reviewed', 'published']:
                stats.num_enrollments_in_evaluation += evaluation.num_participants
                stats.num_votes += evaluation.num_voters
                stats.num_textanswers += evaluation.num_textanswers
                stats.num_textanswers_reviewed += evaluation.num_reviewed_textanswers
            if evaluation.state in ['evaluated', 'reviewed', 'published']:
                stats.num_evaluations_evaluated += 1
            if evaluation.state != 'new':
                stats.num_evaluations += 1
                stats.first_start = min(stats.first_start, evaluation.vote_start_datetime)
                stats.last_end = max(stats.last_end, evaluation.vote_end_date)
    degree_stats = OrderedDict(sorted(degree_stats.items(), key=lambda x: x[0].order))
    degree_stats['total'] = total_stats

    template_data = dict(
        semester=semester,
        evaluations=evaluations,
        disable_breadcrumb_semester=True,
        rewards_active=rewards_active,
        num_evaluations=len(evaluations),
        degree_stats=degree_stats,
        courses=courses,
        approval_states=['new', 'prepared', 'editor_approved', 'approved'],
    )
    return render(request, "staff_semester_view.html", template_data)


class EvaluationOperation:
    email_template_name = None
    email_template_contributor_name = None
    email_template_participant_name = None
    confirmation_message = None

    @staticmethod
    def applicable_to(evaluation):
        raise NotImplementedError

    @staticmethod
    def warning_for_inapplicables(amount):
        raise NotImplementedError

    @staticmethod
    def apply(request, evaluations, email_template=None, email_template_contributor=None, email_template_participant=None):
        raise NotImplementedError


class RevertToNewOperation(EvaluationOperation):
    confirmation_message = gettext_lazy("Do you want to revert the following evaluations to preparation?")

    @staticmethod
    def applicable_to(evaluation):
        return evaluation.state in ['prepared', 'editor_approved', 'approved']

    @staticmethod
    def warning_for_inapplicables(amount):
        return ngettext("{} evaluation can not be reverted, because it already started. It was removed from the selection.",
            "{} evaluations can not be reverted, because they already started. They were removed from the selection.", amount).format(amount)

    @staticmethod
    def apply(request, evaluations, email_template=None, email_template_contributor=None, email_template_participant=None):
        assert email_template_contributor is None
        assert email_template_participant is None

        for evaluation in evaluations:
            evaluation.revert_to_new()
            evaluation.save()
        messages.success(request, ngettext("Successfully reverted {} evaluation to in preparation.",
            "Successfully reverted {} evaluations to in preparation.", len(evaluations)).format(len(evaluations)))


class MoveToPreparedOperation(EvaluationOperation):
    email_template_name = EmailTemplate.EDITOR_REVIEW_NOTICE
    confirmation_message = gettext_lazy("Do you want to send the following evaluations to editor review?")

    @staticmethod
    def applicable_to(evaluation):
        return evaluation.state in ['new', 'editor_approved']

    @staticmethod
    def warning_for_inapplicables(amount):
        return ngettext("{} evaluation can not be reverted, because it already started. It was removed from the selection.",
            "{} evaluations can not be reverted, because they already started. They were removed from the selection.", amount).format(amount)

    @staticmethod
    def apply(request, evaluations, email_template=None, email_template_contributor=None, email_template_participant=None):
        assert email_template_contributor is None
        assert email_template_participant is None

        for evaluation in evaluations:
            evaluation.ready_for_editors()
            evaluation.save()
        messages.success(request, ngettext("Successfully enabled {} evaluation for editor review.",
            "Successfully enabled {} evaluations for editor review.", len(evaluations)).format(len(evaluations)))
        if email_template:
            evaluations_by_responsible = {}
            for evaluation in evaluations:
                for responsible in evaluation.course.responsibles.all():
                    evaluations_by_responsible.setdefault(responsible, []).append(evaluation)

            for responsible, responsible_evaluations in evaluations_by_responsible.items():
                body_params = {'user': responsible, 'evaluations': responsible_evaluations}
                editors = UserProfile.objects \
                    .filter(contributions__evaluation__in=responsible_evaluations, contributions__can_edit=True) \
                    .exclude(pk=responsible.pk)
                email_template.send_to_user(responsible, subject_params={}, body_params=body_params,
                                            use_cc=True, additional_cc_users=editors, request=request)


class StartEvaluationOperation(EvaluationOperation):
    email_template_name = EmailTemplate.EVALUATION_STARTED
    confirmation_message = gettext_lazy("Do you want to immediately start the following evaluations?")

    @staticmethod
    def applicable_to(evaluation):
        return evaluation.state == 'approved' and evaluation.vote_end_date >= date.today()

    @staticmethod
    def warning_for_inapplicables(amount):
        return ngettext("{} evaluation can not be started, because it was not approved, was already evaluated or its evaluation end date lies in the past. It was removed from the selection.",
            "{} evaluations can not be started, because they were not approved, were already evaluated or their evaluation end dates lie in the past. They were removed from the selection.", amount).format(amount)

    @staticmethod
    def apply(request, evaluations, email_template=None, email_template_contributor=None, email_template_participant=None):
        assert email_template_contributor is None
        assert email_template_participant is None

        for evaluation in evaluations:
            evaluation.vote_start_datetime = datetime.now()
            evaluation.evaluation_begin()
            evaluation.save()
        messages.success(request, ngettext("Successfully started {} evaluation.",
            "Successfully started {} evaluations.", len(evaluations)).format(len(evaluations)))
        if email_template:
            email_template.send_to_users_in_evaluations(evaluations, [EmailTemplate.Recipients.ALL_PARTICIPANTS], use_cc=False, request=request)


class RevertToReviewedOperation(EvaluationOperation):
    confirmation_message = gettext_lazy("Do you want to unpublish the following evaluations?")

    @staticmethod
    def applicable_to(evaluation):
        return evaluation.state == 'published'

    @staticmethod
    def warning_for_inapplicables(amount):
        return ngettext("{} evaluation can not be unpublished, because it's results have not been published. It was removed from the selection.",
            "{} evaluations can not be unpublished because their results have not been published. They were removed from the selection.", amount).format(amount)

    @staticmethod
    def apply(request, evaluations, email_template=None, email_template_contributor=None, email_template_participant=None):
        assert email_template_contributor is None
        assert email_template_participant is None

        for evaluation in evaluations:
            evaluation.unpublish()
            evaluation.save()
        messages.success(request, ngettext("Successfully unpublished {} evaluation.",
            "Successfully unpublished {} evaluations.", len(evaluations)).format(len(evaluations)))


class PublishOperation(EvaluationOperation):
    email_template_contributor_name = EmailTemplate.PUBLISHING_NOTICE_CONTRIBUTOR
    email_template_participant_name = EmailTemplate.PUBLISHING_NOTICE_PARTICIPANT
    confirmation_message = gettext_lazy("Do you want to publish the following evaluations?")

    @staticmethod
    def applicable_to(evaluation):
        return evaluation.state == 'reviewed'

    @staticmethod
    def warning_for_inapplicables(amount):
        return ngettext("{} evaluation can not be published, because it's not finished or not all of its text answers have been reviewed. It was removed from the selection.",
           "{} evaluations can not be published, because they are not finished or not all of their text answers have been reviewed. They were removed from the selection.", amount).format(amount)

    @staticmethod
    def apply(request, evaluations, email_template=None, email_template_contributor=None, email_template_participant=None):
        assert email_template is None

        for evaluation in evaluations:
            evaluation.publish()
            evaluation.save()
        messages.success(request, ngettext("Successfully published {} evaluation.",
            "Successfully published {} evaluations.", len(evaluations)).format(len(evaluations)))

        if email_template_contributor:
            EmailTemplate.send_contributor_publish_notifications(evaluations, template=email_template_contributor)
        if email_template_participant:
            EmailTemplate.send_participant_publish_notifications(evaluations, template=email_template_participant)


EVALUATION_OPERATIONS = {
        'new': RevertToNewOperation,
        'prepared': MoveToPreparedOperation,
        'in_evaluation': StartEvaluationOperation,
        'reviewed': RevertToReviewedOperation,
        'published': PublishOperation,
}


@manager_required
def semester_evaluation_operation(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    if semester.participations_are_archived:
        raise PermissionDenied

    target_state = request.GET.get('target_state')
    if target_state not in EVALUATION_OPERATIONS.keys():
        raise SuspiciousOperation("Unknown target state: " + str(target_state))

    evaluation_ids = (request.GET if request.method == 'GET' else request.POST).getlist('evaluation')
    evaluations = list(annotate_evaluations_with_grade_document_counts(Evaluation.objects.filter(id__in=evaluation_ids)))
    evaluations.sort(key=lambda evaluation: evaluation.full_name)

    operation = EVALUATION_OPERATIONS[target_state]

    if request.method == 'POST':
        email_template = None
        email_template_contributor = None
        email_template_participant = None
        if request.POST.get('send_email') == 'on':
            email_template = EmailTemplate(subject=request.POST['email_subject'], body=request.POST['email_body'])
        if request.POST.get('send_email_contributor') == 'on':
            email_template_contributor = EmailTemplate(subject=request.POST['email_subject_contributor'], body=request.POST['email_body_contributor'])
        if request.POST.get('send_email_participant') == 'on':
            email_template_participant = EmailTemplate(subject=request.POST['email_subject_participant'], body=request.POST['email_body_participant'])

        operation.apply(request, evaluations, email_template, email_template_contributor, email_template_participant)
        return redirect('staff:semester_view', semester_id)

    applicable_evaluations = list(filter(operation.applicable_to, evaluations))
    difference = len(evaluations) - len(applicable_evaluations)
    if difference:
        messages.warning(request, operation.warning_for_inapplicables(difference))
    if not applicable_evaluations:  # no evaluations where applicable or none were selected
        messages.warning(request, _("Please select at least one evaluation."))
        return redirect('staff:semester_view', semester_id)

    email_template = None
    email_template_contributor = None
    email_template_participant = None
    if operation.email_template_name:
        email_template = EmailTemplate.objects.get(name=operation.email_template_name)
    if operation.email_template_contributor_name:
        email_template_contributor = EmailTemplate.objects.get(name=operation.email_template_contributor_name)
    if operation.email_template_participant_name:
        email_template_participant = EmailTemplate.objects.get(name=operation.email_template_participant_name)

    template_data = dict(
        semester=semester,
        evaluations=applicable_evaluations,
        target_state=target_state,
        confirmation_message=operation.confirmation_message,
        email_template=email_template,
        email_template_contributor=email_template_contributor,
        email_template_participant=email_template_participant,
        show_email_checkbox=email_template is not None or email_template_contributor is not None or email_template_participant is not None
    )

    return render(request, "staff_evaluation_operation.html", template_data)


@manager_required
def semester_create(request):
    form = SemesterForm(request.POST or None)

    if form.is_valid():
        semester = form.save()
        delete_navbar_cache_for_users([user for user in UserProfile.objects.all() if user.is_reviewer or user.is_grade_publisher])

        messages.success(request, _("Successfully created semester."))
        return redirect('staff:semester_view', semester.id)

    return render(request, "staff_semester_form.html", dict(form=form))


@require_POST
@manager_required
@transaction.atomic
def semester_make_active(request):
    semester_id = request.POST.get("semester_id")
    semester = get_object_or_404(Semester, id=semester_id)

    Semester.objects.update(is_active=None)

    semester.is_active = True
    semester.save()

    return HttpResponse()


@manager_required
def semester_edit(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    form = SemesterForm(request.POST or None, instance=semester)

    if form.is_valid():
        semester = form.save()
        messages.success(request, _("Successfully updated semester."))
        return redirect('staff:semester_view', semester.id)

    return render(request, "staff_semester_form.html", dict(semester=semester, form=form))


@require_POST
@manager_required
def semester_delete(request):
    semester_id = request.POST.get("semester_id")
    semester = get_object_or_404(Semester, id=semester_id)

    if not semester.can_be_deleted_by_manager:
        raise SuspiciousOperation("Deleting semester not allowed")
    RatingAnswerCounter.objects.filter(contribution__evaluation__course__semester=semester).delete()
    TextAnswer.objects.filter(contribution__evaluation__course__semester=semester).delete()
    Contribution.objects.filter(evaluation__course__semester=semester).delete()
    Evaluation.objects.filter(course__semester=semester).delete()
    Course.objects.filter(semester=semester).delete()
    semester.delete()
    delete_navbar_cache_for_users([user for user in UserProfile.objects.all() if user.is_reviewer or user.is_grade_publisher])
    return redirect('staff:index')


@manager_required
def semester_import(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    if semester.participations_are_archived:
        raise PermissionDenied

    excel_form = ImportForm(request.POST or None, request.FILES or None)
    import_type = ImportType.Semester

    errors = []
    warnings = {}
    success_messages = []

    if request.method == "POST":
        operation = request.POST.get('operation')
        if operation not in ('test', 'import'):
            raise SuspiciousOperation("Invalid POST operation")

        if operation == 'test':
            delete_import_file(request.user.id, import_type)  # remove old files if still exist
            excel_form.fields['excel_file'].required = True
            if excel_form.is_valid():
                excel_file = excel_form.cleaned_data['excel_file']
                file_content = excel_file.read()
                success_messages, warnings, errors = EnrollmentImporter.process(file_content, semester, vote_start_datetime=None, vote_end_date=None, test_run=True)
                if not errors:
                    save_import_file(excel_file, request.user.id, import_type)

        elif operation == 'import':
            file_content = get_import_file_content_or_raise(request.user.id, import_type)
            excel_form.fields['vote_start_datetime'].required = True
            excel_form.fields['vote_end_date'].required = True
            if excel_form.is_valid():
                vote_start_datetime = excel_form.cleaned_data['vote_start_datetime']
                vote_end_date = excel_form.cleaned_data['vote_end_date']
                success_messages, warnings, __ = EnrollmentImporter.process(file_content, semester, vote_start_datetime, vote_end_date, test_run=False)
                forward_messages(request, success_messages, warnings)
                delete_import_file(request.user.id, import_type)
                delete_navbar_cache_for_users(UserProfile.objects.all())
                return redirect('staff:semester_view', semester_id)

    test_passed = import_file_exists(request.user.id, import_type)
    # casting warnings to a normal dict is necessary for the template to iterate over it.
    return render(request, "staff_semester_import.html", dict(semester=semester,
        success_messages=success_messages, errors=errors, warnings=dict(warnings),
        excel_form=excel_form, test_passed=test_passed))


@manager_required
def semester_export(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)

    ExportSheetFormset = formset_factory(form=ExportSheetForm, can_delete=True, extra=0, min_num=1, validate_min=True)
    formset = ExportSheetFormset(request.POST or None, form_kwargs={'semester': semester})

    if formset.is_valid():
        include_not_enough_voters = request.POST.get('include_not_enough_voters') == 'on'
        include_unpublished = request.POST.get('include_unpublished') == 'on'
        selection_list = []
        for form in formset:
            selection_list.append((form.cleaned_data['selected_degrees'], form.cleaned_data['selected_course_types']))

        filename = "Evaluation-{}-{}.xls".format(semester.name, get_language())
        response = FileResponse(filename, content_type="application/vnd.ms-excel")

        ExcelExporter().export(
            response, [semester], selection_list, include_not_enough_voters, include_unpublished
        )
        return response

    return render(request, "staff_semester_export.html", dict(semester=semester, formset=formset))


@manager_required
def semester_raw_export(_request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)

    filename = "Evaluation-{}-{}_raw.csv".format(semester.name, get_language())
    response = FileResponse(filename, content_type="text/csv")

    writer = csv.writer(response, delimiter=";", lineterminator="\n")
    writer.writerow([_('Name'), _('Degrees'), _('Type'), _('Single result'), _('State'), _('#Voters'),
        _('#Participants'), _('#Text answers'), _('Average grade')])
    for evaluation in sorted(semester.evaluations.all(), key=lambda cr: cr.full_name):
        degrees = ", ".join([degree.name for degree in evaluation.course.degrees.all()])
        distribution = calculate_average_distribution(evaluation)
        if evaluation.state in ['evaluated', 'reviewed', 'published'] and distribution is not None:
            avg_grade = "{:.1f}".format(distribution_to_grade(distribution))
        else:
            avg_grade = ""
        writer.writerow([evaluation.full_name, degrees, evaluation.course.type.name, evaluation.is_single_result, evaluation.state,
            evaluation.num_voters, evaluation.num_participants, evaluation.textanswer_set.count(), avg_grade])

    return response


@manager_required
def semester_participation_export(_request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    participants = UserProfile.objects.filter(evaluations_participating_in__course__semester=semester).distinct().order_by("username")

    filename = "Evaluation-{}-{}_participation.csv".format(semester.name, get_language())
    response = FileResponse(filename, content_type="text/csv")

    writer = csv.writer(response, delimiter=";", lineterminator="\n")
    writer.writerow([_('Username'), _('Can use reward points'), _('#Required evaluations voted for'),
        _('#Required evaluations'), _('#Optional evaluations voted for'), _('#Optional evaluations'), _('Earned reward points')])
    for participant in participants:
        number_of_required_evaluations = semester.evaluations.filter(participants=participant, is_rewarded=True).count()
        number_of_required_evaluations_voted_for = semester.evaluations.filter(voters=participant, is_rewarded=True).count()
        number_of_optional_evaluations = semester.evaluations.filter(participants=participant, is_rewarded=False).count()
        number_of_optional_evaluations_voted_for = semester.evaluations.filter(voters=participant, is_rewarded=False).count()
        earned_reward_points = RewardPointGranting.objects.filter(semester=semester, user_profile=participant).aggregate(Sum('value'))['value__sum'] or 0
        writer.writerow([
            participant.username, can_reward_points_be_used_by(participant), number_of_required_evaluations_voted_for,
            number_of_required_evaluations, number_of_optional_evaluations_voted_for, number_of_optional_evaluations,
            earned_reward_points
        ])

    return response


@manager_required
def semester_questionnaire_assign(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    if semester.participations_are_archived:
        raise PermissionDenied
    evaluations = semester.evaluations.filter(state='new')
    course_types = CourseType.objects.filter(courses__evaluations__in=evaluations)
    form = QuestionnairesAssignForm(request.POST or None, course_types=course_types)

    if form.is_valid():
        for evaluation in evaluations:
            if form.cleaned_data[evaluation.course.type.name]:
                evaluation.general_contribution.questionnaires.set(form.cleaned_data[evaluation.course.type.name])
            if form.cleaned_data['All contributors']:
                for contribution in evaluation.contributions.exclude(contributor=None):
                    contribution.questionnaires.set(form.cleaned_data['All contributors'])
            evaluation.save()

        messages.success(request, _("Successfully assigned questionnaires."))
        return redirect('staff:semester_view', semester_id)

    return render(request, "staff_semester_questionnaire_assign_form.html", dict(semester=semester, form=form))


@manager_required
def semester_preparation_reminder(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)

    evaluations = semester.evaluations.filter(state__in=['prepared', 'editor_approved']).prefetch_related("course__degrees")

    prepared_evaluations = semester.evaluations.filter(state__in=['prepared'])
    responsibles = list(set(responsible for evaluation in prepared_evaluations for responsible in evaluation.course.responsibles.all()))
    responsibles.sort(key=lambda responsible: (responsible.last_name, responsible.first_name))

    responsible_list = [(responsible, [evaluation for evaluation in evaluations if responsible in evaluation.course.responsibles.all()],
                         responsible.delegates.all()) for responsible in responsibles]

    if request.method == "POST":
        template = EmailTemplate.objects.get(name=EmailTemplate.EDITOR_REVIEW_REMINDER)
        subject_params = {}
        for responsible, evaluations, __ in responsible_list:
            body_params = {"user": responsible, "evaluations": evaluations}
            template.send_to_user(responsible, subject_params, body_params, use_cc=True, request=request)
        messages.success(request, _("Successfully sent reminders to everyone."))
        return HttpResponse()

    template_data = dict(semester=semester, responsible_list=responsible_list)
    return render(request, "staff_semester_preparation_reminder.html", template_data)


@manager_required
def semester_grade_reminder(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)

    courses = semester.courses.filter(
        evaluations__state__in=['evaluated', 'reviewed', 'published'],
        evaluations__wait_for_grade_upload_before_publishing=True,
        gets_no_grade_documents=False
    ).distinct()
    courses = [course for course in courses if not course.final_grade_documents.exists()]
    courses.sort(key=lambda course: course.name)

    responsibles = list(set(responsible for course in courses for responsible in course.responsibles.all()))
    responsibles.sort(key=lambda responsible: (responsible.last_name.lower(), responsible.first_name.lower()))

    responsible_list = [(responsible, [course for course in courses if responsible in course.responsibles.all()])
                        for responsible in responsibles]

    template_data = dict(semester=semester, responsible_list=responsible_list)
    return render(request, "staff_semester_grade_reminder.html", template_data)


@manager_required
def send_reminder(request, semester_id, responsible_id):
    responsible = get_object_or_404(UserProfile, id=responsible_id)
    semester = get_object_or_404(Semester, id=semester_id)

    form = RemindResponsibleForm(request.POST or None, responsible=responsible)

    evaluations = Evaluation.objects.filter(state='prepared', course__responsibles__in=[responsible])

    if form.is_valid():
        form.send(request, evaluations)
        messages.success(request, _("Successfully sent reminder to {}.").format(responsible.full_name))
        return redirect('staff:semester_preparation_reminder', semester_id)

    return render(request, "staff_semester_send_reminder.html", dict(semester=semester, responsible=responsible, form=form))


@require_POST
@manager_required
def semester_archive_participations(request):
    semester_id = request.POST.get("semester_id")
    semester = get_object_or_404(Semester, id=semester_id)

    if not semester.participations_can_be_archived:
        raise SuspiciousOperation("Archiving participations for this semester is not allowed")
    semester.archive_participations()
    return HttpResponse()  # 200 OK


@require_POST
@manager_required
def semester_delete_grade_documents(request):
    semester_id = request.POST.get("semester_id")
    semester = get_object_or_404(Semester, id=semester_id)

    if not semester.grade_documents_can_be_deleted:
        raise SuspiciousOperation("Deleting grade documents for this semester is not allowed")
    semester.delete_grade_documents()
    delete_navbar_cache_for_users(UserProfile.objects.all())
    return HttpResponse()  # 200 OK


@require_POST
@manager_required
def semester_archive_results(request):
    semester_id = request.POST.get("semester_id")
    semester = get_object_or_404(Semester, id=semester_id)

    if not semester.results_can_be_archived:
        raise SuspiciousOperation("Archiving results for this semester is not allowed")
    semester.archive_results()
    delete_navbar_cache_for_users(UserProfile.objects.all())
    return HttpResponse()  # 200 OK


@manager_required
def course_create(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    if semester.participations_are_archived:
        raise PermissionDenied

    course = Course(semester=semester)
    course_form = CourseForm(request.POST or None, instance=course)

    operation = request.POST.get('operation')

    if course_form.is_valid():
        if operation not in ('save', 'save_create_evaluation', 'save_create_single_result'):
            raise SuspiciousOperation("Invalid POST operation")

        course = course_form.save()
        course.set_last_modified(request.user)
        course.save()

        messages.success(request, _("Successfully created course."))
        if operation == 'save_create_evaluation':
            return redirect('staff:evaluation_create', semester_id, course.id)
        if operation == 'save_create_single_result':
            return redirect('staff:single_result_create', semester_id, course.id)
        return redirect('staff:semester_view', semester_id)

    return render(request, "staff_course_form.html", dict(semester=semester, course_form=course_form, editable=True))


@manager_required
def course_edit(request, semester_id, course_id):
    semester = get_object_or_404(Semester, id=semester_id)
    course = get_object_or_404(Course, id=course_id, semester=semester)

    course_form = CourseForm(request.POST or None, instance=course)
    editable = course.can_be_edited_by_manager

    if request.method == "POST" and not editable:
        raise SuspiciousOperation("Modifying this course is not allowed.")

    operation = request.POST.get('operation')

    if course_form.is_valid():
        if operation not in ('save', 'save_create_evaluation', 'save_create_single_result'):
            raise SuspiciousOperation("Invalid POST operation")

        if course_form.has_changed():
            course = course_form.save()
            course.set_last_modified(request.user)
            course.save()
            update_template_cache_of_published_evaluations_in_course(course)

        messages.success(request, _("Successfully updated course."))
        if operation == 'save_create_evaluation':
            return redirect('staff:evaluation_create', semester_id, course.id)
        if operation == 'save_create_single_result':
            return redirect('staff:single_result_create', semester_id, course.id)

        return redirect('staff:semester_view', semester.id)

    template_data = dict(
        course=course, semester=semester, course_form=course_form, editable=editable, disable_breadcrumb_course=True,
    )
    return render(request, "staff_course_form.html", template_data)


@require_POST
@manager_required
def course_delete(request):
    course_id = request.POST.get("course_id")
    course = get_object_or_404(Course, id=course_id)
    if not course.can_be_deleted_by_manager:
        raise SuspiciousOperation("Deleting course not allowed")
    course.delete()
    return HttpResponse()  # 200 OK


@manager_required
def evaluation_create(request, semester_id, course_id=None):
    semester = get_object_or_404(Semester, id=semester_id)
    if semester.participations_are_archived:
        raise PermissionDenied

    evaluation = Evaluation()
    if course_id:
        evaluation.course = Course.objects.get(id=course_id)
    InlineContributionFormset = inlineformset_factory(Evaluation, Contribution, formset=ContributionFormSet, form=ContributionForm, extra=1)

    evaluation_form = EvaluationForm(request.POST or None, instance=evaluation, semester=semester)
    formset = InlineContributionFormset(request.POST or None, instance=evaluation, form_kwargs={'evaluation': evaluation})

    if evaluation_form.is_valid() and formset.is_valid():
        evaluation = evaluation_form.save()
        evaluation.set_last_modified(request.user)
        evaluation.save()
        formset.save()
        update_template_cache_of_published_evaluations_in_course(evaluation.course)

        messages.success(request, _("Successfully created evaluation."))
        return redirect('staff:semester_view', semester_id)

    return render(request, "staff_evaluation_form.html", dict(
        semester=semester, evaluation_form=evaluation_form, formset=formset, manager=True,
        editable=True, state=""
    ))


@manager_required
def single_result_create(request, semester_id, course_id=None):
    semester = get_object_or_404(Semester, id=semester_id)
    if semester.participations_are_archived:
        raise PermissionDenied

    evaluation = Evaluation()
    if course_id:
        evaluation.course = Course.objects.get(id=course_id)

    form = SingleResultForm(request.POST or None, instance=evaluation, semester=semester)

    if form.is_valid():
        evaluation = form.save(user=request.user)
        update_template_cache_of_published_evaluations_in_course(evaluation.course)

        messages.success(request, _("Successfully created single result."))
        return redirect('staff:semester_view', semester_id)

    return render(request, "staff_single_result_form.html", dict(semester=semester, form=form, editable=True))


@manager_required
def evaluation_edit(request, semester_id, evaluation_id):
    semester = get_object_or_404(Semester, id=semester_id)
    evaluation = get_object_or_404(Evaluation, id=evaluation_id, course__semester=semester)

    if request.method == "POST" and not evaluation.can_be_edited_by_manager:
        raise SuspiciousOperation("Modifying this evaluation is not allowed.")

    if evaluation.is_single_result:
        return helper_single_result_edit(request, semester, evaluation)
    return helper_evaluation_edit(request, semester, evaluation)


@manager_required
def helper_evaluation_edit(request, semester, evaluation):
    # Show a message when reward points are granted during the lifetime of the calling view.
    # The @receiver will only live as long as the request is processed
    # as the callback is captured by a weak reference in the Django Framework
    # and no other strong references are being kept.
    # See https://github.com/e-valuation/EvaP/issues/1361 for more information and discussion.
    @receiver(RewardPointGranting.granted_by_removal, weak=True)
    def notify_reward_points(grantings, **_kwargs):  # pylint: disable=unused-variable
        for granting in grantings:
            messages.info(request,
                ngettext(
                    'The removal as participant has granted the user "{granting.user_profile.username}" {granting.value} reward point for the semester.',
                    'The removal as participant has granted the user "{granting.user_profile.username}" {granting.value} reward points for the semester.',
                    granting.value
                ).format(granting=granting)
            )

    InlineContributionFormset = inlineformset_factory(Evaluation, Contribution, formset=ContributionFormSet, form=ContributionForm, extra=1)

    evaluation_form = EvaluationForm(request.POST or None, instance=evaluation, semester=semester)
    formset = InlineContributionFormset(request.POST or None, instance=evaluation, form_kwargs={'evaluation': evaluation})
    editable = evaluation.can_be_edited_by_manager

    operation = request.POST.get('operation')

    if evaluation_form.is_valid() and formset.is_valid():
        if operation not in ('save', 'approve'):
            raise SuspiciousOperation("Invalid POST operation")

        if not evaluation.can_be_edited_by_manager or evaluation.participations_are_archived:
            raise SuspiciousOperation("Modifying this evaluation is not allowed.")

        if evaluation.state in ['evaluated', 'reviewed'] and evaluation.is_in_evaluation_period:
            evaluation.reopen_evaluation()

        form_has_changed = evaluation_form.has_changed() or formset.has_changed()

        if form_has_changed:
            evaluation.set_last_modified(request.user)
        evaluation_form.save()
        formset.save()

        if operation == 'approve':
            evaluation.manager_approve()
            evaluation.save()
            if form_has_changed:
                messages.success(request, _("Successfully updated and approved evaluation."))
            else:
                messages.success(request, _("Successfully approved evaluation."))
        else:
            messages.success(request, _("Successfully updated evaluation."))

        delete_navbar_cache_for_users(evaluation.participants.all())
        delete_navbar_cache_for_users(UserProfile.objects.filter(contributions__evaluation=evaluation))

        return redirect('staff:semester_view', semester.id)

    if evaluation_form.errors or formset.errors:
        messages.error(request, _("The form was not saved. Please resolve the errors shown below."))
    sort_formset(request, formset)
    template_data = dict(
        evaluation=evaluation, semester=semester, evaluation_form=evaluation_form,
        formset=formset, manager=True, state=evaluation.state, editable=editable
    )
    return render(request, "staff_evaluation_form.html", template_data)


@manager_required
def helper_single_result_edit(request, semester, evaluation):
    form = SingleResultForm(request.POST or None, instance=evaluation, semester=semester)

    if form.is_valid():
        if not evaluation.can_be_edited_by_manager or evaluation.participations_are_archived:
            raise SuspiciousOperation("Modifying this evaluation is not allowed.")

        form.save(user=request.user)
        messages.success(request, _("Successfully created single result."))
        return redirect('staff:semester_view', semester.id)

    return render(request, "staff_single_result_form.html", dict(
        evaluation=evaluation, semester=semester, form=form, editable=evaluation.can_be_edited_by_manager
    ))


@require_POST
@manager_required
def evaluation_delete(request):
    evaluation_id = request.POST.get("evaluation_id")
    evaluation = get_object_or_404(Evaluation, id=evaluation_id)

    if not evaluation.can_be_deleted_by_manager:
        raise SuspiciousOperation("Deleting evaluation not allowed")
    if evaluation.is_single_result:
        RatingAnswerCounter.objects.filter(contribution__evaluation=evaluation).delete()
    evaluation.delete()
    update_template_cache_of_published_evaluations_in_course(evaluation.course)
    return HttpResponse()  # 200 OK


@manager_required
def evaluation_email(request, semester_id, evaluation_id):
    semester = get_object_or_404(Semester, id=semester_id)
    evaluation = get_object_or_404(Evaluation, id=evaluation_id, course__semester=semester)
    export = 'export' in request.POST
    form = EvaluationEmailForm(request.POST or None, evaluation=evaluation, export=export)

    if form.is_valid():
        if export:
            email_addresses = '; '.join(form.email_addresses())
            messages.info(request, _('Recipients: ') + '\n' + email_addresses)
            return render(request, "staff_evaluation_email.html", dict(semester=semester, evaluation=evaluation, form=form))
        form.send(request)
        messages.success(request, _("Successfully sent emails for '%s'.") % evaluation.full_name)
        return redirect('staff:semester_view', semester_id)

    return render(request, "staff_evaluation_email.html", dict(semester=semester, evaluation=evaluation, form=form))


@manager_required
def evaluation_person_management(request, semester_id, evaluation_id):
    # This view indeed handles 4 tasks. However, they are tightly coupled, splitting them up
    # would lead to more code duplication. Thus, we decided to leave it as is for now
    # pylint: disable=too-many-locals
    semester = get_object_or_404(Semester, id=semester_id)
    evaluation = get_object_or_404(Evaluation, id=evaluation_id, course__semester=semester)
    if evaluation.participations_are_archived:
        raise PermissionDenied

    # Each form required two times so the errors can be displayed correctly
    participant_excel_form = UserImportForm(request.POST or None, request.FILES or None)
    participant_copy_form = EvaluationParticipantCopyForm(request.POST or None)
    contributor_excel_form = UserImportForm(request.POST or None, request.FILES or None)
    contributor_copy_form = EvaluationParticipantCopyForm(request.POST or None)

    errors = []
    warnings = defaultdict(list)
    success_messages = []

    if request.method == "POST":
        operation = request.POST.get('operation')
        if operation not in ('test-participants', 'import-participants', 'copy-participants',
                             'test-contributors', 'import-contributors', 'copy-contributors'):
            raise SuspiciousOperation("Invalid POST operation")

        import_type = ImportType.Participant if 'participants' in operation else ImportType.Contributor
        excel_form = participant_excel_form if 'participants' in operation else contributor_excel_form
        copy_form = participant_copy_form if 'participants' in operation else contributor_copy_form

        if 'test' in operation:
            delete_import_file(request.user.id, import_type)  # remove old files if still exist
            excel_form.fields['excel_file'].required = True
            if excel_form.is_valid():
                excel_file = excel_form.cleaned_data['excel_file']
                file_content = excel_file.read()
                success_messages, warnings, errors = PersonImporter.process_file_content(import_type, evaluation, test_run=True, file_content=file_content)
                if not errors:
                    save_import_file(excel_file, request.user.id, import_type)

        elif 'import' in operation:
            file_content = get_import_file_content_or_raise(request.user.id, import_type)
            success_messages, warnings, __ = PersonImporter.process_file_content(import_type, evaluation, test_run=False, file_content=file_content)
            delete_import_file(request.user.id, import_type)
            forward_messages(request, success_messages, warnings)
            return redirect('staff:semester_view', semester_id)

        elif 'copy' in operation:
            copy_form.evaluation_selection_required = True
            if copy_form.is_valid():
                import_evaluation = copy_form.cleaned_data['evaluation']
                success_messages, warnings, errors = PersonImporter.process_source_evaluation(import_type, evaluation, test_run=False, source_evaluation=import_evaluation)
                forward_messages(request, success_messages, warnings)
                return redirect('staff:semester_view', semester_id)

    participant_test_passed = import_file_exists(request.user.id, ImportType.Participant)
    contributor_test_passed = import_file_exists(request.user.id, ImportType.Contributor)
    # casting warnings to a normal dict is necessary for the template to iterate over it.
    return render(request, "staff_evaluation_person_management.html", dict(semester=semester, evaluation=evaluation,
        participant_excel_form=participant_excel_form, participant_copy_form=participant_copy_form,
        contributor_excel_form=contributor_excel_form, contributor_copy_form=contributor_copy_form,
        success_messages=success_messages, warnings=dict(warnings), errors=errors,
        participant_test_passed=participant_test_passed, contributor_test_passed=contributor_test_passed))


@manager_required
def evaluation_login_key_export(_request, semester_id, evaluation_id):
    semester = get_object_or_404(Semester, id=semester_id)
    evaluation = get_object_or_404(Evaluation, course__semester=semester, id=evaluation_id)

    filename = "Login_keys-{evaluation.full_name}-{semester.short_name}.csv".format(evaluation=evaluation, semester=semester)
    response = FileResponse(filename, content_type="text/csv")

    writer = csv.writer(response, delimiter=";", lineterminator="\n")
    writer.writerow([_('Last name'), _('First name'), _('Email'), _('Login key')])

    external_participants = (participant for participant in evaluation.participants.all() if participant.is_external)
    for participant in external_participants:
        participant.ensure_valid_login_key()
        writer.writerow([participant.last_name, participant.first_name, participant.email, participant.login_url])

    return response


def get_evaluation_and_contributor_textanswer_sections(evaluation, filter_textanswers):
    TextAnswerSection = namedtuple('TextAnswerSection', ('questionnaire', 'contributor', 'label', 'is_responsible', 'results'))

    evaluation_sections = []
    contributor_sections = []

    for contribution in evaluation.contributions.all().prefetch_related("questionnaires"):
        for questionnaire in contribution.questionnaires.all():
            text_results = []

            for question in questionnaire.text_questions:
                answers = TextAnswer.objects.filter(contribution=contribution, question=question)
                if filter_textanswers:
                    answers = answers.filter(state=TextAnswer.State.NOT_REVIEWED)
                if answers:
                    text_results.append(TextResult(question=question, answers=answers))

            if not text_results:
                continue

            section_list = evaluation_sections if contribution.is_general else contributor_sections
            section_list.append(TextAnswerSection(
                questionnaire, contribution.contributor, contribution.label,
                contribution.contributor in evaluation.course.responsibles.all(), text_results
            ))

    return evaluation_sections, contributor_sections


@reviewer_required
def evaluation_textanswers(request, semester_id, evaluation_id):
    semester = get_object_or_404(Semester, id=semester_id)
    if semester.results_are_archived and not request.user.is_manager:
        raise PermissionDenied
    evaluation = get_object_or_404(Evaluation, id=evaluation_id, course__semester=semester)

    if not evaluation.can_publish_text_results:
        raise PermissionDenied

    view = request.GET.get('view', 'quick')
    filter_textanswers = view == "unreviewed"

    evaluation_sections, contributor_sections = get_evaluation_and_contributor_textanswer_sections(evaluation, filter_textanswers)

    template_data = dict(semester=semester, evaluation=evaluation, view=view)

    if view == 'quick':
        visited = request.session.get('review-visited', set())
        visited.add(evaluation.pk)
        next_evaluation = find_next_unreviewed_evaluation(semester, visited)
        if not next_evaluation and len(visited) > 1:
            visited = {evaluation.pk}
            next_evaluation = find_next_unreviewed_evaluation(semester, visited)
        request.session['review-visited'] = visited

        sections = evaluation_sections + contributor_sections
        template_data.update(dict(sections=sections, next_evaluation=next_evaluation))
        return render(request, "staff_evaluation_textanswers_quick.html", template_data)

    template_data.update(dict(evaluation_sections=evaluation_sections, contributor_sections=contributor_sections))
    return render(request, "staff_evaluation_textanswers_full.html", template_data)


@require_POST
@reviewer_required
def evaluation_textanswers_update_publish(request):
    textanswer_id = request.POST["id"]
    action = request.POST["action"]
    evaluation_id = request.POST["evaluation_id"]

    evaluation = Evaluation.objects.get(pk=evaluation_id)
    if evaluation.course.semester.results_are_archived and not request.user.is_manager:
        raise PermissionDenied
    if not evaluation.can_publish_text_results:
        raise PermissionDenied

    answer = TextAnswer.objects.get(pk=textanswer_id)

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

    if evaluation.state == "evaluated" and evaluation.is_fully_reviewed:
        evaluation.review_finished()
        evaluation.save()
    if evaluation.state == "reviewed" and not evaluation.is_fully_reviewed:
        evaluation.reopen_review()
        evaluation.save()

    return HttpResponse()  # 200 OK


@reviewer_required
def evaluation_textanswer_edit(request, semester_id, evaluation_id, textanswer_id):
    semester = get_object_or_404(Semester, id=semester_id)
    if semester.results_are_archived and not request.user.is_manager:
        raise PermissionDenied
    evaluation = get_object_or_404(Evaluation, id=evaluation_id, course__semester=semester)

    if not evaluation.can_publish_text_results:
        raise PermissionDenied

    textanswer = get_object_or_404(TextAnswer, id=textanswer_id, contribution__evaluation=evaluation)
    form = TextAnswerForm(request.POST or None, instance=textanswer)

    if form.is_valid():
        form.save()
        # jump to edited answer
        url = reverse('staff:evaluation_textanswers', args=[semester_id, evaluation_id]) + '#' + str(textanswer.id)
        return HttpResponseRedirect(url)

    template_data = dict(semester=semester, evaluation=evaluation, form=form, textanswer=textanswer)
    return render(request, "staff_evaluation_textanswer_edit.html", template_data)


@reviewer_required
def evaluation_preview(request, semester_id, evaluation_id):
    semester = get_object_or_404(Semester, id=semester_id)
    if semester.results_are_archived and not request.user.is_manager:
        raise PermissionDenied
    evaluation = get_object_or_404(Evaluation, id=evaluation_id, course__semester=semester)

    return get_valid_form_groups_or_render_vote_page(request, evaluation, preview=True)[1]


@manager_required
def questionnaire_index(request):
    filter_questionnaires = get_parameter_from_url_or_session(request, "filter_questionnaires")

    general_questionnaires = Questionnaire.objects.general_questionnaires()
    contributor_questionnaires = Questionnaire.objects.contributor_questionnaires()

    if filter_questionnaires:
        general_questionnaires = general_questionnaires.exclude(visibility=Questionnaire.Visibility.HIDDEN)
        contributor_questionnaires = contributor_questionnaires.exclude(visibility=Questionnaire.Visibility.HIDDEN)

    general_questionnaires_top = [questionnaire for questionnaire in general_questionnaires if questionnaire.is_above_contributors]
    general_questionnaires_bottom = [questionnaire for questionnaire in general_questionnaires if questionnaire.is_below_contributors]

    template_data = dict(
        general_questionnaires_top=general_questionnaires_top,
        general_questionnaires_bottom=general_questionnaires_bottom,
        contributor_questionnaires=contributor_questionnaires,
        filter_questionnaires=filter_questionnaires,
    )
    return render(request, "staff_questionnaire_index.html", template_data)


@manager_required
def questionnaire_view(request, questionnaire_id):
    questionnaire = get_object_or_404(Questionnaire, id=questionnaire_id)

    # build forms
    contribution = Contribution(contributor=request.user)
    form = QuestionnaireVotingForm(request.POST or None, contribution=contribution, questionnaire=questionnaire)

    return render(request, "staff_questionnaire_view.html", dict(forms=[form], questionnaire=questionnaire))


@manager_required
def questionnaire_create(request):
    questionnaire = Questionnaire()
    InlineQuestionFormset = inlineformset_factory(Questionnaire, Question, formset=AtLeastOneFormSet, form=QuestionForm, extra=1, exclude=('questionnaire',))

    form = QuestionnaireForm(request.POST or None, instance=questionnaire)
    formset = InlineQuestionFormset(request.POST or None, instance=questionnaire)

    if form.is_valid() and formset.is_valid():
        form.save(force_highest_order=True)
        formset.save()

        messages.success(request, _("Successfully created questionnaire."))
        return redirect('staff:questionnaire_index')

    return render(request, "staff_questionnaire_form.html", dict(form=form, formset=formset, editable=True))


def make_questionnaire_edit_forms(request, questionnaire, editable):
    if editable:
        InlineQuestionFormset = inlineformset_factory(Questionnaire, Question, formset=AtLeastOneFormSet, form=QuestionForm, extra=1, exclude=('questionnaire',))
    else:
        question_count = questionnaire.questions.count()
        InlineQuestionFormset = inlineformset_factory(Questionnaire, Question, formset=AtLeastOneFormSet, form=QuestionForm, extra=0, exclude=('questionnaire',),
                                                      can_delete=False, max_num=question_count, validate_max=True, min_num=question_count, validate_min=True)

    form = QuestionnaireForm(request.POST or None, instance=questionnaire)
    formset = InlineQuestionFormset(request.POST or None, instance=questionnaire)

    if not editable:
        editable_fields = ['visibility', 'is_locked', 'name_de', 'name_en', 'description_de', 'description_en', 'type']

        for name, field in form.fields.items():
            if name not in editable_fields:
                field.disabled = True
        for question_form in formset.forms:
            for name, field in question_form.fields.items():
                if name != 'id':
                    field.disabled = True

        # disallow type changed from and to contributor
        if questionnaire.type == Questionnaire.Type.CONTRIBUTOR:
            form.fields['type'].choices = [choice for choice in Questionnaire.Type.choices if choice[0] == Questionnaire.Type.CONTRIBUTOR]
        else:
            form.fields['type'].choices = [choice for choice in Questionnaire.Type.choices if choice[0] != Questionnaire.Type.CONTRIBUTOR]

    return form, formset


@manager_required
def questionnaire_edit(request, questionnaire_id):
    questionnaire = get_object_or_404(Questionnaire, id=questionnaire_id)
    editable = questionnaire.can_be_edited_by_manager

    form, formset = make_questionnaire_edit_forms(request, questionnaire, editable)

    if form.is_valid() and formset.is_valid():
        form.save()
        if editable:
            formset.save()

        messages.success(request, _("Successfully updated questionnaire."))
        return redirect('staff:questionnaire_index')

    template_data = dict(questionnaire=questionnaire, form=form, formset=formset, editable=editable)
    return render(request, "staff_questionnaire_form.html", template_data)


def get_identical_form_and_formset(questionnaire):
    """
    Generates a Questionnaire creation form and formset filled out like the already exisiting Questionnaire
    specified in questionnaire_id. Used for copying and creating of new versions.
    """
    inline_question_formset = inlineformset_factory(Questionnaire, Question, formset=AtLeastOneFormSet, form=QuestionForm, extra=1, exclude=('questionnaire',))

    form = QuestionnaireForm(instance=questionnaire)
    return form, inline_question_formset(instance=questionnaire, queryset=questionnaire.questions.all())


@manager_required
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

        return render(request, "staff_questionnaire_form.html", dict(form=form, formset=formset, editable=True))

    form, formset = get_identical_form_and_formset(copied_questionnaire)
    return render(request, "staff_questionnaire_form.html", dict(form=form, formset=formset, editable=True))


@manager_required
def questionnaire_new_version(request, questionnaire_id):
    old_questionnaire = get_object_or_404(Questionnaire, id=questionnaire_id)

    # Check if we can use the old name with the current time stamp.
    timestamp = date.today()
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
                old_questionnaire.visibility = Questionnaire.Visibility.HIDDEN
                old_questionnaire.save()

                if not form.is_valid() or not formset.is_valid():
                    raise IntegrityError

                form.save()
                formset.save()
                messages.success(request, _("Successfully created questionnaire."))
                return redirect('staff:questionnaire_index')

        except IntegrityError:
            return render(request, "staff_questionnaire_form.html", dict(form=form, formset=formset, editable=True))

    form, formset = get_identical_form_and_formset(old_questionnaire)
    return render(request, "staff_questionnaire_form.html", dict(form=form, formset=formset, editable=True))


@require_POST
@manager_required
def questionnaire_delete(request):
    questionnaire_id = request.POST.get("questionnaire_id")
    questionnaire = get_object_or_404(Questionnaire, id=questionnaire_id)

    if not questionnaire.can_be_deleted_by_manager:
        raise SuspiciousOperation("Deleting questionnaire not allowed")
    questionnaire.delete()
    return HttpResponse()  # 200 OK


@require_POST
@manager_required
def questionnaire_update_indices(request):
    updated_indices = request.POST
    for questionnaire_id, new_order in updated_indices.items():
        questionnaire = Questionnaire.objects.get(pk=questionnaire_id)
        questionnaire.order = new_order
        questionnaire.save()
    return HttpResponse()


@require_POST
@manager_required
def questionnaire_visibility(request):
    questionnaire_id = request.POST.get("questionnaire_id")
    visibility = int(request.POST.get("visibility"))
    if visibility not in Questionnaire.Visibility.values:
        raise SuspiciousOperation("Invalid visibility choice")
    questionnaire = get_object_or_404(Questionnaire, id=questionnaire_id)
    questionnaire.visibility = visibility
    questionnaire.save()
    return HttpResponse()


@require_POST
@manager_required
def questionnaire_set_locked(request):
    questionnaire_id = request.POST.get("questionnaire_id")
    is_locked = bool(int(request.POST.get("is_locked")))
    questionnaire = get_object_or_404(Questionnaire, id=questionnaire_id)
    questionnaire.is_locked = is_locked
    questionnaire.save()
    return HttpResponse()


@manager_required
def degree_index(request):
    degrees = Degree.objects.all()

    DegreeFormset = modelformset_factory(Degree, form=DegreeForm, can_delete=True, extra=1)
    formset = DegreeFormset(request.POST or None, queryset=degrees)

    if formset.is_valid():
        formset.save()
        messages.success(request, _("Successfully updated the degrees."))
        return redirect('staff:degree_index')

    return render(request, "staff_degree_index.html", dict(formset=formset))


@manager_required
def course_type_index(request):
    course_types = CourseType.objects.all()

    CourseTypeFormset = modelformset_factory(CourseType, form=CourseTypeForm, can_delete=True, extra=1)
    formset = CourseTypeFormset(request.POST or None, queryset=course_types)

    if formset.is_valid():
        formset.save()
        messages.success(request, _("Successfully updated the course types."))
        return redirect('staff:course_type_index')

    return render(request, "staff_course_type_index.html", dict(formset=formset))


@manager_required
def course_type_merge_selection(request):
    form = CourseTypeMergeSelectionForm(request.POST or None)

    if form.is_valid():
        main_type = form.cleaned_data['main_type']
        other_type = form.cleaned_data['other_type']
        return redirect('staff:course_type_merge', main_type.id, other_type.id)

    return render(request, "staff_course_type_merge_selection.html", dict(form=form))


@manager_required
def course_type_merge(request, main_type_id, other_type_id):
    main_type = get_object_or_404(CourseType, id=main_type_id)
    other_type = get_object_or_404(CourseType, id=other_type_id)

    if request.method == 'POST':
        Course.objects.filter(type=other_type).update(type=main_type)
        other_type.delete()
        messages.success(request, _("Successfully merged course types."))
        return redirect('staff:course_type_index')

    courses_with_other_type = Course.objects.filter(type=other_type).order_by('semester__created_at', 'name_de')
    return render(request, "staff_course_type_merge.html",
        dict(main_type=main_type, other_type=other_type, courses_with_other_type=courses_with_other_type))


@manager_required
def user_index(request):
    filter_users = get_parameter_from_url_or_session(request, "filter_users")

    users = UserProfile.objects.all()
    if filter_users:
        users = users.exclude(is_active=False)

    users = (users
        # the following six annotations basically add three bools indicating whether each user is part of a group or not.
        .annotate(manager_group_count=Sum(Case(When(groups__name="Manager", then=1), output_field=IntegerField())))
        .annotate(is_manager=ExpressionWrapper(Q(manager_group_count__exact=1), output_field=BooleanField()))
        .annotate(reviewer_group_count=Sum(Case(When(groups__name="Reviewer", then=1), output_field=IntegerField())))
        .annotate(is_reviewer=ExpressionWrapper(Q(reviewer_group_count__exact=1), output_field=BooleanField()))
        .annotate(grade_publisher_group_count=Sum(Case(When(groups__name="Grade publisher", then=1), output_field=IntegerField())))
        .annotate(is_grade_publisher=ExpressionWrapper(Q(grade_publisher_group_count__exact=1), output_field=BooleanField()))
        .prefetch_related('contributions', 'evaluations_participating_in', 'evaluations_participating_in__course__semester', 'represented_users', 'ccing_users', 'courses_responsible_for')
        .order_by('last_name', 'first_name', 'username'))

    return render(request, "staff_user_index.html", dict(users=users, filter_users=filter_users))


@manager_required
def user_create(request):
    form = UserForm(request.POST or None, instance=UserProfile())

    if form.is_valid():
        form.save()
        messages.success(request, _("Successfully created user."))
        return redirect('staff:user_index')

    return render(request, "staff_user_form.html", dict(form=form))


@manager_required
def user_import(request):
    excel_form = UserImportForm(request.POST or None, request.FILES or None)
    import_type = ImportType.User

    errors = []
    warnings = {}
    success_messages = []

    if request.method == "POST":
        operation = request.POST.get('operation')
        if operation not in ('test', 'import'):
            raise SuspiciousOperation("Invalid POST operation")

        if operation == 'test':
            delete_import_file(request.user.id, import_type)  # remove old files if still exist
            excel_form.fields['excel_file'].required = True
            if excel_form.is_valid():
                excel_file = excel_form.cleaned_data['excel_file']
                file_content = excel_file.read()
                __, success_messages, warnings, errors = UserImporter.process(file_content, test_run=True)
                if not errors:
                    save_import_file(excel_file, request.user.id, import_type)

        elif operation == 'import':
            file_content = get_import_file_content_or_raise(request.user.id, import_type)
            __, success_messages, warnings, __ = UserImporter.process(file_content, test_run=False)
            forward_messages(request, success_messages, warnings)
            delete_import_file(request.user.id, import_type)
            return redirect('staff:user_index')

    test_passed = import_file_exists(request.user.id, import_type)
    # casting warnings to a normal dict is necessary for the template to iterate over it.
    return render(request, "staff_user_import.html", dict(excel_form=excel_form,
        success_messages=success_messages, warnings=dict(warnings), errors=errors, test_passed=test_passed))


@manager_required
def user_edit(request, user_id):
    # See comment in helper_evaluation_edit
    @receiver(RewardPointGranting.granted_by_removal, weak=True)
    def notify_reward_points(grantings, **_kwargs):  # pylint: disable=unused-variable
        assert len(grantings) == 1

        messages.info(request,
            ngettext(
                'The removal of evaluations has granted the user "{granting.user_profile.username}" {granting.value} reward point for the active semester.',
                'The removal of evaluations has granted the user "{granting.user_profile.username}" {granting.value} reward points for the active semester.',
                grantings[0].value
            ).format(granting=grantings[0])
        )

    user = get_object_or_404(UserProfile, id=user_id)
    form = UserForm(request.POST or None, request.FILES or None, instance=user)

    evaluations_contributing_to = Evaluation.objects.filter(
        Q(contributions__contributor=user) | Q(course__responsibles__in=[user])
    ).distinct().order_by('course__semester')

    if form.is_valid():
        form.save()
        delete_navbar_cache_for_users([user])
        messages.success(request, _("Successfully updated user."))
        return redirect('staff:user_index')

    return render(request, "staff_user_form.html", dict(form=form, evaluations_contributing_to=evaluations_contributing_to))


@require_POST
@manager_required
def user_delete(request):
    user_id = request.POST.get("user_id")
    user = get_object_or_404(UserProfile, id=user_id)

    if not user.can_be_deleted_by_manager:
        raise SuspiciousOperation("Deleting user not allowed")
    user.delete()
    return HttpResponse()  # 200 OK


@manager_required
def user_bulk_update(request):
    form = UserBulkUpdateForm(request.POST or None, request.FILES or None)
    operation = request.POST.get('operation')
    test_run = operation == 'test'
    import_type = ImportType.UserBulkUpdate

    if request.POST:
        if operation not in ('test', 'bulk_update'):
            raise SuspiciousOperation("Invalid POST operation")

        if test_run:
            delete_import_file(request.user.id, import_type)  # remove old files if still exist
            form.fields['username_file'].required = True
            if form.is_valid():
                username_file = form.cleaned_data['username_file']
                file_content = username_file.read()
                success = False
                try:
                    success = bulk_update_users(request, file_content, test_run)
                except Exception:  # pylint: disable=broad-except
                    if settings.DEBUG:
                        raise
                    messages.error(request, _("An error happened when processing the file. Make sure the file meets the requirements."))

                if success:
                    save_import_file(username_file, request.user.id, import_type)
        else:
            file_content = get_import_file_content_or_raise(request.user.id, import_type)
            bulk_update_users(request, file_content, test_run)
            delete_import_file(request.user.id, import_type)
            return redirect('staff:user_index')

    test_passed = import_file_exists(request.user.id, import_type)
    return render(request, "staff_user_bulk_update.html", dict(form=form, test_passed=test_passed))


@manager_required
def user_merge_selection(request):
    form = UserMergeSelectionForm(request.POST or None)

    if form.is_valid():
        main_user = form.cleaned_data['main_user']
        other_user = form.cleaned_data['other_user']
        return redirect('staff:user_merge', main_user.id, other_user.id)

    return render(request, "staff_user_merge_selection.html", dict(form=form))


@manager_required
def user_merge(request, main_user_id, other_user_id):
    main_user = get_object_or_404(UserProfile, id=main_user_id)
    other_user = get_object_or_404(UserProfile, id=other_user_id)

    if request.method == 'POST':
        merged_user, errors, warnings = merge_users(main_user, other_user)
        if errors:
            messages.error(request, _("Merging the users failed. No data was changed."))
        else:
            messages.success(request, _("Successfully merged users."))
        return redirect('staff:user_index')

    merged_user, errors, warnings = merge_users(main_user, other_user, preview=True)
    return render(request, "staff_user_merge.html", dict(main_user=main_user, other_user=other_user, merged_user=merged_user, errors=errors, warnings=warnings))


@manager_required
def template_edit(request, template_id):
    template = get_object_or_404(EmailTemplate, id=template_id)
    form = EmailTemplateForm(request.POST or None, request.FILES or None, instance=template)

    if form.is_valid():
        form.save()
        messages.success(request, _("Successfully updated template."))
        return redirect('staff:index')

    return render(request, "staff_template_form.html", dict(form=form, template=template))


@manager_required
def faq_index(request):
    sections = FaqSection.objects.all()

    SectionFormset = modelformset_factory(FaqSection, form=FaqSectionForm, can_delete=True, extra=1)
    formset = SectionFormset(request.POST or None, queryset=sections)

    if formset.is_valid():
        formset.save()
        messages.success(request, _("Successfully updated the FAQ sections."))
        return redirect('staff:faq_index')

    return render(request, "staff_faq_index.html", dict(formset=formset, sections=sections))


@manager_required
def faq_section(request, section_id):
    section = get_object_or_404(FaqSection, id=section_id)
    questions = FaqQuestion.objects.filter(section=section)

    InlineQuestionFormset = inlineformset_factory(FaqSection, FaqQuestion, form=FaqQuestionForm, can_delete=True, extra=1, exclude=('section',))
    formset = InlineQuestionFormset(request.POST or None, queryset=questions, instance=section)

    if formset.is_valid():
        formset.save()
        messages.success(request, _("Successfully updated the FAQ questions."))
        return redirect('staff:faq_index')

    template_data = dict(formset=formset, section=section, questions=questions)
    return render(request, "staff_faq_section.html", template_data)


@manager_required
def download_sample_xls(_request, filename):
    email_placeholder = "institution.com"

    if filename not in ["sample.xls", "sample_user.xls"]:
        raise SuspiciousOperation("Invalid file name.")

    read_book = open_workbook(settings.STATICFILES_DIRS[0] + "/" + filename, formatting_info=True)
    write_book = copy_workbook(read_book)
    for sheet_index in range(read_book.nsheets):
        read_sheet = read_book.sheet_by_index(sheet_index)
        write_sheet = write_book.get_sheet(sheet_index)
        for row in range(read_sheet.nrows):
            for col in range(read_sheet.ncols):
                value = read_sheet.cell(row, col).value
                if email_placeholder in value:
                    write_sheet.write(row, col, value.replace(email_placeholder, settings.INSTITUTION_EMAIL_DOMAINS[0]))

    response = FileResponse(filename, content_type="application/vnd.ms-excel")
    write_book.save(response)
    return response


@manager_required
def development_components(request):
    theme_colors = ['primary', 'secondary', 'success', 'info', 'warning', 'danger', 'light', 'dark']
    template_data = {
        'theme_colors': theme_colors
    }
    return render(request, "staff_development_components.html", template_data)


@manager_required
def export_contributor_results_view(request, contributor_id):
    contributor = get_object_or_404(UserProfile, id=contributor_id)
    return export_contributor_results(contributor)
