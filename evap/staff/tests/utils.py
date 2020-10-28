import os
import time

from contextlib import contextmanager

from django_webtest import WebTest

from evap.evaluation.tests.tools import WebTestWith200Check
from evap.staff.tools import ImportType, generate_import_filename


def helper_enter_staff_mode(webtest):
    # This is a bit complicated in WebTest
    # See https://github.com/django-webtest/django-webtest/issues/68#issuecomment-350244293
    webtest.app.set_cookie('sessionid', 'initial')
    session = webtest.app.session
    session['staff_mode_start_time'] = time.time()
    session.save()
    webtest.app.set_cookie('sessionid', session.session_key)


def helper_exit_staff_mode(webtest):
    # This is a bit complicated in WebTest
    # See https://github.com/django-webtest/django-webtest/issues/68#issuecomment-350244293
    webtest.app.set_cookie('sessionid', 'initial')
    session = webtest.app.session
    if 'staff_mode_start_time' in session:
        del session['staff_mode_start_time']
    session.save()
    webtest.app.set_cookie('sessionid', session.session_key)


@contextmanager
def run_in_staff_mode(webtest):
    helper_enter_staff_mode(webtest)
    yield
    helper_exit_staff_mode(webtest)


class WebTestStaffMode(WebTest):
    def setUp(self):
        helper_enter_staff_mode(self)


class WebTestStaffModeWith200Check(WebTestWith200Check):
    def setUp(self):
        helper_enter_staff_mode(self)


def helper_delete_all_import_files(user_id):
    for import_type in ImportType:
        filename = generate_import_filename(user_id, import_type)
        try:
            os.remove(filename)
        except FileNotFoundError:
            pass


# For some form fields, like a <select> which can be configured to create new options,
# setting the value directly would be rejected by Webtest,
# as it would check whether all values are included in the options.
# To circumvent this, set the options beforehand with this helper.
def helper_set_dynamic_choices_field_value(field, value):
    field.options = [(name, False, name) for name in value]
    field.value = value
