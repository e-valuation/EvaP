{ pkgs, lib ? pkgs.lib, python3, pyproject-nix, uv2nix, pyproject-build-systems, workspaceRoot, extraPackages ? [ ], dependency-groups ? [ ], our-packages, ... }:

let
  # When running a nix shell, XDG_DATA_DIRS will be populated so that bash_completion can (lazily) find this completion script
  evap-managepy-completion = pkgs.runCommand "evap-managepy-completion" { } ''
    mkdir -p "$out/share/bash-completion/completions"
    install ${../evap/development/manage_autocompletion.sh} "$out/share/bash-completion/completions/manage.py.bash"
  '';

  workspace = uv2nix.lib.workspace.loadWorkspace { inherit workspaceRoot; };
  overlay = workspace.mkPyprojectOverlay { sourcePreference = "wheel"; };
  package-overrides = final: prev: {
    psycopg-c = prev.psycopg-c.overrideAttrs (old: {
      nativeBuildInputs = (old.nativeBuildInputs or [ ]) ++ [ final.setuptools pkgs.postgresql ];
    });
  };
  evap-override = final: prev: {
    evap = prev.evap.overrideAttrs (old: {
      src = lib.fileset.toSource {
        root = old.src;
        # Small set of required files for the editable package
        fileset = lib.fileset.unions [
          (old.src + "/pyproject.toml")
          (old.src + "/README.md")
          (old.src + "/evap/__init__.py")
        ];
      };
      nativeBuildInputs = old.nativeBuildInputs ++ final.resolveBuildSystem {
        # Needed to install evap in editable mode for development
        editables = [ ];
      };
    });
  };

  baseSet = pkgs.callPackage pyproject-nix.build.packages { python = python3; };
  pythonSet = baseSet.overrideScope (lib.composeManyExtensions [
    pyproject-build-systems.overlays.default
    overlay
    package-overrides
    evap-override
  ]);

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
    our-packages.clean-setup
    evap-managepy-completion
  ] ++ extraPackages;

  passthru = { inherit venv; };

  env = {
    PUPPETEER_SKIP_DOWNLOAD = 1;
    UV_NO_SYNC = "1";
    UV_PYTHON = "${venv}/bin/python";
    UV_PYTHON_DOWNLOADS = "never";
  };

  shellHook = ''
    unset PYTHONPATH
    export REPO_ROOT=$(git rev-parse --show-toplevel)
  '';
}
