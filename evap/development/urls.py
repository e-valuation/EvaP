from django.urls import path

from evap.development import views

urlpatterns = [
    path("components", views.development_components, name="development_components"),
]
