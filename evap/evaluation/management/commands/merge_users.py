from django.core.management.base import BaseCommand

from django.contrib.auth.models import User
from evap.evaluation.merge import merge_model_objects

class Command(BaseCommand):
    args = '<user ID 1> <user ID 2>'
    help = 'Merge two users'
    
    def handle(self, *args, **options):
        try:
            user1 = User.objects.get(pk=int(args[0]))
            user2 = User.objects.get(pk=int(args[1]))
            
            print "Merging user '{1}' into user '{0}'".format(user1, user2)            
            merge_model_objects(user1, user2)            
        except Exception as e:
            import traceback
            traceback.print_exc()
