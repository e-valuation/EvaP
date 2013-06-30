from django.conf.urls import patterns, url

urlpatterns = patterns('evap.student.views',
    url(r"^$", 'index'),
    url(r"^vote/(?P<course_id>\d+)$", 'vote'),
)
