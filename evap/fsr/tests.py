from django.core.urlresolvers import reverse
from django_webtest import WebTest
from django.test import Client
from django.forms.models import inlineformset_factory

from django.contrib.auth.models import User
from evap.evaluation.models import Semester, Questionnaire, UserProfile, Course, Contribution, TextAnswer
from evap.fsr.forms import CourseEmailForm, UserForm, SelectCourseForm, ReviewTextAnswerForm, ContributorFormSet, ContributionForm

import os.path


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

        self.assertEqual(semester.course_set.count(), 23, "Wrong number of courses after Excel import.")
        self.assertEqual(User.objects.count(), original_user_count + 24, "Wrong number of users after Excel import.")

        check_course = Course.objects.get(name_en="Shake")
        check_contributions = Contribution.objects.filter(course=check_course)
        responsible_count = 0
        for contribution in check_contributions:
            if contribution.responsible:
                responsible_count += 1
        self.assertEqual(responsible_count, 1, "Wrong number of responsible contributors after Excel import.")

        check_student = User.objects.get(username="diam.synephebos")
        self.assertEqual(check_student.first_name, "Diam")
        self.assertEqual(check_student.email, "diam.synephebos@student.hpi.uni-potsdam.de")

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
    extra_environ = {'HTTP_ACCEPT_LANGUAGE': 'en'}

    def get_assert_200(self, url, user):
        response = self.app.get(url, user=user)
        self.assertEqual(response.status_code, 200, 'url "{}" failed with user "{}"'.format(url, user))
        return response

    def get_assert_302(self, url, user):
        response = self.app.get(url, user=user)
        self.assertEqual(response.status_code, 302, 'url "{}" failed with user "{}"'.format(url, user))
        return response

    def get_submit_assert_302(self, url, user):
        response = self.get_assert_200(url, user)
        response = response.forms[2].submit("")
        self.assertEqual(response.status_code, 302, 'url "{}" failed with user "{}"'.format(url, user))

    def get_submit_assert_200(self, url, user):
        response = self.get_assert_200(url, user)
        response = response.forms[2].submit("")
        self.assertEqual(response.status_code, 200, 'url "{}" failed with user "{}"'.format(url, user))

    def test_all_urls(self):
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
            ("test_results_semester_x_export", "/results/semester/1/export", "evap"),
            # contributor
            ("test_contributor", "/contributor/", "responsible"),
            ("test_contributor_course_x", "/contributor/course/7", "responsible"),
            ("test_contributor_course_x_preview", "/contributor/course/7/preview", "responsible"),
            ("test_contributor_course_x_edit", "/contributor/course/2/edit", "responsible"),
            ("test_contributor_profile", "/contributor/profile", "responsible")]
        for _, url, user in tests:
            self.get_assert_200(url, user)

    def test_redirecting_urls(self):
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


    # tests of forms that fail without entering any data
    def test_failing_forms(self):
        forms = [
            ("/student/vote/5", "lazy.student", "Vote"),
            ("/fsr/semester/create", "evap", "Save"),
            ("/fsr/semester/1/course/create", "evap"),
            ("/fsr/semester/1/import", "evap"),
            ("/fsr/semester/1/course/1/email", "evap"),
            ("/fsr/questionnaire/2/copy", "evap"),
            ("/fsr/questionnaire/create", "evap"),
            ("/fsr/user/create", "evap"),
        ]
        for form in forms:
            self.get_submit_assert_200(form[0], form[1])


    # tests of forms that succeed without entering any data
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
        self.get_submit_assert_302("/fsr/semester/1/course/8/unpublish", "evap"), # TODO: button should be lower

    def test_fsr_semester_x_course_y_delete__nodata_success(self):
        self.get_submit_assert_302("/fsr/semester/1/course/1/delete", "evap"),

    def test_fsr_questionnaire_x_edit__nodata_success(self):
        self.get_submit_assert_302("/fsr/questionnaire/2/edit", "evap")

    def test_fsr_questionnaire_x_delete__nodata_success(self):
        self.get_submit_assert_302("/fsr/questionnaire/3/delete", "evap"),

    def test_fsr_user_x_delete__nodata_success(self):
        self.get_submit_assert_302("/fsr/user/4/delete", "evap"), # may fail

    def test_fsr_user_x_edit__nodata_success(self):
        self.get_submit_assert_302("/fsr/user/4/edit", "evap")

    def test_fsr_template_x__nodata_success(self):
        self.get_submit_assert_200("/fsr/template/1", "evap")

    def test_fsr_faq__nodata_success(self):
        self.get_submit_assert_302("/fsr/faq/", "evap")

    def test_fsr_faq_x__nodata_success(self):
        self.get_submit_assert_302("/fsr/faq/1", "evap")

    # disabled, crashes for unknown reasons
    #def test_contributor_course_x_edit(self):
    #    self.get_submit_assert_302("/contributor/course/2/edit", "responsible"),

    def test_contributor_profile(self):
        self.get_submit_assert_302("/contributor/profile", "responsible")

    def test_course_email_form(self):
        course = Course.objects.first()
        data = {"body": "wat", "subject": "some subject", "sendToDueParticipants": True}
        form = CourseEmailForm(instance=course, data=data)
        self.assertTrue(form.is_valid())
        form.all_recepients_reachable()
        form.send()

        data = {"body": "wat", "subject": "some subject"}
        form = CourseEmailForm(instance=course, data=data)
        self.assertFalse(form.is_valid())

    def test_user_form(self):
        userprofile = UserProfile.objects.get(pk=1)
        another_userprofile = UserProfile.objects.get(pk=2)
        data = {"username": "mklqoep50x2", "email": "a@b.ce"}
        form = UserForm(instance=userprofile, data=data)
        self.assertTrue(form.is_valid())


        data = {"username": another_userprofile.user.username, "email": "a@b.c"}
        form = UserForm(instance=userprofile, data=data)
        self.assertFalse(form.is_valid())

    def test_course_selection_form(self):
        course1 = Course.objects.get(pk=1)
        course2 = Course.objects.get(pk=2)
        data = {"1": True, "2": False}
        form = SelectCourseForm(course1.degree, [course1, course2], None, data=data)
        self.assertTrue(form.is_valid())

    def test_review_text_answer_form(self):
        textanswer = TextAnswer.objects.get(pk=1)
        data = dict(edited_answer=textanswer.original_answer, needs_further_review=False, hidden=False)
        self.assertTrue(ReviewTextAnswerForm(instance=textanswer, data=data).is_valid())
        data = dict(edited_answer="edited answer", needs_further_review=False, hidden=False)
        self.assertTrue(ReviewTextAnswerForm(instance=textanswer, data=data).is_valid())
        data = dict(edited_answer="edited answer", needs_further_review=True, hidden=True)
        self.assertTrue(ReviewTextAnswerForm(instance=textanswer, data=data).is_valid())

    def test_contributor_form_set(self):
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
        self.assertFalse(Semester.objects.get(pk=1).can_fsr_delete)
        self.client.login(username='evap', password='evap')
        response = self.client.get("/fsr/semester/1/delete", follow=True)
        self.assertTrue("cannot be deleted" in list(response.context['messages'])[0].message)
        self.assertTrue(Semester.objects.filter(pk=1).exists())

        self.assertTrue(Semester.objects.get(pk=2).can_fsr_delete)
        self.get_submit_assert_302("/fsr/semester/2/delete", "evap")
        self.assertFalse(Semester.objects.filter(pk=2).exists())

    def test_semester_publish(self):
        page = self.app.get("/fsr/semester/1/publish", user="evap")
        form = lastform(page)
        form["7"] = "on"
        response = form.submit()
        self.assertTrue("Successfully" in str(response))

    def helper_semester_state_views(self, url, course_ids, old_states, new_state):
        page = self.app.get(url, user="evap")
        form = lastform(page)
        for course_id in course_ids:
            self.assertTrue(Course.objects.get(pk=course_id).state in old_states)
            form[str(course_id)] = "on"
        response = form.submit()
        # TODO: form contains no other options. turn course_ids into a list?
        self.assertTrue("Successfully" in str(response))
        for course_id in course_ids:
            self.assertTrue(Course.objects.get(pk=course_id).state == new_state)

    def test_semester_reset(self):
        self.helper_semester_state_views("/fsr/semester/1/reset", [2], ["prepared"], "new")

    def test_semester_approve(self):
        self.helper_semester_state_views("/fsr/semester/1/approve", [1,2,3], ["new", "prepared", "lecturerApproved"], "approved")

    def test_semester_contributor_ready(self):
        self.helper_semester_state_views("/fsr/semester/1/contributorready", [1,3], ["new", "lecturerApproved"], "prepared")