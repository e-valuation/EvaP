from collections import OrderedDict, defaultdict
import xlrd

from django.conf import settings
from django.db import transaction
from django.utils.translation import ugettext as _
from django.utils.safestring import mark_safe
from django.core.exceptions import ValidationError

from evap.evaluation.models import Course, UserProfile, Degree, Contribution, CourseType
from evap.evaluation.tools import is_external_email


def create_user_list_string_for_message(users):
    msg = ""
    for user in users:
        msg += "<br>"
        msg += "{} {} ({})".format(user.first_name, user.last_name, user.username)
    return msg


# taken from https://stackoverflow.com/questions/390250/elegant-ways-to-support-equivalence-equality-in-python-classes
class CommonEqualityMixin(object):

    def __eq__(self, other):
        return (isinstance(other, self.__class__)
            and self.__dict__ == other.__dict__)


class UserData(CommonEqualityMixin):
    """
        Holds information about a user, retrieved from the Excel file.
    """
    def __init__(self, username, first_name, last_name, title, email, is_responsible):
        self.username = username.strip().lower()
        self.first_name = first_name.strip()
        self.last_name = last_name.strip()
        self.title = title.strip()
        self.email = email.strip().lower()
        self.is_responsible = is_responsible

    def store_in_database(self):
        user, created = UserProfile.objects.update_or_create(username=self.username,
                                                             defaults={
                                                                 'first_name': self.first_name,
                                                                 'last_name': self.last_name,
                                                                 'email': self.email,
                                                                 'title': self.title,
                                                                 'is_active': True})
        if user.needs_login_key:
            user.refresh_login_key()
        return user, created

    def user_already_exists(self):
        return UserProfile.objects.filter(username=self.username).exists()

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


