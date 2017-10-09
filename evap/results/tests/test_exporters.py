import xlrd
from io import BytesIO
from model_mommy import mommy
from django.test import TestCase

from evap.evaluation.models import Semester, Course, Contribution, UserProfile, Question, Questionnaire, RatingAnswerCounter
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

    def test_heading_question_filtering(self):
        course = mommy.make(Course, state='published')
        contributor = mommy.make(UserProfile)
        questionnaire = mommy.make(Questionnaire)

        mommy.make(Question, type="H", questionnaire=questionnaire, order=0)
        heading_question = mommy.make(Question, type="H", questionnaire=questionnaire, order=1)
        likert_question = mommy.make(Question, type="L", questionnaire=questionnaire, order=2)
        mommy.make(Question, type="H", questionnaire=questionnaire, order=3)

        contribution = mommy.make(Contribution, course=course, questionnaires=[questionnaire], contributor=contributor)
        mommy.make(RatingAnswerCounter, question=likert_question, contribution=contribution, answer=3, count=100)

        binary_content = BytesIO()
        ExcelExporter(course.semester).export(binary_content, [[course.type.id]], True, True)
        binary_content.seek(0)
        workbook = xlrd.open_workbook(file_contents=binary_content.read())

        self.assertEqual(workbook.sheets()[0].row_values(2)[0], questionnaire.name)
        self.assertEqual(workbook.sheets()[0].row_values(3)[0], heading_question.text)
        self.assertEqual(workbook.sheets()[0].row_values(4)[0], likert_question.text)
        self.assertEqual(workbook.sheets()[0].row_values(5)[0], "")
