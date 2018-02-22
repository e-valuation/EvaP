from model_mommy import mommy

from evap.evaluation.models import Course, UserProfile
from evap.evaluation.tests.tools import ViewTest, create_course_with_responsible_and_editor

TESTING_COURSE_ID = 2


class TestContributorView(ViewTest):
    url = '/contributor/'
    test_users = ['editor', 'responsible']

    @classmethod
    def setUpTestData(cls):
        create_course_with_responsible_and_editor()


class TestContributorSettingsView(ViewTest):
    url = '/contributor/settings'
    test_users = ['editor', 'responsible']

    @classmethod
    def setUpTestData(cls):
        create_course_with_responsible_and_editor()

    def test_save_settings(self):
        user = mommy.make(UserProfile)
        page = self.get_assert_200(self.url, "responsible")
        form = page.forms["settings-form"]
        form["delegates"] = [user.pk]
        form.submit()

        self.assertEqual(list(UserProfile.objects.get(username='responsible').delegates.all()), [user])


class TestContributorCourseView(ViewTest):
    url = '/contributor/course/%s' % TESTING_COURSE_ID
    test_users = ['editor', 'responsible']

    @classmethod
    def setUpTestData(cls):
        create_course_with_responsible_and_editor(course_id=TESTING_COURSE_ID)
    
    def setUp(self):
        self.course = Course.objects.get(pk=TESTING_COURSE_ID)
    
    def test_wrong_state(self):
        self.course.revert_to_new()
        self.course.save()
        self.get_assert_403(self.url, 'responsible')
 
    def test_information_message(self):
        self.course.editor_approve()
        self.course.save()
        page = self.app.get(self.url, user='editor')
        self.assertContains(page, "You cannot edit this course because it has already been approved")


class TestContributorCoursePreviewView(ViewTest):
    url = '/contributor/course/%s/preview' % TESTING_COURSE_ID
    test_users = ['editor', 'responsible']

    @classmethod
    def setUpTestData(cls):
        cls.course = create_course_with_responsible_and_editor(course_id=TESTING_COURSE_ID)

    def setUp(self):
        self.course = Course.objects.get(pk=TESTING_COURSE_ID)

    def test_wrong_state(self):
        self.course.revert_to_new()
        self.course.save()
        self.get_assert_403(self.url, 'responsible')


class TestContributorCourseEditView(ViewTest):
    url = '/contributor/course/%s/edit' % TESTING_COURSE_ID
    test_users = ['editor', 'responsible']

    @classmethod
    def setUpTestData(cls):
        cls.course = create_course_with_responsible_and_editor(course_id=TESTING_COURSE_ID)

    def setUp(self):
        self.course = Course.objects.get(pk=TESTING_COURSE_ID)

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
        self.course.editor_approve()
        self.course.save()

        self.get_assert_403(self.url, 'responsible')

    def test_contributor_course_edit(self):
        """
            Tests whether the "save" button in the contributor's course edit view does not
            change the course's state, and that the "approve" button does that.
        """
        page = self.get_assert_200(self.url, user="responsible")
        form = page.forms["course-form"]
        form["vote_start_datetime"] = "2098-01-01 11:43:12"
        form["vote_end_date"] = "2099-01-01"

        form.submit(name="operation", value="save")
        self.course = Course.objects.get(pk=self.course.pk)
        self.assertEqual(self.course.state, "prepared")

        form.submit(name="operation", value="approve")
        self.course = Course.objects.get(pk=self.course.pk)
        self.assertEqual(self.course.state, "editor_approved")

        # test what happens if the operation is not specified correctly
        response = form.submit(expect_errors=True)
        self.assertEqual(response.status_code, 403)

    def test_contributor_course_edit_preview(self):
        """
            Asserts that the preview button either renders a preview or shows an error.
        """
        page = self.app.get(self.url, user="responsible")
        form = page.forms["course-form"]
        form["vote_start_datetime"] = "2099-01-01 11:43:12"
        form["vote_end_date"] = "2098-01-01"

        response = form.submit(name="operation", value="preview")
        self.assertNotIn("previewModal", response)
        self.assertIn("The preview could not be rendered", response)

        form["vote_start_datetime"] = "2098-01-01 11:43:12"
        form["vote_end_date"] = "2099-01-01"

        response = form.submit(name="operation", value="preview")
        self.assertIn("previewModal", response)
        self.assertNotIn("The preview could not be rendered", response)

    def test_contact_modal_escape(self):
        """
            Asserts that the course title is correctly escaped in the contact modal.
            Regression test for #1060
        """
        self.course.name_en = "Adam & Eve"
        self.course.save()
        page = self.get_assert_200(self.url, user="responsible")

        self.assertIn("changeParticipantRequestModalLabel", page)

        self.assertNotIn("Adam &amp;amp; Eve", page)
        self.assertIn("Adam &amp; Eve", page)
        self.assertNotIn("Adam & Eve", page)

