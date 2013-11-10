import getpass
import ldap
import sys

from django.core import exceptions
from django.core.management.base import BaseCommand
from django.contrib.auth.management.commands.createsuperuser import RE_VALID_USERNAME, EMAIL_RE
from django.utils.translation import ugettext as _

from evap.evaluation.models import User, UserProfile


class Command(BaseCommand):
    args = '<ldap server> <username>'
    help = 'Imports user data from Active Directory. The username should be specified with realm.'
    
    def handle(self, *args, **options):
        try:
            # connect
            l = ldap.initialize(args[0])
            
            # bind
            l.bind_s(args[1], getpass.getpass("AD Password: "))
            
            # find all users
            result = l.search_s("OU=INSTITUT,DC=hpi,DC=uni-potsdam,DC=de", ldap.SCOPE_SUBTREE, filterstr="(&(&(objectClass=user)(!(objectClass=computer)))(givenName=*)(sn=*)(mail=*))")
            for dn, attrs in result:
                try:
                    user = User.objects.get(username__iexact=attrs['sAMAccountName'][0])
                    user.first_name = attrs['givenName'][0]
                    user.last_name = attrs['sn'][0]
                    user.email = attrs['mail'][0]
                    user.save()
                    
                    p = UserProfile.get_for_user(user)
                    if not p.is_lecturer:
                        p.is_lecturer = dn.endswith("OU=Mitarbeiter,OU=INSTITUT,DC=hpi,DC=uni-potsdam,DC=de")
                    p.save()
                    
                    print "Successfully updated: '{0}'".format(user.username)
                except User.DoesNotExist:
                    pass
                except Exception as e:
                    print e
            
            l.unbind_s()
        
        except KeyboardInterrupt:
            sys.stderr.write("\nOperation cancelled.\n")
            sys.exit(1)
