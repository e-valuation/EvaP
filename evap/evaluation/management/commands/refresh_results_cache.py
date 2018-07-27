from django.core.management.base import BaseCommand
from django.core.serializers.base import ProgressBar
from django.core.cache import caches

from evap.evaluation.models import Course
from evap.results.tools import collect_results
from evap.results.views import warm_up_template_cache


class Command(BaseCommand):
    args = ''
    help = 'Clears the cache and pre-warms it with the results of all courses'
    requires_migrations_checks = True

    def handle(self, *args, **options):
        self.stdout.write("Clearing results cache...")
        caches['results'].clear()
        total_count = Course.objects.count()

        self.stdout.write("Calculating results for all courses...")

        self.stdout.ending = None
        progress_bar = ProgressBar(self.stdout, total_count)

        for counter, course in enumerate(Course.objects.all()):
            progress_bar.update(counter + 1)
            collect_results(course)

        self.stdout.write("Prerendering result index page...\n")

        warm_up_template_cache(Course.objects.filter(state='published'))

        self.stdout.write("Results cache has been refreshed.\n")
