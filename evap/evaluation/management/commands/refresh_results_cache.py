from django.core.management.base import BaseCommand
from django.core.serializers.base import ProgressBar

from evap.evaluation.models import Evaluation
from evap.results.tools import (
    GET_RESULTS_PREFETCH_LOOKUPS,
    STATES_WITH_RESULT_TEMPLATE_CACHING,
    STATES_WITH_RESULTS_CACHING,
    cache_results,
)
from evap.results.views import update_template_cache


class Command(BaseCommand):
    args = ""
    help = "Clears the cache and pre-warms it with the results of all evaluations"
    requires_migrations_checks = True

    def handle(self, *args, **options):
        self.stdout.write("Calculating results for all evaluations...")

        self.stdout.ending = None
        evaluations = Evaluation.objects.filter(state__in=STATES_WITH_RESULTS_CACHING).prefetch_related(
            *GET_RESULTS_PREFETCH_LOOKUPS,
        )
        progress_bar = ProgressBar(self.stdout, evaluations.count())

        for counter, evaluation in enumerate(evaluations):
            progress_bar.update(counter + 1)
            cache_results(evaluation, refetch_related_objects=False)

        self.stdout.write("Prerendering result index page...\n")
        update_template_cache(Evaluation.objects.filter(state__in=STATES_WITH_RESULT_TEMPLATE_CACHING))

        self.stdout.write("Results cache has been refreshed.\n")
