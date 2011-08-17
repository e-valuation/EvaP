from django.conf.urls.defaults import patterns, include, url

urlpatterns = patterns('fsr.views',
    url(r"^$", 'fsr_index'),
    url(r"^create$", 'fsr_semester_create'),
    url(r"^(\d+)$", 'fsr_semester_view'),
    url(r"^(\d+)/create$", 'fsr_course_create'),
    url(r"^(\d+)/edit$", 'fsr_semester_edit'),
    url(r"^(\d+)/import$", 'fsr_semester_import'),
    url(r"^(\d+)/(\d+)/edit$", 'fsr_course_edit'),
)
