from django.test import TestCase

from evap.evaluation.models import Semester
from evap.results.exporters import ExcelExporter


class TestExporters(TestCase):
    def test_grade_color_calculation(self):
        exporter = ExcelExporter(Semester())
        self.assertEqual(exporter.STEP, 0.2)
        self.assertEqual(exporter.normalize_number(1.94999999999), 1.8)
        # self.assertEqual(exporter.normalize_number(1.95), 2.0)  # floats ftw
        self.assertEqual(exporter.normalize_number(1.95000000001), 2.0)
        self.assertEqual(exporter.normalize_number(1.99999999999), 2.0)
        self.assertEqual(exporter.normalize_number(2.0), 2.0)
        self.assertEqual(exporter.normalize_number(2.00000000001), 2.0)
        self.assertEqual(exporter.normalize_number(2.1), 2.0)
        self.assertEqual(exporter.normalize_number(2.149999999999), 2.0)
        # self.assertEqual(exporter.normalize_number(2.15), 2.2)  # floats again
        self.assertEqual(exporter.normalize_number(2.150000000001), 2.2)
        self.assertEqual(exporter.normalize_number(2.8), 2.8)
