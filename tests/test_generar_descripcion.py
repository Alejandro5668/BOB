"""Unit tests for generar_descripcion.py — FakeGroq client, no network calls."""

import ast
import json
from pathlib import Path

import groq as groq_module
import pytest

from generar_descripcion import (
    AVISO_RESULTADO_NO_CONFIABLE,
    ENCABEZADO_RESULTADO,
    MAX_REINTENTOS_RATE_LIMIT,
    MODELO,
    MODELO_AUXILIAR,
    ErrorConfiguracion,
    _crear_completion_con_reintento,
    generar_descripcion,
    postprocesar_descripcion,
)
from prompts import (
    ENTRADA_GENERADOR_DESCRIPCION,
    ENTRADA_GENERADOR_DESCRIPCION_CON_CONTEXTO,
    GENERADOR_DESCRIPCION_TICKET,
    GENERADOR_DESCRIPCION_TICKET_CON_CONTEXTO,
    PLANTILLA_TICKET_JIRA,
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
    """Discriminates by `model`: MODELO_AUXILIAR calls are the verifier
    (JSON {"fundamentado": ...}), anything else is the main generation call."""

    def __init__(self, respuesta="Descripción generada de prueba", fundamentado=True):
        self.calls = []
        self._respuesta = respuesta
        self._fundamentado = fundamentado

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs.get("model") == MODELO_AUXILIAR:
            return FakeResponse(json.dumps({"fundamentado": self._fundamentado}))
        return FakeResponse(self._respuesta)


class FakeChat:
    def __init__(self, respuesta="Descripción generada de prueba", fundamentado=True):
        self.completions = FakeCompletions(respuesta, fundamentado)


class FakeGroq:
    def __init__(self, respuesta="Descripción generada de prueba", fundamentado=True):
        self.chat = FakeChat(respuesta, fundamentado)


# --- Fase 1/2 regression: fail-fast + request shape -----------------------


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

    # Rule 9: no implementation-detail speculation.
    assert "PROHIBIDO mencionar o suponer detalles de implementación" in system_msg
    # Rule 10: no technical-cause diagnosis.
    assert "PROHIBIDO diagnosticar la causa técnica" in system_msg
    # Transcript is sent verbatim, bounded by --- delimiters.
    assert transcripcion in user_msg
    assert "---" in user_msg


def test_no_context_provider_sends_byte_identical_prompt(monkeypatch):
    """`proveedor_contexto` returning "" must select the no-context prompt pair."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    cliente = FakeGroq()
    transcripcion = "El analista describe un error al entrar al módulo de riesgos."

    resultado = generar_descripcion(
        transcripcion,
        cliente=cliente,
        proveedor_contexto=lambda t: "",
    )

    assert resultado == "Descripción generada de prueba"
    kwargs = cliente.chat.completions.calls[0]
    system_msg = kwargs["messages"][0]["content"]
    user_msg = kwargs["messages"][1]["content"]

    assert system_msg == GENERADOR_DESCRIPCION_TICKET
    assert user_msg == ENTRADA_GENERADOR_DESCRIPCION.format(transcripcion=transcripcion)
    assert "===" not in user_msg


def test_context_provider_with_match_uses_prompt_con_contexto(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    cliente = FakeGroq()
    transcripcion = "El analista describe un error al entrar al módulo de riesgos."
    texto_contexto = "Documentación de referencia del módulo de riesgos."

    resultado = generar_descripcion(
        transcripcion,
        cliente=cliente,
        proveedor_contexto=lambda t: texto_contexto,
    )

    assert resultado == "Descripción generada de prueba"
    kwargs = cliente.chat.completions.calls[0]
    system_msg = kwargs["messages"][0]["content"]
    user_msg = kwargs["messages"][1]["content"]

    assert system_msg == GENERADOR_DESCRIPCION_TICKET_CON_CONTEXTO
    assert system_msg.startswith(GENERADOR_DESCRIPCION_TICKET)
    assert "PROHIBIDO presentar contenido del contexto" in system_msg

    # Context block uses === delimiters (distinct from the --- transcript
    # delimiters) and contains only the injected text, verbatim.
    assert "===" in user_msg
    assert texto_contexto in user_msg
    assert transcripcion in user_msg
    assert "---" in user_msg


def test_context_provider_receives_the_transcript(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    cliente = FakeGroq()
    transcripcion = "El analista describe un error al entrar al módulo de riesgos."
    recibido = []

    def proveedor_espia(texto):
        recibido.append(texto)
        return ""

    generar_descripcion(transcripcion, cliente=cliente, proveedor_contexto=proveedor_espia)

    assert recibido == [transcripcion]


def test_default_context_provider_is_contexto_memoria_buscar_contexto(monkeypatch):
    """When `proveedor_contexto` is None, it resolves lazily to
    `contexto_memoria.buscar_contexto` — never raises, never touches
    Groq's request shape when there's nothing to select from."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("MEMORY_DIR", "ruta/que/no/existe")

    cliente = FakeGroq()
    transcripcion = "texto que no coincide con ningún documento conocido"

    resultado = generar_descripcion(
        transcripcion,
        cliente=cliente,
        proveedor_contexto=None,
    )

    assert resultado == "Descripción generada de prueba"
    kwargs = cliente.chat.completions.calls[0]
    assert kwargs["messages"][0]["content"] == GENERADOR_DESCRIPCION_TICKET


# --- Template shape: prompt content ----------------------------------------


@pytest.mark.parametrize("prompt", [GENERADOR_DESCRIPCION_TICKET, GENERADOR_DESCRIPCION_TICKET_CON_CONTEXTO])
def test_system_prompts_embed_plantilla_ticket_jira_verbatim(prompt):
    assert PLANTILLA_TICKET_JIRA in prompt


@pytest.mark.parametrize("prompt", [GENERADOR_DESCRIPCION_TICKET, GENERADOR_DESCRIPCION_TICKET_CON_CONTEXTO])
def test_template_headings_appear_in_fixed_order(prompt):
    encabezados = [
        "## Módulo afectado",
        "## Contexto del módulo",
        "## Qué pasó",
        "## Pasos para reproducir",
        "## Resultado esperado vs. obtenido",
    ]
    posiciones = [prompt.index(h) for h in encabezados]
    assert posiciones == sorted(posiciones)


def test_rule_5_prohibits_inventing_generic_expectation():
    assert "PROHIBIDO inventar un resultado esperado" in GENERADOR_DESCRIPCION_TICKET


def test_rules_3_and_4_require_full_omission_no_placeholder():
    assert "ELIMINA de la respuesta ese encabezado" in GENERADOR_DESCRIPCION_TICKET
    assert "PROHIBIDO rellenar una sección omitida" in GENERADOR_DESCRIPCION_TICKET


def test_rule_6_modulo_afectado_fallback_literal():
    assert "Módulo afectado: no identificado" in GENERADOR_DESCRIPCION_TICKET


def test_rule_7_requires_neutral_spanish():
    assert "español neutro" in GENERADOR_DESCRIPCION_TICKET


def test_rule_12_no_fence_no_preamble_wording():
    assert "sin preámbulo" in GENERADOR_DESCRIPCION_TICKET
    assert "SIN envolverla en un bloque de código" in GENERADOR_DESCRIPCION_TICKET


def test_context_rules_13_to_19_only_in_con_contexto_prompt():
    assert "Módulo > Submódulo" in GENERADOR_DESCRIPCION_TICKET_CON_CONTEXTO
    assert "Módulo > Submódulo" not in GENERADOR_DESCRIPCION_TICKET


def test_rule_15_allows_module_functionality_only_in_contexto_del_modulo_section():
    """Regression: rule 18 originally banned ANY functional enumeration from
    context, making descriptions too terse when good documentation existed
    (real example: cfg_configuracion/lxm_modificar.md — a labels/lists
    management screen — was correctly retrieved but its content was
    discarded entirely). Rule 15 now channels that into one dedicated
    section instead."""
    assert "## Contexto del módulo" in GENERADOR_DESCRIPCION_TICKET_CON_CONTEXTO
    assert "ÚNICA sección donde podés describir funcionalidad" in GENERADOR_DESCRIPCION_TICKET_CON_CONTEXTO
    assert "nunca mezcles el comportamiento documentado con los hechos del incidente" in GENERADOR_DESCRIPCION_TICKET_CON_CONTEXTO


def test_rule_16_context_facts_confined_to_contexto_del_modulo_section():
    assert (
        "eso solo puede ir en `## Contexto del módulo`, nunca en `## Qué pasó`"
        in GENERADOR_DESCRIPCION_TICKET_CON_CONTEXTO
    )


def test_rule_19_still_bans_literal_copying_and_context_leaking_into_steps():
    assert "parafraseá siempre" in GENERADOR_DESCRIPCION_TICKET_CON_CONTEXTO
    assert (
        "usar el contexto para inventar pasos de reproducción o un resultado esperado"
        in GENERADOR_DESCRIPCION_TICKET_CON_CONTEXTO
    )


# --- Sub-module naming via synthetic context (never touches memory/ fixtures) --

CONTEXTO_SUBMODULO_SINTETICO = """## Matriz de riesgos
Pantalla para registrar y calificar riesgos identificados por proceso.

## Submódulos
- Matriz de riesgos: registro y calificación de riesgos.
- Planes de acción: seguimiento de acciones correctivas asociadas a un riesgo."""


def test_synthetic_submodule_context_reaches_user_message_verbatim(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    cliente = FakeGroq()
    transcripcion = "El analista no pudo calificar un riesgo en la matriz de riesgos."

    resultado = generar_descripcion(
        transcripcion,
        cliente=cliente,
        proveedor_contexto=lambda t: CONTEXTO_SUBMODULO_SINTETICO,
    )

    assert resultado == "Descripción generada de prueba"
    kwargs = cliente.chat.completions.calls[0]
    system_msg = kwargs["messages"][0]["content"]
    user_msg = kwargs["messages"][1]["content"]

    assert system_msg == GENERADOR_DESCRIPCION_TICKET_CON_CONTEXTO
    assert "Módulo > Submódulo" in system_msg
    assert user_msg == ENTRADA_GENERADOR_DESCRIPCION_CON_CONTEXTO.format(
        contexto=CONTEXTO_SUBMODULO_SINTETICO, transcripcion=transcripcion
    )


# --- Template output shape (end-to-end through the post-processor) --------


def test_full_template_response_starts_with_modulo_and_contains_que_paso(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    texto = (
        "## Módulo afectado\n"
        "Gestión de riesgos\n\n"
        "## Qué pasó\n"
        "El analista intentó guardar un riesgo y la pantalla se quedó cargando.\n\n"
        "## Pasos para reproducir\n"
        "1. Entrar al módulo de riesgos.\n"
        "2. Completar el formulario de un riesgo nuevo.\n"
        "3. Presionar guardar.\n"
    )
    cliente = FakeGroq(respuesta=texto)

    resultado = generar_descripcion("transcripción de prueba", cliente=cliente)

    assert resultado.startswith("## Módulo afectado")
    assert "## Qué pasó" in resultado


def test_response_without_steps_omits_pasos_heading(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    texto = "## Módulo afectado\nGestión de riesgos\n\n## Qué pasó\nAlgo pasó y no quedaron pasos claros.\n"
    cliente = FakeGroq(respuesta=texto)

    resultado = generar_descripcion("transcripción de prueba", cliente=cliente)

    assert "## Pasos para reproducir" not in resultado


def test_response_without_expectation_omits_resultado_heading(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    texto = "## Módulo afectado\nGestión de riesgos\n\n## Qué pasó\nAlgo pasó y no se mencionó una expectativa.\n"
    cliente = FakeGroq(respuesta=texto)

    resultado = generar_descripcion("transcripción de prueba", cliente=cliente)

    assert "## Resultado esperado vs. obtenido" not in resultado


def test_response_falls_back_to_modulo_no_identificado(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    texto = "## Módulo afectado\nMódulo afectado: no identificado\n\n## Qué pasó\nAlgo pasó.\n"
    cliente = FakeGroq(respuesta=texto)

    resultado = generar_descripcion("transcripción de prueba", cliente=cliente)

    assert "Módulo afectado: no identificado" in resultado


def test_response_has_no_code_fence(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    texto = "## Módulo afectado\nGestión de riesgos\n\n## Qué pasó\nAlgo pasó.\n"
    cliente = FakeGroq(respuesta=texto)

    resultado = generar_descripcion("transcripción de prueba", cliente=cliente)

    assert "```" not in resultado


def test_generar_descripcion_calls_verifier_when_resultado_esperado_present(monkeypatch):
    """End-to-end wiring: the SAME cliente is reused for the verifier call."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    texto = (
        f"## Módulo afectado\nRiesgos\n\n## Qué pasó\nAlgo pasó.\n\n"
        f"{ENCABEZADO_RESULTADO}\nEsperaba ver el ticket #4521 cerrado y obtuvo un error 500.\n"
    )
    cliente = FakeGroq(respuesta=texto, fundamentado=True)

    resultado = generar_descripcion("transcripción de prueba", cliente=cliente)

    assert len(cliente.chat.completions.calls) == 2
    llamada_verificador = cliente.chat.completions.calls[1]
    assert llamada_verificador["model"] == MODELO_AUXILIAR
    assert llamada_verificador["response_format"] == {"type": "json_object"}
    assert "#4521" in resultado


def test_generar_descripcion_no_verifier_call_when_no_resultado_section(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    texto = "## Módulo afectado\nRiesgos\n\n## Qué pasó\nAlgo pasó.\n"
    cliente = FakeGroq(respuesta=texto)

    generar_descripcion("transcripción de prueba", cliente=cliente)

    assert len(cliente.chat.completions.calls) == 1


# --- Post-processor: postprocesar_descripcion --------------------------------


def test_postprocesar_verifier_says_grounded_keeps_text():
    texto = (
        "## Módulo afectado\nRiesgos\n\n"
        "## Qué pasó\nAlgo pasó.\n\n"
        f"{ENCABEZADO_RESULTADO}\nEsperaba ver el ticket #4521 cerrado y obtuvo un error 500.\n"
    )
    cliente = FakeGroq(fundamentado=True)

    assert postprocesar_descripcion(texto, "transcripción", cliente) == texto


def test_postprocesar_verifier_says_not_grounded_replaces_with_notice():
    texto = (
        "## Módulo afectado\nRiesgos\n\n"
        "## Qué pasó\nAlgo pasó.\n\n"
        f"{ENCABEZADO_RESULTADO}\nSe esperaba que funcionara correctamente.\n"
    )
    cliente = FakeGroq(fundamentado=False)

    resultado = postprocesar_descripcion(texto, "transcripción", cliente)

    assert ENCABEZADO_RESULTADO in resultado
    assert AVISO_RESULTADO_NO_CONFIABLE in resultado
    assert "funcionara correctamente" not in resultado


def test_postprocesar_verifier_exception_defaults_to_keeping_text():
    """A broken verifier must never erase real analyst-provided content."""
    texto = (
        "## Módulo afectado\nRiesgos\n\n"
        "## Qué pasó\nAlgo pasó.\n\n"
        f"{ENCABEZADO_RESULTADO}\nEsperaba ver el reporte exportado en PDF.\n"
    )

    class ClienteRoto:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    raise RuntimeError("fallo de red simulado")

    resultado = postprocesar_descripcion(texto, "transcripción", ClienteRoto())

    assert resultado == texto


def test_postprocesar_verifier_malformed_json_defaults_to_keeping_text():
    texto = (
        "## Módulo afectado\nRiesgos\n\n"
        "## Qué pasó\nAlgo pasó.\n\n"
        f"{ENCABEZADO_RESULTADO}\nEsperaba ver el reporte exportado en PDF.\n"
    )

    class ClienteRespuestaInvalida:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    return FakeResponse("esto no es json")

    resultado = postprocesar_descripcion(texto, "transcripción", ClienteRespuestaInvalida())

    assert resultado == texto


def test_postprocesar_absent_section_is_a_no_op_and_skips_verifier():
    texto = "## Módulo afectado\nRiesgos\n\n## Qué pasó\nAlgo pasó.\n"
    cliente = FakeGroq()

    assert postprocesar_descripcion(texto, "transcripción", cliente) == texto
    assert cliente.chat.completions.calls == []


def test_postprocesar_empty_body_becomes_notice_without_calling_verifier():
    texto = f"## Módulo afectado\nRiesgos\n\n## Qué pasó\nAlgo pasó.\n\n{ENCABEZADO_RESULTADO}\n\n"
    cliente = FakeGroq()

    resultado = postprocesar_descripcion(texto, "transcripción", cliente)

    assert AVISO_RESULTADO_NO_CONFIABLE in resultado
    assert cliente.chat.completions.calls == []


def test_postprocesar_strips_wrapping_fence_keeps_inner_fence():
    texto = (
        "```markdown\n"
        "## Módulo afectado\nRiesgos\n\n"
        "## Qué pasó\nUsó `comando --flag` y falló.\n"
        "```"
    )
    cliente = FakeGroq()

    resultado = postprocesar_descripcion(texto, "transcripción", cliente)

    assert not resultado.startswith("```")
    assert not resultado.endswith("```")
    assert "`comando --flag`" in resultado
    assert cliente.chat.completions.calls == []


def test_postprocesar_non_string_content_tolerates_none():
    assert postprocesar_descripcion(None, "transcripción", FakeGroq()) == ""


def test_postprocesar_blank_string_passthrough():
    assert postprocesar_descripcion("   ", "transcripción", FakeGroq()) == "   "


def test_fake_groq_canned_response_round_trips_unchanged():
    """The default FakeGroq canned text has no fence and no Resultado
    heading, so postprocesar_descripcion must no-op — every Fase 1/2
    assertion built on the literal canned string keeps holding."""
    cliente = FakeGroq()
    assert postprocesar_descripcion("Descripción generada de prueba", "transcripción", cliente) == (
        "Descripción generada de prueba"
    )


# --- _crear_completion_con_reintento: rate-limit retry ----------------------


class ErrorRateLimitFalso(RuntimeError):
    def __init__(self, mensaje):
        super().__init__(mensaje)
        self.status_code = 429


class ErrorNoRateLimitFalso(RuntimeError):
    def __init__(self, mensaje):
        super().__init__(mensaje)
        self.status_code = 400


def test_reintento_no_op_on_success():
    cliente = FakeGroq()
    resultado = _crear_completion_con_reintento(cliente, model=MODELO, messages=[])
    assert resultado.choices[0].message.content == "Descripción generada de prueba"
    assert len(cliente.chat.completions.calls) == 1


def test_reintento_retries_on_rate_limit_then_succeeds(monkeypatch):
    esperas = []
    monkeypatch.setattr("generar_descripcion.time.sleep", lambda s: esperas.append(s))

    intentos = {"n": 0}

    class ClienteFallaUnaVez:
        class chat:
            class completions:
                calls = []

                @staticmethod
                def create(**kwargs):
                    ClienteFallaUnaVez.chat.completions.calls.append(kwargs)
                    intentos["n"] += 1
                    if intentos["n"] == 1:
                        raise ErrorRateLimitFalso("... please try again in 3.5s")
                    return FakeResponse("ok")

    resultado = _crear_completion_con_reintento(ClienteFallaUnaVez(), model=MODELO, messages=[])

    assert resultado.choices[0].message.content == "ok"
    assert intentos["n"] == 2
    assert esperas == [4.5]  # parsed wait (3.5) + 1s buffer


def test_reintento_gives_up_after_max_attempts(monkeypatch):
    monkeypatch.setattr("generar_descripcion.time.sleep", lambda s: None)
    llamadas = []

    class ClienteSiempreFalla:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    llamadas.append(kwargs)
                    raise ErrorRateLimitFalso("please try again in 1s")

    with pytest.raises(ErrorRateLimitFalso):
        _crear_completion_con_reintento(ClienteSiempreFalla(), model=MODELO, messages=[])

    assert len(llamadas) == MAX_REINTENTOS_RATE_LIMIT + 1


def test_reintento_does_not_retry_non_rate_limit_errors(monkeypatch):
    llamado = []
    monkeypatch.setattr("generar_descripcion.time.sleep", lambda s: llamado.append(s))

    class ClienteFallaFuerte:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    raise ErrorNoRateLimitFalso("clave inválida")

    with pytest.raises(ErrorNoRateLimitFalso):
        _crear_completion_con_reintento(ClienteFallaFuerte(), model=MODELO, messages=[])

    assert llamado == []


def test_reintento_falls_back_to_default_wait_when_message_unparseable(monkeypatch):
    esperas = []
    monkeypatch.setattr("generar_descripcion.time.sleep", lambda s: esperas.append(s))

    intentos = {"n": 0}

    class ClienteMensajeRaro:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    intentos["n"] += 1
                    if intentos["n"] == 1:
                        raise ErrorRateLimitFalso("rate limited, no parseable wait here")
                    return FakeResponse("ok")

    _crear_completion_con_reintento(ClienteMensajeRaro(), model=MODELO, messages=[])

    assert esperas == [5.0]


# --- Repository rule: no inline prompt text in generar_descripcion.py -----


def test_no_inline_prompt_text_in_generar_descripcion():
    ruta = Path(__file__).resolve().parent.parent / "generar_descripcion.py"
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    limite = 120

    ofensores = []
    for nodo in arbol.body:
        if isinstance(nodo, ast.Assign) and isinstance(nodo.value, ast.Constant):
            valor = nodo.value.value
            if isinstance(valor, str) and len(valor) > limite:
                objetivos = [t.id for t in nodo.targets if isinstance(t, ast.Name)]
                ofensores.append((objetivos, len(valor)))

    assert ofensores == []
