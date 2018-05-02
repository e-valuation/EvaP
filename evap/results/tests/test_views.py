from django.contrib.auth.models import Group
from model_mommy import mommy

from evap.evaluation.models import Semester, UserProfile, Course, Contribution, Questionnaire, Degree, Question, RatingAnswerCounter
from evap.evaluation.tests.tools import ViewTest, WebTest

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


class TestResultsViewContributionWarning(WebTest):

    @classmethod
    def setUpTestData(cls):
        cls.semester = mommy.make(Semester, id=3)
        staff = mommy.make(UserProfile, username='staff', groups=[Group.objects.get(name='Staff')])
        contributor = mommy.make(UserProfile)

        # Set up a course with one question but no answers
        cls.course = mommy.make(Course, id=21, state='published', semester=cls.semester)
        questionnaire = mommy.make(Questionnaire)
        cls.contribution = mommy.make(Contribution, course=cls.course, questionnaires=[questionnaire], contributor=contributor)
        cls.likert_question = mommy.make(Question, type="L", questionnaire=questionnaire, order=2)
        cls.url = '/results/semester/%s/course/%s' % (cls.semester.id, cls.course.id)

    def test_many_answers_course_no_warning(self):
        mommy.make(RatingAnswerCounter, question=self.likert_question, contribution=self.contribution, answer=3, count=10)
        page = self.get_assert_200(self.url, 'staff')
        self.assertNotIn("Only a few participants answered these questions.", page)

    def test_zero_answers_course_no_warning(self):
        page = self.get_assert_200(self.url, 'staff')
        self.assertNotIn("Only a few participants answered these questions.", page)

    def test_few_answers_course_show_warning(self):
        mommy.make(RatingAnswerCounter, question=self.likert_question, contribution=self.contribution, answer=3, count=3)
        page = self.get_assert_200(self.url, 'staff')
        self.assertIn("Only a few participants answered these questions.", page)


class TestResultsSemesterCourseDetailView(ViewTest):
    url = '/results/semester/2/course/21'
    test_users = ['evap', 'contributor', 'responsible']

    @classmethod
    def setUpTestData(cls):
        cls.semester = mommy.make(Semester, id=2)

        mommy.make(UserProfile, username='evap', groups=[Group.objects.get(name='Staff')], email="evap@institution.example.com")
        contributor = mommy.make(UserProfile, username='contributor')
        responsible = mommy.make(UserProfile, username='responsible')

        # Normal course with responsible and contributor.
        cls.course = mommy.make(Course, id=21, state='published', semester=cls.semester)

        # Special single result course.
        cls.single_result_course = mommy.make(Course, state='published', semester=cls.semester)
        questionnaire = Questionnaire.objects.get(name_en=Questionnaire.SINGLE_RESULT_QUESTIONNAIRE_NAME)
        mommy.make(Contribution, course=cls.single_result_course, questionnaires=[questionnaire], responsible=True, can_edit=True, comment_visibility=Contribution.ALL_COMMENTS)

        mommy.make(Contribution, course=cls.course, contributor=responsible, can_edit=True, responsible=True, comment_visibility=Contribution.ALL_COMMENTS)
        mommy.make(Contribution, course=cls.course, contributor=contributor, can_edit=True)

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

class TestResultsSemesterCourseDetailViewPrivateCourse(WebTest):
    def test_private_course(self):
        semester = mommy.make(Semester)
        mommy.make(UserProfile, username='evap', groups=[Group.objects.get(name='Staff')], email="evap@institution.example.com")
        student = mommy.make(UserProfile, username="student", email="student@institution.example.com")
        student_external = mommy.make(UserProfile, username="student_external")
        contributor = mommy.make(UserProfile, username="contributor", email="contributor@institution.example.com")
        responsible = mommy.make(UserProfile, username="responsible", email="responsible@institution.example.com")
        other_responsible = mommy.make(UserProfile, username="other_responsible", email="other_responsible@institution.example.com")
        test1 = mommy.make(UserProfile, username="test1")
        test2 = mommy.make(UserProfile, username="test2")
        mommy.make(UserProfile, username="random", email="random@institution.example.com")
        degree = mommy.make(Degree)
        private_course = mommy.make(Course, state='published', is_private=True, semester=semester, participants=[student, student_external, test1, test2], voters=[test1, test2], degrees=[degree])
        mommy.make(Contribution, course=private_course, contributor=responsible, can_edit=True, responsible=True, comment_visibility=Contribution.ALL_COMMENTS)
        mommy.make(Contribution, course=private_course, contributor=other_responsible, can_edit=True, responsible=True, comment_visibility=Contribution.ALL_COMMENTS)
        mommy.make(Contribution, course=private_course, contributor=contributor, can_edit=True)

        url = '/results/semester/%s' % (semester.id)
        self.assertNotIn(private_course.name, self.app.get(url, user='random'))
        self.assertIn(private_course.name, self.app.get(url, user='student'))
        self.assertIn(private_course.name, self.app.get(url, user='responsible'))
        self.assertIn(private_course.name, self.app.get(url, user='other_responsible'))
        self.assertIn(private_course.name, self.app.get(url, user='contributor'))
        self.assertIn(private_course.name, self.app.get(url, user='evap'))
        self.get_assert_403(url, 'student_external')  # external users can't see results semester view

        url = '/results/semester/%s/course/%s' % (semester.id, private_course.id)
        self.get_assert_403(url, "random")
        self.get_assert_200(url, "student")
        self.get_assert_200(url, "responsible")
        self.get_assert_200(url, "other_responsible")
        self.get_assert_200(url, "contributor")
        self.get_assert_200(url, "evap")
        self.get_assert_200(url, "student_external")  # this external user participates in the course and can see the results


class TestResultsTextanswerVisibility(WebTest):

    fixtures = ['minimal_test_data_results']

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
