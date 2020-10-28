import os
from enum import Enum

from django.contrib import messages
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.core.cache.utils import make_template_fragment_key
from django.core.exceptions import SuspiciousOperation
from django.db import transaction
from django.db.models import Count
from django.conf import settings
from django.utils.html import format_html, format_html_join
from django.utils.translation import gettext_lazy as _

from evap.evaluation.models import Contribution, Course, Evaluation, TextAnswer, UserProfile
from evap.evaluation.models_logging import LogEntry
from evap.evaluation.tools import clean_email, is_external_email
from evap.grades.models import GradeDocument
from evap.results.tools import cache_results, STATES_WITH_RESULTS_CACHING


def forward_messages(request, success_messages, warnings):
    for message in success_messages:
        messages.success(request, message)

    for category in warnings:
        for warning in warnings[category]:
            messages.warning(request, warning)


class ImportType(Enum):
    User = 'user'
    Contributor = 'contributor'
    Participant = 'participant'
    Semester = 'semester'
    UserBulkUpdate = 'user_bulk_update'


def generate_import_filename(user_id, import_type):
    return os.path.join(settings.MEDIA_ROOT, 'temp_import_files', f"{user_id}.{import_type.value}.xls")


def save_import_file(excel_file, user_id, import_type):
    filename = generate_import_filename(user_id, import_type)
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, "wb") as file:
        for chunk in excel_file.chunks():
            file.write(chunk)
    excel_file.seek(0)


def delete_import_file(user_id, import_type):
    filename = generate_import_filename(user_id, import_type)
    try:
        os.remove(filename)
    except OSError:
        pass


def import_file_exists(user_id, import_type):
    filename = generate_import_filename(user_id, import_type)
    return os.path.isfile(filename)


def get_import_file_content_or_raise(user_id, import_type):
    filename = generate_import_filename(user_id, import_type)
    if not os.path.isfile(filename):
        raise SuspiciousOperation("No test run performed previously.")
    with open(filename, "rb") as file:
        return file.read()


def delete_navbar_cache_for_users(users):
    # delete navbar cache from base.html
    for user in users:
        key = make_template_fragment_key('navbar', [user.email, 'de'])
        cache.delete(key)
        key = make_template_fragment_key('navbar', [user.email, 'en'])
        cache.delete(key)


def create_user_list_html_string_for_message(users):
    return format_html_join("", "<br />{} {} ({})", ((user.first_name, user.last_name, user.email) for user in users))


def find_matching_internal_user_for_email(request, email):
    # for internal users only the part before the @ must be the same to match a user to an email
    matching_users = [
        user for user
        in UserProfile.objects.filter(email__startswith=email.split('@')[0] + '@').order_by('id')
        if not user.is_external
    ]

    if not matching_users:
        return None

    if len(matching_users) > 1:
        raise UserProfile.MultipleObjectsReturned(matching_users)

    return matching_users[0]


