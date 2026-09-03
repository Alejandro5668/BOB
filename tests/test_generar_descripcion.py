"""Unit tests for generar_descripcion.py — FakeAnthropic client, no network calls."""

import ast
from pathlib import Path

import pytest

from generar_descripcion import (
    AVISO_RESULTADO_NO_CONFIABLE,
    ENCABEZADO_RESULTADO,
    MODELO,
    MODULO_NO_IDENTIFICADO,
    ErrorConfiguracion,
    generar_descripcion,
    postprocesar_descripcion,
)
from prompts import (
    ENTRADA_GENERADOR_DESCRIPCION,
    ENTRADA_GENERADOR_DESCRIPCION_CON_CONTEXTO,
    GENERADOR_DESCRIPCION_TICKET,
    GENERADOR_DESCRIPCION_TICKET_CON_CONTEXTO,
    PLANTILLA_TICKET_JIRA,
    VERIFICADOR_MODULO_AFECTADO,
    VERIFICADOR_RESULTADO_ESPERADO,
)


class FakeBloqueTexto:
    def __init__(self, text):
        self.type, self.text = "text", text


class FakeMensaje:
    def __init__(self, text):
        self.content = [FakeBloqueTexto(text)]


class FakeMessages:
    """Discriminates by `system`: a `VERIFICADOR_RESULTADO_ESPERADO` call is
    the resultado-esperado verifier, a `VERIFICADOR_MODULO_AFECTADO` call is
    the módulo-afectado verifier (both JSON-prefill), anything else is the
    main generation call. Discriminating on `system` rather than `model`
    because `MODELO == MODELO_AUXILIAR` now (both alias `MODELO_HAIKU`)."""

    def __init__(
        self,
        respuesta="Descripción generada de prueba",
        fundamentado=True,
        modulo_fundamentado=True,
    ):
        self.calls = []
        self._respuesta = respuesta
        self._fundamentado = fundamentado
        self._modulo_fundamentado = modulo_fundamentado

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs.get("system") == VERIFICADOR_RESULTADO_ESPERADO:
            valor = "true" if self._fundamentado else "false"
            return FakeMensaje(f'"fundamentado": {valor}}}')
        if kwargs.get("system") == VERIFICADOR_MODULO_AFECTADO:
            valor = "true" if self._modulo_fundamentado else "false"
            return FakeMensaje(f'"fundamentado": {valor}}}')
        return FakeMensaje(self._respuesta)


class FakeAnthropic:
    def __init__(
        self,
        respuesta="Descripción generada de prueba",
        fundamentado=True,
        modulo_fundamentado=True,
    ):
        self.messages = FakeMessages(respuesta, fundamentado, modulo_fundamentado)


@pytest.fixture(autouse=True)
def _sin_memoria_real(monkeypatch):
    """Client sharing (design decision 7) threads the injected
    `FakeAnthropic` into the default `proveedor_contexto`. Point
    `MEMORY_DIR` away from the project's real `memory/` folder so it is
    never scanned/selected against by these tests: every test here either
    injects its own `proveedor_contexto` or relies on this degrading to
    no-context (zero extra `messages.create` calls)."""
    monkeypatch.setenv("MEMORY_DIR", "ruta/que/no/existe")


# --- Fase 1/2 regression: fail-fast + request shape -----------------------


