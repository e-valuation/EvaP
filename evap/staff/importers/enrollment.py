import difflib
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, fields
from datetime import date, datetime
from typing import NoReturn, TypeAlias, TypeGuard, TypeVar

from django.conf import settings
from django.db import transaction
from django.utils.html import format_html, format_html_join
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from evap.evaluation.models import Contribution, Course, CourseType, Evaluation, Program, Semester, UserProfile
from evap.evaluation.tools import clean_email
from evap.staff.tools import append_user_list_if_not_empty
from evap.tools import ilen, unordered_groupby

from .base import (
    Checker,
    ConvertExceptionsToMessages,
    ExcelFileLocation,
    ExcelFileRowMapper,
    FirstLocationAndCountTracker,
    ImporterLog,
    ImporterLogEntry,
    InputRow,
    RowCheckerMixin,
)
from .user import (
    UserData,
    UserDataEmptyFieldsChecker,
    UserDataMismatchChecker,
    UserDataValidationChecker,
    get_user_profile_objects,
    update_existing_and_create_new_user_profiles,
)


@dataclass(frozen=True)
class InvalidValue:
    # We make this a dataclass to make sure all instances compare equal.

    def __bool__(self) -> NoReturn:
        raise NotImplementedError("Bool conversion of InvalidValue is likely a bug")


invalid_value = InvalidValue()

T = TypeVar("T")
MaybeInvalid: TypeAlias = T | InvalidValue


@dataclass
class CourseData:
    """Holds information about a course, retrieved from an import file."""

    name_de: str
    name_en: str
    programs: MaybeInvalid[set[Program]]
    course_type: MaybeInvalid[CourseType]
    is_graded: MaybeInvalid[bool]
    responsible_email: str

    # An existing course that this imported one should be merged with. See #1596
    merge_into_course: MaybeInvalid[Course | None] = invalid_value

    def __post_init__(self):
        self.name_de = self.name_de.strip()
        self.name_en = self.name_en.strip()
        self.responsible_email = clean_email(self.responsible_email)

    def differing_fields(self, other) -> set[str]:
        return {field.name for field in fields(self) if getattr(self, field.name) != getattr(other, field.name)}


class ValidCourseDataMeta(type):
    def __instancecheck__(cls, instance: object) -> TypeGuard["ValidCourseData"]:
        if not isinstance(instance, CourseData):
            return False
        return all_fields_valid(instance)


class ValidCourseData(CourseData, metaclass=ValidCourseDataMeta):
    """Typing: CourseData instance where no element is invalid_value"""

    programs: set[Program]
    course_type: CourseType
    is_graded: bool
    merge_into_course: Course | None


def all_fields_valid(course_data: CourseData) -> TypeGuard[ValidCourseData]:
    return all(getattr(course_data, field.name) != invalid_value for field in fields(CourseData))


class ProgramImportMapper:
    class InvalidProgramNameError(Exception):
        def __init__(self, *args, invalid_program_name: str, **kwargs):
            self.invalid_program_name = invalid_program_name
            super().__init__(*args, **kwargs)

    def __init__(self) -> None:
        self.programs: dict[str, Program] = {
            import_name.strip().lower(): program
            for program in Program.objects.all()
            for import_name in program.import_names
        }

    def program_from_import_string(self, import_string: str) -> Program:
        trimmed_name = import_string.strip()
        lookup_key = trimmed_name.lower()
        try:
            return self.programs[lookup_key]
        except KeyError as e:
            raise self.InvalidProgramNameError(invalid_program_name=trimmed_name) from e


class CourseTypeImportMapper:
    class InvalidCourseTypeError(Exception):
        def __init__(self, *args, invalid_course_type: str, **kwargs):
            super().__init__(*args, **kwargs)
            self.invalid_course_type: str = invalid_course_type

    def __init__(self) -> None:
        self.course_types: dict[str, CourseType] = {
            import_name.strip().lower(): course_type
            for course_type in CourseType.objects.all()
            for import_name in course_type.import_names
        }

    def course_type_from_import_string(self, import_string: str) -> CourseType:
        stripped_name = import_string.strip()
        try:
            return self.course_types[stripped_name.lower()]
        except KeyError as e:
            raise self.InvalidCourseTypeError(invalid_course_type=stripped_name) from e


