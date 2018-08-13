from django.urls import path

from evap.contributor import views


app_name = "contributor"

urlpatterns = [
    path("", views.index, name="index"),
    path("settings", views.settings_edit, name="settings_edit"),
    path("course/<int:course_id>", views.course_view, name="course_view"),
    path("course/<int:course_id>/edit", views.course_edit, name="course_edit"),
    path("course/<int:course_id>/preview", views.course_preview, name="course_preview"),
    path("course/<int:course_id>/direct_delegate", views.direct_delegate_course_editing_to_user, name="course_direct_delegate")
]
