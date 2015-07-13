from django.core.urlresolvers import reverse
from django_webtest import WebTest
from django.test import TestCase
from webtest import AppError
from django.test import Client
from django.test.utils import override_settings
from django.forms.models import inlineformset_factory
from django.core import mail
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.core.management import call_command
from django.conf import settings
from django.contrib.auth.models import Group
from django.db.utils import IntegrityError

from evap.evaluation.models import Semester, Questionnaire, Question, UserProfile, Course, \
                            Contribution, TextAnswer, EmailTemplate, NotArchiveable, Degree
from evap.evaluation.tools import calculate_average_grades_and_deviation
from evap.staff.forms import CourseEmailForm, UserForm, ContributionFormSet, ContributionForm, \
                             CourseForm, ImportForm, UserImportForm
from evap.contributor.forms import EditorContributionFormSet
from evap.contributor.forms import CourseForm as ContributorCourseForm
from evap.contributor.forms import UserForm as ContributorUserForm
from evap.rewards.models import RewardPointRedemptionEvent, SemesterActivation
from evap.rewards.tools import reward_points_of_user

from model_mommy import mommy

import os.path
import datetime
import unittest


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

    def test_sample_xls(self):
        page = self.app.get("/staff/semester/1/import", user='user')

        original_user_count = UserProfile.objects.all().count()

        form = lastform(page)
        form["vote_start_date"] = "2015-01-01"
        form["vote_end_date"] = "2099-01-01"
        form["excel_file"] = (os.path.join(settings.BASE_DIR, "static", "sample.xls"),)
        form.submit(name="operation", value="import")

        self.assertEqual(UserProfile.objects.count(), original_user_count + 4)

    def test_sample_user_xls(self):
        page = self.app.get("/staff/user/import", user='user')

        original_user_count = UserProfile.objects.all().count()

        form = lastform(page)
        form["excel_file"] = (os.path.join(settings.BASE_DIR, "static", "sample_user.xls"),)
        form.submit(name="operation", value="import")

        self.assertEqual(UserProfile.objects.count(), original_user_count + 2)


class UsecaseTests(WebTest):

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username="staff.user", groups=[Group.objects.get(name="Staff")])

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
        original_user_count = UserProfile.objects.all().count()

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
        user.save()

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
        page = page.click("Seminar")
        page = page.click("Copy")
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
        mommy.make(Course, semester=semester, type="Seminar", contributions=[
                            mommy.make(Contribution, contributor=mommy.make(UserProfile), responsible=True)])
        mommy.make(Course, semester=semester, type="Vorlesung", contributions=[
                            mommy.make(Contribution, contributor=mommy.make(UserProfile), responsible=True)])
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
        contribution = mommy.make(Contribution, contributor=user, responsible=True)

        page = self.app.get(reverse("staff:index"), user="staff.user")
        page = page.click(contribution.course.semester.name_en, index=0)
        page = page.click(contribution.course.name_en)

        # remove responsibility in contributor's checkbox
        form = lastform(page)
        form['contributions-0-responsible'] = False
        page = form.submit()

        self.assertIn("No responsible contributor found", page)


@unittest.skip("skip performance test because of d1dd563")
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


