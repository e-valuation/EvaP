from django.core.urlresolvers import reverse
from django_webtest import WebTest
import webtest

from django.contrib.auth.models import User
from evap.evaluation.models import Semester, Questionnaire

import os.path


class UsecaseTests(WebTest):
    fixtures = ['usecase-tests']
    
    extra_environ = {'HTTP_ACCEPT_LANGUAGE': 'en'}
    
    def test_import(self):
        page = self.app.get(reverse("fsr_root"), user="fsr.user")
        
        # create a new semester
        page = page.click("[Ss]emesters")
        page = page.click("[Nn]ew [Ss]emester")
        semester_form = page.forms[0]
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
        upload_form = page.forms[0]
        upload_form['vote_start_date'] = "02/29/2000"
        upload_form['vote_end_date'] = "02/29/2012"
        upload_form['excel_file'] = (os.path.join(os.path.dirname(__file__), "fixtures", "samples.xls"),)
        page = upload_form.submit().follow()
        
        self.assertEqual(semester.course_set.count(), 23, "Wrong number of courses after Excel import.")
        self.assertEqual(User.objects.count(), original_user_count + 24, "Wrong number of users after Excel import.")
        
        check_student = User.objects.get(username="Diam.Synephebos")
        self.assertEqual(check_student.first_name, "Diam")
        self.assertEqual(check_student.email, "Diam.Synephebos@student.hpi.uni-potsdam.de")
        
        check_lecturer = User.objects.get(username="Sanctus.Aliquyam")
        self.assertEqual(check_lecturer.first_name, "Sanctus")
        self.assertEqual(check_lecturer.last_name, "Aliquyam")
        self.assertEqual(check_lecturer.email, "567@web.de")
        
    def test_logon_key(self):
        with self.assertRaises(webtest.app.AppError):
            self.app.get(reverse("evap.results.views.index"))
        
        user = User.objects.all()[0]
        userprofile = user.get_profile()
        userprofile.generate_logon_key()
        userprofile.save()
        
        url_with_key = reverse("evap.results.views.index") + "?userkey=%s" % userprofile.logon_key
        self.app.get(url_with_key)
    
    def test_create_questionnaire(self):
        page = self.app.get(reverse("fsr_root"), user="fsr.user")
        
        # create a new questionnaire
        page = page.click("[Qq]uestionnaires")
        page = page.click("[Nn]ew [Qq]uestionnaire")
        questionnaire_form = page.forms[0]
        questionnaire_form['name_de'] = "Test Fragebogen"
        questionnaire_form['name_en'] = "test questionnaire"
        questionnaire_form['question_set-0-text_de'] = "Frage 1"
        questionnaire_form['question_set-0-text_en'] = "Question 1"
        questionnaire_form['question_set-0-kind'] = "T"
        page = questionnaire_form.submit().follow()
        
        # retrieve new questionnaire
        questionnaire = Questionnaire.objects.get(name_de="Test Fragebogen", name_en="test questionnaire")
        self.assertEqual(questionnaire.question_set.count(), 1, "New questionnaire is empty.")
    
    def test_create_empty_questionnaire(self):
        page = self.app.get(reverse("fsr_root"), user="fsr.user")
        
        # create a new questionnaire
        page = page.click("[Qq]uestionnaires")
        page = page.click("[Nn]ew [Qq]uestionnaire")
        questionnaire_form = page.forms[0]
        questionnaire_form['name_de'] = "Test Fragebogen"
        questionnaire_form['name_en'] = "test questionnaire"
        page = questionnaire_form.submit()
        
        assert "You must have at least one of these" in page
        
        # retrieve new questionnaire
        with self.assertRaises(Questionnaire.DoesNotExist):
            Questionnaire.objects.get(name_de="Test Fragebogen", name_en="test questionnaire")
    
    def test_copy_questionnaire(self):
        page = self.app.get(reverse("fsr_root"), user="fsr.user")
        
        # create a new questionnaire
        page = page.click("[Qq]uestionnaires")
        page = page.click("Copy")
        questionnaire_form = page.forms[0]
        questionnaire_form['name_de'] = "Test Fragebogen (kopiert)"
        questionnaire_form['name_en'] = "test questionnaire (copied)"
        page = questionnaire_form.submit().follow()
        
        # retrieve new questionnaire
        questionnaire = Questionnaire.objects.get(name_de="Test Fragebogen (kopiert)", name_en="test questionnaire (copied)")
        self.assertEqual(questionnaire.question_set.count(), 2, "New questionnaire is empty.")
    
    def test_assign_questionnaires(self):
        page = self.app.get(reverse("fsr_root"), user="fsr.user")
        
        # assign questionnaire to courses
        page = page.click("[Ss]emester 1 \(en\)", index=0)
        page = page.click("Assign questionnaires")
        assign_form = page.forms[0]
        assign_form['Seminar'] = [1]
        assign_form['Vorlesung'] = [1]
        page = assign_form.submit().follow()
        
        # get semester and check
        semester = Semester.objects.get(pk=1)
        questionnaire = Questionnaire.objects.get(pk=1)
        for course in semester.course_set.all():
            self.assertEqual(course.general_assignment.questionnaires.count(), 1)
            self.assertEqual(course.general_assignment.questionnaires.get(), questionnaire)
