from datetime import datetime, timedelta, date
from unittest.mock import patch, Mock

from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.core.cache import caches
from django.core import mail

from django_webtest import WebTest
from model_mommy import mommy

from evap.evaluation.models import (Contribution, Course, CourseType, EmailTemplate, Evaluation, NotArchiveable,
                                    Question, Questionnaire, RatingAnswerCounter, Semester, TextAnswer, UserProfile)
from evap.evaluation.tests.tools import let_user_vote_for_evaluation
from evap.results.tools import calculate_average_distribution
from evap.results.views import get_evaluation_result_template_fragment_cache_key


@override_settings(EVALUATION_END_OFFSET_HOURS=0)
class TestEvaluations(WebTest):
    def test_approved_to_in_evaluation(self):
        evaluation = mommy.make(Evaluation, state='approved', vote_start_datetime=datetime.now())

        with patch('evap.evaluation.models.EmailTemplate.send_to_users_in_evaluations') as mock:
            Evaluation.update_evaluations()

        template = EmailTemplate.objects.get(name=EmailTemplate.EVALUATION_STARTED)
        mock.assert_called_once_with(template, [evaluation], [EmailTemplate.ALL_PARTICIPANTS],
                                     use_cc=False, request=None)

        evaluation = Evaluation.objects.get(pk=evaluation.pk)
        self.assertEqual(evaluation.state, 'in_evaluation')

    def test_in_evaluation_to_evaluated(self):
        evaluation = mommy.make(Evaluation, state='in_evaluation', vote_start_datetime=datetime.now() - timedelta(days=2),
                            vote_end_date=date.today() - timedelta(days=1))

        with patch('evap.evaluation.models.Evaluation.is_fully_reviewed') as mock:
            mock.__get__ = Mock(return_value=False)
            Evaluation.update_evaluations()

        evaluation = Evaluation.objects.get(pk=evaluation.pk)
        self.assertEqual(evaluation.state, 'evaluated')

    def test_in_evaluation_to_reviewed(self):
        # Evaluation is "fully reviewed" as no open text answers are present by default.
        evaluation = mommy.make(Evaluation, state='in_evaluation', vote_start_datetime=datetime.now() - timedelta(days=2),
                            vote_end_date=date.today() - timedelta(days=1))

        Evaluation.update_evaluations()

        evaluation = Evaluation.objects.get(pk=evaluation.pk)
        self.assertEqual(evaluation.state, 'reviewed')

    def test_in_evaluation_to_published(self):
        # Evaluation is "fully reviewed" and not graded, thus gets published immediately.
        course = mommy.make(Course, is_graded=False)
        evaluation = mommy.make(Evaluation, course=course, state='in_evaluation', vote_start_datetime=datetime.now() - timedelta(days=2),
                            vote_end_date=date.today() - timedelta(days=1))

        with patch('evap.evaluation.tools.send_publish_notifications') as mock:
            Evaluation.update_evaluations()

        mock.assert_called_once_with([evaluation])

        evaluation = Evaluation.objects.get(pk=evaluation.pk)
        self.assertEqual(evaluation.state, 'published')

    @override_settings(EVALUATION_END_WARNING_PERIOD=24)
    def test_evaluation_ends_soon(self):
        evaluation = mommy.make(Evaluation, vote_start_datetime=datetime.now() - timedelta(days=2),
                            vote_end_date=date.today() + timedelta(hours=24))

        self.assertFalse(evaluation.evaluation_ends_soon())

        evaluation.vote_end_date = date.today()
        self.assertTrue(evaluation.evaluation_ends_soon())

        evaluation.vote_end_date = date.today() - timedelta(hours=48)
        self.assertFalse(evaluation.evaluation_ends_soon())

    @override_settings(EVALUATION_END_WARNING_PERIOD=24, EVALUATION_END_OFFSET_HOURS=24)
    def test_evaluation_ends_soon_with_offset(self):
        evaluation = mommy.make(Evaluation, vote_start_datetime=datetime.now() - timedelta(days=2),
                            vote_end_date=date.today())

        self.assertFalse(evaluation.evaluation_ends_soon())

        evaluation.vote_end_date = date.today() - timedelta(hours=24)
        self.assertTrue(evaluation.evaluation_ends_soon())

        evaluation.vote_end_date = date.today() - timedelta(hours=72)
        self.assertFalse(evaluation.evaluation_ends_soon())

    def test_evaluation_ended(self):
        # Evaluation is out of evaluation period.
        course_1 = mommy.make(Course, is_graded=False)
        course_2 = mommy.make(Course, is_graded=False)
        mommy.make(Evaluation, course=course_1, state='in_evaluation', vote_start_datetime=datetime.now() - timedelta(days=2),
                   vote_end_date=date.today() - timedelta(days=1))
        # This evaluation is not.
        mommy.make(Evaluation, course=course_2, state='in_evaluation', vote_start_datetime=datetime.now() - timedelta(days=2),
                   vote_end_date=date.today())

        with patch('evap.evaluation.models.Evaluation.evaluation_end') as mock:
            Evaluation.update_evaluations()

        self.assertEqual(mock.call_count, 1)

    def test_approved_to_in_evaluation_sends_emails(self):
        """ Regression test for #945 """
        participant = mommy.make(UserProfile, email='foo@example.com')
        evaluation = mommy.make(Evaluation, state='approved', vote_start_datetime=datetime.now(), participants=[participant])

        Evaluation.update_evaluations()

        evaluation = Evaluation.objects.get(pk=evaluation.pk)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(evaluation.state, 'in_evaluation')

    def test_has_enough_questionnaires(self):
        # manually circumvent Evaluation's save() method to have a Evaluation without a general contribution
        # the semester must be specified because of https://github.com/vandersonmota/model_mommy/issues/258
        course = mommy.make(Course, semester=mommy.make(Semester), type=mommy.make(CourseType))
        Evaluation.objects.bulk_create([mommy.prepare(Evaluation, course=course)])
        evaluation = Evaluation.objects.get()
        self.assertEqual(evaluation.contributions.count(), 0)
        self.assertFalse(evaluation.general_contribution_has_questionnaires)
        self.assertFalse(evaluation.all_contributions_have_questionnaires)

        editor_contribution = mommy.make(
                Contribution, evaluation=evaluation, contributor=mommy.make(UserProfile),
                can_edit=True, textanswer_visibility=Contribution.GENERAL_TEXTANSWERS)
        evaluation = Evaluation.objects.get()
        self.assertFalse(evaluation.general_contribution_has_questionnaires)
        self.assertFalse(evaluation.all_contributions_have_questionnaires)

        general_contribution = mommy.make(Contribution, evaluation=evaluation, contributor=None)
        evaluation = Evaluation.objects.get()
        self.assertFalse(evaluation.general_contribution_has_questionnaires)
        self.assertFalse(evaluation.all_contributions_have_questionnaires)

        questionnaire = mommy.make(Questionnaire)
        general_contribution.questionnaires.add(questionnaire)
        self.assertTrue(evaluation.general_contribution_has_questionnaires)
        self.assertFalse(evaluation.all_contributions_have_questionnaires)

        editor_contribution.questionnaires.add(questionnaire)
        self.assertTrue(evaluation.general_contribution_has_questionnaires)
        self.assertTrue(evaluation.all_contributions_have_questionnaires)

    def test_deleting_last_modified_user_does_not_delete_evaluation(self):
        user = mommy.make(UserProfile)
        evaluation = mommy.make(Evaluation, last_modified_user=user)
        user.delete()
        self.assertTrue(Evaluation.objects.filter(pk=evaluation.pk).exists())

    def test_single_result_can_be_deleted_only_in_reviewed(self):
        responsible = mommy.make(UserProfile)
        evaluation = mommy.make(Evaluation, is_single_result=True)
        contribution = mommy.make(Contribution,
            evaluation=evaluation, contributor=responsible, can_edit=True, textanswer_visibility=Contribution.GENERAL_TEXTANSWERS,
            questionnaires=[Questionnaire.single_result_questionnaire()]
        )
        mommy.make(RatingAnswerCounter, answer=1, count=1, question=Questionnaire.single_result_questionnaire().questions.first(), contribution=contribution)
        evaluation.single_result_created()
        evaluation.publish()
        evaluation.save()

        self.assertTrue(Evaluation.objects.filter(pk=evaluation.pk).exists())
        self.assertFalse(evaluation.can_be_deleted_by_manager)

        evaluation.unpublish()
        self.assertTrue(evaluation.can_be_deleted_by_manager)

        RatingAnswerCounter.objects.filter(contribution__evaluation=evaluation).delete()
        evaluation.delete()
        self.assertFalse(Evaluation.objects.filter(pk=evaluation.pk).exists())

    def test_single_result_can_be_published(self):
        """ Regression test for #1238 """
        responsible = mommy.make(UserProfile)
        single_result = mommy.make(Evaluation, is_single_result=True, _participant_count=5, _voter_count=5)
        contribution = mommy.make(Contribution,
            evaluation=single_result, contributor=responsible, can_edit=True, textanswer_visibility=Contribution.GENERAL_TEXTANSWERS,
            questionnaires=[Questionnaire.single_result_questionnaire()]
        )
        mommy.make(RatingAnswerCounter, answer=1, count=1, question=Questionnaire.single_result_questionnaire().questions.first(), contribution=contribution)

        single_result.single_result_created()
        single_result.publish()  # used to crash

    def test_adding_second_voter_sets_can_publish_text_results_to_true(self):
        student1 = mommy.make(UserProfile)
        student2 = mommy.make(UserProfile)
        evaluation = mommy.make(Evaluation, participants=[student1, student2], voters=[student1], state="in_evaluation")
        evaluation.save()
        top_general_questionnaire = mommy.make(Questionnaire, type=Questionnaire.TOP)
        mommy.make(Question, questionnaire=top_general_questionnaire, type=Question.LIKERT)
        evaluation.general_contribution.questionnaires.set([top_general_questionnaire])

        self.assertFalse(evaluation.can_publish_text_results)

        let_user_vote_for_evaluation(self.app, student2, evaluation)
        evaluation = Evaluation.objects.get(pk=evaluation.pk)

        self.assertTrue(evaluation.can_publish_text_results)

    def test_textanswers_get_deleted_if_they_cannot_be_published(self):
        student = mommy.make(UserProfile)
        evaluation = mommy.make(Evaluation, state='reviewed', participants=[student], voters=[student], can_publish_text_results=False)
        questionnaire = mommy.make(Questionnaire, type=Questionnaire.TOP)
        question = mommy.make(Question, type=Question.TEXT, questionnaire=questionnaire)
        evaluation.general_contribution.questionnaires.set([questionnaire])
        mommy.make(TextAnswer, question=question, contribution=evaluation.general_contribution)

        self.assertEqual(evaluation.textanswer_set.count(), 1)
        evaluation.publish()
        self.assertEqual(evaluation.textanswer_set.count(), 0)

    def test_textanswers_do_not_get_deleted_if_they_can_be_published(self):
        student = mommy.make(UserProfile)
        student2 = mommy.make(UserProfile)
        evaluation = mommy.make(Evaluation, state='reviewed', participants=[student, student2], voters=[student, student2], can_publish_text_results=True)
        questionnaire = mommy.make(Questionnaire, type=Questionnaire.TOP)
        question = mommy.make(Question, type=Question.TEXT, questionnaire=questionnaire)
        evaluation.general_contribution.questionnaires.set([questionnaire])
        mommy.make(TextAnswer, question=question, contribution=evaluation.general_contribution)

        self.assertEqual(evaluation.textanswer_set.count(), 1)
        evaluation.publish()
        self.assertEqual(evaluation.textanswer_set.count(), 1)

    def test_hidden_textanswers_get_deleted_on_publish(self):
        student = mommy.make(UserProfile)
        student2 = mommy.make(UserProfile)
        evaluation = mommy.make(Evaluation, state='reviewed', participants=[student, student2], voters=[student, student2], can_publish_text_results=True)
        questionnaire = mommy.make(Questionnaire, type=Questionnaire.TOP)
        question = mommy.make(Question, type=Question.TEXT, questionnaire=questionnaire)
        evaluation.general_contribution.questionnaires.set([questionnaire])
        mommy.make(TextAnswer, question=question, contribution=evaluation.general_contribution, answer="hidden", state=TextAnswer.HIDDEN)
        mommy.make(TextAnswer, question=question, contribution=evaluation.general_contribution, answer="published", state=TextAnswer.PUBLISHED)
        mommy.make(TextAnswer, question=question, contribution=evaluation.general_contribution, answer="private", state=TextAnswer.PRIVATE)

        self.assertEqual(evaluation.textanswer_set.count(), 3)
        evaluation.publish()
        self.assertEqual(evaluation.textanswer_set.count(), 2)
        self.assertFalse(TextAnswer.objects.filter(answer="hidden").exists())

    def test_original_textanswers_get_deleted_on_publish(self):
        student = mommy.make(UserProfile)
        student2 = mommy.make(UserProfile)
        evaluation = mommy.make(Evaluation, state='reviewed', participants=[student, student2], voters=[student, student2], can_publish_text_results=True)
        questionnaire = mommy.make(Questionnaire, type=Questionnaire.TOP)
        question = mommy.make(Question, type=Question.TEXT, questionnaire=questionnaire)
        evaluation.general_contribution.questionnaires.set([questionnaire])
        mommy.make(TextAnswer, question=question, contribution=evaluation.general_contribution, answer="published answer", original_answer="original answer", state=TextAnswer.PUBLISHED)

        self.assertEqual(evaluation.textanswer_set.count(), 1)
        self.assertFalse(TextAnswer.objects.get().original_answer is None)
        evaluation.publish()
        self.assertEqual(evaluation.textanswer_set.count(), 1)
        self.assertTrue(TextAnswer.objects.get().original_answer is None)

    def test_publishing_and_unpublishing_effect_on_template_cache(self):
        student = mommy.make(UserProfile)
        evaluation = mommy.make(Evaluation, state='reviewed', participants=[student], voters=[student], can_publish_text_results=True)

        self.assertIsNone(caches['results'].get(get_evaluation_result_template_fragment_cache_key(evaluation.id, "en", True)))
        self.assertIsNone(caches['results'].get(get_evaluation_result_template_fragment_cache_key(evaluation.id, "en", False)))
        self.assertIsNone(caches['results'].get(get_evaluation_result_template_fragment_cache_key(evaluation.id, "de", True)))
        self.assertIsNone(caches['results'].get(get_evaluation_result_template_fragment_cache_key(evaluation.id, "de", False)))

        evaluation.publish()
        evaluation.save()

        self.assertIsNotNone(caches['results'].get(get_evaluation_result_template_fragment_cache_key(evaluation.id, "en", True)))
        self.assertIsNotNone(caches['results'].get(get_evaluation_result_template_fragment_cache_key(evaluation.id, "en", False)))
        self.assertIsNotNone(caches['results'].get(get_evaluation_result_template_fragment_cache_key(evaluation.id, "de", True)))
        self.assertIsNotNone(caches['results'].get(get_evaluation_result_template_fragment_cache_key(evaluation.id, "de", False)))

        evaluation.unpublish()
        evaluation.save()

        self.assertIsNone(caches['results'].get(get_evaluation_result_template_fragment_cache_key(evaluation.id, "en", True)))
        self.assertIsNone(caches['results'].get(get_evaluation_result_template_fragment_cache_key(evaluation.id, "en", False)))
        self.assertIsNone(caches['results'].get(get_evaluation_result_template_fragment_cache_key(evaluation.id, "de", True)))
        self.assertIsNone(caches['results'].get(get_evaluation_result_template_fragment_cache_key(evaluation.id, "de", False)))


