from django.conf.urls import url

from evap.student import views


app_name = "student"

urlpatterns = [
    url(r"^$", views.index, name="index"),
    url(r"^vote/(?P<course_id>\d+)$", views.vote, name="vote"),
]
