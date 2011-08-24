from django.test import TestCase

from evaluation.models import Semester, QuestionGroup

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
    
    def test_questiongroup_views(self):
        questiongroup = QuestionGroup.objects.all()[0]
        
        self.client.get('/fsr/questiongroup')
        self.client.get('/fsr/questiongroup/create')
        self.client.get('/fsr/questiongroup/%d' % questiongroup.id)
        self.client.get('/fsr/questiongroup/%d/edit' % questiongroup.id)
        self.client.get('/fsr/questiongroup/%d/copy' % questiongroup.id)
        self.client.get('/fsr/questiongroup/%d/delete' % questiongroup.id)
