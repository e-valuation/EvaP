from unittest.mock import patch
from uuid import UUID

from django.conf import settings
from django.core import management
from django.core.exceptions import SuspiciousOperation
from django.db.models import prefetch_related_objects
from django.http import Http404
from django.test.testcases import TestCase
from django.urls import reverse
from django.utils import translation
from model_bakery import baker

from evap.evaluation.models import Contribution, Course, Evaluation, TextAnswer, UserProfile
from evap.evaluation.tests.tools import WebTest
from evap.evaluation.tools import (
    discard_cached_related_objects,
    get_object_from_dict_pk_entry_or_logged_40x,
    is_m2m_prefetched,
)


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
        translation.activate("en")
        user = baker.make(UserProfile, language="de", email="user@institution.example.com")
        user.ensure_valid_login_key()

        self.app.get(reverse("evaluation:login_key_authentication", args=[user.login_key]))

        user.refresh_from_db()
        self.assertEqual(user.language, "de")


class SaboteurException(Exception):
    """An exception class used for making sure that our mock is raising the exception and not some other unrelated code"""


class TestLogExceptionsDecorator(TestCase):
    @patch("evap.evaluation.models.Evaluation.update_evaluations", side_effect=SaboteurException())
    @patch("evap.evaluation.management.commands.tools.logger.exception")
    def test_log_exceptions_decorator(self, mock_logger, __):
        """
        Test whether the log exceptions decorator does its thing correctly.
        update_evaluations is just a random management command that uses the decorator.
        One could create a mock management command and call its handle method manually,
        but to me it seemed safer to use a real one.
        """
        with self.assertRaises(SaboteurException):
            management.call_command("update_evaluation_states")

        self.assertTrue(mock_logger.called)
        self.assertIn("failed. Traceback follows:", mock_logger.call_args[0][0])


