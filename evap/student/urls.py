from django.conf.urls.defaults import patterns, include, url

urlpatterns = patterns('evap.student.views',
    url(r"^$", 'index'),
    url(r"^vote/(?P<course_id>\d+)$", 'vote'),
)
