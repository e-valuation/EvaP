from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.utils.translation import ugettext as _
from django.core.exceptions import ValidationError

from evap.evaluation.models import Course, UserProfile, Degree, Contribution
from evap.evaluation.tools import is_external_email

import xlrd
from collections import OrderedDict, defaultdict

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
        user, created = UserProfile.objects.get_or_create(username=self.username)
        user.first_name = self.first_name
        user.last_name = self.last_name
        user.email = self.email
        user.title = self.title
        if user.needs_login_key:
            user.refresh_login_key()
        user.save()
        return created

    def validate(self):
        user = UserProfile()
        user.username = self.username
        user.first_name = self.first_name
        user.last_name = self.last_name
        user.email = self.email
        user.password = "asdf" # clean_fields needs that...
        user.clean_fields()


class CourseData(CommonEqualityMixin):
    """
        Holds information about a course, retrieved from the Excel file.
    """
    def __init__(self, name_de, name_en, type, degree_names, is_graded, responsible_email):
        self.name_de = name_de.strip()
        self.name_en = name_en.strip()
        self.type = type.strip()
        self.is_graded = is_graded.strip()
        self.responsible_email = responsible_email

        degree_names = degree_names.split(',')
        for degree_name in degree_names:
            degree_name = degree_name.strip()
        self.degree_names = degree_names

    def store_in_database(self, vote_start_date, vote_end_date, semester):
        course = Course(name_de=self.name_de,
                        name_en=self.name_en,
                        type=self.type,
                        is_graded=self.is_graded,
                        vote_start_date=vote_start_date,
                        vote_end_date=vote_end_date,
                        semester=semester)
        course.save()
        responsible_dbobj = UserProfile.objects.get(email=self.responsible_email)
        course.contributions.create(contributor=responsible_dbobj, course=course, responsible=True, can_edit=True, comment_visibility=Contribution.ALL_COMMENTS)
        for degree_name in self.degree_names:
            course.degrees.add(Degree.objects.get(name_de=degree_name))


class ExcelImporter(object):
    def __init__(self, request):
        self.associations = OrderedDict()
        self.request = request
        self.book = None
        self.skip_first_n_rows = 1 # first line contains the header
        self.errors = []
        self.warnings = []
        # this is a dictionary to not let this become O(n^2)
        self.users = {}

    def read_book(self, excel_file):
        self.book = xlrd.open_workbook(file_contents=excel_file.read())

    def check_column_count(self, expected_column_count):
        for sheet in self.book.sheets():
            if sheet.nrows <= self.skip_first_n_rows:
                continue
            if (sheet.ncols != expected_column_count):
                self.errors.append(_("Wrong number of columns in sheet '{}'. Expected: {}, actual: {}").format(sheet.name, expected_column_count, sheet.ncols))

    def for_each_row_in_excel_file_do(self, parse_row_function):
        for sheet in self.book.sheets():
            try:
                for row in range(self.skip_first_n_rows, sheet.nrows):
                    line_data = parse_row_function(sheet.row_values(row), sheet.name, row)
                    # store data objects together with the data source location for problem tracking
                    self.associations[(sheet.name, row)] = line_data

                messages.success(self.request, _("Successfully read sheet '%s'.") % sheet.name)
            except Exception:
                messages.warning(self.request, _("A problem occured while reading sheet '%s'.") % sheet.name)
                raise
        messages.success(self.request, _("Successfully read excel file."))

    def process_user(self, user_data, sheet, row):
        curr_email = user_data.email
        if curr_email == "":
            self.errors.append(_('Sheet "{}", row {}: Email address is missing.').format(sheet, row))
            return
        if curr_email not in self.users:
            self.users[curr_email] = user_data
        else:
            if not user_data == self.users[curr_email]:
                self.errors.append(_('Sheet "{}", row {}: The users\'s data (email: {}) differs from it\'s data in a previous row.').format(sheet, row, curr_email))

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
                return # to avoid duplicate errors with validate
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

            if not is_external_email(user_data.email) and len(user_data.username) > settings.INTERNAL_USERNAMES_MAX_LENGTH :
                self.errors.append(_('User {}: Username cannot be longer than {} characters for non-external users.').format(user_data.email, settings.INTERNAL_USERNAMES_MAX_LENGTH))
            if user_data.first_name == "":
                self.errors.append(_('User {}: First name is missing.').format(user_data.email))
            if user_data.last_name == "":
                self.errors.append(_('User {}: Last name is missing.').format(user_data.email))

    def check_user_data_sanity(self):
        for user_data in self.users.values():
            try:
                user = UserProfile.objects.get(username=user_data.username)
                if (user.email != user_data.email
                        or (user.title != None and user.title != user_data.title)
                        or user.first_name != user_data.first_name
                        or user.last_name != user_data.last_name):
                    self.warnings.append(_("The existing user would be overwritten with the following data:") +
                        "\n - {} ({} {} {}, {})".format(user.username, user.title or "", user.first_name, user.last_name, user.email) +
                        _(" (existing)") +
                        "\n - {} ({} {} {}, {})".format(user_data.username, user_data.title or "", user_data.first_name, user_data.last_name, user_data.email) +
                        _(" (new)"))
            except UserProfile.DoesNotExist:
                pass

            users_same_name = UserProfile.objects.filter(first_name=user_data.first_name, last_name=user_data.last_name).exclude(username=user_data.username).all()
            if len(users_same_name) > 0:
                warningstring = _("An existing user has the same first and last name as a new user:")
                for user in users_same_name:
                    warningstring += "\n - {} ({} {} {}, {})".format(user.username, user.title or "", user.first_name, user.last_name, user.email)
                    warningstring += _(" (existing)")
                warningstring += "\n - {} ({} {} {}, {})".format(user_data.username, user_data.title or "", user_data.first_name, user_data.last_name, user_data.email)
                warningstring += _(" (new)")
                self.warnings.append(warningstring)


    def show_errors_and_warnings(self):
        for error in self.errors:
            messages.error(self.request, error)
        for warning in self.warnings:
            messages.warning(self.request, warning)


