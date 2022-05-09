from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.utils import translation


class RequireLoginMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    @staticmethod
    def process_view(request, view_func, _view_args, _view_kwargs):
        # Returning None tells django to pass the request on
        if request.user.is_authenticated:
            return None

        if "no_login_required" in view_func.__dict__ and view_func.no_login_required:
            return None

        if hasattr(view_func, "view_class") and view_func.view_class.__name__ in [
            "OIDCAuthenticationRequestView",
            "OIDCAuthenticationCallbackView",
        ]:
            return None

        return redirect_to_login(request.get_full_path())


def no_login_required(func):
    func.no_login_required = True
    return func


def user_language_middleware(get_response):
    def middleware(request):
        if not (request.user and request.user.is_authenticated):
            return get_response(request)
        if request.user.language == translation.get_language():
            return get_response(request)

        if request.user.language:
            translation.activate(request.user.language)
        else:
            request.user.language = translation.get_language()
            request.user.save()
        lang = request.user.language
        response = get_response(request)
        response.set_cookie(settings.LANGUAGE_COOKIE_NAME, lang)
        return response

    return middleware
