from functools import wraps

from django.core.exceptions import PermissionDenied
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.views import redirect_to_login
from django.utils.decorators import available_attrs

from evap.evaluation.models import UserProfile


class RequestAuthUserBackend(ModelBackend):
    """
    The RequestAuthBackend works together with the login_key_authentication view
    in evaluation/views.py to allow authentication of users via URL parameters,
    i.e. supplied in an email.

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


def internal_required(view_func):
    """
    Decorator for views that checks that the user is logged in and not an external user
    """
    def check_user(user):
        return not user.is_external
    return user_passes_test(check_user)(view_func)


def manager_required(view_func):
    """
    Decorator for views that checks that the user is logged in and a manager
    """
    def check_user(user):
        return user.is_manager
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


def grade_publisher_or_manager_required(view_func):
    """
    Decorator for views that checks that the user is logged in and a grade publisher or a manager
    """
    def check_user(user):
        return user.is_grade_publisher or user.is_manager
    return user_passes_test(check_user)(view_func)


def grade_downloader_required(view_func):
    """
    Decorator for views that checks that the user is logged in and can download grades
    """
    def check_user(user):
        return user.can_download_grades
    return user_passes_test(check_user)(view_func)


def responsible_or_contributor_or_delegate_required(view_func):
    """
    Decorator for views that checks that the user is logged in, is responsible for a course, or is a contributor, or is
    a delegate.
    """
    def check_user(user):
        return user.is_responsible_or_contributor_or_delegate
    return user_passes_test(check_user)(view_func)


def editor_or_delegate_required(view_func):
    """
    Decorator for views that checks that the user is logged in, has edit rights
    for at least one evaluation or is a delegate for such a person.
    """
    def check_user(user):
        return user.is_editor_or_delegate
    return user_passes_test(check_user)(view_func)


def editor_required(view_func):
    """
    Decorator for views that checks that the user is logged in and has edit
    right for at least one evaluation.
    """
    def check_user(user):
        return user.is_editor
    return user_passes_test(check_user)(view_func)


def participant_required(view_func):
    """
    Decorator for views that checks that the user is logged in and
    participates in at least one evaluation.
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
