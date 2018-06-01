
from django.test.testcases import TestCase
from django.core.cache import caches
from django.conf import settings
from django.test import override_settings

from model_mommy import mommy

from evap.evaluation.models import Contribution, RatingAnswerCounter, Questionnaire, Question, Course, UserProfile
from evap.results.tools import get_answers, get_answers_from_answer_counters, get_results_cache_key, calculate_average_distribution, calculate_results, distribution_to_grade
from evap.staff.tools import merge_users


class TestCalculateResults(TestCase):
    def test_caches_published_course(self):
        course = mommy.make(Course, state='published')

        self.assertIsNone(caches['results'].get(get_results_cache_key(course)))

        calculate_results(course)

        self.assertIsNotNone(caches['results'].get(get_results_cache_key(course)))

    def test_cache_unpublished_course(self):
        course = mommy.make(Course, state='published')
        calculate_results(course)
        course.unpublish()

        self.assertIsNone(caches['results'].get(get_results_cache_key(course)))

    def test_calculation_results(self):
        contributor1 = mommy.make(UserProfile)
        student = mommy.make(UserProfile)

        course = mommy.make(Course, state='published', participants=[student, contributor1], voters=[student, contributor1])
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
        self.assertEqual(result.counts, (5, 15, 40, 60, 30))

    def test_calculate_results_after_user_merge(self):
        """ Asserts that merge_users leaves the results cache in a consistent state. Regression test for #907 """
        contributor = mommy.make(UserProfile)
        main_user = mommy.make(UserProfile)
        student = mommy.make(UserProfile)

        course = mommy.make(Course, state='published', participants=[student])
        questionnaire = mommy.make(Questionnaire)
        mommy.make(Question, questionnaire=questionnaire, type="G")
        mommy.make(Contribution, contributor=contributor, course=course, questionnaires=[questionnaire])

        calculate_results(course)

        merge_users(main_user, contributor)

        results = calculate_results(course)

        for section in results:
            self.assertTrue(Contribution.objects.filter(course=course, contributor=section.contributor).exists())

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

    @override_settings(CONTRIBUTOR_GRADE_QUESTIONS_WEIGHT=4, CONTRIBUTOR_NON_GRADE_QUESTIONS_WEIGHT=6, CONTRIBUTIONS_WEIGHT=3, COURSE_GRADE_QUESTIONS_WEIGHT=2, COURSE_NON_GRADE_QUESTIONS_WEIGHT=5)
    def test_average_grade(self):
        contributor1 = mommy.make(UserProfile)
        contributor2 = mommy.make(UserProfile)
        student1 = mommy.make(UserProfile)
        student2 = mommy.make(UserProfile)

        course = mommy.make(Course, participants=[student1, student2], voters=[student1, student2])
        questionnaire = mommy.make(Questionnaire)
        question_grade = mommy.make(Question, questionnaire=questionnaire, type="G")
        question_grade2 = mommy.make(Question, questionnaire=questionnaire, type="G")
        question_likert = mommy.make(Question, questionnaire=questionnaire, type="L")
        general_contribution = mommy.make(Contribution, contributor=None, course=course, questionnaires=[questionnaire])
        contribution1 = mommy.make(Contribution, contributor=contributor1, course=course, questionnaires=[questionnaire])
        contribution2 = mommy.make(Contribution, contributor=contributor2, course=course, questionnaires=[questionnaire])

        mommy.make(RatingAnswerCounter, question=question_grade, contribution=contribution1, answer=2, count=1)
        mommy.make(RatingAnswerCounter, question=question_grade, contribution=contribution2, answer=4, count=2)
        mommy.make(RatingAnswerCounter, question=question_grade2, contribution=contribution1, answer=1, count=1)
        mommy.make(RatingAnswerCounter, question=question_likert, contribution=contribution1, answer=3, count=4)
        mommy.make(RatingAnswerCounter, question=question_likert, contribution=general_contribution, answer=5, count=3)

        contributor_weights_sum = settings.CONTRIBUTOR_GRADE_QUESTIONS_WEIGHT + settings.CONTRIBUTOR_NON_GRADE_QUESTIONS_WEIGHT
        contributor1_average = (settings.CONTRIBUTOR_GRADE_QUESTIONS_WEIGHT * (2 + 1) / 2 + (settings.CONTRIBUTOR_NON_GRADE_QUESTIONS_WEIGHT) * 3) / contributor_weights_sum  # 2.4
        contributor2_average = 4
        contributors_average = (contributor1_average + contributor2_average) / 2  # 3.2

        course_non_grade_average = 5

        contributors_percentage = settings.CONTRIBUTIONS_WEIGHT / (settings.CONTRIBUTIONS_WEIGHT + settings.COURSE_NON_GRADE_QUESTIONS_WEIGHT)  # 0.375
        course_non_grade_percentage = settings.COURSE_NON_GRADE_QUESTIONS_WEIGHT / (settings.CONTRIBUTIONS_WEIGHT + settings.COURSE_NON_GRADE_QUESTIONS_WEIGHT)  # 0.625

        total_grade = contributors_percentage * contributors_average + course_non_grade_percentage * course_non_grade_average  # 1.2 + 3.125 = 4.325

        average_grade = distribution_to_grade(calculate_average_distribution(course))
        self.assertAlmostEqual(average_grade, total_grade)
        self.assertAlmostEqual(average_grade, 4.325)

    @override_settings(CONTRIBUTOR_GRADE_QUESTIONS_WEIGHT=4, CONTRIBUTOR_NON_GRADE_QUESTIONS_WEIGHT=6, CONTRIBUTIONS_WEIGHT=3, COURSE_GRADE_QUESTIONS_WEIGHT=2, COURSE_NON_GRADE_QUESTIONS_WEIGHT=5)
    def test_distribution_without_course_grade_question(self):
        contributor1 = mommy.make(UserProfile)
        contributor2 = mommy.make(UserProfile)
        student1 = mommy.make(UserProfile)
        student2 = mommy.make(UserProfile)

        course = mommy.make(Course, participants=[student1, student2], voters=[student1, student2])
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

        # contribution1: 0.4 * (0.5, 0, 0.5, 0, 0) + 0.6 * (0, 0, 0.5, 0, 0.5) = (0.2, 0, 0.5, 0, 0.3)
        # contribution2: (0, 0.5, 0, 0.5, 0)
        # contributions: (0.1, 0.25, 0.25, 0.25, 0.15)

        # course_non_grade: (0, 0, 0, 0, 1)

        # total: 0.375 * (0.1, 0.25, 0.25, 0.25, 0.15) + 0.625 * (0, 0, 0, 0, 1) = (0.0375, 0.09375, 0.09375, 0.09375, 0.68125)

        distribution = calculate_average_distribution(course)
        self.assertAlmostEqual(distribution[0], 0.0375)
        self.assertAlmostEqual(distribution[1], 0.09375)
        self.assertAlmostEqual(distribution[2], 0.09375)
        self.assertAlmostEqual(distribution[3], 0.09375)
        self.assertAlmostEqual(distribution[4], 0.68125)

    @override_settings(CONTRIBUTOR_GRADE_QUESTIONS_WEIGHT=4, CONTRIBUTOR_NON_GRADE_QUESTIONS_WEIGHT=6, CONTRIBUTIONS_WEIGHT=3, COURSE_GRADE_QUESTIONS_WEIGHT=2, COURSE_NON_GRADE_QUESTIONS_WEIGHT=5)
    def test_distribution_with_course_grade_question(self):
        contributor1 = mommy.make(UserProfile)
        contributor2 = mommy.make(UserProfile)
        student1 = mommy.make(UserProfile)
        student2 = mommy.make(UserProfile)

        course = mommy.make(Course, participants=[student1, student2], voters=[student1, student2])
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
        mommy.make(RatingAnswerCounter, question=question_grade, contribution=general_contribution, answer=2, count=10)

        # contributions and course_non_grade are as above
        # course_grade: (0, 1, 0, 0, 0)

        # total: 0.3 * (0.1, 0.25, 0.25, 0.25, 0.15) + 0.2 * (0, 1, 0, 0, 0) + 0.5 * (0, 0, 0, 0, 1) = (0.03, 0.275, 0.075, 0.075, 0.545)

        distribution = calculate_average_distribution(course)
        self.assertAlmostEqual(distribution[0], 0.03)
        self.assertAlmostEqual(distribution[1], 0.275)
        self.assertAlmostEqual(distribution[2], 0.075)
        self.assertAlmostEqual(distribution[3], 0.075)
        self.assertAlmostEqual(distribution[4], 0.545)
