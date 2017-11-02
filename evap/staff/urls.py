from django.conf.urls import url
from django.views.generic import RedirectView

from evap.staff import views


app_name = "staff"

urlpatterns = [
    url(r"^$", views.index, name="index"),

    url(r"^semester/$", RedirectView.as_view(url='/staff/', permanent=True)),
    url(r"^semester/create$", views.semester_create, name="semester_create"),
    url(r"^semester/(\d+)$", views.semester_view, name="semester_view"),
    url(r"^semester/(\d+)/edit$", views.semester_edit, name="semester_edit"),
    url(r"^semester/(\d+)/import$", views.semester_import, name="semester_import"),
    url(r"^semester/(\d+)/export$", views.semester_export, name="semester_export"),
    url(r"^semester/(\d+)/raw_export$", views.semester_raw_export, name="semester_raw_export"),
    url(r"^semester/(\d+)/participation_export$", views.semester_participation_export, name="semester_participation_export"),
    url(r"^semester/(\d+)/assign$", views.semester_questionnaire_assign, name="semester_questionnaire_assign"),
    url(r"^semester/(\d+)/todo", views.semester_todo, name="semester_todo"),
    url(r"^semester/(\d+)/course/create$", views.course_create, name="course_create"),
    url(r"^semester/(\d+)/course/(\d+)/edit$", views.course_edit, name="course_edit"),
    url(r"^semester/(\d+)/course/(\d+)/email$", views.course_email, name="course_email"),
    url(r"^semester/(\d+)/course/(\d+)/preview$", views.course_preview, name="course_preview"),
    url(r"^semester/(\d+)/course/(\d+)/person_import", views.course_person_import, name="course_person_import"),
    url(r"^semester/(\d+)/course/(\d+)/comments$", views.course_comments, name="course_comments"),
    url(r"^semester/(\d+)/course/(\d+)/comment/([0-9a-f\-]+)/edit$", views.course_comment_edit, name="course_comment_edit"),
    url(r"^semester/(\d+)/courseoperation$", views.semester_course_operation, name="semester_course_operation"),
    url(r"^semester/(\d+)/singleresult/create$", views.single_result_create, name="single_result_create"),
    url(r"^semester/(\d+)/responsible/(\d+)/send_reminder", views.send_reminder, name="send_reminder"),

    url(r"^semester/delete$", views.semester_delete, name="semester_delete"),
    url(r"^semester/archive$", views.semester_archive, name="semester_archive"),
    url(r"^semester/course_delete$", views.course_delete, name="course_delete"),

    url(r"^comments/update_publish$", views.course_comments_update_publish, name="course_comments_update_publish"),

    url(r"^questionnaire/$", views.questionnaire_index, name="questionnaire_index"),
    url(r"^questionnaire/create$", views.questionnaire_create, name="questionnaire_create"),
    url(r"^questionnaire/(\d+)$", views.questionnaire_view, name="questionnaire_view"),
    url(r"^questionnaire/(\d+)/edit$", views.questionnaire_edit, name="questionnaire_edit"),
    url(r"^questionnaire/(\d+)/new_version", views.questionnaire_new_version, name="questionnaire_new_version"),
    url(r"^questionnaire/(\d+)/copy$", views.questionnaire_copy, name="questionnaire_copy"),
    url(r"^questionnaire/delete$", views.questionnaire_delete, name="questionnaire_delete"),
    url(r"^questionnaire/update_indices$", views.questionnaire_update_indices, name="questionnaire_update_indices"),

    url(r"^degrees/$", views.degree_index, name="degree_index"),

    url(r"^course_types/$", views.course_type_index, name="course_type_index"),
    url(r"^course_types/merge$", views.course_type_merge_selection, name="course_type_merge_selection"),
    url(r"^course_types/(\d+)/merge/(\d+)$", views.course_type_merge, name="course_type_merge"),

    url(r"^user/$", views.user_index, name="user_index"),
    url(r"^user/create$", views.user_create, name="user_create"),
    url(r"^user/import$", views.user_import, name="user_import"),
    url(r"^user/(\d+)/edit$", views.user_edit, name="user_edit"),

    url(r"^user/delete$", views.user_delete, name="user_delete"),
    url(r"^user/bulk_delete$", views.user_bulk_delete, name="user_bulk_delete"),
    url(r"^user/merge$", views.user_merge_selection, name="user_merge_selection"),
    url(r"^user/(\d+)/merge/(\d+)$", views.user_merge, name="user_merge"),

    url(r"^template/$", RedirectView.as_view(url='/staff/', permanent=True)),
    url(r"^template/(\d+)$", views.template_edit, name="template_edit"),

    url(r"^faq/$", views.faq_index, name="faq_index"),
    url(r"^faq/(\d+)$", views.faq_section, name="faq_section"),

    url(r"^download_sample_xls/(.+)$", views.download_sample_xls, name="download_sample_xls")
]
