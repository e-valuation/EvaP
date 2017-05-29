from django.core.management.base import BaseCommand
from django.core.serializers.base import ProgressBar
from django.core.cache import cache

from evap.evaluation.models import Course
from evap.evaluation.tools import calculate_results


class Command(BaseCommand):
    args = ''
    help = 'Clears the cache and pre-warms it with the results of all courses'

    def handle(self, *args, **options):
        self.stdout.write("Clearing cache...")
        cache.clear()
        total_count = Course.objects.count()

        self.stdout.write("Calculating results for all courses...")

        self.stdout.ending = None
        progress_bar = ProgressBar(self.stdout, total_count)

        for counter, course in enumerate(Course.objects.all()):
            progress_bar.update(counter + 1)
            calculate_results(course)

        self.stdout.write("Results cache has been refreshed.\n")
