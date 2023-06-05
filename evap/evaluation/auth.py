from functools import wraps
from typing import Callable
import inspect

from django.utils.decorators import method_decorator
from django.contrib.auth.backends import ModelBackend
from django.core.exceptions import PermissionDenied
from mozilla_django_oidc.auth import OIDCAuthenticationBackend

from evap.evaluation.models import UserProfile
from evap.evaluation.tools import clean_email
from evap.rewards.tools import can_reward_points_be_used_by


class RequestAuthUserBackend(ModelBackend):
    """
    The RequestAuthBackend works together with the login_key_authentication view
    in evaluation/views.py to allow authentication of users via URL parameters,
    i.e. supplied in an email.

    It looks for the appropriate key in the login_key field of the UserProfile.
    """

    # Having a different method signature is okay according to django documentation:
    # https://docs.djangoproject.com/en/3.0/topics/auth/customizing/#writing-an-authentication-backend
    def authenticate(self, request, key):  # pylint: disable=arguments-differ
        if not key:
            return None

        try:
            user = UserProfile.objects.get(login_key=key)
            return user
        except UserProfile.DoesNotExist:
            return None


class EmailAuthenticationBackend(ModelBackend):
    # https://docs.djangoproject.com/en/3.1/topics/auth/customizing/#writing-an-authentication-backend
    def authenticate(self, request, email=None, password=None):  # pylint: disable=arguments-differ,arguments-renamed
        try:
            user = UserProfile.objects.get(email=email)
        except UserProfile.DoesNotExist:
            return None

        if user.check_password(password):
            return user

        return None


def class_or_function_check_decorator(test_func: Callable[[UserProfile], bool]):
    def function_decorator(func):
        @wraps(func)
        def wrapped(request, *args, **kwargs):
            if not test_func(request.user):
                raise PermissionDenied
            return func(request, *args, **kwargs)

        return wrapped

    def decorator(class_or_function):
        if inspect.isclass(class_or_function):
            return method_decorator(function_decorator, name="dispatch")(class_or_function)

        assert inspect.isfunction(class_or_function)
        return function_decorator(class_or_function)

    return decorator


@class_or_function_check_decorator
def internal_required(user):
    return not user.is_external


@class_or_function_check_decorator
def staff_permission_required(user):
    return user.has_staff_permission


@class_or_function_check_decorator
def manager_required(user):
    return user.is_manager


@class_or_function_check_decorator
def reviewer_required(user):
    return user.is_reviewer


@class_or_function_check_decorator
def grade_publisher_required(user):
    return user.is_grade_publisher


@class_or_function_check_decorator
def grade_publisher_or_manager_required(user):
    """
    Decorator for views that checks that the user is logged in and a grade publisher or a manager
    """
    return user.is_grade_publisher or user.is_manager


@class_or_function_check_decorator
def grade_downloader_required(user):
    """
    Decorator for views that checks that the user is logged in and can download grades
    """
    return user.can_download_grades


@class_or_function_check_decorator
def responsible_or_contributor_or_delegate_required(user):
    """
    Decorator for views that checks that the user is logged in, is responsible for a course, or is a contributor, or is
    a delegate.
    """
    return user.is_responsible_or_contributor_or_delegate


@class_or_function_check_decorator
def editor_or_delegate_required(user):
    """
    Decorator for views that checks that the user is logged in, has edit rights
    for at least one evaluation or is a delegate for such a person.
    """
    return user.is_editor_or_delegate


@class_or_function_check_decorator
def editor_required(user):
    """
    Decorator for views that checks that the user is logged in and has edit
    right for at least one evaluation.
    """
    return user.is_editor


@class_or_function_check_decorator
def participant_required(user):
    """
    Decorator for views that checks that the user is logged in and
    participates in at least one evaluation.
    """
    return user.is_participant


@class_or_function_check_decorator
def reward_user_required(user):
    """
    Decorator for views that checks that the user is logged in and can use
    reward points.
    """
    return can_reward_points_be_used_by(user)


# see https://mozilla-django-oidc.readthedocs.io/en/stable/
class OpenIDAuthenticationBackend(OIDCAuthenticationBackend):
    def filter_users_by_claims(self, claims):
        email = claims.get("email")
        if not email:
            return []

        try:
            return [self.UserModel.objects.get(email=clean_email(email))]
        except UserProfile.DoesNotExist:
            return []

    def create_user(self, claims):
        user = self.UserModel.objects.create(
            email=claims.get("email"),
            first_name_given=claims.get("given_name", ""),
            last_name=claims.get("family_name", ""),
        )
        return user

    def update_user(self, user, claims):
        if not user.first_name_given:
            user.first_name_given = claims.get("given_name", "")
            user.save()
        if not user.last_name:
            user.last_name = claims.get("family_name", "")
            user.save()
        return user
