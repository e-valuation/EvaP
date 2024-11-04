import functools
import os
from collections.abc import Sequence
from contextlib import contextmanager
from datetime import timedelta

import django.test
import django_webtest
import webtest
from django.conf import settings
from django.contrib.auth.models import Group
from django.db import DEFAULT_DB_ALIAS, connections
from django.http.request import QueryDict
from django.test.utils import CaptureQueriesContext
from django.utils import timezone, translation
from model_bakery import baker

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


def store_ts_test_asset(relative_path: str, content) -> None:
    absolute_path = os.path.join(settings.STATICFILES_DIRS[0], "ts", "rendered", relative_path)

    os.makedirs(os.path.dirname(absolute_path), exist_ok=True)

    with open(absolute_path, "wb") as file:
        file.write(content)


def render_pages(test_item):
    """Decorator which annotates test methods which render pages.
    The containing class is expected to include a `url` attribute which matches a valid path.
    Unlike normal test methods, it should not assert anything and is expected to return a dictionary.
    The key denotes the variant of the page to reflect multiple states, cases or views.
    The value is a byte string of the page content."""

    @functools.wraps(test_item)
    def decorator(self) -> None:
        pages = test_item(self)

        url = getattr(self, "render_pages_url", self.url)

        for name, content in pages.items():
            # Remove the leading slash from the url to prevent that an absolute path is created
            path = os.path.join(url[1:], f"{name}.html")
            store_ts_test_asset(path, content)

    return decorator


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
