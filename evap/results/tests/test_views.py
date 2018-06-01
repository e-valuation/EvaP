from django.contrib.auth.models import Group
from django.core.cache import caches
from model_mommy import mommy

from evap.evaluation.models import Semester, UserProfile, Course, Contribution, Questionnaire, Degree, Question, RatingAnswerCounter
from evap.evaluation.tests.tools import ViewTest, WebTest

import random


class TestResultsView(ViewTest):
    url = '/results/'
    test_users = ['staff']

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='staff', email="staff@institution.example.com")


class TestResultsSemesterDetailView(ViewTest):
    url = '/results/semester/1'
    test_users = ['staff']

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='staff', email="staff@institution.example.com")

        cls.semester = mommy.make(Semester, id=1)


class TestResultsViewContributionWarning(WebTest):
    @classmethod
    def setUpTestData(cls):
        cls.semester = mommy.make(Semester, id=3)
        mommy.make(UserProfile, username='staff', groups=[Group.objects.get(name='Staff')])
        contributor = mommy.make(UserProfile)

        # Set up a course with one question but no answers
        student1 = mommy.make(UserProfile)
        student2 = mommy.make(UserProfile)
        cls.course = mommy.make(Course, id=21, state='published', semester=cls.semester, participants=[student1, student2], voters=[student1, student2])
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
    test_users = ['staff', 'contributor', 'responsible']

    @classmethod
    def setUpTestData(cls):
        cls.semester = mommy.make(Semester, id=2)

        mommy.make(UserProfile, username='staff', groups=[Group.objects.get(name='Staff')], email="staff@institution.example.com")
        contributor = mommy.make(UserProfile, username='contributor')
        responsible = mommy.make(UserProfile, username='responsible')

        # Normal course with responsible and contributor.
        cls.course = mommy.make(Course, id=21, state='published', semester=cls.semester)

        # Special single result course.
        cls.single_result_course = mommy.make(Course, state='published', semester=cls.semester)
        questionnaire = Questionnaire.objects.get(name_en=Questionnaire.SINGLE_RESULT_QUESTIONNAIRE_NAME)
        mommy.make(Contribution, course=cls.single_result_course, questionnaires=[questionnaire], responsible=True, can_edit=True, comment_visibility=Contribution.ALL_COMMENTS)

        mommy.make(Contribution, course=cls.course, contributor=responsible, can_edit=True, responsible=True, comment_visibility=Contribution.ALL_COMMENTS)
        cls.contribution = mommy.make(Contribution, course=cls.course, contributor=contributor, can_edit=True)

    def test_questionnaire_ordering(self):
        top_questionnaire = mommy.make(Questionnaire, type=Questionnaire.TOP)
        contributor_questionnaire = mommy.make(Questionnaire, type=Questionnaire.CONTRIBUTOR)
        bottom_questionnaire = mommy.make(Questionnaire, type=Questionnaire.BOTTOM)

        top_heading_question = mommy.make(Question, type="H", questionnaire=top_questionnaire, order=0)
        top_likert_question = mommy.make(Question, type="L", questionnaire=top_questionnaire, order=1)

        contributor_likert_question = mommy.make(Question, type="L", questionnaire=contributor_questionnaire)

        bottom_heading_question = mommy.make(Question, type="H", questionnaire=bottom_questionnaire, order=0)
        bottom_likert_question = mommy.make(Question, type="L", questionnaire=bottom_questionnaire, order=1)

        self.course.general_contribution.questionnaires.set([top_questionnaire, bottom_questionnaire])
        self.contribution.questionnaires.set([contributor_questionnaire])

        mommy.make(RatingAnswerCounter, question=top_likert_question, contribution=self.course.general_contribution, answer=2, count=100)
        mommy.make(RatingAnswerCounter, question=contributor_likert_question, contribution=self.contribution, answer=1, count=100)
        mommy.make(RatingAnswerCounter, question=bottom_likert_question, contribution=self.course.general_contribution, answer=3, count=100)

        content = self.app.get("/results/semester/2/course/21", user='staff').body.decode()

        top_heading_index = content.index(top_heading_question.text)
        top_likert_index = content.index(top_likert_question.text)
        contributor_likert_index = content.index(contributor_likert_question.text)
        bottom_heading_index = content.index(bottom_heading_question.text)
        bottom_likert_index = content.index(bottom_likert_question.text)

        self.assertTrue(top_heading_index < top_likert_index < contributor_likert_index < bottom_heading_index < bottom_likert_index)

    def test_heading_question_filtering(self):
        contributor = mommy.make(UserProfile)
        questionnaire = mommy.make(Questionnaire)

        heading_question_0 = mommy.make(Question, type="H", questionnaire=questionnaire, order=0)
        heading_question_1 = mommy.make(Question, type="H", questionnaire=questionnaire, order=1)
        likert_question = mommy.make(Question, type="L", questionnaire=questionnaire, order=2)
        heading_question_2 = mommy.make(Question, type="H", questionnaire=questionnaire, order=3)

        contribution = mommy.make(Contribution, course=self.course, questionnaires=[questionnaire], contributor=contributor)
        mommy.make(RatingAnswerCounter, question=likert_question, contribution=contribution, answer=3, count=100)

        page = self.app.get("/results/semester/2/course/21", user='staff')

        self.assertNotIn(heading_question_0.text, page)
        self.assertIn(heading_question_1.text, page)
        self.assertIn(likert_question.text, page)
        self.assertNotIn(heading_question_2.text, page)

    def test_single_result_course(self):
        url = '/results/semester/%s/course/%s' % (self.semester.id, self.single_result_course.id)
        user = 'staff'
        self.get_assert_200(url, user)

    def test_default_view_is_public(self):
        url = '/results/semester/%s/course/%s' % (self.semester.id, self.course.id)
        random.seed(42)  # use explicit seed to always choose the same "random" slogan
        page_without_get_parameter = self.app.get(url, user='staff')
        url = '/results/semester/%s/course/%s?public_view=true' % (self.semester.id, self.course.id)
        random.seed(42)
        page_with_get_parameter = self.app.get(url, user='staff')
        url = '/results/semester/%s/course/%s?public_view=asdf' % (self.semester.id, self.course.id)
        random.seed(42)
        page_with_random_get_parameter = self.app.get(url, user='staff')
        self.assertEqual(page_without_get_parameter.body, page_with_get_parameter.body)
        self.assertEqual(page_without_get_parameter.body, page_with_random_get_parameter.body)

    def test_wrong_state(self):
        course = mommy.make(Course, state='reviewed', semester=self.semester)
        url = '/results/semester/%s/course/%s' % (self.semester.id, course.id)
        self.get_assert_403(url, 'student')


