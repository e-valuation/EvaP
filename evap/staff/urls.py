from django.urls import path
from django.views.generic import RedirectView

from evap.staff import views


app_name = "staff"

urlpatterns = [
    path("", views.index, name="index"),

    path("semester/", RedirectView.as_view(url='/staff/', permanent=True)),
    path("semester/create", views.semester_create, name="semester_create"),
    path("semester/<int:semester_id>", views.semester_view, name="semester_view"),
    path("semester/<int:semester_id>/edit", views.semester_edit, name="semester_edit"),
    path("semester/<int:semester_id>/import", views.semester_import, name="semester_import"),
    path("semester/<int:semester_id>/export", views.semester_export, name="semester_export"),
    path("semester/<int:semester_id>/raw_export", views.semester_raw_export, name="semester_raw_export"),
    path("semester/<int:semester_id>/participation_export", views.semester_participation_export, name="semester_participation_export"),
    path("semester/<int:semester_id>/assign", views.semester_questionnaire_assign, name="semester_questionnaire_assign"),
    path("semester/<int:semester_id>/preparation_reminder", views.semester_preparation_reminder, name="semester_preparation_reminder"),
    path("semester/<int:semester_id>/grade_reminder", views.semester_grade_reminder, name="semester_grade_reminder"),
    path("semester/<int:semester_id>/course/create", views.course_create, name="course_create"),
    path("semester/<int:semester_id>/course/<int:course_id>/edit", views.course_edit, name="course_edit"),
    path("semester/<int:semester_id>/evaluation/create", views.evaluation_create, name="evaluation_create"),
    path("semester/<int:semester_id>/evaluation/create/<int:course_id>", views.evaluation_create, name="evaluation_create"),
    path("semester/<int:semester_id>/evaluation/<int:evaluation_id>/edit", views.evaluation_edit, name="evaluation_edit"),
    path("semester/<int:semester_id>/evaluation/<int:evaluation_id>/email", views.evaluation_email, name="evaluation_email"),
    path("semester/<int:semester_id>/evaluation/<int:evaluation_id>/preview", views.evaluation_preview, name="evaluation_preview"),
    path("semester/<int:semester_id>/evaluation/<int:evaluation_id>/person_management", views.evaluation_person_management, name="evaluation_person_management"),
    path("semester/<int:semester_id>/evaluation/<int:evaluation_id>/login_key_export", views.evaluation_login_key_export, name="evaluation_login_key_export"),
    path("semester/<int:semester_id>/evaluation/<int:evaluation_id>/textanswers", views.evaluation_textanswers, name="evaluation_textanswers"),
    path("semester/<int:semester_id>/evaluation/<int:evaluation_id>/textanswer/<uuid:textanswer_id>/edit", views.evaluation_textanswer_edit, name="evaluation_textanswer_edit"),
    path("semester/<int:semester_id>/evaluationoperation", views.semester_evaluation_operation, name="semester_evaluation_operation"),
    path("semester/<int:semester_id>/singleresult/create", views.single_result_create, name="single_result_create"),
    path("semester/<int:semester_id>/singleresult/create/<int:course_id>", views.single_result_create, name="single_result_create"),
    path("semester/<int:semester_id>/responsible/<int:responsible_id>/send_reminder", views.send_reminder, name="send_reminder"),

    path("semester/delete", views.semester_delete, name="semester_delete"),
    path("semester/archive_participations", views.semester_archive_participations, name="semester_archive_participations"),
    path("semester/delete_grade_documents", views.semester_delete_grade_documents, name="semester_delete_grade_documents"),
    path("semester/archive_results", views.semester_archive_results, name="semester_archive_results"),
    path("semester/course_delete", views.course_delete, name="course_delete"),
    path("semester/evaluation_delete", views.evaluation_delete, name="evaluation_delete"),

    path("textanswers/update_publish", views.evaluation_textanswers_update_publish, name="evaluation_textanswers_update_publish"),

    path("questionnaire/", views.questionnaire_index, name="questionnaire_index"),
    path("questionnaire/create", views.questionnaire_create, name="questionnaire_create"),
    path("questionnaire/<int:questionnaire_id>", views.questionnaire_view, name="questionnaire_view"),
    path("questionnaire/<int:questionnaire_id>/edit", views.questionnaire_edit, name="questionnaire_edit"),
    path("questionnaire/<int:questionnaire_id>/new_version", views.questionnaire_new_version, name="questionnaire_new_version"),
    path("questionnaire/<int:questionnaire_id>/copy", views.questionnaire_copy, name="questionnaire_copy"),
    path("questionnaire/delete", views.questionnaire_delete, name="questionnaire_delete"),
    path("questionnaire/update_indices", views.questionnaire_update_indices, name="questionnaire_update_indices"),

    path("degrees/", views.degree_index, name="degree_index"),

    path("course_types/", views.course_type_index, name="course_type_index"),
    path("course_types/merge", views.course_type_merge_selection, name="course_type_merge_selection"),
    path("course_types/<int:main_type_id>/merge/<int:other_type_id>", views.course_type_merge, name="course_type_merge"),

    path("user/", views.user_index, name="user_index"),
    path("user/create", views.user_create, name="user_create"),
    path("user/import", views.user_import, name="user_import"),
    path("user/<int:user_id>/edit", views.user_edit, name="user_edit"),

    path("user/delete", views.user_delete, name="user_delete"),
    path("user/bulk_delete", views.user_bulk_delete, name="user_bulk_delete"),
    path("user/merge", views.user_merge_selection, name="user_merge_selection"),
    path("user/<int:main_user_id>/merge/<int:other_user_id>", views.user_merge, name="user_merge"),

    path("template/", RedirectView.as_view(url='/staff/', permanent=True)),
    path("template/<int:template_id>", views.template_edit, name="template_edit"),

    path("faq/", views.faq_index, name="faq_index"),
    path("faq/<int:section_id>", views.faq_section, name="faq_section"),

    path("download_sample_xls/<str:filename>", views.download_sample_xls, name="download_sample_xls"),

    path("development/components", views.development_components, name="development_components"),
]
