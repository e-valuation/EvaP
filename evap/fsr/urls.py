from django.conf.urls.defaults import patterns, include, url

urlpatterns = patterns('fsr.views',
    url(r"^$", 'semester_index', name="fsr_root"),
    
    url(r"^semester$", 'semester_index'),
    url(r"^semester/create$", 'semester_create'),
    url(r"^semester/(\d+)$", 'semester_view'),
    url(r"^semester/(\d+)/edit$", 'semester_edit'),
    url(r"^semester/(\d+)/delete$", 'semester_delete'),
    url(r"^semester/(\d+)/import$", 'semester_import'),
    url(r"^semester/(\d+)/assign$", 'semester_assign_questiongroups'),
    url(r"^semester/(\d+)/publish$", 'semester_publish'),
    url(r"^semester/(\d+)/course/create$", 'course_create'),    
    url(r"^semester/(\d+)/course/(\d+)/edit$", 'course_edit'),
    url(r"^semester/(\d+)/course/(\d+)/delete$", 'course_delete'),
    url(r"^semester/(\d+)/course/(\d+)/censor$", 'course_censor'),
    
    url(r"^questiongroup$", 'questiongroup_index'),
    url(r"^questiongroup/create$", 'questiongroup_create'),
    url(r"^questiongroup/(\d+)$", 'questiongroup_view'),
    url(r"^questiongroup/(\d+)/edit$", 'questiongroup_edit'),
    url(r"^questiongroup/(\d+)/copy$", 'questiongroup_copy'),
    url(r"^questiongroup/(\d+)/delete$", 'questiongroup_delete'),
    
    url(r"^user$", 'user_index'),
    url(r"^user/create$", 'user_create'),
    url(r"^user/(\d+)/edit$", 'user_edit'),
    url(r"^user/(\d+)/new_key$", 'user_key_new'),
    url(r"^user/(\d+)/del_key$", 'user_key_remove'),
    url(r"^user/(\d+)/delete$", 'user_delete'),
)
