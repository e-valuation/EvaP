from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render_to_response
from django.template import RequestContext
from django.utils.translation import get_language

from evap.evaluation.auth import login_required, fsr_required
from evap.evaluation.models import Semester
from evap.evaluation.tools import calculate_results, calculate_average_grade

from evap.results.exporters import ExcelExporter


@login_required
def index(request):
    semesters = Semester.objects.all()
    
    return render_to_response(
        "results_index.html",
        dict(semesters=semesters),
        context_instance=RequestContext(request))


@login_required
def semester_detail(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    courses = list(semester.course_set.filter(state="published"))
    
    # annotate each course object with its grade
    for course in courses:
        # first, make sure that there is no preexisting grade attribute
        course.grade = calculate_average_grade(course)
    
    return render_to_response(
        "results_semester_detail.html",
        dict(
            semester=semester,
            courses=courses
        ),
        context_instance=RequestContext(request))


@fsr_required
def semester_export(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    
    filename = "Evaluation-%s-%s.xls" % (semester.name, get_language())
    
    response = HttpResponse(mimetype="application/vnd.ms-excel")
    response["Content-Disposition"] = "attachment; filename=\"%s\"" % filename
    
    exporter = ExcelExporter(semester)
    
    if 'all' in request.GET:
        exporter.export(response, True)
    else:
        exporter.export(response)
    
    return response


@login_required
def course_detail(request, semester_id, course_id):
    semester = get_object_or_404(Semester, id=semester_id)
    course = get_object_or_404(semester.course_set.filter(state="published"), id=course_id)
    
    sections = calculate_results(course)
    
    return render_to_response(
        "results_course_detail.html",
        dict(
            course=course,
            sections=sections
        ),
        context_instance=RequestContext(request))
