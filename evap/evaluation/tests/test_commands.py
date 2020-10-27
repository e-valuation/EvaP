from collections import defaultdict
from datetime import datetime, date, timedelta
from io import StringIO
from itertools import chain, cycle
import os
import random
from unittest.mock import patch

from django.conf import settings
from django.core import management, mail
from django.db.models import Sum
from django.test import TestCase
from django.test.utils import override_settings

from model_bakery import baker

from evap.evaluation.models import (CHOICES, Contribution, Course, Evaluation, EmailTemplate, NO_ANSWER,
    Question, Questionnaire, RatingAnswerCounter, Semester, UserProfile)


class TestAnonymizeCommand(TestCase):
    @classmethod
    def setUpTestData(cls):
        baker.make(EmailTemplate, name="name", subject="Subject", body="Body.")
        baker.make(UserProfile,
          email="secret.email@hpi.de",
          title="Prof.",
          first_name="Secret",
          last_name="User",
          login_key=1234567890,
          login_key_valid_until=date.today())
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

        cls.contributor_questions = baker.make(Question, _quantity=10,
                questionnaire=cls.contributor_questionnaire, type=cycle(iter(CHOICES.keys())))
        cls.general_questions = baker.make(Question, _quantity=10,
                questionnaire=cls.contributor_questionnaire, type=cycle(iter(CHOICES.keys())))

        cls.contributor = baker.make(UserProfile)

        cls.contribution = baker.make(Contribution, contributor=cls.contributor, evaluation=cls.evaluation,
            questionnaires=[cls.contributor_questionnaire, cls.contributor_questionnaire])

        cls.general_contribution = cls.evaluation.general_contribution
        cls.general_contribution.questionnaires.set([cls.general_questionnaire])
        cls.general_contribution.save()

    def setUp(self):
        self.input_patch = patch('builtins.input')
        self.input_mock = self.input_patch.start()
        self.input_mock.return_value = 'yes'
        self.addCleanup(self.input_patch.stop)

    def test_no_empty_rating_answer_counters_left(self):
        for question in chain(self.contributor_questions, self.general_questions):
            choices = [choice for choice in CHOICES[question.type].values if choice != NO_ANSWER]
            for answer in choices:
                baker.make(RatingAnswerCounter, question=question, contribution=self.contribution, count=1, answer=answer)

        old_count = RatingAnswerCounter.objects.count()

        random.seed(0)
        management.call_command('anonymize', stdout=StringIO())

        new_count = RatingAnswerCounter.objects.count()
        self.assertLess(new_count, old_count)

        for counter in RatingAnswerCounter.objects.all():
            self.assertGreater(counter.count, 0)

    def test_question_with_no_answers(self):
        management.call_command('anonymize', stdout=StringIO())
        self.assertEqual(RatingAnswerCounter.objects.count(), 0)

    def test_answer_count_unchanged(self):
        answers_per_question = defaultdict(int)
        random.seed(0)
        for question in chain(self.contributor_questions, self.general_questions):
            choices = [choice for choice in CHOICES[question.type].values if choice != NO_ANSWER]
            for answer in choices:
                count = random.randint(10, 100)  # nosec
                baker.make(RatingAnswerCounter, question=question, contribution=self.contribution, count=count, answer=answer)
                answers_per_question[question] += count

        management.call_command('anonymize', stdout=StringIO())

        for question in chain(self.contributor_questions, self.general_questions):
            answer_count = RatingAnswerCounter.objects.filter(question=question).aggregate(Sum('count'))["count__sum"]
            self.assertEqual(answers_per_question[question], answer_count)

    def test_single_result_anonymization(self):
        questionnaire = Questionnaire.single_result_questionnaire()
        single_result = baker.make(Evaluation, is_single_result=True, course=self.course)
        single_result.general_contribution.questionnaires.set([questionnaire])
        question = Question.objects.get(questionnaire=questionnaire)

        answer_count_before = 0
        choices = [choice for choice in CHOICES[question.type].values if choice != NO_ANSWER]
        random.seed(0)
        for answer in choices:
            count = random.randint(50, 100)  # nosec
            baker.make(RatingAnswerCounter, question=question, contribution=single_result.general_contribution, count=count, answer=answer)
            answer_count_before += count

        management.call_command('anonymize', stdout=StringIO())

        self.assertLessEqual(RatingAnswerCounter.objects.count(), len(choices))
        self.assertEqual(RatingAnswerCounter.objects.aggregate(Sum('count'))["count__sum"], answer_count_before)


class TestRunCommand(TestCase):
    @staticmethod
    def test_calls_runserver():
        args = ["manage.py", "runserver", "0.0.0.0:8000"]
        with patch('django.core.management.execute_from_command_line') as mock:
            management.call_command('run', stdout=StringIO())

        mock.assert_called_once_with(args)


