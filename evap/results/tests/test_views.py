from unittest.mock import patch

from django.contrib.auth.models import Group
from django.test.testcases import TestCase

from django_webtest import WebTest
from model_mommy import mommy

from evap.evaluation.models import (Contribution, Course, Degree, Evaluation, Question, Questionnaire, RatingAnswerCounter,
                                    Semester, UserProfile)
from evap.evaluation.tests.tools import WebTestWith200Check, let_user_vote_for_evaluation
from evap.results.views import get_evaluations_with_prefetched_data

import random


class TestResultsView(WebTestWith200Check):
    url = '/results/'
    test_users = ['manager']

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='manager', email="manager@institution.example.com")


class TestGetEvaluationsWithPrefetchedData(TestCase):
    def test_returns_correct_participant_count(self):
        """ Regression test for #1248 """
        participants = mommy.make(UserProfile, _quantity=2)
        evaluation = mommy.make(Evaluation,
            state='published', _participant_count=2, _voter_count=2,
            participants=participants, voters=participants
        )
        participants[0].delete()
        evaluation = Evaluation.objects.get(pk=evaluation.pk)

        evaluations = get_evaluations_with_prefetched_data([evaluation])
        self.assertEqual(evaluations[0].num_participants, 2)
        self.assertEqual(evaluations[0].num_voters, 2)
        evaluations = get_evaluations_with_prefetched_data(Evaluation.objects.filter(pk=evaluation.pk))
        self.assertEqual(evaluations[0].num_participants, 2)
        self.assertEqual(evaluations[0].num_voters, 2)


class TestResultsViewContributionWarning(WebTest):
    @classmethod
    def setUpTestData(cls):
        cls.semester = mommy.make(Semester, id=3)
        mommy.make(UserProfile, username='manager', groups=[Group.objects.get(name='Manager')])
        contributor = mommy.make(UserProfile)

        # Set up an evaluation with one question but no answers
        student1 = mommy.make(UserProfile)
        student2 = mommy.make(UserProfile)
        cls.evaluation = mommy.make(Evaluation, id=21, state='published', course=mommy.make(Course, semester=cls.semester), participants=[student1, student2], voters=[student1, student2])
        questionnaire = mommy.make(Questionnaire)
        cls.evaluation.general_contribution.questionnaires.set([questionnaire])
        cls.contribution = mommy.make(Contribution, evaluation=cls.evaluation, questionnaires=[questionnaire], contributor=contributor)
        cls.likert_question = mommy.make(Question, type=Question.LIKERT, questionnaire=questionnaire, order=2)
        cls.url = '/results/semester/%s/evaluation/%s' % (cls.semester.id, cls.evaluation.id)

    def test_many_answers_evaluation_no_warning(self):
        mommy.make(RatingAnswerCounter, question=self.likert_question, contribution=self.contribution, answer=3, count=10)
        page = self.app.get(self.url, user='manager', status=200)
        self.assertNotIn("Only a few participants answered these questions.", page)

    def test_zero_answers_evaluation_no_warning(self):
        page = self.app.get(self.url, user='manager', status=200)
        self.assertNotIn("Only a few participants answered these questions.", page)

    def test_few_answers_evaluation_show_warning(self):
        mommy.make(RatingAnswerCounter, question=self.likert_question, contribution=self.contribution, answer=3, count=3)
        page = self.app.get(self.url, user='manager', status=200)
        self.assertIn("Only a few participants answered these questions.", page)


