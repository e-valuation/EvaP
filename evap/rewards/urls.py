from django.conf.urls import url

from evap.rewards import views


app_name = "rewards"

urlpatterns = [
    url(r"^$", views.index, name="index"),

    url(r"^reward_point_redemption_events/$", views.reward_point_redemption_events, name="reward_point_redemption_events"),
    url(r"^reward_point_redemption_event/create$", views.reward_point_redemption_event_create, name="reward_point_redemption_event_create"),
    url(r"^reward_point_redemption_event/(\d+)/edit$", views.reward_point_redemption_event_edit, name="reward_point_redemption_event_edit"),
    url(r"^reward_point_redemption_event/(\d+)/export$", views.reward_point_redemption_event_export, name="reward_point_redemption_event_export"),
    url(r"^reward_point_redemption_event/delete$", views.reward_point_redemption_event_delete, name="reward_point_redemption_event_delete"),

    url(r"^reward_semester_activation/(\d+)/(\w+)$", views.semester_activation, name="semester_activation"),
]
