# Exploration: Haiku-enriched documentation caching layer for context retrieval

## Current State

`contexto_memoria.py::buscar_contexto()` (lines 312-353) is the total provider called from both `generar_descripcion.py::generar_descripcion()` and `consultar_documentacion.py::responder_consulta()`. Flow: `listar_documentos()` (cheap preview listing, unchanged) → `elegir_documentos_relevantes()` (Groq `gpt-oss-20b` picks up to `MAX_ARCHIVOS_SELECCIONADOS=3` paths, unchanged) → **raw `read_text()` per selected path** (lines 336-341, the exact insertion point) → `_ensamblar_contexto()` assembles within `PRESUPUESTO_CARACTERES=6000` budget (unchanged, budget logic is content-agnostic). The whole function degrades to `""` on any exception.

`generar_descripcion.py` owns the reusable Groq pattern: `_crear_cliente()` (lazy, fail-fast `ErrorConfiguracion` on missing `GROQ_API_KEY`) and `_crear_completion_con_reintento()` (retries on `getattr(exc, "status_code", None) == 429`, parsing Groq's `"try again in Xs"` text, 5.0s fallback). Both are imported lazily by `contexto_memoria.py` and `consultar_documentacion.py` — the project's established shared-helper convention.

Test pattern (`tests/test_contexto_memoria.py`): `FakeGroq`/`FakeGroqSecuencia` expose `.chat.completions.create(**kwargs)` returning `.choices[0].message.content`; `cliente` is always an injected keyword param resolved lazily. A `FakeAnthropic` double must follow the same shape.

No `.env.example` file exists in the repo as an editable-by-agent target; `openspec/changes/archive/2026-09-02-asistente-voz-fase4/design.md` documents that automated edits to it were **repeatedly blocked** across Fase 1, 2, and 4 — each time handled as an explicit manual task. `requirements.txt` has no `anthropic` yet. `Dockerfile` uses an explicit named `COPY` (never `COPY . .`). `docker-compose.yml` mounts only `./logs:/app/logs` today. `.gitignore` has no `cache/` entry.

## Affected Areas
- `contexto_memoria.py` — insertion point at lines 336-341 (block-building loop).
- New module `contexto_enriquecido.py` (recommended) — Anthropic client, cache I/O, concurrency fan-out.
- `requirements.txt` — add `anthropic`.
- `Dockerfile` — add new module to explicit `COPY` line.
- `docker-compose.yml` — add `./cache/documentacion:/app/cache/documentacion` volume, mirroring `logs/`.
- `.gitignore` — add `cache/`.
- `.env.example` — add `ANTHROPIC_API_KEY=`; **manual task** (confirmed recurring guardrail, not hypothetical).
- `tests/test_contexto_memoria.py` — existing verbatim-passthrough assertions (e.g. `test_buscar_contexto_returns_selected_file_content_verbatim`) will break once enrichment wires in; needs an injectable no-op seam or explicit update.
- `generar_descripcion.py` / `consultar_documentacion.py` — confirmed **no changes needed**, verified by reading call sites.

## Approaches

1. **New module `contexto_enriquecido.py`**, called lazily from `buscar_contexto()` — public interface e.g. `enriquecer_documentos(seleccionados: list[tuple[str,str]], *, cliente=None) -> list[str]`.
   - Pros: matches existing one-file-per-concern layout; isolates new SDK/env-var/retry shape; `contexto_memoria.py` already lazily imports Groq helpers from other modules inside functions, so this is consistent, not novel.
   - Cons: one more file to wire into Dockerfile's COPY list.
   - Effort: Medium.
2. **Add functions directly to `contexto_memoria.py`.**
   - Pros: fewer files.
   - Cons: contradicts the module's own docstring scope ("schema-free document retrieval"); mixes two unrelated SDKs' client/retry logic where the project has consistently kept Groq logic centralized; bloats the largest existing test file with an unrelated concern.
   - Effort: Low upfront, higher long-term cost.

**Recommendation: Approach 1.**

## Cache Design

Content-addressed via `hashlib.sha256(contenido_raw.encode("utf-8")).hexdigest()`; one plain-text file per hash under `cache/documentacion/<hash>.txt`; read/write both wrapped in try/except `OSError` degrading to "not cached" rather than failing; `cache_dir` resolution mirrors `resolver_directorio()` (explicit arg > env var > default).

## Concurrency Design

`ThreadPoolExecutor(max_workers=3)` for cache **misses only** (hits are checked before submission, no thread needed); results collected by index to preserve selection order, since `_ensamblar_contexto`'s truncation gives earlier blocks budget priority.

## Retry-Wrapper Question — Answered

Verified via web search: Anthropic's SDK raises `APIStatusError` subclasses with `.status_code`/`.response`; `RateLimitError` (429) is one such subclass, so the existing `getattr(exc, "status_code", None) == 429` check would work unchanged in principle. However the wrapper is not directly reusable — it's hardcoded to `cliente.chat.completions.create(**kwargs)` while Anthropic's call shape is `cliente.messages.create(**kwargs)`, and the Groq-specific `"try again in Xs"` regex won't match Anthropic's error text (it'll silently fall back to the 5.0s default, which is safe but not optimal). **Recommendation**: write a small parallel `_crear_mensaje_con_reintento()` reusing the same status-code check and backoff shape, adapted to Anthropic's method surface, rather than one generic function spanning two SDKs. Exact `anthropic` package version, `AuthenticationError` shape, and `retry-after` header availability are web-search-derived, not live-inspected — flagged as a design-phase verification item (should be verified live once the package is installed, same discipline as verifying Groq model names/behavior live in prior phases).

## Risks

- `.env.example` automated-edit historically blocked (manual task required, same as every prior phase).
- Existing verbatim-passthrough tests in `tests/test_contexto_memoria.py` will need an injectable enrichment seam or explicit update to keep testing what they test.
- Anthropic SDK exception shapes verified only via web search, not live SDK inspection — design phase should verify live if the package can be installed in the dev container.
- Docker cache volume write permissions (likely fine, container runs as root per Fase 4 precedent), but must degrade gracefully on any write failure regardless.
- Concurrency must preserve selection order explicitly (not `as_completed` arrival order) since `_ensamblar_contexto`'s truncation gives earlier blocks budget priority.
- Haiku's "4-8 líneas" instruction isn't enforced in code — soft risk only; `_ensamblar_contexto`'s character budget still protects final assembly regardless of length drift.

## Ready for Proposal

Yes.
