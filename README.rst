EvaP - Evaluation Platform
==========================

|build| |dependencies| |landscape| |coveralls|

What is EvaP?
-------------

EvaP is the course evaluation system used internally at Hasso Plattner Institute.

For the documentation, please see our `wiki <https://github.com/fsr-itse/EvaP/wiki>`_.

Installation
------------
The vagrant setup is shown here. For manual installation instructions and production deployment please see the `wiki page on installation <https://github.com/fsr-itse/EvaP/wiki/Installation>`_.

(0) Checkout EvaP and its submodules::

        git clone --recurse-submodules git@github.com:fsr-itse/EvaP.git

(1) After installing Vagrant_, run in your EvaP root directory::

        vagrant up

(2) Open your browser::

        http://localhost:8000/

(3) Log in with the following credentials::

        username: evap
        password: evap

That's it!


Contributing
------------

We'd love to see contributions, feel free to fork! You should probably branch off ``master``, the branch ``release`` is used for stable revisions.


Mailinglist
-----------

We have a mailinglist called evap-dev@lists.myhpi.de.

You can add yourself to the list at http://lists.myhpi.de/HQowKfvd70oVOTPEWG2UhB0OO0rfo8Z.


License
-------

See `LICENSE.rst <LICENSE.rst>`_.



.. |build| image:: https://travis-ci.org/fsr-itse/EvaP.svg
        :alt: Build Status
        :target: https://travis-ci.org/fsr-itse/EvaP
.. _Vagrant: http://www.vagrantup.com/
.. |dependencies| image:: https://gemnasium.com/fsr-itse/EvaP.svg
        :alt: Dependency Status
        :target: https://gemnasium.com/fsr-itse/EvaP
.. |landscape| image:: https://landscape.io/github/fsr-itse/EvaP/master/landscape.png
        :alt: Code Health
        :target: https://landscape.io/github/fsr-itse/EvaP/master
.. |coveralls| image:: https://coveralls.io/repos/fsr-itse/EvaP/badge.svg?branch=master&service=github
        :alt: Code Coverage
        :target: https://coveralls.io/github/fsr-itse/EvaP?branch=master