class TestHelperMethods(WebTest):
    def test_is_m2m_prefetched(self):
        evaluation = baker.make(Evaluation)
        baker.make(Contribution, evaluation=evaluation)

        self.assertFalse(is_m2m_prefetched(evaluation, "contributions"))

        prefetch_related_objects([evaluation], "contributions")
        self.assertTrue(is_m2m_prefetched(evaluation, "contributions"))

        evaluation.refresh_from_db(fields=["contributions"])
        self.assertFalse(is_m2m_prefetched(evaluation, "contributions"))

        evaluation = Evaluation.objects.filter(pk=evaluation.pk).prefetch_related("contributions").first()
        self.assertTrue(is_m2m_prefetched(evaluation, "contributions"))

    def test_discard_cached_related_objects_discards_cached_foreign_key_instances(self):
        evaluation = baker.make(Evaluation, course__name_en="old_name")
        discard_cached_related_objects(evaluation)

        # Instances are implicitly cached on access
        with self.assertNumQueries(1):
            self.assertEqual(evaluation.course.name_en, "old_name")
        Course.objects.filter(pk=evaluation.course.pk).update(name_en="new_name")
        with self.assertNumQueries(0):
            self.assertEqual(evaluation.course.name_en, "old_name")

        # method drops that cache
        discard_cached_related_objects(evaluation)
        with self.assertNumQueries(1):
            self.assertEqual(evaluation.course.name_en, "new_name")

        # Explicitly cached FK-fields (through select_related) are discarded
        evaluation = Evaluation.objects.filter(pk=evaluation.pk).select_related("course").first()
        Course.objects.filter(pk=evaluation.course.pk).update(name_en="even_newer_name")
        with self.assertNumQueries(0):
            self.assertEqual(evaluation.course.name_en, "new_name")
        discard_cached_related_objects(evaluation)
        with self.assertNumQueries(1):
            self.assertEqual(evaluation.course.name_en, "even_newer_name")

    def test_discard_cached_related_objects_discards_cached_reverse_foreign_key_instances(self):
        course = baker.make(Course)
        baker.make(Evaluation, course=course)
        discard_cached_related_objects(course)

        # Reverse FK-relationships are not implicitly cached:
        with self.assertNumQueries(1):
            self.assertEqual(len(list(course.evaluations.all())), 1)
        with self.assertNumQueries(1):
            self.assertEqual(len(list(course.evaluations.all())), 1)

        # Explicitly cached reverse FK-fields (through prefetch_related_objects) are discarded
        prefetch_related_objects([course], "evaluations")
        with self.assertNumQueries(0):
            self.assertEqual(len(list(course.evaluations.all())), 1)
        discard_cached_related_objects(course)
        with self.assertNumQueries(1):
            self.assertEqual(len(list(course.evaluations.all())), 1)

        # Explicitly cached reverse FK-fields (through prefetch_related) are discarded
        course = Course.objects.filter(pk=course.pk).prefetch_related("evaluations").first()
        with self.assertNumQueries(0):
            self.assertEqual(len(list(course.evaluations.all())), 1)
        discard_cached_related_objects(course)
        with self.assertNumQueries(1):
            self.assertEqual(len(list(course.evaluations.all())), 1)

    def test_discard_cached_related_objects_discards_cached_m2m_instances(self):
        evaluation = baker.make(Evaluation)
        baker.make(Contribution, evaluation=evaluation)

        # M2M fields are not implicitly cached
        with self.assertNumQueries(1):
            self.assertEqual(len(list(evaluation.contributions.all())), 2)
        with self.assertNumQueries(1):
            self.assertEqual(len(list(evaluation.contributions.all())), 2)

        # Explicitly cached M2M fields (through prefetch_related_objects) are discarded
        prefetch_related_objects([evaluation], "contributions")
        with self.assertNumQueries(0):
            self.assertEqual(len(list(evaluation.contributions.all())), 2)
        discard_cached_related_objects(evaluation)
        with self.assertNumQueries(1):
            self.assertEqual(len(list(evaluation.contributions.all())), 2)

        # Explicitly cached M2M fields (through prefetch_related) are discarded
        evaluation = Evaluation.objects.filter(pk=evaluation.pk).prefetch_related("contributions").first()
        with self.assertNumQueries(0):
            self.assertEqual(len(list(evaluation.contributions.all())), 2)
        discard_cached_related_objects(evaluation)
        with self.assertNumQueries(1):
            self.assertEqual(len(list(evaluation.contributions.all())), 2)

    def test_get_object_from_dict_pk_entry_or_logged_40x_for_ints(self):
        # Invalid PKs
        with self.assertRaises(SuspiciousOperation):
            get_object_from_dict_pk_entry_or_logged_40x(Evaluation, {}, "pk")

        with self.assertRaises(SuspiciousOperation):
            get_object_from_dict_pk_entry_or_logged_40x(Evaluation, {"pk": "Not a number"}, "pk")

        # Valid id, but object doesn't exist
        with self.assertRaises(Http404):
            get_object_from_dict_pk_entry_or_logged_40x(Evaluation, {"pk": "1234"}, "pk")

        # valid
        evaluation = baker.make(Evaluation)
        self.assertEqual(
            get_object_from_dict_pk_entry_or_logged_40x(Evaluation, {"pk": str(evaluation.pk)}, "pk"), evaluation
        )

    def test_get_object_from_dict_pk_entry_or_logged_40x_for_uuids(self):
        # invalid UUIDs
        with self.assertRaises(SuspiciousOperation):
            get_object_from_dict_pk_entry_or_logged_40x(TextAnswer, {}, "pk")

        with self.assertRaises(SuspiciousOperation):
            get_object_from_dict_pk_entry_or_logged_40x(TextAnswer, {"pk": "Not a number"}, "pk")

        with self.assertRaises(SuspiciousOperation):
            get_object_from_dict_pk_entry_or_logged_40x(TextAnswer, {"pk": "1234"}, "pk")

        with self.assertRaises(SuspiciousOperation):
            get_object_from_dict_pk_entry_or_logged_40x(TextAnswer, {"pk": "{00-0}"}, "pk")

        # Valid id, but object doesn't exist
        with self.assertRaises(Http404):
            get_object_from_dict_pk_entry_or_logged_40x(TextAnswer, {"pk": UUID(int=0)}, "pk")

        answer = baker.make(TextAnswer)
        self.assertEqual(get_object_from_dict_pk_entry_or_logged_40x(TextAnswer, {"pk": str(answer.pk)}, "pk"), answer)
