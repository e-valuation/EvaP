from django_webtest import WebTest
from django.core.urlresolvers import reverse
from evap.evaluation.models import Course, UserProfile, Contribution, Questionnaire, Question
from model_mommy import mommy


class VoteTests(WebTest):

    def test_user_cannot_vote_for_themselves(self):
        contributor1 = mommy.make(UserProfile)
        contributor2 = mommy.make(UserProfile)
        student = mommy.make(UserProfile)

        course = mommy.make(Course, state='inEvaluation', participants=[student, contributor1])
        questionnaire = mommy.make(Questionnaire)
        mommy.make(Question, questionnaire=questionnaire, type="G")
        mommy.make(Contribution, contributor=contributor1, course=course, questionnaires=[questionnaire])
        mommy.make(Contribution, contributor=contributor2, course=course, questionnaires=[questionnaire])

        def get_vote_page(user):
            return self.app.get(reverse('student:vote', kwargs={'course_id': course.id}), user=user)

        response = get_vote_page(contributor1)

        for contributor, _, _ in response.context['contributor_form_groups']:
            self.assertNotEqual(contributor, contributor1, "Contributor should not see the questionnaire about themselves")

        response = get_vote_page(student)
        self.assertTrue(any(contributor == contributor1 for contributor, _, _ in response.context['contributor_form_groups']),
            "Regular students should see the questionnaire about a contributor")
