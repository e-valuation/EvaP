from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render_to_response
from django.template import RequestContext
from django.utils.translation import ugettext as _

from datetime import datetime

from evaluation.models import Course, Semester
from evaluation.tools import calculate_results

@login_required
def index(request):
    objects = []
    for semester in Semester.objects.filter(visible=True).order_by('-created_at'):
        objects.append({
            'semester': semester,
            'courses': semester.course_set.filter(visible=True)
        })
    
    return render_to_response(
        "results_index.html",
        dict(objects=objects),
        context_instance=RequestContext(request))

@login_required
def course_detail(request, id):
    course = get_object_or_404(
        Course.objects.filter(visible=True),
        id=id)
    
    results = calculate_results(course)
    
    return render_to_response(
        "results_course_detail.html",
        dict(
            course=course,
            results=results
        ),
        context_instance=RequestContext(request))
