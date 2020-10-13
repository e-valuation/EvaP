import time

from django.contrib import messages
from django.utils.translation import ugettext as _

from evap.settings import STAFF_MODE_TIMEOUT, STAFF_MODE_INFO_TIMEOUT
from evap.staff.tools import delete_navbar_cache_for_users


def staff_mode_middleware(get_response):
    """
    Middleware handling the staff mode.

    If too much time has passed, the staff mode will be exited.
    Otherwise, the last request time will be updated.
    """

    def middleware(request):
        if is_in_staff_mode(request):
            current_time = time.time()
            if current_time <= request.session.get('staff_mode_start_time', 0) + STAFF_MODE_TIMEOUT:
                # just refresh time
                update_staff_mode(request)
            else:
                exit_staff_mode(request)
                # only show info message if not too much time has passed
                if current_time <= request.session.get('staff_mode_start_time', 0) + STAFF_MODE_TIMEOUT + STAFF_MODE_INFO_TIMEOUT:
                    messages.info(request, _("Your staff mode timed out."))

        if is_in_staff_mode(request):
            request.user.is_participant = False
            request.user.is_student = False
            request.user.is_editor = False
            request.user.is_contributor = False
            request.user.is_delegate = False
            request.user.is_responsible = False
            request.user.is_responsible_or_contributor_or_delegate = False
        else:
            request.user.is_staff = False
            request.user.is_manager = False
            request.user.is_reviewer = False

        response = get_response(request)
        return response

    return middleware


def is_in_staff_mode(request):
    return 'staff_mode_start_time' in request.session


def update_staff_mode(request):
    assert request.user.has_staff_permission

    request.session['staff_mode_start_time'] = time.time()
    request.session.modified = True


def enter_staff_mode(request):
    update_staff_mode(request)
    delete_navbar_cache_for_users([request.user])


def exit_staff_mode(request):
    if is_in_staff_mode(request):
        del request.session['staff_mode_start_time']
        request.session.modified = True
        delete_navbar_cache_for_users([request.user])
