import os

from django.conf import settings
from django.core.exceptions import BadRequest
from django.http import HttpResponse
from django.shortcuts import render


def development_components(request):
    theme_colors = ["primary", "secondary", "success", "info", "warning", "danger", "light", "dark"]
    template_data = {
        "theme_colors": theme_colors,
        "infotext": {"page": "sample_page", "title": "Information", "content": "Give the user some explanation."},
    }
    return render(request, "development_components.html", template_data)


def development_rendered(request, filename):
    fixtures_directory = os.path.join(settings.STATICFILES_DIRS[0], "ts", "rendered")
    try:
        with open(os.path.join(fixtures_directory, filename), encoding="utf-8") as fixture:
            return HttpResponse(fixture)
    except (FileNotFoundError, ValueError, OSError) as e:
        raise BadRequest from e
