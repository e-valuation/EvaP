from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.forms.models import inlineformset_factory
from django.shortcuts import get_object_or_404, redirect, render_to_response
from django.template import RequestContext
from django.utils.datastructures import SortedDict
from django.utils.translation import ugettext as _

from evap.evaluation.models import Assignment, Course, Semester
from evap.evaluation.auth import lecturer_required
from evap.evaluation.tools import questionnaires_and_assignments
from evap.lecturer.forms import CourseForm, UserForm
from evap.fsr.forms import AtLeastOneFormSet, AssignmentForm, LecturerFormSet
from evap.student.forms import QuestionsForm

@lecturer_required
def index(request):
    return render_to_response("lecturer_index.html", dict(), context_instance=RequestContext(request))


@lecturer_required
def profile_edit(request):
    user = request.user
    form = UserForm(request.POST or None, request.FILES or None, instance=user.get_profile())
    
    if form.is_valid():
        form.save()
        
        messages.add_message(request, messages.INFO, _("Successfully updated your profile."))
        return redirect('evap.lecturer.views.index')
    else:
        return render_to_response("lecturer_profile.html", dict(form=form), context_instance=RequestContext(request))


@lecturer_required
def course_index(request):
    user = request.user
    
    semester = Semester.get_latest_or_none()
    own_courses = semester.course_set.filter(assignments__lecturer=user, state="prepared") if semester else None
    proxied_courses = semester.course_set.filter(assignments__lecturer__in=user.proxied_users.all(), state="prepared") if semester else None
    return render_to_response("lecturer_course_index.html", dict(own_courses=own_courses, proxied_courses=proxied_courses), context_instance=RequestContext(request))


@lecturer_required
def course_edit(request, course_id):
    user = request.user
    course = get_object_or_404(Course, id=course_id)
    
    # check rights
    if not (course.is_user_lecturer(user) and course.state=="prepared"):
        raise PermissionDenied
    
    AssignmentFormset = inlineformset_factory(Course, Assignment, formset=LecturerFormSet, form=AssignmentForm, extra=1, exclude=('course', 'read_only'))
    
    form = CourseForm(request.POST or None, instance=course)
    formset = AssignmentFormset(request.POST or None, instance=course, queryset=course.assignments.exclude(read_only=True).exclude(lecturer=None))
    
    operation = request.POST.get('operation')
    
    if form.is_valid() and formset.is_valid():
        if operation not in ('save', 'save_and_approve'):
            raise PermissionDenied
        
        form.save()
        formset.save()
        
        if operation == 'save_and_approve':
            course.lecturer_approve()
            course.save()
            messages.add_message(request, messages.INFO, _("Successfully updated and approved course."))
        else:
            messages.add_message(request, messages.INFO, _("Successfully updated course."))
        return redirect('evap.lecturer.views.course_index')
    else:
        read_only_assignments = course.assignments.exclude(lecturer=None).filter(read_only=True)
        return render_to_response("lecturer_course_form.html", dict(form=form, formset=formset, read_only_assignments=read_only_assignments), context_instance=RequestContext(request))


@lecturer_required
def course_preview(request, course_id):
    user = request.user
    course = get_object_or_404(Course, id=course_id)

    # check rights
    if not (course.is_user_lecturer(user) and course.state=="prepared"):
        raise PermissionDenied

    # build forms
    forms = SortedDict()
    for questionnaire, assignment in questionnaires_and_assignments(course):
        form = QuestionsForm(request.POST or None, assignment=assignment, questionnaire=questionnaire)
        forms[(assignment, questionnaire)] = form
    
    return render_to_response("lecturer_course_preview.html", dict(forms=forms.values(), course=course), context_instance=RequestContext(request))