class IsGradedImportMapper:
    class InvalidIsGradedError(Exception):
        def __init__(self, *args, invalid_is_graded: str, **kwargs):
            super().__init__(*args, **kwargs)
            self.invalid_is_graded: str = invalid_is_graded

    @classmethod
    def is_graded_from_import_string(cls, is_graded: str) -> bool:
        is_graded = is_graded.strip()
        if is_graded in settings.IMPORTER_GRADED_YES:
            return True
        if is_graded in settings.IMPORTER_GRADED_NO:
            return False

        raise cls.InvalidIsGradedError(invalid_is_graded=is_graded)


@dataclass
class EnrollmentInputRow(InputRow):
    """Raw representation of a semantic enrollment importer row, independent on the import format (xls, csv, ...)"""

    # pylint: disable=too-many-instance-attributes

    column_count = 12

    location: ExcelFileLocation

    # Cells in the order of appearance in a row of an import file
    evaluation_program_name: str

    student_last_name: str
    student_first_name: str
    student_email: str

    evaluation_course_type_name: str
    evaluation_is_graded: str
    evaluation_name_de: str
    evaluation_name_en: str

    responsible_title: str
    responsible_last_name: str
    responsible_first_name: str
    responsible_email: str


@dataclass
class EnrollmentParsedRow:
    """
    Representation of an Enrollment Row after parsing the data into the resulting data structures.
    For example, the course program will already be resolved in here.  This is the data structure we want to work with.
    """

    location: ExcelFileLocation

    student_data: UserData
    responsible_data: UserData
    course_data: CourseData


class EnrollmentInputRowMapper:
    def __init__(self, importer_log: ImporterLog):
        self.importer_log: ImporterLog = importer_log

        self.course_type_mapper = CourseTypeImportMapper()
        self.program_mapper = ProgramImportMapper()
        self.is_graded_mapper = IsGradedImportMapper()

        self.invalid_programs_tracker: FirstLocationAndCountTracker | None = None
        self.invalid_course_types_tracker: FirstLocationAndCountTracker | None = None
        self.invalid_is_graded_tracker: FirstLocationAndCountTracker | None = None

    def map(self, rows: Iterable[EnrollmentInputRow]) -> Iterable[EnrollmentParsedRow]:
        self.invalid_programs_tracker = FirstLocationAndCountTracker()
        self.invalid_course_types_tracker = FirstLocationAndCountTracker()
        self.invalid_is_graded_tracker = FirstLocationAndCountTracker()

        result_rows = [self._map_row(row) for row in rows]
        self._log_aggregated_messages()
        return result_rows

    def _map_row(self, row: EnrollmentInputRow) -> EnrollmentParsedRow:
        assert self.invalid_programs_tracker is not None
        assert self.invalid_course_types_tracker is not None
        assert self.invalid_is_graded_tracker is not None

        student_data = UserData(
            first_name=row.student_first_name,
            last_name=row.student_last_name,
            email=row.student_email,
            title="",
        )

        responsible_data = UserData(
            first_name=row.responsible_first_name,
            last_name=row.responsible_last_name,
            title=row.responsible_title,
            email=row.responsible_email,
        )

        programs: MaybeInvalid[set[Program]]
        try:
            programs = {self.program_mapper.program_from_import_string(row.evaluation_program_name)}
        except ProgramImportMapper.InvalidProgramNameError as e:
            programs = invalid_value
            self.invalid_programs_tracker.add_location_for_key(row.location, e.invalid_program_name)

        course_type: MaybeInvalid[CourseType]
        try:
            course_type = self.course_type_mapper.course_type_from_import_string(row.evaluation_course_type_name)
        except CourseTypeImportMapper.InvalidCourseTypeError as e:
            course_type = invalid_value
            self.invalid_course_types_tracker.add_location_for_key(row.location, e.invalid_course_type)

        is_graded: MaybeInvalid[bool]
        try:
            is_graded = self.is_graded_mapper.is_graded_from_import_string(row.evaluation_is_graded)
        except IsGradedImportMapper.InvalidIsGradedError as e:
            is_graded = invalid_value
            self.invalid_is_graded_tracker.add_location_for_key(row.location, e.invalid_is_graded)

        course_data = CourseData(
            name_de=row.evaluation_name_de,
            name_en=row.evaluation_name_en,
            programs=programs,
            course_type=course_type,
            is_graded=is_graded,
            responsible_email=row.responsible_email,
        )

        return EnrollmentParsedRow(
            location=row.location,
            student_data=student_data,
            responsible_data=responsible_data,
            course_data=course_data,
        )

    def _log_aggregated_messages(self) -> None:
        assert self.invalid_course_types_tracker
        assert self.invalid_is_graded_tracker
        assert self.invalid_programs_tracker

        for key, location_string in self.invalid_course_types_tracker.aggregated_keys_and_location_strings():
            self.importer_log.add_error(
                _(
                    '{location}: No course type is associated with the import name "{course_type}". Please manually create it first.'
                ).format(
                    location=location_string,
                    course_type=key,
                ),
                category=ImporterLogEntry.Category.COURSE_TYPE_MISSING,
            )

        for key, location_string in self.invalid_is_graded_tracker.aggregated_keys_and_location_strings():
            self.importer_log.add_error(
                _('{location}: "is_graded" is {is_graded}, but must be {is_graded_yes} or {is_graded_no}').format(
                    location=location_string,
                    is_graded=key,
                    is_graded_yes=settings.IMPORTER_GRADED_YES,
                    is_graded_no=settings.IMPORTER_GRADED_NO,
                ),
                category=ImporterLogEntry.Category.IS_GRADED,
            )

        for key, location_string in self.invalid_programs_tracker.aggregated_keys_and_location_strings():
            self.importer_log.add_error(
                _(
                    '{location}: No program is associated with the import name "{program}". Please manually create it first.'
                ).format(
                    location=location_string,
                    program=key,
                ),
                category=ImporterLogEntry.Category.PROGRAM_MISSING,
            )


