import datetime
import typing
from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any, TypeVar
from urllib.parse import quote

import xlwt
from django.conf import settings
from django.core.exceptions import SuspiciousOperation, ValidationError
from django.db.models import Model
from django.forms.formsets import BaseFormSet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.datastructures import MultiValueDict
from django.utils.translation import get_language
from django.views.generic import FormView

from evap.tools import date_to_datetime

if TYPE_CHECKING:
    from django_stubs_ext import StrOrPromise  # use proper definition with mypy
else:
    try:
        from django_stubs_ext import StrOrPromise  # if installed, use proper definition for typeguard
    except ImportError:
        StrOrPromise = Any  # on production setups, type alias to Any

M = TypeVar("M", bound=Model)
T = TypeVar("T")
CellValue = str | int | float | None
CV = TypeVar("CV", bound=CellValue)


def openid_login_is_active() -> bool:
    return settings.ACTIVATE_OPEN_ID_LOGIN


def password_login_is_active() -> bool:
    return not openid_login_is_active()


def get_object_from_dict_pk_entry_or_logged_40x(
    model_cls: type[M], dict_obj: MultiValueDict[str, Any] | Mapping[str, Any], key: str
) -> M:
    try:
        return get_object_or_404(model_cls, pk=dict_obj[key])
    # ValidationError happens for UUID id fields when passing invalid arguments
    except (KeyError, ValueError, ValidationError) as e:
        raise SuspiciousOperation from e


def is_prefetched(instance, attribute_name: str) -> bool:
    """
    Is the given related attribute prefetched? Can be used to do ordering or counting in python and avoid additional
    database queries
    """
    # foreign key fields
    if attribute_name in instance._state.fields_cache:
        return True

    # m2m and inverse foreign key fields
    if hasattr(instance, "_prefetched_objects_cache") and attribute_name in instance._prefetched_objects_cache:
        return True

    return False


def discard_cached_related_objects(instance: M) -> M:
    """
    Discard all cached related objects (for ForeignKey and M2M Fields). Useful
    if there were changes, but django's caching would still give us the old
    values. Also useful for pickling objects without pickling the whole model
    hierarchy (e.g. for storing instances in a cache)
    """
    # Extracted from django's refresh_from_db, which sadly doesn't offer this part alone (without hitting the DB).
    for field in instance._meta.concrete_fields:  # type: ignore[attr-defined]
        if field.is_relation and field.is_cached(instance):
            field.delete_cached_value(instance)

    for field in instance._meta.related_objects:  # type: ignore[attr-defined]
        if field.is_cached(instance):
            field.delete_cached_value(instance)

    instance._prefetched_objects_cache = {}  # type: ignore[attr-defined]

    return instance


def is_external_email(email: str) -> bool:
    return not any(email.endswith("@" + domain) for domain in settings.INSTITUTION_EMAIL_DOMAINS)


def sort_formset(request: HttpRequest, formset: BaseFormSet) -> None:
    if request.POST:  # if not, there will be no cleaned_data and the models should already be sorted anyways
        formset.is_valid()  # make sure all forms have cleaned_data
        formset.forms.sort(key=lambda f: f.cleaned_data.get("order", 9001))


def vote_end_datetime(vote_end_date: datetime.date) -> datetime.datetime:
    # The evaluation actually ends at EVALUATION_END_OFFSET_HOURS:00 of the day AFTER self.vote_end_date.
    return date_to_datetime(vote_end_date) + datetime.timedelta(hours=24 + settings.EVALUATION_END_OFFSET_HOURS)


def get_parameter_from_url_or_session(request: HttpRequest, parameter: str, default=False) -> bool:
    result_str = request.GET.get(parameter, None)
    if result_str is None:  # if no parameter is given take session value
        result = request.session.get(parameter, default)
    else:
        result = {"true": True, "false": False}.get(result_str.lower())  # convert parameter to boolean
    request.session[parameter] = result  # store value for session
    return result


def translate(**kwargs):
    # pylint is really buggy with this method.
    # pylint: disable=unused-variable, useless-suppression
    # get_language may return None if there is no session (e.g. during management commands)
    return property(lambda self: getattr(self, kwargs[get_language() or "en"]))


EmailT = TypeVar("EmailT", str, None)


def clean_email(email: EmailT) -> EmailT:
    if email:
        email = email.strip().lower()
        # Replace email domains in case there are multiple alias domains used in the organisation and all emails should
        # have the same domain on EvaP.
        for original_domain, replaced_domain in settings.INSTITUTION_EMAIL_REPLACEMENTS:
            if email.endswith(original_domain):
                return email[: -len(original_domain)] + replaced_domain
    return email


