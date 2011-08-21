from django.conf.urls.defaults import patterns, include, url
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.conf import settings

# Uncomment the next two lines to enable the admin:
from django.contrib import admin
admin.autodiscover()

urlpatterns = patterns('',
    url(r"^$", 'views.index'),
    
    url(r"^fsr/", include('fsr.urls')),
    url(r"^results/", include('results.urls')),
    url(r"^student/", include('student.urls')),
    
    
    url(r"^i18n/", include('django.conf.urls.i18n')),
    url(r"^admin/", include(admin.site.urls)),
)
