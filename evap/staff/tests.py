from django.core.urlresolvers import reverse
from django_webtest import WebTest
from django.test import TestCase
from webtest import AppError
from django.test.utils import override_settings
from django.forms.models import inlineformset_factory
from django.core import mail
from django.core.cache import cache
from django.core.management import call_command
from django.conf import settings
from django.contrib.auth.models import Group
from django.utils.six import StringIO

from evap.evaluation.models import Semester, Questionnaire, Question, UserProfile, Course, \
                            Contribution, TextAnswer, EmailTemplate, NotArchiveable, Degree, CourseType
from evap.evaluation.tools import calculate_average_grades_and_deviation
from evap.staff.forms import CourseEmailForm, UserForm, ContributionFormSet, ContributionForm, \
                            CourseForm, SingleResultForm
from evap.contributor.forms import CourseForm as ContributorCourseForm
from evap.staff.tools import merge_users
from evap.rewards.models import RewardPointGranting, RewardPointRedemption, RewardPointRedemptionEvent

from model_mommy import mommy

import os.path


def lastform(page):
    return page.forms[max(key for key in page.forms.keys() if isinstance(key, int))]

def get_form_data_from_instance(FormClass, instance):
    assert FormClass._meta.model == type(instance)
    form = FormClass(instance=instance)
    return {field.html_name: field.value() for field in form}

# taken from http://lukeplant.me.uk/blog/posts/fuzzy-testing-with-assertnumqueries/
class FuzzyInt(int):
    def __new__(cls, lowest, highest):
        obj = super().__new__(cls, highest)
        obj.lowest = lowest
        obj.highest = highest
        return obj

    def __eq__(self, other):
        return other >= self.lowest and other <= self.highest

    def __repr__(self):
        return "[%d..%d]" % (self.lowest, self.highest)

@override_settings(INSTITUTION_EMAIL_DOMAINS=["institution.com", "student.institution.com"])
class SampleXlsTests(WebTest):

    @classmethod
    def setUpTestData(cls):
        mommy.make(Semester, pk=1)
        mommy.make(UserProfile, username="user", groups=[Group.objects.get(name="Staff")])
        mommy.make(CourseType, name_de="Vorlesung", name_en="Vorlesung")
        mommy.make(CourseType, name_de="Seminar", name_en="Seminar")

    def test_sample_xls(self):
        page = self.app.get("/staff/semester/1/import", user='user')

        original_user_count = UserProfile.objects.count()

        form = lastform(page)
        form["vote_start_date"] = "2015-01-01"
        form["vote_end_date"] = "2099-01-01"
        form["excel_file"] = (os.path.join(settings.BASE_DIR, "static", "sample.xls"),)
        form.submit(name="operation", value="import")

        self.assertEqual(UserProfile.objects.count(), original_user_count + 4)

    def test_sample_user_xls(self):
        page = self.app.get("/staff/user/import", user='user')

        original_user_count = UserProfile.objects.count()

        form = lastform(page)
        form["excel_file"] = (os.path.join(settings.BASE_DIR, "static", "sample_user.xls"),)
        form.submit(name="operation", value="import")

        self.assertEqual(UserProfile.objects.count(), original_user_count + 2)


class UsecaseTests(WebTest):

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username="staff.user", groups=[Group.objects.get(name="Staff")])
        mommy.make(CourseType, name_de="Vorlesung", name_en="Vorlesung")
        mommy.make(CourseType, name_de="Seminar", name_en="Seminar")

    def test_import(self):
        page = self.app.get(reverse("staff:index"), user='staff.user')

        # create a new semester
        page = page.click("[Cc]reate [Nn]ew [Ss]emester")
        semester_form = lastform(page)
        semester_form['name_de'] = "Testsemester"
        semester_form['name_en'] = "test semester"
        page = semester_form.submit().follow()

        # retrieve new semester
        semester = Semester.objects.get(name_de="Testsemester",
                                        name_en="test semester")

        self.assertEqual(semester.course_set.count(), 0, "New semester is not empty.")

        # save original user count
        original_user_count = UserProfile.objects.count()

        # import excel file
        page = page.click("[Ii]mport")
        upload_form = lastform(page)
        upload_form['vote_start_date'] = "02/29/2000"
        upload_form['vote_end_date'] = "02/29/2012"
        upload_form['excel_file'] = (os.path.join(os.path.dirname(__file__), "fixtures", "test_enrolment_data.xls"),)
        page = upload_form.submit(name="operation", value="import").follow()

        self.assertEqual(UserProfile.objects.count(), original_user_count + 23)

        courses = Course.objects.filter(semester=semester).all()
        self.assertEqual(len(courses), 23)

        for course in courses:
            responsibles_count = Contribution.objects.filter(course=course, responsible=True).count()
            self.assertEqual(responsibles_count, 1)

        check_student = UserProfile.objects.get(username="diam.synephebos")
        self.assertEqual(check_student.first_name, "Diam")
        self.assertEqual(check_student.email, "diam.synephebos@student.hpi.uni-potsdam.de")

        check_contributor = UserProfile.objects.get(username="sanctus.aliquyam.ext")
        self.assertEqual(check_contributor.first_name, "Sanctus")
        self.assertEqual(check_contributor.last_name, "Aliquyam")
        self.assertEqual(check_contributor.email, "567@web.de")

    def test_login_key(self):
        self.assertRedirects(self.app.get(reverse("results:index")), "/?next=/results/")

        user = mommy.make(UserProfile)
        user.generate_login_key()

        url_with_key = reverse("results:index") + "?userkey=%s" % user.login_key
        self.app.get(url_with_key)

    def test_create_questionnaire(self):
        page = self.app.get(reverse("staff:index"), user="staff.user")

        # create a new questionnaire
        page = page.click("[Cc]reate [Nn]ew [Qq]uestionnaire")
        questionnaire_form = lastform(page)
        questionnaire_form['name_de'] = "Test Fragebogen"
        questionnaire_form['name_en'] = "test questionnaire"
        questionnaire_form['public_name_de'] = "Oeffentlicher Test Fragebogen"
        questionnaire_form['public_name_en'] = "Public Test Questionnaire"
        questionnaire_form['question_set-0-text_de'] = "Frage 1"
        questionnaire_form['question_set-0-text_en'] = "Question 1"
        questionnaire_form['question_set-0-type'] = "T"
        questionnaire_form['index'] = 0
        page = questionnaire_form.submit().follow()

        # retrieve new questionnaire
        questionnaire = Questionnaire.objects.get(name_de="Test Fragebogen", name_en="test questionnaire")
        self.assertEqual(questionnaire.question_set.count(), 1, "New questionnaire is empty.")

    def test_create_empty_questionnaire(self):
        page = self.app.get(reverse("staff:index"), user="staff.user")

        # create a new questionnaire
        page = page.click("[Cc]reate [Nn]ew [Qq]uestionnaire")
        questionnaire_form = lastform(page)
        questionnaire_form['name_de'] = "Test Fragebogen"
        questionnaire_form['name_en'] = "test questionnaire"
        questionnaire_form['public_name_de'] = "Oeffentlicher Test Fragebogen"
        questionnaire_form['public_name_en'] = "Public Test Questionnaire"
        questionnaire_form['index'] = 0
        page = questionnaire_form.submit()

        self.assertIn("You must have at least one of these", page)

        # retrieve new questionnaire
        with self.assertRaises(Questionnaire.DoesNotExist):
            Questionnaire.objects.get(name_de="Test Fragebogen", name_en="test questionnaire")

    def test_copy_questionnaire(self):
        questionnaire = mommy.make(Questionnaire, name_en="Seminar")
        mommy.make(Question, questionnaire=questionnaire)
        page = self.app.get(reverse("staff:index"), user="staff.user")

        # create a new questionnaire
        page = page.click("All questionnaires")
        page = page.click("Copy", index=1)
        questionnaire_form = lastform(page)
        questionnaire_form['name_de'] = "Test Fragebogen (kopiert)"
        questionnaire_form['name_en'] = "test questionnaire (copied)"
        questionnaire_form['public_name_de'] = "Oeffentlicher Test Fragebogen (kopiert)"
        questionnaire_form['public_name_en'] = "Public Test Questionnaire (copied)"
        page = questionnaire_form.submit().follow()

        # retrieve new questionnaire
        questionnaire = Questionnaire.objects.get(name_de="Test Fragebogen (kopiert)", name_en="test questionnaire (copied)")
        self.assertEqual(questionnaire.question_set.count(), 1, "New questionnaire is empty.")

    def test_assign_questionnaires(self):
        semester = mommy.make(Semester, name_en="Semester 1")
        mommy.make(Course, semester=semester, type=CourseType.objects.get(name_de="Seminar"), contributions=[
            mommy.make(Contribution, contributor=mommy.make(UserProfile),
                responsible=True, can_edit=True, comment_visibility=Contribution.ALL_COMMENTS)])
        mommy.make(Course, semester=semester, type=CourseType.objects.get(name_de="Vorlesung"), contributions=[
            mommy.make(Contribution, contributor=mommy.make(UserProfile),
                responsible=True, can_edit=True, comment_visibility=Contribution.ALL_COMMENTS)])
        questionnaire = mommy.make(Questionnaire)
        page = self.app.get(reverse("staff:index"), user="staff.user")

        # assign questionnaire to courses
        page = page.click("Semester 1", index=0)
        page = page.click("Assign Questionnaires")
        assign_form = lastform(page)
        assign_form['Seminar'] = [questionnaire.pk]
        assign_form['Vorlesung'] = [questionnaire.pk]
        page = assign_form.submit().follow()

        for course in semester.course_set.all():
            self.assertEqual(course.general_contribution.questionnaires.count(), 1)
            self.assertEqual(course.general_contribution.questionnaires.get(), questionnaire)

    def test_remove_responsibility(self):
        user = mommy.make(UserProfile)
        contribution = mommy.make(Contribution, contributor=user, responsible=True, can_edit=True, comment_visibility=Contribution.ALL_COMMENTS)

        page = self.app.get(reverse("staff:index"), user="staff.user")
        page = page.click(contribution.course.semester.name_en, index=0)
        page = page.click(contribution.course.name_en)

        # remove responsibility
        form = lastform(page)
        form['contributions-0-responsibility'] = "CONTRIBUTOR"
        page = form.submit()

        self.assertIn("No responsible contributor found", page)


