{ pkgs, python3, poetry2nix, projectDir, poetry-groups ? [ ], extraPackages ? [ ], extraPythonPackages ? (ps: [ ]), ... }:

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
    inherit projectDir;
    preferWheels = true;
    overrides = poetry2nix.overrides.withDefaults (final: prev:
      let
        remove-conflicting-file = package-name: filename: prev.${package-name}.overridePythonAttrs {
          postInstall = "rm $out/${final.python.sitePackages}/${filename}";
        };
      in
      {
        # https://github.com/nix-community/poetry2nix/issues/1499
        django-stubs-ext = prev.django-stubs-ext.override { preferWheel = false; };

        # https://github.com/nix-community/poetry2nix/issues/46
        josepy = remove-conflicting-file "josepy" "CHANGELOG.rst";
        pylint-django = remove-conflicting-file "pylint-django" "CHANGELOG.rst";
      });
    groups = poetry-groups;
    checkGroups = [ ]; # would otherwise always install dev-dependencies
    editablePackageSources.evap = ./evap;
  };
in
pkgs.mkShell {
  packages = with pkgs; [
    (poetry.override { inherit python3; })
    nodejs
    gettext

    poetry-env
    clean-setup
    evap-managepy-completion
  ] ++ extraPackages ++ (extraPythonPackages poetry-env.python.pkgs);

  passthru = { inherit poetry-env; };

  env.PUPPETEER_SKIP_DOWNLOAD = 1;
}
