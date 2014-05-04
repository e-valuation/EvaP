import getpass
from optparse import make_option
import sys

from django.core import exceptions
from django.core.management.base import BaseCommand
from django.contrib.auth.management.commands.createsuperuser import RE_VALID_USERNAME, EMAIL_RE
from django.utils.translation import ugettext as _

from evap.evaluation.models import User, UserProfile


def is_valid_email(value):
    if not EMAIL_RE.search(value):
        raise exceptions.ValidationError(_('Enter a valid email address.\n'))


def is_valid_username(username):
    if not RE_VALID_USERNAME.match(username):
        raise exceptions.ValidationError(_("Error: That username is invalid. Use only letters, digits and underscores.\n"))

    try:
        User.objects.get(username__iexact=username)
    except User.DoesNotExist:
        pass
    else:
        raise exceptions.ValidationError(_("Error: That username is already taken.\n"))


def is_valid_bool_answer(answer):
    if answer not in ['Yes', 'yes', 'No', 'no']:
        raise exceptions.ValidationError(_("Error: Please answer with yes or no\n"))


def read_value(question, validator_func):
    while True:
        value = raw_input(question)
        try:
            validator_func(value)
        except exceptions.ValidationError, e:
            sys.stderr.write(str(e.messages[0]))
            continue
        else:
            return value

def read_value_hidden(question, validator_func):
    while True:
        value = getpass.getpass(question)
        try:
            validator_func(value)
        except exceptions.ValidationError, e:
            sys.stderr.write(str(e.messages[0]))
            continue
        else:
            return value

class Command(BaseCommand):
    args = ''
    help = 'Creates a user'

    option_list = BaseCommand.option_list + (
         make_option('-p',
             action='store_true',
             dest='has_password',
             default=False,
             help='The user to be created should have a password set in the DB (for development)'),
         )

    def handle(self, *args, **options):
        try:
            # Get a username
            username = read_value('Username: ', is_valid_username)

            # Get an email
            email = read_value('Email address: ', is_valid_email)

            # Get password if it should be set
            password = read_value_hidden('Password: ', lambda x: True) if options["has_password"] else None

            # get fsr flag
            is_fsr = True if read_value("Is student representative (yes/no): ", is_valid_bool_answer) in ['Yes', 'yes'] else False

            # create user
            user = User.objects.create(username=username, email=email, is_staff=is_fsr, is_superuser=is_fsr)
            if not password is None:
                user.set_password(password)
                user.save()
            profile = UserProfile.get_for_user(user)
            profile.save()

        except KeyboardInterrupt:
            sys.stderr.write("\nOperation cancelled.\n")
            sys.exit(1)
