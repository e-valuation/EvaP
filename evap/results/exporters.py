from evap.evaluation.models import Questionnaire
from evap.evaluation.tools import calculate_results, calculate_average_grades_and_deviation, get_grade_color, get_deviation_color

from django.utils.translation import ugettext as _

from collections import OrderedDict
from collections import defaultdict
import datetime
import xlwt


class ExcelExporter(object):

    def __init__(self, semester):
        self.semester = semester
        self.styles = dict()

        self.CUSTOM_COLOR_START = 8
        self.NUM_GRADE_COLORS = 21 # 1.0 to 5.0 in 0.2 steps
        self.NUM_DEVIATION_COLORS = 13 # 0.0 to 2.4 in 0.2 steps
        self.STEP = 0.2 # we only have a limited number of custom colors

    def normalize_number(self, number):
        """ floors 'number' to a multiply of self.STEP """
        rounded_number = round(number, 1) # see #302
        return round(int(rounded_number / self.STEP + 0.0001) * self.STEP, 1)

    def create_style(self, workbook, base_style, style_name, palette_index, color):
        color_name = style_name + "_color"
        xlwt.add_palette_colour(color_name, palette_index)
        workbook.set_colour_RGB(palette_index, *color)
        self.styles[style_name] = xlwt.easyxf(base_style.format(color_name), num_format_str="0.0")

    def init_styles(self, workbook):
        self.styles = {
            'default':       xlwt.Style.default_style,
            'avg':           xlwt.easyxf('alignment: horiz centre; font: bold on; borders: left medium, top medium, bottom medium'),
            'headline':      xlwt.easyxf('font: bold on, height 400; alignment: horiz centre, vert centre, wrap on', num_format_str="0.0"),
            'course':        xlwt.easyxf('alignment: horiz centre, wrap on, rota 90; borders: left medium, top medium'),
            'total_voters': xlwt.easyxf('alignment: horiz centre; borders: left medium, bottom medium, right medium'),
            'bold':          xlwt.easyxf('font: bold on'),
            'border_left':   xlwt.easyxf('borders: left medium'),
            'border_right':  xlwt.easyxf('borders: right medium'),
            'border_top_bottom_right': xlwt.easyxf('borders: top medium, bottom medium, right medium')}



        grade_base_style = 'pattern: pattern solid, fore_colour {}; alignment: horiz centre; font: bold on; borders: left medium'
        for i in range(0, self.NUM_GRADE_COLORS):
            grade = 1 + i*self.STEP
            color = get_grade_color(grade)
            palette_index = self.CUSTOM_COLOR_START + i
            style_name = self.grade_to_style(grade)
            self.create_style(workbook, grade_base_style, style_name, palette_index, color)

        deviation_base_style = 'pattern: pattern solid, fore_colour {}; alignment: horiz centre; borders: right medium'
        for i in range(0, self.NUM_DEVIATION_COLORS):
            deviation = i * self.STEP
            color = get_deviation_color(deviation)
            palette_index = self.CUSTOM_COLOR_START + self.NUM_GRADE_COLORS + i
            style_name = self.deviation_to_style(deviation)
            self.create_style(workbook, deviation_base_style, style_name, palette_index, color)


    def grade_to_style(self, grade):
        return 'grade_' + str(self.normalize_number(grade))

    def deviation_to_style(self, deviation):
        return 'deviation_' + str(self.normalize_number(deviation))

    def export(self, response, course_types_list, ignore_not_enough_answers=False):
        self.workbook = xlwt.Workbook()
        self.init_styles(self.workbook)
        counter = 1

        for course_types in course_types_list:
            self.sheet = self.workbook.add_sheet("Sheet " + str(counter))
            counter += 1
            self.row = 0
            self.col = 0

            courses_with_results = list()
            for course in self.semester.course_set.filter(state="published", type__in=course_types).all():
                if course.is_single_result():
                    continue
                results = OrderedDict()
                for questionnaire, contributor, label, data, section_warning in calculate_results(course):
                    results.setdefault(questionnaire.id, []).extend(data)
                courses_with_results.append((course, results))

            courses_with_results.sort(key=lambda cr: cr[0].type)

            qn_frequencies = defaultdict(int)
            for course, results in courses_with_results:
                for questionnaire, results in results.items():
                    qn_frequencies[questionnaire] += 1

            qn_relevant = list(qn_frequencies.items())
            qn_relevant.sort(key=lambda t: -t[1])

            questionnaires = [Questionnaire.objects.get(id=t[0]) for t in qn_relevant]


            writec(self, _("Evaluation {0}\n\n{1}").format(self.semester.name, ", ".join(course_types)), "headline")

            for course, results in courses_with_results:
                writec(self, course.name, "course", cols=2)

            writen(self)
            for course, results in courses_with_results:
                writec(self, "Average", "avg")
                writec(self, "Deviation", "border_top_bottom_right")

            for questionnaire in questionnaires:
                writen(self, questionnaire.name, "bold")
                for course, results in courses_with_results:
                    self.write_two_empty_cells_with_borders()

                for question in questionnaire.question_set.all():
                    if question.is_text_question:
                        continue

                    writen(self, question.text)

                    for course, results in courses_with_results:
                        if questionnaire.id not in results:
                            self.write_two_empty_cells_with_borders()
                            continue
                        qn_results = results[questionnaire.id]
                        values = []
                        deviations = []

                        for grade_result in qn_results:
                            if grade_result.question.id == question.id:
                                if grade_result.average:
                                    values.append(grade_result.average)
                                    deviations.append(grade_result.deviation)
                        enough_answers = course.can_publish_grades
                        if values and (enough_answers or ignore_not_enough_answers):
                            avg = sum(values) / len(values)
                            writec(self, avg, self.grade_to_style(avg))

                            dev = sum(deviations) / len(deviations)
                            writec(self, dev, self.deviation_to_style(dev))
                        else:
                            self.write_two_empty_cells_with_borders()
                writen(self, None)
                for course, results in courses_with_results:
                    self.write_two_empty_cells_with_borders()

            writen(self, _("Overall Average Grade"), "bold")
            for course, results in courses_with_results:
                avg, dev = calculate_average_grades_and_deviation(course)
                if avg:
                    writec(self, avg, self.grade_to_style(avg), cols=2)
                else:
                    self.write_two_empty_cells_with_borders()

            writen(self, _("Overall Average Standard Deviation"), "bold")
            for course, results in courses_with_results:
                avg, dev = calculate_average_grades_and_deviation(course)
                if dev is not None:
                    writec(self, dev, self.deviation_to_style(dev), cols=2)
                else:
                    self.write_two_empty_cells_with_borders()

            writen(self, _("Total Voters/Total Participants"), "bold")
            for course, results in courses_with_results:
                percent_participants = float(course.num_voters)/float(course.num_participants) if course.num_participants > 0 else 0
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
    _write(exporter, label, exporter.styles[style_name], rows, cols)
    exporter.col += 1

def _write(exporter, label, style, rows, cols):
    if rows > 1 or cols > 1:
        exporter.sheet.write_merge(exporter.row, exporter.row+rows-1, exporter.col, exporter.col+cols-1, label, style)
        exporter.col += cols - 1
    else:
        exporter.sheet.write(exporter.row, exporter.col, label, style)
