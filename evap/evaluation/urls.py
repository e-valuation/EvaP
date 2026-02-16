from django.urls import path

from evap.evaluation import views

app_name = "evaluation"

urlpatterns = [
    path("", views.index, name="index"),
    path("faq", views.faq, name="faq"),
    path("set_lang", views.set_lang, name="set_lang"),
    path("legal_notice", views.LegalNoticeView.as_view(), name="legal_notice"),
    path("contact", views.contact, name="contact"),
    path("otp/<str:otp>", views.otp_authentication, name="otp_authentication"),
    path("profile", views.profile_edit, name="profile_edit"),
    path("set_notes", views.set_notes, name="set_notes"),
    path("set_startpage", views.set_startpage, name="set_startpage"),
]
