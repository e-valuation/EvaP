from django.http.request import QueryDict

from django_webtest import WebTest
from model_mommy import mommy

from evap.evaluation.models import Contribution, Course, UserProfile, Questionnaire, Degree
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


def let_user_vote_for_course(app, user, course):
    url = '/student/vote/{}'.format(course.id)
    page = app.get(url, user=user, status=200)
    form = page.forms["student-vote-form"]
    for contribution in course.contributions.all().prefetch_related("questionnaires", "questionnaires__questions"):
        for questionnaire in contribution.questionnaires.all():
            for question in questionnaire.questions.all():
                if question.type == "T":
                    form[question_id(contribution, questionnaire, question)] = "Lorem ispum"
                elif question.type in ["L", "G", "P", "N"]:
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


def create_course_with_responsible_and_editor(course_id=None):
    contributor = mommy.make(UserProfile, username='responsible')
    editor = mommy.make(UserProfile, username='editor')

    if course_id:
        course = mommy.make(Course, state='prepared', degrees=[mommy.make(Degree)], id=course_id)
    else:
        course = mommy.make(Course, state='prepared', degrees=[mommy.make(Degree)])

    mommy.make(Contribution, course=course, contributor=contributor, can_edit=True, responsible=True, questionnaires=[mommy.make(Questionnaire, type=Questionnaire.CONTRIBUTOR)], comment_visibility=Contribution.ALL_COMMENTS)
    mommy.make(Contribution, course=course, contributor=editor, can_edit=True, questionnaires=[mommy.make(Questionnaire, type=Questionnaire.CONTRIBUTOR)])
    course.general_contribution.questionnaires.set([mommy.make(Questionnaire, type=Questionnaire.TOP)])

    return course
