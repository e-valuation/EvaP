from django.conf.urls import url

from evap.results import views


app_name = "results"

urlpatterns = [
    url(r"^$", views.index, name="index"),
    url(r"semester/(\d+)$", views.semester_detail, name="semester_detail"),
    url(r"semester/(\d+)/course/(\d+)$", views.course_detail, name="course_detail"),
]