class CourseMergeLogic:
    class MergeError(Exception):
        def __init__(self, *args, merge_hindrances: list[str], **kwargs):
            super().__init__(*args, **kwargs)
            self.merge_hindrances: list[str] = merge_hindrances

    class NameDeCollisionError(Exception):
        """Course with same name_de, but different name_en exists"""

    class NameEnCollisionError(Exception):
        """Course with same name_en, but different name_de exists"""

    def __init__(self, semester: Semester):
        courses = Course.objects.filter(semester=semester).prefetch_related("type", "responsibles", "evaluations")

        assert ("semester", "name_de") in Course._meta.unique_together
        self.courses_by_name_de = {course.name_de: course for course in courses}

        assert ("semester", "name_en") in Course._meta.unique_together
        self.courses_by_name_en = {course.name_en: course for course in courses}

    @staticmethod
    def get_merge_hindrances(course_data: CourseData, merge_candidate: Course) -> list[str]:
        hindrances = []

        if merge_candidate.type != course_data.course_type:
            hindrances.append(_("the course type does not match"))

        responsibles = merge_candidate.responsibles.all()
        if len(responsibles) != 1 or responsibles[0].email != course_data.responsible_email:
            hindrances.append(_("the responsibles of the course do not match"))

        merge_candidate_evaluations = merge_candidate.evaluations.all()
        if len(merge_candidate_evaluations) != 1:
            hindrances.append(_("the existing course does not have exactly one evaluation"))
            return hindrances

        merge_candidate_evaluation: Evaluation = merge_candidate_evaluations[0]

        if merge_candidate_evaluation.wait_for_grade_upload_before_publishing != course_data.is_graded:
            hindrances.append(_("the evaluation of the existing course has a mismatching grading specification"))

        if merge_candidate_evaluation.is_single_result:
            hindrances.append(_("the evaluation of the existing course is a single result"))
            return hindrances

        if merge_candidate_evaluation.state >= Evaluation.State.IN_EVALUATION:
            hindrances.append(
                _("the import would add participants to the existing evaluation but the evaluation is already running")
            )
        else:
            assert merge_candidate_evaluation._participant_count is None

        return hindrances

    def set_course_merge_target(self, course_data: CourseData) -> None:
        course_with_same_name_en = self.courses_by_name_en.get(course_data.name_en, None)
        course_with_same_name_de = self.courses_by_name_de.get(course_data.name_de, None)

        if course_with_same_name_en is None and course_with_same_name_de is None:
            # No name matches --> no merging, all is fine
            course_data.merge_into_course = None
            return

        if course_with_same_name_en != course_with_same_name_de:
            if course_with_same_name_en is not None:
                raise self.NameEnCollisionError

            if course_with_same_name_de is not None:
                raise self.NameDeCollisionError

        assert course_with_same_name_en is not None
        assert course_with_same_name_de is not None
        assert course_with_same_name_en == course_with_same_name_de

        merge_candidate = course_with_same_name_en

        merge_hindrances = self.get_merge_hindrances(course_data, merge_candidate)
        if merge_hindrances:
            raise self.MergeError(merge_hindrances=merge_hindrances)

        course_data.merge_into_course = merge_candidate


