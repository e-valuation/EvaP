import os
import time
from collections.abc import Sequence
from contextlib import contextmanager
from datetime import timedelta
from importlib import import_module
from typing import Any

import django.test
import django_webtest
import webtest
from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.models import Group
from django.db import DEFAULT_DB_ALIAS, connections
from django.http.request import HttpRequest, QueryDict
from django.test import tag
from django.test.runner import DiscoverRunner
from django.test.selenium import SeleniumTestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone, translation
from model_bakery import baker
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

class SkipLiveServerTestsRunner(DiscoverRunner):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if not self.tags and not self.exclude_tags:
            self.exclude_tags = {"live-server"}


class ResetLanguageOnTearDownMixin:
    def tearDown(self):
        translation.activate("en")  # Django by default does not "reset" this, causing test interdependency
        super().tearDown()


class TestCase(ResetLanguageOnTearDownMixin, django.test.TestCase):
    pass


class WebTest(ResetLanguageOnTearDownMixin, django_webtest.WebTest):
    pass


def to_querydict(dictionary):
    querydict = QueryDict(mutable=True)
    for key, value in dictionary.items():
        querydict[key] = value
    return querydict


# taken from http://lukeplant.me.uk/blog/posts/fuzzy-testing-with-assertnumqueries/
class FuzzyInt(int):
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
    }

    evaluation = baker.make(Evaluation, **evaluation_params)
    contribution = baker.make(
        Contribution,
        evaluation=evaluation,
        contributor=editor,
        questionnaires=[baker.make(Questionnaire, type=Questionnaire.Type.CONTRIBUTOR)],
        role=Contribution.Role.EDITOR,
    )
    evaluation.general_contribution.questionnaires.set([baker.make(Questionnaire, type=Questionnaire.Type.TOP)])

    return {
        "evaluation": evaluation,
        "responsible": responsible,
        "editor": editor,
        "contribution": contribution,
    }


def make_manager():
    return baker.make(
        UserProfile,
        email="manager@institution.example.com",
        groups=[Group.objects.get(name="Manager")],
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
            ):
                # These queries are caused by interacting with the test-app (self.app.get()), since that opens a session.
                # That's not what we want to test for here
                continue

            lower_sql = query["sql"].lower()
            if not any(lower_sql.startswith(prefix) for prefix in allowed_prefixes):
                raise AssertionError("Unexpected modifying query found: " + query["sql"])

@tag("live-server")
class LiveServerTest(SeleniumTestCase):
    external_host = os.environ.get("TEST_HOST", "") or None
    browser = "firefox"
    selenium_hub = None
    headless = True
    window_size = (1920, 3080)

    serialized_rollback = True

    def _screenshot(self, name):
        self.selenium.save_screenshot(os.path.join(settings.BASE_DIR, f"{name}.png"))

    def _create_test_user(self):
        """Create a default test user."""
        test_user = baker.make(
            UserProfile, email="evap@institution.example.com", groups=[Group.objects.get(name="Manager")]
        )
        test_user_password = "evap"
        test_user.set_password(test_user_password)
        test_user.save()
        return test_user

    def _default_login(self):
        """Login a default test user."""
        user = self._create_test_user()
        self._login(user)
        return user

    def _create_session(self):
        request = HttpRequest()
        engine = import_module(settings.SESSION_ENGINE)
        request.session = engine.SessionStore()

        self.request = request  # pylint: disable=attribute-defined-outside-init

    def _update_session(self):
        self.request.session.save()
        # Create session cookie
        cookie_data = {
            "name": settings.SESSION_COOKIE_NAME,
            "value": self.request.session.session_key,
            "path": "/",
            "secure": settings.SESSION_COOKIE_SECURE or False,
        }
        self.selenium.add_cookie(cookie_data)

    def _login(self, user):
        """Login a test user by setting the session cookie."""
        self.selenium.get(self.live_server_url)

        # Create fake session to do user login workflow
        self._create_session()
        login(self.request, user, "evap.evaluation.auth.RequestAuthUserBackend")
        self._update_session()

    def _enter_staff_mode(self):
        self.request.session["staff_mode_start_time"] = time.time()
        self._update_session()

    def _exit_staff_mode(self):
        if "staff_mode_start_time" in self.request.session:
            del self.request.session["staff_mode_start_time"]
            self._update_session()

    @property
    def wait(self) -> WebDriverWait:
        return WebDriverWait(self.selenium, 10)

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.selenium.set_window_size(*cls.window_size)
