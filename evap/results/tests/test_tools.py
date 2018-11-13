from django.conf import settings
from django.core.cache import caches
from django.test import override_settings
from django.test.testcases import TestCase
from model_mommy import mommy

from evap.evaluation.models import Contribution, Course, Question, Questionnaire, RatingAnswerCounter, TextAnswer, UserProfile
from evap.results.tools import calculate_average_distribution, collect_results, distribution_to_grade, \
    get_collect_results_cache_key, get_single_result_rating_result, textanswers_visible_to
from evap.results.views import user_can_see_textanswer
from evap.staff.tools import merge_users


class TestCalculateResults(TestCase):
    def test_caches_published_course(self):
        course = mommy.make(Course, state='published')

        self.assertIsNone(caches['results'].get(get_collect_results_cache_key(course)))

        collect_results(course)

        self.assertIsNotNone(caches['results'].get(get_collect_results_cache_key(course)))

    def test_cache_unpublished_course(self):
        course = mommy.make(Course, state='published', _voter_count=0, _participant_count=0)
        collect_results(course)
        course.unpublish()

        self.assertIsNone(caches['results'].get(get_collect_results_cache_key(course)))

    def test_calculation_results(self):
        contributor1 = mommy.make(UserProfile)
        student = mommy.make(UserProfile)

        course = mommy.make(Course, state='published', participants=[student, contributor1], voters=[student, contributor1])
        questionnaire = mommy.make(Questionnaire)
        question = mommy.make(Question, questionnaire=questionnaire, type=Question.GRADE)
        contribution1 = mommy.make(Contribution, contributor=contributor1, course=course, questionnaires=[questionnaire])

        mommy.make(RatingAnswerCounter, question=question, contribution=contribution1, answer=1, count=5)
        mommy.make(RatingAnswerCounter, question=question, contribution=contribution1, answer=2, count=15)
        mommy.make(RatingAnswerCounter, question=question, contribution=contribution1, answer=3, count=40)
        mommy.make(RatingAnswerCounter, question=question, contribution=contribution1, answer=4, count=60)
        mommy.make(RatingAnswerCounter, question=question, contribution=contribution1, answer=5, count=30)

        course_results = collect_results(course)

        self.assertEqual(len(course_results.questionnaire_results), 1)
        questionnaire_result = course_results.questionnaire_results[0]
        self.assertEqual(len(questionnaire_result.question_results), 1)
        question_result = questionnaire_result.question_results[0]

        self.assertEqual(question_result.count_sum, 150)
        self.assertAlmostEqual(question_result.average, float(109) / 30)
        self.assertEqual(question_result.counts, (5, 15, 40, 60, 30))

    def test_collect_results_after_user_merge(self):
        """ Asserts that merge_users leaves the results cache in a consistent state. Regression test for #907 """
        contributor = mommy.make(UserProfile)
        main_user = mommy.make(UserProfile)
        student = mommy.make(UserProfile)

        course = mommy.make(Course, state='published', participants=[student])
        questionnaire = mommy.make(Questionnaire)
        mommy.make(Question, questionnaire=questionnaire, type=Question.GRADE)
        mommy.make(Contribution, contributor=contributor, course=course, questionnaires=[questionnaire])

        collect_results(course)

        merge_users(main_user, contributor)

        course_results = collect_results(course)

        for contribution_result in course_results.contribution_results:
            self.assertTrue(Contribution.objects.filter(course=course, contributor=contribution_result.contributor).exists())


