"""Unit tests for consultar_documentacion.py — FakeGroq client, no network calls."""

import groq as groq_module
import pytest

from consultar_documentacion import SIN_INFORMACION, MODELO, responder_consulta
from generar_descripcion import ErrorConfiguracion
from prompts import ENTRADA_RESPONDEDOR_CONSULTA, RESPONDEDOR_CONSULTA_DOCUMENTACION


class FakeMessage:
    def __init__(self, content):
        self.content = content


class FakeChoice:
    def __init__(self, content):
        self.message = FakeMessage(content)


class FakeResponse:
    def __init__(self, content):
        self.choices = [FakeChoice(content)]


class FakeCompletions:
    def __init__(self, respuesta="Respuesta de prueba"):
        self.calls = []
        self._respuesta = respuesta

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return FakeResponse(self._respuesta)


class FakeChat:
    def __init__(self, respuesta="Respuesta de prueba"):
        self.completions = FakeCompletions(respuesta)


class FakeGroq:
    def __init__(self, respuesta="Respuesta de prueba"):
        self.chat = FakeChat(respuesta)


def test_no_context_returns_fixed_notice_without_any_network_call(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("Groq client must not be constructed when there's no context")

    monkeypatch.setattr(groq_module, "Groq", fail_if_called)

    resultado = responder_consulta("¿Cómo funciona el módulo de riesgos?", proveedor_contexto=lambda p: "")

    assert resultado == SIN_INFORMACION


def test_missing_key_raises_error_configuracion_when_context_exists(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    with pytest.raises(ErrorConfiguracion):
        responder_consulta(
            "¿Cómo funciona el módulo de riesgos?",
            proveedor_contexto=lambda p: "Documentación real del módulo.",
        )


def test_responder_consulta_with_injected_client_and_context(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    cliente = FakeGroq(respuesta="El módulo permite registrar y valorar riesgos.")
    pregunta = "¿Cómo funciona el módulo de gestión de riesgos?"
    contexto = "Documentación: el módulo permite registrar riesgos y calcular su exposición."

    resultado = responder_consulta(
        pregunta,
        cliente=cliente,
        proveedor_contexto=lambda p: contexto,
    )

    assert resultado == "El módulo permite registrar y valorar riesgos."
    kwargs = cliente.chat.completions.calls[0]
    assert kwargs["model"] == MODELO

    mensajes = kwargs["messages"]
    assert mensajes[0]["content"] == RESPONDEDOR_CONSULTA_DOCUMENTACION
    assert mensajes[1]["content"] == ENTRADA_RESPONDEDOR_CONSULTA.format(
        contexto=contexto, pregunta=pregunta
    )


def test_context_provider_receives_the_question(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    cliente = FakeGroq()
    pregunta = "¿Cómo funciona la gestión documental?"
    recibido = []

    def proveedor_espia(texto):
        recibido.append(texto)
        return "contexto de prueba"

    responder_consulta(pregunta, cliente=cliente, proveedor_contexto=proveedor_espia)

    assert recibido == [pregunta]


def test_groq_failure_raises_error_generacion_with_friendly_message(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    class ClienteRoto:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    raise RuntimeError("401 unauthorized")

    from generar_descripcion import ErrorGeneracion

    with pytest.raises(ErrorGeneracion):
        responder_consulta(
            "¿Cómo funciona el módulo?",
            cliente=ClienteRoto(),
            proveedor_contexto=lambda p: "contexto",
        )
