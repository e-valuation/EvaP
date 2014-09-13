from django.conf.urls import url

from evap.contributor.views import *

urlpatterns = [
    url(r"^$", index),
    url(r"^profile$", profile_edit),
    url(r"^course/(\d+)$", course_view),
    url(r"^course/(\d+)/edit$", course_edit),
    url(r"^course/(\d+)/preview$", course_preview),
]
