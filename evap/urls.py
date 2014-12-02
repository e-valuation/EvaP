from django.conf import settings
from django.conf.urls import include, url
import evap.evaluation.views

# Uncomment the next two lines to enable the admin:
from django.contrib import admin
admin.autodiscover()

import django.contrib.auth.views

urlpatterns = [
    url(r"^$", evap.evaluation.views.index),
    url(r"^faq$", evap.evaluation.views.faq),
    url(r"^logout$", django.contrib.auth.views.logout, {'next_page': "/"}),

    url(r"^staff/", include('evap.staff.urls')),
    url(r"^results/", include('evap.results.urls')),
    url(r"^student/", include('evap.student.urls')),
    url(r"^contributor/", include('evap.contributor.urls')),
    url(r"^rewards/", include('evap.rewards.urls')),

    url(r'^i18n/', include('django.conf.urls.i18n')),
    url(r"^admin/", include(admin.site.urls)),
]

if settings.DEBUG:
    urlpatterns += [url(r'^media/(?P<path>.*)$', 'django.views.static.serve', {'document_root': settings.MEDIA_ROOT})]

if settings.DEBUG and settings.ENABLE_DEBUG_TOOLBAR:
    import debug_toolbar
    urlpatterns += [url(r'^__debug__/', include(debug_toolbar.urls))]
