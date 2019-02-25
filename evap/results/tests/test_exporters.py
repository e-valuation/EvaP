import xlrd
from io import BytesIO
from model_mommy import mommy
from django.test import TestCase
from django.utils import translation

from evap.evaluation.models import (Contribution, Course, CourseType, Evaluation, Question, Questionnaire,
                                    RatingAnswerCounter, Semester, UserProfile)
from evap.results.exporters import ExcelExporter


class TestExporters(TestCase):
    def test_grade_color_calculation(self):
        exporter = ExcelExporter(Semester())
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
        evaluation = mommy.make(Evaluation, state='published', _participant_count=2, _voter_count=2)

        questionnaire_1 = mommy.make(Questionnaire, order=1, type=Questionnaire.TOP)
        questionnaire_2 = mommy.make(Questionnaire, order=4, type=Questionnaire.TOP)
        questionnaire_3 = mommy.make(Questionnaire, order=1, type=Questionnaire.BOTTOM)
        questionnaire_4 = mommy.make(Questionnaire, order=4, type=Questionnaire.BOTTOM)

        question_1 = mommy.make(Question, type=Question.LIKERT, questionnaire=questionnaire_1)
        question_2 = mommy.make(Question, type=Question.LIKERT, questionnaire=questionnaire_2)
        question_3 = mommy.make(Question, type=Question.LIKERT, questionnaire=questionnaire_3)
        question_4 = mommy.make(Question, type=Question.LIKERT, questionnaire=questionnaire_4)

        evaluation.general_contribution.questionnaires.set([questionnaire_1, questionnaire_2, questionnaire_3, questionnaire_4])

        mommy.make(RatingAnswerCounter, question=question_1, contribution=evaluation.general_contribution, answer=3, count=100)
        mommy.make(RatingAnswerCounter, question=question_2, contribution=evaluation.general_contribution, answer=3, count=100)
        mommy.make(RatingAnswerCounter, question=question_3, contribution=evaluation.general_contribution, answer=3, count=100)
        mommy.make(RatingAnswerCounter, question=question_4, contribution=evaluation.general_contribution, answer=3, count=100)

        binary_content = BytesIO()
        ExcelExporter(evaluation.course.semester).export(binary_content, [[evaluation.course.type.id]], True, True)
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
        evaluation = mommy.make(Evaluation, state='published', _participant_count=2, _voter_count=2)
        contributor = mommy.make(UserProfile)
        evaluation.general_contribution.questionnaires.set([mommy.make(Questionnaire)])

        questionnaire = mommy.make(Questionnaire)
        mommy.make(Question, type=Question.HEADING, questionnaire=questionnaire, order=0)
        heading_question = mommy.make(Question, type=Question.HEADING, questionnaire=questionnaire, order=1)
        likert_question = mommy.make(Question, type=Question.LIKERT, questionnaire=questionnaire, order=2)
        mommy.make(Question, type=Question.HEADING, questionnaire=questionnaire, order=3)

        contribution = mommy.make(Contribution, evaluation=evaluation, questionnaires=[questionnaire], contributor=contributor)
        mommy.make(RatingAnswerCounter, question=likert_question, contribution=contribution, answer=3, count=100)

        binary_content = BytesIO()
        ExcelExporter(evaluation.course.semester).export(binary_content, [[evaluation.course.type.id]], True, True)
        binary_content.seek(0)
        workbook = xlrd.open_workbook(file_contents=binary_content.read())

        self.assertEqual(workbook.sheets()[0].row_values(4)[0], questionnaire.name)
        self.assertEqual(workbook.sheets()[0].row_values(5)[0], heading_question.text)
        self.assertEqual(workbook.sheets()[0].row_values(6)[0], likert_question.text)
        self.assertEqual(workbook.sheets()[0].row_values(7)[0], "")

    def test_view_excel_file_sorted(self):
        semester = mommy.make(Semester)
        course_type = mommy.make(CourseType)
        mommy.make(Evaluation, state='published', course=mommy.make(Course, type=course_type, semester=semester, name_de="A", name_en="B"),
                   name_de='Evaluation1', name_en='Evaluation1')

        mommy.make(Evaluation, state='published', course=mommy.make(Course, type=course_type, semester=semester, name_de="B", name_en="A"),
                   name_de='Evaluation2', name_en='Evaluation2')

        content_de = BytesIO()
        with translation.override("de"):
            ExcelExporter(semester).export(content_de, [[course_type.id]], True, True)

        content_en = BytesIO()
        with translation.override("en"):
            ExcelExporter(semester).export(content_en, [[course_type.id]], True, True)

        content_de.seek(0)
        content_en.seek(0)

        # Load responses as Excel files and check for correct sorting
        workbook = xlrd.open_workbook(file_contents=content_de.read())
        self.assertEqual(workbook.sheets()[0].row_values(0)[1], "A – Evaluation1")
        self.assertEqual(workbook.sheets()[0].row_values(0)[2], "B – Evaluation2")

        workbook = xlrd.open_workbook(file_contents=content_en.read())
        self.assertEqual(workbook.sheets()[0].row_values(0)[1], "A – Evaluation2")
        self.assertEqual(workbook.sheets()[0].row_values(0)[2], "B – Evaluation1")

    def test_course_type_ordering(self):
        course_type_1 = mommy.make(CourseType, order=1)
        course_type_2 = mommy.make(CourseType, order=2)
        semester = mommy.make(Semester)
        evaluation_1 = mommy.make(Evaluation, course=mommy.make(Course, semester=semester, type=course_type_1), state='published', _participant_count=2, _voter_count=2)
        evaluation_2 = mommy.make(Evaluation, course=mommy.make(Course, semester=semester, type=course_type_2), state='published', _participant_count=2, _voter_count=2)

        questionnaire = mommy.make(Questionnaire)
        question = mommy.make(Question, type=Question.LIKERT, questionnaire=questionnaire)

        evaluation_1.general_contribution.questionnaires.set([questionnaire])
        mommy.make(RatingAnswerCounter, question=question, contribution=evaluation_1.general_contribution, answer=3, count=2)

        evaluation_2.general_contribution.questionnaires.set([questionnaire])
        mommy.make(RatingAnswerCounter, question=question, contribution=evaluation_2.general_contribution, answer=3, count=2)

        binary_content = BytesIO()
        ExcelExporter(semester).export(binary_content, [[course_type_1.id, course_type_2.id]], True, True)
        binary_content.seek(0)
        workbook = xlrd.open_workbook(file_contents=binary_content.read())

        self.assertEqual(workbook.sheets()[0].row_values(0)[1], evaluation_1.full_name)
        self.assertEqual(workbook.sheets()[0].row_values(0)[2], evaluation_2.full_name)

        course_type_2.order = 0
        course_type_2.save()

        binary_content = BytesIO()
        ExcelExporter(semester).export(binary_content, [[course_type_1.id, course_type_2.id]], True, True)
        binary_content.seek(0)
        workbook = xlrd.open_workbook(file_contents=binary_content.read())

        self.assertEqual(workbook.sheets()[0].row_values(0)[1], evaluation_2.full_name)
        self.assertEqual(workbook.sheets()[0].row_values(0)[2], evaluation_1.full_name)