class TestResultsSemesterEvaluationDetailView(WebTestWith200Check):
    url = '/results/semester/2/evaluation/21'
    test_users = ['manager', 'contributor', 'responsible']

    @classmethod
    def setUpTestData(cls):
        cls.semester = mommy.make(Semester, id=2)

        mommy.make(UserProfile, username='manager', groups=[Group.objects.get(name='Manager')], email="manager@institution.example.com")
        contributor = mommy.make(UserProfile, username='contributor')
        responsible = mommy.make(UserProfile, username='responsible')

        # Normal evaluation with responsible and contributor.
        cls.evaluation = mommy.make(Evaluation, id=21, state='published', course=mommy.make(Course, semester=cls.semester))

        mommy.make(Contribution, evaluation=cls.evaluation, contributor=responsible, can_edit=True, textanswer_visibility=Contribution.GENERAL_TEXTANSWERS)
        cls.contribution = mommy.make(Contribution, evaluation=cls.evaluation, contributor=contributor, can_edit=True)

    def test_questionnaire_ordering(self):
        top_questionnaire = mommy.make(Questionnaire, type=Questionnaire.TOP)
        contributor_questionnaire = mommy.make(Questionnaire, type=Questionnaire.CONTRIBUTOR)
        bottom_questionnaire = mommy.make(Questionnaire, type=Questionnaire.BOTTOM)

        top_heading_question = mommy.make(Question, type=Question.HEADING, questionnaire=top_questionnaire, order=0)
        top_likert_question = mommy.make(Question, type=Question.LIKERT, questionnaire=top_questionnaire, order=1)

        contributor_likert_question = mommy.make(Question, type=Question.LIKERT, questionnaire=contributor_questionnaire)

        bottom_heading_question = mommy.make(Question, type=Question.HEADING, questionnaire=bottom_questionnaire, order=0)
        bottom_likert_question = mommy.make(Question, type=Question.LIKERT, questionnaire=bottom_questionnaire, order=1)

        self.evaluation.general_contribution.questionnaires.set([top_questionnaire, bottom_questionnaire])
        self.contribution.questionnaires.set([contributor_questionnaire])

        mommy.make(RatingAnswerCounter, question=top_likert_question, contribution=self.evaluation.general_contribution, answer=2, count=100)
        mommy.make(RatingAnswerCounter, question=contributor_likert_question, contribution=self.contribution, answer=1, count=100)
        mommy.make(RatingAnswerCounter, question=bottom_likert_question, contribution=self.evaluation.general_contribution, answer=3, count=100)

        content = self.app.get(self.url, user='manager').body.decode()

        top_heading_index = content.index(top_heading_question.text)
        top_likert_index = content.index(top_likert_question.text)
        contributor_likert_index = content.index(contributor_likert_question.text)
        bottom_heading_index = content.index(bottom_heading_question.text)
        bottom_likert_index = content.index(bottom_likert_question.text)

        self.assertTrue(top_heading_index < top_likert_index < contributor_likert_index < bottom_heading_index < bottom_likert_index)

    def test_heading_question_filtering(self):
        contributor = mommy.make(UserProfile)
        questionnaire = mommy.make(Questionnaire)

        heading_question_0 = mommy.make(Question, type=Question.HEADING, questionnaire=questionnaire, order=0)
        heading_question_1 = mommy.make(Question, type=Question.HEADING, questionnaire=questionnaire, order=1)
        likert_question = mommy.make(Question, type=Question.LIKERT, questionnaire=questionnaire, order=2)
        heading_question_2 = mommy.make(Question, type=Question.HEADING, questionnaire=questionnaire, order=3)

        contribution = mommy.make(Contribution, evaluation=self.evaluation, questionnaires=[questionnaire], contributor=contributor)
        mommy.make(RatingAnswerCounter, question=likert_question, contribution=contribution, answer=3, count=100)

        page = self.app.get(self.url, user='manager')

        self.assertNotIn(heading_question_0.text, page)
        self.assertIn(heading_question_1.text, page)
        self.assertIn(likert_question.text, page)
        self.assertNotIn(heading_question_2.text, page)

    def test_default_view_is_public(self):
        random.seed(42)  # use explicit seed to always choose the same "random" slogan
        page_without_get_parameter = self.app.get(self.url, user='manager')
        random.seed(42)
        page_with_get_parameter = self.app.get(self.url + '?view=public', user='manager')
        random.seed(42)
        page_with_random_get_parameter = self.app.get(self.url + '?view=asdf', user='manager')
        self.assertEqual(page_without_get_parameter.body, page_with_get_parameter.body)
        self.assertEqual(page_without_get_parameter.body, page_with_random_get_parameter.body)

    def test_wrong_state(self):
        evaluation = mommy.make(Evaluation, state='reviewed', course=mommy.make(Course, semester=self.semester))
        url = '/results/semester/%s/evaluation/%s' % (self.semester.id, evaluation.id)
        self.app.get(url, user='student', status=403)


