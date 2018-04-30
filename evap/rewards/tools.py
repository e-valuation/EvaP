from datetime import date

from django.conf import settings
from django.contrib import messages
from django.db import models, transaction
from django.db.models import Sum
from django.utils.translation import ugettext as _
from django.utils.translation import ngettext
from django.dispatch import receiver
from django.contrib.auth.decorators import login_required

from evap.evaluation.models import Semester, Course, UserProfile

from evap.rewards.models import RewardPointGranting, RewardPointRedemption, RewardPointRedemptionEvent, \
                                SemesterActivation, NoPointsSelected, NotEnoughPoints, RedemptionEventExpired


@login_required
@transaction.atomic
def save_redemptions(request, redemptions):
    # lock these rows to prevent race conditions
    list(request.user.reward_point_grantings.select_for_update())
    list(request.user.reward_point_redemptions.select_for_update())

    total_points_available = reward_points_of_user(request.user)
    total_points_redeemed = sum(redemptions.values())

    if total_points_redeemed <= 0:
        raise NoPointsSelected(_("You cannot redeem 0 points."))

    if total_points_redeemed > total_points_available:
        raise NotEnoughPoints(_("You don't have enough reward points."))

    for event_id in redemptions:
        if redemptions[event_id] > 0:
            event = RewardPointRedemptionEvent.objects.get(id=event_id)
            if event.redeem_end_date < date.today():
                raise RedemptionEventExpired(_("Sorry, the deadline for this event expired already."))

            RewardPointRedemption.objects.create(
                user_profile=request.user,
                value=redemptions[event_id],
                event=event
            )


def can_user_use_reward_points(user):
    return not user.is_external and user.is_participant


def reward_points_of_user(user):
    count = 0
    for granting in user.reward_point_grantings.all():
        count += granting.value
    for redemption in user.reward_point_redemptions.all():
        count -= redemption.value

    return count


def is_semester_activated(semester):
    return SemesterActivation.objects.filter(semester=semester, is_active=True).exists()


def grant_reward_points(user, semester):
    """
    Grant reward points if eligible.
    When points are granted, return tuple of amount of points granted and points remaining this semester, False otherwise.
    """
    # grant reward points if all conditions are fulfilled

    if not can_user_use_reward_points(user):
        return False
    # has the semester been activated for reward points?
    if not is_semester_activated(semester):
        return False
    # does the user have at least one required course in this semester?
    required_courses = Course.objects.filter(participants=user, semester=semester, is_required_for_reward=True)
    if not required_courses.exists():
        return False

    # How many points have been granted to this user vs how many should they have (this semester)
    granted_points = RewardPointGranting.objects.filter(user_profile=user, semester=semester).aggregate(Sum('value'))['value__sum'] or 0
    progress = float(required_courses.filter(voters=user).count()) / float(required_courses.count())
    target_points = max([points for threshold, points in settings.REWARD_POINTS if threshold <= progress], default=0)

    if target_points > granted_points:
        RewardPointGranting.objects.create(user_profile=user, semester=semester, value=target_points-granted_points)
        max_points = max([points for threshold, points in settings.REWARD_POINTS], default=0)
        return (target_points - granted_points, progress)
    return False

# Signal handlers

@receiver(Course.course_evaluated)
def grant_reward_points_after_evaluate(sender, **kwargs):
    request = kwargs['request']
    semester = kwargs['semester']

    result = grant_reward_points(request.user, semester)
    if result:
        granted, progress = result
        message = ngettext("You just earned {count} reward point for this semester.",
                           "You just earned {count} reward points for this semester.", granted).format(count=granted)

        if progress >= 1.0:
            message += " " + _("Thank you very much for evaluating all your courses.")
        elif Course.objects.filter(participants=request.user, semester=semester, is_required_for_reward=True, state="in_evaluation").exclude(voters=request.user).exists():
            message += " " + _("Please continue evaluating your courses.")

        messages.success(request, message)

@receiver(models.signals.m2m_changed, sender=Course.participants.through)
def grant_reward_points_after_delete(instance, action, reverse, pk_set, **kwargs):
    # if users do not need to evaluate a course anymore, they may have earned reward points
    if action == 'post_remove':
        affected = []

        if reverse:
            # a course got removed from a participant
            user = instance

            for semester in Semester.objects.filter(course__pk__in=pk_set):
                if grant_reward_points(user, semester):
                    affected = [user]
        else:
            # a participant got removed from a course
            course = instance

            for user in UserProfile.objects.filter(pk__in=pk_set):
                if grant_reward_points(user, course.semester):
                    affected.append(user)

        if affected:
            RewardPointGranting.granted_by_removal.send(sender=RewardPointGranting, users=affected)