class TestCourse(TestCase):
    def test_can_be_deleted_by_manager(self):
        course = mommy.make(Course)
        evaluation = mommy.make(Evaluation, course=course)
        self.assertFalse(course.can_be_deleted_by_manager)

        evaluation.delete()
        self.assertTrue(course.can_be_deleted_by_manager)

    def test_responsibles_names(self):
        # last names required for sorting
        user1 = mommy.make(UserProfile, last_name="Doe")
        user2 = mommy.make(UserProfile, last_name="Meyer")
        course = mommy.make(Course, responsibles=[user1, user2])
        self.assertEqual(course.responsibles_names, ("{}, {}").format(user1.full_name, user2.full_name))


class TestUserProfile(TestCase):
    def test_is_student(self):
        some_user = mommy.make(UserProfile)
        self.assertFalse(some_user.is_student)

        student = mommy.make(UserProfile, evaluations_participating_in=[mommy.make(Evaluation)])
        self.assertTrue(student.is_student)

        contributor = mommy.make(UserProfile, contributions=[mommy.make(Contribution)])
        self.assertFalse(contributor.is_student)

        semester_contributed_to = mommy.make(Semester, created_at=date.today())
        semester_participated_in = mommy.make(Semester, created_at=date.today())
        course_contributed_to = mommy.make(Course, semester=semester_contributed_to)
        course_participated_in = mommy.make(Course, semester=semester_participated_in)
        evaluation_contributed_to = mommy.make(Evaluation, course=course_contributed_to)
        evaluation_participated_in = mommy.make(Evaluation, course=course_participated_in)
        contribution = mommy.make(Contribution, evaluation=evaluation_contributed_to)
        user = mommy.make(UserProfile, contributions=[contribution], evaluations_participating_in=[evaluation_participated_in])

        self.assertTrue(user.is_student)

        semester_contributed_to.created_at = date.today() - timedelta(days=1)
        semester_contributed_to.save()

        self.assertTrue(user.is_student)

        semester_participated_in.created_at = date.today() - timedelta(days=2)
        semester_participated_in.save()

        self.assertFalse(user.is_student)

    def test_can_be_deleted_by_manager(self):
        user = mommy.make(UserProfile)
        mommy.make(Evaluation, participants=[user], state="new")
        self.assertFalse(user.can_be_deleted_by_manager)

        user2 = mommy.make(UserProfile)
        mommy.make(Evaluation, participants=[user2], state="in_evaluation")
        self.assertFalse(user2.can_be_deleted_by_manager)

        contributor = mommy.make(UserProfile)
        mommy.make(Contribution, contributor=contributor)
        self.assertFalse(contributor.can_be_deleted_by_manager)

        proxy_user = mommy.make(UserProfile, is_proxy_user=True)
        self.assertFalse(proxy_user.can_be_deleted_by_manager)

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

    def test_can_be_marked_inactive_by_manager(self):
        user = mommy.make(UserProfile)
        mommy.make(Evaluation, participants=[user], state="new")
        self.assertFalse(user.can_be_marked_inactive_by_manager)

        contributor = mommy.make(UserProfile)
        mommy.make(Contribution, contributor=contributor)
        self.assertFalse(contributor.can_be_marked_inactive_by_manager)

        user2 = mommy.make(UserProfile, groups=[Group.objects.get(name="Reviewer")])
        self.assertFalse(user2.can_be_marked_inactive_by_manager)
        user2.groups.set([Group.objects.get(name="Grade publisher")])
        user2.save()
        self.assertFalse(user2.can_be_marked_inactive_by_manager)

        super_user = mommy.make(UserProfile, is_super_user=True)
        self.assertFalse(super_user.can_be_marked_inactive_by_manager)

        proxy_user = mommy.make(UserProfile, is_proxy_user=True)
        self.assertFalse(proxy_user.can_be_marked_inactive_by_manager)


class ParticipationArchivingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.semester = mommy.make(Semester)
        cls.evaluation = mommy.make(Evaluation, state="published", course=mommy.make(Course, semester=cls.semester))
        cls.evaluation.general_contribution.questionnaires.set([mommy.make(Questionnaire)])

        users = mommy.make(UserProfile, _quantity=3)
        cls.evaluation.participants.set(users)
        cls.evaluation.voters.set(users[:2])

    def refresh_evaluation(self):
        """ refresh_from_db does not work with evaluations"""
        self.evaluation = self.semester.evaluations.first()

    def setUp(self):
        self.semester.refresh_from_db()
        self.refresh_evaluation()

    def test_counts_dont_change(self):
        """
            Asserts that evaluation.num_voters evaluation.num_participants don't change after archiving.
        """
        voter_count = self.evaluation.num_voters
        participant_count = self.evaluation.num_participants

        self.semester.archive_participations()
        self.refresh_evaluation()

        self.assertEqual(voter_count, self.evaluation.num_voters)
        self.assertEqual(participant_count, self.evaluation.num_participants)

    def test_participants_do_not_loose_evaluations(self):
        """
            Asserts that participants still participate in their evaluations after the participations get archived.
        """
        some_participant = self.evaluation.participants.first()

        self.semester.archive_participations()

        self.assertEqual(list(some_participant.evaluations_participating_in.all()), [self.evaluation])

    def test_participations_are_archived(self):
        """
            Tests whether participations_are_archived returns True on semesters and evaluations with archived participations.
        """
        self.assertFalse(self.evaluation.participations_are_archived)

        self.semester.archive_participations()
        self.refresh_evaluation()

        self.assertTrue(self.evaluation.participations_are_archived)

    def test_archiving_participations_does_not_change_results(self):
        distribution = calculate_average_distribution(self.evaluation)

        self.semester.archive_participations()
        self.refresh_evaluation()
        caches['results'].clear()

        new_distribution = calculate_average_distribution(self.evaluation)
        self.assertEqual(new_distribution, distribution)

    def test_archiving_participations_twice_raises_exception(self):
        self.semester.archive_participations()
        with self.assertRaises(NotArchiveable):
            self.semester.archive_participations()
        with self.assertRaises(NotArchiveable):
            self.semester.courses.first().evaluations.first()._archive_participations()

    def test_evaluation_participations_are_not_archived_if_participant_count_is_set(self):
        evaluation = mommy.make(Evaluation, state="published", _participant_count=1, _voter_count=1)
        self.assertFalse(evaluation.participations_are_archived)
        self.assertTrue(evaluation.participations_can_be_archived)

    def test_archiving_participations_doesnt_change_single_results_participant_count(self):
        responsible = mommy.make(UserProfile)
        evaluation = mommy.make(Evaluation, state="published", is_single_result=True, _participant_count=5, _voter_count=5)
        contribution = mommy.make(Contribution, evaluation=evaluation, contributor=responsible, can_edit=True, textanswer_visibility=Contribution.GENERAL_TEXTANSWERS)
        contribution.questionnaires.add(Questionnaire.single_result_questionnaire())

        evaluation.course.semester.archive_participations()
        evaluation = Evaluation.objects.get(pk=evaluation.pk)
        self.assertEqual(evaluation._participant_count, 5)
        self.assertEqual(evaluation._voter_count, 5)


