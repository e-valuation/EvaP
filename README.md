# EvaP - Evaluation Platform

[![Build Status](https://github.com/e-valuation/EvaP/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/e-valuation/EvaP/actions?query=workflow%3A%22EvaP+Test+Suite%22)
[![Codacy Badge](https://app.codacy.com/project/badge/Grade/2cf538781fdc4680a7103bcf96417a9a)](https://app.codacy.com/gh/e-valuation/EvaP/dashboard)
[![codecov](https://codecov.io/gh/e-valuation/EvaP/branch/main/graph/badge.svg)](https://codecov.io/gh/e-valuation/EvaP)
[![PyPI](https://img.shields.io/pypi/v/evap)](https://pypi.org/project/evap/)


## What is EvaP?

EvaP is the course evaluation system used internally at Hasso Plattner Institute at the University of Potsdam.

For the documentation, please see our [wiki](https://github.com/e-valuation/EvaP/wiki).

## Development Setup

We use [nix](https://nixos.org/) to manage the development environment. To get a local version of EvaP running, follow these steps:

1. Windows only: Install the Windows Subsystem for Linux (WSL) using `wsl --install -d Ubuntu-24.04` (you may have to restart your computer and run this command again). Enter the WSL environment using the `wsl` command. On your first entry, you need to choose a username and password - anything works (for example: username "evap", password "evap"). Perform the next step outside of `/mnt`, for example by going to your home directory (`cd ~`).
2. Install [git](https://git-scm.com/downloads). Run the following commands to clone and enter the EvaP repository:
   ```bash
   git clone https://github.com/e-valuation/EvaP.git
   cd EvaP
   ```
3. Install nix by running `./nix/setup-nix`. Afterwards, if you get any errors when running nix, restart your computer.
4. Start EvaP and wait until you see a table view and the "evap" row shows "Running":
   ```bash
   nix run
   ```
5. Open your web browser at http://localhost:8000/ and login with email `evap@institution.example.com` and password `evap`.

To stop EvaP, press `Ctrl-C` and confirm with `Enter`.

### What is going on?

The command `nix run` starts a program called `process-compose` which performs some initial setup and orchestrates a number of processes needed to run EvaP. In particular, `nix` and `process-compose` handle installation of all dependencies, setup of the postgres database and redis cache, compilation of TypeScript, SCSS, and translation files, and running the Django development server. When changing Python, HTML, SCSS, or TypeScript files, you do not have to restart the server.

## Contributing

We'd love to see contributions! PRs solving existing issues are most helpful to us. It's best if you ask to be assigned for the issue so we won't have multiple people working on the same issue. Feel free to open issues for bugs, setup problems, or feature requests. If you have other questions, feel free to contact the [organization members](https://github.com/orgs/e-valuation/people).

To work on EvaP, you can open a shell with all dependencies available:
```bash
cd EvaP
nix develop
./manage.py test # In the shell, you can use ./manage.py commands
```
To exit the development shell, press `Ctrl-D` or type `exit`.

If you start your code editor from the `nix develop` shell, it should automatically pick up all dependencies. If this does not work automatically, try using the `nix/nix-python` script in the EvaP project as the Python interpreter in your IDE.

After quitting `nix run`, you can run the command `nix run .#clean-setup` to remove persistent state (database, node modules, localsettings).
Afterwards, `nix run` will recreate everything when you run it the next time.

Before committing, run `./manage.py precommit` or alternatively, the individual commands:
- `./manage.py typecheck`
- `./manage.py test` (check out [--keepdb](https://docs.djangoproject.com/en/6.0/ref/django-admin/#cmdoption-test-keepdb) and [--parallel](https://docs.djangoproject.com/en/6.0/ref/django-admin/#cmdoption-test-parallel) for faster execution)
- `./manage.py lint`
- `./manage.py format`

You can also set up `ruff`, `pylint`, and `prettier` in your IDE to avoid doing this manually all the time.

### Creating a Pull Request (Workflow Suggestion)
1. (once) [Fork](https://github.com/e-valuation/EvaP/fork) the repository so you have a GitHub repo that you have write access to.

2. (once) Set up some authentication for GitHub that allows push access. A common option is using [SSH keys](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/about-ssh), the remaining instructions assume an SSH key setup. An alternative is using the [GitHub CLI tool](https://cli.github.com/).

3. (once) Ensure your [git remotes](https://git-scm.com/book/en/v2/Git-Basics-Working-with-Remotes) are setup to use SSH. To fetch the up-to-date state of the official repo, it's useful to have an "upstream" remote configured:
   ```bash
   git remote set-url origin git@github.com:<your-username>/EvaP.git
   git remote add upstream git@github.com:e-valuation/EvaP.git
   ```

4. Create a branch (`git switch -c <your-branch-name>`), commit your changes (`git add` and `git commit`), and push them (`git push`). "Push" will ask you to specify an upstream branch (`git push -u origin <your-branch-name>`).

5. GitHub should now ask you whether you want to open a pull request ("PR"). If the PR solves an issue, use one of GitHub's [magic keywords](https://docs.github.com/en/issues/tracking-your-work-with-issues/linking-a-pull-request-to-an-issue) (like "fixes") in the pull request description to create a link between your PR and the issue. If necessary, please also provide a short summary of your changes in the description.


## License

MIT, see [LICENSE.md](LICENSE.md).


## Supported Browsers

The platform is only tested in Mozilla Firefox and Google Chrome. Other browsers might not render all pages correctly.