class EnrollmentImporter(ExcelImporter):
    def __init__(self, request):
        super().__init__(request)
        # this is a dictionary to not let this become O(n^2)
        self.courses = {}
        self.enrollments = []
        self.maxEnrollments = 6

    def read_one_enrollment(self, data, sheet_name, row_id):
        student_data = UserData(username=data[3], first_name=data[2], last_name=data[1], email=data[4], title='', is_responsible=False)
        responsible_data = UserData(username=data[12], first_name=data[11], last_name=data[10], title=data[9], email=data[13], is_responsible=True)
        course_data = CourseData(name_de=data[7], name_en=data[8], type=data[5], is_graded=data[6], degree_names=data[0], responsible_email=responsible_data.email)
        return (student_data, responsible_data, course_data)

    def process_course(self, course_data, sheet, row):
        course_id = course_data.name_en
        if course_id not in self.courses:
            self.courses[course_id] = course_data
        else:
            if not course_data == self.courses[course_id]:
                self.errors.append(_('Sheet "{}", row {}: The course\'s "{}" data differs from it\'s data in a previous row.').format(sheet, row, course_data.name_en))

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

    def process_graded_column(self):
        for course_data in self.courses.values():
            if course_data.is_graded == settings.IMPORTER_GRADED_YES:
                course_data.is_graded = True
            elif course_data.is_graded == settings.IMPORTER_GRADED_NO:
                course_data.is_graded = False
            else:
                self.errors.append(_('"is_graded" of course {} is {}, but must be {} or {}').format(course_data.name_en, course_data.is_graded, settings.IMPORTER_GRADED_YES, settings.IMPORTER_GRADED_NO))
                course_data.is_graded = True

    def check_enrollment_data_sanity(self):
        enrollments_per_user = defaultdict(list)
        for enrollment in self.enrollments:
            enrollments_per_user[enrollment[1].username].append(enrollment)
        for username, enrollments in enrollments_per_user.items():
            if len(enrollments) > self.maxEnrollments:
                self.warnings.append(_("Warning: User {} has {} enrollments, which is a lot.").format(username, len(enrollments)))

    def write_enrollments_to_db(self, semester, vote_start_date, vote_end_date):
        students_created = 0
        responsibles_created = 0

        with transaction.atomic():
            for user_data in self.users.values():
                created = user_data.store_in_database()
                if created:
                    if user_data.is_responsible:
                        responsibles_created += 1
                    else:
                        students_created += 1
            for course_data in self.courses.values():
                course_data.store_in_database(vote_start_date, vote_end_date, semester)

            for course_data, student_data in self.enrollments:
                course = Course.objects.get(semester=semester, name_de=course_data.name_de)
                student = UserProfile.objects.get(email=student_data.email)
                course.participants.add(student)

        messages.success(self.request, _("Successfully created {} course(s), {} student(s) and {} contributor(s).").format(len(self.courses), students_created, responsibles_created))

    @classmethod
    def process(cls, request, excel_file, semester, vote_start_date, vote_end_date, test_run):
        """
            Entry point for the view.
        """
        try:
            importer = cls(request)
            importer.read_book(excel_file)
            importer.check_column_count(14)
            if importer.errors:
                importer.show_errors_and_warnings()
                messages.error(importer.request, _("The input data is malformed. No data was imported."))
                return
            importer.for_each_row_in_excel_file_do(importer.read_one_enrollment)
            importer.consolidate_enrollment_data()
            importer.generate_external_usernames_if_external()
            importer.process_graded_column()
            importer.check_user_data_correctness()
            importer.check_course_data_correctness(semester)
            importer.check_enrollment_data_sanity()
            importer.check_user_data_sanity()

            importer.show_errors_and_warnings()
            if importer.errors:
                messages.error(importer.request, _("Errors occurred while parsing the input data. No data was imported."))
                return
            if test_run:
                messages.info(importer.request, _("The test run showed no errors. No data was imported yet."))
            else:
                importer.write_enrollments_to_db(semester, vote_start_date, vote_end_date)
        except Exception as e:
            messages.error(request, _("Import finally aborted after exception: '%s'" % e))
            if settings.DEBUG:
                # re-raise error for further introspection if in debug mode
                raise


