from django.core.management.base import BaseCommand

from evap.evaluation.models import UserProfile
from evap.evaluation.merge import merge_model_objects


class Command(BaseCommand):
    args = '<primary user ID> <duplicate user ID>'
    help = 'Merges duplicate user into primary user'

    def handle(self, *args, **options):
        try:
            user1 = UserProfile.objects.get(pk=int(args[0]))
            user2 = UserProfile.objects.get(pk=int(args[1]))

            self.stdout.write("Merging user '{1}' into user '{0}'".format(user1, user2))
            merge_model_objects(user1, user2)
        except Exception:
            import traceback
            traceback.print_exc()
