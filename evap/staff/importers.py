from collections import OrderedDict, defaultdict
from dataclasses import dataclass
from enum import Enum
from typing import Set, Dict
import xlrd

from django.conf import settings
from django.db import transaction
from django.utils.html import format_html
from django.utils.translation import gettext_lazy, gettext as _
from django.core.exceptions import ValidationError

from evap.evaluation.models import Contribution, Course, CourseType, Degree, Evaluation, UserProfile
from evap.evaluation.tools import clean_email
from evap.staff.tools import create_user_list_html_string_for_message, ImportType


def sorted_messages(messages):
    return OrderedDict(sorted(messages.items(), key=lambda item: item[0].order))


# taken from https://stackoverflow.com/questions/390250/elegant-ways-to-support-equivalence-equality-in-python-classes
class CommonEqualityMixin():

    def __eq__(self, other):
        return (isinstance(other, self.__class__)
            and self.__dict__ == other.__dict__)

    def __hash__(self):
        return hash(tuple(sorted(self.__dict__.items())))


class UserData(CommonEqualityMixin):
    """
        Holds information about a user, retrieved from the Excel file.
    """
    def __init__(self, first_name, last_name, title, email, is_responsible):
        self.first_name = first_name.strip()
        self.last_name = last_name.strip()
        self.title = title.strip()
        self.email = clean_email(email)
        self.is_responsible = is_responsible

    def store_in_database(self):
        user, created = UserProfile.objects.update_or_create(
            email=self.email,
            defaults={
                'first_name': self.first_name,
                'last_name': self.last_name,
                'title': self.title,
                'is_active': True
            }
        )
        return user, created

    def user_already_exists(self):
        return UserProfile.objects.filter(email=self.email).exists()

    def get_user_profile_object(self):
        user = UserProfile()
        user.first_name = self.first_name
        user.last_name = self.last_name
        user.email = self.email
        user.password = "asdf"  # clean_fields needs that...
        return user

    def validate(self):
        user = self.get_user_profile_object()
        user.clean_fields()


@dataclass
class EvaluationData:
    """
        Holds information about an evaluation, retrieved from the Excel file.
    """
    name_de: str
    name_en: str
    degrees: Set[Degree]
    course_type: CourseType
    is_graded: bool
    responsible_email: str
    errors: Dict

    def equals_except_for_degrees(self, other):
        return (
            self.degrees != other.degrees
            and self.name_de == other.name_de
            and self.name_en == other.name_en
            and self.course_type == other.course_type
            and self.is_graded == other.is_graded
            and self.responsible_email == other.responsible_email
        )

    def store_in_database(self, vote_start_datetime, vote_end_date, semester):
        assert not self.errors
        # This is safe because the user's email address is checked before in the importer (see #953)
        responsible_dbobj = UserProfile.objects.get(email=self.responsible_email)
        course = Course(
            name_de=self.name_de,
            name_en=self.name_en,
            type=self.course_type,
            semester=semester,
        )
        course.save()
        course.responsibles.set([responsible_dbobj])
        course.degrees.set(self.degrees)
        evaluation = Evaluation(
            vote_start_datetime=vote_start_datetime,
            vote_end_date=vote_end_date,
            course=course,
            wait_for_grade_upload_before_publishing=self.is_graded,
        )
        evaluation.save()
        evaluation.contributions.create(
            evaluation=evaluation,
            contributor=responsible_dbobj,
            role=Contribution.Role.EDITOR,
            textanswer_visibility=Contribution.TextAnswerVisibility.GENERAL_TEXTANSWERS,
        )


class ImporterError(Enum):
    def __new__(cls, value, label, order):
        variant = object.__new__(cls)
        variant._value_ = value
        variant.label = label
        variant.order = order
        return variant

    GENERAL = ('general', gettext_lazy("General errors"), 0)
    SCHEMA = ('schema', gettext_lazy("Incorrect Excel format"), 1)
    USER = ('user', gettext_lazy("Invalid user data"), 6)

    DEGREE_MISSING = ('missing_degree', gettext_lazy("Missing degrees"), 2)
    COURSE_TYPE_MISSING = ('missing_course_type', gettext_lazy("Missing course types"), 3)
    COURSE = ('course', gettext_lazy("Course issues"), 4)
    IS_GRADED = ('is_graded', gettext_lazy("Invalid values"), 5)


