# EvaP - Evaluation Platform

[![Build Status](https://github.com/e-valuation/EvaP/workflows/EvaP%20Test%20Suite/badge.svg?branch=main)](https://github.com/e-valuation/EvaP/actions?query=workflow%3A%22EvaP+Test+Suite%22)
[![Codacy Badge](https://app.codacy.com/project/badge/Grade/2cf538781fdc4680a7103bcf96417a9a)](https://www.codacy.com/gh/e-valuation/EvaP/dashboard)
[![codecov](https://codecov.io/gh/e-valuation/EvaP/branch/main/graph/badge.svg)](https://codecov.io/gh/e-valuation/EvaP)


## What is EvaP?

EvaP is the course evaluation system used internally at Hasso Plattner Institute at the University of Potsdam.

For the documentation, please see our [wiki](https://github.com/e-valuation/EvaP/wiki).


## Installation

The easiest setup using [Vagrant](https://www.vagrantup.com) is shown here.

0. Install [git](https://git-scm.com/downloads), [Vagrant](https://www.vagrantup.com/downloads.html), and one of [VirtualBox](https://www.virtualbox.org/wiki/Downloads) (recommended) or [Docker](https://docs.docker.com/engine/install/) (for ARM systems).

1. Fork the Evap repository (using the Fork-button in the upper right corner on GitHub).

2. Windows users only (might not apply for the linux subsystem):
   * Line endings: git's [`core.autocrlf` setting](https://git-scm.com/book/en/v2/Customizing-Git-Git-Configuration#_core_autocrlf) has to be `false` or `input` so git does not convert line endings on checkout, because the code will be used in a linux VM. We suggest using this command in Git Bash:

     ```bash
     git config --global core.autocrlf input
     ```

   * Symlink Privileges: Our setup script for the VM creates symlinks in the repository folder. This requires either [explicitly allowing your user account to create symlinks](https://superuser.com/a/105381) or simply running the commands in step 3 as administrator. Thus, we suggest doing step 3 in a Git Bash that was started using "Run as administrator". Generally, this is only required for the first time executing `vagrant up`.

3. Run the following commands on the command line to clone the repository, create the Vagrant VM and run the Django development server.
    To use Docker, replace `vagrant up` with `vagrant up --provider docker && vagrant provision`.
    ```bash
    git clone --recurse-submodules https://github.com/<your_github_username>/EvaP.git
    cd EvaP
    vagrant up
    vagrant ssh
    ./manage.py run
    ```

4. Open your browser at http://localhost:8000/ and login with email ``evap@institution.example.com`` and password ``evap``.


That's it!

## Contributing

We'd love to see contributions, feel free to fork! You should probably branch off ``main``, the branch ``release`` is used for stable revisions.

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
