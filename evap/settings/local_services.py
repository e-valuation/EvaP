# pylint: disable=unused-argument,invalid-name

from evap.settings_resolver import derived


@derived(final={"DATADIR"})
def DATABASES(prev, final):
    return {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": "evap",
            "USER": "evap",
            "PASSWORD": "evap",
            # Absolute path to use unix domain socket
            "HOST": final.DATADIR.resolve(),
            "CONN_MAX_AGE": 600,
        }
    }


@derived(final={"DATADIR"})
def REDIS_URL(prev, final):
    return f"unix://{(final.DATADIR / 'redis.socket').resolve()}"


@derived(final={"REDIS_URL"})
def CACHES(prev, final):
    return {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": f"{final.REDIS_URL}?db=0",
        },
        "results": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": f"{final.REDIS_URL}?db=1",
            "TIMEOUT": None,  # is always invalidated manually
        },
        "sessions": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": f"{final.REDIS_URL}?db=2",
        },
    }
