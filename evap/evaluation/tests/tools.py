import json
import os
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import timedelta
from importlib import import_module
from typing import Any, Tuple

import django.test
import django_webtest
import requests
import webtest
from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.models import Group
from django.contrib.staticfiles.handlers import StaticFilesHandler
from django.db import DEFAULT_DB_ALIAS, connection, connections
from django.http.request import HttpRequest, QueryDict
from django.test import override_settings, tag
from django.test.runner import DiscoverRunner
from django.test.selenium import SeleniumTestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone, translation
from freezegun import freeze_time
from model_bakery import baker
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.expected_conditions import staleness_of
from selenium.webdriver.support.wait import WebDriverWait

from evap.evaluation.models import (
    CHOICES,
    Contribution,
    Course,
    Evaluation,
    Program,
    Question,
    Questionnaire,
    RatingAnswerCounter,
    TextAnswer,
    UserProfile,
)


class EvapTestRunner(DiscoverRunner):
    """Skips selenium tests by default, if no other tags are specified."""

    def __init__(self, *args: Any, headed=False, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        self.__headed = headed

        if not self.tags and not self.exclude_tags:
            self.exclude_tags = {"selenium"}

    @classmethod
    def add_arguments(cls, parser):
        super().add_arguments(parser)

        parser.add_argument(
            "--headed",
            help="Run the tests in non-headless mode, which makes the browser window visible. Useful for debugging.",
            action="store_true",
        )

    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)

        LiveServerTest.headless = not self.__headed


class ResetLanguageOnTearDownMixin:
    def tearDown(self):
        translation.activate("en")  # Django by default does not "reset" this, causing test interdependency
        super().tearDown()


class TestCase(ResetLanguageOnTearDownMixin, django.test.TestCase):
    pass


class SimpleTestCase(ResetLanguageOnTearDownMixin, django.test.SimpleTestCase):
    pass


class WebTest(ResetLanguageOnTearDownMixin, django_webtest.WebTest):
    pass


def to_querydict(dictionary):
    querydict = QueryDict(mutable=True)
    for key, value in dictionary.items():
        querydict[key] = value
    return querydict


# taken from http://lukeplant.me.uk/blog/posts/fuzzy-testing-with-assertnumqueries/
class FuzzyInt(int):  # noqa: PLW1641
    def __new__(cls, lowest, highest):
        obj = super().__new__(cls, highest)
        obj.lowest = lowest
        obj.highest = highest
        return obj

    def __eq__(self, other):
        return self.lowest <= other <= self.highest

    def __repr__(self):
        return f"[{self.lowest}..{self.highest}]"


def let_user_vote_for_evaluation(user, evaluation, create_answers=False):
    evaluation.voters.add(user)
    if evaluation.voters.count() >= 2:
        evaluation.can_publish_text_results = True
        evaluation.save()

    if not create_answers:
        return

    new_textanswers = []
    rac_by_contribution_question = {}
    new_racs = []

    for contribution in evaluation.contributions.all().prefetch_related(
        "ratinganswercounter_set", "questionnaires", "questionnaires__questions"
    ):
        for rac in contribution.ratinganswercounter_set.all():
            if rac.answer == 1:
                rac_by_contribution_question[(contribution, rac.question)] = rac

        for questionnaire in contribution.questionnaires.all():
            for question in questionnaire.questions.all():
                if question.is_text_question:
                    new_textanswers.append(baker.prepare(TextAnswer, contribution=contribution, question=question))
                elif question.is_rating_question:
                    if (contribution, question) not in rac_by_contribution_question:
                        rac = baker.prepare(RatingAnswerCounter, contribution=contribution, question=question, answer=1)
                        new_racs.append(rac)
                        rac_by_contribution_question[(contribution, question)] = rac

                    rac_by_contribution_question[(contribution, question)].count += 1

    TextAnswer.objects.bulk_create(new_textanswers)
    RatingAnswerCounter.objects.bulk_create(new_racs)
    RatingAnswerCounter.objects.bulk_update(rac_by_contribution_question.values(), ["count"])


class WebTestWith200Check(WebTest):
    url = "/"
    test_users: list[UserProfile | str] = []

    def test_check_response_code_200(self):
        for user in self.test_users:
            self.app.get(self.url, user=user, status=200)


def submit_with_modal(
    page: webtest.TestResponse, form: webtest.Form, *, name: str, value: str, **kwargs
) -> webtest.TestResponse:
    # Like form.submit, but looks for a modal instead of a submit button.
    assert page.forms[form.id] == form
    assert page.html.select_one(f"confirmation-modal[type=submit][name={name}][value={value}]")
    params = form.submit_fields() + [(name, value)]
    return form.response.goto(form.action, method=form.method, params=params, **kwargs)