def bulk_update_users(request, user_file_content, test_run):
    # pylint: disable=too-many-branches,too-many-locals
    # user_file must have one user per line in the format "{username},{email}"
    imported_emails = {clean_email(line.decode().split(',')[1]) for line in user_file_content.splitlines()}

    emails_of_users_to_be_created = []
    users_to_be_updated = []
    skipped_external_emails_counter = 0

    for imported_email in imported_emails:
        if is_external_email(imported_email):
            skipped_external_emails_counter += 1
            continue
        try:
            matching_user = find_matching_internal_user_for_email(request, imported_email)
        except UserProfile.MultipleObjectsReturned as e:
            messages.error(
                request,
                format_html(
                    _('Multiple users match the email {}:{}'),
                    imported_email,
                    create_user_list_html_string_for_message(e.args[0])
                )
            )
            return False

        if not matching_user:
            emails_of_users_to_be_created.append(imported_email)
        elif matching_user.email != imported_email:
            users_to_be_updated.append((matching_user, imported_email))

    emails_of_non_obsolete_users = set(imported_emails) | {user.email for user, _ in users_to_be_updated}
    deletable_users, users_to_mark_inactive = [], []
    for user in UserProfile.objects.exclude(email__in=emails_of_non_obsolete_users):
        if user.can_be_deleted_by_manager:
            deletable_users.append(user)
        elif user.is_active and user.can_be_marked_inactive_by_manager:
            users_to_mark_inactive.append(user)

    messages.info(
        request,
        _('The uploaded text file contains {} internal and {} external users. The external users will be ignored. '
        '{} users are currently in the database. Of those, {} will be updated, {} will be deleted and {} will be '
        'marked inactive. {} new users will be created.')
        .format(len(imported_emails)-skipped_external_emails_counter, skipped_external_emails_counter,
            UserProfile.objects.count(), len(users_to_be_updated), len(deletable_users), len(users_to_mark_inactive),
            len(emails_of_users_to_be_created))
    )
    if users_to_be_updated:
        messages.info(request,
            format_html(
                _('Users to be updated are:{}'),
                format_html_join('', '<br />{} {} ({} > {})',
                    ((user.first_name, user.last_name, user.email, email) for user, email in users_to_be_updated)
                )
            )
        )
    if deletable_users:
        messages.info(request,
            format_html(
                _('Users to be deleted are:{}'),
                create_user_list_html_string_for_message(deletable_users)
            )
        )
    if users_to_mark_inactive:
        messages.info(request,
            format_html(
                _('Users to be marked inactive are:{}'),
                create_user_list_html_string_for_message(users_to_mark_inactive)
            )
        )
    if emails_of_users_to_be_created:
        messages.info(request,
            format_html(
                _('Users to be created are:{}'),
                format_html_join('', '<br />{}', ((email, ) for email in emails_of_users_to_be_created))
            )
        )

    with transaction.atomic():
        for user in deletable_users + users_to_mark_inactive:
            for message in remove_user_from_represented_and_ccing_users(user, deletable_users + users_to_mark_inactive, test_run):
                messages.warning(request, message)
        if test_run:
            messages.info(request, _('No data was changed in this test run.'))
        else:
            for user in deletable_users:
                user.delete()
            for user in users_to_mark_inactive:
                user.is_active = False
                user.save()
            for user, email in users_to_be_updated:
                user.email = email
                user.save()
            userprofiles_to_create = []
            for email in emails_of_users_to_be_created:
                userprofiles_to_create.append(UserProfile(email=email))
            UserProfile.objects.bulk_create(userprofiles_to_create)
            messages.success(request, _('Users have been successfully updated.'))

    return True


