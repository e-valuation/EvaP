from django.shortcuts import render


def development_components(request):
    theme_colors = ['primary', 'secondary', 'success', 'info', 'warning', 'danger', 'light', 'dark']
    template_data = {
        'theme_colors': theme_colors,
    }
    return render(request, 'development_components.html', template_data)
