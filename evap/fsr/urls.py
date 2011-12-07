from django.conf.urls.defaults import patterns, url

urlpatterns = patterns('evap.fsr.views',
    url(r"^$", 'semester_index', name="fsr_root"),
    
    url(r"^semester$", 'semester_index'),
    url(r"^semester/create$", 'semester_create'),
    url(r"^semester/(\d+)$", 'semester_view'),
    url(r"^semester/(\d+)/edit$", 'semester_edit'),
    url(r"^semester/(\d+)/delete$", 'semester_delete'),
    url(r"^semester/(\d+)/import$", 'semester_import'),
    url(r"^semester/(\d+)/assign$", 'semester_assign_questionnaires'),
    url(r"^semester/(\d+)/publish$", 'semester_publish'),
    url(r"^semester/(\d+)/approve$", 'semester_approve'),
    url(r"^semester/(\d+)/lecturerready$", 'semester_lecturer_ready'),
    url(r"^semester/(\d+)/lottery$", 'semester_lottery'),
    url(r"^semester/(\d+)/course/create$", 'course_create'),
    url(r"^semester/(\d+)/course/(\d+)/edit$", 'course_edit'),
    url(r"^semester/(\d+)/course/(\d+)/delete$", 'course_delete'),
    url(r"^semester/(\d+)/course/(\d+)/censor$", 'course_censor'),
    url(r"^semester/(\d+)/course/(\d+)/lecturer_ready$", 'course_lecturer_ready'),
    url(r"^semester/(\d+)/course/(\d+)/email$", 'course_email'),
    url(r"^semester/(\d+)/course/(\d+)/unpublish$", 'course_unpublish'),
    
    url(r"^questionnaire$", 'questionnaire_index'),
    url(r"^questionnaire/create$", 'questionnaire_create'),
    url(r"^questionnaire/(\d+)$", 'questionnaire_view'),
    url(r"^questionnaire/(\d+)/edit$", 'questionnaire_edit'),
    url(r"^questionnaire/(\d+)/copy$", 'questionnaire_copy'),
    url(r"^questionnaire/(\d+)/delete$", 'questionnaire_delete'),
    
    url(r"^user$", 'user_index'),
    url(r"^user/create$", 'user_create'),
    url(r"^user/(\d+)/edit$", 'user_edit'),
    
    url(r"^template$", 'template_index'),
    url(r"^template/(\d+)$", 'template_edit'),
)
