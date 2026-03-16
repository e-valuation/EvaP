from django.urls import path

from evap.contributor import views

app_name = "contributor"

urlpatterns = [
    path("", views.index, name="index"),
    path("export", views.export, name="export"),
    path("evaluation/<int:evaluation_id>", views.evaluation_view, name="evaluation_view"),
    path("evaluation/<int:evaluation_id>/edit", views.evaluation_edit, name="evaluation_edit"),
    path("evaluation/<int:evaluation_id>/preview", views.evaluation_preview, name="evaluation_preview"),
    path("evaluation/<int:evaluation_id>/direct_delegation", views.evaluation_direct_delegation, name="evaluation_direct_delegation"),
    path("user_profiles/delegates/", views.DelegatesUserProfileSearchView.as_view(),
         name="fetch_delegates_user_profiles"),
    path("user_profiles/participants/", views.ParticipantsUserProfileSearchView.as_view(),
         name="fetch_participants_user_profiles"),
]
