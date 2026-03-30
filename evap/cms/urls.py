from django.urls import path

from evap.cms import views

app_name = "cms"

urlpatterns = [
    path("ignored_evaluation/delete", views.ignored_evaluation_delete, name="ignored_evaluation_delete"),
]
