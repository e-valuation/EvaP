from django.test import TestCase

from model_mommy import mommy

from evap.evaluation.models import Course, UserProfile, Contribution, Questionnaire, CourseType, Semester


class TestUserProfiles(TestCase):
    def test_users_are_deletable(self):
        user = mommy.make(UserProfile)
        mommy.make(Course, participants=[user], state="new")
        self.assertTrue(user.can_staff_delete)

        user2 = mommy.make(UserProfile)
        mommy.make(Course, participants=[user2], state="inEvaluation")
        self.assertFalse(user2.can_staff_delete)

        contributor = mommy.make(UserProfile)
        mommy.make(Contribution, contributor=contributor)
        self.assertFalse(contributor.can_staff_delete)

    def test_deleting_last_modified_user_does_not_delete_course(self):
        user = mommy.make(UserProfile);
        course = mommy.make(Course, last_modified_user=user);
        user.delete()
        self.assertTrue(Course.objects.filter(pk=course.pk).exists())


class TestCourses(TestCase):
    def test_has_enough_questionnaires(self):
        # manually circumvent Course's save() method to have a Course without a general contribution
        # the semester must be specified because of https://github.com/vandersonmota/model_mommy/issues/258
        Course.objects.bulk_create([mommy.prepare(Course, semester=mommy.make(Semester), type=mommy.make(CourseType))])
        course = Course.objects.get()
        self.assertEqual(course.contributions.count(), 0)
        self.assertFalse(course.has_enough_questionnaires())

        responsible_contribution = mommy.make(
                Contribution, course=course, contributor=mommy.make(UserProfile),
                responsible=True, can_edit=True, comment_visibility=Contribution.ALL_COMMENTS)
        course = Course.objects.get()
        self.assertFalse(course.has_enough_questionnaires())

        general_contribution = mommy.make(Contribution, course=course, contributor=None)
        course = Course.objects.get()  # refresh because of cached properties
        self.assertFalse(course.has_enough_questionnaires())

        q = mommy.make(Questionnaire)
        general_contribution.questionnaires.add(q)
        self.assertFalse(course.has_enough_questionnaires())

        responsible_contribution.questionnaires.add(q)
        self.assertTrue(course.has_enough_questionnaires())
