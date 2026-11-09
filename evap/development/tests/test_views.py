from django.urls import reverse

from evap.evaluation.tests.tools import WebTestWith200Check, make_manager


class TestComponentsView(WebTestWith200Check):
    url = reverse("development_components")

    @classmethod
    def setUpTestData(cls):
        cls.test_users = [make_manager()]
