from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect
from django.core.cache import cache
from django.core.cache.utils import make_template_fragment_key
from django.db import transaction

from evap.evaluation.models import UserProfile, Course, Contribution
from evap.grades.models import GradeDocument
from django.contrib.auth.models import Group

import urllib.parse


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


@transaction.atomic
def merge_users(main_user, other_user, preview=False):
    """Merges other_user into main_user"""

    merged_user = dict()
    merged_user['username'] = main_user.username
    merged_user['title'] = main_user.title if main_user.title else other_user.title or ""
    merged_user['first_name'] = main_user.first_name if main_user.first_name else other_user.first_name or ""
    merged_user['last_name'] = main_user.last_name if main_user.last_name else other_user.last_name or ""
    merged_user['email'] = main_user.email if main_user.email else other_user.email or ""

    merged_user['groups'] = Group.objects.filter(user__in=[main_user, other_user]).distinct()
    merged_user['delegates'] = UserProfile.objects.filter(represented_users__in=[main_user, other_user]).distinct()
    merged_user['represented_users'] = UserProfile.objects.filter(delegates__in=[main_user, other_user]).distinct()
    merged_user['cc_users'] = UserProfile.objects.filter(ccing_users__in=[main_user, other_user]).distinct()
    merged_user['ccing_users'] = UserProfile.objects.filter(cc_users__in=[main_user, other_user]).distinct()

    errors = []
    if any(contribution.course in [contribution.course for contribution in main_user.get_sorted_contributions()] for contribution in other_user.get_sorted_contributions()):
        errors.append('contributions')
    if any(course in main_user.get_sorted_courses_participating_in() for course in other_user.get_sorted_courses_participating_in()):
        errors.append('courses_participating_in')
    if any(course in main_user.get_sorted_courses_voted_for() for course in other_user.get_sorted_courses_voted_for()):
        errors.append('courses_voted_for')

    merged_user['contributions'] = Contribution.objects.filter(contributor__in=[main_user, other_user]).order_by('course__semester__created_at', 'course__name_de')
    merged_user['courses_participating_in'] = Course.objects.filter(participants__in=[main_user, other_user]).order_by('semester__created_at', 'name_de')
    merged_user['courses_voted_for'] = Course.objects.filter(voters__in=[main_user, other_user]).order_by('semester__created_at', 'name_de')

    if preview or errors:
        return (merged_user, errors)


    # update last_modified_user for courses and grade documents
    Course.objects.filter(last_modified_user=other_user).update(last_modified_user=main_user)
    GradeDocument.objects.filter(last_modified_user=other_user).update(last_modified_user=main_user)

    # email must not exist twice
    other_user.email = ""
    other_user.save()

    # update values for main user
    for key, value in merged_user.items():
        setattr(main_user, key, value)
    main_user.save()

    # delete other user
    other_user.delete()

    return (merged_user, errors)