class ImporterWarning(Enum):
    def __new__(cls, value, label, order):
        variant = object.__new__(cls)
        variant._value_ = value
        variant.label = label
        variant.order = order
        return variant

    GENERAL = ('general', gettext_lazy("General warnings"), 0)
    NAME = ('name', gettext_lazy("Name mismatches"), 1)
    INACTIVE = ('inactive', gettext_lazy("Inactive users"), 2)
    DUPL = ('duplicate', gettext_lazy("Possible duplicates"), 3)
    IGNORED = ('ignored', gettext_lazy("Ignored duplicates"), 4)

    DEGREE = ('degree', gettext_lazy("Degree mismatches"), 5)
    MANY = ('too_many_enrollments', gettext_lazy("Unusually high number of enrollments"), 6)


class EvaluationDataFactory:
    def __init__(self):
        self.degrees = {
            import_name.lower(): degree
            for degree in Degree.objects.all()
            for import_name in degree.import_names
        }
        self.course_types = {
            import_name.lower(): course_type
            for course_type in CourseType.objects.all()
            for import_name in course_type.import_names
        }

    def create(self, name_de, name_en, degree_names, course_type_name, is_graded, responsible_email):
        errors = {}
        degrees = {self.get_degree_or_add_error(degree_name, errors) for degree_name in degree_names.split(',')}
        course_type = self.get_course_or_add_error(course_type_name, errors)
        is_graded = self.parse_is_graded_or_add_error(is_graded, errors)

        return EvaluationData(
            name_de=name_de.strip(),
            name_en=name_en.strip(),
            degrees=degrees,
            course_type=course_type,
            is_graded=is_graded,
            responsible_email=responsible_email,
            errors=errors,
        )

    def get_degree_or_add_error(self, degree_name, errors):
        try:
            return self.degrees[degree_name.strip().lower()]
        except KeyError:
            errors.setdefault('degrees', set()).add(degree_name)
            return None

    def get_course_or_add_error(self, course_type_name, errors):
        try:
            return self.course_types[course_type_name.strip().lower()]
        except KeyError:
            errors['course_type'] = course_type_name
            return None

    @staticmethod
    def parse_is_graded_or_add_error(is_graded, errors):
        is_graded = is_graded.strip()
        if is_graded == settings.IMPORTER_GRADED_YES:
            return True
        if is_graded == settings.IMPORTER_GRADED_NO:
            return False
        errors['is_graded'] = is_graded
        return None


