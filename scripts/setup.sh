#!/usr/bin/env bash
# One-command bootstrap/refresh: gets the app running via Docker, always
# from a fresh image build — never silently serves a stale container.
# See CLAUDE.md "Project setup".
#
# Usage (from repo root, or anywhere — resolves its own path):
#   ./scripts/setup.sh
set -e

cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Creado .env a partir de .env.example — completá las claves antes de usar la app:"
  echo "  - ANTHROPIC_API_KEY (requerida: selección, generación, verificación, consulta)"
  echo "  - ELEVENLABS_API_KEY (requerida: transcripción de audio)"
  echo "  - MEMORY_DIR (opcional: sin esta, se usa el fixture memory/ del repo)"
  echo
fi

echo "Reconstruyendo la imagen (siempre desde cero, nunca sirve un build viejo)..."
docker compose build

echo "Levantando el contenedor..."
docker compose up -d

echo "Esperando el healthcheck..."
for _ in $(seq 1 30); do
  estado="$(docker compose ps --format '{{.Health}}' app 2>/dev/null || true)"
  if [ "$estado" = "healthy" ]; then
    puerto="$(grep -o 'BOB_HOST_PORT=.*' .env 2>/dev/null | cut -d= -f2)"
    puerto="${puerto:-8501}"
    echo
    echo "Listo — http://localhost:${puerto}"
    exit 0
  fi
  sleep 2
done

echo "El contenedor no llegó a 'healthy' a tiempo — revisá 'docker compose logs app'."
exit 1