class TestResultsSemesterEvaluationDetailViewFewVoters(WebTest):
    @classmethod
    def setUpTestData(cls):
        cls.semester = mommy.make(Semester, id=2)
        mommy.make(UserProfile, username='manager', groups=[Group.objects.get(name='Manager')], email="manager@institution.example.com")
        responsible = mommy.make(UserProfile, username='responsible')
        cls.student1 = mommy.make(UserProfile, username='student')
        cls.student2 = mommy.make(UserProfile)
        students = mommy.make(UserProfile, _quantity=10)
        students.extend([cls.student1, cls.student2])

        cls.evaluation = mommy.make(Evaluation, id=22, state='in_evaluation', course=mommy.make(Course, semester=cls.semester), participants=students)
        questionnaire = mommy.make(Questionnaire)
        cls.question_grade = mommy.make(Question, questionnaire=questionnaire, type=Question.GRADE)
        mommy.make(Question, questionnaire=questionnaire, type=Question.LIKERT)
        cls.evaluation.general_contribution.questionnaires.set([questionnaire])
        cls.responsible_contribution = mommy.make(Contribution, contributor=responsible, evaluation=cls.evaluation, questionnaires=[questionnaire])

    def setUp(self):
        self.evaluation = Evaluation.objects.get(pk=self.evaluation.pk)

    def helper_test_answer_visibility_one_voter(self, username, expect_page_not_visible=False):
        page = self.app.get("/results/semester/2/evaluation/22", user=username, expect_errors=expect_page_not_visible)
        if expect_page_not_visible:
            self.assertEqual(page.status_code, 403)
        else:
            self.assertEqual(page.status_code, 200)
            number_of_grade_badges = str(page).count("badge-grade")
            self.assertEqual(number_of_grade_badges, 5)  # 1 evaluation overview and 4 questions
            number_of_visible_grade_badges = str(page).count("background-color")
            self.assertEqual(number_of_visible_grade_badges, 0)
            number_of_disabled_grade_badges = str(page).count("badge-grade badge-disabled")
            self.assertEqual(number_of_disabled_grade_badges, 5)

    def helper_test_answer_visibility_two_voters(self, username):
        page = self.app.get("/results/semester/2/evaluation/22", user=username)
        number_of_grade_badges = str(page).count("badge-grade")
        self.assertEqual(number_of_grade_badges, 5)  # 1 evaluation overview and 4 questions
        number_of_visible_grade_badges = str(page).count("background-color")
        self.assertEqual(number_of_visible_grade_badges, 4)  # all but average grade in evaluation overview
        number_of_disabled_grade_badges = str(page).count("badge-grade badge-disabled")
        self.assertEqual(number_of_disabled_grade_badges, 1)

    def test_answer_visibility_one_voter(self):
        let_user_vote_for_evaluation(self.app, self.student1, self.evaluation)
        self.evaluation.evaluation_end()
        self.evaluation.review_finished()
        self.evaluation.publish()
        self.evaluation.save()
        self.assertEqual(self.evaluation.voters.count(), 1)
        self.helper_test_answer_visibility_one_voter("manager")
        self.evaluation = Evaluation.objects.get(id=self.evaluation.id)
        self.helper_test_answer_visibility_one_voter("responsible")
        self.helper_test_answer_visibility_one_voter("student", expect_page_not_visible=True)

    def test_answer_visibility_two_voters(self):
        let_user_vote_for_evaluation(self.app, self.student1, self.evaluation)
        let_user_vote_for_evaluation(self.app, self.student2, self.evaluation)
        self.evaluation.evaluation_end()
        self.evaluation.review_finished()
        self.evaluation.publish()
        self.evaluation.save()
        self.assertEqual(self.evaluation.voters.count(), 2)

        self.helper_test_answer_visibility_two_voters("manager")
        self.helper_test_answer_visibility_two_voters("responsible")
        self.helper_test_answer_visibility_two_voters("student")