def capitalize_first(string: StrOrPromise) -> str:
    """Realize lazy promise objects and capitalize first letter."""
    return string[0].upper() + string[1:]


class FormsetView(FormView):
    """
    Just like `FormView`, but with a renaming from "form" to "formset".
    """

    @property
    def form_class(self):
        return self.formset_class

    def get_context_data(self, **kwargs) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["formset"] = context.pop("form")
        return context

    # As an example for the logic, consider the following: Django calls `get_form_kwargs`, which we delegate to
    # `get_formset_kwargs`. Users can thus override `get_formset_kwargs` instead. If it is not overridden, we delegate
    # to the original `get_form_kwargs` instead. The same approach is used for the other renamed methods.

    def get_form_kwargs(self) -> dict:
        return self.get_formset_kwargs()

    def get_formset_kwargs(self) -> dict:
        return super().get_form_kwargs()

    def form_valid(self, form) -> HttpResponse:
        return self.formset_valid(form)

    def formset_valid(self, formset) -> HttpResponse:
        return super().form_valid(formset)


class SaveValidFormMixin:
    """
    Call `form.save()` if the submitted form is valid.

    Django's `ModelFormMixin` (which inherits from `SingleObjectMixin`) does the same, but cannot always be used, for
    example if a formset for a collection of objects is submitted.
    """

    def form_valid(self, form) -> HttpResponse:
        form.save()
        return super().form_valid(form)  # type: ignore[misc]  # there is no valid way to annotate this


class AttachmentResponse(HttpResponse):
    """
    Helper class that sets the correct Content-Disposition header for a given
    filename.

    In contrast to `django.http.FileResponse`, this class does not read (and
    stream) the content from a filelike object. The content should be written
    _to the response instance_ as if it was a writable file.
    """

    def __init__(self, filename: str, content_type=None, **kwargs) -> None:
        super().__init__(content_type=content_type, **kwargs)
        self.set_content_disposition(filename)

    def set_content_disposition(self, filename: str) -> None:
        try:
            filename.encode("ascii")
            self["Content-Disposition"] = f'attachment; filename="{filename}"'
        except UnicodeEncodeError:
            self["Content-Disposition"] = f"attachment; filename*=utf-8''{quote(filename)}"


class HttpResponseNoContent(HttpResponse):
    """
    HTTP 204 No Content
    Analogous to the built-in `HttpResponseNotModified`.

    Browsers will not reload the page when this status code is returned from a form submission.
    """

    status_code = 204

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        del self["content-type"]

    @HttpResponse.content.setter  # type: ignore[attr-defined]
    def content(self, value):
        if value:
            raise AttributeError("You cannot set content to a 204 (No Content) response")
        self._container = []


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
    default_sheet_name: str | None = None

    def __init__(self) -> None:
        self.workbook = xlwt.Workbook()
        self.cur_row = 0
        self.cur_col = 0
        if self.default_sheet_name is not None:
            self.cur_sheet = self.workbook.add_sheet(self.default_sheet_name)
        else:
            self.cur_sheet = None

    def write_cell(self, label: CellValue = "", style: str = "default") -> None:
        """Write a single cell and move to the next column."""
        self.cur_sheet.write(
            self.cur_row,
            self.cur_col,
            label,
            self.styles[style],
        )
        self.cur_col += 1

    def next_row(self) -> None:
        self.cur_col = 0
        self.cur_row += 1

    def write_row(self, vals: Iterable[CV], style: str | typing.Callable[[CV], str] = "default") -> None:
        """
        Write a cell for every value and go to the next row.
        Styling can be chosen
          - once for all cells by providing a string.
          - separately for every value, based on a callable that maps the value to a style name.
        """
        for val in vals:
            self.write_cell(val, style=style(val) if callable(style) else style)
        self.next_row()

    def write_empty_row_with_styles(self, styles: Iterable[str]) -> None:
        for style in styles:
            self.write_cell(None, style)
        self.next_row()

    @abstractmethod
    def export_impl(self, *args, **kwargs) -> None:
        """Specify the logic to insert the data into the sheet here."""

    def export(self, response, *args, **kwargs) -> None:
        """Convenience method to avoid some boilerplate."""
        self.export_impl(*args, **kwargs)
        self.workbook.save(response)
