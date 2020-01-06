from datetime import timedelta

from django.http.request import QueryDict
from django.utils import timezone

from django_webtest import WebTest
from model_bakery import baker

from evap.evaluation.models import Contribution, Course, Degree, Evaluation, Questionnaire, UserProfile
from evap.student.tools import question_id


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
        return other >= self.lowest and other <= self.highest

    def __repr__(self):
        return "[%d..%d]" % (self.lowest, self.highest)


def let_user_vote_for_evaluation(app, user, evaluation):
    url = '/student/vote/{}'.format(evaluation.id)
    page = app.get(url, user=user, status=200)
    form = page.forms["student-vote-form"]
    for contribution in evaluation.contributions.all().prefetch_related("questionnaires", "questionnaires__questions"):
        for questionnaire in contribution.questionnaires.all():
            for question in questionnaire.questions.all():
                if question.is_text_question:
                    form[question_id(contribution, questionnaire, question)] = "Lorem ispum"
                elif question.is_rating_question:
                    form[question_id(contribution, questionnaire, question)] = 1
    form.submit()


class WebTestWith200Check(WebTest):
    url = "/"
    test_users = []

    def test_check_response_code_200(self):
        for user in self.test_users:
            self.app.get(self.url, user=user, status=200)


def get_form_data_from_instance(FormClass, instance):
    assert FormClass._meta.model == type(instance)
    form = FormClass(instance=instance)
    return {field.html_name: field.value() for field in form}


def create_evaluation_with_responsible_and_editor(evaluation_id=None):
    responsible = baker.make(UserProfile, username='responsible')
    editor = baker.make(UserProfile, username='editor')

    in_one_hour = (timezone.now() + timedelta(hours=1)).replace(second=0, microsecond=0)
    tomorrow = (timezone.now() + timedelta(days=1)).date
    evaluation_params = dict(
        state='prepared',
        course=baker.make(Course, degrees=[baker.make(Degree)], responsibles=[responsible]),
        vote_start_datetime=in_one_hour,
        vote_end_date=tomorrow
    )

    if evaluation_id:
        evaluation_params['id'] = evaluation_id

    evaluation = baker.make(Evaluation, **evaluation_params)
    baker.make(Contribution, evaluation=evaluation, contributor=editor, can_edit=True, questionnaires=[baker.make(Questionnaire, type=Questionnaire.CONTRIBUTOR)])
    evaluation.general_contribution.questionnaires.set([baker.make(Questionnaire, type=Questionnaire.TOP)])

    return evaluation
