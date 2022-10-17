from datetime import date, timedelta

from django.test import override_settings
from django.urls import reverse
from django_webtest import WebTest
from model_bakery import baker

from evap.evaluation.models import Course, Evaluation, Semester, UserProfile
from evap.evaluation.tests.tools import make_manager
from evap.rewards.models import (
    RewardPointGranting,
    RewardPointRedemption,
    RewardPointRedemptionEvent,
    SemesterActivation,
)
from evap.rewards.tools import is_semester_activated, redeemed_points_of_user, reward_points_of_user
from evap.staff.tests.utils import WebTestStaffMode, WebTestStaffModeWith200Check


class TestEventDeleteView(WebTestStaffMode):
    url = reverse("rewards:reward_point_redemption_event_delete")
    csrf_checks = False

    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()

    def test_deletion_success(self):
        event = baker.make(RewardPointRedemptionEvent)
        self.app.post(self.url, params={"event_id": event.pk}, user=self.manager, status=200)
        self.assertFalse(RewardPointRedemptionEvent.objects.filter(pk=event.pk).exists())

    def test_deletion_failure(self):
        """try to delete event that can not be deleted, because people already redeemed points"""
        event = baker.make(RewardPointRedemptionEvent)
        baker.make(RewardPointRedemption, value=1, event=event)

        self.app.post(self.url, params={"event_id": event.pk}, user=self.manager, status=400)
        self.assertTrue(RewardPointRedemptionEvent.objects.filter(pk=event.pk).exists())


class TestIndexView(WebTest):
    csrf_checks = False
    url = reverse("rewards:index")

    @classmethod
    def setUpTestData(cls):
        cls.student = baker.make(UserProfile, email="student@institution.example.com")
        baker.make(Evaluation, participants=[cls.student])
        baker.make(RewardPointGranting, user_profile=cls.student, value=5)
        cls.event1 = baker.make(RewardPointRedemptionEvent, redeem_end_date=date.today() + timedelta(days=1))
        cls.event2 = baker.make(RewardPointRedemptionEvent, redeem_end_date=date.today() + timedelta(days=1))

    def test_redeem_all_points(self):
        response = self.app.get(self.url, user=self.student)
        form = response.forms["reward-redemption-form"]
        form.set(f"points-{self.event1.pk}", 2)
        form.set(f"points-{self.event2.pk}", 3)
        response = form.submit()
        self.assertContains(response, "You successfully redeemed your points.")
        self.assertEqual(0, reward_points_of_user(self.student))

    def test_redeem_too_many_points(self):
        response = self.app.get(self.url, user=self.student)
        form = response.forms["reward-redemption-form"]
        form.set(f"points-{self.event1.pk}", 3)
        form.set(f"points-{self.event2.pk}", 3)
        response = form.submit()
        self.assertContains(response, "have enough reward points.")
        self.assertEqual(5, reward_points_of_user(self.student))

    def test_redeem_points_for_expired_event(self):
        """Regression test for #846"""
        response = self.app.get(self.url, user=self.student)
        form = response.forms["reward-redemption-form"]
        form.set(f"points-{self.event2.pk}", 1)
        RewardPointRedemptionEvent.objects.update(redeem_end_date=date.today() - timedelta(days=1))
        response = form.submit()
        self.assertContains(response, "event expired already.")
        self.assertEqual(5, reward_points_of_user(self.student))

    def post_redemption_request(self, redemption_params, additional_params=None, status=200):
        if additional_params is None:
            additional_params = {
                "previous_redeemed_points": redeemed_points_of_user(self.student),
            }
        return self.app.post(
            self.url, params={**redemption_params, **additional_params}, user=self.student, status=status
        )

    def test_invalid_post_parameters(self):
        self.post_redemption_request({"points-asd": 2}, status=400)
        self.post_redemption_request({"points-": 2}, status=400)
        self.post_redemption_request({f"points-{self.event1.pk}": ""}, status=400)
        self.post_redemption_request({f"points-{self.event1.pk}": "asd"}, status=400)

        # redemption without or with invalid point parameters
        self.post_redemption_request(
            redemption_params={f"points-{self.event1.pk}": 1}, additional_params={}, status=400
        )
        self.post_redemption_request(
            redemption_params={f"points-{self.event1.pk}": 1},
            additional_params={"previous_redeemed_points": "asd"},
            status=400,
        )
        self.assertFalse(RewardPointRedemption.objects.filter(user_profile=self.student).exists())

        # now, a correct request succeeds
        self.post_redemption_request({f"points-{self.event1.pk}": 2})

    def test_inconsistent_previous_redemption_counts(self):
        response1 = self.app.get(self.url, user=self.student)
        form1 = response1.forms["reward-redemption-form"]
        form1.set(f"points-{self.event1.pk}", 2)
        response2 = self.app.get(self.url, user=self.student)
        form2 = response2.forms["reward-redemption-form"]
        form2.set(f"points-{self.event1.pk}", 2)
        form1.submit()
        form2.submit(status=409)
        self.assertEqual(1, RewardPointRedemption.objects.filter(user_profile=self.student).count())


