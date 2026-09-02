# Proposal: Haiku-Enriched Documentation Context

## Intent

`buscar_contexto()` injects **raw** `.md` files into the Groq prompt. That
documentation is written for developers — implementation detail, jargon,
inconsistent length — while the audience is analysts who are not
programmers. Result: descriptions and answers echo implementation
vocabulary, and long raw files consume the 6000-char budget so fewer
documents fit. Enriching each selected document into a short
functional-behavior summary (Claude Haiku 4.5), cached by content hash,
raises answer quality and lowers tokens sent to Groq — paid once per
document version, not once per request.

## Scope

### In Scope
- New module `contexto_enriquecido.py`: lazy Anthropic client, Anthropic-specific
  429 retry wrapper (`messages.create`), per-document enrichment, cache I/O,
  order-preserving `ThreadPoolExecutor` fan-out for cache misses only.
- `contexto_memoria.py::buscar_contexto()` — enrich the selected documents at the
  existing block-building loop; injectable seam so existing tests stay meaningful.
- SHA-256 content-addressed cache at `cache/documentacion/<hash>.txt`; gitignored,
  bind-mounted in compose like `logs/`.
- Non-blocking degradation: missing `ANTHROPIC_API_KEY`, API error, or cache I/O
  failure falls back to that document's raw content.
- `requirements.txt` (`anthropic`), `Dockerfile` COPY line, `docker-compose.yml`
  volume, `.gitignore`, `prompts.py` entry, tests (`FakeAnthropic` double).
- `.env.example`: `ANTHROPIC_API_KEY=` — **planned as a manual task**; automated
  edits to this file were blocked by a permission guardrail in Fase 1, 2 and 4.

### Out of Scope
- Enriching the preview-listing / selection stage (`elegir_documentos_relevantes`).
- Any prompt change in `generar_descripcion.py` or `consultar_documentacion.py`.
- Cache eviction/TTL/size limits; a corpus pre-warm script (design may defer or add).
- Replacing the Groq selector, or changing `_ensamblar_contexto`'s budget logic.

## Capabilities

### New Capabilities
- `documentation-enrichment`: converts a raw technical document into a concise
  functional summary via Haiku, content-addressed caching, bounded concurrency,
  and mandatory raw-content fallback on any failure.

### Modified Capabilities
- `context-retrieval`: assembled context blocks become enriched summaries of the
  selected documents instead of verbatim file content, with per-document fallback
  to verbatim. Retrieval stays a total provider (`""` on failure) and read-only
  against `MEMORY_DIR`.

> `openspec/specs/context-retrieval/spec.md` is flagged STALE (still describes the
> Fase 2 fixed-schema design). The delta MUST be written against the real
> schema-free implementation, not that file.

## Approach

Exploration's Approach 1. `buscar_contexto()` gains one lazily-imported call:
`enriquecer_documentos([(ruta, contenido_raw), ...]) -> list[str]`, same length and
order. Inside: hash each document, read cache; submit only misses to a
`ThreadPoolExecutor(max_workers=3)`; map futures by index; write successes to cache;
any per-document exception yields the raw content. Anthropic's retry wrapper mirrors
Groq's shape (`status_code == 429`, 5s fallback wait) but targets `messages.create`
— it is not reusable across the two SDKs.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `contexto_enriquecido.py` | New | Client, cache, retry, concurrency |
| `contexto_memoria.py` | Modified | Enrich at block-building loop |
| `prompts.py` | Modified | Haiku enrichment prompt constant |
| `requirements.txt` | Modified | `anthropic` |
| `Dockerfile` | Modified | COPY new module |
| `docker-compose.yml` | Modified | `./cache/documentacion` volume |
| `.gitignore` | Modified | `cache/` |
| `.env.example` | Modified (manual) | `ANTHROPIC_API_KEY=` |
| `tests/` | New + Modified | `test_contexto_enriquecido.py`; update verbatim assertions |
| `generar_descripcion.py`, `consultar_documentacion.py` | Unchanged | Verified at call sites |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Enrichment drops a detail the answer needed | Med | Non-restrictive prompt; raw fallback; cache is per-content so a doc edit re-enriches |
| Existing "verbatim" tests break | High | Injectable enrichment seam defaulting to pass-through in tests |
| Concurrency reorders blocks (budget truncation is order-sensitive) | Med | Index/future mapping, never `as_completed` order |
| Anthropic SDK error shapes are doc-derived, not live-inspected | Med | Design-phase smoke test before the retry wrapper is called done |
| `.env.example` automated edit blocked again | High | Manual task with exact copy-paste line, planned up front |
| Cache dir unwritable in container | Low | `OSError` → enrich without caching, never fail |
| Added latency on a full cache miss | Med | Concurrent misses; cache hits are a plain file read |

## Rollback Plan

Additive and revertible as one PR. `contexto_memoria.py` is the only behavioral
edit and it is one call at a known loop; reverting it restores verbatim raw blocks.
No schema, no migration. `cache/documentacion/` is disposable — deleting it only
forces re-enrichment. Kill switch without a revert: unset `ANTHROPIC_API_KEY`; every
document then falls back to raw content and the pipeline behaves exactly as today.

## Dependencies

- `anthropic` Python package (new).
- `ANTHROPIC_API_KEY` provisioned by the operator (**optional at runtime** — absence
  degrades, never blocks). Model: `claude-haiku-4-5-20251001`.
- Human action for the `.env.example` line.

## Success Criteria

- [ ] Selected documents reach Groq as functional summaries, not raw file text.
- [ ] Second identical request performs zero Anthropic calls (cache hit); editing a
      source `.md` produces a new hash and one fresh enrichment.
- [ ] With `ANTHROPIC_API_KEY` unset, `buscar_contexto()` returns raw-content context
      and the app behaves exactly as before this change.
- [ ] A raised Anthropic error for one document degrades only that block; the others
      stay enriched.
- [ ] Block order matches selection order under concurrency.
- [ ] `pytest` green, including updated `test_contexto_memoria.py`.
- [ ] `docker compose up` persists `cache/documentacion/` across container recreation.
