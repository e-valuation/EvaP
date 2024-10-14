from django.contrib import messages
from django.core.exceptions import PermissionDenied, SuspiciousOperation
from django.db import IntegrityError, transaction
from django.db.models import Exists, Max, OuterRef, Q
from django.forms.models import inlineformset_factory
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from evap.contributor.forms import DelegateSelectionForm, EditorContributionForm, EvaluationForm
from evap.evaluation.auth import editor_or_delegate_required, responsible_or_contributor_or_delegate_required
from evap.evaluation.models import (
    Contribution,
    Course,
    CourseType,
    EmailTemplate,
    Evaluation,
    Program,
    Semester,
    UserProfile,
)
from evap.evaluation.tools import (
    AttachmentResponse,
    get_object_from_dict_pk_entry_or_logged_40x,
    get_parameter_from_url_or_session,
    sort_formset,
)
from evap.results.exporters import ResultsExporter
from evap.results.tools import annotate_distributions_and_grades, get_evaluations_with_course_result_attributes
from evap.staff.forms import ContributionFormset
from evap.student.views import render_vote_page


@responsible_or_contributor_or_delegate_required
def index(request):
    user = request.user
    show_delegated = get_parameter_from_url_or_session(request, "show_delegated", True)

    represented_proxy_users = user.represented_users.filter(is_proxy_user=True)
    contributor_visible_states = [
        Evaluation.State.PREPARED,
        Evaluation.State.EDITOR_APPROVED,
        Evaluation.State.APPROVED,
        Evaluation.State.IN_EVALUATION,
        Evaluation.State.EVALUATED,
        Evaluation.State.REVIEWED,
        Evaluation.State.PUBLISHED,
    ]
    own_courses = Course.objects.filter(
        Q(evaluations__state__in=contributor_visible_states)
        & (
            Q(responsibles=user)
            | Q(evaluations__contributions__contributor=user)
            | Q(evaluations__contributions__contributor__in=represented_proxy_users)
            | Q(responsibles__in=represented_proxy_users)
        )
    )

    own_evaluations = (
        Evaluation.objects.filter(course__in=own_courses)
        .annotate(contributes_to=Exists(Evaluation.objects.filter(id=OuterRef("id"), contributions__contributor=user)))
        .prefetch_related("course", "course__evaluations", "course__programs", "course__type", "course__semester")
    )
    own_evaluations = [evaluation for evaluation in own_evaluations if evaluation.can_be_seen_by(user)]

    displayed_evaluations = own_evaluations
    if show_delegated:
        represented_users = user.represented_users.exclude(is_proxy_user=True)
        delegated_courses = Course.objects.filter(
            Q(evaluations__state__in=contributor_visible_states)
            & (
                Q(responsibles__in=represented_users)
                | Q(
                    evaluations__contributions__role=Contribution.Role.EDITOR,
                    evaluations__contributions__contributor__in=represented_users,
                )
            )
        )
        delegated_evaluations = Evaluation.objects.filter(course__in=delegated_courses).prefetch_related(
            "course", "course__evaluations", "course__programs", "course__type", "course__semester"
        )
        delegated_evaluations = [evaluation for evaluation in delegated_evaluations if evaluation.can_be_seen_by(user)]
        for evaluation in delegated_evaluations:
            evaluation.delegated_evaluation = True
        displayed_evaluations += set(delegated_evaluations) - set(displayed_evaluations)

    displayed_evaluations.sort(
        key=lambda evaluation: (evaluation.course.name, evaluation.name)
    )  # evaluations must be sorted for regrouping them in the template

    annotate_distributions_and_grades(e for e in displayed_evaluations if e.state == Evaluation.State.PUBLISHED)
    displayed_evaluations = get_evaluations_with_course_result_attributes(displayed_evaluations)

    semesters = Semester.objects.all()
    semester_list = [
        {
            "semester_name": semester.name,
            "id": semester.id,
            "is_active": semester.is_active,
            "evaluations": [
                evaluation for evaluation in displayed_evaluations if evaluation.course.semester_id == semester.id
            ],
        }
        for semester in semesters
    ]

    template_data = {
        "semester_list": semester_list,
        "show_delegated": show_delegated,
        "delegate_selection_form": DelegateSelectionForm(),
    }
    return render(request, "contributor_index.html", template_data)


@editor_or_delegate_required
def evaluation_view(request, evaluation_id):
    user = request.user
    evaluation = get_object_or_404(Evaluation, id=evaluation_id)

    # check rights
    if (
        not evaluation.is_user_editor_or_delegate(user)
        or not Evaluation.State.PREPARED <= evaluation.state <= Evaluation.State.REVIEWED
    ):
        raise PermissionDenied

    InlineContributionFormset = inlineformset_factory(
        Evaluation, Contribution, formset=ContributionFormset, form=EditorContributionForm, extra=0
    )

    form = EvaluationForm(request.POST or None, instance=evaluation)
    formset = InlineContributionFormset(request.POST or None, instance=evaluation)

    # make everything read-only
    for cform in formset.forms + [form]:
        for field in cform.fields.values():
            field.disabled = True

    template_data = {
        "form": form,
        "formset": formset,
        "evaluation": evaluation,
        "editable": False,
        "questionnaires_with_answers_per_contributor": {},
    }

    return render(request, "contributor_evaluation_form.html", template_data)


