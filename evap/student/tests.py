from django.test import TestCase, Client
from django.contrib.auth.models import User, UserManager
from django.core.urlresolvers import reverse
from evap.evaluation.models import Course

class VoteTests(TestCase):
    fixtures = ['vote_test']

    def test_user_cannot_vote_for_themselves(self):
        if not self.client.login(username='tutor', password='tutor'):
            self.fail('Fixture error: tutor user could not log in')
        course = Course.objects.get() # there is only one
        def get_vote_page():
            return self.client.get(reverse('evap.student.views.vote', kwargs={'course_id': course.id}))
        response = get_vote_page() 
        tutorUser = User.objects.get(username='tutor')
        for form in response.context['forms']:
            self.assertNotEquals(form.contribution.contributor, tutorUser,
                    "Contributor should not see the questionnaire about themselves")
        self.client.logout()
        if not self.client.login(username='student', password='student'):
            self.fail('Fixture error: student user could not log in')
        response = get_vote_page()
        self.assertTrue(any(form.contribution.contributor == tutorUser for form in response.context['forms']),
                "Regular students should see the questionnaire about a contributor")
