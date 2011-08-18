from django.conf.urls.defaults import patterns, include, url

urlpatterns = patterns('fsr.views',
    url(r"^$", 'index'),
    url(r"^create$", 'semester_create'),
    url(r"^(\d+)$", 'semester_view'),
    url(r"^(\d+)/create$", 'course_create'),
    url(r"^(\d+)/edit$", 'semester_edit'),
    url(r"^(\d+)/import$", 'semester_import'),
    url(r"^(\d+)/(\d+)/edit$", 'course_edit'),
)
