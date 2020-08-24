from django.utils.translation import gettext as _

from evap.evaluation.tools import ExcelExporter


class RewardsExporter(ExcelExporter):
    default_sheet_name = _("Redemptions")

    def export_impl(self, redemptions_by_user):
        self.write_row([
            _("Last name"),
            _("First name"),
            _("Email address"),
            _("Number of points"),
        ], "bold")

        for user, value in redemptions_by_user.items():
            self.write_row([
                user.last_name,
                user.first_name,
                user.email,
                value
            ])
