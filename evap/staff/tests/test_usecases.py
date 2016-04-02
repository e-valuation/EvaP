import os.path

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.urlresolvers import reverse

from model_mommy import mommy

from evap.evaluation.models import Semester, Questionnaire, Question, UserProfile, Course, \
                            CourseType, Contribution
from evap.evaluation.tests.test_utils import WebTest, lastform


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
        upload_form['excel_file'] = (os.path.join(settings.BASE_DIR, "staff/fixtures/test_enrolment_data.xls"),)
        upload_form.submit(name="operation", value="import").follow()

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

        url_with_key = reverse("results:index") + "?loginkey=%s" % user.login_key
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
        questionnaire_form.submit().follow()

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
