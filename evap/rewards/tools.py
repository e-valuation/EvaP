from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render_to_response
from django.template import RequestContext
from django.utils.translation import ugettext as _

from evap.evaluation.auth import login_required

from evap.rewards.models import RewardPointRedemption, RewardPointRedemptionEvent

@login_required
@transaction.atomic
def save_redemptions(request, redemptions):
    total_points_available = request.user.userprofile.reward_points
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
