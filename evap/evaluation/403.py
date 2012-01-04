# the functionality to show a custom 403 page is missing in Django 1.3
# so we provide a custom one here
import django.http
import django.template
import django.template.loader

def fallback_403(request):
  """
Fallback 403 handler which prints out a hard-coded string patterned
after the Apache default 403 page.

Templates: None
Context: None
"""
  return django.http.HttpResponseForbidden(
      _("""<!DOCTYPE HTML PUBLIC "-//IETF//DTD HTML 2.0//EN">
<html><head>
<title>403 Forbidden</title>
</head><body>
<h1>Forbidden</h1>
<p>You don't have permission to access %(path)s on this server.</p>
<hr>
</body></html>""") % {'path': request.path})

def access_denied(request, template_name='403.html'):
  """
Default 403 handler, which looks for the which prints out a hard-coded string patterned
after the Apache default 403 page.

Templates: `403.html`
Context:
request
The django request object
"""
  t = django.template.loader.get_template(template_name)
  template_values = {}
  template_values['request'] = request
  return django.http.HttpResponseForbidden(
      t.render(django.template.RequestContext(request, template_values)))

class Django403Middleware(object):
  """Replaces vanilla django.http.HttpResponseForbidden() responses
with a rendering of 403.html
"""
  def process_response(self, request, response):
    # If the response object is a vanilla 403 constructed with
    # django.http.HttpResponseForbidden() then call our custom 403 view
    # function
    if isinstance(response, django.http.HttpResponseForbidden) and \
        set(dir(response)) == set(dir(django.http.HttpResponseForbidden())):
      try:
        return access_denied(request)
      except django.template.TemplateDoesNotExist, e:
        return fallback_403(request)

    return response

