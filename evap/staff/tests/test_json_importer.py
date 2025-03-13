import json
import os
from datetime import date, datetime
from io import StringIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core import mail
from django.core.management import call_command
from django.test import TestCase
from model_bakery import baker

from evap.evaluation.models import Contribution, Course, Evaluation, Questionnaire, Semester, UserProfile
from evap.evaluation.tests.tools import make_manager
from evap.staff.importers.json import ImportDict, JSONImporter, NameChange

EXAMPLE_DATA: ImportDict = {
    "students": [
        {"gguid": "0x1", "email": "1@example.com", "name": "1", "christianname": "1"},
        {"gguid": "0x2", "email": "2@example.com", "name": "2", "christianname": "2"},
    ],
    "lecturers": [
        {"gguid": "0x3", "email": "3@example.com", "name": "3", "christianname": "3", "titlefront": "Prof. Dr."},
        {"gguid": "0x4", "email": "4@example.com", "name": "4", "christianname": "4", "titlefront": "Dr."},
        {"gguid": "0x5", "email": "5@example.com", "name": "5", "christianname": "5", "titlefront": ""},
        {"gguid": "0x6", "email": "6@example.com", "name": "6", "christianname": "6", "titlefront": ""},
    ],
    "events": [
        {
            "gguid": "0x5",
            "lvnr": 1,
            "title": "Prozessorientierte Informationssysteme",
            "title_en": "Process-oriented information systems",
            "type": "Vorlesung",
            "isexam": False,
            "courses": [],
            "relatedevents": {"gguid": "0x6"},
            "appointments": [{"begin": "15.04.2024 10:15:00", "end": "15.07.2024 11:45:00"}],
            "lecturers": [{"gguid": "0x3"}],
            "students": [{"gguid": "0x1"}, {"gguid": "0x2"}],
        },
        {
            "gguid": "0x6",
            "lvnr": 2,
            "title": "Prozessorientierte Informationssysteme",
            "title_en": "Process-oriented information systems",
            "type": "Klausur",
            "isexam": True,
            "courses": [
                {"cprid": "BA-Inf", "scale": "GRADE_PARTICIPATION"},
                {"cprid": "MA-Inf", "scale": "GRADE_PARTICIPATION"},
            ],
            "relatedevents": {"gguid": "0x5"},
            "appointments": [{"begin": "29.07.2024 10:15:00", "end": "29.07.2024 11:45:00"}],
            "lecturers": [{"gguid": "0x3"}, {"gguid": "0x4"}, {"gguid": "0x5"}],
            "students": [{"gguid": "0x1"}, {"gguid": "0x2"}],
        },
    ],
}
EXAMPLE_JSON = json.dumps(EXAMPLE_DATA)


