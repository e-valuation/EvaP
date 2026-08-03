from collections.abc import Callable

import requests
from django.conf import settings
from django.http.request import HttpRequest
from django.http.response import HttpResponse, HttpResponseBase


class InvalidHtmlError(Exception):
    def __init__(self, path: str, html: str, errors: list) -> None:
        self.path = path
        self.html = html
        self.errors = errors

    def format_error(self, error) -> str:
        s = f"error: {error['message']}\n"
        if "extract" in error:
            s += f"context:\n{error['extract']}"
        return s

    def __str__(self) -> str:
        errors = "\n".join(self.format_error(e) for e in self.errors)
        return f"html validation failed for {self.path}:\n{errors}"


class NuValidatorMiddleware:
    IGNORED_ERROR_PATTERNS = (
        "autocomplete",
        "not allowed as child of element “span”",
        # accessibility
        "aria",
        'same "nearest ancestor autofocus scoping root element"',
        "Every active “role=tab” element must have a corresponding “role=tabpanel” element",
        "An element with “role=tab” must be contained in, or owned by, an element with the “role” value “tablist”",
        # custom attributes
        "custom-success",
        "reload-on-success",
        "Attribute “tomselect-no-sort” not allowed on element “select”",
        # table correctness
        "seen in “table”",
        "not allowed as child of element “tr”",
        # column count
        "999 columns",
        "999 established",
    )

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponseBase]) -> None:
        self.get_response = get_response
        assert isinstance(settings.VNU_URL, str)
        self.vnu_url = settings.VNU_URL

    def __call__(self, request: HttpRequest) -> HttpResponseBase:
        response = self.get_response(request)
        if (
            isinstance(response, HttpResponse)
            and response.headers.get("Content-Type", "").startswith("text/html")
            and response.text
        ):
            self.validate_html(request.path, response.text)
        return response

    def validate_html(self, path: str, html: str) -> None:
        errors = requests.post(
            self.vnu_url,
            params={
                "out": "json",
                "level": "error",
                "filterpattern": "|".join(f".*{p}.*" for p in self.IGNORED_ERROR_PATTERNS),
            },
            headers={"Content-Type": "text/html"},
            data=html,
            timeout=10,
        ).json()["messages"]

        if errors:
            raise InvalidHtmlError(path, html, errors)
