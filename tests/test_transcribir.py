"""Unit tests for transcribir.py — FakeElevenLabs client, no network calls."""

import pytest

import transcribir
from transcribir import (
    MODELO,
    ErrorConfiguracionAudio,
    ErrorTranscripcion,
    transcribir_bytes,
)


class FakeSpeechToTextResponse:
    def __init__(self, text):
        self.text = text


class FakeSpeechToText:
    def __init__(self, respuesta="transcripción de prueba", error=None):
        self.calls = []
        self._respuesta = respuesta
        self._error = error

    def convert(self, **kwargs):
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return FakeSpeechToTextResponse(self._respuesta)


class FakeElevenLabs:
    def __init__(self, respuesta="transcripción de prueba", error=None):
        self.speech_to_text = FakeSpeechToText(respuesta, error)


# --- Fail-fast + request shape ---------------------------------------------


def test_missing_key_raises_error_configuracion_before_any_call(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("ElevenLabs client must not be constructed without a key")

    import elevenlabs as elevenlabs_module

    monkeypatch.setattr(elevenlabs_module, "ElevenLabs", fail_if_called)

    with pytest.raises(ErrorConfiguracionAudio):
        transcribir_bytes(b"audio-bytes-fake")


def test_blank_key_raises_error_configuracion(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "   ")

    def fail_if_called(*args, **kwargs):
        raise AssertionError("ElevenLabs client must not be constructed with a blank key")

    import elevenlabs as elevenlabs_module

    monkeypatch.setattr(elevenlabs_module, "ElevenLabs", fail_if_called)

    with pytest.raises(ErrorConfiguracionAudio):
        transcribir_bytes(b"audio-bytes-fake")


def test_transcribir_bytes_with_injected_client():
    cliente = FakeElevenLabs(respuesta="el cliente reporta un error en riesgos")

    texto = transcribir_bytes(b"audio-bytes-fake", cliente=cliente)

    assert texto == "el cliente reporta un error en riesgos"
    assert len(cliente.speech_to_text.calls) == 1

    kwargs = cliente.speech_to_text.calls[0]
    assert kwargs["model_id"] == MODELO
    assert kwargs["language_code"] == "spa"
    assert kwargs["file"] == b"audio-bytes-fake"
    assert "keyterms" not in kwargs


def test_keyterms_passed_through_and_capped_at_1000():
    cliente = FakeElevenLabs()
    muchos_terminos = [f"termino{i}" for i in range(1200)]

    transcribir_bytes(b"audio-bytes-fake", cliente=cliente, keyterms=muchos_terminos)

    kwargs = cliente.speech_to_text.calls[0]
    assert len(kwargs["keyterms"]) == 1000
    assert kwargs["keyterms"][0] == "termino0"


def test_empty_keyterms_not_sent():
    cliente = FakeElevenLabs()

    transcribir_bytes(b"audio-bytes-fake", cliente=cliente, keyterms=[])

    assert "keyterms" not in cliente.speech_to_text.calls[0]


def test_api_failure_wrapped_in_error_transcripcion():
    cliente = FakeElevenLabs(error=RuntimeError("401 unauthorized"))

    with pytest.raises(ErrorTranscripcion):
        transcribir_bytes(b"audio-bytes-fake", cliente=cliente)


def test_custom_modelo_and_idioma_forwarded():
    cliente = FakeElevenLabs()

    transcribir_bytes(
        b"audio-bytes-fake", cliente=cliente, modelo="scribe_v1", idioma="en"
    )

    kwargs = cliente.speech_to_text.calls[0]
    assert kwargs["model_id"] == "scribe_v1"
    assert kwargs["language_code"] == "en"
