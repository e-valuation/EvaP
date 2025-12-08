import json
import os
from copy import deepcopy
from datetime import date, datetime, timedelta
from io import StringIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.conf import settings
from django.core import mail
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from model_bakery import baker
from pydantic import ValidationError

from evap.evaluation.models import (
    Contribution,
    Course,
    CourseType,
    Evaluation,
    ExamType,
    Program,
    Questionnaire,
    Semester,
    UserProfile,
)
from evap.evaluation.tests.tools import make_manager
from evap.staff.importers.json import ImportDict, JSONImporter, NameChange, WarningMessage

EXAMPLE_DATA: ImportDict = {
    "students": [
        {"gguid": "0x1", "email": "1@example.com", "name": "1", "christianname": "w_1", "callingname": "1"},
        {"gguid": "0x2", "email": "2@example.com", "name": "2", "christianname": "w_2", "callingname": "2"},
    ],
    "lecturers": [
        {
            "gguid": "0x3",
            "email": "3@example.com",
            "name": "3",
            "christianname": "3",
            "titlefront": "Prof. Dr.",
        },
        {
            "gguid": "0x4",
            "email": "4@example.com",
            "name": "4",
            "christianname": "4",
            "titlefront": "Dr.",
        },
        {
            "gguid": "0x5",
            "email": "5@example.com",
            "name": "5",
            "christianname": "5",
            "titlefront": "",
        },
        {
            "gguid": "0x6",
            "email": "6@example.com",
            "name": "6",
            "christianname": "6",
            "titlefront": "",
        },
    ],
    "events": [
        {
            "gguid": "0x5",
            "title": "Prozessorientierte Informationssysteme",
            "title_en": "Process-oriented information systems",
            "type": "Vorlesung",
            "isexam": False,
            "courses": [],
            "appointments": [
                {"begin": "30.04.2024 10:15:00", "end": "30.04.2024 11:45:00"},
                {"begin": "15.07.2024 10:15:00", "end": "15.07.2024 11:45:00"},
            ],
            "relatedevents": [{"gguid": "0x6"}],
            "lecturers": [{"gguid": "0x3"}],
            "students": [{"gguid": "0x1"}, {"gguid": "0x2"}],
            "language": "Deutsch",
        },
        {
            "gguid": "0x6",
            "title": "Prozessorientierte Informationssysteme",
            "title_en": "Process-oriented information systems",
            "type": "Klausur",
            "isexam": True,
            "courses": [
                {"cprid": "BA-Inf", "scale": "GRADE_PARTICIPATION"},
                {"cprid": "MA-Inf", "scale": "GRADE_PARTICIPATION"},
            ],
            "appointments": [{"begin": "29.07.2024 10:15:00", "end": "29.07.2024 11:45:00"}],
            "relatedevents": [{"gguid": "0x5"}],
            "lecturers": [{"gguid": "0x3"}, {"gguid": "0x4"}, {"gguid": "0x5"}],
            "students": [{"gguid": "0x1"}, {"gguid": "0x2"}],
            "language": "Deutsch",
        },
        {
            "gguid": "0x7",
            "title": "Bachelorprojekt: Prozessorientierte Informationssysteme",
            "title_en": "Bachelor's Project: Process-oriented information systems",
            "type": "Bachelorprojekt",
            "isexam": True,
            "courses": [
                {"cprid": "BA-Inf", "scale": "GRADE_PARTICIPATION"},
            ],
            "lecturers": [{"gguid": "0x3"}],
            "students": [{"gguid": "0x1"}, {"gguid": "0x2"}],
            "language": "Englisch",
        },
    ],
}
EXAMPLE_DATA_WITHOUT_RELATED_EVALUATION = {
    "students": EXAMPLE_DATA["students"],
    "lecturers": EXAMPLE_DATA["lecturers"],
    "events": [
        {
            "gguid": "0x10",
            "title": "Allerbestes Projekt",
            "title_en": "Best Project Ever",
            "type": "Bachelorprojekt",
            "isexam": True,
            "courses": [{"cprid": "BA-Inf", "scale": "GRADE_TO_A_THIRD"}],
            "lecturers": [{"gguid": "0x3"}],
            "students": [{"gguid": "0x1"}, {"gguid": "0x2"}],
            "appointments": [{"begin": "29.07.2024 10:15:00", "end": "29.07.2024 11:45:00"}],
            "language": "Deutsch",
        }
    ],
}
EXAMPLE_DATA_SPECIAL_CASES: ImportDict = {
    "students": [
        {"gguid": "0x1", "email": "", "name": "1", "christianname": "w_1", "callingname": "1"},
        {"gguid": "0x2", "email": "2@example.com", "name": "2", "christianname": "w_2", "callingname": "2"},
        {"gguid": "0x7", "email": "ignored.student@example.com", "name": "7", "christianname": "7", "callingname": "7"},
        {
            "gguid": "0x11",
            "email": "IGNORED.StUdEnT2@example.CoM",
            "name": "11",
            "christianname": "11",
            "callingname": "11",
        },
    ],
    "lecturers": [
        {"gguid": "0x3", "email": "", "name": "3", "christianname": "3", "titlefront": "Prof. Dr."},
        {
            "gguid": "0x4",
            "email": "4@example.com",
            "name": "4",
            "christianname": "4",
            "titlefront": "Prof. Dr.",
        },
        {
            "gguid": "0x5",
            "email": "5@example.com",
            "name": "5",
            "christianname": "5",
            "titlefront": "Prof. Dr.",
        },
        {
            "gguid": "0x6",
            "email": "ignored.lecturer@example.com",
            "name": "6",
            "christianname": "6",
            "titlefront": "Prof. Dr.",
        },
        {
            "gguid": "0x12",
            "email": "IGNORED.lectURer2@ExAmPlE.CoM",
            "name": "12",
            "christianname": "12",
            "titlefront": "Prof. Dr.",
        },
    ],
    "events": [
        {
            "gguid": "0x7",
            "title": "Terminlose Vorlesung",
            "title_en": "",
            "type": "Vorlesung",
            "isexam": False,
            "relatedevents": [{"gguid": "0x42"}, {"gguid": "0x43"}],
            "lecturers": [{"gguid": "0x3"}],
            "students": [{"gguid": "0x1"}, {"gguid": "0x2"}],
            "language": "Deutsch",
        },
        {
            "gguid": "0x8",
            "title": "Klausurlose Vorlesung",
            "title_en": "",
            "type": "Vorlesung",
            "isexam": False,
            "lecturers": [{"gguid": "0x3"}],
            "students": [{"gguid": "0x1"}, {"gguid": "0x2"}],
            "language": "Englisch",
        },
        {
            "gguid": "0x9",
            "title": "Vorlesung mit vielen Verantwortlichen",
            "title_en": "",
            "type": "Vorlesung",
            "isexam": False,
            "lecturers": [{"gguid": "0x4"}, {"gguid": "0x5"}, {"gguid": "0x12"}],
            "students": [],
            "appointments": [{"begin": "29.07.2024 10:15:00", "end": "29.07.2024 11:45:00"}],
            "language": "Deutsch",
        },
        {
            "gguid": "0x42",
            "title": "Die Antwort auf die endgültige Frage nach dem Leben",
            "title_en": "The Answer to the Ultimate Question of Life",
            "type": "Klausur",
            "isexam": True,
            "courses": [
                {"cprid": "BA-Inf", "scale": "GRADE_PARTICIPATION"},
                {"cprid": "Ignore", "scale": "GRADE_PARTICIPATION"},
                {"cprid": "P", "scale": "GRADE_PARTICIPATION"},
            ],
            "appointments": [{"begin": "01.01.2025 01:01:01", "end": "31.12.2025 12:31:00"}],
            "relatedevents": [{"gguid": "0x7"}],
            "students": [{"gguid": "0x1"}, {"gguid": "0x2"}],
            "language": "Deutsch",
        },
        {
            "gguid": "0x43",
            "title": "Die Antwort auf die endgültige Frage nach dem Universum",
            "title_en": "The Answer to the Ultimate Question of the Universe",
            "type": "Klausur",
            "isexam": True,
            "courses": [
                {"cprid": "Master Program", "scale": "GRADE_PARTICIPATION"},
            ],
            "appointments": [{"begin": "01.01.2025 01:01:01", "end": "01.12.2025 12:31:00"}],
            "relatedevents": [{"gguid": "0x7"}],
            "lecturers": [{"gguid": "0x3"}],
            "language": "Deutsch",
        },
        {
            "gguid": "0x44",
            "title": "Der ganze Rest",
            "title_en": "Everything",
            "type": "CT",
            "isexam": False,
            "appointments": [{"begin": "01.01.2025 01:01:01", "end": "31.12.2025 12:31:00"}],
            "lecturers": [{"gguid": "0x3"}],
            "students": [{"gguid": "0x1"}, {"gguid": "0x2"}],
            "language": "random_value",
        },
        {
            "gguid": "0x50",
            "title": "Späte Vorlesung",
            "title_en": "Late Lecture",
            "type": "Vorlesung",
            "isexam": False,
            "appointments": [{"begin": "01.03.2025 08:00:00", "end": "20.03.2025 12:00:00"}],
            "relatedevents": [{"gguid": "0x51"}],
            "lecturers": [{"gguid": "0x3"}],
            "students": [{"gguid": "0x1"}, {"gguid": "0x2"}],
            "language": "Deutsch",
        },
        {
            "gguid": "0x51",
            "title": "Frühe Klausur - Früh",
            "title_en": "Early Exam - Early",
            "type": "Klausur",
            "isexam": True,
            "courses": [
                {"cprid": "Master Program", "scale": "GRADE_PARTICIPATION"},
            ],
            "appointments": [{"begin": "01.01.2025 08:00:00", "end": "01.01.2025 12:00:00"}],
            "relatedevents": [{"gguid": "0x50"}],
            "lecturers": [{"gguid": "0x3"}],
            "students": [{"gguid": "0x1"}, {"gguid": "0x2"}],
            "language": "Deutsch",
        },
        {
            "gguid": "0x10",
            "title": "Vorlesung mit ignorierten Verantwortlichen",
            "title_en": "",
            "type": "Vorlesung",
            "isexam": False,
            "lecturers": [{"gguid": "0x3"}, {"gguid": "0x6"}],
            "students": [{"gguid": "0x1"}, {"gguid": "0x7"}],
            "appointments": [{"begin": "29.07.2024 10:15:00", "end": "29.07.2024 11:45:00"}],
            "language": "Deutsch",
        },
    ],
}
EXAMPLE_JSON = json.dumps(EXAMPLE_DATA)


