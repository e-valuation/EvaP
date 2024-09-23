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

  # added lines below:
  extraPackages = with pkgs; [ hello asciiquarium ];
  extraPythonPackages = ps: with ps; [ python-lsp-server ];
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

We provide a `Containerfile` that sets everything up:
```bash
podman build --tag evap-image nix/
podman create --name evap-container --userns=keep-id:uid=1001,gid=1001 --volume $PWD:/evap --publish 8000:8000 evap-image
```

From now on, you can use the container whenever you want to work on EvaP.
Start the container with `podman start evap-container` and enter it with `podman exec -it evap-container machinectl shell -q evap@`.
When entering the container for the first time, it may take a while until the database and development environment have finished setting up.
You can run `./manage.py test` to check whether everything worked out correctly.
Finally, stop the container with `podman stop evap-container`.
