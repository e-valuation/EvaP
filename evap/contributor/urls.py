from django.conf.urls import url

from evap.contributor import views


app_name = "contributor"

urlpatterns = [
    url(r"^$", views.index, name="index"),
    url(r"^settings$", views.settings_edit, name="settings_edit"),
    url(r"^course/(\d+)$", views.course_view, name="course_view"),
    url(r"^course/(\d+)/edit$", views.course_edit, name="course_edit"),
    url(r"^course/(\d+)/preview$", views.course_preview, name="course_preview"),
]
