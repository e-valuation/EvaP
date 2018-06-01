from django.test.utils import override_settings
from django.urls import reverse
from model_mommy import mommy

from evap.evaluation.models import UserProfile, Course, Questionnaire, Question, Contribution, TextAnswer, RatingAnswerCounter
from evap.evaluation.tests.tools import ViewTest
from evap.student.tools import question_id
from evap.student.views import SUCCESS_MAGIC_STRING


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

        cls.top_course_questionnaire = mommy.make(Questionnaire, type=Questionnaire.TOP)
        cls.bottom_course_questionnaire = mommy.make(Questionnaire, type=Questionnaire.BOTTOM)
        cls.contributor_questionnaire = mommy.make(Questionnaire, type=Questionnaire.CONTRIBUTOR)

        cls.contributor_heading_question = mommy.make(Question, questionnaire=cls.contributor_questionnaire, order=0, type="H")
        cls.contributor_text_question = mommy.make(Question, questionnaire=cls.contributor_questionnaire, order=1, type="T")
        cls.contributor_likert_question = mommy.make(Question, questionnaire=cls.contributor_questionnaire, order=2, type="L")

        cls.top_heading_question = mommy.make(Question, questionnaire=cls.top_course_questionnaire, order=0, type="H")
        cls.top_text_question = mommy.make(Question, questionnaire=cls.top_course_questionnaire, order=1, type="T")
        cls.top_likert_question = mommy.make(Question, questionnaire=cls.top_course_questionnaire, order=2, type="L")
        cls.top_grade_question = mommy.make(Question, questionnaire=cls.top_course_questionnaire, order=3, type="G")

        cls.bottom_heading_question = mommy.make(Question, questionnaire=cls.bottom_course_questionnaire, order=0, type="H")
        cls.bottom_text_question = mommy.make(Question, questionnaire=cls.bottom_course_questionnaire, order=1, type="T")
        cls.bottom_likert_question = mommy.make(Question, questionnaire=cls.bottom_course_questionnaire, order=2, type="L")
        cls.bottom_grade_question = mommy.make(Question, questionnaire=cls.bottom_course_questionnaire, order=3, type="G")

        cls.contribution1 = mommy.make(Contribution, contributor=cls.contributor1, questionnaires=[cls.contributor_questionnaire],
                                       course=cls.course)
        cls.contribution2 = mommy.make(Contribution, contributor=cls.contributor2, questionnaires=[cls.contributor_questionnaire],
                                       course=cls.course)

        cls.course.general_contribution.questionnaires.set([cls.top_course_questionnaire, cls.bottom_course_questionnaire])

    def test_question_ordering(self):
        page = self.get_assert_200(self.url, user=self.voting_user1.username)

        top_heading_index = page.body.decode().index(self.top_heading_question.text)
        top_text_index = page.body.decode().index(self.top_text_question.text)

        contributor_heading_index = page.body.decode().index(self.contributor_heading_question.text)
        contributor_likert_index = page.body.decode().index(self.contributor_likert_question.text)

        bottom_heading_index = page.body.decode().index(self.bottom_heading_question.text)
        bottom_grade_index = page.body.decode().index(self.bottom_grade_question.text)

        self.assertTrue(top_heading_index < top_text_index < contributor_heading_index < contributor_likert_index < bottom_heading_index < bottom_grade_index)

    def fill_form(self, form, fill_complete):
        form[question_id(self.course.general_contribution, self.top_course_questionnaire, self.top_text_question)] = "some text"
        form[question_id(self.course.general_contribution, self.top_course_questionnaire, self.top_grade_question)] = 3
        form[question_id(self.course.general_contribution, self.top_course_questionnaire, self.top_likert_question)] = 1

        form[question_id(self.course.general_contribution, self.bottom_course_questionnaire, self.bottom_text_question)] = "some bottom text"
        form[question_id(self.course.general_contribution, self.bottom_course_questionnaire, self.bottom_grade_question)] = 4
        form[question_id(self.course.general_contribution, self.bottom_course_questionnaire, self.bottom_likert_question)] = 2

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

        self.assertEqual(response.status_code, 200)
        self.assertIn("vote for all rating questions", response)

        form = page.forms["student-vote-form"]

        self.assertEqual(form[question_id(self.course.general_contribution, self.top_course_questionnaire, self.top_text_question)].value, "some text")
        self.assertEqual(form[question_id(self.course.general_contribution, self.top_course_questionnaire, self.top_likert_question)].value, "1")
        self.assertEqual(form[question_id(self.course.general_contribution, self.top_course_questionnaire, self.top_grade_question)].value, "3")

        self.assertEqual(form[question_id(self.course.general_contribution, self.bottom_course_questionnaire, self.bottom_text_question)].value, "some bottom text")
        self.assertEqual(form[question_id(self.course.general_contribution, self.bottom_course_questionnaire, self.bottom_likert_question)].value, "2")
        self.assertEqual(form[question_id(self.course.general_contribution, self.bottom_course_questionnaire, self.bottom_grade_question)].value, "4")

        self.assertEqual(form[question_id(self.contribution1, self.contributor_questionnaire, self.contributor_text_question)].value, "some other text")
        self.assertEqual(form[question_id(self.contribution1, self.contributor_questionnaire, self.contributor_likert_question)].value, "4")

        self.assertEqual(form[question_id(self.contribution2, self.contributor_questionnaire, self.contributor_text_question)].value, "some more text")

    def test_answer(self):
        page = self.get_assert_200(self.url, user=self.voting_user1.username)
        form = page.forms["student-vote-form"]
        self.fill_form(form, fill_complete=True)
        response = form.submit()
        self.assertEqual(SUCCESS_MAGIC_STRING, response.body.decode())

        page = self.get_assert_200(self.url, user=self.voting_user2.username)
        form = page.forms["student-vote-form"]
        self.fill_form(form, fill_complete=True)
        response = form.submit()
        self.assertEqual(SUCCESS_MAGIC_STRING, response.body.decode())

        self.assertEqual(len(TextAnswer.objects.all()), 8)
        self.assertEqual(len(RatingAnswerCounter.objects.all()), 6)

        self.assertEqual(RatingAnswerCounter.objects.filter(question=self.top_likert_question).count(), 1)
        self.assertEqual(RatingAnswerCounter.objects.get(question=self.top_likert_question).answer, 1)

        self.assertEqual(RatingAnswerCounter.objects.filter(question=self.top_grade_question).count(), 1)
        self.assertEqual(RatingAnswerCounter.objects.get(question=self.top_grade_question).answer, 3)

        self.assertEqual(RatingAnswerCounter.objects.filter(question=self.bottom_likert_question).count(), 1)
        self.assertEqual(RatingAnswerCounter.objects.get(question=self.bottom_likert_question).answer, 2)

        self.assertEqual(RatingAnswerCounter.objects.filter(question=self.bottom_grade_question).count(), 1)
        self.assertEqual(RatingAnswerCounter.objects.get(question=self.bottom_grade_question).answer, 4)

        self.assertEqual(RatingAnswerCounter.objects.filter(question=self.contributor_likert_question).count(), 2)
        self.assertEqual(RatingAnswerCounter.objects.get(question=self.contributor_likert_question, contribution=self.contribution1).answer, 4)
        self.assertEqual(RatingAnswerCounter.objects.get(question=self.contributor_likert_question, contribution=self.contribution2).answer, 2)

        self.assertEqual(TextAnswer.objects.filter(question=self.top_text_question).count(), 2)
        self.assertEqual(TextAnswer.objects.filter(question=self.bottom_text_question).count(), 2)
        self.assertEqual(TextAnswer.objects.filter(question=self.contributor_text_question).count(), 4)

        self.assertEqual(TextAnswer.objects.filter(question=self.top_text_question)[0].contribution, self.course.general_contribution)
        self.assertEqual(TextAnswer.objects.filter(question=self.top_text_question)[1].contribution, self.course.general_contribution)

        answers = TextAnswer.objects.filter(question=self.contributor_text_question, contribution=self.contribution1).values_list('original_answer', flat=True)
        self.assertEqual(list(answers), ["some other text"] * 2)

        answers = TextAnswer.objects.filter(question=self.contributor_text_question, contribution=self.contribution2).values_list('original_answer', flat=True)
        self.assertEqual(list(answers), ["some more text"] * 2)

        answers = TextAnswer.objects.filter(question=self.top_text_question, contribution=self.course.general_contribution).values_list('original_answer', flat=True)
        self.assertEqual(list(answers), ["some text"] * 2)

        answers = TextAnswer.objects.filter(question=self.bottom_text_question, contribution=self.course.general_contribution).values_list('original_answer', flat=True)
        self.assertEqual(list(answers), ["some bottom text"] * 2)

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

    def test_user_logged_out(self):
        page = self.get_assert_200(self.url, user=self.voting_user1.username)
        form = page.forms["student-vote-form"]
        self.fill_form(form, fill_complete=True)
        page = self.get_assert_302(reverse("django-auth-logout"), user=self.voting_user1.username)
        response = form.submit()
        self.assertEqual(response.status_code, 302)
        self.assertNotIn(SUCCESS_MAGIC_STRING, response)

    def test_midterm_evaluation_warning(self):
        evaluation_warning = "The results of this evaluation will be published while the course is still running."
        page = self.get_assert_200(self.url, user=self.voting_user1.username)
        self.assertNotIn(evaluation_warning, page)

        self.course.is_midterm_evaluation = True
        self.course.save()

        page = self.get_assert_200(self.url, user=self.voting_user1.username)
        self.assertIn(evaluation_warning, page)

    def helper_test_answer_publish_confirmation(self, form_element):
        page = self.get_assert_200(self.url, user=self.voting_user1.username)
        form = page.forms["student-vote-form"]
        self.fill_form(form, fill_complete=True)
        if form_element:
            form[form_element] = True
        response = form.submit()
        self.assertEqual(SUCCESS_MAGIC_STRING, response.body.decode())
        course = Course.objects.get(pk=self.course.pk)
        if form_element:
            self.assertTrue(course.can_publish_text_results)
        else:
            self.assertFalse(course.can_publish_text_results)

    def test_user_checked_top_text_answer_publish_confirmation(self):
        self.helper_test_answer_publish_confirmation("text_results_publish_confirmation_top")

    def test_user_checked_bottom_text_answer_publish_confirmation(self):
        self.helper_test_answer_publish_confirmation("text_results_publish_confirmation_bottom")

    def test_user_did_not_check_text_answer_publish_confirmation(self):
        self.helper_test_answer_publish_confirmation(None)
