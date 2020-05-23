from unittest.mock import patch
from io import StringIO
import random

from django.contrib.auth.models import Group
from django.core.cache import caches
from django.core.management import call_command
from django.test.testcases import TestCase
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext

from django_webtest import WebTest
from model_bakery import baker

from evap.evaluation.models import (Contribution, Course, Degree, Evaluation, Question, Questionnaire,
                                    RatingAnswerCounter,
                                    Semester, UserProfile)
from evap.evaluation.tests.tools import WebTestWith200Check, let_user_vote_for_evaluation
from evap.results.exporters import TextAnswerExcelExporter
from evap.results.views import get_evaluations_with_prefetched_data


class TestResultsView(WebTest):
    url = '/results/'

    @patch('evap.evaluation.models.Evaluation.can_be_seen_by', new=(lambda self, user: True))
    def test_multiple_evaluations_per_course(self):
        baker.make(UserProfile, email="student@institution.example.com")

        # course with no evaluations does not show up
        course = baker.make(Course)
        page = self.app.get(self.url, user="student@institution.example.com")
        self.assertNotContains(page, course.name)
        caches['results'].clear()

        # course with one evaluation is a single line with the evaluation's full_name
        evaluation = baker.make(Evaluation, course=course, name_en='unique_evaluation_name1', name_de="foo", state='published')
        page = self.app.get(self.url, user="student@institution.example.com")
        self.assertContains(page, evaluation.full_name)
        caches['results'].clear()

        # course with two evaluations is three lines without using the full names
        evaluation2 = baker.make(Evaluation, course=course, name_en='unique_evaluation_name2', name_de="bar", state='published')
        page = self.app.get(self.url, user="student@institution.example.com")
        self.assertContains(page, course.name)
        self.assertContains(page, evaluation.name_en)
        self.assertContains(page, evaluation2.name_en)
        self.assertNotContains(page, evaluation.full_name)
        self.assertNotContains(page, evaluation2.full_name)
        caches['results'].clear()

    # using LocMemCache so the cache queries don't show up in the query count that's measured here
    @override_settings(CACHES={
        'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'testing_cache_default'},
        'sessions': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'testing_cache_results'},
        'results': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'testing_cache_sessions'},
    })
    @patch('evap.evaluation.models.Evaluation.can_be_seen_by', new=(lambda self, user: True))
    def test_num_queries_is_constant(self):
        """
            ensures that the number of queries in the user list is constant
            and not linear to the number of courses/evaluations
        """
        baker.make(UserProfile, email="student@institution.example.com")

        # warm up some caches
        self.app.get(self.url, user="student@institution.example.com")

        def make_course_with_evaluations(unique_suffix):
            course = baker.make(Course)
            baker.make(Evaluation, course=course, name_en='foo' + unique_suffix, name_de='foo' + unique_suffix, state='published', _voter_count=0)
            baker.make(Evaluation, course=course, name_en='bar' + unique_suffix, name_de='bar' + unique_suffix, state='published', _voter_count=0)

        # first measure the number of queries with two courses
        make_course_with_evaluations('frob')
        make_course_with_evaluations('spam')
        call_command("refresh_results_cache", stdout=StringIO())
        with CaptureQueriesContext(connection) as context:
            self.app.get(self.url, user="student@institution.example.com")
        num_queries_before = context.final_queries - context.initial_queries

        # then measure the number of queries with one more course and compare
        make_course_with_evaluations('eggs')
        call_command("refresh_results_cache", stdout=StringIO())
        with CaptureQueriesContext(connection) as context:
            self.app.get(self.url, user="student@institution.example.com")
        num_queries_after = context.final_queries - context.initial_queries

        self.assertEqual(num_queries_before, num_queries_after)

        # django does not clear the LocMemCache in between tests. clear it here just to be safe.
        caches['default'].clear()
        caches['sessions'].clear()
        caches['results'].clear()


