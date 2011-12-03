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
        p = self.app.get(reverse("fsr_root"), user="fsr.user")
        
        # create a new semester
        p = p.click("[Ss]emesters")
        p = p.click("[Nn]ew [Ss]emester")
        semester_form = p.forms[0]
        semester_form['name_de'] = "Testsemester"
        semester_form['name_en'] = "test semester"
        p = semester_form.submit().follow()
        
        # retrieve new semester
        semester = Semester.objects.get(name_de="Testsemester",
                                        name_en="test semester")
        
        self.assertEqual(semester.course_set.count(), 0, "New semester is not empty.")
        
        # safe original user count
        original_user_count = User.objects.all().count()
        
        # import excel file
        p = p.click("[Ii]mport")
        upload_form = p.forms[0]
        upload_form['vote_start_date'] = "02/29/2000"
        upload_form['vote_end_date'] = "02/29/2012"
        upload_form['excel_file'] = (os.path.join(os.path.dirname(__file__), "fixtures", "samples.xls"),)
        p = upload_form.submit().follow()
        
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
        p = self.app.get(reverse("fsr_root"), user="fsr.user")
        
        # create a new questionnaire
        p = p.click("[Qq]uestionnaires")
        p = p.click("[Nn]ew [Qq]uestionnaire")
        questionnaire_form = p.forms[0]
        questionnaire_form['name_de'] = "Test Fragebogen"
        questionnaire_form['name_en'] = "test questionnaire"
        questionnaire_form['question_set-0-text_de'] = "Frage 1"
        questionnaire_form['question_set-0-text_en'] = "Question 1"
        questionnaire_form['question_set-0-kind'] = "T"
        p = questionnaire_form.submit().follow()
        
        # retrieve new questionnaire
        q = Questionnaire.objects.get(name_de="Test Fragebogen", name_en="test questionnaire")
        self.assertEqual(q.question_set.count(), 1, "New questionnaire is empty.")
    
    def test_create_empty_questionnaire(self):
        p = self.app.get(reverse("fsr_root"), user="fsr.user")
        
        # create a new questionnaire
        p = p.click("[Qq]uestionnaires")
        p = p.click("[Nn]ew [Qq]uestionnaire")
        questionnaire_form = p.forms[0]
        questionnaire_form['name_de'] = "Test Fragebogen"
        questionnaire_form['name_en'] = "test questionnaire"
        p = questionnaire_form.submit()
        
        assert "You must have at least one of these" in p
        
        # retrieve new questionnaire
        with self.assertRaises(Questionnaire.DoesNotExist):
            Questionnaire.objects.get(name_de="Test Fragebogen", name_en="test questionnaire")
    
    def test_copy_questionnaire(self):
        p = self.app.get(reverse("fsr_root"), user="fsr.user")
        
        # create a new questionnaire
        p = p.click("[Qq]uestionnaires")
        p = p.click("Copy")
        questionnaire_form = p.forms[0]
        questionnaire_form['name_de'] = "Test Fragebogen (kopiert)"
        questionnaire_form['name_en'] = "test questionnaire (copied)"
        p = questionnaire_form.submit().follow()
        
        # retrieve new questionnaire
        q = Questionnaire.objects.get(name_de="Test Fragebogen (kopiert)", name_en="test questionnaire (copied)")
        self.assertEqual(q.question_set.count(), 2, "New questionnaire is empty.")
    
    def test_assign_questionnaires(self):
        p = self.app.get(reverse("fsr_root"), user="fsr.user")
        
        # assign questionnaire to courses
        p = p.click("[Ss]emester 1 \(en\)", index=0)
        p = p.click("Assign questionnaires")
        assign_form = p.forms[0]
        assign_form['Seminar'] = [1]
        assign_form['Vorlesung'] = [1]
        p = assign_form.submit().follow()
        
        # get semester and check
        semester = Semester.objects.get(pk=1)
        questionnaire = Questionnaire.objects.get(pk=1)
        for course in semester.course_set.all():
            self.assertEqual(course.general_assignment.questionnaires.count(), 1)
            self.assertEqual(course.general_assignment.questionnaires.get(), questionnaire)