class ExcelImporter():

    def __init__(self):
        self.associations = OrderedDict()
        self.book = None
        self.skip_first_n_rows = 1  # first line contains the header
        self.success_messages = []
        self.errors = defaultdict(list)
        self.warnings = defaultdict(list)

        # this is a dictionary to not let this become O(n^2)
        # ordered to always keep the order of the imported users the same when iterating over it
        # (otherwise, testing is a pain)
        self.users = OrderedDict()

    def read_book(self, file_content):
        try:
            self.book = xlrd.open_workbook(file_contents=file_content)
        except xlrd.XLRDError as e:
            self.errors[ImporterError.SCHEMA].append(_("Couldn't read the file. Error: {}").format(e))

    def check_column_count(self, expected_column_count):
        for sheet in self.book.sheets():
            if sheet.nrows <= self.skip_first_n_rows:
                continue
            if sheet.ncols != expected_column_count:
                self.errors[ImporterError.SCHEMA].append(
                    _("Wrong number of columns in sheet '{}'. Expected: {}, actual: {}")
                    .format(sheet.name, expected_column_count, sheet.ncols))

    def for_each_row_in_excel_file_do(self, row_function):
        for sheet in self.book.sheets():
            try:
                for row in range(self.skip_first_n_rows, sheet.nrows):
                    data = []  # container for normalized cell data
                    for cell in sheet.row_values(row):
                        data.append(' '.join(cell.split()))  # see https://stackoverflow.com/questions/2077897/substitute-multiple-whitespace-with-single-whitespace-in-python
                    row_function(data, sheet, row)
                self.success_messages.append(_("Successfully read sheet '%s'.") % sheet.name)
            except Exception:
                self.warnings[ImporterWarning.GENERAL].append(
                    _("A problem occured while reading sheet {}.").format(sheet.name))
                raise
        self.success_messages.append(_("Successfully read Excel file."))

    def process_user(self, user_data, sheet, row):
        curr_email = user_data.email
        if curr_email == "":
            self.errors[ImporterError.USER].append(
                _('Sheet "{}", row {}: Email address is missing.').format(sheet, row + 1))
            return
        if curr_email not in self.users:
            self.users[curr_email] = user_data
        else:
            if not user_data == self.users[curr_email]:
                self.errors[ImporterError.USER].append(
                    _('Sheet "{}", row {}: The users\'s data (email: {}) differs from it\'s data in a previous row.')
                    .format(sheet, row + 1, curr_email))

    def check_user_data_correctness(self):
        for user_data in self.users.values():
            try:
                user_data.validate()
            except ValidationError as e:
                self.errors[ImporterError.USER].append(
                    _('User {}: Error when validating: {}').format(user_data.email, e))

            if user_data.first_name == "":
                self.errors[ImporterError.USER].append(_('User {}: First name is missing.').format(user_data.email))
            if user_data.last_name == "":
                self.errors[ImporterError.USER].append(_('User {}: Last name is missing.').format(user_data.email))

    @staticmethod
    def _create_user_string(user):
        return format_html("{} {} {}, {}", user.title or "", user.first_name, user.last_name, user.email or "")

    @staticmethod
    def _create_user_data_mismatch_warning(user, user_data, test_run):
        if test_run:
            msg = format_html(_("The existing user would be overwritten with the following data:"))
        else:
            msg = format_html(_("The existing user was overwritten with the following data:"))
        return (msg
            + format_html("<br /> - {} ({})", ExcelImporter._create_user_string(user), _("existing"))
            + format_html("<br /> - {} ({})", ExcelImporter._create_user_string(user_data), _("new")))

    @staticmethod
    def _create_user_inactive_warning(user, test_run):
        user_string = ExcelImporter._create_user_string(user)
        if test_run:
            return format_html(_("The following user is currently marked inactive and will be marked active upon importing: {}"), user_string)

        return format_html(_("The following user was previously marked inactive and is now marked active upon importing: {}"), user_string)

    def _create_user_name_collision_warning(self, user_data, users_with_same_names):
        warningstring = format_html(_("An existing user has the same first and last name as a new user:"))
        for user in users_with_same_names:
            warningstring += format_html("<br /> - {} ({})", self._create_user_string(user), _("existing"))
        warningstring += format_html("<br /> - {} ({})", self._create_user_string(user_data), _("new"))

        self.warnings[ImporterWarning.DUPL].append(warningstring)

    def check_user_data_sanity(self, test_run):
        for user_data in self.users.values():
            try:
                user = UserProfile.objects.get(email=user_data.email)
                if ((user.title is not None and user.title != user_data.title)
                        or user.first_name != user_data.first_name
                        or user.last_name != user_data.last_name):
                    self.warnings[ImporterWarning.NAME].append(
                        self._create_user_data_mismatch_warning(user, user_data, test_run))
                if not user.is_active:
                    self.warnings[ImporterWarning.INACTIVE].append(self._create_user_inactive_warning(user, test_run))
            except UserProfile.DoesNotExist:
                pass

            users_same_name = (UserProfile.objects
                .filter(first_name=user_data.first_name, last_name=user_data.last_name)
                .exclude(email=user_data.email))
            if len(users_same_name) > 0:
                self._create_user_name_collision_warning(user_data, users_same_name)


