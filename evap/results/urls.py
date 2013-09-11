from django.conf.urls import patterns, url

urlpatterns = patterns('evap.results.views',
    url(r"^$", 'index'),
    url(r"semester/(\d+)$", 'semester_detail'),
    url(r"semester/(\d+)/export$", 'semester_export'),
    url(r"semester/(\d+)/course/(\d+)$", 'course_detail'),
)
