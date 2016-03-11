from django.conf.urls import url

from evap.evaluation.views import *


app_name = "evaluation"

urlpatterns = [
    url(r"^$", index, name="index"),
    url(r"^faq$", faq, name="faq"),
    url(r"^legal_notice$", legal_notice, name="legal_notice"),
    url(r"feedback/create", feedback_create, name="feedback_create"),
    url(r"feedback/(?P<feedback_id>\d+)/delete$", feedback_delete, name="feedback_delete"),
    url(r"feedback/(?P<feedback_id>\d+)/process", feedback_process, name="feedback_process"),

]