class TestGetEvaluationsWithPrefetchedData(TestCase):
    def test_returns_correct_participant_count(self):
        """ Regression test for #1248 """
        participants = baker.make(UserProfile, _quantity=2)
        evaluation = baker.make(
            Evaluation,
            state='published',
            _participant_count=2,
            _voter_count=2,
            participants=participants,
            voters=participants,
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
        cls.semester = baker.make(Semester, id=3)
        baker.make(UserProfile, email='manager@institution.example.com', groups=[Group.objects.get(name='Manager')])
        contributor = baker.make(UserProfile)

        # Set up an evaluation with one question but no answers
        student1 = baker.make(UserProfile)
        student2 = baker.make(UserProfile)
        cls.evaluation = baker.make(Evaluation, id=21, state='published', course=baker.make(Course, semester=cls.semester), participants=[student1, student2], voters=[student1, student2])
        questionnaire = baker.make(Questionnaire)
        cls.evaluation.general_contribution.questionnaires.set([questionnaire])
        cls.contribution = baker.make(Contribution, evaluation=cls.evaluation, questionnaires=[questionnaire], contributor=contributor)
        cls.likert_question = baker.make(Question, type=Question.LIKERT, questionnaire=questionnaire, order=2)
        cls.url = '/results/semester/%s/evaluation/%s' % (cls.semester.id, cls.evaluation.id)

    def test_many_answers_evaluation_no_warning(self):
        baker.make(RatingAnswerCounter, question=self.likert_question, contribution=self.contribution, answer=3, count=10)
        page = self.app.get(self.url, user="manager@institution.example.com", status=200)
        self.assertNotIn("Only a few participants answered these questions.", page)

    def test_zero_answers_evaluation_no_warning(self):
        page = self.app.get(self.url, user="manager@institution.example.com", status=200)
        self.assertNotIn("Only a few participants answered these questions.", page)

    def test_few_answers_evaluation_show_warning(self):
        baker.make(RatingAnswerCounter, question=self.likert_question, contribution=self.contribution, answer=3, count=3)
        page = self.app.get(self.url, user="manager@institution.example.com", status=200)
        self.assertIn("Only a few participants answered these questions.", page)


class TestResultsSemesterEvaluationDetailView(WebTestWith200Check):
    url = '/results/semester/2/evaluation/21'
    test_users = ['manager@institution.example.com', 'contributor@institution.example.com', 'responsible@institution.example.com']

    @classmethod
    def setUpTestData(cls):
        cls.semester = baker.make(Semester, id=2)

        baker.make(UserProfile, email='manager@institution.example.com', groups=[Group.objects.get(name='Manager')])
        contributor = baker.make(UserProfile, email='contributor@institution.example.com')
        responsible = baker.make(UserProfile, email='responsible@institution.example.com')

        # Normal evaluation with responsible and contributor.
        cls.evaluation = baker.make(Evaluation, id=21, state='published', course=baker.make(Course, semester=cls.semester))

        baker.make(Contribution, evaluation=cls.evaluation, contributor=responsible, can_edit=True, textanswer_visibility=Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS)
        cls.contribution = baker.make(Contribution, evaluation=cls.evaluation, contributor=contributor, can_edit=True)

    def test_questionnaire_ordering(self):
        top_questionnaire = baker.make(Questionnaire, type=Questionnaire.Type.TOP)
        contributor_questionnaire = baker.make(Questionnaire, type=Questionnaire.Type.CONTRIBUTOR)
        bottom_questionnaire = baker.make(Questionnaire, type=Questionnaire.Type.BOTTOM)

        top_heading_question = baker.make(Question, type=Question.HEADING, questionnaire=top_questionnaire, order=0)
        top_likert_question = baker.make(Question, type=Question.LIKERT, questionnaire=top_questionnaire, order=1)

        contributor_likert_question = baker.make(Question, type=Question.LIKERT, questionnaire=contributor_questionnaire)

        bottom_heading_question = baker.make(Question, type=Question.HEADING, questionnaire=bottom_questionnaire, order=0)
        bottom_likert_question = baker.make(Question, type=Question.LIKERT, questionnaire=bottom_questionnaire, order=1)

        self.evaluation.general_contribution.questionnaires.set([top_questionnaire, bottom_questionnaire])
        self.contribution.questionnaires.set([contributor_questionnaire])

        baker.make(RatingAnswerCounter, question=top_likert_question, contribution=self.evaluation.general_contribution, answer=2, count=100)
        baker.make(RatingAnswerCounter, question=contributor_likert_question, contribution=self.contribution, answer=1, count=100)
        baker.make(RatingAnswerCounter, question=bottom_likert_question, contribution=self.evaluation.general_contribution, answer=3, count=100)

        content = self.app.get(self.url, user="manager@institution.example.com").body.decode()

        top_heading_index = content.index(top_heading_question.text)
        top_likert_index = content.index(top_likert_question.text)
        contributor_likert_index = content.index(contributor_likert_question.text)
        bottom_heading_index = content.index(bottom_heading_question.text)
        bottom_likert_index = content.index(bottom_likert_question.text)

        self.assertTrue(top_heading_index < top_likert_index < contributor_likert_index < bottom_heading_index < bottom_likert_index)

    def test_heading_question_filtering(self):
        contributor = baker.make(UserProfile)
        questionnaire = baker.make(Questionnaire)

        heading_question_0 = baker.make(Question, type=Question.HEADING, questionnaire=questionnaire, order=0)
        heading_question_1 = baker.make(Question, type=Question.HEADING, questionnaire=questionnaire, order=1)
        likert_question = baker.make(Question, type=Question.LIKERT, questionnaire=questionnaire, order=2)
        heading_question_2 = baker.make(Question, type=Question.HEADING, questionnaire=questionnaire, order=3)

        contribution = baker.make(Contribution, evaluation=self.evaluation, questionnaires=[questionnaire], contributor=contributor)
        baker.make(RatingAnswerCounter, question=likert_question, contribution=contribution, answer=3, count=100)

        page = self.app.get(self.url, user="manager@institution.example.com")

        self.assertNotIn(heading_question_0.text, page)
        self.assertIn(heading_question_1.text, page)
        self.assertIn(likert_question.text, page)
        self.assertNotIn(heading_question_2.text, page)

    def test_default_view_is_public(self):
        random.seed(42)  # use explicit seed to always choose the same "random" slogan
        page_without_get_parameter = self.app.get(self.url, user="manager@institution.example.com")
        random.seed(42)
        page_with_get_parameter = self.app.get(self.url + '?view=public', user="manager@institution.example.com")
        random.seed(42)
        page_with_random_get_parameter = self.app.get(self.url + '?view=asdf', user="manager@institution.example.com")
        self.assertEqual(page_without_get_parameter.body, page_with_get_parameter.body)
        self.assertEqual(page_without_get_parameter.body, page_with_random_get_parameter.body)

    def test_wrong_state(self):
        evaluation = baker.make(Evaluation, state='reviewed', course=baker.make(Course, semester=self.semester))
        url = '/results/semester/%s/evaluation/%s' % (self.semester.id, evaluation.id)
        self.app.get(url, user="student@institution.example.com", status=403)

    def test_preview_without_rating_answers(self):
        evaluation = baker.make(Evaluation, state='evaluated', course=baker.make(Course, semester=self.semester))
        url = f'/results/semester/{self.semester.id}/evaluation/{evaluation.id}'
        self.app.get(url, user="manager@institution.example.com")

    def test_preview_with_rating_answers(self):
        evaluation = baker.make(Evaluation, state='evaluated', course=baker.make(Course, semester=self.semester))
        questionnaire = baker.make(Questionnaire, type=Questionnaire.Type.TOP)
        likert_question = baker.make(Question, type=Question.LIKERT, questionnaire=questionnaire, order=1)
        evaluation.general_contribution.questionnaires.set([questionnaire])
        participants = baker.make(UserProfile, _quantity=20)
        evaluation.participants.set(participants)
        evaluation.voters.set(participants)
        baker.make(RatingAnswerCounter, question=likert_question, contribution=evaluation.general_contribution, answer=1, count=20)

        url = f'/results/semester/{self.semester.id}/evaluation/{evaluation.id}'
        self.app.get(url, user="manager@institution.example.com")


class TestResultsSemesterEvaluationDetailViewFewVoters(WebTest):
    @classmethod
    def setUpTestData(cls):
        cls.semester = baker.make(Semester, id=2)
        baker.make(UserProfile, email='manager@institution.example.com', groups=[Group.objects.get(name='Manager')])
        responsible = baker.make(UserProfile, email='responsible@institution.example.com')
        cls.student1 = baker.make(UserProfile, email='student1@institution.example.com')
        cls.student2 = baker.make(UserProfile, email='student2@example.com')
        students = baker.make(UserProfile, _quantity=10)
        students.extend([cls.student1, cls.student2])

        cls.evaluation = baker.make(Evaluation, id=22, state='in_evaluation', course=baker.make(Course, semester=cls.semester), participants=students)
        questionnaire = baker.make(Questionnaire)
        cls.question_grade = baker.make(Question, questionnaire=questionnaire, type=Question.GRADE)
        baker.make(Question, questionnaire=questionnaire, type=Question.LIKERT)
        cls.evaluation.general_contribution.questionnaires.set([questionnaire])
        cls.responsible_contribution = baker.make(Contribution, contributor=responsible, evaluation=cls.evaluation, questionnaires=[questionnaire])

    def setUp(self):
        self.evaluation = Evaluation.objects.get(pk=self.evaluation.pk)

    def helper_test_answer_visibility_one_voter(self, user_email, expect_page_not_visible=False):
        page = self.app.get("/results/semester/2/evaluation/22", user=user_email, expect_errors=expect_page_not_visible)
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

    def helper_test_answer_visibility_two_voters(self, user_email):
        page = self.app.get("/results/semester/2/evaluation/22", user=user_email)
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
        self.helper_test_answer_visibility_one_voter("manager@institution.example.com")
        self.evaluation = Evaluation.objects.get(id=self.evaluation.id)
        self.helper_test_answer_visibility_one_voter("responsible@institution.example.com")
        self.helper_test_answer_visibility_one_voter("student@institution.example.com", expect_page_not_visible=True)

    def test_answer_visibility_two_voters(self):
        let_user_vote_for_evaluation(self.app, self.student1, self.evaluation)
        let_user_vote_for_evaluation(self.app, self.student2, self.evaluation)
        self.evaluation.evaluation_end()
        self.evaluation.review_finished()
        self.evaluation.publish()
        self.evaluation.save()
        self.assertEqual(self.evaluation.voters.count(), 2)

        self.helper_test_answer_visibility_two_voters("manager@institution.example.com")
        self.helper_test_answer_visibility_two_voters("responsible@institution.example.com")
        self.helper_test_answer_visibility_two_voters("student@institution.example.com")


class TestResultsSemesterEvaluationDetailViewPrivateEvaluation(WebTest):
    @patch('evap.results.templatetags.results_templatetags.get_grade_color', new=lambda x: (0, 0, 0))
    def test_private_evaluation(self):
        semester = baker.make(Semester)
        baker.make(UserProfile, email='manager@institution.example.com', groups=[Group.objects.get(name='Manager')])
        student = baker.make(UserProfile, email="student@institution.example.com")
        student_external = baker.make(UserProfile, email="student_external@example.com")
        contributor = baker.make(UserProfile, email="contributor@institution.example.com")
        responsible = baker.make(UserProfile, email="responsible@institution.example.com")
        responsible_contributor = baker.make(UserProfile, email="responsible_contributor@institution.example.com")
        test1 = baker.make(UserProfile, email="test1@institution.example.com")
        test2 = baker.make(UserProfile, email="test2@institution.example.com")
        baker.make(UserProfile, email="random@institution.example.com")
        degree = baker.make(Degree)
        course = baker.make(Course, semester=semester, degrees=[degree], is_private=True, responsibles=[responsible, responsible_contributor])
        private_evaluation = baker.make(Evaluation, course=course, state='published', participants=[student, student_external, test1, test2], voters=[test1, test2])
        private_evaluation.general_contribution.questionnaires.set([baker.make(Questionnaire)])
        baker.make(Contribution, evaluation=private_evaluation, contributor=responsible_contributor, can_edit=True, textanswer_visibility=Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS)
        baker.make(Contribution, evaluation=private_evaluation, contributor=contributor, can_edit=True)

        url = '/results/'
        self.assertNotIn(private_evaluation.full_name, self.app.get(url, user="random@institution.example.com"))
        self.assertIn(private_evaluation.full_name, self.app.get(url, user="student@institution.example.com"))
        self.assertIn(private_evaluation.full_name, self.app.get(url, user="responsible@institution.example.com"))
        self.assertIn(private_evaluation.full_name, self.app.get(url, user="responsible_contributor@institution.example.com"))
        self.assertIn(private_evaluation.full_name, self.app.get(url, user="contributor@institution.example.com"))
        self.assertIn(private_evaluation.full_name, self.app.get(url, user="manager@institution.example.com"))
        self.app.get(url, user="student_external@example.com", status=403)  # external users can't see results semester view

        url = '/results/semester/%s/evaluation/%s' % (semester.id, private_evaluation.id)
        self.app.get(url, user="random@institution.example.com", status=403)
        self.app.get(url, user="student@institution.example.com", status=200)
        self.app.get(url, user="responsible@institution.example.com", status=200)
        self.app.get(url, user="responsible_contributor@institution.example.com", status=200)
        self.app.get(url, user="contributor@institution.example.com", status=200)
        self.app.get(url, user="manager@institution.example.com", status=200)
        self.app.get(url, user="student_external@example.com", status=200)  # this external user participates in the evaluation and can see the results


class TestResultsTextanswerVisibilityForManager(WebTest):
    fixtures = ['minimal_test_data_results']

    @classmethod
    def setUpTestData(cls):
        manager_group = Group.objects.get(name="Manager")
        baker.make(UserProfile, email="manager@institution.example.com", groups=[manager_group])

    def test_textanswer_visibility_for_manager_before_publish(self):
        evaluation = Evaluation.objects.get(id=1)
        evaluation._voter_count = 0  # set these to 0 to make unpublishing work
        evaluation._participant_count = 0
        evaluation.unpublish()
        evaluation.save()

        page = self.app.get("/results/semester/1/evaluation/1?view=full", user="manager@institution.example.com")
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
        page = self.app.get("/results/semester/1/evaluation/1?view=full", user="manager@institution.example.com")
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
        page = self.app.get("/results/semester/1/evaluation/1", user="responsible@institution.example.com")
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
        page = self.app.get("/results/semester/1/evaluation/1", user="responsible_contributor@institution.example.com")
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
        page = self.app.get("/results/semester/1/evaluation/1", user="delegate_for_responsible@institution.example.com")
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
        page = self.app.get("/results/semester/1/evaluation/1", user="contributor@institution.example.com")
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
        page = self.app.get("/results/semester/1/evaluation/1", user="delegate_for_contributor@institution.example.com")
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
        page = self.app.get("/results/semester/1/evaluation/1", user="contributor_general_textanswers@institution.example.com")
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
        page = self.app.get("/results/semester/1/evaluation/1", user="student@institution.example.com")
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
        self.app.get("/results/semester/1/evaluation/1", user="student_external@example.com", status=403)

    def test_textanswer_visibility_info_is_shown(self):
        page = self.app.get("/results/semester/1/evaluation/1", user="contributor@institution.example.com")
        self.assertRegex(page.body.decode(), r"can be seen by:<br />\s*contributor user")

    def test_textanswer_visibility_info_for_proxy_user(self):
        page = self.app.get("/results/semester/1/evaluation/1", user="responsible@institution.example.com")
        self.assertIn("responsible_contributor user (1 person)", page)


class TestResultsOtherContributorsListOnExportView(WebTest):
    @classmethod
    def setUpTestData(cls):
        cls.semester = baker.make(Semester, id=2)
        responsible = baker.make(UserProfile, email='responsible@institution.example.com')
        cls.evaluation = baker.make(Evaluation, id=21, state='published', course=baker.make(Course, semester=cls.semester, responsibles=[responsible]))

        questionnaire = baker.make(Questionnaire)
        baker.make(Question, questionnaire=questionnaire, type=Question.LIKERT)
        cls.evaluation.general_contribution.questionnaires.set([questionnaire])

        baker.make(Contribution, evaluation=cls.evaluation, contributor=responsible, questionnaires=[questionnaire], can_edit=True, textanswer_visibility=Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS)
        cls.other_contributor_1 = baker.make(UserProfile, email='other_contributor_1@institution.example.com')
        baker.make(Contribution, evaluation=cls.evaluation, contributor=cls.other_contributor_1, questionnaires=[questionnaire], textanswer_visibility=Contribution.TextAnswerVisibility.OWN_TEXTANSWERS)
        cls.other_contributor_2 = baker.make(UserProfile, email='other_contributor_2@institution.example.com')
        baker.make(Contribution, evaluation=cls.evaluation, contributor=cls.other_contributor_2, questionnaires=[questionnaire], textanswer_visibility=Contribution.TextAnswerVisibility.OWN_TEXTANSWERS)

    def test_contributor_list(self):
        url = '/results/semester/{}/evaluation/{}?view=export'.format(self.semester.id, self.evaluation.id)
        page = self.app.get(url, user="responsible@institution.example.com")
        self.assertIn("<li>{}</li>".format(self.other_contributor_1.full_name), page)
        self.assertIn("<li>{}</li>".format(self.other_contributor_2.full_name), page)


class TestResultsTextanswerVisibilityForExportView(WebTest):
    fixtures = ['minimal_test_data_results']

    @classmethod
    def setUpTestData(cls):
        manager_group = Group.objects.get(name="Manager")
        cls.manager = baker.make(UserProfile, email="manager@institution.example.com", groups=[manager_group])

    def test_textanswer_visibility_for_responsible(self):
        page = self.app.get("/results/semester/1/evaluation/1?view=export", user="responsible@institution.example.com")

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
        page = self.app.get("/results/semester/1/evaluation/1?view=export", user="responsible_contributor@institution.example.com")

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
        page = self.app.get("/results/semester/1/evaluation/1?view=export", user="contributor@institution.example.com")

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
        page = self.app.get("/results/semester/1/evaluation/1?view=export", user="contributor_general_textanswers@institution.example.com")

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
        page = self.app.get("/results/semester/1/evaluation/1?view=export", user="student@institution.example.com")

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
        contributor_id = UserProfile.objects.get(email="responsible@institution.example.com").id
        page = self.app.get("/results/semester/1/evaluation/1?view=export&contributor_id={}".format(contributor_id), user="manager@institution.example.com")

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
        contributor = UserProfile.objects.get(email="contributor@institution.example.com")
        contributor.groups.add(manager_group)
        page = self.app.get("/results/semester/1/evaluation/1?view=export&contributor_id={}".format(contributor.id), user="contributor@institution.example.com")

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
        cls.semester = baker.make(Semester)
        baker.make(UserProfile, email="manager@institution.example.com", groups=[Group.objects.get(name='Manager')])
        baker.make(UserProfile, email="reviewer@institution.example.com", groups=[Group.objects.get(name='Reviewer')])
        student = baker.make(UserProfile, email="student@institution.example.com")
        student_external = baker.make(UserProfile, email="student_external@example.com")
        contributor = baker.make(UserProfile, email="contributor@institution.example.com")
        responsible = baker.make(UserProfile, email="responsible@institution.example.com")

        course = baker.make(Course, semester=cls.semester, degrees=[baker.make(Degree)], responsibles=[responsible])
        cls.evaluation = baker.make(Evaluation, course=course, state='published', participants=[student, student_external], voters=[student, student_external])
        cls.evaluation.general_contribution.questionnaires.set([baker.make(Questionnaire)])
        cls.contribution = baker.make(Contribution, evaluation=cls.evaluation, can_edit=True, textanswer_visibility=Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS, contributor=responsible)
        cls.contribution = baker.make(Contribution, evaluation=cls.evaluation, contributor=contributor)

    @patch('evap.results.templatetags.results_templatetags.get_grade_color', new=lambda x: (0, 0, 0))
    def test_unarchived_results(self):
        url = '/results/'
        self.assertIn(self.evaluation.full_name, self.app.get(url, user="student@institution.example.com"))
        self.assertIn(self.evaluation.full_name, self.app.get(url, user="responsible@institution.example.com"))
        self.assertIn(self.evaluation.full_name, self.app.get(url, user="contributor@institution.example.com"))
        self.assertIn(self.evaluation.full_name, self.app.get(url, user="manager@institution.example.com"))
        self.assertIn(self.evaluation.full_name, self.app.get(url, user="reviewer@institution.example.com"))
        self.app.get(url, user="student_external@example.com", status=403)  # external users can't see results semester view

        url = '/results/semester/%s/evaluation/%s' % (self.semester.id, self.evaluation.id)
        self.app.get(url, user="student@institution.example.com", status=200)
        self.app.get(url, user="responsible@institution.example.com", status=200)
        self.app.get(url, user="contributor@institution.example.com", status=200)
        self.app.get(url, user="manager@institution.example.com", status=200)
        self.app.get(url, user="reviewer@institution.example.com", status=200)
        self.app.get(url, user="student_external@example.com", status=200)

    def test_archived_results(self):
        self.semester.archive_results()

        url = '/results/semester/%s/evaluation/%s' % (self.semester.id, self.evaluation.id)
        self.app.get(url, user="student@institution.example.com", status=403)
        self.app.get(url, user="responsible@institution.example.com", status=200)
        self.app.get(url, user="contributor@institution.example.com", status=200)
        self.app.get(url, user="manager@institution.example.com", status=200)
        self.app.get(url, user="reviewer@institution.example.com", status=403)
        self.app.get(url, user="student_external@example.com", status=403)


class TestTextAnswerExportView(WebTest):

    @classmethod
    def setUpTestData(cls):
        baker.make(UserProfile, email="reviewer@institution.example.com", groups=[Group.objects.get(name="Reviewer")])
        evaluation = baker.make(Evaluation)
        cls.url = f"/results/evaluation/{evaluation.id}/text_answers_export"

    def test_file_sent(self):
        def mock(_self, res):
            res.write(b"1337")

        with patch.object(TextAnswerExcelExporter, "export", mock):
            response = self.app.get(self.url, user="reviewer@institution.example.com", status=200)
            self.assertEqual(response.headers["Content-Type"], "application/vnd.ms-excel")
            self.assertEqual(response.content, b"1337")

    @patch("evap.results.exporters.TextAnswerExcelExporter.export")
    def test_permission_denied(self, export_method):
        baker.make(UserProfile, email="student@institution.example.com")
        baker.make(UserProfile, email="manager@institution.example.com", groups=[Group.objects.get(name="Manager")])

        self.app.get(self.url, user="student@institution.example.com", status=403)
        export_method.assert_not_called()

        self.app.get(self.url, user="reviewer@institution.example.com", status=200)
        export_method.assert_called_once()

        export_method.reset_mock()
        self.app.get(self.url, user="manager@institution.example.com", status=200)
        export_method.assert_called_once()
