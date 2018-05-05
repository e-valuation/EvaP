from django.contrib import messages
from django.core.exceptions import PermissionDenied, SuspiciousOperation
from django.forms.models import inlineformset_factory
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import ugettext as _
from django.db import IntegrityError, transaction

from evap.contributor.forms import CourseForm, DelegatesForm, EditorContributionForm
from evap.evaluation.auth import contributor_or_delegate_required, editor_or_delegate_required, editor_required
from evap.evaluation.models import Contribution, Course, Semester
from evap.evaluation.tools import STATES_ORDERED, sort_formset
from evap.results.tools import calculate_average_distribution, distribution_to_grade
from evap.staff.forms import ContributionFormSet
from evap.student.views import get_valid_form_groups_or_render_vote_page


@contributor_or_delegate_required
def index(request):
    user = request.user

    contributor_visible_states = ['prepared', 'editor_approved', 'approved', 'in_evaluation', 'evaluated', 'reviewed', 'published']
    own_courses = Course.objects.filter(contributions__contributor=user, state__in=contributor_visible_states)

    represented_users = user.represented_users.all()
    delegated_courses = Course.objects.exclude(id__in=own_courses).filter(contributions__can_edit=True, contributions__contributor__in=represented_users, state__in=contributor_visible_states)

    all_courses = list(own_courses) + list(delegated_courses)
    all_courses.sort(key=lambda course: list(STATES_ORDERED.keys()).index(course.state))

    for course in all_courses:
        course.avg_grade = distribution_to_grade(calculate_average_distribution(course)) if course.can_user_see_grades(user) else None

    semesters = Semester.objects.all()
    semester_list = [dict(
        semester_name=semester.name,
        id=semester.id,
        is_active_semester=semester.is_active_semester,
        courses=[course for course in all_courses if course.semester_id == semester.id]
    ) for semester in semesters]

    template_data = dict(semester_list=semester_list, delegated_courses=delegated_courses)
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
def course_view(request, course_id):
    user = request.user
    course = get_object_or_404(Course, id=course_id)

    # check rights
    if not course.is_user_editor_or_delegate(user) or course.state not in ['prepared', 'editor_approved', 'approved', 'in_evaluation', 'evaluated', 'reviewed']:
        raise PermissionDenied

    InlineContributionFormset = inlineformset_factory(Course, Contribution, formset=ContributionFormSet, form=EditorContributionForm, extra=0)

    form = CourseForm(request.POST or None, instance=course)
    formset = InlineContributionFormset(request.POST or None, instance=course)

    # make everything read-only
    for cform in formset.forms + [form]:
        for field in cform.fields.values():
            field.disabled = True

    template_data = dict(form=form, formset=formset, course=course, editable=False,
                         responsibles=[contributor.username for contributor in course.responsible_contributors])
    return render(request, "contributor_course_form.html", template_data)


def render_preview(request, formset, course_form, course):
    # open transaction to not let any other requests see anything of what we're doing here
    try:
        with transaction.atomic():
            course_form.save(user=request.user)
            formset.save()
            request.POST = None  # this prevents errors rendered in the vote form

            preview_response = get_valid_form_groups_or_render_vote_page(request, course, preview=True, for_rendering_in_modal=True)[1].content.decode()
            raise IntegrityError  # rollback transaction to discard the database writes
    except IntegrityError:
        pass

    return preview_response


@editor_or_delegate_required
def course_edit(request, course_id):
    user = request.user
    course = get_object_or_404(Course, id=course_id)

    # check rights
    if not (course.is_user_editor_or_delegate(user) and course.state == 'prepared'):
        raise PermissionDenied

    post_operation = request.POST.get('operation') if request.POST else None
    preview = post_operation == 'preview'

    InlineContributionFormset = inlineformset_factory(Course, Contribution, formset=ContributionFormSet, form=EditorContributionForm, extra=1)
    course_form = CourseForm(request.POST or None, instance=course)
    formset = InlineContributionFormset(request.POST or None, instance=course, can_change_responsible=False, form_kwargs={'course': course})

    forms_are_valid = course_form.is_valid() and formset.is_valid()

    if forms_are_valid and not preview:
        if post_operation not in ('save', 'approve'):
            raise SuspiciousOperation("Invalid POST operation")

        course_form.save(user=user)
        formset.save()

        if post_operation == 'approve':
            course.editor_approve()
            course.save()
            messages.success(request, _("Successfully updated and approved course."))
        else:
            messages.success(request, _("Successfully updated course."))

        return redirect('contributor:index')
    else:
        preview_html = None
        if preview and forms_are_valid:
            preview_html = render_preview(request, formset, course_form, course)

        if not forms_are_valid and (course_form.errors or formset.errors):
            if preview:
                messages.error(request, _("The preview could not be rendered. Please resolve the errors shown below."))
            else:
                messages.error(request, _("The form was not saved. Please resolve the errors shown below."))

        sort_formset(request, formset)
        template_data = dict(form=course_form, formset=formset, course=course, editable=True, preview_html=preview_html,
                             responsibles=[contributor.username for contributor in course.responsible_contributors])
        return render(request, "contributor_course_form.html", template_data)


@contributor_or_delegate_required
def course_preview(request, course_id):
    user = request.user
    course = get_object_or_404(Course, id=course_id)

    # check rights
    if not (course.is_user_contributor_or_delegate(user) and course.state in ['prepared', 'editor_approved', 'approved', 'in_evaluation', 'evaluated', 'reviewed']):
        raise PermissionDenied

    return get_valid_form_groups_or_render_vote_page(request, course, preview=True)[1]
