from datetime import date, datetime, timedelta
from unittest.mock import Mock, call, patch

from django.contrib.auth.models import Group
from django.core import mail
from django.core.cache import caches
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django_webtest import WebTest
from model_bakery import baker

from evap.evaluation.models import (
    Contribution,
    Course,
    CourseType,
    EmailTemplate,
    Evaluation,
    NotArchivableError,
    Question,
    Questionnaire,
    QuestionType,
    RatingAnswerCounter,
    Semester,
    TextAnswer,
    UserProfile,
)
from evap.evaluation.tests.tools import (
    let_user_vote_for_evaluation,
    make_contributor,
    make_editor,
    make_rating_answer_counters,
)
from evap.grades.models import GradeDocument
from evap.results.tools import cache_results, calculate_average_distribution
from evap.results.views import get_evaluation_result_template_fragment_cache_key


class TestSemester(WebTest):
    def test_can_be_deleted_by_manager(self):
        semester = baker.make(Semester)
        self.assertTrue(semester.can_be_deleted_by_manager)

        semester.is_active = True
        self.assertFalse(semester.can_be_deleted_by_manager)
        semester.is_active = False

        voter = baker.make(UserProfile)
        baker.make(Evaluation, course__semester=semester, state=Evaluation.State.PUBLISHED, voters=[voter])
        self.assertFalse(semester.can_be_deleted_by_manager)

        semester.archive()
        self.assertFalse(semester.can_be_deleted_by_manager)

        semester.delete_grade_documents()
        self.assertFalse(semester.can_be_deleted_by_manager)

        semester.archive_results()
        self.assertTrue(semester.can_be_deleted_by_manager)


class TestQuestionnaire(WebTest):
    def test_can_be_deleted_by_manager(self):
        questionnaire = baker.make(Questionnaire)
        self.assertTrue(questionnaire.can_be_deleted_by_manager)

        baker.make(Contribution, questionnaires=[questionnaire])
        self.assertFalse(questionnaire.can_be_deleted_by_manager)


