import csv
import itertools
from collections import OrderedDict, defaultdict, namedtuple
from collections.abc import Container
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, cast

import openpyxl
from django.conf import settings
from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import PermissionDenied, SuspiciousOperation
from django.db import IntegrityError, transaction
from django.db.models import (
    BooleanField,
    Case,
    Count,
    ExpressionWrapper,
    Func,
    IntegerField,
    OuterRef,
    Prefetch,
    Q,
    Sum,
    When,
)
from django.dispatch import receiver
from django.forms import BaseForm, formset_factory
from django.forms.models import inlineformset_factory, modelformset_factory
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseBadRequest, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.html import format_html
from django.utils.translation import get_language
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy, ngettext
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, FormView, UpdateView
from django_stubs_ext import StrOrPromise

from evap.contributor.views import export_contributor_results
from evap.evaluation.auth import manager_required, reviewer_required, staff_permission_required
from evap.evaluation.models import (
    Answer,
    Contribution,
    Course,
    CourseType,
    Degree,
    EmailTemplate,
    Evaluation,
    FaqQuestion,
    FaqSection,
    Infotext,
    Question,
    Questionnaire,
    RatingAnswerCounter,
    Semester,
    TextAnswer,
    UserProfile,
    VoteTimestamp,
)
from evap.evaluation.tools import (
    AttachmentResponse,
    FormsetView,
    HttpResponseNoContent,
    SaveValidFormMixin,
    get_object_from_dict_pk_entry_or_logged_40x,
    get_parameter_from_url_or_session,
    sort_formset,
)
from evap.grades.models import GradeDocument
from evap.results.exporters import ResultsExporter
from evap.results.tools import TextResult, calculate_average_distribution, distribution_to_grade
from evap.results.views import update_template_cache_of_published_evaluations_in_course
from evap.rewards.models import RewardPointGranting
from evap.rewards.tools import can_reward_points_be_used_by, is_semester_activated
from evap.staff import staff_mode
from evap.staff.forms import (
    AtLeastOneFormset,
    ContributionCopyForm,
    ContributionCopyFormset,
    ContributionForm,
    ContributionFormset,
    CourseCopyForm,
    CourseForm,
    CourseTypeForm,
    CourseTypeMergeSelectionForm,
    DegreeForm,
    EvaluationCopyForm,
    EvaluationEmailForm,
    EvaluationForm,
    EvaluationParticipantCopyForm,
    ExportSheetForm,
    FaqQuestionForm,
    FaqSectionForm,
    ImportForm,
    InfotextForm,
    ModelWithImportNamesFormset,
    QuestionForm,
    QuestionnaireForm,
    QuestionnairesAssignForm,
    RemindResponsibleForm,
    SemesterForm,
    SingleResultForm,
    TextAnswerForm,
    TextAnswerWarningForm,
    UserBulkUpdateForm,
    UserEditSelectionForm,
    UserForm,
    UserImportForm,
    UserMergeSelectionForm,
)
from evap.staff.importers import (
    ImporterLogEntry,
    import_enrollments,
    import_persons_from_evaluation,
    import_persons_from_file,
    import_users,
)
from evap.staff.tools import (
    ImportType,
    bulk_update_users,
    delete_import_file,
    find_unreviewed_evaluations,
    get_import_file_content_or_raise,
    import_file_exists,
    merge_users,
    save_import_file,
)
from evap.student.forms import QuestionnaireVotingForm
from evap.student.models import TextAnswerWarning
from evap.student.views import render_vote_page


@manager_required
def index(request):
    template_data = {
        "semesters": Semester.objects.all(),
        "templates": EmailTemplate.objects.all().order_by("id"),
        "sections": FaqSection.objects.all(),
        "disable_breadcrumb_manager": True,
    }
    return render(request, "staff_index.html", template_data)


def annotate_evaluations_with_grade_document_counts(evaluations):
    return evaluations.annotate(
        midterm_grade_documents_count=Count(
            "course__grade_documents",
            filter=Q(course__grade_documents__type=GradeDocument.Type.MIDTERM_GRADES),
            distinct=True,
        ),
        final_grade_documents_count=Count(
            "course__grade_documents",
            filter=Q(course__grade_documents__type=GradeDocument.Type.FINAL_GRADES),
            distinct=True,
        ),
    )


def get_evaluations_with_prefetched_data(semester):
    evaluations = (
        semester.evaluations.select_related("course__type")
        .prefetch_related(
            Prefetch(
                "contributions", queryset=Contribution.objects.filter(contributor=None), to_attr="general_contribution"
            ),
            "course__degrees",
            "course__responsibles",
            "course__semester",
            "contributions__questionnaires",
        )
        .annotate(
            num_contributors=Count("contributions", filter=~Q(contributions__contributor=None), distinct=True),
            num_textanswers=Count(
                "contributions__textanswer_set",
                filter=Q(contributions__evaluation__can_publish_text_results=True),
                distinct=True,
            ),
            num_reviewed_textanswers=Count(
                "contributions__textanswer_set",
                filter=~Q(contributions__textanswer_set__review_decision=TextAnswer.ReviewDecision.UNDECIDED),
                distinct=True,
            ),
            num_course_evaluations=Count("course__evaluations", distinct=True),
        )
    ).order_by("pk")
    evaluations = annotate_evaluations_with_grade_document_counts(evaluations)
    evaluations = Evaluation.annotate_with_participant_and_voter_counts(evaluations)

    return evaluations


@reviewer_required
def semester_view(request, semester_id) -> HttpResponse:
    semester = get_object_or_404(Semester, id=semester_id)
    if semester.results_are_archived and not request.user.is_manager:
        raise PermissionDenied
    rewards_active = is_semester_activated(semester)

    evaluations = get_evaluations_with_prefetched_data(semester)
    evaluations = sorted(evaluations, key=lambda cr: cr.full_name)
    courses = Course.objects.filter(semester=semester).prefetch_related(
        "type", "degrees", "responsibles", "evaluations"
    )

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

    degree_stats: dict[Degree, Stats] = defaultdict(Stats)
    total_stats = Stats()
    for evaluation in evaluations:
        if evaluation.is_single_result:
            continue
        degrees = evaluation.course.degrees.all()
        stats_objects = [degree_stats[degree] for degree in degrees]
        stats_objects += [total_stats]
        for stats in stats_objects:
            if evaluation.state >= Evaluation.State.IN_EVALUATION:
                stats.num_enrollments_in_evaluation += evaluation.num_participants
                stats.num_votes += evaluation.num_voters
                stats.num_textanswers += evaluation.num_textanswers
                stats.num_textanswers_reviewed += evaluation.num_reviewed_textanswers
            if evaluation.state >= Evaluation.State.EVALUATED:
                stats.num_evaluations_evaluated += 1
            if evaluation.state != Evaluation.State.NEW:
                stats.num_evaluations += 1
                stats.first_start = min(stats.first_start, evaluation.vote_start_datetime)
                stats.last_end = max(stats.last_end, evaluation.vote_end_date)
    degree_stats = OrderedDict(sorted(degree_stats.items(), key=lambda x: x[0].order))

    degree_stats_with_total = cast(dict[Degree | str, Stats], degree_stats)
    degree_stats_with_total["total"] = total_stats

    template_data = {
        "semester": semester,
        "evaluations": evaluations,
        "Evaluation": Evaluation,
        "disable_breadcrumb_semester": True,
        "rewards_active": rewards_active,
        "num_evaluations": len(evaluations),
        "degree_stats": degree_stats_with_total,
        "courses": courses,
        "approval_states": [
            Evaluation.State.NEW,
            Evaluation.State.PREPARED,
            Evaluation.State.EDITOR_APPROVED,
            Evaluation.State.APPROVED,
        ],
    }
    return render(request, "staff_semester_view.html", template_data)


class EvaluationOperation:
    email_template_name: str | None = None
    email_template_contributor_name: str | None = None
    email_template_participant_name: str | None = None
    confirmation_message: StrOrPromise | None = None

    @staticmethod
    def applicable_to(evaluation):
        raise NotImplementedError

    @staticmethod
    def warning_for_inapplicables(amount):
        raise NotImplementedError

    @staticmethod
    def apply(
        request, evaluations, email_template=None, email_template_contributor=None, email_template_participant=None
    ):
        raise NotImplementedError


class RevertToNewOperation(EvaluationOperation):
    confirmation_message = gettext_lazy("Do you want to revert the following evaluations to preparation?")

    @staticmethod
    def applicable_to(evaluation):
        return Evaluation.State.PREPARED <= evaluation.state <= Evaluation.State.APPROVED

    @staticmethod
    def warning_for_inapplicables(amount):
        return ngettext(
            "{} evaluation can not be reverted, because it already started. It was removed from the selection.",
            "{} evaluations can not be reverted, because they already started. They were removed from the selection.",
            amount,
        ).format(amount)

    @staticmethod
    def apply(
        request, evaluations, email_template=None, email_template_contributor=None, email_template_participant=None
    ):
        assert email_template_contributor is None
        assert email_template_participant is None

        for evaluation in evaluations:
            evaluation.revert_to_new()
            evaluation.save()
        messages.success(
            request,
            ngettext(
                "Successfully reverted {} evaluation to in preparation.",
                "Successfully reverted {} evaluations to in preparation.",
                len(evaluations),
            ).format(len(evaluations)),
        )


class ReadyForEditorsOperation(EvaluationOperation):
    email_template_name = EmailTemplate.EDITOR_REVIEW_NOTICE
    confirmation_message = gettext_lazy("Do you want to send the following evaluations to editor review?")

    @staticmethod
    def applicable_to(evaluation):
        return evaluation.state in [Evaluation.State.NEW, Evaluation.State.EDITOR_APPROVED]

    @staticmethod
    def warning_for_inapplicables(amount):
        return ngettext(
            "{} evaluation can not be reverted, because it already started. It was removed from the selection.",
            "{} evaluations can not be reverted, because they already started. They were removed from the selection.",
            amount,
        ).format(amount)

    @staticmethod
    def apply(
        request, evaluations, email_template=None, email_template_contributor=None, email_template_participant=None
    ):
        assert email_template_contributor is None
        assert email_template_participant is None

        for evaluation in evaluations:
            evaluation.ready_for_editors()
            evaluation.save()
        messages.success(
            request,
            ngettext(
                "Successfully enabled {} evaluation for editor review.",
                "Successfully enabled {} evaluations for editor review.",
                len(evaluations),
            ).format(len(evaluations)),
        )
        if email_template:
            evaluations_by_responsible = {}
            for evaluation in evaluations:
                for responsible in evaluation.course.responsibles.all():
                    evaluations_by_responsible.setdefault(responsible, []).append(evaluation)

            for responsible, responsible_evaluations in evaluations_by_responsible.items():
                body_params = {"user": responsible, "evaluations": responsible_evaluations}
                editors = UserProfile.objects.filter(
                    contributions__evaluation__in=responsible_evaluations,
                    contributions__role=Contribution.Role.EDITOR,
                ).exclude(pk=responsible.pk)
                email_template.send_to_user(
                    responsible,
                    subject_params={},
                    body_params=body_params,
                    use_cc=True,
                    additional_cc_users=editors,
                    request=request,
                )


