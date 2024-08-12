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
      perSystem = { self', inputs', pkgs, system, ... }:
        let
          fs = pkgs.lib.fileset;
          projectDir = fs.toSource {
            root = ./.;
            fileset = fs.difference ./. (fs.unions [
              (fs.maybeMissing ./result)
              (fs.maybeMissing ./custom-nix)
              ./flake.lock
            ]);
          };
        in
        {
          packages.evap = pkgs.callPackage ./nix/evap.nix {
            poetry2nix = inputs.poetry2nix.lib.mkPoetry2Nix { inherit pkgs; };
            inherit projectDir;
          };
          devShells.default = pkgs.callPackage ./nix/shell.nix {
            inherit projectDir;
            inherit (self'.packages) evap;
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
                initialScript.before = ''
                  CREATE USER evap;
                  ALTER USER evap WITH PASSWORD 'evap';
                  ALTER USER evap CREATEDB;
                  CREATE DATABASE evap OWNER evap;
                '';
              };
            };
          };
        };
    };
}
