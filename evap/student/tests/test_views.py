from django.contrib.auth.models import Group
from django.test.utils import override_settings
from django.urls import reverse
from model_mommy import mommy

from evap.evaluation.models import UserProfile, Course, Questionnaire, Question, Contribution
from evap.evaluation.tests.tools import WebTest, ViewTest

import pdb


class TestStudentIndexView(ViewTest):
    test_users = ['student']
    url = '/student/'

    def setUp(self):
        # View is only visible to users participating in at least one course.
        user = mommy.make(UserProfile, username='student')
        mommy.make(Course, participants=[user])


@override_settings(INSTITUTION_EMAIL_DOMAINS=["example.com"])
class TestVoteView(WebTest):

    @classmethod
    def setUpTestData(cls):
        cls.voting_user = mommy.make(UserProfile, username="lazy.student")
        cls.contributor1 = mommy.make(UserProfile, username="first.contributor")
        cls.contributor2 = mommy.make(UserProfile, username="second.contributor")

        cls.course = mommy.make(Course, pk=5, participants=[cls.voting_user, cls.contributor1], state="in_evaluation", name_en="TestCourse")

        cls.general_questionnaire = mommy.make(Questionnaire, name_en="GeneralQuestionnaire")
        cls.contributor_questionnaire = mommy.make(Questionnaire, name_en="ContributorQuestionnaire")

        cls.contributor_text_question = mommy.make(Question, questionnaire=cls.contributor_questionnaire, text_en="how?", type="T")
        cls.contributor_likert_question = mommy.make(Question, questionnaire=cls.contributor_questionnaire, text_en="how much?", type="L")
        cls.general_text_question = mommy.make(Question, questionnaire=cls.general_questionnaire, text_en="how?", type="T")
        cls.general_likert_question = mommy.make(Question, questionnaire=cls.general_questionnaire, text_en="how much?", type="L")
        cls.general_grade_question = mommy.make(Question, questionnaire=cls.general_questionnaire, text_en="your grade", type="G")

        cls.contribution1 = mommy.make(Contribution, contributor=cls.contributor1, questionnaires=[cls.contributor_questionnaire],
                   course=cls.course)
        cls.contribution2 = mommy.make(Contribution, contributor=cls.contributor2, questionnaires=[cls.contributor_questionnaire],
                   course=cls.course)

        cls.course.general_contribution.questionnaires.set([cls.general_questionnaire])

    def fill_incomplete_form(self, form):
        form[question_id(self.course.general_contribution, self.general_questionnaire, self.general_text_question)] = "some text"
        form[question_id(self.course.general_contribution, self.general_questionnaire, self.general_likert_question)] = 1
        form[question_id(self.course.general_contribution, self.general_questionnaire, self.general_grade_question)] = 6

        form[question_id(self.contribution1, self.contributor_questionnaire, self.contributor_text_question)] = "some other text"
        form[question_id(self.contribution1, self.contributor_questionnaire, self.contributor_likert_question)] = 1

        form[question_id(self.contribution2, self.contributor_questionnaire, self.contributor_text_question)] = "some more text"

    def fill_complete_form(self, form):
        self.fill_incomplete_form(form)
        form[question_id(self.contribution2, self.contributor_questionnaire, self.contributor_likert_question)] = 2

    def test_incomplete_form(self):
        """
            Submits a student vote, verifies that an error message is
            displayed if not all rating questions have been answered and that all
            given answers stay selected/filled.
        """
        page = self.get_assert_200(self.vote_url(), user="lazy.student")
        form = page.forms["student-vote-form"]
        self.fill_incomplete_form(form)
        response = form.submit()

        self.assertIn("vote for all rating questions", response)

        #Check existing answers
        form = page.forms["student-vote-form"]
        self.assertEqual(form[question_id(self.course.general_contribution, self.general_questionnaire, self.general_text_question)].value,
                         "some text")
        self.assertEqual(form[question_id(self.course.general_contribution, self.general_questionnaire, self.general_likert_question)].value,
                         "1")
        self.assertEqual(form[question_id(self.course.general_contribution, self.general_questionnaire, self.general_grade_question)].value,
                         "6")

        self.assertEqual(form[question_id(self.contribution1, self.contributor_questionnaire, self.contributor_text_question)].value,
                         "some other text")
        self.assertEqual(form[question_id(self.contribution1, self.contributor_questionnaire, self.contributor_likert_question)].value,
                         "1")

        self.assertEqual(form[question_id(self.contribution2, self.contributor_questionnaire, self.contributor_text_question)].value,
                         "some more text")

        form[question_id(self.contribution2, self.contributor_questionnaire, self.contributor_likert_question)] = 3  # give missing answer
        form.submit()

        self.get_assert_403(self.vote_url(), user="lazy.student")


    def test_user_cannot_vote_multiple_times(self):
        page = self.get_assert_200(self.vote_url(), user="lazy.student")
        form = page.forms["student-vote-form"]
        self.fill_complete_form(form)
        form.submit()

        page = self.get_assert_403(self.vote_url(), user="lazy.student")

    def test_user_cannot_vote_for_themselves(self):
        def get_vote_page(user):
            return self.app.get(reverse('student:vote', kwargs={'course_id': self.course.id}), user=user)

        response = get_vote_page(self.contributor1)

        for contributor, _, _, _ in response.context['contributor_form_groups']:
            self.assertNotEqual(contributor, self.contributor1, "Contributor should not see the questionnaire about themselves")

        response = get_vote_page(self.voting_user)
        self.assertTrue(any(contributor == self.contributor1 for contributor, _, _, _ in response.context['contributor_form_groups']),
            "Regular students should see the questionnaire about a contributor")

    def vote_url(self):
        return "/student/vote/" + str(self.course.pk)

def question_id(contribution, questionnaire, question):
    return "question_" + str(contribution.pk) + "_" + str(questionnaire.pk) + "_" + str(question.pk)
