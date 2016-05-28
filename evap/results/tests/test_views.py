from django.contrib.auth.models import Group
from model_mommy import mommy

from evap.evaluation.models import Semester, UserProfile, Course, Contribution, Questionnaire, Degree
from evap.evaluation.tests.test_utils import ViewTest


class TestResultsView(ViewTest):
    url = '/results/'
    test_users = ['evap']

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='evap')


class TestResultsSemesterDetailView(ViewTest):
    url = '/results/semester/1'
    test_users = ['evap']

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='evap')

        cls.semester = mommy.make(Semester, id=1)


class TestResultsSemesterCourseDetailView(ViewTest):
    url = '/results/semester/2/course/21'
    test_users = ['evap', 'contributor', 'responsible']

    fixtures = ['minimal_test_data_results']

    @classmethod
    def setUpTestData(cls):
        cls.semester = mommy.make(Semester, id=2)

        mommy.make(UserProfile, username='evap', groups=[Group.objects.get(name='Staff')])
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

    def test_single_result_course(self):
        url = '/results/semester/%s/course/%s' % (self.semester.id, self.single_result_course.id)
        user = 'evap'
        response = self.app.get(url, user=user)
        self.assertEqual(response.status_code, 200, 'url "{}" failed with user "{}"'.format(self.url, user))

    def test_private_course(self):
        student = UserProfile.objects.get(username="student")
        contributor = UserProfile.objects.get(username="contributor")
        responsible = UserProfile.objects.get(username="responsible")
        test1 = mommy.make(UserProfile, username="test1")
        test2 = mommy.make(UserProfile, username="test2")
        mommy.make(UserProfile, username="random")
        degree = mommy.make(Degree)
        private_course = mommy.make(Course, state='published', is_private=True, semester=self.semester, participants=[student, test1, test2], voters=[test1, test2], degrees=[degree])
        mommy.make(Contribution, course=private_course, contributor=responsible, can_edit=True, responsible=True, comment_visibility=Contribution.ALL_COMMENTS)
        mommy.make(Contribution, course=private_course, contributor=contributor, can_edit=True)

        url = '/results/semester/%s' % (self.semester.id)
        page = self.app.get(url, user='random')
        self.assertNotIn(private_course.name, page)
        page = self.app.get(url, user='student')
        self.assertIn(private_course.name, page)
        page = self.app.get(url, user='responsible')
        self.assertIn(private_course.name, page)
        page = self.app.get(url, user='contributor')
        self.assertIn(private_course.name, page)
        page = self.app.get(url, user='evap')
        self.assertIn(private_course.name, page)

        url = '/results/semester/%s/course/%s' % (self.semester.id, private_course.id)
        self.get_assert_403(url, "random")
        self.get_assert_200(url, "student")
        self.get_assert_200(url, "responsible")
        self.get_assert_200(url, "contributor")
        self.get_assert_200(url, "evap")

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

    def test_textanswer_visibility_for_contributor_all_comments(self):
        page = self.app.get("/results/semester/1/course/1", user='contributor_all_comments')
        self.assertIn(".course_orig_published.", page)
        self.assertNotIn(".course_orig_hidden.", page)
        self.assertNotIn(".course_orig_published_changed.", page)
        self.assertIn(".course_changed_published.", page)
        self.assertIn(".responsible_orig_published.", page)
        self.assertNotIn(".responsible_orig_hidden.", page)
        self.assertNotIn(".responsible_orig_published_changed.", page)
        self.assertIn(".responsible_changed_published.", page)
        self.assertNotIn(".responsible_orig_private.", page)
        self.assertNotIn(".responsible_orig_notreviewed.", page)
        self.assertIn(".contributor_orig_published.", page)
        self.assertNotIn(".contributor_orig_private.", page)

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
