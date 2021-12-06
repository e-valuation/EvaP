import functools
import os
from datetime import timedelta
from typing import List, Union

from django.conf import settings
from django.contrib.auth.models import Group
from django.http.request import QueryDict
from django.utils import timezone
from django_webtest import WebTest
from model_bakery import baker

from evap.evaluation.models import (
    CHOICES,
    Contribution,
    Course,
    Degree,
    Evaluation,
    Questionnaire,
    RatingAnswerCounter,
    UserProfile,
)
from evap.student.tools import answer_field_id


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
        return "[%d..%d]" % (self.lowest, self.highest)


def let_user_vote_for_evaluation(app, user, evaluation):
    url = "/student/vote/{}".format(evaluation.id)
    page = app.get(url, user=user, status=200)
    form = page.forms["student-vote-form"]
    for contribution in evaluation.contributions.all().prefetch_related("questionnaires", "questionnaires__questions"):
        for questionnaire in contribution.questionnaires.all():
            for question in questionnaire.questions.all():
                if question.is_text_question:
                    form[answer_field_id(contribution, questionnaire, question)] = "Lorem ispum"
                elif question.is_rating_question:
                    form[answer_field_id(contribution, questionnaire, question)] = 1
    form.submit()


def render_pages(test_item):
    """Decorator which annotates test methods which render pages.
    The containing class is expected to include a `url` attribute which matches a valid path.
    Unlike normal test methods, it should not assert anything and is expected to return a dictionary.
    The key denotes the variant of the page to reflect multiple states, cases or views.
    The value is a byte string of the page content."""

    @functools.wraps(test_item)
    def decorator(self):
        pages = test_item(self)

        static_directory = settings.STATICFILES_DIRS[0]

        # Remove the leading slash from the url to prevent that an absolute path is created
        directory = os.path.join(static_directory, "ts", "rendered", self.url[1:])
        os.makedirs(directory, exist_ok=True)

        for name, content in pages.items():
            with open(os.path.join(directory, f"{name}.html"), "wb") as html_file:
                html_file.write(content)

    return decorator


class WebTestWith200Check(WebTest):
    url = "/"
    test_users: List[Union[UserProfile, str]] = []

    def test_check_response_code_200(self):
        for user in self.test_users:
            self.app.get(self.url, user=user, status=200)


def get_form_data_from_instance(FormClass, instance, **kwargs):
    assert FormClass._meta.model == type(instance)
    form = FormClass(instance=instance, **kwargs)
    return {field.html_name: field.value() for field in form}


def create_evaluation_with_responsible_and_editor(evaluation_id=None):
    responsible = baker.make(UserProfile, email="responsible@institution.example.com")
    editor = baker.make(UserProfile, email="editor@institution.example.com")

    in_one_hour = (timezone.now() + timedelta(hours=1)).replace(second=0, microsecond=0)
    tomorrow = (timezone.now() + timedelta(days=1)).date
    evaluation_params = dict(
        state=Evaluation.State.PREPARED,
        course=baker.make(Course, degrees=[baker.make(Degree)], responsibles=[responsible]),
        vote_start_datetime=in_one_hour,
        vote_end_date=tomorrow,
    )

    if evaluation_id:
        evaluation_params["id"] = evaluation_id

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


def make_rating_answer_counters(question, contribution, answer_counts=None):
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

    return baker.make(
        RatingAnswerCounter,
        question=question,
        contribution=contribution,
        _bulk_create=True,
        _quantity=len(answer_counts),
        answer=iter(CHOICES[question.type].values),
        count=iter(answer_counts),
    )
