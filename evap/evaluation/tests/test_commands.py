import os
import random
from collections import defaultdict
from datetime import date, datetime, timedelta
from io import StringIO
from itertools import chain, cycle
from unittest.mock import MagicMock, call, patch

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core import mail, management
from django.core.management import CommandError
from django.db.models import Sum
from django.test.utils import override_settings
from model_bakery import baker

from evap.evaluation.models import (
    CHOICES,
    NO_ANSWER,
    Contribution,
    Course,
    EmailTemplate,
    Evaluation,
    Question,
    Questionnaire,
    RatingAnswerCounter,
    Semester,
    TextAnswer,
    UserProfile,
)
from evap.evaluation.tests.tools import TestCase, make_manager, make_rating_answer_counters
from evap.tools import MonthAndDay


class TestAnonymizeCommand(TestCase):
    @classmethod
    def setUpTestData(cls):
        baker.make(EmailTemplate, name="name", subject="Subject", plain_content="Body.")
        baker.make(
            UserProfile,
            email="secret.email@hpi.de",
            title="Prof.",
            first_name_given="Secret",
            last_name="User",
            password=make_password(None),
            login_key=1234567890,
            login_key_valid_until=date.today(),
        )
        semester1 = baker.make(Semester, name_de="S1", name_en="S1")
        baker.make(Semester, name_de="S2", name_en="S2")
        cls.course = baker.make(
            Course,
            semester=semester1,
            name_de="Eine private Veranstaltung",
            name_en="A private course",
            is_private=True,
        )
        course2 = baker.make(
            Course,
            semester=semester1,
            name_de="Veranstaltungsexperimente",
            name_en="Course experiments",
        )
        cls.evaluation = baker.make(
            Evaluation,
            course=cls.course,
            name_de="Wie man Software testet",
            name_en="Testing your software",
        )
        baker.make(
            Evaluation,
            course=course2,
            name_de="Die Entstehung von Unicode 😄",
            name_en="History of Unicode 😄",
        )

        cls.contributor_questionnaire = baker.make(Questionnaire, type=Questionnaire.Type.CONTRIBUTOR)
        cls.general_questionnaire = baker.make(Questionnaire, type=Questionnaire.Type.TOP)

        cls.contributor_questions = baker.make(
            Question,
            _bulk_create=True,
            _quantity=10,
            questionnaire=cls.contributor_questionnaire,
            type=cycle(iter(CHOICES.keys())),
        )
        cls.general_questions = baker.make(
            Question,
            _bulk_create=True,
            _quantity=10,
            questionnaire=cls.contributor_questionnaire,
            type=cycle(iter(CHOICES.keys())),
        )

        cls.contributor = baker.make(UserProfile, password=make_password(None))

        cls.contribution = baker.make(
            Contribution,
            contributor=cls.contributor,
            evaluation=cls.evaluation,
            questionnaires=[cls.contributor_questionnaire, cls.contributor_questionnaire],
        )

        cls.general_contribution = cls.evaluation.general_contribution
        cls.general_contribution.questionnaires.set([cls.general_questionnaire])
        cls.general_contribution.save()

    def setUp(self):
        self.input_patch = patch("builtins.input")
        self.input_mock = self.input_patch.start()
        self.input_mock.return_value = "yes"
        self.addCleanup(self.input_patch.stop)

    def test_no_empty_rating_answer_counters_left(self):
        counters = []
        for question in chain(self.contributor_questions, self.general_questions):
            counts = [1 for choice in CHOICES[question.type].values if choice != NO_ANSWER]
            counters.extend(make_rating_answer_counters(question, self.contribution, counts, False))
        RatingAnswerCounter.objects.bulk_create(counters)

        old_count = RatingAnswerCounter.objects.count()

        management.call_command("anonymize", stdout=StringIO())

        new_count = RatingAnswerCounter.objects.count()
        self.assertLess(new_count, old_count)

        for counter in RatingAnswerCounter.objects.all():
            self.assertGreater(counter.count, 0)

    def test_question_with_no_answers(self):
        management.call_command("anonymize", stdout=StringIO())
        self.assertEqual(RatingAnswerCounter.objects.count(), 0)

    def test_answer_count_unchanged(self):
        answers_per_question = defaultdict(int)

        counters = []
        for question in chain(self.contributor_questions, self.general_questions):
            counts = [random.randint(10, 100) for choice in CHOICES[question.type].values if choice != NO_ANSWER]
            counters.extend(make_rating_answer_counters(question, self.contribution, counts, False))
            answers_per_question[question] += sum(counts)
        RatingAnswerCounter.objects.bulk_create(counters)

        management.call_command("anonymize", stdout=StringIO())

        for question in chain(self.contributor_questions, self.general_questions):
            answer_count = RatingAnswerCounter.objects.filter(question=question).aggregate(Sum("count"))["count__sum"]
            self.assertEqual(answers_per_question[question], answer_count)

    def test_single_result_anonymization(self):
        questionnaire = Questionnaire.single_result_questionnaire()
        single_result = baker.make(Evaluation, is_single_result=True, course=self.course)
        single_result.general_contribution.questionnaires.set([questionnaire])
        question = Question.objects.get(questionnaire=questionnaire)

        answer_count_before = 0
        choices = [choice for choice in CHOICES[question.type].values if choice != NO_ANSWER]

        answer_counts = [random.randint(50, 100) for answer in choices]
        answer_count_before = sum(answer_counts)
        make_rating_answer_counters(question, single_result.general_contribution, answer_counts)

        management.call_command("anonymize", stdout=StringIO())

        self.assertLessEqual(RatingAnswerCounter.objects.count(), len(choices))
        self.assertEqual(RatingAnswerCounter.objects.aggregate(Sum("count"))["count__sum"], answer_count_before)

    def test_user_with_password(self):
        baker.make(UserProfile, password=make_password("evap"))
        with self.assertRaises(AssertionError):
            management.call_command("anonymize", stdout=StringIO())


