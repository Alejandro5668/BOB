"""Unit tests for transcribir.py — fake model, no real Whisper inference."""

import os
import tempfile

import pytest

import transcribir
from transcribir import (
    ErrorDependenciaAudio,
    ErrorTranscripcion,
    transcribir_bytes,
)


class FakeSegment:
    def __init__(self, text, end):
        self.text = text
        self.end = end


class FakeInfo:
    def __init__(self, duration):
        self.duration = duration


class FakeModel:
    """Stands in for faster_whisper.WhisperModel via the loader seam."""

    def __init__(self, segments, info, error=None):
        self._segments = segments
        self._info = info
        self._error = error

    def transcribe(self, ruta, vad_filter=True, language="es", beam_size=1):
        if self._error is not None:
            raise self._error
        return iter(self._segments), self._info


def _spy_named_temp_file(monkeypatch, created_paths):
    original = tempfile.NamedTemporaryFile

    def spy(*args, **kwargs):
        tmp = original(*args, **kwargs)
        created_paths.append(tmp.name)
        return tmp

    monkeypatch.setattr(transcribir.tempfile, "NamedTemporaryFile", spy)


def test_temp_file_deleted_on_success(monkeypatch):
    created_paths = []
    _spy_named_temp_file(monkeypatch, created_paths)

    segments = [FakeSegment("hola ", 1.0), FakeSegment("mundo", 2.0)]
    info = FakeInfo(duration=2.0)
    monkeypatch.setattr(
        transcribir, "_cargar_modelo", lambda: FakeModel(segments, info)
    )

    texto = transcribir_bytes(b"audio-bytes-fake")

    assert texto == "hola mundo"
    assert len(created_paths) == 1
    assert not os.path.exists(created_paths[0])


def test_temp_file_deleted_on_exception(monkeypatch):
    created_paths = []
    _spy_named_temp_file(monkeypatch, created_paths)

    monkeypatch.setattr(
        transcribir,
        "_cargar_modelo",
        lambda: FakeModel([], FakeInfo(1.0), error=RuntimeError("decode boom")),
    )

    with pytest.raises(ErrorTranscripcion):
        transcribir_bytes(b"audio-bytes-fake")

    assert len(created_paths) == 1
    assert not os.path.exists(created_paths[0])


def test_on_progress_receives_monotonic_fraction_in_range(monkeypatch):
    segments = [
        FakeSegment("uno ", 1.0),
        FakeSegment("dos ", 2.0),
        FakeSegment("tres", 4.0),
    ]
    info = FakeInfo(duration=4.0)
    monkeypatch.setattr(
        transcribir, "_cargar_modelo", lambda: FakeModel(segments, info)
    )

    valores = []
    transcribir_bytes(b"audio-bytes-fake", on_progress=valores.append)

    assert valores == sorted(valores)
    assert all(0.0 <= v <= 1.0 for v in valores)
    assert valores[-1] == 1.0


def test_missing_av_raises_error_dependencia_audio(monkeypatch):
    import importlib.util as real_importlib_util

    def fake_find_spec(name):
        if name == "av":
            return None
        return real_importlib_util.find_spec(name)

    monkeypatch.setattr(transcribir.importlib.util, "find_spec", fake_find_spec)

    with pytest.raises(ErrorDependenciaAudio):
        transcribir.verificar_dependencias()
