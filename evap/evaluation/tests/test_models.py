from datetime import datetime, timedelta, date
from unittest.mock import patch, Mock

from django.test import TestCase, override_settings
from django.core.cache import caches
from django.core import mail

from model_mommy import mommy

from evap.evaluation.models import (Contribution, Course, CourseType, EmailTemplate, NotArchiveable, Question,
                                    Questionnaire, RatingAnswerCounter, Semester, TextAnswer, UserProfile)
from evap.evaluation.tests.tools import WebTest
from evap.results.tools import calculate_average_distribution
from evap.results.views import get_course_result_template_fragment_cache_key


@override_settings(EVALUATION_END_OFFSET_HOURS=0)
class TestCourses(WebTest):
    def test_approved_to_in_evaluation(self):
        course = mommy.make(Course, state='approved', vote_start_datetime=datetime.now())

        with patch('evap.evaluation.models.EmailTemplate.send_to_users_in_courses') as mock:
            Course.update_courses()

        template = EmailTemplate.objects.get(name=EmailTemplate.EVALUATION_STARTED)
        mock.assert_called_once_with(template, [course], [EmailTemplate.ALL_PARTICIPANTS],
                                     use_cc=False, request=None)

        course = Course.objects.get(pk=course.pk)
        self.assertEqual(course.state, 'in_evaluation')

    def test_in_evaluation_to_evaluated(self):
        course = mommy.make(Course, state='in_evaluation', vote_start_datetime=datetime.now() - timedelta(days=2),
                            vote_end_date=date.today() - timedelta(days=1))

        with patch('evap.evaluation.models.Course.is_fully_reviewed') as mock:
            mock.__get__ = Mock(return_value=False)
            Course.update_courses()

        course = Course.objects.get(pk=course.pk)
        self.assertEqual(course.state, 'evaluated')

    def test_in_evaluation_to_reviewed(self):
        # Course is "fully reviewed" as no open text_answers are present by default,
        course = mommy.make(Course, state='in_evaluation', vote_start_datetime=datetime.now() - timedelta(days=2),
                            vote_end_date=date.today() - timedelta(days=1))

        Course.update_courses()

        course = Course.objects.get(pk=course.pk)
        self.assertEqual(course.state, 'reviewed')

    def test_in_evaluation_to_published(self):
        # Course is "fully reviewed" and not graded, thus gets published immediately.
        course = mommy.make(Course, state='in_evaluation', vote_start_datetime=datetime.now() - timedelta(days=2),
                            vote_end_date=date.today() - timedelta(days=1),
                            is_graded=False)

        with patch('evap.evaluation.tools.send_publish_notifications') as mock:
            Course.update_courses()

        mock.assert_called_once_with([course])

        course = Course.objects.get(pk=course.pk)
        self.assertEqual(course.state, 'published')

    @override_settings(EVALUATION_END_WARNING_PERIOD=24)
    def test_evaluation_ends_soon(self):
        course = mommy.make(Course, vote_start_datetime=datetime.now() - timedelta(days=2),
                            vote_end_date=date.today() + timedelta(hours=24))

        self.assertFalse(course.evaluation_ends_soon())

        course.vote_end_date = date.today()
        self.assertTrue(course.evaluation_ends_soon())

        course.vote_end_date = date.today() - timedelta(hours=48)
        self.assertFalse(course.evaluation_ends_soon())

    @override_settings(EVALUATION_END_WARNING_PERIOD=24, EVALUATION_END_OFFSET_HOURS=24)
    def test_evaluation_ends_soon_with_offset(self):
        course = mommy.make(Course, vote_start_datetime=datetime.now() - timedelta(days=2),
                            vote_end_date=date.today())

        self.assertFalse(course.evaluation_ends_soon())

        course.vote_end_date = date.today() - timedelta(hours=24)
        self.assertTrue(course.evaluation_ends_soon())

        course.vote_end_date = date.today() - timedelta(hours=72)
        self.assertFalse(course.evaluation_ends_soon())

    def test_evaluation_ended(self):
        # Course is out of evaluation period.
        mommy.make(Course, state='in_evaluation', vote_start_datetime=datetime.now() - timedelta(days=2),
                   vote_end_date=date.today() - timedelta(days=1), is_graded=False)
        # This course is not.
        mommy.make(Course, state='in_evaluation', vote_start_datetime=datetime.now() - timedelta(days=2),
                   vote_end_date=date.today(), is_graded=False)

        with patch('evap.evaluation.models.Course.evaluation_end') as mock:
            Course.update_courses()

        self.assertEqual(mock.call_count, 1)

    def test_approved_to_in_evaluation_sends_emails(self):
        """ Regression test for #945 """
        participant = mommy.make(UserProfile, email='foo@example.com')
        course = mommy.make(Course, state='approved', vote_start_datetime=datetime.now(), participants=[participant])

        Course.update_courses()

        course = Course.objects.get(pk=course.pk)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(course.state, 'in_evaluation')

    def test_has_enough_questionnaires(self):
        # manually circumvent Course's save() method to have a Course without a general contribution
        # the semester must be specified because of https://github.com/vandersonmota/model_mommy/issues/258
        Course.objects.bulk_create([mommy.prepare(Course, semester=mommy.make(Semester), type=mommy.make(CourseType))])
        course = Course.objects.get()
        self.assertEqual(course.contributions.count(), 0)
        self.assertFalse(course.general_contribution_has_questionnaires)
        self.assertFalse(course.all_contributions_have_questionnaires)

        responsible_contribution = mommy.make(
                Contribution, course=course, contributor=mommy.make(UserProfile),
                responsible=True, can_edit=True, comment_visibility=Contribution.ALL_COMMENTS)
        course = Course.objects.get()
        self.assertFalse(course.general_contribution_has_questionnaires)
        self.assertFalse(course.all_contributions_have_questionnaires)

        general_contribution = mommy.make(Contribution, course=course, contributor=None)
        course = Course.objects.get()
        self.assertFalse(course.general_contribution_has_questionnaires)
        self.assertFalse(course.all_contributions_have_questionnaires)

        questionnaire = mommy.make(Questionnaire)
        general_contribution.questionnaires.add(questionnaire)
        self.assertTrue(course.general_contribution_has_questionnaires)
        self.assertFalse(course.all_contributions_have_questionnaires)

        responsible_contribution.questionnaires.add(questionnaire)
        self.assertTrue(course.general_contribution_has_questionnaires)
        self.assertTrue(course.all_contributions_have_questionnaires)

    def test_deleting_last_modified_user_does_not_delete_course(self):
        user = mommy.make(UserProfile)
        course = mommy.make(Course, last_modified_user=user)
        user.delete()
        self.assertTrue(Course.objects.filter(pk=course.pk).exists())

    def test_responsible_contributors_ordering(self):
        course = mommy.make(Course)
        responsible1 = mommy.make(UserProfile)
        responsible2 = mommy.make(UserProfile)
        contribution1 = mommy.make(Contribution, course=course, contributor=responsible1, responsible=True, can_edit=True, comment_visibility=Contribution.ALL_COMMENTS, order=0)
        mommy.make(Contribution, course=course, contributor=responsible2, responsible=True, can_edit=True, comment_visibility=Contribution.ALL_COMMENTS, order=1)

        self.assertEqual(list(course.responsible_contributors), [responsible1, responsible2])

        contribution1.order = 2
        contribution1.save()

        course = Course.objects.get(pk=course.pk)
        self.assertEqual(list(course.responsible_contributors), [responsible2, responsible1])

    def test_single_result_can_be_deleted_only_in_reviewed(self):
        responsible = mommy.make(UserProfile)
        course = mommy.make(Course, semester=mommy.make(Semester), is_single_result=True)
        contribution = mommy.make(Contribution,
            course=course, contributor=responsible, responsible=True, can_edit=True, comment_visibility=Contribution.ALL_COMMENTS,
            questionnaires=[Questionnaire.single_result_questionnaire()]
        )
        mommy.make(RatingAnswerCounter, answer=1, count=1, question=Questionnaire.single_result_questionnaire().question_set.first(), contribution=contribution)
        course.single_result_created()
        course.publish()
        course.save()

        self.assertTrue(Course.objects.filter(pk=course.pk).exists())
        self.assertFalse(course.can_staff_delete)

        course.unpublish()
        self.assertTrue(course.can_staff_delete)

        RatingAnswerCounter.objects.filter(contribution__course=course).delete()
        course.delete()
        self.assertFalse(Course.objects.filter(pk=course.pk).exists())

    def test_single_result_can_be_published(self):
        """ Regression test for #1238 """
        responsible = mommy.make(UserProfile)
        single_result = mommy.make(Course,
            semester=mommy.make(Semester), is_single_result=True, _participant_count=5, _voter_count=5
        )
        contribution = mommy.make(Contribution,
            course=single_result, contributor=responsible, responsible=True, can_edit=True, comment_visibility=Contribution.ALL_COMMENTS,
            questionnaires=[Questionnaire.single_result_questionnaire()]
        )
        mommy.make(RatingAnswerCounter, answer=1, count=1, question=Questionnaire.single_result_questionnaire().question_set.first(), contribution=contribution)

        single_result.single_result_created()
        single_result.publish()  # used to crash

    def test_adding_second_voter_sets_can_publish_text_results_to_true(self):
        student1 = mommy.make(UserProfile)
        student2 = mommy.make(UserProfile)
        course = mommy.make(Course, participants=[student1, student2], voters=[student1], state="in_evaluation")
        course.save()
        top_course_questionnaire = mommy.make(Questionnaire, type=Questionnaire.TOP)
        mommy.make(Question, questionnaire=top_course_questionnaire, type="L")
        course.general_contribution.questionnaires.set([top_course_questionnaire])

        self.assertFalse(course.can_publish_text_results)

        self.let_user_vote_for_course(student2, course)
        course = Course.objects.get(pk=course.pk)

        self.assertTrue(course.can_publish_text_results)

    def test_text_answers_get_deleted_if_they_cannot_be_published(self):
        student = mommy.make(UserProfile)
        course = mommy.make(Course, state='reviewed', participants=[student], voters=[student], can_publish_text_results=False)
        questionnaire = mommy.make(Questionnaire, type=Questionnaire.TOP)
        question = mommy.make(Question, type="T", questionnaire=questionnaire)
        course.general_contribution.questionnaires.set([questionnaire])
        mommy.make(TextAnswer, question=question, contribution=course.general_contribution)

        self.assertEqual(course.textanswer_set.count(), 1)
        course.publish()
        self.assertEqual(course.textanswer_set.count(), 0)

    def test_text_answers_do_not_get_deleted_if_they_can_be_published(self):
        student = mommy.make(UserProfile)
        student2 = mommy.make(UserProfile)
        course = mommy.make(Course, state='reviewed', participants=[student, student2], voters=[student, student2], can_publish_text_results=True)
        questionnaire = mommy.make(Questionnaire, type=Questionnaire.TOP)
        question = mommy.make(Question, type="T", questionnaire=questionnaire)
        course.general_contribution.questionnaires.set([questionnaire])
        mommy.make(TextAnswer, question=question, contribution=course.general_contribution)

        self.assertEqual(course.textanswer_set.count(), 1)
        course.publish()
        self.assertEqual(course.textanswer_set.count(), 1)

    def test_hidden_text_answers_get_deleted_on_publish(self):
        student = mommy.make(UserProfile)
        student2 = mommy.make(UserProfile)
        course = mommy.make(Course, state='reviewed', participants=[student, student2], voters=[student, student2], can_publish_text_results=True)
        questionnaire = mommy.make(Questionnaire, type=Questionnaire.TOP)
        question = mommy.make(Question, type="T", questionnaire=questionnaire)
        course.general_contribution.questionnaires.set([questionnaire])
        mommy.make(TextAnswer, question=question, contribution=course.general_contribution, answer="hidden", state=TextAnswer.HIDDEN)
        mommy.make(TextAnswer, question=question, contribution=course.general_contribution, answer="published", state=TextAnswer.PUBLISHED)
        mommy.make(TextAnswer, question=question, contribution=course.general_contribution, answer="private", state=TextAnswer.PRIVATE)

        self.assertEqual(course.textanswer_set.count(), 3)
        course.publish()
        self.assertEqual(course.textanswer_set.count(), 2)
        self.assertFalse(TextAnswer.objects.filter(answer="hidden").exists())

    def test_original_text_answers_get_deleted_on_publish(self):
        student = mommy.make(UserProfile)
        student2 = mommy.make(UserProfile)
        course = mommy.make(Course, state='reviewed', participants=[student, student2], voters=[student, student2], can_publish_text_results=True)
        questionnaire = mommy.make(Questionnaire, type=Questionnaire.TOP)
        question = mommy.make(Question, type="T", questionnaire=questionnaire)
        course.general_contribution.questionnaires.set([questionnaire])
        mommy.make(TextAnswer, question=question, contribution=course.general_contribution, answer="published answer", original_answer="original answer", state=TextAnswer.PUBLISHED)

        self.assertEqual(course.textanswer_set.count(), 1)
        self.assertFalse(TextAnswer.objects.get().original_answer is None)
        course.publish()
        self.assertEqual(course.textanswer_set.count(), 1)
        self.assertTrue(TextAnswer.objects.get().original_answer is None)

    def test_publishing_and_unpublishing_effect_on_template_cache(self):
        student = mommy.make(UserProfile)
        course = mommy.make(Course, state='reviewed', participants=[student], voters=[student], can_publish_text_results=True)

        self.assertIsNone(caches['results'].get(get_course_result_template_fragment_cache_key(course.id, "en", True)))
        self.assertIsNone(caches['results'].get(get_course_result_template_fragment_cache_key(course.id, "en", False)))
        self.assertIsNone(caches['results'].get(get_course_result_template_fragment_cache_key(course.id, "de", True)))
        self.assertIsNone(caches['results'].get(get_course_result_template_fragment_cache_key(course.id, "de", False)))

        course.publish()

        self.assertIsNotNone(caches['results'].get(get_course_result_template_fragment_cache_key(course.id, "en", True)))
        self.assertIsNotNone(caches['results'].get(get_course_result_template_fragment_cache_key(course.id, "en", False)))
        self.assertIsNotNone(caches['results'].get(get_course_result_template_fragment_cache_key(course.id, "de", True)))
        self.assertIsNotNone(caches['results'].get(get_course_result_template_fragment_cache_key(course.id, "de", False)))

        course.unpublish()

        self.assertIsNone(caches['results'].get(get_course_result_template_fragment_cache_key(course.id, "en", True)))
        self.assertIsNone(caches['results'].get(get_course_result_template_fragment_cache_key(course.id, "en", False)))
        self.assertIsNone(caches['results'].get(get_course_result_template_fragment_cache_key(course.id, "de", True)))
        self.assertIsNone(caches['results'].get(get_course_result_template_fragment_cache_key(course.id, "de", False)))


