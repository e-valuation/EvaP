from django.conf.urls import url

from evap.evaluation.views import *

urlpatterns = [
    url(r"^$", index, name="index"),
    url(r"^faq$", faq, name="faq"),
    url(r"^legal_notice$", legal_notice, name="legal_notice"),
]