class TestReloadTestdataCommand(TestCase):
    @patch('builtins.input')
    @patch('evap.evaluation.management.commands.reload_testdata.call_command')
    def test_aborts(self, mock_call_command, mock_input):
        mock_input.return_value = 'not yes'

        management.call_command('reload_testdata', stdout=StringIO())

        self.assertEqual(mock_call_command.call_count, 0)

    @patch('builtins.input')
    @patch('evap.evaluation.management.commands.reload_testdata.call_command')
    def test_executes_key_commands(self, mock_call_command, mock_input):
        mock_input.return_value = 'yes'

        management.call_command('reload_testdata', stdout=StringIO())

        mock_call_command.assert_any_call('reset_db', interactive=False)
        mock_call_command.assert_any_call('migrate')
        mock_call_command.assert_any_call('flush', interactive=False)
        mock_call_command.assert_any_call('loaddata', 'test_data')
        mock_call_command.assert_any_call('clear_cache')
        mock_call_command.assert_any_call('refresh_results_cache')
        mock_call_command.assert_any_call('clear_cache', '--cache=sessions')

        self.assertEqual(mock_call_command.call_count, 7)


class TestRefreshResultsCacheCommand(TestCase):
    def test_calls_cache_results(self):
        baker.make(Evaluation, state='published')

        with patch('evap.evaluation.management.commands.refresh_results_cache.cache_results') as mock:
            management.call_command('refresh_results_cache', stdout=StringIO())

        self.assertEqual(mock.call_count, Evaluation.objects.count())


class TestUpdateEvaluationStatesCommand(TestCase):
    def test_update_evaluations_called(self):
        with patch('evap.evaluation.models.Evaluation.update_evaluations') as mock:
            management.call_command('update_evaluation_states')

        self.assertEqual(mock.call_count, 1)


class TestDumpTestDataCommand(TestCase):
    @staticmethod
    def test_dumpdata_called():
        with patch('evap.evaluation.management.commands.dump_testdata.call_command') as mock:
            management.call_command('dump_testdata')

        outfile_name = os.path.join(settings.BASE_DIR, "evaluation", "fixtures", "test_data.json")
        mock.assert_called_once_with('dumpdata', 'auth.group', 'evaluation', 'rewards', 'student', 'grades',
                                     '--exclude=evaluation.LogEntry', indent=2, natural_foreign=True,
                                     natural_primary=True, output=outfile_name)


@override_settings(REMIND_X_DAYS_AHEAD_OF_END_DATE=[0, 2])
class TestSendRemindersCommand(TestCase):
    def test_remind_user_about_one_evaluation(self):
        user_to_remind = baker.make(UserProfile)
        evaluation = baker.make(
            Evaluation,
            state='in_evaluation',
            vote_start_datetime=datetime.now() - timedelta(days=1),
            vote_end_date=date.today() + timedelta(days=2),
            participants=[user_to_remind])

        with patch('evap.evaluation.models.EmailTemplate.send_reminder_to_user') as mock:
            management.call_command('send_reminders')

        self.assertEqual(mock.call_count, 1)
        mock.assert_called_once_with(user_to_remind, first_due_in_days=2, due_evaluations=[(evaluation, 2)])

    def test_remind_user_once_about_two_evaluations(self):
        user_to_remind = baker.make(UserProfile)
        evaluation1 = baker.make(
            Evaluation,
            state='in_evaluation',
            vote_start_datetime=datetime.now() - timedelta(days=1),
            vote_end_date=date.today() + timedelta(days=0),
            participants=[user_to_remind])
        evaluation2 = baker.make(
            Evaluation,
            state='in_evaluation',
            vote_start_datetime=datetime.now() - timedelta(days=1),
            vote_end_date=date.today() + timedelta(days=2),
            participants=[user_to_remind])

        with patch('evap.evaluation.models.EmailTemplate.send_reminder_to_user') as mock:
            management.call_command('send_reminders')

        self.assertEqual(mock.call_count, 1)
        mock.assert_called_once_with(user_to_remind, first_due_in_days=0, due_evaluations=[(evaluation1, 0), (evaluation2, 2)])

    def test_dont_remind_already_voted(self):
        user_no_remind = baker.make(UserProfile)
        baker.make(
            Evaluation,
            state='in_evaluation',
            vote_start_datetime=datetime.now() - timedelta(days=1),
            vote_end_date=date.today() + timedelta(days=2),
            participants=[user_no_remind],
            voters=[user_no_remind])

        with patch('evap.evaluation.models.EmailTemplate.send_reminder_to_user') as mock:
            management.call_command('send_reminders')

        self.assertEqual(mock.call_count, 0)
        self.assertEqual(len(mail.outbox), 0)
