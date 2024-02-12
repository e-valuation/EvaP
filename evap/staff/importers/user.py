import functools
import operator
from collections.abc import Iterable
from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils.html import escape, format_html
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from evap.evaluation.models import UserProfile
from evap.evaluation.tools import clean_email, unordered_groupby
from evap.staff.tools import append_user_list_if_not_empty, user_edit_link

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


@dataclass(eq=True, frozen=True)
class UserData:
    """Holds information about a user from the import file (may have to be created)"""

    first_name: str
    last_name: str
    title: str
    email: str

    @staticmethod
    def bulk_update_fields():
        """Fields passed to bulk_update when updating existing users with new UserData"""
        return ["first_name_given", "last_name", "title", "email", "is_active"]

    def __init__(self, first_name: str, last_name: str, title: str, email: str):
        # object.__setattr__ is needed to initialize instances of frozen dataclasses
        object.__setattr__(self, "first_name", first_name.strip())
        object.__setattr__(self, "last_name", last_name.strip())
        object.__setattr__(self, "title", title.strip())
        object.__setattr__(self, "email", clean_email(email))

    def apply_to_and_make_active(self, user_profile: UserProfile):
        """Intended to update existing UserProfile entries from the database. email is not touched"""
        user_profile.first_name_given = self.first_name
        user_profile.last_name = self.last_name
        user_profile.title = self.title
        user_profile.is_active = True

    def get_user_profile_object(self) -> UserProfile:
        """Create a new UserProfile object with the same data. Used for validation and bulk insertion"""
        obj = UserProfile(email=self.email)
        obj.set_unusable_password()
        self.apply_to_and_make_active(obj)
        return obj

    def validate(self) -> None:
        user = self.get_user_profile_object()

        # User might already exist in the database. In this case, we will later update the existing user.
        # blank password would trigger an error here although its fine for us.
        user.full_clean(validate_unique=False)


@dataclass
class UserParsedRow:
    """
    Representation of an User Row after parsing the data into the resulting data structures.
    """

    location: ExcelFileLocation

    user_data: UserData


@dataclass
class UserInputRow(InputRow):
    """Raw representation of a semantic user importer row, independent on the import format (xls, csv, ...)"""

    column_count = 4

    location: ExcelFileLocation

    # Cells in the order of appearance in a row of an import file
    title: str
    first_name: str
    last_name: str
    email: str

    def as_parsed_row(self) -> UserParsedRow:
        user_data = UserData(
            first_name=self.first_name,
            last_name=self.last_name,
            email=self.email,
            title=self.title,
        )

        return UserParsedRow(location=self.location, user_data=user_data)


class UserDataEmptyFieldsChecker(Checker):
    """Assert email, first name and last name are not empty"""

    def check_userdata(self, user_data: UserData, location: ExcelFileLocation):
        if user_data.email == "":
            self.importer_log.add_error(
                _("{location}: Email address is missing.").format(location=location),
                category=ImporterLogEntry.Category.USER,
            )

        if user_data.first_name == "":
            self.importer_log.add_error(
                _("{location}: User {email}: First name is missing.").format(location=location, email=user_data.email),
                category=ImporterLogEntry.Category.USER,
            )

        if user_data.last_name == "":
            self.importer_log.add_error(
                _("{location}: User {email}: Last name is missing.").format(location=location, email=user_data.email),
                category=ImporterLogEntry.Category.USER,
            )