def get_form_data_from_instance(form_cls, instance, **kwargs):
    assert form_cls._meta.model is type(instance)
    form = form_cls(instance=instance, **kwargs)
    return {field.html_name: field.value() for field in form}


def create_evaluation_with_responsible_and_editor():
    responsible = baker.make(UserProfile, email="responsible@institution.example.com")
    editor = baker.make(UserProfile, email="editor@institution.example.com")

    in_one_hour = (timezone.now() + timedelta(hours=1)).replace(second=0, microsecond=0)
    tomorrow = (timezone.now() + timedelta(days=1)).date
    evaluation_params = {
        "state": Evaluation.State.PREPARED,
        "course": baker.make(Course, programs=[baker.make(Program)], responsibles=[responsible]),
        "vote_start_datetime": in_one_hour,
        "vote_end_date": tomorrow,
        "main_language": "en",
    }

    evaluation = baker.make(Evaluation, **evaluation_params)
    contribution = baker.make(
        Contribution,
        evaluation=evaluation,
        contributor=editor,
        questionnaires=[baker.make(Questionnaire, type=Questionnaire.Type.CONTRIBUTOR)],
        role=Contribution.Role.EDITOR,
    )
    evaluation.general_contribution.questionnaires.set(
        [
            baker.make(Questionnaire, type=Questionnaire.Type.TOP),
            baker.make(Questionnaire, type=Questionnaire.Type.DROPOUT),
            baker.make(Questionnaire, type=Questionnaire.Type.BOTTOM),
        ]
    )

    return {
        "evaluation": evaluation,
        "responsible": responsible,
        "editor": editor,
        "contribution": contribution,
    }


def make_manager(**kwargs):
    return baker.make(
        UserProfile,
        email="manager@institution.example.com",
        groups=[Group.objects.get(name="Manager")],
        **kwargs,
    )


def make_contributor(user, evaluation):
    """Make user a contributor of evaluation."""
    return baker.make(Contribution, evaluation=evaluation, contributor=user, role=Contribution.Role.CONTRIBUTOR)


def make_editor(user, evaluation):
    """Make user an editor of evaluation."""
    return baker.make(
        Contribution,
        evaluation=evaluation,
        contributor=user,
        role=Contribution.Role.EDITOR,
    )


def make_rating_answer_counters(
    question: Question,
    contribution: Contribution,
    answer_counts: Sequence[int] | None = None,
    store_in_db: bool = True,
):
    """
    Create RatingAnswerCounters for a question for a contribution.
    Examples:
    make_rating_answer_counters(rating_question, contribution, [5, 15, 40, 60, 30])
    make_rating_answer_counters(yesno_question, contribution, [15, 2])
    make_rating_answer_counters(bipolar_question, contribution, [5, 5, 15, 30, 25, 15, 10])
    """
    expected_counts = len(CHOICES[question.type].grades)

    if answer_counts is None:
        answer_counts = [0] * expected_counts
        answer_counts[0] = 42

    assert len(answer_counts) == expected_counts

    counters = baker.prepare(
        RatingAnswerCounter,
        question=question,
        contribution=contribution,
        _quantity=len(answer_counts),
        answer=iter(CHOICES[question.type].values),
        count=iter(answer_counts),
    )

    if store_in_db:
        RatingAnswerCounter.objects.bulk_create(counters)

    return counters


@contextmanager
def assert_no_database_modifications(*args, **kwargs):
    assert len(connections.all()) == 1, "Found more than one connection, so the decorator might monitor the wrong one"

    # may be extended with other non-modifying verbs
    allowed_prefixes = ["select", "savepoint", "release savepoint"]

    conn = connections[DEFAULT_DB_ALIAS]
    with CaptureQueriesContext(conn):
        yield

        for query in conn.queries_log:
            if (
                query["sql"].startswith('INSERT INTO "testing_cache_sessions"')
                or query["sql"].startswith('UPDATE "testing_cache_sessions"')
                or query["sql"].startswith('DELETE FROM "testing_cache_sessions"')
                or query["sql"].startswith('UPDATE "evaluation_userprofile" SET "last_login" = ')
            ):
                # These queries are caused by interacting with the test-app (self.app.get()), since that opens a session.
                # That's not what we want to test for here
                continue

            lower_sql = query["sql"].lower()
            if not any(lower_sql.startswith(prefix) for prefix in allowed_prefixes):
                raise AssertionError("Unexpected modifying query found: " + query["sql"])


