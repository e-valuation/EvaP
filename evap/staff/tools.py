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
        errors.append('participant_in')
    if any(course in main_user.get_sorted_courses_voted_for() for course in other_user.get_sorted_courses_voted_for()):
        errors.append('voted_for')

    merged_user['contributions'] = Contribution.objects.filter(contributor__in=[main_user, other_user]).order_by('course__semester__created_at', 'course__name_de')
    merged_user['participant_in'] = Course.objects.filter(participants__in=[main_user, other_user]).order_by('semester__created_at', 'name_de')
    merged_user['voted_for'] = Course.objects.filter(voters__in=[main_user, other_user]).order_by('semester__created_at', 'name_de')

    if preview or errors:
        return (merged_user, errors)


    # update last_modified_user for course
    for course in Course.objects.filter(last_modified_user=other_user):
        course.last_modified_user = main_user
        course.save()

    # update last_modified_user for grade documents
    for grade_document in GradeDocument.objects.filter(last_modified_user=other_user):
        grade_document.last_modified_user = main_user
        grade_document.save()

    # add all groups of other user
    for group in merged_user['groups']:
        main_user.groups.add(group)

    # add all delegates and represented users from other user
    for delegate in merged_user['delegates']:
        main_user.delegates.add(delegate)
    for represented_user in merged_user['represented_users']:
        main_user.represented_users.add(represented_user)

    # add all cc users and cc'ing users from other user
    for cc_user in merged_user['cc_users']:
        main_user.cc_users.add(cc_user)
    for ccing_user in merged_user['ccing_users']:
        main_user.ccing_users.add(ccing_user)

    # add all participations and votings
    for course in merged_user['participant_in']:
        course.participants.add(main_user)
    for course in merged_user['voted_for']:
        course.voters.add(main_user)

    # add all contributions
    for contribution in merged_user['contributions']:
        contribution.contributor = main_user
        contribution.save()

    other_user.delete()

    main_user.username = merged_user['username']
    main_user.title = merged_user['title']
    main_user.first_name = merged_user['first_name']
    main_user.last_name = merged_user['last_name']
    main_user.email = merged_user['email']
    main_user.save()

    return (merged_user, errors)
