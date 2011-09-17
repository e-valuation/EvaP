from django.test import TestCase

from evaluation.models import Semester, Questionnaire

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
