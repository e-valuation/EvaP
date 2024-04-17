{
  description = "EvaP";

  inputs = {
    flake-utils.url = "github:numtide/flake-utils";
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    poetry2nix = {
      url = "github:nix-community/poetry2nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = { self, nixpkgs, flake-utils, ... }@inputs:
    flake-utils.lib.eachDefaultSystem (system:
      let
        # see https://github.com/nix-community/poetry2nix/tree/master#api for more functions and examples.
        pkgs = nixpkgs.legacyPackages.${system};
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
          default = self.packages.${system}.evap;
        };

        devShells.default = pkgs.mkShell {
          inputsFrom = [ self.packages.${system}.evap ];
          packages = [ pkgs.poetry ];
        };
      });
}
