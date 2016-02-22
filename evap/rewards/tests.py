from django.conf import settings
from django_webtest import WebTest
from evap.evaluation.models import Course
from evap.evaluation.models import UserProfile
from evap.rewards.models import SemesterActivation
from evap.rewards.models import RewardPointRedemptionEvent
from evap.rewards.tools import reward_points_of_user
from evap.staff.tests import lastform
from django.core.urlresolvers import reverse
from model_mommy import mommy


class RewardTests(WebTest):
    fixtures = ['minimal_test_data_rewards']
    csrf_checks = False

    def test_delete_redemption_events(self):
        """
            Submits a request that tries to delete an event where users already redeemed points -> should not work.
            It also submits a request that should delete the event.
        """
        # try to delete event that can not be deleted, because people already redeemed points
        response = self.app.post(reverse("rewards:reward_point_redemption_event_delete"), {"event_id": 1,}, user="evap", expect_errors=True)
        self.assertEqual(response.status_code, 400)
        self.assertTrue(RewardPointRedemptionEvent.objects.filter(pk=2).exists())

        # now delete for real
        response = self.app.post(reverse("rewards:reward_point_redemption_event_delete"), {"event_id": 2,}, user="evap")
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
        form = lastform(response)
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

        form = lastform(response)
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

        form = lastform(response)
        name = form.get('name').value
        form.set('name', 'new name')

        response = form.submit()
        self.assertRedirects(response, reverse('rewards:reward_point_redemption_events'))
        self.assertNotEqual(RewardPointRedemptionEvent.objects.get(pk=2).name, name)

    def test_grant_reward_points(self):
        """
            submits several requests that trigger the reward point granting and checks that the reward point
            granting works as expected for the different requests.
        """
        user = UserProfile.objects.get(pk=5)
        reward_points_before_end = reward_points_of_user(user)
        response = self.app.get(reverse("student:vote", args=[9]), user="student")

        form = lastform(response)
        for key, value in form.fields.items():
            if key is not None and "question" in key:
                form.set(key, 6)

        response = form.submit()
        self.assertRedirects(response, reverse('student:index'))

        # semester is not activated --> number of reward points should not increase
        self.assertEqual(reward_points_before_end, reward_points_of_user(user))

        # reset course for another try
        course = Course.objects.get(pk=9)
        course.voters = []
        # activate semester
        activation = SemesterActivation.objects.get(semester=course.semester)
        activation.is_active = True
        activation.save()
        # create a new course
        new_course = mommy.make(Course, semester=course.semester)
        new_course.save()
        new_course.participants.add(user)
        new_course.save()
        response = form.submit()
        self.assertRedirects(response, reverse('student:index'))

        # user also has other courses this semester --> number of reward points should not increase
        self.assertEqual(reward_points_before_end, reward_points_of_user(user))

        course.voters = []
        course.save()
        new_course.participants.remove(user)
        new_course.save()

        # last course of user so he may get reward points
        response = form.submit()
        self.assertRedirects(response, reverse('student:index'))
        # if this test fails because of this assertion check that the user is allowed to receive reward points!
        self.assertEqual(reward_points_before_end + settings.REWARD_POINTS_PER_SEMESTER, reward_points_of_user(user))

        # test behaviour if user already got reward points
        course.voters = []
        course.save()
        response = form.submit()
        self.assertRedirects(response, reverse('student:index'))
        self.assertEqual(reward_points_before_end + settings.REWARD_POINTS_PER_SEMESTER, reward_points_of_user(user))