class EnrollmentImporter(ExcelImporter):
    def __init__(self):
        super().__init__()
        # this is a dictionary to not let this become O(n^2)
        self.evaluations = {}
        self.enrollments = []
        self.names_de = set()
        self.evaluation_data_factory = EvaluationDataFactory()

    def read_one_enrollment(self, data, sheet, row):
        student_data = UserData(first_name=data[2], last_name=data[1], email=data[3], title='', is_responsible=False)
        responsible_data = UserData(first_name=data[10], last_name=data[9], title=data[8], email=data[11], is_responsible=True)
        evaluation_data = self.evaluation_data_factory.create(
            name_de=data[6],
            name_en=data[7],
            degree_names=data[0],
            course_type_name=data[4],
            is_graded=data[5],
            responsible_email=responsible_data.email,
        )
        self.associations[(sheet.name, row)] = (student_data, responsible_data, evaluation_data)

    def process_evaluation(self, evaluation_data, sheet, row):
        evaluation_id = evaluation_data.name_en
        if evaluation_id not in self.evaluations:
            if evaluation_data.name_de in self.names_de:
                self.errors[ImporterError.COURSE].append(
                    _('Sheet "{}", row {}: The German name for course "{}" already exists for another course.')
                    .format(sheet, row + 1, evaluation_data.name_en))
            else:
                self.evaluations[evaluation_id] = evaluation_data
                self.names_de.add(evaluation_data.name_de)
        else:
            if evaluation_data.equals_except_for_degrees(self.evaluations[evaluation_id]):
                self.warnings[ImporterWarning.DEGREE].append(
                    _('Sheet "{}", row {}: The course\'s "{}" degree differs from it\'s degree in a previous row.'
                      ' Both degrees have been set for the course.')
                    .format(sheet, row + 1, evaluation_data.name_en)
                )
                self.evaluations[evaluation_id].degrees |= evaluation_data.degrees
            elif evaluation_data != self.evaluations[evaluation_id]:
                self.errors[ImporterError.COURSE].append(
                    _('Sheet "{}", row {}: The course\'s "{}" data differs from it\'s data in a previous row.')
                    .format(sheet, row + 1, evaluation_data.name_en))

    def consolidate_enrollment_data(self):
        for (sheet, row), (student_data, responsible_data, evaluation_data) in self.associations.items():
            self.process_user(student_data, sheet, row)
            self.process_user(responsible_data, sheet, row)
            self.process_evaluation(evaluation_data, sheet, row)
            self.enrollments.append((evaluation_data, student_data))

    def check_evaluation_data_correctness(self, semester):
        degree_names = set()
        course_type_names = set()
        for evaluation_data in self.evaluations.values():
            if Course.objects.filter(semester=semester, name_en=evaluation_data.name_en).exists():
                self.errors[ImporterError.COURSE].append(
                    _("Course {} does already exist in this semester.").format(evaluation_data.name_en))
            if Course.objects.filter(semester=semester, name_de=evaluation_data.name_de).exists():
                self.errors[ImporterError.COURSE].append(
                    _("Course {} does already exist in this semester.").format(evaluation_data.name_de))
            if 'degrees' in evaluation_data.errors:
                degree_names |= evaluation_data.errors['degrees']
            if 'course_type' in evaluation_data.errors:
                course_type_names.add(evaluation_data.errors['course_type'])
            if 'is_graded' in evaluation_data.errors:
                self.errors[ImporterError.IS_GRADED].append(
                    _('"is_graded" of course {} is {}, but must be {} or {}')
                    .format(evaluation_data.name_en, evaluation_data.errors['is_graded'],
                            settings.IMPORTER_GRADED_YES, settings.IMPORTER_GRADED_NO))

        for degree_name in degree_names:
            self.errors[ImporterError.DEGREE_MISSING].append(
                _("Error: No degree is associated with the import name \"{}\". Please manually create it first.")
                .format(degree_name))
        for course_type_name in course_type_names:
            self.errors[ImporterError.COURSE_TYPE_MISSING].append(
                _("Error: No course type is associated with the import name \"{}\". Please manually create it first.")
                .format(course_type_name))

    def check_enrollment_data_sanity(self):
        enrollments_per_user = defaultdict(list)
        for enrollment in self.enrollments:
            index = enrollment[1].email
            enrollments_per_user[index].append(enrollment)
        for email, enrollments in enrollments_per_user.items():
            if len(enrollments) > settings.IMPORTER_MAX_ENROLLMENTS:
                self.warnings[ImporterWarning.MANY].append(
                    _("Warning: User {} has {} enrollments, which is a lot.").format(email, len(enrollments)))

    def write_enrollments_to_db(self, semester, vote_start_datetime, vote_end_date):
        students_created = []
        responsibles_created = []

        with transaction.atomic():
            for user_data in self.users.values():
                # this also marks the users active
                __, created = user_data.store_in_database()
                if created:
                    if user_data.is_responsible:
                        responsibles_created.append(user_data)
                    else:
                        students_created.append(user_data)
            for evaluation_data in self.evaluations.values():
                evaluation_data.store_in_database(vote_start_datetime, vote_end_date, semester)

            for evaluation_data, student_data in self.enrollments:
                evaluation = Evaluation.objects.get(course__semester=semester, course__name_de=evaluation_data.name_de)
                student = UserProfile.objects.get(email=student_data.email)
                evaluation.participants.add(student)

        msg = format_html(_("Successfully created {} courses/evaluations, {} students and {} contributors:"),
            len(self.evaluations), len(students_created), len(responsibles_created))
        msg += create_user_list_html_string_for_message(students_created + responsibles_created)
        self.success_messages.append(msg)

    def create_test_success_messages(self):
        filtered_users = [user_data for user_data in self.users.values() if not user_data.user_already_exists()]

        self.success_messages.append(_("The test run showed no errors. No data was imported yet."))
        msg = format_html(_("The import run will create {} courses/evaluations and {} users:"), len(self.evaluations), len(filtered_users))
        msg += create_user_list_html_string_for_message(filtered_users)
        self.success_messages.append(msg)

    @classmethod
    def process(cls, excel_content, semester, vote_start_datetime, vote_end_date, test_run):
        """
            Entry point for the view.
        """
        try:
            importer = cls()
            importer.read_book(excel_content)
            if importer.errors:
                return importer.success_messages, importer.warnings, importer.errors

            importer.check_column_count(12)

            if importer.errors:
                importer.errors[ImporterError.GENERAL].append(_("The input data is malformed. No data was imported."))
                return importer.success_messages, importer.warnings, importer.errors

            importer.for_each_row_in_excel_file_do(importer.read_one_enrollment)
            importer.consolidate_enrollment_data()
            importer.check_user_data_correctness()
            importer.check_evaluation_data_correctness(semester)
            importer.check_enrollment_data_sanity()
            importer.check_user_data_sanity(test_run)

            if importer.errors:
                importer.errors[ImporterError.GENERAL].append(
                    _("Errors occurred while parsing the input data. No data was imported."))
            elif test_run:
                importer.create_test_success_messages()
            else:
                importer.write_enrollments_to_db(semester, vote_start_datetime, vote_end_date)

        except Exception as e:  # pylint: disable=broad-except
            importer.errors[ImporterError.GENERAL].append(_("Import finally aborted after exception: '%s'" % e))
            if settings.DEBUG:
                # re-raise error for further introspection if in debug mode
                raise

        return importer.success_messages, importer.warnings, importer.errors


