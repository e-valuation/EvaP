from django.conf.urls import url

from evap.evaluation.views import *


app_name = "evaluation"

urlpatterns = [
    url(r"^$", index, name="index"),
    url(r"^faq$", faq, name="faq"),
    url(r"^set_language", set_and_save_language, name="set_lang"),
    url(r"^legal_notice$", legal_notice, name="legal_notice"),
    url(r"feedback/send$", feedback_send, name="feedback_send"),
]