class PerformanceTests(WebTest):

    def test_num_queries_user_list(self):
        """
            ensures that the number of queries in the user list is constant
            and not linear to the number of users
        """
        num_users = 50
        mommy.make(UserProfile, username="staff.user", groups=[Group.objects.get(name="Staff")])
        mommy.make(UserProfile, _quantity=num_users)

        with self.assertNumQueries(FuzzyInt(0, num_users-1)):
            self.app.get("/staff/user/", user="staff.user")


class UnitTests(TestCase):

    def test_users_are_deletable(self):
        user = mommy.make(UserProfile)
        course = mommy.make(Course, participants=[user], state="new")
        self.assertTrue(user.can_staff_delete)

        user2 = mommy.make(UserProfile)
        course2 = mommy.make(Course, participants=[user2], state="inEvaluation")
        self.assertFalse(user2.can_staff_delete)

        contributor = mommy.make(UserProfile)
        mommy.make(Contribution, contributor=contributor)
        self.assertFalse(contributor.can_staff_delete)

    def test_deleting_last_modified_user_does_not_delete_course(self):
        user = mommy.make(UserProfile);
        course = mommy.make(Course, last_modified_user=user);
        user.delete()
        self.assertTrue(Course.objects.filter(pk=course.pk).exists())

    def test_has_enough_questionnaires(self):
        # manually circumvent Course's save() method to have a Course without a general contribution
        # the semester must be specified because of https://github.com/vandersonmota/model_mommy/issues/258
        courses = Course.objects.bulk_create([mommy.prepare(Course, semester=mommy.make(Semester), type=mommy.make(CourseType))])
        course = Course.objects.get()
        self.assertEqual(course.contributions.count(), 0)
        self.assertFalse(course.has_enough_questionnaires())

        responsible_contribution = mommy.make(Contribution, course=course, contributor=mommy.make(UserProfile), responsible=True, can_edit=True, comment_visibility=Contribution.ALL_COMMENTS)
        course = Course.objects.get()
        self.assertFalse(course.has_enough_questionnaires())

        general_contribution = mommy.make(Contribution, course=course, contributor=None)
        course = Course.objects.get() # refresh because of cached properties
        self.assertFalse(course.has_enough_questionnaires())

        q = mommy.make(Questionnaire)
        general_contribution.questionnaires.add(q)
        self.assertFalse(course.has_enough_questionnaires())

        responsible_contribution.questionnaires.add(q)
        self.assertTrue(course.has_enough_questionnaires())