class TestImportUserProfiles(TestCase):
    def setUp(self):
        self.students = EXAMPLE_DATA["students"]
        self.lecturers = EXAMPLE_DATA["lecturers"]

        self.semester = baker.make(Semester)

    def test_import_students(self):
        self.assertEqual(UserProfile.objects.count(), 0)

        importer = JSONImporter(self.semester, "01.01.2000")
        importer._import_students(self.students)

        user_profiles = UserProfile.objects.all()

        for i, user_profile in enumerate(user_profiles.order_by("email")):
            self.assertEqual(user_profile.email, self.students[i]["email"])
            self.assertEqual(user_profile.last_name, self.students[i]["name"])
            self.assertEqual(user_profile.first_name_given, self.students[i]["christianname"])

        self.assertEqual(importer.statistics.name_changes, [])

    def test_import_existing_students(self):
        user_profile = baker.make(
            UserProfile, email=self.students[0]["email"], last_name="Doe", first_name_given="Jane"
        )

        importer = JSONImporter(self.semester, "01.01.2000")
        importer._import_students(self.students)

        self.assertEqual(UserProfile.objects.count(), 2)

        user_profile.refresh_from_db()

        self.assertEqual(user_profile.email, self.students[0]["email"])
        self.assertEqual(user_profile.last_name, self.students[0]["name"])
        self.assertEqual(user_profile.first_name_given, self.students[0]["christianname"])

        self.assertEqual(
            importer.statistics.name_changes,
            [
                NameChange(
                    old_last_name="Doe",
                    old_first_name_given="Jane",
                    new_last_name=self.students[0]["name"],
                    new_first_name_given=self.students[0]["christianname"],
                    email=self.students[0]["email"],
                )
            ],
        )

    def test_import_lecturers(self):
        self.assertEqual(UserProfile.objects.count(), 0)

        importer = JSONImporter(self.semester, "01.01.2000")
        importer._import_lecturers(self.lecturers)

        user_profiles = UserProfile.objects.all()

        for i, user_profile in enumerate(user_profiles.order_by("email")):
            self.assertEqual(user_profile.email, self.lecturers[i]["email"])
            self.assertEqual(user_profile.last_name, self.lecturers[i]["name"])
            self.assertEqual(user_profile.first_name_given, self.lecturers[i]["christianname"])
            self.assertEqual(user_profile.title, self.lecturers[i]["titlefront"])

        self.assertEqual(importer.statistics.name_changes, [])

    def test_import_existing_lecturers(self):
        user_profile = baker.make(
            UserProfile, email=self.lecturers[0]["email"], last_name="Doe", first_name_given="Jane"
        )

        importer = JSONImporter(self.semester, "01.01.2000")
        importer._import_lecturers(self.lecturers)

        self.assertEqual(UserProfile.objects.count(), 4)

        user_profile.refresh_from_db()

        self.assertEqual(user_profile.email, self.lecturers[0]["email"])
        self.assertEqual(user_profile.last_name, self.lecturers[0]["name"])
        self.assertEqual(user_profile.first_name_given, self.lecturers[0]["christianname"])
        self.assertEqual(user_profile.title, self.lecturers[0]["titlefront"])

        self.assertEqual(
            importer.statistics.name_changes,
            [
                NameChange(
                    old_last_name="Doe",
                    old_first_name_given="Jane",
                    new_last_name=self.lecturers[0]["name"],
                    new_first_name_given=self.lecturers[0]["christianname"],
                    email=self.lecturers[0]["email"],
                )
            ],
        )


