from django.conf.urls.defaults import patterns, include, url

urlpatterns = patterns('results.views',
    url(r"^$", 'index'),
    url(r"course/(?P<id>\d+)", 'course_detail')
)
