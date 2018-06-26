from django.test import TestCase, override_settings
from django.urls import reverse

from model_mommy import mommy

from evap.evaluation.models import Course, Questionnaire, Question
from evap.evaluation.models import UserProfile
from evap.evaluation.tests.tools import WebTest
from evap.rewards.models import SemesterActivation, RewardPointGranting
from evap.rewards.tools import reward_points_of_user


@override_settings(REWARD_POINTS=[
    (1.0/3.0, 1),
    (2.0/3.0, 2),
    (3.0/3.0, 3),
])
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
        self.assertEqual(reward_points_of_user(self.student), 3)

    def test_semester_activated_not_all_courses(self):
        SemesterActivation.objects.create(semester=self.course.semester, is_active=True)
        mommy.make(Course, semester=self.course.semester, participants=[self.student])
        self.form.submit()
        self.assertEqual(1, reward_points_of_user(self.student))

    def test_already_got_grant_objects_but_points_missing(self):
        SemesterActivation.objects.create(semester=self.course.semester, is_active=True)
        mommy.make(RewardPointGranting, user_profile=self.student, value=0, semester=self.course.semester)
        self.form.submit()
        self.assertEqual(3, reward_points_of_user(self.student))
        self.assertEqual(2, RewardPointGranting.objects.filter(user_profile=self.student, semester=self.course.semester).count())

    def test_already_got_enough_points(self):
        SemesterActivation.objects.create(semester=self.course.semester, is_active=True)
        mommy.make(RewardPointGranting, user_profile=self.student, value=3, semester=self.course.semester)
        self.form.submit()
        self.assertEqual(3, reward_points_of_user(self.student))
        self.assertEqual(1, RewardPointGranting.objects.filter(user_profile=self.student, semester=self.course.semester).count())


@override_settings(REWARD_POINTS=[
    (1.0/3.0, 1),
    (2.0/3.0, 2),
    (3.0/3.0, 3),
])
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

        self.assertEqual(reward_points_of_user(self.student), 3)

    def test_course_removed_from_participant(self):
        self.student.courses_participating_in.remove(self.course)

        self.assertEqual(reward_points_of_user(self.student), 3)
