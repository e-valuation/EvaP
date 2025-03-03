from datetime import date, datetime, timedelta

from django.utils.formats import localize
from model_bakery import baker

from evap.evaluation.models import Contribution, Course, Evaluation, Questionnaire, UserProfile
from evap.evaluation.models_logging import FieldAction, InstanceActionType
from evap.evaluation.tests.tools import TestCase


class TestLoggedModel(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.old_start_date = datetime.now()
        cls.new_start_date = cls.old_start_date + timedelta(days=10)

        cls.course = baker.make(Course)

        cls.evaluation = baker.make(
            Evaluation,
            course=cls.course,
            state=Evaluation.State.PREPARED,
            vote_start_datetime=cls.old_start_date,
            vote_end_date=date.today() + timedelta(days=20),
        )
        cls.evaluation.save()  # first logentry

        cls.evaluation.vote_start_datetime = cls.new_start_date
        cls.evaluation.save()  # second logentry

        cls.logentry = cls.evaluation.related_logentries()[1]

    def test_voters_not_in_evaluation_data(self):
        self.assertFalse(any("voters" in entry.data for entry in self.evaluation.related_logentries()))

    def test_datetime_change(self):
        self.assertEqual(
            self.logentry.data["vote_start_datetime"],
            {"change": [localize(self.old_start_date), localize(self.new_start_date)]},
        )

    def test_data_attribute_is_correctly_parsed_to_fieldactions(self):
        self.assertEqual(
            self.logentry.field_context_data["vote_start_datetime"],
            [
                FieldAction(
                    "Start of evaluation",
                    "change",
                    [localize(self.old_start_date), localize(self.new_start_date)],
                )
            ],
        )

    def test_deletion_data(self):
        self.assertEqual(
            self.evaluation._get_change_data(action_type=InstanceActionType.DELETE)["course"]["delete"][0],
            self.course.id,
        )
        self.evaluation.delete()
        self.assertEqual(self.evaluation.related_logentries().count(), 0)

    def test_creation(self):
        course = baker.make(Course)
        self.assertEqual(course.related_logentries().count(), 1)

    def test_bulk_creation(self):
        course = baker.make(Course)
        evaluation = baker.prepare(Evaluation, course=course)
        Evaluation.objects.bulk_create([evaluation])
        Evaluation.update_log_after_bulk_create([evaluation])

        self.assertEqual(evaluation.related_logentries().count(), 1)

    def test_related_logged_model_creation(self):
        self.assertEqual(self.evaluation.related_logentries().count(), 2)
        contribution = baker.make(Contribution, evaluation=self.evaluation)
        self.assertFalse(contribution.related_logentries().exists())
        self.assertEqual(self.evaluation.related_logentries().count(), 3)

    def test_m2m_creation(self):
        self.assertEqual(self.evaluation.related_logentries().count(), 2)
        questionnaire = baker.make(Questionnaire)
        contribution = self.evaluation.contributions.get(contributor__isnull=True)
        contribution.questionnaires.add(questionnaire)
        self.assertEqual(self.evaluation.related_logentries().count(), 3)
        self.assertEqual(
            self.evaluation.related_logentries().order_by("id").last().data["questionnaires"]["add"], [questionnaire.id]
        )

    def test_m2m_bulk_creation(self):
        self.assertEqual(self.evaluation.related_logentries().count(), 2)

        participant1 = baker.make(UserProfile)
        through1 = Evaluation.participants.through(evaluation=self.evaluation, userprofile=participant1)

        Evaluation.participants.through.objects.bulk_create([through1])
        Evaluation.update_log_after_m2m_bulk_create(
            [self.evaluation],  # this already has a logentry attached, it should be updated
            [through1],
            "evaluation_id",
            "userprofile_id",
            "participants",
        )
        self.assertEqual(self.evaluation.related_logentries().count(), 2)
        self.assertEqual(
            self.evaluation.related_logentries().order_by("id").first().data["participants"]["add"],
            [participant1.pk],
        )

        evaluation = Evaluation.objects.get(pk=self.evaluation.pk)
        participant2 = baker.make(UserProfile)
        through2 = Evaluation.participants.through(evaluation=evaluation, userprofile=participant2)

        Evaluation.participants.through.objects.bulk_create([through2])
        Evaluation.update_log_after_m2m_bulk_create(
            [evaluation],  # no logentry so far
            [through2],
            "evaluation_id",
            "userprofile_id",
            "participants",
        )
        self.assertEqual(self.evaluation.related_logentries().count(), 3)
        self.assertEqual(
            self.evaluation.related_logentries().order_by("id").last().data["participants"]["add"],
            [participant2.pk],
        )

    def test_none_value_not_included_on_creation(self):
        contributor = baker.make(UserProfile)
        baker.make(Contribution, evaluation=self.evaluation, contributor=contributor)
        self.assertIn("contributor", self.evaluation.related_logentries().order_by("id").last().data)

        baker.make(Contribution, evaluation=self.evaluation, contributor=None)
        self.assertNotIn("contributor", self.evaluation.related_logentries().order_by("id").last().data)

    def test_simultaneous_add_and_remove(self):
        # Regression test for https://github.com/e-valuation/EvaP/issues/1594
        participant1 = baker.make(UserProfile)
        participant2 = baker.make(UserProfile)
        self.evaluation.participants.add(participant1)
        # Refresh reference to evaluation, to force new log entry
        self.evaluation = Evaluation.objects.get(pk=self.evaluation.pk)

        self.evaluation.participants.remove(participant1)
        self.evaluation.participants.add(participant2)
        self.assertEqual(
            self.evaluation.related_logentries().order_by("id").last().data,
            {"participants": {"add": [participant2.id], "remove": [participant1.id]}},
        )
