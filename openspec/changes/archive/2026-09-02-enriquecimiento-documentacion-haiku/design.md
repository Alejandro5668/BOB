# Design: Haiku-Enriched Documentation Context

## Technical Approach

Exploration's Approach 1. A new module `contexto_enriquecido.py` owns the Anthropic
client, the content-addressed cache, the Anthropic-specific 429 retry wrapper, and an
order-preserving `ThreadPoolExecutor` fan-out. `contexto_memoria.py::buscar_contexto()`
changes only at the block-building loop (current lines 335-341): it now collects
`(ruta, contenido)` pairs and passes them through one injectable `enriquecedor` seam that
returns one block per input document, same length and order. `_ensamblar_contexto()`,
`listar_documentos()`, `elegir_documentos_relevantes()`, `generar_descripcion.py` and
`consultar_documentacion.py` are untouched.

## Architecture Decisions

| # | Decision | Choice | Rejected alternative | Rationale |
|---|---|---|---|---|
| 1 | Module boundary | New `contexto_enriquecido.py` | Functions inside `contexto_memoria.py` | Keeps the two SDKs' client/retry logic apart; `contexto_memoria.py`'s docstring scopes it to schema-free retrieval; avoids bloating the largest test file |
| 2 | Config-error type | Local `ErrorConfiguracionAnthropic` | Reuse `generar_descripcion.ErrorConfiguracion` | That type is documented as `GROQ_API_KEY`-specific and is **fatal** at the generation call site. A missing Anthropic key is **non-fatal**. A shared type risks an upstream `except ErrorConfiguracion` conflating "blocked" with "degrade" |
| 3 | Retry wrapper | Separate `_crear_mensaje_con_reintento()` | Reuse `generar_descripcion._crear_completion_con_reintento` | Call surface is `cliente.messages.create(**kwargs)`, not `chat.completions.create`. `.status_code == 429` check is identical (verified live, SDK 1.3.0) but the method is not |
| 4 | Backoff delay | Fixed `5.0s` | Parse a delay from the message text | Groq's `"try again in Xs"` regex has no Anthropic equivalent; a `retry-after` header read was not live-verified, so it is deliberately not relied on |
| 5 | Concurrency result collection | Preallocated `resultados` list indexed by position; futures held in an index-keyed dict | `as_completed()` | `_ensamblar_contexto` gives earlier blocks budget priority — order must be structurally guaranteed, not incidental |
| 6 | Cache write timing | Main thread, after the pool closes | Inside each worker | One writer, no concurrent `mkdir`/rename races, and an `OSError` cannot kill a worker mid-flight |
| 7 | Cache write mode | tmp file + `Path.replace()` | Direct `write_text` | `os.replace` is atomic on POSIX and Windows; a reader in another process never sees a half-written summary |
| 8 | Cache key | `sha256(contenido)` only | Include prompt text / model id | Confirmed decision: content-only key. Manual wipe of `cache/documentacion/` if the prompt or model changes — recorded in the module docstring |
| 9 | Enrichment replaces raw | Summary substitutes the block | Append summary to raw | Confirmed decision; appending would defeat the token-budget goal |
| 10 | Prompt location | `prompts.py` constants | Literal in `contexto_enriquecido.py` | CLAUDE.md "Prompt repository convention" is mandatory |
| 11 | Pre-warm script | **Deferred — not in this change** | Ship it now | See "Deferred" below |
| 12 | Test seam | Explicit `enriquecedor=` kwarg on `buscar_contexto` | Rely on `ANTHROPIC_API_KEY` being unset in CI | An unset key makes the test pass by accident; on a dev machine with the key set the same test would hit the network |

