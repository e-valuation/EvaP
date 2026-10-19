from django.urls import path

from evap.evaluation import views
from evap.middleware import no_login_required

app_name = "evaluation"

urlpatterns = [
    path("", views.index, name="index"),
    path("faq", views.faq, name="faq"),
    path("set_lang", views.set_lang, name="set_lang"),
    path("contact", views.contact, name="contact"),
    path("key/<int:key>", views.login_key_authentication, name="login_key_authentication"),
    path("profile", views.profile_edit, name="profile_edit"),
    path("set_notes", views.set_notes, name="set_notes"),
    path("set_startpage", views.set_startpage, name="set_startpage"),
    path("demo/questiontypes", no_login_required(views.questiontypes), name="demo_questiontypes"),
]