class CourseNameChecker(Checker):
    """
    Assert that
        - courses are mergeable (set merge_into_course in this case) or course names do not collide
        - the same german name is only used by the same course

        same name_en is by definition the same course, so we don't need to check for duplicate name_en in the file.
        dfferent name_de for the same name_en is handled in the CourseDataMismatchChecker
    """

    def __init__(self, *args, semester: Semester, **kwargs):
        super().__init__(*args, **kwargs)

        self.course_merge_logic = CourseMergeLogic(semester)
        self.course_merged_tracker = FirstLocationAndCountTracker()
        self.course_merge_impossible_tracker = FirstLocationAndCountTracker()
        self.name_de_collision_tracker = FirstLocationAndCountTracker()
        self.name_en_collision_tracker = FirstLocationAndCountTracker()

        self.name_en_by_name_de: dict[str, str] = {}
        self.name_de_mismatch_tracker = FirstLocationAndCountTracker()

    def check_course_data(self, course_data: CourseData, location: ExcelFileLocation) -> None:
        try:
            self.course_merge_logic.set_course_merge_target(course_data)

        except CourseMergeLogic.MergeError as e:
            self.course_merge_impossible_tracker.add_location_for_key(
                location, (course_data.name_en, tuple(e.merge_hindrances))
            )

        except CourseMergeLogic.NameDeCollisionError:
            self.name_de_collision_tracker.add_location_for_key(location, course_data.name_de)

        except CourseMergeLogic.NameEnCollisionError:
            self.name_en_collision_tracker.add_location_for_key(location, course_data.name_en)

        if course_data.merge_into_course != invalid_value and course_data.merge_into_course:
            self.course_merged_tracker.add_location_for_key(location, course_data.name_en)

        self.name_en_by_name_de.setdefault(course_data.name_de, course_data.name_en)
        if course_data.name_en != self.name_en_by_name_de[course_data.name_de]:
            # using (name_en, name_de) as key to have one error for each course that shares the name_de
            self.name_de_mismatch_tracker.add_location_for_key(location, (course_data.name_en, course_data.name_de))

    def finalize(self) -> None:
        for name_en, _location_string in self.course_merged_tracker.aggregated_keys_and_location_strings():
            self.importer_log.add_warning(
                _(
                    'Course "{course_name}" already exists. The course will not be created, instead users are imported into the '
                    "evaluation of the existing course and any additional programs are added.",
                ).format(course_name=name_en),
                category=ImporterLogEntry.Category.EXISTS,
            )

        for key, location_string in self.course_merge_impossible_tracker.aggregated_keys_and_location_strings():
            name_en, merge_hindrances = key
            self.importer_log.add_error(
                format_html(
                    _(
                        "{location}: Course {course_name} already exists in this semester, but the courses cannot be merged for the following reasons:{reasons}"
                    ),
                    location=location_string,
                    course_name=f'"{name_en}"',
                    reasons=format_html_join("", "<br /> - {}", ([msg] for msg in merge_hindrances)),
                ),
                category=ImporterLogEntry.Category.COURSE,
            )

        for name_de, location_string in self.name_de_collision_tracker.aggregated_keys_and_location_strings():
            self.importer_log.add_error(
                _(
                    '{location}: Course "{course_name}" (DE) already exists in this semester with a different english name.'
                ).format(
                    location=location_string,
                    course_name=name_de,
                ),
                category=ImporterLogEntry.Category.COURSE,
            )

        for name_en, location_string in self.name_en_collision_tracker.aggregated_keys_and_location_strings():
            self.importer_log.add_error(
                _(
                    '{location}: Course "{course_name}" (EN) already exists in this semester with a different german name.'
                ).format(
                    location=location_string,
                    course_name=name_en,
                ),
                category=ImporterLogEntry.Category.COURSE,
            )

        for (name_en, __), location_string in self.name_de_mismatch_tracker.aggregated_keys_and_location_strings():
            self.importer_log.add_error(
                _(
                    '{location}: The German name for course "{course_name}" is already used for another course in the import file.'
                ).format(
                    location=location_string,
                    course_name=name_en,
                ),
                category=ImporterLogEntry.Category.COURSE,
            )


