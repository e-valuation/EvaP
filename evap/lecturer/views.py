from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.forms.models import inlineformset_factory
from django.shortcuts import get_object_or_404, redirect, render_to_response
from django.template import RequestContext
from django.utils.translation import ugettext as _

from evap.evaluation.auth import lecturer_required
from evap.lecturer.forms import *
from evap.fsr.forms import AtLeastOneFormSet, AssignmentForm


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
    courses = [course for course in semester.course_set.all() if course.is_user_lecturer(user)] if semester else None
    return render_to_response("lecturer_course_index.html", dict(courses=courses), context_instance=RequestContext(request))


@lecturer_required
def course_edit(request, course_id):
    user = request.user
    course = get_object_or_404(Course, id=course_id)
    
    # check rights
    if not course.is_user_lecturer(user):
        raise PermissionDenied
        
    AssignmentFormset = inlineformset_factory(Course, Assignment, formset=AtLeastOneFormSet, form=AssignmentForm, extra=1, exclude=('course'))
    
    form = CourseForm(request.POST or None, instance=course)
    formset = AssignmentFormset(request.POST or None, instance=course, queryset=course.assignments.exclude(lecturer=None))
    
    if form.is_valid() and formset.is_valid():
        form.save()
        formset.save()
        
        messages.add_message(request, messages.INFO, _("Successfully updated course."))
        return redirect('evap.lecturer.views.course_index')
    else:
        return render_to_response("lecturer_course_form.html", dict(form=form, formset=formset), context_instance=RequestContext(request))
