from django.urls import path

from evap.contributor import views


app_name = "contributor"

urlpatterns = [
    path("", views.index, name="index"),
    path("settings", views.settings_edit, name="settings_edit"),
    path("export", views.export, name="export"),
    path("evaluation/<int:evaluation_id>", views.evaluation_view, name="evaluation_view"),
    path("evaluation/<int:evaluation_id>/edit", views.evaluation_edit, name="evaluation_edit"),
    path("evaluation/<int:evaluation_id>/preview", views.evaluation_preview, name="evaluation_preview"),
    path("evaluation/<int:evaluation_id>/direct_delegation", views.evaluation_direct_delegation, name="evaluation_direct_delegation")
]
