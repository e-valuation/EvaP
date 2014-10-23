from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render_to_response
from django.template import RequestContext
from django.utils.translation import ugettext as _
from datetime import datetime

from evap.evaluation.auth import reward_user_required

from evap.rewards.models import RewardPointGranting, RewardPointRedemption, RewardPointRedemptionEvent
from evap.rewards.tools import save_redemptions

@reward_user_required
def index(request):
    if request.method == 'POST':
        redemptions = {}
        for key, value in request.POST.iteritems():
            if(key.startswith('points-')):
                redemptions[int(key.rpartition('-')[2])] = int(value)
     
        if save_redemptions(request, redemptions):
            messages.success(request, _("You successfully redeemed your points."))
        else:
            messages.error(request, _("You don't have enough reward points."))            

    total_points_available = request.user.userprofile.reward_points
    reward_point_grantings = RewardPointGranting.objects.filter(user_profile=request.user.userprofile)
    reward_point_redemptions = RewardPointRedemption.objects.filter(user_profile=request.user.userprofile)
    events = RewardPointRedemptionEvent.objects.filter(redeem_end_date__gte=datetime.now())
    events = sorted(events, key=lambda event: event.date)

    reward_point_actions=[]
    for granting in reward_point_grantings:
        reward_point_actions.append((granting.granting_time, _('Reward for') + ' ' + granting.semester.name, granting.value, ''))
    for redemption in reward_point_redemptions:
        reward_point_actions.append((redemption.redemption_time, redemption.event.name, '', redemption.value))

    reward_point_actions = sorted(reward_point_actions, key=lambda action: action[0], reverse=True)

    return render_to_response(
        "rewards_index.html",
        dict(
            reward_point_actions=reward_point_actions,
            total_points_available=total_points_available,
            events=events,
            point_selection=[x for x in range(0,total_points_available+1)]
        ),
        context_instance=RequestContext(request))
