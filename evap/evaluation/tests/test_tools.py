from django.core.cache import cache
from django.core.urlresolvers import reverse
from django.test.testcases import TestCase
from django.conf import settings
from django.test import override_settings

from evap.evaluation.models import Contribution, RatingAnswerCounter, Questionnaire, Question
from evap.evaluation.tools import get_answers, get_answers_from_answer_counters, calculate_average_grades_and_deviation
from django.utils import translation
from model_mommy import mommy

from evap.evaluation.models import Course, UserProfile
from evap.evaluation.tests.tools import WebTest
from evap.evaluation.tools import calculate_results, set_or_get_language


class TestCalculateResults(TestCase):
    def test_caches_published_course(self):
        course = mommy.make(Course, state='published')

        self.assertIsNone(cache.get('evap.staff.results.tools.calculate_results-{:d}'.format(course.id)))

        calculate_results(course)

        self.assertIsNotNone(cache.get('evap.staff.results.tools.calculate_results-{:d}'.format(course.id)))

    def test_calculation_results(self):
        contributor1 = mommy.make(UserProfile)
        student = mommy.make(UserProfile)

        course = mommy.make(Course, state='published', participants=[student, contributor1])
        questionnaire = mommy.make(Questionnaire)
        question = mommy.make(Question, questionnaire=questionnaire, type="G")
        contribution1 = mommy.make(Contribution, contributor=contributor1, course=course, questionnaires=[questionnaire])

        mommy.make(RatingAnswerCounter, question=question, contribution=contribution1, answer=1, count=5)
        mommy.make(RatingAnswerCounter, question=question, contribution=contribution1, answer=2, count=15)
        mommy.make(RatingAnswerCounter, question=question, contribution=contribution1, answer=3, count=40)
        mommy.make(RatingAnswerCounter, question=question, contribution=contribution1, answer=4, count=60)
        mommy.make(RatingAnswerCounter, question=question, contribution=contribution1, answer=5, count=30)

        results = calculate_results(course)

        self.assertEqual(len(results), 1)
        self.assertEqual(len(results[0].results), 1)
        result = results[0].results[0]

        self.assertEqual(result.total_count, 150)
        self.assertAlmostEqual(result.average, float(109) / 30)
        self.assertAlmostEqual(result.deviation, 1.015983376941878)

    def test_answer_counting(self):
        contributor1 = mommy.make(UserProfile)
        contributor2 = mommy.make(UserProfile)
        student = mommy.make(UserProfile)

        course1 = mommy.make(Course, state='published', participants=[student, contributor1])
        questionnaire = mommy.make(Questionnaire)
        question1 = mommy.make(Question, questionnaire=questionnaire, type="G")
        question2 = mommy.make(Question, questionnaire=questionnaire, type="G")
        contribution1 = mommy.make(Contribution, contributor=contributor1, course=course1, questionnaires=[questionnaire])
        contribution2 = mommy.make(Contribution, contributor=contributor1, questionnaires=[questionnaire])
        contribution3 = mommy.make(Contribution, contributor=contributor2, course=course1, questionnaires=[questionnaire])

        rating_answer_counters = []
        rating_answer_counters.append(mommy.make(RatingAnswerCounter, question=question1, contribution=contribution1, answer=1, count=1))
        rating_answer_counters.append(mommy.make(RatingAnswerCounter, question=question1, contribution=contribution1, answer=3, count=4))
        rating_answer_counters.append(mommy.make(RatingAnswerCounter, question=question1, contribution=contribution1, answer=4, count=2))
        rating_answer_counters.append(mommy.make(RatingAnswerCounter, question=question1, contribution=contribution1, answer=5, count=3))

        # create some unrelated answer counters for different questions / contributions
        mommy.make(RatingAnswerCounter, question=question1, contribution=contribution2, answer=1, count=1)
        mommy.make(RatingAnswerCounter, question=question1, contribution=contribution3, answer=1, count=1)
        mommy.make(RatingAnswerCounter, question=question2, contribution=contribution1, answer=1, count=1)

        answer_counters = get_answers(contribution1, question1)
        self.assertSetEqual(set(rating_answer_counters), set(answer_counters))

        answers = get_answers_from_answer_counters(answer_counters)
        self.assertListEqual(answers, [1, 3, 3, 3, 3, 4, 4, 5, 5, 5])

    @override_settings(CONTRIBUTION_PERCENTAGE=0.3, GRADE_PERCENTAGE=0.6)
    def test_average_grades(self):
        contributor1 = mommy.make(UserProfile)
        contributor2 = mommy.make(UserProfile)

        course = mommy.make(Course)
        questionnaire = mommy.make(Questionnaire)
        question_grade = mommy.make(Question, questionnaire=questionnaire, type="G")
        question_likert = mommy.make(Question, questionnaire=questionnaire, type="L")
        general_contribution = mommy.make(Contribution, contributor=None, course=course, questionnaires=[questionnaire])
        contribution1 = mommy.make(Contribution, contributor=contributor1, course=course, questionnaires=[questionnaire])
        contribution2 = mommy.make(Contribution, contributor=contributor2, course=course, questionnaires=[questionnaire])

        mommy.make(RatingAnswerCounter, question=question_grade, contribution=contribution1, answer=1, count=1)
        mommy.make(RatingAnswerCounter, question=question_grade, contribution=contribution2, answer=4, count=2)
        mommy.make(RatingAnswerCounter, question=question_likert, contribution=contribution1, answer=3, count=4)
        mommy.make(RatingAnswerCounter, question=question_likert, contribution=general_contribution, answer=5, count=3)

        total_likert = settings.CONTRIBUTION_PERCENTAGE * 3 + (1 - settings.CONTRIBUTION_PERCENTAGE) * 5
        total_grade = 2.5
        total = settings.GRADE_PERCENTAGE * total_grade + (1 - settings.GRADE_PERCENTAGE) * total_likert

        average, deviation = calculate_average_grades_and_deviation(course)

        self.assertAlmostEqual(average, total)
        self.assertAlmostEqual(deviation, 0)

    @override_settings(CONTRIBUTION_PERCENTAGE=0.3, GRADE_PERCENTAGE=0.6)
    def test_average_deviation(self):
        contributor1 = mommy.make(UserProfile)
        contributor2 = mommy.make(UserProfile)

        course = mommy.make(Course)
        questionnaire = mommy.make(Questionnaire)
        question_grade = mommy.make(Question, questionnaire=questionnaire, type="G")
        question_likert = mommy.make(Question, questionnaire=questionnaire, type="L")
        general_contribution = mommy.make(Contribution, contributor=None, course=course, questionnaires=[questionnaire])
        contribution1 = mommy.make(Contribution, contributor=contributor1, course=course, questionnaires=[questionnaire])
        contribution2 = mommy.make(Contribution, contributor=contributor2, course=course, questionnaires=[questionnaire])

        mommy.make(RatingAnswerCounter, question=question_grade, contribution=contribution1, answer=1, count=1)
        mommy.make(RatingAnswerCounter, question=question_grade, contribution=contribution1, answer=3, count=1)
        mommy.make(RatingAnswerCounter, question=question_grade, contribution=contribution2, answer=4, count=2)
        mommy.make(RatingAnswerCounter, question=question_grade, contribution=contribution2, answer=2, count=2)
        mommy.make(RatingAnswerCounter, question=question_likert, contribution=contribution1, answer=3, count=4)
        mommy.make(RatingAnswerCounter, question=question_likert, contribution=contribution1, answer=5, count=4)
        mommy.make(RatingAnswerCounter, question=question_likert, contribution=general_contribution, answer=5, count=3)

        __, deviation = calculate_average_grades_and_deviation(course)

        total_likert_dev = settings.CONTRIBUTION_PERCENTAGE * 1 + (1 - settings.CONTRIBUTION_PERCENTAGE) * 0
        total_grade_dev = 1
        total_dev = settings.GRADE_PERCENTAGE * total_grade_dev + (1 - settings.GRADE_PERCENTAGE) * total_likert_dev

        self.assertAlmostEqual(deviation, total_dev)


class TestLanguageSignalReceiver(WebTest):
    def test_signal_sets_language_if_none(self):
        """
        Activate 'de' as language and check that user gets this as initial language as he has None.
        """
        translation.activate('de')

        user = mommy.make(UserProfile, language=None)
        user.generate_login_key()

        set_or_get_language(None, user, None)

        user.refresh_from_db()
        self.assertEqual(user.language, 'de')

    def test_signal_doesnt_set_language(self):
        """
        Activate 'en' as langauge and check, that user does not get this langauge as he has one.
        """
        translation.activate('en')
        user = mommy.make(UserProfile, language='de')
        user.generate_login_key()

        self.app.get(reverse("results:index") + "?loginkey=%s" % user.login_key)

        user.refresh_from_db()
        self.assertEqual(user.language, 'de')