class TestImportEvents(TestCase):
    def setUp(self):
        self.semester = baker.make(Semester)

    def _import(self):
        importer = JSONImporter(self.semester, "01.01.2000")
        importer.import_json(EXAMPLE_JSON)
        return importer

    def test_import_courses(self):
        importer = self._import()

        self.assertEqual(Course.objects.count(), 1)
        course = Course.objects.first()

        self.assertEqual(course.semester, self.semester)
        self.assertEqual(course.cms_id, EXAMPLE_DATA["events"][0]["gguid"])
        self.assertEqual(course.name_de, EXAMPLE_DATA["events"][0]["title"])
        self.assertEqual(course.name_en, EXAMPLE_DATA["events"][0]["title_en"])
        self.assertEqual(course.type.name_de, EXAMPLE_DATA["events"][0]["type"])
        self.assertSetEqual(
            {d.name_de for d in course.programs.all()}, {d["cprid"] for d in EXAMPLE_DATA["events"][1]["courses"]}
        )
        self.assertSetEqual(
            set(course.responsibles.values_list("email", flat=True)),
            {"3@example.com"},
        )

        main_evaluation = Evaluation.objects.get(name_en="")
        self.assertEqual(main_evaluation.course, course)
        self.assertEqual(main_evaluation.name_de, "")
        self.assertEqual(main_evaluation.name_en, "")
        # [{"begin": "15.04.2024 10:15", "end": "15.07.2024 11:45"}]
        self.assertEqual(main_evaluation.vote_start_datetime, datetime(2024, 7, 8, 8, 0))
        self.assertEqual(main_evaluation.vote_end_date, date(2024, 7, 21))
        self.assertSetEqual(
            set(main_evaluation.participants.values_list("email", flat=True)),
            {"1@example.com", "2@example.com"},
        )

        self.assertEqual(Contribution.objects.filter(evaluation=main_evaluation).count(), 2)
        self.assertSetEqual(
            set(
                Contribution.objects.filter(evaluation=main_evaluation, contributor__isnull=False).values_list(
                    "contributor__email", flat=True
                )
            ),
            {"3@example.com"},
        )

        exam_evaluation = Evaluation.objects.get(name_en="Exam")
        self.assertEqual(exam_evaluation.course, course)
        self.assertEqual(exam_evaluation.name_de, "Prüfung")
        self.assertEqual(exam_evaluation.name_en, "Exam")
        # [{"begin": "29.07.2024 10:15", "end": "29.07.2024 11:45"}]
        self.assertEqual(exam_evaluation.vote_start_datetime, datetime(2024, 7, 30, 8, 0))
        self.assertEqual(exam_evaluation.vote_end_date, date(2024, 8, 1))
        self.assertSetEqual(
            set(exam_evaluation.participants.values_list("email", flat=True)),
            {"1@example.com", "2@example.com"},
        )
        self.assertTrue(exam_evaluation.wait_for_grade_upload_before_publishing)

        self.assertEqual(Contribution.objects.filter(evaluation=exam_evaluation).count(), 4)
        self.assertSetEqual(
            set(
                Contribution.objects.filter(evaluation=exam_evaluation, contributor__isnull=False).values_list(
                    "contributor__email", flat=True
                )
            ),
            {"3@example.com", "4@example.com", "5@example.com"},
        )

        self.assertEqual(len(importer.statistics.new_courses), 1)
        self.assertEqual(len(importer.statistics.new_evaluations), 2)

    def test_import_courses_evaluation_approved(self):
        self._import()

        evaluation = Evaluation.objects.get(name_en="")

        evaluation.name_en = "Test"
        evaluation.save()

        importer = self._import()

        evaluation = Evaluation.objects.get(pk=evaluation.pk)

        self.assertEqual(evaluation.name_en, "")
        self.assertEqual(len(importer.statistics.attempted_changes), 0)

        evaluation.general_contribution.questionnaires.add(
            baker.make(Questionnaire, type=Questionnaire.Type.CONTRIBUTOR)
        )
        evaluation.manager_approve()
        evaluation.name_en = "Test"
        evaluation.save()

        importer = self._import()

        evaluation = Evaluation.objects.get(pk=evaluation.pk)

        self.assertEqual(evaluation.name_en, "Test")

        self.assertEqual(len(importer.statistics.attempted_changes), 1)

    def test_import_courses_update(self):
        self._import()

        self.assertEqual(Course.objects.count(), 1)
        course = Course.objects.all()[0]
        course.name_de = "Doe"
        course.name_en = "Jane"
        course.save()

        importer = self._import()

        course.refresh_from_db()

        self.assertEqual(course.name_de, EXAMPLE_DATA["events"][0]["title"])
        self.assertEqual(course.name_en, EXAMPLE_DATA["events"][0]["title_en"])

        self.assertEqual(len(importer.statistics.updated_courses), 1)
        self.assertEqual(len(importer.statistics.new_courses), 0)

    def test_importer_log_email_sent(self):
        manager = make_manager()

        self._import()

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, "[EvaP] JSON importer log")
        self.assertEqual(mail.outbox[0].recipients(), [manager.email])

    @patch("evap.staff.importers.json.JSONImporter.import_json")
    def test_management_command(self, mock_import_json):
        output = StringIO()

        with TemporaryDirectory() as temp_dir:
            test_filename = os.path.join(temp_dir, "test.json")
            with open(test_filename, "w", encoding="utf-8") as f:
                f.write(EXAMPLE_JSON)
            call_command("json_import", self.semester.id, test_filename, "01.01.2000", stdout=output)

            mock_import_json.assert_called_once_with(EXAMPLE_JSON)
