EvaP - Evaluation Platform
==========================

|build|_

What is EvaP?
-------------

EvaP (a successor to the infamous EvaJ) is a course evaluation system used
internally at Hasso Plattner Institute.

For the documentation, please look into the *docs* subdirectory or the generated
documentation at ReadTheDocs: https://evap.readthedocs.org.

Installation
------------
The vagrant setup and a quick manual install are shown here. For more detailed instructions (including production deployment) see http://evap.readthedocs.org/en/latest/installation.html.

(0) Checkout EvaP and its submodules::

        git clone --recurse-submodules git@github.com:fsr-itse/EvaP.git

Vagrant
~~~~~~~
(1) After installing Vagrant_, run in your EvaP root directory::

        vagrant up

(2) create yourself an admin account::

        vagrant ssh
        cd /vagrant
        python manage.py createsuperuser
        
(3) and open your browser::

        http://localhost:8000/

Manual Install
~~~~~~~~~~~~~~

(1) simply install the requirements::

        pip install -r requirements.txt

(2) run the database initialization and migrations::

        python manage.py syncdb
        python manage.py migrate

(3) make the translations work::

        python manage.py compilemessages

(4) create yourself an admin account::

        python manage.py createsuperuser

(5) start the development server::

        python evap/manage.py runserver

(6) and open your browser::

        http://localhost:8000/

More detailed instructions (also covering production deployment) can be found at http://evap.readthedocs.org/en/latest/installation.html.

Mailinglist
-----------

We have a mailinglist evap-dev@lists.myhpi.de

You can add yourself to the list at http://lists.myhpi.de/HQowKfvd70oVOTPEWG2UhB0OO0rfo8Z

Contributors to EvaP
--------------------

- Michael Grünewald
- Stefan Richter
- Matthias Jacob
- Arvid Heise
- Nicolas Fricke
- Stefanie Reinicke
- Thomas Schulz
- Matthias Kohnen
- Johannes Linke
- Johannes Wolf
- others

License
-------

The software is licensed under the MIT license. The source code includes other
components in whole or in part; namely jQuery, jQuery UI, jQuery UI Multiselect
and jQuery Formset. These components are used under the MIT resp. BSD licenses.
It also uses symbols of the Silk icon set from famfamfam.com, which is licensed
under a Creative Commons Attribution 2.5 License.

The source repository may include logos, names or other trademarks of the
Hasso Plattner Institute or other entities; potential usage restrictions for
these elements still apply and are not touched by the software license.

::

  EvaP - Evaluation Platform
  Copyright (C) 2011  Michael Grünewald and Stefan Richter

  Permission is hereby granted, free of charge, to any person obtaining a copy
  of this software and associated documentation files (the "Software"), to deal
  in the Software without restriction, including without limitation the rights
  to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
  copies of the Software, and to permit persons to whom the Software is
  furnished to do so, subject to the following conditions:

  The above copyright notice and this permission notice shall be included in
  all copies or substantial portions of the Software.

  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
  THE SOFTWARE.

.. |build| image:: https://travis-ci.org/fsr-itse/EvaP.png
.. _build: https://travis-ci.org/fsr-itse/EvaP
.. _Vagrant: http://www.vagrantup.com/
