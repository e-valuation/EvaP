{ pkgs, lib ? pkgs.lib, python3, poetry2nix, pyproject, poetrylock, extras ? [ ], poetry-groups ? [ ], extraPackages ? [ ], extraPythonPackages ? (ps: [ ]), ... }:

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

  poetry-env = poetry2nix.mkPoetryEnv {
    python = python3;
    # We pass these instead of `projectDir` to avoid adding the dependency on other files.
    inherit pyproject poetrylock extras;
    preferWheels = true;
    overrides = poetry2nix.overrides.withDefaults (final: prev: {
      # https://github.com/nix-community/poetry2nix/issues/1499
      django-stubs-ext = prev.django-stubs-ext.override { preferWheel = false; };

      psycopg = prev.psycopg.overridePythonAttrs (old: {
        buildInputs = old.buildInputs or [ ]
          ++ lib.optionals pkgs.stdenv.isDarwin [ pkgs.openssl ];
        propagatedBuildInputs = old.propagatedBuildInputs or [ ] ++ [ pkgs.postgresql ];
      });

      psycopg-c = prev.psycopg-c.overridePythonAttrs (old: {
        nativeBuildInputs = old.nativeBuildInputs or [ ] ++ [ pkgs.postgresql ];
        propagatedBuildInputs = old.propagatedBuildInputs or [ ] ++ [ final.setuptools ];
      });
    });
    groups = poetry-groups;
    checkGroups = [ ]; # would otherwise always install dev-dependencies
  };
in
pkgs.mkShell {
  packages = with pkgs; [
    nodejs
    gettext

    poetry-env
    clean-setup
    evap-managepy-completion
  ] ++ extraPackages ++ (extraPythonPackages poetry-env.python.pkgs);

  passthru = { inherit poetry-env; };

  env.PUPPETEER_SKIP_DOWNLOAD = 1;
}
