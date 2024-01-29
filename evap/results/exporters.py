import warnings
from collections import OrderedDict, defaultdict
from itertools import chain, repeat

import xlwt
from django.db.models import Q
from django.utils.translation import gettext as _

from evap.evaluation.models import CourseType, Degree, Evaluation, Questionnaire
from evap.evaluation.tools import ExcelExporter
from evap.results.tools import (
    RatingResult,
    calculate_average_course_distribution,
    calculate_average_distribution,
    distribution_to_grade,
    get_grade_color,
    get_results,
)


class ResultsExporter(ExcelExporter):
    CUSTOM_COLOR_START = 8
    NUM_GRADE_COLORS = 21  # 1.0 to 5.0 in 0.2 steps
    STEP = 0.2  # we only have a limited number of custom colors

    # Filled in ResultsExporter.init_grade_styles
    COLOR_MAPPINGS: dict[int, tuple[int, int, int]] = {}

    styles = {
        "evaluation": xlwt.easyxf(
            "alignment: horiz centre, wrap on, rota 90; borders: left medium, top medium, right medium, bottom medium"
        ),
        "total_voters": xlwt.easyxf("alignment: horiz centre; borders: left medium, right medium"),
        "evaluation_rate": xlwt.easyxf("alignment: horiz centre; borders: left medium, bottom medium, right medium"),
        "evaluation_weight": xlwt.easyxf("alignment: horiz centre; borders: left medium, right medium"),
        "degree": xlwt.easyxf("alignment: wrap on; borders: left medium, right medium"),
        # Grade styles added in ResultsExporter.init_grade_styles() #
        **ExcelExporter.styles,
    }

    def __init__(self):
        super().__init__()

        for index, color in self.COLOR_MAPPINGS.items():
            self.workbook.set_colour_RGB(index, *color)

    @classmethod
    def grade_to_style(cls, grade):
        return "grade_" + str(cls.normalize_number(grade))

    @classmethod
    def normalize_number(cls, number):
        """floors 'number' to a multiply of cls.STEP"""
        rounded_number = round(number, 1)  # see #302
        return round(int(rounded_number / cls.STEP + 0.0001) * cls.STEP, 1)

    @classmethod
    def init_grade_styles(cls):
        """
        Adds the grade styles to cls.styles and as a xlwt identifier.
        This also notes all registered colors in cls.COLOR_MAPPINGS for the instances.

        This method should only be called once, right after the class definition.
        Instances need the styles, but they should only be registered once for xlwt.
        """

        if len(cls.COLOR_MAPPINGS) > 0:
            # Method has already been called (probably in another import of this file).
            warnings.warn(
                "ResultsExporter.init_grade_styles has been called, "
                "although the styles have already been initialized. "
                "This can happen, if the file is imported / run multiple "
                "times in one application run.",
                ImportWarning,
            )
            return

        grade_base_style = "pattern: pattern solid, fore_colour {}; alignment: horiz centre; font: bold on; borders: left medium, right medium"
        for i in range(0, cls.NUM_GRADE_COLORS):
            grade = 1 + i * cls.STEP
            color = get_grade_color(grade)
            palette_index = cls.CUSTOM_COLOR_START + i
            style_name = cls.grade_to_style(grade)
            color_name = style_name + "_color"
            xlwt.add_palette_colour(color_name, palette_index)
            cls.COLOR_MAPPINGS[palette_index] = color
            cls.styles[style_name] = xlwt.easyxf(grade_base_style.format(color_name), num_format_str="0.0")

    @staticmethod
    def filter_text_and_heading_questions(questions):
        questions = [question for question in questions if not question.is_text_question]

        # remove heading questions if they have no "content" below them
        filtered_questions = []
        for index, question in enumerate(questions):
            if question.is_heading_question:
                # filter out if there are no more questions or the next question is also a heading question
                if index == len(questions) - 1 or questions[index + 1].is_heading_question:
                    continue
            filtered_questions.append(question)

        return filtered_questions

    @staticmethod
    def filter_evaluations(semesters, evaluation_states, degrees, course_types, contributor, include_not_enough_voters):
        # pylint: disable=too-many-locals
        course_results_exist = False
        evaluations_with_results = []
        used_questionnaires = set()
        evaluations_filter = Q(
            course__semester__in=semesters,
            state__in=evaluation_states,
            course__degrees__in=degrees,
            course__type__in=course_types,
        )
        if contributor:
            evaluations_filter = evaluations_filter & (
                Q(course__responsibles__in=[contributor]) | Q(contributions__contributor__in=[contributor])
            )
        evaluations = Evaluation.objects.filter(evaluations_filter).distinct()
        for evaluation in evaluations:
            if evaluation.is_single_result:
                continue
            if not evaluation.can_publish_rating_results and not include_not_enough_voters:
                continue
            results = OrderedDict()
            for contribution_result in get_results(evaluation).contribution_results:
                for questionnaire_result in contribution_result.questionnaire_results:
                    # RatingQuestion.counts is a tuple of integers or None, if this tuple is all zero, we want to exclude it
                    if all(
                        not question_result.question.is_rating_question or not RatingResult.has_answers(question_result)
                        for question_result in questionnaire_result.question_results
                    ):
                        continue
                    if (
                        not contributor
                        or contribution_result.contributor is None
                        or contribution_result.contributor == contributor
                    ):
                        results.setdefault(questionnaire_result.questionnaire.id, []).extend(
                            questionnaire_result.question_results
                        )
                        used_questionnaires.add(questionnaire_result.questionnaire)
            evaluation.course_evaluations_count = evaluation.course.evaluations.count()
            if evaluation.course_evaluations_count > 1:
                course_results_exist = True
                weight_sum = sum(evaluation.weight for evaluation in evaluation.course.evaluations.all())
                evaluation.weight_percentage = int((evaluation.weight / weight_sum) * 100)
                evaluation.course.avg_grade = distribution_to_grade(
                    calculate_average_course_distribution(evaluation.course)
                )
            evaluations_with_results.append((evaluation, results))

        evaluations_with_results.sort(
            key=lambda cr: (cr[0].course.semester.id, cr[0].course.type.order, cr[0].full_name)
        )
        used_questionnaires = sorted(used_questionnaires)

        return evaluations_with_results, used_questionnaires, course_results_exist

    def write_headings_and_evaluation_info(
        self, evaluations_with_results, semesters, contributor, degrees, course_types, verbose_heading
    ):
        export_name = _("Evaluation")
        if contributor:
            export_name += f"\n{contributor.full_name}"
        elif len(semesters) == 1:
            export_name += f"\n{semesters[0].name}"
        if verbose_heading:
            degree_names = [degree.name for degree in Degree.objects.filter(pk__in=degrees)]
            course_type_names = [course_type.name for course_type in CourseType.objects.filter(pk__in=course_types)]
            self.write_cell(
                f"{export_name}\n\n{', '.join(degree_names)}\n\n{', '.join(course_type_names)}",
                "headline",
            )
        else:
            self.write_cell(export_name, "headline")

        for evaluation, __ in evaluations_with_results:
            title = evaluation.full_name
            if len(semesters) > 1:
                title += f"\n{evaluation.course.semester.name}"
            responsible_names = [responsible.full_name for responsible in evaluation.course.responsibles.all()]
            title += f"\n{', '.join(responsible_names)}"
            self.write_cell(title, "evaluation")

        self.next_row()
        self.write_cell(_("Degrees"), "bold")
        for evaluation, __ in evaluations_with_results:
            self.write_cell("\n".join([d.name for d in evaluation.course.degrees.all()]), "degree")

        self.next_row()
        self.write_cell(_("Course Type"), "bold")
        for evaluation, __ in evaluations_with_results:
            self.write_cell(evaluation.course.type.name, "border_left_right")

        self.next_row()
        # One more cell is needed for the question column
        self.write_empty_row_with_styles(["default"] + ["border_left_right"] * len(evaluations_with_results))

    def write_overall_results(self, evaluations_with_results, course_results_exist):
        evaluations = [e for e, __ in evaluations_with_results]

        self.write_cell(_("Overall Average Grade"), "bold")
        averages = (distribution_to_grade(calculate_average_distribution(e)) for e in evaluations)
        self.write_row(averages, lambda avg: self.grade_to_style(avg) if avg else "border_left_right")

        self.write_cell(_("Total voters/Total participants"), "bold")
        voter_ratios = (f"{e.num_voters}/{e.num_participants}" for e in evaluations)
        self.write_row(voter_ratios, style="total_voters")

        self.write_cell(_("Evaluation rate"), "bold")
        # round down like in progress bar
        participant_percentages = (
            f"{int((e.num_voters / e.num_participants) * 100) if e.num_participants > 0 else 0}%" for e in evaluations
        )
        self.write_row(participant_percentages, style="evaluation_rate")

        if course_results_exist:
            # Only query the number of evaluations once and keep track of it here.
            count_gt_1 = [e.course_evaluations_count > 1 for e in evaluations]

            # Borders only if there is a course grade below. Offset by one column
            self.write_empty_row_with_styles(
                ["default"] + ["border_left_right" if gt1 else "default" for gt1 in count_gt_1]
            )

            self.write_cell(_("Evaluation weight"), "bold")
            weight_percentages = (f"{e.weight_percentage}%" if gt1 else None for e, gt1 in zip(evaluations, count_gt_1))
            self.write_row(weight_percentages, lambda s: "evaluation_weight" if s is not None else "default")

            self.write_cell(_("Course Grade"), "bold")
            for evaluation, gt1 in zip(evaluations, count_gt_1):
                if not gt1:
                    self.write_cell()
                    continue

                avg = evaluation.course.avg_grade
                style = self.grade_to_style(avg) if avg is not None else "border_left_right"
                self.write_cell(avg, style)
            self.next_row()

            # Same reasoning as above.
            self.write_empty_row_with_styles(["default"] + ["border_top" if gt1 else "default" for gt1 in count_gt_1])

    def write_questionnaire(self, questionnaire, evaluations_with_results, contributor):
        if contributor and questionnaire.type == Questionnaire.Type.CONTRIBUTOR:
            self.write_cell(f"{questionnaire.public_name} ({contributor.full_name})", "bold")
        else:
            self.write_cell(questionnaire.public_name, "bold")

        # first cell of row is printed above
        self.write_empty_row_with_styles(["border_left_right"] * len(evaluations_with_results))

        for question in self.filter_text_and_heading_questions(questionnaire.questions.all()):
            self.write_cell(question.text, "italic" if question.is_heading_question else "default")

            for __, results in evaluations_with_results:
                if questionnaire.id not in results or question.is_heading_question:
                    self.write_cell(style="border_left_right")
                    continue

                values = []
                count_sum = 0
                approval_count = 0

                for grade_result in results[questionnaire.id]:
                    if grade_result.question.id != question.id or not RatingResult.has_answers(grade_result):
                        continue
                    values.append(grade_result.average * grade_result.count_sum)
                    count_sum += grade_result.count_sum
                    if grade_result.question.is_yes_no_question:
                        approval_count += grade_result.approval_count

                if not values:
                    self.write_cell(style="border_left_right")
                    continue

                avg = sum(values) / count_sum
                if question.is_yes_no_question:
                    percent_approval = approval_count / count_sum if count_sum > 0 else 0
                    self.write_cell(f"{percent_approval:.0%}", self.grade_to_style(avg))
                else:
                    self.write_cell(avg, self.grade_to_style(avg))
            self.next_row()

        self.write_empty_row_with_styles(["default"] + ["border_left_right"] * len(evaluations_with_results))

    # pylint: disable=arguments-differ
    def export_impl(
        self,
        semesters,
        selection_list,
        include_not_enough_voters=False,
        include_unpublished=False,
        contributor=None,
        verbose_heading=True,
    ):
        # We want to throw early here, since workbook.save() will throw an IndexError otherwise.
        assert len(selection_list) > 0

        for sheet_counter, (degrees, course_types) in enumerate(selection_list, 1):
            self.cur_sheet = self.workbook.add_sheet("Sheet " + str(sheet_counter))
            self.cur_row = 0
            self.cur_col = 0

            evaluation_states = [Evaluation.State.PUBLISHED]
            if include_unpublished:
                evaluation_states.extend([Evaluation.State.EVALUATED, Evaluation.State.REVIEWED])

            evaluations_with_results, used_questionnaires, course_results_exist = self.filter_evaluations(
                semesters,
                evaluation_states,
                degrees,
                course_types,
                contributor,
                include_not_enough_voters,
            )

            self.write_headings_and_evaluation_info(
                evaluations_with_results, semesters, contributor, degrees, course_types, verbose_heading
            )

            for questionnaire in used_questionnaires:
                self.write_questionnaire(questionnaire, evaluations_with_results, contributor)

            self.write_overall_results(evaluations_with_results, course_results_exist)


