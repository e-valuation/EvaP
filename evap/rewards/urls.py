from django.conf.urls import url

from evap.rewards.views import *

urlpatterns = [
    url(r"^$", index),
]
