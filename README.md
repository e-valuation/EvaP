# EvaP - Evaluation Platform

[![Build Status](https://github.com/e-valuation/EvaP/workflows/EvaP%20Test%20Suite/badge.svg?branch=main)](https://github.com/e-valuation/EvaP/actions?query=workflow%3A%22EvaP+Test+Suite%22)
[![Codacy Badge](https://app.codacy.com/project/badge/Grade/2cf538781fdc4680a7103bcf96417a9a)](https://www.codacy.com/gh/e-valuation/EvaP/dashboard)
[![codecov](https://codecov.io/gh/e-valuation/EvaP/branch/main/graph/badge.svg)](https://codecov.io/gh/e-valuation/EvaP)


## What is EvaP?

EvaP is the course evaluation system used internally at Hasso Plattner Institute at the University of Potsdam.

For the documentation, please see our [wiki](https://github.com/e-valuation/EvaP/wiki).

## Development Setup

To develop EvaP, you will have to install [`git`](https://git-scm.com/downloads) and [`nix`](https://nixos.org/) with support for nix flakes.

If you are using Windows, we recommend that you [install the Windows Terminal](https://aka.ms/terminal) and set up the Windows Subsystem for Linux.
[Install WSL2](https://learn.microsoft.com/en-us/windows/wsl/install), start an Ubuntu VM, and [enable systemd support](https://devblogs.microsoft.com/commandline/systemd-support-is-now-available-in-wsl/).
Now, you can follow the Linux instructions to install git and nix.

To install nix on your computer, we recommend that you use the [Determinate Nix Installer](https://install.determinate.systems/).
Alternatively, you can use a virtual machine or container, as long as it can run nix. For example, see this [example setup with `podman`](./nix/tricks.md#development-container-with-podman).

Next, clone the EvaP repository using `git clone --recurse-submodules https://github.com/e-valuation/EvaP.git`.
When you are inside the `EvaP` directory, you can
- use `nix run .#services` to run the database system storing EvaP's data, and
- run `nix develop` to make all needed development tools available in your current shell session.

To initialize the database and perform additional setup steps, you need to run the `initialize-setup` command that is available in the `nix develop` environment.
You will only need to perform this step once.

You can start EvaP by running `./manage.py run`.
Open your browser at http://localhost:8000/ and login with email `evap@institution.example.com` and password `evap`.

For additional tips and tricks around the development setup, see [`nix/tricks.md`](./nix/tricks.md).

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
