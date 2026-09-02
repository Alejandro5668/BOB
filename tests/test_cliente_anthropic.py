"""Unit tests for contexto_enriquecido.py — content-addressed cache, Haiku
summarization with mandatory raw fallback, and order-preserving bounded
concurrency.

`FakeAnthropic` mirrors the real `anthropic` SDK's `.messages.create(**kwargs)`
call surface and `.content` (list of blocks with `.type`/`.text`) response
shape — NOT Groq's `chat.completions.create` / `choices[0].message.content`
shape used by `FakeGroq` in `test_contexto_memoria.py`. No real network call
is ever made in these tests.
"""

import threading
import time

import pytest

import contexto_enriquecido as ce


class FakeBloqueTexto:
    def __init__(self, text):
        self.type, self.text = "text", text


class FakeMensaje:
    def __init__(self, text):
        self.content = [FakeBloqueTexto(text)]


class FakeMessages:
    def __init__(self, resumen="RESUMEN", error=None):
        self.calls, self._resumen, self._error = [], resumen, error

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return FakeMensaje(self._resumen)


class FakeAnthropic:
    def __init__(self, resumen="RESUMEN", error=None):
        self.messages = FakeMessages(resumen, error)


class FakeMessagesPorIndice:
    """Returns a canned result per call, keyed by which document (`ruta`)
    is being enriched — for testing per-document error/latency behavior."""

    def __init__(self, por_ruta):
        self.calls = []
        self._por_ruta = por_ruta

    def create(self, **kwargs):
        self.calls.append(kwargs)
        contenido_mensaje = kwargs["messages"][0]["content"]
        # ruta is embedded in ENTRADA_ENRIQUECEDOR_DOCUMENTACION's first line
        ruta = contenido_mensaje.split("\n", 1)[0].removeprefix("Documento: ")
        accion = self._por_ruta[ruta]
        if callable(accion):
            return accion()
        if isinstance(accion, Exception):
            raise accion
        return FakeMensaje(accion)


class FakeAnthropicPorIndice:
    def __init__(self, por_ruta):
        self.messages = FakeMessagesPorIndice(por_ruta)


@pytest.fixture(autouse=True)
def _sin_clave_anthropic(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


# --- Content-addressed cache -------------------------------------------------


def test_cache_hit_performs_zero_api_calls(tmp_path):
    cliente = FakeAnthropic(resumen="RESUMEN cacheado")
    documentos = [("doc.md", "contenido original")]

    primero = ce.enriquecer_documentos(documentos, cliente=cliente, directorio_cache=str(tmp_path))
    assert cliente.messages.calls  # first call is a miss, must hit the API
    assert primero == ["RESUMEN cacheado"]

    cliente_segunda_vuelta = FakeAnthropic(resumen="NO DEBERÍA USARSE")
    segundo = ce.enriquecer_documentos(
        documentos, cliente=cliente_segunda_vuelta, directorio_cache=str(tmp_path)
    )

    assert cliente_segunda_vuelta.messages.calls == []
    assert segundo == ["RESUMEN cacheado"]


def test_changed_content_triggers_a_fresh_call(tmp_path):
    cliente = FakeAnthropic(resumen="RESUMEN v1")
    ce.enriquecer_documentos([("doc.md", "contenido v1")], cliente=cliente, directorio_cache=str(tmp_path))

    cliente_v2 = FakeAnthropic(resumen="RESUMEN v2")
    resultado = ce.enriquecer_documentos(
        [("doc.md", "contenido v2")], cliente=cliente_v2, directorio_cache=str(tmp_path)
    )

    assert cliente_v2.messages.calls  # new hash -> cache miss -> fresh call
    assert resultado == ["RESUMEN v2"]


# --- Mandatory raw fallback --------------------------------------------------


def test_missing_api_key_returns_raw_content_and_never_raises(tmp_path):
    documentos = [("doc.md", "contenido crudo original")]

    resultado = ce.enriquecer_documentos(documentos, directorio_cache=str(tmp_path))

    assert resultado == ["contenido crudo original"]


def test_api_error_for_one_document_degrades_only_that_block(tmp_path):
    documentos = [
        ("falla.md", "contenido crudo que falla"),
        ("ok.md", "contenido crudo que funciona"),
    ]
    cliente = FakeAnthropicPorIndice(
        {
            "falla.md": RuntimeError("fallo simulado de la API"),
            "ok.md": "RESUMEN ok",
        }
    )

    resultado = ce.enriquecer_documentos(documentos, cliente=cliente, directorio_cache=str(tmp_path))

    assert resultado == ["contenido crudo que falla", "RESUMEN ok"]


def test_empty_haiku_response_degrades_to_raw(tmp_path):
    cliente = FakeAnthropic(resumen="   ")  # blank after strip()
    documentos = [("doc.md", "contenido crudo")]

    resultado = ce.enriquecer_documentos(documentos, cliente=cliente, directorio_cache=str(tmp_path))

    assert resultado == ["contenido crudo"]


def test_unwritable_cache_directory_still_returns_the_summary(tmp_path, monkeypatch):
    cliente = FakeAnthropic(resumen="RESUMEN pese a caché rota")
    documentos = [("doc.md", "contenido crudo")]

    def _mkdir_falla(self, parents=True, exist_ok=True):
        raise OSError("directorio de caché no escribible (simulado)")

    monkeypatch.setattr("pathlib.Path.mkdir", _mkdir_falla)

    resultado = ce.enriquecer_documentos(documentos, cliente=cliente, directorio_cache=str(tmp_path))

    assert resultado == ["RESUMEN pese a caché rota"]


# --- Bounded concurrent enrichment preserving order --------------------------


def test_order_preserved_when_a_later_document_completes_first(tmp_path):
    orden_de_finalizacion = []

    def _lento():
        time.sleep(0.15)
        orden_de_finalizacion.append("doc0.md")
        return FakeMensaje("RESUMEN 0")

    def _rapido():
        orden_de_finalizacion.append("doc1.md")
        return FakeMensaje("RESUMEN 1")

    cliente = FakeAnthropicPorIndice({"doc0.md": _lento, "doc1.md": _rapido})
    documentos = [("doc0.md", "contenido 0"), ("doc1.md", "contenido 1")]

    resultado = ce.enriquecer_documentos(documentos, cliente=cliente, directorio_cache=str(tmp_path))

    # doc1.md's call finishes first in wall-clock time...
    assert orden_de_finalizacion == ["doc1.md", "doc0.md"]
    # ...but results stay in original selection order, not completion order.
    assert resultado == ["RESUMEN 0", "RESUMEN 1"]


# --- Total contract / misc ---------------------------------------------------


def test_enriquecer_documentos_returns_empty_list_for_empty_input():
    assert ce.enriquecer_documentos([]) == []


def test_hash_contenido_is_sha256_of_raw_bytes():
    import hashlib

    assert ce._hash_contenido("hola") == hashlib.sha256("hola".encode("utf-8")).hexdigest()


def test_resolver_directorio_cache_explicit_arg_wins(monkeypatch):
    monkeypatch.setenv("CACHE_DOCUMENTACION_DIR", "/env/cache")
    from pathlib import Path

    assert ce.resolver_directorio_cache("/explicit/cache") == Path("/explicit/cache")


def test_resolver_directorio_cache_defaults(monkeypatch):
    monkeypatch.delenv("CACHE_DOCUMENTACION_DIR", raising=False)
    from pathlib import Path

    assert ce.resolver_directorio_cache() == Path(ce.DIRECTORIO_CACHE_POR_DEFECTO)
