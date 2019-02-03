from django.conf import settings
from django.urls import include, path
import django.contrib.auth.views


urlpatterns = [
    path("", include('evap.evaluation.urls')),
    path("staff/", include('evap.staff.urls')),
    path("results/", include('evap.results.urls')),
    path("student/", include('evap.student.urls')),
    path("contributor/", include('evap.contributor.urls')),
    path("rewards/", include('evap.rewards.urls')),
    path("grades/", include('evap.grades.urls')),

    path("logout", django.contrib.auth.views.LogoutView.as_view(next_page="/"), name="django-auth-logout"),
]

if settings.DEBUG and settings.ENABLE_DEBUG_TOOLBAR:
    import debug_toolbar
    urlpatterns += [path('__debug__/', include(debug_toolbar.urls))]
