{ pkgs, evap, projectDir, ... }:

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
in
pkgs.mkShell {
  inputsFrom = [ evap ];
  packages = with pkgs; [
    poetry
    nodejs

    clean-setup
    initialize-setup
  ];

  env.PUPPETEER_SKIP_DOWNLOAD = 1;

  shellHook = ''
    # TODO: doesn't work with other shells from direnv
    source "${projectDir}/deployment/manage_autocompletion.sh"
  '';
}
