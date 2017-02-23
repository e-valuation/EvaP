import logging
import sys

logger = logging.getLogger(__name__)


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
