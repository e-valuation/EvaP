from django.shortcuts import get_object_or_404, redirect, render_to_response
from django.template import RequestContext
from django.utils.translation import ugettext as _

from evaluation.auth import login_required
from evaluation.models import Course, Semester
from evaluation.tools import calculate_results, calculate_average_grade


@login_required
def index(request):
    semesters = Semester.objects.filter(visible=True).order_by('-created_at')
    
    return render_to_response(
        "results_index.html",
        dict(semesters=semesters),
        context_instance=RequestContext(request))


@login_required
def semester_detail(request, semester_id):
    semester = get_object_or_404(Semester.objects.filter(visible=True), id=semester_id)
    courses = list(semester.course_set.filter(state="published"))
    
    # annotate each course object with its grade
    for course in courses:
        # first, make sure that there is no preexisting grade attribute
        assert not hasattr(course, 'grade')
        course.grade = calculate_average_grade(course)
    
    return render_to_response(
        "results_semester_detail.html",
        dict(
            semester=semester,
            courses=courses
        ),
        context_instance=RequestContext(request))


@login_required
def course_detail(request, semester_id, course_id):
    semester = get_object_or_404(Semester.objects.filter(visible=True), id=semester_id)
    course = get_object_or_404(semester.course_set.filter(state="published"), id=course_id)
    
    sections = calculate_results(course)
    
    return render_to_response(
        "results_course_detail.html",
        dict(
            course=course,
            sections=sections
        ),
        context_instance=RequestContext(request))
