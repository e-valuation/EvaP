from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.forms.models import inlineformset_factory
from django.shortcuts import get_object_or_404, redirect, render_to_response
from django.template import RequestContext
from django.utils.datastructures import SortedDict
from django.utils.translation import ugettext as _

from evap.evaluation.models import Assignment, Course, Semester, UserProfile
from evap.evaluation.auth import editor_required, editor_or_delegate_required
from evap.evaluation.tools import questionnaires_and_assignments, STATES_ORDERED
from evap.lecturer.forms import CourseForm, UserForm
from evap.fsr.forms import AtLeastOneFormSet, AssignmentForm, LecturerFormSet
from evap.student.forms import QuestionsForm

@editor_or_delegate_required
def index(request):
    user = request.user
    
    sorter = lambda course: STATES_ORDERED.keys().index(course.state)
    
    own_courses = list(set(Course.objects.filter(assignments__can_edit=True, assignments__lecturer=user, state__in=['prepared', 'lecturerApproved', 'approved', 'inEvaluation'])))
    own_courses.sort(key=sorter)

    delegated_courses = list(set(Course.objects.exclude(assignments__lecturer=user).filter(assignments__can_edit=True, assignments__lecturer__in=user.represented_users.all(), state__in=['prepared', 'lecturerApproved', 'approved', 'inEvaluation'])))
    delegated_courses.sort(key=sorter)
    
    return render_to_response("lecturer_index.html", dict(own_courses=own_courses, delegated_courses=delegated_courses), context_instance=RequestContext(request))


@editor_required
def profile_edit(request):
    user = request.user
    form = UserForm(request.POST or None, request.FILES or None, instance = UserProfile.objects.get_or_create(user=user)[0])
    
    if form.is_valid():
        form.save()
        
        messages.add_message(request, messages.INFO, _("Successfully updated your profile."))
        return redirect('evap.lecturer.views.index')
    else:
        return render_to_response("lecturer_profile.html", dict(form=form), context_instance=RequestContext(request))

@editor_or_delegate_required
def course_view(request, course_id):
    user = request.user
    course = get_object_or_404(Course, id=course_id)
        
    # check rights
    if not (course.is_user_editor_or_delegate(user) and course.state in ['prepared', 'lecturerApproved', 'approved']):
        raise PermissionDenied

    AssignmentFormset = inlineformset_factory(Course, Assignment, formset=LecturerFormSet, form=AssignmentForm, extra=1, exclude=('course'))
    
    form = CourseForm(request.POST or None, instance=course)
    formset = AssignmentFormset(request.POST or None, instance=course, queryset=course.assignments.exclude(lecturer=None))
    
    # make everything read-only
    for cform in formset.forms + [form]:
        for name, field in cform.fields.iteritems():
            field.widget.attrs['readonly'] = True
            field.widget.attrs['disabled'] = True
    
    return render_to_response("lecturer_course_form.html", dict(form=form, formset=formset, course=course, edit=False), context_instance=RequestContext(request))


@editor_or_delegate_required
def course_edit(request, course_id):
    user = request.user
    course = get_object_or_404(Course, id=course_id)
    
    # check rights
    if not (course.is_user_editor_or_delegate(user) and course.state in ('prepared')):
        raise PermissionDenied
    
    AssignmentFormset = inlineformset_factory(Course, Assignment, formset=LecturerFormSet, form=AssignmentForm, extra=1, exclude=('course'))
    
    form = CourseForm(request.POST or None, instance=course)
    formset = AssignmentFormset(request.POST or None, prefix='assignment', instance=course, queryset=course.assignments.exclude(lecturer=None))
    
    operation = request.POST.get('operation')
    
    if form.is_valid() and formset.is_valid():
        if operation not in ('save', 'approve'):
            raise PermissionDenied
        
        form.save(user=request.user)
        formset.save()
        
        if operation == 'approve':
            # approve course
            course.lecturer_approve()
            course.save()
            messages.add_message(request, messages.INFO, _("Successfully updated and approved course."))
        else:
            messages.add_message(request, messages.INFO, _("Successfully updated course."))
        
        return redirect('evap.lecturer.views.index')
    else:
        return render_to_response("lecturer_course_form.html", dict(form=form, formset=formset, course=course, edit=True), context_instance=RequestContext(request))


@editor_or_delegate_required
def course_preview(request, course_id):
    user = request.user
    course = get_object_or_404(Course, id=course_id)

    # build forms
    forms = SortedDict()
    for questionnaire, assignment in questionnaires_and_assignments(course):
        form = QuestionsForm(request.POST or None, assignment=assignment, questionnaire=questionnaire)
        forms[(assignment, questionnaire)] = form
    
    return render_to_response("lecturer_course_preview.html", dict(forms=forms.values(), course=course), context_instance=RequestContext(request))
