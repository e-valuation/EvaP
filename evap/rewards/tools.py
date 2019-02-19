from datetime import date

from django.conf import settings
from django.contrib import messages
from django.db import models, transaction
from django.db.models import Sum
from django.utils.translation import ugettext as _
from django.utils.translation import ngettext
from django.dispatch import receiver
from django.contrib.auth.decorators import login_required

from evap.evaluation.models import Semester, Evaluation, UserProfile

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


def grant_reward_points_if_eligible(user, semester):
    if not can_user_use_reward_points(user):
        return None, False
    if not is_semester_activated(semester):
        return None, False
    # does the user have at least one required evaluation in this semester?
    required_evaluations = Evaluation.objects.filter(participants=user, course__semester=semester, is_rewarded=True)
    if not required_evaluations.exists():
        return None, False

    # How many points have been granted to this user vs how many should they have (this semester)
    granted_points = RewardPointGranting.objects.filter(user_profile=user, semester=semester).aggregate(Sum('value'))['value__sum'] or 0
    progress = float(required_evaluations.filter(voters=user).count()) / float(required_evaluations.count())
    target_points = max([points for threshold, points in settings.REWARD_POINTS if threshold <= progress], default=0)
    missing_points = target_points - granted_points

    if missing_points > 0:
        granting = RewardPointGranting.objects.create(user_profile=user, semester=semester, value=missing_points)
        return granting, progress >= 1.0
    return None, False


# Signal handlers

@receiver(Evaluation.evaluation_evaluated)
def grant_reward_points_after_evaluate(request, semester, **_kwargs):
    granting, completed_evaluation = grant_reward_points_if_eligible(request.user, semester)
    if granting:
        message = ngettext("You just earned {count} reward point for this semester.",
                           "You just earned {count} reward points for this semester.", granting.value).format(count=granting.value)

        if completed_evaluation:
            message += " " + _("You now received all possible reward points for this semester. Great!")
        elif Evaluation.objects.filter(participants=request.user, course__semester=semester, is_rewarded=True).exclude(state__in=['evaluated', 'reviewed', 'published'], voters=request.user).exists():
            # at least one evaluation exists that the user hasn't evaluated and is not past its evaluation period
            message += " " + _("We're looking forward to receiving feedback for your other evaluations as well.")

        messages.success(request, message)


@receiver(models.signals.m2m_changed, sender=Evaluation.participants.through)
def grant_reward_points_after_delete(instance, action, reverse, pk_set, **_kwargs):
    # if users do not need to evaluate anymore, they may have earned reward points
    if action == 'post_remove':
        grantings = []

        if reverse:
            # an evaluation got removed from a participant
            user = instance

            for semester in Semester.objects.filter(courses__evaluations__pk__in=pk_set):
                granting, __ = grant_reward_points_if_eligible(user, semester)
                if granting:
                    grantings = [granting]
        else:
            # a participant got removed from an evaluation
            evaluation = instance

            for user in UserProfile.objects.filter(pk__in=pk_set):
                granting, __ = grant_reward_points_if_eligible(user, evaluation.course.semester)
                if granting:
                    grantings.append(granting)

        if grantings:
            RewardPointGranting.granted_by_removal.send(sender=RewardPointGranting, grantings=grantings)
