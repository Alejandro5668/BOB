"""Unit tests for consultar_documentacion.py — FakeAnthropic client, no
network calls. Every assertion goes through `.texto`/`.tipo` on the
`RespuestaConsulta` return value (never a bare `str` comparison) so the
return-contract break introduced in this PR fails LOUD if it regresses."""

import pytest

from cliente_anthropic import ErrorConfiguracion
from consultar_documentacion import (
    MODELO,
    SIN_INFORMACION,
    TIPO_PREGUNTA_ACLARATORIA,
    TIPO_RESPUESTA,
    TIPO_SIN_INFORMACION,
    _interpretar_respuesta,
    responder_consulta,
)
from prompts import (
    ENTRADA_RESPONDEDOR_CONSULTA,
    MARCA_PREGUNTA_ACLARATORIA,
    MARCA_RESPUESTA_DIRECTA,
    PREFILL_RESPONDEDOR_CONSULTA,
    RESPONDEDOR_CONSULTA_DOCUMENTACION,
)


class FakeBloqueTexto:
    def __init__(self, text):
        self.type, self.text = "text", text


class FakeMensaje:
    def __init__(self, text):
        self.content = [FakeBloqueTexto(text)]


class FakeMessages:
    # Canned text is PREFILL-SHAPED: it continues from `[TIPO:` rather than
    # repeating it, exactly like what the real Anthropic API returns for an
    # assistant-turn prefill.
    def __init__(self, respuesta="RESPUESTA] Respuesta de prueba"):
        self.calls = []
        self._respuesta = respuesta

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return FakeMensaje(self._respuesta)


class FakeAnthropic:
    def __init__(self, respuesta="RESPUESTA] Respuesta de prueba"):
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

    assert resultado.texto == SIN_INFORMACION
    assert resultado.tipo == TIPO_SIN_INFORMACION


def test_missing_key_raises_error_configuracion_when_context_exists(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with pytest.raises(ErrorConfiguracion):
        responder_consulta(
            "¿Cómo funciona el módulo de riesgos?",
            proveedor_contexto=lambda p: "Documentación real del módulo.",
        )


def test_responder_consulta_with_injected_client_and_context(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    cliente = FakeAnthropic(respuesta="RESPUESTA] El módulo permite registrar y valorar riesgos.")
    pregunta = "¿Cómo funciona el módulo de gestión de riesgos?"
    contexto = "Documentación: el módulo permite registrar riesgos y calcular su exposición."

    resultado = responder_consulta(
        pregunta,
        cliente=cliente,
        proveedor_contexto=lambda p: contexto,
    )

    assert resultado.texto == "El módulo permite registrar y valorar riesgos."
    assert resultado.tipo == TIPO_RESPUESTA
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


# --- Type-tag protocol: request shape + `_interpretar_respuesta` parsing ---


def test_request_sends_the_type_tag_prefill_as_the_last_message(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    cliente = FakeAnthropic()

    responder_consulta(
        "¿Cómo funciona el módulo?",
        cliente=cliente,
        proveedor_contexto=lambda p: "contexto",
    )

    kwargs = cliente.messages.calls[0]
    assert kwargs["messages"][-1] == {
        "role": "assistant",
        "content": PREFILL_RESPONDEDOR_CONSULTA,
    }


def test_respuesta_marker_is_stripped_from_the_analyst_facing_text():
    resultado = _interpretar_respuesta(f"{MARCA_RESPUESTA_DIRECTA} El módulo permite X.")

    assert resultado.texto == "El módulo permite X."
    assert resultado.tipo == TIPO_RESPUESTA


def test_aclaracion_marker_returns_a_clarifying_question_state():
    resultado = _interpretar_respuesta(f"{MARCA_PREGUNTA_ACLARATORIA} ¿Te referís al módulo A o al B?")

    assert resultado.texto == "¿Te referís al módulo A o al B?"
    assert resultado.tipo == TIPO_PREGUNTA_ACLARATORIA


def test_unknown_marker_degrades_to_respuesta_keeping_the_full_text():
    texto_crudo = "[TIPO:DESCONOCIDO] Algo de texto."

    resultado = _interpretar_respuesta(texto_crudo)

    assert resultado.texto == texto_crudo.strip()
    assert resultado.tipo == TIPO_RESPUESTA


def test_missing_marker_degrades_to_respuesta_keeping_the_full_text():
    texto_crudo = "El módulo permite registrar riesgos, sin ninguna marca de tipo."

    resultado = _interpretar_respuesta(texto_crudo)

    assert resultado.texto == texto_crudo.strip()
    assert resultado.tipo == TIPO_RESPUESTA


def test_a_closing_bracket_inside_the_prose_is_not_mistaken_for_a_marker():
    """The `]` from `partition` is structural: it is only meaningful as the
    very FIRST one in a prefill-shaped answer. A `]` the model writes mid
    prose (e.g. quoting a list) after the marker must not itself confuse the
    parser once the marker has already been consumed."""
    texto_crudo = f"{MARCA_RESPUESTA_DIRECTA} Ver la lista [1, 2, 3] de casos."

    resultado = _interpretar_respuesta(texto_crudo)

    assert resultado.texto == "Ver la lista [1, 2, 3] de casos."
    assert resultado.tipo == TIPO_RESPUESTA


def test_the_three_states_are_mutually_exclusive(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    respuesta_directa = _interpretar_respuesta(f"{MARCA_RESPUESTA_DIRECTA} texto")
    pregunta_aclaratoria = _interpretar_respuesta(f"{MARCA_PREGUNTA_ACLARATORIA} pregunta")
    sin_informacion = responder_consulta(
        "¿algo?", cliente=FakeAnthropic(), proveedor_contexto=lambda p: ""
    )

    tipos = {respuesta_directa.tipo, pregunta_aclaratoria.tipo, sin_informacion.tipo}

    assert tipos == {TIPO_RESPUESTA, TIPO_PREGUNTA_ACLARATORIA, TIPO_SIN_INFORMACION}
    assert len(tipos) == 3


# --- Prompt shape: `RESPONDEDOR_CONSULTA_DOCUMENTACION` ---


def test_prompt_declares_both_type_markers_verbatim():
    assert MARCA_RESPUESTA_DIRECTA in RESPONDEDOR_CONSULTA_DOCUMENTACION
    assert MARCA_PREGUNTA_ACLARATORIA in RESPONDEDOR_CONSULTA_DOCUMENTACION


def test_prompt_no_longer_instructs_the_model_to_emit_the_sin_informacion_notice():
    """The old bullet told the model to EMIT the reserved sentence as its own
    answer whenever context didn't cover the question — even when context WAS
    found, collapsing the SIN_INFORMACION state into an ordinary answer. The
    sentence may still appear quoted as part of an explicit BAN on using it in
    that state; what must be gone is the instructing pattern that told the
    model to say it."""
    assert f'decilo: "{SIN_INFORMACION}"' not in RESPONDEDOR_CONSULTA_DOCUMENTACION
    assert "no uses la frase" in RESPONDEDOR_CONSULTA_DOCUMENTACION.lower()


def test_prompt_requires_signaling_uncertainty_and_variability():
    prompt = RESPONDEDOR_CONSULTA_DOCUMENTACION.lower()
    assert "sin confirmar" in prompt
    assert "varía" in prompt or "variantes" in prompt


def test_prompt_limits_a_clarification_to_one_question():
    prompt = RESPONDEDOR_CONSULTA_DOCUMENTACION.lower()
    assert "una sola pregunta" in prompt
