from io import BytesIO

import xlrd
from django.utils import translation
from model_bakery import baker

from evap.contributor.views import export_contributor_results
from evap.evaluation.models import (
    Contribution,
    Course,
    CourseType,
    Evaluation,
    Program,
    Question,
    Questionnaire,
    QuestionType,
    Semester,
    TextAnswer,
    UserProfile,
)
from evap.evaluation.tests.tools import TestCase, make_rating_answer_counters
from evap.results.exporters import ResultsExporter, TextAnswerExporter
from evap.results.tools import cache_results, get_results
from evap.results.views import filter_text_answers


class TestExporters(TestCase):
    def test_grade_color_calculation(self):
        exporter = ResultsExporter()
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
        program = baker.make(Program)
        evaluation = baker.make(
            Evaluation,
            course__programs=[program],
            state=Evaluation.State.PUBLISHED,
            _participant_count=2,
            _voter_count=2,
        )

        questionnaire_1 = baker.make(Questionnaire, order=1, type=Questionnaire.Type.TOP)
        questionnaire_2 = baker.make(Questionnaire, order=4, type=Questionnaire.Type.TOP)
        questionnaire_3 = baker.make(Questionnaire, order=1, type=Questionnaire.Type.BOTTOM)
        questionnaire_4 = baker.make(Questionnaire, order=4, type=Questionnaire.Type.BOTTOM)

        question_1 = baker.make(Question, type=QuestionType.POSITIVE_LIKERT, questionnaire=questionnaire_1)
        question_2 = baker.make(Question, type=QuestionType.POSITIVE_LIKERT, questionnaire=questionnaire_2)
        question_3 = baker.make(Question, type=QuestionType.POSITIVE_LIKERT, questionnaire=questionnaire_3)
        question_4 = baker.make(Question, type=QuestionType.POSITIVE_LIKERT, questionnaire=questionnaire_4)

        evaluation.general_contribution.questionnaires.set(
            [questionnaire_1, questionnaire_2, questionnaire_3, questionnaire_4]
        )

        make_rating_answer_counters(question_1, evaluation.general_contribution)
        make_rating_answer_counters(question_2, evaluation.general_contribution)
        make_rating_answer_counters(question_3, evaluation.general_contribution)
        make_rating_answer_counters(question_4, evaluation.general_contribution)

        cache_results(evaluation)

        binary_content = BytesIO()
        ResultsExporter().export(
            binary_content,
            [evaluation.course.semester],
            [([course_program.id for course_program in evaluation.course.programs.all()], [evaluation.course.type.id])],
            True,
            True,
        )
        binary_content.seek(0)
        workbook = xlrd.open_workbook(file_contents=binary_content.read())

        self.assertEqual(workbook.sheets()[0].row_values(4)[0], questionnaire_1.public_name)
        self.assertEqual(workbook.sheets()[0].row_values(5)[0], question_1.text)

        self.assertEqual(workbook.sheets()[0].row_values(7)[0], questionnaire_2.public_name)
        self.assertEqual(workbook.sheets()[0].row_values(8)[0], question_2.text)

        self.assertEqual(workbook.sheets()[0].row_values(10)[0], questionnaire_3.public_name)
        self.assertEqual(workbook.sheets()[0].row_values(11)[0], question_3.text)

        self.assertEqual(workbook.sheets()[0].row_values(13)[0], questionnaire_4.public_name)
        self.assertEqual(workbook.sheets()[0].row_values(14)[0], question_4.text)

    def test_heading_question_filtering(self):
        program = baker.make(Program)
        evaluation = baker.make(
            Evaluation,
            course__programs=[program],
            state=Evaluation.State.PUBLISHED,
            _participant_count=2,
            _voter_count=2,
        )
        contributor = baker.make(UserProfile)
        evaluation.general_contribution.questionnaires.set([baker.make(Questionnaire)])

        questionnaire = baker.make(Questionnaire)
        baker.make(Question, type=QuestionType.HEADING, questionnaire=questionnaire, order=0)
        heading_question = baker.make(Question, type=QuestionType.HEADING, questionnaire=questionnaire, order=1)
        likert_question = baker.make(Question, type=QuestionType.POSITIVE_LIKERT, questionnaire=questionnaire, order=2)
        baker.make(Question, type=QuestionType.HEADING, questionnaire=questionnaire, order=3)

        contribution = baker.make(
            Contribution, evaluation=evaluation, questionnaires=[questionnaire], contributor=contributor
        )
        make_rating_answer_counters(likert_question, contribution)

        cache_results(evaluation)

        binary_content = BytesIO()
        ResultsExporter().export(
            binary_content,
            [evaluation.course.semester],
            [([course_program.id for course_program in evaluation.course.programs.all()], [evaluation.course.type.id])],
            True,
            True,
        )
        binary_content.seek(0)
        workbook = xlrd.open_workbook(file_contents=binary_content.read())

        self.assertEqual(workbook.sheets()[0].row_values(4)[0], questionnaire.public_name)
        self.assertEqual(workbook.sheets()[0].row_values(5)[0], heading_question.text)
        self.assertEqual(workbook.sheets()[0].row_values(6)[0], likert_question.text)
        self.assertEqual(workbook.sheets()[0].row_values(7)[0], "")

    def test_view_excel_file_sorted(self):
        semester = baker.make(Semester)
        course_type = baker.make(CourseType)
        program = baker.make(Program)
        evaluation1 = baker.make(
            Evaluation,
            state=Evaluation.State.PUBLISHED,
            course=baker.make(
                Course, programs=[program], type=course_type, semester=semester, name_de="A", name_en="B"
            ),
            name_de="Evaluation1",
            name_en="Evaluation1",
        )
        evaluation2 = baker.make(
            Evaluation,
            state=Evaluation.State.PUBLISHED,
            course=baker.make(
                Course, programs=[program], type=course_type, semester=semester, name_de="B", name_en="A"
            ),
            name_de="Evaluation2",
            name_en="Evaluation2",
        )

        cache_results(evaluation1)
        cache_results(evaluation2)

        content_de = BytesIO()
        with translation.override("de"):
            ResultsExporter().export(content_de, [semester], [([program.id], [course_type.id])], True, True)

        content_en = BytesIO()
        with translation.override("en"):
            ResultsExporter().export(content_en, [semester], [([program.id], [course_type.id])], True, True)

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
        program = baker.make(Program)
        course_type_1 = baker.make(CourseType, order=1)
        course_type_2 = baker.make(CourseType, order=2)
        semester = baker.make(Semester)
        evaluation_1 = baker.make(
            Evaluation,
            course=baker.make(Course, semester=semester, programs=[program], type=course_type_1),
            state=Evaluation.State.PUBLISHED,
            _participant_count=2,
            _voter_count=2,
        )
        evaluation_2 = baker.make(
            Evaluation,
            course=baker.make(Course, semester=semester, programs=[program], type=course_type_2),
            state=Evaluation.State.PUBLISHED,
            _participant_count=2,
            _voter_count=2,
        )

        cache_results(evaluation_1)
        cache_results(evaluation_2)

        questionnaire = baker.make(Questionnaire)
        question = baker.make(Question, type=QuestionType.POSITIVE_LIKERT, questionnaire=questionnaire)

        evaluation_1.general_contribution.questionnaires.set([questionnaire])
        make_rating_answer_counters(question, evaluation_1.general_contribution)

        evaluation_2.general_contribution.questionnaires.set([questionnaire])
        make_rating_answer_counters(question, evaluation_2.general_contribution)

        binary_content = BytesIO()
        ResultsExporter().export(
            binary_content, [semester], [([program.id], [course_type_1.id, course_type_2.id])], True, True
        )
        binary_content.seek(0)
        workbook = xlrd.open_workbook(file_contents=binary_content.read())

        self.assertEqual(workbook.sheets()[0].row_values(0)[1], evaluation_1.full_name + "\n")
        self.assertEqual(workbook.sheets()[0].row_values(0)[2], evaluation_2.full_name + "\n")

        course_type_2.order = 0
        course_type_2.save()

        binary_content = BytesIO()
        ResultsExporter().export(
            binary_content, [semester], [([program.id], [course_type_1.id, course_type_2.id])], True, True
        )
        binary_content.seek(0)
        workbook = xlrd.open_workbook(file_contents=binary_content.read())

        self.assertEqual(workbook.sheets()[0].row_values(0)[1], evaluation_2.full_name + "\n")
        self.assertEqual(workbook.sheets()[0].row_values(0)[2], evaluation_1.full_name + "\n")

    def test_multiple_sheets(self):
        binary_content = BytesIO()
        semester = baker.make(Semester)
        ResultsExporter().export(binary_content, [semester], [([], []), ([], [])])

        binary_content.seek(0)
        workbook = xlrd.open_workbook(file_contents=binary_content.read())

        self.assertEqual(len(workbook.sheets()), 2)

    @staticmethod
    def get_export_sheet(semester, program, course_types, include_unpublished=True, include_not_enough_voters=True):
        binary_content = BytesIO()
        ResultsExporter().export(
            binary_content,
            [semester],
            [([program.id], course_types)],
            include_unpublished=include_unpublished,
            include_not_enough_voters=include_not_enough_voters,
        )
        binary_content.seek(0)
        workbook = xlrd.open_workbook(file_contents=binary_content.read())
        return workbook.sheets()[0]

    def test_include_unpublished(self):
        semester = baker.make(Semester)
        program = baker.make(Program)
        published_evaluation = baker.make(
            Evaluation,
            state=Evaluation.State.PUBLISHED,
            course__semester=semester,
            course__programs=[program],
            course__type__order=1,
        )
        unpublished_evaluation = baker.make(
            Evaluation,
            state=Evaluation.State.REVIEWED,
            course__semester=semester,
            course__programs=[program],
            course__type__order=2,
        )
        course_types = [published_evaluation.course.type.id, unpublished_evaluation.course.type.id]

        cache_results(published_evaluation)
        cache_results(unpublished_evaluation)

        # First, make sure that the unpublished does not appear
        sheet = self.get_export_sheet(
            include_unpublished=False, semester=semester, program=program, course_types=course_types
        )
        self.assertEqual(len(sheet.row_values(0)), 2)
        self.assertEqual(sheet.row_values(0)[1][:-1], published_evaluation.full_name)

        # Now, make sure that it appears when wanted
        sheet = self.get_export_sheet(
            include_unpublished=True, semester=semester, program=program, course_types=course_types
        )
        self.assertEqual(len(sheet.row_values(0)), 3)
        # These two should be ordered according to evaluation.course.type.order
        self.assertEqual(sheet.row_values(0)[1][:-1], published_evaluation.full_name)
        self.assertEqual(sheet.row_values(0)[2][:-1], unpublished_evaluation.full_name)

    def test_include_not_enough_voters(self):
        semester = baker.make(Semester)
        program = baker.make(Program)
        enough_voters_evaluation = baker.make(
            Evaluation,
            state=Evaluation.State.PUBLISHED,
            course__semester=semester,
            course__programs=[program],
            _voter_count=1000,
            _participant_count=1000,
        )
        not_enough_voters_evaluation = baker.make(
            Evaluation,
            state=Evaluation.State.PUBLISHED,
            course__semester=semester,
            course__programs=[program],
            _voter_count=1,
            _participant_count=1000,
        )

        cache_results(enough_voters_evaluation)
        cache_results(not_enough_voters_evaluation)

        course_types = [enough_voters_evaluation.course.type.id, not_enough_voters_evaluation.course.type.id]

        # First, make sure that the one with only a single voter does not appear
        sheet = self.get_export_sheet(semester, program, course_types, include_not_enough_voters=False)
        self.assertEqual(len(sheet.row_values(0)), 2)
        self.assertEqual(sheet.row_values(0)[1][:-1], enough_voters_evaluation.full_name)

        # Now, check with the option enabled
        sheet = self.get_export_sheet(semester, program, course_types, include_not_enough_voters=True)
        self.assertEqual(len(sheet.row_values(0)), 3)
        self.assertEqual(
            {enough_voters_evaluation.full_name, not_enough_voters_evaluation.full_name},
            {sheet.row_values(0)[1][:-1], sheet.row_values(0)[2][:-1]},
        )

    def test_no_program_or_course_type(self):
        evaluation = baker.make(Evaluation)
        with self.assertRaises(AssertionError):
            ResultsExporter().export(BytesIO(), [evaluation.course.semester], [])

    def test_exclude_single_result(self):
        program = baker.make(Program)
        evaluation = baker.make(
            Evaluation, is_single_result=True, state=Evaluation.State.PUBLISHED, course__programs=[program]
        )
        cache_results(evaluation)
        sheet = self.get_export_sheet(evaluation.course.semester, program, [evaluation.course.type.id])
        self.assertEqual(
            len(sheet.row_values(0)), 1, "There should be no column for the evaluation, only the row description"
        )

    def test_exclude_used_but_unanswered_questionnaires(self):
        program = baker.make(Program)
        evaluation = baker.make(
            Evaluation,
            _voter_count=10,
            _participant_count=10,
            state=Evaluation.State.PUBLISHED,
            course__programs=[program],
        )
        used_questionnaire = baker.make(Questionnaire)
        used_question = baker.make(Question, type=QuestionType.POSITIVE_LIKERT, questionnaire=used_questionnaire)
        unused_questionnaire = baker.make(Questionnaire)
        unused_question = baker.make(Question, type=QuestionType.POSITIVE_LIKERT, questionnaire=unused_questionnaire)

        evaluation.general_contribution.questionnaires.set([used_questionnaire, unused_questionnaire])
        make_rating_answer_counters(used_question, evaluation.general_contribution)
        cache_results(evaluation)

        sheet = self.get_export_sheet(evaluation.course.semester, program, [evaluation.course.type.id])
        self.assertEqual(sheet.row_values(4)[0], used_questionnaire.public_name)
        self.assertEqual(sheet.row_values(5)[0], used_question.text)
        self.assertNotIn(unused_questionnaire.name, sheet.col_values(0))
        self.assertNotIn(unused_question.text, sheet.col_values(0))

    def test_program_course_type_name(self):
        program = baker.make(Program, name_en="Celsius")
        course_type = baker.make(CourseType, name_en="LetsPlay")
        evaluation = baker.make(
            Evaluation, course__programs=[program], course__type=course_type, state=Evaluation.State.PUBLISHED
        )
        cache_results(evaluation)

        sheet = self.get_export_sheet(evaluation.course.semester, program, [course_type.id])
        self.assertEqual(sheet.col_values(1)[1:3], [program.name, course_type.name])

    def test_multiple_evaluations(self):
        semester = baker.make(Semester)
        program = baker.make(Program)
        evaluation1 = baker.make(
            Evaluation, course__semester=semester, course__programs=[program], state=Evaluation.State.PUBLISHED
        )
        evaluation2 = baker.make(
            Evaluation, course__semester=semester, course__programs=[program], state=Evaluation.State.PUBLISHED
        )
        cache_results(evaluation1)
        cache_results(evaluation2)

        sheet = self.get_export_sheet(semester, program, [evaluation1.course.type.id, evaluation2.course.type.id])

        self.assertEqual(set(sheet.row_values(0)[1:]), {evaluation1.full_name + "\n", evaluation2.full_name + "\n"})

    def test_correct_grades_and_bottom_numbers(self):
        program = baker.make(Program)
        evaluation = baker.make(
            Evaluation,
            _voter_count=5,
            _participant_count=10,
            course__programs=[program],
            state=Evaluation.State.PUBLISHED,
        )
        questionnaire1 = baker.make(Questionnaire, order=1)
        questionnaire2 = baker.make(Questionnaire, order=2)
        question1 = baker.make(Question, type=QuestionType.POSITIVE_LIKERT, questionnaire=questionnaire1)
        question2 = baker.make(Question, type=QuestionType.POSITIVE_LIKERT, questionnaire=questionnaire2)

        make_rating_answer_counters(question1, evaluation.general_contribution, [1, 0, 1, 0, 0])
        make_rating_answer_counters(question2, evaluation.general_contribution, [0, 1, 0, 1, 0])

        evaluation.general_contribution.questionnaires.set([questionnaire1, questionnaire2])
        cache_results(evaluation)

        sheet = self.get_export_sheet(evaluation.course.semester, program, [evaluation.course.type.id])

        self.assertEqual(sheet.row_values(5)[1], 2.0)  # question 1 average
        self.assertEqual(sheet.row_values(8)[1], 3.0)  # question 2 average
        self.assertEqual(sheet.row_values(10)[1], 2.5)  # Average grade
        self.assertEqual(sheet.row_values(11)[1], "5/10")  # Voters / Participants
        self.assertEqual(sheet.row_values(12)[1], "50%")  # Voter percentage

    def test_course_grade(self):
        program = baker.make(Program)
        course = baker.make(Course, programs=[program])
        evaluations = baker.make(
            Evaluation,
            course=course,
            name_en=iter(["eval0", "eval1", "eval2"]),
            name_de=iter(["eval0", "eval1", "eval2"]),
            state=Evaluation.State.PUBLISHED,
            _voter_count=5,
            _participant_count=10,
            _quantity=3,
        )

        grades_per_eval = [[1, 1, 0, 0, 0], [0, 1, 1, 0, 0], [1, 0, 1, 0, 0]]
        expected_average = 2.0

        questionnaire = baker.make(Questionnaire)
        question = baker.make(Question, type=QuestionType.POSITIVE_LIKERT, questionnaire=questionnaire)
        for grades, e in zip(grades_per_eval, evaluations, strict=True):
            make_rating_answer_counters(question, e.general_contribution, grades)
            e.general_contribution.questionnaires.set([questionnaire])
        for evaluation in evaluations:
            cache_results(evaluation)

        sheet = self.get_export_sheet(course.semester, program, [course.type.id])
        self.assertEqual(sheet.row_values(12)[1], expected_average)
        self.assertEqual(sheet.row_values(12)[2], expected_average)
        self.assertEqual(sheet.row_values(12)[3], expected_average)

    def test_yes_no_question_result(self):
        program = baker.make(Program)
        evaluation = baker.make(
            Evaluation,
            _voter_count=6,
            _participant_count=10,
            course__programs=[program],
            state=Evaluation.State.PUBLISHED,
        )
        questionnaire = baker.make(Questionnaire)
        question = baker.make(Question, type=QuestionType.POSITIVE_YES_NO, questionnaire=questionnaire)

        make_rating_answer_counters(question, evaluation.general_contribution, [4, 2])

        evaluation.general_contribution.questionnaires.set([questionnaire])
        cache_results(evaluation)

        sheet = self.get_export_sheet(evaluation.course.semester, program, [evaluation.course.type.id])
        self.assertEqual(sheet.row_values(5)[0], question.text)
        self.assertEqual(sheet.row_values(5)[1], "67%")

    def test_contributor_result_export(self):
        program = baker.make(Program)
        contributor = baker.make(UserProfile)
        other_contributor = baker.make(UserProfile)
        evaluation_1 = baker.make(
            Evaluation,
            course=baker.make(Course, programs=[program], responsibles=[contributor]),
            state=Evaluation.State.PUBLISHED,
            _participant_count=10,
            _voter_count=1,
        )
        evaluation_2 = baker.make(
            Evaluation,
            course=baker.make(Course, programs=[program], responsibles=[other_contributor]),
            state=Evaluation.State.PUBLISHED,
            _participant_count=2,
            _voter_count=2,
        )
        contribution = baker.make(Contribution, evaluation=evaluation_2, contributor=contributor)
        other_contribution = baker.make(Contribution, evaluation=evaluation_2, contributor=other_contributor)

        general_questionnaire = baker.make(Questionnaire, type=Questionnaire.Type.TOP)
        contributor_questionnaire = baker.make(Questionnaire, type=Questionnaire.Type.CONTRIBUTOR)
        general_question = baker.make(Question, type=QuestionType.POSITIVE_LIKERT, questionnaire=general_questionnaire)
        contributor_question = baker.make(
            Question, type=QuestionType.POSITIVE_LIKERT, questionnaire=contributor_questionnaire
        )

        evaluation_1.general_contribution.questionnaires.set([general_questionnaire])
        make_rating_answer_counters(general_question, evaluation_1.general_contribution, [2, 0, 0, 0, 0])
        evaluation_2.general_contribution.questionnaires.set([general_questionnaire])
        make_rating_answer_counters(general_question, evaluation_2.general_contribution, [0, 0, 0, 2, 0])

        contribution.questionnaires.set([contributor_questionnaire])
        make_rating_answer_counters(contributor_question, contribution, [0, 0, 2, 0, 0])
        other_contribution.questionnaires.set([contributor_questionnaire])
        make_rating_answer_counters(contributor_question, other_contribution, [0, 2, 0, 0, 0])

        cache_results(evaluation_1)
        cache_results(evaluation_2)

        binary_content = export_contributor_results(contributor).content
        workbook = xlrd.open_workbook(file_contents=binary_content)

        self.assertEqual(
            workbook.sheets()[0].row_values(0)[1],
            f"{evaluation_1.full_name}\n{evaluation_1.course.semester.name}\n{contributor.full_name}",
        )
        self.assertEqual(
            workbook.sheets()[0].row_values(0)[2],
            f"{evaluation_2.full_name}\n{evaluation_2.course.semester.name}\n{other_contributor.full_name}",
        )
        self.assertEqual(workbook.sheets()[0].row_values(4)[0], general_questionnaire.public_name)
        self.assertEqual(workbook.sheets()[0].row_values(5)[0], general_question.text)
        self.assertEqual(workbook.sheets()[0].row_values(5)[2], 4.0)
        self.assertEqual(
            workbook.sheets()[0].row_values(7)[0],
            f"{contributor_questionnaire.public_name} ({contributor.full_name})",
        )
        self.assertEqual(workbook.sheets()[0].row_values(8)[0], contributor_question.text)
        self.assertEqual(workbook.sheets()[0].row_values(8)[2], 3.0)
        self.assertEqual(workbook.sheets()[0].row_values(10)[0], "Overall Average Grade")
        self.assertEqual(workbook.sheets()[0].row_values(10)[2], 3.25)

    def test_text_answer_export(self):
        evaluation = baker.make(Evaluation, state=Evaluation.State.PUBLISHED, can_publish_text_results=True)
        questions = baker.make(
            Question,
            questionnaire__type=iter(Questionnaire.Type.values),
            type=QuestionType.TEXT,
            _quantity=len(Questionnaire.Type.values),
            _bulk_create=True,
            allows_additional_textanswers=False,
        )

        baker.make(
            TextAnswer,
            question=iter(questions[idx] for idx in [0, 1, 2, 2, 0]),
            contribution__evaluation=evaluation,
            contribution__questionnaires=iter(questions[idx].questionnaire for idx in [0, 1, 2, 2, 0]),
            review_decision=TextAnswer.ReviewDecision.PUBLIC,
            _quantity=5,
        )

        cache_results(evaluation)
        evaluation_result = get_results(evaluation)
        filter_text_answers(evaluation_result)

        results = TextAnswerExporter.InputData(evaluation_result.contribution_results)

        binary_content = BytesIO()
        TextAnswerExporter(
            evaluation.name, evaluation.course.semester.name, evaluation.course.responsibles_names, results, None
        ).export(binary_content)
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
