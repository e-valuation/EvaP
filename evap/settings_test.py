from pathlib import Path

SECRET_KEY = "evap-github-actions-secret-key"  # nosec
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "evap",
        "USER": "evap",
        "PASSWORD": "evap",
        "HOST": Path("./data/").resolve(),
    }
}

REDIS_URL = f"unix://{Path('./data/redis.socket').resolve()}"

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": f"{REDIS_URL}?db=0",
    },
    "results": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": f"{REDIS_URL}?db=1",
        "TIMEOUT": None,  # is always invalidated manually
    },
    "sessions": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": f"{REDIS_URL}?db=2",
    },
}