class TestEventsView(WebTestStaffModeWith200Check):
    url = reverse("rewards:reward_point_redemption_events")

    @classmethod
    def setUpTestData(cls):
        cls.test_users = [make_manager()]

        baker.make(RewardPointRedemptionEvent, redeem_end_date=date.today() + timedelta(days=1))
        baker.make(RewardPointRedemptionEvent, redeem_end_date=date.today() + timedelta(days=1))


class TestEventCreateView(WebTestStaffMode):
    url = reverse("rewards:reward_point_redemption_event_create")

    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()

    def test_create_redemption_event(self):
        """submits a newly created redemption event and checks that the event has been created"""
        self.assertEqual(RewardPointRedemptionEvent.objects.count(), 0)
        response = self.app.get(self.url, user=self.manager)

        form = response.forms["reward-point-redemption-event-form"]
        form.set("name", "Test3Event")
        form.set("date", "2014-12-10")
        form.set("redeem_end_date", "2014-11-20")

        response = form.submit()
        self.assertRedirects(response, reverse("rewards:reward_point_redemption_events"))
        self.assertEqual(RewardPointRedemptionEvent.objects.count(), 1)


class TestEventEditView(WebTestStaffMode):
    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        cls.event = baker.make(RewardPointRedemptionEvent, name="old name")
        cls.url = reverse("rewards:reward_point_redemption_event_edit", args=[cls.event.pk])

    def test_edit_redemption_event(self):
        """submits a newly created redemption event and checks that the event has been created"""
        response = self.app.get(self.url, user=self.manager)

        form = response.forms["reward-point-redemption-event-form"]
        form.set("name", "new name")

        response = form.submit()
        self.assertRedirects(response, reverse("rewards:reward_point_redemption_events"))
        self.assertEqual(RewardPointRedemptionEvent.objects.get(pk=self.event.pk).name, "new name")


class TestExportView(WebTestStaffModeWith200Check):
    @classmethod
    def setUpTestData(cls):
        cls.test_users = [make_manager()]
        event = baker.make(RewardPointRedemptionEvent, redeem_end_date=date.today() + timedelta(days=1))
        baker.make(RewardPointRedemption, value=1, event=event)
        cls.url = f"/rewards/reward_point_redemption_event/{event.pk}/export"


@override_settings(
    REWARD_POINTS=[
        (1 / 3, 1),
        (2 / 3, 2),
        (3 / 3, 3),
    ]
)
class TestSemesterActivationView(WebTestStaffMode):
    csrf_checks = False

    @classmethod
    def setUpTestData(cls):
        cls.manager = make_manager()
        cls.semester = baker.make(Semester)
        cls.student = baker.make(UserProfile, email="student@institution.example.com")
        course = baker.make(Course, semester=cls.semester)
        cls.evaluation = baker.make(
            Evaluation,
            state=Evaluation.State.IN_EVALUATION,
            participants=[cls.student],
            voters=[cls.student],
            course=course,
        )

        cls.url = f"/rewards/reward_semester_activation/{cls.semester.pk}/"

    def test_activate(self):
        baker.make(SemesterActivation, semester=self.semester, is_active=False)
        self.app.post(self.url + "on", user=self.manager)
        self.assertTrue(is_semester_activated(self.semester))

    def test_deactivate(self):
        baker.make(SemesterActivation, semester=self.semester, is_active=True)
        self.app.post(self.url + "off", user=self.manager)
        self.assertFalse(is_semester_activated(self.semester))

    def test_activate_after_voting(self):
        baker.make(SemesterActivation, semester=self.semester, is_active=False)
        self.assertEqual(0, reward_points_of_user(self.student))
        response = self.app.post(self.url + "on", user=self.manager)
        self.assertContains(response, "3 reward points were granted")
        self.assertEqual(3, reward_points_of_user(self.student))
