import json
from datetime import date, datetime

from django.test import TestCase
from model_bakery import baker

from evap.evaluation.models import Course, Evaluation, Semester, UserProfile
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
            "lvnr": 1,
            "title": "Prozessorientierte Informationssysteme",
            "title_en": "Process-oriented information systems",
            "type": "Vorlesung",
            "isexam": False,
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
            "lvnr": 2,
            "title": "Prozessorientierte Informationssysteme",
            "title_en": "Process-oriented information systems",
            "type": "Klausur",
            "isexam": True,
            "courses": [
                {"cprid": "BA-Inf", "scale": ""},
                {"cprid": "MA-Inf", "scale": ""},
            ],
            "relatedevents": {"gguid": "0x5"},
            "appointments": [{"begin": "29.07.2024 10:15", "end": "29.07.2024 11:45"}],
            "lecturers": [{"gguid": "0x3"}, {"gguid": "0x4"}],
            "students": [{"gguid": "0x1"}, {"gguid": "0x2"}],
        },
    ],
}
EXAMPLE_JSON = json.dumps(EXAMPLE_DATA)


class ImportUserProfilesTestCase(TestCase):
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


class ImportEventsTestCase(TestCase):
    def setUp(self):
        self.semester = baker.make(Semester)

    def _import(self):
        importer = JSONImporter(self.semester)
        importer.import_json(EXAMPLE_DATA)
        return importer

    def test_import_courses(self):
        importer = self._import()

        self.assertEqual(Course.objects.all().count(), 1)
        course = Course.objects.all()[0]

        self.assertEqual(course.semester, self.semester)
        self.assertEqual(course.cms_id, EXAMPLE_DATA["events"][0]["gguid"])
        self.assertEqual(course.name_de, EXAMPLE_DATA["events"][0]["title"])
        self.assertEqual(course.name_en, EXAMPLE_DATA["events"][0]["title_en"])
        self.assertEqual(course.type.name_de, EXAMPLE_DATA["events"][0]["type"])
        self.assertListEqual(
            [d.name_de for d in course.degrees.all()], [d["cprid"] for d in EXAMPLE_DATA["events"][0]["courses"]]
        )
        self.assertListEqual(
            list(course.responsibles.all()),
            [importer.user_profile_map[lecturer["gguid"]] for lecturer in EXAMPLE_DATA["events"][0]["lecturers"]],
        )

        main_evaluation = Evaluation.objects.get(name_en="")
        self.assertEqual(main_evaluation.course, course)
        self.assertEqual(main_evaluation.name_de, "")
        self.assertEqual(main_evaluation.name_en, "")
        # [{"begin": "15.04.2024 10:15", "end": "15.07.2024 11:45"}]
        self.assertEqual(main_evaluation.vote_start_datetime, datetime(2024, 7, 8, 8, 0))
        self.assertEqual(main_evaluation.vote_end_date, date(2024, 7, 21))
        self.assertListEqual(
            list(main_evaluation.participants.all()),
            [importer.user_profile_map[student["gguid"]] for student in EXAMPLE_DATA["events"][0]["students"]],
        )
        self.assertTrue(main_evaluation.wait_for_grade_upload_before_publishing)
        # FIXME lecturers

        exam_evaluation = Evaluation.objects.get(name_en="Exam")
        self.assertEqual(exam_evaluation.course, course)
        self.assertEqual(exam_evaluation.name_de, "Klausur")
        self.assertEqual(exam_evaluation.name_en, "Exam")
        # [{"begin": "29.07.2024 10:15", "end": "29.07.2024 11:45"}]
        self.assertEqual(exam_evaluation.vote_start_datetime, datetime(2024, 7, 30, 8, 0))
        self.assertEqual(exam_evaluation.vote_end_date, date(2024, 8, 1))
        self.assertListEqual(
            list(exam_evaluation.participants.all()),
            [importer.user_profile_map[student["gguid"]] for student in EXAMPLE_DATA["events"][1]["students"]],
        )
        self.assertFalse(exam_evaluation.wait_for_grade_upload_before_publishing)
        # FIXME lecturers

    def test_import_courses_update(self):
        pass
