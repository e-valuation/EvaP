from django.conf.urls import patterns, url

from evap.student.views import *

urlpatterns = [
    url(r"^$", index),
    url(r"^vote/(?P<course_id>\d+)$", vote),
]