class UserImporter(ExcelImporter):
    def __init__(self, request):
        super().__init__(request)

    def read_one_user(self, data, sheet_name, row_id):
        user_data = UserData(username=data[0], title=data[1], first_name=data[2], last_name=data[3], email=data[4], is_responsible=False)
        return (user_data)

    def consolidate_user_data(self):
        for (sheet, row), (user_data) in self.associations.items():
            self.process_user(user_data, sheet, row)

    def save_users_to_db(self):
        """
            Stores the read data in the database. Errors might still
            occur because of the data already in the database.
        """
        with transaction.atomic():
            users_count = 0
            for (sheet, row), (user_data) in self.associations.items():
                try:
                    created = user_data.store_in_database()
                    if created:
                        users_count += 1

                except Exception as e:
                    messages.error(self.request, _("A problem occured while writing the entries to the database. The original data location was row %(row)d of sheet '%(sheet)s'. The error message has been: '%(error)s'") % dict(row=row, sheet=sheet, error=e))
                    raise
        messages.success(self.request, _("Successfully created %(users)d user(s).") % dict(users=users_count))

    @classmethod
    def process(cls, request, excel_file, test_run):
        """
            Entry point for the view.
        """
        try:
            importer = cls(request)
            importer.read_book(excel_file)
            importer.check_column_count(5)
            if importer.errors:
                importer.show_errors_and_warnings()
                messages.error(importer.request, _("The input data is malformed. No data was imported."))
                return
            importer.for_each_row_in_excel_file_do(importer.read_one_user)
            importer.consolidate_user_data()
            importer.generate_external_usernames_if_external()
            importer.check_user_data_correctness()
            importer.check_user_data_sanity()

            importer.show_errors_and_warnings()
            if importer.errors:
                messages.error(importer.request, _("Errors occurred while parsing the input data. No data was imported."))
                return
            if test_run:
                messages.info(importer.request, _("The test run showed no errors. No data was imported yet."))
            else:
                importer.save_users_to_db()
        except Exception as e:
            messages.error(request, _("Import finally aborted after exception: '%s'" % e))
            if settings.DEBUG:
                # re-raise error for further introspection if in debug mode
                raise