class UserDataMismatchChecker(Checker):
    """Assert UserData matches previous occurrences in the import as well as the database"""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # maps user's mail to UserData instance where it was first seen to have O(1) lookup
        self.users: dict[str, UserData] = {}

        self.in_file_mismatch_tracker = FirstLocationAndCountTracker()

    def check_userdata(self, user_data: UserData, location: ExcelFileLocation):
        if user_data.email == "":
            # UserDataEmptyFieldsChecker will give an error for these, no need to spam additional errors
            return

        stored_user_data = self.users.setdefault(user_data.email, user_data)
        if user_data != stored_user_data:
            self.in_file_mismatch_tracker.add_location_for_key(location, user_data.email)

    def finalize(self) -> None:
        # Mismatches to older rows in the file
        for email, location in self.in_file_mismatch_tracker.aggregated_keys_and_location_strings():
            self.importer_log.add_error(
                _('{location}: The data of user "{email}" differs from their data in a previous row.').format(
                    location=location, email=email
                ),
                category=ImporterLogEntry.Category.USER,
            )

        # Mismatches to database entries
        user_query = UserProfile.objects.filter(email__in=self.users.keys())
        db_users_by_email = {db_user.email: db_user for db_user in user_query}

        for user_data in self.users.values():
            db_user = db_users_by_email.get(user_data.email)
            if db_user is None:
                continue

            if (
                (db_user.title is not None and db_user.title != user_data.title)
                or db_user.first_name_given != user_data.first_name
                or db_user.last_name != user_data.last_name
            ):
                self._add_user_data_mismatch_warning(db_user, user_data)

            if not db_user.is_active:
                self._add_user_inactive_warning(db_user)

        # Existing users with the same name
        same_name_filter = functools.reduce(
            operator.or_,
            (
                Q(first_name_given=user.first_name) & Q(last_name=user.last_name) & ~Q(email=user.email)
                for user in self.users.values()
            ),
            Q(pk=None),  # always false Q as initializer, required for empty self.users
        )

        db_users_by_name = unordered_groupby(
            ((db_user.first_name_given, db_user.last_name), db_user)
            for db_user in UserProfile.objects.filter(same_name_filter)
        )

        for user_data in self.users.values():
            existing_db_users = db_users_by_name.get((user_data.first_name, user_data.last_name), [])
            if existing_db_users:
                self._add_user_name_collision_warning(user_data, existing_db_users)

    def _add_user_data_mismatch_warning(self, user: UserProfile, user_data: UserData):
        if self.test_run:
            msg = escape(_("The existing user would be overwritten with the following data:"))
        else:
            msg = escape(_("The existing user was overwritten with the following data:"))

        msg = (
            msg
            + format_html("<br /> - {} ({})", self._create_user_string(user), _("existing"))
            + format_html("<br /> - {} ({})", self._create_user_string(user_data), _("import"))
        )

        self.importer_log.add_warning(msg, category=ImporterLogEntry.Category.NAME)

    def _add_user_inactive_warning(self, user: UserProfile):
        user_string = self._create_user_string(user)
        if self.test_run:
            msg = format_html(
                _("The following user is currently marked inactive and will be marked active upon importing: {}"),
                user_string,
            )
        else:
            msg = format_html(
                _("The following user was previously marked inactive and is now marked active upon importing: {}"),
                user_string,
            )

        self.importer_log.add_warning(msg, category=ImporterLogEntry.Category.INACTIVE)

    def _add_user_name_collision_warning(self, user_data: UserData, users_with_same_names: Iterable[UserProfile]):
        msg = escape(_("A user in the import file has the same first and last name as an existing user:"))
        for user in users_with_same_names:
            msg += format_html("<br /> - {} ({})", self._create_user_string(user), _("existing"))
        msg += format_html("<br /> - {} ({})", self._create_user_string(user_data), _("import"))

        self.importer_log.add_warning(msg, category=ImporterLogEntry.Category.DUPL)

    @staticmethod
    def _create_user_string(user: UserProfile | UserData):
        if isinstance(user, UserProfile):
            return format_html(
                "{} {} {}, {} [{}]",
                user.title or "",
                user.first_name_given or "(empty)",
                user.last_name or "(empty)",
                user.email or "(empty)",
                user_edit_link(user.pk),
            )

        return format_html("{} {} {}, {}", user.title or "", user.first_name, user.last_name, user.email or "")


class UserDataValidationChecker(Checker):
    """Run django validation against UserData instances"""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        # Only give one error per unique user_data.
        self.already_checked: set[UserData] = set()

    def check_userdata(self, user_data: UserData, _location: ExcelFileLocation):
        if user_data.email == "":
            # Should trigger another checker. We cannot meaningfully give an error message.
            return

        if user_data in self.already_checked:
            return
        self.already_checked.add(user_data)

        try:
            user_data.validate()
        except ValidationError as e:
            self.importer_log.add_error(
                _("User {user_email}: Error when validating: {error}").format(user_email=user_data.email, error=e),
                category=ImporterLogEntry.Category.USER,
            )


