from django.core.management.commands.loaddata import Command as LoadDataCommand

from evap.evaluation.models_logging import disable_logentries


class Command(LoadDataCommand):
    args = ""
    help = "Loads the test data without creating evaluation log entries."

    @disable_logentries()
    def handle(self, *args, **options):
        super().handle(*args, **options)
