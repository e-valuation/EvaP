from django.urls import path

from evap.grades import views

app_name = "grades"

urlpatterns = [
    path("", views.IndexView.as_view(), name="index"),
    path("download/<int:grade_document_id>", views.download_grades, name="download_grades"),
    path("semester/<int:semester_id>", views.SemesterView.as_view(), name="semester_view"),
    path("course/<int:course_id>", views.CourseView.as_view(), name="course_view"),
    path("course/<int:course_id>/upload", views.upload_grades, name="upload_grades"),
    path("grade_document/<int:grade_document_id>/edit", views.edit_grades, name="edit_grades"),

    path("delete_grades", views.delete_grades, name="delete_grades"),
    path("set_no_grades", views.set_no_grades, name="set_no_grades"),
]
