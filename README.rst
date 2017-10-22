EvaP - Evaluation Platform
==========================

|build| |dependencies| |landscape| |coveralls|

What is EvaP?
-------------

EvaP is the course evaluation system used internally at Hasso Plattner Institute.

For the documentation, please see our `wiki <https://github.com/fsr-itse/EvaP/wiki>`_.

Installation
------------
The easiest setup using Vagrant_ and VirtualBox_ is shown here. For manual installation instructions and production deployment please see the `wiki page on installation <https://github.com/fsr-itse/EvaP/wiki/Installation>`_.

(0) Install git_, Vagrant_ and VirtualBox_

(1) Fork the Evap repository (using the Fork-button in the upper right corner on GitHub)

(2) Run the following commands on the command line to clone the repository, create the Vagrant VM and run the Django development server::

        git clone --recurse-submodules https://github.com/<your_github_username>/EvaP.git
        cd EvaP
        vagrant up
        vagrant ssh
        ./manage.py run

(3) Open your browser at http://localhost:8000/ and login with username ``evap`` and password ``evap``


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
.. |dependencies| image:: https://gemnasium.com/fsr-itse/EvaP.svg
        :alt: Dependency Status
        :target: https://gemnasium.com/fsr-itse/EvaP
.. |landscape| image:: https://landscape.io/github/fsr-itse/EvaP/master/landscape.png
        :alt: Code Health
        :target: https://landscape.io/github/fsr-itse/EvaP/master
.. |coveralls| image:: https://coveralls.io/repos/github/fsr-itse/EvaP/badge.svg?branch=master
        :alt: Code Coverage
        :target: https://coveralls.io/github/fsr-itse/EvaP?branch=master
.. _Vagrant: https://www.vagrantup.com/downloads.html
.. _VirtualBox: https://www.virtualbox.org/wiki/Downloads
.. _git: https://git-scm.com/downloads
