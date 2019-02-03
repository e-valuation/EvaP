from django.urls import path

from evap.student import views


app_name = "student"

urlpatterns = [
    path("", views.index, name="index"),
    path("vote/<int:evaluation_id>", views.vote, name="vote"),
]
