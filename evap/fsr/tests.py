from django.core.urlresolvers import reverse
from django_webtest import WebTest
from django.test import Client
from django.forms.models import inlineformset_factory
from django.core import mail
from django.core.exceptions import ObjectDoesNotExist
from django.conf import settings

from django.contrib.auth.models import User
from evap.evaluation.models import Semester, Questionnaire, UserProfile, Course, Contribution, TextAnswer, EmailTemplate
from evap.fsr.forms import CourseEmailForm, UserForm, SelectCourseForm, ReviewTextAnswerForm, \
                            ContributorFormSet, ContributionForm, CourseForm
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
        page = self.app.get(reverse("fsr_root"), user='fsr.user')

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
        original_user_count = User.objects.all().count()

        # import excel file
        page = page.click("[Ii]mport")
        upload_form = lastform(page)
        upload_form['vote_start_date'] = "02/29/2000"
        upload_form['vote_end_date'] = "02/29/2012"
        upload_form['excel_file'] = (os.path.join(os.path.dirname(__file__), "fixtures", "samples.xls"),)
        page = upload_form.submit().follow()

        self.assertEqual(User.objects.count(), original_user_count + 24)

        courses = Course.objects.filter(semester=semester).all()
        self.assertEqual(len(courses), 23)

        for course in courses:
            responsibles_count = Contribution.objects.filter(course=course, responsible=True).count()
            self.assertEqual(responsibles_count, 1)

        check_student = User.objects.get(username="diam.synephebos")
        self.assertEqual(check_student.first_name, "Diam")
        self.assertEqual(check_student.email, "")

        check_contributor = User.objects.get(username="sanctus.aliquyam")
        self.assertEqual(check_contributor.first_name, "")
        self.assertEqual(check_contributor.last_name, "Aliquyam")
        self.assertEqual(check_contributor.email, "567@web.de")

    def test_login_key(self):
        environ = self.app.extra_environ
        self.app.extra_environ = {}
        self.assertRedirects(self.app.get(reverse("evap.results.views.index"), extra_environ={}), "/?next=/results/")
        self.app.extra_environ = environ

        user = User.objects.all()[0]
        userprofile = UserProfile.get_for_user(user)
        userprofile.generate_login_key()
        userprofile.save()

        url_with_key = reverse("evap.results.views.index") + "?userkey=%s" % userprofile.login_key
        self.app.get(url_with_key)

    def test_create_questionnaire(self):
        page = self.app.get(reverse("fsr_root"), user="fsr.user")

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
        page = self.app.get(reverse("fsr_root"), user="fsr.user")

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
        page = self.app.get(reverse("fsr_root"), user="fsr.user")

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
        page = self.app.get(reverse("fsr_root"), user="fsr.user")

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
        page = self.app.get(reverse("fsr_root"), user="fsr.user")

        # remove responsibility in lecturer's checkbox
        page = page.click("Semester 1 \(en\)", index=0)
        page = page.click("Course 1 \(en\)")
        form = lastform(page)

        # add one questionnaire to avoid the error message preventing the responsibility error to show
        form['general_questions'] = True

        form['contributions-0-responsible'] = False
        page = form.submit()

        assert "No responsible contributor found" in page

    def test_num_queries_user_list(self):
        """
            ensures that the number of queries in the user list is constant
            and not linear to the number of users
        """
        num_users = 50
        for i in range(0, num_users):
            user = User.objects.get_or_create(id=9000+i, username=i)
        with self.assertNumQueries(FuzzyInt(0, num_users-1)):
            self.app.get("/fsr/user/", user="fsr.user")

    def test_users_are_deletable(self):
        self.assertTrue(UserProfile.objects.filter(user__username="participant_user").get().can_fsr_delete)
        self.assertFalse(UserProfile.objects.filter(user__username="contributor_user").get().can_fsr_delete)



