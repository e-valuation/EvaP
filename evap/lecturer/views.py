from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render_to_response
from django.template import RequestContext
from django.utils.datastructures import SortedDict
from django.utils.translation import ugettext as _

from lecturer.forms import *

@login_required
def index(request):
    return render_to_response("lecturer_index.html", dict(), context_instance=RequestContext(request))

@login_required
def profile_edit(request):
    user = request.user
    form = UserForm(request.POST or None, request.FILES or None, instance=user.get_profile())
    
    if form.is_valid():
        form.save()
        
        messages.add_message(request, messages.INFO, _("Successfully updated your profile."))
        return redirect('lecturer.views.index')
    else:
        return render_to_response("lecturer_profile.html", dict(form=form), context_instance=RequestContext(request))


@login_required
def course_index(request):
    user = request.user
    
    semester = get_object_or_404(Semester)
    courses = semester.course_set.filter(primary_lecturers__pk=user.id)
    return render_to_response("lecturer_course_index.html", dict(courses=courses), context_instance=RequestContext(request))

@login_required
def course_edit(request, course_id):
    user = request.user
    course = get_object_or_404(Course, id=course_id)
    
    # check rights
    if not course.primary_lecturers.filter(pk=user.id).exists():
        return HttpResponseForbidden()
        
    form = CourseForm(request.POST or None, instance = course)
    
    if form.is_valid():
        form.save()
        
        messages.add_message(request, messages.INFO, _("Successfully updated course."))
        return redirect('lecturer.views.course_index')
    else:
        return render_to_response("lecturer_course_form.html", dict(form=form), context_instance=RequestContext(request))
