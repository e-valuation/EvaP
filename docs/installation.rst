Installation
============

Dependencies
------------

EvaP is written in Python using the Django framework and you need at least
Python 2.6 to run it. Apart from Python and Django there are some other
dependencies that are listed in the file ``requirements.txt``. The file is 
in a format that pip can use to automatically install all the requirements.

Filesystem Structure
--------------------

We recommend that you install the application into the directory ``/opt/evap``
according to the filesystem hierarchy standard. Clone the repository or copy the
files into that directory. The installation should be correct if the settings
file has the path ``/opt/evap/evap/settings.py``. Make sure that all files and
directories are readable by the Apache web server. Additionally please make sure
that the directory ``/opt/evap/evap/upload`` is writable by the web server.

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

File Refresh
------------

You have to run some additional commands during the installation and whenever
you upgrade the software. Perform these steps in the ``/opt/evap/evap``
directory after you have upgraded the files:

- ``python manage.py migrate`` to perform any potential database updates.
- ``python manage.py collectstatic`` to collect all files that the front-end
  webserver should serve.
- ``python manage.py compilemessages`` to update the binary translation catalog.

Finally, restart the Apache web server.

Apache 2 Configuration
----------------------

We recommend the following Apache configuration:

::

        WSGIScriptAlias / /opt/evap/handler.wsgi
        <Location /login>
                AuthName "HPI Domain Login"
                AuthType Kerberos
                KrbAuthRealms HPI.UNI-POTSDAM.DE
                KrbMethodNegotiate On
                KrbMethodK5Passwd On
                KrbVerifyKDC off

                Require valid-user
        </Location>

        Alias /static /opt/evap/evap/staticfiles
        Alias /media /opt/evap/evap/upload

Cron Configuration
----------------------

EvaP has components which need to react to timed events.
This behavior is implemented by running a cronjob, which in turn triggers
a management command.

For example you could use a /etc/cron.hourly/evap lie

::

    #!/bin/sh
    
    pushd  /opt/evap/evap
    python manage.py run_tasks
    popd
