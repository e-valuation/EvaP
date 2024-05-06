from dataclasses import dataclass
from typing import TypedDict

from django.db import transaction

from evap.evaluation.models import Semester, UserProfile
from evap.evaluation.tools import clean_email


class ImportStudent(TypedDict):
    gguid: str
    email: str
    name: str
    christianname: str


class ImportLecturer(TypedDict):
    gguid: str
    email: str
    name: str
    christianname: str
    titlefront: str


class ImportCourse(TypedDict):
    cprid: str
    scale: str


class ImportRelated(TypedDict):
    gguid: str


class ImportAppointment(TypedDict):
    begin: str
    end: str


class ImportEvent(TypedDict):
    gguid: str
    lvnr: int
    title: str
    title_en: str
    type: str
    isexam: bool
    courses: list[ImportCourse]
    relatedevents: list[ImportRelated]
    appointments: list[ImportAppointment]
    lecturers: list[ImportRelated]
    students: list[ImportStudent]


class ImportDict(TypedDict):
    students: list[ImportStudent]
    lecturers: list[ImportLecturer]
    events: list[ImportEvent]


class JSONImporter:
    def __init__(self, semester: Semester):
        self.semester = semester
        self.user_profile_map: dict[str, UserProfile] = {}

    def _import_students(self, data: list[ImportStudent]):
        for entry in data:
            email = clean_email(entry["email"])
            user_profile = UserProfile.objects.update_or_create(
                email=email,
                defaults=dict(last_name=entry["name"], first_name_given=entry["christianname"]),
            )

            self.user_profile_map[entry["gguid"]] = user_profile

    def _import_lecturers(self, data: list[ImportLecturer]):
        pass

    def _import_events(self, data: list[ImportEvent]):
        pass

    @transaction.atomic
    def import_json(self, data: ImportDict):
        pass
