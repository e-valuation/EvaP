from django.conf.urls import url

from evap.results.views import index, semester_detail, course_detail


app_name = "results"

urlpatterns = [
    url(r"^$", index, name="index"),
    url(r"semester/(\d+)$", semester_detail, name="semester_detail"),
    url(r"semester/(\d+)/course/(\d+)$", course_detail, name="course_detail"),
]
