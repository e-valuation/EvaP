from evap.evaluation.models import Questionnaire
from evap.evaluation.tools import calculate_results, calculate_average_grade

from django.utils.datastructures import SortedDict
from django.utils.translation import ugettext as _

from collections import defaultdict
import datetime
import xlwt


class ExcelExporter(object):
    def __init__(self, semester):
        self.semester = semester
    
    def export(self, response, all=False):
        courses_with_results = list()
        for course in self.semester.course_set.filter(state="published").all():
            results = SortedDict()
            for questionnaire, contributor, data, grade in calculate_results(course):
                results.setdefault(questionnaire.id, []).append((contributor, data, grade))
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
        
        # formatting for average grades
        avg_style = xlwt.easyxf('alignment: horiz centre; font: bold on; borders: left medium, top medium, bottom medium')
        avg_style_good = xlwt.easyxf('pattern: pattern solid, fore_colour light_green; alignment: horiz centre; font: bold on; borders: left medium', num_format_str="0.0")
        avg_style_medium = xlwt.easyxf('pattern: pattern solid, fore_colour light_yellow; alignment: horiz centre; font: bold on; borders: left medium', num_format_str="0.0")
        avg_style_bad = xlwt.easyxf('pattern: pattern solid, fore_colour light_yellow; alignment: horiz centre; font: bold on; borders: left medium', num_format_str="0.0")
        
        # formatting for variances
        var_style_good = xlwt.easyxf('alignment: horiz centre; borders: right medium', num_format_str="0.0")
        var_style_medium = xlwt.easyxf('pattern: pattern solid, fore_colour gray25; alignment: horiz centre; borders: right medium', num_format_str="0.0")
        var_style_bad = xlwt.easyxf('pattern: pattern solid, fore_colour gray40; alignment: horiz centre; borders: right medium', num_format_str="0.0")
        
        # formatting for overall grades
        over_style_good = xlwt.easyxf('pattern: pattern solid, fore_colour light_green; alignment: horiz centre; font: bold on; borders: left medium, right medium', num_format_str="0.0")
        over_style_medium = xlwt.easyxf('pattern: pattern solid, fore_colour light_yellow; alignment: horiz centre; font: bold on; borders: left medium, right medium', num_format_str="0.0")
        over_style_bad = xlwt.easyxf('pattern: pattern solid, fore_colour light_yellow; alignment: horiz centre; font: bold on; borders: left medium, right medium', num_format_str="0.0")
        
        # formatting for special fields
        headline_style = xlwt.easyxf('font: bold on, height 400; alignment: horiz centre, vert centre, wrap on', num_format_str="0.0")
        course_style = xlwt.easyxf('alignment: horiz centre, wrap on, rota 90; borders: left medium, top medium')
        course_unfinished_style = xlwt.easyxf('alignment: horiz centre, wrap on, rota 90; borders: left medium, top medium; font: italic on')
        total_answers_style = xlwt.easyxf('alignment: horiz centre; borders: left medium, bottom medium, right medium')
        
        # general formattings
        bold_style = xlwt.easyxf('font: bold on')
        border_left_style = xlwt.easyxf('borders: left medium')
        border_right_style = xlwt.easyxf('borders: right medium')
        border_top_bottom_right_style = xlwt.easyxf('borders: top medium, bottom medium, right medium')
        
        self.writec(_(u"Evaluation {0} - created on {1}").format(self.semester.name, datetime.date.today()), headline_style)
        for course, results in courses_with_results:
            if course.state == "published":
                self.writec(course.name, course_style, cols=2)
            else:
                self.writec(course.name, course_unfinished_style, cols=2)
        
        self.writen()
        for course, results in courses_with_results:
            self.writec("Average", avg_style)
            self.writec("Variance", border_top_bottom_right_style)
        
        for questionnaire in questionnaires:
            self.writen(questionnaire.name, bold_style)
            for course, results in courses_with_results:
                self.writec(None, border_left_style)
                self.writec(None, border_right_style)
            
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
                        for contributor, data, grade in qn_results:
                            for grade_result in data:
                                if grade_result.question.id == question.id:
                                    if grade_result.average:
                                        values.append(grade_result.average)
                                        variances.append(grade_result.variance)
                                        if not grade_result.show:
                                            enough_answers = False
                                    break
                        if values and (enough_answers or all):
                            avg = sum(values) / len(values)
                            if avg < 2:
                                self.writec(avg, avg_style_good)
                            elif avg < 3:
                                self.writec(avg, avg_style_medium)
                            else:
                                self.writec(avg, avg_style_bad)
                            
                            var = sum(variances) / len(variances)
                            if var < 0.5:
                                self.writec(var, var_style_good)
                            elif var < 1:
                                self.writec(var, var_style_medium)
                            else:
                                self.writec(var, var_style_bad)
                        else:
                            self.writec(None, border_left_style)
                            self.writec(None, border_right_style)
                    else:
                        self.writec(None, border_left_style)
                        self.writec(None, border_right_style)
            self.writen(None)
            for course, results in courses_with_results:
                    self.writec(None, border_left_style)
                    self.writec(None, border_right_style)
        
        self.writen(_(u"Overall Grade"), bold_style)
        for course, results in courses_with_results:
            avg = calculate_average_grade(course)
            if avg:
                if avg < 2:
                    self.writec(avg, over_style_good, cols=2)
                elif avg < 3:
                    self.writec(avg, over_style_medium, cols=2)
                else:
                    self.writec(avg, over_style_bad, cols=2)
            else:
                self.writec(None, border_left_style)
                self.writec(None, border_right_style)
        
        self.writen(_(u"Total Answers"), bold_style)
        for course, results in courses_with_results:
            self.writec(course.num_voters, total_answers_style, cols=2)
        
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
