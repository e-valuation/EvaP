from evap.rewards.models import RewardPointRedemption, RewardPointRedemptionEvent

from django.utils.translation import ugettext as _

from collections import OrderedDict
from collections import defaultdict
import datetime
import xlwt

from operator import itemgetter


class ExcelExporter(object):

    def __init__(self, event):
        self.event = event

    styles = {
        'default':       xlwt.Style.default_style,
        'bold':          xlwt.easyxf('font: bold on'),
    }

    def export(self, response):
        redemptions = []
        for redemption in self.event.reward_point_redemptions.all():
            redemptions.append((redemption.user_profile.user.last_name, redemption.user_profile.user.first_name, redemption.user_profile.user.email, redemption.value))

        redemptions.sort(key=itemgetter(0,1))

        self.workbook = xlwt.Workbook()
        self.sheet = self.workbook.add_sheet(_(u"Redemptions"))
        self.row = 0
        self.col = 0

        self.writec(_("Last name"), "bold")
        self.writec(_("First name"), "bold")
        self.writec(_("Email address"), "bold")
        self.writec(_("Number of points"), "bold")

        #self.writec(_(u"Evaluation {0} - created on {1}").format(self.semester.name, datetime.date.today()), "headline")
        for redemption in redemptions:
            self.writen(redemption[0], "default")
            self.writec(redemption[1], "default")
            self.writec(redemption[2], "default")
            self.writec(redemption[3], "default")

        self.workbook.save(response)

    def writen(self, label="", style_name="default"):
        """Write the cell at the beginning of the next row."""
        self.col = 0
        self.row += 1
        self.writec(label, style_name)

    def writec(self, label, style_name, rows=1, cols=1):
        """Write the cell in the next column of the current line."""
        self._write(label, ExcelExporter.styles[style_name], rows, cols )
        self.col += 1

    def _write(self, label, style, rows, cols):
        if rows > 1 or cols > 1:
            self.sheet.write_merge(self.row, self.row+rows-1, self.col, self.col+cols-1, label, style)
            self.col += cols - 1
        else:
            self.sheet.write(self.row, self.col, label, style)
