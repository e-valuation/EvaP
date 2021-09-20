# EvaP - Evaluation Platform

[![Build Status](https://github.com/e-valuation/EvaP/workflows/EvaP%20Test%20Suite/badge.svg?branch=master)](https://github.com/e-valuation/EvaP/actions?query=workflow%3A%22EvaP+Test+Suite%22)
[![Requirements Status](https://requires.io/github/e-valuation/EvaP/requirements.svg?branch=master)](https://requires.io/github/e-valuation/EvaP/requirements/?branch=master)
[![Codacy Badge](https://app.codacy.com/project/badge/Grade/2cf538781fdc4680a7103bcf96417a9a)](https://www.codacy.com/gh/e-valuation/EvaP/dashboard)
[![codecov](https://codecov.io/gh/e-valuation/EvaP/branch/master/graph/badge.svg)](https://codecov.io/gh/e-valuation/EvaP)


## What is EvaP?

EvaP is the course evaluation system used internally at Hasso Plattner Institute at the University of Potsdam.

For the documentation, please see our [wiki](https://github.com/e-valuation/EvaP/wiki).


## Installation

The easiest setup using [Vagrant](https://www.vagrantup.com) and [VirtualBox](https://www.virtualbox.org) is shown here. For manual installation instructions and production deployment please see the [wiki page on installation](https://github.com/e-valuation/EvaP/wiki/Installation).

0. Install [git](https://git-scm.com/downloads), [Vagrant](https://www.vagrantup.com/downloads.html) and [VirtualBox](https://www.virtualbox.org/wiki/Downloads)

1. Fork the Evap repository (using the Fork-button in the upper right corner on GitHub)

2. If you're using Windows, you want to change git's autocrlf setting to "input" so git will not change line endings when checking out files, using this command:

        git config --global core.autocrlf input

3. Run the following commands on the command line to clone the repository, create the Vagrant VM and run the Django development server:

        git clone --recurse-submodules https://github.com/<your_github_username>/EvaP.git
        cd EvaP
        vagrant up
        vagrant ssh
        ./manage.py run

4. Open your browser at http://localhost:8000/ and login with email ``evap@institution.example.com`` and password ``evap``


That's it!


## Contributing

We'd love to see contributions, feel free to fork! You should probably branch off ``master``, the branch ``release`` is used for stable revisions.

Before committing, run the following commands:
- `./manage.py test` (runs the test suite)
- `./manage.py lint` (runs the linter)
- `./manage.py format` (applies automatic code formatting on Python files)

or, to combine all three, simply run `./manage.py precommit`

You can also set up `pylint`, `isort` and `black` in your IDE to avoid doing this manually all the time.

## License

MIT, see [LICENSE.md](LICENSE.md).


## Supported Browsers

The platform is only tested in Mozilla Firefox and Google Chrome. Other browsers might not render all pages correctly.