## Data Flow

    buscar_contexto(transcripcion)
      │
      ├─ listar_documentos()            (preview listing — NEVER enriched)
      ├─ elegir_documentos_relevantes() (Groq gpt-oss-20b, <= 3 paths)
      ├─ read_text() per path ──→ [(ruta, contenido_raw), ...]   order = selection order
      │
      └─ enriquecer_documentos(pares)              contexto_enriquecido.py
             │
             ├─ sha256(contenido) per doc
             ├─ cache/documentacion/<hash>.txt  ──HIT──→ resultados[i] = cached
             │                                   MISS─┐
             │                                        ▼
             │                          ThreadPoolExecutor(max_workers=3)
             │                          Haiku messages.create (429 retry x3)
             │                                        │
             │        futuros[i].result() ────OK──────┤──→ resultados[i] = resumen
             │                                        │        └─ write cache (main thread)
             │                            any Exception├──→ resultados[i] stays raw
             ▼
        list[str], len == len(pares), same order
             │
      └─ _ensamblar_contexto(bloques, 6000)  (unchanged)

## File Changes

| File | Action | Description |
|---|---|---|
| `contexto_enriquecido.py` | Create | Client, cache I/O, retry wrapper, concurrent fan-out, public `enriquecer_documentos` |
| `contexto_memoria.py` | Modify | `Enriquecedor` alias, `enriquecedor=` kwarg, block-building loop replaced |
| `prompts.py` | Modify | `ENRIQUECEDOR_DOCUMENTACION` + `ENTRADA_ENRIQUECEDOR_DOCUMENTACION` |
| `requirements.txt` | Modify | `anthropic>=1.3` |
| `Dockerfile` | Modify | Add module to the explicit `COPY` list |
| `docker-compose.yml` | Modify | `./cache/documentacion:/app/cache/documentacion` volume |
| `.gitignore` | Modify | `cache/` |
| `.dockerignore` | Modify | `cache/` (build-context hygiene) |
| `.env.example` | Modify (**MANUAL**) | `ANTHROPIC_API_KEY=` — automated edits to this path were blocked in Fase 1, 2 and 4 |
| `tests/test_contexto_enriquecido.py` | Create | `FakeAnthropic` double, cache hit/miss, fallback, order |
| `tests/test_contexto_memoria.py` | Modify | Verbatim test becomes an enriched test; new fallback tests |

## Interfaces / Contracts

### `contexto_enriquecido.py` (complete)