# See method definition.
ResultsExporter.init_grade_styles()


class TextAnswerExporter(ExcelExporter):
    class InputData:
        def __init__(self, contribution_results):
            self.questionnaires = defaultdict(list)

            for contribution_result in contribution_results:
                contributor_name = (
                    contribution_result.contributor.full_name if contribution_result.contributor is not None else ""
                )
                for questionnaire_result in contribution_result.questionnaire_results:
                    for result in questionnaire_result.question_results:
                        q_type = result.question.questionnaire.type
                        answers = [answer.answer for answer in result.answers]
                        self.questionnaires[q_type].append((contributor_name, result.question, answers))

    default_sheet_name = _("Text Answers")

    def __init__(self, evaluation_name, semester_name, responsibles, results, contributor_name):
        super().__init__()
        self.evaluation_name = evaluation_name
        self.semester_name = semester_name
        self.responsibles = responsibles
        assert isinstance(results, TextAnswerExporter.InputData)
        self.results = results
        self.contributor_name = contributor_name

    def export_impl(self):  # pylint: disable=arguments-differ
        self.cur_sheet.col(0).width = 10000
        self.cur_sheet.col(1).width = 40000

        self.write_row([self.evaluation_name])
        self.write_row([self.semester_name])
        self.write_row([self.responsibles])

        if self.contributor_name is not None:
            self.write_row([_("Export for {}").format(self.contributor_name)])

        for questionnaire_type in Questionnaire.Type.values:
            # The first line of every questionnaire type should have an overline.
            line_styles = chain(["border_top"], repeat("default"))
            for contributor_name, question, answers in self.results.questionnaires[questionnaire_type]:
                # The first line of every question should contain the
                # question text and contributor name (if present).
                question_title = (f"{contributor_name}: " if contributor_name else "") + question.text
                first_col = chain([question_title], repeat(""))

                for answer, first_cell, line_style in zip(answers, first_col, line_styles):
                    self.write_row([first_cell, answer], style=line_style)