class DuplicateUserDataChecker(Checker):
    """Check for duplicate users"""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.first_location_by_user_data: dict[UserData, ExcelFileLocation] = {}

        self.tracker = FirstLocationAndCountTracker()

    def check_userdata(self, user_data: UserData, location: ExcelFileLocation):
        if user_data not in self.first_location_by_user_data:
            self.first_location_by_user_data[user_data] = location
            return

        first_location = self.first_location_by_user_data[user_data]
        self.tracker.add_location_for_key(location=location, key=first_location)

    def finalize(self) -> None:
        for first_location, location_string in self.tracker.aggregated_keys_and_location_strings():
            self.importer_log.add_warning(
                _("{location}: The duplicated row was ignored. It was first found at {first_location}.").format(
                    location=location_string,
                    first_location=first_location,
                ),
                category=ImporterLogEntry.Category.IGNORED,
            )


class UserDataAdapter(RowCheckerMixin):
    """Adapter to use Checkers for UserData with UserParsedRow"""

    def __init__(self, user_data_checker):
        self.user_data_checker = user_data_checker

    def check_row(self, row: UserParsedRow):
        self.user_data_checker.check_userdata(row.user_data, row.location)

    def finalize(self) -> None:
        self.user_data_checker.finalize()


@transaction.atomic
def import_users(excel_content: bytes, test_run: bool) -> tuple[list[UserProfile], ImporterLog]:
    importer_log = ImporterLog()

    with ConvertExceptionsToMessages(importer_log):
        excel_mapper = ExcelFileRowMapper(skip_first_n_rows=1, row_cls=UserInputRow, importer_log=importer_log)
        raw_rows = excel_mapper.map(excel_content)
        importer_log.raise_if_has_errors()

        rows = [raw_row.as_parsed_row() for raw_row in raw_rows]

        for checker in [
            UserDataAdapter(UserDataMismatchChecker(test_run, importer_log)),
            UserDataAdapter(DuplicateUserDataChecker(test_run, importer_log)),
            UserDataAdapter(UserDataEmptyFieldsChecker(test_run, importer_log)),
            UserDataAdapter(UserDataValidationChecker(test_run, importer_log)),
        ]:
            checker.check_rows(rows)
        importer_log.raise_if_has_errors()

        users = [row.user_data for row in rows]

        # Both will contain the updated data from the UserData instances, but the existing users are not yet saved.
        existing_user_profiles, new_user_profiles = get_user_profile_objects(users)
        resulting_user_profiles = existing_user_profiles + new_user_profiles

        if test_run:
            importer_log.add_success(_("The test run showed no errors. No data was imported yet."))
            msg = ngettext(
                "The import run will create 1 user",
                "The import run will create {user_count} users",
                len(new_user_profiles),
            ).format(user_count=len(new_user_profiles))
            msg = append_user_list_if_not_empty(msg, new_user_profiles)

            importer_log.add_success(msg)
        else:
            update_existing_and_create_new_user_profiles(existing_user_profiles, new_user_profiles)
            msg = ngettext(
                "Successfully created 1 user",
                "Successfully created {user_count} users",
                len(new_user_profiles),
            ).format(user_count=len(new_user_profiles))
            msg = append_user_list_if_not_empty(msg, new_user_profiles)

            importer_log.add_success(msg)

        return resulting_user_profiles, importer_log

    return [], importer_log


def get_user_profile_objects(users: Iterable[UserData]) -> tuple[list[UserProfile], list[UserProfile]]:
    user_data_by_email = {user_data.email: user_data for user_data in users}

    existing_objects = list(UserProfile.objects.filter(email__in=user_data_by_email.keys()))
    for obj in existing_objects:
        assert obj.email is not None  # for mypy
        user_data_by_email[obj.email].apply_to_and_make_active(obj)

    existing_emails = {obj.email for obj in existing_objects}
    new_objects = [
        user_data.get_user_profile_object()
        for user_data in user_data_by_email.values()
        if user_data.email not in existing_emails
    ]

    return existing_objects, new_objects


def update_existing_and_create_new_user_profiles(
    existing_user_profiles: Iterable[UserProfile],
    new_user_profiles: Iterable[UserProfile],
):
    for user_profile in existing_user_profiles:
        user_profile.save()

    for user_profile in new_user_profiles:
        user_profile.save()
