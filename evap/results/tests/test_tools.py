from datetime import datetime

from django.conf import settings
from django.core.cache import caches
from django.test import override_settings
from django.test.testcases import TestCase
from model_bakery import baker

from evap.evaluation.models import (
    Contribution,
    Course,
    Evaluation,
    Question,
    Questionnaire,
    QuestionType,
    RatingAnswerCounter,
    TextAnswer,
    UserProfile,
)
from evap.evaluation.tests.tools import make_rating_answer_counters
from evap.results.tools import (
    cache_results,
    calculate_average_course_distribution,
    calculate_average_distribution,
    can_textanswer_be_seen_by,
    create_rating_result,
    distribution_to_grade,
    get_results,
    get_results_cache_key,
    get_single_result_rating_result,
    normalized_distribution,
    textanswers_visible_to,
    unipolarized_distribution,
)
from evap.staff.tools import merge_users


class TestCalculateResults(TestCase):
    def test_cache_results(self):
        evaluation = baker.make(Evaluation, state=Evaluation.State.PUBLISHED)

        self.assertIsNone(caches["results"].get(get_results_cache_key(evaluation)))

        cache_results(evaluation)

        self.assertIsNotNone(caches["results"].get(get_results_cache_key(evaluation)))

    def test_caching_lifecycle(self):
        evaluation = baker.make(Evaluation, state=Evaluation.State.IN_EVALUATION)

        self.assertIsNone(caches["results"].get(get_results_cache_key(evaluation)))

        evaluation.end_evaluation()
        evaluation.save()

        self.assertIsNotNone(caches["results"].get(get_results_cache_key(evaluation)))

        evaluation.reopen_evaluation()
        evaluation.save()

        self.assertIsNone(caches["results"].get(get_results_cache_key(evaluation)))

    def test_caching_works_after_multiple_transitions(self):
        evaluation = baker.make(Evaluation, state=Evaluation.State.IN_EVALUATION)

        self.assertIsNone(caches["results"].get(get_results_cache_key(evaluation)))

        evaluation.end_evaluation()
        evaluation.end_review()
        evaluation.publish()
        evaluation.save()

        self.assertIsNotNone(caches["results"].get(get_results_cache_key(evaluation)))

    def test_calculation_unipolar_results(self):
        contributor1 = baker.make(UserProfile)
        student = baker.make(UserProfile)

        evaluation = baker.make(
            Evaluation,
            state=Evaluation.State.PUBLISHED,
            participants=[student, contributor1],
            voters=[student, contributor1],
        )
        questionnaire = baker.make(Questionnaire)
        question = baker.make(Question, questionnaire=questionnaire, type=QuestionType.GRADE)
        contribution1 = baker.make(
            Contribution, contributor=contributor1, evaluation=evaluation, questionnaires=[questionnaire]
        )

        make_rating_answer_counters(question, contribution1, [5, 15, 40, 60, 30])

        cache_results(evaluation)
        evaluation_results = get_results(evaluation)

        self.assertEqual(len(evaluation_results.questionnaire_results), 1)
        questionnaire_result = evaluation_results.questionnaire_results[0]
        self.assertEqual(len(questionnaire_result.question_results), 1)
        question_result = questionnaire_result.question_results[0]

        self.assertEqual(question_result.count_sum, 150)
        self.assertAlmostEqual(question_result.average, float(109) / 30)
        self.assertEqual(question_result.counts, (5, 15, 40, 60, 30))

    def test_calculation_bipolar_results(self):
        contributor1 = baker.make(UserProfile)
        student = baker.make(UserProfile)

        evaluation = baker.make(
            Evaluation,
            state=Evaluation.State.PUBLISHED,
            participants=[student, contributor1],
            voters=[student, contributor1],
        )
        questionnaire = baker.make(Questionnaire)
        question = baker.make(Question, questionnaire=questionnaire, type=QuestionType.EASY_DIFFICULT)
        contribution1 = baker.make(
            Contribution, contributor=contributor1, evaluation=evaluation, questionnaires=[questionnaire]
        )

        make_rating_answer_counters(question, contribution1, [5, 5, 15, 30, 25, 15, 10])

        cache_results(evaluation)
        evaluation_results = get_results(evaluation)

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

    def test_results_cache_after_user_merge(self):
        """Asserts that merge_users leaves the results cache in a consistent state. Regression test for #907"""
        contributor = baker.make(UserProfile)
        main_user = baker.make(UserProfile)
        student = baker.make(UserProfile)

        evaluation = baker.make(Evaluation, state=Evaluation.State.PUBLISHED, participants=[student])
        questionnaire = baker.make(Questionnaire)
        baker.make(Question, questionnaire=questionnaire, type=QuestionType.GRADE)
        baker.make(Contribution, contributor=contributor, evaluation=evaluation, questionnaires=[questionnaire])

        cache_results(evaluation)

        merge_users(main_user, contributor)

        evaluation_results = get_results(evaluation)

        for contribution_result in evaluation_results.contribution_results:
            self.assertTrue(
                Contribution.objects.filter(evaluation=evaluation, contributor=contribution_result.contributor).exists()
            )