class TestResultsSemesterEvaluationDetailViewPrivateEvaluation(WebTest):
    @patch('evap.results.templatetags.results_templatetags.get_grade_color', new=lambda x: (0, 0, 0))
    def test_private_evaluation(self):
        semester = mommy.make(Semester)
        mommy.make(UserProfile, username='manager', groups=[Group.objects.get(name='Manager')], email="manager@institution.example.com")
        student = mommy.make(UserProfile, username="student", email="student@institution.example.com")
        student_external = mommy.make(UserProfile, username="student_external")
        contributor = mommy.make(UserProfile, username="contributor", email="contributor@institution.example.com")
        responsible = mommy.make(UserProfile, username="responsible", email="responsible@institution.example.com")
        responsible_contributor = mommy.make(UserProfile, username="responsible_contributor", email="responsible_contributor@institution.example.com")
        test1 = mommy.make(UserProfile, username="test1")
        test2 = mommy.make(UserProfile, username="test2")
        mommy.make(UserProfile, username="random", email="random@institution.example.com")
        degree = mommy.make(Degree)
        course = mommy.make(Course, semester=semester, degrees=[degree], is_private=True, responsibles=[responsible, responsible_contributor])
        private_evaluation = mommy.make(Evaluation, course=course, state='published', participants=[student, student_external, test1, test2], voters=[test1, test2])
        private_evaluation.general_contribution.questionnaires.set([mommy.make(Questionnaire)])
        mommy.make(Contribution, evaluation=private_evaluation, contributor=responsible_contributor, can_edit=True, textanswer_visibility=Contribution.GENERAL_TEXTANSWERS)
        mommy.make(Contribution, evaluation=private_evaluation, contributor=contributor, can_edit=True)

        url = '/results/'
        self.assertNotIn(private_evaluation.full_name, self.app.get(url, user='random'))
        self.assertIn(private_evaluation.full_name, self.app.get(url, user='student'))
        self.assertIn(private_evaluation.full_name, self.app.get(url, user='responsible'))
        self.assertIn(private_evaluation.full_name, self.app.get(url, user='responsible_contributor'))
        self.assertIn(private_evaluation.full_name, self.app.get(url, user='contributor'))
        self.assertIn(private_evaluation.full_name, self.app.get(url, user='manager'))
        self.app.get(url, user='student_external', status=403)  # external users can't see results semester view

        url = '/results/semester/%s/evaluation/%s' % (semester.id, private_evaluation.id)
        self.app.get(url, user="random", status=403)
        self.app.get(url, user="student", status=200)
        self.app.get(url, user="responsible", status=200)
        self.app.get(url, user="responsible_contributor", status=200)
        self.app.get(url, user="contributor", status=200)
        self.app.get(url, user="manager", status=200)
        self.app.get(url, user="student_external", status=200)  # this external user participates in the evaluation and can see the results


class TestResultsTextanswerVisibilityForManager(WebTest):
    fixtures = ['minimal_test_data_results']

    @classmethod
    def setUpTestData(cls):
        manager_group = Group.objects.get(name="Manager")
        mommy.make(UserProfile, username="manager", groups=[manager_group])

    def test_textanswer_visibility_for_manager_before_publish(self):
        evaluation = Evaluation.objects.get(id=1)
        evaluation._voter_count = 0  # set these to 0 to make unpublishing work
        evaluation._participant_count = 0
        evaluation.unpublish()
        evaluation.save()

        page = self.app.get("/results/semester/1/evaluation/1?view=full", user='manager')
        self.assertIn(".general_orig_published.", page)
        self.assertNotIn(".general_orig_hidden.", page)
        self.assertNotIn(".general_orig_published_changed.", page)
        self.assertIn(".general_changed_published.", page)
        self.assertIn(".contributor_orig_published.", page)
        self.assertIn(".contributor_orig_private.", page)
        self.assertIn(".responsible_contributor_orig_published.", page)
        self.assertNotIn(".responsible_contributor_orig_hidden.", page)
        self.assertNotIn(".responsible_contributor_orig_published_changed.", page)
        self.assertIn(".responsible_contributor_changed_published.", page)
        self.assertIn(".responsible_contributor_orig_private.", page)
        self.assertNotIn(".responsible_contributor_orig_notreviewed.", page)

    def test_textanswer_visibility_for_manager(self):
        page = self.app.get("/results/semester/1/evaluation/1?view=full", user='manager')
        self.assertIn(".general_orig_published.", page)
        self.assertNotIn(".general_orig_hidden.", page)
        self.assertNotIn(".general_orig_published_changed.", page)
        self.assertIn(".general_changed_published.", page)
        self.assertIn(".contributor_orig_published.", page)
        self.assertIn(".contributor_orig_private.", page)
        self.assertIn(".responsible_contributor_orig_published.", page)
        self.assertNotIn(".responsible_contributor_orig_hidden.", page)
        self.assertNotIn(".responsible_contributor_orig_published_changed.", page)
        self.assertIn(".responsible_contributor_changed_published.", page)
        self.assertIn(".responsible_contributor_orig_private.", page)
        self.assertNotIn(".responsible_contributor_orig_notreviewed.", page)


