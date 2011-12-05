from evap.evaluation.models import Questionnaire
from evap.evaluation.tools import calculate_results, calculate_average_grade

from django.utils.datastructures import SortedDict
from django.utils.translation import ugettext as _

from collections import defaultdict
import xlwt


class ExcelExporter(object):
    def __init__(self, semester):
        self.semester = semester
    
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
        self.row = 0
        self.col = 0
        
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
        
        self.writec()
        for course, results in courses_with_results:
            self.writec(course.name, fmt_vert, cols=2)
        self.writen(None)
        
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
                        variances = []
                        enough_answers = True
                        for lecturer, data, grade in qn_results:
                            for grade_result in data:
                                if grade_result.question.id == question.id:
                                    if grade_result.average:
                                        values.append(grade_result.average)
                                        variances.append(grade_result.variance)
                                        if not grade_result.show:
                                            enough_answers = False
                                    break
                        if values:
                            self.writec(sum(values) / len(values), fmt_num if enough_answers else fmt_num_it)
                            self.writec(sum(variances) / len(variances), fmt_num if enough_answers else fmt_num_it)
                        else:
                            self.writec()
                            self.writec()
                    else:
                        self.writec()
                        self.writec()
        
        self.writen(_(u"Overall Grade"), fmt_bold)
        for course, results in courses_with_results:
            self.writec(calculate_average_grade(course), fmt_num, cols=2)
        
        self.writen(_(u"Total Answers"), fmt_bold)
        for course, results in courses_with_results:
            self.writec(course.voters.count(), cols=2)
        
        self.workbook.save(response)
    
    def writen(self, *args, **kwargs):
        """Write the cell at the beginning of the next row."""
        self.col = 0
        self.row += 1
        self.writec(*args, **kwargs)
    
    def writec(self, *args, **kwargs):
        """Write the cell in the next column of the current line."""
        self._write(*args, **kwargs)
        self.col += 1
    
    def _write(self, *args, **kwargs):
        rows = kwargs.pop('rows', 1)
        cols = kwargs.pop('cols', 1)
        if rows > 1 or cols > 1:
            self.sheet.write_merge(self.row, self.row+rows-1, self.col, self.col+cols-1, *args, **kwargs)
            self.col += cols - 1
        else:
            self.sheet.write(self.row, self.col, *args, **kwargs)
