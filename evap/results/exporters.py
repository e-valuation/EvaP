from evap.evaluation.models import Questionnaire
from evap.evaluation.tools import calculate_results, calculate_average_and_medium_grades, get_grade_color

from django.utils.translation import ugettext as _

from collections import OrderedDict
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
        
    # We only assign different colors every 0.2 grades, because excel limits the number of custom colors
    # colors up to 0x20 are already pre-defined in the xls-format
    grades_and_indices = [(1 + i*2/10.0, 0x20 + i) for i in range(21)]
       
    grade_base_style = 'pattern: pattern solid, fore_colour {}; alignment: horiz centre; font: bold on; borders: left medium'
    # Adding evaP colors to palette
    for grade, index in grades_and_indices:
        color_name = 'custom_grade_color_' + str(grade)
        style_name = 'grade_' + str(grade)
        xlwt.add_palette_colour(color_name, index)
        styles[style_name] = xlwt.easyxf(grade_base_style.format(color_name), num_format_str="0.0")

    @classmethod
    def add_color_palette_to_workbook(cls, workbook):
        for grade, index in cls.grades_and_indices:
            workbook.set_colour_RGB(index, *get_grade_color(grade))

    @staticmethod
    def grade_to_style(grade):
        # Round grade to .2 steps
        grade = int(grade * 5) * 0.2
        return 'grade_' + str(grade)
        
    @staticmethod
    def variance_to_style(variance):
        rounded_variance = round(variance, 1)
        if rounded_variance < 0.5:
            return 'variance_low'
        elif rounded_variance < 1.0:
            return 'variance_med'
        else:
            return 'variance_high'

    def export(self, response, ignore_not_enough_answers=False):
        courses_with_results = list()
        for course in self.semester.course_set.filter(state="published").all():
            results = OrderedDict()
            for questionnaire, contributor, data, avg_likert, med_likert, avg_grade, med_grade, avg_total, med_total, section_warning in calculate_results(course):
                results.setdefault(questionnaire.id, []).append((contributor, data, avg_total, med_total))
            courses_with_results.append((course, results))

        courses_with_results.sort(key=lambda cr: cr[0].kind)

        qn_frequencies = defaultdict(int)
        for course, results in courses_with_results:
            for questionnaire, results in results.items():
                qn_frequencies[questionnaire] += 1

        qn_relevant = list(qn_frequencies.items())
        qn_relevant.sort(key=lambda t: -t[1])

        questionnaires = [Questionnaire.objects.get(id=t[0]) for t in qn_relevant]

        self.workbook = xlwt.Workbook()
        self.sheet = self.workbook.add_sheet(_(u"Results"))
        self.row = 0
        self.col = 0

        
        self.add_color_palette_to_workbook(self.workbook)

        writec(self, _(u"Evaluation {0} - created on {1}").format(self.semester.name, datetime.date.today()), "headline")
        for course, results in courses_with_results:
            if course.state == "published":
                writec(self, course.name, "course", cols=2)
            else:
                writec(self, course.name, "course_unfinished", cols=2)

        writen(self)
        for course, results in courses_with_results:
            writec(self, "Average", "avg")
            writec(self, "Variance", "border_top_bottom_right")

        for questionnaire in questionnaires:
            writen(self, questionnaire.name, "bold")
            for course, results in courses_with_results:
                self.write_two_empty_cells_with_borders()

            for question in questionnaire.question_set.all():
                if question.is_text_question():
                    continue

                writen(self, question.text)

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
                        if values and (enough_answers or ignore_not_enough_answers):
                            avg = sum(values) / len(values)
                            writec(self, avg, ExcelExporter.grade_to_style(avg));

                            var = sum(variances) / len(variances)
                            writec(self, var, ExcelExporter.variance_to_style(var))
                        else:
                            self.write_two_empty_cells_with_borders()
                    else:
                        self.write_two_empty_cells_with_borders()
            writen(self, None)
            for course, results in courses_with_results:
                self.write_two_empty_cells_with_borders()

        writen(self, _(u"Overall Average Grade"), "bold")
        for course, results in courses_with_results:
            avg, med = calculate_average_and_medium_grades(course)
            if avg:
                writec(self, avg, ExcelExporter.grade_to_style(avg), cols=2)
            else:
                self.write_two_empty_cells_with_borders()

        writen(self, _(u"Overall Median Grade"), "bold")
        for course, results in courses_with_results:
            avg, med = calculate_average_and_medium_grades(course)
            if med:
                writec(self, med, ExcelExporter.grade_to_style(med), cols=2)
            else:
                self.write_two_empty_cells_with_borders()

        writen(self, _(u"Total Voters/Total Participants"), "bold")
        for course, results in courses_with_results:
            percent_participants = float(course.num_voters)/float(course.num_participants)
            writec(self, "{}/{} ({:.0%})".format(course.num_voters, course.num_participants, percent_participants), "total_voters", cols=2)

        self.workbook.save(response)


    def write_two_empty_cells_with_borders(self):
        writec(self, None, "border_left")
        writec(self, None, "border_right")


def writen(exporter, label="", style_name="default"):
    """Write the cell at the beginning of the next row."""
    exporter.col = 0
    exporter.row += 1
    writec(exporter, label, style_name)

def writec(exporter, label, style_name, rows=1, cols=1):
    """Write the cell in the next column of the current line."""
    _write(exporter, label, ExcelExporter.styles[style_name], rows, cols )
    exporter.col += 1

def _write(exporter, label, style, rows, cols):
    if rows > 1 or cols > 1:
        exporter.sheet.write_merge(exporter.row, exporter.row+rows-1, exporter.col, exporter.col+cols-1, label, style)
        exporter.col += cols - 1
    else:
        exporter.sheet.write(exporter.row, exporter.col, label, style)