class TestResultsTextanswerVisibility(WebTest):
    fixtures = ['minimal_test_data_results']

    def test_textanswer_visibility_for_responsible(self):
        page = self.app.get("/results/semester/1/evaluation/1", user='responsible')
        self.assertIn(".general_orig_published.", page)
        self.assertNotIn(".general_orig_hidden.", page)
        self.assertNotIn(".general_orig_published_changed.", page)
        self.assertIn(".general_changed_published.", page)
        self.assertNotIn(".contributor_orig_published.", page)
        self.assertNotIn(".contributor_orig_private.", page)
        self.assertNotIn(".responsible_contributor_orig_published.", page)
        self.assertNotIn(".responsible_contributor_orig_hidden.", page)
        self.assertNotIn(".responsible_contributor_orig_published_changed.", page)
        self.assertNotIn(".responsible_contributor_changed_published.", page)
        self.assertNotIn(".responsible_contributor_orig_private.", page)
        self.assertNotIn(".responsible_contributor_orig_notreviewed.", page)

    def test_textanswer_visibility_for_responsible_contributor(self):
        page = self.app.get("/results/semester/1/evaluation/1", user='responsible_contributor')
        self.assertIn(".general_orig_published.", page)
        self.assertNotIn(".general_orig_hidden.", page)
        self.assertNotIn(".general_orig_published_changed.", page)
        self.assertIn(".general_changed_published.", page)
        self.assertNotIn(".contributor_orig_published.", page)
        self.assertNotIn(".contributor_orig_private.", page)
        self.assertIn(".responsible_contributor_orig_published.", page)
        self.assertNotIn(".responsible_contributor_orig_hidden.", page)
        self.assertNotIn(".responsible_contributor_orig_published_changed.", page)
        self.assertIn(".responsible_contributor_changed_published.", page)
        self.assertIn(".responsible_contributor_orig_private.", page)
        self.assertNotIn(".responsible_contributor_orig_notreviewed.", page)

    def test_textanswer_visibility_for_delegate_for_responsible(self):
        page = self.app.get("/results/semester/1/evaluation/1", user='delegate_for_responsible')
        self.assertIn(".general_orig_published.", page)
        self.assertNotIn(".general_orig_hidden.", page)
        self.assertNotIn(".general_orig_published_changed.", page)
        self.assertIn(".general_changed_published.", page)
        self.assertNotIn(".contributor_orig_published.", page)
        self.assertNotIn(".contributor_orig_private.", page)
        self.assertNotIn(".responsible_contributor_orig_published.", page)
        self.assertNotIn(".responsible_contributor_orig_hidden.", page)
        self.assertNotIn(".responsible_contributor_orig_published_changed.", page)
        self.assertNotIn(".responsible_contributor_changed_published.", page)
        self.assertNotIn(".responsible_contributor_orig_private.", page)
        self.assertNotIn(".responsible_contributor_orig_notreviewed.", page)

    def test_textanswer_visibility_for_contributor(self):
        page = self.app.get("/results/semester/1/evaluation/1", user='contributor')
        self.assertNotIn(".general_orig_published.", page)
        self.assertNotIn(".general_orig_hidden.", page)
        self.assertNotIn(".general_orig_published_changed.", page)
        self.assertNotIn(".general_changed_published.", page)
        self.assertIn(".contributor_orig_published.", page)
        self.assertIn(".contributor_orig_private.", page)
        self.assertNotIn(".responsible_contributor_orig_published.", page)
        self.assertNotIn(".responsible_contributor_orig_hidden.", page)
        self.assertNotIn(".responsible_contributor_orig_published_changed.", page)
        self.assertNotIn(".responsible_contributor_changed_published.", page)
        self.assertNotIn(".responsible_contributor_orig_private.", page)
        self.assertNotIn(".responsible_contributor_orig_notreviewed.", page)

    def test_textanswer_visibility_for_delegate_for_contributor(self):
        page = self.app.get("/results/semester/1/evaluation/1", user='delegate_for_contributor')
        self.assertNotIn(".general_orig_published.", page)
        self.assertNotIn(".general_orig_hidden.", page)
        self.assertNotIn(".general_orig_published_changed.", page)
        self.assertNotIn(".general_changed_published.", page)
        self.assertIn(".contributor_orig_published.", page)
        self.assertNotIn(".contributor_orig_private.", page)
        self.assertNotIn(".responsible_contributor_orig_published.", page)
        self.assertNotIn(".responsible_contributor_orig_hidden.", page)
        self.assertNotIn(".responsible_contributor_orig_published_changed.", page)
        self.assertNotIn(".responsible_contributor_changed_published.", page)
        self.assertNotIn(".responsible_contributor_orig_private.", page)
        self.assertNotIn(".responsible_contributor_orig_notreviewed.", page)

    def test_textanswer_visibility_for_contributor_general_textanswers(self):
        page = self.app.get("/results/semester/1/evaluation/1", user='contributor_general_textanswers')
        self.assertIn(".general_orig_published.", page)
        self.assertNotIn(".general_orig_hidden.", page)
        self.assertNotIn(".general_orig_published_changed.", page)
        self.assertIn(".general_changed_published.", page)
        self.assertNotIn(".contributor_orig_published.", page)
        self.assertNotIn(".contributor_orig_private.", page)
        self.assertNotIn(".responsible_contributor_orig_published.", page)
        self.assertNotIn(".responsible_contributor_orig_hidden.", page)
        self.assertNotIn(".responsible_contributor_orig_published_changed.", page)
        self.assertNotIn(".responsible_contributor_changed_published.", page)
        self.assertNotIn(".responsible_contributor_orig_private.", page)
        self.assertNotIn(".responsible_contributor_orig_notreviewed.", page)

    def test_textanswer_visibility_for_student(self):
        page = self.app.get("/results/semester/1/evaluation/1", user='student')
        self.assertNotIn(".general_orig_published.", page)
        self.assertNotIn(".general_orig_hidden.", page)
        self.assertNotIn(".general_orig_published_changed.", page)
        self.assertNotIn(".general_changed_published.", page)
        self.assertNotIn(".contributor_orig_published.", page)
        self.assertNotIn(".contributor_orig_private.", page)
        self.assertNotIn(".responsible_contributor_orig_published.", page)
        self.assertNotIn(".responsible_contributor_orig_hidden.", page)
        self.assertNotIn(".responsible_contributor_orig_published_changed.", page)
        self.assertNotIn(".responsible_contributor_changed_published.", page)
        self.assertNotIn(".responsible_contributor_orig_private.", page)
        self.assertNotIn(".responsible_contributor_orig_notreviewed.", page)

    def test_textanswer_visibility_for_student_external(self):
        # the external user does not participate in or contribute to the evaluation and therefore can't see the results
        self.app.get("/results/semester/1/evaluation/1", user='student_external', status=403)

    def test_textanswer_visibility_info_is_shown(self):
        page = self.app.get("/results/semester/1/evaluation/1", user='contributor')
        self.assertIn("can be seen by: contributor user", page)


