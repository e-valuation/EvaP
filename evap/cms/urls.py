from django.urls import path

from evap.cms import views

app_name = "cms"

urlpatterns = [
    path("ignored_evaluation/delete", views.ignored_evaluation_delete, name="ignored_evaluation_delete"),
    path("cms_course_link_update_activation", views.cms_course_link_update_activation, name="cms_course_link_update_activation"),
    path("cms_evaluation_link_update_activation", views.cms_evaluation_link_update_activation, name="cms_evaluation_link_update_activation"),
    path("evaluation_merge_selection/<int:main_evaluation_id>", views.evaluation_merge_selection, name="evaluation_merge_selection"),
]
