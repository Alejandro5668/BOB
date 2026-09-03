#!/usr/bin/env bash
# One-command production deploy to Render, carrying the REAL documentation
# corpus — never the memory/ fixture. See CLAUDE.md "Production deploy".
#
# Why this can't be a normal git-push auto-deploy: the real docs must never
# be committed to this repo (see "Context retrieval decision"), so a
# GitHub-connected Render service would only ever see the 3-file fixture.
# This script bakes the real docs into the image locally instead, the same
# way the initial deploy was done, then pushes + redeploys.
#
# Usage (from repo root):
#   KAWAK_DOCS_DIR="/path/to/real/docs" ./scripts/deploy-render.sh
#
# Requires: docker (already logged in — `docker login`), render CLI
# (already logged in — `render login`).
set -e

cd "$(dirname "$0")/.."

IMAGEN="alejandro767967/bob:latest"
SERVICIO_RENDER="srv-dacei70n74is73ct8jn0"

if [ -z "$KAWAK_DOCS_DIR" ]; then
  echo "Falta KAWAK_DOCS_DIR — pasá la ruta a la carpeta real de documentación:"
  echo '  KAWAK_DOCS_DIR="/c/Users/alexp/OneDrive/Documentos/1" ./scripts/deploy-render.sh'
  exit 1
fi

if [ ! -d "$KAWAK_DOCS_DIR" ]; then
  echo "No existe la carpeta: $KAWAK_DOCS_DIR"
  exit 1
fi

git -C . diff --quiet -- memory/ || {
  echo "memory/ tiene cambios sin commitear — resolvé eso primero (este script lo sobreescribe temporalmente)."
  exit 1
}

# Siempre restaura memory/ al fixture versionado, incluso si algo falla a mitad de camino.
trap 'echo "Restaurando memory/ al fixture del repo..."; git checkout -- memory/; git clean -fd memory/' EXIT

echo "Reemplazando memory/ (fixture) por la documentación real (temporal, solo para este build)..."
rm -rf memory/*
cp -r "$KAWAK_DOCS_DIR/." memory/
echo "$(find memory -name '*.md' | wc -l) documentos reales listos para el build."

echo "Construyendo la imagen..."
docker build -t "$IMAGEN" .

echo "Subiendo la imagen a Docker Hub (repo privado)..."
docker push "$IMAGEN"

echo "Restaurando memory/ al fixture antes de redeployar (no dejar los docs reales en el working tree)..."
git checkout -- memory/
git clean -fd memory/
trap - EXIT

echo "Redeployando en Render..."
render deploys create "$SERVICIO_RENDER" --wait

echo
echo "Listo — https://bob-vjwv.onrender.com"