@override_settings(EVALUATION_END_OFFSET_HOURS=0)
class TestEvaluations(WebTest):
    def test_approved_to_in_evaluation(self):
        evaluation = baker.make(Evaluation, state=Evaluation.State.APPROVED, vote_start_datetime=datetime.now())

        with patch("evap.evaluation.models.EmailTemplate") as mock:
            mock.EVALUATION_STARTED = EmailTemplate.EVALUATION_STARTED
            mock.Recipients.ALL_PARTICIPANTS = EmailTemplate.Recipients.ALL_PARTICIPANTS
            mock.objects.get.return_value = mock
            Evaluation.update_evaluations()

        self.assertEqual(mock.objects.get.call_args_list[0][1]["name"], EmailTemplate.EVALUATION_STARTED)
        mock.send_to_users_in_evaluations.assert_called_once_with(
            [evaluation], [EmailTemplate.Recipients.ALL_PARTICIPANTS], use_cc=False, request=None
        )

        evaluation = Evaluation.objects.get(pk=evaluation.pk)
        self.assertEqual(evaluation.state, Evaluation.State.IN_EVALUATION)

    def test_in_evaluation_to_evaluated(self):
        evaluation = baker.make(
            Evaluation,
            state=Evaluation.State.IN_EVALUATION,
            vote_start_datetime=datetime.now() - timedelta(days=2),
            vote_end_date=date.today() - timedelta(days=1),
        )

        with patch("evap.evaluation.models.Evaluation.is_fully_reviewed") as mock:
            mock.__get__ = Mock(return_value=False)
            Evaluation.update_evaluations()

        evaluation = Evaluation.objects.get(pk=evaluation.pk)
        self.assertEqual(evaluation.state, Evaluation.State.EVALUATED)

    def test_in_evaluation_to_reviewed(self):
        # Evaluation is "fully reviewed" as no open text answers are present by default.
        evaluation = baker.make(
            Evaluation,
            state=Evaluation.State.IN_EVALUATION,
            vote_start_datetime=datetime.now() - timedelta(days=2),
            vote_end_date=date.today() - timedelta(days=1),
        )

        Evaluation.update_evaluations()

        evaluation = Evaluation.objects.get(pk=evaluation.pk)
        self.assertEqual(evaluation.state, Evaluation.State.REVIEWED)

    def test_in_evaluation_to_published(self):
        # Evaluation is "fully reviewed" and not graded, thus gets published immediately.
        course = baker.make(Course)
        evaluation = baker.make(
            Evaluation,
            course=course,
            state=Evaluation.State.IN_EVALUATION,
            vote_start_datetime=datetime.now() - timedelta(days=2),
            vote_end_date=date.today() - timedelta(days=1),
            wait_for_grade_upload_before_publishing=False,
        )

        with (
            patch("evap.evaluation.models.EmailTemplate.send_participant_publish_notifications") as participant_mock,
            patch("evap.evaluation.models.EmailTemplate.send_contributor_publish_notifications") as contributor_mock,
        ):
            Evaluation.update_evaluations()

        participant_mock.assert_called_once_with([evaluation])
        contributor_mock.assert_called_once_with([evaluation])

        evaluation = Evaluation.objects.get(pk=evaluation.pk)
        self.assertEqual(evaluation.state, Evaluation.State.PUBLISHED)

    @override_settings(EVALUATION_END_WARNING_PERIOD=24)
    def test_ends_soon(self):
        evaluation = baker.make(
            Evaluation,
            vote_start_datetime=datetime.now() - timedelta(days=2),
            vote_end_date=date.today() + timedelta(hours=24),
        )

        self.assertFalse(evaluation.ends_soon)

        evaluation.vote_end_date = date.today()
        self.assertTrue(evaluation.ends_soon)

        evaluation.vote_end_date = date.today() - timedelta(hours=48)
        self.assertFalse(evaluation.ends_soon)

    @override_settings(EVALUATION_END_WARNING_PERIOD=24, EVALUATION_END_OFFSET_HOURS=24)
    def test_ends_soon_with_offset(self):
        evaluation = baker.make(
            Evaluation, vote_start_datetime=datetime.now() - timedelta(days=2), vote_end_date=date.today()
        )

        self.assertFalse(evaluation.ends_soon)

        evaluation.vote_end_date = date.today() - timedelta(hours=24)
        self.assertTrue(evaluation.ends_soon)

        evaluation.vote_end_date = date.today() - timedelta(hours=72)
        self.assertFalse(evaluation.ends_soon)

    def test_evaluation_ended(self):
        # Evaluation is out of evaluation period.
        course_1 = baker.make(Course)
        course_2 = baker.make(Course)
        baker.make(
            Evaluation,
            course=course_1,
            state=Evaluation.State.IN_EVALUATION,
            vote_start_datetime=datetime.now() - timedelta(days=2),
            vote_end_date=date.today() - timedelta(days=1),
            wait_for_grade_upload_before_publishing=False,
        )
        # This evaluation is not.
        baker.make(
            Evaluation,
            course=course_2,
            state=Evaluation.State.IN_EVALUATION,
            vote_start_datetime=datetime.now() - timedelta(days=2),
            vote_end_date=date.today(),
            wait_for_grade_upload_before_publishing=False,
        )

        with patch("evap.evaluation.models.Evaluation.end_evaluation") as mock:
            Evaluation.update_evaluations()

        self.assertEqual(mock.call_count, 1)

    def test_approved_to_in_evaluation_sends_emails(self):
        """Regression test for #945"""
        participant = baker.make(UserProfile, email="foo@example.com")
        evaluation = baker.make(
            Evaluation, state=Evaluation.State.APPROVED, vote_start_datetime=datetime.now(), participants=[participant]
        )

        Evaluation.update_evaluations()

        evaluation = Evaluation.objects.get(pk=evaluation.pk)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(evaluation.state, Evaluation.State.IN_EVALUATION)

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
            Contribution,
            evaluation=evaluation,
            contributor=baker.make(UserProfile),
            role=Contribution.Role.EDITOR,
            textanswer_visibility=Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS,
        )
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

    def test_single_result_can_be_deleted_only_in_reviewed(self):
        responsible = baker.make(UserProfile)
        evaluation = baker.make(Evaluation, is_single_result=True)
        contribution = baker.make(
            Contribution,
            evaluation=evaluation,
            contributor=responsible,
            questionnaires=[Questionnaire.single_result_questionnaire()],
            role=Contribution.Role.EDITOR,
            textanswer_visibility=Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS,
        )
        make_rating_answer_counters(Questionnaire.single_result_questionnaire().questions.first(), contribution)
        evaluation.skip_review_single_result()
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
        """Regression test for #1238"""
        responsible = baker.make(UserProfile)
        single_result = baker.make(Evaluation, is_single_result=True, _participant_count=5, _voter_count=5)
        contribution = baker.make(
            Contribution,
            evaluation=single_result,
            contributor=responsible,
            questionnaires=[Questionnaire.single_result_questionnaire()],
            role=Contribution.Role.EDITOR,
            textanswer_visibility=Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS,
        )
        make_rating_answer_counters(Questionnaire.single_result_questionnaire().questions.first(), contribution)

        single_result.skip_review_single_result()
        single_result.publish()  # used to crash

    def test_second_vote_sets_can_publish_text_results_to_true(self):
        student1 = baker.make(UserProfile, email="student1@institution.example.com")
        student2 = baker.make(UserProfile, email="student2@example.com")
        evaluation = baker.make(
            Evaluation, participants=[student1, student2], voters=[student1], state=Evaluation.State.IN_EVALUATION
        )
        evaluation.save()
        top_general_questionnaire = baker.make(Questionnaire, type=Questionnaire.Type.TOP)
        baker.make(Question, questionnaire=top_general_questionnaire, type=QuestionType.POSITIVE_LIKERT)
        evaluation.general_contribution.questionnaires.set([top_general_questionnaire])

        self.assertFalse(evaluation.can_publish_text_results)

        let_user_vote_for_evaluation(student2, evaluation)
        evaluation = Evaluation.objects.get(pk=evaluation.pk)

        self.assertTrue(evaluation.can_publish_text_results)

    def test_textanswers_get_deleted_if_they_cannot_be_published(self):
        student = baker.make(UserProfile)
        evaluation = baker.make(
            Evaluation,
            state=Evaluation.State.REVIEWED,
            participants=[student],
            voters=[student],
            can_publish_text_results=False,
        )
        questionnaire = baker.make(Questionnaire, type=Questionnaire.Type.TOP)
        question = baker.make(Question, type=QuestionType.TEXT, questionnaire=questionnaire)
        evaluation.general_contribution.questionnaires.set([questionnaire])
        baker.make(TextAnswer, question=question, contribution=evaluation.general_contribution)

        self.assertEqual(evaluation.textanswer_set.count(), 1)
        evaluation.publish()
        self.assertEqual(evaluation.textanswer_set.count(), 0)

    def test_textanswers_do_not_get_deleted_if_they_can_be_published(self):
        student = baker.make(UserProfile)
        student2 = baker.make(UserProfile)
        evaluation = baker.make(
            Evaluation,
            state=Evaluation.State.REVIEWED,
            participants=[student, student2],
            voters=[student, student2],
            can_publish_text_results=True,
        )
        questionnaire = baker.make(Questionnaire, type=Questionnaire.Type.TOP)
        question = baker.make(Question, type=QuestionType.TEXT, questionnaire=questionnaire)
        evaluation.general_contribution.questionnaires.set([questionnaire])
        baker.make(TextAnswer, question=question, contribution=evaluation.general_contribution)

        self.assertEqual(evaluation.textanswer_set.count(), 1)
        evaluation.publish()
        self.assertEqual(evaluation.textanswer_set.count(), 1)

    def test_textanswers_to_delete_get_deleted_on_publish(self):
        student = baker.make(UserProfile)
        student2 = baker.make(UserProfile)
        evaluation = baker.make(
            Evaluation,
            state=Evaluation.State.REVIEWED,
            participants=[student, student2],
            voters=[student, student2],
            can_publish_text_results=True,
        )
        questionnaire = baker.make(Questionnaire, type=Questionnaire.Type.TOP)
        question = baker.make(Question, type=QuestionType.TEXT, questionnaire=questionnaire)
        evaluation.general_contribution.questionnaires.set([questionnaire])
        baker.make(
            TextAnswer,
            question=question,
            contribution=evaluation.general_contribution,
            answer=iter(["deleted", "public", "private"]),
            review_decision=iter(
                [
                    TextAnswer.ReviewDecision.DELETED,
                    TextAnswer.ReviewDecision.PUBLIC,
                    TextAnswer.ReviewDecision.PRIVATE,
                ]
            ),
            _quantity=3,
            _bulk_create=True,
        )

        self.assertEqual(evaluation.textanswer_set.count(), 3)
        evaluation.publish()
        self.assertEqual(evaluation.textanswer_set.count(), 2)
        self.assertFalse(TextAnswer.objects.filter(answer="deleted").exists())

    def test_original_textanswers_get_deleted_on_publish(self):
        student = baker.make(UserProfile)
        student2 = baker.make(UserProfile)
        evaluation = baker.make(
            Evaluation,
            state=Evaluation.State.REVIEWED,
            participants=[student, student2],
            voters=[student, student2],
            can_publish_text_results=True,
        )
        questionnaire = baker.make(Questionnaire, type=Questionnaire.Type.TOP)
        question = baker.make(Question, type=QuestionType.TEXT, questionnaire=questionnaire)
        evaluation.general_contribution.questionnaires.set([questionnaire])
        baker.make(
            TextAnswer,
            question=question,
            contribution=evaluation.general_contribution,
            answer="published answer",
            original_answer="original answer",
            review_decision=TextAnswer.ReviewDecision.PUBLIC,
        )

        self.assertEqual(evaluation.textanswer_set.count(), 1)
        self.assertFalse(TextAnswer.objects.get().original_answer is None)
        evaluation.publish()
        self.assertEqual(evaluation.textanswer_set.count(), 1)
        self.assertTrue(TextAnswer.objects.get().original_answer is None)

    def test_publishing_and_unpublishing_effect_on_template_cache(self):
        student = baker.make(UserProfile)
        evaluation = baker.make(
            Evaluation,
            state=Evaluation.State.REVIEWED,
            participants=[student],
            voters=[student],
            can_publish_text_results=True,
        )

        self.assertIsNone(
            caches["results"].get(get_evaluation_result_template_fragment_cache_key(evaluation.id, "en", True))
        )
        self.assertIsNone(
            caches["results"].get(get_evaluation_result_template_fragment_cache_key(evaluation.id, "en", False))
        )
        self.assertIsNone(
            caches["results"].get(get_evaluation_result_template_fragment_cache_key(evaluation.id, "de", True))
        )
        self.assertIsNone(
            caches["results"].get(get_evaluation_result_template_fragment_cache_key(evaluation.id, "de", False))
        )

        evaluation.publish()
        evaluation.save()

        self.assertIsNotNone(
            caches["results"].get(get_evaluation_result_template_fragment_cache_key(evaluation.id, "en", True))
        )
        self.assertIsNotNone(
            caches["results"].get(get_evaluation_result_template_fragment_cache_key(evaluation.id, "en", False))
        )
        self.assertIsNotNone(
            caches["results"].get(get_evaluation_result_template_fragment_cache_key(evaluation.id, "de", True))
        )
        self.assertIsNotNone(
            caches["results"].get(get_evaluation_result_template_fragment_cache_key(evaluation.id, "de", False))
        )

        evaluation.unpublish()
        evaluation.save()

        self.assertIsNone(
            caches["results"].get(get_evaluation_result_template_fragment_cache_key(evaluation.id, "en", True))
        )
        self.assertIsNone(
            caches["results"].get(get_evaluation_result_template_fragment_cache_key(evaluation.id, "en", False))
        )
        self.assertIsNone(
            caches["results"].get(get_evaluation_result_template_fragment_cache_key(evaluation.id, "de", True))
        )
        self.assertIsNone(
            caches["results"].get(get_evaluation_result_template_fragment_cache_key(evaluation.id, "de", False))
        )

    def assert_textanswer_review_state(
        self,
        evaluation,
        expected_default_value,
        expected_value_with_gets_no_grade_documents,
        expected_value_with_wait_for_grade_upload_before_publishing,
        expected_value_after_grade_upload,
    ):
        self.assertEqual(evaluation.textanswer_review_state, expected_default_value)

        evaluation.course.gets_no_grade_documents = True
        self.assertEqual(evaluation.textanswer_review_state, expected_value_with_gets_no_grade_documents)
        evaluation.course.gets_no_grade_documents = False

        evaluation.wait_for_grade_upload_before_publishing = True
        self.assertEqual(
            evaluation.textanswer_review_state, expected_value_with_wait_for_grade_upload_before_publishing
        )

        grade_document = baker.make(GradeDocument, type=GradeDocument.Type.FINAL_GRADES, course=evaluation.course)
        self.assertEqual(evaluation.textanswer_review_state, expected_value_after_grade_upload)
        grade_document.delete()

        evaluation.wait_for_grade_upload_before_publishing = False

    def test_textanswer_review_state(self):
        evaluation = baker.make(
            Evaluation,
            state=Evaluation.State.IN_EVALUATION,
            can_publish_text_results=True,
            wait_for_grade_upload_before_publishing=False,
        )

        self.assert_textanswer_review_state(
            evaluation,
            evaluation.TextAnswerReviewState.NO_TEXTANSWERS,
            evaluation.TextAnswerReviewState.NO_TEXTANSWERS,
            evaluation.TextAnswerReviewState.NO_TEXTANSWERS,
            evaluation.TextAnswerReviewState.NO_TEXTANSWERS,
        )

        textanswer = baker.make(TextAnswer, contribution=evaluation.general_contribution)
        del evaluation.num_textanswers  # reset cached_property cache

        # text_answer_review_state should be NO_REVIEW_NEEDED as long as we are still in_evaluation
        self.assert_textanswer_review_state(
            evaluation,
            evaluation.TextAnswerReviewState.NO_REVIEW_NEEDED,
            evaluation.TextAnswerReviewState.NO_REVIEW_NEEDED,
            evaluation.TextAnswerReviewState.NO_REVIEW_NEEDED,
            evaluation.TextAnswerReviewState.NO_REVIEW_NEEDED,
        )

        evaluation.end_evaluation()
        evaluation.save()

        self.assert_textanswer_review_state(
            evaluation,
            evaluation.TextAnswerReviewState.REVIEW_URGENT,
            evaluation.TextAnswerReviewState.REVIEW_URGENT,  # course has `gets_no_grade_documents`
            evaluation.TextAnswerReviewState.REVIEW_NEEDED,  # still waiting for grades
            evaluation.TextAnswerReviewState.REVIEW_URGENT,  # grades were uploaded
        )

        textanswer.review_decision = TextAnswer.ReviewDecision.PUBLIC
        textanswer.save()
        del evaluation.num_reviewed_textanswers  # reset cached_property cache

        self.assert_textanswer_review_state(
            evaluation,
            evaluation.TextAnswerReviewState.REVIEWED,
            evaluation.TextAnswerReviewState.REVIEWED,
            evaluation.TextAnswerReviewState.REVIEWED,
            evaluation.TextAnswerReviewState.REVIEWED,
        )


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
        self.assertEqual(course.responsibles_names, f"{user1.full_name}, {user2.full_name}")


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
        user = baker.make(
            UserProfile, contributions=[contribution], evaluations_participating_in=[evaluation_participated_in]
        )

        self.assertTrue(user.is_student)

        semester_contributed_to.created_at = date.today() - timedelta(days=1)
        semester_contributed_to.save()

        # invalidate cached_property
        del user.is_student
        self.assertTrue(user.is_student)

        semester_participated_in.created_at = date.today() - timedelta(days=2)
        semester_participated_in.save()

        # invalidate cached_property
        del user.is_student
        self.assertFalse(user.is_student)

    def test_can_be_deleted_by_manager(self):
        user = baker.make(UserProfile)
        baker.make(Evaluation, participants=[user], state=Evaluation.State.NEW)
        self.assertFalse(user.can_be_deleted_by_manager)

        user2 = baker.make(UserProfile)
        baker.make(Evaluation, participants=[user2], state=Evaluation.State.IN_EVALUATION)
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
        evaluation = baker.make(Evaluation, state=Evaluation.State.NEW)
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

    def test_get_sorted_due_evaluations(self):
        student = baker.make(UserProfile, email="student@example.com")
        course = baker.make(Course)

        evaluations = baker.make(
            Evaluation,
            course=course,
            name_en=iter(["C", "B", "A"]),
            name_de=iter(["C", "B", "A"]),
            vote_end_date=iter([date.today(), date.today(), date.today() + timedelta(days=1)]),
            state=Evaluation.State.IN_EVALUATION,
            participants=[student],
            _quantity=3,
        )

        sorted_evaluations = student.get_sorted_due_evaluations()
        self.assertEqual(sorted_evaluations, [(evaluations[1], 0), (evaluations[0], 0), (evaluations[2], 1)])

    def test_correct_sorting(self):
        baker.make(
            UserProfile,
            last_name=iter(["Y", "x", "", ""]),
            first_name_given=iter(["x", "x", "a", ""]),
            email=iter(["3xy@example.com", "4xx@example.com", "2a@example.com", "1unnamed@example.com"]),
            _quantity=4,
            _bulk_create=True,
        )
        email_list = [user.email for user in UserProfile.objects.all()]
        self.assertEqual(email_list, ["4xx@example.com", "3xy@example.com", "2a@example.com", "1unnamed@example.com"])


class ParticipationArchivingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.semester = baker.make(Semester)
        cls.evaluation = baker.make(
            Evaluation, state=Evaluation.State.PUBLISHED, course=baker.make(Course, semester=cls.semester)
        )
        cls.evaluation.general_contribution.questionnaires.set([baker.make(Questionnaire)])

        users = baker.make(UserProfile, _bulk_create=True, _quantity=3)
        cls.evaluation.participants.set(users)
        cls.evaluation.voters.set(users[:2])

    def refresh_evaluation(self):
        """refresh_from_db does not work with evaluations"""
        self.evaluation = self.semester.evaluations.first()

    def test_counts_dont_change(self):
        """
        Asserts that evaluation.num_voters evaluation.num_participants don't change after archiving.
        """
        voter_count = self.evaluation.num_voters
        participant_count = self.evaluation.num_participants

        self.semester.archive()
        self.refresh_evaluation()

        self.assertEqual(voter_count, self.evaluation.num_voters)
        self.assertEqual(participant_count, self.evaluation.num_participants)

    def test_participants_do_not_loose_evaluations(self):
        """
        Asserts that participants still participate in their evaluations after the participations get archived.
        """
        some_participant = self.evaluation.participants.first()

        self.semester.archive()

        self.assertEqual(list(some_participant.evaluations_participating_in.all()), [self.evaluation])

    def test_participations_are_archived(self):
        """
        Tests whether participations_are_archived returns True on semesters and evaluations with archived participations.
        """
        self.assertFalse(self.evaluation.participations_are_archived)

        self.semester.archive()
        self.refresh_evaluation()

        self.assertTrue(self.evaluation.participations_are_archived)

    def test_archiving_participations_does_not_change_results(self):
        cache_results(self.evaluation)
        distribution = calculate_average_distribution(self.evaluation)

        self.semester.archive()
        self.refresh_evaluation()
        caches["results"].clear()

        cache_results(self.evaluation)
        new_distribution = calculate_average_distribution(self.evaluation)
        self.assertEqual(new_distribution, distribution)

    def test_archiving_participations_twice_raises_exception(self):
        self.semester.archive()
        with self.assertRaises(NotArchivableError):
            self.semester.archive()
        with self.assertRaises(NotArchivableError):
            self.semester.courses.first().evaluations.first()._archive()

    def test_evaluation_participations_are_not_archived_if_participant_count_is_set(self):
        evaluation = baker.make(Evaluation, state=Evaluation.State.PUBLISHED, _participant_count=1, _voter_count=1)
        self.assertFalse(evaluation.participations_are_archived)
        self.assertTrue(evaluation.participations_can_be_archived)

    def test_archiving_participations_doesnt_change_single_results_participant_count(self):
        responsible = baker.make(UserProfile)
        evaluation = baker.make(
            Evaluation, state=Evaluation.State.PUBLISHED, is_single_result=True, _participant_count=5, _voter_count=5
        )
        contribution = baker.make(
            Contribution,
            evaluation=evaluation,
            contributor=responsible,
            role=Contribution.Role.EDITOR,
            textanswer_visibility=Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS,
        )
        contribution.questionnaires.add(Questionnaire.single_result_questionnaire())

        evaluation.course.semester.archive()
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
        baker.make(
            Contribution,
            evaluation=cls.evaluation,
            contributor=cls.user,
            role=Contribution.Role.EDITOR,
            textanswer_visibility=Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS,
        )

        cls.template = baker.make(EmailTemplate, plain_content="{{ login_url }}")

        EmailTemplate.objects.filter(name="Login Key Created").update(plain_content="{{ user.login_url }}")

    @override_settings(PAGE_URL="https://example.com")
    def test_no_login_url_when_delegates_in_cc(self):
        self.user.delegates.add(self.other_user)
        self.template.send_to_users_in_evaluations(
            [self.evaluation], EmailTemplate.Recipients.CONTRIBUTORS, use_cc=True, request=None
        )
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(mail.outbox[0].body, "")  # message does not contain the login url
        self.assertEqual(mail.outbox[1].body, self.user.login_url)  # separate email with login url was sent
        self.assertEqual(len(mail.outbox[1].cc), 0)
        self.assertEqual(mail.outbox[1].to, [self.user.email])

    def test_no_login_url_when_cc_users_in_cc(self):
        self.user.cc_users.add(self.other_user)
        self.template.send_to_users_in_evaluations(
            [self.evaluation], [EmailTemplate.Recipients.CONTRIBUTORS], use_cc=True, request=None
        )
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(mail.outbox[0].body, "")  # message does not contain the login url
        self.assertEqual(mail.outbox[1].body, self.user.login_url)  # separate email with login url was sent
        self.assertEqual(len(mail.outbox[1].cc), 0)
        self.assertEqual(mail.outbox[1].to, [self.user.email])

    def test_login_url_when_nobody_in_cc(self):
        # message is not sent to others in cc
        self.template.send_to_users_in_evaluations(
            [self.evaluation], [EmailTemplate.Recipients.CONTRIBUTORS], use_cc=True, request=None
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].body, self.user.login_url)  # message does contain the login url

    def test_login_url_when_use_cc_is_false(self):
        # message is not sent to others in cc
        self.user.delegates.add(self.other_user)
        self.template.send_to_users_in_evaluations(
            [self.evaluation], [EmailTemplate.Recipients.CONTRIBUTORS], use_cc=False, request=None
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].body, self.user.login_url)  # message does contain the login url


