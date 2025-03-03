import csv
from datetime import date, datetime

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
from evap.evaluation.models import Semester, UserProfile
from evap.evaluation.tools import AttachmentResponse, get_object_from_dict_pk_entry_or_logged_40x
from evap.rewards.exporters import RewardsExporter
from evap.rewards.forms import RewardPointRedemptionEventForm, RewardPointRedemptionFormSet
from evap.rewards.models import (
    RewardPointGranting,
    RewardPointRedemption,
    RewardPointRedemptionEvent,
    SemesterActivation,
)
from evap.rewards.tools import grant_eligible_reward_points_for_semester, redeemed_points_of_user, reward_points_of_user


@reward_user_required
def index(request):
    status = 200

    events = RewardPointRedemptionEvent.objects.filter(redeem_end_date__gte=date.today()).order_by("date")

    # pylint: disable=unexpected-keyword-arg
    formset = RewardPointRedemptionFormSet(
        request.POST or None,
        initial=[{"event": e, "points": 0} for e in events],
        user=request.user,
    )
    if request.method == "POST":
        with formset.lock():
            try:
                previous_redeemed_points = int(request.POST["previous_redeemed_points"])
            except ValueError as e:
                raise BadRequest from e

            if previous_redeemed_points != redeemed_points_of_user(request.user):
                # Do formset validation here in order to do within the lock
                formset.is_valid()
                status = 409
                messages.error(
                    request,
                    _(
                        "It appears that your browser sent multiple redemption requests. You can see all successful redemptions below."
                    ),
                )
            elif formset.is_valid():
                formset.save()
                messages.success(request, _("You successfully redeemed your points."))
                return redirect("rewards:index")

    total_points_available = reward_points_of_user(request.user)
    reward_point_grantings = RewardPointGranting.objects.filter(user_profile=request.user)
    reward_point_redemptions = RewardPointRedemption.objects.filter(user_profile=request.user)

    granted_point_actions = [
        (granting.granting_time, _("Reward for") + " " + granting.semester.name, granting.value, "")
        for granting in reward_point_grantings
    ]
    redemption_point_actions = [
        (redemption.redemption_time, redemption.event.name, "", redemption.value)
        for redemption in reward_point_redemptions
    ]

    reward_point_actions = sorted(
        granted_point_actions + redemption_point_actions, key=lambda action: action[0], reverse=True
    )

    template_data = {
        "reward_point_actions": reward_point_actions,
        "total_points_available": total_points_available,
        "total_points_spent": sum(redemption.value for redemption in reward_point_redemptions),
        "events": events,
        "formset": formset,
        "forms": zip(formset, events, strict=True),
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

    RewardsExporter().export(response, event.users_with_redeemed_points())

    return response


@manager_required
def reward_points_export(request):
    filename = _("RewardPoints") + f"-{get_language()}.csv"
    response = AttachmentResponse(filename, content_type="text/csv")

    writer = csv.writer(response, delimiter=";", lineterminator="\n")
    writer.writerow([_("Email address"), _("Number of points")])
    profiles_with_points = (
        UserProfile.objects.annotate(
            points=Sum("reward_point_grantings__value", default=0) - Sum("reward_point_redemptions__value", default=0)
        )
        .filter(points__gt=0)
        .order_by("-points")
    )

    for profile in profiles_with_points.all():
        writer.writerow(
            [
                profile.email,
                profile.points,
            ]
        )

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
