from django.core import mail

from model_mommy import mommy

from evap.evaluation.models import Course, UserProfile, Contribution
from evap.evaluation.tests.tools import WebTest, WebTestWith200Check, create_course_with_responsible_and_editor

TESTING_COURSE_ID = 2


class TestContributorDirectDelegationView(WebTest):
    csrf_checks = False

    @classmethod
    def setUpTestData(cls):
        cls.course = mommy.make(Course, state='prepared')

        cls.responsible = mommy.make(UserProfile)
        cls.non_responsible = mommy.make(UserProfile, email="a@b.c")
        mommy.make(Contribution, course=cls.course, contributor=cls.responsible, can_edit=True, responsible=True, comment_visibility=Contribution.ALL_COMMENTS)

    def test_direct_delegation_request(self):
        data = {"delegate_to": self.non_responsible.id}
        page = self.app.post('/contributor/course/{}/direct_delegation'.format(self.course.id), params=data, user=self.responsible).follow()

        self.assertContains(
            page,
            '{} was added as a contributor for course &quot;{}&quot; and was sent an email with further information.'.format(str(self.non_responsible), str(self.course))
        )

        contribution = Contribution.objects.get(contributor=self.non_responsible)
        self.assertTrue(contribution.can_edit)
        self.assertFalse(contribution.responsible)

        self.assertEqual(len(mail.outbox), 1)

    def test_direct_delegation_request_with_existing_contribution(self):
        contribution = mommy.make(Contribution, course=self.course, contributor=self.non_responsible, can_edit=False, responsible=False)
        old_contribution_count = Contribution.objects.count()

        data = {"delegate_to": self.non_responsible.id}
        page = self.app.post('/contributor/course/{}/direct_delegation'.format(self.course.id), params=data, user=self.responsible).follow()

        self.assertContains(
            page,
            '{} was added as a contributor for course &quot;{}&quot; and was sent an email with further information.'.format(str(self.non_responsible), str(self.course))
        )

        self.assertEqual(Contribution.objects.count(), old_contribution_count)

        contribution.refresh_from_db()
        self.assertTrue(contribution.can_edit)
        self.assertFalse(contribution.responsible)

        self.assertEqual(len(mail.outbox), 1)


class TestContributorView(WebTestWith200Check):
    url = '/contributor/'
    test_users = ['editor', 'responsible']

    @classmethod
    def setUpTestData(cls):
        create_course_with_responsible_and_editor()


class TestContributorSettingsView(WebTestWith200Check):
    url = '/contributor/settings'
    test_users = ['editor', 'responsible']

    @classmethod
    def setUpTestData(cls):
        create_course_with_responsible_and_editor()

    def test_save_settings(self):
        user = mommy.make(UserProfile)
        page = self.app.get(self.url, user="responsible", status=200)
        form = page.forms["settings-form"]
        form["delegates"] = [user.pk]
        form.submit()

        self.assertEqual(list(UserProfile.objects.get(username='responsible').delegates.all()), [user])


class TestContributorCourseView(WebTestWith200Check):
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
        self.app.get(self.url, user='responsible', status=403)

    def test_information_message(self):
        self.course.editor_approve()
        self.course.save()

        page = self.app.get(self.url, user='editor')
        self.assertContains(page, "You cannot edit this course because it has already been approved")
        self.assertNotContains(page, "Please review the course's details below, add all contributors and select suitable questionnaires. Once everything is okay, please approve the course on the bottom of the page.")


class TestContributorCoursePreviewView(WebTestWith200Check):
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
        self.app.get(self.url, user='responsible', status=403)


class TestContributorCourseEditView(WebTestWith200Check):
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
        self.app.get(self.url, user='student', status=403)

    def test_wrong_state(self):
        """
            Asserts that a contributor attempting to edit a course
            that is in a state where editing is not allowed gets a 403.
        """
        self.course.editor_approve()
        self.course.save()

        self.app.get(self.url, user='responsible', status=403)

    def test_contributor_course_edit(self):
        """
            Tests whether the "save" button in the contributor's course edit view does not
            change the course's state, and that the "approve" button does that.
        """
        page = self.app.get(self.url, user="responsible", status=200)
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
        page = self.app.get(self.url, user="responsible", status=200)

        self.assertIn("changeParticipantRequestModalLabel", page)

        self.assertNotIn("Adam &amp;amp; Eve", page)
        self.assertIn("Adam &amp; Eve", page)
        self.assertNotIn("Adam & Eve", page)

    def test_information_message(self):
        page = self.app.get(self.url, user='editor')
        self.assertNotContains(page, "You cannot edit this course because it has already been approved")
        self.assertContains(page, "Please review the course's details below, add all contributors and select suitable questionnaires. Once everything is okay, please approve the course on the bottom of the page.")
