from django.conf.urls import url

from evap.results.views import index, semester_detail, semester_export, course_detail

urlpatterns = [
    url(r"^$", index),
    url(r"semester/(\d+)$", semester_detail),
    url(r"semester/(\d+)/export$", semester_export),
    url(r"semester/(\d+)/course/(\d+)$", course_detail),
]