class TestUserProfile(TestCase):

    def test_is_student(self):
        some_user = mommy.make(UserProfile)
        self.assertFalse(some_user.is_student)

        student = mommy.make(UserProfile, courses_participating_in=[mommy.make(Course)])
        self.assertTrue(student.is_student)

        contributor = mommy.make(UserProfile, contributions=[mommy.make(Contribution)])
        self.assertFalse(contributor.is_student)

        semester_contributed_to = mommy.make(Semester, created_at=date.today())
        semester_participated_in = mommy.make(Semester, created_at=date.today())
        course_contributed_to = mommy.make(Course, semester=semester_contributed_to)
        course_participated_in = mommy.make(Course, semester=semester_participated_in)
        contribution = mommy.make(Contribution, course=course_contributed_to)
        user = mommy.make(UserProfile, contributions=[contribution], courses_participating_in=[course_participated_in])

        self.assertTrue(user.is_student)

        semester_contributed_to.created_at = date.today() - timedelta(days=1)
        semester_contributed_to.save()

        self.assertTrue(user.is_student)

        semester_participated_in.created_at = date.today() - timedelta(days=2)
        semester_participated_in.save()

        self.assertFalse(user.is_student)

    def test_can_staff_delete(self):
        user = mommy.make(UserProfile)
        mommy.make(Course, participants=[user], state="new")
        self.assertFalse(user.can_staff_delete)

        user2 = mommy.make(UserProfile)
        mommy.make(Course, participants=[user2], state="in_evaluation")
        self.assertFalse(user2.can_staff_delete)

        contributor = mommy.make(UserProfile)
        mommy.make(Contribution, contributor=contributor)
        self.assertFalse(contributor.can_staff_delete)

    def test_inactive_users_hidden(self):
        active_user = mommy.make(UserProfile)
        mommy.make(UserProfile, is_active=False)

        self.assertEqual(list(UserProfile.objects.exclude_inactive_users().all()), [active_user])

    def test_inactive_users_shown(self):
        active_user = mommy.make(UserProfile)
        inactive_user = mommy.make(UserProfile, is_active=False)

        user_list = list(UserProfile.objects.all())
        self.assertIn(active_user, user_list)
        self.assertIn(inactive_user, user_list)


class ParticipationArchivingTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.semester = mommy.make(Semester)
        cls.course = mommy.make(Course, state="published", semester=cls.semester)
        cls.course.general_contribution.questionnaires.set([mommy.make(Questionnaire)])

        users = mommy.make(UserProfile, _quantity=3)
        cls.course.participants.set(users)
        cls.course.voters.set(users[:2])

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

        self.semester.archive_participations()
        self.refresh_course()

        self.assertEqual(voter_count, self.course.num_voters)
        self.assertEqual(participant_count, self.course.num_participants)

    def test_participants_do_not_loose_courses(self):
        """
            Asserts that participants still participate in their courses after the participations get archived.
        """
        some_participant = self.course.participants.first()

        self.semester.archive_participations()

        self.assertEqual(list(some_participant.courses_participating_in.all()), [self.course])

    def test_participations_are_archived(self):
        """
            Tests whether participations_are_archived returns True on semesters and courses with archived participations.
        """
        self.assertFalse(self.course.participations_are_archived)

        self.semester.archive_participations()
        self.refresh_course()

        self.assertTrue(self.course.participations_are_archived)

    def test_archiving_participations_does_not_change_results(self):
        distribution = calculate_average_distribution(self.course)

        self.semester.archive_participations()
        self.refresh_course()
        caches['results'].clear()

        new_distribution = calculate_average_distribution(self.course)
        self.assertEqual(new_distribution, distribution)

    def test_archiving_participations_twice_raises_exception(self):
        self.semester.archive_participations()
        with self.assertRaises(NotArchiveable):
            self.semester.archive_participations()
        with self.assertRaises(NotArchiveable):
            self.semester.course_set.first()._archive_participations()

    def test_course_participations_are_not_archived_if_participant_count_is_set(self):
        course = mommy.make(Course, state="published", _participant_count=1, _voter_count=1)
        self.assertFalse(course.participations_are_archived)
        self.assertTrue(course.participations_can_be_archived)

    def test_archiving_participations_doesnt_change_single_results_participant_count(self):
        responsible = mommy.make(UserProfile)
        course = mommy.make(Course,
            state="published", is_single_result=True, _participant_count=5, _voter_count=5
        )
        contribution = mommy.make(Contribution, course=course, contributor=responsible, responsible=True, can_edit=True, comment_visibility=Contribution.ALL_COMMENTS)
        contribution.questionnaires.add(Questionnaire.single_result_questionnaire())

        course.semester.archive_participations()
        course = Course.objects.get(pk=course.pk)
        self.assertEqual(course._participant_count, 5)
        self.assertEqual(course._voter_count, 5)


