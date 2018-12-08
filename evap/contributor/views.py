from django.contrib import messages
from django.core.exceptions import PermissionDenied, SuspiciousOperation
from django.forms.models import inlineformset_factory
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import ugettext as _
from django.db import IntegrityError, transaction
from django.views.decorators.http import require_POST

from evap.contributor.forms import EvaluationForm, DelegatesForm, EditorContributionForm, DelegateSelectionForm
from evap.evaluation.auth import contributor_or_delegate_required, editor_or_delegate_required, editor_required
from evap.evaluation.models import Contribution, Evaluation, Semester, UserProfile, EmailTemplate
from evap.evaluation.tools import get_parameter_from_url_or_session, STATES_ORDERED, sort_formset
from evap.results.tools import calculate_average_distribution, distribution_to_grade
from evap.staff.forms import ContributionFormSet
from evap.student.views import get_valid_form_groups_or_render_vote_page


@contributor_or_delegate_required
def index(request):
    user = request.user
    show_delegated = get_parameter_from_url_or_session(request, "show_delegated", True)

    contributor_visible_states = ['prepared', 'editor_approved', 'approved', 'in_evaluation', 'evaluated', 'reviewed', 'published']
    own_evaluations = Evaluation.objects.filter(contributions__contributor=user, state__in=contributor_visible_states)

    displayed_evaluations = list(own_evaluations)
    if show_delegated:
        represented_users = user.represented_users.all()
        delegated_evaluations = Evaluation.objects.exclude(id__in=own_evaluations).filter(contributions__can_edit=True, contributions__contributor__in=represented_users, state__in=contributor_visible_states)
        for evaluation in delegated_evaluations:
            evaluation.delegated_evaluation = True
        displayed_evaluations += list(delegated_evaluations)
    displayed_evaluations.sort(key=lambda evaluation: list(STATES_ORDERED.keys()).index(evaluation.state))

    delegate_selection_form = DelegateSelectionForm()

    for evaluation in displayed_evaluations:
        evaluation.distribution = calculate_average_distribution(evaluation)
        evaluation.avg_grade = distribution_to_grade(evaluation.distribution)

    semesters = Semester.objects.all()
    semester_list = [dict(
        semester_name=semester.name,
        id=semester.id,
        is_active_semester=semester.is_active_semester,
        evaluations=[evaluation for evaluation in displayed_evaluations if evaluation.semester_id == semester.id]
    ) for semester in semesters]

    template_data = dict(
        semester_list=semester_list,
        show_delegated=show_delegated,
        delegate_selection_form=delegate_selection_form,
    )
    return render(request, "contributor_index.html", template_data)


@editor_required
def settings_edit(request):
    user = request.user
    form = DelegatesForm(request.POST or None, request.FILES or None, instance=user)

    if form.is_valid():
        form.save()

        messages.success(request, _("Successfully updated your settings."))
        return redirect('contributor:settings_edit')
    else:
        return render(request, "contributor_settings.html", dict(
            form=form,
            delegate_of=user.represented_users.all(),
            cc_users=user.cc_users.all(),
            ccing_users=user.ccing_users.all(),
        ))


@editor_or_delegate_required
def evaluation_view(request, evaluation_id):
    user = request.user
    evaluation = get_object_or_404(Evaluation, id=evaluation_id)

    # check rights
    if not evaluation.is_user_editor_or_delegate(user) or evaluation.state not in ['prepared', 'editor_approved', 'approved', 'in_evaluation', 'evaluated', 'reviewed']:
        raise PermissionDenied

    InlineContributionFormset = inlineformset_factory(Evaluation, Contribution, formset=ContributionFormSet, form=EditorContributionForm, extra=0)

    form = EvaluationForm(request.POST or None, instance=evaluation)
    formset = InlineContributionFormset(request.POST or None, instance=evaluation)

    # make everything read-only
    for cform in formset.forms + [form]:
        for field in cform.fields.values():
            field.disabled = True

    template_data = dict(form=form, formset=formset, evaluation=evaluation, editable=False,
                         responsibles=[contributor.username for contributor in evaluation.responsible_contributors])
    return render(request, "contributor_evaluation_form.html", template_data)


