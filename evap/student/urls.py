from django.conf.urls.defaults import patterns, include, url

urlpatterns = patterns('student.views',
    url(r"^$", 'index'),
    url(r"^vote/(?P<course_id>\d+)$", 'vote'),
)