@override_settings(INSTITUTION_EMAIL_DOMAINS=["example.com"])
class TestEmailTemplate(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = baker.make(UserProfile, email="user@example.com")
        cls.additional_cc = baker.make(UserProfile, email="additional@example.com")
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

    def test_send_multi_alternatives_email(self):
        template = EmailTemplate(
            subject="Example", plain_content="Example plain content", html_content="<p>Example html content</p>"
        )
        template.send_to_user(self.user, {}, {}, False)
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(isinstance(mail.outbox[0], mail.message.EmailMultiAlternatives))
        self.assertEqual(mail.outbox[0].body, "Example plain content")
        self.assertEqual(len(mail.outbox[0].alternatives), 1)
        self.assertEqual(mail.outbox[0].alternatives[0][1], "text/html")
        self.assertIn("<p>Example html content</p>", mail.outbox[0].alternatives[0][0])

    def test_plain_content_escaped_and_copied_on_empty_html_content(self):
        template = EmailTemplate(subject="Subject <>&", plain_content="A\nB <>& {{ some_var }}", html_content="")
        template.send_to_user(self.user, {}, {"some_var": "0 < 1"}, False)

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.alternatives[0][1], "text/html")
        html_content = message.alternatives[0][0]

        self.assertEqual("Subject <>&", message.subject)
        self.assertEqual("A\nB <>& 0 < 1", message.body)
        self.assertIn("A<br>B &lt;&gt;&amp; 0 &lt; 1\n", html_content)
        self.assertNotIn("<>&", html_content)

    def test_escaping_with_html_content(self):
        template = EmailTemplate(
            subject="Subject <>&",
            plain_content="A\nB <>& {{ some_var }}",
            html_content="Html content &amp;<br/> {{ some_var }}",
        )
        template.send_to_user(self.user, {}, {"some_var": "0 < 1"}, False)

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.alternatives[0][1], "text/html")
        html_content = message.alternatives[0][0]

        self.assertEqual("Subject <>&", message.subject)
        self.assertEqual("A\nB <>& 0 < 1", message.body)
        self.assertIn("Html content &amp;<br/> 0 &lt; 1", html_content)
        self.assertNotIn("<>&", html_content)

    def test_put_delegates_in_cc(self):
        delegate_a = baker.make(UserProfile, email="delegate-a@example.com")
        delegate_b = baker.make(UserProfile, email="delegate-b@example.com")
        self.user.delegates.add(delegate_a, delegate_b)
        self.template.send_to_user(self.user, {}, {}, use_cc=True)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(set(mail.outbox[0].cc), {delegate_a.email, delegate_b.email})

    def test_put_cc_users_in_cc(self):
        cc_a = baker.make(UserProfile, email="cc-a@example.com")
        cc_b = baker.make(UserProfile, email="cc-b@example.com")
        self.user.cc_users.add(cc_a, cc_b)
        self.template.send_to_user(self.user, {}, {}, use_cc=True)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(set(mail.outbox[0].cc), {cc_a.email, cc_b.email})

    def test_put_additional_cc_users_in_cc(self):
        additional_cc_b = baker.make(UserProfile, email="additional-b@example.com")
        self.template.send_to_user(
            self.user, {}, {}, use_cc=True, additional_cc_users=[self.additional_cc, additional_cc_b]
        )

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(set(mail.outbox[0].cc), {self.additional_cc.email, additional_cc_b.email})

    def test_put_delegates_of_additional_cc_user_in_cc(self):
        additional_delegate_a = baker.make(UserProfile, email="additional-delegate-a@example.com")
        additional_delegate_b = baker.make(UserProfile, email="additional-delegate-b@example.com")
        self.additional_cc.delegates.add(additional_delegate_a, additional_delegate_b)
        self.template.send_to_user(self.user, {}, {}, use_cc=True, additional_cc_users=[self.additional_cc])

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            set(mail.outbox[0].cc), {self.additional_cc.email, additional_delegate_a.email, additional_delegate_b.email}
        )

    def test_cc_does_not_contain_duplicates(self):
        user_a = baker.make(UserProfile, email="a@example.com")
        user_b = baker.make(UserProfile, email="b@example.com")
        user_c = baker.make(UserProfile, email="c@example.com")
        self.user.delegates.add(user_a)
        self.user.cc_users.add(self.additional_cc, user_b)
        self.additional_cc.delegates.add(user_b, user_c)
        self.additional_cc.cc_users.add(user_a, user_c)
        self.template.send_to_user(self.user, {}, {}, use_cc=True, additional_cc_users=[self.additional_cc])

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(len(mail.outbox[0].cc), 4)
        self.assertEqual(set(mail.outbox[0].cc), {self.additional_cc.email, user_a.email, user_b.email, user_c.email})

    def test_disable_cc(self):
        delegate = baker.make(UserProfile, email="delegate@example.com")
        cc_user = baker.make(UserProfile, email="cc@example.com")
        self.user.delegates.add(delegate)
        self.user.cc_users.add(cc_user)
        self.additional_cc.delegates.add(delegate)
        self.additional_cc.cc_users.add(cc_user)
        self.template.send_to_user(self.user, {}, {}, use_cc=False, additional_cc_users=[self.additional_cc])

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(set(mail.outbox[0].cc), {self.additional_cc.email})

    @staticmethod
    def test_send_contributor_publish_notifications():
        responsible1 = baker.make(UserProfile)
        responsible2 = baker.make(UserProfile)
        # use is_single_result to get can_publish_average_grade to become true
        evaluation1 = baker.make(Evaluation, course__responsibles=[responsible1], is_single_result=True)
        evaluation2 = baker.make(Evaluation, course__responsibles=[responsible2])

        editor1 = baker.make(UserProfile)
        contributor1 = baker.make(UserProfile)

        contributor2 = baker.make(UserProfile)
        editor2 = baker.make(UserProfile)
        contributor_both = baker.make(UserProfile)

        # Contributions for evaluation1
        make_contributor(responsible1, evaluation1)
        make_contributor(contributor1, evaluation1)
        make_contributor(contributor_both, evaluation1)
        make_editor(editor1, evaluation1)

        # Contributions for evaluation2
        make_editor(editor2, evaluation2)
        contributor_both_contribution = make_contributor(contributor_both, evaluation2)
        contributor2_contribution = make_contributor(contributor2, evaluation2)

        baker.make(TextAnswer, contribution=contributor_both_contribution)
        baker.make(TextAnswer, contribution=contributor2_contribution)

        expected_calls = [
            # these 4 are included since they are contributors for evaluation1 which can publish the average grade
            call(responsible1, {}, {"user": responsible1, "evaluations": {evaluation1}}, use_cc=True),
            call(editor1, {}, {"user": editor1, "evaluations": {evaluation1}}, use_cc=True),
            call(contributor1, {}, {"user": contributor1, "evaluations": {evaluation1}}, use_cc=True),
            call(
                contributor_both, {}, {"user": contributor_both, "evaluations": {evaluation1, evaluation2}}, use_cc=True
            ),
            # contributor2 has textanswers, so they are notified
            call(contributor2, {}, {"user": contributor2, "evaluations": {evaluation2}}, use_cc=True),
        ]

        with patch("evap.evaluation.models.EmailTemplate.send_to_user") as send_to_user_mock:
            EmailTemplate.send_contributor_publish_notifications({evaluation1, evaluation2})
            # Assert that all expected publish notifications are sent to contributors.
            send_to_user_mock.assert_has_calls(expected_calls, any_order=True)

        # if general textanswers for an evaluation exist, all responsibles should also be notified
        baker.make(TextAnswer, contribution=evaluation2.general_contribution)
        expected_calls.append(call(responsible2, {}, {"user": responsible2, "evaluations": {evaluation2}}, use_cc=True))

        with patch("evap.evaluation.models.EmailTemplate.send_to_user") as send_to_user_mock:
            EmailTemplate.send_contributor_publish_notifications({evaluation1, evaluation2})
            send_to_user_mock.assert_has_calls(expected_calls, any_order=True)


