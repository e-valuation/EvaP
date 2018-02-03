from django.urls import path

from evap.grades import views


app_name = "grades"

urlpatterns = [
    path("", views.index, name="index"),

    path("download/<int:grade_document_id>", views.download_grades, name="download_grades"),
    path("semester/<int:semester_id>", views.semester_view, name="semester_view"),
    path("semester/<int:semester_id>/course/<int:course_id>", views.course_view, name="course_view"),
    path("semester/<int:semester_id>/course/<int:course_id>/upload", views.upload_grades, name="upload_grades"),
    path("semester/<int:semester_id>/course/<int:course_id>/edit/<int:grade_document_id>", views.edit_grades, name="edit_grades"),

    path("delete_grades", views.delete_grades, name="delete_grades"),
    path("toggle_no_grades", views.toggle_no_grades, name="toggle_no_grades"),

    path("semester/<int:semester_id>/grade_activation/<str:active>", views.semester_grade_activation, name="semester_grade_activation"),
]
