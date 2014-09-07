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

    styles = {
        'default':       xlwt.Style.default_style,
        'avg':           xlwt.easyxf('alignment: horiz centre; font: bold on; borders: left medium, top medium, bottom medium'),
        'variance_low':  xlwt.easyxf('alignment: horiz centre; borders: right medium', num_format_str="0.0"),
        'variance_med':  xlwt.easyxf('pattern: pattern solid, fore_colour gray25; alignment: horiz centre; borders: right medium', num_format_str="0.0"),
        'variance_high': xlwt.easyxf('pattern: pattern solid, fore_colour gray40; alignment: horiz centre; borders: right medium', num_format_str="0.0"),
        'headline':      xlwt.easyxf('font: bold on, height 400; alignment: horiz centre, vert centre, wrap on', num_format_str="0.0"),
        'course':        xlwt.easyxf('alignment: horiz centre, wrap on, rota 90; borders: left medium, top medium'),
        'course_unfinished': xlwt.easyxf('alignment: horiz centre, wrap on, rota 90; borders: left medium, top medium; font: italic on'),
        'total_voters': xlwt.easyxf('alignment: horiz centre; borders: left medium, bottom medium, right medium'),
        'bold':          xlwt.easyxf('font: bold on'),
        'border_left':   xlwt.easyxf('borders: left medium'),
        'border_right':  xlwt.easyxf('borders: right medium'),
        'border_top_bottom_right': xlwt.easyxf('borders: top medium, bottom medium, right medium')}

    grade_color_palette = [["custom_dark_green",  0x20, (136, 191, 74)],
                               ["custom_light_green", 0x21, (187, 209, 84)],
                               ["custom_yellow",      0x22, (239, 226, 88)],
                               ["custom_orange",      0x23, (242, 158, 88)],
                               ["custom_red",         0x24, (235,  89, 90)]]

    # Adding evaP colors to palette
    for index, c in enumerate(grade_color_palette):
        xlwt.add_palette_colour(c[0], c[1])
        styles['grade_' + str(index)] = xlwt.easyxf('pattern: pattern solid, fore_colour '+c[0]+'; alignment: horiz centre; font: bold on; borders: left medium', num_format_str="0.0")


    @classmethod
    def add_color_palette_to_workbook(cls, workbook):
        for c in cls.grade_color_palette:
            workbook.set_colour_RGB(c[1], *c[2])

    @staticmethod
    def grade_to_style(grade):
        rounded_grade = round(grade, 1)
        if grade < 1.5:
            return 'grade_0'
        elif grade < 2.5:
            return 'grade_1'
        elif grade < 3.5:
            return 'grade_2'
        elif grade < 4.5:
            return 'grade_3'
        else:
            return 'grade_4'

    @staticmethod
    def variance_to_style(variance):
        rounded_variance = round(variance, 1)
        if rounded_variance < 0.5:
            return 'variance_low'
        elif rounded_variance < 1.0:
            return 'variance_med'
        else:
            return 'variance_high'

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

        self.writec(_(u"Evaluation {0} - created on {1}").format(self.semester.name, datetime.date.today()), "headline")
        for course, results in courses_with_results:
            if course.state == "published":
                self.writec(course.name, "course", cols=2)
            else:
                self.writec(course.name, "course_unfinished", cols=2)

        self.writen()
        for course, results in courses_with_results:
            self.writec("Average", "avg")
            self.writec("Variance", "border_top_bottom_right")

        for questionnaire in questionnaires:
            self.writen(questionnaire.name, "bold")
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

        self.writen(_(u"Overall Average Grade"), "bold")
        for course, results in courses_with_results:
            avg, med = calculate_average_and_medium_grades(course)
            if avg:
                self.writec(avg, ExcelExporter.grade_to_style(avg), cols=2)
            else:
                self.write_two_empty_cells_with_borders()

        self.writen(_(u"Overall Median Grade"), "bold")
        for course, results in courses_with_results:
            avg, med = calculate_average_and_medium_grades(course)
            if med:
                self.writec(med, ExcelExporter.grade_to_style(med), cols=2)
            else:
                self.write_two_empty_cells_with_borders()

        self.writen(_(u"Total Voters/Total Participants"), "bold")
        for course, results in courses_with_results:
            self.writec(str(course.num_voters) + "/" + str(course.num_participants) + " ({:.0%})".format(float(course.num_voters)/float(course.num_participants)), "total_voters", cols=2)

        self.workbook.save(response)


    def write_two_empty_cells_with_borders(self):
        self.writec(None, "border_left")
        self.writec(None, "border_right")

    def writen(self, label="", style_name="default"):
        """Write the cell at the beginning of the next row."""
        self.col = 0
        self.row += 1
        self.writec(label, style_name)

    def writec(self, label, style_name, rows=1, cols=1):
        """Write the cell in the next column of the current line."""
        self._write(label, ExcelExporter.styles[style_name], rows, cols )
        self.col += 1

    def _write(self, label, style, rows, cols):
        if rows > 1 or cols > 1:
            self.sheet.write_merge(self.row, self.row+rows-1, self.col, self.col+cols-1, label, style)
            self.col += cols - 1
        else:
            self.sheet.write(self.row, self.col, label, style)
