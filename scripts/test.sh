#!/bin/sh
# Tests im Image, Repo per Volume eingehängt. Nie gegen das echte IN: .env wird nicht geladen.
set -e
cd "$(dirname "$0")/.."
docker build -q -t dss-in-mcp-test . >/dev/null
# --user root: das Image läuft produktiv als non-root (siehe Dockerfile), aber hier wird per pip
# in den Container installiert und das Repo per Volume eingehängt - für den Testlauf unschädlich.
docker run --rm --user root -v "$PWD":/app -w /app dss-in-mcp-test \
    sh -c "pip install -q --root-user-action=ignore -r requirements-dev.txt && python -m pytest -q -p no:cacheprovider $*"
