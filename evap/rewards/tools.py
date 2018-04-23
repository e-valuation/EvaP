from datetime import date

from django.conf import settings
from django.contrib import messages
from django.db import models, transaction
from django.db.models import Sum
from django.utils.translation import ugettext as _
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


def target_points(progress, thresholds=None):
    """
    How many points should a user have based on their evaluation progress?
    Progress should be 0.0 when none and 1.0 when all courses are evaluated.
    thresholds is a list of tuples of form (<progress threshold>, <target reward value>).
    If thresholds is None the REWARD_POINTS setting is used.
    """
    thresholds = thresholds if thresholds is not None else settings.REWARD_POINTS
    # Filter reward point targets we have enough progress for
    threshold_passed_reward_amount = map(lambda a: a[1], filter(lambda v: v[0] <= progress, thresholds))
    # Return the highest reward point target, or 0 if no thresholds were passed
    return max(threshold_passed_reward_amount, default=0)


def grant_reward_points(user, semester):
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

    voted_courses_count = required_courses.filter(voters=user).count()
    # full evaluation progress from 0.0 to 1.0
    progress = float(voted_courses_count) / float(required_courses.count())

    # How many points have been granted to this user this semester?
    granted_points = RewardPointGranting.objects.filter(user_profile=user, semester=semester).aggregate(Sum('value'))['value__sum'] or 0
    points_missing = target_points(progress) - granted_points

    if points_missing < 1:
        return False

    # grant missing reward points
    RewardPointGranting.objects.create(user_profile=user, semester=semester, value=points_missing)
    return True

# Signal handlers

@receiver(Course.course_evaluated)
def grant_reward_points_after_evaluate(sender, **kwargs):
    request = kwargs['request']
    semester = kwargs['semester']

    if grant_reward_points(request.user, semester):
        messages.success(request, _("You just have earned reward points for this semester because you evaluated all your courses. Thank you very much!"))

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