@override_settings(INSTITUTION_EMAIL_DOMAINS=["example.com"])
class URLTests(WebTest):
    fixtures = ['minimal_test_data']
    csrf_checks = False

    def get_assert_200(self, url, user):
        response = self.app.get(url, user=user)
        self.assertEqual(response.status_code, 200, 'url "{}" failed with user "{}"'.format(url, user))
        return response

    def get_assert_302(self, url, user):
        response = self.app.get(url, user=user)
        self.assertEqual(response.status_code, 302, 'url "{}" failed with user "{}"'.format(url, user))
        return response

    def get_assert_403(self, url, user):
        try:
            self.app.get(url, user=user, status=403)
        except AppError as e:
            self.fail('url "{}" failed with user "{}"'.format(url, user))

    def get_submit_assert_302(self, url, user, name="", value=""):
        response = self.get_assert_200(url, user)
        response = response.forms[2].submit(name=name, value=value)
        self.assertEqual(response.status_code, 302, 'url "{}" failed with user "{}"'.format(url, user))
        return response

    def get_submit_assert_200(self, url, user):
        response = self.get_assert_200(url, user)
        response = response.forms[2].submit("")
        self.assertEqual(response.status_code, 200, 'url "{}" failed with user "{}"'.format(url, user))
        return response

    def test_all_urls(self):
        """
            This tests visits all URLs of evap and verifies they return a 200 for the specified user.
        """
        tests = [
            # student pages
            ("test_student", "/student/", "student"),
            ("test_student_vote_x", "/student/vote/5", "lazy.student"),
            # staff main page
            ("test_staff", "/staff/", "evap"),
            # staff semester
            ("test_staff_semester_create", "/staff/semester/create", "evap"),
            ("test_staff_semester_x", "/staff/semester/1", "evap"),
            ("test_staff_semester_x", "/staff/semester/1?tab=asdf", "evap"),
            ("test_staff_semester_x_edit", "/staff/semester/1/edit", "evap"),
            ("test_staff_semester_x_course_create", "/staff/semester/1/course/create", "evap"),
            ("test_staff_semester_x_import", "/staff/semester/1/import", "evap"),
            ("test_staff_semester_x_export", "/staff/semester/1/export", "evap"),
            ("test_staff_semester_x_assign", "/staff/semester/1/assign", "evap"),
            ("test_staff_semester_x_lottery", "/staff/semester/1/lottery", "evap"),
            ("test_staff_semester_x_todo", "/staff/semester/1/todo", "evap"),
            # staff semester course
            ("test_staff_semester_x_course_y_edit", "/staff/semester/1/course/5/edit", "evap"),
            ("test_staff_semester_x_course_y_email", "/staff/semester/1/course/1/email", "evap"),
            ("test_staff_semester_x_course_y_preview", "/staff/semester/1/course/1/preview", "evap"),
            ("test_staff_semester_x_course_y_comments", "/staff/semester/1/course/5/comments", "evap"),
            ("test_staff_semester_x_course_y_comment_z_edit", "/staff/semester/1/course/7/comment/12/edit", "evap"),
            ("test_staff_semester_x_courseoperation", "/staff/semester/1/courseoperation?course=1&operation=prepare", "evap"),
            # staff semester single_result
            ("test_staff_semester_x_single_result_create", "/staff/semester/1/singleresult/create", "evap"),
            ("test_staff_semester_x_single_result_y_edit", "/staff/semester/1/course/11/edit", "evap"),
            # staff questionnaires
            ("test_staff_questionnaire", "/staff/questionnaire/", "evap"),
            ("test_staff_questionnaire_create", "/staff/questionnaire/create", "evap"),
            ("test_staff_questionnaire_x_edit", "/staff/questionnaire/3/edit", "evap"),
            ("test_staff_questionnaire_x", "/staff/questionnaire/2", "evap"),
            ("test_staff_questionnaire_x_copy", "/staff/questionnaire/2/copy", "evap"),
            ("test_staff_questionnaire_delete", "/staff/questionnaire/create", "evap"),
            # staff user
            ("test_staff_user", "/staff/user/", "evap"),
            ("test_staff_user_import", "/staff/user/import", "evap"),
            ("test_staff_sample_xls", "/static/sample_user.xls", "evap"),
            ("test_staff_user_create", "/staff/user/create", "evap"),
            ("test_staff_user_x_edit", "/staff/user/4/edit", "evap"),
            ("test_staff_user_merge", "/staff/user/merge", "evap"),
            ("test_staff_user_x_merge_x", "/staff/user/4/merge/5", "evap"),
            # staff template
            ("test_staff_template_x", "/staff/template/1", "evap"),
            # faq
            ("test_staff_faq", "/staff/faq/", "evap"),
            ("test_staff_faq_x", "/staff/faq/1", "evap"),
            # rewards
            ("rewards_index", "/rewards/", "student"),
            ("reward_points_redemption_events", "/rewards/reward_point_redemption_events/", "evap"),
            ("reward_points_redemption_event_create", "/rewards/reward_point_redemption_event/create", "evap"),
            ("reward_points_redemption_event_edit", "/rewards/reward_point_redemption_event/1/edit", "evap"),
            ("reward_points_redemption_event_export", "/rewards/reward_point_redemption_event/1/export", "evap"),
            ("reward_points_semester_activation", "/rewards/reward_semester_activation/1/on", "evap"),
            ("reward_points_semester_deactivation", "/rewards/reward_semester_activation/1/off", "evap"),
            ("reward_points_semester_overview", "/rewards/semester/1/reward_points", "evap"),
            # degrees
            ("degree_index", "/staff/degrees/", "evap"),
            # course types
            ("course_type_index", "/staff/course_types/", "evap")]
        for _, url, user in tests:
            self.get_assert_200(url, user)

    def test_permission_denied(self):
        """
            Tests whether all the 403s Evap can throw are correctly thrown.
        """
        self.get_assert_403("/contributor/course/7", "editor_of_course_1")
        self.get_assert_403("/contributor/course/7/preview", "editor_of_course_1")
        self.get_assert_403("/contributor/course/2/edit", "editor_of_course_1")
        self.get_assert_403("/student/vote/5", "student")
        self.get_assert_403("/results/semester/1/course/8", "student"),
        self.get_assert_403("/results/semester/1/course/7", "student"),

    def test_redirecting_urls(self):
        """
            Tests whether some pages that cannot be accessed (e.g. for courses in certain states)
            do not return 200 but redirect somewhere else.
        """
        tests = [
            ("test_staff_semester_x_course_y_edit_fail", "/staff/semester/1/course/8/edit", "evap"),
        ]

        for _, url, user in tests:
            self.get_assert_302(url, user)

    def test_failing_forms(self):
        """
            Tests whether forms that fail because of missing required fields
            when submitting them without entering any data actually do that.
        """
        forms = [
            ("/staff/semester/create", "evap"),
            ("/staff/semester/1/course/create", "evap"),
            ("/staff/semester/1/import", "evap"),
            ("/staff/questionnaire/create", "evap"),
            ("/staff/user/create", "evap"),
            ("/staff/user/merge", "evap"),
        ]
        for form in forms:
            response = self.get_submit_assert_200(form[0], form[1])
            self.assertIn("is required", response)

        forms = [
            ("/student/vote/5", "lazy.student"),
            ("/staff/semester/1/course/1/email", "evap"),
        ]
        for form in forms:
            response = self.get_submit_assert_200(form[0], form[1])
            self.assertIn("alert-danger", response)

    def test_failing_questionnaire_copy(self):
        """
            Tests whether copying and submitting a questionnaire form wihtout entering a new name fails.
        """
        response = self.get_submit_assert_200("/staff/questionnaire/2/copy", "evap")
        self.assertIn("already exists", response)

    """
        The following tests test whether forms that succeed when
        submitting them without entering any data actually do that.
        They are in individual methods because most of them change the database.
    """

    def test_staff_semester_x_edit__nodata_success(self):
        self.get_submit_assert_302("/staff/semester/1/edit", "evap")

    def test_staff_semester_x_assign__nodata_success(self):
        self.get_submit_assert_302("/staff/semester/1/assign", "evap")

    def test_staff_semester_x_lottery__nodata_success(self):
        self.get_submit_assert_200("/staff/semester/1/lottery", "evap")

    def test_staff_semester_x_course_y_edit__nodata_success(self):
        self.get_submit_assert_302("/staff/semester/1/course/1/edit", "evap", name="operation", value="save")

    def test_staff_questionnaire_x_edit__nodata_success(self):
        self.get_submit_assert_302("/staff/questionnaire/3/edit", "evap")

    def test_staff_user_x_edit__nodata_success(self):
        self.get_submit_assert_302("/staff/user/4/edit", "evap")

    def test_staff_template_x__nodata_success(self):
        self.get_submit_assert_200("/staff/template/1", "evap")

    def test_staff_faq__nodata_success(self):
        self.get_submit_assert_302("/staff/faq/", "evap")

    def test_staff_faq_x__nodata_success(self):
        self.get_submit_assert_302("/staff/faq/1", "evap")

    def test_contributor_settings(self):
        self.get_submit_assert_302("/contributor/settings", "responsible")

    def test_course_email_form(self):
        """
            Tests the CourseEmailForm with one valid and one invalid input dataset.
        """
        course = Course.objects.get(pk="1")
        data = {"body": "wat", "subject": "some subject", "recipients": ["due_participants"]}
        form = CourseEmailForm(instance=course, data=data)
        self.assertTrue(form.is_valid())
        self.assertTrue(form.missing_email_addresses() == 0)
        form.send()

        data = {"body": "wat", "subject": "some subject"}
        form = CourseEmailForm(instance=course, data=data)
        self.assertFalse(form.is_valid())

    def test_user_form(self):
        """
            Tests the UserForm with one valid and one invalid input dataset.
        """
        user = UserProfile.objects.get(pk=1)
        another_user = UserProfile.objects.get(pk=2)
        data = {"username": "mklqoep50x2", "email": "a@b.ce"}
        form = UserForm(instance=user, data=data)
        self.assertTrue(form.is_valid())

        data = {"username": another_user.username, "email": "a@b.c"}
        form = UserForm(instance=user, data=data)
        self.assertFalse(form.is_valid())

    def test_contributor_form_set(self):
        """
            Tests the ContributionFormset with various input data sets.
        """
        course = mommy.make(Course)

        ContributionFormset = inlineformset_factory(Course, Contribution, formset=ContributionFormSet, form=ContributionForm, extra=0)

        data = {
            'contributions-TOTAL_FORMS': 1,
            'contributions-INITIAL_FORMS': 0,
            'contributions-MAX_NUM_FORMS': 5,
            'contributions-0-course': course.pk,
            'contributions-0-questionnaires': [1],
            'contributions-0-order': 0,
            'contributions-0-responsibility': "RESPONSIBLE",
            'contributions-0-comment_visibility': "ALL",
        }
        # no contributor and no responsible
        self.assertFalse(ContributionFormset(instance=course, form_kwargs={'course': course}, data=data.copy()).is_valid())
        # valid
        data['contributions-0-contributor'] = 1
        self.assertTrue(ContributionFormset(instance=course, form_kwargs={'course': course}, data=data.copy()).is_valid())
        # duplicate contributor
        data['contributions-TOTAL_FORMS'] = 2
        data['contributions-1-contributor'] = 1
        data['contributions-1-course'] = course.pk
        data['contributions-1-questionnaires'] = [1]
        data['contributions-1-order'] = 1
        self.assertFalse(ContributionFormset(instance=course, form_kwargs={'course': course}, data=data).is_valid())
        # two responsibles
        data['contributions-1-contributor'] = 2
        data['contributions-1-responsibility'] = "RESPONSIBLE"
        self.assertFalse(ContributionFormset(instance=course, form_kwargs={'course': course}, data=data).is_valid())

    def test_semester_deletion(self):
        """
            Tries to delete two semesters via the respective post request,
            only the second attempt should succeed.
        """
        self.assertFalse(Semester.objects.get(pk=1).can_staff_delete)
        response = self.app.post("/staff/semester/delete", {"semester_id": 1,}, user="evap", expect_errors=True)
        self.assertEqual(response.status_code, 400)
        self.assertTrue(Semester.objects.filter(pk=1).exists())

        self.assertTrue(Semester.objects.get(pk=2).can_staff_delete)
        response = self.app.post("/staff/semester/delete", {"semester_id": 2,}, user="evap")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Semester.objects.filter(pk=2).exists())

    def helper_semester_state_views(self, course_ids, old_state, new_state, operation):
        page = self.app.get("/staff/semester/1", user="evap")
        form = page.forms["form_" + old_state]
        for course_id in course_ids:
            self.assertIn(Course.objects.get(pk=course_id).state, old_state)
        form['course'] = course_ids
        response = form.submit('operation', value=operation)

        form = lastform(response)
        response = form.submit()
        self.assertIn("Successfully", str(response))
        for course_id in course_ids:
            self.assertEqual(Course.objects.get(pk=course_id).state, new_state)

    """
        The following tests make sure the course state transitions are triggerable via the UI.
    """
    def test_semester_publish(self):
        self.helper_semester_state_views([7], "reviewed", "published", "publish")

    def test_semester_reset(self):
        self.helper_semester_state_views([2], "prepared", "new", "revertToNew")

    def test_semester_approve_1(self):
        self.helper_semester_state_views([1], "new", "approved", "approve")

    def test_semester_approve_2(self):
        self.helper_semester_state_views([2], "prepared", "approved", "approve")

    def test_semester_approve_3(self):
        self.helper_semester_state_views([3], "editorApproved", "approved", "approve")

    def test_semester_contributor_ready_1(self):
        self.helper_semester_state_views([1, 10], "new", "prepared", "prepare")

    def test_semester_contributor_ready_2(self):
        self.helper_semester_state_views([3], "editorApproved", "prepared", "reenableEditorReview")

    def test_semester_unpublish(self):
        self.helper_semester_state_views([8], "published", "reviewed", "unpublish")

    def test_course_create(self):
        """
            Tests the course creation view with one valid and one invalid input dataset.
        """
        data = dict(name_de="asdf", name_en="asdf", type=1, degrees=["1"],
                    vote_start_date="02/1/2014", vote_end_date="02/1/2099", general_questions=["2"])
        response = self.get_assert_200("/staff/semester/1/course/create", "evap")
        form = lastform(response)
        form["name_de"] = "lfo9e7bmxp1xi"
        form["name_en"] = "asdf"
        form["type"] = 1
        form["degrees"] = ["1"]
        form["vote_start_date"] = "02/1/2099"
        form["vote_end_date"] = "02/1/2014" # wrong order to get the validation error
        form["general_questions"] = ["2"]

        form['contributions-TOTAL_FORMS'] = 1
        form['contributions-INITIAL_FORMS'] = 0
        form['contributions-MAX_NUM_FORMS'] = 5
        form['contributions-0-course'] = ''
        form['contributions-0-contributor'] = 6
        form['contributions-0-questionnaires'] = [1]
        form['contributions-0-order'] = 0
        form['contributions-0-responsibility'] = "RESPONSIBLE"
        form['contributions-0-comment_visibility'] = "ALL"

        form.submit()
        self.assertNotEqual(Course.objects.order_by("pk").last().name_de, "lfo9e7bmxp1xi")

        form["vote_start_date"] = "02/1/2014"
        form["vote_end_date"] = "02/1/2099" # now do it right

        form.submit()
        self.assertEqual(Course.objects.order_by("pk").last().name_de, "lfo9e7bmxp1xi")

    def test_single_result_create(self):
        """
            Tests the single result creation view with one valid and one invalid input dataset.
        """
        response = self.get_assert_200("/staff/semester/1/singleresult/create", "evap")
        form = lastform(response)
        form["name_de"] = "qwertz"
        form["name_en"] = "qwertz"
        form["type"] = 1
        form["degrees"] = ["1"]
        form["event_date"] = "02/1/2014"
        form["answer_1"] = 6
        form["answer_3"] = 2
        # missing responsible to get a validation error

        form.submit()
        self.assertNotEqual(Course.objects.order_by("pk").last().name_de, "qwertz")

        form["responsible"] = 2 # now do it right

        form.submit()
        self.assertEqual(Course.objects.order_by("pk").last().name_de, "qwertz")

    def test_course_email(self):
        """
            Tests whether the course email view actually sends emails.
        """
        page = self.get_assert_200("/staff/semester/1/course/5/email", user="evap")
        form = lastform(page)
        form.get("recipients", index=0).checked = True # send to all participants
        form["subject"] = "asdf"
        form["body"] = "asdf"
        form.submit()

        self.assertEqual(len(mail.outbox), 2)

    def test_questionnaire_deletion(self):
        """
            Tries to delete two questionnaires via the respective post request,
            only the second attempt should succeed.
        """
        self.assertFalse(Questionnaire.objects.get(pk=2).can_staff_delete)
        response = self.app.post("/staff/questionnaire/delete", {"questionnaire_id": 2,}, user="evap", expect_errors=True)
        self.assertEqual(response.status_code, 400)
        self.assertTrue(Questionnaire.objects.filter(pk=2).exists())

        self.assertTrue(Questionnaire.objects.get(pk=3).can_staff_delete)
        response = self.app.post("/staff/questionnaire/delete", {"questionnaire_id": 3,}, user="evap")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Questionnaire.objects.filter(pk=3).exists())

    def test_create_user(self):
        """
            Tests whether the user creation view actually creates a user.
        """
        page = self.get_assert_200("/staff/user/create", "evap")
        form = lastform(page)
        form["username"] = "mflkd862xmnbo5"
        form["first_name"] = "asd"
        form["last_name"] = "asd"
        form["email"] = "a@b.de"

        form.submit()

        self.assertEqual(UserProfile.objects.order_by("pk").last().username, "mflkd862xmnbo5")

    def test_emailtemplate(self):
        """
            Tests the emailtemplate view with one valid and one invalid input datasets.
        """
        page = self.get_assert_200("/staff/template/1", "evap")
        form = lastform(page)
        form["subject"] = "subject: mflkd862xmnbo5"
        form["body"] = "body: mflkd862xmnbo5"
        response = form.submit()

        self.assertEqual(EmailTemplate.objects.get(pk=1).body, "body: mflkd862xmnbo5")

        form["body"] = " invalid tag: {{}}"
        response = form.submit()
        self.assertEqual(EmailTemplate.objects.get(pk=1).body, "body: mflkd862xmnbo5")

    def test_contributor_course_edit(self):
        """
            Tests whether the "save" button in the contributor's course edit view does not
            change the course's state, and that the "approve" button does that.
        """
        page = self.get_assert_200("/contributor/course/2/edit", user="responsible")
        form = lastform(page)
        form["vote_start_date"] = "02/1/2098"
        form["vote_end_date"] = "02/1/2099"

        form.submit(name="operation", value="save")
        self.assertEqual(Course.objects.get(pk=2).state, "prepared")

        form.submit(name="operation", value="approve")
        self.assertEqual(Course.objects.get(pk=2).state, "editorApproved")

        # test what happens if the operation is not specified correctly
        response = form.submit(expect_errors=True)
        self.assertEqual(response.status_code, 403)

    def test_student_vote(self):
        """
            Submits a student vote for coverage, verifies that an error message is
            displayed if not all rating questions have been answered and that all
            given answers stay selected/filled and that the student cannot vote on
            the course a second time.
        """
        page = self.get_assert_200("/student/vote/5", user="lazy.student")
        form = lastform(page)
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
        form = lastform(page)
        self.assertEqual(form["question_17_2_3"].value, "some text")
        self.assertEqual(form["question_17_2_4"].value, "1")
        self.assertEqual(form["question_17_2_5"].value, "6")
        self.assertEqual(form["question_18_1_1"].value, "some other text")
        self.assertEqual(form["question_18_1_2"].value, "1")
        self.assertEqual(form["question_19_1_1"].value, "some more text")
        self.assertEqual(form["question_19_1_2"].value, "1")
        self.assertEqual(form["question_20_1_1"].value, "and the last text")
        form["question_20_1_2"] = 1 # give missing answer
        response = form.submit()

        self.get_assert_403("/student/vote/5", user="lazy.student")

    def test_course_type_form(self):
        """
            Adds a course type via the staff form and verifies that the type was created in the db.
        """
        page = self.get_assert_200("/staff/course_types/", user="evap")
        form = lastform(page)
        last_form_id = int(form["form-TOTAL_FORMS"].value) - 1
        form["form-" + str(last_form_id) + "-name_de"].value = "Test"
        form["form-" + str(last_form_id) + "-name_en"].value = "Test"
        response = form.submit()
        self.assertIn("Successfully", str(response))

        self.assertTrue(CourseType.objects.filter(name_de="Test", name_en="Test").exists())

    def test_degree_form(self):
        """
            Adds a degree via the staff form and verifies that the degree was created in the db.
        """
        page = self.get_assert_200("/staff/degrees/", user="evap")
        form = lastform(page)
        last_form_id = int(form["form-TOTAL_FORMS"].value) - 1
        form["form-" + str(last_form_id) + "-name_de"].value = "Test"
        form["form-" + str(last_form_id) + "-name_en"].value = "Test"
        response = form.submit()
        self.assertIn("Successfully", str(response))

        self.assertTrue(Degree.objects.filter(name_de="Test", name_en="Test").exists())