class CourseData(CommonEqualityMixin):
    """
        Holds information about a course, retrieved from the Excel file.
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
        course = Course(name_de=self.name_de,
                        name_en=self.name_en,
                        type=course_type,
                        is_graded=self.is_graded,
                        vote_start_datetime=vote_start_datetime,
                        vote_end_date=vote_end_date,
                        semester=semester)
        course.save()
        # This is safe because the user's email address is checked before in the importer (see #953)
        responsible_dbobj = UserProfile.objects.get(email=self.responsible_email)
        course.contributions.create(contributor=responsible_dbobj, course=course, responsible=True, can_edit=True, comment_visibility=Contribution.ALL_COMMENTS)
        for degree_name in self.degree_names:
            course.degrees.add(Degree.objects.get(name_de=degree_name))


class ExcelImporter(object):
    W_NAME = 'name'
    W_EMAIL = 'email'
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
            self.errors.append(_('Sheet "{}", row {}: Email address is missing.').format(sheet, row+1))
            return
        if curr_email not in self.users:
            self.users[curr_email] = user_data
        else:
            if not user_data == self.users[curr_email]:
                self.errors.append(_('Sheet "{}", row {}: The users\'s data (email: {}) differs from it\'s data in a previous row.').format(sheet, row+1, curr_email))

    def generate_external_usernames_if_external(self):
        for user_data in self.users.values():
            if is_external_email(user_data.email):
                if user_data.username != "":
                    self.errors.append(_('User {}: Username must be empty for external users.').format(user_data.username))
                username = (user_data.first_name + '.' + user_data.last_name + '.ext').lower()
                for old, new in settings.USERNAME_REPLACEMENTS:
                    username = username.replace(old, new)
                user_data.username = username

    def check_user_data_correctness(self):
        username_to_user = {}
        for user_data in self.users.values():
            if user_data.username in username_to_user:
                self.errors.append(_('The imported data contains two email addresses with the same username '
                    + _("('{}' and '{}').")).format(user_data.email, username_to_user[user_data.username].email))
            username_to_user[user_data.username] = user_data

        for user_data in self.users.values():
            if not is_external_email(user_data.email) and user_data.username == "":
                self.errors.append(_('Emailaddress {}: Username cannot be empty for non-external users.').format(user_data.email))
                return  # to avoid duplicate errors with validate
            try:
                user_data.validate()
            except ValidationError as e:
                self.errors.append(_('User {}: Error when validating: {}').format(user_data.email, e))

            try:
                duplicate_email_user = UserProfile.objects.get(email=user_data.email)
                if duplicate_email_user.username != user_data.username:
                    self.errors.append(_('User {}, username {}: Another user with the same email address and a '
                        'different username ({}) already exists.').format(user_data.email, user_data.username, duplicate_email_user.username))
            except UserProfile.DoesNotExist:
                pass

            if not is_external_email(user_data.email) and len(user_data.username) > settings.INTERNAL_USERNAMES_MAX_LENGTH:
                self.errors.append(_('User {}: Username cannot be longer than {} characters for non-external users.').format(user_data.email, settings.INTERNAL_USERNAMES_MAX_LENGTH))
            if user_data.first_name == "":
                # This might be meaningless due to an empty email, but in that case, there will be
                # another error saying that the email address is missing for this user.
                self.errors.append(_('User {}: First name is missing.').format(user_data.email))
            if user_data.last_name == "":
                self.errors.append(_('User {}: Last name is missing.').format(user_data.email))

    @staticmethod
    def _create_user_string(user):
        return "{} ({} {} {}, {})".format(user.username, user.title or "", user.first_name, user.last_name, user.email or "")

    @staticmethod
    def _create_user_data_mismatch_warning(user, user_data):
        return (mark_safe(_("The existing user would be overwritten with the following data:") +
            "<br> - " + ExcelImporter._create_user_string(user) + _(" (existing)") +
            "<br> - " + ExcelImporter._create_user_string(user_data) + _(" (new)")))

    @staticmethod
    def _create_user_inactive_warning(user):
        return mark_safe(_("The following user is currently marked inactive and will be marked active upon importing:") + " "
                + ExcelImporter._create_user_string(user))

    def _create_user_name_collision_warning(self, user_data, users_with_same_names):
        warningstring = _("An existing user has the same first and last name as a new user:")
        for user in users_with_same_names:
            warningstring += "<br> - " + self._create_user_string(user) + _(" (existing)")
        warningstring += "<br> - " + self._create_user_string(user_data) + _(" (new)")
        self.warnings[self.W_DUPL].append(mark_safe(warningstring))

    def check_user_data_sanity(self):
        for user_data in self.users.values():
            try:
                user = UserProfile.objects.get(username=user_data.username)
                if user.email != user_data.email:
                    self.warnings[self.W_EMAIL].append(self._create_user_data_mismatch_warning(user, user_data))
                if ((user.title is not None and user.title != user_data.title)
                        or user.first_name != user_data.first_name
                        or user.last_name != user_data.last_name):
                    self.warnings[self.W_NAME].append(self._create_user_data_mismatch_warning(user, user_data))
                if not user.is_active:
                    self.warnings[self.W_INACTIVE].append(self._create_user_inactive_warning(user))
            except UserProfile.DoesNotExist:
                pass

            users_same_name = (UserProfile.objects
                .filter(first_name=user_data.first_name, last_name=user_data.last_name)
                .exclude(username=user_data.username)
                .all())
            if len(users_same_name) > 0:
                self._create_user_name_collision_warning(user_data, users_same_name)


class EnrollmentImporter(ExcelImporter):
    W_MANY = 'too many enrollments'  # extension of ExcelImporter.warnings keys

    def __init__(self):
        super().__init__()
        # this is a dictionary to not let this become O(n^2)
        self.courses = {}
        self.enrollments = []

    def read_one_enrollment(self, data):
        student_data = UserData(username=data[3], first_name=data[2], last_name=data[1], email=data[4], title='', is_responsible=False)
        responsible_data = UserData(username=data[12], first_name=data[11], last_name=data[10], title=data[9], email=data[13], is_responsible=True)
        course_data = CourseData(name_de=data[7], name_en=data[8], type_name=data[5], is_graded=data[6], degree_names=data[0], responsible_email=responsible_data.email)
        return (student_data, responsible_data, course_data)

    def process_course(self, course_data, sheet, row):
        course_id = course_data.name_en
        if course_id not in self.courses:
            self.courses[course_id] = course_data
        else:
            if not course_data == self.courses[course_id]:
                self.errors.append(_('Sheet "{}", row {}: The course\'s "{}" data differs from it\'s data in a previous row.').format(sheet, row+1, course_data.name_en))

    def consolidate_enrollment_data(self):
        for (sheet, row), (student_data, responsible_data, course_data) in self.associations.items():
            self.process_user(student_data, sheet, row)
            self.process_user(responsible_data, sheet, row)
            self.process_course(course_data, sheet, row)
            self.enrollments.append((course_data, student_data))

    def check_course_data_correctness(self, semester):
        for course_data in self.courses.values():
            already_exists = Course.objects.filter(semester=semester, name_de=course_data.name_de).exists()
            if already_exists:
                self.errors.append(_("Course {} does already exist in this semester.").format(course_data.name_en))

        degree_names = set()
        for course_data in self.courses.values():
            degree_names.update(course_data.degree_names)
        for degree_name in degree_names:
            if not Degree.objects.filter(name_de=degree_name).exists():
                self.errors.append(_("Error: The degree \"{}\" does not exist yet. Please manually create it first.").format(degree_name))

        course_type_names = set(course_data.type_name for course_data in self.courses.values())
        for course_type_name in course_type_names:
            if not CourseType.objects.filter(name_de=course_type_name).exists():
                self.errors.append(_("Error: The course type \"{}\" does not exist yet. Please manually create it first.").format(course_type_name))

    def process_graded_column(self):
        for course_data in self.courses.values():
            if course_data.is_graded == settings.IMPORTER_GRADED_YES:
                course_data.is_graded = True
            elif course_data.is_graded == settings.IMPORTER_GRADED_NO:
                course_data.is_graded = False
            else:
                self.errors.append(_('"is_graded" of course {} is {}, but must be {} or {}').format(
                    course_data.name_en, course_data.is_graded, settings.IMPORTER_GRADED_YES, settings.IMPORTER_GRADED_NO))
                course_data.is_graded = True

    def check_enrollment_data_sanity(self):
        enrollments_per_user = defaultdict(list)
        for enrollment in self.enrollments:
            # At this point the user should have a non-empty email address (see #953)
            index = enrollment[1].username if enrollment[1].username else enrollment[1].email
            enrollments_per_user[index].append(enrollment)
        for username, enrollments in enrollments_per_user.items():
            if len(enrollments) > settings.IMPORTER_MAX_ENROLLMENTS:
                self.warnings[self.W_MANY].append(_("Warning: User {} has {} enrollments, which is a lot.").format(username, len(enrollments)))

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
            for course_data in self.courses.values():
                course_data.store_in_database(vote_start_datetime, vote_end_date, semester)

            for course_data, student_data in self.enrollments:
                course = Course.objects.get(semester=semester, name_de=course_data.name_de)
                # This is safe because the user's email address is checked before in the importer (see #953)
                student = UserProfile.objects.get(email=student_data.email)
                course.participants.add(student)

        msg = _("Successfully created {} course(s), {} student(s) and {} contributor(s):").format(
            len(self.courses), len(students_created), len(responsibles_created))
        msg += create_user_list_string_for_message(students_created + responsibles_created)
        self.success_messages.append(mark_safe(msg))

    def create_test_success_messages(self):
        filtered_users = [user_data for user_data in self.users.values() if not user_data.user_already_exists()]

        self.success_messages.append(_("The test run showed no errors. No data was imported yet."))
        msg = _("The import run will create {} courses and {} users:").format(len(self.courses), len(filtered_users))
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

            importer.check_column_count(14)

            if importer.errors:
                importer.errors.append(_("The input data is malformed. No data was imported."))
                return importer.success_messages, importer.warnings, importer.errors

            importer.for_each_row_in_excel_file_do(importer.read_one_enrollment)
            importer.consolidate_enrollment_data()
            importer.generate_external_usernames_if_external()
            importer.process_graded_column()
            importer.check_user_data_correctness()
            importer.check_course_data_correctness(semester)
            importer.check_enrollment_data_sanity()
            importer.check_user_data_sanity()

            if importer.errors:
                importer.errors.append(_("Errors occurred while parsing the input data. No data was imported."))
            elif test_run:
                importer.create_test_success_messages()
            else:
                importer.write_enrollments_to_db(semester, vote_start_datetime, vote_end_date)

            return importer.success_messages, importer.warnings, importer.errors
        except Exception as e:
            importer.errors.append(_("Import finally aborted after exception: '%s'" % e))
            if settings.DEBUG:
                # re-raise error for further introspection if in debug mode
                raise


class UserImporter(ExcelImporter):
    def read_one_user(self, data):
        user_data = UserData(username=data[0], title=data[1], first_name=data[2], last_name=data[3], email=data[4], is_responsible=False)
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
                                         " The error message has been: '%(error)s'") % dict(row=row+1, sheet=sheet, error=e))
                    raise

        msg = _("Successfully created {} user(s):").format(len(created_users))
        msg += create_user_list_string_for_message(created_users)
        self.success_messages.append(mark_safe(msg))
        return new_participants

    def get_user_profile_list(self):
        new_participants = []
        for user_data in self.users.values():
            try:
                new_participant = UserProfile.objects.get(username=user_data.username)
            except UserProfile.DoesNotExist:
                new_participant = user_data.get_user_profile_object()
            new_participants.append(new_participant)
        return new_participants

    def create_test_success_messages(self):
        filtered_users = [user_data for user_data in self.users.values() if not user_data.user_already_exists()]

        self.success_messages.append(_("The test run showed no errors. No data was imported yet."))
        msg = _("The import run will create {} user(s):").format(len(filtered_users))
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

            importer.check_column_count(5)
            if importer.errors:
                importer.errors.append(_("The input data is malformed. No data was imported."))
                return [], importer.success_messages, importer.warnings, importer.errors

            importer.for_each_row_in_excel_file_do(importer.read_one_user)
            importer.consolidate_user_data()
            importer.generate_external_usernames_if_external()
            importer.check_user_data_correctness()
            importer.check_user_data_sanity()

            if importer.errors:
                importer.errors.append(_("Errors occurred while parsing the input data. No data was imported."))
                return [], importer.success_messages, importer.warnings, importer.errors
            if test_run:
                importer.create_test_success_messages()
                return importer.get_user_profile_list(), importer.success_messages, importer.warnings, importer.errors
            else:
                return importer.save_users_to_db(), importer.success_messages, importer.warnings, importer.errors

        except Exception as e:
            importer.errors.append(_("Import finally aborted after exception: '%s'" % e))
            if settings.DEBUG:
                # re-raise error for further introspection if in debug mode
                raise


class PersonImporter:
    def __init__(self):
        self.success_messages = []
        self.warnings = defaultdict(list)
        self.errors = []

    def process_participants(self, course, test_run, user_list):
        course_participants = course.participants.all()
        already_related = [user for user in user_list if user in course_participants]
        users_to_add = [user for user in user_list if user not in course_participants]

        if already_related:
            msg = _("The following {} user(s) are already course participants in course {}:").format(len(already_related), course.name)
            msg += create_user_list_string_for_message(already_related)
            self.warnings[ExcelImporter.W_GENERAL].append(mark_safe(msg))

        if not test_run:
            course.participants.add(*users_to_add)
            msg = _("{} participants added to the course {}:").format(len(users_to_add), course.name)
        else:
            msg = _("{} participants would be added to the course {}:").format(len(users_to_add), course.name)
        msg += create_user_list_string_for_message(users_to_add)

        self.success_messages.append(mark_safe(msg))

    def process_contributors(self, course, test_run, user_list):
        already_related_contributions = Contribution.objects.filter(course=course, contributor__in=user_list).all()
        already_related = [contribution.contributor for contribution in already_related_contributions]
        if already_related:
            msg = _("The following {} user(s) are already contributing to course {}:").format(len(already_related), course.name)
            msg += create_user_list_string_for_message(already_related)
            self.warnings[ExcelImporter.W_GENERAL].append(mark_safe(msg))

        # since the user profiles are not necessarily saved to the database, they are not guaranteed to have a pk yet which
        # makes anything relying on hashes unusable here (for a faster list difference)
        users_to_add = [user for user in user_list if user not in already_related]

        if not test_run:
            for user in users_to_add:
                order = Contribution.objects.filter(course=course).count()
                Contribution.objects.create(course=course, contributor=user, order=order)
            msg = _("{} contributors added to the course {}:").format(len(users_to_add), course.name)
        else:
            msg = _("{} contributors would be added to the course {}:").format(len(users_to_add), course.name)
        msg += create_user_list_string_for_message(users_to_add)

        self.success_messages.append(mark_safe(msg))

    @classmethod
    def process_file_content(cls, import_type, course, test_run, file_content):
        importer = cls()

        # the user import also makes these users active
        user_list, importer.success_messages, importer.warnings, importer.errors = UserImporter.process(file_content, test_run)
        if import_type == 'participant':
            importer.process_participants(course, test_run, user_list)
        else:  # import_type == 'contributor'
            importer.process_contributors(course, test_run, user_list)

        return importer.success_messages, importer.warnings, importer.errors

    @classmethod
    def process_source_course(cls, import_type, course, test_run, source_course):
        importer = cls()

        if import_type == 'participant':
            user_list = list(source_course.participants.all())
            importer.process_participants(course, test_run, user_list)
        else:  # import_type == 'contributor'
            user_list = list(UserProfile.objects.filter(contributions__course=source_course))
            importer.process_contributors(course, test_run, user_list)

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
    ExcelImporter.W_NAME: _("Name mismatches"),
    ExcelImporter.W_INACTIVE: _("Inactive users"),
    ExcelImporter.W_EMAIL: _("Email mismatches"),
    ExcelImporter.W_DUPL: _("Possible duplicates"),
    ExcelImporter.W_GENERAL: _("General warnings"),
    EnrollmentImporter.W_MANY: _("Unusually high number of enrollments")
}