class BeginEvaluationOperation(EvaluationOperation):
    email_template_name = EmailTemplate.EVALUATION_STARTED
    confirmation_message = gettext_lazy("Do you want to immediately start the following evaluations?")

    @staticmethod
    def applicable_to(evaluation):
        return evaluation.state == Evaluation.State.APPROVED and evaluation.vote_end_date >= date.today()

    @staticmethod
    def warning_for_inapplicables(amount):
        return ngettext(
            "{} evaluation can not be started, because it was not approved, was already evaluated or its evaluation end date lies in the past. It was removed from the selection.",
            "{} evaluations can not be started, because they were not approved, were already evaluated or their evaluation end dates lie in the past. They were removed from the selection.",
            amount,
        ).format(amount)

    @staticmethod
    def apply(
        request, evaluations, email_template=None, email_template_contributor=None, email_template_participant=None
    ):
        assert email_template_contributor is None
        assert email_template_participant is None

        for evaluation in evaluations:
            evaluation.vote_start_datetime = datetime.now()
            evaluation.begin_evaluation()
            evaluation.save()
        messages.success(
            request,
            ngettext(
                "Successfully started {} evaluation.", "Successfully started {} evaluations.", len(evaluations)
            ).format(len(evaluations)),
        )
        if email_template:
            email_template.send_to_users_in_evaluations(
                evaluations, [EmailTemplate.Recipients.ALL_PARTICIPANTS], use_cc=False, request=request
            )


class UnpublishOperation(EvaluationOperation):
    confirmation_message = gettext_lazy("Do you want to unpublish the following evaluations?")

    @staticmethod
    def applicable_to(evaluation):
        return evaluation.state == Evaluation.State.PUBLISHED

    @staticmethod
    def warning_for_inapplicables(amount):
        return ngettext(
            "{} evaluation can not be unpublished, because it's results have not been published. It was removed from the selection.",
            "{} evaluations can not be unpublished because their results have not been published. They were removed from the selection.",
            amount,
        ).format(amount)

    @staticmethod
    def apply(
        request, evaluations, email_template=None, email_template_contributor=None, email_template_participant=None
    ):
        assert email_template_contributor is None
        assert email_template_participant is None

        for evaluation in evaluations:
            evaluation.unpublish()
            evaluation.save()
        messages.success(
            request,
            ngettext(
                "Successfully unpublished {} evaluation.", "Successfully unpublished {} evaluations.", len(evaluations)
            ).format(len(evaluations)),
        )


class PublishOperation(EvaluationOperation):
    email_template_contributor_name = EmailTemplate.PUBLISHING_NOTICE_CONTRIBUTOR
    email_template_participant_name = EmailTemplate.PUBLISHING_NOTICE_PARTICIPANT
    confirmation_message = gettext_lazy("Do you want to publish the following evaluations?")

    @staticmethod
    def applicable_to(evaluation):
        return evaluation.state == Evaluation.State.REVIEWED

    @staticmethod
    def warning_for_inapplicables(amount):
        return ngettext(
            "{} evaluation can not be published, because it's not finished or not all of its text answers have been reviewed. It was removed from the selection.",
            "{} evaluations can not be published, because they are not finished or not all of their text answers have been reviewed. They were removed from the selection.",
            amount,
        ).format(amount)

    @staticmethod
    def apply(
        request, evaluations, email_template=None, email_template_contributor=None, email_template_participant=None
    ):
        assert email_template is None

        for evaluation in evaluations:
            evaluation.publish()
            evaluation.save()
        messages.success(
            request,
            ngettext(
                "Successfully published {} evaluation.", "Successfully published {} evaluations.", len(evaluations)
            ).format(len(evaluations)),
        )

        if email_template_contributor:
            EmailTemplate.send_contributor_publish_notifications(evaluations, template=email_template_contributor)
        if email_template_participant:
            EmailTemplate.send_participant_publish_notifications(evaluations, template=email_template_participant)


EVALUATION_OPERATIONS = {
    Evaluation.State.NEW: RevertToNewOperation,
    Evaluation.State.PREPARED: ReadyForEditorsOperation,
    Evaluation.State.IN_EVALUATION: BeginEvaluationOperation,
    Evaluation.State.REVIEWED: UnpublishOperation,
    Evaluation.State.PUBLISHED: PublishOperation,
}


def target_state_and_operation_from_str(target_state_str: str) -> tuple[int, type[EvaluationOperation]]:
    try:
        target_state = int(target_state_str)
    except (KeyError, ValueError, TypeError) as err:
        raise SuspiciousOperation("Could not parse target_state") from err

    if target_state not in EVALUATION_OPERATIONS:
        raise SuspiciousOperation(f"Unknown target state: {target_state}")

    return target_state, EVALUATION_OPERATIONS[target_state]


