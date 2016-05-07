from django.core.urlresolvers import reverse

from evap.evaluation.models import UserProfile
from evap.evaluation.tests.tools import WebTest
from evap.rewards.models import RewardPointRedemptionEvent
from evap.rewards.tools import reward_points_of_user


class ViewTests(WebTest):
    fixtures = ['minimal_test_data_rewards']
    csrf_checks = False

    def test_delete_redemption_events(self):
        """
            Submits a request that tries to delete an event where users already redeemed points -> should not work.
            It also submits a request that should delete the event.
        """
        # try to delete event that can not be deleted, because people already redeemed points
        response = self.app.post(reverse("rewards:reward_point_redemption_event_delete"), {"event_id": 1}, user="evap", expect_errors=True)
        self.assertEqual(response.status_code, 400)
        self.assertTrue(RewardPointRedemptionEvent.objects.filter(pk=2).exists())

        # now delete for real
        response = self.app.post(reverse("rewards:reward_point_redemption_event_delete"), {"event_id": 2}, user="evap")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(RewardPointRedemptionEvent.objects.filter(pk=2).exists())

    def test_redeem_reward_points(self):
        """
            Submits a request that redeems all available reward points and checks that this works.
            Also checks that it is not possible to redeem more points than the user actually has.
        """
        response = self.app.get(reverse("rewards:index"), user="student")
        self.assertEqual(response.status_code, 200)

        user = UserProfile.objects.get(pk=5)
        form = response.forms["reward-redemption-form"]
        form.set("points-1", reward_points_of_user(user))
        response = form.submit()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "You successfully redeemed your points.")
        self.assertEqual(0, reward_points_of_user(user))

        form.set("points-1", 1)
        form.set("points-2", 3)
        response = form.submit()
        self.assertIn(b"have enough reward points.", response.body)

    def test_create_redemption_event(self):
        """
            submits a newly created redemption event and checks that the event has been created
        """
        response = self.app.get(reverse("rewards:reward_point_redemption_event_create"), user="evap")

        form = response.forms["reward-point-redemption-event-form"]
        form.set('name', 'Test3Event')
        form.set('date', '2014-12-10')
        form.set('redeem_end_date', '2014-11-20')

        response = form.submit()
        self.assertRedirects(response, reverse('rewards:reward_point_redemption_events'))
        self.assertEqual(RewardPointRedemptionEvent.objects.count(), 3)

    def test_edit_redemption_event(self):
        """
            submits a changed redemption event and tests whether it actually has changed
        """
        response = self.app.get(reverse("rewards:reward_point_redemption_event_edit", args=[2]), user="evap")

        form = response.forms["reward-point-redemption-event-form"]
        name = form.get('name').value
        form.set('name', 'new name')

        response = form.submit()
        self.assertRedirects(response, reverse('rewards:reward_point_redemption_events'))
        self.assertNotEqual(RewardPointRedemptionEvent.objects.get(pk=2).name, name)
