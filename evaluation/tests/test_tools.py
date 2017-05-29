from django.core.cache import cache
from django.test.testcases import TestCase
from model_mommy import mommy

from evap.evaluation.models import Course
from evap.evaluation.tools import calculate_results


class TestCalculateResults(TestCase):
    def test_caches_published_course(self):
        course = mommy.make(Course, state='published')

        self.assertIsNone(cache.get('evap.staff.results.tools.calculate_results-{:d}'.format(course.id)))

        calculate_results(course)

        self.assertIsNotNone(cache.get('evap.staff.results.tools.calculate_results-{:d}'.format(course.id)))