class UserImporter(ExcelImporter):

    def __init__(self):
        super().__init__()
        self._read_user_data = dict()

    def read_one_user(self, data, sheet, row):
        user_data = UserData(title=data[0], first_name=data[1], last_name=data[2], email=data[3], is_responsible=False)
        self.associations[(sheet.name, row)] = user_data
        if user_data not in self._read_user_data:
            self._read_user_data[user_data] = (sheet.name, row)
        else:
            orig_sheet, orig_row = self._read_user_data[user_data]
            warningstring = _("The duplicated row {row} in sheet '{sheet}' was ignored. It was first found in sheet '{orig_sheet}' on row {orig_row}.").format(
                    sheet=sheet.name,
                    row=row + 1,
                    orig_sheet=orig_sheet,
                    orig_row=orig_row + 1,
            )
            self.warnings[ImporterWarning.IGNORED].append(warningstring)

    def consolidate_user_data(self):
        for (sheet, row), (user_data) in self.associations.items():
            self.process_user(user_data, sheet, row)

    def save_users_to_db(self):
        """
            Stores the read data in the database. Errors might still
            occur because of the data already in the database.
        """
        new_participants = []
        created_users = []
        with transaction.atomic():
            for user_data in self.users.values():
                try:
                    user, created = user_data.store_in_database()
                    new_participants.append(user)
                    if created:
                        created_users.append(user)

                except Exception as error:
                    self.errors[ImporterError.GENERAL].append(
                        _("A problem occured while writing the entries to the database."
                          " The error message has been: '{}'").format(error=error))
                    raise

        msg = format_html(_("Successfully created {} users:"), len(created_users))
        msg += create_user_list_html_string_for_message(created_users)
        self.success_messages.append(msg)
        return new_participants

    def get_user_profile_list(self):
        new_participants = []
        for user_data in self.users.values():
            try:
                new_participant = UserProfile.objects.get(email=user_data.email)
            except UserProfile.DoesNotExist:
                new_participant = user_data.get_user_profile_object()
            new_participants.append(new_participant)
        return new_participants

    def create_test_success_messages(self):
        filtered_users = [user_data for user_data in self.users.values() if not user_data.user_already_exists()]

        self.success_messages.append(_("The test run showed no errors. No data was imported yet."))
        msg = format_html(_("The import run will create {} users:"), len(filtered_users))
        msg += create_user_list_html_string_for_message(filtered_users)
        self.success_messages.append(msg)

    @classmethod
    def process(cls, excel_content, test_run):
        """
            Entry point for the view.
        """
        try:
            importer = cls()

            importer.read_book(excel_content)
            if importer.errors:
                return [], importer.success_messages, importer.warnings, importer.errors

            importer.check_column_count(4)
            if importer.errors:
                importer.errors[ImporterError.GENERAL].append(_("The input data is malformed. No data was imported."))
                return [], importer.success_messages, importer.warnings, importer.errors

            importer.for_each_row_in_excel_file_do(importer.read_one_user)
            importer.consolidate_user_data()
            importer.check_user_data_correctness()
            importer.check_user_data_sanity(test_run)

            if importer.errors:
                importer.errors[ImporterError.GENERAL].append(
                    _("Errors occurred while parsing the input data. No data was imported."))
                return [], importer.success_messages, importer.warnings, importer.errors
            if test_run:
                importer.create_test_success_messages()
                return importer.get_user_profile_list(), importer.success_messages, importer.warnings, importer.errors

            return importer.save_users_to_db(), importer.success_messages, importer.warnings, importer.errors

        except Exception as e:  # pylint: disable=broad-except
            importer.errors[ImporterError.GENERAL].append(_("Import finally aborted after exception: '%s'" % e))
            if settings.DEBUG:
                # re-raise error for further introspection if in debug mode
                raise


