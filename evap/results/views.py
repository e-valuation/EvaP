from django.shortcuts import get_object_or_404, redirect, render_to_response
from django.template import RequestContext
from django.utils.translation import ugettext as _

from evaluation.auth import login_required
from evaluation.models import Course, Semester
from evaluation.tools import calculate_results, calculate_average_grade


@login_required
def index(request):
    semesters = Semester.objects.filter(visible=True).order_by('-created_at')
    
    if len(semesters) > 0:
        latest_semester = semesters[0]
        latest_semester_courses = latest_semester.course_set.filter(visible=True)
        older_semesters = semesters[1:]
    else:
        latest_semester = None
        latest_semester_courses = []
        older_semesters = None
    
    return render_to_response(
        "results_index.html",
        dict(
            latest_semester=latest_semester,
            latest_semester_courses=latest_semester_courses,
            older_semesters=older_semesters
        ),
        context_instance=RequestContext(request))


@login_required
def semester_detail(request, semester_id):
    semester = get_object_or_404(Semester.objects.filter(visible=True), id=semester_id)
    courses = list(semester.course_set.filter(visible=True))
    for course in courses:
        # annotate course objects with grade
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
    course = get_object_or_404(semester.course_set.filter(visible=True), id=course_id)
    
    sections = calculate_results(course)
    
    return render_to_response(
        "results_course_detail.html",
        dict(
            course=course,
            sections=sections
        ),
        context_instance=RequestContext(request))
