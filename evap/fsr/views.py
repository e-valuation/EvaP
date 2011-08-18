from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render_to_response
from django.template import RequestContext
from django.utils.translation import ugettext as _

import xlrd

from evaluation.models import Semester, Course
from fsr.forms import ImportForm, SemesterForm, CourseForm
from fsr.tools import find_or_create_course, find_or_create_user

@login_required
def index(request):
    semesters = Semester.objects.all()
    return render_to_response("fsr_index.html", dict(semesters=semesters), context_instance=RequestContext(request))

@login_required
def semester_view(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    courses = semester.course_set.all()
    return render_to_response("fsr_semester_view.html", dict(semester=semester, courses=courses), context_instance=RequestContext(request))

@login_required
def semester_create(request):
    form = SemesterForm(request.POST or None)
    
    if form.is_valid():
        s = form.save()
        
        messages.add_message(request, messages.INFO, _("Successfully created semester."))
        return redirect('fsr.views.semester_view', s.id)
    else:
        return render_to_response("fsr_semester_create.html", dict(form=form), context_instance=RequestContext(request))

@login_required
def semester_edit(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    form = SemesterForm(request.POST or None, instance = semester)
    
    if form.is_valid():
        form.save()
        
        messages.add_message(request, messages.INFO, _("Successfully updated semester."))
        return redirect('fsr.views.semester_view', semester_id)
    else:
        return render_to_response("fsr_semester_edit.html", dict(semester=semester, form=form), context_instance=RequestContext(request))

@login_required
def semester_import(request, semester_id):   
    semester = get_object_or_404(Semester, id=semester_id)
    form = ImportForm(request.POST or None, request.FILES or None)
    
    if form.is_valid():
        # extract data from form
        book = xlrd.open_workbook(file_contents=form.cleaned_data['excel_file'].read())
        vote_start_date = form.cleaned_data['vote_start_date']
        vote_end_date = form.cleaned_data['vote_end_date']
        publish_date = form.cleaned_data['publish_date']
        
        # parse table
        with transaction.commit_on_success():
            for sheet in book.sheets():
                try:
                    for row in range(1, sheet.nrows):
                        # load complete row
                        data = [sheet.cell(row,col).value for col in range(sheet.ncols)]
                        
                        # find or create student
                        student = find_or_create_user(username=data[3], first_name=data[1], last_name=data[2])
                        
                        # find or create primary lecturer
                        lecturer = find_or_create_user(username=data[9], first_name=data[7], last_name=data[8])
                        
                        # find or create course
                        course = find_or_create_course(semester, name_de=data[5], name_en=data[6], vote_start_date=vote_start_date, vote_end_date=vote_end_date, publish_date=publish_date)
                        
                        course.participants.add(student)
                        course.primary_lecturers.add(lecturer)
                    messages.add_message(request, messages.INFO, _("Successfully imported sheet '%s'.") % (sheet.name))
                except Exception,e:
                    messages.add_message(request, messages.ERROR, _("Error while importing sheet Successfully imported sheet '%s'. All changes undone") % (sheet.name))
                    raise
        
        messages.add_message(request, messages.INFO, _("Import successful."))
        return redirect('fsr.views.semester_view', semester_id)
    else:
        return render_to_response("fsr_import.html", dict(semester=semester, form=form), context_instance=RequestContext(request))

@login_required
def course_create(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    form = CourseForm(request.POST or None)
    
    if form.is_valid():
        form.save()
        
        messages.add_message(request, messages.INFO, _("Successfully created course."))
        return redirect('fsr.views.semester_view', semester_id)
    else:
        return render_to_response("fsr_course_create.html", dict(semester=semester, form=form), context_instance=RequestContext(request))

@login_required
def course_edit(request, semester_id, course_id):
    semester = get_object_or_404(Semester, id=semester_id)
    course = get_object_or_404(Course, id=course_id)
    form = CourseForm(request.POST or None, instance = course)
    
    if form.is_valid():
        form.save()
        
        messages.add_message(request, messages.INFO, _("Successfully updated course."))
        return redirect('fsr.views.semester_view', semester_id)
    else:
        return render_to_response("fsr_course_edit.html", dict(semester=semester, form=form), context_instance=RequestContext(request))
    