class TestResultsSemesterCourseDetailViewFewVoters(ViewTest):
    @classmethod
    def setUpTestData(cls):
        cls.semester = mommy.make(Semester, id=2)
        mommy.make(UserProfile, username='staff', groups=[Group.objects.get(name='Staff')], email="staff@institution.example.com")
        responsible = mommy.make(UserProfile, username='responsible')
        student1 = mommy.make(UserProfile, username='student')
        cls.student2 = mommy.make(UserProfile)

        cls.course = mommy.make(Course, id=22, state='published', semester=cls.semester, participants=[student1, cls.student2], voters=[student1])
        questionnaire = mommy.make(Questionnaire)
        cls.question_grade = mommy.make(Question, questionnaire=questionnaire, type="G")
        question_likert = mommy.make(Question, questionnaire=questionnaire, type="L")
        cls.course.general_contribution.questionnaires.set([questionnaire])
        cls.responsible_contribution = mommy.make(Contribution, contributor=responsible, course=cls.course, questionnaires=[questionnaire])

        mommy.make(RatingAnswerCounter, question=cls.question_grade, contribution=cls.responsible_contribution, answer=1, count=1)
        mommy.make(RatingAnswerCounter, question=question_likert, contribution=cls.responsible_contribution, answer=3, count=1)
        cls.course.general_contribution.questionnaires.set([questionnaire])
        mommy.make(RatingAnswerCounter, question=question_likert, contribution=cls.course.general_contribution, answer=5, count=1)

    def helper_test_answer_visibility(self, username, expect_page_not_visible_first=False):
        caches["results"].clear()
        page = self.app.get("/results/semester/2/course/22", user=username, expect_errors=expect_page_not_visible_first)
        if expect_page_not_visible_first:
            self.assertEqual(page.status_code, 403)
        else:
            self.assertEqual(page.status_code, 200)
            number_of_grade_badges = str(page).count("grade-bg-result-bar text-center")
            self.assertEqual(number_of_grade_badges, 5)  # 1 course overview and 4 questions
            number_of_visible_grade_badges = str(page).count("background-color")
            self.assertEqual(number_of_visible_grade_badges, 0)
            number_of_disabled_grade_badges = str(page).count("grade-bg-result-bar text-center grade-bg-disabled")
            self.assertEqual(number_of_disabled_grade_badges, 5)

        # add additional voter
        self.course.voters.add(self.student2)

        caches["results"].clear()
        page = self.app.get("/results/semester/2/course/22", user=username)
        number_of_grade_badges = str(page).count("grade-bg-result-bar text-center")
        self.assertEqual(number_of_grade_badges, 5)  # 1 course overview and 4 questions
        number_of_visible_grade_badges = str(page).count("background-color")
        self.assertEqual(number_of_visible_grade_badges, 4)  # all but average grade in course overview
        number_of_disabled_grade_badges = str(page).count("grade-bg-result-bar text-center grade-bg-disabled")
        self.assertEqual(number_of_disabled_grade_badges, 1)

        # remove additional voter
        self.course.voters.remove(self.student2)

    def test_answer_visibility(self):
        self.helper_test_answer_visibility("staff")
        self.helper_test_answer_visibility("responsible")
        self.helper_test_answer_visibility("student", expect_page_not_visible_first=True)


class TestResultsSemesterCourseDetailViewPrivateCourse(WebTest):
    def test_private_course(self):
        semester = mommy.make(Semester)
        mommy.make(UserProfile, username='staff', groups=[Group.objects.get(name='Staff')], email="staff@institution.example.com")
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
        self.assertIn(private_course.name, self.app.get(url, user='staff'))
        self.get_assert_403(url, 'student_external')  # external users can't see results semester view

        url = '/results/semester/%s/course/%s' % (semester.id, private_course.id)
        self.get_assert_403(url, "random")
        self.get_assert_200(url, "student")
        self.get_assert_200(url, "responsible")
        self.get_assert_200(url, "other_responsible")
        self.get_assert_200(url, "contributor")
        self.get_assert_200(url, "staff")
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
