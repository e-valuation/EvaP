from django_webtest import WebTest
from django.test import TestCase

from evap.evaluation.models import Semester
from evap.results.exporters import ExcelExporter

class UsecaseTests(WebTest):
    fixtures = ['minimal_test_data_results']

    def test_textanswer_visibility_for_responsible(self):
        page = self.app.get("/results/semester/1/course/1", user='responsible')
        self.assertIn(".course_orig_published.", page)
        self.assertNotIn(".course_orig_hidden.", page)
        self.assertNotIn(".course_orig_published_changed.", page)
        self.assertIn(".course_changed_published.", page)
        self.assertIn(".responsible_orig_published.", page)
        self.assertNotIn(".responsible_orig_hidden.", page)
        self.assertNotIn(".responsible_orig_published_changed.", page)
        self.assertIn(".responsible_changed_published.", page)
        self.assertIn(".responsible_orig_private.", page)
        self.assertNotIn(".responsible_orig_notreviewed.", page)
        self.assertIn(".contributor_orig_published.", page)
        self.assertNotIn(".contributor_orig_private.", page) # private comment not visible

    def test_textanswer_visibility_for_delegate_for_responsible(self):
        page = self.app.get("/results/semester/1/course/1", user='delegate_for_responsible')
        self.assertIn(".course_orig_published.", page)
        self.assertNotIn(".course_orig_hidden.", page)
        self.assertNotIn(".course_orig_published_changed.", page)
        self.assertIn(".course_changed_published.", page)
        self.assertIn(".responsible_orig_published.", page)
        self.assertNotIn(".responsible_orig_hidden.", page)
        self.assertNotIn(".responsible_orig_published_changed.", page)
        self.assertIn(".responsible_changed_published.", page)
        self.assertNotIn(".responsible_orig_private.", page) # private comment not visible
        self.assertNotIn(".responsible_orig_notreviewed.", page)
        self.assertIn(".contributor_orig_published.", page)
        self.assertNotIn(".contributor_orig_private.", page) # private comment not visible

    def test_textanswer_visibility_for_contributor(self):
        page = self.app.get("/results/semester/1/course/1", user='contributor')
        self.assertNotIn(".course_orig_published.", page)
        self.assertNotIn(".course_orig_hidden.", page)
        self.assertNotIn(".course_orig_published_changed.", page)
        self.assertNotIn(".course_changed_published.", page)
        self.assertNotIn(".responsible_orig_published.", page)
        self.assertNotIn(".responsible_orig_hidden.", page)
        self.assertNotIn(".responsible_orig_published_changed.", page)
        self.assertNotIn(".responsible_changed_published.", page)
        self.assertNotIn(".responsible_orig_private.", page)
        self.assertNotIn(".responsible_orig_notreviewed.", page)
        self.assertIn(".contributor_orig_published.", page)
        self.assertIn(".contributor_orig_private.", page)

    def test_textanswer_visibility_for_delegate_for_contributor(self):
        page = self.app.get("/results/semester/1/course/1", user='delegate_for_contributor')
        self.assertNotIn(".course_orig_published.", page)
        self.assertNotIn(".course_orig_hidden.", page)
        self.assertNotIn(".course_orig_published_changed.", page)
        self.assertNotIn(".course_changed_published.", page)
        self.assertNotIn(".responsible_orig_published.", page)
        self.assertNotIn(".responsible_orig_hidden.", page)
        self.assertNotIn(".responsible_orig_published_changed.", page)
        self.assertNotIn(".responsible_changed_published.", page)
        self.assertNotIn(".responsible_orig_private.", page)
        self.assertNotIn(".responsible_orig_notreviewed.", page)
        self.assertIn(".contributor_orig_published.", page)
        self.assertNotIn(".contributor_orig_private.", page)

    def test_textanswer_visibility_for_contributor_course_comments(self):
        page = self.app.get("/results/semester/1/course/1", user='contributor_course_comments')
        self.assertIn(".course_orig_published.", page)
        self.assertNotIn(".course_orig_hidden.", page)
        self.assertNotIn(".course_orig_published_changed.", page)
        self.assertIn(".course_changed_published.", page)
        self.assertNotIn(".responsible_orig_published.", page)
        self.assertNotIn(".responsible_orig_hidden.", page)
        self.assertNotIn(".responsible_orig_published_changed.", page)
        self.assertNotIn(".responsible_changed_published.", page)
        self.assertNotIn(".responsible_orig_private.", page)
        self.assertNotIn(".responsible_orig_notreviewed.", page)
        self.assertNotIn(".contributor_orig_published.", page)
        self.assertNotIn(".contributor_orig_private.", page)

    def test_textanswer_visibility_for_contributor_all_comments(self):
        page = self.app.get("/results/semester/1/course/1", user='contributor_all_comments')
        self.assertIn(".course_orig_published.", page)
        self.assertNotIn(".course_orig_hidden.", page)
        self.assertNotIn(".course_orig_published_changed.", page)
        self.assertIn(".course_changed_published.", page)
        self.assertIn(".responsible_orig_published.", page)
        self.assertNotIn(".responsible_orig_hidden.", page)
        self.assertNotIn(".responsible_orig_published_changed.", page)
        self.assertIn(".responsible_changed_published.", page)
        self.assertNotIn(".responsible_orig_private.", page)
        self.assertNotIn(".responsible_orig_notreviewed.", page)
        self.assertIn(".contributor_orig_published.", page)
        self.assertNotIn(".contributor_orig_private.", page)

    def test_textanswer_visibility_for_student(self):
        page = self.app.get("/results/semester/1/course/1", user='student')
        self.assertNotIn(".course_orig_published.", page)
        self.assertNotIn(".course_orig_hidden.", page)
        self.assertNotIn(".course_orig_published_changed.", page)
        self.assertNotIn(".course_changed_published.", page)
        self.assertNotIn(".responsible_orig_published.", page)
        self.assertNotIn(".responsible_orig_hidden.", page)
        self.assertNotIn(".responsible_orig_published_changed.", page)
        self.assertNotIn(".responsible_changed_published.", page)
        self.assertNotIn(".responsible_orig_private.", page)
        self.assertNotIn(".responsible_orig_notreviewed.", page)
        self.assertNotIn(".contributor_orig_published.", page)
        self.assertNotIn(".contributor_orig_private.", page)

class UnitTests(TestCase):

    def test_grade_color_calculation(self):
        exporter = ExcelExporter(Semester())
        self.assertEqual(exporter.STEP, 0.2)
        self.assertEqual(exporter.normalize_number(1.94999999999), 1.8)
        #self.assertEqual(exporter.normalize_number(1.95), 2.0) # floats ftw
        self.assertEqual(exporter.normalize_number(1.95000000001), 2.0)
        self.assertEqual(exporter.normalize_number(1.99999999999), 2.0)
        self.assertEqual(exporter.normalize_number(2.0), 2.0)
        self.assertEqual(exporter.normalize_number(2.00000000001), 2.0)
        self.assertEqual(exporter.normalize_number(2.1), 2.0)
        self.assertEqual(exporter.normalize_number(2.149999999999), 2.0)
        #self.assertEqual(exporter.normalize_number(2.15), 2.2) # floats again
        self.assertEqual(exporter.normalize_number(2.150000000001), 2.2)
        self.assertEqual(exporter.normalize_number(2.8), 2.8)