```python
"""Haiku-based functional enrichment of the finally-selected documentation.

Turns each raw `.md` (written for developers) into a short functional
summary for the analyst-facing prompts, cached by SHA-256 of the raw
content at `cache/documentacion/<hash>.txt`.

TOTAL by contract: `enriquecer_documentos` never raises and always returns
one block per input document, in the input order. Any failure (missing
`ANTHROPIC_API_KEY`, API error, empty response, cache I/O error) degrades
that one document to its verbatim raw content.

CACHE KEY IS CONTENT-ONLY: it does NOT include the prompt text or the model
id. If `ENRIQUECEDOR_DOCUMENTACION` or `MODELO_ENRIQUECEDOR` changes, wipe
`cache/documentacion/` by hand or stale summaries will be served forever.

Prompt text lives in `prompts.py` (see CLAUDE.md "Prompt repository
convention"). Never imports Streamlit.
"""

from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from prompts import ENRIQUECEDOR_DOCUMENTACION, ENTRADA_ENRIQUECEDOR_DOCUMENTACION

logger = logging.getLogger(__name__)

MODELO_ENRIQUECEDOR = "claude-haiku-4-5-20251001"
MAX_TOKENS_ENRIQUECIMIENTO = 700
MAX_TRABAJADORES = 3
MAX_REINTENTOS_RATE_LIMIT = 3
# Anthropic's error text has no Groq-style "try again in Xs" to parse, and
# the `retry-after` header was not live-verified — fixed backoff on purpose.
ESPERA_RATE_LIMIT = 5.0
DIRECTORIO_CACHE_POR_DEFECTO = "./cache/documentacion"


class ErrorConfiguracionAnthropic(RuntimeError):
    """ANTHROPIC_API_KEY absent/blank. Non-fatal: callers degrade to raw content.

    Deliberately NOT `generar_descripcion.ErrorConfiguracion`, which is
    documented as GROQ-specific and IS fatal at its call site.
    """


class ErrorEnriquecimiento(RuntimeError):
    """Haiku answered, but with nothing usable."""


# --- Client ---------------------------------------------------------------


def _crear_cliente():
    """Build the Anthropic client, failing fast if the key is not set.

    Mirrors `generar_descripcion._crear_cliente`: env-only, no network call
    before the check, never logs the key value.
    """
    clave = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not clave:
        raise ErrorConfiguracionAnthropic(
            "ANTHROPIC_API_KEY no está configurada; la documentación se usará sin enriquecer."
        )

    from anthropic import Anthropic

    return Anthropic(api_key=clave)


def _crear_mensaje_con_reintento(cliente, **kwargs):
    """`cliente.messages.create(**kwargs)` with 429 retry.

    Same `status_code == 429` shape as the Groq wrapper (verified live,
    anthropic 1.3.0) but a different call surface, so it is a separate
    function rather than a generic one spanning both SDKs.
    """
    intentos = 0
    while True:
        try:
            return cliente.messages.create(**kwargs)
        except Exception as exc:
            es_rate_limit = getattr(exc, "status_code", None) == 429
            intentos += 1
            if not es_rate_limit or intentos > MAX_REINTENTOS_RATE_LIMIT:
                raise
            logger.warning(
                "Rate limit de Anthropic alcanzado, reintentando en %.1fs (intento %d/%d)",
                ESPERA_RATE_LIMIT, intentos, MAX_REINTENTOS_RATE_LIMIT,
            )
            time.sleep(ESPERA_RATE_LIMIT)


# --- Content-addressed cache ----------------------------------------------


def resolver_directorio_cache(directorio: Optional[str] = None) -> Path:
    """Explicit arg > `CACHE_DOCUMENTACION_DIR` env var > `./cache/documentacion`.

    Mirrors `contexto_memoria.resolver_directorio`. The env var is optional;
    it is not required in `.env`.
    """
    valor = (
        directorio
        if directorio is not None
        else os.environ.get("CACHE_DOCUMENTACION_DIR", "").strip()
    )
    if not valor:
        valor = DIRECTORIO_CACHE_POR_DEFECTO
    return Path(valor)


def _hash_contenido(contenido: str) -> str:
    return hashlib.sha256(contenido.encode("utf-8")).hexdigest()


def _leer_cache(raiz: Path, clave: str) -> Optional[str]:
    """Cached summary, or None (miss / unreadable / empty). Never raises."""
    try:
        ruta = raiz / f"{clave}.txt"
        if not ruta.is_file():
            return None
        texto = ruta.read_text(encoding="utf-8")
    except OSError:
        return None
    return texto or None


def _escribir_cache(raiz: Path, clave: str, resumen: str) -> None:
    """Atomic tmp+replace write. Never raises: an unwritable cache only
    means the next request re-enriches."""
    try:
        raiz.mkdir(parents=True, exist_ok=True)
        temporal = raiz / f"{clave}.{os.getpid()}-{threading.get_ident()}.tmp"
        temporal.write_text(resumen, encoding="utf-8")
        temporal.replace(raiz / f"{clave}.txt")
    except OSError as exc:
        logger.warning(
            "No se pudo escribir la caché de enriquecimiento (%s): %s: %s",
            raiz, type(exc).__name__, exc,
        )


# --- Single-document enrichment -------------------------------------------


def _enriquecer_uno(cliente, ruta: str, contenido: str) -> str:
    """One Haiku call. Raises on failure; the caller maps that to raw fallback."""
    respuesta = _crear_mensaje_con_reintento(
        cliente,
        model=MODELO_ENRIQUECEDOR,
        max_tokens=MAX_TOKENS_ENRIQUECIMIENTO,
        temperature=0.0,
        system=ENRIQUECEDOR_DOCUMENTACION,
        messages=[
            {
                "role": "user",
                "content": ENTRADA_ENRIQUECEDOR_DOCUMENTACION.format(
                    ruta=ruta, contenido=contenido
                ),
            }
        ],
    )
    # Anthropic returns a list of content blocks, NOT Groq's
    # `choices[0].message.content` — this is the shape FakeAnthropic must mimic.
    texto = "".join(
        bloque.text for bloque in respuesta.content if getattr(bloque, "type", None) == "text"
    ).strip()
    if not texto:
        raise ErrorEnriquecimiento(f"Respuesta vacía de Haiku para {ruta}")
    return texto


# --- Public: total, order-preserving --------------------------------------


def enriquecer_documentos(
    documentos: list[tuple[str, str]],
    *,
    cliente=None,
    directorio_cache: Optional[str] = None,
) -> list[str]:
    """Return one block per `(ruta, contenido_raw)` pair, same length and order.

    Enriched summary when available, verbatim raw content otherwise. Never
    raises. Only cache misses reach the thread pool; hits are a plain file
    read. Results are placed by index — `as_completed` is deliberately not
    used, because `_ensamblar_contexto` gives earlier blocks budget priority.
    """
    if not documentos:
        return []

    resultados: list[str] = [contenido for _, contenido in documentos]  # raw fallback preloaded
    raiz = resolver_directorio_cache(directorio_cache)
    claves = [_hash_contenido(contenido) for _, contenido in documentos]

    pendientes: list[int] = []
    for i, clave in enumerate(claves):
        en_cache = _leer_cache(raiz, clave)
        if en_cache is not None:
            resultados[i] = en_cache
        else:
            pendientes.append(i)

    if not pendientes:
        return resultados

    if cliente is None:
        try:
            cliente = _crear_cliente()
        except Exception as exc:
            logger.warning(
                "Enriquecimiento omitido, se usa documentación cruda: %s: %s",
                type(exc).__name__, exc,
            )
            return resultados

    with ThreadPoolExecutor(max_workers=min(MAX_TRABAJADORES, len(pendientes))) as pool:
        futuros = {
            i: pool.submit(_enriquecer_uno, cliente, documentos[i][0], documentos[i][1])
            for i in pendientes
        }

    for i, futuro in futuros.items():  # dict order == selection order
        try:
            resumen = futuro.result()
        except Exception as exc:
            logger.warning(
                "Enriquecimiento falló para %s, se usa contenido crudo: %s: %s",
                documentos[i][0], type(exc).__name__, exc,
            )
            continue
        resultados[i] = resumen
        _escribir_cache(raiz, claves[i], resumen)

    return resultados
```

