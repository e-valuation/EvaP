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
            python3 = pkgs.python310;
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
              superuser = "postgres";
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
      };
    };
}
