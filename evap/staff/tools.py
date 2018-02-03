import urllib.parse
import os

from django.contrib import messages
from django.contrib.auth.models import Group
from django.urls import reverse
from django.http import HttpResponseRedirect
from django.core.cache import cache
from django.core.cache.utils import make_template_fragment_key
from django.core.exceptions import SuspiciousOperation, PermissionDenied
from django.db import transaction
from django.conf import settings
from django.utils.translation import ugettext_lazy as _
from django.utils.safestring import mark_safe

from evap.evaluation.models import UserProfile, Course, Contribution
from evap.grades.models import GradeDocument
from evap.results.tools import calculate_results


def get_parameter_from_url_or_session(request, parameter):
    result = request.GET.get(parameter, None)
    if result is None:  # if no parameter is given take session value
        result = request.session.get(parameter, False)  # defaults to False if no session value exists
    else:
        result = {'true': True, 'false': False}.get(result.lower())  # convert parameter to boolean
    request.session[parameter] = result  # store value for session
    return result


def raise_permission_denied_if_archived(archiveable):
    if archiveable.is_archived:
        raise PermissionDenied


def forward_messages(request, success_messages, warnings):
    for message in success_messages:
        messages.success(request, message)

    for category in warnings:
        for warning in warnings[category]:
            messages.warning(request, warning)


def generate_import_filename(user_id, import_type):
    return settings.MEDIA_ROOT + '/temp_import_files/' + str(user_id) + '.xls' + '.' + import_type


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


def custom_redirect(url_name, *args, **kwargs):
    url = reverse(url_name, args=args)
    params = urllib.parse.urlencode(kwargs)
    return HttpResponseRedirect(url + "?%s" % params)


def delete_navbar_cache():
    # delete navbar cache from base.html
    for user in UserProfile.objects.all():
        key = make_template_fragment_key('navbar', [user.username, 'de'])
        cache.delete(key)
        key = make_template_fragment_key('navbar', [user.username, 'en'])
        cache.delete(key)


def bulk_delete_users(request, username_file, test_run):
    usernames = [u.decode().strip() for u in username_file.readlines()]
    users = UserProfile.objects.exclude(username__in=usernames)
    deletable_users = [u for u in users if u.can_staff_delete]
    users_to_mark_inactive = [u for u in users if u.is_active and not u.can_staff_delete and u.can_staff_mark_inactive]

    messages.info(request, _('The uploaded text file contains {} usernames. {} other users have been found in the database. '
                           'Of those, {} will be deleted and {} will be marked inactive.')
                  .format(len(usernames), len(users), len(deletable_users), len(users_to_mark_inactive)))
    messages.info(request, mark_safe(_('Users to be deleted are:<br />{}')
                  .format('<br />'.join([u.username for u in deletable_users]))))
    messages.info(request, mark_safe(_('Users to be marked inactive are:<br />{}')
                  .format('<br />'.join([u.username for u in users_to_mark_inactive]))))

    if test_run:
        messages.info(request, _('No users were deleted or marked inactive in this test run.'))
    else:
        for user in deletable_users:
            user.delete()
        for user in users_to_mark_inactive:
            user.is_active = False
            user.save()

        messages.info(request, _('{} users have been deleted').format(len(deletable_users)))
        messages.info(request, _('{} users have been marked inactive').format(len(users_to_mark_inactive)))


@transaction.atomic
def merge_users(main_user, other_user, preview=False):
    """Merges other_user into main_user"""

    merged_user = dict()
    merged_user['username'] = main_user.username
    merged_user['is_active'] = main_user.is_active or other_user.is_active
    merged_user['title'] = main_user.title if main_user.title else other_user.title or ""
    merged_user['first_name'] = main_user.first_name if main_user.first_name else other_user.first_name or ""
    merged_user['last_name'] = main_user.last_name if main_user.last_name else other_user.last_name or ""
    merged_user['email'] = main_user.email if main_user.email else other_user.email or None

    merged_user['groups'] = Group.objects.filter(user__in=[main_user, other_user]).distinct()
    merged_user['is_superuser'] = main_user.is_superuser or other_user.is_superuser
    merged_user['delegates'] = UserProfile.objects.filter(represented_users__in=[main_user, other_user]).distinct()
    merged_user['represented_users'] = UserProfile.objects.filter(delegates__in=[main_user, other_user]).distinct()
    merged_user['cc_users'] = UserProfile.objects.filter(ccing_users__in=[main_user, other_user]).distinct()
    merged_user['ccing_users'] = UserProfile.objects.filter(cc_users__in=[main_user, other_user]).distinct()

    errors = []
    warnings = []
    if any(contribution.course in [contribution.course for contribution in main_user.get_sorted_contributions()] for contribution in other_user.get_sorted_contributions()):
        errors.append('contributions')
    if any(course in main_user.get_sorted_courses_participating_in() for course in other_user.get_sorted_courses_participating_in()):
        errors.append('courses_participating_in')
    if any(course in main_user.get_sorted_courses_voted_for() for course in other_user.get_sorted_courses_voted_for()):
        errors.append('courses_voted_for')

    if main_user.reward_point_grantings.all().exists() and other_user.reward_point_grantings.all().exists():
        warnings.append('rewards')

    merged_user['contributions'] = Contribution.objects.filter(contributor__in=[main_user, other_user]).order_by('course__semester__created_at', 'course__name_de')
    merged_user['courses_participating_in'] = Course.objects.filter(participants__in=[main_user, other_user]).order_by('semester__created_at', 'name_de')
    merged_user['courses_voted_for'] = Course.objects.filter(voters__in=[main_user, other_user]).order_by('semester__created_at', 'name_de')

    merged_user['reward_point_grantings'] = main_user.reward_point_grantings.all() if main_user.reward_point_grantings.all().exists() else other_user.reward_point_grantings.all()
    merged_user['reward_point_redemptions'] = main_user.reward_point_redemptions.all() if main_user.reward_point_redemptions.all().exists() else other_user.reward_point_redemptions.all()

    if preview or errors:
        return merged_user, errors, warnings

    # update last_modified_user for courses and grade documents
    Course.objects.filter(last_modified_user=other_user).update(last_modified_user=main_user)
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

    # refresh results cache
    for course in Course.objects.filter(contributions__contributor=main_user).distinct():
        calculate_results(course, force_recalculation=True)

    # delete other_user
    other_user.delete()

    return merged_user, errors, warnings