class TestResultsOtherContributorsListOnExportView(WebTest):
    @classmethod
    def setUpTestData(cls):
        cls.semester = mommy.make(Semester, id=2)
        responsible = mommy.make(UserProfile, username='responsible')
        cls.evaluation = mommy.make(Evaluation, id=21, state='published', course=mommy.make(Course, semester=cls.semester, responsibles=[responsible]))

        questionnaire = mommy.make(Questionnaire)
        mommy.make(Question, questionnaire=questionnaire, type=Question.LIKERT)
        cls.evaluation.general_contribution.questionnaires.set([questionnaire])

        mommy.make(Contribution, evaluation=cls.evaluation, contributor=responsible, questionnaires=[questionnaire], can_edit=True, textanswer_visibility=Contribution.GENERAL_TEXTANSWERS)
        cls.other_contributor_1 = mommy.make(UserProfile, username='other contributor 1')
        mommy.make(Contribution, evaluation=cls.evaluation, contributor=cls.other_contributor_1, questionnaires=[questionnaire], textanswer_visibility=Contribution.OWN_TEXTANSWERS)
        cls.other_contributor_2 = mommy.make(UserProfile, username='other contributor 2')
        mommy.make(Contribution, evaluation=cls.evaluation, contributor=cls.other_contributor_2, questionnaires=[questionnaire], textanswer_visibility=Contribution.OWN_TEXTANSWERS)

    def test_contributor_list(self):
        url = '/results/semester/{}/evaluation/{}?view=export'.format(self.semester.id, self.evaluation.id)
        page = self.app.get(url, user='responsible')
        self.assertIn("<li>{}</li>".format(self.other_contributor_1.username), page)
        self.assertIn("<li>{}</li>".format(self.other_contributor_2.username), page)


