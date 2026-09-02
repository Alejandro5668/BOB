"""Centralized logging setup: console (captured by `docker compose logs`)
plus a rotating file under `logs/app.log` so failures survive container
recreation. Every domain module logs the real exception here before
wrapping it in a friendly, user-facing message — never log secret values
(API keys, full audio bytes).
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_CONFIGURED = False


def configurar_logging() -> None:
    """Idempotent: safe to call from every module's import path."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    directorio_logs = Path("logs")
    directorio_logs.mkdir(exist_ok=True)

    formato = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    consola = logging.StreamHandler()
    consola.setFormatter(formato)

    archivo = RotatingFileHandler(
        directorio_logs / "app.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8"
    )
    archivo.setFormatter(formato)

    raiz = logging.getLogger()
    raiz.setLevel(logging.INFO)
    raiz.addHandler(consola)
    raiz.addHandler(archivo)

    _CONFIGURED = True
