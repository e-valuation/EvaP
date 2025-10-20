from collections.abc import Callable
from typing import TypeAlias
from weakref import WeakSet

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.utils import translation
from django.views import View
from mozilla_django_oidc.views import OIDCAuthenticationCallbackView, OIDCAuthenticationRequestView

ViewFuncOrClass: TypeAlias = Callable | View

VIEWS_WITHOUT_LOGIN_REQUIRED: WeakSet[ViewFuncOrClass] = WeakSet()
VIEWS_WITHOUT_LOGIN_REQUIRED.add(OIDCAuthenticationCallbackView)
VIEWS_WITHOUT_LOGIN_REQUIRED.add(OIDCAuthenticationRequestView)


class RequireLoginMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    @staticmethod
    def _is_or_wraps_view_not_requiring_login(view: ViewFuncOrClass) -> bool:
        if view in VIEWS_WITHOUT_LOGIN_REQUIRED:
            return True

        if hasattr(view, "__wrapped__"):
            return RequireLoginMiddleware._is_or_wraps_view_not_requiring_login(view.__wrapped__)

        return False

    @classmethod
    def process_view(cls, request, view_func, _view_args, _view_kwargs):
        # Returning None tells django to pass the request on
        if request.user.is_authenticated:
            return None

        view = getattr(view_func, "view_class", view_func)
        if cls._is_or_wraps_view_not_requiring_login(view):
            return None

        return redirect_to_login(request.get_full_path())


def no_login_required(class_or_function: ViewFuncOrClass):
    # view funcs of class based views are shared, so we cannot track them here. Use the decorator on the class instead.
    assert not hasattr(class_or_function, "view_class"), "unexpected called with a view function of a class based view"

    VIEWS_WITHOUT_LOGIN_REQUIRED.add(class_or_function)
    return class_or_function


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
