{
  description = "EvaP";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

    pyproject-nix = {
      url = "github:nix-community/pyproject.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    uv2nix = {
      url = "github:adisbladis/uv2nix";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    pyproject-build-systems = {
      url = "github:pyproject-nix/build-system-pkgs";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.uv2nix.follows = "uv2nix";
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
          dependency-groups = if pkgs.stdenv.isDarwin then [ "psycopg-c" ] else [ "psycopg-binary" ];
        in
        rec {
          evap = pkgs.callPackage ./nix/shell.nix {
            inherit (self.packages.${system}) python3;
            inherit (inputs) pyproject-nix uv2nix pyproject-build-systems;
            inherit dependency-groups;
            workspaceRoot = ./.;
          };
          evap-dev = evap.override (prev: { dependency-groups = (prev.dependency-groups or [ ]) ++ [ "dev" ]; });
          default = evap-dev;

          impure = pkgs.mkShell {
            packages = with pkgs; [
              (self.packages.${system}.python3)
              uv
              postgresql
            ];
            shellHook = ''
              unset PYTHONPATH
            '';
          };
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
                  inherit (self.devShells.${system}.evap.passthru) venv;
                })
            ];
          };
        in
        rec {
          python3 = pkgs.python310;

          services = make-process-compose true;
          services-full = make-process-compose false;

          wait-for-pc = pkgs.writeShellApplication {
            name = "wait-for-pc";
            runtimeInputs = [ pkgs.jq ];
            text = ''
              while [ "$(${lib.getExe services} process list -o json 2>/dev/null | jq '.[] |= .is_ready == "Ready" or .status == "Completed" or .status == "Disabled" | all')" != "true" ]; do
                  sleep 1
              done
            '';
          };

          build-dist = pkgs.writeShellApplication {
            name = "build-dist";
            runtimeInputs = with pkgs; [ nodejs gettext git ];
            text =
              let
                python-dev = self.devShells.${system}.evap-dev.passthru.venv;
                python-build = self.packages.${system}.python3.withPackages (ps: [ ps.build ]);
              in
              ''
                set -x
                npm ci
                ${python-dev}/bin/python ./manage.py compilemessages
                ${python-dev}/bin/python ./manage.py scss --production
                ${python-dev}/bin/python ./manage.py ts compile --fresh
                ${python-build}/bin/python -m build
              '';
          };
        });
    };
}
