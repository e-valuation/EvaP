from django.conf.urls.defaults import patterns, include, url

urlpatterns = patterns('evap.results.views',
    url(r"^$", 'index'),
    url(r"semester/(\d+)$", 'semester_detail'),
    url(r"semester/(\d+)/course/(\d+)$", 'course_detail'),
)
