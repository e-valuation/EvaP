from datetime import datetime

from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import BadRequest, SuspiciousOperation
from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils.translation import get_language
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, UpdateView

from evap.evaluation.auth import manager_required, reward_user_required
from evap.evaluation.models import Semester
from evap.evaluation.tools import AttachmentResponse, get_object_from_dict_pk_entry_or_logged_40x
from evap.rewards.exporters import RewardsExporter
from evap.rewards.forms import RewardPointRedemptionEventForm
from evap.rewards.models import (
    NoPointsSelectedError,
    NotEnoughPointsError,
    OutdatedRedemptionDataError,
    RedemptionEventExpiredError,
    RewardPointGranting,
    RewardPointRedemption,
    RewardPointRedemptionEvent,
    SemesterActivation,
)
from evap.rewards.tools import grant_eligible_reward_points_for_semester, reward_points_of_user, save_redemptions


def redeem_reward_points(request):
    redemptions = {}
    try:
        for key, value in request.POST.items():
            if key.startswith("points-"):
                event_id = int(key.rpartition("-")[2])
                redemptions[event_id] = int(value)
        previous_redeemed_points = int(request.POST["previous_redeemed_points"])
    except (ValueError, KeyError, TypeError) as e:
        raise BadRequest from e

    try:
        save_redemptions(request, redemptions, previous_redeemed_points)
        messages.success(request, _("You successfully redeemed your points."))
    except (
        NoPointsSelectedError,
        NotEnoughPointsError,
        RedemptionEventExpiredError,
        OutdatedRedemptionDataError,
    ) as error:
        status_code = 400
        if isinstance(error, NoPointsSelectedError):
            error_string = _("You cannot redeem 0 points.")
        elif isinstance(error, NotEnoughPointsError):
            error_string = _("You don't have enough reward points.")
        elif isinstance(error, RedemptionEventExpiredError):
            error_string = _("Sorry, the deadline for this event expired already.")
        elif isinstance(error, OutdatedRedemptionDataError):
            status_code = 409
            error_string = _(
                "It appears that your browser sent multiple redemption requests. You can see all successful redemptions below."
            )
        messages.error(request, error_string)
        return status_code
    return 200


@reward_user_required
def index(request):
    status = 200
    if request.method == "POST":
        status = redeem_reward_points(request)
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

    template_data = {
        "reward_point_actions": reward_point_actions,
        "total_points_available": total_points_available,
        "total_points_spent": sum(redemption.value for redemption in reward_point_redemptions),
        "events": events,
    }
    return render(request, "rewards_index.html", template_data, status=status)


@manager_required
def reward_point_redemption_events(request):
    upcoming_events = RewardPointRedemptionEvent.objects.filter(redeem_end_date__gte=datetime.now()).order_by("date")
    past_events = RewardPointRedemptionEvent.objects.filter(redeem_end_date__lt=datetime.now()).order_by("-date")
    total_points_granted = RewardPointGranting.objects.aggregate(Sum("value"))["value__sum"] or 0
    total_points_redeemed = RewardPointRedemption.objects.aggregate(Sum("value"))["value__sum"] or 0
    total_points_available = total_points_granted - total_points_redeemed
    template_data = {
        "upcoming_events": upcoming_events,
        "past_events": past_events,
        "total_points_available": total_points_available,
    }
    return render(request, "rewards_reward_point_redemption_events.html", template_data)


@manager_required
class RewardPointRedemptionEventCreateView(SuccessMessageMixin, CreateView):
    model = RewardPointRedemptionEvent
    form_class = RewardPointRedemptionEventForm
    template_name = "rewards_reward_point_redemption_event_form.html"
    success_url = reverse_lazy("rewards:reward_point_redemption_events")
    success_message = gettext_lazy("Successfully created event.")


@manager_required
class RewardPointRedemptionEventEditView(SuccessMessageMixin, UpdateView):
    model = RewardPointRedemptionEvent
    form_class = RewardPointRedemptionEventForm
    template_name = "rewards_reward_point_redemption_event_form.html"
    success_url = reverse_lazy("rewards:reward_point_redemption_events")
    success_message = gettext_lazy("Successfully updated event.")
    pk_url_kwarg = "event_id"
    context_object_name = "event"


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


@require_POST
@manager_required
def semester_activation_edit(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    status = request.POST.get("activation_status")
    if status == "on":
        active = True
    elif status == "off":
        active = False
    else:
        raise SuspiciousOperation("Invalid activation keyword")
    SemesterActivation.objects.update_or_create(semester=semester, defaults={"is_active": active})
    if active:
        grant_eligible_reward_points_for_semester(request, semester)
    return redirect("staff:semester_view", semester_id)
