{ poetry2nix, projectDir, ... }:

poetry2nix.mkPoetryApplication {
  inherit projectDir;
  preferWheels = true;
  overrides = poetry2nix.overrides.withDefaults (final: prev: {
    # https://github.com/nix-community/poetry2nix/issues/1499
    django-stubs-ext = prev.django-stubs-ext.override { preferWheel = false; };
  });
}
