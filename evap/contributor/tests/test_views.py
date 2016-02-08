from model_mommy import mommy
from webtest.app import AppError

from evap.evaluation.models import Course, Contribution, UserProfile
from evap.evaluation.tests.test_utils import ViewTest


TESTING_COURSE_ID = 2


def course_with_responsible_and_editor():
    contributor = mommy.make(UserProfile, username='responsible')
    editor = mommy.make(UserProfile, username='editor')

    course = mommy.make(Course, state='prepared', id=TESTING_COURSE_ID)

    mommy.make(Contribution, course=course, contributor=contributor, can_edit=True, responsible=True)
    mommy.make(Contribution, course=course, contributor=editor, can_edit=True)

    return course


class TestContributorView(ViewTest):
    url = '/contributor/'
    test_users = ['editor', 'responsible']

    @classmethod
    def setUpTestData(cls):
        course_with_responsible_and_editor()


class TestContributorSettingsView(ViewTest):
    url = '/contributor/settings'
    test_users = ['editor', 'responsible']

    @classmethod
    def setUpTestData(cls):
        course_with_responsible_and_editor()

class TestContributorCourseView(ViewTest):
    test_users = ['editor', 'responsible']
    url = '/contributor/course/%s' % TESTING_COURSE_ID

    @classmethod
    def setUpTestData(cls):
        course_with_responsible_and_editor()


class TestContributorCoursePreviewView(ViewTest):
    test_users = ['editor', 'responsible']
    url = '/contributor/course/%s/preview' % TESTING_COURSE_ID

    @classmethod
    def setUpTestData(cls):
        course_with_responsible_and_editor()


class TestContributorCourseEditView(ViewTest):
    test_users = ['editor', 'responsible']
    url = '/contributor/course/%s/edit' % TESTING_COURSE_ID

    @classmethod
    def setUpTestData(cls):
        course_with_responsible_and_editor()

    def get_assert_403(self, url, user):
        try:
            self.app.get(url, user=user, status=403)
        except AppError as e:
            self.fail('url "{}" failed with user "{}"'.format(url, user))

    def test_not_authenticated(self):
        """
            Asserts that an unauthorized user gets redirected to the login page.
        """
        response = self.app.get(self.url)
        self.assertRedirects(response, '/?next=/contributor/course/%s/edit' % TESTING_COURSE_ID)

    def test_wrong_usergroup(self):
        """
            Asserts that a user who is not part of the usergroup
            that is required for a specific view gets a 403.
            Regression test for #483
        """
        self.get_assert_403(self.url, 'student')

    def test_wrong_state(self):
        """
            Asserts that a contributor attempting to edit a course
            that is in a state where editing is not allowed gets a 403.
        """
        course = Course.objects.get(pk=TESTING_COURSE_ID)

        course.editor_approve()
        course.save()

        self.get_assert_403(self.url, 'responsible')