class SimilarCourseNameChecker(Checker):
    """
    Searches for courses that have names with small edit distance and warns about them to make users aware of possible
    typos.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.course_en_tracker = FirstLocationAndCountTracker()
        self.course_de_tracker = FirstLocationAndCountTracker()

    def check_course_data(self, course_data: CourseData, location: ExcelFileLocation) -> None:
        self.course_en_tracker.add_location_for_key(location, course_data.name_en)
        self.course_de_tracker.add_location_for_key(location, course_data.name_de)

    def finalize(self) -> None:
        warning_texts = []

        for tracker in [self.course_en_tracker, self.course_de_tracker]:
            for needle_name, location_string in tracker.aggregated_keys_and_location_strings():
                matches = difflib.get_close_matches(
                    needle_name,
                    (name for name in tracker.keys() if name > needle_name),
                    n=1,
                    cutoff=settings.IMPORTER_COURSE_NAME_SIMILARITY_WARNING_THRESHOLD,
                )
                if matches:
                    warning_texts.append(
                        _('{location}: The course names "{name1}" and "{name2}" have a low edit distance.').format(
                            location=location_string,
                            name1=needle_name,
                            name2=matches[0],
                        )
                    )

        for warning_text in warning_texts:
            self.importer_log.add_warning(warning_text, category=ImporterLogEntry.Category.SIMILAR_COURSE_NAMES)


class ExistingParticipationChecker(Checker, RowCheckerMixin):
    """Warn if users are already stored as participants for a course in the database"""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.participant_emails_per_course_name_en: defaultdict[str, set[str]] = defaultdict(set)

    def check_row(self, row: EnrollmentParsedRow) -> None:
        # invalid value will still be set for courses with merge conflicts
        if row.course_data.merge_into_course is not None and row.course_data.merge_into_course != invalid_value:
            self.participant_emails_per_course_name_en[row.course_data.name_en].add(row.student_data.email)

    def finalize(self) -> None:
        # To reduce database traffic, we only load existing participations for users and evaluations seen in the import
        # file. They could still contain false positives, so we need to check each import row against these tuples
        seen_user_emails = [
            email for email_set in self.participant_emails_per_course_name_en.values() for email in email_set
        ]
        seen_evaluation_names = self.participant_emails_per_course_name_en.keys()

        existing_participation_pairs = [
            (participation.evaluation.course.name_en, participation.userprofile.email)  # type: ignore[misc]
            for participation in Evaluation.participants.through._default_manager.filter(
                evaluation__course__name_en__in=seen_evaluation_names, userprofile__email__in=seen_user_emails
            ).prefetch_related("userprofile", "evaluation__course")
        ]

        existing_participant_emails_per_course_name_en = unordered_groupby(existing_participation_pairs)

        for course_name_en, import_participant_emails in self.participant_emails_per_course_name_en.items():
            existing_participant_emails = set(existing_participant_emails_per_course_name_en.get(course_name_en, []))
            colliding_participant_emails = existing_participant_emails.intersection(import_participant_emails)

            if colliding_participant_emails:
                self.importer_log.add_warning(
                    ngettext(
                        "Course {course_name}: 1 participant from the import file already participates in the evaluation.",
                        "Course {course_name}: {participant_count} participants from the import file already participate in the evaluation.",
                        len(colliding_participant_emails),
                    ).format(course_name=course_name_en, participant_count=len(colliding_participant_emails)),
                    category=ImporterLogEntry.Category.ALREADY_PARTICIPATING,
                )


class CourseDataMismatchChecker(Checker):
    """Assert CourseData is consistent between rows"""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.course_data_by_name_en: dict[str, CourseData] = {}
        self.tracker = FirstLocationAndCountTracker()

    def check_course_data(self, course_data: CourseData, location: ExcelFileLocation) -> None:
        if not all_fields_valid(course_data):
            return

        stored = self.course_data_by_name_en.setdefault(course_data.name_en, course_data)

        # programs would be merged if course data is equal otherwise.
        differing_fields = course_data.differing_fields(stored) - {"programs"}
        if differing_fields:
            self.tracker.add_location_for_key(location, (course_data.name_en, tuple(differing_fields)))

    def finalize(self) -> None:
        for (course_name, differing_fields), location_string in self.tracker.aggregated_keys_and_location_strings():
            self.importer_log.add_error(
                _(
                    '{location}: The data of course "{name}" differs from its data in the columns ({columns}) in a previous row.'
                ).format(
                    location=location_string,
                    name=course_name,
                    columns=", ".join(differing_fields),
                ),
                category=ImporterLogEntry.Category.COURSE,
            )


class UserProgramMismatchChecker(Checker, RowCheckerMixin):
    """Assert that a users program is consistent between rows"""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.program_by_email: dict[str, Program] = {}
        self.tracker = FirstLocationAndCountTracker()

    def check_row(self, row: EnrollmentParsedRow):
        if row.student_data.email == "":
            return

        if isinstance(row.course_data.programs, InvalidValue):
            return

        assert len(row.course_data.programs) == 1, "Checker expected to have courses without merged programs"
        program = next(iter(row.course_data.programs))
        stored_program = self.program_by_email.setdefault(row.student_data.email, program)

        if stored_program != program:
            self.tracker.add_location_for_key(row.location, row.student_data.email)

    def finalize(self) -> None:
        for student_email, location_string in self.tracker.aggregated_keys_and_location_strings():
            self.importer_log.add_error(
                _('{location}: The program of user "{email}" differs from their program in a previous row.').format(
                    location=location_string,
                    email=student_email,
                ),
                category=ImporterLogEntry.Category.PROGRAM,
            )


class TooManyEnrollmentsChecker(Checker, RowCheckerMixin):
    """Warn when users exceed settings.IMPORTER_MAX_ENROLLMENTS enrollments"""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.evaluation_names_en_per_user: defaultdict[str, set[str]] = defaultdict(set)

    def check_row(self, row: EnrollmentParsedRow):
        if row.student_data.email == "":
            return

        self.evaluation_names_en_per_user[row.student_data.email].add(row.course_data.name_en)

    def finalize(self) -> None:
        for email, evaluation_names_en in self.evaluation_names_en_per_user.items():
            enrollment_count = len(evaluation_names_en)
            if enrollment_count > settings.IMPORTER_MAX_ENROLLMENTS:
                self.importer_log.add_warning(
                    _("Warning: User {} has {} enrollments, which is a lot.").format(email, enrollment_count),
                    category=ImporterLogEntry.Category.TOO_MANY_ENROLLMENTS,
                )


class UserDataAdapter(RowCheckerMixin):
    def __init__(self, user_data_checker) -> None:
        self.user_data_checker = user_data_checker

    def check_row(self, row: EnrollmentParsedRow) -> None:
        self.user_data_checker.check_userdata(row.student_data, row.location)
        self.user_data_checker.check_userdata(row.responsible_data, row.location)

    def finalize(self) -> None:
        self.user_data_checker.finalize()


class CourseDataAdapter(RowCheckerMixin):
    def __init__(self, course_data_checker) -> None:
        self.course_data_checker = course_data_checker

    def check_row(self, row: EnrollmentParsedRow) -> None:
        self.course_data_checker.check_course_data(row.course_data, row.location)

    def finalize(self) -> None:
        self.course_data_checker.finalize()


@transaction.atomic
def import_enrollments(
    excel_content: bytes,
    semester: Semester,
    vote_start_datetime: datetime | None,
    vote_end_date: date | None,
    test_run: bool,
) -> ImporterLog:
    # pylint: disable=too-many-locals
    importer_log = ImporterLog()

    with ConvertExceptionsToMessages(importer_log):
        input_rows = ExcelFileRowMapper(
            skip_first_n_rows=1,
            row_cls=EnrollmentInputRow,
            importer_log=importer_log,
        ).map(excel_content)
        importer_log.raise_if_has_errors()

        parsed_rows = EnrollmentInputRowMapper(importer_log).map(input_rows)
        for checker in [
            TooManyEnrollmentsChecker(test_run, importer_log),
            UserProgramMismatchChecker(test_run, importer_log),
            CourseDataAdapter(CourseNameChecker(test_run, importer_log, semester=semester)),
            CourseDataAdapter(CourseDataMismatchChecker(test_run, importer_log)),
            CourseDataAdapter(SimilarCourseNameChecker(test_run, importer_log)),
            UserDataAdapter(UserDataEmptyFieldsChecker(test_run, importer_log)),
            UserDataAdapter(UserDataMismatchChecker(test_run, importer_log)),
            UserDataAdapter(UserDataValidationChecker(test_run, importer_log)),
            ExistingParticipationChecker(test_run, importer_log),
        ]:
            checker.check_rows(parsed_rows)

        importer_log.raise_if_has_errors()

        user_data_list, course_data_list = normalize_rows(parsed_rows)
        existing_user_profiles, new_user_profiles = get_user_profile_objects(user_data_list)

        responsible_emails = {course_data.responsible_email for course_data in course_data_list}
        new_responsibles_count = ilen(user for user in new_user_profiles if user.email in responsible_emails)
        new_participants_count = len(new_user_profiles) - new_responsibles_count
        new_course_count = ilen(course for course in course_data_list if not course.merge_into_course)

        importer_log.raise_if_has_errors()
        if test_run:
            importer_log.add_success(_("The test run showed no errors. No data was imported yet."))
            msg = _("The import run will create {evaluation_string} and {user_string}").format(
                evaluation_string=ngettext(
                    "1 course/evaluation", "{count} courses/evaluations", new_course_count
                ).format(count=new_course_count),
                user_string=ngettext("1 user", "{count} users", len(new_user_profiles)).format(
                    count=len(new_user_profiles)
                ),
            )

        else:
            assert vote_start_datetime is not None, "Import-run requires vote_start_datetime"
            assert vote_end_date is not None, "Import-run requires vote_end-date"
            update_existing_and_create_new_user_profiles(existing_user_profiles, new_user_profiles)
            update_existing_and_create_new_courses(course_data_list, semester, vote_start_datetime, vote_end_date)
            store_participations_in_db(parsed_rows)

            msg = _("Successfully created {evaluation_string}, {participant_string} and {contributor_string}").format(
                evaluation_string=ngettext(
                    "1 course/evaluation", "{count} courses/evaluations", new_course_count
                ).format(count=new_course_count),
                participant_string=ngettext("1 participant", "{count} participants", new_participants_count).format(
                    count=new_participants_count
                ),
                contributor_string=ngettext("1 contributor", "{count} contributors", new_responsibles_count).format(
                    count=new_responsibles_count
                ),
            )

        msg = append_user_list_if_not_empty(msg, new_user_profiles)
        importer_log.add_success(msg)

    return importer_log


def normalize_rows(enrollment_rows: Iterable[EnrollmentParsedRow]) -> tuple[list[UserData], list[ValidCourseData]]:
    """The row schema has denormalized students and evaluations. Normalize / merge them back together"""
    user_data_by_email: dict[str, UserData] = {}
    course_data_by_name_en: dict[str, ValidCourseData] = {}

    for row in enrollment_rows:
        stored = user_data_by_email.setdefault(row.student_data.email, row.student_data)
        assert stored == row.student_data

        stored = user_data_by_email.setdefault(row.responsible_data.email, row.responsible_data)
        assert stored == row.responsible_data

        assert all_fields_valid(row.course_data)
        course_data = course_data_by_name_en.setdefault(row.course_data.name_en, row.course_data)
        assert course_data.differing_fields(row.course_data) <= {"programs"}

        course_data.programs.update(row.course_data.programs)

    return list(user_data_by_email.values()), list(course_data_by_name_en.values())


def update_existing_and_create_new_courses(
    course_data_iterable: Iterable[ValidCourseData],
    semester: Semester,
    vote_start_datetime: datetime,
    vote_end_date: date,
) -> None:
    assert ("semester", "name_en") in Course._meta.unique_together
    course_data_by_name_en = {course_data.name_en: course_data for course_data in course_data_iterable}

    # Create all courses without a merge-target
    new_course_objects = [
        Course(
            name_de=course_data.name_de,
            name_en=course_data.name_en,
            type=course_data.course_type,
            semester=semester,
        )
        for course_data in course_data_iterable
        if not course_data.merge_into_course
    ]

    for course in new_course_objects:
        course.save()

    # Create one evaluation per newly created course
    evaluation_objects = [
        Evaluation(
            vote_start_datetime=vote_start_datetime,
            vote_end_date=vote_end_date,
            course=course,
            wait_for_grade_upload_before_publishing=course_data_by_name_en[course.name_en].is_graded,
        )
        for course in new_course_objects
    ]

    for evaluation in evaluation_objects:
        evaluation.save()

    # Create M2M entries for the responsibles of the newly created courses
    responsible_emails = {course_data.responsible_email for course_data in course_data_iterable}
    responsible_objs_by_email = {obj.email: obj for obj in UserProfile.objects.filter(email__in=responsible_emails)}

    for course in new_course_objects:
        course.responsibles.add(responsible_objs_by_email[course_data_by_name_en[course.name_en].responsible_email])

    # Create Contributions for the responsibles of the newly created courses
    evaluation_objects_by_course = {evaluation.course: evaluation for evaluation in evaluation_objects}
    contribution_objects = [
        Contribution(
            evaluation=evaluation_objects_by_course[course],
            contributor=responsible_objs_by_email[course_data_by_name_en[course.name_en].responsible_email],
            role=Contribution.Role.EDITOR,
            textanswer_visibility=Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS,
        )
        for course in new_course_objects
    ]

    for obj in contribution_objects:
        obj.save()

    # Create M2M entries for the programs of the newly created courses
    for course in new_course_objects:
        course.programs.add(*course_data_by_name_en[course.name_en].programs)

    courses_to_update = semester.courses.filter(
        name_en__in=[course_data.name_en for course_data in course_data_iterable if course_data.merge_into_course]
    )

    # Create M2M entries for the programs of the courses that are updated
    for course in courses_to_update:
        course.programs.add(*course_data_by_name_en[course.name_en].programs)


def store_participations_in_db(enrollment_rows: Iterable[EnrollmentParsedRow]):
    """Assume that the users and courses/evaluations already exist, add the participations"""

    user_emails = {row.student_data.email for row in enrollment_rows}
    users_by_email = {user.email: user for user in UserProfile.objects.filter(email__in=user_emails)}

    course_names_en = {row.course_data.name_en for row in enrollment_rows}
    evaluations_by_course_name_en = {
        evaluation.course.name_en: evaluation
        for evaluation in Evaluation.objects.select_related("course").filter(course__name_en__in=course_names_en)
    }

    participants_by_evaluation = defaultdict(list)
    for row in enrollment_rows:
        participants_by_evaluation[evaluations_by_course_name_en[row.course_data.name_en]].append(
            users_by_email[row.student_data.email]
        )

    for evaluation, participants in participants_by_evaluation.items():
        evaluation.participants.add(*participants)
