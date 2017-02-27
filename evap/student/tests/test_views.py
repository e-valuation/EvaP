from django.test.utils import override_settings
from django.urls import reverse
from model_mommy import mommy

from evap.evaluation.models import UserProfile, Course, Questionnaire, Question, Contribution
from evap.evaluation.tests.tools import WebTest


@override_settings(INSTITUTION_EMAIL_DOMAINS=["example.com"])
class TestVoteView(WebTest):
    fixtures = ['minimal_test_data']

    def test_complete_vote_usecase(self):
        """
            Submits a student vote, verifies that an error message is
            displayed if not all rating questions have been answered and that all
            given answers stay selected/filled and that the student cannot vote on
            the course a second time.
        """
        page = self.get_assert_200("/student/vote/5", user="lazy.student")
        form = page.forms["student-vote-form"]
        form["question_17_2_3"] = "some text"
        form["question_17_2_4"] = 1
        form["question_17_2_5"] = 6
        form["question_18_1_1"] = "some other text"
        form["question_18_1_2"] = 1
        form["question_19_1_1"] = "some more text"
        form["question_19_1_2"] = 1
        form["question_20_1_1"] = "and the last text"
        response = form.submit()

        self.assertIn("vote for all rating questions", response)
        form = page.forms["student-vote-form"]
        self.assertEqual(form["question_17_2_3"].value, "some text")
        self.assertEqual(form["question_17_2_4"].value, "1")
        self.assertEqual(form["question_17_2_5"].value, "6")
        self.assertEqual(form["question_18_1_1"].value, "some other text")
        self.assertEqual(form["question_18_1_2"].value, "1")
        self.assertEqual(form["question_19_1_1"].value, "some more text")
        self.assertEqual(form["question_19_1_2"].value, "1")
        self.assertEqual(form["question_20_1_1"].value, "and the last text")
        form["question_20_1_2"] = 1  # give missing answer
        form.submit()

        self.get_assert_403("/student/vote/5", user="lazy.student")

    def test_simple_vote(self):
        page = self.get_assert_200("/student/vote/5", user="lazy.student")
        form = page.forms["student-vote-form"]
        form["question_17_2_3"] = "some text"
        form["question_17_2_4"] = 1
        form["question_17_2_5"] = 6
        form["question_18_1_1"] = "some other text"
        form["question_18_1_2"] = 1
        form["question_19_1_1"] = "some more text"
        form["question_19_1_2"] = 1
        form["question_20_1_1"] = "and the last text"
        form["question_20_1_2"] = 1
        form.submit()

        self.get_assert_403("/student/vote/5", user="lazy.student")

    def test_user_cannot_vote_for_themselves(self):
        contributor1 = mommy.make(UserProfile)
        contributor2 = mommy.make(UserProfile)
        student = mommy.make(UserProfile)

        course = mommy.make(Course, state='in_evaluation', participants=[student, contributor1])
        questionnaire = mommy.make(Questionnaire)
        mommy.make(Question, questionnaire=questionnaire, type="G")
        mommy.make(Contribution, contributor=contributor1, course=course, questionnaires=[questionnaire])
        mommy.make(Contribution, contributor=contributor2, course=course, questionnaires=[questionnaire])

        def get_vote_page(user):
            return self.app.get(reverse('student:vote', kwargs={'course_id': course.id}), user=user)

        response = get_vote_page(contributor1)

        for contributor, _, _, _ in response.context['contributor_form_groups']:
            self.assertNotEqual(contributor, contributor1, "Contributor should not see the questionnaire about themselves")

        response = get_vote_page(student)
        self.assertTrue(any(contributor == contributor1 for contributor, _, _, _ in response.context['contributor_form_groups']),
            "Regular students should see the questionnaire about a contributor")
