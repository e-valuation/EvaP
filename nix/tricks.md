# Optimizing the Development Environment

This page contains various tips and tricks around the development setup.

## Automatic Activation

To automatically activate the `nix develop` environment when entering the `EvaP` directory, you can install [`direnv`](https://direnv.net/) and [`nix-direnv`](https://github.com/nix-community/nix-direnv).
Afterwards, create the file `.envrc` with the following contents:
```
use flake
```

## Shell Completions

The file `deployment/manage_autocompletion.sh` contains bash completions (tab completions) for the `./manage.py` script.
To activate them, use `source deployment/manage_autocompletion.sh`.
You can also do this in your `.envrc` file (note that the completions only work for `bash` though).

## Extra Packages

To install additional packages in the `nix develop` environment, edit the `devShells` part in `flake.nix` like so:

```nix
devShells.default = pkgs.callPackage ./nix/shell.nix {
  inherit (self'.packages) evap;
  extraPackages = with pkgs; [ hello asciiquarium ]; # <--- added line here
};
```

Find the packages you are looking for at https://search.nixos.org/packages.
Make sure to not include these changes in your git commits.
You can use `git update-index --assume-unchanged`, if you know what you are doing.

## Clean Setup

To remove the directories created by the `initialize-setup` command, use the `clean-setup` command.

## Development Container with Podman

You can use [`podman`](https://podman.io/) to start a container to develop EvaP.
The container will be isolated from the rest of your system, so that you do not need to install nix on your computer.

Create a new file called `Containerfile` (TODO: should we just include this file in the repo?) with the following contents (adapted from https://github.com/DeterminateSystems/nix-installer/blob/04b07fa15e527f23cc4a3c0db0a1b3aaa0160dc0/README.md#in-a-container):
```Containerfile
FROM docker.io/ubuntu:latest

RUN apt-get update -y && apt-get install -y curl systemd direnv

RUN curl --proto '=https' --tlsv1.2 -sSf -L https://install.determinate.systems/nix | sh -s -- install linux \
  --extra-conf "sandbox = false" \
  --no-start-daemon \
  --no-confirm

# TODO: automatically start databases?

RUN groupadd --gid 1001 evap && useradd --uid 1001 --gid 1001 --no-user-group -ms /bin/bash evap
USER evap
WORKDIR /evap
RUN echo 'eval "$(direnv hook bash)"' >> ~/.bashrc

USER root
CMD [ "/bin/systemd" ]
```

Then, build an image and create a container with
```bash
podman build -t evap-image .
podman create --name evap-container --userns=keep-id:uid=1001,gid=1001 -v $PWD:/evap -p 8000:8000 evap-image
```

From now on, you can use the container whenever you want to work on EvaP.
Start the container with `podman start evap-container` and enter it with `podman exec -u evap -it evap-container /bin/bash`.
After entering the container, you should be able to run `nix develop`.

The container has `direnv` already set up, you can create the following `.envrc` and then allow it with `direnv allow`:
```
if ! has nix_direnv_version || ! nix_direnv_version 3.0.5; then
  source_url "https://raw.githubusercontent.com/nix-community/nix-direnv/3.0.5/direnvrc" "sha256-RuwIS+QKFj/T9M2TFXScjBsLR6V3A17YVoEW/Q6AZ1w="
fi
use flake
source deployment/manage_autocompletion.sh
```