class TestRefreshResultsCacheCommand(TestCase):
    def test_calls_cache_results(self):
        baker.make(Evaluation, state=Evaluation.State.PUBLISHED)

        with patch("evap.evaluation.management.commands.refresh_results_cache.cache_results") as mock:
            management.call_command("refresh_results_cache", stdout=StringIO())

        self.assertEqual(mock.call_count, Evaluation.objects.count())


class TestScssCommand(TestCase):
    def setUp(self):
        self.scss_path = os.path.join(settings.STATICFILES_DIRS[0], "scss", "evap.scss")
        self.css_path = os.path.join(settings.STATICFILES_DIRS[0], "css", "evap.css")

    @patch("subprocess.run")
    def test_scss_called(self, mock_subprocess_run):
        management.call_command("scss")

        mock_subprocess_run.assert_called_once_with(
            ["npx", "sass", self.scss_path, self.css_path],
            check=True,
        )

    @patch("subprocess.run")
    def test_scss_watch_called(self, mock_subprocess_run):
        mock_subprocess_run.side_effect = KeyboardInterrupt

        management.call_command("scss", "--watch")

        mock_subprocess_run.assert_called_once_with(
            ["npx", "sass", self.scss_path, self.css_path, "--watch", "--poll"],
            check=True,
        )

    @patch("subprocess.run")
    def test_scss_production_called(self, mock_subprocess_run):
        management.call_command("scss", "--production")

        mock_subprocess_run.assert_called_once_with(
            ["npx", "sass", self.scss_path, self.css_path, "--style", "compressed", "--no-source-map"],
            check=True,
        )

    @patch("subprocess.run")
    def test_scss_called_with_no_sass_installed(self, mock_subprocess_run):
        mock_subprocess_run.side_effect = FileNotFoundError()

        with self.assertRaisesMessage(CommandError, "Could not find sass command"):
            management.call_command("scss")


class TestTsCommend(TestCase):
    def setUp(self):
        self.ts_path = os.path.join(settings.STATICFILES_DIRS[0], "ts")

    @patch("subprocess.run")
    def test_ts_compile(self, mock_subprocess_run):
        management.call_command("ts", "compile")

        mock_subprocess_run.assert_called_once_with(
            ["npx", "tsc", "--project", os.path.join(self.ts_path, "tsconfig.compile.json")],
            check=True,
        )

    @patch("subprocess.run")
    def test_ts_compile_with_watch(self, mock_subprocess_run):
        mock_subprocess_run.side_effect = KeyboardInterrupt

        management.call_command("ts", "compile", "--watch")

        mock_subprocess_run.assert_called_once_with(
            ["npx", "tsc", "--project", os.path.join(self.ts_path, "tsconfig.compile.json"), "--watch"],
            check=True,
        )

    @patch("subprocess.run")
    @patch("evap.evaluation.management.commands.ts.call_command")
    @patch("evap.evaluation.management.commands.ts.Command.render_pages")
    def test_ts_test(self, mock_render_pages, mock_call_command, mock_subprocess_run):
        management.call_command("ts", "test")

        # Mock render pages to prevent a second call into the test framework
        mock_render_pages.assert_called_once()
        mock_call_command.assert_called_once_with("scss")
        mock_subprocess_run.assert_has_calls(
            [
                call(
                    ["npx", "tsc", "--project", os.path.join(self.ts_path, "tsconfig.compile.json")],
                    check=True,
                ),
                call(["npx", "jest"], check=True),
            ]
        )

    @patch("subprocess.run")
    def test_ts_called_with_no_npm_installed(self, mock_subprocess_run):
        mock_subprocess_run.side_effect = FileNotFoundError()

        with self.assertRaisesMessage(CommandError, "Could not find npx command"):
            management.call_command("ts", "compile")


