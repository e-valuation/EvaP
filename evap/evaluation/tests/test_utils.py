from django_webtest import WebTest
from model_mommy import mommy

from evap.evaluation.models import Contribution, Course, UserProfile
import heapq

class ViewTest(WebTest):
    url = "/"
    test_users = []

    def test_check_response_code_200(self):
        for user in self.test_users:
            response = self.app.get(self.url, user=user)
            self.assertEqual(response.status_code, 200, 'url "{}" failed with user "{}"'.format(self.url, user))


def lastform(page):
    # Hacky hack to ignore the feedback form. We take the second biggest numeric index.
    return page.forms[heapq.nlargest(2, [key for key in page.forms.keys() if isinstance(key, int)])[1]]


def get_form_data_from_instance(FormClass, instance):
    assert FormClass._meta.model == type(instance)
    form = FormClass(instance=instance)
    return {field.html_name: field.value() for field in form}


def course_with_responsible_and_editor(course_id=None):
    contributor = mommy.make(UserProfile, username='responsible')
    editor = mommy.make(UserProfile, username='editor')

    if course_id:
        course = mommy.make(Course, state='prepared', id=course_id)
    else:
        course = mommy.make(Course, state='prepared')

    mommy.make(Contribution, course=course, contributor=contributor, can_edit=True, responsible=True)
    mommy.make(Contribution, course=course, contributor=editor, can_edit=True)

    return course
