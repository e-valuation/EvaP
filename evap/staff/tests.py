from django.core.urlresolvers import reverse
from django_webtest import WebTest
from webtest import AppError
from django.test import Client
from django.forms.models import inlineformset_factory
from django.core import mail
from django.core.exceptions import ObjectDoesNotExist
from django.conf import settings

from evap.evaluation.models import Semester, Questionnaire, UserProfile, Course, Contribution, TextAnswer, EmailTemplate
from evap.staff.forms import CourseEmailForm, UserForm, SelectCourseForm, ReviewTextAnswerForm, \
                            ContributionFormSet, ContributionForm, CourseForm
from evap.rewards.models import RewardPointRedemptionEvent, SemesterActivation
from evap.rewards.tools import reward_points_of_user

import os.path
import datetime


def lastform(page):
    return page.forms[max(page.forms.keys())]


# taken from http://lukeplant.me.uk/blog/posts/fuzzy-testing-with-assertnumqueries/
class FuzzyInt(int):
    def __new__(cls, lowest, highest):
        obj = super(FuzzyInt, cls).__new__(cls, highest)
        obj.lowest = lowest
        obj.highest = highest
        return obj

    def __eq__(self, other):
        return other >= self.lowest and other <= self.highest

    def __repr__(self):
        return "[%d..%d]" % (self.lowest, self.highest)


class UsecaseTests(WebTest):
    fixtures = ['usecase-tests']
    extra_environ = {'HTTP_ACCEPT_LANGUAGE': 'en'}

    def test_import(self):
        page = self.app.get(reverse("staff_root"), user='staff.user')

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

        # safe original user count
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
        environ = self.app.extra_environ
        self.app.extra_environ = {}
        self.assertRedirects(self.app.get(reverse("evap.results.views.index"), extra_environ={}), "/?next=/results/")
        self.app.extra_environ = environ

        user = UserProfile.objects.all()[0]
        user.generate_login_key()
        user.save()

        url_with_key = reverse("evap.results.views.index") + "?userkey=%s" % user.login_key
        self.app.get(url_with_key)

    def test_create_questionnaire(self):
        page = self.app.get(reverse("staff_root"), user="staff.user")

        # create a new questionnaire
        page = page.click("[Cc]reate [Nn]ew [Qq]uestionnaire")
        questionnaire_form = lastform(page)
        questionnaire_form['name_de'] = "Test Fragebogen"
        questionnaire_form['name_en'] = "test questionnaire"
        questionnaire_form['public_name_de'] = "Oeffentlicher Test Fragebogen"
        questionnaire_form['public_name_en'] = "Public Test Questionnaire"
        questionnaire_form['question_set-0-text_de'] = "Frage 1"
        questionnaire_form['question_set-0-text_en'] = "Question 1"
        questionnaire_form['question_set-0-kind'] = "T"
        questionnaire_form['index'] = 0
        page = questionnaire_form.submit().follow()

        # retrieve new questionnaire
        questionnaire = Questionnaire.objects.get(name_de="Test Fragebogen", name_en="test questionnaire")
        self.assertEqual(questionnaire.question_set.count(), 1, "New questionnaire is empty.")

    def test_create_empty_questionnaire(self):
        page = self.app.get(reverse("staff_root"), user="staff.user")

        # create a new questionnaire
        page = page.click("[Cc]reate [Nn]ew [Qq]uestionnaire")
        questionnaire_form = lastform(page)
        questionnaire_form['name_de'] = "Test Fragebogen"
        questionnaire_form['name_en'] = "test questionnaire"
        questionnaire_form['public_name_de'] = "Oeffentlicher Test Fragebogen"
        questionnaire_form['public_name_en'] = "Public Test Questionnaire"
        questionnaire_form['index'] = 0
        page = questionnaire_form.submit()

        assert "You must have at least one of these" in page

        # retrieve new questionnaire
        with self.assertRaises(Questionnaire.DoesNotExist):
            Questionnaire.objects.get(name_de="Test Fragebogen", name_en="test questionnaire")

    def test_copy_questionnaire(self):
        page = self.app.get(reverse("staff_root"), user="staff.user")

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
        self.assertEqual(questionnaire.question_set.count(), 2, "New questionnaire is empty.")

    def test_assign_questionnaires(self):
        page = self.app.get(reverse("staff_root"), user="staff.user")

        # assign questionnaire to courses
        page = page.click("Semester 1 \(en\)", index=0)
        page = page.click("Assign Questionnaires")
        assign_form = lastform(page)
        assign_form['Seminar'] = [1]
        assign_form['Vorlesung'] = [1]
        page = assign_form.submit().follow()

        # get semester and check
        semester = Semester.objects.get(pk=1)
        questionnaire = Questionnaire.objects.get(pk=1)
        for course in semester.course_set.all():
            self.assertEqual(course.general_contribution.questionnaires.count(), 1)
            self.assertEqual(course.general_contribution.questionnaires.get(), questionnaire)

    def test_remove_responsibility(self):
        page = self.app.get(reverse("staff_root"), user="staff.user")

        # remove responsibility in lecturer's checkbox
        page = page.click("Semester 1 \(en\)", index=0)
        page = page.click("Course 1 \(en\)")
        form = lastform(page)

        # add one questionnaire to avoid the error message preventing the responsibility error to show
        form['general_questions'] = True

        form['contributions-0-responsible'] = False
        page = form.submit()

        assert "No responsible contributor found" in page

    # disabled, see issue #164: https://github.com/fsr-itse/EvaP/issues/164
    #def test_num_queries_user_list(self):
    #    """
    #        ensures that the number of queries in the user list is constant
    #        and not linear to the number of users
    #    """
    #    num_users = 50
    #    for i in range(0, num_users):
    #        user = UserProfile.objects.get_or_create(id=9000+i, username=i)
    #    with self.assertNumQueries(FuzzyInt(0, num_users-1)):
    #        self.app.get("/staff/user/", user="staff.user")

    def test_users_are_deletable(self):
        self.assertTrue(UserProfile.objects.filter(username="participant_user").get().can_staff_delete)
        self.assertFalse(UserProfile.objects.filter(username="contributor_user").get().can_staff_delete)