@manager_required
def evaluation_operation(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    if semester.participations_are_archived:
        raise PermissionDenied

    evaluation_ids = (request.GET if request.method == "GET" else request.POST).getlist("evaluation")
    evaluations = list(
        annotate_evaluations_with_grade_document_counts(
            Evaluation.objects.filter(id__in=evaluation_ids).prefetch_related("course__semester")
        )
    )
    if any(evaluation.course.semester != semester for evaluation in evaluations):
        raise SuspiciousOperation

    evaluations.sort(key=lambda evaluation: evaluation.full_name)

    target_state, operation = target_state_and_operation_from_str(request.GET["target_state"])

    if request.method == "POST":
        email_template = None
        email_template_contributor = None
        email_template_participant = None
        if request.POST.get("send_email") == "on":
            email_template = EmailTemplate(
                subject=request.POST["email_subject"],
                plain_content=request.POST["email_plain"],
                html_content=request.POST["email_html"],
            )
        if request.POST.get("send_email_contributor") == "on":
            email_template_contributor = EmailTemplate(
                subject=request.POST["email_subject_contributor"],
                plain_content=request.POST["email_plain_contributor"],
                html_content=request.POST["email_html_contributor"],
            )
        if request.POST.get("send_email_participant") == "on":
            email_template_participant = EmailTemplate(
                subject=request.POST["email_subject_participant"],
                plain_content=request.POST["email_plain_participant"],
                html_content=request.POST["email_html_participant"],
            )

        operation.apply(request, evaluations, email_template, email_template_contributor, email_template_participant)
        return redirect("staff:semester_view", semester.id)

    applicable_evaluations = list(filter(operation.applicable_to, evaluations))
    difference = len(evaluations) - len(applicable_evaluations)
    if difference:
        messages.warning(request, operation.warning_for_inapplicables(difference))
    if not applicable_evaluations:  # no evaluations where applicable or none were selected
        messages.warning(request, _("Please select at least one evaluation."))
        return redirect("staff:semester_view", semester.id)

    email_template = None
    email_template_contributor = None
    email_template_participant = None
    if operation.email_template_name:
        email_template = EmailTemplate.objects.get(name=operation.email_template_name)
    if operation.email_template_contributor_name:
        email_template_contributor = EmailTemplate.objects.get(name=operation.email_template_contributor_name)
    if operation.email_template_participant_name:
        email_template_participant = EmailTemplate.objects.get(name=operation.email_template_participant_name)

    template_data = {
        "semester": semester,
        "evaluations": applicable_evaluations,
        "target_state": target_state,
        "confirmation_message": operation.confirmation_message,
        "email_template": email_template,
        "email_template_contributor": email_template_contributor,
        "email_template_participant": email_template_participant,
        "show_email_checkbox": email_template is not None
        or email_template_contributor is not None
        or email_template_participant is not None,
    }

    return render(request, "staff_evaluation_operation.html", template_data)


@manager_required
class SemesterCreateView(SuccessMessageMixin, CreateView):
    template_name = "staff_semester_form.html"
    model = Semester
    form_class = SemesterForm
    success_message = gettext_lazy("Successfully created semester.")

    def get_success_url(self) -> str:
        assert self.object is not None
        return reverse("staff:semester_view", args=[self.object.id])


@manager_required
class SemesterEditView(SuccessMessageMixin, UpdateView):
    template_name = "staff_semester_form.html"
    model = Semester
    form_class = SemesterForm
    pk_url_kwarg = "semester_id"
    success_message = gettext_lazy("Successfully updated semester.")

    def get_success_url(self) -> str:
        return reverse("staff:semester_view", args=[self.object.id])


@require_POST
@manager_required
@transaction.atomic
def semester_make_active(request):
    semester = get_object_from_dict_pk_entry_or_logged_40x(Semester, request.POST, "semester_id")

    Semester.objects.update(is_active=None)
    semester.is_active = True
    semester.save()

    return HttpResponse()


@require_POST
@manager_required
def semester_delete(request):
    semester = get_object_from_dict_pk_entry_or_logged_40x(Semester, request.POST, "semester_id")

    if not semester.can_be_deleted_by_manager:
        raise SuspiciousOperation("Deleting semester not allowed")
    with transaction.atomic():
        RatingAnswerCounter.objects.filter(contribution__evaluation__course__semester=semester).delete()
        TextAnswer.objects.filter(contribution__evaluation__course__semester=semester).delete()
        Contribution.objects.filter(evaluation__course__semester=semester).delete()
        Evaluation.objects.filter(course__semester=semester).delete()
        Course.objects.filter(semester=semester).delete()
        semester.delete()
    return redirect("staff:index")


@manager_required
def semester_import(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    if semester.participations_are_archived:
        raise PermissionDenied

    excel_form = ImportForm(request.POST or None, request.FILES or None)
    import_type = ImportType.SEMESTER

    importer_log = None

    if request.method == "POST":
        operation = request.POST.get("operation")
        if operation not in ("test", "import"):
            raise SuspiciousOperation("Invalid POST operation")

        if operation == "test":
            delete_import_file(request.user.id, import_type)  # remove old files if still exist
            excel_form.fields["excel_file"].required = True
            if excel_form.is_valid():
                excel_file = excel_form.cleaned_data["excel_file"]
                file_content = excel_file.read()
                importer_log = import_enrollments(
                    file_content, semester, vote_start_datetime=None, vote_end_date=None, test_run=True
                )
                if not importer_log.has_errors():
                    save_import_file(excel_file, request.user.id, import_type)

        elif operation == "import":
            file_content = get_import_file_content_or_raise(request.user.id, import_type)
            excel_form.fields["vote_start_datetime"].required = True
            excel_form.fields["vote_end_date"].required = True
            if excel_form.is_valid():
                vote_start_datetime = excel_form.cleaned_data["vote_start_datetime"]
                vote_end_date = excel_form.cleaned_data["vote_end_date"]
                importer_log = import_enrollments(
                    file_content, semester, vote_start_datetime, vote_end_date, test_run=False
                )
                importer_log.forward_messages_to_django(request)
                delete_import_file(request.user.id, import_type)
                return redirect("staff:semester_view", semester_id)

    test_passed = import_file_exists(request.user.id, import_type)
    # casting warnings to a normal dict is necessary for the template to iterate over it.
    return render(
        request,
        "staff_semester_import.html",
        {
            "semester": semester,
            "importer_log": importer_log,
            "excel_form": excel_form,
            "test_passed": test_passed,
        },
    )


@manager_required
def semester_export(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)

    ExportSheetFormset = formset_factory(form=ExportSheetForm, can_delete=True, extra=0, min_num=1, validate_min=True)
    formset = ExportSheetFormset(request.POST or None, form_kwargs={"semester": semester})

    if formset.is_valid():
        include_not_enough_voters = request.POST.get("include_not_enough_voters") == "on"
        include_unpublished = request.POST.get("include_unpublished") == "on"
        selection_list = []
        for form in formset:
            selection_list.append((form.cleaned_data["selected_degrees"], form.cleaned_data["selected_course_types"]))

        filename = f"Evaluation-{semester.name}-{get_language()}.xls"
        response = AttachmentResponse(filename, content_type="application/vnd.ms-excel")

        ResultsExporter().export(response, [semester], selection_list, include_not_enough_voters, include_unpublished)
        return response

    return render(request, "staff_semester_export.html", {"semester": semester, "formset": formset})


@manager_required
def semester_raw_export(_request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)

    filename = f"Evaluation-{semester.name}-{get_language()}_raw.csv"
    response = AttachmentResponse(filename, content_type="text/csv")

    writer = csv.writer(response, delimiter=";", lineterminator="\n")
    writer.writerow(
        [
            _("Name"),
            _("Degrees"),
            _("Type"),
            _("Single result"),
            _("State"),
            _("#Voters"),
            _("#Participants"),
            _("#Text answers"),
            _("Average grade"),
        ]
    )
    for evaluation in sorted(semester.evaluations.all(), key=lambda cr: cr.full_name):
        degrees = ", ".join([degree.name for degree in evaluation.course.degrees.all()])
        avg_grade = ""
        if evaluation.can_staff_see_average_grade:
            distribution = calculate_average_distribution(evaluation)
            if distribution is not None:
                avg_grade = f"{distribution_to_grade(distribution):.1f}"
        writer.writerow(
            [
                evaluation.full_name,
                degrees,
                evaluation.course.type.name,
                evaluation.is_single_result,
                evaluation.state_str,
                evaluation.num_voters,
                evaluation.num_participants,
                evaluation.textanswer_set.count(),
                avg_grade,
            ]
        )

    return response


@manager_required
def semester_participation_export(_request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    participants = (
        UserProfile.objects.filter(evaluations_participating_in__course__semester=semester).distinct().order_by("email")
    )

    filename = f"Evaluation-{semester.name}-{get_language()}_participation.csv"
    response = AttachmentResponse(filename, content_type="text/csv")

    writer = csv.writer(response, delimiter=";", lineterminator="\n")
    writer.writerow(
        [
            _("Email"),
            _("Can use reward points"),
            _("#Required evaluations voted for"),
            _("#Required evaluations"),
            _("#Optional evaluations voted for"),
            _("#Optional evaluations"),
            _("Earned reward points"),
        ]
    )
    for participant in participants:
        number_of_required_evaluations = semester.evaluations.filter(participants=participant, is_rewarded=True).count()
        number_of_required_evaluations_voted_for = semester.evaluations.filter(
            voters=participant, is_rewarded=True
        ).count()
        number_of_optional_evaluations = semester.evaluations.filter(
            participants=participant, is_rewarded=False
        ).count()
        number_of_optional_evaluations_voted_for = semester.evaluations.filter(
            voters=participant, is_rewarded=False
        ).count()
        query = RewardPointGranting.objects.filter(semester=semester, user_profile=participant).aggregate(Sum("value"))
        earned_reward_points = query["value__sum"] or 0
        writer.writerow(
            [
                participant.email,
                can_reward_points_be_used_by(participant),
                number_of_required_evaluations_voted_for,
                number_of_required_evaluations,
                number_of_optional_evaluations_voted_for,
                number_of_optional_evaluations,
                earned_reward_points,
            ]
        )

    return response


@manager_required
def vote_timestamps_export(_request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    timestamps = VoteTimestamp.objects.filter(evaluation__course__semester=semester).prefetch_related(
        "evaluation__course__degrees"
    )

    filename = f"Voting-Timestamps-{semester.name}.csv"
    response = AttachmentResponse(filename, content_type="text/csv")

    writer = csv.writer(response, delimiter=";", lineterminator="\n")
    writer.writerow(
        [
            _("Evaluation id"),
            _("Course type"),
            _("Course degrees"),
            _("Vote end date"),
            _("Timestamp"),
        ]
    )

    for timestamp in timestamps:
        writer.writerow(
            [
                timestamp.evaluation.id,
                timestamp.evaluation.course.type.name,
                ", ".join([degree.name for degree in timestamp.evaluation.course.degrees.all()]),
                timestamp.evaluation.vote_end_date,
                timestamp.timestamp,
            ]
        )

    return response


@manager_required
def semester_questionnaire_assign(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    if semester.participations_are_archived:
        raise PermissionDenied
    evaluations = semester.evaluations.filter(state=Evaluation.State.NEW)
    course_types = CourseType.objects.filter(courses__evaluations__in=evaluations)
    form = QuestionnairesAssignForm(request.POST or None, course_types=course_types)

    if form.is_valid():
        for evaluation in evaluations:
            if form.cleaned_data[evaluation.course.type.name]:
                evaluation.general_contribution.questionnaires.set(form.cleaned_data[evaluation.course.type.name])
            if form.cleaned_data["all-contributors"]:
                for contribution in evaluation.contributions.exclude(contributor=None):
                    contribution.questionnaires.set(form.cleaned_data["all-contributors"])
            evaluation.save()

        messages.success(request, _("Successfully assigned questionnaires."))
        return redirect("staff:semester_view", semester_id)

    return render(request, "staff_semester_questionnaire_assign_form.html", {"semester": semester, "form": form})


@manager_required
def semester_preparation_reminder(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)

    evaluations = semester.evaluations.filter(
        state__in=[Evaluation.State.PREPARED, Evaluation.State.EDITOR_APPROVED]
    ).prefetch_related("course__degrees")

    prepared_evaluations = semester.evaluations.filter(state=Evaluation.State.PREPARED)
    responsibles = UserProfile.objects.filter(courses_responsible_for__evaluations__in=prepared_evaluations).distinct()

    responsible_list = [
        (
            responsible,
            [evaluation for evaluation in evaluations if responsible in evaluation.course.responsibles.all()],
            responsible.delegates.all(),
        )
        for responsible in responsibles
    ]

    if request.method == "POST":
        template = EmailTemplate.objects.get(name=EmailTemplate.EDITOR_REVIEW_REMINDER)
        subject_params = {}
        for responsible, evaluations, __ in responsible_list:
            body_params = {"user": responsible, "evaluations": evaluations}
            template.send_to_user(responsible, subject_params, body_params, use_cc=True, request=request)
        messages.success(request, _("Successfully sent reminders to everyone."))
        return HttpResponse()

    template_data = {"semester": semester, "responsible_list": responsible_list}
    return render(request, "staff_semester_preparation_reminder.html", template_data)


@manager_required
def semester_grade_reminder(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)

    courses = (
        semester.courses.filter(
            evaluations__state__gte=Evaluation.State.EVALUATED,
            evaluations__wait_for_grade_upload_before_publishing=True,
            gets_no_grade_documents=False,
        )
        .distinct()
        .prefetch_related("responsibles")
    )

    courses = [course for course in courses if not course.final_grade_documents.exists()]
    courses.sort(key=lambda course: course.name)

    responsibles = UserProfile.objects.filter(courses_responsible_for__in=courses).distinct()

    responsible_list = [
        (responsible, [course for course in courses if responsible in course.responsibles.all()])
        for responsible in responsibles
    ]

    template_data = {"semester": semester, "responsible_list": responsible_list}
    return render(request, "staff_semester_grade_reminder.html", template_data)


@manager_required
def send_reminder(request, semester_id, responsible_id):
    responsible = get_object_or_404(UserProfile, id=responsible_id)
    semester = get_object_or_404(Semester, id=semester_id)

    form = RemindResponsibleForm(request.POST or None, responsible=responsible)

    evaluations = Evaluation.objects.filter(state=Evaluation.State.PREPARED, course__responsibles__in=[responsible])

    if form.is_valid():
        form.send(request, evaluations)
        messages.success(request, _("Successfully sent reminder to {}.").format(responsible.full_name))
        return redirect("staff:semester_preparation_reminder", semester_id)

    return render(
        request, "staff_semester_send_reminder.html", {"semester": semester, "responsible": responsible, "form": form}
    )


@require_POST
@manager_required
def semester_archive_participations(request):
    semester = get_object_from_dict_pk_entry_or_logged_40x(Semester, request.POST, "semester_id")

    if not semester.participations_can_be_archived:
        raise SuspiciousOperation("Archiving participations for this semester is not allowed")
    semester.archive()
    return HttpResponse()  # 200 OK


@require_POST
@manager_required
def semester_delete_grade_documents(request):
    semester = get_object_from_dict_pk_entry_or_logged_40x(Semester, request.POST, "semester_id")

    if not semester.grade_documents_can_be_deleted:
        raise SuspiciousOperation("Deleting grade documents for this semester is not allowed")
    semester.delete_grade_documents()
    return HttpResponse()  # 200 OK


@require_POST
@manager_required
def semester_archive_results(request):
    semester_id = request.POST.get("semester_id")
    semester = get_object_or_404(Semester, id=semester_id)

    if not semester.results_can_be_archived:
        raise SuspiciousOperation("Archiving results for this semester is not allowed")
    semester.archive_results()
    return HttpResponse()  # 200 OK


@manager_required
def course_create(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    if semester.participations_are_archived:
        raise PermissionDenied

    course = Course(semester=semester)
    course_form = CourseForm(request.POST or None, instance=course)

    operation = request.POST.get("operation")

    if course_form.is_valid():
        if operation not in ("save", "save_create_evaluation", "save_create_single_result"):
            raise SuspiciousOperation("Invalid POST operation")

        course = course_form.save()

        messages.success(request, _("Successfully created course."))
        if operation == "save_create_evaluation":
            return redirect("staff:evaluation_create_for_course", course.id)
        if operation == "save_create_single_result":
            return redirect("staff:single_result_create_for_course", course.id)
        return redirect("staff:semester_view", semester_id)

    return render(
        request, "staff_course_form.html", {"semester": semester, "course_form": course_form, "editable": True}
    )


@manager_required
def course_copy(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    course_form = CourseCopyForm(request.POST or None, instance=course)

    if course_form.is_valid():
        copied_course = course_form.save()
        messages.success(request, _("Successfully copied course."))

        inactive_users = UserProfile.objects.filter(
            Q(contributions__evaluation__course=copied_course, is_active=False)
            | Q(courses_responsible_for=copied_course, is_active=False)
        ).distinct()
        if inactive_users:
            messages.warning(
                request,
                _("The accounts of the following contributors were reactivated:")
                + f" {', '.join(user.full_name for user in inactive_users)}",
            )
            inactive_users.update(is_active=True)

        return redirect("staff:semester_view", copied_course.semester_id)

    evaluations = sorted(course.evaluations.exclude(is_single_result=True), key=lambda cr: cr.full_name)
    return render(
        request,
        "staff_course_copyform.html",
        {
            "course": course,
            "evaluations": evaluations,
            "semester": course.semester,
            "course_form": course_form,
            "editable": True,
            "disable_breadcrumb_course": True,
        },
    )


@manager_required
class CourseEditView(SuccessMessageMixin, UpdateView):
    model = Course
    pk_url_kwarg = "course_id"
    form_class = CourseForm
    template_name = "staff_course_form.html"
    success_message = gettext_lazy("Successfully updated course.")

    object: Course

    def get_object(self, *args, **kwargs) -> Course:
        course = super().get_object(*args, **kwargs)
        if self.request.method == "POST" and not course.can_be_edited_by_manager:
            raise SuspiciousOperation("Modifying this course is not allowed.")
        return course

    def get_context_data(self, **kwargs) -> dict[str, Any]:
        context_data = super().get_context_data(**kwargs) | {
            "semester": self.object.semester,
            "editable": self.object.can_be_edited_by_manager,
            "disable_breadcrumb_course": True,
        }
        context_data["course_form"] = context_data.pop("form")
        return context_data

    def form_valid(self, form: BaseForm) -> HttpResponse:
        assert isinstance(form, CourseForm)  # https://www.github.com/typeddjango/django-stubs/issues/1809

        if self.request.POST.get("operation") not in ("save", "save_create_evaluation", "save_create_single_result"):
            raise SuspiciousOperation("Invalid POST operation")

        response = super().form_valid(form)
        if form.has_changed():
            update_template_cache_of_published_evaluations_in_course(self.object)
        return response

    def get_success_url(self) -> str:
        match self.request.POST["operation"]:
            case "save":
                return reverse("staff:semester_view", args=[self.object.semester.id])
            case "save_create_evaluation":
                return reverse("staff:evaluation_create_for_course", args=[self.object.id])
            case "save_create_single_result":
                return reverse("staff:single_result_create_for_course", args=[self.object.id])
        raise SuspiciousOperation("Unexpected operation")


@require_POST
@manager_required
def course_delete(request):
    course = get_object_from_dict_pk_entry_or_logged_40x(Course, request.POST, "course_id")
    if not course.can_be_deleted_by_manager:
        raise SuspiciousOperation("Deleting course not allowed")
    course.delete()
    return HttpResponse()  # 200 OK


def evaluation_create_impl(request, semester: Semester, course: Course | None):
    if course is not None:
        assert course.semester == semester
    if semester.participations_are_archived:
        raise PermissionDenied
    evaluation = Evaluation(course=course)

    InlineContributionFormset = inlineformset_factory(
        Evaluation, Contribution, formset=ContributionFormset, form=ContributionForm, extra=1
    )

    evaluation_form = EvaluationForm(request.POST or None, instance=evaluation, semester=semester)
    formset = InlineContributionFormset(
        request.POST or None, instance=evaluation, form_kwargs={"evaluation": evaluation}
    )

    if evaluation_form.is_valid() and formset.is_valid():
        evaluation = evaluation_form.save()
        formset.save()
        update_template_cache_of_published_evaluations_in_course(evaluation.course)

        messages.success(request, _("Successfully created evaluation."))
        return redirect("staff:semester_view", semester.id)

    return render(
        request,
        "staff_evaluation_form.html",
        {
            "semester": semester,
            "evaluation_form": evaluation_form,
            "formset": formset,
            "manager": True,
            "editable": True,
            "state": "",
            "questionnaires_with_answers_per_contributor": {},
        },
    )


@manager_required
def evaluation_create_for_semester(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    return evaluation_create_impl(request, semester, None)


@manager_required
def evaluation_create_for_course(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    return evaluation_create_impl(request, course.semester, course)


@manager_required
def evaluation_copy(request, evaluation_id):
    evaluation = get_object_or_404(Evaluation, id=evaluation_id)

    form = EvaluationCopyForm(request.POST or None, evaluation)

    InlineContributionFormset = inlineformset_factory(
        Evaluation, Contribution, formset=ContributionCopyFormset, form=ContributionCopyForm, extra=1
    )
    formset = InlineContributionFormset(request.POST or None, instance=evaluation, new_instance=form.instance)

    if form.is_valid() and formset.is_valid():
        copied_evaluation = form.save()
        formset.save()
        update_template_cache_of_published_evaluations_in_course(copied_evaluation.course)

        messages.success(request, _("Successfully created evaluation."))
        return redirect("staff:semester_view", evaluation.course.semester.pk)

    return render(
        request,
        "staff_evaluation_form.html",
        {
            "semester": evaluation.course.semester,
            "evaluation_form": form,
            "formset": formset,
            "manager": True,
            "editable": True,
            "state": "",
            "questionnaires_with_answers_per_contributor": {},
        },
    )


def single_result_create_impl(request, semester: Semester, course: Course | None):
    if course is not None:
        assert course.semester == semester
    if semester.participations_are_archived:
        raise PermissionDenied
    evaluation = Evaluation(course=course)

    form = SingleResultForm(request.POST or None, instance=evaluation, semester=semester)

    if form.is_valid():
        evaluation = form.save()
        update_template_cache_of_published_evaluations_in_course(evaluation.course)

        messages.success(request, _("Successfully created single result."))
        return redirect("staff:semester_view", semester.pk)

    return render(request, "staff_single_result_form.html", {"semester": semester, "form": form, "editable": True})


@manager_required
def single_result_create_for_semester(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    return single_result_create_impl(request, semester, None)


@manager_required
def single_result_create_for_course(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    return single_result_create_impl(request, course.semester, course)


@manager_required
def evaluation_edit(request, evaluation_id):
    evaluation = get_object_or_404(Evaluation, id=evaluation_id)

    if request.method == "POST" and not evaluation.can_be_edited_by_manager:
        raise SuspiciousOperation("Modifying this evaluation is not allowed.")

    if evaluation.is_single_result:
        return helper_single_result_edit(request, evaluation)
    return helper_evaluation_edit(request, evaluation)


@manager_required
def helper_evaluation_edit(request, evaluation):
    # Show a message when reward points are granted during the lifetime of the calling view.
    # The @receiver will only live as long as the request is processed
    # as the callback is captured by a weak reference in the Django Framework
    # and no other strong references are being kept.
    # See https://github.com/e-valuation/EvaP/issues/1361 for more information and discussion.
    @receiver(RewardPointGranting.granted_by_removal, weak=True)
    def notify_reward_points(grantings, **_kwargs):
        for granting in grantings:
            messages.info(
                request,
                ngettext(
                    'The removal as participant has granted the user "{granting.user_profile.email}" {granting.value} reward point for the semester.',
                    'The removal as participant has granted the user "{granting.user_profile.email}" {granting.value} reward points for the semester.',
                    granting.value,
                ).format(granting=granting),
            )

    editable = evaluation.can_be_edited_by_manager
    InlineContributionFormset = inlineformset_factory(
        Evaluation, Contribution, formset=ContributionFormset, form=ContributionForm, extra=1 if editable else 0
    )

    evaluation_form = EvaluationForm(request.POST or None, instance=evaluation, semester=evaluation.course.semester)
    formset = InlineContributionFormset(
        request.POST or None, instance=evaluation, form_kwargs={"evaluation": evaluation}
    )

    operation = request.POST.get("operation")

    if evaluation_form.is_valid() and formset.is_valid():
        if operation not in ("save", "approve"):
            raise SuspiciousOperation("Invalid POST operation")

        if not evaluation.can_be_edited_by_manager or evaluation.participations_are_archived:
            raise SuspiciousOperation("Modifying this evaluation is not allowed.")

        if (
            Evaluation.State.EVALUATED <= evaluation.state <= Evaluation.State.REVIEWED
            and evaluation.is_in_evaluation_period
        ):
            evaluation.reopen_evaluation()

        form_has_changed = evaluation_form.has_changed() or formset.has_changed()

        evaluation_form.save()
        formset.save()

        if operation == "approve":
            evaluation.manager_approve()
            evaluation.save()
            if form_has_changed:
                messages.success(request, _("Successfully updated and approved evaluation."))
            else:
                messages.success(request, _("Successfully approved evaluation."))
        else:
            messages.success(request, _("Successfully updated evaluation."))

        return redirect("staff:semester_view", evaluation.course.semester.id)

    assert set(Answer.__subclasses__()) == {TextAnswer, RatingAnswerCounter}
    contributor_questionnaire_pairs = [
        (answer.contribution.contributor, answer.question.questionnaire)
        for answer_cls in [TextAnswer, RatingAnswerCounter]
        for answer in answer_cls.objects.filter(contribution__evaluation=evaluation).select_related(
            "question__questionnaire", "contribution__contributor"
        )
    ]

    questionnaires_with_answers_per_contributor = defaultdict(list)
    for contributor, questionnaire in contributor_questionnaire_pairs:
        questionnaires_with_answers_per_contributor[contributor].append(questionnaire)

    if evaluation_form.errors or formset.errors:
        messages.error(request, _("The form was not saved. Please resolve the errors shown below."))
    sort_formset(request, formset)
    template_data = {
        "evaluation": evaluation,
        "semester": evaluation.course.semester,
        "evaluation_form": evaluation_form,
        "formset": formset,
        "manager": True,
        "state": evaluation.state,
        "editable": editable,
        "questionnaires_with_answers_per_contributor": questionnaires_with_answers_per_contributor,
    }
    return render(request, "staff_evaluation_form.html", template_data)


@manager_required
def helper_single_result_edit(request, evaluation):
    semester = evaluation.course.semester
    form = SingleResultForm(request.POST or None, instance=evaluation, semester=semester)

    if form.is_valid():
        if not evaluation.can_be_edited_by_manager or evaluation.participations_are_archived:
            raise SuspiciousOperation("Modifying this evaluation is not allowed.")

        form.save()
        messages.success(request, _("Successfully updated single result."))
        return redirect("staff:semester_view", semester.id)

    return render(
        request,
        "staff_single_result_form.html",
        {"evaluation": evaluation, "semester": semester, "form": form, "editable": evaluation.can_be_edited_by_manager},
    )


@require_POST
@manager_required
def evaluation_delete(request):
    evaluation = get_object_from_dict_pk_entry_or_logged_40x(Evaluation, request.POST, "evaluation_id")

    if not evaluation.can_be_deleted_by_manager:
        raise SuspiciousOperation("Deleting evaluation not allowed")
    if evaluation.is_single_result:
        RatingAnswerCounter.objects.filter(contribution__evaluation=evaluation).delete()
    evaluation.delete()
    update_template_cache_of_published_evaluations_in_course(evaluation.course)
    return HttpResponse()  # 200 OK


@manager_required
def evaluation_email(request, evaluation_id):
    evaluation = get_object_or_404(Evaluation, id=evaluation_id)
    export = "export" in request.POST
    form = EvaluationEmailForm(request.POST or None, evaluation=evaluation, export=export)

    if form.is_valid():
        if export:
            email_addresses = "; ".join(form.email_addresses())
            messages.info(request, _("Recipients: ") + "\n" + email_addresses)
            return render(
                request,
                "staff_evaluation_email.html",
                {"semester": evaluation.course.semester, "evaluation": evaluation, "form": form},
            )
        form.send(request)
        messages.success(request, _("Successfully sent emails for '%s'.") % evaluation.full_name)
        return redirect("staff:semester_view", evaluation.course.semester.pk)

    return render(
        request,
        "staff_evaluation_email.html",
        {"semester": evaluation.course.semester, "evaluation": evaluation, "form": form},
    )


def helper_delete_users_from_evaluation(evaluation, operation):
    if "participants" in operation:
        deleted_person_count = evaluation.participants.count()
        deletion_message = _("{} participants were deleted from evaluation {}")
        evaluation.participants.clear()
    elif "contributors" in operation:
        deleted_person_count = evaluation.contributions.exclude(contributor=None).count()
        deletion_message = _("{} contributors were deleted from evaluation {}")
        evaluation.contributions.exclude(contributor=None).delete()

    return deleted_person_count, deletion_message


@manager_required
@transaction.atomic
def evaluation_person_management(request, evaluation_id):
    # This view indeed handles 4 tasks. However, they are tightly coupled, splitting them up
    # would lead to more code duplication. Thus, we decided to leave it as is for now
    # pylint: disable=too-many-locals
    evaluation = get_object_or_404(Evaluation, id=evaluation_id)
    if evaluation.participations_are_archived:
        raise PermissionDenied

    # Each form required two times so the errors can be displayed correctly
    participant_excel_form = UserImportForm(request.POST or None, request.FILES or None, prefix="pe")
    participant_copy_form = EvaluationParticipantCopyForm(request.POST or None, prefix="pc")
    contributor_excel_form = UserImportForm(request.POST or None, request.FILES or None, prefix="ce")
    contributor_copy_form = EvaluationParticipantCopyForm(request.POST or None, prefix="cc")

    importer_log = None

    if request.method == "POST":
        operation = request.POST.get("operation")
        if operation not in (
            "test-participants",
            "import-participants",
            "copy-participants",
            "import-replace-participants",
            "copy-replace-participants",
            "test-contributors",
            "import-contributors",
            "copy-contributors",
            "import-replace-contributors",
            "copy-replace-contributors",
        ):
            raise SuspiciousOperation("Invalid POST operation")

        import_type = ImportType.PARTICIPANT if "participants" in operation else ImportType.CONTRIBUTOR
        excel_form = participant_excel_form if "participants" in operation else contributor_excel_form
        copy_form = participant_copy_form if "participants" in operation else contributor_copy_form

        if "test" in operation:
            delete_import_file(request.user.id, import_type)  # remove old files if still exist
            excel_form.fields["excel_file"].required = True
            if excel_form.is_valid():
                excel_file = excel_form.cleaned_data["excel_file"]
                file_content = excel_file.read()
                importer_log = import_persons_from_file(
                    import_type, evaluation, test_run=True, file_content=file_content
                )
                if not importer_log.has_errors():
                    save_import_file(excel_file, request.user.id, import_type)

        else:
            if "replace" in operation:
                deleted_person_count, deletion_message = helper_delete_users_from_evaluation(evaluation, operation)

            if "import" in operation:
                file_content = get_import_file_content_or_raise(request.user.id, import_type)
                importer_log = import_persons_from_file(
                    import_type, evaluation, test_run=False, file_content=file_content
                )
                delete_import_file(request.user.id, import_type)
            elif "copy" in operation:
                copy_form.evaluation_selection_required = True
                if copy_form.is_valid():
                    import_evaluation = copy_form.cleaned_data["evaluation"]
                    importer_log = import_persons_from_evaluation(
                        import_type, evaluation, test_run=False, source_evaluation=import_evaluation
                    )

            if "replace" in operation:
                importer_log.add_success(
                    format_html(deletion_message, deleted_person_count, evaluation.full_name),
                    category=ImporterLogEntry.Category.RESULT,
                )

            importer_log.forward_messages_to_django(request)
            return redirect("staff:semester_view", evaluation.course.semester.pk)

    participant_test_passed = import_file_exists(request.user.id, ImportType.PARTICIPANT)
    contributor_test_passed = import_file_exists(request.user.id, ImportType.CONTRIBUTOR)
    # casting warnings to a normal dict is necessary for the template to iterate over it.
    return render(
        request,
        "staff_evaluation_person_management.html",
        {
            "semester": evaluation.course.semester,
            "evaluation": evaluation,
            "participant_excel_form": participant_excel_form,
            "participant_copy_form": participant_copy_form,
            "contributor_excel_form": contributor_excel_form,
            "contributor_copy_form": contributor_copy_form,
            "importer_log": importer_log,
            "participant_test_passed": participant_test_passed,
            "contributor_test_passed": contributor_test_passed,
        },
    )


@manager_required
def evaluation_login_key_export(_request, evaluation_id):
    evaluation = get_object_or_404(Evaluation, id=evaluation_id)

    filename = f"Login_keys-{evaluation.full_name}-{evaluation.course.semester.short_name}.csv"
    response = AttachmentResponse(filename, content_type="text/csv")

    writer = csv.writer(response, delimiter=";", lineterminator="\n")
    writer.writerow([_("Last name"), _("First name"), _("Email"), _("Login key")])

    external_participants = (participant for participant in evaluation.participants.all() if participant.is_external)
    for participant in external_participants:
        participant.ensure_valid_login_key()
        writer.writerow([participant.last_name, participant.first_name, participant.email, participant.login_url])

    return response


TextAnswerSection = namedtuple(
    "TextAnswerSection", ("questionnaire", "contributor", "label", "is_responsible", "results")
)


def get_evaluation_and_contributor_textanswer_sections(
    evaluation: Evaluation,
    textanswer_filter: Q,
) -> tuple[list[TextAnswerSection], list[TextAnswerSection]]:
    evaluation_sections = []
    contributor_sections = []
    evaluation_responsibles = list(evaluation.course.responsibles.all())

    raw_answers = (
        TextAnswer.objects.filter(contribution__evaluation=evaluation)
        .select_related("question__questionnaire", "contribution__contributor")
        .order_by("contribution", "question__questionnaire", "question")
        .filter(textanswer_filter)
    )

    questionnaire_answer_groups = itertools.groupby(
        raw_answers, lambda answer: (answer.contribution, answer.question.questionnaire)
    )

    for (contribution, questionnaire), questionnaire_answers in questionnaire_answer_groups:
        text_results = []
        for question, answers_iter in itertools.groupby(questionnaire_answers, lambda answer: answer.question):
            answers = list(answers_iter)
            if not answers:
                continue
            text_results.append(TextResult(question=question, answers=answers))

        if not text_results:
            continue

        section = TextAnswerSection(
            questionnaire,
            contribution.contributor,
            contribution.label,
            contribution.contributor in evaluation_responsibles,
            text_results,
        )
        if contribution.is_general:
            evaluation_sections.append(section)
        else:
            contributor_sections.append(section)

    return evaluation_sections, contributor_sections


@reviewer_required
def evaluation_textanswers(request: HttpRequest, evaluation_id: int) -> HttpResponse:
    evaluation = get_object_or_404(Evaluation, id=evaluation_id)
    semester = evaluation.course.semester
    if semester.results_are_archived:
        raise PermissionDenied

    if evaluation.state == Evaluation.State.PUBLISHED:
        raise PermissionDenied
    if not evaluation.can_publish_text_results:
        raise PermissionDenied

    view = request.GET.get("view", "quick")
    assert view in ["quick", "full", "undecided", "flagged"]
    filter_for_view = {
        "undecided": Q(review_decision=TextAnswer.ReviewDecision.UNDECIDED),
        "flagged": Q(is_flagged=True),
    }

    evaluation_sections, contributor_sections = get_evaluation_and_contributor_textanswer_sections(
        evaluation,
        filter_for_view.get(view, Q()),
    )

    template_data = {"semester": semester, "evaluation": evaluation, "view": view}

    if view == "quick":
        visited = request.session.get("review-visited", set())
        skipped = request.session.get("review-skipped", set())
        visited.add(evaluation.pk)
        next_evaluations = find_unreviewed_evaluations(semester, visited | skipped)
        if not next_evaluations and (len(visited) > 1 or len(skipped) > 0):
            visited = {evaluation.pk}
            skipped = set()
            request.session["review-skipped"] = skipped
            next_evaluations = find_unreviewed_evaluations(semester, visited | skipped)
        request.session["review-visited"] = visited

        sections = evaluation_sections + contributor_sections
        template_data.update({"sections": sections, "evaluation": evaluation, "next_evaluations": next_evaluations})
        return render(request, "staff_evaluation_textanswers_quick.html", template_data)

    template_data.update({"evaluation_sections": evaluation_sections, "contributor_sections": contributor_sections})
    return render(request, "staff_evaluation_textanswers_full.html", template_data)


@reviewer_required
def semester_flagged_textanswers(request: HttpRequest, semester_id: int) -> HttpResponse:
    semester = get_object_or_404(Semester, id=semester_id)
    flagged_textanswers = TextAnswer.objects.filter(
        is_flagged=True,
        contribution__evaluation__course__semester=semester,
    ).order_by("contribution__evaluation")

    template_data = {
        "semester": semester,
        "flagged_textanswers": flagged_textanswers,
    }
    return render(request, "staff_semester_flagged_textanswers.html", template_data)


@reviewer_required
def evaluation_textanswers_skip(request):
    evaluation = get_object_from_dict_pk_entry_or_logged_40x(Evaluation, request.POST, "evaluation_id")
    visited = request.session.get("review-skipped", set())
    visited.add(evaluation.pk)
    request.session["review-skipped"] = visited
    return HttpResponse()


def assert_textanswer_review_permissions(evaluation: Evaluation) -> None:
    if evaluation.state == Evaluation.State.PUBLISHED:
        raise PermissionDenied
    if evaluation.course.semester.results_are_archived:
        raise PermissionDenied
    if not evaluation.can_publish_text_results:
        raise PermissionDenied


@require_POST
@reviewer_required
def evaluation_textanswers_update_publish(request):
    answer = get_object_from_dict_pk_entry_or_logged_40x(TextAnswer, request.POST, "answer_id")
    evaluation = answer.contribution.evaluation
    action = request.POST.get("action", None)

    assert_textanswer_review_permissions(evaluation)

    if action == "textanswer_edit":
        return redirect("staff:evaluation_textanswer_edit", answer.pk)

    review_decision_for_action = {
        "publish": TextAnswer.ReviewDecision.PUBLIC,
        "make_private": TextAnswer.ReviewDecision.PRIVATE,
        "delete": TextAnswer.ReviewDecision.DELETED,
        "unreview": TextAnswer.ReviewDecision.UNDECIDED,
    }

    if action not in review_decision_for_action:
        raise SuspiciousOperation

    answer.review_decision = review_decision_for_action[action]
    answer.save()

    if evaluation.state == Evaluation.State.EVALUATED and evaluation.is_fully_reviewed:
        evaluation.end_review()
        evaluation.save()
    if evaluation.state == Evaluation.State.REVIEWED and not evaluation.is_fully_reviewed:
        evaluation.reopen_review()
        evaluation.save()

    return HttpResponseNoContent()


@require_POST
@reviewer_required
def evaluation_textanswers_update_flag(request):
    answer = get_object_from_dict_pk_entry_or_logged_40x(TextAnswer, request.POST, "answer_id")
    assert_textanswer_review_permissions(answer.contribution.evaluation)

    is_flagged_bool_string = request.POST.get("is_flagged", None)
    if is_flagged_bool_string not in ["true", "false"]:
        return HttpResponseBadRequest()

    answer.is_flagged = is_flagged_bool_string == "true"
    answer.save()

    return HttpResponseNoContent()


@manager_required
def evaluation_textanswer_edit(request, textanswer_id):
    textanswer = get_object_or_404(TextAnswer, id=textanswer_id)
    evaluation = textanswer.contribution.evaluation
    assert_textanswer_review_permissions(evaluation)

    form = TextAnswerForm(request.POST or None, instance=textanswer)

    if form.is_valid():
        form.save()
        # jump to edited answer
        url = reverse("staff:evaluation_textanswers", args=[evaluation.pk]) + "#" + str(textanswer.id)
        return HttpResponseRedirect(url)

    template_data = {
        "semester": evaluation.course.semester,
        "evaluation": evaluation,
        "form": form,
        "textanswer": textanswer,
    }
    return render(request, "staff_evaluation_textanswer_edit.html", template_data)


@reviewer_required
def evaluation_preview(request, evaluation_id):
    evaluation = get_object_or_404(Evaluation, id=evaluation_id)
    if evaluation.course.semester.results_are_archived and not request.user.is_manager:
        raise PermissionDenied

    return render_vote_page(request, evaluation, preview=True)


@manager_required
def questionnaire_index(request):
    filter_questionnaires = get_parameter_from_url_or_session(request, "filter_questionnaires")

    prefetch_list = ("questions", "contributions__evaluation")
    general_questionnaires = Questionnaire.objects.general_questionnaires().prefetch_related(*prefetch_list)
    contributor_questionnaires = Questionnaire.objects.contributor_questionnaires().prefetch_related(*prefetch_list)

    if filter_questionnaires:
        general_questionnaires = general_questionnaires.exclude(visibility=Questionnaire.Visibility.HIDDEN)
        contributor_questionnaires = contributor_questionnaires.exclude(visibility=Questionnaire.Visibility.HIDDEN)

    general_questionnaires_top = [
        questionnaire for questionnaire in general_questionnaires if questionnaire.is_above_contributors
    ]
    general_questionnaires_bottom = [
        questionnaire for questionnaire in general_questionnaires if questionnaire.is_below_contributors
    ]

    template_data = {
        "general_questionnaires_top": general_questionnaires_top,
        "general_questionnaires_bottom": general_questionnaires_bottom,
        "contributor_questionnaires": contributor_questionnaires,
        "filter_questionnaires": filter_questionnaires,
    }
    return render(request, "staff_questionnaire_index.html", template_data)


@manager_required
def questionnaire_view(request, questionnaire_id):
    questionnaire = get_object_or_404(Questionnaire, id=questionnaire_id)

    # build forms
    contribution = Contribution(contributor=request.user)
    form = QuestionnaireVotingForm(request.POST or None, contribution=contribution, questionnaire=questionnaire)

    return render(request, "staff_questionnaire_view.html", {"forms": [form], "questionnaire": questionnaire})


@manager_required
def questionnaire_create(request):
    questionnaire = Questionnaire()
    InlineQuestionFormset = inlineformset_factory(
        Questionnaire, Question, formset=AtLeastOneFormset, form=QuestionForm, extra=1, exclude=("questionnaire",)
    )

    form = QuestionnaireForm(request.POST or None, instance=questionnaire)
    formset = InlineQuestionFormset(request.POST or None, instance=questionnaire)

    if form.is_valid() and formset.is_valid():
        form.save(force_highest_order=True)
        formset.save()

        messages.success(request, _("Successfully created questionnaire."))
        return redirect("staff:questionnaire_index")

    return render(request, "staff_questionnaire_form.html", {"form": form, "formset": formset, "editable": True})


def disable_all_except_named(fields: dict[str, Any], names_of_editable: Container[str]):
    for name, field in fields.items():
        if name not in names_of_editable:
            field.disabled = True


def make_questionnaire_edit_forms(request, questionnaire, editable):
    if editable:
        formset_kwargs = {"extra": 1}
    else:
        question_count = questionnaire.questions.count()
        formset_kwargs = {
            "extra": 0,
            "can_delete": False,
            "validate_min": True,
            "validate_max": True,
            "min_num": question_count,
            "max_num": question_count,
        }
    InlineQuestionFormset = inlineformset_factory(
        Questionnaire,
        Question,
        formset=AtLeastOneFormset,
        form=QuestionForm,
        exclude=("questionnaire",),
        **formset_kwargs,
    )

    form = QuestionnaireForm(request.POST or None, instance=questionnaire)
    formset = InlineQuestionFormset(request.POST or None, instance=questionnaire)

    if not editable:
        disable_all_except_named(
            form.fields, ["visibility", "is_locked", "name_de", "name_en", "description_de", "description_en", "type"]
        )
        for question_form in formset.forms:
            disable_all_except_named(question_form.fields, ["id"])

        # disallow type changed from and to contributor
        form.fields["type"].choices = [
            choice
            for choice in Questionnaire.Type.choices
            if (choice[0] == Questionnaire.Type.CONTRIBUTOR) == (questionnaire.type == Questionnaire.Type.CONTRIBUTOR)
        ]

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
        return redirect("staff:questionnaire_index")

    template_data = {"questionnaire": questionnaire, "form": form, "formset": formset, "editable": editable}
    return render(request, "staff_questionnaire_form.html", template_data)


def get_identical_form_and_formset(questionnaire):
    """
    Generates a Questionnaire creation form and formset filled out like the already exisiting Questionnaire
    specified in questionnaire_id. Used for copying and creating of new versions.
    """
    inline_question_formset = inlineformset_factory(
        Questionnaire, Question, formset=AtLeastOneFormset, form=QuestionForm, extra=1, exclude=("questionnaire",)
    )

    form = QuestionnaireForm(instance=questionnaire)
    return form, inline_question_formset(instance=questionnaire, queryset=questionnaire.questions.all())


@manager_required
def questionnaire_copy(request, questionnaire_id):
    copied_questionnaire = get_object_or_404(Questionnaire, id=questionnaire_id)

    if request.method == "POST":
        questionnaire = Questionnaire()
        InlineQuestionFormset = inlineformset_factory(
            Questionnaire, Question, formset=AtLeastOneFormset, form=QuestionForm, extra=1, exclude=("questionnaire",)
        )

        form = QuestionnaireForm(request.POST, instance=questionnaire)
        formset = InlineQuestionFormset(request.POST.copy(), instance=questionnaire, save_as_new=True)

        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            messages.success(request, _("Successfully created questionnaire."))
            return redirect("staff:questionnaire_index")

        return render(request, "staff_questionnaire_form.html", {"form": form, "formset": formset, "editable": True})

    form, formset = get_identical_form_and_formset(copied_questionnaire)
    return render(request, "staff_questionnaire_form.html", {"form": form, "formset": formset, "editable": True})


@manager_required
def questionnaire_new_version(request, questionnaire_id):
    old_questionnaire = get_object_or_404(Questionnaire, id=questionnaire_id)

    # Check if we can use the old name with the current time stamp.
    timestamp = date.today()
    new_name_de = f"{old_questionnaire.name_de} (until {timestamp})"
    new_name_en = f"{old_questionnaire.name_en} (until {timestamp})"

    # If not, redirect back and suggest to edit the already created version.
    if Questionnaire.objects.filter(Q(name_de=new_name_de) | Q(name_en=new_name_en)):
        messages.error(request, _("Questionnaire creation aborted. A new version was already created today."))
        return redirect("staff:questionnaire_index")

    if request.method == "POST":
        questionnaire = Questionnaire()
        InlineQuestionFormset = inlineformset_factory(
            Questionnaire, Question, formset=AtLeastOneFormset, form=QuestionForm, extra=1, exclude=("questionnaire",)
        )

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
                return redirect("staff:questionnaire_index")

        except IntegrityError:
            return render(
                request, "staff_questionnaire_form.html", {"form": form, "formset": formset, "editable": True}
            )

    form, formset = get_identical_form_and_formset(old_questionnaire)
    return render(request, "staff_questionnaire_form.html", {"form": form, "formset": formset, "editable": True})


@require_POST
@manager_required
def questionnaire_delete(request):
    questionnaire = get_object_from_dict_pk_entry_or_logged_40x(Questionnaire, request.POST, "questionnaire_id")

    if not questionnaire.can_be_deleted_by_manager:
        raise SuspiciousOperation("Deleting questionnaire not allowed")
    questionnaire.delete()
    return HttpResponse()  # 200 OK


@require_POST
@manager_required
def questionnaire_update_indices(request):
    try:
        order_by_questionnaire = {int(key): int(value) for key, value in request.POST.items()}
    except (TypeError, ValueError) as e:
        raise SuspiciousOperation from e

    questionnaires = list(Questionnaire.objects.filter(pk__in=order_by_questionnaire.keys()))
    if len(questionnaires) != len(order_by_questionnaire):
        raise Http404("Questionnaire not found.")

    for questionnaire in questionnaires:
        questionnaire.order = order_by_questionnaire[questionnaire.pk]

    Questionnaire.objects.bulk_update(questionnaires, ["order"])
    return HttpResponse()


@require_POST
@manager_required
def questionnaire_visibility(request):
    questionnaire = get_object_from_dict_pk_entry_or_logged_40x(Questionnaire, request.POST, "questionnaire_id")
    try:
        visibility = int(request.POST["visibility"])
    except (KeyError, TypeError, ValueError) as e:
        raise SuspiciousOperation from e

    if visibility not in Questionnaire.Visibility.values:
        raise SuspiciousOperation("Invalid visibility choice")

    questionnaire.visibility = visibility
    questionnaire.save()
    return HttpResponse()


@require_POST
@manager_required
def questionnaire_set_locked(request):
    questionnaire = get_object_from_dict_pk_entry_or_logged_40x(Questionnaire, request.POST, "questionnaire_id")
    try:
        is_locked = bool(int(request.POST["is_locked"]))
    except (KeyError, TypeError, ValueError) as e:
        raise SuspiciousOperation from e

    questionnaire.is_locked = is_locked
    questionnaire.save()
    return HttpResponse()


@manager_required
class DegreeIndexView(SuccessMessageMixin, SaveValidFormMixin, FormsetView):
    model = Degree
    formset_class = modelformset_factory(
        Degree,
        form=DegreeForm,
        formset=ModelWithImportNamesFormset,
        can_delete=True,
        extra=1,
    )
    template_name = "staff_degree_index.html"
    success_url = reverse_lazy("staff:degree_index")
    success_message = gettext_lazy("Successfully updated the degrees.")


@manager_required
class CourseTypeIndexView(SuccessMessageMixin, SaveValidFormMixin, FormsetView):
    model = CourseType
    formset_class = modelformset_factory(
        CourseType,
        form=CourseTypeForm,
        formset=ModelWithImportNamesFormset,
        can_delete=True,
        extra=1,
    )
    template_name = "staff_course_type_index.html"
    success_url = reverse_lazy("staff:course_type_index")
    success_message = gettext_lazy("Successfully updated the course types.")


@manager_required
def course_type_merge_selection(request):
    form = CourseTypeMergeSelectionForm(request.POST or None)

    if form.is_valid():
        main_type = form.cleaned_data["main_type"]
        other_type = form.cleaned_data["other_type"]
        return redirect("staff:course_type_merge", main_type.id, other_type.id)

    return render(request, "staff_course_type_merge_selection.html", {"form": form})


@manager_required
def course_type_merge(request, main_type_id, other_type_id):
    main_type = get_object_or_404(CourseType, id=main_type_id)
    other_type = get_object_or_404(CourseType, id=other_type_id)

    if request.method == "POST":
        main_type.import_names += other_type.import_names
        main_type.save()
        Course.objects.filter(type=other_type).update(type=main_type)
        other_type.delete()
        messages.success(request, _("Successfully merged course types."))
        return redirect("staff:course_type_index")

    courses_with_other_type = Course.objects.filter(type=other_type).order_by("semester__created_at", "name_de")
    return render(
        request,
        "staff_course_type_merge.html",
        {"main_type": main_type, "other_type": other_type, "courses_with_other_type": courses_with_other_type},
    )


@manager_required
def text_answer_warnings_index(request):
    text_answer_warnings = TextAnswerWarning.objects.all()

    TextAnswerWarningFormset = modelformset_factory(
        TextAnswerWarning, form=TextAnswerWarningForm, can_delete=True, extra=1
    )
    formset = TextAnswerWarningFormset(request.POST or None, queryset=text_answer_warnings)

    if formset.is_valid():
        formset.save()
        messages.success(request, _("Successfully updated text warning answers."))
        return redirect("staff:text_answer_warnings")

    return render(
        request,
        "staff_text_answer_warnings.html",
        {
            "formset": formset,
            "text_answer_warnings": TextAnswerWarning.objects.all(),
        },
    )


@manager_required
def user_index(request):
    form = UserEditSelectionForm(request.POST or None)

    if form.is_valid():
        user = form.cleaned_data["user"]
        return redirect("staff:user_edit", user.id)

    return render(request, "staff_user_index.html", {"form": form})


@manager_required
def user_list(request):
    filter_users = get_parameter_from_url_or_session(request, "filter_users")

    users = UserProfile.objects.all()
    if filter_users:
        users = users.exclude(is_active=False)

    users = (
        users
        # the following six annotations basically add three bools indicating whether each user is part of a group or not.
        .annotate(manager_group_count=Sum(Case(When(groups__name="Manager", then=1), output_field=IntegerField())))
        .annotate(is_manager=ExpressionWrapper(Q(manager_group_count__exact=1), output_field=BooleanField()))
        .annotate(reviewer_group_count=Sum(Case(When(groups__name="Reviewer", then=1), output_field=IntegerField())))
        .annotate(is_reviewer=ExpressionWrapper(Q(reviewer_group_count__exact=1), output_field=BooleanField()))
        .annotate(
            grade_publisher_group_count=Sum(
                Case(When(groups__name="Grade publisher", then=1), output_field=IntegerField())
            )
        )
        .annotate(
            is_grade_publisher=ExpressionWrapper(Q(grade_publisher_group_count__exact=1), output_field=BooleanField())
        )
        .prefetch_related(
            "contributions",
            "evaluations_participating_in",
            "evaluations_participating_in__course__semester",
            "represented_users",
            "ccing_users",
            "courses_responsible_for",
        )
        .order_by(*UserProfile._meta.ordering)
    )

    return render(request, "staff_user_list.html", {"users": users, "filter_users": filter_users})


@manager_required
class UserCreateView(SuccessMessageMixin, CreateView):
    model = UserProfile
    form_class = UserForm
    template_name = "staff_user_form.html"
    success_url = reverse_lazy("staff:user_index")
    success_message = gettext_lazy("Successfully created user.")


@manager_required
def user_import(request):
    excel_form = UserImportForm(request.POST or None, request.FILES or None)
    import_type = ImportType.USER

    importer_log = None

    if request.method == "POST":
        operation = request.POST.get("operation")
        if operation not in ("test", "import"):
            raise SuspiciousOperation("Invalid POST operation")

        if operation == "test":
            delete_import_file(request.user.id, import_type)  # remove old files if still exist
            excel_form.fields["excel_file"].required = True
            if excel_form.is_valid():
                excel_file = excel_form.cleaned_data["excel_file"]
                file_content = excel_file.read()
                __, importer_log = import_users(file_content, test_run=True)
                if not importer_log.has_errors():
                    save_import_file(excel_file, request.user.id, import_type)

        elif operation == "import":
            file_content = get_import_file_content_or_raise(request.user.id, import_type)
            __, importer_log = import_users(file_content, test_run=False)
            importer_log.forward_messages_to_django(request)
            delete_import_file(request.user.id, import_type)
            return redirect("staff:user_index")

    test_passed = import_file_exists(request.user.id, import_type)
    # casting warnings to a normal dict is necessary for the template to iterate over it.
    return render(
        request,
        "staff_user_import.html",
        {
            "excel_form": excel_form,
            "importer_log": importer_log,
            "test_passed": test_passed,
        },
    )


@manager_required
def user_edit(request, user_id):
    # See comment in helper_evaluation_edit
    @receiver(RewardPointGranting.granted_by_removal, weak=True)
    def notify_reward_points(grantings, **_kwargs):
        assert len(grantings) == 1

        messages.info(
            request,
            ngettext(
                'The removal of evaluations has granted the user "{granting.user_profile.email}" {granting.value} reward point for the active semester.',
                'The removal of evaluations has granted the user "{granting.user_profile.email}" {granting.value} reward points for the active semester.',
                grantings[0].value,
            ).format(granting=grantings[0]),
        )

    user = get_object_or_404(UserProfile, id=user_id)
    form = UserForm(request.POST or None, request.FILES or None, instance=user)

    evaluations_contributing_to = (
        Evaluation.objects.filter(Q(contributions__contributor=user) | Q(course__responsibles__in=[user]))
        .distinct()
        .order_by("course__semester")
    )

    if form.is_valid():
        form.save()
        messages.success(request, _("Successfully updated user."))
        for message in form.remove_messages:
            messages.warning(request, message)
        return redirect("staff:user_index")

    return render(
        request,
        "staff_user_form.html",
        {
            "form": form,
            "evaluations_contributing_to": evaluations_contributing_to,
            "has_due_evaluations": bool(user.get_sorted_due_evaluations()),
            "user_id": user_id,
            "user_with_same_email": form.user_with_same_email,
        },
    )


@require_POST
@manager_required
def user_delete(request):
    user = get_object_from_dict_pk_entry_or_logged_40x(UserProfile, request.POST, "user_id")

    if not user.can_be_deleted_by_manager:
        raise SuspiciousOperation("Deleting user not allowed")
    user.delete()
    messages.success(request, _("Successfully deleted user."))
    return HttpResponse()  # 200 OK


@require_POST
@manager_required
def user_resend_email(request):
    user = get_object_from_dict_pk_entry_or_logged_40x(UserProfile, request.POST, "user_id")

    template = EmailTemplate.objects.get(name=EmailTemplate.EVALUATION_STARTED)
    body_params = {
        "user": user,
        "evaluations": user.get_sorted_due_evaluations(),
        "due_evaluations": {},
    }

    template.send_to_user(user, {}, body_params, use_cc=False)
    messages.success(request, _("Successfully resent evaluation started email."))
    return HttpResponse()  # 200 OK


@manager_required
def user_bulk_update(request):
    form = UserBulkUpdateForm(request.POST or None, request.FILES or None)
    operation = request.POST.get("operation")
    test_run = operation == "test"
    import_type = ImportType.USER_BULK_UPDATE

    if request.POST:
        if operation not in ("test", "bulk_update"):
            raise SuspiciousOperation("Invalid POST operation")

        if test_run:
            delete_import_file(request.user.id, import_type)  # remove old files if still exist
            form.fields["user_file"].required = True
            if form.is_valid():
                user_file = form.cleaned_data["user_file"]
                file_content = user_file.read()
                success = False
                try:
                    success = bulk_update_users(request, file_content, test_run)
                except Exception:  # pylint: disable=broad-except
                    if settings.DEBUG:
                        raise
                    messages.error(
                        request,
                        _("An error happened when processing the file. Make sure the file meets the requirements."),
                    )

                if success:
                    save_import_file(user_file, request.user.id, import_type)
        else:
            file_content = get_import_file_content_or_raise(request.user.id, import_type)
            bulk_update_users(request, file_content, test_run)
            delete_import_file(request.user.id, import_type)
            return redirect("staff:user_index")

    test_passed = import_file_exists(request.user.id, import_type)
    return render(request, "staff_user_bulk_update.html", {"form": form, "test_passed": test_passed})


@manager_required
class UserMergeSelectionView(FormView):
    form_class = UserMergeSelectionForm
    template_name = "staff_user_merge_selection.html"

    def get_context_data(self, **kwargs) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)

        class UserNameFromEmail(Func):
            # django docs support our usage here:
            # https://docs.djangoproject.com/en/5.0/ref/models/expressions/#func-expressions
            # pylint: disable=abstract-method
            template = "split_part(%(expressions)s, '@', 1)"

        query = UserProfile.objects.annotate(username_part_of_email=UserNameFromEmail("email"))

        users_with_merge_candidates = query.annotate(
            merge_candidate_pk=query.filter(username_part_of_email=UserNameFromEmail(OuterRef("email")))
            .filter(pk__lt=OuterRef("pk"))
            .values("pk")[:1]
        ).exclude(merge_candidate_pk=None)

        merge_candidate_ids = [user.merge_candidate_pk for user in users_with_merge_candidates]
        merge_candidates_by_id = {user.pk: user for user in UserProfile.objects.filter(pk__in=merge_candidate_ids)}

        suggested_merges = [
            (user, merge_candidates_by_id[user.merge_candidate_pk])
            for user in users_with_merge_candidates
            if not user.is_external and not merge_candidates_by_id[user.merge_candidate_pk].is_external
        ]

        context["suggested_merges"] = suggested_merges
        return context

    def form_valid(self, form: UserMergeSelectionForm) -> HttpResponse:
        return redirect(
            "staff:user_merge",
            form.cleaned_data["main_user"].id,
            form.cleaned_data["other_user"].id,
        )


@manager_required
def user_merge(request, main_user_id, other_user_id):
    main_user = get_object_or_404(UserProfile, id=main_user_id)
    other_user = get_object_or_404(UserProfile, id=other_user_id)

    if request.method == "POST":
        merged_user, errors, warnings = merge_users(main_user, other_user)
        if errors:
            messages.error(request, _("Merging the users failed. No data was changed."))
        else:
            messages.success(request, _("Successfully merged users."))
        return redirect("staff:user_index")

    merged_user, errors, warnings = merge_users(main_user, other_user, preview=True)
    return render(
        request,
        "staff_user_merge.html",
        {
            "main_user": main_user,
            "other_user": other_user,
            "merged_user": merged_user,
            "errors": errors,
            "warnings": warnings,
        },
    )


@manager_required
class TemplateEditView(SuccessMessageMixin, UpdateView):
    model = EmailTemplate
    pk_url_kwarg = "template_id"
    fields = ("subject", "plain_content", "html_content")
    success_message = gettext_lazy("Successfully updated template.")
    success_url = reverse_lazy("staff:index")
    template_name = "staff_template_form.html"

    def get_context_data(self, **kwargs) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        template = context["template"] = context.pop("emailtemplate")

        available_variables = [
            "contact_email",
            "page_url",
            "login_url",  # only if they need it
            "user",
        ]

        if template.name == EmailTemplate.STUDENT_REMINDER:
            available_variables += ["first_due_in_days", "due_evaluations"]
        elif template.name in [
            EmailTemplate.EDITOR_REVIEW_NOTICE,
            EmailTemplate.EDITOR_REVIEW_REMINDER,
            EmailTemplate.PUBLISHING_NOTICE_CONTRIBUTOR,
            EmailTemplate.PUBLISHING_NOTICE_PARTICIPANT,
        ]:
            available_variables += ["evaluations"]
        elif template.name == EmailTemplate.TEXT_ANSWER_REVIEW_REMINDER:
            available_variables += ["evaluation_url_tuples"]
        elif template.name == EmailTemplate.EVALUATION_STARTED:
            available_variables += ["evaluations", "due_evaluations"]
        elif template.name == EmailTemplate.DIRECT_DELEGATION:
            available_variables += ["evaluation", "delegate_user"]

        available_variables = ["{{ " + variable + " }}" for variable in available_variables]
        available_variables.sort()

        context["available_variables"] = available_variables

        return context


@manager_required
class FaqIndexView(SuccessMessageMixin, SaveValidFormMixin, FormsetView):
    model = FaqSection
    formset_class = modelformset_factory(FaqSection, form=FaqSectionForm, can_delete=True, extra=1)
    template_name = "staff_faq_index.html"
    success_url = reverse_lazy("staff:faq_index")
    success_message = gettext_lazy("Successfully updated the FAQ sections.")

    def get_context_data(self, **kwargs) -> dict[str, Any]:
        return super().get_context_data(**kwargs) | {"sections": FaqSection.objects.all()}


@manager_required
def faq_section(request, section_id):
    section = get_object_or_404(FaqSection, id=section_id)
    questions = FaqQuestion.objects.filter(section=section)

    InlineQuestionFormset = inlineformset_factory(
        FaqSection, FaqQuestion, form=FaqQuestionForm, can_delete=True, extra=1, exclude=("section",)
    )
    formset = InlineQuestionFormset(request.POST or None, queryset=questions, instance=section)

    if formset.is_valid():
        formset.save()
        messages.success(request, _("Successfully updated the FAQ questions."))
        return redirect("staff:faq_index")

    template_data = {"formset": formset, "section": section, "questions": questions}
    return render(request, "staff_faq_section.html", template_data)


@manager_required
class InfotextsView(SuccessMessageMixin, SaveValidFormMixin, FormsetView):
    formset_class = modelformset_factory(Infotext, form=InfotextForm, edit_only=True, extra=0)
    template_name = "staff_infotexts.html"
    success_url = reverse_lazy("staff:infotexts")
    success_message = gettext_lazy("Successfully updated the infotext entries.")


@manager_required
def download_sample_file(_request, filename):
    email_placeholder = "institution.com"

    if filename not in ["sample.xlsx", "sample_user.xlsx"]:
        raise SuspiciousOperation("Invalid file name.")

    book = openpyxl.load_workbook(filename=settings.STATICFILES_DIRS[0] + "/" + filename)
    for sheet in book:
        for row in sheet:
            for cell in row:
                if cell.value is not None:
                    cell.value = cell.value.replace(email_placeholder, settings.INSTITUTION_EMAIL_DOMAINS[0])

    response = AttachmentResponse(
        filename, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    book.save(response)
    return response


@manager_required
def export_contributor_results_view(request, contributor_id):
    contributor = get_object_or_404(UserProfile, id=contributor_id)
    return export_contributor_results(contributor)


@require_POST
@staff_permission_required
def enter_staff_mode(request):
    staff_mode.enter_staff_mode(request)
    return redirect("evaluation:index")


@require_POST
@staff_permission_required
def exit_staff_mode(request):
    staff_mode.exit_staff_mode(request)
    return redirect("evaluation:index")
