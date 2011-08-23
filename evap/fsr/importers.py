from django.contrib import messages
from django.contrib.auth.models import User
from django.db import transaction
from django.utils.translation import ugettext as _
from evaluation.models import Course, Semester
import xlrd

def import_excel_file(request, excel_file, semester, vote_start_date, vote_end_date):
    book = xlrd.open_workbook(file_contents=excel_file.read())
    
    with transaction.commit_on_success():
        course_count = 0
        student_count = 0
        lecturer_count = 0
        
        for sheet in book.sheets():
            try:
                for row in range(1, sheet.nrows):
                    # load complete row
                    data = [sheet.cell(row,col).value for col in range(sheet.ncols)]
                    
                    # find or create student
                    student, student_is_new = User.objects.get_or_create(
                        username=data[3],
                        defaults=dict(first_name=data[2], last_name=data[1]))
                    
                    # find or create primary lecturer
                    lecturer, lecturer_is_new = User.objects.get_or_create(
                        username=data[9],
                        defaults=dict(first_name=data[7], last_name=data[8]))
                    
                    # find or create course
                    course, course_is_new = Course.objects.get_or_create(
                        semester=semester,
                        name_de=data[5],
                        name_en=data[6],
                        kind=data[4],
                        defaults=dict(vote_start_date=vote_start_date, vote_end_date=vote_end_date)
                    )
                    
                    course.participants.add(student)
                    course.primary_lecturers.add(lecturer)
                    
                    if course_is_new:
                        course_count += 1
                    if student_is_new:
                        student_count += 1
                    if lecturer_is_new:
                        lecturer_count += 1
                    
                messages.add_message(request, messages.INFO, _("Successfully imported sheet '%s'.") % sheet.name)
            except Exception,e:
                messages.add_message(request, messages.ERROR, _("Error while importing sheet '%(name)s'. All changes undone. The error message has been: '%(error)s'") % dict(name=sheet.name, error=e))
                raise
        messages.add_message(request, messages.INFO, _("Successfully created %(courses)d courses, %(students)d students and %(lecturers)d lecturers.") % dict(courses=course_count, students=student_count, lecturers=lecturer_count))
