from django.core.exceptions import ImproperlyConfigured
from django.contrib import auth, messages
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.decorators import user_passes_test
from django.utils.decorators import available_attrs
from django.utils.translation import ugettext_lazy as _

from evap.evaluation.models import UserProfile

from datetime import date
from functools import wraps


class RequestAuthMiddleware(object):
    """
    Middleware for utilizing request-based authentication.

    If request.user is not authenticated, then this middleware attempts to
    authenticate a user with the ``userkey`` URL variable.
    If authentication is successful, the user is automatically logged in to
    persist the user in the session.
    """

    field_name = "userkey"

    def process_request(self, request):
        # AuthenticationMiddleware is required so that request.user exists.
        if not hasattr(request, 'user'):
            raise ImproperlyConfigured(
                "The Django remote user auth middleware requires the"
                " authentication middleware to be installed.  Edit your"
                " MIDDLEWARE_CLASSES setting to insert"
                " 'django.contrib.auth.middleware.AuthenticationMiddleware'"
                " before the RequestAuthMiddleware class.")

        try:
            key = int(request.GET[self.field_name])
        except (KeyError, ValueError):
            # If specified variable doesn't exist or does not convert to an int
            # then return (leaving request.user set to AnonymousUser by the
            # AuthenticationMiddleware).
            return

        # We are seeing this user for the first time in this session, attempt
        # to authenticate the user.
        user = auth.authenticate(key=key)
        if user:
            # User is valid.  Set request.user and persist user in the session
            # by logging the user in.
            request.user = user
            auth.login(request, user)
        else:
            messages.warning(request, _(u"Invalid login key"))


class RequestAuthUserBackend(ModelBackend):
    """
    The RequestAuthBackend works together with the RequestAuthMiddleware to
    allow authentication of users via URL parameters, i.e. supplied in an
    email.

    It looks for the appropriate key in the login_key field of the UserProfile.
    """
    def authenticate(self, key):
        if not key:
            return None

        try:
            return UserProfile.objects.get(login_key=key, login_key_valid_until__gte=date.today())
        except UserProfile.DoesNotExist:
            return None

def login_required(func):
    """
    Decorator for views that checks that the user is logged in
    """
    def check_user(user):
        return user.is_authenticated()
    return user_passes_test(check_user)(func)


def fsr_required(func):
    """
    Decorator for views that checks that the user is logged in and member
    of the student representatives
    """

    def check_user(user):
        if not user.is_authenticated():
            return False
        return user.is_staff
    return user_passes_test(check_user)(func)


def editor_or_delegate_required(func):
    """
    Decorator for views that checks that the user is logged in, has edit rights
    for at least one course or is a delegate for such a person.
    """

    def check_user(user):
        if not user.is_authenticated():
            return False
        return user.is_editor_or_delegate
    return user_passes_test(check_user)(func)


def editor_required(func):
    """
    Decorator for views that checks that the user is logged in and has edit
    right for at least one course.
    """

    def check_user(user):
        if not user.is_authenticated():
            return False
        return user.is_editor
    return user_passes_test(check_user)(func)

def enrollment_required(func):
    """
    Decorator for views that checks that the user is logged in and is
    enrolled in at least one course.
    """

    def check_user(user):
        if not user.is_authenticated():
            return False
        return user.enrolled_in_courses
    return user_passes_test(check_user)(func)

def reward_user_required(func):
    """
    Decorator for views that checks that the user is logged in and can use
    reward points.
    """

    def check_user(user):
        from evap.rewards.tools import can_user_use_reward_points
        if not user.is_authenticated():
            return False
        return can_user_use_reward_points(user)
    return user_passes_test(check_user)(func)
