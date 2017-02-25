from django.conf.urls import url

from evap.grades import views


app_name = "grades"

urlpatterns = [
    url(r"^$", views.index, name="index"),

    url(r"^download/(\d+)$", views.download_grades, name="download_grades"),
    url(r"^semester/(\d+)$", views.semester_view, name="semester_view"),
    url(r"^semester/(\d+)/course/(\d+)$", views.course_view, name="course_view"),
    url(r"^semester/(\d+)/course/(\d+)/upload$", views.upload_grades, name="upload_grades"),
    url(r"^semester/(\d+)/course/(\d+)/edit/(\d+)$", views.edit_grades, name="edit_grades"),

    url(r"^delete_grades$", views.delete_grades, name="delete_grades"),
    url(r"^toggle_no_grades$", views.toggle_no_grades, name="toggle_no_grades"),

    url(r"^semester/(\d+)/grade_activation/(\w+)$", views.semester_grade_activation, name="semester_grade_activation"),
]
