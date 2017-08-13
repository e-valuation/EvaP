from datetime import date, timedelta

from django.contrib.auth.models import Group
from django.urls import reverse

from model_mommy import mommy

from evap.evaluation.models import UserProfile, Course, Semester
from evap.evaluation.tests.tools import ViewTest
from evap.rewards.models import RewardPointRedemptionEvent, RewardPointGranting, RewardPointRedemption, SemesterActivation
from evap.rewards.tools import reward_points_of_user, is_semester_activated


class TestEventDeleteView(ViewTest):
    url = reverse('rewards:reward_point_redemption_event_delete')
    csrf_checks = False

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='staff', groups=[Group.objects.get(name='Staff')])

    def test_deletion_success(self):
        mommy.make(RewardPointRedemptionEvent, pk=1)
        response = self.app.post(self.url, params={'event_id': 1}, user='staff')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(RewardPointRedemptionEvent.objects.filter(pk=1).exists())

    def test_deletion_failure(self):
        """ try to delete event that can not be deleted, because people already redeemed points """
        event = mommy.make(RewardPointRedemptionEvent, pk=1)
        mommy.make(RewardPointRedemption, value=1, event=event)

        response = self.app.post(self.url, params={'event_id': 1}, user='staff', expect_errors=True)
        self.assertEqual(response.status_code, 400)
        self.assertTrue(RewardPointRedemptionEvent.objects.filter(pk=1).exists())


class TestIndexView(ViewTest):
    url = reverse('rewards:index')
    test_users = ['student']
    csrf_checks = False

    @classmethod
    def setUpTestData(cls):
        cls.student = mommy.make(UserProfile, username='student', email='foo@institution.example.com')
        mommy.make(Course, participants=[cls.student])
        mommy.make(RewardPointGranting, user_profile=cls.student, value=5)
        mommy.make(RewardPointRedemptionEvent, pk=1, redeem_end_date=date.today() + timedelta(days=1))
        mommy.make(RewardPointRedemptionEvent, pk=2, redeem_end_date=date.today() + timedelta(days=1))

    def test_redeem_all_points(self):
        response = self.app.get(reverse('rewards:index'), user='student')
        form = response.forms['reward-redemption-form']
        form.set('points-1', 2)
        form.set('points-2', 3)
        response = form.submit()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "You successfully redeemed your points.")
        self.assertEqual(0, reward_points_of_user(self.student))

    def test_redeem_too_many_points(self):
        response = self.app.get(reverse('rewards:index'), user='student')
        form = response.forms['reward-redemption-form']
        form.set('points-1', 3)
        form.set('points-2', 3)
        response = form.submit()
        self.assertContains(response, "have enough reward points.")
        self.assertEqual(5, reward_points_of_user(self.student))

    def test_redeem_points_for_expired_event(self):
        """ Regression test for #846 """
        response = self.app.get(reverse('rewards:index'), user='student')
        form = response.forms['reward-redemption-form']
        form.set('points-2', 1)
        RewardPointRedemptionEvent.objects.update(redeem_end_date=date.today() - timedelta(days=1))
        response = form.submit()
        self.assertContains(response, "event expired already.")
        self.assertEqual(5, reward_points_of_user(self.student))


class TestEventsView(ViewTest):
    url = reverse('rewards:reward_point_redemption_events')
    test_users = ['staff']

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='staff', groups=[Group.objects.get(name='Staff')])
        mommy.make(RewardPointRedemptionEvent, pk=1, redeem_end_date=date.today() + timedelta(days=1))
        mommy.make(RewardPointRedemptionEvent, pk=2, redeem_end_date=date.today() + timedelta(days=1))


class TestEventCreateView(ViewTest):
    url = reverse('rewards:reward_point_redemption_event_create')
    test_users = ['staff']
    csrf_checks = False

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='staff', groups=[Group.objects.get(name='Staff')])

    def test_create_redemption_event(self):
        """ submits a newly created redemption event and checks that the event has been created """
        self.assertEqual(RewardPointRedemptionEvent.objects.count(), 0)
        response = self.app.get(self.url, user='staff')

        form = response.forms['reward-point-redemption-event-form']
        form.set('name', 'Test3Event')
        form.set('date', '2014-12-10')
        form.set('redeem_end_date', '2014-11-20')

        response = form.submit()
        self.assertRedirects(response, reverse('rewards:reward_point_redemption_events'))
        self.assertEqual(RewardPointRedemptionEvent.objects.count(), 1)


class TestEventEditView(ViewTest):
    url = reverse('rewards:reward_point_redemption_event_edit', args=[1])
    test_users = ['staff']
    csrf_checks = False

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='staff', groups=[Group.objects.get(name='Staff')])
        mommy.make(RewardPointRedemptionEvent, pk=1, name='old name')

    def test_edit_redemption_event(self):
        """ submits a newly created redemption event and checks that the event has been created """
        response = self.app.get(self.url, user='staff')

        form = response.forms['reward-point-redemption-event-form']
        form.set('name', 'new name')

        response = form.submit()
        self.assertRedirects(response, reverse('rewards:reward_point_redemption_events'))
        self.assertEqual(RewardPointRedemptionEvent.objects.get(pk=1).name, 'new name')


class TestExportView(ViewTest):
    url = '/rewards/reward_point_redemption_event/1/export'
    test_users = ['staff']

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='staff', groups=[Group.objects.get(name='Staff')])
        event = mommy.make(RewardPointRedemptionEvent, pk=1, redeem_end_date=date.today() + timedelta(days=1))
        mommy.make(RewardPointRedemption, value=1, event=event)


class TestSemesterActivationView(ViewTest):
    url = '/rewards/reward_semester_activation/1/'
    csrf_checks = False

    @classmethod
    def setUpTestData(cls):
        mommy.make(UserProfile, username='staff', groups=[Group.objects.get(name='Staff')])
        cls.semester = mommy.make(Semester, pk=1)

    def test_activate(self):
        mommy.make(SemesterActivation, semester=self.semester, is_active=False)
        self.app.post(self.url + 'on', user='staff')
        self.assertTrue(is_semester_activated(self.semester))

    def test_deactivate(self):
        mommy.make(SemesterActivation, semester=self.semester, is_active=True)
        self.app.post(self.url + 'off', user='staff')
        self.assertFalse(is_semester_activated(self.semester))
