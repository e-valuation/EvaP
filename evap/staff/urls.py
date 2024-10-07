from django.urls import path
from django.views.generic import RedirectView

from evap.staff import views

app_name = "staff"

urlpatterns = [
    path("", views.index, name="index"),

    path("semester/", RedirectView.as_view(url='/staff/', permanent=True)),
    path("semester/create", views.SemesterCreateView.as_view(), name="semester_create"),
    path("semester/<int:semester_id>", views.semester_view, name="semester_view"),
    path("semester/<int:semester_id>/edit", views.SemesterEditView.as_view(), name="semester_edit"),
    path("semester/make_active", views.semester_make_active, name="semester_make_active"),
    path("semester/delete", views.semester_delete, name="semester_delete"),
    path("semester/<int:semester_id>/import", views.semester_import, name="semester_import"),
    path("semester/<int:semester_id>/export", views.semester_export, name="semester_export"),
    path("semester/<int:semester_id>/raw_export", views.semester_raw_export, name="semester_raw_export"),
    path("semester/<int:semester_id>/participation_export", views.semester_participation_export, name="semester_participation_export"),
    path("semester/<int:semester_id>/vote_timestamps_export", views.vote_timestamps_export, name="vote_timestamps_export"),
    path("semester/<int:semester_id>/assign", views.semester_questionnaire_assign, name="semester_questionnaire_assign"),
    path("semester/<int:semester_id>/preparation_reminder", views.semester_preparation_reminder, name="semester_preparation_reminder"),
    path("semester/<int:semester_id>/grade_reminder", views.semester_grade_reminder, name="semester_grade_reminder"),
    path("semester/<int:semester_id>/responsible/<int:responsible_id>/send_reminder", views.send_reminder, name="send_reminder"),
    path("semester/archive_participations", views.semester_archive_participations, name="semester_archive_participations"),
    path("semester/archive_results", views.semester_archive_results, name="semester_archive_results"),
    path("semester/delete_grade_documents", views.semester_delete_grade_documents, name="semester_delete_grade_documents"),

    path("semester/<int:semester_id>/evaluation/create", views.evaluation_create_for_semester, name="evaluation_create_for_semester"),
    path("course/<int:course_id>/evaluation/create", views.evaluation_create_for_course, name="evaluation_create_for_course"),
    path("evaluation/delete", views.evaluation_delete, name="evaluation_delete"),
    path("evaluation/<int:evaluation_id>/edit", views.evaluation_edit, name="evaluation_edit"),
    path("evaluation/<int:evaluation_id>/copy", views.evaluation_copy, name="evaluation_copy"),
    path("evaluation/<int:evaluation_id>/email", views.evaluation_email, name="evaluation_email"),
    path("evaluation/<int:evaluation_id>/preview", views.evaluation_preview, name="evaluation_preview"),
    path("evaluation/<int:evaluation_id>/person_management", views.evaluation_person_management, name="evaluation_person_management"),
    path("evaluation/<int:evaluation_id>/login_key_export", views.evaluation_login_key_export, name="evaluation_login_key_export"),
    path("semester/<int:semester_id>/evaluation/operation", views.evaluation_operation, name="evaluation_operation"),

    path("semester/<int:semester_id>/course/create", views.course_create, name="course_create"),
    path("course/delete", views.course_delete, name="course_delete"),
    path("course/<int:course_id>/edit", views.CourseEditView.as_view(), name="course_edit"),
    path("course/<int:course_id>/copy", views.course_copy, name="course_copy"),

    path("semester/<int:semester_id>/singleresult/create", views.single_result_create_for_semester, name="single_result_create_for_semester"),
    path("course/<int:course_id>/singleresult/create", views.single_result_create_for_course, name="single_result_create_for_course"),

    path("evaluation/<int:evaluation_id>/textanswers", views.evaluation_textanswers, name="evaluation_textanswers"),
    path("semester/<int:semester_id>/flagged_textanswers", views.semester_flagged_textanswers, name="semester_flagged_textanswers"),
    path("textanswer/<uuid:textanswer_id>/edit", views.evaluation_textanswer_edit, name="evaluation_textanswer_edit"),
    path("textanswers/update_publish", views.evaluation_textanswers_update_publish, name="evaluation_textanswers_update_publish"),
    path("textanswers/update_flag", views.evaluation_textanswers_update_flag, name="evaluation_textanswers_update_flag"),
    path("textanswers/skip", views.evaluation_textanswers_skip, name="evaluation_textanswers_skip"),

    path("questionnaire/", views.questionnaire_index, name="questionnaire_index"),
    path("questionnaire/create", views.questionnaire_create, name="questionnaire_create"),
    path("questionnaire/<int:questionnaire_id>", views.questionnaire_view, name="questionnaire_view"),
    path("questionnaire/<int:questionnaire_id>/edit", views.questionnaire_edit, name="questionnaire_edit"),
    path("questionnaire/<int:questionnaire_id>/new_version", views.questionnaire_new_version, name="questionnaire_new_version"),
    path("questionnaire/<int:questionnaire_id>/copy", views.questionnaire_copy, name="questionnaire_copy"),
    path("questionnaire/delete", views.questionnaire_delete, name="questionnaire_delete"),
    path("questionnaire/update_indices", views.questionnaire_update_indices, name="questionnaire_update_indices"),
    path("questionnaire/questionnaire_visibility", views.questionnaire_visibility, name="questionnaire_visibility"),
    path("questionnaire/questionnaire_set_locked", views.questionnaire_set_locked, name="questionnaire_set_locked"),

    path("programs/", views.ProgramIndexView.as_view(), name="program_index"),

    path("course_types/", views.CourseTypeIndexView.as_view(), name="course_type_index"),
    path("course_types/merge", views.course_type_merge_selection, name="course_type_merge_selection"),
    path("course_types/<int:main_type_id>/merge/<int:other_type_id>", views.course_type_merge, name="course_type_merge"),

    path("user/", views.user_index, name="user_index"),
    path("user/create", views.UserCreateView.as_view(), name="user_create"),
    path("user/import", views.user_import, name="user_import"),
    path("user/export", views.user_export, name="user_export"),
    path("user/<int:user_id>/edit", views.user_edit, name="user_edit"),
    path("user/list", views.user_list, name="user_list"),
    path("user/delete", views.user_delete, name="user_delete"),
    path("user/resend_email", views.user_resend_email, name="user_resend_email"),
    path("user/bulk_update", views.user_bulk_update, name="user_bulk_update"),
    path("user/merge", views.UserMergeSelectionView.as_view(), name="user_merge_selection"),
    path("user/<int:main_user_id>/merge/<int:other_user_id>", views.user_merge, name="user_merge"),

    path("template/", RedirectView.as_view(url='/staff/', permanent=True)),
    path("template/<int:template_id>", views.TemplateEditView.as_view(), name="template_edit"),

    path("text_answer_warnings/", views.text_answer_warnings_index, name="text_answer_warnings"),

    path("faq/", views.FaqIndexView.as_view(), name="faq_index"),
    path("faq/<int:section_id>", views.faq_section, name="faq_section"),

    path("infotexts/", views.InfotextsView.as_view(), name="infotexts"),

    path("download_sample_file/<str:filename>", views.download_sample_file, name="download_sample_file"),

    path("export_contributor_results/<int:contributor_id>", views.export_contributor_results_view, name="export_contributor_results"),

    path("enter_staff_mode", views.enter_staff_mode, name="enter_staff_mode"),
    path("exit_staff_mode", views.exit_staff_mode, name="exit_staff_mode"),
]