def render_preview(request, formset, evaluation_form, evaluation):
    # open transaction to not let any other requests see anything of what we're doing here
    try:
        with transaction.atomic():
            evaluation = evaluation_form.save()
            evaluation.set_last_modified(request.user)
            evaluation.save()
            formset.save()
            request.POST = None  # this prevents errors rendered in the vote form

            preview_response = get_valid_form_groups_or_render_vote_page(request, evaluation, preview=True, for_rendering_in_modal=True)[1].content.decode()
            raise IntegrityError  # rollback transaction to discard the database writes
    except IntegrityError:
        pass

    return preview_response


@editor_or_delegate_required
def evaluation_edit(request, evaluation_id):
    evaluation = get_object_or_404(Evaluation, id=evaluation_id)

    # check rights
    if not (evaluation.is_user_editor_or_delegate(request.user) and evaluation.state == 'prepared'):
        raise PermissionDenied

    post_operation = request.POST.get('operation') if request.POST else None
    preview = post_operation == 'preview'

    InlineContributionFormset = inlineformset_factory(Evaluation, Contribution, formset=ContributionFormSet, form=EditorContributionForm, extra=1)
    evaluation_form = EvaluationForm(request.POST or None, instance=evaluation)
    formset = InlineContributionFormset(request.POST or None, instance=evaluation, can_change_responsible=False, form_kwargs={'evaluation': evaluation})

    forms_are_valid = evaluation_form.is_valid() and formset.is_valid()
    if forms_are_valid and not preview:
        if post_operation not in ('save', 'approve'):
            raise SuspiciousOperation("Invalid POST operation")

        form_has_changed = evaluation_form.has_changed() or formset.has_changed()

        if form_has_changed:
            evaluation.set_last_modified(request.user)
        evaluation_form.save()
        formset.save()

        if post_operation == 'approve':
            evaluation.editor_approve()
            evaluation.save()
            if form_has_changed:
                messages.success(request, _("Successfully updated and approved evaluation."))
            else:
                messages.success(request, _("Successfully approved evaluation."))
        else:
            messages.success(request, _("Successfully updated evaluation."))

        return redirect('contributor:index')
    else:
        preview_html = None
        if preview and forms_are_valid:
            preview_html = render_preview(request, formset, evaluation_form, evaluation)

        if not forms_are_valid and (evaluation_form.errors or formset.errors):
            if preview:
                messages.error(request, _("The preview could not be rendered. Please resolve the errors shown below."))
            else:
                messages.error(request, _("The form was not saved. Please resolve the errors shown below."))

        sort_formset(request, formset)
        template_data = dict(form=evaluation_form, formset=formset, evaluation=evaluation, editable=True, preview_html=preview_html,
                             responsibles=[contributor.username for contributor in evaluation.responsible_contributors])
        return render(request, "contributor_evaluation_form.html", template_data)


@contributor_or_delegate_required
def evaluation_preview(request, evaluation_id):
    user = request.user
    evaluation = get_object_or_404(Evaluation, id=evaluation_id)

    # check rights
    if not (evaluation.is_user_contributor_or_delegate(user) and evaluation.state in ['prepared', 'editor_approved', 'approved', 'in_evaluation', 'evaluated', 'reviewed']):
        raise PermissionDenied

    return get_valid_form_groups_or_render_vote_page(request, evaluation, preview=True)[1]


@require_POST
@editor_or_delegate_required
def evaluation_direct_delegation(request, evaluation_id):
    delegate_user_id = request.POST.get("delegate_to")

    evaluation = get_object_or_404(Evaluation, id=evaluation_id)
    delegate_user = get_object_or_404(UserProfile, id=delegate_user_id)

    Contribution.objects.update_or_create(evaluation=evaluation, contributor=delegate_user, defaults={'can_edit': True})

    template = EmailTemplate.objects.get(name=EmailTemplate.DIRECT_DELEGATION)
    subject_params = {"evaluation": evaluation, "user": request.user, "delegate_user": delegate_user}
    body_params = subject_params

    # we don't provide the request here since send_to_user only uses it to display a warning message in case the user does not have
    # an email address. In this special case, we don't want that warning. Instead, we want a mail to the admins.
    EmailTemplate.send_to_user(delegate_user, template, subject_params, body_params, use_cc=True, additional_cc_user=request.user)

    messages.add_message(
        request,
        messages.SUCCESS,
        _('{} was added as a contributor for evaluation "{}" and was sent an email with further information.').format(str(delegate_user), str(evaluation))
    )

    return redirect('contributor:index')
