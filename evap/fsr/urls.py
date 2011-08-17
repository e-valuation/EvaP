from django.conf.urls.defaults import patterns, include, url

urlpatterns = patterns('',
    url(r"^$", 'fsr.views.fsr_index'),
    url(r"^create$", 'fsr.views.fsr_semester_create'),
    url(r"^(\d+)$", 'fsr.views.fsr_semester_view'),
    url(r"^(\d+)/edit$", 'fsr.views.fsr_semester_edit'),
    url(r"^(\d+)/import$", 'fsr.views.fsr_semester_import'),
)