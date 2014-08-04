from evap.evaluation.models import Questionnaire
from evap.evaluation.tools import calculate_results, calculate_average_and_medium_grades

from django.utils.datastructures import SortedDict
from django.utils.translation import ugettext as _

from collections import defaultdict
import datetime
import xlwt


class ExcelExporter(object):

    def __init__(self, semester):
        self.semester = semester

    grade_color_palette = [["custom_dark_green",  0x20, (120, 241, 89)],
                               ["custom_light_green", 0x21, (188, 241, 89)],
                               ["custom_yellow",      0x22, (241, 226, 89)],
                               ["custom_orange",      0x23, (241, 158, 89)],
                               ["custom_red",         0x24, (241,  89, 89)]]

    # Adding evaP colors to palette
    grade_styles = []
    for c in grade_color_palette:
        xlwt.add_palette_colour(c[0], c[1])
        grade_styles.append(xlwt.easyxf('pattern: pattern solid, fore_colour '+c[0]+'; alignment: horiz centre; font: bold on; borders: left medium', num_format_str="0.0"))


    avg_style = xlwt.easyxf('alignment: horiz centre; font: bold on; borders: left medium, top medium, bottom medium')

    # formatting for variances
    variance_styles = [xlwt.easyxf('alignment: horiz centre; borders: right medium', num_format_str="0.0"),
                       xlwt.easyxf('pattern: pattern solid, fore_colour gray25; alignment: horiz centre; borders: right medium', num_format_str="0.0"),
                       xlwt.easyxf('pattern: pattern solid, fore_colour gray40; alignment: horiz centre; borders: right medium', num_format_str="0.0")]

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

    @classmethod
    def add_color_palette_to_workbook(cls, workbook):
        for c in cls.grade_color_palette:
            workbook.set_colour_RGB(c[1], *c[2])

    @classmethod
    def grade_to_style(cls, grade):
        rounded_grade = round(grade, 1)
        if grade < 1.5:
            return cls.grade_styles[0]
        elif grade < 2.5:
            return cls.grade_styles[1]
        elif grade < 3.5:
            return cls.grade_styles[2]
        elif grade < 4.5:
            return cls.grade_styles[3]
        else:
            return cls.grade_styles[4]

    @classmethod
    def variance_to_style(cls, variance):
        rounded_variance = round(variance, 1)
        if rounded_variance < 0.5:
            return cls.variance_styles[0]
        elif rounded_variance < 1.0:
            return cls.variance_styles[1]
        else:
            return cls.variance_styles[2]

    def export(self, response, all=False):
        courses_with_results = list()
        for course in self.semester.course_set.filter(state="published").all():
            results = SortedDict()
            for questionnaire, contributor, data, avg_likert, med_likert, avg_grade, med_grade, avg_total, med_total in calculate_results(course):
                results.setdefault(questionnaire.id, []).append((contributor, data, avg_total, med_total))
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

        
        self.add_color_palette_to_workbook(self.workbook)

        self.writec(_(u"Evaluation {0} - created on {1}").format(self.semester.name, datetime.date.today()), ExcelExporter.headline_style)
        for course, results in courses_with_results:
            if course.state == "published":
                self.writec(course.name, ExcelExporter.course_style, cols=2)
            else:
                self.writec(course.name, ExcelExporter.course_unfinished_style, cols=2)

        self.writen()
        for course, results in courses_with_results:
            self.writec("Average", ExcelExporter.avg_style)
            self.writec("Variance", ExcelExporter.border_top_bottom_right_style)

        for questionnaire in questionnaires:
            self.writen(questionnaire.name, ExcelExporter.bold_style)
            for course, results in courses_with_results:
                self.write_two_empty_cells_with_borders()

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
                        for contributor, data, avg_grade, med_grade in qn_results:
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
                            self.writec(avg, ExcelExporter.grade_to_style(avg));

                            var = sum(variances) / len(variances)
                            self.writec(var, ExcelExporter.variance_to_style(var))
                        else:
                            self.write_two_empty_cells_with_borders()
                    else:
                        self.write_two_empty_cells_with_borders()
            self.writen(None)
            for course, results in courses_with_results:
                    self.write_two_empty_cells_with_borders()

        self.writen(_(u"Overall Average Grade"), ExcelExporter.bold_style)
        for course, results in courses_with_results:
            avg, med = calculate_average_and_medium_grades(course)
            if avg:
                self.writec(avg, ExcelExporter.grade_to_style(avg), cols=2)
            else:
                self.write_two_empty_cells_with_borders()

        self.writen(_(u"Overall Median Grade"), ExcelExporter.bold_style)
        for course, results in courses_with_results:
            avg, med = calculate_average_and_medium_grades(course)
            if med:
                self.writec(med, ExcelExporter.grade_to_style(med), cols=2)
            else:
                self.write_two_empty_cells_with_borders()

        self.writen(_(u"Total Answers"), ExcelExporter.bold_style)
        for course, results in courses_with_results:
            self.writec(course.num_voters, ExcelExporter.total_answers_style, cols=2)

        self.workbook.save(response)


    def write_two_empty_cells_with_borders(self):
        self.writec(None, ExcelExporter.border_left_style)
        self.writec(None, ExcelExporter.border_right_style)

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