class TestResultsTextanswerVisibilityForExportView(WebTest):
    fixtures = ['minimal_test_data_results']

    @classmethod
    def setUpTestData(cls):
        manager_group = Group.objects.get(name="Manager")
        cls.manager = mommy.make(UserProfile, username="manager", groups=[manager_group])

    def test_textanswer_visibility_for_responsible(self):
        page = self.app.get("/results/semester/1/evaluation/1?view=export", user='responsible')

        self.assertIn(".general_orig_published.", page)
        self.assertNotIn(".general_orig_hidden.", page)
        self.assertNotIn(".general_orig_published_changed.", page)
        self.assertIn(".general_changed_published.", page)
        self.assertNotIn(".contributor_orig_published.", page)
        self.assertNotIn(".contributor_orig_private.", page)
        self.assertNotIn(".responsible_contributor_orig_published.", page)
        self.assertNotIn(".responsible_contributor_orig_hidden.", page)
        self.assertNotIn(".responsible_contributor_orig_published_changed.", page)
        self.assertNotIn(".responsible_contributor_changed_published.", page)
        self.assertNotIn(".responsible_contributor_orig_private.", page)
        self.assertNotIn(".responsible_contributor_orig_notreviewed.", page)

    def test_textanswer_visibility_for_responsible_contributor(self):
        page = self.app.get("/results/semester/1/evaluation/1?view=export", user='responsible_contributor')

        self.assertIn(".general_orig_published.", page)
        self.assertNotIn(".general_orig_hidden.", page)
        self.assertNotIn(".general_orig_published_changed.", page)
        self.assertIn(".general_changed_published.", page)
        self.assertNotIn(".contributor_orig_published.", page)
        self.assertNotIn(".contributor_orig_private.", page)
        self.assertIn(".responsible_contributor_orig_published.", page)
        self.assertNotIn(".responsible_contributor_orig_hidden.", page)
        self.assertNotIn(".responsible_contributor_orig_published_changed.", page)
        self.assertIn(".responsible_contributor_changed_published.", page)
        self.assertNotIn(".responsible_contributor_orig_private.", page)
        self.assertNotIn(".responsible_contributor_orig_notreviewed.", page)

    def test_textanswer_visibility_for_contributor(self):
        page = self.app.get("/results/semester/1/evaluation/1?view=export", user='contributor')

        self.assertNotIn(".general_orig_published.", page)
        self.assertNotIn(".general_orig_hidden.", page)
        self.assertNotIn(".general_orig_published_changed.", page)
        self.assertNotIn(".general_changed_published.", page)
        self.assertIn(".contributor_orig_published.", page)
        self.assertNotIn(".contributor_orig_private.", page)
        self.assertNotIn(".responsible_contributor_orig_published.", page)
        self.assertNotIn(".responsible_contributor_orig_hidden.", page)
        self.assertNotIn(".responsible_contributor_orig_published_changed.", page)
        self.assertNotIn(".responsible_contributor_changed_published.", page)
        self.assertNotIn(".responsible_contributor_orig_private.", page)
        self.assertNotIn(".responsible_contributor_orig_notreviewed.", page)

    def test_textanswer_visibility_for_contributor_general_textanswers(self):
        page = self.app.get("/results/semester/1/evaluation/1?view=export", user='contributor_general_textanswers')

        self.assertIn(".general_orig_published.", page)
        self.assertNotIn(".general_orig_hidden.", page)
        self.assertNotIn(".general_orig_published_changed.", page)
        self.assertIn(".general_changed_published.", page)
        self.assertNotIn(".contributor_orig_published.", page)
        self.assertNotIn(".contributor_orig_private.", page)
        self.assertNotIn(".responsible_contributor_orig_published.", page)
        self.assertNotIn(".responsible_contributor_orig_hidden.", page)
        self.assertNotIn(".responsible_contributor_orig_published_changed.", page)
        self.assertNotIn(".responsible_contributor_changed_published.", page)
        self.assertNotIn(".responsible_contributor_orig_private.", page)
        self.assertNotIn(".responsible_contributor_orig_notreviewed.", page)

    def test_textanswer_visibility_for_student(self):
        page = self.app.get("/results/semester/1/evaluation/1?view=export", user='student')

        self.assertNotIn(".general_orig_published.", page)
        self.assertNotIn(".general_orig_hidden.", page)
        self.assertNotIn(".general_orig_published_changed.", page)
        self.assertNotIn(".general_changed_published.", page)
        self.assertNotIn(".contributor_orig_published.", page)
        self.assertNotIn(".contributor_orig_private.", page)
        self.assertNotIn(".responsible_contributor_orig_published.", page)
        self.assertNotIn(".responsible_contributor_orig_hidden.", page)
        self.assertNotIn(".responsible_contributor_orig_published_changed.", page)
        self.assertNotIn(".responsible_contributor_changed_published.", page)
        self.assertNotIn(".responsible_contributor_orig_private.", page)
        self.assertNotIn(".responsible_contributor_orig_notreviewed.", page)

    def test_textanswer_visibility_for_manager(self):
        contributor_id = UserProfile.objects.get(username="responsible").id
        page = self.app.get("/results/semester/1/evaluation/1?view=export&contributor_id={}".format(contributor_id), user='manager')

        self.assertIn(".general_orig_published.", page)
        self.assertNotIn(".general_orig_hidden.", page)
        self.assertNotIn(".general_orig_published_changed.", page)
        self.assertIn(".general_changed_published.", page)
        self.assertNotIn(".contributor_orig_published.", page)
        self.assertNotIn(".contributor_orig_private.", page)
        self.assertNotIn(".responsible_contributor_orig_published.", page)
        self.assertNotIn(".responsible_contributor_orig_hidden.", page)
        self.assertNotIn(".responsible_contributor_orig_published_changed.", page)
        self.assertNotIn(".responsible_contributor_changed_published.", page)
        self.assertNotIn(".responsible_contributor_orig_private.", page)
        self.assertNotIn(".responsible_contributor_orig_notreviewed.", page)

    def test_textanswer_visibility_for_manager_contributor(self):
        manager_group = Group.objects.get(name="Manager")
        contributor = UserProfile.objects.get(username="contributor")
        contributor.groups.add(manager_group)
        page = self.app.get("/results/semester/1/evaluation/1?view=export&contributor_id={}".format(contributor.id), user='contributor')

        self.assertNotIn(".general_orig_published.", page)
        self.assertNotIn(".general_orig_hidden.", page)
        self.assertNotIn(".general_orig_published_changed.", page)
        self.assertNotIn(".general_changed_published.", page)
        self.assertIn(".contributor_orig_published.", page)
        self.assertNotIn(".contributor_orig_private.", page)
        self.assertNotIn(".responsible_contributor_orig_published.", page)
        self.assertNotIn(".responsible_contributor_orig_hidden.", page)
        self.assertNotIn(".responsible_contributor_orig_published_changed.", page)
        self.assertNotIn(".responsible_contributor_changed_published.", page)
        self.assertNotIn(".responsible_contributor_orig_private.", page)
        self.assertNotIn(".responsible_contributor_orig_notreviewed.", page)


