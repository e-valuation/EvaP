import datetime
from unittest.mock import patch
from django.test import TestCase
from model_mommy import mommy

from evap.evaluation.models import Course


class TestCourses(TestCase):
    today = datetime.date.today()

    def test_approved_to_inEvaluation(self):
        course = mommy.make(Course, state='approved',  vote_start_date=self.today)

        with patch('evap.evaluation.models.EmailTemplate.send_evaluation_started_notifications') as mock:
            Course.update_courses()

        mock.assert_called_once_with([course])

        course = Course.objects.get(pk=course.pk)
        self.assertEqual(course.state, 'inEvaluation')

    def test_inEvaluation_to_evaluated(self):
        course = mommy.make(Course, state='inEvaluation', vote_end_date=self.today - datetime.timedelta(days=1))

        with patch('evap.evaluation.models.Course.is_fully_reviewed') as mock:
            mock.return_value = False
            Course.update_courses()

        course = Course.objects.get(pk=course.pk)
        self.assertEqual(course.state, 'evaluated')

    def test_inEvaluation_to_reviewed(self):
        # Course is "fully reviewed" as no open text_answers are present by default,
        course = mommy.make(Course, state='inEvaluation', vote_end_date=self.today - datetime.timedelta(days=1))

        Course.update_courses()

        course = Course.objects.get(pk=course.pk)
        self.assertEqual(course.state, 'reviewed')

    def test_inEvaluation_to_published(self):
        # Course is "fully reviewed" and not graded, thus gets published immediately.
        course = mommy.make(Course, state='inEvaluation', vote_end_date=self.today - datetime.timedelta(days=1),
                            is_graded=False)

        with patch('evap.evaluation.tools.send_publish_notifications') as mock:
            Course.update_courses()

        mock.assert_called_once_with(evaluation_results_courses=[course])

        course = Course.objects.get(pk=course.pk)
        self.assertEqual(course.state, 'published')