### `contexto_memoria.py` — exact edit

Add next to `ProveedorContexto` (line 44):

```python
Enriquecedor = Callable[[list[tuple[str, str]]], list[str]]
```

Replace the signature (lines 312-314) and the block-building loop (lines 335-346):

```python
def buscar_contexto(
    transcripcion: str,
    *,
    directorio: Optional[str] = None,
    cliente=None,
    enriquecedor: Optional[Enriquecedor] = None,
) -> str:
```

```python
        raiz = resolver_directorio(directorio)
        pares: list[tuple[str, str]] = []
        for ruta_relativa in seleccionados:
            try:
                contenido = (raiz / ruta_relativa).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            pares.append((ruta_relativa, contenido))

        if not pares:
            return ""

        if enriquecedor is None:
            from contexto_enriquecido import enriquecer_documentos as enriquecedor

        # Defense in depth: `enriquecer_documentos` is total by contract, but a
        # broken/injected enricher must degrade to raw blocks, never to "".
        try:
            bloques = enriquecedor(pares)
            if len(bloques) != len(pares):
                raise ValueError(
                    f"El enriquecedor devolvió {len(bloques)} bloques para {len(pares)} documentos"
                )
        except Exception as exc:
            logger.warning(
                "Enriquecimiento no utilizable, se usa documentación cruda: %s: %s",
                type(exc).__name__, exc,
            )
            bloques = [contenido for _, contenido in pares]

        return _ensamblar_contexto(bloques, PRESUPUESTO_CARACTERES)
```

`from X import y as enriquecedor` rebinding a parameter inside the function is the exact
pattern `generar_descripcion.generar_descripcion` already uses for `proveedor_contexto`.

