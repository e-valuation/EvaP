import logging
import sys

from django.conf import settings

logger = logging.getLogger(__name__)


def confirm_harmful_operation(output):
    """Usage: Abort if it does not return true"""

    if input("Are you sure you want to continue? (yes/no) ") != "yes":
        output.write("Aborting...")
        return False
    output.write("")

    if not settings.DEBUG:
        output.write("DEBUG is disabled. Are you sure you are not running")
        if input("on a production system and want to continue? (yes/no) ") != "yes":
            output.write("Aborting...")
            return False
        output.write("")

    return True


def log_exceptions(cls):
    """
    This decorator is meant to decorate management commands.
    Any exceptions raised in the command's handle method will be logged and re-raised.
    Can be replaced if https://code.djangoproject.com/ticket/27877 gets implemented.
    """

    class NewClass(cls):
        def handle(self, *args, **options):
            try:
                super().handle(args, options)
            except Exception:
                logger.exception("Management command '{}' failed. Traceback follows: ".format(sys.argv[1]))
                raise

    return NewClass
