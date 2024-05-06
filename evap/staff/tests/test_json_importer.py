import json

from django.test import TestCase
from model_bakery import baker

from evap.evaluation.models import Semester, UserProfile
from evap.staff.importers.json import ImportDict, JSONImporter

EXAMPLE_DATA: ImportDict = {
    "students": [
        {"gguid": "0x1", "email": "1@example.com", "name": "1", "christianname": "1"},
        {"gguid": "0x2", "email": "2@example.com", "name": "2", "christianname": "2"},
    ],
    "lecturers": [
        {"gguid": "0x3", "email": "3@example.com", "name": "3", "christianname": "3", "titlefront": "Prof. Dr."},
        {"gguid": "0x4", "email": "4@example.com", "name": "4", "christianname": "4", "titlefront": "Dr."},
    ],
    "events": [
        {
            "gguid": "0x5",
            "lvnr": "1",
            "title": "Prozessorientierte Informationssysteme",
            "title_en": "Process-oriented information systems",
            "type": "Vorlesung",
            "isexam": "false",
            "courses": [
                {"cprid": "BA-Inf", "scale": "GRADE_PARTICIPATION"},
                {"cprid": "MA-Inf", "scale": "GRADE_PARTICIPATION"},
            ],
            "relatedevents": {"gguid": "0x6"},
            "appointments": [{"begin": "15.04.2024 10:15", "end": "15.07.2024 11:45"}],
            "lecturers": [{"gguid": "0x3"}],
            "students": [{"gguid": "0x1"}, {"gguid": "0x2"}],
        },
        {
            "gguid": "0x6",
            "lvnr": "2",
            "title": "Prozessorientierte Informationssysteme",
            "title_en": "Process-oriented information systems",
            "type": "Klausur",
            "isexam": "true",
            "courses": [
                {"cprid": "BA-Inf", "scale": "GRADE_TO_A_THIRD"},
                {"cprid": "MA-Inf", "scale": "GRADE_TO_A_THIRD"},
            ],
            "relatedevents": {"gguid": "0x5"},
            "appointments": [{"begin": "29.07.2024 10:15", "end": "29.07.2024 11:45"}],
            "lecturers": [{"gguid": "0x3"}, {"gguid": "0x4"}],
            "students": [{"gguid": "0x1"}, {"gguid": "0x2"}],
        },
    ],
}
EXAMPLE_JSON = json.dumps(EXAMPLE_DATA)


class ImportStudentsTestCase(TestCase):
    @classmethod
    def setUp(self):
        self.students = EXAMPLE_DATA["students"]
        self.lecturers = EXAMPLE_DATA["lecturers"]

        self.semester = baker.make(Semester)

    def test_import_students(self):
        self.assertEqual(UserProfile.objects.all().count(), 0)

        importer = JSONImporter(self.semester)
        importer._import_students(self.students)

        user_profiles = UserProfile.objects.all()
        self.assertEqual(user_profiles.count(), 2)

        for i, user_profile in enumerate(user_profiles):
            self.assertEqual(user_profile.email, self.students[i]["email"])
            self.assertEqual(user_profile.last_name, self.students[i]["name"])
            self.assertEqual(user_profile.first_name_given, self.students[i]["christianname"])

    def test_import_existing_students(self):

        user_profile = baker.make(UserProfile, email=self.students[0]["email"])
        print(user_profile.email)

        importer = JSONImporter(self.semester)
        importer._import_students(self.students)

        assert UserProfile.objects.all().count() == 2

        user_profile.refresh_from_db()

        self.assertEqual(user_profile.email, self.students[0]["email"])
        self.assertEqual(user_profile.last_name, self.students[0]["name"])
        self.assertEqual(user_profile.first_name_given, self.students[0]["christianname"])

    def test_import_lecturers(self):
        self.assertEqual(UserProfile.objects.all().count(), 0)

        importer = JSONImporter(self.semester)
        importer._import_lecturers(self.lecturers)

        user_profiles = UserProfile.objects.all()
        self.assertEqual(user_profiles.count(), 2)

        for i, user_profile in enumerate(user_profiles):
            self.assertEqual(user_profile.email, self.lecturers[i]["email"])
            self.assertEqual(user_profile.last_name, self.lecturers[i]["name"])
            self.assertEqual(user_profile.first_name_given, self.lecturers[i]["christianname"])
            self.assertEqual(user_profile.title, self.lecturers[i]["titlefront"])

    def test_import_existing_lecturers(self):

        user_profile = baker.make(UserProfile, email=self.lecturers[0]["email"])
        print(user_profile.email)

        importer = JSONImporter(self.semester)
        importer._import_lecturers(self.lecturers)

        assert UserProfile.objects.all().count() == 2

        user_profile.refresh_from_db()

        self.assertEqual(user_profile.email, self.lecturers[0]["email"])
        self.assertEqual(user_profile.last_name, self.lecturers[0]["name"])
        self.assertEqual(user_profile.first_name_given, self.lecturers[0]["christianname"])
        self.assertEqual(user_profile.title, self.lecturers[0]["titlefront"])
