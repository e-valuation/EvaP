from copy import deepcopy
import sys
from evap.new_settings.lazy import derived
from model_bakery import random_gen


class DevSettings:
    PAGE_URL = "localhost:8000"

    @derived(prev={"INSTALLED_APPS"}, final={"DEBUG"})
    @staticmethod
    def INSTALLED_APPS(prev, final):
        if final.DEBUG:
            return prev.INSTALLED_APPS + ["evap.development"]
        return prev.INSTALLED_APPS

    CONTACT_EMAIL = "webmaster@localhost"
    DEFAULT_FROM_EMAIL = "webmaster@localhost"
    REPLY_TO_EMAIL = DEFAULT_FROM_EMAIL
    SEND_ALL_EMAILS_TO_ADMINS_IN_BCC = False

    LEGAL_NOTICE_TEXT = (
        "Objection! (this is a default setting that the administrators should change, please contact them)"
    )


def replace_if_testing(name, value):
    return derived(prev={name}, final={"TESTING"})(lambda prev, final: value if final.TESTING else getattr(prev, name))


class TestSettings:
    TEST_RUNNER = "evap.evaluation.tests.tools.EvapTestRunner"
    TESTING = "test" in sys.argv or "pytest" in sys.modules

    @derived(prev={"STORAGES"}, final={"TESTING"})
    @staticmethod
    def STORAGES(prev, final):
        if final.TESTING:
            storages = deepcopy(prev.STORAGES)
            # do not use ManifestStaticFilesStorage as it requires running collectstatic beforehand
            storages["staticfiles"]["BACKEND"] = "django.contrib.staticfiles.storage.StaticFilesStorage"
            return storages
        return prev.STORAGES

    @derived(prev={"CACHES"}, final={"TESTING"})
    @staticmethod
    def CACHES(prev, final):
        if final.TESTING:
            # use the database for caching. it's properly reset between tests in constrast to redis,
            # and does not change behaviour in contrast to disabling the cache entirely.
            return {
                "default": {
                    "BACKEND": "django.core.cache.backends.db.DatabaseCache",
                    "LOCATION": "testing_cache_default",
                },
                "results": {
                    "BACKEND": "django.core.cache.backends.db.DatabaseCache",
                    "LOCATION": "testing_cache_results",
                },
                "sessions": {
                    "BACKEND": "django.core.cache.backends.db.DatabaseCache",
                    "LOCATION": "testing_cache_sessions",
                },
            }
        return prev.CACHES

    @derived(prev={"BAKER_CUSTOM_FIELDS_GEN"}, final={"TESTING"})
    @staticmethod
    def BAKER_CUSTOM_FIELDS_GEN(prev, final):
        if final.TESTING:
            # give random char field values a reasonable length
            return {"django.db.models.CharField": lambda: random_gen.gen_string(20)}
        return prev.BAKER_CUSTOM_FIELDS_GEN


def show_toolbar(request):
    return True


class DebugToolbarSettings:
    # Very helpful but eats a lot of performance on sql-heavy pages.
    # Works only with DEBUG = True and Django's development server (so no apache).
    ENABLE_DEBUG_TOOLBAR = False

    @derived(final={"DEBUG", "ENABLE_DEBUG_TOOLBAR", "TESTING"})
    @staticmethod
    def REALLY_ENABLE_DEBUG_TOOLBAR(prev, final):
        return final.ENABLE_DEBUG_TOOLBAR and final.DEBUG and not final.TESTING

    @derived(prev={"INSTALLED_APPS"}, final={"REALLY_ENABLE_DEBUG_TOOLBAR"})
    @staticmethod
    def INSTALLED_APPS(prev, final):
        if final.REALLY_ENABLE_DEBUG_TOOLBAR:
            return prev.INSTALLED_APPS + ["debug_toolbar"]
        return prev.INSTALLED_APPS

    @derived(prev={"MIDDLEWARE"}, final={"REALLY_ENABLE_DEBUG_TOOLBAR"})
    @staticmethod
    def MIDDLEWARE(prev, final):
        if final.REALLY_ENABLE_DEBUG_TOOLBAR:
            return ["debug_toolbar.middleware.DebugToolbarMiddleware"] + prev.MIDDLEWARE
        return prev.MIDDLEWARE

    @derived(prev={"DEBUG_TOOLBAR_CONFIG"}, final={"REALLY_ENABLE_DEBUG_TOOLBAR"})
    @staticmethod
    def DEBUG_TOOLBAR_CONFIG(prev, final):
        if final.REALLY_ENABLE_DEBUG_TOOLBAR:
            return {
                "SHOW_TOOLBAR_CALLBACK": "evap.new_settings.dev.show_toolbar",
                "JQUERY_URL": "",
            }
        return prev.DEBUG_TOOLBAR_CONFIG
