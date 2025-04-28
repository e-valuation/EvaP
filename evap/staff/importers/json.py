import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, TypedDict

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.utils.timezone import now

from evap.evaluation.models import Contribution, Course, CourseType, Evaluation, Program, Semester, UserProfile
from evap.evaluation.tools import clean_email
from evap.staff.tools import update_or_create_with_changes, update_with_changes

logger = logging.getLogger("import")


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
    students: list[ImportRelated]


class ImportDict(TypedDict):
    students: list[ImportStudent]
    lecturers: list[ImportLecturer]
    events: list[ImportEvent]


@dataclass
class NameChange:
    old_last_name: str
    old_first_name_given: str
    new_last_name: str
    new_first_name_given: str
    email: str


@dataclass
class WarningMessage:
    obj: str
    message: str


@dataclass
class ImportStatistics:
    name_changes: list[NameChange] = field(default_factory=list)
    new_courses: list[Course] = field(default_factory=list)
    new_evaluations: list[Evaluation] = field(default_factory=list)
    updated_courses: list[Course] = field(default_factory=list)
    updated_evaluations: list[Evaluation] = field(default_factory=list)
    attempted_changes: list[Evaluation] = field(default_factory=list)
    warnings: list[Evaluation] = field(default_factory=list)

    @staticmethod
    def _make_heading(heading: str, separator: str = "-") -> str:
        return f"{heading}\n{separator * len(heading)}\n"

    @staticmethod
    def _make_total(total: int) -> str:
        return f"({total} in total)\n\n"

    @staticmethod
    def _make_stats(heading: str, objects: list) -> str:
        log = ImportStatistics._make_heading(heading)
        log += ImportStatistics._make_total(len(objects))
        for obj in objects:
            log += f"- {obj}\n"
        log += "\n"
        return log

    def get_log(self) -> str:
        log = self._make_heading("JSON IMPORTER REPORT", "=")
        log += "\n"
        log += f"Import finished at {now()}\n\n"

        log += self._make_heading("Name Changes")
        log += self._make_total(len(self.name_changes))
        for name_change in self.name_changes:
            log += f"- {name_change.old_first_name_given} {name_change.old_last_name} → {name_change.new_first_name_given} {name_change.new_last_name} (email: {name_change.email})\n"

        log += self._make_stats("New Courses", self.new_courses)
        log += self._make_stats("New Evaluations", self.new_evaluations)
        log += self._make_stats("Updated Courses", self.updated_courses)
        log += self._make_stats("Updated Evaluations", self.updated_evaluations)
        log += self._make_stats("Attempted Changes", self.attempted_changes)

        log += self._make_heading("Warnings")
        log += self._make_total(len(self.warnings))
        for warning in self.warnings:
            log += f"- {warning.obj}: {warning.message}\n"

        return log

    def send_mail(self):
        subject = "[EvaP] JSON importer log"

        managers = UserProfile.objects.filter(groups__name="Manager", email__isnull=False)
        if not managers:
            return
        mail = EmailMultiAlternatives(
            subject,
            self.get_log(),
            settings.SERVER_EMAIL,
            [manager.email for manager in managers],
        )
        mail.send()


