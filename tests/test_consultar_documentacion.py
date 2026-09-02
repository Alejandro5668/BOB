"""Unit tests for consultar_documentacion.py — FakeAnthropic client, no
network calls. Keeps every assertion as a bare `str` comparison in this
PR — the `.texto`/`.tipo` return-contract break is a separate, later
change (PR2)."""

import pytest

from cliente_anthropic import ErrorConfiguracion
from consultar_documentacion import MODELO, SIN_INFORMACION, responder_consulta
from prompts import ENTRADA_RESPONDEDOR_CONSULTA, RESPONDEDOR_CONSULTA_DOCUMENTACION


class FakeBloqueTexto:
    def __init__(self, text):
        self.type, self.text = "text", text


class FakeMensaje:
    def __init__(self, text):
        self.content = [FakeBloqueTexto(text)]


class FakeMessages:
    def __init__(self, respuesta="Respuesta de prueba"):
        self.calls = []
        self._respuesta = respuesta

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return FakeMensaje(self._respuesta)


class FakeAnthropic:
    def __init__(self, respuesta="Respuesta de prueba"):
        self.messages = FakeMessages(respuesta)


@pytest.fixture(autouse=True)
def _sin_memoria_real(monkeypatch):
    """Same isolation rationale as test_generar_descripcion.py: client
    sharing threads an injected client into the default
    `proveedor_contexto`, so tests that don't explicitly inject their own
    `proveedor_contexto` must not accidentally scan the project's real
    `memory/` folder."""
    monkeypatch.setenv("MEMORY_DIR", "ruta/que/no/existe")


def test_no_context_returns_fixed_notice_without_any_network_call(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("Anthropic client must not be constructed when there's no context")

    import anthropic

    monkeypatch.setattr(anthropic, "Anthropic", fail_if_called)

    resultado = responder_consulta("¿Cómo funciona el módulo de riesgos?", proveedor_contexto=lambda p: "")

    assert resultado == SIN_INFORMACION


def test_missing_key_raises_error_configuracion_when_context_exists(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with pytest.raises(ErrorConfiguracion):
        responder_consulta(
            "¿Cómo funciona el módulo de riesgos?",
            proveedor_contexto=lambda p: "Documentación real del módulo.",
        )


def test_responder_consulta_with_injected_client_and_context(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    cliente = FakeAnthropic(respuesta="El módulo permite registrar y valorar riesgos.")
    pregunta = "¿Cómo funciona el módulo de gestión de riesgos?"
    contexto = "Documentación: el módulo permite registrar riesgos y calcular su exposición."

    resultado = responder_consulta(
        pregunta,
        cliente=cliente,
        proveedor_contexto=lambda p: contexto,
    )

    assert resultado == "El módulo permite registrar y valorar riesgos."
    kwargs = cliente.messages.calls[0]
    assert kwargs["model"] == MODELO
    assert kwargs["system"] == RESPONDEDOR_CONSULTA_DOCUMENTACION

    user_msg = kwargs["messages"][0]["content"]
    assert user_msg == ENTRADA_RESPONDEDOR_CONSULTA.format(contexto=contexto, pregunta=pregunta)


def test_context_provider_receives_the_question(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    cliente = FakeAnthropic()
    pregunta = "¿Cómo funciona la gestión documental?"
    recibido = []

    def proveedor_espia(texto):
        recibido.append(texto)
        return "contexto de prueba"

    responder_consulta(pregunta, cliente=cliente, proveedor_contexto=proveedor_espia)

    assert recibido == [pregunta]


def test_anthropic_failure_raises_error_generacion_with_friendly_message(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    class MessagesRotas:
        def create(self, **kwargs):
            raise RuntimeError("401 unauthorized")

    class ClienteRoto:
        def __init__(self):
            self.messages = MessagesRotas()

    from generar_descripcion import ErrorGeneracion

    with pytest.raises(ErrorGeneracion):
        responder_consulta(
            "¿Cómo funciona el módulo?",
            cliente=ClienteRoto(),
            proveedor_contexto=lambda p: "contexto",
        )


def test_injected_client_is_shared_with_the_default_context_provider(monkeypatch):
    """Design decision 7: when a client IS injected, it must be threaded
    into the default `proveedor_contexto` (`contexto_memoria.buscar_contexto`)
    rather than each stage building its own."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    cliente = FakeAnthropic()
    recibidos = {}

    def buscar_contexto_espia(pregunta, *, cliente=None, directorio=None):
        recibidos["cliente"] = cliente
        return ""

    monkeypatch.setattr("contexto_memoria.buscar_contexto", buscar_contexto_espia)

    responder_consulta("¿algo?", cliente=cliente)

    assert recibidos["cliente"] is cliente
