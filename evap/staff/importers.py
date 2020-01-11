from collections import OrderedDict, defaultdict
import xlrd

from django.conf import settings
from django.db import transaction
from django.utils.translation import ugettext_lazy, ugettext as _
from django.utils.safestring import mark_safe
from django.core.exceptions import ValidationError

from evap.evaluation.models import Contribution, Course, CourseType, Degree, Evaluation, UserProfile
from evap.evaluation.tools import clean_email


def create_user_list_string_for_message(users):
    msg = ""
    for user in users:
        msg += "<br />"
        msg += "{} {} ({})".format(user.first_name, user.last_name, user.email)
    return msg


# taken from https://stackoverflow.com/questions/390250/elegant-ways-to-support-equivalence-equality-in-python-classes
class CommonEqualityMixin():

    def __eq__(self, other):
        return (isinstance(other, self.__class__)
            and self.__dict__ == other.__dict__)


class UserData(CommonEqualityMixin):
    """
        Holds information about a user, retrieved from the Excel file.
    """
    def __init__(self, first_name, last_name, title, email, is_responsible):
        self.first_name = first_name.strip()
        self.last_name = last_name.strip()
        self.title = title.strip()
        self.email = clean_email(email)
        self.username = self.email
        self.is_responsible = is_responsible

    def store_in_database(self):
        user, created = UserProfile.objects.update_or_create(
            email=self.email,
            defaults={
                'username': self.username,
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
        user.username = self.username
        user.first_name = self.first_name
        user.last_name = self.last_name
        user.email = self.email
        user.password = "asdf"  # clean_fields needs that...
        return user

    def validate(self):
        user = self.get_user_profile_object()
        user.clean_fields()


class EvaluationData(CommonEqualityMixin):
    """
        Holds information about an evaluation, retrieved from the Excel file.
    """
    def __init__(self, name_de, name_en, type_name, degree_names, is_graded, responsible_email):
        self.name_de = name_de.strip()
        self.name_en = name_en.strip()
        self.type_name = type_name.strip()
        self.is_graded = is_graded.strip()
        self.responsible_email = responsible_email

        degree_names = degree_names.split(',')
        for degree_name in degree_names:
            degree_name = degree_name.strip()
        self.degree_names = degree_names

    def store_in_database(self, vote_start_datetime, vote_end_date, semester):
        course_type = CourseType.objects.get(name_de=self.type_name)
        # This is safe because the user's email address is checked before in the importer (see #953)
        responsible_dbobj = UserProfile.objects.get(email=self.responsible_email)
        course = Course(
            name_de=self.name_de,
            name_en=self.name_en,
            type=course_type,
            is_graded=self.is_graded,
            semester=semester,
        )
        course.save()
        course.responsibles.set([responsible_dbobj])
        for degree_name in self.degree_names:
            course.degrees.add(Degree.objects.get(name_de=degree_name))
        evaluation = Evaluation(
            vote_start_datetime=vote_start_datetime,
            vote_end_date=vote_end_date,
            course=course,
        )
        evaluation.save()
        evaluation.contributions.create(contributor=responsible_dbobj, evaluation=evaluation, can_edit=True, textanswer_visibility=Contribution.GENERAL_TEXTANSWERS)


class ExcelImporter():
    W_NAME = 'name'
    W_DUPL = 'duplicate'
    W_GENERAL = 'general'
    W_INACTIVE = 'inactive'

    def __init__(self):
        self.associations = OrderedDict()
        self.book = None
        self.skip_first_n_rows = 1  # first line contains the header
        self.errors = []
        self.success_messages = []
        self.warnings = defaultdict(list)

        # this is a dictionary to not let this become O(n^2)
        # ordered to always keep the order of the imported users the same when iterating over it
        # (otherwise, testing is a pain)
        self.users = OrderedDict()

    def read_book(self, file_content):
        try:
            self.book = xlrd.open_workbook(file_contents=file_content)
        except xlrd.XLRDError as e:
            self.errors.append(_("Couldn't read the file. Error: {}").format(e))

    def check_column_count(self, expected_column_count):
        for sheet in self.book.sheets():
            if sheet.nrows <= self.skip_first_n_rows:
                continue
            if sheet.ncols != expected_column_count:
                self.errors.append(_("Wrong number of columns in sheet '{}'. Expected: {}, actual: {}").format(sheet.name, expected_column_count, sheet.ncols))

    def for_each_row_in_excel_file_do(self, parse_row_function):
        for sheet in self.book.sheets():
            try:
                for row in range(self.skip_first_n_rows, sheet.nrows):
                    line_data = parse_row_function(sheet.row_values(row))
                    # store data objects together with the data source location for problem tracking
                    self.associations[(sheet.name, row)] = line_data

                self.success_messages.append(_("Successfully read sheet '%s'.") % sheet.name)
            except Exception:
                self.warnings[self.W_GENERAL].append(_("A problem occured while reading sheet {}.").format(sheet.name))
                raise
        self.success_messages.append(_("Successfully read Excel file."))

    def process_user(self, user_data, sheet, row):
        curr_email = user_data.email
        if curr_email == "":
            self.errors.append(_('Sheet "{}", row {}: Email address is missing.').format(sheet, row + 1))
            return
        if curr_email not in self.users:
            self.users[curr_email] = user_data
        else:
            if not user_data == self.users[curr_email]:
                self.errors.append(_('Sheet "{}", row {}: The users\'s data (email: {}) differs from it\'s data in a previous row.').format(sheet, row + 1, curr_email))

    def check_user_data_correctness(self):
        for user_data in self.users.values():
            try:
                user_data.validate()
            except ValidationError as e:
                self.errors.append(_('User {}: Error when validating: {}').format(user_data.email, e))

            if user_data.first_name == "":
                self.errors.append(_('User {}: First name is missing.').format(user_data.email))
            if user_data.last_name == "":
                self.errors.append(_('User {}: Last name is missing.').format(user_data.email))

    @staticmethod
    def _create_user_string(user):
        return "{} {} {}, {}".format(user.title or "", user.first_name, user.last_name, user.email or "")

    @staticmethod
    def _create_user_data_mismatch_warning(user, user_data, test_run):
        if test_run:
            msg = _("The existing user would be overwritten with the following data:")
        else:
            msg = _("The existing user was overwritten with the following data:")
        return (mark_safe(msg
            + "<br /> - " + ExcelImporter._create_user_string(user) + _(" (existing)")
            + "<br /> - " + ExcelImporter._create_user_string(user_data) + _(" (new)")))

    @staticmethod
    def _create_user_inactive_warning(user, test_run):
        if test_run:
            msg = _("The following user is currently marked inactive and will be marked active upon importing:")
        else:
            msg = _("The following user was previously marked inactive and is now marked active upon importing:")
        return mark_safe((msg) + " " + ExcelImporter._create_user_string(user))

    def _create_user_name_collision_warning(self, user_data, users_with_same_names):
        warningstring = _("An existing user has the same first and last name as a new user:")
        for user in users_with_same_names:
            warningstring += "<br /> - " + self._create_user_string(user) + _(" (existing)")
        warningstring += "<br /> - " + self._create_user_string(user_data) + _(" (new)")
        self.warnings[self.W_DUPL].append(mark_safe(warningstring))

    def check_user_data_sanity(self, test_run):
        for user_data in self.users.values():
            try:
                user = UserProfile.objects.get(email=user_data.email)
                if ((user.title is not None and user.title != user_data.title)
                        or user.first_name != user_data.first_name
                        or user.last_name != user_data.last_name):
                    self.warnings[self.W_NAME].append(self._create_user_data_mismatch_warning(user, user_data, test_run))
                if not user.is_active:
                    self.warnings[self.W_INACTIVE].append(self._create_user_inactive_warning(user, test_run))
            except UserProfile.DoesNotExist:
                pass

            users_same_name = (UserProfile.objects
                .filter(first_name=user_data.first_name, last_name=user_data.last_name)
                .exclude(email=user_data.email)
                .all())
            if len(users_same_name) > 0:
                self._create_user_name_collision_warning(user_data, users_same_name)


class EnrollmentImporter(ExcelImporter):
    # extension of ExcelImporter.warnings keys
    W_DEGREE = 'degree'
    W_MANY = 'too_many_enrollments'

    def __init__(self):
        super().__init__()
        # this is a dictionary to not let this become O(n^2)
        self.evaluations = {}
        self.enrollments = []
        self.names_de = set()

    @staticmethod
    def read_one_enrollment(data):
        student_data = UserData(first_name=data[2], last_name=data[1], email=data[3], title='', is_responsible=False)
        responsible_data = UserData(first_name=data[10], last_name=data[9], title=data[8], email=data[11], is_responsible=True)
        evaluation_data = EvaluationData(name_de=data[6], name_en=data[7], type_name=data[4], is_graded=data[5], degree_names=data[0],
                responsible_email=responsible_data.email)
        return (student_data, responsible_data, evaluation_data)

    def process_evaluation(self, evaluation_data, sheet, row):
        evaluation_id = evaluation_data.name_en
        if evaluation_id not in self.evaluations:
            if evaluation_data.name_de in self.names_de:
                self.errors.append(_('Sheet "{}", row {}: The German name for course "{}" already exists for another course.').format(sheet, row + 1, evaluation_data.name_en))
            else:
                self.evaluations[evaluation_id] = evaluation_data
                self.names_de.add(evaluation_data.name_de)
        else:
            if (set(evaluation_data.degree_names) != set(self.evaluations[evaluation_id].degree_names)
                    and evaluation_data.name_de == self.evaluations[evaluation_id].name_de
                    and evaluation_data.name_en == self.evaluations[evaluation_id].name_en
                    and evaluation_data.type_name == self.evaluations[evaluation_id].type_name
                    and evaluation_data.is_graded == self.evaluations[evaluation_id].is_graded
                    and evaluation_data.responsible_email == self.evaluations[evaluation_id].responsible_email):
                self.warnings[self.W_DEGREE].append(
                    _('Sheet "{}", row {}: The course\'s "{}" degree differs from it\'s degree in a previous row. Both degrees have been set for the course.')
                    .format(sheet, row + 1, evaluation_data.name_en)
                )
                self.evaluations[evaluation_id].degree_names.extend(evaluation_data.degree_names)
            elif evaluation_data != self.evaluations[evaluation_id]:
                self.errors.append(_('Sheet "{}", row {}: The course\'s "{}" data differs from it\'s data in a previous row.').format(sheet, row + 1, evaluation_data.name_en))

    def consolidate_enrollment_data(self):
        for (sheet, row), (student_data, responsible_data, evaluation_data) in self.associations.items():
            self.process_user(student_data, sheet, row)
            self.process_user(responsible_data, sheet, row)
            self.process_evaluation(evaluation_data, sheet, row)
            self.enrollments.append((evaluation_data, student_data))

    def check_evaluation_data_correctness(self, semester):
        for evaluation_data in self.evaluations.values():
            if Course.objects.filter(semester=semester, name_en=evaluation_data.name_en).exists():
                self.errors.append(_("Course {} does already exist in this semester.").format(evaluation_data.name_en))
            if Course.objects.filter(semester=semester, name_de=evaluation_data.name_de).exists():
                self.errors.append(_("Course {} does already exist in this semester.").format(evaluation_data.name_de))

        degree_names = set()
        for evaluation_data in self.evaluations.values():
            degree_names.update(evaluation_data.degree_names)
        for degree_name in degree_names:
            if not Degree.objects.filter(name_de=degree_name).exists():
                self.errors.append(_("Error: The degree \"{}\" does not exist yet. Please manually create it first.").format(degree_name))

        course_type_names = set(evaluation_data.type_name for evaluation_data in self.evaluations.values())
        for course_type_name in course_type_names:
            if not CourseType.objects.filter(name_de=course_type_name).exists():
                self.errors.append(_("Error: The course type \"{}\" does not exist yet. Please manually create it first.").format(course_type_name))

    def process_graded_column(self):
        for evaluation_data in self.evaluations.values():
            if evaluation_data.is_graded == settings.IMPORTER_GRADED_YES:
                evaluation_data.is_graded = True
            elif evaluation_data.is_graded == settings.IMPORTER_GRADED_NO:
                evaluation_data.is_graded = False
            else:
                self.errors.append(_('"is_graded" of course {} is {}, but must be {} or {}').format(
                    evaluation_data.name_en, evaluation_data.is_graded, settings.IMPORTER_GRADED_YES, settings.IMPORTER_GRADED_NO))
                evaluation_data.is_graded = True

    def check_enrollment_data_sanity(self):
        enrollments_per_user = defaultdict(list)
        for enrollment in self.enrollments:
            index = enrollment[1].email
            enrollments_per_user[index].append(enrollment)
        for email, enrollments in enrollments_per_user.items():
            if len(enrollments) > settings.IMPORTER_MAX_ENROLLMENTS:
                self.warnings[self.W_MANY].append(_("Warning: User {} has {} enrollments, which is a lot.").format(email, len(enrollments)))

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

        msg = _("Successfully created {} courses/evaluations, {} students and {} contributors:").format(
            len(self.evaluations), len(students_created), len(responsibles_created))
        msg += create_user_list_string_for_message(students_created + responsibles_created)
        self.success_messages.append(mark_safe(msg))

    def create_test_success_messages(self):
        filtered_users = [user_data for user_data in self.users.values() if not user_data.user_already_exists()]

        self.success_messages.append(_("The test run showed no errors. No data was imported yet."))
        msg = _("The import run will create {} courses/evaluations and {} users:").format(len(self.evaluations), len(filtered_users))
        msg += create_user_list_string_for_message(filtered_users)
        self.success_messages.append(mark_safe(msg))

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
                importer.errors.append(_("The input data is malformed. No data was imported."))
                return importer.success_messages, importer.warnings, importer.errors

            importer.for_each_row_in_excel_file_do(importer.read_one_enrollment)
            importer.consolidate_enrollment_data()
            importer.process_graded_column()
            importer.check_user_data_correctness()
            importer.check_evaluation_data_correctness(semester)
            importer.check_enrollment_data_sanity()
            importer.check_user_data_sanity(test_run)

            if importer.errors:
                importer.errors.append(_("Errors occurred while parsing the input data. No data was imported."))
            elif test_run:
                importer.create_test_success_messages()
            else:
                importer.write_enrollments_to_db(semester, vote_start_datetime, vote_end_date)

        except Exception as e:  # pylint: disable=broad-except
            importer.errors.append(_("Import finally aborted after exception: '%s'" % e))
            if settings.DEBUG:
                # re-raise error for further introspection if in debug mode
                raise

        return importer.success_messages, importer.warnings, importer.errors


class UserImporter(ExcelImporter):
    @staticmethod
    def read_one_user(data):
        user_data = UserData(title=data[0], first_name=data[1], last_name=data[2], email=data[3], is_responsible=False)
        return user_data

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
            for (sheet, row), (user_data) in self.associations.items():
                try:
                    user, created = user_data.store_in_database()
                    new_participants.append(user)
                    if created:
                        created_users.append(user)

                except Exception as e:
                    self.errors.append(_("A problem occured while writing the entries to the database."
                                         " The original data location was row %(row)d of sheet '%(sheet)s'."
                                         " The error message has been: '%(error)s'") % dict(row=row + 1, sheet=sheet, error=e))
                    raise

        msg = _("Successfully created {} users:").format(len(created_users))
        msg += create_user_list_string_for_message(created_users)
        self.success_messages.append(mark_safe(msg))
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
        msg = _("The import run will create {} users:").format(len(filtered_users))
        msg += create_user_list_string_for_message(filtered_users)
        self.success_messages.append(mark_safe(msg))

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
                importer.errors.append(_("The input data is malformed. No data was imported."))
                return [], importer.success_messages, importer.warnings, importer.errors

            importer.for_each_row_in_excel_file_do(importer.read_one_user)
            importer.consolidate_user_data()
            importer.check_user_data_correctness()
            importer.check_user_data_sanity(test_run)

            if importer.errors:
                importer.errors.append(_("Errors occurred while parsing the input data. No data was imported."))
                return [], importer.success_messages, importer.warnings, importer.errors
            if test_run:
                importer.create_test_success_messages()
                return importer.get_user_profile_list(), importer.success_messages, importer.warnings, importer.errors

            return importer.save_users_to_db(), importer.success_messages, importer.warnings, importer.errors

        except Exception as e:  # pylint: disable=broad-except
            importer.errors.append(_("Import finally aborted after exception: '%s'" % e))
            if settings.DEBUG:
                # re-raise error for further introspection if in debug mode
                raise


class PersonImporter:
    def __init__(self):
        self.success_messages = []
        self.warnings = defaultdict(list)
        self.errors = []

    def process_participants(self, evaluation, test_run, user_list):
        evaluation_participants = evaluation.participants.all()
        already_related = [user for user in user_list if user in evaluation_participants]
        users_to_add = [user for user in user_list if user not in evaluation_participants]

        if already_related:
            msg = _("The following {} users are already participants in evaluation {}:").format(len(already_related), evaluation.name)
            msg += create_user_list_string_for_message(already_related)
            self.warnings[ExcelImporter.W_GENERAL].append(mark_safe(msg))

        if not test_run:
            evaluation.participants.add(*users_to_add)
            msg = _("{} participants added to the evaluation {}:").format(len(users_to_add), evaluation.name)
        else:
            msg = _("{} participants would be added to the evaluation {}:").format(len(users_to_add), evaluation.name)
        msg += create_user_list_string_for_message(users_to_add)

        self.success_messages.append(mark_safe(msg))

    def process_contributors(self, evaluation, test_run, user_list):
        already_related_contributions = Contribution.objects.filter(evaluation=evaluation, contributor__in=user_list).all()
        already_related = [contribution.contributor for contribution in already_related_contributions]
        if already_related:
            msg = _("The following {} users are already contributing to evaluation {}:").format(len(already_related), evaluation.name)
            msg += create_user_list_string_for_message(already_related)
            self.warnings[ExcelImporter.W_GENERAL].append(mark_safe(msg))

        # since the user profiles are not necessarily saved to the database, they are not guaranteed to have a pk yet which
        # makes anything relying on hashes unusable here (for a faster list difference)
        users_to_add = [user for user in user_list if user not in already_related]

        if not test_run:
            for user in users_to_add:
                order = Contribution.objects.filter(evaluation=evaluation).count()
                Contribution.objects.create(evaluation=evaluation, contributor=user, order=order)
            msg = _("{} contributors added to the evaluation {}:").format(len(users_to_add), evaluation.name)
        else:
            msg = _("{} contributors would be added to the evaluation {}:").format(len(users_to_add), evaluation.name)
        msg += create_user_list_string_for_message(users_to_add)

        self.success_messages.append(mark_safe(msg))

    @classmethod
    def process_file_content(cls, import_type, evaluation, test_run, file_content):
        importer = cls()

        # the user import also makes these users active
        user_list, importer.success_messages, importer.warnings, importer.errors = UserImporter.process(file_content, test_run)
        if import_type == 'participant':
            importer.process_participants(evaluation, test_run, user_list)
        else:  # import_type == 'contributor'
            importer.process_contributors(evaluation, test_run, user_list)

        return importer.success_messages, importer.warnings, importer.errors

    @classmethod
    def process_source_evaluation(cls, import_type, evaluation, test_run, source_evaluation):
        importer = cls()

        if import_type == 'participant':
            user_list = list(source_evaluation.participants.all())
            importer.process_participants(evaluation, test_run, user_list)
        else:  # import_type == 'contributor'
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


# Dictionary to translate internal keys to UI strings.
WARNING_DESCRIPTIONS = {
    ExcelImporter.W_NAME: ugettext_lazy("Name mismatches"),
    ExcelImporter.W_INACTIVE: ugettext_lazy("Inactive users"),
    ExcelImporter.W_DUPL: ugettext_lazy("Possible duplicates"),
    ExcelImporter.W_GENERAL: ugettext_lazy("General warnings"),
    EnrollmentImporter.W_DEGREE: ugettext_lazy("Degree mismatches"),
    EnrollmentImporter.W_MANY: ugettext_lazy("Unusually high number of enrollments")
}
