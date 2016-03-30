from django.test.utils import override_settings
from django.forms.models import inlineformset_factory
from django.core import mail

from evap.evaluation.models import Semester, Questionnaire, UserProfile, Course, \
                            EmailTemplate, Degree, CourseType, Contribution
from evap.evaluation.tests.test_utils import WebTest, lastform
from evap.staff.forms import ContributionFormSet, ContributionForm

from model_mommy import mommy



"""
These tests were created to get a higher test coverage. Some actually contain functional
tests and should be moved to their appropriate place, others don't really test anything
and should be replaced by better tests. Eventually, this file is to be removed.
"""


@override_settings(INSTITUTION_EMAIL_DOMAINS=["example.com"])
class URLTests(WebTest):
    fixtures = ['minimal_test_data']
    csrf_checks = False

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
            ("test_staff_rewards_index", "/rewards/", "student"),
            ("test_staff_reward_points_redemption_events", "/rewards/reward_point_redemption_events/", "evap"),
            ("test_staff_reward_points_redemption_event_create", "/rewards/reward_point_redemption_event/create", "evap"),
            ("test_staff_reward_points_redemption_event_edit", "/rewards/reward_point_redemption_event/1/edit", "evap"),
            ("test_staff_reward_points_redemption_event_export", "/rewards/reward_point_redemption_event/1/export", "evap"),
            ("test_staff_reward_points_semester_activation", "/rewards/reward_semester_activation/1/on", "evap"),
            ("test_staff_reward_points_semester_deactivation", "/rewards/reward_semester_activation/1/off", "evap"),
            ("test_staff_reward_points_semester_overview", "/rewards/semester/1/reward_points", "evap"),
            # degrees
            ("test_staff_degree_index", "/staff/degrees/", "evap"),
            # course types
            ("test_staff_course_type_index", "/staff/course_types/", "evap"),
            ("test_staff_course_type_merge", "/staff/course_types/merge", "evap"),
            ("test_staff_course_type_x_merge_x", "/staff/course_types/2/merge/3", "evap"),
        ]
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
            ("/staff/course_types/merge", "evap"),
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
        form["vote_end_date"] = "02/1/2014"  # wrong order to get the validation error
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
        form["vote_end_date"] = "02/1/2099"  # now do it right

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
        form.submit()

        self.assertEqual(EmailTemplate.objects.get(pk=1).body, "body: mflkd862xmnbo5")

        form["body"] = " invalid tag: {{}}"
        form.submit()
        self.assertEqual(EmailTemplate.objects.get(pk=1).body, "body: mflkd862xmnbo5")

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
        form["question_20_1_2"] = 1  # give missing answer
        form.submit()

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

    def test_course_type_merge(self):
        """
            Tests that the merging of course types works as expected.
        """
        main_type = CourseType.objects.get(name_en="Master project")
        other_type = CourseType.objects.get(name_en="Obsolete course type")
        num_courses_with_main_type = Course.objects.filter(type=main_type).count()
        courses_with_other_type = Course.objects.filter(type=other_type)
        self.assertGreater(courses_with_other_type.count(), 0)

        page = self.get_assert_200("/staff/course_types/" + str(main_type.pk) + "/merge/" + str(other_type.pk), user="evap")
        form = lastform(page)
        response = form.submit()
        self.assertIn("Successfully", str(response))

        self.assertFalse(CourseType.objects.filter(name_en="Obsolete course type").exists())
        self.assertEqual(Course.objects.filter(type=main_type).count(), num_courses_with_main_type + 1)
        for course in courses_with_other_type:
            self.assertTrue(course.type == main_type)
