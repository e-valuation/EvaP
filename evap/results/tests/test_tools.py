from django.conf import settings
from django.core.cache import caches
from django.test import override_settings
from django.test.testcases import TestCase
from model_mommy import mommy

from evap.evaluation.models import (Contribution, Course, Evaluation, Question, Questionnaire, RatingAnswerCounter,
                                    TextAnswer, UserProfile)
from evap.results.tools import (calculate_average_distribution, collect_results, distribution_to_grade,
                                get_collect_results_cache_key, get_single_result_rating_result, normalized_distribution,
                                RatingResult, textanswers_visible_to, unipolarized_distribution)
from evap.results.views import user_can_see_textanswer
from evap.staff.tools import merge_users


class TestCalculateResults(TestCase):
    def test_caches_published_evaluation(self):
        evaluation = mommy.make(Evaluation, state='published')

        self.assertIsNone(caches['results'].get(get_collect_results_cache_key(evaluation)))

        collect_results(evaluation)

        self.assertIsNotNone(caches['results'].get(get_collect_results_cache_key(evaluation)))

    def test_cache_unpublished_evaluation(self):
        evaluation = mommy.make(Evaluation, state='published', _voter_count=0, _participant_count=0)
        collect_results(evaluation)
        evaluation.unpublish()

        self.assertIsNone(caches['results'].get(get_collect_results_cache_key(evaluation)))

    def test_calculation_unipolar_results(self):
        contributor1 = mommy.make(UserProfile)
        student = mommy.make(UserProfile)

        evaluation = mommy.make(Evaluation, state='published', participants=[student, contributor1], voters=[student, contributor1])
        questionnaire = mommy.make(Questionnaire)
        question = mommy.make(Question, questionnaire=questionnaire, type=Question.GRADE)
        contribution1 = mommy.make(Contribution, contributor=contributor1, evaluation=evaluation, questionnaires=[questionnaire])

        mommy.make(RatingAnswerCounter, question=question, contribution=contribution1, answer=1, count=5)
        mommy.make(RatingAnswerCounter, question=question, contribution=contribution1, answer=2, count=15)
        mommy.make(RatingAnswerCounter, question=question, contribution=contribution1, answer=3, count=40)
        mommy.make(RatingAnswerCounter, question=question, contribution=contribution1, answer=4, count=60)
        mommy.make(RatingAnswerCounter, question=question, contribution=contribution1, answer=5, count=30)

        evaluation_results = collect_results(evaluation)

        self.assertEqual(len(evaluation_results.questionnaire_results), 1)
        questionnaire_result = evaluation_results.questionnaire_results[0]
        self.assertEqual(len(questionnaire_result.question_results), 1)
        question_result = questionnaire_result.question_results[0]

        self.assertEqual(question_result.count_sum, 150)
        self.assertAlmostEqual(question_result.average, float(109) / 30)
        self.assertEqual(question_result.counts, (5, 15, 40, 60, 30))

    def test_calculation_bipolar_results(self):
        contributor1 = mommy.make(UserProfile)
        student = mommy.make(UserProfile)

        evaluation = mommy.make(Evaluation, state='published', participants=[student, contributor1], voters=[student, contributor1])
        questionnaire = mommy.make(Questionnaire)
        question = mommy.make(Question, questionnaire=questionnaire, type=Question.EASY_DIFFICULT)
        contribution1 = mommy.make(Contribution, contributor=contributor1, evaluation=evaluation, questionnaires=[questionnaire])

        mommy.make(RatingAnswerCounter, question=question, contribution=contribution1, answer=-3, count=5)
        mommy.make(RatingAnswerCounter, question=question, contribution=contribution1, answer=-2, count=5)
        mommy.make(RatingAnswerCounter, question=question, contribution=contribution1, answer=-1, count=15)
        mommy.make(RatingAnswerCounter, question=question, contribution=contribution1, answer=0, count=30)
        mommy.make(RatingAnswerCounter, question=question, contribution=contribution1, answer=1, count=25)
        mommy.make(RatingAnswerCounter, question=question, contribution=contribution1, answer=2, count=15)
        mommy.make(RatingAnswerCounter, question=question, contribution=contribution1, answer=3, count=10)

        evaluation_results = collect_results(evaluation)

        self.assertEqual(len(evaluation_results.questionnaire_results), 1)
        questionnaire_result = evaluation_results.questionnaire_results[0]
        self.assertEqual(len(questionnaire_result.question_results), 1)
        question_result = questionnaire_result.question_results[0]

        self.assertEqual(question_result.count_sum, 105)
        self.assertAlmostEqual(question_result.average, 2.58730158)
        self.assertEqual(question_result.counts, (5, 5, 15, 30, 25, 15, 10))
        self.assertEqual(question_result.minus_balance_count, 32.5)
        distribution = normalized_distribution(question_result.counts)
        self.assertAlmostEqual(distribution[0], 0.04761904)
        self.assertAlmostEqual(distribution[1], 0.04761904)
        self.assertAlmostEqual(distribution[2], 0.1428571)
        self.assertAlmostEqual(distribution[3], 0.28571428)
        self.assertAlmostEqual(distribution[4], 0.2380952)
        self.assertAlmostEqual(distribution[5], 0.1428571)
        self.assertAlmostEqual(distribution[6], 0.09523809)

    def test_collect_results_after_user_merge(self):
        """ Asserts that merge_users leaves the results cache in a consistent state. Regression test for #907 """
        contributor = mommy.make(UserProfile)
        main_user = mommy.make(UserProfile)
        student = mommy.make(UserProfile)

        evaluation = mommy.make(Evaluation, state='published', participants=[student])
        questionnaire = mommy.make(Questionnaire)
        mommy.make(Question, questionnaire=questionnaire, type=Question.GRADE)
        mommy.make(Contribution, contributor=contributor, evaluation=evaluation, questionnaires=[questionnaire])

        collect_results(evaluation)

        merge_users(main_user, contributor)

        evaluation_results = collect_results(evaluation)

        for contribution_result in evaluation_results.contribution_results:
            self.assertTrue(Contribution.objects.filter(evaluation=evaluation, contributor=contribution_result.contributor).exists())


