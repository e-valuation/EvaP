from django.urls import path

from evap.cms import views

app_name = "cms"

urlpatterns = [
    path("ignored_evaluation/delete", views.ignored_evaluation_delete, name="ignored_evaluation_delete"),
    path("course_link_update_activation", views.course_link_update_activation, name="course_link_update_activation"),
    path("evaluation_link_update_activation", views.evaluation_link_update_activation, name="evaluation_link_update_activation"),
]
