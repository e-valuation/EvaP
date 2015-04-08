from django.conf import settings
from django.conf.urls import include, url
import evap.evaluation.views

# Uncomment the next two lines to enable the admin:
from django.contrib import admin
admin.autodiscover()

import django.contrib.auth.views

urlpatterns = [
    url(r"^$", evap.evaluation.views.index, name="evap-evaluation-index"),
    url(r"^faq$", evap.evaluation.views.faq, name="evap-evaluation-faq"),
    url(r"^legal_notice$", evap.evaluation.views.legal_notice, name="evap-evaluation-legal_notice"),
    url(r"^logout$", django.contrib.auth.views.logout, {'next_page': "/"}, name="django-auth-logout"),

    url(r"^staff/", include('evap.staff.urls', namespace="staff")),
    url(r"^results/", include('evap.results.urls', namespace="results")),
    url(r"^student/", include('evap.student.urls', namespace="student")),
    url(r"^contributor/", include('evap.contributor.urls', namespace="contributor")),
    url(r"^rewards/", include('evap.rewards.urls', namespace="rewards")),

    url(r'^i18n/', include('django.conf.urls.i18n')),
    url(r"^admin/", include(admin.site.urls)),
]

if settings.DEBUG:
    urlpatterns += [url(r'^media/(?P<path>.*)$', 'django.views.static.serve', {'document_root': settings.MEDIA_ROOT})]

if settings.DEBUG and settings.ENABLE_DEBUG_TOOLBAR:
    import debug_toolbar
    urlpatterns += [url(r'^__debug__/', include(debug_toolbar.urls))]