class TestUpdateEvaluationStatesCommand(TestCase):
    def test_update_evaluations_called(self):
        with patch("evap.evaluation.models.Evaluation.update_evaluations") as mock:
            management.call_command("update_evaluation_states")

        self.assertEqual(mock.call_count, 1)


@override_settings(REMIND_X_DAYS_AHEAD_OF_END_DATE=[0, 2])
class TestSendRemindersCommand(TestCase):
    def test_remind_user_about_one_evaluation(self):
        user_to_remind = baker.make(UserProfile)
        evaluation = baker.make(
            Evaluation,
            state=Evaluation.State.IN_EVALUATION,
            vote_start_datetime=datetime.now() - timedelta(days=1),
            vote_end_date=date.today() + timedelta(days=2),
            participants=[user_to_remind],
        )

        with patch("evap.evaluation.models.EmailTemplate.send_reminder_to_user") as mock:
            management.call_command("send_reminders")

        self.assertEqual(mock.call_count, 1)
        mock.assert_called_once_with(user_to_remind, first_due_in_days=2, due_evaluations=[(evaluation, 2)])

    def test_remind_user_once_about_two_evaluations(self):
        user_to_remind = baker.make(UserProfile)
        evaluation1 = baker.make(
            Evaluation,
            state=Evaluation.State.IN_EVALUATION,
            vote_start_datetime=datetime.now() - timedelta(days=1),
            vote_end_date=date.today() + timedelta(days=0),
            participants=[user_to_remind],
        )
        evaluation2 = baker.make(
            Evaluation,
            state=Evaluation.State.IN_EVALUATION,
            vote_start_datetime=datetime.now() - timedelta(days=1),
            vote_end_date=date.today() + timedelta(days=2),
            participants=[user_to_remind],
        )

        with patch("evap.evaluation.models.EmailTemplate.send_reminder_to_user") as mock:
            management.call_command("send_reminders")

        self.assertEqual(mock.call_count, 1)
        mock.assert_called_once_with(
            user_to_remind, first_due_in_days=0, due_evaluations=[(evaluation1, 0), (evaluation2, 2)]
        )

    def test_dont_remind_already_voted(self):
        user_no_remind = baker.make(UserProfile)
        baker.make(
            Evaluation,
            state=Evaluation.State.IN_EVALUATION,
            vote_start_datetime=datetime.now() - timedelta(days=1),
            vote_end_date=date.today() + timedelta(days=2),
            participants=[user_no_remind],
            voters=[user_no_remind],
        )

        with patch("evap.evaluation.models.EmailTemplate.send_reminder_to_user") as mock:
            management.call_command("send_reminders")

        self.assertEqual(mock.call_count, 0)
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(TEXTANSWER_REVIEW_REMINDER_WEEKDAYS=list(range(7)))
    def test_send_text_answer_review_reminder(self):
        manager = make_manager()
        evaluation = baker.make(
            Evaluation,
            state=Evaluation.State.EVALUATED,
            can_publish_text_results=True,
            wait_for_grade_upload_before_publishing=False,
        )
        baker.make(
            TextAnswer,
            contribution=evaluation.general_contribution,
        )

        with patch("evap.evaluation.models.EmailTemplate.send_to_user") as mock:
            management.call_command("send_reminders")

        mock.assert_has_calls(
            [
                call(
                    manager,
                    subject_params={},
                    body_params={
                        "user": manager,
                        "evaluation_url_tuples": [
                            (
                                evaluation,
                                f"{settings.PAGE_URL}/staff/evaluation/{evaluation.id}/textanswers",
                            )
                        ],
                    },
                    use_cc=False,
                ),
            ]
        )

    @override_settings(
        GRADE_REMINDER_EMAIL_RECIPIENTS=["test1@example.com", "test2@example.com"],
        GRADE_REMINDER_EMAIL_DATES=[
            MonthAndDay(month=date.today().month, day=(date.today() + timedelta(days=1)).day),
            MonthAndDay(month=date.today().month, day=date.today().day),
        ],
    )
    def test_send_grade_reminder(self):
        semester1 = baker.make(Semester)
        semester2 = baker.make(Semester)

        responsible = baker.make(UserProfile)
        course_args = {"responsibles": [responsible], "gets_no_grade_documents": False}

        course1 = baker.make(Course, name_en="Z-Course1", semester=semester1, **course_args)
        course2 = baker.make(Course, name_en="A-Course2", semester=semester1, **course_args)

        course3 = baker.make(Course, name_en="Course3", semester=semester2, **course_args)
        baker.make(Course, name_en="Course4", semester=semester2, **course_args)

        baker.make(
            Evaluation,
            course=iter([course1, course1, course2, course3]),
            state=Evaluation.State.EVALUATED,
            wait_for_grade_upload_before_publishing=True,
            _fill_optional=["name_de", "name_en"],
            _quantity=4,
        )

        with patch("evap.evaluation.models.EmailTemplate.send_to_address") as send_mock:
            management.call_command("send_reminders")

        send_mock.assert_has_calls(
            [
                call(
                    recipient_email="test1@example.com",
                    subject_params={"semester": semester1},
                    body_params={
                        "semester": semester1,
                        "responsibles_and_courses_without_final_grades": {responsible: [course2, course1]}.items(),
                    },
                ),
                call(
                    recipient_email="test2@example.com",
                    subject_params={"semester": semester1},
                    body_params={
                        "semester": semester1,
                        "responsibles_and_courses_without_final_grades": {responsible: [course2, course1]}.items(),
                    },
                ),
                call(
                    recipient_email="test1@example.com",
                    subject_params={"semester": semester2},
                    body_params={
                        "semester": semester2,
                        "responsibles_and_courses_without_final_grades": {responsible: [course3]}.items(),
                    },
                ),
                call(
                    recipient_email="test2@example.com",
                    subject_params={"semester": semester2},
                    body_params={
                        "semester": semester2,
                        "responsibles_and_courses_without_final_grades": {responsible: [course3]}.items(),
                    },
                ),
            ]
        )