Also update the module docstring: it currently promises only `is_dir`/`is_file`/`rglob`/
`resolve`/`read_text` against `MEMORY_DIR` (still true) — add that selected content is
passed to `contexto_enriquecido` before assembly.

### `prompts.py` — new constants (append after `ENTRADA_SELECTOR_DOCUMENTOS`)

```python
ENRIQUECEDOR_DOCUMENTACION = """Resumís documentación técnica interna para analistas que entienden el negocio pero no son programadores.

Explicá qué hace la funcionalidad o el módulo y para qué sirve: qué permite hacer, en qué casos se usa, y qué pasa cuando se usa. Dejá afuera el detalle de implementación (nombres de tablas, funciones, rutas de archivos, fragmentos de código) salvo que sea lo único que explique el comportamiento.

Escribí entre 4 y 8 líneas, en español, en texto corrido o viñetas simples. No inventes nada que no esté en el documento: si algo no está, no lo menciones. Devolvé solo el resumen, sin encabezados, preámbulos ni comentarios sobre el resumen."""
"""Prompt de sistema del enriquecedor (Claude Haiku, ver
`contexto_enriquecido.py`): convierte un .md de documentación técnica en un
resumen funcional breve antes de inyectarlo como contexto."""

ENTRADA_ENRIQUECEDOR_DOCUMENTACION = """Documento: {ruta}
---
{contenido}
---
Resumen funcional:"""
"""Mensaje de usuario para ENRIQUECEDOR_DOCUMENTACION: ruta relativa del
documento + su contenido crudo."""
```

### Infrastructure diffs (exact)

```diff
--- requirements.txt
 streamlit>=1.40
 elevenlabs>=2.0
 groq>=0.11
+anthropic>=1.3
 python-dotenv
 pytest
```
(1.3.0 is the version verified live for the `RateLimitError.status_code == 429` shape.)

```diff
--- Dockerfile
-COPY app.py transcribir.py generar_descripcion.py contexto_memoria.py consultar_documentacion.py prompts.py logging_config.py ./
+COPY app.py transcribir.py generar_descripcion.py contexto_memoria.py contexto_enriquecido.py consultar_documentacion.py prompts.py logging_config.py ./
```

```diff
--- docker-compose.yml
     volumes:
       - ./logs:/app/logs
+      - ./cache/documentacion:/app/cache/documentacion
```

```diff
--- .gitignore
 *.wav
 logs/
+cache/
 docker-compose.override.yml
```

```diff
--- .dockerignore
 *.wav
+cache/
 *.mp3
```

### `.env.example` — MANUAL TASK (do not attempt an automated edit)

Automated edits to this path were blocked in Fase 1, Fase 2 and Fase 4. Exact line for
the operator to append:

```
ANTHROPIC_API_KEY=
```

Optional, only if the cache should not live at `./cache/documentacion`:

```
CACHE_DOCUMENTACION_DIR=
```

Leaving `ANTHROPIC_API_KEY` blank is a supported state: every document falls back to raw
content and the app behaves exactly as before this change.

## Testing Strategy

| Layer | What to test | Approach |
|---|---|---|
| Unit — `contexto_enriquecido` | Cache hit performs zero API calls; changed content = new hash = fresh call; hash is `sha256` of the raw bytes | `tmp_path` cache dir via `directorio_cache=`, `FakeAnthropic` counting calls |
| Unit — `contexto_enriquecido` | Missing key returns raw and never raises; per-document API error degrades only that block; empty Haiku response degrades; unwritable cache dir still returns the summary | `monkeypatch.delenv`, `FakeAnthropicSecuencia` raising on the 2nd doc |
| Unit — `contexto_enriquecido` | Order preserved when a later document completes first | `FakeAnthropic` that `time.sleep`s longer for index 0 |
| Unit — `contexto_memoria` | Enriched summary reaches `_ensamblar_contexto`; enricher failure and length mismatch fall back to raw; the preview listing is never enriched | Injected `enriquecedor=` lambda; assert `FakeAnthropic` never constructed |
| Integration | `buscar_contexto` end to end with fake Groq + fake Anthropic | Existing `_crear_arbol` tmp trees |
| Manual smoke | Real key, real corpus: first request populates `cache/documentacion/`, second makes zero Anthropic calls; `docker compose up` keeps the cache across recreation | Documented in tasks |