class CourseFormTests(TestCase):

    def helper_test_course_form_same_name(self, CourseFormClass):
        courses = Course.objects.all()

        form_data = get_form_data_from_instance(CourseForm, courses[0])
        form_data["vote_start_date"] = "02/1/2098" # needed to fix the form
        form_data["vote_end_date"] = "02/1/2099" # needed to fix the form

        form = CourseForm(form_data, instance=courses[0])
        self.assertTrue(form.is_valid())
        form_data['name_de'] = courses[1].name_de
        form = CourseForm(form_data, instance=courses[0])
        self.assertFalse(form.is_valid())

    def test_course_form_same_name(self):
        """
            Test whether giving a course the same name as another course
            in the same semester in the course edit form is invalid.
        """
        courses = mommy.make(Course, semester=mommy.make(Semester), degrees=[mommy.make(Degree)], _quantity=2)
        courses[0].general_contribution.questionnaires = [mommy.make(Questionnaire)]
        courses[1].general_contribution.questionnaires = [mommy.make(Questionnaire)]

        self.helper_test_course_form_same_name(CourseForm)
        self.helper_test_course_form_same_name(ContributorCourseForm)

    def helper_date_validation(self, CourseFormClass, start_date, end_date, expected_result):
        course = Course.objects.get()

        form_data = get_form_data_from_instance(CourseFormClass, course)
        form_data["vote_start_date"] = start_date
        form_data["vote_end_date"] = end_date

        form = CourseFormClass(form_data, instance=course)
        self.assertEqual(form.is_valid(), expected_result)

    def test_contributor_course_form_date_validation(self):
        """
            Tests validity of various start/end date combinations in
            the two course edit forms.
        """
        course = mommy.make(Course, degrees=[mommy.make(Degree)])
        course.general_contribution.questionnaires = [mommy.make(Questionnaire)]

        # contributors: start date must be in the future
        self.helper_date_validation(ContributorCourseForm, "02/1/1999", "02/1/2099", False)

        # contributors: end date must be in the future
        self.helper_date_validation(ContributorCourseForm, "02/1/2099", "02/1/1999", False)

        # contributors: start date must be < end date
        self.helper_date_validation(ContributorCourseForm, "02/1/2099", "02/1/2098", False)

        # contributors: valid data
        self.helper_date_validation(ContributorCourseForm, "02/1/2098", "02/1/2099", True)

        # staff: neither end nor start date must be in the future
        self.helper_date_validation(CourseForm, "02/1/1998", "02/1/1999", True)

        # staff: valid data in the future
        self.helper_date_validation(CourseForm, "02/1/2098", "02/1/2099", True)

        # staff: but start date must be < end date
        self.helper_date_validation(CourseForm, "02/1/1999", "02/1/1998", False)


