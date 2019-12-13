import xlrd
from io import BytesIO
from model_bakery import baker
from django.test import TestCase
from django.utils import translation

from evap.evaluation.models import (Contribution, Course, CourseType, Degree, Evaluation, Question, Questionnaire,
                                    RatingAnswerCounter, Semester, UserProfile)
from evap.results.exporters import ExcelExporter


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

        questionnaire_1 = baker.make(Questionnaire, order=1, type=Questionnaire.TOP)
        questionnaire_2 = baker.make(Questionnaire, order=4, type=Questionnaire.TOP)
        questionnaire_3 = baker.make(Questionnaire, order=1, type=Questionnaire.BOTTOM)
        questionnaire_4 = baker.make(Questionnaire, order=4, type=Questionnaire.BOTTOM)

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