@override_settings(INSTITUTION_EMAIL_DOMAINS=["example.com"])
class URLTests(WebTest):
    fixtures = ['minimal_test_data']

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

    def get_submit_assert_302(self, url, user):
        response = self.get_assert_200(url, user)
        response = response.forms[2].submit("")
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
            ("test_index", "/", ""),
            ("test_faq", "/faq", ""),
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
            ("test_staff_semester_x_delete", "/staff/semester/2/delete", "evap"),
            ("test_staff_semester_x_course_create", "/staff/semester/1/course/create", "evap"),
            ("test_staff_semester_x_import", "/staff/semester/1/import", "evap"),
            ("test_staff_semester_x_assign", "/staff/semester/1/assign", "evap"),
            ("test_staff_semester_x_lottery", "/staff/semester/1/lottery", "evap"),
            ("test_staff_semester_x_todo", "/staff/semester/1/todo", "evap"),
            # staff semester course
            ("test_staff_semester_x_course_y_edit", "/staff/semester/1/course/5/edit", "evap"),
            ("test_staff_semester_x_course_y_email", "/staff/semester/1/course/1/email", "evap"),
            ("test_staff_semester_x_course_y_preview", "/staff/semester/1/course/1/preview", "evap"),
            ("test_staff_semester_x_course_y_comments", "/staff/semester/1/course/5/comments", "evap"),
            ("test_staff_semester_x_course_y_comment_z_edit", "/staff/semester/1/course/7/comment/12/edit", "evap"),
            ("test_staff_semester_x_course_y_delete", "/staff/semester/1/course/1/delete", "evap"),
            ("test_staff_semester_x_courseoperation", "/staff/semester/1/courseoperation?course=1&operation=prepare", "evap"),
            # staff semester single_result
            ("test_staff_semester_x_single_result_y_edit", "/staff/semester/1/course/11/edit", "evap"),
            ("test_staff_semester_x_single_result_y_delete", "/staff/semester/1/course/11/delete", "evap"),
            # staff questionnaires
            ("test_staff_questionnaire", "/staff/questionnaire/", "evap"),
            ("test_staff_questionnaire_create", "/staff/questionnaire/create", "evap"),
            ("test_staff_questionnaire_x_edit", "/staff/questionnaire/3/edit", "evap"),
            ("test_staff_questionnaire_x", "/staff/questionnaire/2", "evap"),
            ("test_staff_questionnaire_x_copy", "/staff/questionnaire/2/copy", "evap"),
            ("test_staff_questionnaire_x_delete", "/staff/questionnaire/3/delete", "evap"),
            ("test_staff_questionnaire_delete", "/staff/questionnaire/create", "evap"),
            # staff user
            ("test_staff_user", "/staff/user/", "evap"),
            ("test_staff_user_import", "/staff/user/import", "evap"),
            ("test_staff_sample_xls", "/static/sample_user.xls", "evap"),
            ("test_staff_user_create", "/staff/user/create", "evap"),
            ("test_staff_user_x_delete", "/staff/user/4/delete", "evap"),
            ("test_staff_user_x_edit", "/staff/user/4/edit", "evap"),
            # staff template
            ("test_staff_template_x", "/staff/template/1", "evap"),
            # faq
            ("test_staff_faq", "/staff/faq/", "evap"),
            ("test_staff_faq_x", "/staff/faq/1", "evap"),
            # results
            ("test_results", "/results/", "evap"),
            ("test_results_semester_x", "/results/semester/1", "evap"),
            ("test_results_semester_x_course_y", "/results/semester/1/course/8", "evap"),
            ("test_results_semester_x_course_y", "/results/semester/1/course/8", "contributor"),
            ("test_results_semester_x_course_y", "/results/semester/1/course/8", "responsible"),
            ("test_results_semester_x_export", "/results/semester/1/export", "evap"),
            ("test_results_semester_x_course_y", "/results/semester/1/course/11", "evap"), # single result
            # contributor
            ("test_contributor", "/contributor/", "responsible"),
            ("test_contributor", "/contributor/", "editor"),
            ("test_contributor_course_x", "/contributor/course/7", "responsible"),
            ("test_contributor_course_x", "/contributor/course/7", "editor"),
            ("test_contributor_course_x_preview", "/contributor/course/7/preview", "responsible"),
            ("test_contributor_course_x_preview", "/contributor/course/7/preview", "editor"),
            ("test_contributor_course_x_edit", "/contributor/course/2/edit", "responsible"),
            ("test_contributor_course_x_edit", "/contributor/course/2/edit", "editor"),
            ("test_contributor_profile", "/contributor/profile", "responsible"),
            ("test_contributor_profile", "/contributor/profile", "editor"),
            # rewards
            ("rewards_index", "/rewards/", "student"),
            ("reward_points_redemption_events", "/rewards/reward_point_redemption_events/", "evap"),
            ("reward_points_redemption_event_create", "/rewards/reward_point_redemption_event/create", "evap"),
            ("reward_points_redemption_event_edit", "/rewards/reward_point_redemption_event/1/edit", "evap"),
            ("reward_points_redemption_event_export", "/rewards/reward_point_redemption_event/1/export", "evap"),
            ("reward_points_semester_activation", "/rewards/reward_semester_activation/1/on", "evap"),
            ("reward_points_semester_deactivation", "/rewards/reward_semester_activation/1/off", "evap"),
            ("reward_points_semester_overview", "/rewards/semester/1/reward_points", "evap"),]
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
            ("test_staff_semester_x_course_y_delete_fail", "/staff/semester/1/course/8/delete", "evap"),
            ("test_staff_questionnaire_x_edit_fail", "/staff/questionnaire/2/edit", "evap"),
            ("test_staff_user_x_delete_fail", "/staff/user/2/delete", "evap"),
            ("test_staff_semester_x_delete_fail", "/staff/semester/1/delete", "evap"),
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

    def test_staff_semester_x_delete__nodata_success(self):
        self.get_submit_assert_302("/staff/semester/2/delete", "evap")

    def test_staff_semester_x_assign__nodata_success(self):
        self.get_submit_assert_302("/staff/semester/1/assign", "evap")

    def test_staff_semester_x_lottery__nodata_success(self):
        self.get_submit_assert_200("/staff/semester/1/lottery", "evap")

    def test_staff_semester_x_course_y_edit__nodata_success(self):
        self.get_submit_assert_302("/staff/semester/1/course/1/edit", "evap")

    def test_staff_semester_x_course_y_delete__nodata_success(self):
        self.get_submit_assert_302("/staff/semester/1/course/1/delete", "evap"),

    def test_staff_questionnaire_x_edit__nodata_success(self):
        self.get_submit_assert_302("/staff/questionnaire/3/edit", "evap")

    def test_staff_questionnaire_x_delete__nodata_success(self):
        self.get_submit_assert_302("/staff/questionnaire/3/delete", "evap"),

    def test_staff_user_x_delete__nodata_success(self):
        self.get_submit_assert_302("/staff/user/4/delete", "evap"),

    def test_staff_user_x_edit__nodata_success(self):
        self.get_submit_assert_302("/staff/user/4/edit", "evap")

    def test_staff_template_x__nodata_success(self):
        self.get_submit_assert_200("/staff/template/1", "evap")

    def test_staff_faq__nodata_success(self):
        self.get_submit_assert_302("/staff/faq/", "evap")

    def test_staff_faq_x__nodata_success(self):
        self.get_submit_assert_302("/staff/faq/1", "evap")

    def test_contributor_profile(self):
        self.get_submit_assert_302("/contributor/profile", "responsible")

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

        ContributionFormset = inlineformset_factory(Course, Contribution, formset=ContributionFormSet, form=ContributionForm, extra=0, exclude=('course',))

        data = {
            'contributions-TOTAL_FORMS': 1,
            'contributions-INITIAL_FORMS': 0,
            'contributions-MAX_NUM_FORMS': 5,
            'contributions-0-course': course.pk,
            'contributions-0-questionnaires': [1],
            'contributions-0-order': 0,
            'contributions-0-responsible': "on",
        }
        # no contributor and no responsible
        self.assertFalse(ContributionFormset(instance=course, data=data.copy()).is_valid())
        # valid
        data['contributions-0-contributor'] = 1
        self.assertTrue(ContributionFormset(instance=course, data=data.copy()).is_valid())
        # duplicate contributor
        data['contributions-TOTAL_FORMS'] = 2
        data['contributions-1-contributor'] = 1
        data['contributions-1-course'] = course.pk
        data['contributions-1-questionnaires'] = [1]
        data['contributions-1-order'] = 1
        self.assertFalse(ContributionFormset(instance=course, data=data).is_valid())
        # two responsibles
        data['contributions-1-contributor'] = 2
        data['contributions-1-responsible'] = "on"
        self.assertFalse(ContributionFormset(instance=course, data=data).is_valid())

    def test_semester_deletion(self):
        """
            Tries to delete two semesters via the respective view,
            only the second attempt should succeed.
        """
        self.assertFalse(Semester.objects.get(pk=1).can_staff_delete)
        self.client.login(username='evap', password='evap')
        response = self.client.get("/staff/semester/1/delete", follow=True)
        self.assertIn("cannot be deleted", list(response.context['messages'])[0].message)
        self.assertTrue(Semester.objects.filter(pk=1).exists())

        self.assertTrue(Semester.objects.get(pk=2).can_staff_delete)
        self.get_submit_assert_302("/staff/semester/2/delete", "evap")
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
        data = dict(name_de="asdf", name_en="asdf", type="asdf", degrees=["1"],
                    vote_start_date="02/1/2014", vote_end_date="02/1/2099", general_questions=["2"])
        response = self.get_assert_200("/staff/semester/1/course/create", "evap")
        form = lastform(response)
        form["name_de"] = "lfo9e7bmxp1xi"
        form["name_en"] = "asdf"
        form["type"] = "a type"
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
        form['contributions-0-responsible'] = "on"

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
        form["type"] = "a type"
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
            Tries to delete two questionnaires via the respective view,
            only the second attempt should succeed.
        """
        self.assertFalse(Questionnaire.objects.get(pk=2).can_staff_delete)
        self.client.login(username='evap', password='evap')
        page = self.client.get("/staff/questionnaire/2/delete", follow=True)
        self.assertIn("cannot be deleted", list(page.context['messages'])[0].message)
        self.assertTrue(Questionnaire.objects.filter(pk=2).exists())

        self.assertTrue(Questionnaire.objects.get(pk=3).can_staff_delete)
        self.get_submit_assert_302("/staff/questionnaire/3/delete", "evap")
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

        ContributionFormset = inlineformset_factory(Course, Contribution, formset=ContributionFormSet, form=ContributionForm, extra=0, exclude=('course',))

        # here we have two responsibles (one of them deleted), and a deleted contributor with no questionnaires.
        data = {
            'contributions-TOTAL_FORMS': 3,
            'contributions-INITIAL_FORMS': 0,
            'contributions-MAX_NUM_FORMS': 5,
            'contributions-0-course': course.pk,
            'contributions-0-questionnaires': [questionnaire.pk],
            'contributions-0-order': 0,
            'contributions-0-responsible': "on",
            'contributions-0-contributor': user1.pk,
            'contributions-0-DELETE': 'on',
            'contributions-1-course': course.pk,
            'contributions-1-questionnaires': [questionnaire.pk],
            'contributions-1-order': 0,
            'contributions-1-responsible': "on",
            'contributions-1-contributor': user2.pk,
            'contributions-2-course': course.pk,
            'contributions-2-questionnaires': [],
            'contributions-2-order': 1,
            'contributions-2-contributor': user2.pk,
            'contributions-2-DELETE': 'on',
        }

        formset = ContributionFormset(instance=course, data=data)
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
        contribution1 = mommy.make(Contribution, course=course, contributor=user1, responsible=True, can_edit=True, questionnaires=[questionnaire])

        ContributionFormset = inlineformset_factory(Course, Contribution, formset=ContributionFormSet, form=ContributionForm, extra=0, exclude=('course',))

        data = {
            'contributions-TOTAL_FORMS': 2,
            'contributions-INITIAL_FORMS': 1,
            'contributions-MAX_NUM_FORMS': 5,
            'contributions-0-id': contribution1.pk,
            'contributions-0-course': course.pk,
            'contributions-0-questionnaires': [questionnaire.pk],
            'contributions-0-order': 0,
            'contributions-0-responsible': "on",
            'contributions-0-contributor': user1.pk,
            'contributions-0-DELETE': 'on',
            'contributions-1-course': course.pk,
            'contributions-1-questionnaires': [questionnaire.pk],
            'contributions-1-order': 0,
            'contributions-1-responsible': "on",
            'contributions-1-contributor': user1.pk ,
        }

        formset = ContributionFormset(instance=course, data=data)
        self.assertTrue(formset.is_valid())

    def test_editors_cannot_change_responsible(self):
        """
            Asserts that editors cannot change the responsible of a course
            through POST-hacking. Regression test for #504.
        """
        course = mommy.make(Course)
        user1 = mommy.make(UserProfile)
        user2 = mommy.make(UserProfile)
        questionnaire = mommy.make(Questionnaire, is_for_contributors=True)
        contribution1 = mommy.make(Contribution, course=course, contributor=user1, responsible=True, can_edit=True, questionnaires=[questionnaire])

        EditorContributionFormset = inlineformset_factory(Course, Contribution, formset=EditorContributionFormSet, form=ContributionForm, extra=0, exclude=('course',))

        data = {
            'contributions-TOTAL_FORMS': 1,
            'contributions-INITIAL_FORMS': 1,
            'contributions-MAX_NUM_FORMS': 5,
            'contributions-0-id': contribution1.pk,
            'contributions-0-course': course.pk,
            'contributions-0-questionnaires': [questionnaire.pk],
            'contributions-0-order': 1,
            'contributions-0-responsible': "on",
            'contributions-0-contributor': user1.pk,
        }

        formset = EditorContributionFormset(instance=course, data=data.copy())
        self.assertTrue(formset.is_valid())

        self.assertTrue(course.contributions.get(responsible=True).contributor == user1)
        data["contributions-0-contributor"] = user2.pk
        formset = EditorContributionFormset(instance=course, data=data.copy())
        self.assertTrue(formset.is_valid())
        formset.save()
        self.assertTrue(course.contributions.get(responsible=True).contributor == user1)


class ArchivingTests(WebTest):
    fixtures = ['minimal_test_data']

    @classmethod
    def setUpTestData(cls):
        new_semester = mommy.make(Semester)
        course1 = Course.objects.get(pk=7)
        course1.publish()
        course1.semester = new_semester
        course1.save()
        course2 = Course.objects.get(pk=8)
        course2.semester = new_semester
        course2.save()
        cls.test_semester = new_semester

    def test_counts_dont_change(self):
        """
            Asserts that course.num_voters course.num_participants don't change after archiving.
        """
        semester = ArchivingTests.test_semester

        voters_counts = {}
        participant_counts = {}
        for course in semester.course_set.all():
            voters_counts[course] = course.num_voters
            participant_counts[course] = course.num_participants
        some_participant = semester.course_set.first().participants.first()
        course_count = some_participant.course_set.count()

        semester.archive()

        for course in semester.course_set.all():
            self.assertEqual(voters_counts[course], course.num_voters)
            self.assertEqual(participant_counts[course], course.num_participants)
        # participants should not loose courses, as they should see all of them
        self.assertEqual(course_count, some_participant.course_set.count())

    def test_is_archived(self):
        """
            Tests whether is_archived returns True on archived semesters and courses.
        """
        semester = ArchivingTests.test_semester

        for course in semester.course_set.all():
            self.assertFalse(course.is_archived)

        semester.archive()

        for course in semester.course_set.all():
            self.assertTrue(course.is_archived)

    def test_archiving_does_not_change_results(self):
        semester = ArchivingTests.test_semester

        results = {}
        for course in semester.course_set.all():
            results[course] = calculate_average_grades_and_deviation(course)

        semester.archive()
        cache.clear()

        for course in semester.course_set.all():
            self.assertTrue(calculate_average_grades_and_deviation(course) == results[course])

    def test_archiving_twice_raises_exception(self):
        semester = ArchivingTests.test_semester
        semester.archive()
        with self.assertRaises(NotArchiveable):
            semester.archive()
        with self.assertRaises(NotArchiveable):
            semester.course_set.first()._archive()

    def get_assert_403(self, url, user):
        try:
            self.app.get(url, user=user, status=403)
        except AppError as e:
            self.fail('url "{}" failed with user "{}"'.format(url, user))

    def test_raise_403(self):
        """
            Tests whether inaccessible views on archived semesters/courses correctly raise a 403.
        """
        semester = ArchivingTests.test_semester
        semester.archive()

        semester_url = "/staff/semester/{}/".format(semester.pk)

        self.get_assert_403(semester_url + "import", "evap")
        self.get_assert_403(semester_url + "assign", "evap")
        self.get_assert_403(semester_url + "course/create", "evap")
        self.get_assert_403(semester_url + "course/7/edit", "evap")
        self.get_assert_403(semester_url + "course/7/delete", "evap")
        self.get_assert_403(semester_url + "courseoperation", "evap")


class RedirectionTest(WebTest):
    fixtures = ['minimal_test_data']

    def get_assert_403(self, url, user):
        try:
            self.app.get(url, user=user, status=403)
        except AppError as e:
            self.fail('url "{}" failed with user "{}"'.format(url, user))

    def test_not_authenticated(self):
        """
            Asserts that an unauthorized user gets redirected to the login page.
        """
        url = "/contributor/course/3/edit"
        response = self.app.get(url)
        self.assertRedirects(response, "/?next=/contributor/course/3/edit")

    def test_wrong_usergroup(self):
        """
            Asserts that a user who is not part of the usergroup
            that is required for a specific view gets a 403.
            Regression test for #483
        """
        url = "/contributor/course/2/edit"
        self.get_assert_403(url, "student")

    def test_wrong_state(self):
        """
            Asserts that a contributor attempting to edit a course
            that is in a state where editing is not allowed gets a 403.
        """
        url = "/contributor/course/3/edit"
        self.get_assert_403(url, "responsible")

    def test_ok(self):
        """
            Asserts that an editor of a course can access
            the edit page of that course.
        """
        url = "/contributor/course/2/edit"
        response = self.app.get(url, user="responsible")
        self.assertEqual(response.status_code, 200)


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


class TextAnswerReviewTest(WebTest):
    csrf_checks = False

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username="staff.user", groups=[Group.objects.get(name="Staff")])
        mommy.make(Course, pk=1)

    def helper(self, old_state, expected_new_state, action):
        textanswer = mommy.make(TextAnswer, state=old_state)
        response = self.app.post("/staff/comments/updatepublish", {"id": textanswer.id, "action": action, "course_id": 1}, user="staff.user")
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
        form = ContributorUserForm(data=data)
        self.assertFalse(form.is_valid())

        data = {"username": "uiae", "email": user.email.upper()}
        form = UserForm(data=data)
        self.assertFalse(form.is_valid())
        form = ContributorUserForm(data=data)
        self.assertFalse(form.is_valid())

        data = {"username": "uiae", "email": user.email.upper()}
        form = UserForm(instance=user, data=data)
        self.assertTrue(form.is_valid())
        form = ContributorUserForm(instance=user, data=data)
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
