from django.conf.urls import patterns, url
from django.views.generic import RedirectView

urlpatterns = patterns('evap.fsr.views',
    url(r"^$", 'index', name="fsr_root"),
    
    url(r"^semester/$", RedirectView.as_view(url='/fsr/')),
    url(r"^semester/create$", 'semester_create'),
    url(r"^semester/(\d+)$", 'semester_view'),
    url(r"^semester/(\d+)/edit$", 'semester_edit'),
    url(r"^semester/(\d+)/delete$", 'semester_delete'),
    url(r"^semester/(\d+)/import$", 'semester_import'),
    url(r"^semester/(\d+)/assign$", 'semester_assign_questionnaires'),
    url(r"^semester/(\d+)/publish$", 'semester_publish'),
    url(r"^semester/(\d+)/approve$", 'semester_approve'),
    url(r"^semester/(\d+)/contributorready$", 'semester_contributor_ready'),
    url(r"^semester/(\d+)/lottery$", 'semester_lottery'),
    url(r"^semester/(\d+)/course/create$", 'course_create'),
    url(r"^semester/(\d+)/course/(\d+)/edit$", 'course_edit'),
    url(r"^semester/(\d+)/course/(\d+)/delete$", 'course_delete'),
    url(r"^semester/(\d+)/course/(\d+)/review$", 'course_review'),
    url(r"^semester/(\d+)/course/(\d+)/review/(\d+)$", 'course_review'),
    url(r"^semester/(\d+)/course/(\d+)/contributor_ready$", 'course_contributor_ready'),
    url(r"^semester/(\d+)/course/(\d+)/email$", 'course_email'),
    url(r"^semester/(\d+)/course/(\d+)/unpublish$", 'course_unpublish'),
    url(r"^semester/(\d+)/course/(\d+)/preview$", 'course_preview'),
    url(r"^semester/(\d+)/course/(\d+)/comments$", 'course_comments'),
    
    url(r"^questionnaire/$", 'questionnaire_index'),
    url(r"^questionnaire/create$", 'questionnaire_create'),
    url(r"^questionnaire/(\d+)$", 'questionnaire_view'),
    url(r"^questionnaire/(\d+)/edit$", 'questionnaire_edit'),
    url(r"^questionnaire/(\d+)/copy$", 'questionnaire_copy'),
    url(r"^questionnaire/(\d+)/delete$", 'questionnaire_delete'),
    
    url(r"^user/$", 'user_index'),
    url(r"^user/create$", 'user_create'),
    url(r"^user/(\d+)/edit$", 'user_edit'),
    url(r"^user/(\d+)/delete$", 'user_delete'),
    
    url(r"^template/$", RedirectView.as_view(url='/fsr/')),
    url(r"^template/(\d+)$", 'template_edit'),

    url(r"faq/$", "faq_index"),
    url(r"faq/(\d+)$", "faq_section"),
)
