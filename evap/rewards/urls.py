from django.conf.urls import url

from evap.rewards.views import *


app_name = "rewards"

urlpatterns = [
    url(r"^$", index, name="index"),

    url(r"^reward_point_redemption_events/$", reward_point_redemption_events, name="reward_point_redemption_events"),
    url(r"^reward_point_redemption_event/create$", reward_point_redemption_event_create, name="reward_point_redemption_event_create"),
    url(r"^reward_point_redemption_event/(\d+)/edit$", reward_point_redemption_event_edit, name="reward_point_redemption_event_edit"),
    url(r"^reward_point_redemption_event/(\d+)/delete$", reward_point_redemption_event_delete, name="reward_point_redemption_event_delete"),
    url(r"^reward_point_redemption_event/(\d+)/export$", reward_point_redemption_event_export, name="reward_point_redemption_event_export"),

    url(r"^reward_semester_activation/(\d+)/(\w+)$", semester_activation, name="semester_activation"),

    url(r"^semester/(\d+)/reward_points$", semester_reward_points, name="semester_reward_points"),
]
