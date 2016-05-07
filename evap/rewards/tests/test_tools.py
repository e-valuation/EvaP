from django.conf import settings
from django.core.urlresolvers import reverse

from model_mommy import mommy

from evap.evaluation.models import Course
from evap.evaluation.models import UserProfile
from evap.evaluation.tests.tools import WebTest
from evap.rewards.models import SemesterActivation
from evap.rewards.tools import reward_points_of_user


class GrantRewardPointsTests(WebTest):
    fixtures = ['minimal_test_data_rewards']
    csrf_checks = False

    def test_grant_reward_points(self):
        """
            submits several requests that trigger the reward point granting and checks that the reward point
            granting works as expected for the different requests.
        """
        user = UserProfile.objects.get(pk=5)
        reward_points_before_end = reward_points_of_user(user)
        response = self.app.get(reverse("student:vote", args=[9]), user="student")

        form = response.forms["student-vote-form"]
        for key in form.fields.keys():
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
