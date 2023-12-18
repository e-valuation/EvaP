# EvaP - Evaluation Platform

[![Build Status](https://github.com/e-valuation/EvaP/workflows/EvaP%20Test%20Suite/badge.svg?branch=main)](https://github.com/e-valuation/EvaP/actions?query=workflow%3A%22EvaP+Test+Suite%22)
[![Codacy Badge](https://app.codacy.com/project/badge/Grade/2cf538781fdc4680a7103bcf96417a9a)](https://www.codacy.com/gh/e-valuation/EvaP/dashboard)
[![codecov](https://codecov.io/gh/e-valuation/EvaP/branch/main/graph/badge.svg)](https://codecov.io/gh/e-valuation/EvaP)


## What is EvaP?

EvaP is the course evaluation system used internally at Hasso Plattner Institute at the University of Potsdam.

For the documentation, please see our [wiki](https://github.com/e-valuation/EvaP/wiki).


## Installation (for Development)

The easiest setup using [Vagrant](https://www.vagrantup.com) is shown here.

1. Install [git](https://git-scm.com/downloads), [Vagrant](https://www.vagrantup.com/downloads.html), and one of [VirtualBox](https://www.virtualbox.org/wiki/Downloads) (recommended) or [Docker](https://docs.docker.com/engine/install/) (for ARM systems).

2. Run the following commands on the command line to clone the repository, create the Vagrant VM and run the Django development server.
   * If you are familiar with the fork-based open source workflow, create a fork and clone that (using SSH if you prefer that).

   * Windows users: We have observed [weird](https://www.github.com/git-for-windows/git/issues/4705) [behavior](https://www.github.com/git-for-windows/git/issues/4704) with SSH in Git Bash on Windows and thus recommend using PowerShell instead.

   * To use Docker, replace `vagrant up` with `vagrant up --provider docker && vagrant provision`.

   ```bash
   git clone --recurse-submodules https://github.com/e-valuation/EvaP.git
   cd EvaP
   vagrant up
   vagrant ssh
   ```
   and, after the last command opened an SSH session in the development machine:
   ```bash
   ./manage.py run
   ```

3. Open your browser at http://localhost:8000/ and login with email `evap@institution.example.com` and password `evap`.

That's it!

## Contributing

We'd love to see contributions! PRs solving existing issues are most helpful to us. It's best if you ask to be assigned for the issue so we won't have multiple people working on the same issue. Feel free to open issues for bugs, setup problems, or feature requests. If you have other questions, feel free to contact the [organization members](https://github.com/orgs/e-valuation/people). You should probably branch off `main`, the branch `release` is used for stable revisions.

Before committing, run the following commands:
- `./manage.py test` (runs the test suite)
- `./manage.py lint` (runs linting)
- `./manage.py format` (applies automatic code formatting)

or, to combine all three, simply run `./manage.py precommit`.

You can also set up `pylint`, `isort`, `black` and `prettier` in your IDE to avoid doing this manually all the time.

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
