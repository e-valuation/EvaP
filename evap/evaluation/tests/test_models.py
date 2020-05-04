from datetime import datetime, timedelta, date
from unittest.mock import patch, Mock

from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.core.cache import caches
from django.core import mail

from django_webtest import WebTest
from model_bakery import baker

from evap.evaluation.models import (Contribution, Course, CourseType, EmailTemplate, Evaluation, NotArchiveable,
                                    Question, Questionnaire, RatingAnswerCounter, Semester, TextAnswer, UserProfile)
from evap.evaluation.tests.tools import let_user_vote_for_evaluation
from evap.results.tools import calculate_average_distribution
from evap.results.views import get_evaluation_result_template_fragment_cache_key


@override_settings(EVALUATION_END_OFFSET_HOURS=0)
class TestEvaluations(WebTest):
    def test_approved_to_in_evaluation(self):
        evaluation = baker.make(Evaluation, state='approved', vote_start_datetime=datetime.now())

        with patch('evap.evaluation.models.EmailTemplate') as mock:
            mock.EVALUATION_STARTED = EmailTemplate.EVALUATION_STARTED
            mock.Recipients.ALL_PARTICIPANTS = EmailTemplate.Recipients.ALL_PARTICIPANTS
            mock.objects.get.return_value = mock
            Evaluation.update_evaluations()

        self.assertEqual(mock.objects.get.call_args_list[0][1]['name'], EmailTemplate.EVALUATION_STARTED)
        mock.send_to_users_in_evaluations.assert_called_once_with(
            [evaluation], [EmailTemplate.Recipients.ALL_PARTICIPANTS], use_cc=False, request=None
        )

        evaluation = Evaluation.objects.get(pk=evaluation.pk)
        self.assertEqual(evaluation.state, 'in_evaluation')

    def test_in_evaluation_to_evaluated(self):
        evaluation = baker.make(Evaluation, state='in_evaluation', vote_start_datetime=datetime.now() - timedelta(days=2),
                            vote_end_date=date.today() - timedelta(days=1))

        with patch('evap.evaluation.models.Evaluation.is_fully_reviewed') as mock:
            mock.__get__ = Mock(return_value=False)
            Evaluation.update_evaluations()

        evaluation = Evaluation.objects.get(pk=evaluation.pk)
        self.assertEqual(evaluation.state, 'evaluated')

    def test_in_evaluation_to_reviewed(self):
        # Evaluation is "fully reviewed" as no open text answers are present by default.
        evaluation = baker.make(Evaluation, state='in_evaluation', vote_start_datetime=datetime.now() - timedelta(days=2),
                            vote_end_date=date.today() - timedelta(days=1))

        Evaluation.update_evaluations()

        evaluation = Evaluation.objects.get(pk=evaluation.pk)
        self.assertEqual(evaluation.state, 'reviewed')

    def test_in_evaluation_to_published(self):
        # Evaluation is "fully reviewed" and not graded, thus gets published immediately.
        course = baker.make(Course)
        evaluation = baker.make(Evaluation, course=course, state='in_evaluation', vote_start_datetime=datetime.now() - timedelta(days=2),
                            vote_end_date=date.today() - timedelta(days=1), wait_for_grade_upload_before_publishing=False)

        with patch('evap.evaluation.models.EmailTemplate.send_participant_publish_notifications') as participant_mock,\
                patch('evap.evaluation.models.EmailTemplate.send_contributor_publish_notifications') as contributor_mock:
            Evaluation.update_evaluations()

        participant_mock.assert_called_once_with([evaluation])
        contributor_mock.assert_called_once_with([evaluation])

        evaluation = Evaluation.objects.get(pk=evaluation.pk)
        self.assertEqual(evaluation.state, 'published')

    @override_settings(EVALUATION_END_WARNING_PERIOD=24)
    def test_evaluation_ends_soon(self):
        evaluation = baker.make(Evaluation, vote_start_datetime=datetime.now() - timedelta(days=2),
                            vote_end_date=date.today() + timedelta(hours=24))

        self.assertFalse(evaluation.evaluation_ends_soon())

        evaluation.vote_end_date = date.today()
        self.assertTrue(evaluation.evaluation_ends_soon())

        evaluation.vote_end_date = date.today() - timedelta(hours=48)
        self.assertFalse(evaluation.evaluation_ends_soon())

    @override_settings(EVALUATION_END_WARNING_PERIOD=24, EVALUATION_END_OFFSET_HOURS=24)
    def test_evaluation_ends_soon_with_offset(self):
        evaluation = baker.make(Evaluation, vote_start_datetime=datetime.now() - timedelta(days=2),
                            vote_end_date=date.today())

        self.assertFalse(evaluation.evaluation_ends_soon())

        evaluation.vote_end_date = date.today() - timedelta(hours=24)
        self.assertTrue(evaluation.evaluation_ends_soon())

        evaluation.vote_end_date = date.today() - timedelta(hours=72)
        self.assertFalse(evaluation.evaluation_ends_soon())

    def test_evaluation_ended(self):
        # Evaluation is out of evaluation period.
        course_1 = baker.make(Course)
        course_2 = baker.make(Course)
        baker.make(Evaluation, course=course_1, state='in_evaluation', vote_start_datetime=datetime.now() - timedelta(days=2),
                   vote_end_date=date.today() - timedelta(days=1), wait_for_grade_upload_before_publishing=False)
        # This evaluation is not.
        baker.make(Evaluation, course=course_2, state='in_evaluation', vote_start_datetime=datetime.now() - timedelta(days=2),
                   vote_end_date=date.today(), wait_for_grade_upload_before_publishing=False)

        with patch('evap.evaluation.models.Evaluation.evaluation_end') as mock:
            Evaluation.update_evaluations()

        self.assertEqual(mock.call_count, 1)

    def test_approved_to_in_evaluation_sends_emails(self):
        """ Regression test for #945 """
        participant = baker.make(UserProfile, email='foo@example.com')
        evaluation = baker.make(Evaluation, state='approved', vote_start_datetime=datetime.now(), participants=[participant])

        Evaluation.update_evaluations()

        evaluation = Evaluation.objects.get(pk=evaluation.pk)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(evaluation.state, 'in_evaluation')

    def test_has_enough_questionnaires(self):
        # manually circumvent Evaluation's save() method to have a Evaluation without a general contribution
        # the semester must be specified because of https://github.com/vandersonmota/model_bakery/issues/258
        course = baker.make(Course, semester=baker.make(Semester), type=baker.make(CourseType))
        Evaluation.objects.bulk_create([baker.prepare(Evaluation, course=course)])
        evaluation = Evaluation.objects.get()
        self.assertEqual(evaluation.contributions.count(), 0)
        self.assertFalse(evaluation.general_contribution_has_questionnaires)
        self.assertFalse(evaluation.all_contributions_have_questionnaires)

        editor_contribution = baker.make(
                Contribution, evaluation=evaluation, contributor=baker.make(UserProfile),
                can_edit=True, textanswer_visibility=Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS)
        evaluation = Evaluation.objects.get()
        self.assertFalse(evaluation.general_contribution_has_questionnaires)
        self.assertFalse(evaluation.all_contributions_have_questionnaires)

        general_contribution = baker.make(Contribution, evaluation=evaluation, contributor=None)
        evaluation = Evaluation.objects.get()
        self.assertFalse(evaluation.general_contribution_has_questionnaires)
        self.assertFalse(evaluation.all_contributions_have_questionnaires)

        questionnaire = baker.make(Questionnaire)
        general_contribution.questionnaires.add(questionnaire)
        self.assertTrue(evaluation.general_contribution_has_questionnaires)
        self.assertFalse(evaluation.all_contributions_have_questionnaires)

        editor_contribution.questionnaires.add(questionnaire)
        self.assertTrue(evaluation.general_contribution_has_questionnaires)
        self.assertTrue(evaluation.all_contributions_have_questionnaires)

    def test_deleting_last_modified_user_does_not_delete_evaluation(self):
        user = baker.make(UserProfile)
        evaluation = baker.make(Evaluation, last_modified_user=user)
        user.delete()
        self.assertTrue(Evaluation.objects.filter(pk=evaluation.pk).exists())

    def test_single_result_can_be_deleted_only_in_reviewed(self):
        responsible = baker.make(UserProfile)
        evaluation = baker.make(Evaluation, is_single_result=True)
        contribution = baker.make(Contribution,
            evaluation=evaluation, contributor=responsible, can_edit=True, textanswer_visibility=Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS,
            questionnaires=[Questionnaire.single_result_questionnaire()]
        )
        baker.make(RatingAnswerCounter, answer=1, count=1, question=Questionnaire.single_result_questionnaire().questions.first(), contribution=contribution)
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

    @staticmethod
    def test_single_result_can_be_published():
        """ Regression test for #1238 """
        responsible = baker.make(UserProfile)
        single_result = baker.make(Evaluation, is_single_result=True, _participant_count=5, _voter_count=5)
        contribution = baker.make(Contribution,
            evaluation=single_result, contributor=responsible, can_edit=True, textanswer_visibility=Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS,
            questionnaires=[Questionnaire.single_result_questionnaire()]
        )
        baker.make(RatingAnswerCounter, answer=1, count=1, question=Questionnaire.single_result_questionnaire().questions.first(), contribution=contribution)

        single_result.single_result_created()
        single_result.publish()  # used to crash

    def test_second_vote_sets_can_publish_text_results_to_true(self):
        student1 = baker.make(UserProfile)
        student2 = baker.make(UserProfile)
        evaluation = baker.make(Evaluation, participants=[student1, student2], voters=[student1], state="in_evaluation")
        evaluation.save()
        top_general_questionnaire = baker.make(Questionnaire, type=Questionnaire.Type.TOP)
        baker.make(Question, questionnaire=top_general_questionnaire, type=Question.LIKERT)
        evaluation.general_contribution.questionnaires.set([top_general_questionnaire])

        self.assertFalse(evaluation.can_publish_text_results)

        let_user_vote_for_evaluation(self.app, student2, evaluation)
        evaluation = Evaluation.objects.get(pk=evaluation.pk)

        self.assertTrue(evaluation.can_publish_text_results)

    def test_textanswers_get_deleted_if_they_cannot_be_published(self):
        student = baker.make(UserProfile)
        evaluation = baker.make(Evaluation, state='reviewed', participants=[student], voters=[student], can_publish_text_results=False)
        questionnaire = baker.make(Questionnaire, type=Questionnaire.Type.TOP)
        question = baker.make(Question, type=Question.TEXT, questionnaire=questionnaire)
        evaluation.general_contribution.questionnaires.set([questionnaire])
        baker.make(TextAnswer, question=question, contribution=evaluation.general_contribution)

        self.assertEqual(evaluation.textanswer_set.count(), 1)
        evaluation.publish()
        self.assertEqual(evaluation.textanswer_set.count(), 0)

    def test_textanswers_do_not_get_deleted_if_they_can_be_published(self):
        student = baker.make(UserProfile)
        student2 = baker.make(UserProfile)
        evaluation = baker.make(Evaluation, state='reviewed', participants=[student, student2], voters=[student, student2], can_publish_text_results=True)
        questionnaire = baker.make(Questionnaire, type=Questionnaire.Type.TOP)
        question = baker.make(Question, type=Question.TEXT, questionnaire=questionnaire)
        evaluation.general_contribution.questionnaires.set([questionnaire])
        baker.make(TextAnswer, question=question, contribution=evaluation.general_contribution)

        self.assertEqual(evaluation.textanswer_set.count(), 1)
        evaluation.publish()
        self.assertEqual(evaluation.textanswer_set.count(), 1)

    def test_hidden_textanswers_get_deleted_on_publish(self):
        student = baker.make(UserProfile)
        student2 = baker.make(UserProfile)
        evaluation = baker.make(Evaluation, state='reviewed', participants=[student, student2], voters=[student, student2], can_publish_text_results=True)
        questionnaire = baker.make(Questionnaire, type=Questionnaire.Type.TOP)
        question = baker.make(Question, type=Question.TEXT, questionnaire=questionnaire)
        evaluation.general_contribution.questionnaires.set([questionnaire])
        baker.make(TextAnswer, question=question, contribution=evaluation.general_contribution, answer="hidden", state=TextAnswer.State.HIDDEN)
        baker.make(TextAnswer, question=question, contribution=evaluation.general_contribution, answer="published", state=TextAnswer.State.PUBLISHED)
        baker.make(TextAnswer, question=question, contribution=evaluation.general_contribution, answer="private", state=TextAnswer.State.PRIVATE)

        self.assertEqual(evaluation.textanswer_set.count(), 3)
        evaluation.publish()
        self.assertEqual(evaluation.textanswer_set.count(), 2)
        self.assertFalse(TextAnswer.objects.filter(answer="hidden").exists())

    def test_original_textanswers_get_deleted_on_publish(self):
        student = baker.make(UserProfile)
        student2 = baker.make(UserProfile)
        evaluation = baker.make(Evaluation, state='reviewed', participants=[student, student2], voters=[student, student2], can_publish_text_results=True)
        questionnaire = baker.make(Questionnaire, type=Questionnaire.Type.TOP)
        question = baker.make(Question, type=Question.TEXT, questionnaire=questionnaire)
        evaluation.general_contribution.questionnaires.set([questionnaire])
        baker.make(TextAnswer, question=question, contribution=evaluation.general_contribution, answer="published answer", original_answer="original answer", state=TextAnswer.State.PUBLISHED)

        self.assertEqual(evaluation.textanswer_set.count(), 1)
        self.assertFalse(TextAnswer.objects.get().original_answer is None)
        evaluation.publish()
        self.assertEqual(evaluation.textanswer_set.count(), 1)
        self.assertTrue(TextAnswer.objects.get().original_answer is None)

    def test_publishing_and_unpublishing_effect_on_template_cache(self):
        student = baker.make(UserProfile)
        evaluation = baker.make(Evaluation, state='reviewed', participants=[student], voters=[student], can_publish_text_results=True)

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
        course = baker.make(Course)
        evaluation = baker.make(Evaluation, course=course)
        self.assertFalse(course.can_be_deleted_by_manager)

        evaluation.delete()
        self.assertTrue(course.can_be_deleted_by_manager)

    def test_responsibles_names(self):
        # last names required for sorting
        user1 = baker.make(UserProfile, last_name="Doe")
        user2 = baker.make(UserProfile, last_name="Meyer")
        course = baker.make(Course, responsibles=[user1, user2])
        self.assertEqual(course.responsibles_names, ("{}, {}").format(user1.full_name, user2.full_name))


