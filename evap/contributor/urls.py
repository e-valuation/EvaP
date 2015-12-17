from django.conf.urls import url

from evap.contributor.views import index, settings_edit, course_view, course_edit, course_preview


app_name = "contributor"

urlpatterns = [
    url(r"^$", index, name="index"),
    url(r"^settings$", settings_edit, name="settings_edit"),
    url(r"^course/(\d+)$", course_view, name="course_view"),
    url(r"^course/(\d+)/edit$", course_edit, name="course_edit"),
    url(r"^course/(\d+)/preview$", course_preview, name="course_preview"),
]