class TestCalculateAverageDistribution(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.student1 = mommy.make(UserProfile)
        cls.student2 = mommy.make(UserProfile)

        cls.course = mommy.make(Course, state='published', participants=[cls.student1, cls.student2], voters=[cls.student1, cls.student2])
        cls.questionnaire = mommy.make(Questionnaire)
        cls.question_grade = mommy.make(Question, questionnaire=cls.questionnaire, type=Question.GRADE)
        cls.question_likert = mommy.make(Question, questionnaire=cls.questionnaire, type=Question.LIKERT)
        cls.question_likert_2 = mommy.make(Question, questionnaire=cls.questionnaire, type=Question.LIKERT)
        cls.general_contribution = cls.course.general_contribution
        cls.general_contribution.questionnaires.set([cls.questionnaire])
        cls.contribution1 = mommy.make(Contribution, contributor=mommy.make(UserProfile), course=cls.course, questionnaires=[cls.questionnaire])
        cls.contribution2 = mommy.make(Contribution, contributor=mommy.make(UserProfile), course=cls.course, questionnaires=[cls.questionnaire])

    @override_settings(CONTRIBUTOR_GRADE_QUESTIONS_WEIGHT=4, CONTRIBUTOR_NON_GRADE_RATING_QUESTIONS_WEIGHT=6, CONTRIBUTIONS_WEIGHT=3, GENERAL_GRADE_QUESTIONS_WEIGHT=2, GENERAL_NON_GRADE_QUESTIONS_WEIGHT=5)
    def test_average_grade(self):
        question_grade2 = mommy.make(Question, questionnaire=self.questionnaire, type=Question.GRADE)

        mommy.make(RatingAnswerCounter, question=self.question_grade, contribution=self.contribution1, answer=2, count=1)
        mommy.make(RatingAnswerCounter, question=self.question_grade, contribution=self.contribution2, answer=4, count=2)
        mommy.make(RatingAnswerCounter, question=question_grade2, contribution=self.contribution1, answer=1, count=1)
        mommy.make(RatingAnswerCounter, question=self.question_likert, contribution=self.contribution1, answer=3, count=4)
        mommy.make(RatingAnswerCounter, question=self.question_likert, contribution=self.general_contribution, answer=5, count=5)
        mommy.make(RatingAnswerCounter, question=self.question_likert_2, contribution=self.general_contribution, answer=3, count=3)

        contributor_weights_sum = settings.CONTRIBUTOR_GRADE_QUESTIONS_WEIGHT + settings.CONTRIBUTOR_NON_GRADE_RATING_QUESTIONS_WEIGHT
        contributor1_average = ((settings.CONTRIBUTOR_GRADE_QUESTIONS_WEIGHT * ((2 * 1) + (1 * 1)) / (1 + 1)) + (settings.CONTRIBUTOR_NON_GRADE_RATING_QUESTIONS_WEIGHT * 3)) / contributor_weights_sum  # 2.4
        contributor2_average = 4
        contributors_average = ((4 * contributor1_average) + (2 * contributor2_average)) / (4 + 2)  # 2.9333333

        course_non_grade_average = ((5 * 5) + (3 * 3)) / (5 + 3)  # 4.25

        contributors_percentage = settings.CONTRIBUTIONS_WEIGHT / (settings.CONTRIBUTIONS_WEIGHT + settings.GENERAL_NON_GRADE_QUESTIONS_WEIGHT)  # 0.375
        course_non_grade_percentage = settings.GENERAL_NON_GRADE_QUESTIONS_WEIGHT / (settings.CONTRIBUTIONS_WEIGHT + settings.GENERAL_NON_GRADE_QUESTIONS_WEIGHT)  # 0.625

        total_grade = contributors_percentage * contributors_average + course_non_grade_percentage * course_non_grade_average  # 1.1 + 2.65625 = 3.75625

        average_grade = distribution_to_grade(calculate_average_distribution(self.course))
        self.assertAlmostEqual(average_grade, total_grade)
        self.assertAlmostEqual(average_grade, 3.75625)

    @override_settings(CONTRIBUTOR_GRADE_QUESTIONS_WEIGHT=4, CONTRIBUTOR_NON_GRADE_RATING_QUESTIONS_WEIGHT=6, CONTRIBUTIONS_WEIGHT=3, GENERAL_GRADE_QUESTIONS_WEIGHT=2, GENERAL_NON_GRADE_QUESTIONS_WEIGHT=5)
    def test_distribution_without_course_grade_question(self):
        mommy.make(RatingAnswerCounter, question=self.question_grade, contribution=self.contribution1, answer=1, count=1)
        mommy.make(RatingAnswerCounter, question=self.question_grade, contribution=self.contribution1, answer=3, count=1)
        mommy.make(RatingAnswerCounter, question=self.question_grade, contribution=self.contribution2, answer=4, count=1)
        mommy.make(RatingAnswerCounter, question=self.question_grade, contribution=self.contribution2, answer=2, count=1)
        mommy.make(RatingAnswerCounter, question=self.question_likert, contribution=self.contribution1, answer=3, count=3)
        mommy.make(RatingAnswerCounter, question=self.question_likert, contribution=self.contribution1, answer=5, count=3)
        mommy.make(RatingAnswerCounter, question=self.question_likert, contribution=self.general_contribution, answer=5, count=5)
        mommy.make(RatingAnswerCounter, question=self.question_likert_2, contribution=self.general_contribution, answer=3, count=3)

        # contribution1: 0.4 * (0.5, 0, 0.5, 0, 0) + 0.6 * (0, 0, 0.5, 0, 0.5) = (0.2, 0, 0.5, 0, 0.3)
        # contribution2: (0, 0.5, 0, 0.5, 0)
        # contributions: (6 / 8) * (0.2, 0, 0.5, 0, 0.3) + (2 / 8) * (0, 0.5, 0, 0.5, 0) = (0.15, 0.125, 0.375, 0.125, 0.225)

        # course_non_grade: (0, 0, 0.375, 0, 0.625)

        # total: 0.375 * (0.15, 0.125, 0.375, 0.125, 0.225) + 0.625 * (0, 0, 0.375, 0, 0.625) = (0.05625, 0.046875, 0.375, 0.046875, 0.475)

        distribution = calculate_average_distribution(self.course)
        self.assertAlmostEqual(distribution[0], 0.05625)
        self.assertAlmostEqual(distribution[1], 0.046875)
        self.assertAlmostEqual(distribution[2], 0.375)
        self.assertAlmostEqual(distribution[3], 0.046875)
        self.assertAlmostEqual(distribution[4], 0.475)

    @override_settings(CONTRIBUTOR_GRADE_QUESTIONS_WEIGHT=4, CONTRIBUTOR_NON_GRADE_RATING_QUESTIONS_WEIGHT=6, CONTRIBUTIONS_WEIGHT=3, GENERAL_GRADE_QUESTIONS_WEIGHT=2, GENERAL_NON_GRADE_QUESTIONS_WEIGHT=5)
    def test_distribution_with_course_grade_question(self):
        mommy.make(RatingAnswerCounter, question=self.question_grade, contribution=self.contribution1, answer=1, count=1)
        mommy.make(RatingAnswerCounter, question=self.question_grade, contribution=self.contribution1, answer=3, count=1)
        mommy.make(RatingAnswerCounter, question=self.question_grade, contribution=self.contribution2, answer=4, count=1)
        mommy.make(RatingAnswerCounter, question=self.question_grade, contribution=self.contribution2, answer=2, count=1)
        mommy.make(RatingAnswerCounter, question=self.question_likert, contribution=self.contribution1, answer=3, count=3)
        mommy.make(RatingAnswerCounter, question=self.question_likert, contribution=self.contribution1, answer=5, count=3)
        mommy.make(RatingAnswerCounter, question=self.question_likert, contribution=self.general_contribution, answer=5, count=5)
        mommy.make(RatingAnswerCounter, question=self.question_likert_2, contribution=self.general_contribution, answer=3, count=3)
        mommy.make(RatingAnswerCounter, question=self.question_grade, contribution=self.general_contribution, answer=2, count=10)

        # contributions and course_non_grade are as above
        # course_grade: (0, 1, 0, 0, 0)

        # total: 0.3 * (0.15, 0.125, 0.375, 0.125, 0.225) + 0.2 * (0, 1, 0, 0, 0) + 0.5 * (0, 0, 0.375, 0, 0.625) = (0.045, 0.2375, 0.3, 0.0375, 0.38)

        distribution = calculate_average_distribution(self.course)
        self.assertAlmostEqual(distribution[0], 0.045)
        self.assertAlmostEqual(distribution[1], 0.2375)
        self.assertAlmostEqual(distribution[2], 0.3)
        self.assertAlmostEqual(distribution[3], 0.0375)
        self.assertAlmostEqual(distribution[4], 0.38)

    def test_get_single_result_rating_result(self):
        single_result_course = mommy.make(Course, state='published', is_single_result=True)
        questionnaire = Questionnaire.objects.get(name_en=Questionnaire.SINGLE_RESULT_QUESTIONNAIRE_NAME)
        contribution = mommy.make(Contribution, contributor=mommy.make(UserProfile), course=single_result_course, questionnaires=[questionnaire], responsible=True, can_edit=True, textanswer_visibility=Contribution.GENERAL_TEXTANSWERS)
        mommy.make(RatingAnswerCounter, question=questionnaire.questions.first(), contribution=contribution, answer=1, count=1)
        mommy.make(RatingAnswerCounter, question=questionnaire.questions.first(), contribution=contribution, answer=4, count=1)
        distribution = calculate_average_distribution(single_result_course)
        self.assertEqual(distribution, (0.5, 0, 0, 0.5, 0))
        rating_result = get_single_result_rating_result(single_result_course)
        self.assertEqual(rating_result.counts, (1, 0, 0, 1, 0))

    def test_result_calculation_with_no_contributor_rating_question_does_not_fail(self):
        course = mommy.make(Course, state='published', participants=[self.student1, self.student2], voters=[self.student1, self.student2])
        questionnaire_text = mommy.make(Questionnaire)
        mommy.make(Question, questionnaire=questionnaire_text, type=Question.TEXT)
        mommy.make(Contribution, contributor=mommy.make(UserProfile), course=course, questionnaires=[questionnaire_text])

        course.general_contribution.questionnaires.set([self.questionnaire])
        mommy.make(RatingAnswerCounter, question=self.question_grade, contribution=course.general_contribution, answer=1, count=1)

        distribution = calculate_average_distribution(course)
        self.assertEqual(distribution[0], 1)


class TestTextAnswerVisibilityInfo(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.delegate1 = mommy.make(UserProfile, username="delegate1")
        cls.delegate2 = mommy.make(UserProfile, username="delegate2")
        cls.contributor_own = mommy.make(UserProfile, username="contributor_own", delegates=[cls.delegate1])
        cls.contributor_general = mommy.make(UserProfile, username="contributor_general", delegates=[cls.delegate2])
        cls.responsible1 = mommy.make(UserProfile, username="responsible1", delegates=[cls.delegate1, cls.contributor_general])
        cls.responsible2 = mommy.make(UserProfile, username="responsible2")
        cls.other_user = mommy.make(UserProfile, username="other_user")

        cls.course = mommy.make(Course, state='published', can_publish_text_results=True)
        cls.questionnaire = mommy.make(Questionnaire)
        cls.question = mommy.make(Question, questionnaire=cls.questionnaire, type=Question.TEXT)
        cls.general_contribution = cls.course.general_contribution
        cls.general_contribution.questionnaires.set([cls.questionnaire])
        cls.responsible1_contribution = mommy.make(Contribution, contributor=cls.responsible1, course=cls.course,
            questionnaires=[cls.questionnaire], responsible=True, can_edit=True, textanswer_visibility=Contribution.GENERAL_TEXTANSWERS)
        cls.responsible2_contribution = mommy.make(Contribution, contributor=cls.responsible2, course=cls.course,
            questionnaires=[cls.questionnaire], responsible=True, can_edit=True, textanswer_visibility=Contribution.GENERAL_TEXTANSWERS)
        cls.contributor_own_contribution = mommy.make(Contribution, contributor=cls.contributor_own, course=cls.course,
            questionnaires=[cls.questionnaire], textanswer_visibility=Contribution.OWN_TEXTANSWERS)
        cls.contributor_general_contribution = mommy.make(Contribution, contributor=cls.contributor_general, course=cls.course,
            questionnaires=[cls.questionnaire], textanswer_visibility=Contribution.GENERAL_TEXTANSWERS)
        cls.general_contribution_textanswer = mommy.make(TextAnswer, question=cls.question, contribution=cls.general_contribution, state=TextAnswer.PUBLISHED)
        cls.responsible1_textanswer = mommy.make(TextAnswer, question=cls.question, contribution=cls.responsible1_contribution, state=TextAnswer.PUBLISHED)
        cls.responsible2_textanswer = mommy.make(TextAnswer, question=cls.question, contribution=cls.responsible2_contribution, state=TextAnswer.PUBLISHED)
        cls.contributor_own_textanswer = mommy.make(TextAnswer, question=cls.question, contribution=cls.contributor_own_contribution, state=TextAnswer.PUBLISHED)
        cls.contributor_general_textanswer = mommy.make(TextAnswer, question=cls.question, contribution=cls.contributor_general_contribution, state=TextAnswer.PUBLISHED)

    def test_correct_contributors_and_delegate_count_are_shown_in_textanswer_visibility_info(self):
        textanswers = [
            self.general_contribution_textanswer, self.responsible1_textanswer, self.responsible2_textanswer,
            self.contributor_own_textanswer, self.contributor_general_textanswer
        ]
        visible_to = [textanswers_visible_to(textanswer.contribution) for textanswer in textanswers]
        users_seeing_contribution = [(set(), set()) for _ in range(len(textanswers))]

        for user in UserProfile.objects.all():
            represented_users = [user] + list(user.represented_users.all())
            for i in range(len(textanswers)):
                if user_can_see_textanswer(user, represented_users, textanswers[i], 'full'):
                    if user_can_see_textanswer(user, [user], textanswers[i], 'full'):
                        users_seeing_contribution[i][0].add(user)
                    else:
                        users_seeing_contribution[i][1].add(user)

        for i in range(len(textanswers)):
            self.assertCountEqual(visible_to[i][0], users_seeing_contribution[i][0])

        expected_delegate_counts = [
            2,  # delegate1, delegate2
            2,  # delegate1, contributor_general
            0,
            1,  # delegate1
            1,  # delegate2
        ]

        for i in range(len(textanswers)):
            self.assertTrue(visible_to[i][1] == len(users_seeing_contribution[i][1]) == expected_delegate_counts[i])