class SingleResultFormTests(TestCase):

    def test_single_result_form_saves_participant_and_voter_count(self):
        responsible = mommy.make(UserProfile)
        course_type = mommy.make(CourseType)
        form_data = {
            "name_de": "qwertz",
            "name_en": "qwertz",
            "type": course_type.pk,
            "degrees": ["1"],
            "event_date": "02/1/2014",
            "responsible": responsible.pk,
            "answer_1": 6,
            "answer_2": 0,
            "answer_3": 2,
            "answer_4": 0,
            "answer_5": 2,
        }
        course = Course(semester=mommy.make(Semester))
        form = SingleResultForm(form_data, instance=course)
        self.assertTrue(form.is_valid())

        form.save(user=mommy.make(UserProfile))

        course = Course.objects.first()
        self.assertEqual(course.num_participants, 10)
        self.assertEqual(course.num_voters, 10)

class ContributionFormsetTests(TestCase):

    def test_dont_validate_deleted_contributions(self):
        """
            Tests whether contributions marked for deletion are validated.
            Regression test for #415 and #244
        """
        course = mommy.make(Course)
        user1 = mommy.make(UserProfile)
        user2 = mommy.make(UserProfile)
        user3 = mommy.make(UserProfile)
        questionnaire = mommy.make(Questionnaire, is_for_contributors=True)

        ContributionFormset = inlineformset_factory(Course, Contribution, formset=ContributionFormSet, form=ContributionForm, extra=0)

        # here we have two responsibles (one of them deleted), and a deleted contributor with no questionnaires.
        data = {
            'contributions-TOTAL_FORMS': 3,
            'contributions-INITIAL_FORMS': 0,
            'contributions-MAX_NUM_FORMS': 5,
            'contributions-0-course': course.pk,
            'contributions-0-questionnaires': [questionnaire.pk],
            'contributions-0-order': 0,
            'contributions-0-responsibility': "RESPONSIBLE",
            'contributions-0-comment_visibility': "ALL",
            'contributions-0-contributor': user1.pk,
            'contributions-0-DELETE': 'on',
            'contributions-1-course': course.pk,
            'contributions-1-questionnaires': [questionnaire.pk],
            'contributions-1-order': 0,
            'contributions-1-responsibility': "RESPONSIBLE",
            'contributions-1-comment_visibility': "ALL",
            'contributions-1-contributor': user2.pk,
            'contributions-2-course': course.pk,
            'contributions-2-questionnaires': [],
            'contributions-2-order': 1,
            'contributions-2-responsibility': "NONE",
            'contributions-2-comment_visibility': "OWN",
            'contributions-2-contributor': user2.pk,
            'contributions-2-DELETE': 'on',
        }

        formset = ContributionFormset(instance=course, form_kwargs={'course': course}, data=data)
        self.assertTrue(formset.is_valid())

    def test_take_deleted_contributions_into_account(self):
        """
            Tests whether contributions marked for deletion are properly taken into account
            when the same contributor got added again in the same formset.
            Regression test for #415
        """
        course = mommy.make(Course)
        user1 = mommy.make(UserProfile)
        questionnaire = mommy.make(Questionnaire, is_for_contributors=True)
        contribution1 = mommy.make(Contribution, course=course, contributor=user1, responsible=True, can_edit=True, comment_visibility=Contribution.ALL_COMMENTS, questionnaires=[questionnaire])

        ContributionFormset = inlineformset_factory(Course, Contribution, formset=ContributionFormSet, form=ContributionForm, extra=0)

        data = {
            'contributions-TOTAL_FORMS': 2,
            'contributions-INITIAL_FORMS': 1,
            'contributions-MAX_NUM_FORMS': 5,
            'contributions-0-id': contribution1.pk,
            'contributions-0-course': course.pk,
            'contributions-0-questionnaires': [questionnaire.pk],
            'contributions-0-order': 0,
            'contributions-0-responsibility': "RESPONSIBLE",
            'contributions-0-comment_visibility': "ALL",
            'contributions-0-contributor': user1.pk,
            'contributions-0-DELETE': 'on',
            'contributions-1-course': course.pk,
            'contributions-1-questionnaires': [questionnaire.pk],
            'contributions-1-order': 0,
            'contributions-1-responsibility': "RESPONSIBLE",
            'contributions-1-comment_visibility': "ALL",
            'contributions-1-contributor': user1.pk,
        }

        formset = ContributionFormset(instance=course, form_kwargs={'course': course}, data=data)
        self.assertTrue(formset.is_valid())

    def test_obsolete_staff_only(self):
        """
            Asserts that obsolete questionnaires are shown to staff members only if
            they are already selected for a contribution of the Course, and
            that staff_only questionnaires are always shown.
            Regression test for #593.
        """
        course = mommy.make(Course)
        questionnaire = mommy.make(Questionnaire, is_for_contributors=True, obsolete=False, staff_only=False)
        questionnaire_obsolete = mommy.make(Questionnaire, is_for_contributors=True, obsolete=True, staff_only=False)
        questionnaire_staff_only = mommy.make(Questionnaire, is_for_contributors=True, obsolete=False, staff_only=True)

        # the normal and staff_only questionnaire should be shown.
        contribution1 = mommy.make(Contribution, course=course, contributor=mommy.make(UserProfile), questionnaires=[])

        InlineContributionFormset = inlineformset_factory(Course, Contribution, formset=ContributionFormSet, form=ContributionForm, extra=1)
        formset = InlineContributionFormset(instance=course, form_kwargs={'course': course})

        expected = set([questionnaire, questionnaire_staff_only])
        self.assertEqual(expected, set(formset.forms[0].fields['questionnaires'].queryset.all()))
        self.assertEqual(expected, set(formset.forms[1].fields['questionnaires'].queryset.all()))

        # suppose we had an obsolete questionnaire already selected, that should be shown as well
        contribution1.questionnaires = [questionnaire_obsolete]

        InlineContributionFormset = inlineformset_factory(Course, Contribution, formset=ContributionFormSet, form=ContributionForm, extra=1)
        formset = InlineContributionFormset(instance=course, form_kwargs={'course': course})

        expected = set([questionnaire, questionnaire_staff_only, questionnaire_obsolete])
        self.assertEqual(expected, set(formset.forms[0].fields['questionnaires'].queryset.all()))
        self.assertEqual(expected, set(formset.forms[1].fields['questionnaires'].queryset.all()))


