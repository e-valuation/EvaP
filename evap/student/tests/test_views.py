from django.contrib.auth.models import Group
from django.test.utils import override_settings
from django.urls import reverse
from model_mommy import mommy

from evap.evaluation.models import UserProfile, Course, Questionnaire, Question, Contribution, TextAnswer, RatingAnswerCounter
from evap.evaluation.tests.tools import WebTest, ViewTest
from evap.student.tools import question_id


class TestStudentIndexView(ViewTest):
    test_users = ['student']
    url = '/student/'

    def setUp(self):
        # View is only visible to users participating in at least one course.
        user = mommy.make(UserProfile, username='student')
        mommy.make(Course, participants=[user])


@override_settings(INSTITUTION_EMAIL_DOMAINS=["example.com"])
class TestVoteView(ViewTest):
    url = '/student/vote/1'

    @classmethod
    def setUpTestData(cls):
        cls.voting_user1 = mommy.make(UserProfile)
        cls.voting_user2 = mommy.make(UserProfile)
        cls.contributor1 = mommy.make(UserProfile)
        cls.contributor2 = mommy.make(UserProfile)

        cls.course = mommy.make(Course, pk=1, participants=[cls.voting_user1, cls.voting_user2, cls.contributor1], state="in_evaluation")

        cls.general_questionnaire = mommy.make(Questionnaire)
        cls.contributor_questionnaire = mommy.make(Questionnaire)

        cls.contributor_text_question = mommy.make(Question, questionnaire=cls.contributor_questionnaire, type="T")
        cls.contributor_likert_question = mommy.make(Question, questionnaire=cls.contributor_questionnaire, type="L")
        cls.general_text_question = mommy.make(Question, questionnaire=cls.general_questionnaire, type="T")
        cls.general_likert_question = mommy.make(Question, questionnaire=cls.general_questionnaire, type="L")
        cls.general_grade_question = mommy.make(Question, questionnaire=cls.general_questionnaire, type="G")

        cls.contribution1 = mommy.make(Contribution, contributor=cls.contributor1, questionnaires=[cls.contributor_questionnaire],
                                       course=cls.course)
        cls.contribution2 = mommy.make(Contribution, contributor=cls.contributor2, questionnaires=[cls.contributor_questionnaire],
                                       course=cls.course)

        cls.course.general_contribution.questionnaires.set([cls.general_questionnaire])

    def fill_form(self, form, fill_complete):
        form[question_id(self.course.general_contribution, self.general_questionnaire, self.general_text_question)] = "some text"
        form[question_id(self.course.general_contribution, self.general_questionnaire, self.general_grade_question)] = 3
        form[question_id(self.course.general_contribution, self.general_questionnaire, self.general_likert_question)] = 1

        form[question_id(self.contribution1, self.contributor_questionnaire, self.contributor_text_question)] = "some other text"
        form[question_id(self.contribution1, self.contributor_questionnaire, self.contributor_likert_question)] = 4

        form[question_id(self.contribution2, self.contributor_questionnaire, self.contributor_text_question)] = "some more text"

        if fill_complete:
            form[question_id(self.contribution2, self.contributor_questionnaire, self.contributor_likert_question)] = 2

    def test_incomplete_form(self):
        """
            Submits a student vote, verifies that an error message is
            displayed if not all rating questions have been answered and that all
            given answers stay selected/filled.
        """
        page = self.get_assert_200(self.url, user=self.voting_user1.username)
        form = page.forms["student-vote-form"]
        self.fill_form(form, fill_complete=False)
        response = form.submit()

        self.assertIn("vote for all rating questions", response)

        form = page.forms["student-vote-form"]
        self.assertEqual(form[question_id(self.course.general_contribution, self.general_questionnaire, self.general_text_question)].value, "some text")
        self.assertEqual(form[question_id(self.course.general_contribution, self.general_questionnaire, self.general_likert_question)].value, "1")
        self.assertEqual(form[question_id(self.course.general_contribution, self.general_questionnaire, self.general_grade_question)].value, "3")

        self.assertEqual(form[question_id(self.contribution1, self.contributor_questionnaire, self.contributor_text_question)].value, "some other text")
        self.assertEqual(form[question_id(self.contribution1, self.contributor_questionnaire, self.contributor_likert_question)].value, "4")

        self.assertEqual(form[question_id(self.contribution2, self.contributor_questionnaire, self.contributor_text_question)].value, "some more text")

    def test_answer(self):
        page = self.get_assert_200(self.url, user=self.voting_user1.username)
        form = page.forms["student-vote-form"]
        self.fill_form(form, fill_complete=True)
        form.submit()

        page = self.get_assert_200(self.url, user=self.voting_user2.username)
        form = page.forms["student-vote-form"]
        self.fill_form(form, fill_complete=True)
        form.submit()

        self.assertEqual(len(TextAnswer.objects.all()), 6)
        self.assertEqual(len(RatingAnswerCounter.objects.all()), 4)

        self.assertEqual(RatingAnswerCounter.objects.filter(question=self.general_likert_question).count(), 1)
        self.assertEqual(RatingAnswerCounter.objects.get(question=self.general_likert_question).answer, 1)

        self.assertEqual(RatingAnswerCounter.objects.filter(question=self.general_grade_question).count(), 1)
        self.assertEqual(RatingAnswerCounter.objects.get(question=self.general_grade_question).answer, 3)

        self.assertEqual(RatingAnswerCounter.objects.filter(question=self.contributor_likert_question).count(), 2)
        self.assertEqual(RatingAnswerCounter.objects.filter(question=self.contributor_likert_question)[0].answer, 4)
        self.assertEqual(RatingAnswerCounter.objects.filter(question=self.contributor_likert_question)[1].answer, 2)
        self.assertEqual(RatingAnswerCounter.objects.filter(question=self.contributor_likert_question)[0].contribution, self.contribution1)
        self.assertEqual(RatingAnswerCounter.objects.filter(question=self.contributor_likert_question)[1].contribution, self.contribution2)

        self.assertEqual(TextAnswer.objects.filter(question=self.general_text_question).count(), 2)
        self.assertEqual(TextAnswer.objects.filter(question=self.contributor_text_question).count(), 4)

        self.assertEqual(TextAnswer.objects.filter(question=self.general_text_question)[0].contribution, self.course.general_contribution)
        self.assertEqual(TextAnswer.objects.filter(question=self.general_text_question)[1].contribution, self.course.general_contribution)
        self.assertEqual(TextAnswer.objects.filter(question=self.contributor_text_question)[0].contribution, self.contribution1)
        self.assertEqual(TextAnswer.objects.filter(question=self.contributor_text_question)[1].contribution, self.contribution2)
        self.assertEqual(TextAnswer.objects.filter(question=self.contributor_text_question)[2].contribution, self.contribution1)
        self.assertEqual(TextAnswer.objects.filter(question=self.contributor_text_question)[3].contribution, self.contribution2)

        self.assertEqual(TextAnswer.objects.filter(question=self.contributor_text_question)[0].answer, "some other text")
        self.assertEqual(TextAnswer.objects.filter(question=self.contributor_text_question)[1].answer, "some more text")
        self.assertEqual(TextAnswer.objects.filter(question=self.general_text_question)[0].answer, "some text")


    def test_user_cannot_vote_multiple_times(self):
        page = self.get_assert_200(self.url, user=self.voting_user1.username)
        form = page.forms["student-vote-form"]
        self.fill_form(form, True)
        form.submit()

        self.get_assert_403(self.url, user=self.voting_user1.username)

    def test_user_cannot_vote_for_themselves(self):
        response = self.get_assert_200(self.url, user=self.contributor1)

        for contributor, _, _, _ in response.context['contributor_form_groups']:
            self.assertNotEqual(contributor, self.contributor1, "Contributor should not see the questionnaire about themselves")

        response = self.get_assert_200(self.url, user=self.voting_user1)
        self.assertTrue(any(contributor == self.contributor1 for contributor, _, _, _ in response.context['contributor_form_groups']),
            "Regular students should see the questionnaire about a contributor")
