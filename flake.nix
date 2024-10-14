{
  description = "EvaP";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    poetry2nix = {
      url = "github:nix-community/poetry2nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    process-compose-flake.url = "github:Platonic-Systems/process-compose-flake";
    services-flake.url = "github:juspay/services-flake";
  };

  outputs = { self, nixpkgs, ... }@inputs:
    let
      lib = nixpkgs.lib;
      systems = [ "x86_64-linux" "aarch64-linux" "aarch64-darwin" "x86_64-darwin" ];
      forAllSystems = lib.genAttrs systems;
      pkgsFor = lib.genAttrs systems (system: import nixpkgs { inherit system; });
    in
    {
      devShells = forAllSystems (system:
        let
          pkgs = pkgsFor.${system};
        in
        rec {
          evap = pkgs.callPackage ./nix/shell.nix {
            python3 = pkgs.python310;
            poetry2nix = inputs.poetry2nix.lib.mkPoetry2Nix { inherit pkgs; };
            pyproject = ./pyproject.toml;
            poetrylock = ./poetry.lock;
          };
          evap-dev = evap.override { poetry-groups = [ "dev" ]; };
          default = evap-dev;
        });

      packages = forAllSystems (system:
        let
          pkgs = pkgsFor.${system};
          make-process-compose = only-databases: (import inputs.process-compose-flake.lib { inherit pkgs; }).makeProcessCompose {
            modules = [
              inputs.services-flake.processComposeModules.default
              (import
                ./nix/services.nix
                {
                  inherit pkgs only-databases;
                  inherit (inputs) services-flake;
                  inherit (self.devShells.${system}.evap.passthru) poetry-env;
                })
            ];
          };
        in
        {
          services = make-process-compose true;
          services-full = make-process-compose false;

          wait-for-pc =
            let
              pc = lib.getExe self.packages.${system}.services;
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
        });
    };
}
