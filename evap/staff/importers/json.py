from datetime import datetime, timedelta
from typing import TypedDict

from django.db import transaction

from evap.evaluation.models import Contribution, Course, CourseType, Degree, Evaluation, Semester, UserProfile
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
    relatedevents: ImportRelated
    appointments: list[ImportAppointment]
    lecturers: list[ImportRelated]
    students: list[ImportRelated]


class ImportDict(TypedDict):
    students: list[ImportStudent]
    lecturers: list[ImportLecturer]
    events: list[ImportEvent]


class JSONImporter:
    DATETIME_FORMAT = "%d.%m.%Y %H:%M"

    def __init__(self, semester: Semester):
        self.semester = semester
        self.user_profile_map: dict[str, UserProfile] = {}
        self.course_type_cache: dict[str, CourseType] = {}
        self.degree_cache: dict[str, Degree] = {}
        self.course_map: dict[str, Course] = {}

    def _get_course_type(self, name: str) -> CourseType:
        if name in self.course_type_cache:
            return self.course_type_cache[name]

        course_type = CourseType.objects.get_or_create(name_de=name, defaults={"name_en": name})[0]
        self.course_type_cache[name] = course_type
        return course_type

    def _get_degree(self, name: str) -> Degree:
        if name in self.degree_cache:
            return self.degree_cache[name]

        degree = Degree.objects.get_or_create(name_de=name, defaults={"name_en": name})[0]
        self.degree_cache[name] = degree
        return degree

    def _get_user_profiles(self, data: list[ImportRelated]) -> list[UserProfile]:
        return [self.user_profile_map[related["gguid"]] for related in data]

    def _import_students(self, data: list[ImportStudent]):
        for entry in data:
            email = clean_email(entry["email"])
            user_profile, __ = UserProfile.objects.update_or_create(
                email=email,
                defaults={"last_name": entry["name"], "first_name_given": entry["christianname"]},
            )

            self.user_profile_map[entry["gguid"]] = user_profile

    def _import_lecturers(self, data: list[ImportLecturer]):
        for entry in data:
            email = clean_email(entry["email"])
            user_profile, __ = UserProfile.objects.update_or_create(
                email=email,
                defaults={
                    "last_name": entry["name"],
                    "first_name_given": entry["christianname"],
                    "title": entry["titlefront"],
                },
            )

            self.user_profile_map[entry["gguid"]] = user_profile

    def _import_course(self, data: ImportEvent) -> Course:
        course_type = self._get_course_type(data["type"])
        degrees = [self._get_degree(c["cprid"]) for c in data["courses"]]
        responsibles = self._get_user_profiles(data["lecturers"])
        course, __ = Course.objects.update_or_create(
            semester=self.semester,
            cms_id=data["gguid"],
            defaults={"name_de": data["title"], "name_en": data["title_en"], "type": course_type},
        )
        course.degrees.set(degrees)
        course.responsibles.set(responsibles)

        self.course_map[data["gguid"]] = course

        return course

    def _import_evaluation(self, course: Course, data: ImportEvent) -> Evaluation:
        course_end = datetime.strptime(data["appointments"][0]["end"], self.DATETIME_FORMAT)

        if data["isexam"]:
            # Set evaluation time frame of three days for exam evaluations:
            evaluation_start_datetime = course_end.replace(hour=8, minute=0) + timedelta(days=1)
            evaluation_end_date = (course_end + timedelta(days=3)).date()

            name_de = "Klausur"
            name_en = "Exam"
        else:
            # Set evaluation time frame of two weeks for normal evaluations:
            # Start datetime is at 8:00 am on the monday in the week before the event ends
            evaluation_start_datetime = course_end.replace(hour=8, minute=0) - timedelta(
                weeks=1, days=course_end.weekday()
            )
            # End date is on the sunday in the week the event ends
            evaluation_end_date = (course_end + timedelta(days=6 - course_end.weekday())).date()

            name_de, name_en = "", ""

        # If events are graded for any degree, wait for grade upload before publishing
        wait_for_grade_upload_before_publishing = any(filter(lambda grade: grade["scale"], data["courses"]))

        participants = self._get_user_profiles(data["students"])

        evaluation, __ = Evaluation.objects.update_or_create(
            course=course,
            cms_id=data["gguid"],
            defaults={
                "name_de": name_de,
                "name_en": name_en,
                "vote_start_datetime": evaluation_start_datetime,
                "vote_end_date": evaluation_end_date,
                "wait_for_grade_upload_before_publishing": wait_for_grade_upload_before_publishing,
            },
        )
        evaluation.participants.set(participants)

        for lecturer in data["lecturers"]:
            self._import_contribution(evaluation, lecturer)

        return evaluation

    def _import_contribution(self, evaluation: Evaluation, data: ImportRelated):
        user_profile = self.user_profile_map[data["gguid"]]

        contribution, __ = Contribution.objects.update_or_create(
            evaluation=evaluation,
            contributor=user_profile,
        )
        return contribution

    def _import_events(self, data: list[ImportEvent]):
        # Divide in two lists so corresponding courses are imported before their exams
        normal_events = filter(lambda e: not e["isexam"], data)
        exam_events = filter(lambda e: e["isexam"], data)

        for event in normal_events:
            event: ImportEvent

            course = self._import_course(event)

            self._import_evaluation(course, event)

        for event in exam_events:
            event: ImportEvent

            course = self.course_map[event["relatedevents"]["gguid"]]

            self._import_evaluation(course, event)

    @transaction.atomic
    def import_json(self, data: ImportDict):
        self._import_students(data["students"])
        self._import_lecturers(data["lecturers"])
        self._import_events(data["events"])
