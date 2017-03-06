from django.conf.urls import url

from evap.student.views import index, vote


app_name = "student"

urlpatterns = [
    url(r"^$", index, name="index"),
    url(r"^vote/(?P<course_id>\d+)$", vote, name="vote"),
]
