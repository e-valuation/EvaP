import xlrd
from io import BytesIO
from model_mommy import mommy
from django.test import TestCase
from django.utils import translation

from evap.evaluation.models import Semester, Course, Contribution, UserProfile, Question, Questionnaire, RatingAnswerCounter, CourseType
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
        course = mommy.make(Course, state='published')

        questionnaire_1 = mommy.make(Questionnaire, order=1, type=Questionnaire.TOP)
        questionnaire_2 = mommy.make(Questionnaire, order=4, type=Questionnaire.TOP)
        questionnaire_3 = mommy.make(Questionnaire, order=1, type=Questionnaire.BOTTOM)
        questionnaire_4 = mommy.make(Questionnaire, order=4, type=Questionnaire.BOTTOM)

        question_1 = mommy.make(Question, type="L", questionnaire=questionnaire_1)
        question_2 = mommy.make(Question, type="L", questionnaire=questionnaire_2)
        question_3 = mommy.make(Question, type="L", questionnaire=questionnaire_3)
        question_4 = mommy.make(Question, type="L", questionnaire=questionnaire_4)

        course.general_contribution.questionnaires.set([questionnaire_1, questionnaire_2, questionnaire_3, questionnaire_4])

        mommy.make(RatingAnswerCounter, question=question_1, contribution=course.general_contribution, answer=3, count=100)
        mommy.make(RatingAnswerCounter, question=question_2, contribution=course.general_contribution, answer=3, count=100)
        mommy.make(RatingAnswerCounter, question=question_3, contribution=course.general_contribution, answer=3, count=100)
        mommy.make(RatingAnswerCounter, question=question_4, contribution=course.general_contribution, answer=3, count=100)

        binary_content = BytesIO()
        ExcelExporter(course.semester).export(binary_content, [[course.type.id]], True, True)
        binary_content.seek(0)
        workbook = xlrd.open_workbook(file_contents=binary_content.read())

        self.assertEqual(workbook.sheets()[0].row_values(2)[0], questionnaire_1.name)
        self.assertEqual(workbook.sheets()[0].row_values(3)[0], question_1.text)

        self.assertEqual(workbook.sheets()[0].row_values(5)[0], questionnaire_2.name)
        self.assertEqual(workbook.sheets()[0].row_values(6)[0], question_2.text)

        self.assertEqual(workbook.sheets()[0].row_values(8)[0], questionnaire_3.name)
        self.assertEqual(workbook.sheets()[0].row_values(9)[0], question_3.text)

        self.assertEqual(workbook.sheets()[0].row_values(11)[0], questionnaire_4.name)
        self.assertEqual(workbook.sheets()[0].row_values(12)[0], question_4.text)

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

    def test_view_excel_file_sorted(self):
        semester = mommy.make(Semester)
        course_type = mommy.make(CourseType)
        course1 = mommy.make(Course, state='published', type=course_type,
                             name_de='A - Course1', name_en='B - Course1', semester=semester)

        course2 = mommy.make(Course, state='published', type=course_type,
                             name_de='B - Course2', name_en='A - Course2', semester=semester)

        mommy.make(Contribution, course=course1, responsible=True, can_edit=True, comment_visibility=Contribution.ALL_COMMENTS)
        mommy.make(Contribution, course=course2, responsible=True, can_edit=True, comment_visibility=Contribution.ALL_COMMENTS)

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
        self.assertEqual(workbook.sheets()[0].row_values(0)[1], "A - Course1")
        self.assertEqual(workbook.sheets()[0].row_values(0)[2], "B - Course2")

        workbook = xlrd.open_workbook(file_contents=content_en.read())
        self.assertEqual(workbook.sheets()[0].row_values(0)[1], "A - Course2")
        self.assertEqual(workbook.sheets()[0].row_values(0)[2], "B - Course1")