class URLTests(WebTest):
    fixtures = ['minimal_test_data']
    csrf_checks = False
    extra_environ = {'HTTP_ACCEPT_LANGUAGE': 'en'}

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
            # fsr main page
            ("test_fsr", "/fsr/", "evap"),
            # fsr semester
            ("test_fsr_semester_create", "/fsr/semester/create", "evap"),
            ("test_fsr_semester_x", "/fsr/semester/1", "evap"),
            ("test_fsr_semester_x", "/fsr/semester/1?tab=asdf", "evap"),
            ("test_fsr_semester_x_edit", "/fsr/semester/1/edit", "evap"),
            ("test_fsr_semester_x_delete", "/fsr/semester/2/delete", "evap"),
            ("test_fsr_semester_x_course_create", "/fsr/semester/1/course/create", "evap"),
            ("test_fsr_semester_x_import", "/fsr/semester/1/import", "evap"),
            ("test_fsr_semester_x_assign", "/fsr/semester/1/assign", "evap"),
            ("test_fsr_semester_x_lottery", "/fsr/semester/1/lottery", "evap"),
            ("test_fsr_semester_x_reset", "/fsr/semester/1/reset", "evap"),
            ("test_fsr_semester_x_contributorready", "/fsr/semester/1/contributorready", "evap"),
            ("test_fsr_semester_x_approve", "/fsr/semester/1/approve", "evap"),
            ("test_fsr_semester_x_publish", "/fsr/semester/1/publish", "evap"),
            # fsr semester course
            ("test_fsr_semester_x_course_y_edit", "/fsr/semester/1/course/5/edit", "evap"),
            ("test_fsr_semester_x_course_y_email", "/fsr/semester/1/course/1/email", "evap"),
            ("test_fsr_semester_x_course_y_preview", "/fsr/semester/1/course/1/preview", "evap"),
            ("test_fsr_semester_x_course_y_comments", "/fsr/semester/1/course/5/comments", "evap"),
            ("test_fsr_semester_x_course_y_review", "/fsr/semester/1/course/5/review", "evap"),
            ("test_fsr_semester_x_course_y_unpublish", "/fsr/semester/1/course/8/unpublish", "evap"),
            ("test_fsr_semester_x_course_y_delete", "/fsr/semester/1/course/1/delete", "evap"),
            # fsr questionnaires
            ("test_fsr_questionnaire", "/fsr/questionnaire/", "evap"),
            ("test_fsr_questionnaire_create", "/fsr/questionnaire/create", "evap"),
            ("test_fsr_questionnaire_x_edit", "/fsr/questionnaire/2/edit", "evap"),
            ("test_fsr_questionnaire_x", "/fsr/questionnaire/2", "evap"),
            ("test_fsr_questionnaire_x_copy", "/fsr/questionnaire/2/copy", "evap"),
            ("test_fsr_questionnaire_x_delete", "/fsr/questionnaire/3/delete", "evap"),
            ("test_fsr_questionnaire_delete", "/fsr/questionnaire/create", "evap"),
            # fsr user
            ("test_fsr_user", "/fsr/user/", "evap"),
            ("test_fsr_user_import", "/fsr/user/import", "evap"),
            ("test_fsr_sample_xls", "/static/sample_user.xls", "evap"),
            ("test_fsr_user_create", "/fsr/user/create", "evap"),
            ("test_fsr_user_x_delete", "/fsr/user/4/delete", "evap"),
            ("test_fsr_user_x_edit", "/fsr/user/4/edit", "evap"),
            # fsr template
            ("test_fsr_template_x", "/fsr/template/1", "evap"),
            # faq
            ("test_fsr_faq", "/fsr/faq/", "evap"),
            ("test_fsr_faq_x", "/fsr/faq/1", "evap"),
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
            ("test_fsr_semester_x_course_y_edit_fail", "/fsr/semester/1/course/8/edit", "evap"),
            ("test_fsr_semester_x_course_y_delete_fail", "/fsr/semester/1/course/8/delete", "evap"),
            ("test_fsr_semester_x_course_y_review_fail", "/fsr/semester/1/course/8/review", "evap"),
            ("test_fsr_semester_x_course_y_unpublish_fail", "/fsr/semester/1/course/7/unpublish", "evap"),
            ("test_fsr_questionnaire_x_edit_fail", "/fsr/questionnaire/4/edit", "evap"),
            ("test_fsr_user_x_delete_fail", "/fsr/user/2/delete", "evap"),
            ("test_fsr_semester_x_delete_fail", "/fsr/semester/1/delete", "evap"),
        ]

        for _, url, user in tests:
            self.get_assert_302(url, user)


    def test_failing_forms(self):
        """
            Tests whether forms that fail because of missing required fields
            when submitting them without entering any data actually do that.
        """
        forms = [
            ("/student/vote/5", "lazy.student", "Vote"),
            ("/fsr/semester/create", "evap", "Save"),
            ("/fsr/semester/1/course/create", "evap"),
            ("/fsr/semester/1/import", "evap"),
            ("/fsr/semester/1/course/1/email", "evap"),
            ("/fsr/questionnaire/create", "evap"),
            ("/fsr/user/create", "evap"),
        ]
        for form in forms:
            response = self.get_submit_assert_200(form[0], form[1])
            self.assertIn("is required", response)

    def test_failing_questionnaire_copy(self):
        """
            Tests whether copying and submitting a questionnaire form wihtout entering a new name fails.
        """
        response = self.get_submit_assert_200("/fsr/questionnaire/2/copy", "evap")
        self.assertIn("already exists", response)

    """
        The following tests test whether forms that succeed when
        submitting them without entering any data actually do that.
        They are in individual methods because most of them change the database.
    """

    def test_fsr_semester_x_edit__nodata_success(self):
        self.get_submit_assert_302("/fsr/semester/1/edit", "evap")

    def test_fsr_semester_x_delete__nodata_success(self):
        self.get_submit_assert_302("/fsr/semester/2/delete", "evap")

    def test_fsr_semester_x_assign__nodata_success(self):
        self.get_submit_assert_302("/fsr/semester/1/assign", "evap")

    def test_fsr_semester_x_lottery__nodata_success(self):
        self.get_submit_assert_200("/fsr/semester/1/lottery", "evap")

    def test_fsr_semester_x_reset__nodata_success(self):
        self.get_submit_assert_302("/fsr/semester/1/reset", "evap")

    def test_fsr_semester_x_contributorready__nodata_success(self):
        self.get_submit_assert_302("/fsr/semester/1/contributorready", "evap")

    def test_fsr_semester_x_approve__nodata_success(self):
        self.get_submit_assert_302("/fsr/semester/1/approve", "evap")

    def test_fsr_semester_x_publish__nodata_success(self):
        self.get_submit_assert_302("/fsr/semester/1/publish", "evap")

    def test_fsr_semester_x_course_y_edit__nodata_success(self):
        self.get_submit_assert_302("/fsr/semester/1/course/1/edit", "evap")

    def test_fsr_semester_x_course_y_review__nodata_success(self):
        self.get_submit_assert_302("/fsr/semester/1/course/5/review", "evap")

    def test_fsr_semester_x_course_y_unpublish__nodata_success(self):
        self.get_submit_assert_302("/fsr/semester/1/course/8/unpublish", "evap"),

    def test_fsr_semester_x_course_y_delete__nodata_success(self):
        self.get_submit_assert_302("/fsr/semester/1/course/1/delete", "evap"),

    def test_fsr_questionnaire_x_edit__nodata_success(self):
        self.get_submit_assert_302("/fsr/questionnaire/2/edit", "evap")

    def test_fsr_questionnaire_x_delete__nodata_success(self):
        self.get_submit_assert_302("/fsr/questionnaire/3/delete", "evap"),

    def test_fsr_user_x_delete__nodata_success(self):
        self.get_submit_assert_302("/fsr/user/4/delete", "evap"),

    def test_fsr_user_x_edit__nodata_success(self):
        self.get_submit_assert_302("/fsr/user/4/edit", "evap")

    def test_fsr_template_x__nodata_success(self):
        self.get_submit_assert_200("/fsr/template/1", "evap")

    def test_fsr_faq__nodata_success(self):
        self.get_submit_assert_302("/fsr/faq/", "evap")

    def test_fsr_faq_x__nodata_success(self):
        self.get_submit_assert_302("/fsr/faq/1", "evap")

    def test_contributor_profile(self):
        self.get_submit_assert_302("/contributor/profile", "responsible")

    def test_course_email_form(self):
        """
            Tests the CourseEmailForm with one valid and one invalid input dataset.
        """
        course = Course.objects.get(pk="1")
        data = {"body": "wat", "subject": "some subject", "sendToDueParticipants": True}
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
        userprofile = UserProfile.objects.get(pk=1)
        another_userprofile = UserProfile.objects.get(pk=2)
        data = {"username": "mklqoep50x2", "email": "a@b.ce"}
        form = UserForm(instance=userprofile, data=data)
        self.assertTrue(form.is_valid())

        data = {"username": another_userprofile.user.username, "email": "a@b.c"}
        form = UserForm(instance=userprofile, data=data)
        self.assertFalse(form.is_valid())

    def test_course_selection_form(self):
        """
            Tests the SelectCourseForm with one valid input dataset
            (one cannot make it invalid through the UI).
        """
        course1 = Course.objects.get(pk=1)
        course2 = Course.objects.get(pk=2)
        data = {"1": True, "2": False}
        form = SelectCourseForm(course1.degree, [course1, course2], None, data=data)
        self.assertTrue(form.is_valid())

    def test_review_text_answer_form(self):
        """
            Tests the ReviewTextAnswerForm with three valid input datasets
            (one cannot make it invalid through the UI).
        """
        textanswer = TextAnswer.objects.get(pk=1)
        data = dict(edited_answer=textanswer.original_answer, needs_further_review=False, hidden=False)
        self.assertTrue(ReviewTextAnswerForm(instance=textanswer, data=data).is_valid())
        data = dict(edited_answer="edited answer", needs_further_review=False, hidden=False)
        self.assertTrue(ReviewTextAnswerForm(instance=textanswer, data=data).is_valid())
        data = dict(edited_answer="edited answer", needs_further_review=True, hidden=True)
        self.assertTrue(ReviewTextAnswerForm(instance=textanswer, data=data).is_valid())

    def test_contributor_form_set(self):
        """
            Tests the ContributionFormset with various input data sets.
        """
        course = Course.objects.create(pk=9001, semester_id=1)

        ContributionFormset = inlineformset_factory(Course, Contribution, formset=ContributorFormSet, form=ContributionForm, extra=0, exclude=('course',))

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
        self.assertFalse(Semester.objects.get(pk=1).can_fsr_delete)
        self.client.login(username='evap', password='evap')
        response = self.client.get("/fsr/semester/1/delete", follow=True)
        self.assertIn("cannot be deleted", list(response.context['messages'])[0].message)
        self.assertTrue(Semester.objects.filter(pk=1).exists())

        self.assertTrue(Semester.objects.get(pk=2).can_fsr_delete)
        self.get_submit_assert_302("/fsr/semester/2/delete", "evap")
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
        self.helper_semester_state_views("/fsr/semester/1/publish", [7], ["reviewed"], "published")

    def test_semester_reset(self):
        self.helper_semester_state_views("/fsr/semester/1/reset", [2], ["prepared"], "new")

    def test_semester_approve(self):
        self.helper_semester_state_views("/fsr/semester/1/approve", [1,2,3], ["new", "prepared", "lecturerApproved"], "approved")

    def test_semester_contributor_ready(self):
        self.helper_semester_state_views("/fsr/semester/1/contributorready", [1,3], ["new", "lecturerApproved"], "prepared")

    def test_course_create(self):
        """
            Tests the course creation view with one valid and one invalid input dataset.
        """
        data = dict(name_de="asdf", name_en="asdf", kind="asdf", degree="asd",
                    vote_start_date="02/1/2014", vote_end_date="02/1/2099", general_questions=["2"])
        response = self.get_assert_200("/fsr/semester/1/course/create", "evap")
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
        self.get_assert_302("/fsr/semester/1/course/4/review", user="evap")
        self.assertEqual(Course.objects.get(pk=6).state, "evaluated")

        page = self.get_assert_200("/fsr/semester/1/course/6/review", user="evap")

        form = lastform(page)
        form["form-0-hidden"] = "on"
        form["form-1-needs_further_review"] = "on"
        # Actually this is not guaranteed, but i'll just guarantee it now for this test.
        self.assertEqual(form["form-0-id"].value, "5")
        self.assertEqual(form["form-1-id"].value, "8")
        page = form.submit(name="operation", value="save_and_next").follow()

        form = lastform(page)
        form["form-0-reviewed_answer"] = "mflkd862xmnbo5"
        page = form.submit()

        self.assertEqual(TextAnswer.objects.get(pk=5).hidden, True)
        self.assertEqual(TextAnswer.objects.get(pk=5).reviewed_answer, "")
        self.assertEqual(TextAnswer.objects.get(pk=8).reviewed_answer, "mflkd862xmnbo5")
        self.assertEqual(Course.objects.get(pk=6).state, "reviewed")

        self.get_assert_302("/fsr/semester/1/course/6/review", user="evap")

    def test_course_email(self):
        """
            Tests whether the course email view actually sends emails.
        """
        page = self.get_assert_200("/fsr/semester/1/course/5/email", user="evap")
        form = lastform(page)
        form["subject"] = "asdf"
        form["body"] = "asdf"
        form.submit()

        self.assertEqual(len(mail.outbox), 1)

    def test_questionnaire_deletion(self):
        """
            Tries to delete two questionnaires via the respective view,
            only the second attempt should succeed.
        """
        self.assertFalse(Questionnaire.objects.get(pk=2).can_fsr_delete)
        self.client.login(username='evap', password='evap')
        page = self.client.get("/fsr/questionnaire/2/delete", follow=True)
        self.assertIn("cannot be deleted", list(page.context['messages'])[0].message)
        self.assertTrue(Questionnaire.objects.filter(pk=2).exists())

        self.assertTrue(Questionnaire.objects.get(pk=3).can_fsr_delete)
        self.get_submit_assert_302("/fsr/questionnaire/3/delete", "evap")
        self.assertFalse(Questionnaire.objects.filter(pk=3).exists())

    def test_create_user(self):
        """
            Tests whether the user creation view actually creates a user.
        """
        page = self.get_assert_200("/fsr/user/create", "evap")
        form = lastform(page)
        form["username"] = "mflkd862xmnbo5"
        form["first_name"] = "asd"
        form["last_name"] = "asd"
        form["email"] = "a@b.de"

        form.submit()

        self.assertEqual(User.objects.order_by("pk").last().username, "mflkd862xmnbo5")

    def test_emailtemplate(self):
        """
            Tests the emailtemplate view with one valid and one invalid input datasets.
        """
        page = self.get_assert_200("/fsr/template/1", "evap")
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

    def test_delete_redemption_events(self):
        """
            Submits a request that tries to delete an event where users already redeemed points -> should not work.
            Secondly it issues a GET Request and asserts that the page for deleting events is returned.
            Last it submits a request that should delete the event.
        """
        # try to delete event that can not be deleted, because people already redeemed points
        response = self.app.post(reverse("evap.rewards.views.reward_point_redemption_event_delete", args=[1]), user="evap")
        self.assertRedirects(response, reverse('evap.rewards.views.reward_point_redemption_events'))
        response = response.follow()
        self.assertContains(response, "cannot be deleted")
        self.assertTrue(RewardPointRedemptionEvent.objects.filter(pk=2).exists())

        # make sure that a GET Request does not delete an event
        response = self.app.get(reverse("evap.rewards.views.reward_point_redemption_event_delete", args=[2]), user="evap")
        self.assertTemplateUsed(response, "rewards_reward_point_redemption_event_delete.html")
        self.assertTrue(RewardPointRedemptionEvent.objects.filter(pk=2).exists())

        # now delete for real
        response = self.app.post(reverse("evap.rewards.views.reward_point_redemption_event_delete", args=[2]), user="evap")
        self.assertRedirects(response, reverse('evap.rewards.views.reward_point_redemption_events'))
        self.assertFalse(RewardPointRedemptionEvent.objects.filter(pk=2).exists())

    def test_redeem_reward_points(self):
        """
            Submits a request that redeems all available reward points and checks that this works.
            Also checks that it is not possible to redeem more points than the user actually has.
        """
        response = self.app.get(reverse("evap.rewards.views.index"), user="student")
        self.assertEqual(response.status_code, 200)

        user_profile = UserProfile.objects.get(pk=5)
        form = lastform(response)
        form.set("points-1", reward_points_of_user(user_profile))
        response = form.submit()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "You successfully redeemed your points.")
        self.assertEqual(0, reward_points_of_user(user_profile))

        form.set("points-1", 1)
        form.set("points-2", 3)
        response = form.submit()
        self.assertIn("have enough reward points.", response.body)

    def test_create_redemption_event(self):
        """
            submits a newly created redemption event and checks that the event has been created
        """
        response = self.app.get(reverse("evap.rewards.views.reward_point_redemption_event_create"), user="evap")

        form = lastform(response)
        form.set('name', 'Test3Event')
        form.set('date', '2014-12-10')
        form.set('redeem_end_date', '2014-11-20')

        response = form.submit()
        self.assertRedirects(response, reverse('evap.rewards.views.reward_point_redemption_events'))
        self.assertEqual(RewardPointRedemptionEvent.objects.count(), 3)

    def test_edit_redemption_event(self):
        """
            submits a changed redemption event and tests whether it actually has changed
        """
        response = self.app.get(reverse("evap.rewards.views.reward_point_redemption_event_edit", args=[2]), user="evap")

        form = lastform(response)
        name = form.get('name').value
        form.set('name', 'new name')

        response = form.submit()
        self.assertRedirects(response, reverse('evap.rewards.views.reward_point_redemption_events'))
        self.assertNotEqual(RewardPointRedemptionEvent.objects.get(pk=2).name, name)

    def test_grant_reward_points(self):
        """
            submits several requests that trigger the reward point granting and checks that the reward point
            granting works as expected for the different requests.
        """
        user_profile = UserProfile.objects.get(pk=5)
        reward_points_before_end = reward_points_of_user(user_profile)
        response = self.app.get(reverse("evap.student.views.vote", args=[9]), user="student")

        form = lastform(response)
        for key, value in form.fields.iteritems():
            if key is not None and "question" in key:
                form.set(key, 6)

        response = form.submit()
        self.assertRedirects(response, reverse('evap.student.views.index'))

        # semester is not activated --> number of reward points should not increase
        self.assertEqual(reward_points_before_end, reward_points_of_user(user_profile))

        # reset course for another try
        course = Course.objects.get(pk=9)
        course.voters = []
        # activate semester
        activation = SemesterActivation.objects.get(semester=course.semester)
        activation.is_active = True
        activation.save()
        # create a new course
        new_course = Course(semester=course.semester, name_de="bhabda", name_en="dsdsfds")
        new_course.save()
        new_course.participants.add(user_profile.user)
        new_course.save()
        response = form.submit()
        self.assertRedirects(response, reverse('evap.student.views.index'))

        # user also has other courses this semester --> number of reward points should not increase
        self.assertEqual(reward_points_before_end, reward_points_of_user(user_profile))

        course.voters = []
        course.save()
        new_course.participants.remove(user_profile.user)
        new_course.save()

        # last course of user so he may get reward points
        response = form.submit()
        self.assertRedirects(response, reverse('evap.student.views.index'))
        self.assertEqual(reward_points_before_end + settings.REWARD_POINTS_PER_SEMESTER, reward_points_of_user(user_profile))

        # test behaviour if user already got reward points
        course.voters = []
        course.save()
        response = form.submit()
        self.assertRedirects(response, reverse('evap.student.views.index'))
        self.assertEqual(reward_points_before_end + settings.REWARD_POINTS_PER_SEMESTER, reward_points_of_user(user_profile))