class TestEmailRecipientList(TestCase):
    def test_recipient_list(self):
        evaluation = baker.make(Evaluation)
        responsible = baker.make(UserProfile)
        editor = baker.make(UserProfile)
        contributor = baker.make(UserProfile)
        evaluation.course.responsibles.set([responsible])
        baker.make(Contribution, evaluation=evaluation, contributor=editor, role=Contribution.Role.EDITOR)
        baker.make(Contribution, evaluation=evaluation, contributor=contributor)

        participant1 = baker.make(UserProfile, evaluations_participating_in=[evaluation])
        participant2 = baker.make(UserProfile, evaluations_participating_in=[evaluation])
        evaluation.voters.set([participant1])

        recipient_list = EmailTemplate.recipient_list_for_evaluation(evaluation, [], filter_users_in_cc=False)
        self.assertCountEqual(recipient_list, [])

        recipient_list = EmailTemplate.recipient_list_for_evaluation(
            evaluation, [EmailTemplate.Recipients.RESPONSIBLE], filter_users_in_cc=False
        )
        self.assertCountEqual(recipient_list, [responsible])

        recipient_list = EmailTemplate.recipient_list_for_evaluation(
            evaluation, [EmailTemplate.Recipients.EDITORS], filter_users_in_cc=False
        )
        self.assertCountEqual(recipient_list, [responsible, editor])

        recipient_list = EmailTemplate.recipient_list_for_evaluation(
            evaluation, [EmailTemplate.Recipients.CONTRIBUTORS], filter_users_in_cc=False
        )
        self.assertCountEqual(recipient_list, [responsible, editor, contributor])

        recipient_list = EmailTemplate.recipient_list_for_evaluation(
            evaluation, [EmailTemplate.Recipients.ALL_PARTICIPANTS], filter_users_in_cc=False
        )
        self.assertCountEqual(recipient_list, [participant1, participant2])

        recipient_list = EmailTemplate.recipient_list_for_evaluation(
            evaluation, [EmailTemplate.Recipients.DUE_PARTICIPANTS], filter_users_in_cc=False
        )
        self.assertCountEqual(recipient_list, [participant2])

    def test_recipient_list_filtering(self):
        evaluation = baker.make(Evaluation)

        contributor1 = baker.make(UserProfile)
        contributor2 = baker.make(UserProfile, delegates=[contributor1])

        baker.make(Contribution, evaluation=evaluation, contributor=contributor1)
        baker.make(Contribution, evaluation=evaluation, contributor=contributor2)

        # no-one should get filtered.
        recipient_list = EmailTemplate.recipient_list_for_evaluation(
            evaluation, [EmailTemplate.Recipients.CONTRIBUTORS], filter_users_in_cc=False
        )
        self.assertCountEqual(recipient_list, [contributor1, contributor2])

        # contributor1 is in cc of contributor2 and gets filtered.
        recipient_list = EmailTemplate.recipient_list_for_evaluation(
            evaluation, [EmailTemplate.Recipients.CONTRIBUTORS], filter_users_in_cc=True
        )
        self.assertCountEqual(recipient_list, [contributor2])

        contributor3 = baker.make(UserProfile, delegates=[contributor2])
        baker.make(Contribution, evaluation=evaluation, contributor=contributor3)

        # again, no-one should get filtered.
        recipient_list = EmailTemplate.recipient_list_for_evaluation(
            evaluation, [EmailTemplate.Recipients.CONTRIBUTORS], filter_users_in_cc=False
        )
        self.assertCountEqual(recipient_list, [contributor1, contributor2, contributor3])

        # contributor1 is in cc of contributor2 and gets filtered.
        # contributor2 is in cc of contributor3 but is not filtered since contributor1 wouldn't get an email at all then.
        recipient_list = EmailTemplate.recipient_list_for_evaluation(
            evaluation, [EmailTemplate.Recipients.CONTRIBUTORS], filter_users_in_cc=True
        )
        self.assertCountEqual(recipient_list, [contributor2, contributor3])


class QuestionnaireTests(TestCase):
    def test_locked_contributor_questionnaire(self):
        questionnaire = baker.prepare(Questionnaire, is_locked=True, type=Questionnaire.Type.CONTRIBUTOR)
        self.assertRaises(ValidationError, questionnaire.clean)