class URLTests(WebTest):
    fixtures = ['minimal_test_data']
    csrf_checks = False
    extra_environ = {'HTTP_ACCEPT_LANGUAGE': 'en'}

    def setUp(self):
        settings.INSTITUTION_EMAIL_DOMAINS.append("example.com")

    def tearDown(self):
        # settings are persistent between tests, so remove that again
        settings.INSTITUTION_EMAIL_DOMAINS.remove("example.com")

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
            ("test_staff_semester_x_reset", "/staff/semester/1/reset", "evap"),
            ("test_staff_semester_x_contributorready", "/staff/semester/1/contributorready", "evap"),
            ("test_staff_semester_x_approve", "/staff/semester/1/approve", "evap"),
            ("test_staff_semester_x_publish", "/staff/semester/1/publish", "evap"),
            # staff semester course
            ("test_staff_semester_x_course_y_edit", "/staff/semester/1/course/5/edit", "evap"),
            ("test_staff_semester_x_course_y_email", "/staff/semester/1/course/1/email", "evap"),
            ("test_staff_semester_x_course_y_preview", "/staff/semester/1/course/1/preview", "evap"),
            ("test_staff_semester_x_course_y_comments", "/staff/semester/1/course/5/comments", "evap"),
            ("test_staff_semester_x_course_y_review", "/staff/semester/1/course/5/review", "evap"),
            ("test_staff_semester_x_course_y_unpublish", "/staff/semester/1/course/8/unpublish", "evap"),
            ("test_staff_semester_x_course_y_delete", "/staff/semester/1/course/1/delete", "evap"),
            # staff questionnaires
            ("test_staff_questionnaire", "/staff/questionnaire/", "evap"),
            ("test_staff_questionnaire_create", "/staff/questionnaire/create", "evap"),
            ("test_staff_questionnaire_x_edit", "/staff/questionnaire/2/edit", "evap"),
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
            ("test_staff_semester_x_course_y_review_fail", "/staff/semester/1/course/8/review", "evap"),
            ("test_staff_semester_x_course_y_unpublish_fail", "/staff/semester/1/course/7/unpublish", "evap"),
            ("test_staff_questionnaire_x_edit_fail", "/staff/questionnaire/4/edit", "evap"),
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

    def test_staff_semester_x_reset__nodata_success(self):
        self.get_submit_assert_302("/staff/semester/1/reset", "evap")

    def test_staff_semester_x_contributorready__nodata_success(self):
        self.get_submit_assert_302("/staff/semester/1/contributorready", "evap")

    def test_staff_semester_x_approve__nodata_success(self):
        self.get_submit_assert_302("/staff/semester/1/approve", "evap")

    def test_staff_semester_x_publish__nodata_success(self):
        self.get_submit_assert_302("/staff/semester/1/publish", "evap")

    def test_staff_semester_x_course_y_edit__nodata_success(self):
        self.get_submit_assert_302("/staff/semester/1/course/1/edit", "evap")

    def test_staff_semester_x_course_y_review__nodata_success(self):
        self.get_submit_assert_302("/staff/semester/1/course/5/review", "evap")

    def test_staff_semester_x_course_y_unpublish__nodata_success(self):
        self.get_submit_assert_302("/staff/semester/1/course/8/unpublish", "evap"),

    def test_staff_semester_x_course_y_delete__nodata_success(self):
        self.get_submit_assert_302("/staff/semester/1/course/1/delete", "evap"),

    def test_staff_questionnaire_x_edit__nodata_success(self):
        self.get_submit_assert_302("/staff/questionnaire/2/edit", "evap")

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
        form.all_recepients_reachable()
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

    def test_course_selection_form(self):
        """
            Tests the SelectCourseForm with one valid input dataset
            (one cannot make it invalid through the UI).
        """
        course1 = Course.objects.get(pk=1)
        course2 = Course.objects.get(pk=2)
        data = {"1": True, "2": False}
        form = SelectCourseForm([course1, course2], data=data)
        self.assertTrue(form.is_valid())

    def test_review_text_answer_form(self):
        """
            Tests the ReviewTextAnswerForm with three valid input datasets
            (one cannot make it invalid through the UI).
        """
        textanswer = TextAnswer.objects.get(pk=1)
        data = dict(reviewed_answer=textanswer.original_answer, needs_further_review=False, hidden=False)
        self.assertTrue(ReviewTextAnswerForm(instance=textanswer, data=data).is_valid())
        data = dict(reviewed_answer="edited answer", needs_further_review=False, hidden=False)
        self.assertTrue(ReviewTextAnswerForm(instance=textanswer, data=data).is_valid())
        data = dict(reviewed_answer="edited answer", needs_further_review=True, hidden=True)
        self.assertTrue(ReviewTextAnswerForm(instance=textanswer, data=data).is_valid())

    def test_contributor_form_set(self):
        """
            Tests the ContributionFormset with various input data sets.
        """
        course = Course.objects.create(pk=9001, semester_id=1)

        ContributionFormset = inlineformset_factory(Course, Contribution, formset=ContributionFormSet, form=ContributionForm, extra=0, exclude=('course',))

        data = {
            'contributions-TOTAL_FORMS': 1,
            'contributions-INITIAL_FORMS': 0,
            'contributions-MAX_NUM_FORMS': 5,
            'contributions-0-course': 9001,
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
        data['contributions-1-course'] = 9001
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

    def helper_semester_state_views(self, url, course_ids, old_states, new_state):
        page = self.app.get(url, user="evap")
        form = lastform(page)
        for course_id in course_ids:
            self.assertIn(Course.objects.get(pk=course_id).state, old_states)
            form[str(course_id)] = "on"
        response = form.submit()
        self.assertIn("Successfully", str(response))
        for course_id in course_ids:
            self.assertEqual(Course.objects.get(pk=course_id).state,  new_state)

    """
        The following four tests test the course state transitions triggerable via the UI.
    """
    def test_semester_publish(self):
        self.helper_semester_state_views("/staff/semester/1/publish", [7], ["reviewed"], "published")

    def test_semester_reset(self):
        self.helper_semester_state_views("/staff/semester/1/reset", [2], ["prepared"], "new")

    def test_semester_approve(self):
        self.helper_semester_state_views("/staff/semester/1/approve", [1,2,3], ["new", "prepared", "lecturerApproved"], "approved")

    def test_semester_contributor_ready(self):
        self.helper_semester_state_views("/staff/semester/1/contributorready", [1,3], ["new", "lecturerApproved"], "prepared")

    def test_course_create(self):
        """
            Tests the course creation view with one valid and one invalid input dataset.
        """
        data = dict(name_de="asdf", name_en="asdf", kind="asdf", degree="asd",
                    vote_start_date="02/1/2014", vote_end_date="02/1/2099", general_questions=["2"])
        response = self.get_assert_200("/staff/semester/1/course/create", "evap")
        form = lastform(response)
        form["name_de"] = "lfo9e7bmxp1xi"
        form["name_en"] = "asdf"
        form["kind"] = "a type"
        form["degree"] = "a degree"
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

    def test_course_review(self):
        """
            Tests the course review view with various input datasets.
        """
        self.get_assert_302("/staff/semester/1/course/4/review", user="evap")
        self.assertEqual(Course.objects.get(pk=6).state, "evaluated")

        page = self.get_assert_200("/staff/semester/1/course/6/review", user="evap")

        form = lastform(page)
        form["form-0-hidden"] = "on"
        form["form-1-needs_further_review"] = "on"
        # Actually this is not guaranteed, but i'll just guarantee it now for this test.
        self.assertEqual(form["form-0-id"].value, "5")
        self.assertEqual(form["form-1-id"].value, "8")
        page = form.submit(name="operation", value="save_and_next").follow()

        form = lastform(page)
        self.assertEqual(form["form-0-reviewed_answer"].value, "mfj49s1my.45j")
        form["form-0-reviewed_answer"] = "mflkd862xmnbo5"
        page = form.submit()

        self.assertEqual(TextAnswer.objects.get(pk=5).hidden, True)
        self.assertEqual(TextAnswer.objects.get(pk=5).reviewed_answer, "")
        self.assertEqual(TextAnswer.objects.get(pk=8).reviewed_answer, "mflkd862xmnbo5")
        self.assertEqual(Course.objects.get(pk=6).state, "reviewed")

        self.get_assert_302("/staff/semester/1/course/6/review", user="evap")

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

        form.submit(name="operation", value="save")
        self.assertEqual(Course.objects.get(pk=2).state, "prepared")

        form.submit(name="operation", value="approve")
        self.assertEqual(Course.objects.get(pk=2).state, "lecturerApproved")

        # test what happens if the operation is not specified correctly
        response = form.submit(expect_errors=True)
        self.assertEqual(response.status_code, 403)

    def test_student_vote(self):
        """
            Submits a student vote for coverage and verifies that the
            student cannot vote on the course a second time.
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
        form["question_20_1_2"] = 1
        response = form.submit()

        self.get_assert_403("/student/vote/5", user="lazy.student")

class ContributorFormTests(WebTest):
    csrf_checks = False
    extra_environ = {'HTTP_ACCEPT_LANGUAGE': 'en'}

    def test_dont_validate_deleted_contributions(self):
        """
            Tests whether contributions marked for deletion are validated.
            Regression test for #415 and #244
        """
        course = Course.objects.create(pk=9001, semester_id=1)
        user = UserProfile.objects.create(pk=9001)
        user = UserProfile.objects.create(pk=9002, username="1")
        user = UserProfile.objects.create(pk=9003, username="2")
        questionnaire = Questionnaire.objects.create(pk=9001, index=0, is_for_contributors=True)

        ContributionFormset = inlineformset_factory(Course, Contribution, formset=ContributionFormSet, form=ContributionForm, extra=0, exclude=('course',))

        # here we have two responsibles (one of them deleted), and a deleted contributor with no questionnaires.
        data = {
            'contributions-TOTAL_FORMS': 3,
            'contributions-INITIAL_FORMS': 0,
            'contributions-MAX_NUM_FORMS': 5,
            'contributions-0-course': 9001,
            'contributions-0-questionnaires': [9001],
            'contributions-0-order': 0,
            'contributions-0-responsible': "on",
            'contributions-0-contributor': 9001,
            'contributions-0-DELETE': 'on',
            'contributions-1-course': 9001,
            'contributions-1-questionnaires': [9001],
            'contributions-1-order': 0,
            'contributions-1-responsible': "on",
            'contributions-1-contributor': 9002,
            'contributions-2-course': 9001,
            'contributions-2-questionnaires': [],
            'contributions-2-order': 1,
            'contributions-2-contributor': 9003,
            'contributions-2-DELETE': 'on',
        }

        formset = ContributionFormset(instance=course, data=data.copy())
        self.assertTrue(formset.is_valid())

    def test_take_deleted_contributions_into_account(self):
        """
            Tests whether contributions marked for deletion are properly taken into account 
            when the same contributor got added again in the same formset.
            Regression test for #415
        """
        course = Course.objects.create(pk=9001, semester_id=1)
        user1 = UserProfile.objects.create(pk=9001)
        questionnaire = Questionnaire.objects.create(pk=9001, index=0, is_for_contributors=True)

        contribution1 = Contribution.objects.create(pk=9001, course=course, contributor=user1, responsible=True, can_edit=True)
        contribution1.questionnaires = [questionnaire]

        ContributionFormset = inlineformset_factory(Course, Contribution, formset=ContributionFormSet, form=ContributionForm, extra=0, exclude=('course',))

        data = {
            'contributions-TOTAL_FORMS': 2,
            'contributions-INITIAL_FORMS': 1,
            'contributions-MAX_NUM_FORMS': 5,
            'contributions-0-id': 9001,
            'contributions-0-course': 9001,
            'contributions-0-questionnaires': [9001],
            'contributions-0-order': 0,
            'contributions-0-responsible': "on",
            'contributions-0-contributor': 9001,
            'contributions-0-DELETE': 'on',
            'contributions-1-course': 9001,
            'contributions-1-questionnaires': [9001],
            'contributions-1-order': 0,
            'contributions-1-responsible': "on",
            'contributions-1-contributor': 9001,
        }

        formset = ContributionFormset(instance=course, data=data.copy())
        self.assertTrue(formset.is_valid())
