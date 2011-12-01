from django.conf import settings
from django.conf.urls.defaults import patterns, include, url
from django.contrib.staticfiles.urls import staticfiles_urlpatterns

# Uncomment the next two lines to enable the admin:
from django.contrib import admin
admin.autodiscover()

urlpatterns = patterns('',
    url(r"^$", 'evap.evaluation.views.index'),
    url(r"^login$", 'django.views.generic.simple.redirect_to', {'url': "/"}),
    url(r"^logout$", 'django.contrib.auth.views.logout', {'next_page': "/"}),
    
    url(r"^fsr/", include('evap.fsr.urls')),
    url(r"^results/", include('evap.results.urls')),
    url(r"^student/", include('evap.student.urls')),
    url(r"^lecturer/", include('evap.lecturer.urls')),
    
    url(r"^i18n/", include('django.conf.urls.i18n')),
    url(r"^admin/", include(admin.site.urls)),
)

if not settings.DEBUG:
    urlpatterns.append(url(r'^sentry/', include('sentry.web.urls')))

if settings.DEBUG:
    urlpatterns += patterns('',
        url(r'^media/(?P<path>.*)$', 'django.views.static.serve', { 'document_root': settings.MEDIA_ROOT,}),
   )
