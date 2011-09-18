from django.core.urlresolvers import reverse
from django.test import TestCase
from django_webtest import WebTest

from django.contrib.auth.models import User
from evaluation.models import Semester, Questionnaire

import os.path

class SimpleViewTestsTest(TestCase):
    fixtures = ['simple-tests']
    
    def test_semester_views(self):
        semester = Semester.objects.all()[0]
        course = semester.course_set.all()[0]
        
        self.client.get('/fsr/')
        self.client.get('/fsr/semester')
        self.client.get('/fsr/semester/create')
        self.client.get('/fsr/semester/%d' % semester.id)
        self.client.get('/fsr/semester/%d/edit' % semester.id)
        self.client.get('/fsr/semester/%d/import' % semester.id)
        self.client.get('/fsr/semester/%d/assign' % semester.id)
        self.client.get('/fsr/semester/%d/course/create' % semester.id)
        self.client.get('/fsr/semester/%d/course/%d/edit' % (semester.id, course.id))
        self.client.get('/fsr/semester/%d/course/%d/delete' % (semester.id, course.id))
        self.client.get('/fsr/semester/%d/course/%d/censor' % (semester.id, course.id))
        self.client.get('/fsr/semester/%d/course/%d/publish'% (semester.id, course.id))
    
    def test_questionnaire_views(self):
        questionnaire = Questionnaire.objects.all()[0]
        
        self.client.get('/fsr/questionnaire')
        self.client.get('/fsr/questionnaire/create')
        self.client.get('/fsr/questionnaire/%d' % questionnaire.id)
        self.client.get('/fsr/questionnaire/%d/edit' % questionnaire.id)
        self.client.get('/fsr/questionnaire/%d/copy' % questionnaire.id)
        self.client.get('/fsr/questionnaire/%d/delete' % questionnaire.id)


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
        
        # import excel file
        p = p.click("[Ii]mport")
        upload_form = p.forms[0]
        upload_form['vote_start_date'] = "02/29/2000"
        upload_form['vote_end_date'] = "02/29/2012"
        upload_form['excel_file'] = (os.path.join(os.path.dirname(__file__), "fixtures", "samples.xls"),)
        p = upload_form.submit().follow()
        
        self.assertEqual(semester.course_set.count(), 23, "Wrong number of courses after Excel import.")
        self.assertEqual(User.objects.count(), 25, "Wrong number of users after Excel import.")