@transaction.atomic
def merge_users(main_user, other_user, preview=False):
    """Merges other_user into main_user"""
    # This is much stuff to do. However, splitting it up into subtasks doesn't make much sense.
    # pylint: disable=too-many-statements

    merged_user = dict()
    merged_user['is_active'] = main_user.is_active or other_user.is_active
    merged_user['title'] = main_user.title or other_user.title or ""
    merged_user['first_name'] = main_user.first_name or other_user.first_name or ""
    merged_user['last_name'] = main_user.last_name or other_user.last_name or ""
    merged_user['email'] = main_user.email or other_user.email or None

    merged_user['groups'] = Group.objects.filter(user__in=[main_user, other_user]).distinct()
    merged_user['is_superuser'] = main_user.is_superuser or other_user.is_superuser
    merged_user['is_proxy_user'] = main_user.is_proxy_user or other_user.is_proxy_user
    merged_user['delegates'] = UserProfile.objects.filter(represented_users__in=[main_user, other_user]).distinct()
    merged_user['represented_users'] = UserProfile.objects.filter(delegates__in=[main_user, other_user]).distinct()
    merged_user['cc_users'] = UserProfile.objects.filter(ccing_users__in=[main_user, other_user]).distinct()
    merged_user['ccing_users'] = UserProfile.objects.filter(cc_users__in=[main_user, other_user]).distinct()

    errors = []
    warnings = []
    courses_main_user_is_responsible_for = main_user.get_sorted_courses_responsible_for()
    if any(course in courses_main_user_is_responsible_for for course in other_user.get_sorted_courses_responsible_for()):
        errors.append('courses_responsible_for')
    if any(contribution.evaluation in [contribution.evaluation for contribution in main_user.get_sorted_contributions()] for contribution in other_user.get_sorted_contributions()):
        errors.append('contributions')
    if any(evaluation in main_user.get_sorted_evaluations_participating_in() for evaluation in other_user.get_sorted_evaluations_participating_in()):
        errors.append('evaluations_participating_in')
    if any(evaluation in main_user.get_sorted_evaluations_voted_for() for evaluation in other_user.get_sorted_evaluations_voted_for()):
        errors.append('evaluations_voted_for')

    if main_user.reward_point_grantings.all().exists() and other_user.reward_point_grantings.all().exists():
        warnings.append('rewards')

    merged_user['courses_responsible_for'] = Course.objects.filter(responsibles__in=[main_user, other_user]).order_by('semester__created_at', 'name_de')
    merged_user['contributions'] = Contribution.objects.filter(contributor__in=[main_user, other_user]).order_by('evaluation__course__semester__created_at', 'evaluation__name_de')
    merged_user['evaluations_participating_in'] = Evaluation.objects.filter(participants__in=[main_user, other_user]).order_by('course__semester__created_at', 'name_de')
    merged_user['evaluations_voted_for'] = Evaluation.objects.filter(voters__in=[main_user, other_user]).order_by('course__semester__created_at', 'name_de')

    merged_user['reward_point_grantings'] = main_user.reward_point_grantings.all() or other_user.reward_point_grantings.all()
    merged_user['reward_point_redemptions'] = main_user.reward_point_redemptions.all() or other_user.reward_point_redemptions.all()

    if preview or errors:
        return merged_user, errors, warnings

    # update responsibility
    for course in Course.objects.filter(responsibles__in=[other_user]):
        responsibles = list(course.responsibles.all())
        responsibles.remove(other_user)
        responsibles.append(main_user)
        course.responsibles.set(responsibles)

    GradeDocument.objects.filter(last_modified_user=other_user).update(last_modified_user=main_user)

    # email must not exist twice. other_user can't be deleted before contributions have been changed
    other_user.email = ""
    other_user.save()

    # update values for main user
    for key, value in merged_user.items():
        attr = getattr(main_user, key)
        if hasattr(attr, "set"):
            attr.set(value)  # use the 'set' method for e.g. many-to-many relations
        else:
            setattr(main_user, key, value)  # use direct assignment for everything else
    main_user.save()

    # delete rewards
    other_user.reward_point_grantings.all().delete()
    other_user.reward_point_redemptions.all().delete()

    # update logs
    LogEntry.objects.filter(user=other_user).update(user=main_user)

    # refresh results cache
    evaluations = Evaluation.objects.filter(
        contributions__contributor=main_user,
        state__in=STATES_WITH_RESULTS_CACHING
    ).distinct()
    for evaluation in evaluations:
        cache_results(evaluation)

    # delete other_user
    other_user.delete()

    return merged_user, errors, warnings


def find_next_unreviewed_evaluation(semester, excluded):
    return semester.evaluations.exclude(pk__in=excluded) \
        .exclude(state='published') \
        .exclude(can_publish_text_results=False) \
        .filter(contributions__textanswer_set__state=TextAnswer.State.NOT_REVIEWED) \
        .annotate(num_unreviewed_textanswers=Count("contributions__textanswer_set")) \
        .order_by('vote_end_date', '-num_unreviewed_textanswers').first()


def remove_user_from_represented_and_ccing_users(user, ignored_users=None, test_run=False):
    remove_messages = []
    ignored_users = ignored_users or []
    for represented_user in user.represented_users.exclude(id__in=[user.id for user in ignored_users]):
        if test_run:
            remove_messages.append(_("{} will be removed from the delegates of {}.").format(user.full_name, represented_user.full_name))
        else:
            represented_user.delegates.remove(user)
            remove_messages.append(_("Removed {} from the delegates of {}.").format(user.full_name, represented_user.full_name))
    for cc_user in user.ccing_users.exclude(id__in=[user.id for user in ignored_users]):
        if test_run:
            remove_messages.append(_("{} will be removed from the CC users of {}.").format(user.full_name, cc_user.full_name))
        else:
            cc_user.cc_users.remove(user)
            remove_messages.append(_("Removed {} from the CC users of {}.").format(user.full_name, cc_user.full_name))
    return remove_messages
