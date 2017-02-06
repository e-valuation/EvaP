from django.contrib import messages
from django.core.exceptions import PermissionDenied, SuspiciousOperation
from django.forms.models import inlineformset_factory
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import ugettext as _

from evap.evaluation.models import Contribution, Course, Semester
from evap.evaluation.auth import editor_required, editor_or_delegate_required, contributor_or_delegate_required
from evap.evaluation.tools import STATES_ORDERED, sort_formset
from evap.contributor.forms import CourseForm, DelegatesForm
from evap.staff.forms import ContributionFormSet
from evap.contributor.forms import EditorContributionForm
from evap.student.views import vote_preview


@contributor_or_delegate_required
def index(request):
    user = request.user

    contributor_visible_states = ['prepared', 'editor_approved', 'approved', 'in_evaluation', 'evaluated', 'reviewed', 'published']
    own_courses = Course.objects.filter(contributions__contributor=user, state__in=contributor_visible_states)

    represented_users = user.represented_users.all()
    delegated_courses = Course.objects.exclude(id__in=own_courses).filter(contributions__can_edit=True, contributions__contributor__in=represented_users, state__in=contributor_visible_states)

    all_courses = list(own_courses) + list(delegated_courses)
    all_courses.sort(key=lambda course: list(STATES_ORDERED.keys()).index(course.state))

    semesters = Semester.objects.all()
    semester_list = [dict(semester_name=semester.name, id=semester.id, courses=[course for course in all_courses if course.semester_id == semester.id]) for semester in semesters]

    template_data = dict(semester_list=semester_list, delegated_courses=delegated_courses)
    return render(request, "contributor_index.html", template_data)


@editor_required
def settings_edit(request):
    user = request.user
    form = DelegatesForm(request.POST or None, request.FILES or None, instance=user)

    if form.is_valid():
        form.save()

        messages.success(request, _("Successfully updated your settings."))
        return redirect('contributor:index')
    else:
        return render(request, "contributor_settings.html", dict(form=form))


@editor_or_delegate_required
def course_view(request, course_id):
    user = request.user
    course = get_object_or_404(Course, id=course_id)

    # check rights
    if not (course.is_user_editor_or_delegate(user) and course.state in ['prepared', 'editor_approved', 'approved', 'in_evaluation', 'evaluated', 'reviewed']):
        raise PermissionDenied

    InlineContributionFormset = inlineformset_factory(Course, Contribution, formset=ContributionFormSet, form=EditorContributionForm, extra=0)

    form = CourseForm(request.POST or None, instance=course)
    formset = InlineContributionFormset(request.POST or None, instance=course)

    # make everything read-only
    for cform in formset.forms + [form]:
        for field in cform.fields.values():
            field.disabled = True

    template_data = dict(form=form, formset=formset, course=course, editable=False, responsible=course.responsible_contributor.username)
    return render(request, "contributor_course_form.html", template_data)


@editor_or_delegate_required
def course_edit(request, course_id):
    user = request.user
    course = get_object_or_404(Course, id=course_id)

    # check rights
    if not (course.is_user_editor_or_delegate(user) and course.state == 'prepared'):
        raise PermissionDenied

    InlineContributionFormset = inlineformset_factory(Course, Contribution, formset=ContributionFormSet, form=EditorContributionForm, extra=1)

    course_form = CourseForm(request.POST or None, instance=course)
    formset = InlineContributionFormset(request.POST or None, instance=course, form_kwargs={'course': course})

    if course_form.is_valid() and formset.is_valid():
        operation = request.POST.get('operation')
        if operation not in ('save', 'approve'):
            raise SuspiciousOperation("Invalid POST operation")

        course_form.save(user=user)
        formset.save()

        if operation == 'approve':
            # approve course
            course.editor_approve()
            course.save()
            messages.success(request, _("Successfully updated and approved course."))
        else:
            messages.success(request, _("Successfully updated course."))

        return redirect('contributor:index')
    else:
        messages.error(request, _("The form was not saved. Please resolve the errors shown below."))
        sort_formset(request, formset)
        template_data = dict(form=course_form, formset=formset, course=course, editable=True, responsible=course.responsible_contributor.username)
        return render(request, "contributor_course_form.html", template_data)


@contributor_or_delegate_required
def course_preview(request, course_id):
    user = request.user
    course = get_object_or_404(Course, id=course_id)

    # check rights
    if not (course.is_user_contributor_or_delegate(user) and course.state in ['prepared', 'editor_approved', 'approved', 'in_evaluation', 'evaluated', 'reviewed']):
        raise PermissionDenied

    return vote_preview(request, course)