class TestLoginUrlEmail(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.other_user = mommy.make(UserProfile, email="other@extern.com")
        cls.user = mommy.make(UserProfile, email="extern@extern.com")
        cls.user.ensure_valid_login_key()

        cls.course = mommy.make(Course)
        mommy.make(Contribution, course=cls.course, contributor=cls.user, responsible=True, can_edit=True, comment_visibility=Contribution.ALL_COMMENTS)

        cls.template = mommy.make(EmailTemplate, body="{{ login_url }}")

        EmailTemplate.objects.filter(name="Login Key Created").update(body="{{ user.login_url }}")

    def test_no_login_url_when_delegates_in_cc(self):
        self.user.delegates.add(self.other_user)
        EmailTemplate.send_to_users_in_courses(self.template, [self.course], EmailTemplate.CONTRIBUTORS, use_cc=True, request=None)
        self.assertEqual(len(mail.outbox), 2)
        self.assertFalse("loginkey" in mail.outbox[0].body)  # message does not contain the login url
        self.assertTrue("loginkey" in mail.outbox[1].body)  # separate email with login url was sent
        self.assertEqual(len(mail.outbox[1].cc), 0)
        self.assertEqual(mail.outbox[1].to, [self.user.email])

    def test_no_login_url_when_cc_users_in_cc(self):
        self.user.cc_users.add(self.other_user)
        EmailTemplate.send_to_users_in_courses(self.template, [self.course], [EmailTemplate.CONTRIBUTORS], use_cc=True, request=None)
        self.assertEqual(len(mail.outbox), 2)
        self.assertFalse("loginkey" in mail.outbox[0].body)  # message does not contain the login url
        self.assertTrue("loginkey" in mail.outbox[1].body)  # separate email with login url was sent
        self.assertEqual(len(mail.outbox[1].cc), 0)
        self.assertEqual(mail.outbox[1].to, [self.user.email])

    def test_login_url_when_nobody_in_cc(self):
        # message is not sent to others in cc
        EmailTemplate.send_to_users_in_courses(self.template, [self.course], [EmailTemplate.CONTRIBUTORS], use_cc=True, request=None)
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue("loginkey" in mail.outbox[0].body)  # message does contain the login url

    def test_login_url_when_use_cc_is_false(self):
        # message is not sent to others in cc
        self.user.delegates.add(self.other_user)
        EmailTemplate.send_to_users_in_courses(self.template, [self.course], [EmailTemplate.CONTRIBUTORS], use_cc=False, request=None)
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue("loginkey" in mail.outbox[0].body)  # message does contain the login url


class TestEmailTemplate(TestCase):
    def test_missing_email_address(self):
        """
        Tests that __send_to_user behaves when the user has no email address.
        Regression test to https://github.com/fsr-itse/EvaP/issues/825
        """
        user = mommy.make(UserProfile, email=None)
        template = EmailTemplate.objects.get(name=EmailTemplate.STUDENT_REMINDER)
        EmailTemplate.send_to_user(user, template, {}, {}, False, None)


class TestEmailRecipientList(TestCase):
    def test_recipient_list(self):
        course = mommy.make(Course)
        responsible = mommy.make(UserProfile)
        editor = mommy.make(UserProfile)
        contributor = mommy.make(UserProfile)
        mommy.make(Contribution, course=course, contributor=responsible, responsible=True, can_edit=True, comment_visibility=Contribution.ALL_COMMENTS)
        mommy.make(Contribution, course=course, contributor=editor, can_edit=True)
        mommy.make(Contribution, course=course, contributor=contributor)

        participant1 = mommy.make(UserProfile, courses_participating_in=[course])
        participant2 = mommy.make(UserProfile, courses_participating_in=[course])
        course.voters.set([participant1])

        recipient_list = EmailTemplate.recipient_list_for_course(course, [], filter_users_in_cc=False)
        self.assertCountEqual(recipient_list, [])

        recipient_list = EmailTemplate.recipient_list_for_course(course, [EmailTemplate.RESPONSIBLE], filter_users_in_cc=False)
        self.assertCountEqual(recipient_list, [responsible])

        recipient_list = EmailTemplate.recipient_list_for_course(course, [EmailTemplate.EDITORS], filter_users_in_cc=False)
        self.assertCountEqual(recipient_list, [responsible, editor])

        recipient_list = EmailTemplate.recipient_list_for_course(course, [EmailTemplate.CONTRIBUTORS], filter_users_in_cc=False)
        self.assertCountEqual(recipient_list, [responsible, editor, contributor])

        recipient_list = EmailTemplate.recipient_list_for_course(course, [EmailTemplate.ALL_PARTICIPANTS], filter_users_in_cc=False)
        self.assertCountEqual(recipient_list, [participant1, participant2])

        recipient_list = EmailTemplate.recipient_list_for_course(course, [EmailTemplate.DUE_PARTICIPANTS], filter_users_in_cc=False)
        self.assertCountEqual(recipient_list, [participant2])

    def test_recipient_list_filtering(self):
        course = mommy.make(Course)

        contributor1 = mommy.make(UserProfile)
        contributor2 = mommy.make(UserProfile, delegates=[contributor1])

        mommy.make(Contribution, course=course, contributor=contributor1)
        mommy.make(Contribution, course=course, contributor=contributor2)

        # no-one should get filtered.
        recipient_list = EmailTemplate.recipient_list_for_course(course, [EmailTemplate.CONTRIBUTORS], filter_users_in_cc=False)
        self.assertCountEqual(recipient_list, [contributor1, contributor2])

        # contributor1 is in cc of contributor2 and gets filtered.
        recipient_list = EmailTemplate.recipient_list_for_course(course, [EmailTemplate.CONTRIBUTORS], filter_users_in_cc=True)
        self.assertCountEqual(recipient_list, [contributor2])

        contributor3 = mommy.make(UserProfile, delegates=[contributor2])
        mommy.make(Contribution, course=course, contributor=contributor3)

        # again, no-one should get filtered.
        recipient_list = EmailTemplate.recipient_list_for_course(course, [EmailTemplate.CONTRIBUTORS], filter_users_in_cc=False)
        self.assertCountEqual(recipient_list, [contributor1, contributor2, contributor3])

        # contributor1 is in cc of contributor2 and gets filtered.
        # contributor2 is in cc of contributor3 but is not filtered since contributor1 wouldn't get an email at all then.
        recipient_list = EmailTemplate.recipient_list_for_course(course, [EmailTemplate.CONTRIBUTORS], filter_users_in_cc=True)
        self.assertCountEqual(recipient_list, [contributor2, contributor3])