class TestUserProfile(TestCase):
    def test_is_student(self):
        some_user = baker.make(UserProfile)
        self.assertFalse(some_user.is_student)

        student = baker.make(UserProfile, evaluations_participating_in=[baker.make(Evaluation)])
        self.assertTrue(student.is_student)

        contributor = baker.make(UserProfile, contributions=[baker.make(Contribution)])
        self.assertFalse(contributor.is_student)

        semester_contributed_to = baker.make(Semester, created_at=date.today())
        semester_participated_in = baker.make(Semester, created_at=date.today())
        course_contributed_to = baker.make(Course, semester=semester_contributed_to)
        course_participated_in = baker.make(Course, semester=semester_participated_in)
        evaluation_contributed_to = baker.make(Evaluation, course=course_contributed_to)
        evaluation_participated_in = baker.make(Evaluation, course=course_participated_in)
        contribution = baker.make(Contribution, evaluation=evaluation_contributed_to)
        user = baker.make(UserProfile, contributions=[contribution], evaluations_participating_in=[evaluation_participated_in])

        self.assertTrue(user.is_student)

        semester_contributed_to.created_at = date.today() - timedelta(days=1)
        semester_contributed_to.save()

        self.assertTrue(user.is_student)

        semester_participated_in.created_at = date.today() - timedelta(days=2)
        semester_participated_in.save()

        self.assertFalse(user.is_student)

    def test_can_be_deleted_by_manager(self):
        user = baker.make(UserProfile)
        baker.make(Evaluation, participants=[user], state="new")
        self.assertFalse(user.can_be_deleted_by_manager)

        user2 = baker.make(UserProfile)
        baker.make(Evaluation, participants=[user2], state="in_evaluation")
        self.assertFalse(user2.can_be_deleted_by_manager)

        contributor = baker.make(UserProfile)
        baker.make(Contribution, contributor=contributor)
        self.assertFalse(contributor.can_be_deleted_by_manager)

        proxy_user = baker.make(UserProfile, is_proxy_user=True)
        self.assertFalse(proxy_user.can_be_deleted_by_manager)

    def test_inactive_users_hidden(self):
        active_user = baker.make(UserProfile)
        baker.make(UserProfile, is_active=False)

        self.assertEqual(list(UserProfile.objects.exclude(is_active=False)), [active_user])

    def test_inactive_users_shown(self):
        active_user = baker.make(UserProfile)
        inactive_user = baker.make(UserProfile, is_active=False)

        user_list = list(UserProfile.objects.all())
        self.assertIn(active_user, user_list)
        self.assertIn(inactive_user, user_list)

    def test_can_be_marked_inactive_by_manager(self):
        user = baker.make(UserProfile)
        evaluation = baker.make(Evaluation, state="new")
        self.assertTrue(user.can_be_marked_inactive_by_manager)
        evaluation.participants.set([user])
        evaluation.save()
        self.assertFalse(user.can_be_marked_inactive_by_manager)

        contributor = baker.make(UserProfile)
        baker.make(Contribution, contributor=contributor)
        self.assertFalse(contributor.can_be_marked_inactive_by_manager)

        reviewer = baker.make(UserProfile, groups=[Group.objects.get(name="Reviewer")])
        self.assertFalse(reviewer.can_be_marked_inactive_by_manager)

        grade_publisher = baker.make(UserProfile, groups=[Group.objects.get(name="Grade publisher")])
        self.assertFalse(grade_publisher.can_be_marked_inactive_by_manager)

        super_user = baker.make(UserProfile, is_superuser=True)
        self.assertFalse(super_user.can_be_marked_inactive_by_manager)

        proxy_user = baker.make(UserProfile, is_proxy_user=True)
        self.assertFalse(proxy_user.can_be_marked_inactive_by_manager)

    @override_settings(INSTITUTION_EMAIL_REPLACEMENTS=[("example.com", "institution.com")])
    def test_email_domain_replacement(self):
        user = baker.make(UserProfile, email="test@example.com")
        self.assertEqual(user.email, "test@institution.com")


class ParticipationArchivingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.semester = baker.make(Semester)
        cls.evaluation = baker.make(Evaluation, state="published", course=baker.make(Course, semester=cls.semester))
        cls.evaluation.general_contribution.questionnaires.set([baker.make(Questionnaire)])

        users = baker.make(UserProfile, _quantity=3)
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
        evaluation = baker.make(Evaluation, state="published", _participant_count=1, _voter_count=1)
        self.assertFalse(evaluation.participations_are_archived)
        self.assertTrue(evaluation.participations_can_be_archived)

    def test_archiving_participations_doesnt_change_single_results_participant_count(self):
        responsible = baker.make(UserProfile)
        evaluation = baker.make(Evaluation, state="published", is_single_result=True, _participant_count=5, _voter_count=5)
        contribution = baker.make(Contribution, evaluation=evaluation, contributor=responsible, can_edit=True, textanswer_visibility=Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS)
        contribution.questionnaires.add(Questionnaire.single_result_questionnaire())

        evaluation.course.semester.archive_participations()
        evaluation = Evaluation.objects.get(pk=evaluation.pk)
        self.assertEqual(evaluation._participant_count, 5)
        self.assertEqual(evaluation._voter_count, 5)


class TestLoginUrlEmail(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.other_user = baker.make(UserProfile, email="other@extern.com")
        cls.user = baker.make(UserProfile, email="extern@extern.com")
        cls.user.ensure_valid_login_key()

        cls.evaluation = baker.make(Evaluation)
        baker.make(Contribution, evaluation=cls.evaluation, contributor=cls.user, can_edit=True, textanswer_visibility=Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS)

        cls.template = baker.make(EmailTemplate, body="{{ login_url }}")

        EmailTemplate.objects.filter(name="Login Key Created").update(body="{{ user.login_url }}")

    @override_settings(PAGE_URL="https://example.com")
    def test_no_login_url_when_delegates_in_cc(self):
        self.user.delegates.add(self.other_user)
        self.template.send_to_users_in_evaluations([self.evaluation], EmailTemplate.Recipients.CONTRIBUTORS, use_cc=True, request=None)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(mail.outbox[0].body, "")  # message does not contain the login url
        self.assertEqual(mail.outbox[1].body, self.user.login_url)  # separate email with login url was sent
        self.assertEqual(len(mail.outbox[1].cc), 0)
        self.assertEqual(mail.outbox[1].to, [self.user.email])

    def test_no_login_url_when_cc_users_in_cc(self):
        self.user.cc_users.add(self.other_user)
        self.template.send_to_users_in_evaluations([self.evaluation], [EmailTemplate.Recipients.CONTRIBUTORS], use_cc=True, request=None)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(mail.outbox[0].body, "")  # message does not contain the login url
        self.assertEqual(mail.outbox[1].body, self.user.login_url)  # separate email with login url was sent
        self.assertEqual(len(mail.outbox[1].cc), 0)
        self.assertEqual(mail.outbox[1].to, [self.user.email])

    def test_login_url_when_nobody_in_cc(self):
        # message is not sent to others in cc
        self.template.send_to_users_in_evaluations([self.evaluation], [EmailTemplate.Recipients.CONTRIBUTORS], use_cc=True, request=None)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].body, self.user.login_url)  # message does contain the login url

    def test_login_url_when_use_cc_is_false(self):
        # message is not sent to others in cc
        self.user.delegates.add(self.other_user)
        self.template.send_to_users_in_evaluations([self.evaluation], [EmailTemplate.Recipients.CONTRIBUTORS], use_cc=False, request=None)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].body, self.user.login_url)  # message does contain the login url


