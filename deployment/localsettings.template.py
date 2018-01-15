DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',   # postgresql', 'mysql', 'sqlite3' or 'oracle'.
        'NAME': 'evap',                         # Or path to database file if using sqlite3.
        'USER': 'evap',                         # Not used with sqlite3.
        'PASSWORD': 'evap',                     # Not used with sqlite3.
        'HOST': '127.0.0.1',                    # Set to empty string for localhost. Not used with sqlite3.
        'PORT': '',                             # Set to empty string for default. Not used with sqlite3.
        'CONN_MAX_AGE': 600,
    }
}

SECRET_KEY = "${SECRET_KEY}"