### `FakeAnthropic` double (shape differs from `FakeGroq`)

```python
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
```

### `tests/test_contexto_memoria.py` — exact required change

`test_buscar_contexto_returns_selected_file_content_verbatim` (lines 337-346) asserts raw
passthrough, which is no longer the behavior. Replace it with the two tests below. Do NOT
"fix" it by relying on `ANTHROPIC_API_KEY` being unset — that would pass by accident in CI
and hit the real network on a developer machine that has the key.

```python
def test_buscar_contexto_uses_enriched_summary_instead_of_raw_content(tmp_path):
    raiz = _crear_arbol(
        tmp_path / "memory",
        {"riesgos/index.md": "Documentación real de riesgos.", "otro.md": "irrelevante"},
    )
    cliente = FakeGroq(archivos_elegidos=["riesgos/index.md"])
    recibidos = []

    def enriquecedor(pares):
        recibidos.extend(pares)
        return [f"RESUMEN de {ruta}" for ruta, _ in pares]

    contexto = cm.buscar_contexto(
        "transcripción", directorio=str(raiz), cliente=cliente, enriquecedor=enriquecedor
    )

    assert contexto == "RESUMEN de riesgos/index.md"
    # The enricher receives (ruta_relativa, contenido_crudo) pairs in selection order.
    assert recibidos == [("riesgos/index.md", "Documentación real de riesgos.")]


def test_buscar_contexto_falls_back_to_raw_content_when_enricher_fails(tmp_path):
    raiz = _crear_arbol(tmp_path / "memory", {"riesgos/index.md": "Documentación real de riesgos."})
    cliente = FakeGroq(archivos_elegidos=["riesgos/index.md"])

    def enriquecedor(pares):
        raise RuntimeError("fallo simulado de enriquecimiento")

    contexto = cm.buscar_contexto(
        "transcripción", directorio=str(raiz), cliente=cliente, enriquecedor=enriquecedor
    )

    assert contexto == "Documentación real de riesgos."  # degrades to raw, never to ""
```

Add a third test asserting the length-mismatch guard (`enriquecedor=lambda pares: []`
→ raw content, not `""`). Every other `buscar_contexto` test in the file returns `""`
before the block-building stage and needs no change. As a belt-and-braces guard against a
future test reaching the network, add to `tests/test_contexto_memoria.py` (no `conftest.py`
exists in this repo):

```python
@pytest.fixture(autouse=True)
def _sin_clave_anthropic(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
```

## Deferred: corpus pre-warm script

**Explicitly deferred — do NOT include it in this change.** The cache is self-warming: the
first real request over a document enriches and caches it. A pre-warm script would enrich
the whole corpus (273 files in the real Kawak docs) when Groq only ever selects at most 3
per request, so it would pay for hundreds of summaries that may never be read, and it needs
its own CLI entry point, cost forecast, and failure semantics. Revisit only if measured
first-request latency on cache misses turns out to be a real complaint.

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or
process-integration boundary. The only new filesystem writes are inside
`cache/documentacion/`, with filenames derived from a hex SHA-256 digest (`[0-9a-f]{64}`),
so no attacker-influenced path component can traverse out of that directory.

## Migration / Rollout

No migration. Additive, revertible as one PR. `cache/documentacion/` is disposable —
deleting it only forces re-enrichment. Kill switch without a revert: unset
`ANTHROPIC_API_KEY`, and every document falls back to raw content.

## Open Questions

- [ ] `MAX_TOKENS_ENRIQUECIMIENTO = 700` is an estimate for a 4-8 line Spanish summary; a
      truncated summary is still cached as-is. Confirm during the manual smoke test and
      raise the value if real summaries hit the cap.
- [ ] Whether `anthropic>=1.3` should be pinned exactly. Following the existing
      `groq>=0.11` / `streamlit>=1.40` convention for now.