class PersonImporter:
    def __init__(self):
        self.success_messages = []
        self.warnings = defaultdict(list)
        self.errors = defaultdict(list)

    def process_participants(self, evaluation, test_run, user_list):
        evaluation_participants = evaluation.participants.all()
        already_related = [user for user in user_list if user in evaluation_participants]
        users_to_add = [user for user in user_list if user not in evaluation_participants]

        if already_related:
            msg = format_html(_("The following {} users are already participants in evaluation {}:"), len(already_related), evaluation.name)
            msg += create_user_list_html_string_for_message(already_related)
            self.warnings[ImporterWarning.GENERAL].append(msg)

        if not test_run:
            evaluation.participants.add(*users_to_add)
            msg = format_html(_("{} participants added to the evaluation {}:"), len(users_to_add), evaluation.name)
        else:
            msg = format_html(_("{} participants would be added to the evaluation {}:"), len(users_to_add), evaluation.name)
        msg += create_user_list_html_string_for_message(users_to_add)

        self.success_messages.append(msg)

    def process_contributors(self, evaluation, test_run, user_list):
        already_related_contributions = Contribution.objects.filter(evaluation=evaluation, contributor__in=user_list)
        already_related = [contribution.contributor for contribution in already_related_contributions]
        if already_related:
            msg = format_html(_("The following {} users are already contributing to evaluation {}:"), len(already_related), evaluation.name)
            msg += create_user_list_html_string_for_message(already_related)
            self.warnings[ImporterWarning.GENERAL].append(msg)

        # since the user profiles are not necessarily saved to the database, they are not guaranteed to have a pk yet which
        # makes anything relying on hashes unusable here (for a faster list difference)
        users_to_add = [user for user in user_list if user not in already_related]

        if not test_run:
            for user in users_to_add:
                order = Contribution.objects.filter(evaluation=evaluation).count()
                Contribution.objects.create(evaluation=evaluation, contributor=user, order=order)
            msg = format_html(_("{} contributors added to the evaluation {}:"), len(users_to_add), evaluation.name)
        else:
            msg = format_html(_("{} contributors would be added to the evaluation {}:"), len(users_to_add), evaluation.name)
        msg += create_user_list_html_string_for_message(users_to_add)

        self.success_messages.append(msg)

    @classmethod
    def process_file_content(cls, import_type, evaluation, test_run, file_content):
        importer = cls()

        # the user import also makes these users active
        user_list, importer.success_messages, importer.warnings, importer.errors = UserImporter.process(file_content, test_run)
        if import_type == ImportType.Participant:
            importer.process_participants(evaluation, test_run, user_list)
        else:
            assert import_type == ImportType.Contributor
            importer.process_contributors(evaluation, test_run, user_list)

        return importer.success_messages, importer.warnings, importer.errors

    @classmethod
    def process_source_evaluation(cls, import_type, evaluation, test_run, source_evaluation):
        importer = cls()

        if import_type == ImportType.Participant:
            user_list = list(source_evaluation.participants.all())
            importer.process_participants(evaluation, test_run, user_list)
        else:
            assert import_type == ImportType.Contributor
            user_list = list(UserProfile.objects.filter(contributions__evaluation=source_evaluation))
            importer.process_contributors(evaluation, test_run, user_list)

        cls.make_users_active(user_list)

        return importer.success_messages, importer.warnings, importer.errors

    @staticmethod
    def make_users_active(user_list):
        for user in user_list:
            if not user.is_active:
                user.is_active = True
                user.save()
