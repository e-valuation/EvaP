from django.urls import path

from evap.results import views


app_name = "results"

urlpatterns = [
    path("", views.index, name="index"),
    path("semester/<int:semester_id>/evaluation/<int:evaluation_id>", views.evaluation_detail, name="evaluation_detail"),
    path("evaluation/<int:evaluation_id>/text_answers_export", views.evaluation_text_answers_export, name="evaluation_text_answers_export"),
]