class TestLoginUrlEmail(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.other_user = mommy.make(UserProfile, email="other@extern.com")
        cls.user = mommy.make(UserProfile, email="extern@extern.com")
        cls.user.ensure_valid_login_key()

        cls.evaluation = mommy.make(Evaluation)
        mommy.make(Contribution, evaluation=cls.evaluation, contributor=cls.user, can_edit=True, textanswer_visibility=Contribution.GENERAL_TEXTANSWERS)

        cls.template = mommy.make(EmailTemplate, body="{{ login_url }}")

        EmailTemplate.objects.filter(name="Login Key Created").update(body="{{ user.login_url }}")

    @override_settings(PAGE_URL="https://example.com")
    def test_no_login_url_when_delegates_in_cc(self):
        self.user.delegates.add(self.other_user)
        EmailTemplate.send_to_users_in_evaluations(self.template, [self.evaluation], EmailTemplate.CONTRIBUTORS, use_cc=True, request=None)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(mail.outbox[0].body, "")  # message does not contain the login url
        self.assertEqual(mail.outbox[1].body, self.user.login_url)  # separate email with login url was sent
        self.assertEqual(len(mail.outbox[1].cc), 0)
        self.assertEqual(mail.outbox[1].to, [self.user.email])

    def test_no_login_url_when_cc_users_in_cc(self):
        self.user.cc_users.add(self.other_user)
        EmailTemplate.send_to_users_in_evaluations(self.template, [self.evaluation], [EmailTemplate.CONTRIBUTORS], use_cc=True, request=None)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(mail.outbox[0].body, "")  # message does not contain the login url
        self.assertEqual(mail.outbox[1].body, self.user.login_url)  # separate email with login url was sent
        self.assertEqual(len(mail.outbox[1].cc), 0)
        self.assertEqual(mail.outbox[1].to, [self.user.email])

    def test_login_url_when_nobody_in_cc(self):
        # message is not sent to others in cc
        EmailTemplate.send_to_users_in_evaluations(self.template, [self.evaluation], [EmailTemplate.CONTRIBUTORS], use_cc=True, request=None)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].body, self.user.login_url)  # message does contain the login url

    def test_login_url_when_use_cc_is_false(self):
        # message is not sent to others in cc
        self.user.delegates.add(self.other_user)
        EmailTemplate.send_to_users_in_evaluations(self.template, [self.evaluation], [EmailTemplate.CONTRIBUTORS], use_cc=False, request=None)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].body, self.user.login_url)  # message does contain the login url


