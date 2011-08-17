from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.db import transaction
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render_to_response
from django.template import RequestContext
from django.utils.translation import ugettext as _

import xlrd

from evaluation.models import Semester, Course
from fsr.forms import ImportForm

@login_required
def fsr_index(request):
    courses = Semester.current().course_set.all()
    return render_to_response("fsr_index.html", dict(courses=courses), context_instance=RequestContext(request))

@login_required
def fsr_import(request):
    # import data from excel file
    semester = Semester.current()
    form = ImportForm(request.POST or None, request.FILES or None)
    
    if form.is_valid():
        book = xlrd.open_workbook(file_contents=form.cleaned_data['excel_file'].read())
        with transaction.commit_on_success():
            for sheet in book.sheets():
                try:
                    for row in range(1, sheet.nrows):
                        # load complete row
                        data = [sheet.cell(row,col).value for col in range(sheet.ncols)]
                        
                        # find or create student
                        student = find_student(data)
                        
                        # find or create course
                        course = find_course(semester, data)
                        course.participants.add(student)
                    messages.add_message(request, messages.INFO, _("Successfully imported sheet '%s'.") % (sheet.name))
                except Exception,e:
                    messages.add_message(request, messages.ERROR, _("Error while importing sheet Successfully imported sheet '%s'. All changes undone") % (sheet.name))
                    raise
        
        messages.add_message(request, messages.INFO, _("Import successful."))
        return redirect('fsr.views.fsr_index')
    else:
        return render_to_response("fsr_import.html", dict(form=form), context_instance=RequestContext(request))

def find_student(data):
    try:
        return User.objects.get(username=data[3])
    except User.DoesNotExist:
        user = User(username = data[3], first_name = data[1], last_name = data[2])
        user.save()
        return user

def find_course(semester, data):
    try:
        return semester.course_set.get(name_de=data[5])
    except Course.DoesNotExist:
        course = Course(name_de = data[5], name_en = data[6], semester = semester)
        course.save()
        return course
    