class LiveServerTest(SeleniumTestCase):
    browser = "firefox"
    selenium: WebDriver
    headless = True
    window_size = (1920, 4096)  # large height to workaround scrolling
    serialized_rollback = True  # SeleniumTestCase is a TransactionTestCase, which drops migration data. This keeps fixture data but may slow down tests, see https://docs.djangoproject.com/en/5.0/topics/testing/overview/#test-case-serialized-rollback
    static_handler = StaticFilesHandler  # see StaticLiveServerTestCase

    def setUp(self) -> None:
        super().setUp()

        self.request = self.make_request()
        self.manager = make_manager()
        self.selenium.get(self.live_server_url)
        self.login(self.manager)

    def reverse(self, *args, **kwargs):
        return self.live_server_url + reverse(*args, **kwargs)

    @classmethod
    def make_request(cls) -> HttpRequest:
        request = HttpRequest()
        engine = import_module(settings.SESSION_ENGINE)
        request.session = engine.SessionStore()
        return request

    def update_session(self) -> None:
        self.request.session.save()
        self.selenium.add_cookie(
            {
                "name": settings.SESSION_COOKIE_NAME,
                "value": self.request.session.session_key,
                "path": "/",
                "secure": settings.SESSION_COOKIE_SECURE or False,
            }
        )

    def login(self, user) -> None:
        """Login a test user by setting the session cookie."""
        login(self.request, user, "evap.evaluation.auth.RequestAuthUserBackend")
        self.update_session()

    @contextmanager
    def enter_staff_mode(self) -> Iterator[None]:
        self.request.session["staff_mode_start_time"] = time.time()
        self.update_session()
        yield
        del self.request.session["staff_mode_start_time"]
        self.update_session()

    @property
    def wait(self) -> WebDriverWait:
        return WebDriverWait(self.selenium, 10)

    @contextmanager
    def wait_until_page_reloads(self):
        html_element = self.selenium.find_element(By.TAG_NAME, "html")
        yield
        self.wait.until(staleness_of(html_element))

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.selenium.set_window_size(*cls.window_size)


@override_settings(SLOGANS_EN=["Einigermaßen verlässlich aussehende Pixeltestung"])
@tag("vrt")
class VisualRegressionTestCase(LiveServerTest):
    window_size = (1920, 1080)
    _http_timeout_seconds = 3

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.apiUrl = os.environ.get("VRT_APIURL")
        self.ciBuildId = os.environ.get("VRT_CIBUILDID")
        self.branchName = os.environ.get("VRT_BRANCHNAME")
        self.apiKey = os.environ.get("VRT_APIKEY")
        self.projectId = os.environ.get("VRT_PROJECT")

        self.headers = {
            "apiKey": self.apiKey,
            "Content-Type": "application/json",
        }

        self.data = {
            "project": self.projectId,
            "projectId": self.projectId,  # this is not a typo, depending on the request either project/projectId is used
            "branchName": self.branchName,
            "ciBuildId": self.ciBuildId,
        }

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()

        cls.freezer = freeze_time("2025-10-27")
        cls.freezer.start()

    @classmethod
    def tearDownClass(cls) -> None:
        super().tearDownClass()
        cls.freezer.stop()

    @property
    def viewport(self):
        return f"{self.window_size[0]}x{self.window_size[1]}"

    def setUp(self) -> None:
        super().setUp()
        self.build_id = self._startVRTSession()

    def tearDown(self) -> None:
        super().tearDown()
        self._stopVRTSession()

    def _startVRTSession(self) -> str:
        registration_response = requests.post(
            f"{self.apiUrl}/builds",
            data=json.dumps(self.data),
            headers=self.headers,
            timeout=self._http_timeout_seconds,
        )

        registration_response.raise_for_status()
        return registration_response.json().get("id")

    def _stopVRTSession(self):
        # marks the session of the current as done
        requests.patch(
            f"{self.apiUrl}/builds/{self.build_id}",
            data={},
            headers=self.headers,
            timeout=self._http_timeout_seconds,
        ).raise_for_status()

    def _postScreenshot(self, name) -> Tuple[str, str]:
        test_data = self.data | {
            "name": name,
            "imageBase64": self.selenium.get_screenshot_as_base64(),
            "viewport": self.viewport,
            "buildId": self.build_id,
        }

        test_response = requests.post(
            f"{self.apiUrl}/test-runs",
            data=json.dumps(test_data),
            headers=self.headers,
            timeout=self._http_timeout_seconds,
        )

        test_response.raise_for_status()
        payload = test_response.json()
        return (payload.get("status"), payload.get("url", "<url-not-found>"))

    def trigger_screenshot(self, name: str):
        full_name = self.__class__.__name__ + "_" + name

        status, review_url = self._postScreenshot(full_name)

        switcher = {
            "new": f"No Baseline! Review manually: {review_url}",
            "unresolved": f"Difference found: {review_url}",
        }

        error_message = switcher.get(status)

        if error_message:
            self.fail(error_message)


def classes_of_element(element: WebElement) -> list[str]:
    classes = element.get_attribute("class")
    if classes is None:
        return []
    return classes.split(" ")
