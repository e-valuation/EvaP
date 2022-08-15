from datetime import datetime

from django.contrib import messages
from django.core.exceptions import BadRequest, SuspiciousOperation
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import get_language
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from evap.evaluation.auth import manager_required, reward_user_required
from evap.evaluation.models import Semester
from evap.evaluation.tools import AttachmentResponse, get_object_from_dict_pk_entry_or_logged_40x
from evap.rewards.exporters import RewardsExporter
from evap.rewards.forms import RewardPointRedemptionEventForm
from evap.rewards.models import (
    NoPointsSelected,
    NotEnoughPoints,
    RedemptionEventExpired,
    RewardPointGranting,
    RewardPointRedemption,
    RewardPointRedemptionEvent,
    SemesterActivation,
)
from evap.rewards.tools import (
    grant_eligible_reward_points_for_semester,
    redeemed_points_of_user,
    reward_points_of_user,
    save_redemptions,
)
from evap.staff.views import semester_view


def check_consistent_previous_redemption_counts(request):
    reward = request.POST.get("previous_reward_points")
    redeemed = request.POST.get("previous_redeemed_points")
    if reward is None or redeemed is None or not reward.isalnum() or not redeemed.isalnum():
        raise BadRequest("Invalid redeemed-points or left-points field in redemption request")
    return int(reward) == reward_points_of_user(request.user) and int(redeemed) == redeemed_points_of_user(request.user)


def redeem_reward_points(request):
    redemptions = {}
    try:
        for key, value in request.POST.items():
            if key.startswith("points-"):
                event_id = int(key.rpartition("-")[2])
                redemptions[event_id] = int(value)
    except ValueError as e:
        raise BadRequest from e

    try:
        save_redemptions(request, redemptions)
        messages.success(request, _("You successfully redeemed your points."))
    except (NoPointsSelected, NotEnoughPoints, RedemptionEventExpired) as error:
        messages.warning(request, error)


@reward_user_required
def index(request):
    status = 200
    if request.method == "POST":
        if check_consistent_previous_redemption_counts(request):
            redeem_reward_points(request)
        else:
            messages.warning(
                request,
                _(
                    "Probably your browser sent multiple redemption request. You can see all successful redemptions below."
                ),
            )
            status = 409
    total_points_available = reward_points_of_user(request.user)
    reward_point_grantings = RewardPointGranting.objects.filter(user_profile=request.user)
    reward_point_redemptions = RewardPointRedemption.objects.filter(user_profile=request.user)
    events = RewardPointRedemptionEvent.objects.filter(redeem_end_date__gte=datetime.now()).order_by("date")

    reward_point_actions = []
    for granting in reward_point_grantings:
        reward_point_actions.append(
            (granting.granting_time, _("Reward for") + " " + granting.semester.name, granting.value, "")
        )
    for redemption in reward_point_redemptions:
        reward_point_actions.append((redemption.redemption_time, redemption.event.name, "", redemption.value))

    reward_point_actions.sort(key=lambda action: action[0], reverse=True)

    template_data = dict(
        reward_point_actions=reward_point_actions,
        total_points_available=total_points_available,
        total_points_spent=sum(reward.value for reward in reward_point_redemptions),
        events=events,
        point_selection=range(0, total_points_available + 1),
    )
    return render(request, "rewards_index.html", template_data, status=status)


@manager_required
def reward_point_redemption_events(request):
    upcoming_events = RewardPointRedemptionEvent.objects.filter(redeem_end_date__gte=datetime.now()).order_by("date")
    past_events = RewardPointRedemptionEvent.objects.filter(redeem_end_date__lt=datetime.now()).order_by("-date")
    template_data = dict(upcoming_events=upcoming_events, past_events=past_events)
    return render(request, "rewards_reward_point_redemption_events.html", template_data)


@manager_required
def reward_point_redemption_event_create(request):
    event = RewardPointRedemptionEvent()
    form = RewardPointRedemptionEventForm(request.POST or None, instance=event)

    if form.is_valid():
        form.save()
        messages.success(request, _("Successfully created event."))
        return redirect("rewards:reward_point_redemption_events")

    return render(request, "rewards_reward_point_redemption_event_form.html", dict(form=form))


@manager_required
def reward_point_redemption_event_edit(request, event_id):
    event = get_object_or_404(RewardPointRedemptionEvent, id=event_id)
    form = RewardPointRedemptionEventForm(request.POST or None, instance=event)

    if form.is_valid():
        event = form.save()

        messages.success(request, _("Successfully updated event."))
        return redirect("rewards:reward_point_redemption_events")

    return render(request, "rewards_reward_point_redemption_event_form.html", dict(event=event, form=form))


@require_POST
@manager_required
def reward_point_redemption_event_delete(request):
    event = get_object_from_dict_pk_entry_or_logged_40x(RewardPointRedemptionEvent, request.POST, "event_id")

    if not event.can_delete:
        raise SuspiciousOperation("Deleting redemption event not allowed")
    event.delete()
    return HttpResponse()  # 200 OK


@manager_required
def reward_point_redemption_event_export(request, event_id):
    event = get_object_or_404(RewardPointRedemptionEvent, id=event_id)

    filename = _("RewardPoints") + f"-{event.date}-{event.name}-{get_language()}.xls"
    response = AttachmentResponse(filename, content_type="application/vnd.ms-excel")

    RewardsExporter().export(response, event.redemptions_by_user())

    return response


@manager_required
def semester_activation(request, semester_id, active):
    semester = get_object_or_404(Semester, id=semester_id)
    active = active == "on"

    SemesterActivation.objects.update_or_create(semester=semester, defaults={"is_active": active})
    if active:
        grant_eligible_reward_points_for_semester(request, semester)

    return semester_view(request=request, semester_id=semester_id)
