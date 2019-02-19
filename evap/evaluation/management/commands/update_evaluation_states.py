from django.core.management.base import BaseCommand

from evap.evaluation.models import Evaluation
from evap.evaluation.management.commands.tools import log_exceptions


@log_exceptions
class Command(BaseCommand):
    help = 'Updates the state of all evaluations whose evaluation period starts or ends today.'

    def handle(self, *args, **options):
        Evaluation.update_evaluations()
