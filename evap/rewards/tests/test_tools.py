from django.test import override_settings
from django.urls import reverse
from model_bakery import baker

from evap.evaluation.models import NO_ANSWER, Course, Evaluation, Question, Questionnaire, QuestionType, UserProfile
from evap.evaluation.tests.tools import TestCase, WebTest
from evap.rewards.models import RewardPointGranting, SemesterActivation
from evap.rewards.tools import reward_points_of_user


@override_settings(
    REWARD_POINTS=[
        (1 / 3, 1),
        (2 / 3, 2),
        (3 / 3, 3),
    ]
)
class TestGrantRewardPoints(WebTest):
    @classmethod
    def setUpTestData(cls):
        cls.student = baker.make(UserProfile, email="student@institution.example.com")
        cls.evaluation = baker.make(Evaluation, state=Evaluation.State.IN_EVALUATION, participants=[cls.student])

        questionnaire = baker.make(Questionnaire)
        baker.make(Question, questionnaire=questionnaire, type=QuestionType.GRADE)
        cls.evaluation.general_contribution.questionnaires.set([questionnaire])

    def setUp(self):
        response = self.app.get(reverse("student:vote", args=[self.evaluation.pk]), user=self.student)

        self.form = response.forms["student-vote-form"]
        for key in self.form.fields.keys():
            if key is not None and "question" in key:
                self.form.set(key, NO_ANSWER)

    def test_semester_not_activated(self):
        self.form.submit()
        self.assertEqual(0, reward_points_of_user(self.student))

    def test_everything_works(self):
        SemesterActivation.objects.create(semester=self.evaluation.course.semester, is_active=True)
        self.form.submit()
        self.assertEqual(reward_points_of_user(self.student), 3)

    def test_semester_activated_not_all_evaluations(self):
        SemesterActivation.objects.create(semester=self.evaluation.course.semester, is_active=True)
        baker.make(
            Evaluation, course=baker.make(Course, semester=self.evaluation.course.semester), participants=[self.student]
        )
        self.form.submit()
        self.assertEqual(1, reward_points_of_user(self.student))

    def test_already_got_grant_objects_but_points_missing(self):
        SemesterActivation.objects.create(semester=self.evaluation.course.semester, is_active=True)
        baker.make(RewardPointGranting, user_profile=self.student, value=0, semester=self.evaluation.course.semester)
        self.form.submit()
        self.assertEqual(3, reward_points_of_user(self.student))
        self.assertEqual(
            2,
            RewardPointGranting.objects.filter(
                user_profile=self.student, semester=self.evaluation.course.semester
            ).count(),
        )

    def test_already_got_enough_points(self):
        SemesterActivation.objects.create(semester=self.evaluation.course.semester, is_active=True)
        baker.make(RewardPointGranting, user_profile=self.student, value=3, semester=self.evaluation.course.semester)
        self.form.submit()
        self.assertEqual(3, reward_points_of_user(self.student))
        self.assertEqual(
            1,
            RewardPointGranting.objects.filter(
                user_profile=self.student, semester=self.evaluation.course.semester
            ).count(),
        )


@override_settings(
    REWARD_POINTS=[
        (1 / 3, 1),
        (2 / 3, 2),
        (3 / 3, 3),
    ]
)
class TestGrantRewardPointsParticipationChange(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.evaluation = baker.make(Evaluation)
        already_evaluated = baker.make(Evaluation, course=baker.make(Course, semester=cls.evaluation.course.semester))
        SemesterActivation.objects.create(semester=cls.evaluation.course.semester, is_active=True)
        cls.student = baker.make(
            UserProfile,
            email="student@institution.example.com",
            evaluations_participating_in=[cls.evaluation, already_evaluated],
            evaluations_voted_for=[already_evaluated],
        )

    def test_participant_removed_from_evaluation(self):
        self.evaluation.participants.remove(self.student)

        self.assertEqual(reward_points_of_user(self.student), 3)

    def test_evaluation_removed_from_participant(self):
        self.student.evaluations_participating_in.remove(self.evaluation)

        self.assertEqual(reward_points_of_user(self.student), 3)
