from evap.evaluation.models import Course, Questionnaire, Semester
from evap.evaluation.tools import calculate_results, calculate_average_grade

from django.utils.datastructures import SortedDict
from django.utils.translation import ugettext as _

from collections import defaultdict

import xlwt

class ExcelExporter(object):
    def __init__(self, semester):
        self.semester = semester
        pass
    
    def export(self, response):
        courses_with_results = list()
        for course in self.semester.course_set.all():
            results = SortedDict()
            for questionnaire, lecturer, data, grade in calculate_results(course):
                results.setdefault(questionnaire.id, []).append((lecturer, data, grade))
            courses_with_results.append((course, results))
        
        courses_with_results.sort(key=lambda cr: cr[0].kind)
        
        qn_frequencies = defaultdict(int)
        for course, results in courses_with_results:
            for questionnaire, results in results.items():
                qn_frequencies[questionnaire] += 1
        
        qn_relevant = qn_frequencies.items()
        qn_relevant.sort(key=lambda t: -t[1])
        
        questionnaires = [Questionnaire.objects.get(id=t[0]) for t in qn_relevant]
        
        self.workbook = xlwt.Workbook()
        self.sheet = self.workbook.add_sheet(_(u"Results"))
        self.row = -1
        self.col = -1
        
        fmt_bold = xlwt.XFStyle()
        fmt_bold.font.bold = True
        
        fmt_num = xlwt.easyxf(num_format_str="0.0")
        fmt_num.alignment.horz = fmt_num.alignment.HORZ_CENTER
        
        fmt_num_it = xlwt.easyxf(num_format_str="0.0")
        fmt_num_it.alignment.horz = fmt_num.alignment.HORZ_CENTER
        fmt_num_it.font.italic = True
        
        fmt_vert = xlwt.XFStyle()
        fmt_vert.alignment.orie = fmt_vert.alignment.ORIENTATION_90_CW
        fmt_vert.alignment.rota = 90
        fmt_vert.alignment.horz = fmt_vert.alignment.HORZ_CENTER
        
        self.writen(None)
        for course, results in courses_with_results:
            self.writec(course.name, fmt_vert)
        
        for questionnaire in questionnaires:
            self.writen(questionnaire.name, fmt_bold)
            
            for question_index, question in enumerate(questionnaire.question_set.all()):
                if question.is_text_question():
                    continue
                
                self.writen(question.text)
                
                for course, results in courses_with_results:
                    qn_results = results.get(questionnaire.id, None)
                    if qn_results:
                        values = []
                        enough_answers = True
                        for lecturer, data, grade in qn_results:
                            for grade_result in data:
                                if grade_result.question.id == question.id:
                                    if grade_result.average:
                                        values.append(grade_result.average)
                                        if not grade_result.show:
                                            enough_answers = False
                                    break
                        if values:
                            self.writec(sum(values)/len(values), fmt_num if enough_answers else fmt_num_it)
                        else:
                            self.writec()
                    else:
                        self.writec()
        
        self.workbook.save(response)
    
    def writen(self, *args, **kwargs):
        """Write the cell at the beginning of the next row."""
        self.col = 0
        self.row += 1
        self._write(*args, **kwargs)
    
    def writec(self, *args, **kwargs):
        """Write the cell in the next column of the current line."""
        self.col += 1
        self._write(*args, **kwargs)
    
    def _write(self, *args, **kwargs):
        self.sheet.write(self.row, self.col, *args, **kwargs)
