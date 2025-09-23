# pylint: disable=invalid-name

import sys
from copy import deepcopy

from evap.settings_resolver import derived

TEST_RUNNER = "evap.evaluation.tests.tools.EvapTestRunner"
TESTING = "test" in sys.argv or "pytest" in sys.modules


@derived(prev={"STORAGES"}, final={"TESTING"})
def STORAGES(prev, final):
    if final.TESTING:
        storages = deepcopy(prev.STORAGES)
        # do not use ManifestStaticFilesStorage as it requires running collectstatic beforehand
        storages["staticfiles"]["BACKEND"] = "django.contrib.staticfiles.storage.StaticFilesStorage"
        return storages
    return prev.STORAGES


@derived(prev={"CACHES"}, final={"TESTING"})
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
def BAKER_CUSTOM_FIELDS_GEN(prev, final):
    if final.TESTING:
        from model_bakery import random_gen  # noqa: PLC0415

        # give random char field values a reasonable length
        return {"django.db.models.CharField": lambda: random_gen.gen_string(20)}
    return prev.BAKER_CUSTOM_FIELDS_GEN
