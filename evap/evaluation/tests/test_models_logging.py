from datetime import date, datetime, timedelta

from django.test import TestCase
from django.utils.formats import localize
from model_bakery import baker

from evap.evaluation.models import Evaluation, Course, Contribution, Questionnaire
from evap.evaluation.models_logging import FieldAction


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
        self.assertEqual(self.evaluation._get_change_data(action_type="delete")["course"]["delete"][0], self.course.id)
        self.evaluation.delete()
        self.assertEqual(self.evaluation.related_logentries().count(), 0)

    def test_creation(self):
        course = baker.make(Course)
        self.assertEqual(course.related_logentries().count(), 1)

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

    def test_none_value_not_included(self):
        baker.make(Contribution, evaluation=self.evaluation, label="testlabel")
        self.assertIn("label", self.evaluation.related_logentries().order_by("id").last().data)

        baker.make(Contribution, evaluation=self.evaluation, label=None)
        self.assertNotIn("label", self.evaluation.related_logentries().order_by("id").last().data)
