from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from model_mommy import mommy

from evap.evaluation.models import Course, Questionnaire, Question
from evap.evaluation.models import UserProfile
from evap.evaluation.tests.tools import WebTest
from evap.rewards.models import SemesterActivation, RewardPointGranting
from evap.rewards.tools import reward_points_of_user, target_points


class TestGrantRewardPoints(WebTest):
    csrf_checks = False

    @classmethod
    def setUpTestData(cls):
        cls.student = mommy.make(UserProfile, username='student', email='foo@institution.example.com')
        cls.course = mommy.make(Course, state='in_evaluation', participants=[cls.student])

        questionnaire = mommy.make(Questionnaire)
        mommy.make(Question, questionnaire=questionnaire, type="G")
        cls.course.general_contribution.questionnaires.set([questionnaire])

    def setUp(self):
        response = self.app.get(reverse("student:vote", args=[self.course.pk]), user="student")

        self.form = response.forms["student-vote-form"]
        for key in self.form.fields.keys():
            if key is not None and "question" in key:
                self.form.set(key, 6)

    def test_semester_not_activated(self):
        self.form.submit()
        self.assertEqual(0, reward_points_of_user(self.student))

    def test_everything_works(self):
        SemesterActivation.objects.create(semester=self.course.semester, is_active=True)
        self.form.submit()
        self.assertEqual(reward_points_of_user(self.student), target_points(1.0))

    def test_semester_activated_not_all_courses(self):
        SemesterActivation.objects.create(semester=self.course.semester, is_active=True)
        mommy.make(Course, semester=self.course.semester, participants=[self.student])
        self.form.submit()
        self.assertEqual(target_points(0.5), reward_points_of_user(self.student))

    def test_already_got_points(self):
        SemesterActivation.objects.create(semester=self.course.semester, is_active=True)
        mommy.make(RewardPointGranting, user_profile=self.student, value=0, semester=self.course.semester)
        self.form.submit()
        self.assertEqual(target_points(1.0), reward_points_of_user(self.student))

    def test_target_points(self):
        thresholds = [
            (0.5, 2),
            (1.0, 5),
        ]
        self.assertEqual(target_points(0.0, thresholds=thresholds), 0)
        self.assertEqual(target_points(0.6, thresholds=thresholds), 2)
        self.assertEqual(target_points(0.9, thresholds=thresholds), 2)
        self.assertEqual(target_points(1.0, thresholds=thresholds), 5)
        self.assertEqual(target_points(1.0, thresholds=[]), 0)


class TestGrantRewardPointsParticipationChange(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.course = mommy.make(Course)
        already_evaluated = mommy.make(Course, semester=cls.course.semester)
        SemesterActivation.objects.create(semester=cls.course.semester, is_active=True)
        cls.student = mommy.make(UserProfile, username="student", email="foo@institution.example.com",
            courses_participating_in=[cls.course, already_evaluated], courses_voted_for=[already_evaluated])

    def test_participant_removed_from_course(self):
        self.course.participants.remove(self.student)

        self.assertEqual(reward_points_of_user(self.student), settings.REWARD_POINTS_PER_SEMESTER)

    def test_course_removed_from_participant(self):
        self.student.courses_participating_in.remove(self.course)

        self.assertEqual(reward_points_of_user(self.student), settings.REWARD_POINTS_PER_SEMESTER)

