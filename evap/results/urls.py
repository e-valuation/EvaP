from django.urls import path

from evap.results import views


app_name = "results"

urlpatterns = [
    path("", views.index, name="index"),
    path("semester/<int:semester_id>/course/<int:course_id>", views.course_detail, name="course_detail"),
]