class JSONImporter:
    DATETIME_FORMAT = "%d.%m.%Y %H:%M:%S"

    def __init__(self, semester: Semester, default_course_end: str) -> None:
        self.semester = semester
        self.default_course_end = default_course_end
        self.user_profile_map: dict[str, UserProfile] = {}
        self.course_type_cache: dict[str, CourseType] = {
            import_name.strip().lower(): course_type
            for course_type in CourseType.objects.all()
            for import_name in course_type.import_names
        }
        self.program_cache: dict[str, Program] = {
            import_name.strip().lower(): program
            for program in Program.objects.all()
            for import_name in program.import_names
        }
        self.course_map: dict[str, Course] = {}
        self.statistics = ImportStatistics()

    def _choose_responsibles(self, user_profiles: list[UserProfile]) -> list[UserProfile]:
        user_profiles_by_len = {}
        for user_profile in user_profiles:
            user_profile_len = len(user_profile.title)
            user_profiles_by_len.setdefault(user_profile_len, []).append(user_profile)
        for key in sorted(user_profiles_by_len.keys(), reverse=True):
            return user_profiles_by_len[key]
        return []

    def _filter_user_profiles(self, user_profiles: list[UserProfile]) -> list[UserProfile]:
        return list(filter(lambda p: p.email not in settings.NON_RESPONSIBLE_USERS, user_profiles))

    def _get_course_type(self, name: str) -> CourseType:
        lookup = name.strip().lower()
        if lookup in self.course_type_cache:
            return self.course_type_cache[lookup]

        course_type, __ = CourseType.objects.get_or_create(name_de=name, defaults={"name_en": name})
        self.course_type_cache[name] = course_type
        return course_type

    def _get_program(self, name: str) -> Program:
        lookup = name.strip().lower()
        if lookup in self.program_cache:
            return self.program_cache[lookup]

        program, __ = Program.objects.get_or_create(name_de=name, defaults={"name_en": name})
        self.program_cache[name] = program
        return program

    def _get_user_profiles(self, data: list[ImportRelated]) -> list[UserProfile]:
        return [
            self.user_profile_map[related["gguid"]] for related in data if related["gguid"] in self.user_profile_map
        ]

    def _create_name_change_from_changes(self, user_profile: UserProfile, changes: dict[str, tuple[Any, Any]]) -> None:
        change = NameChange(
            old_last_name=changes["last_name"][0] if changes.get("last_name") else user_profile.last_name,
            old_first_name_given=(
                changes["first_name_given"][0] if changes.get("first_name_given") else user_profile.first_name_given
            ),
            new_last_name=user_profile.last_name,
            new_first_name_given=user_profile.first_name_given,
            email=user_profile.email,
        )
        self.statistics.name_changes.append(change)

    def _import_students(self, data: list[ImportStudent]) -> None:
        for entry in data:
            email = clean_email(entry["email"])
            if not email:
                self.statistics.warnings.append(
                    WarningMessage(obj=f"Student {entry['christianname']} {entry['name']}", message="No email defined")
                )
            else:
                user_profile, __, changes = update_or_create_with_changes(
                    UserProfile,
                    email=email,
                    defaults={"last_name": entry["name"], "first_name_given": entry["christianname"]},
                )
                if changes:
                    self._create_name_change_from_changes(user_profile, changes)

                self.user_profile_map[entry["gguid"]] = user_profile

    def _import_lecturers(self, data: list[ImportLecturer]) -> None:
        for entry in data:
            email = clean_email(entry["email"])
            if not email:
                self.statistics.warnings.append(
                    WarningMessage(
                        obj=f"Contributor {entry['christianname']} {entry['name']}", message="No email defined"
                    )
                )
            else:
                user_profile, __, changes = update_or_create_with_changes(
                    UserProfile,
                    email=email,
                    defaults={
                        "last_name": entry["name"],
                        "first_name_given": entry["christianname"],
                        "title": entry["titlefront"],
                    },
                )
                if changes:
                    self._create_name_change_from_changes(user_profile, changes)

                self.user_profile_map[entry["gguid"]] = user_profile

    def _import_course(self, data: ImportEvent, course_type: CourseType | None = None) -> Course:
        course_type = self._get_course_type(data["type"]) if course_type is None else course_type
        responsibles = self._get_user_profiles(data["lecturers"])
        responsibles = self._filter_user_profiles(responsibles)
        responsibles = self._choose_responsibles(responsibles)
        if not data["title_en"]:
            data["title_en"] = data["title"]
        course, created, changes = update_or_create_with_changes(
            Course,
            semester=self.semester,
            cms_id=data["gguid"],
            defaults={"name_de": data["title"], "name_en": data["title_en"], "type": course_type},
        )
        course.responsibles.set(responsibles)

        if created:
            self.statistics.new_courses.append(course)
        elif changes:
            self.statistics.updated_courses.append(course)

        self.course_map[data["gguid"]] = course

        return course

    def _import_course_programs(self, course: Course, data: ImportEvent) -> None:
        programs = [
            self._get_program(c["cprid"]) for c in data["courses"] if c["cprid"] not in settings.IGNORE_PROGRAMS
        ]
        course.programs.set(programs)

    def _import_course_from_unused_exam(self, data: ImportEvent) -> Course | None:
        splitted_title = data["title"].split(":", 1)
        if len(splitted_title) < 2:
            return None
        prefix = splitted_title[0].strip()

        try:
            course_type = CourseType.objects.get(import_names__contains=[prefix])
        except CourseType.DoesNotExist:
            return None

        data["title"] = splitted_title[1].strip()
        data["title_en"] = data["title_en"].split(":", 1)[1].strip() if ":" in data["title_en"] else data["title_en"]

        return self._import_course(data, course_type)

    # pylint: disable=too-many-locals
    def _import_evaluation(self, course: Course, data: ImportEvent) -> Evaluation:
        if "appointments" not in data:
            self.statistics.warnings.append(
                WarningMessage(obj=course.name, message="No dates defined, using default end date")
            )
            course_end = datetime.strptime(self.default_course_end, "%d.%m.%Y")
        else:
            last_appointment = sorted(data["appointments"], key=lambda x: x["end"])[-1]
            course_end = datetime.strptime(last_appointment["end"], self.DATETIME_FORMAT)

        if data["isexam"]:
            # Set evaluation time frame of three days for exam evaluations:
            evaluation_start_datetime = course_end.replace(hour=8, minute=0, second=0, microsecond=0) + timedelta(
                days=1
            )
            evaluation_end_date = (course_end + timedelta(days=3)).date()

            name_de = data["title"].split(" - ")[-1] if " - " in data["title"] else "Prüfung"
            name_en = data["title_en"].split(" - ")[-1] if " - " in data["title_en"] else "Exam"

            weight = 1

            # If events are graded for any program, wait for grade upload before publishing
            wait_for_grade_upload_before_publishing = any(grade["scale"] for grade in data["courses"])
            # Update previously created main evaluation
            course.evaluations.all().update(
                wait_for_grade_upload_before_publishing=wait_for_grade_upload_before_publishing
            )
        else:
            # Set evaluation time frame of two weeks for normal evaluations:
            # Start datetime is at 8:00 am on the monday in the week before the event ends
            evaluation_start_datetime = course_end.replace(hour=8, minute=0, second=0, microsecond=0) - timedelta(
                weeks=1, days=course_end.weekday()
            )
            # End date is on the sunday in the week the event ends
            evaluation_end_date = (course_end + timedelta(days=6 - course_end.weekday())).date()

            name_de, name_en = "", ""

            weight = 9

            # Might be overwritten when importing related exam evaluation
            wait_for_grade_upload_before_publishing = True

        participants = self._get_user_profiles(data["students"]) if "students" in data else []

        defaults = {
            "name_de": name_de,
            "name_en": name_en,
            "vote_start_datetime": evaluation_start_datetime,
            "vote_end_date": evaluation_end_date,
            "wait_for_grade_upload_before_publishing": wait_for_grade_upload_before_publishing,
            "weight": weight,
        }
        evaluation, created = Evaluation.objects.get_or_create(
            course=course,
            cms_id=data["gguid"],
            defaults=defaults,
        )
        if evaluation.state < Evaluation.State.APPROVED:
            direct_changes = update_with_changes(evaluation, defaults)

            participant_changes = set(evaluation.participants.all()) != set(participants)
            evaluation.participants.set(participants)

            any_lecturers_changed = False
            if "lecturers" not in data:
                self.statistics.warnings.append(
                    WarningMessage(obj=evaluation.full_name, message="No contributors defined")
                )
            else:
                for lecturer in data["lecturers"]:
                    __, lecturer_created, lecturer_changes = self._import_contribution(evaluation, lecturer)
                    if lecturer_changes or lecturer_created:
                        any_lecturers_changed = True

            if not created and (direct_changes or participant_changes or any_lecturers_changed):
                self.statistics.updated_evaluations.append(evaluation)
        else:
            self.statistics.attempted_changes.append(evaluation)

        if created:
            self.statistics.new_evaluations.append(evaluation)

        return evaluation

    def _import_contribution(
        self, evaluation: Evaluation, data: ImportRelated
    ) -> tuple[Contribution | None, bool, dict[str, tuple[any, any]]]:
        if data["gguid"] not in self.user_profile_map:
            return None, False, {}

        user_profile = self.user_profile_map[data["gguid"]]

        if user_profile.email in settings.NON_RESPONSIBLE_USERS:
            return None, False, {}

        contribution, created, changes = update_or_create_with_changes(
            Contribution,
            evaluation=evaluation,
            contributor=user_profile,
        )
        return contribution, created, changes

    def _import_events(self, data: list[ImportEvent]) -> None:
        # Divide in two lists so corresponding courses are imported before their exams
        non_exam_events = (event for event in data if not event["isexam"])
        exam_events = (event for event in data if event["isexam"])

        for event in non_exam_events:
            course = self._import_course(event)

            self._import_evaluation(course, event)

        unused_events = []
        for event in exam_events:
            if not event["relatedevents"]:
                unused_events.append(event)
                continue

            course = self.course_map[event["relatedevents"][0]["gguid"]]

            self._import_course_programs(course, event)

            self._import_evaluation(course, event)
        for event in unused_events:
            course = self._import_course_from_unused_exam(event)
            if not course:
                self.statistics.warnings.append(
                    WarningMessage(obj=event["title"], message="No related event or matching prefix found")
                )
                continue
            event["isexam"] = False
            self._import_course_programs(course, event)
            self._import_evaluation(course, event)

    @transaction.atomic
    def import_dict(self, data: ImportDict) -> None:
        self._import_students(data["students"])
        self._import_lecturers(data["lecturers"])
        self._import_events(data["events"])
        self.statistics.send_mail()

    def import_json(self, data: str) -> None:
        self.import_dict(json.loads(data))
