from datetime import date, timedelta
from functools import wraps

from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from django.contrib import auth, messages
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.views import redirect_to_login
from django.utils.decorators import available_attrs
from django.utils.translation import ugettext_lazy as _

from evap.evaluation.models import UserProfile, EmailTemplate


class RequestAuthMiddleware(object):
    """
    Middleware for utilizing request-based authentication.

    If request.user is not authenticated, then this middleware attempts to
    authenticate a user with the ``loginkey`` URL variable.
    If authentication is successful, the user is automatically logged in to
    persist the user in the session.
    """

    field_name = "loginkey"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        self.process_request(request)
        response = self.get_response(request)
        return response

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

        # We are seeing this user for the first time in this session, attempt to authenticate the user.
        user = auth.authenticate(request, key=key)

        if user and not user.is_active:
            messages.error(request, _("Inactive users are not allowed to login."))
            return

        # If we already have an authenticated user don't try to login a new user. Show an error message if another user
        # tries to login with a URL in this situation.
        if request.user.is_authenticated:
            if user != request.user:
                messages.error(request, _("Another user is currently logged in. Please logout first and then use the login URL again."))
            return

        if user and user.login_key_valid_until >= date.today():
            # User is valid. Set request.user and persist user in the session by logging the user in.
            request.user = user
            auth.login(request, user)
            messages.success(request, _("Logged in as %s.") % user.full_name)
            # Invalidate the login key (set to yesterday).
            user.login_key_valid_until = date.today() - timedelta(1)
            user.save()
        elif user:
            # A user exists, but the login key is not valid anymore. Send the user a new one.
            user.generate_login_key()
            EmailTemplate.send_login_url_to_user(user)
            messages.warning(request, _("The login URL was already used. We sent you a new one to your email address."))
        else:
            messages.warning(request, _("Invalid login URL. Please request a new one below."))


class RequestAuthUserBackend(ModelBackend):
    """
    The RequestAuthBackend works together with the RequestAuthMiddleware to
    allow authentication of users via URL parameters, i.e. supplied in an
    email.

    It looks for the appropriate key in the login_key field of the UserProfile.
    """
    def authenticate(self, request, key):
        if not key:
            return None

        try:
            return UserProfile.objects.get(login_key=key)
        except UserProfile.DoesNotExist:
            return None


def user_passes_test(test_func):
    """
    Decorator for views that checks whether users are authenticated
    (redirecting to login if not) and pass a given test (raising 403
    if not). The test should be a callable
    that takes the user object and returns True if the user passes.
    """
    def decorator(view_func):
        @wraps(view_func, assigned=available_attrs(view_func))
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if not test_func(request.user):
                raise PermissionDenied()
            else:
                return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator


def staff_required(view_func):
    """
    Decorator for views that checks that the user is logged in and a staff member
    """
    def check_user(user):
        return user.is_staff
    return user_passes_test(check_user)(view_func)


def reviewer_required(view_func):
    """
    Decorator for views that checks that the user is logged in and a reviewer
    """
    def check_user(user):
        return user.is_reviewer
    return user_passes_test(check_user)(view_func)


def grade_publisher_required(view_func):
    """
    Decorator for views that checks that the user is logged in and a grade publisher
    """
    def check_user(user):
        return user.is_grade_publisher
    return user_passes_test(check_user)(view_func)


def grade_publisher_or_staff_required(view_func):
    """
    Decorator for views that checks that the user is logged in and a grade publisher or a staff member
    """
    def check_user(user):
        return user.is_grade_publisher or user.is_staff
    return user_passes_test(check_user)(view_func)


def grade_downloader_required(view_func):
    """
    Decorator for views that checks that the user is logged in and can download grades
    """
    def check_user(user):
        return user.can_download_grades
    return user_passes_test(check_user)(view_func)


def contributor_or_delegate_required(view_func):
    """
    Decorator for views that checks that the user is logged in, has edit rights
    for at least one course or is a delegate for such a person or is a
    contributor.
    """
    def check_user(user):
        return user.is_contributor_or_delegate
    return user_passes_test(check_user)(view_func)


def editor_or_delegate_required(view_func):
    """
    Decorator for views that checks that the user is logged in, has edit rights
    for at least one course or is a delegate for such a person.
    """
    def check_user(user):
        return user.is_editor_or_delegate
    return user_passes_test(check_user)(view_func)


def editor_required(view_func):
    """
    Decorator for views that checks that the user is logged in and has edit
    right for at least one course.
    """
    def check_user(user):
        return user.is_editor
    return user_passes_test(check_user)(view_func)


def participant_required(view_func):
    """
    Decorator for views that checks that the user is logged in and
    participates in at least one course.
    """
    def check_user(user):
        return user.is_participant
    return user_passes_test(check_user)(view_func)


def reward_user_required(view_func):
    """
    Decorator for views that checks that the user is logged in and can use
    reward points.
    """
    def check_user(user):
        from evap.rewards.tools import can_user_use_reward_points
        return can_user_use_reward_points(user)
    return user_passes_test(check_user)(view_func)
