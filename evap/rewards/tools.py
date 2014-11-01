from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render_to_response
from django.template import RequestContext
from django.utils.translation import ugettext as _

from evap.evaluation.auth import login_required
from evap.evaluation.models import Course
from django.dispatch import receiver

from datetime import date

from evap.rewards.models import RewardPointGranting, RewardPointRedemption, RewardPointRedemptionEvent, SemesterActivation

@login_required
@transaction.atomic
def save_redemptions(request, redemptions):
    total_points_available = reward_points_of_user(request.user.userprofile)
    total = 0
    for event_id in redemptions:
        total += redemptions[event_id]

    if total <= total_points_available and total_points_available > 0:
        for event_id in redemptions:
            if redemptions[event_id] > 0:
                redemption = RewardPointRedemption(
                    user_profile=request.user.userprofile,
                    value=redemptions[event_id],
                    event=RewardPointRedemptionEvent.objects.get(id=event_id)
                )
                redemption.save()
        return True

    return False


def can_user_use_reward_points(userprofile):
    return not userprofile.is_external and userprofile.enrolled_in_courses


def reward_points_of_user(userprofile):
    reward_point_grantings = RewardPointGranting.objects.filter(user_profile=userprofile)
    reward_point_redemptions = RewardPointRedemption.objects.filter(user_profile=userprofile)
    
    count = 0
    for granting in reward_point_grantings:
        count += granting.value
    for redemption in reward_point_redemptions:
        count -= redemption.value

    return count


@receiver(Course.course_evaluated)
def grant_reward_points(sender, **kwargs):
    request = kwargs['request']
    semester = kwargs['semester']
    if can_user_use_reward_points(request.user.userprofile):
        # has the semester been activated for reward points?
        try:
            activation = SemesterActivation.objects.get(semester=semester)
        except SemesterActivation.DoesNotExist:
            return
        
        if activation.is_active:
            # does the user not participate in any more courses in this semester?
            if not Course.objects.filter(participants=request.user, semester=semester).exclude(voters=request.user).exists():
                # did the user not already get reward points for this semester?
                if not RewardPointGranting.objects.filter(user_profile=request.user.userprofile, semester=semester):
                    granting = RewardPointGranting(user_profile=request.user.userprofile, semester=semester, value=settings.REWARD_POINTS_PER_SEMESTER)
                    granting.save()
                    messages.success(request, _("You just have earned reward points for this semester because you evaluated all your courses. Thank you very much!"))
