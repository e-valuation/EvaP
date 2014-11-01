from django.conf.urls import url

from evap.rewards.views import *

urlpatterns = [
    url(r"^$", index),

    url(r"^reward_point_redemption_events/$", reward_point_redemption_events),
    url(r"^reward_point_redemption_event/create$", reward_point_redemption_event_create),
    url(r"^reward_point_redemption_event/(\d+)/edit$", reward_point_redemption_event_edit),
    url(r"^reward_point_redemption_event/(\d+)/delete$", reward_point_redemption_event_delete),
    url(r"^reward_point_redemption_event/(\d+)/export$", reward_point_redemption_event_export),
]
