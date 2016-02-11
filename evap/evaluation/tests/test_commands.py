from django.core import management
from unittest.mock import patch
from django.test.testcases import TestCase


class TestUpdateCourseStatesCommand(TestCase):
    def test_update_courses_called(self):
        with patch('evap.evaluation.models.Course.update_courses') as mock:
            management.call_command('update_course_states')

        self.assertEquals(mock.call_count, 1)
