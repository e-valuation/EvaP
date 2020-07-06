from io import BytesIO

from model_bakery import baker
from django.test import TestCase
from django.utils import translation

import xlrd

from evap.contributor.views import export_contributor_results
from evap.evaluation.models import (Contribution, Course, CourseType, Degree, Evaluation, Question, Questionnaire,
                                    RatingAnswerCounter, Semester, UserProfile, TextAnswer)
from evap.results.exporters import ExcelExporter, TextAnswerExcelExporter
from evap.results.tools import collect_results
from evap.results.views import filter_text_answers


class TestExporters(TestCase):
    def test_grade_color_calculation(self):
        exporter = ExcelExporter()
        self.assertEqual(exporter.STEP, 0.2)
        self.assertEqual(exporter.normalize_number(1.94999999999), 1.8)
        # self.assertEqual(exporter.normalize_number(1.95), 2.0)  # floats ftw
        self.assertEqual(exporter.normalize_number(1.95000000001), 2.0)
        self.assertEqual(exporter.normalize_number(1.99999999999), 2.0)
        self.assertEqual(exporter.normalize_number(2.0), 2.0)
        self.assertEqual(exporter.normalize_number(2.00000000001), 2.0)
        self.assertEqual(exporter.normalize_number(2.1), 2.0)
        self.assertEqual(exporter.normalize_number(2.149999999999), 2.0)
        # self.assertEqual(exporter.normalize_number(2.15), 2.2)  # floats again
        self.assertEqual(exporter.normalize_number(2.150000000001), 2.2)
        self.assertEqual(exporter.normalize_number(2.8), 2.8)

    def test_questionnaire_ordering(self):
        degree = baker.make(Degree)
        evaluation = baker.make(
            Evaluation,
            course=baker.make(Course, degrees=[degree]),
            state='published',
            _participant_count=2,
            _voter_count=2
        )

        questionnaire_1 = baker.make(Questionnaire, order=1, type=Questionnaire.Type.TOP)
        questionnaire_2 = baker.make(Questionnaire, order=4, type=Questionnaire.Type.TOP)
        questionnaire_3 = baker.make(Questionnaire, order=1, type=Questionnaire.Type.BOTTOM)
        questionnaire_4 = baker.make(Questionnaire, order=4, type=Questionnaire.Type.BOTTOM)

        question_1 = baker.make(Question, type=Question.LIKERT, questionnaire=questionnaire_1)
        question_2 = baker.make(Question, type=Question.LIKERT, questionnaire=questionnaire_2)
        question_3 = baker.make(Question, type=Question.LIKERT, questionnaire=questionnaire_3)
        question_4 = baker.make(Question, type=Question.LIKERT, questionnaire=questionnaire_4)

        evaluation.general_contribution.questionnaires.set([questionnaire_1, questionnaire_2, questionnaire_3, questionnaire_4])

        baker.make(RatingAnswerCounter, question=question_1, contribution=evaluation.general_contribution, answer=3, count=100)
        baker.make(RatingAnswerCounter, question=question_2, contribution=evaluation.general_contribution, answer=3, count=100)
        baker.make(RatingAnswerCounter, question=question_3, contribution=evaluation.general_contribution, answer=3, count=100)
        baker.make(RatingAnswerCounter, question=question_4, contribution=evaluation.general_contribution, answer=3, count=100)

        binary_content = BytesIO()
        ExcelExporter().export(
            binary_content,
            [evaluation.course.semester],
            [([course_degree.id for course_degree in evaluation.course.degrees.all()], [evaluation.course.type.id])],
            True,
            True
        )
        binary_content.seek(0)
        workbook = xlrd.open_workbook(file_contents=binary_content.read())

        self.assertEqual(workbook.sheets()[0].row_values(4)[0], questionnaire_1.name)
        self.assertEqual(workbook.sheets()[0].row_values(5)[0], question_1.text)

        self.assertEqual(workbook.sheets()[0].row_values(7)[0], questionnaire_2.name)
        self.assertEqual(workbook.sheets()[0].row_values(8)[0], question_2.text)

        self.assertEqual(workbook.sheets()[0].row_values(10)[0], questionnaire_3.name)
        self.assertEqual(workbook.sheets()[0].row_values(11)[0], question_3.text)

        self.assertEqual(workbook.sheets()[0].row_values(13)[0], questionnaire_4.name)
        self.assertEqual(workbook.sheets()[0].row_values(14)[0], question_4.text)

    def test_heading_question_filtering(self):
        degree = baker.make(Degree)
        evaluation = baker.make(
            Evaluation,
            course=baker.make(Course, degrees=[degree]),
            state='published',
            _participant_count=2,
            _voter_count=2
        )
        contributor = baker.make(UserProfile)
        evaluation.general_contribution.questionnaires.set([baker.make(Questionnaire)])

        questionnaire = baker.make(Questionnaire)
        baker.make(Question, type=Question.HEADING, questionnaire=questionnaire, order=0)
        heading_question = baker.make(Question, type=Question.HEADING, questionnaire=questionnaire, order=1)
        likert_question = baker.make(Question, type=Question.LIKERT, questionnaire=questionnaire, order=2)
        baker.make(Question, type=Question.HEADING, questionnaire=questionnaire, order=3)

        contribution = baker.make(Contribution, evaluation=evaluation, questionnaires=[questionnaire], contributor=contributor)
        baker.make(RatingAnswerCounter, question=likert_question, contribution=contribution, answer=3, count=100)

        binary_content = BytesIO()
        ExcelExporter().export(
            binary_content,
            [evaluation.course.semester],
            [([course_degree.id for course_degree in evaluation.course.degrees.all()], [evaluation.course.type.id])],
            True,
            True
        )
        binary_content.seek(0)
        workbook = xlrd.open_workbook(file_contents=binary_content.read())

        self.assertEqual(workbook.sheets()[0].row_values(4)[0], questionnaire.name)
        self.assertEqual(workbook.sheets()[0].row_values(5)[0], heading_question.text)
        self.assertEqual(workbook.sheets()[0].row_values(6)[0], likert_question.text)
        self.assertEqual(workbook.sheets()[0].row_values(7)[0], "")

    def test_view_excel_file_sorted(self):
        semester = baker.make(Semester)
        course_type = baker.make(CourseType)
        degree = baker.make(Degree)
        baker.make(
            Evaluation,
            state='published',
            course=baker.make(Course, degrees=[degree], type=course_type, semester=semester, name_de="A", name_en="B"),
            name_de='Evaluation1',
            name_en='Evaluation1'
        )
        baker.make(
            Evaluation,
            state='published',
            course=baker.make(Course, degrees=[degree], type=course_type, semester=semester, name_de="B", name_en="A"),
            name_de='Evaluation2',
            name_en='Evaluation2'
        )

        content_de = BytesIO()
        with translation.override("de"):
            ExcelExporter().export(content_de, [semester], [([degree.id], [course_type.id])], True, True)

        content_en = BytesIO()
        with translation.override("en"):
            ExcelExporter().export(content_en, [semester], [([degree.id], [course_type.id])], True, True)

        content_de.seek(0)
        content_en.seek(0)

        # Load responses as Excel files and check for correct sorting
        workbook = xlrd.open_workbook(file_contents=content_de.read())
        self.assertEqual(workbook.sheets()[0].row_values(0)[1], "A – Evaluation1\n")
        self.assertEqual(workbook.sheets()[0].row_values(0)[2], "B – Evaluation2\n")

        workbook = xlrd.open_workbook(file_contents=content_en.read())
        self.assertEqual(workbook.sheets()[0].row_values(0)[1], "A – Evaluation2\n")
        self.assertEqual(workbook.sheets()[0].row_values(0)[2], "B – Evaluation1\n")

    def test_course_type_ordering(self):
        degree = baker.make(Degree)
        course_type_1 = baker.make(CourseType, order=1)
        course_type_2 = baker.make(CourseType, order=2)
        semester = baker.make(Semester)
        evaluation_1 = baker.make(Evaluation,
            course=baker.make(Course, semester=semester, degrees=[degree], type=course_type_1),
            state='published',
            _participant_count=2,
            _voter_count=2
        )
        evaluation_2 = baker.make(Evaluation,
            course=baker.make(Course, semester=semester, degrees=[degree], type=course_type_2),
            state='published',
            _participant_count=2,
            _voter_count=2
        )

        questionnaire = baker.make(Questionnaire)
        question = baker.make(Question, type=Question.LIKERT, questionnaire=questionnaire)

        evaluation_1.general_contribution.questionnaires.set([questionnaire])
        baker.make(RatingAnswerCounter, question=question, contribution=evaluation_1.general_contribution, answer=3, count=2)

        evaluation_2.general_contribution.questionnaires.set([questionnaire])
        baker.make(RatingAnswerCounter, question=question, contribution=evaluation_2.general_contribution, answer=3, count=2)

        binary_content = BytesIO()
        ExcelExporter().export(binary_content, [semester], [([degree.id], [course_type_1.id, course_type_2.id])], True, True)
        binary_content.seek(0)
        workbook = xlrd.open_workbook(file_contents=binary_content.read())

        self.assertEqual(workbook.sheets()[0].row_values(0)[1], evaluation_1.full_name + "\n")
        self.assertEqual(workbook.sheets()[0].row_values(0)[2], evaluation_2.full_name + "\n")

        course_type_2.order = 0
        course_type_2.save()

        binary_content = BytesIO()
        ExcelExporter().export(binary_content, [semester], [([degree.id], [course_type_1.id, course_type_2.id])], True, True)
        binary_content.seek(0)
        workbook = xlrd.open_workbook(file_contents=binary_content.read())

        self.assertEqual(workbook.sheets()[0].row_values(0)[1], evaluation_2.full_name + "\n")
        self.assertEqual(workbook.sheets()[0].row_values(0)[2], evaluation_1.full_name + "\n")

    def test_multiple_sheets(self):
        binary_content = BytesIO()
        semester = baker.make(Semester)
        ExcelExporter().export(binary_content, [semester], [([], []), ([], [])])

        binary_content.seek(0)
        workbook = xlrd.open_workbook(file_contents=binary_content.read())

        self.assertEqual(len(workbook.sheets()), 2)

    @staticmethod
    def get_export_sheet(semester, degree, course_types, include_unpublished=True, include_not_enough_voters=True):
        binary_content = BytesIO()
        ExcelExporter().export(
            binary_content,
            [semester],
            [([degree.id], course_types)],
            include_unpublished=include_unpublished,
            include_not_enough_voters=include_not_enough_voters,
        )
        binary_content.seek(0)
        workbook = xlrd.open_workbook(file_contents=binary_content.read())
        return workbook.sheets()[0]

    def test_include_unpublished(self):
        semester = baker.make(Semester)
        degree = baker.make(Degree)
        published_evaluation = baker.make(Evaluation, state="published", course__semester=semester, course__degrees=[degree], course__type__order=1)
        unpublished_evaluation = baker.make(Evaluation, state="reviewed", course__semester=semester, course__degrees=[degree], course__type__order=2)
        course_types = [published_evaluation.course.type.id, unpublished_evaluation.course.type.id]

        # First, make sure that the unpublished does not appear
        sheet = self.get_export_sheet(include_unpublished=False, semester=semester, degree=degree, course_types=course_types)
        self.assertEqual(len(sheet.row_values(0)), 2)
        self.assertEqual(
            sheet.row_values(0)[1][:-1],
            published_evaluation.full_name
        )

        # Now, make sure that it appears when wanted
        sheet = self.get_export_sheet(include_unpublished=True, semester=semester, degree=degree, course_types=course_types)
        self.assertEqual(len(sheet.row_values(0)), 3)
        # These two should be ordered according to evaluation.course.type.order
        self.assertEqual(sheet.row_values(0)[1][:-1], published_evaluation.full_name)
        self.assertEqual(sheet.row_values(0)[2][:-1], unpublished_evaluation.full_name)

    def test_include_not_enough_voters(self):
        semester = baker.make(Semester)
        degree = baker.make(Degree)
        enough_voters_evaluation = baker.make(
            Evaluation,
            state="published",
            course__semester=semester,
            course__degrees=[degree],
            _voter_count=1000,
            _participant_count=1000,
        )
        not_enough_voters_evaluation = baker.make(
            Evaluation,
            state="published",
            course__semester=semester,
            course__degrees=[degree],
            _voter_count=1,
            _participant_count=1000,
        )

        course_types = [enough_voters_evaluation.course.type.id, not_enough_voters_evaluation.course.type.id]

        # First, make sure that the one with only a single voter does not appear
        sheet = self.get_export_sheet(semester, degree, course_types, include_not_enough_voters=False)
        self.assertEqual(len(sheet.row_values(0)), 2)
        self.assertEqual(
            sheet.row_values(0)[1][:-1],
            enough_voters_evaluation.full_name
        )

        # Now, check with the option enabled
        sheet = self.get_export_sheet(semester, degree, course_types, include_not_enough_voters=True)
        self.assertEqual(len(sheet.row_values(0)), 3)
        self.assertEqual(
                {enough_voters_evaluation.full_name, not_enough_voters_evaluation.full_name},
                {sheet.row_values(0)[1][:-1], sheet.row_values(0)[2][:-1]}
        )

    def test_no_degree_or_course_type(self):
        evaluation = baker.make(Evaluation)
        with self.assertRaises(AssertionError):
            ExcelExporter().export(BytesIO(), [evaluation.course.semester], [])

    def test_exclude_single_result(self):
        degree = baker.make(Degree)
        evaluation = baker.make(Evaluation, is_single_result=True, state="published", course__degrees=[degree])
        sheet = self.get_export_sheet(evaluation.course.semester, degree, [evaluation.course.type.id])
        self.assertEqual(len(sheet.row_values(0)), 1, "There should be no column for the evaluation, only the row description")

    def test_exclude_used_but_unanswered_questionnaires(self):
        degree = baker.make(Degree)
        evaluation = baker.make(Evaluation, _voter_count=10, _participant_count=10, state="published", course__degrees=[degree])
        used_questionnaire = baker.make(Questionnaire)
        used_question = baker.make(Question, type=Question.LIKERT, questionnaire=used_questionnaire)
        unused_questionnaire = baker.make(Questionnaire)
        unused_question = baker.make(Question, type=Question.LIKERT, questionnaire=unused_questionnaire)
        baker.make(RatingAnswerCounter, question=used_question, contribution=evaluation.general_contribution, answer=3, count=10)
        evaluation.general_contribution.questionnaires.set([used_questionnaire, unused_questionnaire])

        sheet = self.get_export_sheet(evaluation.course.semester, degree, [evaluation.course.type.id])
        self.assertEqual(sheet.row_values(4)[0], used_questionnaire.name)
        self.assertEqual(sheet.row_values(5)[0], used_question.text)
        self.assertNotIn(unused_questionnaire.name, sheet.col_values(0))
        self.assertNotIn(unused_question.text, sheet.col_values(0))

    def test_degree_course_type_name(self):
        degree = baker.make(Degree, name_en="Celsius")
        course_type = baker.make(CourseType, name_en="LetsPlay")
        evaluation = baker.make(Evaluation, course__degrees=[degree], course__type=course_type, state="published")

        sheet = self.get_export_sheet(evaluation.course.semester, degree, [course_type.id])
        self.assertEqual(sheet.col_values(1)[1:3], [degree.name, course_type.name])

    def test_multiple_evaluations(self):
        semester = baker.make(Semester)
        degree = baker.make(Degree)
        evaluation1 = baker.make(Evaluation, course__semester=semester, course__degrees=[degree], state="published")
        evaluation2 = baker.make(Evaluation, course__semester=semester, course__degrees=[degree], state="published")

        sheet = self.get_export_sheet(semester, degree, [evaluation1.course.type.id, evaluation2.course.type.id])

        self.assertEqual(
            set(sheet.row_values(0)[1:]),
            set((evaluation1.full_name + "\n", evaluation2.full_name + "\n"))
        )

    def test_correct_grades_and_bottom_numbers(self):
        degree = baker.make(Degree)
        evaluation = baker.make(Evaluation, _voter_count=5, _participant_count=10, course__degrees=[degree], state="published")
        questionnaire1 = baker.make(Questionnaire, order=1)
        questionnaire2 = baker.make(Questionnaire, order=2)
        question1 = baker.make(Question, type=Question.LIKERT, questionnaire=questionnaire1)
        question2 = baker.make(Question, type=Question.LIKERT, questionnaire=questionnaire2)
        baker.make(RatingAnswerCounter, answer=1, count=1, question=question1, contribution=evaluation.general_contribution)
        baker.make(RatingAnswerCounter, answer=3, count=1, question=question1, contribution=evaluation.general_contribution)
        baker.make(RatingAnswerCounter, answer=2, count=1, question=question2, contribution=evaluation.general_contribution)
        baker.make(RatingAnswerCounter, answer=4, count=1, question=question2, contribution=evaluation.general_contribution)

        evaluation.general_contribution.questionnaires.set([questionnaire1, questionnaire2])

        sheet = self.get_export_sheet(evaluation.course.semester, degree, [evaluation.course.type.id])

        self.assertEqual(sheet.row_values(5)[1], 2.0)       # question 1 average
        self.assertEqual(sheet.row_values(8)[1], 3.0)       # question 2 average
        self.assertEqual(sheet.row_values(10)[1], 2.5)      # Average grade
        self.assertEqual(sheet.row_values(11)[1], "5/10")   # Voters / Participants
        self.assertEqual(sheet.row_values(12)[1], "50%")    # Voter percentage


    def test_contributor_result_export(self):
        degree = baker.make(Degree)
        contributor = baker.make(UserProfile)
        other_contributor = baker.make(UserProfile)
        evaluation_1 = baker.make(
            Evaluation,
            course=baker.make(Course, degrees=[degree], responsibles=[contributor]),
            state='published',
            _participant_count=10,
            _voter_count=1
        )
        evaluation_2 = baker.make(
            Evaluation,
            course=baker.make(Course, degrees=[degree], responsibles=[other_contributor]),
            state='published',
            _participant_count=2,
            _voter_count=2,
        )
        contribution = baker.make(Contribution, evaluation=evaluation_2, contributor=contributor)
        other_contribution = baker.make(Contribution, evaluation=evaluation_2, contributor=other_contributor)

        general_questionnaire = baker.make(Questionnaire, type=Questionnaire.Type.TOP)
        contributor_questionnaire = baker.make(Questionnaire, type=Questionnaire.Type.CONTRIBUTOR)
        general_question = baker.make(Question, type=Question.LIKERT, questionnaire=general_questionnaire)
        contributor_question = baker.make(Question, type=Question.LIKERT, questionnaire=contributor_questionnaire)

        evaluation_1.general_contribution.questionnaires.set([general_questionnaire])
        baker.make(RatingAnswerCounter, question=general_question, contribution=evaluation_1.general_contribution, answer=1, count=2)
        evaluation_2.general_contribution.questionnaires.set([general_questionnaire])
        baker.make(RatingAnswerCounter, question=general_question, contribution=evaluation_2.general_contribution, answer=4, count=2)

        contribution.questionnaires.set([contributor_questionnaire])
        baker.make(RatingAnswerCounter, question=contributor_question, contribution=contribution, answer=3, count=2)
        other_contribution.questionnaires.set([contributor_questionnaire])
        baker.make(RatingAnswerCounter, question=contributor_question, contribution=other_contribution, answer=2, count=2)

        binary_content = export_contributor_results(contributor).content
        workbook = xlrd.open_workbook(file_contents=binary_content)

        self.assertEqual(
            workbook.sheets()[0].row_values(0)[1],
            "{}\n{}\n{}".format(evaluation_1.full_name, evaluation_1.course.semester.name, contributor.full_name)
        )
        self.assertEqual(
            workbook.sheets()[0].row_values(0)[2],
            "{}\n{}\n{}".format(evaluation_2.full_name, evaluation_2.course.semester.name, other_contributor.full_name)
        )
        self.assertEqual(workbook.sheets()[0].row_values(4)[0], general_questionnaire.name)
        self.assertEqual(workbook.sheets()[0].row_values(5)[0], general_question.text)
        self.assertEqual(workbook.sheets()[0].row_values(5)[2], 4.0)
        self.assertEqual(workbook.sheets()[0].row_values(7)[0], "{} ({})".format(contributor_questionnaire.name, contributor.full_name))
        self.assertEqual(workbook.sheets()[0].row_values(8)[0], contributor_question.text)
        self.assertEqual(workbook.sheets()[0].row_values(8)[2], 3.0)
        self.assertEqual(workbook.sheets()[0].row_values(10)[0], "Overall Average Grade")
        self.assertEqual(workbook.sheets()[0].row_values(10)[2], 3.25)

    def test_text_answer_export(self):
        evaluation = baker.make(Evaluation, can_publish_text_results=True)
        questions = [baker.make(Question, questionnaire__type=t, type=Question.TEXT) for t in Questionnaire.Type.values]

        for idx in [0, 1, 2, 2, 0]:
            baker.make(
                TextAnswer,
                question=questions[idx],
                contribution__evaluation=evaluation,
                contribution__questionnaires=[questions[idx].questionnaire],
                state=TextAnswer.State.PUBLISHED
            )

        evaluation_result = collect_results(evaluation)
        filter_text_answers(evaluation_result)

        results = TextAnswerExcelExporter.InputData(evaluation_result.contribution_results)

        binary_content = BytesIO()
        TextAnswerExcelExporter(evaluation.name, evaluation.course.semester.name,
                                evaluation.course.responsibles_names,
                                results, None).export(binary_content)
        binary_content.seek(0)
        workbook = xlrd.open_workbook(file_contents=binary_content.read())
        sheet = workbook.sheets()[0]

        # Sheet headline
        self.assertEqual(sheet.row_values(0)[0], evaluation.name)
        self.assertEqual(sheet.row_values(1)[0], evaluation.course.semester.name)
        self.assertEqual(sheet.row_values(2)[0], evaluation.course.responsibles_names)

        # Questions are ordered by questionnaire type, answers keep their order respectively
        self.assertEqual(sheet.row_values(3)[0], questions[0].text)
        self.assertEqual(sheet.row_values(5)[0], questions[1].text)
        self.assertEqual(sheet.row_values(6)[0], questions[2].text)
