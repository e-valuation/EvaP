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

  outputs = { self, nixpkgs, flake-parts, ... }@inputs:
    flake-parts.lib.mkFlake { inherit inputs; } {
      imports = [
        inputs.process-compose-flake.flakeModule
      ];
      systems = [
        "x86_64-linux"
      ];
      perSystem = { config, system, ... }:
        let
          # see https://github.com/nix-community/poetry2nix/tree/master#api for more functions and examples.
          pkgs = nixpkgs.legacyPackages.${system};
          inherit (pkgs) lib;
          poetry2nix = inputs.poetry2nix.lib.mkPoetry2Nix { inherit pkgs; };
        in
        {
          packages = {
            evap = poetry2nix.mkPoetryApplication {
              projectDir = self;
              preferWheels = true;
              overrides = poetry2nix.overrides.withDefaults (final: prev: {
                # https://github.com/nix-community/poetry2nix/issues/1499
                django-stubs-ext = prev.django-stubs-ext.override { preferWheel = false; };
              });
            };
          };

          # Start with `nix run .#services`
          process-compose."services" = {
            imports = [
              inputs.services-flake.processComposeModules.default
            ];

            services = {
              redis."r1".enable = true;
              postgres."pg1" = {
                enable = true;
                # initialDatabases = [
                #   { name = "evap"; }
                # ];
                initialScript.before = ''
                    CREATE USER evap;
                    ALTER USER evap WITH PASSWORD 'evap';
                    CREATE DATABASE evap OWNER evap;
                '';
              };
            };
          };

          devShells = {
            default = pkgs.mkShell {
              inputsFrom = [ self.packages.${system}.evap ];
              packages = with pkgs; [
                poetry
              ];
            };
          };
        };
    };
}
