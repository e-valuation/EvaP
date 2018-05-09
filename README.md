# EvaP - Evaluation Platform

[![build status](https://travis-ci.org/fsr-itse/EvaP.svg)](https://travis-ci.org/fsr-itse/EvaP)
[![Dependency Status](https://gemnasium.com/fsr-itse/EvaP.svg)](https://gemnasium.com/fsr-itse/EvaP)
[![Codacy Badge](https://api.codacy.com/project/badge/Grade/4721b900582d4ca1b0392af26f5f5c7b)](https://www.codacy.com/app/evap/EvaP?utm_source=github.com&amp;utm_medium=referral&amp;utm_content=fsr-itse/EvaP&amp;utm_campaign=Badge_Grade)
[![Code Coverage](https://coveralls.io/repos/github/fsr-itse/EvaP/badge.svg?branch=master)](https://coveralls.io/github/fsr-itse/EvaP?branch=master)


## What is EvaP?

EvaP is the course evaluation system used internally at Hasso Plattner Institute at the University of Potsdam.

For the documentation, please see our [wiki](https://github.com/fsr-itse/EvaP/wiki).


## Installation

The easiest setup using [Vagrant](https://www.vagrantup.com) and [VirtualBox](https://www.virtualbox.org) is shown here. For manual installation instructions and production deployment please see the [wiki page on installation](https://github.com/fsr-itse/EvaP/wiki/Installation).

0. Install [git](https://git-scm.com/downloads), [Vagrant](https://www.vagrantup.com/downloads.html) and [VirtualBox](https://www.virtualbox.org/wiki/Downloads)

1. Fork the Evap repository (using the Fork-button in the upper right corner on GitHub)

2. Run the following commands on the command line to clone the repository, create the Vagrant VM and run the Django development server:

        git clone --recurse-submodules https://github.com/<your_github_username>/EvaP.git
        cd EvaP
        vagrant up
        vagrant ssh
        ./manage.py run

3. Open your browser at http://localhost:8000/ and login with username ``evap`` and password ``evap``


That's it!


## Contributing

We'd love to see contributions, feel free to fork! You should probably branch off ``master``, the branch ``release`` is used for stable revisions.


## License

MIT, see [LICENSE.md](LICENSE.md).


## Supported Browsers

The platform is only tested in Mozilla Firefox and Google Chrome. Other browsers might not render all pages correctly.
