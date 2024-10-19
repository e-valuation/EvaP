# EvaP - Evaluation Platform

[![Build Status](https://github.com/e-valuation/EvaP/workflows/EvaP%20Test%20Suite/badge.svg?branch=main)](https://github.com/e-valuation/EvaP/actions?query=workflow%3A%22EvaP+Test+Suite%22)
[![Codacy Badge](https://app.codacy.com/project/badge/Grade/2cf538781fdc4680a7103bcf96417a9a)](https://app.codacy.com/gh/e-valuation/EvaP/dashboard)
[![codecov](https://codecov.io/gh/e-valuation/EvaP/branch/main/graph/badge.svg)](https://codecov.io/gh/e-valuation/EvaP)


## What is EvaP?

EvaP is the course evaluation system used internally at Hasso Plattner Institute at the University of Potsdam.

For the documentation, please see our [wiki](https://github.com/e-valuation/EvaP/wiki).

## Development Setup

We use [nix](https://nixos.org/) to manage the development environment.

1. Windows only: Install the Windows Subsystem for Linux (WSL) using `wsl --install -d Ubuntu-24.04` (you may have to restart your computer and run this command again). Enter the WSL environment using the `wsl` command. On your first entry, you need to choose a username and password - anything works (for example: username "evap", password "evap"). Perform the next step outside of `/mnt`, for example by going to your home directory (`cd ~`).
2. Install [git](https://git-scm.com/downloads). Run the following commands to clone and enter the EvaP repository:
   ```
   git clone --recurse-submodules https://github.com/e-valuation/EvaP.git
   cd EvaP
   ```
3. On Linux and WSL, install nix by running `./nix/setup-nix`. On MacOS, install nix using the [Determinate Nix Installer](https://install.determinate.systems/). Afterwards, if you get a permission error when running nix, restart your computer.
4. Start the needed background services for EvaP:
   ```
   nix run .#services-full
   ```
5. Open a new terminal. Enter the development shell and start EvaP:
   ```
   cd EvaP
   nix develop
   ./manage.py run
   ```
6. Open your web browser at http://localhost:8000/ and login with email `evap@institution.example.com` and password `evap`.

To stop EvaP or the background services, press `Ctrl-C`.
To exit the development shell, press `Ctrl-D` or type `exit`.

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
