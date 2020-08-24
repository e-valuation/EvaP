from abc import ABC, abstractmethod
import datetime
from urllib.parse import quote
import xlwt

from django.conf import settings
from django.contrib.auth import user_logged_in
from django.dispatch import receiver
from django.http import HttpResponse
from django.utils import translation
from django.utils.translation import LANGUAGE_SESSION_KEY, get_language


def is_external_email(email):
    return not any([email.endswith("@" + domain) for domain in settings.INSTITUTION_EMAIL_DOMAINS])


def sort_formset(request, formset):
    if request.POST:  # if not, there will be no cleaned_data and the models should already be sorted anyways
        formset.is_valid()  # make sure all forms have cleaned_data
        formset.forms.sort(key=lambda f: f.cleaned_data.get("order", 9001))


def date_to_datetime(date):
    return datetime.datetime(year=date.year, month=date.month, day=date.day)


@receiver(user_logged_in)
def set_or_get_language(user, request, **_kwargs):
    if user.language:
        translation.activate(user.language)
    else:
        user.language = get_language()
        user.save()
    request.session[LANGUAGE_SESSION_KEY] = user.language


def get_parameter_from_url_or_session(request, parameter, default=False):
    result = request.GET.get(parameter, None)
    if result is None:  # if no parameter is given take session value
        result = request.session.get(parameter, default)
    else:
        result = {'true': True, 'false': False}.get(result.lower())  # convert parameter to boolean
    request.session[parameter] = result  # store value for session
    return result


def translate(**kwargs):
    # get_language may return None if there is no session (e.g. during management commands)
    return property(lambda self: getattr(self, kwargs[get_language() or 'en']))


def clean_email(email):
    if email:
        email = email.strip().lower()
        # Replace email domains in case there are multiple alias domains used in the organisation and all emails should
        # have the same domain on EvaP.
        for original_domain, replaced_domain in settings.INSTITUTION_EMAIL_REPLACEMENTS:
            if email.endswith(original_domain):
                return email[:-len(original_domain)] + replaced_domain
    return email


class FileResponse(HttpResponse):
    def __init__(self, filename, content_type=None, **kwargs):
        super().__init__(content_type=content_type, **kwargs)
        self.set_content_disposition(filename)

    def set_content_disposition(self, filename):
        try:
            filename.encode("ascii")
            self["Content-Disposition"] = f"attachment; filename=\"{filename}\""
        except UnicodeEncodeError:
            self["Content-Disposition"] = f"attachment; filename*=utf-8''{quote(filename)}"


class ExcelExporter(ABC):
    styles = {
        "default":                  xlwt.Style.default_style,
        "headline":                 xlwt.easyxf("font: bold on, height 400; alignment: horiz centre, vert centre, wrap on; borders: bottom medium", num_format_str="0.0"),
        "bold":                     xlwt.easyxf("font: bold on"),
        "italic":                   xlwt.easyxf("font: italic on"),
        "border_left_right":        xlwt.easyxf("borders: left medium, right medium"),
        "border_top_bottom_right":  xlwt.easyxf("borders: top medium, bottom medium, right medium"),
        "border_top":               xlwt.easyxf("borders: top medium"),
    }

    # Derived classes can set this to
    # have a sheet added at initialization.
    default_sheet_name = None

    def __init__(self):
        self.workbook = xlwt.Workbook()
        self.cur_row = 0
        self.cur_col = 0
        if self.default_sheet_name is not None:
            self.cur_sheet = self.workbook.add_sheet(self.default_sheet_name)
        else:
            self.cur_sheet = None

    def write_cell(self, label="", style="default"):
        """Write a single cell and move to the next column."""
        self.cur_sheet.write(
            self.cur_row,
            self.cur_col,
            label,
            self.styles[style],
        )
        self.cur_col += 1

    def next_row(self):
        self.cur_col = 0
        self.cur_row += 1

    def write_row(self, vals, style="default"):
        """
        Write a cell for every value and go to the next row.
        Styling can be chosen
          - once for all cells by providing a string.
          - separately for every value, based on a callable that maps the value to a style name.
        """
        for val in vals:
            self.write_cell(val, style=style(val) if callable(style) else style)
        self.next_row()

    def write_empty_row_with_styles(self, styles):
        for style in styles:
            self.write_cell(None, style)
        self.next_row()

    @abstractmethod
    def export_impl(self, *args, **kwargs):
        """Specify the logic to insert the data into the sheet here."""

    def export(self, response, *args, **kwargs):
        """Convenience method to avoid some boilerplate."""
        self.export_impl(*args, **kwargs)
        self.workbook.save(response)
