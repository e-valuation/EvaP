from collections import OrderedDict

from django.utils.translation import ugettext as _

import xlwt

from evap.evaluation.models import CourseType
from evap.results.tools import collect_results, calculate_average_distribution, get_grade_color, distribution_to_grade


class ExcelExporter(object):

    CUSTOM_COLOR_START = 8
    NUM_GRADE_COLORS = 21  # 1.0 to 5.0 in 0.2 steps
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
            'default':          xlwt.Style.default_style,
            'headline':         xlwt.easyxf('font: bold on, height 400; alignment: horiz centre, vert centre, wrap on; borders: bottom medium', num_format_str="0.0"),
            'course':           xlwt.easyxf('alignment: horiz centre, wrap on, rota 90; borders: left medium, top medium, right medium, bottom medium'),
            'total_voters':     xlwt.easyxf('alignment: horiz centre; borders: left medium, right medium'),
            'evaluation_rate':  xlwt.easyxf('alignment: horiz centre; borders: left medium, bottom medium, right medium'),
            'bold':             xlwt.easyxf('font: bold on'),
            'italic':           xlwt.easyxf('font: italic on'),
            'border_left_right': xlwt.easyxf('borders: left medium, right medium'),
            'border_top_bottom_right': xlwt.easyxf('borders: top medium, bottom medium, right medium')}

        grade_base_style = 'pattern: pattern solid, fore_colour {}; alignment: horiz centre; font: bold on; borders: left medium, right medium'
        for i in range(0, self.NUM_GRADE_COLORS):
            grade = 1 + i * self.STEP
            color = get_grade_color(grade)
            palette_index = self.CUSTOM_COLOR_START + i
            style_name = self.grade_to_style(grade)
            color_name = style_name + "_color"
            self.create_color(workbook, color_name, palette_index, color)
            self.create_style(grade_base_style, style_name, color_name)

    def grade_to_style(self, grade):
        return 'grade_' + str(self.normalize_number(grade))

    def filter_text_and_heading_questions(self, questions):
        # remove text questions:
        questions = [question for question in questions if not question.is_text_question]

        # remove heading questions if they have no "content" below them
        filtered_questions = []
        for index in range(len(questions)):
            question = questions[index]
            if question.is_heading_question:
                # filter out if there are no more questions or the next question is also a heading question
                if index == len(questions) - 1 or questions[index + 1].is_heading_question:
                    continue
            filtered_questions.append(question)

        return filtered_questions

    def export(self, response, course_types_list, include_not_enough_voters=False, include_unpublished=False):
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
            for course in self.semester.courses.filter(state__in=course_states, type__in=course_types).all():
                if course.is_single_result:
                    continue
                if not course.can_publish_rating_results and not include_not_enough_voters:
                    continue
                results = OrderedDict()
                for questionnaire_result in collect_results(course).questionnaire_results:
                    if all(not question_result.question.is_rating_question or question_result.counts is None for question_result in questionnaire_result.question_results):
                        continue
                    results.setdefault(questionnaire_result.questionnaire.id, []).extend(questionnaire_result.question_results)
                    used_questionnaires.add(questionnaire_result.questionnaire)
                courses_with_results.append((course, results))

            courses_with_results.sort(key=lambda cr: (cr[0].type.order, cr[0].name))
            used_questionnaires = sorted(used_questionnaires)

            course_type_names = [ct.name for ct in CourseType.objects.filter(pk__in=course_types)]
            writec(self, _("Evaluation {0}\n\n{1}").format(self.semester.name, ", ".join(course_type_names)), "headline")

            for course, results in courses_with_results:
                writec(self, course.name, "course")

            writen(self)
            for course, results in courses_with_results:
                self.write_empty_cell_with_borders()

            for questionnaire in used_questionnaires:
                writen(self, questionnaire.name, "bold")
                for course, results in courses_with_results:
                    self.write_empty_cell_with_borders()

                filtered_questions = self.filter_text_and_heading_questions(questionnaire.questions.all())

                for question in filtered_questions:
                    if question.is_heading_question:
                        writen(self, question.text, "italic")
                    else:
                        writen(self, question.text)

                    for course, results in courses_with_results:
                        if questionnaire.id not in results or question.is_heading_question:
                            self.write_empty_cell_with_borders()
                            continue
                        qn_results = results[questionnaire.id]
                        values = []
                        count_sum = 0
                        approval_count = 0

                        for grade_result in qn_results:
                            if grade_result.question.id == question.id:
                                if grade_result.has_answers:
                                    values.append(grade_result.average * grade_result.count_sum)
                                    count_sum += grade_result.count_sum
                                    if grade_result.question.is_yes_no_question:
                                        approval_count += grade_result.approval_count
                        if values:
                            avg = sum(values) / count_sum

                            if question.is_yes_no_question:
                                percent_approval = approval_count / count_sum if count_sum > 0 else 0
                                writec(self, "{:.0%}".format(percent_approval), self.grade_to_style(avg))
                            else:
                                writec(self, avg, self.grade_to_style(avg))
                        else:
                            self.write_empty_cell_with_borders()
                writen(self)
                for course, results in courses_with_results:
                    self.write_empty_cell_with_borders()

            writen(self, _("Overall Average Grade"), "bold")
            for course, results in courses_with_results:
                avg = distribution_to_grade(calculate_average_distribution(course))
                if avg:
                    writec(self, avg, self.grade_to_style(avg))
                else:
                    self.write_empty_cell_with_borders()

            writen(self, _("Total voters/Total participants"), "bold")
            for course, results in courses_with_results:
                writec(self, "{}/{}".format(course.num_voters, course.num_participants), "total_voters")

            writen(self, _("Evaluation rate"), "bold")
            for course, results in courses_with_results:
                # round down like in progress bar
                percentage_participants = int((course.num_voters / course.num_participants) * 100) if course.num_participants > 0 else 0
                writec(self, "{}%".format(percentage_participants), "evaluation_rate")

        self.workbook.save(response)

    def write_empty_cell_with_borders(self):
        writec(self, None, "border_left_right")


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
