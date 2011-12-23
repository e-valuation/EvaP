from django.conf.urls.defaults import patterns, url

urlpatterns = patterns('evap.lecturer.views',
    url(r"^$", 'index'),
    url(r"^profile$", 'profile_edit'),
    url(r"^course$", 'course_index'),
    url(r"^course/(\d+)$", 'course_edit'),
    url(r"^course/(\d+)/preview$", 'course_preview'),
)
