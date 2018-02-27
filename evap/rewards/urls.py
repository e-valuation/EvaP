from django.urls import path

from evap.rewards import views


app_name = "rewards"

urlpatterns = [
    path("", views.index, name="index"),

    path("reward_point_redemption_events/", views.reward_point_redemption_events, name="reward_point_redemption_events"),
    path("reward_point_redemption_event/create", views.reward_point_redemption_event_create, name="reward_point_redemption_event_create"),
    path("reward_point_redemption_event/<int:event_id>/edit", views.reward_point_redemption_event_edit, name="reward_point_redemption_event_edit"),
    path("reward_point_redemption_event/<int:event_id>/export", views.reward_point_redemption_event_export, name="reward_point_redemption_event_export"),
    path("reward_point_redemption_event/delete", views.reward_point_redemption_event_delete, name="reward_point_redemption_event_delete"),

    path("reward_semester_activation/<int:semester_id>/<str:active>", views.semester_activation, name="semester_activation"),
]
