from django.conf.urls import url

from evap.evaluation import views


app_name = "evaluation"

urlpatterns = [
    url(r"^$", views.index, name="index"),
    url(r"^faq$", views.faq, name="faq"),
    url(r"^set_lang", views.set_lang, name="set_lang"),
    url(r"^legal_notice$", views.legal_notice, name="legal_notice"),
    url(r"contact$", views.contact, name="contact"),
]
