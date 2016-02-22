from django.conf.urls import url
from django.views.generic import RedirectView

from evap.staff.views import *


app_name = "staff"

urlpatterns = [
    url(r"^$", index, name="index"),

    url(r"^semester/$", RedirectView.as_view(url='/staff/', permanent=True)),
    url(r"^semester/create$", semester_create, name="semester_create"),
    url(r"^semester/(\d+)$", semester_view, name="semester_view"),
    url(r"^semester/(\d+)/edit$", semester_edit, name="semester_edit"),
    url(r"^semester/(\d+)/import$", semester_import, name="semester_import"),
    url(r"^semester/(\d+)/export$", semester_export, name="semester_export"),
    url(r"^semester/(\d+)/assign$", semester_assign_questionnaires, name="semester_assign_questionnaires"),
    url(r"^semester/(\d+)/todo", semester_todo, name="semester_todo"),
    url(r"^semester/(\d+)/lottery$", semester_lottery, name="semester_lottery"),
    url(r"^semester/(\d+)/course/create$", course_create, name="course_create"),
    url(r"^semester/(\d+)/course/(\d+)/edit$", course_edit, name="course_edit"),
    url(r"^semester/(\d+)/course/(\d+)/email$", course_email, name="course_email"),
    url(r"^semester/(\d+)/course/(\d+)/preview$", course_preview, name="course_preview"),
    url(r"^semester/(\d+)/course/(\d+)/importparticipants", course_import_participants, name="course_import_participants"),
    url(r"^semester/(\d+)/course/(\d+)/comments$", course_comments, name="course_comments"),
    url(r"^semester/(\d+)/course/(\d+)/comment/(\d+)/edit$", course_comment_edit, name="course_comment_edit"),
    url(r"^semester/(\d+)/courseoperation$", semester_course_operation, name="semester_course_operation"),
    url(r"^semester/(\d+)/singleresult/create$", single_result_create, name="single_result_create"),

    url(r"^semester/delete$", semester_delete, name="semester_delete"),
    url(r"^semester/archive$", semester_archive, name="semester_archive"),
    url(r"^semester/course_delete$", course_delete, name="course_delete"),

    url(r"^comments/update_publish$", course_comments_update_publish, name="course_comments_update_publish"),

    url(r"^questionnaire/$", questionnaire_index, name="questionnaire_index"),
    url(r"^questionnaire/create$", questionnaire_create, name="questionnaire_create"),
    url(r"^questionnaire/(\d+)$", questionnaire_view, name="questionnaire_view"),
    url(r"^questionnaire/(\d+)/edit$", questionnaire_edit, name="questionnaire_edit"),
    url(r"^questionnaire/(\d+)/copy$", questionnaire_copy, name="questionnaire_copy"),
    url(r"^questionnaire/delete$", questionnaire_delete, name="questionnaire_delete"),
    url(r"^questionnaire/update_indices$", questionnaire_update_indices, name="questionnaire_update_indices"),

    url(r"^degrees/$", degree_index, name="degree_index"),

    url(r"^user/$", user_index, name="user_index"),
    url(r"^user/create$", user_create, name="user_create"),
    url(r"^user/import$", user_import, name="user_import"),
    url(r"^user/(\d+)/edit$", user_edit, name="user_edit"),

    url(r"^user/delete$", user_delete, name="user_delete"),

    url(r"^template/$", RedirectView.as_view(url='/staff/', permanent=True)),
    url(r"^template/(\d+)$", template_edit, name="template_edit"),

    url(r"faq/$", faq_index, name="faq_index"),
    url(r"faq/(\d+)$", faq_section, name="faq_section"),
]