class TestLintCommand(TestCase):
    @patch("subprocess.run")
    def test_pylint_called(self, mock_subprocess_run: MagicMock):
        management.call_command("lint", stdout=StringIO())
        self.assertEqual(mock_subprocess_run.call_count, 3)
        mock_subprocess_run.assert_any_call(["ruff", "check", "."], check=False)
        mock_subprocess_run.assert_any_call(["pylint", "evap", "tools"], check=False)
        mock_subprocess_run.assert_any_call(["npx", "eslint", "--quiet"], cwd="evap/static/ts", check=False)


class TestFormatCommand(TestCase):
    @patch("subprocess.run")
    def test_formatters_called(self, mock_subprocess_run):
        management.call_command("format")
        self.assertEqual(len(mock_subprocess_run.mock_calls), 3)
        mock_subprocess_run.assert_has_calls(
            [
                call(["black", "."], check=False),
                call(["isort", "."], check=False),
                call(["npx", "prettier", "--write", "evap/static/ts/**/*.ts"], check=False),
            ]
        )


class TestTypecheckCommand(TestCase):
    @patch("subprocess.run")
    def test_mypy_called(self, mock_subprocess_run):
        management.call_command("typecheck")
        self.assertEqual(len(mock_subprocess_run.mock_calls), 1)
        mock_subprocess_run.assert_has_calls([call(["mypy"], check=True)])


class TestPrecommitCommand(TestCase):
    @patch("subprocess.run")
    @patch("evap.evaluation.management.commands.precommit.call_command")
    def test_subcommands_called(self, mock_call_command, mock_subprocess_run):
        management.call_command("precommit")

        mock_subprocess_run.assert_called_with(["./manage.py", "test"], check=False)

        self.assertEqual(mock_call_command.call_count, 3)
        mock_call_command.assert_any_call("typecheck")
        mock_call_command.assert_any_call("lint")
        mock_call_command.assert_any_call("format")


@override_settings(TEXTANSWER_REVIEW_REMINDER_WEEKDAYS=range(7))
class TestSendTextanswerRemindersCommand(TestCase):
    def test_send_reminder(self):
        make_manager()
        evaluation = baker.make(
            Evaluation,
            state=Evaluation.State.EVALUATED,
            wait_for_grade_upload_before_publishing=False,
            can_publish_text_results=True,
        )
        baker.make(
            TextAnswer,
            contribution=evaluation.general_contribution,
            review_decision=TextAnswer.ReviewDecision.UNDECIDED,
        )

        management.call_command("send_reminders")

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(evaluation.name, mail.outbox[0].body)

    def test_send_no_reminder_if_not_needed(self):
        make_manager()
        management.call_command("send_reminders")
        self.assertEqual(len(mail.outbox), 0)
