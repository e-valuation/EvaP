from django.test import TestCase
from django.core.cache import cache

from model_mommy import mommy

from evap.evaluation.tools import calculate_average_grades_and_deviation
from evap.evaluation.models import Course, UserProfile, Contribution, Questionnaire, CourseType, Semester, NotArchiveable


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


class ArchivingTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.semester = mommy.make(Semester)
        cls.course = mommy.make(Course, pk=7, state="published", semester=cls.semester)

        users = mommy.make(UserProfile, _quantity=3)
        cls.course.participants = users
        cls.course.voters = users[:2]

    def refresh_course(self):
        """ refresh_from_db does not work with courses"""
        self.course = self.semester.course_set.first()

    def setUp(self):
        self.semester.refresh_from_db()
        self.refresh_course()

    def test_counts_dont_change(self):
        """
            Asserts that course.num_voters course.num_participants don't change after archiving.
        """
        voter_count = self.course.num_voters
        participant_count = self.course.num_participants

        self.semester.archive()
        self.refresh_course()

        self.assertEqual(voter_count, self.course.num_voters)
        self.assertEqual(participant_count, self.course.num_participants)

    def test_participants_do_not_loose_courses(self):
        """
            Asserts that participants still participate in their courses after they get archived.
        """
        some_participant = self.course.participants.first()

        self.semester.archive()

        self.assertEqual(list(some_participant.courses_participating_in.all()), [self.course])

    def test_is_archived(self):
        """
            Tests whether is_archived returns True on archived semesters and courses.
        """
        self.assertFalse(self.course.is_archived)

        self.semester.archive()
        self.refresh_course()

        self.assertTrue(self.course.is_archived)

    def test_archiving_does_not_change_results(self):
        results = calculate_average_grades_and_deviation(self.course)

        self.semester.archive()
        self.refresh_course()
        cache.clear()

        self.assertEqual(calculate_average_grades_and_deviation(self.course), results)

    def test_archiving_twice_raises_exception(self):
        self.semester.archive()
        with self.assertRaises(NotArchiveable):
            self.semester.archive()
        with self.assertRaises(NotArchiveable):
            self.semester.course_set.first()._archive()

    def test_course_is_not_archived_if_participant_count_is_set(self):
        course = mommy.make(Course, state="published", _participant_count=1, _voter_count=1)
        self.assertFalse(course.is_archived)
        self.assertTrue(course.is_archiveable)

    def test_archiving_doesnt_change_single_results_participant_count(self):
        responsible = mommy.make(UserProfile)
        course = mommy.make(Course, state="published")
        contribution = mommy.make(Contribution, course=course, contributor=responsible, responsible=True)
        contribution.questionnaires.add(Questionnaire.get_single_result_questionnaire())
        self.assertTrue(course.is_single_result())

        course._participant_count = 5
        course._voter_count = 5
        course.save()

        course._archive()
        self.assertEqual(course._participant_count, 5)
        self.assertEqual(course._voter_count, 5)
