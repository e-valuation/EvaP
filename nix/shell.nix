{ pkgs, python3, poetry2nix, projectDir, poetry-groups ? [ ], extraPackages ? [ ], extraPythonPackages ? (ps: [ ]), ... }:

let
  clean-setup = pkgs.writeShellScriptBin "clean-setup" ''
    read -p "Delete node_modules/ and data/? [y/N] "
    [[ "$REPLY" =~ ^[Yy]$ ]] || exit 1
    set -ex
    rm -rf node_modules/ data/
  '';

  initialize-setup = pkgs.writeShellScriptBin "initialize-setup" ''
    set -ex

    npm ci
    cp deployment/localsettings.template.py evap/localsettings.py
    sed -i -e "s/\$SECRET_KEY/$(head /dev/urandom | tr -dc A-Za-z0-9 | head -c 32)/" evap/localsettings.py
    git submodule update --init
    ./manage.py migrate --noinput
    ./manage.py collectstatic --noinput
    ./manage.py compilemessages --locale de
    ./manage.py loaddata test_data.json
    ./manage.py refresh_results_cache
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
    initialize-setup
  ] ++ extraPackages ++ (extraPythonPackages poetry-env.python.pkgs);

  env.PUPPETEER_SKIP_DOWNLOAD = 1;
}
