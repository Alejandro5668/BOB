"""Minimal check for logging_config: creates logs/, is idempotent, never
raises. Not exhaustive — this is wiring, not business logic."""

import logging

import logging_config


def test_configurar_logging_creates_logs_dir_and_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    logging_config._CONFIGURED = False
    raiz = logging.getLogger()
    handlers_previos = list(raiz.handlers)

    logging_config.configurar_logging()
    assert (tmp_path / "logs").is_dir()
    handlers_despues_primera_llamada = list(raiz.handlers)
    assert len(handlers_despues_primera_llamada) == len(handlers_previos) + 2

    logging_config.configurar_logging()
    assert raiz.handlers == handlers_despues_primera_llamada

    for handler in handlers_despues_primera_llamada:
        if handler not in handlers_previos:
            raiz.removeHandler(handler)
    logging_config._CONFIGURED = False
