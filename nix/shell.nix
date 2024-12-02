{ pkgs, lib ? pkgs.lib, python3, pyproject-nix, uv2nix, pyproject-build-systems, workspaceRoot, extraPackages ? [ ], dependency-groups ? [ ], ... }:

let
  # When running a nix shell, XDG_DATA_DIRS will be populated so that bash_completion can (lazily) find this completion script
  evap-managepy-completion = pkgs.runCommand "evap-managepy-completion" { } ''
    mkdir -p "$out/share/bash-completion/completions"
    install ${../deployment/manage_autocompletion.sh} "$out/share/bash-completion/completions/manage.py.bash"
  '';

  clean-setup = pkgs.writeShellScriptBin "clean-setup" ''
    read -p "Delete node_modules/, data/ and evap/localsettings.py? [y/N] "
    [[ "$REPLY" =~ ^[Yy]$ ]] || exit 1
    set -ex
    rm -rf node_modules/ data/ evap/localsettings.py
  '';

  workspace = uv2nix.lib.workspace.loadWorkspace { inherit workspaceRoot; };
  overlay = workspace.mkPyprojectOverlay { sourcePreference = "wheel"; };
  package-overrides = final: prev: {
    psycopg-c = prev.psycopg-c.overrideAttrs (old: {
      nativeBuildInputs = (old.nativeBuildInputs or [ ]) ++ [ final.setuptools pkgs.postgresql ];
    });
  };
  baseSet = pkgs.callPackage pyproject-nix.build.packages { python = python3; };
  pythonSet = baseSet.overrideScope (lib.composeManyExtensions [ pyproject-build-systems.overlays.default overlay package-overrides ]);

  editableOverlay = workspace.mkEditablePyprojectOverlay { root = "$REPO_ROOT"; };
  editablePythonSet = pythonSet.overrideScope editableOverlay;
  venv = editablePythonSet.mkVirtualEnv "evap-dev-env" { evap = dependency-groups; };
in
pkgs.mkShell {
  packages = with pkgs; [
    nodejs
    gettext
    git

    venv
    clean-setup
    evap-managepy-completion
  ] ++ extraPackages;

  passthru = { inherit venv; };

  env.PUPPETEER_SKIP_DOWNLOAD = 1;

  shellHook = ''
    unset PYTHONPATH
    export REPO_ROOT=$(git rev-parse --show-toplevel)
    export UV_NO_SYNC=1
  '';
}