def render_preview(request, formset, evaluation_form, evaluation):
    # open transaction to not let any other requests see anything of what we're doing here
    try:
        with transaction.atomic():
            evaluation = evaluation_form.save()
            formset.save()
            request.POST = None  # this prevents errors rendered in the vote form

            preview_response = mark_safe(
                render_vote_page(request, evaluation, preview=True, for_rendering_in_modal=True).content.decode()
            )
            raise IntegrityError  # rollback transaction to discard the database writes
    except IntegrityError:
        pass

    return preview_response


@editor_or_delegate_required
def evaluation_edit(request, evaluation_id):
    evaluation = get_object_or_404(Evaluation, id=evaluation_id)

    # check rights
    if not (evaluation.is_user_editor_or_delegate(request.user) and evaluation.state == Evaluation.State.PREPARED):
        raise PermissionDenied

    post_operation = request.POST.get("operation") if request.POST else None
    preview = post_operation == "preview"

    InlineContributionFormset = inlineformset_factory(
        Evaluation, Contribution, formset=ContributionFormset, form=EditorContributionForm, extra=1
    )
    evaluation_form = EvaluationForm(request.POST or None, instance=evaluation)
    formset = InlineContributionFormset(
        request.POST or None, instance=evaluation, form_kwargs={"evaluation": evaluation}
    )

    forms_are_valid = evaluation_form.is_valid() and formset.is_valid()
    if forms_are_valid and not preview:
        if post_operation not in ("save", "approve"):
            raise SuspiciousOperation("Invalid POST operation")

        form_has_changed = evaluation_form.has_changed() or formset.has_changed()

        evaluation_form.save()
        formset.save()

        if post_operation == "approve":
            evaluation.editor_approve()
            evaluation.save()
            if form_has_changed:
                messages.success(request, _("Successfully updated and approved evaluation."))
            else:
                messages.success(request, _("Successfully approved evaluation."))
        else:
            messages.success(request, _("Successfully updated evaluation."))

        return redirect("contributor:index")

    preview_html = None
    if preview and forms_are_valid:
        preview_html = render_preview(request, formset, evaluation_form, evaluation)

    if not forms_are_valid and (evaluation_form.errors or formset.errors):
        if preview:
            messages.error(request, _("The preview could not be rendered. Please resolve the errors shown below."))
        else:
            messages.error(request, _("The form was not saved. Please resolve the errors shown below."))

    sort_formset(request, formset)
    template_data = {
        "form": evaluation_form,
        "formset": formset,
        "evaluation": evaluation,
        "editable": True,
        "preview_html": preview_html,
        "questionnaires_with_answers_per_contributor": {},
    }
    return render(request, "contributor_evaluation_form.html", template_data)


@responsible_or_contributor_or_delegate_required
def evaluation_preview(request, evaluation_id):
    user = request.user
    evaluation = get_object_or_404(Evaluation, id=evaluation_id)

    # check rights
    if not (
        evaluation.is_user_responsible_or_contributor_or_delegate(user)
        and Evaluation.State.PREPARED <= evaluation.state <= Evaluation.State.REVIEWED
    ):
        raise PermissionDenied

    return render_vote_page(request, evaluation, preview=True)


@require_POST
@editor_or_delegate_required
def evaluation_direct_delegation(request, evaluation_id):
    evaluation = get_object_or_404(Evaluation, id=evaluation_id)
    delegate_user = get_object_from_dict_pk_entry_or_logged_40x(UserProfile, request.POST, "delegate_to")

    contribution, created = Contribution.objects.update_or_create(
        evaluation=evaluation,
        contributor=delegate_user,
        defaults={"role": Contribution.Role.EDITOR},
    )
    if created:
        contribution.order = evaluation.contributions.all().aggregate(Max("order"))["order__max"] + 1
        contribution.save()

    template = EmailTemplate.objects.get(name=EmailTemplate.DIRECT_DELEGATION)
    subject_params = {"evaluation": evaluation, "user": request.user, "delegate_user": delegate_user}
    body_params = subject_params

    # we don't provide the request here since send_to_user only uses it to display a warning message in case the user does not have
    # an email address. In this special case, we don't want that warning. Instead, we want a mail to the admins.
    template.send_to_user(
        delegate_user,
        subject_params=subject_params,
        body_params=body_params,
        use_cc=True,
        additional_cc_users=[request.user],
    )

    messages.add_message(
        request,
        messages.SUCCESS,
        _('{} was added as a contributor for evaluation "{}" and was sent an email with further information.').format(
            str(delegate_user), str(evaluation)
        ),
    )

    return redirect("contributor:index")


def export_contributor_results(contributor):
    filename = f"Evaluation_{contributor.full_name}.xls"
    response = AttachmentResponse(filename, content_type="application/vnd.ms-excel")
    ResultsExporter().export(
        response,
        Semester.objects.all(),
        [(Program.objects.all(), CourseType.objects.all())],
        include_not_enough_voters=True,
        include_unpublished=False,
        contributor=contributor,
        verbose_heading=False,
    )
    return response


@responsible_or_contributor_or_delegate_required
def export(request):
    return export_contributor_results(request.user)
