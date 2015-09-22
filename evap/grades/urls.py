from django.conf.urls import url

from evap.grades.views import *

urlpatterns = [
    url(r"^$", index, name="index"),

    url(r"^download/(\d+)$", download_grades, name="download_grades"),
    url(r"^semester/(\d+)$", semester_view, name="semester_view"),
    url(r"^semester/(\d+)/course/(\d+)$", course_view, name="course_view"),
    url(r"^semester/(\d+)/course/(\d+)/upload$", upload_grades, name="upload_grades"),
    url(r"^semester/(\d+)/course/(\d+)/edit/(\d+)$", edit_grades, name="edit_grades"),
    url(r"^semester/(\d+)/course/(\d+)/delete/(\d+)$", delete_grades, name="delete_grades"),
    url(r"^semester/(\d+)/course/(\d+)/togglenogrades$", toggle_no_grades, name="toggle_no_grades"),
]
