{
  description = "Python tool to run a given REPL session and evaluate the outcomes";

  inputs.pyproject-nix.url = "github:pyproject-nix/pyproject.nix";
  inputs.pyproject-nix.inputs.nixpkgs.follows = "nixpkgs";
  inputs.flake-utils.url = "github:numtide/flake-utils";

  outputs =
  { nixpkgs, pyproject-nix, flake-utils, ... }: flake-utils.lib.eachDefaultSystem (system:
  let

    project = pyproject-nix.lib.project.loadPyproject {
      projectRoot = ./.;
    };

    pythonAttr = "python3";

    overlay = final: prev: {
      pythonPackagesExtensions = prev.pythonPackagesExtensions ++ [
        (python-final: python-prev: { 
          argh = python-prev.argh.overridePythonAttrs(old: rec {
            version = "0.30.5";
            src = python-final.fetchPypi {
              pname = "argh";
              inherit version;
              sha256 = "sha256-s339YXoJ0ZpKe8rtDgYLKIvHrI39wPrPiGpJol/zNyg=";
            };
            doCheck = false;
          });
          msgspec = python-prev.msgspec.overridePythonAttrs(old: rec {
            version = "0.20.0";
            src = final.fetchFromGitHub {
              owner = "jcrist";
              repo = "msgspec";
              tag = "${version}";
              sha256 = "sha256-DWDmnSuo12oXl9NVfNhIOtWrQeJ9DMmHxOyHY33Datk=";
            };
            build-system = [ python-final.setuptools-scm ];
          });
        })
      ];
    };
  in
  let
    pkgs = import nixpkgs { inherit system; overlays = [ overlay ]; };
    python = pkgs.${pythonAttr};
    pythonEnv = python.withPackages (project.renderers.withPackages { inherit python; });
  in
  {
    devShells.default = pkgs.mkShell { packages = [ pythonEnv ]; };
    packages.default = python.pkgs.buildPythonPackage (project.renderers.buildPythonPackage { inherit python; });
  });
}
