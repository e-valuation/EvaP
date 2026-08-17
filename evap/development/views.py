from django.http import HttpRequest, HttpResponse
from django.shortcuts import render


def development_components(request: HttpRequest) -> HttpResponse:
    theme_colors = ["primary", "secondary", "success", "info", "warning", "danger", "light", "dark"]
    template_data = {
        "theme_colors": theme_colors,
        "infotext": {"page": "sample_page", "title": "Information", "content": "Give the user some explanation."},
    }
    return render(request, "development_components.html", template_data)
