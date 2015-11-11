from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import ugettext as _
from django.utils.translation import get_language
from django.http import HttpResponse
from datetime import datetime
from operator import attrgetter

from evap.evaluation.auth import reward_user_required, staff_required
from evap.evaluation.models import Semester, Course

from evap.staff.views import semester_view

from evap.rewards.models import RewardPointGranting, RewardPointRedemption, RewardPointRedemptionEvent, SemesterActivation, NoPointsSelected, NotEnoughPoints
from evap.rewards.tools import save_redemptions, reward_points_of_user, can_user_use_reward_points
from evap.rewards.forms import RewardPointRedemptionEventForm
from evap.rewards.exporters import ExcelExporter

@reward_user_required
def index(request):
    if request.method == 'POST':
        redemptions = {}
        for key, value in request.POST.items():
            if(key.startswith('points-')):
                event_id = int(key.rpartition('-')[2])
                redemptions[event_id] = int(value)

        try:
            save_redemptions(request, redemptions)
            messages.success(request, _("You successfully redeemed your points."))
        except (NoPointsSelected, NotEnoughPoints) as error:
            messages.warning(request, error)

    total_points_available = reward_points_of_user(request.user)
    reward_point_grantings = RewardPointGranting.objects.filter(user_profile=request.user)
    reward_point_redemptions = RewardPointRedemption.objects.filter(user_profile=request.user)
    events = RewardPointRedemptionEvent.objects.filter(redeem_end_date__gte=datetime.now())
    events = sorted(events, key=lambda event: event.date)

    reward_point_actions=[]
    for granting in reward_point_grantings:
        reward_point_actions.append((granting.granting_time, _('Reward for') + ' ' + granting.semester.name, granting.value, ''))
    for redemption in reward_point_redemptions:
        reward_point_actions.append((redemption.redemption_time, redemption.event.name, '', redemption.value))

    reward_point_actions.sort(key=lambda action: action[0], reverse=True)

    template_data = dict(
            reward_point_actions=reward_point_actions,
            total_points_available=total_points_available,
            events=events,
            point_selection=[x for x in range(0,total_points_available+1)])
    return render(request, "rewards_index.html", template_data)


@staff_required
def semester_reward_points(request, semester_id):
    semester = get_object_or_404(Semester, id=semester_id)
    courses = Course.objects.filter(semester=semester)
    participants = set()
    for course in courses:
        for participant in course.participants.all():
            if can_user_use_reward_points(participant):
                participants.add(participant)
    participants = sorted(participants, key=attrgetter('last_name', 'first_name'))

    data = []
    for participant in participants:
        number_of_required_courses = Course.objects.filter(semester=semester, participants=participant, is_required_for_reward=True).count()
        number_of_required_courses_voted_for = Course.objects.filter(semester=semester, voters=participant, is_required_for_reward=True).count()
        number_of_optional_courses = Course.objects.filter(semester=semester, participants=participant, is_required_for_reward=False).count()
        number_of_optional_courses_voted_for = Course.objects.filter(semester=semester, voters=participant, is_required_for_reward=False).count()
        earned_reward_points = RewardPointGranting.objects.filter(semester=semester, user_profile=participant).exists()
        data.append((participant, number_of_required_courses_voted_for, number_of_required_courses,
            number_of_optional_courses_voted_for, number_of_optional_courses, earned_reward_points))

    template_data = dict(semester=semester, data=data, disable_breadcrumb_semester=False)
    return render(request, "rewards_semester_reward_points_view.html", template_data)


@staff_required
def reward_point_redemption_events(request):
    upcoming_events = RewardPointRedemptionEvent.objects.filter(redeem_end_date__gte=datetime.now()).order_by('date')
    past_events = RewardPointRedemptionEvent.objects.filter(redeem_end_date__lt=datetime.now()).order_by('-date')
    template_data = dict(upcoming_events=upcoming_events, past_events=past_events)
    return render(request, "rewards_reward_point_redemption_events.html", template_data)


@staff_required
def reward_point_redemption_event_create(request):
    event = RewardPointRedemptionEvent()
    form = RewardPointRedemptionEventForm(request.POST or None, instance=event)

    if form.is_valid():
        form.save()
        messages.success(request, _("Successfully created event."))
        return redirect('rewards:reward_point_redemption_events')
    else:
        return render(request, "rewards_reward_point_redemption_event_form.html", dict(form=form))


@staff_required
def reward_point_redemption_event_edit(request, event_id):
    event = get_object_or_404(RewardPointRedemptionEvent, id=event_id)
    form = RewardPointRedemptionEventForm(request.POST or None, instance=event)

    if form.is_valid():
        event = form.save()

        messages.success(request, _("Successfully updated event."))
        return redirect('rewards:reward_point_redemption_events')
    else:
        return render(request, "rewards_reward_point_redemption_event_form.html", dict(event=event, form=form))


@staff_required
def reward_point_redemption_event_delete(request, event_id):
    event = get_object_or_404(RewardPointRedemptionEvent, id=event_id)

    if event.can_delete:
        if request.method == 'POST':
            event.delete()
            return redirect('rewards:reward_point_redemption_events')
        else:
            return render(request, "rewards_reward_point_redemption_event_delete.html", dict(event=event))
    else:
        messages.warning(request, _("This event cannot be deleted because some users already redeemed points for it."))
        return redirect('rewards:reward_point_redemption_events')


@staff_required
def reward_point_redemption_event_export(request, event_id):
    event = get_object_or_404(RewardPointRedemptionEvent, id=event_id)

    filename = _("RewardPoints")+"-%s-%s-%s.xls" % (event.date, event.name, get_language())

    response = HttpResponse(content_type="application/vnd.ms-excel")
    response["Content-Disposition"] = "attachment; filename=\"%s\"" % filename

    ExcelExporter(event.redemptions_by_user()).export(response)

    return response


@staff_required
def semester_activation(request, semester_id, active):
    if active == 'on':
        active = True
    else:
        active = False

    try:
        activation = SemesterActivation.objects.filter(semester=Semester.objects.get(id=semester_id)).get()
        activation.is_active = active
    except SemesterActivation.DoesNotExist:
        activation = SemesterActivation(semester=Semester.objects.get(id=semester_id), is_active=active)
    activation.save()

    return semester_view(request=request, semester_id=semester_id)