class ArchivingTests(WebTest):

    @classmethod
    def setUpTestData(cls):
        cls.semester = mommy.make(Semester)
        cls.course = mommy.make(Course, pk=7, state="published", semester=cls.semester)

        users = mommy.make(UserProfile, _quantity=3)
        cls.course.participants = users
        cls.course.voters = users[:2]

    def refresh_course(self):
        """ refresh_from_db does not work with courses"""
        self.course = self.semester.course_set.first()

    def setUp(self):
        self.semester.refresh_from_db()
        self.refresh_course()

    def test_counts_dont_change(self):
        """
            Asserts that course.num_voters course.num_participants don't change after archiving.
        """
        voter_count = self.course.num_voters
        participant_count = self.course.num_participants

        self.semester.archive()
        self.refresh_course()

        self.assertEqual(voter_count, self.course.num_voters)
        self.assertEqual(participant_count, self.course.num_participants)

    def test_participants_do_not_loose_courses(self):
        """
            Asserts that participants still participate in their courses after they get archived.
        """
        some_participant = self.course.participants.first()

        self.semester.archive()

        self.assertEqual(list(some_participant.courses_participating_in.all()), [self.course])

    def test_is_archived(self):
        """
            Tests whether is_archived returns True on archived semesters and courses.
        """
        self.assertFalse(self.course.is_archived)

        self.semester.archive()
        self.refresh_course()

        self.assertTrue(self.course.is_archived)

    def test_archiving_does_not_change_results(self):
        results = calculate_average_grades_and_deviation(self.course)

        self.semester.archive()
        self.refresh_course()
        cache.clear()

        self.assertEqual(calculate_average_grades_and_deviation(self.course), results)

    def test_archiving_twice_raises_exception(self):
        self.semester.archive()
        with self.assertRaises(NotArchiveable):
            self.semester.archive()
        with self.assertRaises(NotArchiveable):
            self.semester.course_set.first()._archive()

    def get_assert_403(self, url, user):
        try:
            self.app.get(url, user=user, status=403)
        except AppError as e:
            self.fail('url "{}" failed with user "{}"'.format(url, user))

    def test_raise_403(self):
        """
            Tests whether inaccessible views on archived semesters/courses correctly raise a 403.
        """
        self.semester.archive()

        semester_url = "/staff/semester/{}/".format(self.semester.pk)

        self.get_assert_403(semester_url + "import", "evap")
        self.get_assert_403(semester_url + "assign", "evap")
        self.get_assert_403(semester_url + "course/create", "evap")
        self.get_assert_403(semester_url + "course/7/edit", "evap")
        self.get_assert_403(semester_url + "courseoperation", "evap")

    def test_course_is_not_archived_if_participant_count_is_set(self):
        course = mommy.make(Course, state="published", _participant_count=1, _voter_count=1)
        self.assertFalse(course.is_archived)
        self.assertTrue(course.is_archiveable)

    def test_archiving_doesnt_change_single_results_participant_count(self):
        responsible = mommy.make(UserProfile)
        course = mommy.make(Course, state="published")
        contribution = mommy.make(Contribution, course=course, contributor=responsible, responsible=True)
        contribution.questionnaires.add(Questionnaire.get_single_result_questionnaire())
        self.assertTrue(course.is_single_result())

        course._participant_count = 5
        course._voter_count = 5
        course.save()

        course._archive()
        self.assertEqual(course._participant_count, 5)
        self.assertEqual(course._voter_count, 5)


