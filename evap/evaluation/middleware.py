from django.utils.deprecation import MiddlewareMixin

from .models import LoggedModel


class LoggingRequestMiddleware(MiddlewareMixin):
    """Expose request to LoggedModel.
    This middleware sets request as a local thread variable, making it
    available to the model-level utilities to allow tracking of the
    authenticated user making a change.

    Taken from https://github.com/treyhunner/django-simple-history/
    """

    def process_request(self, request):
        LoggedModel.thread.request = request

    def process_response(self, request, response):
        if hasattr(LoggedModel.thread, "request"):
            del LoggedModel.thread.request
        return response