@override_settings(INSTITUTION_EMAIL_DOMAINS=["example.com"])
class TestEmailTemplate(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = baker.make(UserProfile, email='user@example.com')
        cls.additional_cc = baker.make(UserProfile, email='additional@example.com')
        cls.template = EmailTemplate.objects.get(name=EmailTemplate.EDITOR_REVIEW_NOTICE)

    @staticmethod
    def test_missing_email_address():
        """
        Tests send_to_user when the user has no email address.
        Regression test to https://github.com/e-valuation/EvaP/issues/825
        """
        user = baker.make(UserProfile, email=None)
        template = EmailTemplate.objects.get(name=EmailTemplate.STUDENT_REMINDER)
        template.send_to_user(user, {}, {}, False, None)

    def test_put_delegates_in_cc(self):
        delegate_a = baker.make(UserProfile, email='delegate-a@example.com')
        delegate_b = baker.make(UserProfile, email='delegate-b@example.com')
        self.user.delegates.add(delegate_a, delegate_b)
        self.template.send_to_user(self.user, {}, {}, use_cc=True)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(set(mail.outbox[0].cc), {delegate_a.email, delegate_b.email})

    def test_put_cc_users_in_cc(self):
        cc_a = baker.make(UserProfile, email='cc-a@example.com')
        cc_b = baker.make(UserProfile, email='cc-b@example.com')
        self.user.cc_users.add(cc_a, cc_b)
        self.template.send_to_user(self.user, {}, {}, use_cc=True)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(set(mail.outbox[0].cc), {cc_a.email, cc_b.email})

    def test_put_additional_cc_users_in_cc(self):
        additional_cc_b = baker.make(UserProfile, email='additional-b@example.com')
        self.template.send_to_user(self.user, {}, {}, use_cc=True,
                                   additional_cc_users=[self.additional_cc, additional_cc_b])

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(set(mail.outbox[0].cc), {self.additional_cc.email, additional_cc_b.email})

    def test_put_delegates_of_additional_cc_user_in_cc(self):
        additional_delegate_a = baker.make(UserProfile, email='additional-delegate-a@example.com')
        additional_delegate_b = baker.make(UserProfile, email='additional-delegate-b@example.com')
        self.additional_cc.delegates.add(additional_delegate_a, additional_delegate_b)
        self.template.send_to_user(self.user, {}, {}, use_cc=True, additional_cc_users=[self.additional_cc])

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(set(mail.outbox[0].cc),
            {self.additional_cc.email, additional_delegate_a.email, additional_delegate_b.email})

    def test_cc_does_not_contain_duplicates(self):
        user_a = baker.make(UserProfile, email='a@example.com')
        user_b = baker.make(UserProfile, email='b@example.com')
        user_c = baker.make(UserProfile, email='c@example.com')
        self.user.delegates.add(user_a)
        self.user.cc_users.add(self.additional_cc, user_b)
        self.additional_cc.delegates.add(user_b, user_c)
        self.additional_cc.cc_users.add(user_a, user_c)
        self.template.send_to_user(self.user, {}, {}, use_cc=True, additional_cc_users=[self.additional_cc])

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(len(mail.outbox[0].cc), 4)
        self.assertEqual(set(mail.outbox[0].cc), {self.additional_cc.email, user_a.email, user_b.email, user_c.email})

    def test_disable_cc(self):
        delegate = baker.make(UserProfile, email='delegate@example.com')
        cc_user = baker.make(UserProfile, email='cc@example.com')
        self.user.delegates.add(delegate)
        self.user.cc_users.add(cc_user)
        self.additional_cc.delegates.add(delegate)
        self.additional_cc.cc_users.add(cc_user)
        self.template.send_to_user(self.user, {}, {}, use_cc=False, additional_cc_users=[self.additional_cc])

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(set(mail.outbox[0].cc), {self.additional_cc.email})


class TestEmailRecipientList(TestCase):
    def test_recipient_list(self):
        evaluation = baker.make(Evaluation)
        responsible = baker.make(UserProfile)
        editor = baker.make(UserProfile)
        contributor = baker.make(UserProfile)
        evaluation.course.responsibles.set([responsible])
        baker.make(Contribution, evaluation=evaluation, contributor=editor, can_edit=True)
        baker.make(Contribution, evaluation=evaluation, contributor=contributor)

        participant1 = baker.make(UserProfile, evaluations_participating_in=[evaluation])
        participant2 = baker.make(UserProfile, evaluations_participating_in=[evaluation])
        evaluation.voters.set([participant1])

        recipient_list = EmailTemplate.recipient_list_for_evaluation(evaluation, [], filter_users_in_cc=False)
        self.assertCountEqual(recipient_list, [])

        recipient_list = EmailTemplate.recipient_list_for_evaluation(evaluation, [EmailTemplate.Recipients.RESPONSIBLE], filter_users_in_cc=False)
        self.assertCountEqual(recipient_list, [responsible])

        recipient_list = EmailTemplate.recipient_list_for_evaluation(evaluation, [EmailTemplate.Recipients.EDITORS], filter_users_in_cc=False)
        self.assertCountEqual(recipient_list, [responsible, editor])

        recipient_list = EmailTemplate.recipient_list_for_evaluation(evaluation, [EmailTemplate.Recipients.CONTRIBUTORS], filter_users_in_cc=False)
        self.assertCountEqual(recipient_list, [responsible, editor, contributor])

        recipient_list = EmailTemplate.recipient_list_for_evaluation(evaluation, [EmailTemplate.Recipients.ALL_PARTICIPANTS], filter_users_in_cc=False)
        self.assertCountEqual(recipient_list, [participant1, participant2])

        recipient_list = EmailTemplate.recipient_list_for_evaluation(evaluation, [EmailTemplate.Recipients.DUE_PARTICIPANTS], filter_users_in_cc=False)
        self.assertCountEqual(recipient_list, [participant2])

    def test_recipient_list_filtering(self):
        evaluation = baker.make(Evaluation)

        contributor1 = baker.make(UserProfile)
        contributor2 = baker.make(UserProfile, delegates=[contributor1])

        baker.make(Contribution, evaluation=evaluation, contributor=contributor1)
        baker.make(Contribution, evaluation=evaluation, contributor=contributor2)

        # no-one should get filtered.
        recipient_list = EmailTemplate.recipient_list_for_evaluation(evaluation, [EmailTemplate.Recipients.CONTRIBUTORS], filter_users_in_cc=False)
        self.assertCountEqual(recipient_list, [contributor1, contributor2])

        # contributor1 is in cc of contributor2 and gets filtered.
        recipient_list = EmailTemplate.recipient_list_for_evaluation(evaluation, [EmailTemplate.Recipients.CONTRIBUTORS], filter_users_in_cc=True)
        self.assertCountEqual(recipient_list, [contributor2])

        contributor3 = baker.make(UserProfile, delegates=[contributor2])
        baker.make(Contribution, evaluation=evaluation, contributor=contributor3)

        # again, no-one should get filtered.
        recipient_list = EmailTemplate.recipient_list_for_evaluation(evaluation, [EmailTemplate.Recipients.CONTRIBUTORS], filter_users_in_cc=False)
        self.assertCountEqual(recipient_list, [contributor1, contributor2, contributor3])

        # contributor1 is in cc of contributor2 and gets filtered.
        # contributor2 is in cc of contributor3 but is not filtered since contributor1 wouldn't get an email at all then.
        recipient_list = EmailTemplate.recipient_list_for_evaluation(evaluation, [EmailTemplate.Recipients.CONTRIBUTORS], filter_users_in_cc=True)
        self.assertCountEqual(recipient_list, [contributor2, contributor3])


class QuestionnaireTests(TestCase):
    def test_locked_contributor_questionnaire(self):
        questionnaire = baker.prepare(Questionnaire, is_locked=True, type=Questionnaire.Type.CONTRIBUTOR)
        self.assertRaises(ValidationError, questionnaire.clean)
