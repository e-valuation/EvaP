# EvaP Nix Setup

This document describes the experimental nix setup for EvaP.

## Development Setup

To develop EvaP, you will have to install [`git`](https://git-scm.com/downloads) and [`nix`](https://nixos.org/) (with support for nix flakes).

If you are using Windows, we recommend that you [install the Windows Terminal](https://aka.ms/terminal) and set up the Windows Subsystem for Linux.
[Install WSL2](https://learn.microsoft.com/en-us/windows/wsl/install), start an Ubuntu VM, and [enable systemd support](https://devblogs.microsoft.com/commandline/systemd-support-is-now-available-in-wsl/).
Now, you can follow the Linux instructions to install git and nix.

To install nix on your computer, we recommend that you use the [Determinate Nix Installer](https://install.determinate.systems/).
Alternatively, you can use a virtual machine or container, as long as it can run nix. For example, see this [example setup with `podman`](todo).

Next, clone the EvaP repository using `git clone --recurse-submodules https://github.com/e-valuation/EvaP.git`.
When you are inside the `EvaP` directory, you can
- use `nix run .#services` to run the database system storing EvaP's data, and
- run `nix develop` to make all needed development tools available in your current shell session.

You always need to enter the `nix develop` environment before you can use the `./manage.py` script.
For convenience, you can install [`direnv`](https://direnv.net/) and [`nix-direnv`](https://github.com/nix-community/nix-direnv) to automatically enter the `nix develop` environment.

After your first setup, you should run `./manage.py first-time-setup`.
Finally, you can start EvaP by running `./manage.py run`.
Open your browser at http://localhost:8000/ and login with email evap@institution.example.com and password evap.

# (wiki article with podman setup)

You can use [`podman`](https://podman.io/) to start a container to develop EvaP.
The container will be isolated from the rest of your system, so that you do not need to install nix on your computer.

Create a new file called `Containerfile` (TODO: should we just include this file in the repo?) with the following contents (adapted from https://github.com/DeterminateSystems/nix-installer/blob/04b07fa15e527f23cc4a3c0db0a1b3aaa0160dc0/README.md#in-a-container):
```Containerfile
FROM docker.io/ubuntu:latest
# TODO: fix a version?

RUN apt-get update -y && apt-get install curl systemd -y

RUN curl --proto '=https' --tlsv1.2 -sSf -L https://install.determinate.systems/nix | sh -s -- install linux \
  --extra-conf "sandbox = false" \
  --no-start-daemon \
  --no-confirm

# TODO: add a new user?
# TODO: install direnv
# TODO: automatically start databases?

WORKDIR /evap

CMD [ "/bin/systemd" ]
```

Then, build an image with `podman build -t evap-image .` and create a container with `podman create --name evap-container -v /path/to/your/evap/directory:/evap -p 8000:8000 evap-image`.

From now on, you can use the container whenever you want to work on EvaP.
Start the container with `podman start evap-container` and enter it with `podman exec -it evap-container /bin/bash`.
After entering the container, you should be able to run `nix develop`.
