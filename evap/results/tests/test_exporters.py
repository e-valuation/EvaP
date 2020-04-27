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
