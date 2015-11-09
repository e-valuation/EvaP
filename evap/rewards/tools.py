from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.utils.translation import ugettext as _
from django.dispatch import receiver

from django.contrib.auth.decorators import login_required
from evap.evaluation.models import Course

from evap.rewards.models import RewardPointGranting, RewardPointRedemption, RewardPointRedemptionEvent, SemesterActivation, NoPointsSelected, NotEnoughPoints

@login_required
@transaction.atomic
def save_redemptions(request, redemptions):
    total_points_available = reward_points_of_user(request.user)
    total_points_redeemed = sum(redemptions.values())

    if total_points_redeemed <= 0:
        raise NoPointsSelected(_("You cannot redeem 0 points."))

    if total_points_redeemed > total_points_available:
        raise NotEnoughPoints(_("You don't have enough reward points."))

    for event_id in redemptions:
        if redemptions[event_id] > 0:
            redemption = RewardPointRedemption(
                user_profile=request.user,
                value=redemptions[event_id],
                event=RewardPointRedemptionEvent.objects.get(id=event_id)
            )
            redemption.save()

def can_user_use_reward_points(user):
    return not user.is_external and user.is_participant


def reward_points_of_user(user):
    reward_point_grantings = RewardPointGranting.objects.filter(user_profile=user)
    reward_point_redemptions = RewardPointRedemption.objects.filter(user_profile=user)

    count = 0
    for granting in reward_point_grantings:
        count += granting.value
    for redemption in reward_point_redemptions:
        count -= redemption.value

    return count


@receiver(Course.course_evaluated)
def grant_reward_points(sender, **kwargs):
    # grant reward points if all conditions are fulfilled

    request = kwargs['request']
    semester = kwargs['semester']
    if not can_user_use_reward_points(request.user):
        return
    # has the semester been activated for reward points?
    if not is_semester_activated(semester):
        return
    # does the user have at least one required course in this semester?
    required_courses = Course.objects.filter(participants=request.user, semester=semester, is_required_for_reward=True)
    if not required_courses.exists():
        return
    # does the user not participate in any more required courses in this semester?
    if required_courses.exclude(voters=request.user).exists():
        return
    # did the user not already get reward points for this semester?
    if not RewardPointGranting.objects.filter(user_profile=request.user, semester=semester):
        granting = RewardPointGranting(user_profile=request.user, semester=semester, value=settings.REWARD_POINTS_PER_SEMESTER)
        granting.save()
        messages.success(request, _("You just have earned reward points for this semester because you evaluated all your courses. Thank you very much!"))


def is_semester_activated(semester):
    try:
        activation = SemesterActivation.objects.get(semester=semester)
        return activation.is_active
    except SemesterActivation.DoesNotExist:
        return False
