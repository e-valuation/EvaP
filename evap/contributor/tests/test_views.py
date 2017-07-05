from evap.evaluation.models import Course
from evap.evaluation.tests.tools import ViewTest, course_with_responsible_and_editor

TESTING_COURSE_ID = 2


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
        course_with_responsible_and_editor(course_id=2)


class TestContributorCoursePreviewView(ViewTest):
    test_users = ['editor', 'responsible']
    url = '/contributor/course/%s/preview' % TESTING_COURSE_ID

    @classmethod
    def setUpTestData(cls):
        course_with_responsible_and_editor(course_id=2)


class TestContributorCourseEditView(ViewTest):
    test_users = ['editor', 'responsible']
    url = '/contributor/course/%s/edit' % TESTING_COURSE_ID

    @classmethod
    def setUpTestData(cls):
        course_with_responsible_and_editor(course_id=2)

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

    def test_contributor_course_edit(self):
        """
            Tests whether the "save" button in the contributor's course edit view does not
            change the course's state, and that the "approve" button does that.
        """
        course = Course.objects.get(pk=TESTING_COURSE_ID)

        page = self.get_assert_200(self.url, user="responsible")
        form = page.forms["course-form"]
        form["vote_start_datetime"] = "02/1/2098 11:43:12"
        form["vote_end_date"] = "02/1/2099"

        form.submit(name="operation", value="save")
        course = Course.objects.get(pk=course.pk)
        self.assertEqual(course.state, "prepared")

        form.submit(name="operation", value="approve")
        course = Course.objects.get(pk=course.pk)
        self.assertEqual(course.state, "editor_approved")

        # test what happens if the operation is not specified correctly
        response = form.submit(expect_errors=True)
        self.assertEqual(response.status_code, 403)
