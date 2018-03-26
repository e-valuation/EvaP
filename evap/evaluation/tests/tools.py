from django.http.request import QueryDict

from django_webtest import WebTest as DjangoWebTest
from model_mommy import mommy
from webtest import AppError

from evap.evaluation.models import Contribution, Course, UserProfile, Questionnaire, Degree


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


class WebTest(DjangoWebTest):

    def get_assert_200(self, url, user):
        response = self.app.get(url, user=user)
        self.assertEqual(response.status_code, 200, 'url "{}" failed with user "{}"'.format(url, user))
        return response

    def get_assert_403(self, url, user):
        try:
            self.app.get(url, user=user, status=403)
        except AppError:
            self.fail('url "{}" failed with user "{}"'.format(url, user))

    def get_assert_302(self, url, user):
        response = self.app.get(url, user=user)
        self.assertEqual(response.status_code, 302, 'url "{}" failed with user "{}"'.format(url, user))
        return response

    def get_submit_assert_200(self, url, user):
        response = self.get_assert_200(url, user)
        response = response.forms[1].submit("")
        self.assertEqual(response.status_code, 200, 'url "{}" failed with user "{}"'.format(url, user))
        return response


class ViewTest(WebTest):
    url = "/"
    test_users = []

    def test_check_response_code_200(self):
        for user in self.test_users:
            self.get_assert_200(self.url, user)


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

    mommy.make(Contribution, course=course, contributor=contributor, can_edit=True, responsible=True, questionnaires=[mommy.make(Questionnaire, is_for_contributors=True)], comment_visibility=Contribution.ALL_COMMENTS)
    mommy.make(Contribution, course=course, contributor=editor, can_edit=True, questionnaires=[mommy.make(Questionnaire, is_for_contributors=True)])
    course.general_contribution.questionnaires.set([mommy.make(Questionnaire, is_for_contributors=False)])

    return course
