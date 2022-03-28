import uuid

from evap.evaluation.models_logging import LoggedModel


class LoggingRequestMiddleware:
    """Expose request to LoggedModel.
    This middleware sets request as a local thread variable, making it
    available to the model-level utilities to allow tracking of the
    authenticated user making a change.

    Taken from https://github.com/treyhunner/django-simple-history/
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        LoggedModel.thread.request = request
        LoggedModel.thread.request_id = str(uuid.uuid4())

        try:
            # django documentation says to just do this without the try, and that exceptions will be handled:
            # https://docs.djangoproject.com/en/4.0/topics/http/middleware/#writing-your-own-middleware
            # However, django-webtest sets DEBUG_PROPAGATE_EXCEPTIONS, and propagated exceptions caused our deletion to
            # be skipped, leading to weird errors in the tests executed afterwards. See #1727.
            response = self.get_response(request)
        finally:
            del LoggedModel.thread.request
            del LoggedModel.thread.request_id

        return response
