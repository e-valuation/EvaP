import datetime
from abc import ABC, abstractmethod
from typing import Any, Mapping, Optional, Type, TypeVar
from urllib.parse import quote

import xlwt
from django.conf import settings
from django.core.exceptions import SuspiciousOperation, ValidationError
from django.db.models import Model
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.translation import get_language

M = TypeVar("M", bound=Model)


def get_object_from_dict_pk_entry_or_logged_40x(model_cls: Type[M], dict_obj: Mapping[str, Any], key: str) -> M:
    try:
        return get_object_or_404(model_cls, pk=dict_obj[key])
    # ValidationError happens for UUID id fields when passing invalid arguments
    except (KeyError, ValueError, ValidationError) as e:
        raise SuspiciousOperation from e


# TODO: Test
def is_m2m_prefetched(instance, attribute_name):
    """
    Is the given M2M-attribute prefetched? Can be used to do ordering or counting
    in python and avoid additional database queries
    """
    return hasattr(instance, "_prefetched_objects_cache") and attribute_name in instance._prefetched_objects_cache


def is_external_email(email):
    return not any(email.endswith("@" + domain) for domain in settings.INSTITUTION_EMAIL_DOMAINS)


def sort_formset(request, formset):
    if request.POST:  # if not, there will be no cleaned_data and the models should already be sorted anyways
        formset.is_valid()  # make sure all forms have cleaned_data
        formset.forms.sort(key=lambda f: f.cleaned_data.get("order", 9001))


def date_to_datetime(date):
    return datetime.datetime(year=date.year, month=date.month, day=date.day)


def vote_end_datetime(vote_end_date):
    # The evaluation actually ends at EVALUATION_END_OFFSET_HOURS:00 of the day AFTER self.vote_end_date.
    return date_to_datetime(vote_end_date) + datetime.timedelta(hours=24 + settings.EVALUATION_END_OFFSET_HOURS)


def get_parameter_from_url_or_session(request, parameter, default=False):
    result = request.GET.get(parameter, None)
    if result is None:  # if no parameter is given take session value
        result = request.session.get(parameter, default)
    else:
        result = {"true": True, "false": False}.get(result.lower())  # convert parameter to boolean
    request.session[parameter] = result  # store value for session
    return result


def translate(**kwargs):
    # pylint is really buggy with this method.
    # pylint: disable=unused-variable, useless-suppression
    # get_language may return None if there is no session (e.g. during management commands)
    return property(lambda self: getattr(self, kwargs[get_language() or "en"]))


def clean_email(email):
    if email:
        email = email.strip().lower()
        # Replace email domains in case there are multiple alias domains used in the organisation and all emails should
        # have the same domain on EvaP.
        for original_domain, replaced_domain in settings.INSTITUTION_EMAIL_REPLACEMENTS:
            if email.endswith(original_domain):
                return email[: -len(original_domain)] + replaced_domain
    return email


def capitalize_first(string):
    return string[0].upper() + string[1:]


class FileResponse(HttpResponse):
    def __init__(self, filename, content_type=None, **kwargs):
        super().__init__(content_type=content_type, **kwargs)
        self.set_content_disposition(filename)

    def set_content_disposition(self, filename):
        try:
            filename.encode("ascii")
            self["Content-Disposition"] = f'attachment; filename="{filename}"'
        except UnicodeEncodeError:
            self["Content-Disposition"] = f"attachment; filename*=utf-8''{quote(filename)}"


class ExcelExporter(ABC):
    styles = {
        "default": xlwt.Style.default_style,
        "headline": xlwt.easyxf(
            "font: bold on, height 400; alignment: horiz centre, vert centre, wrap on; borders: bottom medium",
            num_format_str="0.0",
        ),
        "bold": xlwt.easyxf("font: bold on"),
        "italic": xlwt.easyxf("font: italic on"),
        "border_left_right": xlwt.easyxf("borders: left medium, right medium"),
        "border_top_bottom_right": xlwt.easyxf("borders: top medium, bottom medium, right medium"),
        "border_top": xlwt.easyxf("borders: top medium"),
    }

    # Derived classes can set this to
    # have a sheet added at initialization.
    default_sheet_name: Optional[str] = None

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
