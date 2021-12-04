SECRET_KEY = "evap-github-actions-secret-key"  # nosec
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "evap",
        "USER": "postgres",
        "PASSWORD": "postgres",
        "HOST": "postgres",
        "PORT": "5432",
    }
}
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://redis:6379/0",
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient", "MAX_ENTRIES": 5000},
    },
    "results": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://redis:6379/1",
        "TIMEOUT": None,
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient", "MAX_ENTRIES": 100000},
    },
    "sessions": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://redis:6379/2",
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient", "MAX_ENTRIES": 5000},
    },
}
