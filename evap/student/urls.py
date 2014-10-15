from django.conf.urls import url

from evap.student.views import *

urlpatterns = [
    url(r"^$", index),
    url(r"^vote/(?P<course_id>\d+)$", vote),
]
