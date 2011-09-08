from django.conf.urls.defaults import patterns, include, url

urlpatterns = patterns('lecturer.views',
    url(r"^$", 'index'),
    url(r"^profile$", 'profile_edit'),
    url(r"^course$", 'course_index'),
    url(r"^course/(\d+)$", 'course_edit'),
)
