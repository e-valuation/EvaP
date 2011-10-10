Installation
============

Dependencies
------------

EvaP is written in Python using the Django framework. It has the following 
dependencies:

- Python 2.6
- Django 1.3
- South 0.7.3
- PIL 1.1.7
- xlrd 0.7.1

You also need the following packages if you want to run the test suite:

- django-webtest 1.4.2
- WebTest 1.3, WebOb 1.1.1

There is a file ``requirements.txt`` which lists a files in a format that pip 
can use to automatically install all the requirements.

Settings
--------

The configuration of the application is done by modifying the ``settings.py`` 
in the ``evap`` folder. For a production environment you should change the 
following settings:

- Choose an appropriate database and modify the ``default`` entry in the 
  ``DATABASES`` settings. Please make sure that you use a database that 
  supports transactions.
- Change the ``DEFAULT_FROM_EMAIL`` to an administrative mail address.
- Change ``MEDIA_ROOT`` to a directory that is writable by the web application.
  This directory will hold user-uploaded files like photos.
- You might want to change the ``SECRET_KEY``.
- Modify the ``LOGGING`` configuration so that it suits your needs.
- Finally, set ``DEBUG`` to ``False``.

Preparation
-----------

Run ``manage.py collectstatic`` to collect all files that the front-end 
webserver should serve.
