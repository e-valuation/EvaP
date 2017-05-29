from django.core.management.base import BaseCommand

from evap.evaluation.models import Course


class Command(BaseCommand):
    help = 'Updates the state of all courses whose evaluation period starts or ends today.'

    def handle(self, *args, **options):
        Course.update_courses()
