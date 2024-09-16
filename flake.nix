{
  description = "EvaP";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    poetry2nix = {
      url = "github:nix-community/poetry2nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    flake-parts.url = "github:hercules-ci/flake-parts";
    process-compose-flake.url = "github:Platonic-Systems/process-compose-flake";
    services-flake.url = "github:juspay/services-flake";
  };

  outputs = { self, flake-parts, ... }@inputs:
    flake-parts.lib.mkFlake { inherit inputs; } {
      imports = [
        inputs.process-compose-flake.flakeModule
      ];
      systems = [ "x86_64-linux" "aarch64-linux" "aarch64-darwin" "x86_64-darwin" ];
      perSystem = { self', inputs', pkgs, system, ... }: {
        devShells = rec {
          evap = pkgs.callPackage ./nix/shell.nix {
            poetry2nix = inputs.poetry2nix.lib.mkPoetry2Nix { inherit pkgs; };
            projectDir = self;
          };
          evap-dev = evap.override { poetry-groups = [ "dev" ]; };
          default = evap-dev;
        };

        # Start with `nix run .#services`
        process-compose."services" = {
          imports = [
            inputs.services-flake.processComposeModules.default
          ];

          httpServer = {
            enable = true;
            uds = "process-compose.socket";
          };

          services = {
            redis."r1" = {
              enable = true;
              extraConfig = ''
                locale-collate "C"
              '';
            };
            postgres."pg1" = {
              enable = true;
              initialScript.before = ''
                CREATE USER evap;
                ALTER USER evap WITH PASSWORD 'evap';
                ALTER USER evap CREATEDB;
                CREATE DATABASE evap OWNER evap;
              '';
            };
          };
        };

        packages.install-services-unit =
          let
            # We need to make `bash` available in the path for the readiness-checks.
            wrapped-services = pkgs.runCommand "wrapped-services" { nativeBuildInputs = [ pkgs.makeWrapper ]; } ''
              makeWrapper ${self'.packages.services}/bin/services $out/bin/services --prefix PATH ':' ${pkgs.lib.makeBinPath [pkgs.bash]}
            '';
          in
          pkgs.writeShellScriptBin "install-services-unit" ''
            set -ex
            WORKING_DIR="''${XDG_DATA_HOME:-$HOME/.local/share}/evap-services/"
            mkdir -p $WORKING_DIR
            cat > ''${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/evap-services.service <<EOF
                [Unit]
                Description=EvaP Database Services

                [Service]
                Type=simple
                WorkingDirectory=''$WORKING_DIR
                ExecStart=${wrapped-services}/bin/services up --tui=false
                ExecStop=${wrapped-services}/bin/services down

                [Install]
                WantedBy=multi-user.target
            EOF
          '';
      };
    };
}
