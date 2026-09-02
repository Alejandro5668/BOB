"""Unit tests for cliente_anthropic.py — shared client construction, 429
retry, and the JSON-mode replacement helper (`_pedir_json`) used by every
LLM call site in this project. No real network call is ever made here.
"""

from pathlib import Path

import pytest

import cliente_anthropic as ca


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


@pytest.fixture(autouse=True)
def _sin_clave_anthropic(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


# --- _crear_cliente: fail-fast ----------------------------------------------


def test_missing_key_raises_error_configuracion():
    with pytest.raises(ca.ErrorConfiguracion):
        ca._crear_cliente()


def test_blank_key_raises_error_configuracion(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "   ")
    with pytest.raises(ca.ErrorConfiguracion):
        ca._crear_cliente()


def test_crear_cliente_passes_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "clave-de-prueba")
    capturado = {}

    class FakeAnthropicSDK:
        def __init__(self, api_key):
            capturado["api_key"] = api_key

    import anthropic

    monkeypatch.setattr(anthropic, "Anthropic", FakeAnthropicSDK)

    ca._crear_cliente()

    assert capturado["api_key"] == "clave-de-prueba"


# --- _texto_de ---------------------------------------------------------------


def test_texto_de_joins_text_blocks():
    respuesta = FakeMensaje("hola mundo")
    assert ca._texto_de(respuesta) == "hola mundo"


def test_texto_de_ignores_non_text_blocks():
    class FakeBloqueOtro:
        type = "tool_use"

    class FakeRespuestaMixta:
        content = [FakeBloqueOtro(), FakeBloqueTexto("texto real")]

    assert ca._texto_de(FakeRespuestaMixta()) == "texto real"


# --- _crear_mensaje_con_reintento: rate-limit retry --------------------------


class ErrorRateLimitFalso(RuntimeError):
    def __init__(self, mensaje):
        super().__init__(mensaje)
        self.status_code = 429


class ErrorNoRateLimitFalso(RuntimeError):
    def __init__(self, mensaje):
        super().__init__(mensaje)
        self.status_code = 400


def test_reintento_no_op_on_success():
    cliente = FakeAnthropic(resumen="ok")
    resultado = ca._crear_mensaje_con_reintento(cliente, model=ca.MODELO_HAIKU, messages=[])
    assert ca._texto_de(resultado) == "ok"
    assert len(cliente.messages.calls) == 1


def test_reintento_retries_on_rate_limit_then_succeeds(monkeypatch):
    esperas = []
    monkeypatch.setattr("cliente_anthropic.time.sleep", lambda s: esperas.append(s))

    intentos = {"n": 0}

    class MessagesFallaUnaVez:
        def __init__(self):
            self.calls = []

        def create(self, **kwargs):
            self.calls.append(kwargs)
            intentos["n"] += 1
            if intentos["n"] == 1:
                raise ErrorRateLimitFalso("rate limited")
            return FakeMensaje("ok")

    class ClienteFallaUnaVez:
        def __init__(self):
            self.messages = MessagesFallaUnaVez()

    resultado = ca._crear_mensaje_con_reintento(ClienteFallaUnaVez(), model=ca.MODELO_HAIKU, messages=[])

    assert ca._texto_de(resultado) == "ok"
    assert intentos["n"] == 2
    assert esperas == [ca.ESPERA_RATE_LIMIT]


def test_reintento_gives_up_after_max_attempts(monkeypatch):
    monkeypatch.setattr("cliente_anthropic.time.sleep", lambda s: None)
    llamadas = []

    class MessagesSiempreFalla:
        def create(self, **kwargs):
            llamadas.append(kwargs)
            raise ErrorRateLimitFalso("rate limited")

    class ClienteSiempreFalla:
        def __init__(self):
            self.messages = MessagesSiempreFalla()

    with pytest.raises(ErrorRateLimitFalso):
        ca._crear_mensaje_con_reintento(ClienteSiempreFalla(), model=ca.MODELO_HAIKU, messages=[])

    assert len(llamadas) == ca.MAX_REINTENTOS_RATE_LIMIT + 1


def test_reintento_does_not_retry_non_rate_limit_errors(monkeypatch):
    llamado = []
    monkeypatch.setattr("cliente_anthropic.time.sleep", lambda s: llamado.append(s))

    class MessagesFallaFuerte:
        def create(self, **kwargs):
            raise ErrorNoRateLimitFalso("clave inválida")

    class ClienteFallaFuerte:
        def __init__(self):
            self.messages = MessagesFallaFuerte()

    with pytest.raises(ErrorNoRateLimitFalso):
        ca._crear_mensaje_con_reintento(ClienteFallaFuerte(), model=ca.MODELO_HAIKU, messages=[])

    assert llamado == []


# --- _pedir_json: assistant-prefill JSON mode --------------------------------


def test_pedir_json_parses_prefilled_response():
    cliente = FakeAnthropic(resumen='"archivos": ["doc.md"]}')

    datos = ca._pedir_json(
        cliente, model=ca.MODELO_HAIKU, system="sistema", mensaje_usuario="usuario", max_tokens=100
    )

    assert datos == {"archivos": ["doc.md"]}
    kwargs = cliente.messages.calls[0]
    assert kwargs["messages"][-1] == {"role": "assistant", "content": "{"}
    assert kwargs["messages"][0] == {"role": "user", "content": "usuario"}
    assert kwargs["system"] == "sistema"
    assert kwargs["temperature"] == 0.0


def test_pedir_json_tolerates_trailing_prose_after_the_object():
    cliente = FakeAnthropic(resumen='"fundamentado": true} Espero que esto ayude.')

    datos = ca._pedir_json(
        cliente, model=ca.MODELO_HAIKU, system="sistema", mensaje_usuario="usuario", max_tokens=100
    )

    assert datos == {"fundamentado": True}


def test_pedir_json_raises_on_malformed_json():
    cliente = FakeAnthropic(resumen="esto no es json")

    with pytest.raises(ValueError):
        ca._pedir_json(
            cliente, model=ca.MODELO_HAIKU, system="sistema", mensaje_usuario="usuario", max_tokens=100
        )


# --- Repository hygiene: Groq fully retired -----------------------------------


def test_no_module_or_test_imports_groq():
    raiz = Path(__file__).resolve().parent.parent
    archivo_actual = Path(__file__).resolve()
    patrones_prohibidos = ("import" + " groq", "from" + " groq")
    ofensores = []
    rutas = list(raiz.glob("*.py")) + list((raiz / "tests").glob("*.py"))
    for ruta in rutas:
        if ruta.resolve() == archivo_actual:
            continue  # this test file legitimately contains the search patterns as data
        texto = ruta.read_text(encoding="utf-8")
        if any(patron in texto for patron in patrones_prohibidos):
            ofensores.append(str(ruta))
    assert ofensores == []


def test_requirements_no_longer_lists_groq():
    raiz = Path(__file__).resolve().parent.parent
    texto = (raiz / "requirements.txt").read_text(encoding="utf-8")
    assert "groq" not in texto.lower()