def test_missing_key_raises_error_configuracion_before_any_call(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("Anthropic client must not be constructed without a key")

    import anthropic

    monkeypatch.setattr(anthropic, "Anthropic", fail_if_called)

    with pytest.raises(ErrorConfiguracion):
        generar_descripcion("transcripción de prueba")


def test_blank_key_raises_error_configuracion(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "   ")

    def fail_if_called(*args, **kwargs):
        raise AssertionError("Anthropic client must not be constructed with a blank key")

    import anthropic

    monkeypatch.setattr(anthropic, "Anthropic", fail_if_called)

    with pytest.raises(ErrorConfiguracion):
        generar_descripcion("transcripción de prueba")


def test_generar_descripcion_with_injected_client(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    cliente = FakeAnthropic()
    transcripcion = "El analista describe un error al entrar al módulo de riesgos."

    resultado = generar_descripcion(transcripcion, cliente=cliente)

    assert resultado == "Descripción generada de prueba"
    assert len(cliente.messages.calls) == 1

    kwargs = cliente.messages.calls[0]
    assert kwargs["model"] == MODELO
    assert "temperature" not in kwargs
    assert kwargs["max_tokens"] == 1024

    system_msg = kwargs["system"]
    user_msg = kwargs["messages"][0]["content"]

    # Rule 9: no implementation-detail speculation.
    assert "PROHIBIDO mencionar o suponer detalles de implementación" in system_msg
    # Rule 10: no technical-cause diagnosis.
    assert "PROHIBIDO diagnosticar la causa técnica" in system_msg
    # Transcript is sent verbatim, bounded by --- delimiters.
    assert transcripcion in user_msg
    assert "---" in user_msg


def test_no_context_provider_sends_byte_identical_prompt(monkeypatch):
    """`proveedor_contexto` returning "" must select the no-context prompt pair."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    cliente = FakeAnthropic()
    transcripcion = "El analista describe un error al entrar al módulo de riesgos."

    resultado = generar_descripcion(
        transcripcion,
        cliente=cliente,
        proveedor_contexto=lambda t: "",
    )

    assert resultado == "Descripción generada de prueba"
    kwargs = cliente.messages.calls[0]
    system_msg = kwargs["system"]
    user_msg = kwargs["messages"][0]["content"]

    assert system_msg == GENERADOR_DESCRIPCION_TICKET
    assert user_msg == ENTRADA_GENERADOR_DESCRIPCION.format(transcripcion=transcripcion)
    assert "===" not in user_msg


def test_context_provider_with_match_uses_prompt_con_contexto(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    cliente = FakeAnthropic()
    transcripcion = "El analista describe un error al entrar al módulo de riesgos."
    texto_contexto = "Documentación de referencia del módulo de riesgos."

    resultado = generar_descripcion(
        transcripcion,
        cliente=cliente,
        proveedor_contexto=lambda t: texto_contexto,
    )

    assert resultado == "Descripción generada de prueba"
    kwargs = cliente.messages.calls[0]
    system_msg = kwargs["system"]
    user_msg = kwargs["messages"][0]["content"]

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
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    cliente = FakeAnthropic()
    transcripcion = "El analista describe un error al entrar al módulo de riesgos."
    recibido = []

    def proveedor_espia(texto):
        recibido.append(texto)
        return ""

    generar_descripcion(transcripcion, cliente=cliente, proveedor_contexto=proveedor_espia)

    assert recibido == [transcripcion]


def test_default_context_provider_is_contexto_memoria_buscar_contexto(monkeypatch):
    """When `proveedor_contexto` is None, it resolves to a closure over
    `contexto_memoria.buscar_contexto` — never raises, never touches the
    request shape when there's nothing to select from."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("MEMORY_DIR", "ruta/que/no/existe")

    cliente = FakeAnthropic()
    transcripcion = "texto que no coincide con ningún documento conocido"

    resultado = generar_descripcion(
        transcripcion,
        cliente=cliente,
        proveedor_contexto=None,
    )

    assert resultado == "Descripción generada de prueba"
    assert len(cliente.messages.calls) == 1  # missing MEMORY_DIR degrades before any selector call
    kwargs = cliente.messages.calls[0]
    assert kwargs["system"] == GENERADOR_DESCRIPCION_TICKET


# --- Template shape: prompt content ----------------------------------------


@pytest.mark.parametrize("prompt", [GENERADOR_DESCRIPCION_TICKET, GENERADOR_DESCRIPCION_TICKET_CON_CONTEXTO])
def test_system_prompts_embed_plantilla_ticket_jira_verbatim(prompt):
    assert PLANTILLA_TICKET_JIRA in prompt


@pytest.mark.parametrize("prompt", [GENERADOR_DESCRIPCION_TICKET, GENERADOR_DESCRIPCION_TICKET_CON_CONTEXTO])
def test_template_headings_appear_in_fixed_order(prompt):
    encabezados = [
        "## Módulo afectado",
        "## Descripción del error",
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


def test_context_rules_14_to_20_only_in_con_contexto_prompt():
    assert "ruta completa de navegación" in GENERADOR_DESCRIPCION_TICKET_CON_CONTEXTO
    assert "ruta completa de navegación" not in GENERADOR_DESCRIPCION_TICKET


def test_rule_15_module_path_not_capped_at_two_levels():
    """Regression: a real 3-level case ("módulo de riesgos" > opción
    "Administración de riesgos" > "mapa térmico") lost its middle level
    because rule 14 (now 15) originally hardcoded exactly "Módulo >
    Submódulo". Fixed to allow as many levels as the analyst narrated."""
    assert "no un tope fijo de dos niveles" in GENERADOR_DESCRIPCION_TICKET_CON_CONTEXTO
    assert (
        "eso NO significa tres módulos distintos"
        in GENERADOR_DESCRIPCION_TICKET_CON_CONTEXTO
    )


def test_rule_15_allows_context_precision_inline_marked_in_descripcion_error():
    """Regression: the original design confined all context-derived
    functionality to a dedicated '## Contexto del módulo' section. Removed
    at the user's request (developers don't need a generic functionality
    primer, they need case traceability) — context precision now goes
    inline in '## Descripción del error', but ONLY behind an explicit
    "Según la documentación," marker, which replaces the heading boundary
    as the anti-hallucination line between analyst-stated facts and
    documentation-derived precision."""
    assert "## Contexto del módulo" not in GENERADOR_DESCRIPCION_TICKET_CON_CONTEXTO
    assert 'empiece con "Según la documentación,"' in GENERADOR_DESCRIPCION_TICKET_CON_CONTEXTO
    assert "## Descripción del error" in GENERADOR_DESCRIPCION_TICKET_CON_CONTEXTO


def test_rule_16_unmarked_context_content_still_banned_from_facts():
    assert (
        'sin esa marca, PROHIBIDO presentar contenido del contexto como algo que ocurrió'
        in GENERADOR_DESCRIPCION_TICKET_CON_CONTEXTO
    )


def test_rule_19_still_bans_literal_copying_and_context_leaking_into_steps():
    assert "parafraseá siempre" in GENERADOR_DESCRIPCION_TICKET_CON_CONTEXTO
    assert (
        "agregar un paso nuevo que el analista no mencionó, o para inventar un resultado esperado"
        in GENERADOR_DESCRIPCION_TICKET_CON_CONTEXTO
    )


def test_rule_19_allows_context_to_refine_step_wording_only():
    assert (
        "el contexto solo puede usarse para AFINAR LA REDACCIÓN de un paso que el analista ya narró"
        in GENERADOR_DESCRIPCION_TICKET_CON_CONTEXTO
    )


# --- Sub-module naming via synthetic context (never touches memory/ fixtures) --

CONTEXTO_SUBMODULO_SINTETICO = """## Matriz de riesgos
Pantalla para registrar y calificar riesgos identificados por proceso.

## Submódulos
- Matriz de riesgos: registro y calificación de riesgos.
- Planes de acción: seguimiento de acciones correctivas asociadas a un riesgo."""


def test_synthetic_submodule_context_reaches_user_message_verbatim(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    cliente = FakeAnthropic()
    transcripcion = "El analista no pudo calificar un riesgo en la matriz de riesgos."

    resultado = generar_descripcion(
        transcripcion,
        cliente=cliente,
        proveedor_contexto=lambda t: CONTEXTO_SUBMODULO_SINTETICO,
    )

    assert resultado == "Descripción generada de prueba"
    kwargs = cliente.messages.calls[0]
    system_msg = kwargs["system"]
    user_msg = kwargs["messages"][0]["content"]

    assert system_msg == GENERADOR_DESCRIPCION_TICKET_CON_CONTEXTO
    assert "ruta completa de navegación" in system_msg
    assert user_msg == ENTRADA_GENERADOR_DESCRIPCION_CON_CONTEXTO.format(
        contexto=CONTEXTO_SUBMODULO_SINTETICO, transcripcion=transcripcion
    )


# --- Template output shape (end-to-end through the post-processor) --------


def test_full_template_response_starts_with_modulo_and_contains_que_paso(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    texto = (
        "## Módulo afectado\n"
        "Gestión de riesgos\n\n"
        "## Descripción del error\n"
        "El analista intentó guardar un riesgo y la pantalla se quedó cargando.\n\n"
        "## Pasos para reproducir\n"
        "1. Entrar al módulo de riesgos.\n"
        "2. Completar el formulario de un riesgo nuevo.\n"
        "3. Presionar guardar.\n"
    )
    cliente = FakeAnthropic(respuesta=texto)

    resultado = generar_descripcion("transcripción de prueba", cliente=cliente)

    assert resultado.startswith("## Módulo afectado")
    assert "## Descripción del error" in resultado


def test_response_without_steps_omits_pasos_heading(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    texto = "## Módulo afectado\nGestión de riesgos\n\n## Descripción del error\nAlgo pasó y no quedaron pasos claros.\n"
    cliente = FakeAnthropic(respuesta=texto)

    resultado = generar_descripcion("transcripción de prueba", cliente=cliente)

    assert "## Pasos para reproducir" not in resultado


def test_response_without_expectation_omits_resultado_heading(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    texto = "## Módulo afectado\nGestión de riesgos\n\n## Descripción del error\nAlgo pasó y no se mencionó una expectativa.\n"
    cliente = FakeAnthropic(respuesta=texto)

    resultado = generar_descripcion("transcripción de prueba", cliente=cliente)

    assert "## Resultado esperado vs. obtenido" not in resultado


def test_response_falls_back_to_modulo_no_identificado(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    texto = "## Módulo afectado\nMódulo afectado: no identificado\n\n## Descripción del error\nAlgo pasó.\n"
    cliente = FakeAnthropic(respuesta=texto)

    resultado = generar_descripcion("transcripción de prueba", cliente=cliente)

    assert "Módulo afectado: no identificado" in resultado


def test_response_has_no_code_fence(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    texto = "## Módulo afectado\nGestión de riesgos\n\n## Descripción del error\nAlgo pasó.\n"
    cliente = FakeAnthropic(respuesta=texto)

    resultado = generar_descripcion("transcripción de prueba", cliente=cliente)

    assert "```" not in resultado


def test_generar_descripcion_calls_verifier_when_resultado_esperado_present(monkeypatch):
    """End-to-end wiring: the SAME cliente is reused for the verifier call."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    texto = (
        f"## Módulo afectado\nRiesgos\n\n## Descripción del error\nAlgo pasó.\n\n"
        f"{ENCABEZADO_RESULTADO}\nEsperaba ver el ticket #4521 cerrado y obtuvo un error 500.\n"
    )
    cliente = FakeAnthropic(respuesta=texto, fundamentado=True)

    resultado = generar_descripcion("transcripción de prueba", cliente=cliente)

    assert len(cliente.messages.calls) == 2
    llamada_verificador = cliente.messages.calls[1]
    assert llamada_verificador["system"] == VERIFICADOR_RESULTADO_ESPERADO
    assert llamada_verificador["messages"][-1] == {"role": "assistant", "content": "{"}
    assert "#4521" in resultado


def test_generar_descripcion_no_verifier_call_when_no_resultado_section(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    texto = "## Módulo afectado\nRiesgos\n\n## Descripción del error\nAlgo pasó.\n"
    cliente = FakeAnthropic(respuesta=texto)

    generar_descripcion("transcripción de prueba", cliente=cliente)

    assert len(cliente.messages.calls) == 1


# --- Post-processor: postprocesar_descripcion --------------------------------


def test_postprocesar_verifier_says_grounded_keeps_text():
    texto = (
        "## Módulo afectado\nRiesgos\n\n"
        "## Descripción del error\nAlgo pasó.\n\n"
        f"{ENCABEZADO_RESULTADO}\nEsperaba ver el ticket #4521 cerrado y obtuvo un error 500.\n"
    )
    cliente = FakeAnthropic(fundamentado=True)

    assert postprocesar_descripcion(texto, "transcripción", cliente) == texto


def test_postprocesar_verifier_says_not_grounded_replaces_with_notice():
    texto = (
        "## Módulo afectado\nRiesgos\n\n"
        "## Descripción del error\nAlgo pasó.\n\n"
        f"{ENCABEZADO_RESULTADO}\nSe esperaba que funcionara correctamente.\n"
    )
    cliente = FakeAnthropic(fundamentado=False)

    resultado = postprocesar_descripcion(texto, "transcripción", cliente)

    assert ENCABEZADO_RESULTADO in resultado
    assert AVISO_RESULTADO_NO_CONFIABLE in resultado
    assert "funcionara correctamente" not in resultado


def test_postprocesar_verifier_exception_defaults_to_keeping_text():
    """A broken verifier must never erase real analyst-provided content."""
    texto = (
        "## Módulo afectado\nRiesgos\n\n"
        "## Descripción del error\nAlgo pasó.\n\n"
        f"{ENCABEZADO_RESULTADO}\nEsperaba ver el reporte exportado en PDF.\n"
    )

    class MessagesRotas:
        def create(self, **kwargs):
            raise RuntimeError("fallo de red simulado")

    class ClienteRoto:
        def __init__(self):
            self.messages = MessagesRotas()

    resultado = postprocesar_descripcion(texto, "transcripción", ClienteRoto())

    assert resultado == texto


def test_postprocesar_verifier_malformed_json_defaults_to_keeping_text():
    texto = (
        "## Módulo afectado\nRiesgos\n\n"
        "## Descripción del error\nAlgo pasó.\n\n"
        f"{ENCABEZADO_RESULTADO}\nEsperaba ver el reporte exportado en PDF.\n"
    )

    class MessagesRespuestaInvalida:
        def create(self, **kwargs):
            return FakeMensaje("esto no es json")

    class ClienteRespuestaInvalida:
        def __init__(self):
            self.messages = MessagesRespuestaInvalida()

    resultado = postprocesar_descripcion(texto, "transcripción", ClienteRespuestaInvalida())

    assert resultado == texto


def test_postprocesar_absent_section_is_a_no_op_and_skips_verifier():
    texto = "## Módulo afectado\nRiesgos\n\n## Descripción del error\nAlgo pasó.\n"
    cliente = FakeAnthropic()

    assert postprocesar_descripcion(texto, "transcripción", cliente) == texto
    assert cliente.messages.calls == []


# --- Post-processor: módulo-afectado verifier (only when contexto is non-empty) --


def test_postprocesar_modulo_verifier_skipped_when_no_contexto():
    """Real bug this guards against: the model invented 'Edición masiva de
    documentos' instead of the analyst's own 'listado único de documentos'.
    Without contexto (rule 6's only source is the transcript itself), the
    verifier must not run at all — zero extra calls, same as before this
    guardrail existed."""
    texto = "## Módulo afectado\nEdición masiva de documentos\n\n## Descripción del error\nAlgo pasó.\n"
    cliente = FakeAnthropic()

    resultado = postprocesar_descripcion(texto, "transcripción", cliente, contexto="")

    assert resultado == texto
    assert cliente.messages.calls == []


def test_postprocesar_modulo_verifier_says_literal_keeps_text():
    texto = "## Módulo afectado\nListado único de documentos\n\n## Descripción del error\nAlgo pasó.\n"
    cliente = FakeAnthropic(modulo_fundamentado=True)

    resultado = postprocesar_descripcion(
        texto, "transcripción", cliente, contexto="doc de Listado único de documentos"
    )

    assert resultado == texto
    assert len(cliente.messages.calls) == 1
    assert cliente.messages.calls[0]["system"] == VERIFICADOR_MODULO_AFECTADO


def test_postprocesar_modulo_verifier_accepts_grounded_submodulo_not_verbatim():
    """Regression: a real bug. 'Gestión documental > Registro de documento'
    is legitimately grounded — 'Gestión documental' is verbatim from the
    transcript, 'Registro de documento' is a fair derivation from the
    retrieved doc's actual subject (gst_documental/reg_insertar.php) — but
    it's NOT a verbatim substring of either source. An earlier version of
    this verifier asked "is this a literal quote?" and wrongly rejected it,
    replacing a correct answer with 'no identificado'. The verifier must
    ask "is this grounded?", not "is this literal?"."""
    texto = "## Módulo afectado\nGestión documental > Registro de documento\n\n## Descripción del error\nAlgo pasó.\n"
    cliente = FakeAnthropic(modulo_fundamentado=True)

    resultado = postprocesar_descripcion(
        texto,
        "En el módulo de gestión documental un cliente reporta un problema.",
        cliente,
        contexto="Documentación de gst_documental/reg_insertar.php: formulario de registro de un documento.",
    )

    assert resultado == texto
    assert "no identificado" not in resultado


def test_postprocesar_modulo_verifier_says_invented_replaces_with_no_identificado():
    texto = "## Módulo afectado\nEdición masiva de documentos\n\n## Descripción del error\nAlgo pasó.\n"
    cliente = FakeAnthropic(modulo_fundamentado=False)

    resultado = postprocesar_descripcion(
        texto,
        "El analista habló del listado único de documentos.",
        cliente,
        contexto="doc de Listado único de documentos",
    )

    assert MODULO_NO_IDENTIFICADO in resultado
    assert "Edición masiva de documentos" not in resultado
    assert "## Descripción del error" in resultado  # rest of the ticket untouched


def test_postprocesar_modulo_verifier_skipped_when_already_no_identificado():
    texto = f"## Módulo afectado\n{MODULO_NO_IDENTIFICADO}\n\n## Descripción del error\nAlgo pasó.\n"
    cliente = FakeAnthropic()

    resultado = postprocesar_descripcion(texto, "transcripción", cliente, contexto="algún contexto")

    assert resultado == texto
    assert cliente.messages.calls == []


def test_postprocesar_modulo_verifier_exception_defaults_to_keeping_text():
    texto = "## Módulo afectado\nListado único de documentos\n\n## Descripción del error\nAlgo pasó.\n"

    class MessagesRotas:
        def create(self, **kwargs):
            raise RuntimeError("fallo de red simulado")

    class ClienteRoto:
        def __init__(self):
            self.messages = MessagesRotas()

    resultado = postprocesar_descripcion(texto, "transcripción", ClienteRoto(), contexto="algún contexto")

    assert resultado == texto


def test_generar_descripcion_calls_modulo_verifier_when_context_used(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    texto = "## Módulo afectado\nListado único de documentos\n\n## Descripción del error\nAlgo pasó.\n"
    cliente = FakeAnthropic(respuesta=texto, modulo_fundamentado=True)

    resultado = generar_descripcion(
        "transcripción de prueba",
        cliente=cliente,
        proveedor_contexto=lambda t: "doc de Listado único de documentos",
    )

    assert resultado == texto.strip()  # _texto_de() strips the raw response first
    # 1 generation call + 1 módulo-afectado verifier call.
    assert len(cliente.messages.calls) == 2
    assert cliente.messages.calls[1]["system"] == VERIFICADOR_MODULO_AFECTADO


def test_postprocesar_empty_body_becomes_notice_without_calling_verifier():
    texto = f"## Módulo afectado\nRiesgos\n\n## Descripción del error\nAlgo pasó.\n\n{ENCABEZADO_RESULTADO}\n\n"
    cliente = FakeAnthropic()

    resultado = postprocesar_descripcion(texto, "transcripción", cliente)

    assert AVISO_RESULTADO_NO_CONFIABLE in resultado
    assert cliente.messages.calls == []


def test_postprocesar_strips_wrapping_fence_keeps_inner_fence():
    texto = (
        "```markdown\n"
        "## Módulo afectado\nRiesgos\n\n"
        "## Descripción del error\nUsó `comando --flag` y falló.\n"
        "```"
    )
    cliente = FakeAnthropic()

    resultado = postprocesar_descripcion(texto, "transcripción", cliente)

    assert not resultado.startswith("```")
    assert not resultado.endswith("```")
    assert "`comando --flag`" in resultado
    assert cliente.messages.calls == []


def test_postprocesar_non_string_content_tolerates_none():
    assert postprocesar_descripcion(None, "transcripción", FakeAnthropic()) == ""


def test_postprocesar_blank_string_passthrough():
    assert postprocesar_descripcion("   ", "transcripción", FakeAnthropic()) == "   "


def test_fake_anthropic_canned_response_round_trips_unchanged():
    """The default FakeAnthropic canned text has no fence and no Resultado
    heading, so postprocesar_descripcion must no-op — every Fase 1/2
    assertion built on the literal canned string keeps holding."""
    cliente = FakeAnthropic()
    assert postprocesar_descripcion("Descripción generada de prueba", "transcripción", cliente) == (
        "Descripción generada de prueba"
    )


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
