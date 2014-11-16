from evap.rewards.models import RewardPointRedemption, RewardPointRedemptionEvent

from django.utils.translation import ugettext as _

from collections import OrderedDict
from collections import defaultdict
import datetime
import xlwt

from operator import itemgetter

from evap.results.exporters import writen, writec


class ExcelExporter(object):

    def __init__(self, redemptions_by_user):
        self.redemptions_by_user = redemptions_by_user

    styles = {
        'default':       xlwt.Style.default_style,
        'bold':          xlwt.easyxf('font: bold on'),
    }

    def export(self, response):
        redemptions_dict = self.redemptions_by_user
        
        self.workbook = xlwt.Workbook()
        self.sheet = self.workbook.add_sheet(_(u"Redemptions"))
        self.row = 0
        self.col = 0

        writec(self, _("Last name"), "bold")
        writec(self, _("First name"), "bold")
        writec(self, _("Email address"), "bold")
        writec(self, _("Number of points"), "bold")

        for user_profile, value in redemptions_dict.items():
            writen(self, user_profile.user.last_name, "default")
            writec(self, user_profile.user.first_name, "default")
            writec(self, user_profile.user.email, "default")
            writec(self, value, "default")

        self.workbook.save(response)