class TestImportUserProfiles(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.students = EXAMPLE_DATA["students"]
        cls.lecturers = EXAMPLE_DATA["lecturers"]

        cls.semester = baker.make(Semester)

    def test_import_students(self):
        self.assertEqual(UserProfile.objects.count(), 0)

        importer = JSONImporter(self.semester, date(2000, 1, 1))
        importer._import_students(self.students)

        user_profiles = UserProfile.objects.all()

        for i, user_profile in enumerate(user_profiles.order_by("email")):
            self.assertEqual(user_profile.email, self.students[i]["email"])
            self.assertEqual(user_profile.last_name, self.students[i]["name"])
            self.assertEqual(user_profile.first_name_given, self.students[i]["callingname"])

        self.assertEqual(importer.statistics.name_changes, [])

    def test_import_existing_students(self):
        user_profile = baker.make(
            UserProfile, email=self.students[0]["email"], last_name="Doe", first_name_given="Jane"
        )

        importer = JSONImporter(self.semester, date(2000, 1, 1))
        importer._import_students(self.students)

        self.assertEqual(UserProfile.objects.count(), 2)

        user_profile.refresh_from_db()

        self.assertEqual(user_profile.email, self.students[0]["email"])
        self.assertEqual(user_profile.last_name, self.students[0]["name"])
        self.assertEqual(user_profile.first_name_given, self.students[0]["callingname"])

        self.assertEqual(
            importer.statistics.name_changes,
            [
                NameChange(
                    old_last_name="Doe",
                    old_first_name_given="Jane",
                    new_last_name=self.students[0]["name"],
                    new_first_name_given=self.students[0]["callingname"],
                    email=self.students[0]["email"],
                )
            ],
        )

    def test_import_lecturers(self):
        self.assertEqual(UserProfile.objects.count(), 0)

        importer = JSONImporter(self.semester, date(2000, 1, 1))
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

        importer = JSONImporter(self.semester, date(2000, 1, 1))
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
    @classmethod
    def setUpTestData(cls):
        cls.semester = baker.make(Semester)

    def _import(self, data=None):
        if not data:
            data = EXAMPLE_DATA
        data = json.dumps(data)
        importer = JSONImporter(self.semester, date(2000, 1, 1))
        importer.import_json(data)
        return importer

    @override_settings(EXAM_EVALUATION_DEFAULT_DURATION=timedelta(days=3))
    def test_import_courses(self):
        importer = self._import()

        course = Course.objects.get()

        self.assertEqual(course.semester, self.semester)
        self.assertEqual(course.cms_id, EXAMPLE_DATA["events"][0]["gguid"])
        self.assertEqual(course.name_de, EXAMPLE_DATA["events"][0]["title"])
        self.assertEqual(course.name_en, EXAMPLE_DATA["events"][0]["title_en"])
        self.assertEqual(course.type.name_de, EXAMPLE_DATA["events"][0]["type"])
        self.assertEqual(
            {d.name_de for d in course.programs.all()}, {d["cprid"] for d in EXAMPLE_DATA["events"][1]["courses"]}
        )
        self.assertEqual(
            set(course.responsibles.values_list("email", flat=True)),
            {"3@example.com"},
        )

        main_evaluation = Evaluation.objects.get(name_en="")
        self.assertEqual(main_evaluation.course, course)
        self.assertEqual(main_evaluation.name_de, "")
        self.assertEqual(main_evaluation.name_en, "")
        self.assertEqual(main_evaluation.exam_type, None)
        # [{"begin": "30.04.2024 10:15", "end": "15.07.2024 11:45"}]
        self.assertEqual(main_evaluation.vote_start_datetime, datetime(2024, 7, 8, 8, 0))
        # exam is on 29.07.2024, so evaluation period should be until day before
        self.assertEqual(main_evaluation.vote_end_date, date(2024, 7, 28))
        self.assertEqual(
            set(main_evaluation.participants.values_list("email", flat=True)),
            {"1@example.com", "2@example.com"},
        )
        self.assertTrue(main_evaluation.is_rewarded)

        self.assertEqual(Contribution.objects.filter(evaluation=main_evaluation).count(), 2)
        self.assertEqual(
            set(
                Contribution.objects.filter(evaluation=main_evaluation, contributor__isnull=False).values_list(
                    "contributor__email", flat=True
                )
            ),
            {"3@example.com"},
        )
        self.assertTrue(
            all(
                contribution.role == Contribution.Role.EDITOR
                for contribution in Contribution.objects.filter(evaluation=main_evaluation, contributor__isnull=False)
            )
        )

        exam_evaluation = Evaluation.objects.get(name_en="Exam")
        self.assertEqual(exam_evaluation.course, course)
        self.assertEqual(exam_evaluation.name_de, "Klausur")
        self.assertEqual(exam_evaluation.name_en, "Exam")
        self.assertEqual(exam_evaluation.exam_type.name_de, "Klausur")
        self.assertEqual(exam_evaluation.exam_type.name_en, "Exam")
        # [{"begin": "29.07.2024 10:15", "end": "29.07.2024 11:45"}]
        self.assertEqual(exam_evaluation.vote_start_datetime, datetime(2024, 7, 30, 8, 0))
        self.assertEqual(exam_evaluation.vote_end_date, date(2024, 8, 1))
        self.assertEqual(
            set(exam_evaluation.participants.values_list("email", flat=True)),
            {"1@example.com", "2@example.com"},
        )
        self.assertTrue(exam_evaluation.wait_for_grade_upload_before_publishing)
        self.assertFalse(exam_evaluation.is_rewarded)

        self.assertEqual(Contribution.objects.filter(evaluation=exam_evaluation).count(), 4)
        self.assertEqual(
            set(
                Contribution.objects.filter(evaluation=exam_evaluation, contributor__isnull=False).values_list(
                    "contributor__email", flat=True
                )
            ),
            {"3@example.com", "4@example.com", "5@example.com"},
        )
        self.assertTrue(
            all(
                contribution.role == Contribution.Role.EDITOR
                for contribution in Contribution.objects.filter(evaluation=exam_evaluation, contributor__isnull=False)
            )
        )

        self.assertEqual(len(importer.statistics.new_courses), 1)
        self.assertEqual(len(importer.statistics.new_evaluations), 2)

    def test_import_courses_exam_without_related_evaluation(self):
        CourseType.objects.create(name_en="Foo", name_de="Foo", import_names=["nat"])
        course_type = CourseType.objects.create(name_en="Bar", name_de="Bar", import_names=["Bachelorprojekt"])

        self._import(EXAMPLE_DATA_WITHOUT_RELATED_EVALUATION)

        self.assertEqual(Course.objects.count(), 1)
        self.assertEqual(Evaluation.objects.count(), 1)

        evaluation = Evaluation.objects.first()
        self.assertEqual(evaluation.course.name_de, "Allerbestes Projekt")
        self.assertEqual(evaluation.course.name_en, "Best Project Ever")
        self.assertEqual(evaluation.name_de, "")
        self.assertEqual(evaluation.name_en, "")
        self.assertEqual(evaluation.course.type, course_type)

        self.assertEqual(
            set(evaluation.participants.values_list("email", flat=True)),
            {"1@example.com", "2@example.com"},
        )

        self.assertEqual(
            set(
                Contribution.objects.filter(evaluation=evaluation, contributor__isnull=False).values_list(
                    "contributor__email", flat=True
                )
            ),
            {"3@example.com"},
        )

    @override_settings(IGNORE_PROGRAMS=["Ignore"])
    def test_import_courses_special_cases(self):
        course_type = CourseType.objects.create(name_en="Course Type", name_de="Kurstyp", import_names=["CT"])
        Program.objects.create(name_en="Program", name_de="Studiengang", import_names=["P"])
        importer = self._import(EXAMPLE_DATA_SPECIAL_CASES)

        self.assertEqual(Course.objects.count(), 6)
        self.assertEqual(Evaluation.objects.count(), len(EXAMPLE_DATA_SPECIAL_CASES["events"]))

        evaluation = Evaluation.objects.first()
        self.assertEqual(evaluation.course.name_de, "Terminlose Vorlesung")

        # evaluation has no English name, uses German
        self.assertEqual(evaluation.course.name_en, "Terminlose Vorlesung")

        # evaluation has German language
        self.assertEqual(evaluation.main_language, "de")

        # evaluation has multiple exams, use correct date (first exam end: 01.12.2025)
        self.assertEqual(evaluation.vote_start_datetime, datetime(1999, 12, 20, 8, 0))
        self.assertEqual(evaluation.vote_end_date, date(2025, 11, 30))

        # evaluation_without_exam has no "appointments", uses default dates
        evaluation_without_exam = Evaluation.objects.get(cms_id="0x8")
        self.assertEqual(evaluation_without_exam.vote_start_datetime, datetime(1999, 12, 20, 8, 0))
        self.assertEqual(evaluation_without_exam.vote_end_date, date(2000, 1, 2))

        # evaluation has English language
        self.assertEqual(evaluation_without_exam.main_language, "en")

        # use import names and only import non-ignored programs
        self.assertEqual({d.name_en for d in evaluation.course.programs.all()}, {"BA-Inf", "Master Program", "Program"})
        evaluation_everything = Evaluation.objects.get(cms_id="0x44")
        self.assertEqual(evaluation_everything.course.type, course_type)

        # evaluation has undecided language
        self.assertEqual(evaluation_everything.main_language, Evaluation.UNDECIDED_MAIN_LANGUAGE)

        # disambiguate exam names
        evaluation_life = Evaluation.objects.get(cms_id="0x42")
        self.assertEqual(evaluation_life.name_de, "Klausur")
        self.assertEqual(evaluation_life.name_en, "Exam")
        evaluation_universe = Evaluation.objects.get(cms_id="0x43")
        self.assertEqual(evaluation_universe.name_de, "Klausur (2)")
        self.assertEqual(evaluation_universe.name_en, "Exam (2)")

        # use second part of title after dash
        evaluation_early = Evaluation.objects.get(cms_id="0x51")
        self.assertTrue(evaluation_early.exam_type)
        self.assertEqual(evaluation_early.name_de, "Früh")
        self.assertEqual(evaluation_early.name_en, "Early")

        # don't update evaluation period for late course
        evaluation_late_lecture = Evaluation.objects.get(cms_id="0x50")
        self.assertEqual(evaluation_late_lecture.vote_start_datetime, datetime(2025, 3, 10, 8, 0))
        self.assertEqual(evaluation_late_lecture.vote_end_date, date(2025, 3, 23))

        # check warnings
        self.assertCountEqual(
            importer.statistics.warnings,
            [
                WarningMessage(
                    obj="Contributor 3 3",
                    message="No email defined",
                ),
                WarningMessage(
                    obj="Student 1 1",
                    message="No email defined",
                ),
                WarningMessage(
                    obj=f"{evaluation.course.name} ({evaluation.course.type})",
                    message="No dates defined, using default end date",
                ),
                WarningMessage(
                    obj=evaluation_life.full_name,
                    message="No contributors defined",
                ),
                WarningMessage(
                    obj=f"{evaluation_without_exam.full_name} ({evaluation_without_exam.course.type})",
                    message="No dates defined, using default end date",
                ),
                WarningMessage(
                    obj=evaluation_late_lecture.full_name,
                    message="Exam date (2025-01-01) is on or before start date of main evaluation",
                ),
                WarningMessage(
                    obj="Der ganze Rest",
                    message='Event has an unknown language ("random_value"), main language was set to undecided',
                ),
            ],
        )

        # use first relatedevent, ignore other
        self.assertCountEqual(
            evaluation.course.evaluations.all(),
            [
                evaluation,
                evaluation_life,
                evaluation_universe,
            ],
        )

        # use weights
        self.assertEqual(evaluation_everything.weight, settings.MAIN_EVALUATION_DEFAULT_WEIGHT)
        self.assertEqual(evaluation_life.weight, settings.EXAM_EVALUATION_DEFAULT_WEIGHT)

    def test_import_ignore_non_responsible_users(self):
        with override_settings(NON_RESPONSIBLE_USERS=["4@example.com", "ignored.lecturer2@example.com"]):
            self._import(EXAMPLE_DATA_SPECIAL_CASES)
            evaluation = Evaluation.objects.get(cms_id="0x9")
            self.assertEqual(set(evaluation.course.responsibles.values_list("email", flat=True)), {"5@example.com"})
            self.assertEqual(
                set(
                    Contribution.objects.filter(evaluation=evaluation, contributor__isnull=False).values_list(
                        "contributor__email", flat=True
                    )
                ),
                {"5@example.com"},
            )

        with override_settings(NON_RESPONSIBLE_USERS=[]):
            self._import(EXAMPLE_DATA_SPECIAL_CASES)
            evaluation = Evaluation.objects.get(cms_id="0x9")
            self.assertEqual(
                set(evaluation.course.responsibles.values_list("email", flat=True)),
                {"4@example.com", "5@example.com", "ignored.lecturer2@example.com"},
            )
            self.assertEqual(
                set(
                    Contribution.objects.filter(evaluation=evaluation, contributor__isnull=False).values_list(
                        "contributor__email", flat=True
                    )
                ),
                {"4@example.com", "5@example.com", "ignored.lecturer2@example.com"},
            )

    def test_import_ignore_users(self):
        with override_settings(
            IGNORE_USERS=[
                "ignored.student@example.com",
                "ignored.student2@example.com",
                "ignored.lecturer@example.com",
                "ignored.lecturer2@example.com",
            ]
        ):
            self._import(EXAMPLE_DATA_SPECIAL_CASES)

            self.assertFalse(UserProfile.objects.filter(email="ignored.student@example.com").exists())
            self.assertFalse(UserProfile.objects.filter(email="ignored.student2@example.com").exists())
            self.assertFalse(UserProfile.objects.filter(email="ignored.lecturer@example.com").exists())
            self.assertFalse(UserProfile.objects.filter(email="ignored.lecturer2@example.com").exists())

        with override_settings(IGNORE_USERS=[]):
            self._import(EXAMPLE_DATA_SPECIAL_CASES)

            self.assertTrue(UserProfile.objects.filter(email="ignored.student@example.com").exists())
            self.assertTrue(UserProfile.objects.filter(email="ignored.student2@example.com").exists())
            self.assertTrue(UserProfile.objects.filter(email="ignored.lecturer@example.com").exists())
            self.assertTrue(UserProfile.objects.filter(email="ignored.lecturer2@example.com").exists())

    def test_import_courses_evaluation_approved(self):
        self._import()

        evaluation = Evaluation.objects.get(name_en="")

        evaluation.is_rewarded = False
        evaluation.save()

        importer = self._import()

        evaluation = Evaluation.objects.get(pk=evaluation.pk)

        self.assertTrue(evaluation.is_rewarded)
        self.assertEqual(len(importer.statistics.attempted_changes), 0)

        evaluation.general_contribution.questionnaires.add(
            baker.make(Questionnaire, type=Questionnaire.Type.CONTRIBUTOR)
        )
        evaluation.main_language = "en"
        evaluation.manager_approve()
        evaluation.is_rewarded = False
        evaluation.save()

        importer = self._import()

        evaluation = Evaluation.objects.get(pk=evaluation.pk)

        self.assertFalse(evaluation.is_rewarded)

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

    def test_importer_wrong_data(self):
        wrong_data = deepcopy(EXAMPLE_DATA)
        wrong_data["events"][0]["isexam"] = "false"
        with self.assertRaises(ValidationError):
            self._import(wrong_data)

        data_with_additional_attribute = deepcopy(EXAMPLE_DATA)
        data_with_additional_attribute["extra_attribute"] = True
        # don't fail
        self._import(data_with_additional_attribute)

    def test_first_name_given_fallback(self):
        example_data = deepcopy(EXAMPLE_DATA)
        example_data["students"][1]["callingname"] = ""
        self._import(example_data)

        self.assertEqual(UserProfile.objects.get(email="1@example.com").first_name_given, "1")
        self.assertEqual(UserProfile.objects.get(email="2@example.com").first_name_given, "w_2")

    def test_import_skipped_because_of_course_type_skipped(self):
        CourseType.objects.create(name_en="Lecture", name_de="Vorlesung", skip_on_automated_import=True)

        importer = self._import()

        self.assertTrue(
            WarningMessage(
                obj=EXAMPLE_DATA["events"][0]["title"],
                message="Course skipped because skipping of courses with type Lecture is activated",
            )
            in importer.statistics.warnings,
        )
        self.assertFalse(Evaluation.objects.filter(cms_id="0x5").exists())
        self.assertFalse(Evaluation.objects.filter(cms_id="0x6").exists())

    @patch("evap.staff.importers.json.JSONImporter.import_json")
    def test_management_command(self, mock_import_json):
        output = StringIO()

        with TemporaryDirectory() as temp_dir:
            test_filename = os.path.join(temp_dir, "test.json")
            with open(test_filename, "w", encoding="utf-8") as f:
                f.write(EXAMPLE_JSON)
            call_command("json_import", self.semester.id, test_filename, "01.01.2000", stdout=output)

            mock_import_json.assert_called_once_with(EXAMPLE_JSON)

            with self.assertRaises(CommandError):
                call_command("json_import", self.semester.id + 42, test_filename, "01.01.2000", stdout=output)

    def test_disambiguate_name(self):
        importer = JSONImporter(self.semester, date(2000, 1, 1))

        self.assertEqual(importer._disambiguate_name("Klausur", []), "Klausur")
        self.assertEqual(importer._disambiguate_name("Klausur", [""]), "Klausur")
        self.assertEqual(importer._disambiguate_name("Klausur", ["Klausur"]), "Klausur (2)")
        self.assertEqual(importer._disambiguate_name("Klausur", ["Klausur", "Klausur (2)"]), "Klausur (3)")
        self.assertEqual(importer._disambiguate_name("Klausur", ["Klausur", "Klausur (3)"]), "Klausur (4)")
        self.assertEqual(importer._disambiguate_name("Klausur", ["Klausur (0)"]), "Klausur (1)")
        # doesn't match on negative numbers
        self.assertEqual(importer._disambiguate_name("Klausur", ["Klausur (-1)"]), "Klausur")
        # doesn't fail on arbitary strings
        self.assertEqual(importer._disambiguate_name("Klausur", ["Klausur (mündlich)"]), "Klausur")
        self.assertEqual(importer._disambiguate_name("Klausur", ["Klausur 2"]), "Klausur")

    def test_exam_type_existing(self):
        exam_type = ExamType.objects.create(name_en="Presentation", name_de="Präsentation")
        data = deepcopy(EXAMPLE_DATA)
        data["events"][1]["type"] = "Präsentation"

        self._import(data)

        exam_evaluation = Evaluation.objects.get(cms_id=data["events"][1]["gguid"])

        self.assertEqual(exam_evaluation.name_de, exam_type.name_de)
        self.assertEqual(exam_evaluation.name_en, exam_type.name_en)

    def test_exam_type_different_name(self):
        data = deepcopy(EXAMPLE_DATA)
        data["events"][1]["type"] = "Präsentation"

        self._import(data)

        exam_evaluation = Evaluation.objects.get(cms_id=data["events"][1]["gguid"])

        self.assertEqual(exam_evaluation.exam_type.name_de, "Präsentation")
        self.assertEqual(exam_evaluation.exam_type.name_en, "Präsentation")
        self.assertEqual(exam_evaluation.name_de, exam_evaluation.exam_type.name_de)
        self.assertEqual(exam_evaluation.name_en, exam_evaluation.exam_type.name_de)

    def test_clean_whitespaces(self):
        importer = JSONImporter(self.semester, date(2000, 1, 1))
        self.assertEqual(importer._clean_whitespaces(" front"), "front")
        self.assertEqual(importer._clean_whitespaces("back "), "back")
        self.assertEqual(importer._clean_whitespaces("inbetween  inbetween"), "inbetween inbetween")
        self.assertEqual(importer._clean_whitespaces("inbetween \n inbetween"), "inbetween inbetween")
        # non-breaking whitespace
        self.assertEqual(importer._clean_whitespaces("inbetween  inbetween"), "inbetween inbetween")
