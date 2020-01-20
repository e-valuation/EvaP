from django.utils.translation import ugettext as _

import xlwt

from evap.results.exporters import writen, writec


class ExcelExporter():

    def __init__(self, redemptions_by_user):
        self.redemptions_by_user = redemptions_by_user

        self.styles = {
            'default':       xlwt.Style.default_style,
            'bold':          xlwt.easyxf('font: bold on'),
        }

        self.workbook = xlwt.Workbook()
        self.sheet = self.workbook.add_sheet(_("Redemptions"))
        self.row = 0
        self.col = 0

    def export(self, response):
        redemptions_dict = self.redemptions_by_user

        writec(self, _("Last name"), "bold")
        writec(self, _("First name"), "bold")
        writec(self, _("Email address"), "bold")
        writec(self, _("Number of points"), "bold")

        for user, value in redemptions_dict.items():
            writen(self, user.last_name, "default")
            writec(self, user.first_name, "default")
            writec(self, user.email, "default")
            writec(self, value, "default")

        self.workbook.save(response)
