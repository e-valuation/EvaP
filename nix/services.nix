{ pkgs, lib ? pkgs.lib, venv }: {
  databases = {
    cli.options = {
      no-server = false;
      unix-socket = "process-compose.socket";
    };

    services = {
      redis."r1" = {
        enable = true;
        port = 0; # disable listening via TCP
        unixSocket = "../redis.socket";
        unixSocketPerm = 777;
        extraConfig = ''
          locale-collate "C"
        '';
      };
      postgres."pg1" = {
        enable = true;
        superuser = "postgres";
        listen_addresses = ""; # disable listening via TCP
        socketDir = "data";
        createDatabase = false;
        initialScript.before = ''
          DROP USER IF EXISTS evap;
          DROP DATABASE IF EXISTS evap;
          CREATE USER evap PASSWORD 'evap' CREATEDB;
          CREATE DATABASE evap OWNER evap;
        '';
      };
    };
  };

  devenv-setup = {
    settings.processes = {
      npm-ci = {
        command = pkgs.writeShellApplication {
          name = "npm-ci";
          runtimeInputs = with pkgs; [ nodejs coreutils ];
          text = ''
            set -e
            CUR_HASH=$(nix-hash --flat ./package.json ./package-lock.json | paste -sd " ")
            echo "Hash is $CUR_HASH"
            if [[ -f node_modules/evap-hash && "$CUR_HASH" == "$(cat node_modules/evap-hash)" ]]; then
                echo "Equal node_modules/evap-hash found, exiting."
                echo "If you want to install a fresh environment, run clean-setup in a nix develop shell."
                exit 0
            fi
            npm ci
            echo "$CUR_HASH" > node_modules/evap-hash
          '';
        };
      };

      init-django = {
        command = pkgs.writeShellApplication {
          name = "init-django";
          runtimeInputs = with pkgs; [ venv git gnused gettext coreutils ];
          text = ''
            set -e
            if [[ -f evap/localsettings.py ]]; then
                echo "Found evap/localsettings.py, exiting."
                echo "If you want to install a fresh environment, run clean-setup in a nix develop shell."
                exit 0
            fi
            set -x
            cp evap/development/localsettings.template.py evap/localsettings.py
            sed -i -e "s/\$SECRET_KEY/$(head /dev/urandom | LC_ALL=C tr -dc A-Za-z0-9 | head -c 32)/" evap/localsettings.py
            git submodule update --init
            ./manage.py compilemessages --locale de
            ./manage.py reload_testdata --noinput
          '';
        };
        depends_on = {
          "pg1".condition = "process_healthy";
          "r1".condition = "process_healthy";
        };
      };
    };
  };
}
