"""Unit tests for generar_descripcion.py — FakeGroq client, no network calls."""

import groq as groq_module
import pytest

from generar_descripcion import (
    MODELO,
    ErrorConfiguracion,
    generar_descripcion,
)


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
    def __init__(self, respuesta="Descripción generada de prueba"):
        self.calls = []
        self._respuesta = respuesta

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return FakeResponse(self._respuesta)


class FakeChat:
    def __init__(self):
        self.completions = FakeCompletions()


class FakeGroq:
    def __init__(self):
        self.chat = FakeChat()


def test_missing_key_raises_error_configuracion_before_any_call(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("Groq client must not be constructed without a key")

    monkeypatch.setattr(groq_module, "Groq", fail_if_called)

    with pytest.raises(ErrorConfiguracion):
        generar_descripcion("transcripción de prueba")


def test_blank_key_raises_error_configuracion(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "   ")

    def fail_if_called(*args, **kwargs):
        raise AssertionError("Groq client must not be constructed with a blank key")

    monkeypatch.setattr(groq_module, "Groq", fail_if_called)

    with pytest.raises(ErrorConfiguracion):
        generar_descripcion("transcripción de prueba")


def test_generar_descripcion_with_injected_client(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    cliente = FakeGroq()
    transcripcion = "El analista describe un error al entrar al módulo de riesgos."

    resultado = generar_descripcion(transcripcion, cliente=cliente)

    assert resultado == "Descripción generada de prueba"
    assert len(cliente.chat.completions.calls) == 1

    kwargs = cliente.chat.completions.calls[0]
    assert kwargs["model"] == MODELO
    assert kwargs["temperature"] == 0.2
    assert kwargs["max_tokens"] == 1024

    mensajes = kwargs["messages"]
    system_msg = mensajes[0]["content"]
    user_msg = mensajes[1]["content"]

    # Rule 4: no implementation-detail speculation.
    assert "PROHIBIDO mencionar o suponer detalles de implementación" in system_msg
    # Rule 5: no technical-cause diagnosis.
    assert "PROHIBIDO diagnosticar la causa técnica" in system_msg
    # Transcript is sent verbatim, bounded by --- delimiters.
    assert transcripcion in user_msg
    assert "---" in user_msg
