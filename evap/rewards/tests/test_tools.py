from django.conf import settings
from django.urls import reverse

from model_mommy import mommy

from evap.evaluation.models import Course, Questionnaire, Question
from evap.evaluation.models import UserProfile
from evap.evaluation.tests.tools import WebTest
from evap.rewards.models import SemesterActivation, RewardPointGranting
from evap.rewards.tools import reward_points_of_user


class TestGrantRewardPoints(WebTest):
    csrf_checks = False

    @classmethod
    def setUpTestData(cls):
        cls.student = mommy.make(UserProfile, username='student', email='foo@institution.example.com')
        cls.course = mommy.make(Course, pk=1, state='in_evaluation', participants=[cls.student])

        questionnaire = mommy.make(Questionnaire)
        mommy.make(Question, questionnaire=questionnaire, type="G")
        cls.course.general_contribution.questionnaires.set([questionnaire])

    def setUp(self):
        response = self.app.get(reverse("student:vote", args=[1]), user="student")

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
        self.assertEqual(settings.REWARD_POINTS_PER_SEMESTER, reward_points_of_user(self.student))

    def test_semester_activated_not_all_courses(self):
        SemesterActivation.objects.create(semester=self.course.semester, is_active=True)
        mommy.make(Course, semester=self.course.semester, participants=[self.student])
        self.form.submit()
        self.assertEqual(0, reward_points_of_user(self.student))

    def test_already_got_points(self):
        SemesterActivation.objects.create(semester=self.course.semester, is_active=True)
        mommy.make(RewardPointGranting, user_profile=self.student, value=0, semester=self.course.semester)
        self.form.submit()
        self.assertEqual(0, reward_points_of_user(self.student))
