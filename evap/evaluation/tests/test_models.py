from datetime import date, timedelta
from unittest.mock import patch
from django.test import TestCase
from model_mommy import mommy

from evap.evaluation.models import Course, UserProfile, Contribution, Semester


class TestCourses(TestCase):

    def test_approved_to_inEvaluation(self):
        course = mommy.make(Course, state='approved',  vote_start_date=date.today())

        with patch('evap.evaluation.models.EmailTemplate.send_evaluation_started_notifications') as mock:
            Course.update_courses()

        mock.assert_called_once_with([course])

        course = Course.objects.get(pk=course.pk)
        self.assertEqual(course.state, 'inEvaluation')

    def test_inEvaluation_to_evaluated(self):
        course = mommy.make(Course, state='inEvaluation', vote_end_date=date.today() - timedelta(days=1))

        with patch('evap.evaluation.models.Course.is_fully_reviewed') as mock:
            mock.return_value = False
            Course.update_courses()

        course = Course.objects.get(pk=course.pk)
        self.assertEqual(course.state, 'evaluated')

    def test_inEvaluation_to_reviewed(self):
        # Course is "fully reviewed" as no open text_answers are present by default,
        course = mommy.make(Course, state='inEvaluation', vote_end_date=date.today() - timedelta(days=1))

        Course.update_courses()

        course = Course.objects.get(pk=course.pk)
        self.assertEqual(course.state, 'reviewed')

    def test_inEvaluation_to_published(self):
        # Course is "fully reviewed" and not graded, thus gets published immediately.
        course = mommy.make(Course, state='inEvaluation', vote_end_date=date.today() - timedelta(days=1),
                            is_graded=False)

        with patch('evap.evaluation.tools.send_publish_notifications') as mock:
            Course.update_courses()

        mock.assert_called_once_with([course])

        course = Course.objects.get(pk=course.pk)
        self.assertEqual(course.state, 'published')

class TestUserProfile(TestCase):

    def test_is_student(self):
        some_user = mommy.make(UserProfile)
        self.assertFalse(some_user.is_student)

        student = mommy.make(UserProfile, courses_participating_in=[mommy.make(Course)])
        self.assertTrue(student.is_student)

        contributor = mommy.make(UserProfile, contributions=[mommy.make(Contribution)])
        self.assertFalse(contributor.is_student)

        semester_contributed_to = mommy.make(Semester, created_at=date.today())
        semester_participated_in = mommy.make(Semester, created_at=date.today())
        course_contributed_to = mommy.make(Course, semester=semester_contributed_to)
        course_participated_in = mommy.make(Course, semester=semester_participated_in)
        contribution = mommy.make(Contribution, course=course_contributed_to)
        user = mommy.make(UserProfile, contributions=[contribution], courses_participating_in=[course_participated_in])

        self.assertTrue(user.is_student)

        semester_contributed_to.created_at = date.today() - timedelta(days=1)
        semester_contributed_to.save()

        self.assertTrue(user.is_student)

        semester_participated_in.created_at = date.today() - timedelta(days=2)
        semester_participated_in.save()

        self.assertFalse(user.is_student)
