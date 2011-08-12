from django.conf.urls.defaults import patterns, include, url
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.conf import settings

# Uncomment the next two lines to enable the admin:
from django.contrib import admin
admin.autodiscover()

urlpatterns = patterns('',
    url(r"^student/$", 'evaluation.views.student_index'),
    url(r"^student/vote/(?P<course_id>\d+)/$", 'evaluation.views.student_vote'),
    
    url(r"^admin/", include(admin.site.urls)),
)
