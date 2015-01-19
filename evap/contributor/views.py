from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.forms.models import inlineformset_factory
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import ugettext as _

from evap.evaluation.models import Contribution, Course, Semester
from evap.evaluation.auth import editor_required, editor_or_delegate_required, delegate_or_contributor_required
from evap.evaluation.tools import STATES_ORDERED
from evap.contributor.forms import CourseForm, UserForm
from evap.staff.forms import ContributionForm, ContributionFormSet
from evap.student.views import vote_preview


@delegate_or_contributor_required
def index(request):
    user = request.user

    contributor_visible_states = ['prepared', 'lecturerApproved', 'approved', 'inEvaluation', 'evaluated', 'reviewed', 'published']
    own_courses = Course.objects.filter(contributions__contributor=user, state__in=contributor_visible_states)

    represented_users = user.represented_users.all()
    delegated_courses = Course.objects.exclude(id__in=own_courses).filter(contributions__can_edit=True, contributions__contributor__in=represented_users, state__in=contributor_visible_states)

    all_courses = list(own_courses) + list(delegated_courses)
    all_courses.sort(key=lambda course: list(STATES_ORDERED.keys()).index(course.state))

    semesters = Semester.objects.all()
    semester_list = [dict(semester_name=semester.name, id=semester.id, courses=[course for course in all_courses if course.semester_id == semester.id]) for semester in semesters]

    template_data = dict(semester_list=semester_list, delegated_courses=delegated_courses, user=user)
    return render(request, "contributor_index.html", template_data)


@editor_required
def profile_edit(request):
    user = request.user
    form = UserForm(request.POST or None, request.FILES or None, instance=user)

    if form.is_valid():
        form.save()

        messages.success(request, _("Successfully updated your profile."))
        return redirect('evap.contributor.views.index')
    else:
        return render(request, "contributor_profile.html", dict(form=form))


@editor_or_delegate_required
def course_view(request, course_id):
    user = request.user
    course = get_object_or_404(Course, id=course_id)

    # check rights
    if not (course.is_user_editor_or_delegate(user) and course.state in ['prepared', 'lecturerApproved', 'approved', 'inEvaluation', 'evaluated', 'reviewed']):
        raise PermissionDenied

    ContributionFormset = inlineformset_factory(Course, Contribution, formset=ContributionFormSet, form=ContributionForm, extra=0, exclude=('course',))

    form = CourseForm(request.POST or None, instance=course)
    formset = ContributionFormset(request.POST or None, instance=course, queryset=course.contributions.exclude(contributor=None))

    # make everything read-only
    for cform in formset.forms + [form]:
        for name, field in cform.fields.items():
            field.widget.attrs['readonly'] = "True"
            field.widget.attrs['disabled'] = "True"

    template_data = dict(form=form, formset=formset, course=course, edit=False, responsible=course.responsible_contributors_username)
    return render(request, "contributor_course_form.html", template_data)

@editor_or_delegate_required
def course_edit(request, course_id):
    user = request.user
    course = get_object_or_404(Course, id=course_id)

    # check rights
    if not (course.is_user_editor_or_delegate(user) and course.state == 'prepared'):
        raise PermissionDenied

    ContributionFormset = inlineformset_factory(Course, Contribution, formset=ContributionFormSet, form=ContributionForm, extra=1, exclude=('course',))

    form = CourseForm(request.POST or None, instance=course)
    formset = ContributionFormset(request.POST or None, instance=course, queryset=course.contributions.exclude(contributor=None))

    operation = request.POST.get('operation')

    if form.is_valid() and formset.is_valid():
        if operation not in ('save', 'approve'):
            raise PermissionDenied

        form.save(user=user)
        formset.save()

        if operation == 'approve':
            # approve course
            course.contributor_approve()
            course.save()
            messages.success(request, _("Successfully updated and approved course."))
        else:
            messages.success(request, _("Successfully updated course."))

        return redirect('evap.contributor.views.index')
    else:
        template_data = dict(form=form, formset=formset, course=course, edit=True, responsible=course.responsible_contributors_username)
        return render(request, "contributor_course_form.html", template_data)

@delegate_or_contributor_required
def course_preview(request, course_id):
    user = request.user
    course = get_object_or_404(Course, id=course_id)

    # check rights
    if not ((course.is_user_editor_or_delegate(user) or course.is_user_contributor(user)) and course.state in ['prepared', 'lecturerApproved', 'approved', 'inEvaluation', 'evaluated', 'reviewed']):
        raise PermissionDenied

    return vote_preview(request, course)
