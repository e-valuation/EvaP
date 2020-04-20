from datetime import datetime, timedelta, date
from unittest.mock import patch, Mock

from django.test import TestCase, override_settings

from django_webtest import WebTest
from model_bakery import baker

import json

from evap.evaluation.models import (Contribution, Course, CourseType, EmailTemplate, Evaluation, FieldAction, NotArchiveable,
                                    Question, Questionnaire, RatingAnswerCounter, Semester, TextAnswer, UserProfile, log_serialize)


"""
Create an Evaluation
check the LogEntry
make a change
check the LogEntry
"""


class TestLoggedModel(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.old_start_date = datetime.now()
        cls.new_start_date =  cls.old_start_date + timedelta(days=10)
        cls.evaluation = baker.make(Evaluation,
                state='prepared',
                vote_start_datetime=cls.old_start_date,
                vote_end_date=date.today() + timedelta(days=20),
        )
        cls.evaluation.save()  # first logentry
        
        cls.evaluation.vote_start_datetime = cls.new_start_date
        cls.evaluation.save()  # second logentry

        cls.logentry = cls.evaluation.all_logentries()[1]

    def test_logentries_get_created(self):
        self.assertEqual(len(self.evaluation.all_logentries()), 2)

    def test_changes_are_recorded_to_data_attribute(self):
        self.assertEqual(json.loads(self.logentry.data), {
            'vote_start_datetime': {
                    'change': [log_serialize(self.old_start_date), log_serialize(self.new_start_date)]
                }
            })

    def test_data_attribute_is_correctly_parsed_to_fieldactions(self):
        self.assertEqual(self.logentry._evaluation_log_template_context(json.loads(self.logentry.data)), {
            'vote_start_datetime': [
                FieldAction(
                    "start of evaluation",
                    "change",
                    [log_serialize(self.old_start_date), log_serialize(self.new_start_date)]
                )
            ]
        })


