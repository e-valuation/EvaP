from unittest.mock import patch

from django.conf import settings
from django.core import management
from django.urls import reverse
from django.test.testcases import TestCase
from django.utils import translation

from model_bakery import baker

from evap.evaluation.tests.tools import WebTest
from evap.evaluation.models import UserProfile


class TestLanguageSignalReceiver(WebTest):
    def test_signal_sets_language_if_none(self):
        """
        Check that a user gets the default language set if they have none
        """
        user = baker.make(UserProfile, language=None, email="user@institution.example.com")
        user.ensure_valid_login_key()

        self.app.get("/", user=user)

        user.refresh_from_db()
        self.assertEqual(user.language, settings.LANGUAGE_CODE)

    def test_signal_doesnt_set_language(self):
        """
        Activate 'en' as langauge and check, that user does not get this langauge as he has one.
        """
        translation.activate('en')
        user = baker.make(UserProfile, language='de', email="user@institution.example.com")
        user.ensure_valid_login_key()

        self.app.get(reverse("evaluation:login_key_authentication", args=[user.login_key]))

        user.refresh_from_db()
        self.assertEqual(user.language, 'de')


class TestLogExceptionsDecorator(TestCase):
    @patch('evap.evaluation.models.Evaluation.update_evaluations', side_effect=Exception())
    @patch('evap.evaluation.management.commands.tools.logger.exception')
    def test_log_exceptions_decorator(self, mock_logger, __):
        """
            Test whether the log exceptions decorator does its thing correctly.
            update_evaluations is just a random management command that uses the decorator.
            One could create a mock management command and call its handle method manually,
            but to me it seemed safer to use a real one.
        """
        try:
            management.call_command('update_evaluation_states')
        except Exception:
            pass
        self.assertTrue(mock_logger.called)
        self.assertIn("failed. Traceback follows:", mock_logger.call_args[0][0])


class TestPythonVersion(TestCase):
    def test_dict_unpacking(self):
        """ python >= 3.5 """
        d = {'a': 1, 'b': 2}
        self.assertEqual({**d, 'b': 3, 'c': 4}, {'a': 1, 'b': 3, 'c': 4})

    def test_format_strings(self):
        """ python >= 3.6 """
        world = 'World'
        self.assertEqual(f'Hello {world}', 'Hello World')

    def test_breakpoint_available(self):
        """ python >= 3.7 """
        import builtins
        self.assertTrue(hasattr(builtins, 'breakpoint'))