class TestDataTest(TestCase):

    def load_test_data(self):
        """
            Asserts that the test data still load cleanly.
            This test does not have the "test_" prefix, as it is meant
            to be started manually e.g. by Travis.
        """
        try:
            call_command("loaddata", "test_data", verbosity=0)
        except Exception:
            self.fail("Test data failed to load.")


class MergeUsersTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user1 = mommy.make(UserProfile, username="test1")
        cls.user2 = mommy.make(UserProfile, username="test2")
        cls.user3 = mommy.make(UserProfile, username="test3")
        cls.group1 = mommy.make(Group, name="group1")
        cls.group2 = mommy.make(Group, name="group2")
        cls.main_user = mommy.make(UserProfile,
            username="main_user",
            title="Dr.",
            first_name="Main",
            last_name="",
            email="",  # test that merging works when taking the email from other user (UniqueConstraint)
            groups=[cls.group1],
            delegates=[cls.user1, cls.user2],
            represented_users=[cls.user3],
            cc_users=[cls.user1],
            ccing_users=[]
        )
        cls.other_user = mommy.make(UserProfile,
            username="other_user",
            title="",
            first_name="Other",
            last_name="User",
            email="other@test.com",
            groups=[cls.group2],
            delegates=[cls.user3],
            represented_users=[cls.user1],
            cc_users=[],
            ccing_users=[cls.user1, cls.user2],
            is_superuser=True
        )
        cls.course1 = mommy.make(Course, name="course1", participants=[cls.main_user, cls.other_user])  # this should make the merge fail
        cls.course2 = mommy.make(Course, name="course2", participants=[cls.main_user], voters=[cls.main_user])
        cls.course3 = mommy.make(Course, name="course3", participants=[cls.other_user], voters=[cls.other_user])
        cls.contribution1 = mommy.make(Contribution, contributor=cls.main_user, course=cls.course1)
        cls.contribution2 = mommy.make(Contribution, contributor=cls.other_user, course=cls.course1)  # this should make the merge fail
        cls.contribution3 = mommy.make(Contribution, contributor=cls.other_user, course=cls.course2)
        cls.rewardpointgranting_main = mommy.make(RewardPointGranting, user_profile=cls.main_user)
        cls.rewardpointgranting_other = mommy.make(RewardPointGranting, user_profile=cls.other_user)
        cls.rewardpointredemption_main = mommy.make(RewardPointRedemption, user_profile=cls.main_user)
        cls.rewardpointredemption_other = mommy.make(RewardPointRedemption, user_profile=cls.other_user)

    def test_merge_handles_all_attributes(self):
        user1 = mommy.make(UserProfile)
        user2 = mommy.make(UserProfile)

        all_attrs = list(field.name for field in UserProfile._meta.get_fields(include_hidden=True))

        # these are relations to intermediate models generated by django for m2m relations.
        # we can safely ignore these since the "normal" fields of the m2m relations are present as well.
        all_attrs = list(attr for attr in all_attrs if not attr.startswith("UserProfile_"))

        # equally named fields are not supported, sorry
        self.assertEqual(len(all_attrs), len(set(all_attrs)))

        # some attributes we don't care about when merging
        ignored_attrs = set([
            'id', # nothing to merge here
            'password', # not used in production
            'last_login', # something to really not care about
            'user_permissions', # we don't use permissions
            'logentry', # wtf
            'login_key', # we decided to discard other_user's login key
            'login_key_valid_until', # not worth dealing with
            'Course_voters+', # some more intermediate models, for an explanation see above
            'Course_participants+', # intermediate model
        ])
        expected_attrs = set(all_attrs) - ignored_attrs

        # actual merge happens here
        merged_user, errors, warnings = merge_users(user1, user2)
        handled_attrs = set(merged_user.keys())

        # attributes that are handled in the merge method but that are not present in the merged_user dict
        # add attributes here only if you're actually dealing with them in merge_users().
        additional_handled_attrs = set([
            'grades_last_modified_user+',
            'course_last_modified_user+',
        ])

        actual_attrs = handled_attrs | additional_handled_attrs

        self.assertEqual(expected_attrs, actual_attrs)

    def test_merge_users(self):
        merged_user, errors, warnings = merge_users(self.main_user, self.other_user)  # merge should fail
        self.assertSequenceEqual(errors, ['contributions', 'courses_participating_in'])
        self.assertSequenceEqual(warnings, ['rewards'])

        # assert that nothing has changed
        self.main_user.refresh_from_db()
        self.other_user.refresh_from_db()
        self.assertEqual(self.main_user.username, "main_user")
        self.assertEqual(self.main_user.title, "Dr.")
        self.assertEqual(self.main_user.first_name, "Main")
        self.assertEqual(self.main_user.last_name, "")
        self.assertEqual(self.main_user.email, "")
        self.assertSequenceEqual(self.main_user.groups.all(), [self.group1])
        self.assertSequenceEqual(self.main_user.delegates.all(), [self.user1, self.user2])
        self.assertSequenceEqual(self.main_user.represented_users.all(), [self.user3])
        self.assertSequenceEqual(self.main_user.cc_users.all(), [self.user1])
        self.assertSequenceEqual(self.main_user.ccing_users.all(), [])
        self.assertFalse(self.main_user.is_superuser)
        self.assertTrue(RewardPointGranting.objects.filter(user_profile=self.main_user).exists())
        self.assertTrue(RewardPointRedemption.objects.filter(user_profile=self.main_user).exists())
        self.assertEqual(self.other_user.username, "other_user")
        self.assertEqual(self.other_user.title, "")
        self.assertEqual(self.other_user.first_name, "Other")
        self.assertEqual(self.other_user.last_name, "User")
        self.assertEqual(self.other_user.email, "other@test.com")
        self.assertSequenceEqual(self.other_user.groups.all(), [self.group2])
        self.assertSequenceEqual(self.other_user.delegates.all(), [self.user3])
        self.assertSequenceEqual(self.other_user.represented_users.all(), [self.user1])
        self.assertSequenceEqual(self.other_user.cc_users.all(), [])
        self.assertSequenceEqual(self.other_user.ccing_users.all(), [self.user1, self.user2])
        self.assertSequenceEqual(self.course1.participants.all(), [self.main_user, self.other_user])
        self.assertSequenceEqual(self.course2.participants.all(), [self.main_user])
        self.assertSequenceEqual(self.course2.voters.all(), [self.main_user])
        self.assertSequenceEqual(self.course3.participants.all(), [self.other_user])
        self.assertSequenceEqual(self.course3.voters.all(), [self.other_user])
        self.assertTrue(RewardPointGranting.objects.filter(user_profile=self.other_user).exists())
        self.assertTrue(RewardPointRedemption.objects.filter(user_profile=self.other_user).exists())

        # fix data
        self.course1.participants = [self.main_user]
        self.contribution2.delete()

        merged_user, errors, warnings = merge_users(self.main_user, self.other_user)  # merge should succeed
        self.assertEqual(errors, [])
        self.assertSequenceEqual(warnings, ['rewards']) # rewards warning is still there

        self.main_user.refresh_from_db()
        self.assertEqual(self.main_user.username, "main_user")
        self.assertEqual(self.main_user.title, "Dr.")
        self.assertEqual(self.main_user.first_name, "Main")
        self.assertEqual(self.main_user.last_name, "User")
        self.assertEqual(self.main_user.email, "other@test.com")
        self.assertSequenceEqual(self.main_user.groups.all(), [self.group1, self.group2])
        self.assertSequenceEqual(self.main_user.delegates.all(), [self.user1, self.user2, self.user3])
        self.assertSequenceEqual(self.main_user.represented_users.all(), [self.user1, self.user3])
        self.assertSequenceEqual(self.main_user.cc_users.all(), [self.user1])
        self.assertSequenceEqual(self.main_user.ccing_users.all(), [self.user1, self.user2])
        self.assertSequenceEqual(self.course1.participants.all(), [self.main_user])
        self.assertSequenceEqual(self.course2.participants.all(), [self.main_user])
        self.assertSequenceEqual(self.course2.voters.all(), [self.main_user])
        self.assertSequenceEqual(self.course3.participants.all(), [self.main_user])
        self.assertSequenceEqual(self.course3.voters.all(), [self.main_user])
        self.assertTrue(self.main_user.is_superuser)
        self.assertTrue(RewardPointGranting.objects.filter(user_profile=self.main_user).exists())
        self.assertTrue(RewardPointRedemption.objects.filter(user_profile=self.main_user).exists())
        self.assertFalse(RewardPointGranting.objects.filter(user_profile=self.other_user).exists())
        self.assertFalse(RewardPointRedemption.objects.filter(user_profile=self.other_user).exists())


