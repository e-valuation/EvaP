from django.contrib.auth.models import Group
from model_mommy import mommy

from evap.evaluation.models import Semester, UserProfile, Course, Contribution, Questionnaire, Degree, Question, RatingAnswerCounter
from evap.evaluation.tests.tools import ViewTest

import random


class TestResultsView(ViewTest):
    url = '/results/'
    test_users = ['evap']

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='evap', email="evap@institution.example.com")


class TestResultsSemesterDetailView(ViewTest):
    url = '/results/semester/1'
    test_users = ['evap']

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='evap', email="evap@institution.example.com")

        cls.semester = mommy.make(Semester, id=1)


class TestResultsSemesterCourseDetailView(ViewTest):
    url = '/results/semester/2/course/21'
    test_users = ['evap', 'contributor', 'responsible']

    fixtures = ['minimal_test_data_results']

    @classmethod
    def setUpTestData(cls):
        cls.semester = mommy.make(Semester, id=2)

        mommy.make(UserProfile, username='evap', groups=[Group.objects.get(name='Staff')], email="evap@institution.example.com")
        contributor = UserProfile.objects.get(username="contributor")
        responsible = UserProfile.objects.get(username="responsible")
        # contributor = mommy.make(UserProfile, username='contributor')  # Add again when fixtures are removed
        # responsible = mommy.make(UserProfile, username='responsible')

        # Normal course with responsible and contributor.
        cls.course = mommy.make(Course, id=21, state='published', semester=cls.semester)

        # Special single result course.
        cls.single_result_course = mommy.make(Course, state='published', semester=cls.semester)
        questionnaire = Questionnaire.objects.get(name_en=Questionnaire.SINGLE_RESULT_QUESTIONNAIRE_NAME)
        mommy.make(Contribution, course=cls.single_result_course, questionnaires=[questionnaire], responsible=True, can_edit=True, comment_visibility=Contribution.ALL_COMMENTS)

        mommy.make(Contribution, course=cls.course, contributor=responsible, can_edit=True, responsible=True, comment_visibility=Contribution.ALL_COMMENTS)
        mommy.make(Contribution, course=cls.course, contributor=contributor, can_edit=True)

    def _create_questionaire_with_answers(self, answer_count=10):
        questionnaire = mommy.make(Questionnaire)
        likert_question = mommy.make(Question, type="L", questionnaire=questionnaire, order=2)
        contributor = mommy.make(UserProfile)
        contribution = mommy.make(Contribution, course=self.course, questionnaires=[questionnaire], contributor=contributor)
        mommy.make(RatingAnswerCounter, question=likert_question, contribution=contribution, answer=3, count=answer_count)

    def test_heading_question_filtering(self):
        contributor = mommy.make(UserProfile)
        questionnaire = mommy.make(Questionnaire)

        heading_question_0 = mommy.make(Question, type="H", questionnaire=questionnaire, order=0)
        heading_question_1 = mommy.make(Question, type="H", questionnaire=questionnaire, order=1)
        likert_question = mommy.make(Question, type="L", questionnaire=questionnaire, order=2)
        heading_question_2 = mommy.make(Question, type="H", questionnaire=questionnaire, order=3)

        contribution = mommy.make(Contribution, course=self.course, questionnaires=[questionnaire], contributor=contributor)
        mommy.make(RatingAnswerCounter, question=likert_question, contribution=contribution, answer=3, count=100)

        page = self.app.get("/results/semester/2/course/21", user='evap')

        self.assertNotIn(heading_question_0.text, page)
        self.assertIn(heading_question_1.text, page)
        self.assertIn(likert_question.text, page)
        self.assertNotIn(heading_question_2.text, page)

    def test_many_answers_course_no_warning(self):
        self._create_questionaire_with_answers(answer_count=10)
        url = '/results/semester/%s/course/%s' % (self.semester.id, self.course.id)
        user = 'evap'
        page = self.get_assert_200(url, user)
        self.assertNotIn("Only a few participants answered these questions.", page)

    def test_zero_answers_course_no_warning(self):
        self._create_questionaire_with_answers(answer_count=0)
        url = '/results/semester/%s/course/%s' % (self.semester.id, self.course.id)
        user = 'evap'
        page = self.get_assert_200(url, user)
        self.assertNotIn("Only a few participants answered these questions.", page)

    def test_few_answers_course_show_warning(self):
        self._create_questionaire_with_answers(answer_count=3)
        url = '/results/semester/%s/course/%s' % (self.semester.id, self.course.id)
        user = 'evap'
        page = self.get_assert_200(url, user)
        self.assertIn("Only a few participants answered these questions.", page)

    def test_single_result_course(self):
        url = '/results/semester/%s/course/%s' % (self.semester.id, self.single_result_course.id)
        user = 'evap'
        self.get_assert_200(url, user)

    def test_default_view_is_public(self):
        url = '/results/semester/%s/course/%s' % (self.semester.id, self.course.id)
        random.seed(42)  # use explicit seed to always choose the same "random" slogan
        page_without_get_parameter = self.app.get(url, user='evap')
        url = '/results/semester/%s/course/%s?public_view=true' % (self.semester.id, self.course.id)
        random.seed(42)
        page_with_get_parameter = self.app.get(url, user='evap')
        url = '/results/semester/%s/course/%s?public_view=asdf' % (self.semester.id, self.course.id)
        random.seed(42)
        page_with_random_get_parameter = self.app.get(url, user='evap')
        self.assertEqual(page_without_get_parameter.body, page_with_get_parameter.body)
        self.assertEqual(page_without_get_parameter.body, page_with_random_get_parameter.body)

    def test_wrong_state(self):
        course = mommy.make(Course, state='reviewed', semester=self.semester)
        url = '/results/semester/%s/course/%s' % (self.semester.id, course.id)
        self.get_assert_403(url, 'student')

    def test_private_course(self):
        student = UserProfile.objects.get(username="student")
        student_external = UserProfile.objects.get(username="student_external")
        contributor = UserProfile.objects.get(username="contributor")
        responsible = UserProfile.objects.get(username="responsible")
        other_responsible = UserProfile.objects.get(username="other_responsible")
        test1 = mommy.make(UserProfile, username="test1")
        test2 = mommy.make(UserProfile, username="test2")
        mommy.make(UserProfile, username="random", email="random@institution.example.com")
        degree = mommy.make(Degree)
        private_course = mommy.make(Course, state='published', is_private=True, semester=self.semester, participants=[student, student_external, test1, test2], voters=[test1, test2], degrees=[degree])
        mommy.make(Contribution, course=private_course, contributor=responsible, can_edit=True, responsible=True, comment_visibility=Contribution.ALL_COMMENTS)
        mommy.make(Contribution, course=private_course, contributor=other_responsible, can_edit=True, responsible=True, comment_visibility=Contribution.ALL_COMMENTS)
        mommy.make(Contribution, course=private_course, contributor=contributor, can_edit=True)

        url = '/results/semester/%s' % (self.semester.id)
        page = self.app.get(url, user='random')
        self.assertNotIn(private_course.name, page)
        page = self.app.get(url, user='student')
        self.assertIn(private_course.name, page)
        page = self.app.get(url, user='responsible')
        self.assertIn(private_course.name, page)
        page = self.app.get(url, user='other_responsible')
        self.assertIn(private_course.name, page)
        page = self.app.get(url, user='contributor')
        self.assertIn(private_course.name, page)
        page = self.app.get(url, user='evap')
        self.assertIn(private_course.name, page)
        self.get_assert_403(url, 'student_external')  # external users can't see results semester view

        url = '/results/semester/%s/course/%s' % (self.semester.id, private_course.id)
        self.get_assert_403(url, "random")
        self.get_assert_200(url, "student")
        self.get_assert_200(url, "responsible")
        self.get_assert_200(url, "other_responsible")
        self.get_assert_200(url, "contributor")
        self.get_assert_200(url, "evap")
        self.get_assert_200(url, "student_external")  # this external user participates in the course and can see the results

    def test_textanswer_visibility_for_responsible(self):
        page = self.app.get("/results/semester/1/course/1", user='responsible')
        self.assertIn(".course_orig_published.", page)
        self.assertNotIn(".course_orig_hidden.", page)
        self.assertNotIn(".course_orig_published_changed.", page)
        self.assertIn(".course_changed_published.", page)
        self.assertIn(".responsible_orig_published.", page)
        self.assertNotIn(".responsible_orig_hidden.", page)
        self.assertNotIn(".responsible_orig_published_changed.", page)
        self.assertIn(".responsible_changed_published.", page)
        self.assertIn(".responsible_orig_private.", page)
        self.assertNotIn(".responsible_orig_notreviewed.", page)
        self.assertIn(".contributor_orig_published.", page)
        self.assertNotIn(".contributor_orig_private.", page)  # private comment not visible
        self.assertNotIn(".other_responsible_orig_published.", page)
        self.assertNotIn(".other_responsible_orig_hidden.", page)
        self.assertNotIn(".other_responsible_orig_published_changed.", page)
        self.assertNotIn(".other_responsible_changed_published.", page)
        self.assertNotIn(".other_responsible_orig_private.", page)
        self.assertNotIn(".other_responsible_orig_notreviewed.", page)

    def test_textanswer_visibility_for_other_responsible(self):
        page = self.app.get("/results/semester/1/course/1", user='other_responsible')
        self.assertIn(".course_orig_published.", page)
        self.assertNotIn(".course_orig_hidden.", page)
        self.assertNotIn(".course_orig_published_changed.", page)
        self.assertIn(".course_changed_published.", page)
        self.assertNotIn(".responsible_orig_published.", page)
        self.assertNotIn(".responsible_orig_hidden.", page)
        self.assertNotIn(".responsible_orig_published_changed.", page)
        self.assertNotIn(".responsible_changed_published.", page)
        self.assertNotIn(".responsible_orig_private.", page)
        self.assertNotIn(".responsible_orig_notreviewed.", page)
        self.assertIn(".contributor_orig_published.", page)
        self.assertNotIn(".contributor_orig_private.", page)  # private comment not visible
        self.assertIn(".other_responsible_orig_published.", page)
        self.assertNotIn(".other_responsible_orig_hidden.", page)
        self.assertNotIn(".other_responsible_orig_published_changed.", page)
        self.assertIn(".other_responsible_changed_published.", page)
        self.assertIn(".other_responsible_orig_private.", page)
        self.assertNotIn(".other_responsible_orig_notreviewed.", page)

    def test_textanswer_visibility_for_delegate_for_responsible(self):
        page = self.app.get("/results/semester/1/course/1", user='delegate_for_responsible')
        self.assertIn(".course_orig_published.", page)
        self.assertNotIn(".course_orig_hidden.", page)
        self.assertNotIn(".course_orig_published_changed.", page)
        self.assertIn(".course_changed_published.", page)
        self.assertIn(".responsible_orig_published.", page)
        self.assertNotIn(".responsible_orig_hidden.", page)
        self.assertNotIn(".responsible_orig_published_changed.", page)
        self.assertIn(".responsible_changed_published.", page)
        self.assertNotIn(".responsible_orig_private.", page)  # private comment not visible
        self.assertNotIn(".responsible_orig_notreviewed.", page)
        self.assertIn(".contributor_orig_published.", page)
        self.assertNotIn(".contributor_orig_private.", page)  # private comment not visible
        self.assertNotIn(".other_responsible_orig_published.", page)
        self.assertNotIn(".other_responsible_orig_hidden.", page)
        self.assertNotIn(".other_responsible_orig_published_changed.", page)
        self.assertNotIn(".other_responsible_changed_published.", page)
        self.assertNotIn(".other_responsible_orig_private.", page)
        self.assertNotIn(".other_responsible_orig_notreviewed.", page)

    def test_textanswer_visibility_for_contributor(self):
        page = self.app.get("/results/semester/1/course/1", user='contributor')
        self.assertNotIn(".course_orig_published.", page)
        self.assertNotIn(".course_orig_hidden.", page)
        self.assertNotIn(".course_orig_published_changed.", page)
        self.assertNotIn(".course_changed_published.", page)
        self.assertNotIn(".responsible_orig_published.", page)
        self.assertNotIn(".responsible_orig_hidden.", page)
        self.assertNotIn(".responsible_orig_published_changed.", page)
        self.assertNotIn(".responsible_changed_published.", page)
        self.assertNotIn(".responsible_orig_private.", page)
        self.assertNotIn(".responsible_orig_notreviewed.", page)
        self.assertIn(".contributor_orig_published.", page)
        self.assertIn(".contributor_orig_private.", page)
        self.assertNotIn(".other_responsible_orig_published.", page)
        self.assertNotIn(".other_responsible_orig_hidden.", page)
        self.assertNotIn(".other_responsible_orig_published_changed.", page)
        self.assertNotIn(".other_responsible_changed_published.", page)
        self.assertNotIn(".other_responsible_orig_private.", page)
        self.assertNotIn(".other_responsible_orig_notreviewed.", page)

    def test_textanswer_visibility_for_delegate_for_contributor(self):
        page = self.app.get("/results/semester/1/course/1", user='delegate_for_contributor')
        self.assertNotIn(".course_orig_published.", page)
        self.assertNotIn(".course_orig_hidden.", page)
        self.assertNotIn(".course_orig_published_changed.", page)
        self.assertNotIn(".course_changed_published.", page)
        self.assertNotIn(".responsible_orig_published.", page)
        self.assertNotIn(".responsible_orig_hidden.", page)
        self.assertNotIn(".responsible_orig_published_changed.", page)
        self.assertNotIn(".responsible_changed_published.", page)
        self.assertNotIn(".responsible_orig_private.", page)
        self.assertNotIn(".responsible_orig_notreviewed.", page)
        self.assertIn(".contributor_orig_published.", page)
        self.assertNotIn(".contributor_orig_private.", page)
        self.assertNotIn(".other_responsible_orig_published.", page)
        self.assertNotIn(".other_responsible_orig_hidden.", page)
        self.assertNotIn(".other_responsible_orig_published_changed.", page)
        self.assertNotIn(".other_responsible_changed_published.", page)
        self.assertNotIn(".other_responsible_orig_private.", page)
        self.assertNotIn(".other_responsible_orig_notreviewed.", page)

    def test_textanswer_visibility_for_contributor_course_comments(self):
        page = self.app.get("/results/semester/1/course/1", user='contributor_course_comments')
        self.assertIn(".course_orig_published.", page)
        self.assertNotIn(".course_orig_hidden.", page)
        self.assertNotIn(".course_orig_published_changed.", page)
        self.assertIn(".course_changed_published.", page)
        self.assertNotIn(".responsible_orig_published.", page)
        self.assertNotIn(".responsible_orig_hidden.", page)
        self.assertNotIn(".responsible_orig_published_changed.", page)
        self.assertNotIn(".responsible_changed_published.", page)
        self.assertNotIn(".responsible_orig_private.", page)
        self.assertNotIn(".responsible_orig_notreviewed.", page)
        self.assertNotIn(".contributor_orig_published.", page)
        self.assertNotIn(".contributor_orig_private.", page)
        self.assertNotIn(".other_responsible_orig_published.", page)
        self.assertNotIn(".other_responsible_orig_hidden.", page)
        self.assertNotIn(".other_responsible_orig_published_changed.", page)
        self.assertNotIn(".other_responsible_changed_published.", page)
        self.assertNotIn(".other_responsible_orig_private.", page)
        self.assertNotIn(".other_responsible_orig_notreviewed.", page)

    def test_textanswer_visibility_for_contributor_all_comments(self):
        page = self.app.get("/results/semester/1/course/1", user='contributor_all_comments')
        self.assertIn(".course_orig_published.", page)
        self.assertNotIn(".course_orig_hidden.", page)
        self.assertNotIn(".course_orig_published_changed.", page)
        self.assertIn(".course_changed_published.", page)
        self.assertNotIn(".responsible_orig_published.", page)
        self.assertNotIn(".responsible_orig_hidden.", page)
        self.assertNotIn(".responsible_orig_published_changed.", page)
        self.assertNotIn(".responsible_changed_published.", page)
        self.assertNotIn(".responsible_orig_private.", page)
        self.assertNotIn(".responsible_orig_notreviewed.", page)
        self.assertIn(".contributor_orig_published.", page)
        self.assertNotIn(".contributor_orig_private.", page)
        self.assertNotIn(".other_responsible_orig_published.", page)
        self.assertNotIn(".other_responsible_orig_hidden.", page)
        self.assertNotIn(".other_responsible_orig_published_changed.", page)
        self.assertNotIn(".other_responsible_changed_published.", page)
        self.assertNotIn(".other_responsible_orig_private.", page)
        self.assertNotIn(".other_responsible_orig_notreviewed.", page)

    def test_textanswer_visibility_for_student(self):
        page = self.app.get("/results/semester/1/course/1", user='student')
        self.assertNotIn(".course_orig_published.", page)
        self.assertNotIn(".course_orig_hidden.", page)
        self.assertNotIn(".course_orig_published_changed.", page)
        self.assertNotIn(".course_changed_published.", page)
        self.assertNotIn(".responsible_orig_published.", page)
        self.assertNotIn(".responsible_orig_hidden.", page)
        self.assertNotIn(".responsible_orig_published_changed.", page)
        self.assertNotIn(".responsible_changed_published.", page)
        self.assertNotIn(".responsible_orig_private.", page)
        self.assertNotIn(".responsible_orig_notreviewed.", page)
        self.assertNotIn(".contributor_orig_published.", page)
        self.assertNotIn(".contributor_orig_private.", page)
        self.assertNotIn(".other_responsible_orig_published.", page)
        self.assertNotIn(".other_responsible_orig_hidden.", page)
        self.assertNotIn(".other_responsible_orig_published_changed.", page)
        self.assertNotIn(".other_responsible_changed_published.", page)
        self.assertNotIn(".other_responsible_orig_private.", page)
        self.assertNotIn(".other_responsible_orig_notreviewed.", page)

    def test_textanswer_visibility_for_student_external(self):
        # the external user does not participate in or contribute to the course and therefore can't see the results
        self.get_assert_403("/results/semester/1/course/1", 'student_external')
