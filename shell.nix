{ sources ? import ./nix/sources.nix }:
let
  pkgs = import sources.nixpkgs {
    config.allowUnfree = true;
   };
in
pkgs.mkShell {
  buildInputs = [
    (pkgs.python313.withPackages (ps: with ps; [
      numpy
      scipy
      scikit-learn
      requests
      beautifulsoup4
      google-genai
      psycopg2
      mechanicalsoup
      pillow
      onnxruntime
      numpy
      python-telegram-bot
      python-dotenv
      fuzzywuzzy
      openai
      dateparser
    ]))
    pkgs.niv
  ];
}

