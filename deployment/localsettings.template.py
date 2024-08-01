DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'evap',
        'USER': 'evap',
        'PASSWORD': 'evap',
        'HOST': '127.0.0.1',                    # Set to empty string for localhost.
        'PORT': '',                             # Set to empty string for default.
        'CONN_MAX_AGE': 600,
    }
}

# Make this unique, and don't share it with anybody.
SECRET_KEY = "${SECRET_KEY}"  # nosec

# Make apache work when DEBUG == False
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