class TestCalculateAverageDistribution(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.student1 = mommy.make(UserProfile)
        cls.student2 = mommy.make(UserProfile)

        cls.evaluation = mommy.make(Evaluation, state='published', participants=[cls.student1, cls.student2], voters=[cls.student1, cls.student2])
        cls.questionnaire = mommy.make(Questionnaire)
        cls.question_grade = mommy.make(Question, questionnaire=cls.questionnaire, type=Question.GRADE)
        cls.question_likert = mommy.make(Question, questionnaire=cls.questionnaire, type=Question.LIKERT)
        cls.question_likert_2 = mommy.make(Question, questionnaire=cls.questionnaire, type=Question.LIKERT)
        cls.question_bipolar = mommy.make(Question, questionnaire=cls.questionnaire, type=Question.FEW_MANY)
        cls.question_bipolar_2 = mommy.make(Question, questionnaire=cls.questionnaire, type=Question.LITTLE_MUCH)
        cls.general_contribution = cls.evaluation.general_contribution
        cls.general_contribution.questionnaires.set([cls.questionnaire])
        cls.contribution1 = mommy.make(Contribution, contributor=mommy.make(UserProfile), evaluation=cls.evaluation, questionnaires=[cls.questionnaire])
        cls.contribution2 = mommy.make(Contribution, contributor=mommy.make(UserProfile), evaluation=cls.evaluation, questionnaires=[cls.questionnaire])

    @override_settings(CONTRIBUTOR_GRADE_QUESTIONS_WEIGHT=4, CONTRIBUTOR_NON_GRADE_RATING_QUESTIONS_WEIGHT=6, CONTRIBUTIONS_WEIGHT=3, GENERAL_GRADE_QUESTIONS_WEIGHT=2, GENERAL_NON_GRADE_QUESTIONS_WEIGHT=5)
    def test_average_grade(self):
        question_grade2 = mommy.make(Question, questionnaire=self.questionnaire, type=Question.GRADE)

        mommy.make(RatingAnswerCounter, question=self.question_grade, contribution=self.contribution1, answer=2, count=1)
        mommy.make(RatingAnswerCounter, question=self.question_grade, contribution=self.contribution2, answer=4, count=2)
        mommy.make(RatingAnswerCounter, question=question_grade2, contribution=self.contribution1, answer=1, count=1)
        mommy.make(RatingAnswerCounter, question=self.question_likert, contribution=self.contribution1, answer=3, count=4)
        mommy.make(RatingAnswerCounter, question=self.question_likert, contribution=self.general_contribution, answer=5, count=5)
        mommy.make(RatingAnswerCounter, question=self.question_likert_2, contribution=self.general_contribution, answer=3, count=3)
        mommy.make(RatingAnswerCounter, question=self.question_bipolar, contribution=self.general_contribution, answer=3, count=2)
        mommy.make(RatingAnswerCounter, question=self.question_bipolar_2, contribution=self.general_contribution, answer=-1, count=4)

        contributor_weights_sum = settings.CONTRIBUTOR_GRADE_QUESTIONS_WEIGHT + settings.CONTRIBUTOR_NON_GRADE_RATING_QUESTIONS_WEIGHT
        contributor1_average = ((settings.CONTRIBUTOR_GRADE_QUESTIONS_WEIGHT * ((2 * 1) + (1 * 1)) / (1 + 1)) + (settings.CONTRIBUTOR_NON_GRADE_RATING_QUESTIONS_WEIGHT * 3)) / contributor_weights_sum  # 2.4
        contributor2_average = 4
        contributors_average = ((4 * contributor1_average) + (2 * contributor2_average)) / (4 + 2)  # 2.9333333

        general_non_grade_average = ((5 * 5) + (3 * 3) + (2 * 5) + (4 * 7 / 3)) / (5 + 3 + 2 + 4)  # 3.80952380

        contributors_percentage = settings.CONTRIBUTIONS_WEIGHT / (settings.CONTRIBUTIONS_WEIGHT + settings.GENERAL_NON_GRADE_QUESTIONS_WEIGHT)  # 0.375
        general_non_grade_percentage = settings.GENERAL_NON_GRADE_QUESTIONS_WEIGHT / (settings.CONTRIBUTIONS_WEIGHT + settings.GENERAL_NON_GRADE_QUESTIONS_WEIGHT)  # 0.625

        total_grade = contributors_percentage * contributors_average + general_non_grade_percentage * general_non_grade_average  # 1.1 + 2.38095238 = 3.48095238

        average_grade = distribution_to_grade(calculate_average_distribution(self.evaluation))
        self.assertAlmostEqual(average_grade, total_grade)
        self.assertAlmostEqual(average_grade, 3.48095238)

    @override_settings(CONTRIBUTOR_GRADE_QUESTIONS_WEIGHT=4, CONTRIBUTOR_NON_GRADE_RATING_QUESTIONS_WEIGHT=6, CONTRIBUTIONS_WEIGHT=3, GENERAL_GRADE_QUESTIONS_WEIGHT=2, GENERAL_NON_GRADE_QUESTIONS_WEIGHT=5)
    def test_distribution_without_general_grade_question(self):
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

        # general_non_grade: (0, 0, 0.375, 0, 0.625)

        # total: 0.375 * (0.15, 0.125, 0.375, 0.125, 0.225) + 0.625 * (0, 0, 0.375, 0, 0.625) = (0.05625, 0.046875, 0.375, 0.046875, 0.475)

        distribution = calculate_average_distribution(self.evaluation)
        self.assertAlmostEqual(distribution[0], 0.05625)
        self.assertAlmostEqual(distribution[1], 0.046875)
        self.assertAlmostEqual(distribution[2], 0.375)
        self.assertAlmostEqual(distribution[3], 0.046875)
        self.assertAlmostEqual(distribution[4], 0.475)

    @override_settings(CONTRIBUTOR_GRADE_QUESTIONS_WEIGHT=4, CONTRIBUTOR_NON_GRADE_RATING_QUESTIONS_WEIGHT=6, CONTRIBUTIONS_WEIGHT=3, GENERAL_GRADE_QUESTIONS_WEIGHT=2, GENERAL_NON_GRADE_QUESTIONS_WEIGHT=5)
    def test_distribution_with_general_grade_question(self):
        mommy.make(RatingAnswerCounter, question=self.question_grade, contribution=self.contribution1, answer=1, count=1)
        mommy.make(RatingAnswerCounter, question=self.question_grade, contribution=self.contribution1, answer=3, count=1)
        mommy.make(RatingAnswerCounter, question=self.question_grade, contribution=self.contribution2, answer=4, count=1)
        mommy.make(RatingAnswerCounter, question=self.question_grade, contribution=self.contribution2, answer=2, count=1)
        mommy.make(RatingAnswerCounter, question=self.question_likert, contribution=self.contribution1, answer=3, count=3)
        mommy.make(RatingAnswerCounter, question=self.question_likert, contribution=self.contribution1, answer=5, count=3)
        mommy.make(RatingAnswerCounter, question=self.question_likert, contribution=self.general_contribution, answer=5, count=5)
        mommy.make(RatingAnswerCounter, question=self.question_likert_2, contribution=self.general_contribution, answer=3, count=3)
        mommy.make(RatingAnswerCounter, question=self.question_grade, contribution=self.general_contribution, answer=2, count=10)

        # contributions and general_non_grade are as above
        # general_grade: (0, 1, 0, 0, 0)

        # total: 0.3 * (0.15, 0.125, 0.375, 0.125, 0.225) + 0.2 * (0, 1, 0, 0, 0) + 0.5 * (0, 0, 0.375, 0, 0.625) = (0.045, 0.2375, 0.3, 0.0375, 0.38)

        distribution = calculate_average_distribution(self.evaluation)
        self.assertAlmostEqual(distribution[0], 0.045)
        self.assertAlmostEqual(distribution[1], 0.2375)
        self.assertAlmostEqual(distribution[2], 0.3)
        self.assertAlmostEqual(distribution[3], 0.0375)
        self.assertAlmostEqual(distribution[4], 0.38)

    def test_get_single_result_rating_result(self):
        single_result_evaluation = mommy.make(Evaluation, state='published', is_single_result=True)
        questionnaire = Questionnaire.objects.get(name_en=Questionnaire.SINGLE_RESULT_QUESTIONNAIRE_NAME)
        contribution = mommy.make(Contribution, contributor=mommy.make(UserProfile), evaluation=single_result_evaluation, questionnaires=[questionnaire], can_edit=True, textanswer_visibility=Contribution.GENERAL_TEXTANSWERS)
        mommy.make(RatingAnswerCounter, question=questionnaire.questions.first(), contribution=contribution, answer=1, count=1)
        mommy.make(RatingAnswerCounter, question=questionnaire.questions.first(), contribution=contribution, answer=4, count=1)
        distribution = calculate_average_distribution(single_result_evaluation)
        self.assertEqual(distribution, (0.5, 0, 0, 0.5, 0))
        rating_result = get_single_result_rating_result(single_result_evaluation)
        self.assertEqual(rating_result.counts, (1, 0, 0, 1, 0))

    def test_result_calculation_with_no_contributor_rating_question_does_not_fail(self):
        evaluation = mommy.make(Evaluation, state='published', participants=[self.student1, self.student2], voters=[self.student1, self.student2])
        questionnaire_text = mommy.make(Questionnaire)
        mommy.make(Question, questionnaire=questionnaire_text, type=Question.TEXT)
        mommy.make(Contribution, contributor=mommy.make(UserProfile), evaluation=evaluation, questionnaires=[questionnaire_text])

        evaluation.general_contribution.questionnaires.set([self.questionnaire])
        mommy.make(RatingAnswerCounter, question=self.question_grade, contribution=evaluation.general_contribution, answer=1, count=1)

        distribution = calculate_average_distribution(evaluation)
        self.assertEqual(distribution[0], 1)

    def test_unipolarized_unipolar(self):
        counts = (5, 3, 1, 1, 0)

        answer_counters = [
            mommy.make(RatingAnswerCounter, question=self.question_likert, contribution=self.general_contribution, answer=answer, count=count)
            for answer, count in enumerate(counts, start=1)
        ]

        result = RatingResult(self.question_likert, answer_counters)
        distribution = unipolarized_distribution(result)
        self.assertAlmostEqual(distribution[0], 0.5)
        self.assertAlmostEqual(distribution[1], 0.3)
        self.assertAlmostEqual(distribution[2], 0.1)
        self.assertAlmostEqual(distribution[3], 0.1)
        self.assertAlmostEqual(distribution[4], 0.0)

    def test_unipolarized_bipolar(self):
        counts = (0, 1, 4, 8, 2, 2, 3)

        answer_counters = [
            mommy.make(RatingAnswerCounter, question=self.question_bipolar, contribution=self.general_contribution, answer=answer, count=count)
            for answer, count in enumerate(counts, start=-3)
        ]

        result = RatingResult(self.question_bipolar, answer_counters)
        distribution = unipolarized_distribution(result)
        self.assertAlmostEqual(distribution[0], 0.4)
        self.assertAlmostEqual(distribution[1], 0.2)
        self.assertAlmostEqual(distribution[2], 0.15)
        self.assertAlmostEqual(distribution[3], 0.1)
        self.assertAlmostEqual(distribution[4], 0.15)

    def test_unipolarized_yesno(self):
        counts = (57, 43)
        question_yesno = mommy.make(Question, questionnaire=self.questionnaire, type=Question.POSITIVE_YES_NO)
        answer_counters = [
            mommy.make(RatingAnswerCounter, question=question_yesno, contribution=self.general_contribution, answer=1, count=counts[0]),
            mommy.make(RatingAnswerCounter, question=question_yesno, contribution=self.general_contribution, answer=5, count=counts[1])
        ]

        result = RatingResult(question_yesno, answer_counters)
        distribution = unipolarized_distribution(result)
        self.assertAlmostEqual(distribution[0], 0.57)
        self.assertEqual(distribution[1], 0)
        self.assertEqual(distribution[2], 0)
        self.assertEqual(distribution[3], 0)
        self.assertAlmostEqual(distribution[4], 0.43)


class TestTextAnswerVisibilityInfo(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.delegate1 = mommy.make(UserProfile, username="delegate1")
        cls.delegate2 = mommy.make(UserProfile, username="delegate2")
        cls.contributor_own = mommy.make(UserProfile, username="contributor_own", delegates=[cls.delegate1])
        cls.contributor_general = mommy.make(UserProfile, username="contributor_general", delegates=[cls.delegate2])
        cls.responsible1 = mommy.make(UserProfile, username="responsible1", delegates=[cls.delegate1, cls.contributor_general])
        cls.responsible2 = mommy.make(UserProfile, username="responsible2")
        cls.responsible_without_contribution = mommy.make(UserProfile, username="responsible_without_contribution")
        cls.other_user = mommy.make(UserProfile, username="other_user")

        cls.evaluation = mommy.make(Evaluation, course=mommy.make(Course, responsibles=[cls.responsible1, cls.responsible2, cls.responsible_without_contribution]), state='published', can_publish_text_results=True)
        cls.questionnaire = mommy.make(Questionnaire)
        cls.question = mommy.make(Question, questionnaire=cls.questionnaire, type=Question.TEXT)
        cls.general_contribution = cls.evaluation.general_contribution
        cls.general_contribution.questionnaires.set([cls.questionnaire])
        cls.responsible1_contribution = mommy.make(Contribution, contributor=cls.responsible1, evaluation=cls.evaluation,
            questionnaires=[cls.questionnaire], can_edit=True, textanswer_visibility=Contribution.GENERAL_TEXTANSWERS)
        cls.responsible2_contribution = mommy.make(Contribution, contributor=cls.responsible2, evaluation=cls.evaluation,
            questionnaires=[cls.questionnaire], can_edit=True, textanswer_visibility=Contribution.GENERAL_TEXTANSWERS)
        cls.contributor_own_contribution = mommy.make(Contribution, contributor=cls.contributor_own, evaluation=cls.evaluation,
            questionnaires=[cls.questionnaire], textanswer_visibility=Contribution.OWN_TEXTANSWERS)
        cls.contributor_general_contribution = mommy.make(Contribution, contributor=cls.contributor_general, evaluation=cls.evaluation,
            questionnaires=[cls.questionnaire], textanswer_visibility=Contribution.GENERAL_TEXTANSWERS)
        cls.general_contribution_textanswer = mommy.make(TextAnswer, question=cls.question, contribution=cls.general_contribution, state=TextAnswer.PUBLISHED)
        cls.responsible1_textanswer = mommy.make(TextAnswer, question=cls.question, contribution=cls.responsible1_contribution, state=TextAnswer.PUBLISHED)
        cls.responsible2_textanswer = mommy.make(TextAnswer, question=cls.question, contribution=cls.responsible2_contribution, state=TextAnswer.PUBLISHED)
        cls.contributor_own_textanswer = mommy.make(TextAnswer, question=cls.question, contribution=cls.contributor_own_contribution, state=TextAnswer.PUBLISHED)
        cls.contributor_general_textanswer = mommy.make(TextAnswer, question=cls.question, contribution=cls.contributor_general_contribution, state=TextAnswer.PUBLISHED)

    def test_text_answer_visible_to_non_contributing_responsible(self):
        self.assertIn(self.responsible_without_contribution, textanswers_visible_to(self.general_contribution_textanswer.contribution)[0])

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