class TestEmailTemplate(TestCase):
    def test_missing_email_address(self):
        """
        Tests that __send_to_user behaves when the user has no email address.
        Regression test to https://github.com/fsr-de/EvaP/issues/825
        """
        user = mommy.make(UserProfile, email=None)
        template = EmailTemplate.objects.get(name=EmailTemplate.STUDENT_REMINDER)
        EmailTemplate.send_to_user(user, template, {}, {}, False, None)


class TestEmailRecipientList(TestCase):
    def test_recipient_list(self):
        evaluation = mommy.make(Evaluation)
        responsible = mommy.make(UserProfile)
        editor = mommy.make(UserProfile)
        contributor = mommy.make(UserProfile)
        evaluation.course.responsibles.set([responsible])
        mommy.make(Contribution, evaluation=evaluation, contributor=editor, can_edit=True)
        mommy.make(Contribution, evaluation=evaluation, contributor=contributor)

        participant1 = mommy.make(UserProfile, evaluations_participating_in=[evaluation])
        participant2 = mommy.make(UserProfile, evaluations_participating_in=[evaluation])
        evaluation.voters.set([participant1])

        recipient_list = EmailTemplate.recipient_list_for_evaluation(evaluation, [], filter_users_in_cc=False)
        self.assertCountEqual(recipient_list, [])

        recipient_list = EmailTemplate.recipient_list_for_evaluation(evaluation, [EmailTemplate.RESPONSIBLE], filter_users_in_cc=False)
        self.assertCountEqual(recipient_list, [responsible])

        recipient_list = EmailTemplate.recipient_list_for_evaluation(evaluation, [EmailTemplate.EDITORS], filter_users_in_cc=False)
        self.assertCountEqual(recipient_list, [responsible, editor])

        recipient_list = EmailTemplate.recipient_list_for_evaluation(evaluation, [EmailTemplate.CONTRIBUTORS], filter_users_in_cc=False)
        self.assertCountEqual(recipient_list, [responsible, editor, contributor])

        recipient_list = EmailTemplate.recipient_list_for_evaluation(evaluation, [EmailTemplate.ALL_PARTICIPANTS], filter_users_in_cc=False)
        self.assertCountEqual(recipient_list, [participant1, participant2])

        recipient_list = EmailTemplate.recipient_list_for_evaluation(evaluation, [EmailTemplate.DUE_PARTICIPANTS], filter_users_in_cc=False)
        self.assertCountEqual(recipient_list, [participant2])

    def test_recipient_list_filtering(self):
        evaluation = mommy.make(Evaluation)

        contributor1 = mommy.make(UserProfile)
        contributor2 = mommy.make(UserProfile, delegates=[contributor1])

        mommy.make(Contribution, evaluation=evaluation, contributor=contributor1)
        mommy.make(Contribution, evaluation=evaluation, contributor=contributor2)

        # no-one should get filtered.
        recipient_list = EmailTemplate.recipient_list_for_evaluation(evaluation, [EmailTemplate.CONTRIBUTORS], filter_users_in_cc=False)
        self.assertCountEqual(recipient_list, [contributor1, contributor2])

        # contributor1 is in cc of contributor2 and gets filtered.
        recipient_list = EmailTemplate.recipient_list_for_evaluation(evaluation, [EmailTemplate.CONTRIBUTORS], filter_users_in_cc=True)
        self.assertCountEqual(recipient_list, [contributor2])

        contributor3 = mommy.make(UserProfile, delegates=[contributor2])
        mommy.make(Contribution, evaluation=evaluation, contributor=contributor3)

        # again, no-one should get filtered.
        recipient_list = EmailTemplate.recipient_list_for_evaluation(evaluation, [EmailTemplate.CONTRIBUTORS], filter_users_in_cc=False)
        self.assertCountEqual(recipient_list, [contributor1, contributor2, contributor3])

        # contributor1 is in cc of contributor2 and gets filtered.
        # contributor2 is in cc of contributor3 but is not filtered since contributor1 wouldn't get an email at all then.
        recipient_list = EmailTemplate.recipient_list_for_evaluation(evaluation, [EmailTemplate.CONTRIBUTORS], filter_users_in_cc=True)
        self.assertCountEqual(recipient_list, [contributor2, contributor3])
