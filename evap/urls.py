from django.conf import settings
from django.conf.urls import include, url
import django.views.static
import django.contrib.auth.views

from django.contrib import admin
admin.autodiscover()


urlpatterns = [
    url(r"^", include('evap.evaluation.urls')),
    url(r"^staff/", include('evap.staff.urls')),
    url(r"^results/", include('evap.results.urls')),
    url(r"^student/", include('evap.student.urls')),
    url(r"^contributor/", include('evap.contributor.urls')),
    url(r"^rewards/", include('evap.rewards.urls')),
    url(r"^grades/", include('evap.grades.urls')),

    url(r"^logout$", django.contrib.auth.views.LogoutView.as_view(next_page="/"), name="django-auth-logout"),

    url(r"^admin/", admin.site.urls),
]

if settings.DEBUG:
    urlpatterns += [url(r'^media/(?P<path>.*)$', django.views.static.serve, {'document_root': settings.MEDIA_ROOT})]

if settings.DEBUG and settings.ENABLE_DEBUG_TOOLBAR:
    import debug_toolbar
    urlpatterns += [url(r'^__debug__/', include(debug_toolbar.urls))]