class TextAnswerReviewTest(WebTest):
    csrf_checks = False

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username="staff.user", groups=[Group.objects.get(name="Staff")])
        mommy.make(Course, pk=1)

    def helper(self, old_state, expected_new_state, action):
        textanswer = mommy.make(TextAnswer, state=old_state)
        response = self.app.post("/staff/comments/update_publish", {"id": textanswer.id, "action": action, "course_id": 1}, user="staff.user")
        self.assertEqual(response.status_code, 200)
        textanswer.refresh_from_db()
        self.assertEqual(textanswer.state, expected_new_state)

    def test_review_actions(self):
        self.helper(TextAnswer.NOT_REVIEWED, TextAnswer.PUBLISHED, "publish")
        self.helper(TextAnswer.NOT_REVIEWED, TextAnswer.HIDDEN, "hide")
        self.helper(TextAnswer.NOT_REVIEWED, TextAnswer.PRIVATE, "make_private")
        self.helper(TextAnswer.PUBLISHED, TextAnswer.NOT_REVIEWED, "unreview")


class UserFormTests(TestCase):

    def test_user_with_same_email(self):
        """
            Tests whether the user form correctly handles email adresses
            that already exist in the database
            Regression test for #590
        """
        user = mommy.make(UserProfile, email="uiae@example.com")

        data = {"username": "uiae", "email": user.email}
        form = UserForm(data=data)
        self.assertFalse(form.is_valid())

        data = {"username": "uiae", "email": user.email.upper()}
        form = UserForm(data=data)
        self.assertFalse(form.is_valid())

        data = {"username": "uiae", "email": user.email.upper()}
        form = UserForm(instance=user, data=data)
        self.assertTrue(form.is_valid())

    def test_user_with_same_username(self):
        """
            Tests whether the user form correctly handles usernames
            that already exist in the database
        """
        user = mommy.make(UserProfile)

        data = {"username": user.username}
        form = UserForm(data=data)
        self.assertFalse(form.is_valid())

        data = {"username": user.username.upper()}
        form = UserForm(data=data)
        self.assertFalse(form.is_valid())

        data = {"username": user.username.upper()}
        form = UserForm(instance=user, data=data)
        self.assertTrue(form.is_valid())


# New style tests
@override_settings(INSTITUTION_EMAIL_DOMAINS=["institution.com", "student.institution.com"])
class TestSemesterCourseImportParticipants(WebTest):
    @classmethod
    def setUpTestData(cls):
        mommy.make(Semester, pk=1)
        mommy.make(UserProfile, username="user", groups=[Group.objects.get(name="Staff")])
        cls.course = mommy.make(Course, pk=1)

    def test_import_valid_file(self):
        page = self.app.get("/staff/semester/1/course/1/importparticipants", user='user')

        original_participant_count = self.course.participants.count()

        form = lastform(page)
        form["excel_file"] = (os.path.join(settings.BASE_DIR, "staff/fixtures/valid_user_import.xls"),)
        form.submit(name="operation", value="import")

        self.assertEqual(self.course.participants.count(), original_participant_count + 2)

    def test_import_invalid_file(self):
        page = self.app.get("/staff/semester/1/course/1/importparticipants", user='user')

        original_user_count = UserProfile.objects.count()

        form = lastform(page)
        form["excel_file"] = (os.path.join(settings.BASE_DIR, "staff/fixtures/invalid_user_import.xls"),)

        reply = form.submit(name="operation", value="import")

        self.assertContains(reply, 'Sheet &quot;Sheet1&quot;, row 2: Email address is missing.')
        self.assertContains(reply, 'Errors occurred while parsing the input data. No data was imported.')

        self.assertEquals(UserProfile.objects.count(), original_user_count)

    def test_test_run(self):
        page = self.app.get("/staff/semester/1/course/1/importparticipants", user='user')

        original_participant_count = self.course.participants.count()

        form = lastform(page)
        form["excel_file"] = (os.path.join(settings.BASE_DIR, "staff/fixtures/valid_user_import.xls"),)
        form.submit(name="operation", value="test")

        self.assertEqual(self.course.participants.count(), original_participant_count)

    def test_suspicious_operation(self):
        page = self.app.get("/staff/semester/1/course/1/importparticipants", user='user')

        form = lastform(page)
        form["excel_file"] = (os.path.join(settings.BASE_DIR, "staff/fixtures/valid_user_import.xls"),)

        # Should throw SuspiciousOperation Exception.
        reply = form.submit(name="operation", value="hackit", expect_errors=True)

        self.assertEqual(reply.status_code, 400)
