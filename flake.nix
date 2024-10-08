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
      perSystem = { self', inputs', pkgs, lib, system, ... }: {
        devShells = rec {
          evap = pkgs.callPackage ./nix/shell.nix {
            python3 = pkgs.python310;
            poetry2nix = inputs.poetry2nix.lib.mkPoetry2Nix { inherit pkgs; };
            pyproject = ./pyproject.toml;
            poetrylock = ./poetry.lock;
          };
          evap-dev = evap.override { poetry-groups = [ "dev" ]; };
          default = evap-dev;
        };

        # Start with `nix run .#services`
        process-compose =
          let
            make = only-databases: import ./nix/services.nix {
              inherit pkgs only-databases;
              inherit (inputs) services-flake;
              inherit (self'.devShells.evap.passthru) poetry-env;
            };
          in
          {
            services = make true;
            services-full = make false;
          };

        packages.wait-for-pc =
          let
            pc = lib.getExe self'.packages.services;
          in
          pkgs.writeShellApplication {
            name = "wait-for-pc";
            runtimeInputs = [ pkgs.jq ];
            text = ''
              while [ "$(${pc} process list -o json 2>/dev/null | jq '.[] |= .is_ready == "Ready" or .status == "Completed" or .status == "Disabled" | all')" != "true" ]; do
                  sleep 1
              done
            '';
          };
      };
    };
}
