from django.contrib import messages
from django.db import transaction
from django.utils.translation import ugettext as _
from evaluation.models import Semester, Course, Question, QuestionGroup
from fsr.tools import find_or_create_course, find_or_create_user
import xlrd

def import_excel_file(request, excel_file, semester, vote_start_date, vote_end_date):
    book = xlrd.open_workbook(file_contents=excel_file.read())
    
    with transaction.commit_on_success():
        count = 0
        for sheet in book.sheets():
            try:
                for row in range(1, sheet.nrows):
                    # load complete row
                    data = [sheet.cell(row,col).value for col in range(sheet.ncols)]
                    
                    # find or create student
                    student = find_or_create_user(username=data[3], first_name=data[2], last_name=data[1])
                    
                    # find or create primary lecturer
                    lecturer = find_or_create_user(username=data[9], first_name=data[7], last_name=data[8])
                    
                    # find or create course
                    course = find_or_create_course(semester, name_de=data[5], name_en=data[6], kind=data[4], vote_start_date=vote_start_date, vote_end_date=vote_end_date)
                    
                    course.participants.add(student)
                    course.primary_lecturers.add(lecturer)
                    count = count + 1
                messages.add_message(request, messages.INFO, _("Successfully imported sheet '%s'.") % sheet.name)
            except Exception,e:
                messages.add_message(request, messages.ERROR, _("Error while importing sheet '%(name)s'. All changes undone. The error message has been: '%(error)s'") % dict(name=sheet.name, error=e))
                raise
        messages.add_message(request, messages.INFO, _("Successfully imported %d courses.") % count)
