from django.conf.urls.defaults import patterns, include, url

urlpatterns = patterns('',
    url(r"^$", 'fsr.views.fsr_index'),
    url(r"^import$", 'fsr.views.fsr_import'),
)