class TestCalculateAverageDistribution(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.student1 = baker.make(UserProfile)
        cls.student2 = baker.make(UserProfile)

        cls.evaluation = baker.make(
            Evaluation,
            state=Evaluation.State.PUBLISHED,
            participants=[cls.student1, cls.student2],
            voters=[cls.student1, cls.student2],
        )
        cls.questionnaire = baker.make(Questionnaire)
        cls.question_grade = baker.make(Question, questionnaire=cls.questionnaire, type=QuestionType.GRADE)
        cls.question_likert = baker.make(Question, questionnaire=cls.questionnaire, type=QuestionType.POSITIVE_LIKERT)
        cls.question_likert_2 = baker.make(Question, questionnaire=cls.questionnaire, type=QuestionType.POSITIVE_LIKERT)
        cls.question_negative_likert = baker.make(
            Question, questionnaire=cls.questionnaire, type=QuestionType.NEGATIVE_LIKERT
        )
        cls.question_bipolar = baker.make(Question, questionnaire=cls.questionnaire, type=QuestionType.FEW_MANY)
        cls.question_bipolar_2 = baker.make(Question, questionnaire=cls.questionnaire, type=QuestionType.LITTLE_MUCH)
        cls.general_contribution = cls.evaluation.general_contribution
        cls.general_contribution.questionnaires.set([cls.questionnaire])
        cls.contribution1 = baker.make(
            Contribution,
            contributor=baker.make(UserProfile),
            evaluation=cls.evaluation,
            questionnaires=[cls.questionnaire],
        )
        cls.contribution2 = baker.make(
            Contribution,
            contributor=baker.make(UserProfile),
            evaluation=cls.evaluation,
            questionnaires=[cls.questionnaire],
        )

    @override_settings(
        CONTRIBUTOR_GRADE_QUESTIONS_WEIGHT=4,
        CONTRIBUTOR_NON_GRADE_RATING_QUESTIONS_WEIGHT=6,
        CONTRIBUTIONS_WEIGHT=3,
        GENERAL_GRADE_QUESTIONS_WEIGHT=2,
        GENERAL_NON_GRADE_QUESTIONS_WEIGHT=5,
    )
    def test_average_grade(self):
        question_grade2 = baker.make(Question, questionnaire=self.questionnaire, type=QuestionType.GRADE)

        counters = [
            *make_rating_answer_counters(self.question_grade, self.contribution1, [0, 1, 0, 0, 0], False),
            *make_rating_answer_counters(self.question_grade, self.contribution2, [0, 0, 0, 2, 0], False),
            *make_rating_answer_counters(question_grade2, self.contribution1, [1, 0, 0, 0, 0], False),
            *make_rating_answer_counters(self.question_likert, self.contribution1, [0, 0, 4, 0, 0], False),
            *make_rating_answer_counters(self.question_likert, self.general_contribution, [0, 0, 0, 0, 5], False),
            *make_rating_answer_counters(self.question_likert_2, self.general_contribution, [0, 0, 3, 0, 0], False),
            *make_rating_answer_counters(
                self.question_negative_likert, self.general_contribution, [0, 0, 0, 4, 0], False
            ),
            *make_rating_answer_counters(
                self.question_bipolar, self.general_contribution, [0, 0, 0, 0, 0, 0, 2], False
            ),
            *make_rating_answer_counters(
                self.question_bipolar_2, self.general_contribution, [0, 0, 4, 0, 0, 0, 0], False
            ),
        ]
        RatingAnswerCounter.objects.bulk_create(counters)

        cache_results(self.evaluation)

        contributor_weights_sum = (
            settings.CONTRIBUTOR_GRADE_QUESTIONS_WEIGHT + settings.CONTRIBUTOR_NON_GRADE_RATING_QUESTIONS_WEIGHT
        )
        contributor1_average = (
            (settings.CONTRIBUTOR_GRADE_QUESTIONS_WEIGHT * ((2 * 1) + (1 * 1)) / (1 + 1))
            + (settings.CONTRIBUTOR_NON_GRADE_RATING_QUESTIONS_WEIGHT * 3)
        ) / contributor_weights_sum  # 2.4
        contributor2_average = 4
        contributors_average = ((4 * contributor1_average) + (2 * contributor2_average)) / (4 + 2)  # 2.9333333

        general_non_grade_average = ((5 * 5) + (3 * 3) + (4 * 4) + (2 * 5) + (4 * 7 / 3)) / (
            5 + 3 + 4 + 2 + 4
        )  # 3.85185185

        contributors_percentage = settings.CONTRIBUTIONS_WEIGHT / (
            settings.CONTRIBUTIONS_WEIGHT + settings.GENERAL_NON_GRADE_QUESTIONS_WEIGHT
        )  # 0.375
        general_non_grade_percentage = settings.GENERAL_NON_GRADE_QUESTIONS_WEIGHT / (
            settings.CONTRIBUTIONS_WEIGHT + settings.GENERAL_NON_GRADE_QUESTIONS_WEIGHT
        )  # 0.625

        total_grade = (
            contributors_percentage * contributors_average + general_non_grade_percentage * general_non_grade_average
        )  # 1.1 + 2.4074074 = 3.5074074

        average_grade = distribution_to_grade(calculate_average_distribution(self.evaluation))
        self.assertAlmostEqual(average_grade, total_grade)
        self.assertAlmostEqual(average_grade, 3.5074074)

    @override_settings(
        CONTRIBUTOR_GRADE_QUESTIONS_WEIGHT=4,
        CONTRIBUTOR_NON_GRADE_RATING_QUESTIONS_WEIGHT=6,
        CONTRIBUTIONS_WEIGHT=3,
        GENERAL_GRADE_QUESTIONS_WEIGHT=2,
        GENERAL_NON_GRADE_QUESTIONS_WEIGHT=5,
    )
    def test_distribution_without_general_grade_question(self):
        counters = [
            *make_rating_answer_counters(self.question_grade, self.contribution1, [1, 0, 1, 0, 0], False),
            *make_rating_answer_counters(self.question_grade, self.contribution2, [0, 1, 0, 1, 0], False),
            *make_rating_answer_counters(self.question_likert, self.contribution1, [0, 0, 3, 0, 3], False),
            *make_rating_answer_counters(self.question_likert, self.general_contribution, [0, 0, 0, 0, 5], False),
            *make_rating_answer_counters(self.question_likert_2, self.general_contribution, [0, 0, 3, 0, 0], False),
        ]
        RatingAnswerCounter.objects.bulk_create(counters)

        cache_results(self.evaluation)

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

    @override_settings(
        CONTRIBUTOR_GRADE_QUESTIONS_WEIGHT=4,
        CONTRIBUTOR_NON_GRADE_RATING_QUESTIONS_WEIGHT=6,
        CONTRIBUTIONS_WEIGHT=3,
        GENERAL_GRADE_QUESTIONS_WEIGHT=2,
        GENERAL_NON_GRADE_QUESTIONS_WEIGHT=5,
    )
    def test_distribution_with_general_grade_question(self):
        counters = [
            *make_rating_answer_counters(self.question_grade, self.contribution1, [1, 0, 1, 0, 0], False),
            *make_rating_answer_counters(self.question_grade, self.contribution2, [0, 1, 0, 1, 0], False),
            *make_rating_answer_counters(self.question_likert, self.contribution1, [0, 0, 3, 0, 3], False),
            *make_rating_answer_counters(self.question_likert, self.general_contribution, [0, 0, 0, 0, 5], False),
            *make_rating_answer_counters(self.question_likert_2, self.general_contribution, [0, 0, 3, 0, 0], False),
            *make_rating_answer_counters(self.question_grade, self.general_contribution, [0, 10, 0, 0, 0], False),
        ]
        RatingAnswerCounter.objects.bulk_create(counters)

        cache_results(self.evaluation)

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
        single_result_evaluation = baker.make(Evaluation, state=Evaluation.State.PUBLISHED, is_single_result=True)
        questionnaire = Questionnaire.single_result_questionnaire()
        contribution = baker.make(
            Contribution,
            contributor=baker.make(UserProfile),
            evaluation=single_result_evaluation,
            questionnaires=[questionnaire],
            role=Contribution.Role.EDITOR,
            textanswer_visibility=Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS,
        )
        make_rating_answer_counters(questionnaire.questions.first(), contribution, [1, 0, 0, 1, 0])

        cache_results(single_result_evaluation)
        distribution = calculate_average_distribution(single_result_evaluation)
        self.assertEqual(distribution, (0.5, 0, 0, 0.5, 0))
        rating_result = get_single_result_rating_result(single_result_evaluation)
        self.assertEqual(rating_result.counts, (1, 0, 0, 1, 0))

    def test_result_calculation_with_no_contributor_rating_question(self):
        evaluation = baker.make(
            Evaluation,
            state=Evaluation.State.PUBLISHED,
            participants=[self.student1, self.student2],
            voters=[self.student1, self.student2],
        )
        questionnaire_text = baker.make(Questionnaire)
        baker.make(Question, questionnaire=questionnaire_text, type=QuestionType.TEXT)
        baker.make(
            Contribution,
            contributor=baker.make(UserProfile),
            evaluation=evaluation,
            questionnaires=[questionnaire_text],
        )

        evaluation.general_contribution.questionnaires.set([self.questionnaire])
        make_rating_answer_counters(self.question_grade, evaluation.general_contribution, [1, 0, 0, 0, 0])
        cache_results(evaluation)

        distribution = calculate_average_distribution(evaluation)
        self.assertEqual(distribution[0], 1)

    def test_unipolarized_unipolar(self):
        answer_counters = make_rating_answer_counters(self.question_likert, self.general_contribution, [5, 3, 1, 1, 0])

        result = create_rating_result(self.question_likert, answer_counters)
        distribution = unipolarized_distribution(result)
        self.assertAlmostEqual(distribution[0], 0.5)
        self.assertAlmostEqual(distribution[1], 0.3)
        self.assertAlmostEqual(distribution[2], 0.1)
        self.assertAlmostEqual(distribution[3], 0.1)
        self.assertAlmostEqual(distribution[4], 0.0)

    def test_unipolarized_bipolar(self):
        answer_counters = make_rating_answer_counters(
            self.question_bipolar, self.general_contribution, [0, 1, 4, 8, 2, 2, 3]
        )

        result = create_rating_result(self.question_bipolar, answer_counters)
        distribution = unipolarized_distribution(result)
        self.assertAlmostEqual(distribution[0], 0.4)
        self.assertAlmostEqual(distribution[1], 0.2)
        self.assertAlmostEqual(distribution[2], 0.15)
        self.assertAlmostEqual(distribution[3], 0.1)
        self.assertAlmostEqual(distribution[4], 0.15)

    def test_unipolarized_yesno(self):
        question_yesno = baker.make(Question, questionnaire=self.questionnaire, type=QuestionType.POSITIVE_YES_NO)
        answer_counters = make_rating_answer_counters(question_yesno, self.general_contribution, [57, 43])

        result = create_rating_result(question_yesno, answer_counters)
        distribution = unipolarized_distribution(result)
        self.assertAlmostEqual(distribution[0], 0.57)
        self.assertEqual(distribution[1], 0)
        self.assertEqual(distribution[2], 0)
        self.assertEqual(distribution[3], 0)
        self.assertAlmostEqual(distribution[4], 0.43)

    def test_calculate_average_course_distribution(self):
        make_rating_answer_counters(self.question_grade, self.contribution1, [2, 0, 0, 0, 0])

        course = self.evaluation.course
        single_result = baker.make(
            Evaluation,
            name_de="Single Result",
            name_en="Single Result",
            course=course,
            weight=3,
            is_single_result=True,
            vote_start_datetime=datetime.now(),
            vote_end_date=datetime.now().date(),
            state=Evaluation.State.PUBLISHED,
        )
        single_result_questionnaire = Questionnaire.single_result_questionnaire()
        single_result_question = single_result_questionnaire.questions.first()

        contribution = baker.make(
            Contribution, evaluation=single_result, contributor=None, questionnaires=[single_result_questionnaire]
        )
        make_rating_answer_counters(single_result_question, contribution, [0, 1, 1, 0, 0])
        cache_results(single_result)
        cache_results(self.evaluation)

        distribution = calculate_average_course_distribution(course)
        self.assertEqual(distribution[0], 0.25)
        self.assertEqual(distribution[1], 0.375)
        self.assertEqual(distribution[2], 0.375)
        self.assertEqual(distribution[3], 0)
        self.assertEqual(distribution[4], 0)


class TestTextAnswerVisibilityInfo(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.delegate1 = baker.make(UserProfile, email="delegate1@institution.example.com")
        cls.delegate2 = baker.make(UserProfile, email="delegate2@institution.example.com")
        cls.shared_delegate = baker.make(UserProfile, email="shared_delegate@institution.example.com")
        cls.contributor_own = baker.make(
            UserProfile, email="contributor_own@institution.example.com", delegates=[cls.delegate1, cls.shared_delegate]
        )
        cls.contributor_general = baker.make(
            UserProfile,
            email="contributor_general@institution.example.com",
            delegates=[cls.delegate2, cls.shared_delegate],
        )
        cls.responsible1 = baker.make(
            UserProfile,
            email="responsible1@institution.example.com",
            delegates=[cls.delegate1, cls.contributor_general, cls.shared_delegate],
        )
        cls.responsible2 = baker.make(UserProfile, email="responsible2@institution.example.com")
        cls.responsible_without_contribution = baker.make(
            UserProfile, email="responsible_without_contribution@institution.example.com"
        )
        cls.other_user = baker.make(UserProfile, email="other_user@institution.example.com")

        cls.evaluation = baker.make(
            Evaluation,
            course=baker.make(
                Course, responsibles=[cls.responsible1, cls.responsible2, cls.responsible_without_contribution]
            ),
            state=Evaluation.State.PUBLISHED,
            can_publish_text_results=True,
        )
        cls.questionnaire = baker.make(Questionnaire)
        cls.question = baker.make(Question, questionnaire=cls.questionnaire, type=QuestionType.TEXT)
        cls.question_likert = baker.make(Question, questionnaire=cls.questionnaire, type=QuestionType.POSITIVE_LIKERT)
        cls.general_contribution = cls.evaluation.general_contribution
        cls.general_contribution.questionnaires.set([cls.questionnaire])
        cls.responsible1_contribution = baker.make(
            Contribution,
            contributor=cls.responsible1,
            evaluation=cls.evaluation,
            questionnaires=[cls.questionnaire],
            role=Contribution.Role.EDITOR,
            textanswer_visibility=Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS,
        )
        cls.responsible2_contribution = baker.make(
            Contribution,
            contributor=cls.responsible2,
            evaluation=cls.evaluation,
            questionnaires=[cls.questionnaire],
            role=Contribution.Role.EDITOR,
            textanswer_visibility=Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS,
        )
        cls.contributor_own_contribution = baker.make(
            Contribution,
            contributor=cls.contributor_own,
            evaluation=cls.evaluation,
            questionnaires=[cls.questionnaire],
            textanswer_visibility=Contribution.TextAnswerVisibility.OWN_TEXTANSWERS,
        )
        cls.contributor_general_contribution = baker.make(
            Contribution,
            contributor=cls.contributor_general,
            evaluation=cls.evaluation,
            questionnaires=[cls.questionnaire],
            textanswer_visibility=Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS,
        )
        cls.general_contribution_textanswer = baker.make(
            TextAnswer,
            question=cls.question,
            contribution=cls.general_contribution,
            review_decision=TextAnswer.ReviewDecision.PUBLIC,
        )
        cls.responsible1_textanswer = baker.make(
            TextAnswer,
            question=cls.question,
            contribution=cls.responsible1_contribution,
            review_decision=TextAnswer.ReviewDecision.PUBLIC,
        )
        cls.responsible1_additional_textanswer = baker.make(
            TextAnswer,
            question=cls.question_likert,
            contribution=cls.responsible1_contribution,
            review_decision=TextAnswer.ReviewDecision.PUBLIC,
        )
        cls.responsible2_textanswer = baker.make(
            TextAnswer,
            question=cls.question,
            contribution=cls.responsible2_contribution,
            review_decision=TextAnswer.ReviewDecision.PUBLIC,
        )
        cls.contributor_own_textanswer = baker.make(
            TextAnswer,
            question=cls.question,
            contribution=cls.contributor_own_contribution,
            review_decision=TextAnswer.ReviewDecision.PUBLIC,
        )
        cls.contributor_general_textanswer = baker.make(
            TextAnswer,
            question=cls.question,
            contribution=cls.contributor_general_contribution,
            review_decision=TextAnswer.ReviewDecision.PUBLIC,
        )

    def test_text_answer_visible_to_non_contributing_responsible(self):
        self.assertIn(
            self.responsible_without_contribution,
            textanswers_visible_to(self.general_contribution_textanswer.contribution).visible_by_contribution,
        )

    def test_contributors_and_delegate_count_in_textanswer_visibility_info(self):
        textanswers = [
            self.general_contribution_textanswer,
            self.responsible1_textanswer,
            self.responsible1_additional_textanswer,
            self.responsible2_textanswer,
            self.contributor_own_textanswer,
            self.contributor_general_textanswer,
        ]
        visible_to = [textanswers_visible_to(textanswer.contribution) for textanswer in textanswers]
        users_seeing_contribution = [(set(), set()) for _ in range(len(textanswers))]

        for user in UserProfile.objects.all():
            represented_users = [user] + list(user.represented_users.all())
            for i, textanswer in enumerate(textanswers):
                if can_textanswer_be_seen_by(user, represented_users, textanswer, "full"):
                    if can_textanswer_be_seen_by(user, [user], textanswer, "full"):
                        users_seeing_contribution[i][0].add(user)
                    else:
                        users_seeing_contribution[i][1].add(user)

        for i in range(len(textanswers)):
            self.assertCountEqual(visible_to[i].visible_by_contribution, users_seeing_contribution[i][0])

        expected_delegate_counts = [
            3,  # delegate1, delegate2, shared_delegate
            3,  # delegate1, contributor_general, shared_delegate
            3,  # delegate1, contributor_general, shared_delegate
            0,
            2,  # delegate1, shared_delegate
            2,  # delegate2, shared_delegate
        ]

        for i in range(len(textanswers)):
            self.assertTrue(
                visible_to[i].visible_by_delegation_count
                == len(users_seeing_contribution[i][1])
                == expected_delegate_counts[i]
            )
