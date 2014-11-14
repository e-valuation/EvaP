from evap.rewards.models import RewardPointRedemption, RewardPointRedemptionEvent

from django.utils.translation import ugettext as _

from operator import attrgetter

from collections import OrderedDict
from collections import defaultdict
import datetime
import xlwt

from operator import itemgetter

from evap.results.exporters import writen, writec


class ExcelExporter(object):

    def __init__(self, reward_point_redemptions):
        self.reward_point_redemptions = reward_point_redemptions

    styles = {
        'default':       xlwt.Style.default_style,
        'bold':          xlwt.easyxf('font: bold on'),
    }

    def export(self, response):
        redemptions = self.reward_point_redemptions
        redemptions = sorted(redemptions, key=attrgetter('user_profile.user.last_name', 'user_profile.user.first_name'))

        self.workbook = xlwt.Workbook()
        self.sheet = self.workbook.add_sheet(_(u"Redemptions"))
        self.row = 0
        self.col = 0

        writec(self, _("Last name"), "bold")
        writec(self, _("First name"), "bold")
        writec(self, _("Email address"), "bold")
        writec(self, _("Number of points"), "bold")

        for redemption in redemptions:
            user = redemption.user_profile.user
            writen(self, user.last_name, "default")
            writec(self, user.first_name, "default")
            writec(self, user.email, "default")
            writec(self, redemption.value, "default")

        self.workbook.save(response)
