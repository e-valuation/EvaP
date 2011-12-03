import sys

from django.core import exceptions
from django.core.management.base import BaseCommand
from django.contrib.auth.management.commands.createsuperuser import RE_VALID_USERNAME, EMAIL_RE
from django.utils.translation import ugettext as _

from evap.evaluation.models import User


def is_valid_email(value):
    if not EMAIL_RE.search(value):
        raise exceptions.ValidationError(_('Enter a valid e-mail address.\n'))


def is_valid_username(username):
    if not RE_VALID_USERNAME.match(username):
        raise exceptions.ValidationError(_("Error: That username is invalid. Use only letters, digits and underscores.\n"))
    
    try:
        User.objects.get(username=username)
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


class Command(BaseCommand):
    args = ''
    help = 'Creates a user'
    
    def handle(self, *args, **options):
        try:
            # Get a username
            username = read_value('Username: ', is_valid_username)
            
            # Get an email
            email = read_value('E-mail address: ', is_valid_email)
            
            # get fsr flag
            is_fsr = True if read_value("Is FSR member (yes/no): ", is_valid_bool_answer) in ['Yes', 'yes'] else False
            
            # get lecturer flag
            is_lecturer = True if read_value("Is lecturer (yes/no): ", is_valid_bool_answer) in ['Yes', 'yes'] else False
            
            # create user
            u = User.objects.create(username=username, email=email, is_staff=is_fsr)
            p = u.get_profile()
            p.is_lecturer = is_lecturer
            p.save()
            
        except KeyboardInterrupt:
            sys.stderr.write("\nOperation cancelled.\n")
            sys.exit(1)
