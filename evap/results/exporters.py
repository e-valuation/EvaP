from collections import OrderedDict

from django.utils.translation import ugettext as _

import xlwt

from evap.evaluation.models import CourseType
from evap.evaluation.tools import calculate_results, calculate_average_grades_and_deviation, get_grade_color, get_deviation_color, has_no_rating_answers


class ExcelExporter(object):

    CUSTOM_COLOR_START = 8
    NUM_GRADE_COLORS = 21  # 1.0 to 5.0 in 0.2 steps
    NUM_DEVIATION_COLORS = 13  # 0.0 to 2.4 in 0.2 steps
    STEP = 0.2  # we only have a limited number of custom colors

    def __init__(self, semester):
        self.semester = semester
        self.styles = dict()

    def normalize_number(self, number):
        """ floors 'number' to a multiply of self.STEP """
        rounded_number = round(number, 1)  # see #302
        return round(int(rounded_number / self.STEP + 0.0001) * self.STEP, 1)

    def create_color(self, workbook, color_name, palette_index, color):
        xlwt.add_palette_colour(color_name, palette_index)
        workbook.set_colour_RGB(palette_index, *color)

    def create_style(self, base_style, style_name, color_name):
        self.styles[style_name] = xlwt.easyxf(base_style.format(color_name), num_format_str="0.0")

    def init_styles(self, workbook):
        self.styles = {
            'default':       xlwt.Style.default_style,
            'avg':           xlwt.easyxf('alignment: horiz centre; font: bold on; borders: left medium, top medium, bottom medium'),
            'headline':      xlwt.easyxf('font: bold on, height 400; alignment: horiz centre, vert centre, wrap on', num_format_str="0.0"),
            'course':        xlwt.easyxf('alignment: horiz centre, wrap on, rota 90; borders: left medium, top medium, right medium'),
            'total_voters':  xlwt.easyxf('alignment: horiz centre; borders: left medium, bottom medium, right medium'),
            'bold':          xlwt.easyxf('font: bold on'),
            'border_left':   xlwt.easyxf('borders: left medium'),
            'border_right':  xlwt.easyxf('borders: right medium'),
            'border_top_bottom_right': xlwt.easyxf('borders: top medium, bottom medium, right medium')}

        grade_base_style = 'pattern: pattern solid, fore_colour {}; alignment: horiz centre; font: bold on; borders: left medium'
        for i in range(0, self.NUM_GRADE_COLORS):
            grade = 1 + i * self.STEP
            color = get_grade_color(grade)
            palette_index = self.CUSTOM_COLOR_START + i
            style_name = self.grade_to_style(grade)
            color_name = style_name + "_color"
            self.create_color(workbook, color_name, palette_index, color)
            self.create_style(grade_base_style, style_name, color_name)
            self.create_style(grade_base_style + ', right medium', style_name + '_total', color_name)

        deviation_base_style = 'pattern: pattern solid, fore_colour {}; alignment: horiz centre; borders: right medium'
        for i in range(0, self.NUM_DEVIATION_COLORS):
            deviation = i * self.STEP
            color = get_deviation_color(deviation)
            palette_index = self.CUSTOM_COLOR_START + self.NUM_GRADE_COLORS + i
            style_name = self.deviation_to_style(deviation)
            color_name = style_name + "_color"
            self.create_color(workbook, color_name, palette_index, color)
            self.create_style(deviation_base_style, style_name, color_name)
            self.create_style(deviation_base_style + ', left medium', style_name + '_total', color_name)

    def grade_to_style(self, grade, total=False):
        style_name = 'grade_' + str(self.normalize_number(grade))
        if total:
            style_name += "_total"
        return style_name

    def deviation_to_style(self, deviation, total=False):
        style_name = 'deviation_' + str(self.normalize_number(deviation))
        if total:
            style_name += "_total"
        return style_name

    def export(self, response, course_types_list, ignore_not_enough_answers=False, include_unpublished=False):
        self.workbook = xlwt.Workbook()
        self.init_styles(self.workbook)
        counter = 1

        for course_types in course_types_list:
            self.sheet = self.workbook.add_sheet("Sheet " + str(counter))
            counter += 1
            self.row = 0
            self.col = 0

            courses_with_results = list()
            course_states = ['published']
            if include_unpublished:
                course_states.extend(['evaluated', 'reviewed'])

            used_questionnaires = set()
            for course in self.semester.course_set.filter(state__in=course_states, type__in=course_types).all():
                if course.is_single_result:
                    continue
                results = OrderedDict()
                for questionnaire, contributor, __, data, __ in calculate_results(course):
                    if has_no_rating_answers(course, contributor, questionnaire):
                        continue
                    results.setdefault(questionnaire.id, []).extend(data)
                    used_questionnaires.add(questionnaire)
                courses_with_results.append((course, results))

            courses_with_results.sort(key=lambda cr: cr[0].type)
            used_questionnaires = sorted(used_questionnaires)

            course_type_names = [ct.name for ct in CourseType.objects.filter(pk__in=course_types)]
            writec(self, _("Evaluation {0}\n\n{1}").format(self.semester.name, ", ".join(course_type_names)), "headline")

            for course, results in courses_with_results:
                writec(self, course.name, "course", cols=2)

            writen(self)
            for course, results in courses_with_results:
                writec(self, "Average", "avg")
                writec(self, "Deviation", "border_top_bottom_right")

            for questionnaire in used_questionnaires:
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
                        total_count = 0

                        for grade_result in qn_results:
                            if grade_result.question.id == question.id:
                                if grade_result.average:
                                    values.append(grade_result.average * grade_result.total_count)
                                    deviations.append(grade_result.deviation * grade_result.total_count)
                                    total_count += grade_result.total_count
                        enough_answers = course.can_publish_grades
                        if values and (enough_answers or ignore_not_enough_answers):
                            avg = sum(values) / total_count
                            writec(self, avg, self.grade_to_style(avg))

                            dev = sum(deviations) / total_count
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
                    writec(self, avg, self.grade_to_style(avg, total=True), cols=2)
                else:
                    self.write_two_empty_cells_with_borders()

            writen(self, _("Overall Average Standard Deviation"), "bold")
            for course, results in courses_with_results:
                avg, dev = calculate_average_grades_and_deviation(course)
                if dev is not None:
                    writec(self, dev, self.deviation_to_style(dev, total=True), cols=2)
                else:
                    self.write_two_empty_cells_with_borders()

            writen(self, _("Total Voters/Total Participants"), "bold")
            for course, results in courses_with_results:
                percent_participants = float(course.num_voters) / float(course.num_participants) if course.num_participants > 0 else 0
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