class TestArchivedResults(WebTest):
    @classmethod
    def setUpTestData(cls):
        cls.semester = mommy.make(Semester)
        mommy.make(UserProfile, username='manager', groups=[Group.objects.get(name='Manager')], email="manager@institution.example.com")
        mommy.make(UserProfile, username='reviewer', groups=[Group.objects.get(name='Reviewer')], email="reviewer@institution.example.com")
        student = mommy.make(UserProfile, username="student", email="student@institution.example.com")
        student_external = mommy.make(UserProfile, username="student_external")
        contributor = mommy.make(UserProfile, username="contributor", email="contributor@institution.example.com")
        responsible = mommy.make(UserProfile, username="responsible", email="responsible@institution.example.com")

        course = mommy.make(Course, semester=cls.semester, degrees=[mommy.make(Degree)], responsibles=[responsible])
        cls.evaluation = mommy.make(Evaluation, course=course, state='published', participants=[student, student_external], voters=[student, student_external])
        cls.evaluation.general_contribution.questionnaires.set([mommy.make(Questionnaire)])
        cls.contribution = mommy.make(Contribution, evaluation=cls.evaluation, can_edit=True, textanswer_visibility=Contribution.GENERAL_TEXTANSWERS, contributor=responsible)
        cls.contribution = mommy.make(Contribution, evaluation=cls.evaluation, contributor=contributor)

    @patch('evap.results.templatetags.results_templatetags.get_grade_color', new=lambda x: (0, 0, 0))
    def test_unarchived_results(self):
        url = '/results/'
        self.assertIn(self.evaluation.full_name, self.app.get(url, user='student'))
        self.assertIn(self.evaluation.full_name, self.app.get(url, user='responsible'))
        self.assertIn(self.evaluation.full_name, self.app.get(url, user='contributor'))
        self.assertIn(self.evaluation.full_name, self.app.get(url, user='manager'))
        self.assertIn(self.evaluation.full_name, self.app.get(url, user='reviewer'))
        self.app.get(url, user='student_external', status=403)  # external users can't see results semester view

        url = '/results/semester/%s/evaluation/%s' % (self.semester.id, self.evaluation.id)
        self.app.get(url, user="student", status=200)
        self.app.get(url, user="responsible", status=200)
        self.app.get(url, user="contributor", status=200)
        self.app.get(url, user="manager", status=200)
        self.app.get(url, user="reviewer", status=200)
        self.app.get(url, user='student_external', status=200)

    def test_archived_results(self):
        self.semester.archive_results()

        url = '/results/semester/%s/evaluation/%s' % (self.semester.id, self.evaluation.id)
        self.app.get(url, user='student', status=403)
        self.app.get(url, user='responsible', status=200)
        self.app.get(url, user='contributor', status=200)
        self.app.get(url, user='manager', status=200)
        self.app.get(url, user='reviewer', status=403)
        self.app.get(url, user='student_external', status=403)
