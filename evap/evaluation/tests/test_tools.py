from unittest.mock import patch

from django.core import management
from django.core.urlresolvers import reverse
from django.test.testcases import TestCase
from django.utils import translation

from model_mommy import mommy

from evap.evaluation.tests.tools import WebTest
from evap.evaluation.tools import set_or_get_language
from evap.evaluation.models import UserProfile


class TestLanguageSignalReceiver(WebTest):
    def test_signal_sets_language_if_none(self):
        """
        Activate 'de' as language and check that user gets this as initial language as he has None.
        """
        translation.activate('de')

        user = mommy.make(UserProfile, language=None)
        user.generate_login_key()

        set_or_get_language(None, user, None)

        user.refresh_from_db()
        self.assertEqual(user.language, 'de')

    def test_signal_doesnt_set_language(self):
        """
        Activate 'en' as langauge and check, that user does not get this langauge as he has one.
        """
        translation.activate('en')
        user = mommy.make(UserProfile, language='de')
        user.generate_login_key()

        self.app.get(reverse("results:index") + "?loginkey=%s" % user.login_key)

        user.refresh_from_db()
        self.assertEqual(user.language, 'de')


class TestLogExceptionsDecorator(TestCase):
    @patch('evap.evaluation.models.Course.update_courses', side_effect=Exception())
    @patch('evap.evaluation.management.commands.tools.logger.exception')
    def test_log_exceptions_decorator(self, mock_logger, __):
        """
            Test whether the log exceptions decorator does its thing correctly.
            update_courses is just a random management command that uses the decorator.
            One could create a mock management command and call its handle method manually,
            but to me it seemed safer to use a real one.
        """
        try:
            management.call_command('update_course_states')
        except Exception:
            pass
        self.assertTrue(mock_logger.called)
        self.assertIn("failed. Traceback follows:", mock_logger.call_args[0][0])
