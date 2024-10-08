{ pkgs, lib ? pkgs.lib, services-flake, only-databases, ... }: {
  imports = [
    services-flake.processComposeModules.default
  ];

  httpServer = {
    enable = true;
    uds = "process-compose.socket";
  };

  services = {
    redis."r1" = {
      enable = true;
      port = 0; # disable listening via TCP
      extraConfig = ''
        locale-collate "C"
        unixsocket ../redis.socket
        unixsocketperm 777
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

  # See https://github.com/juspay/services-flake/issues/352
  settings.processes."r1".readiness_probe.exec.command = lib.mkForce "true";

  settings.processes."npm-ci" = {
    command = pkgs.writeShellApplication {
      name = "npm-ci";
      runtimeInputs = [ pkgs.nodejs ];
      text = ''
        CUR_HASH=$(nix-hash --flat <(cat ./package.json ./package-lock.json))
        echo "Hash is $CUR_HASH"
        if [[ -f node_modules/evap-hash && "$CUR_HASH" == "$(cat node_modules/evap-hash)" ]]; then
            echo "Equal hash found, exiting"
            exit 0
        fi
        npm ci
        echo "$CUR_HASH" > node_modules/evap-hash
      '';
    };
    disabled = only-databases;
  };
}
