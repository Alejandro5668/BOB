"""Schema-free document retrieval from the read-only `memory/` folder.

`MEMORY_DIR` can be ANY folder of Markdown documentation — no fixed index
file, no required subfolder layout, no per-module summary convention.
This deliberately replaced an earlier design that required a `MEMORY.md`
index + `modulos/<carpeta>/_modulo.md` layout: the real Kawak PHP
documentation folder has neither (see CLAUDE.md "Context retrieval
decision" for why).

Every `.md` file found anywhere under `MEMORY_DIR` is a candidate. Instead
of our own lexical scoring heuristic, Groq itself picks which files (if
any) are relevant to a transcript, given a lightweight file listing —
leaning on the model's judgment rather than a fixed matching algorithm.

Never imports Streamlit (see spec "Standalone Testable Module"). Never
writes, creates, or deletes anything under `MEMORY_DIR`: only `is_dir`,
`is_file`, `rglob`, `resolve`, and `read_text` are used.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

PRESUPUESTO_CARACTERES = 6000
MARCADOR_TRUNCADO = "[contenido truncado]"

MAX_DOCUMENTOS_LISTADOS = 500  # safety valve on listing size, not a schema requirement
MAX_ARCHIVOS_SELECCIONADOS = 3
LONGITUD_VISTA_PREVIA = 160

# gpt-oss models reason internally before answering, and those reasoning
# tokens count against max_tokens — confirmed live: a 200-token cap cut the
# reasoning off mid-thought, leaving an empty completion Groq's JSON mode
# then rejected as invalid (400). reasoning_effort="low" cuts that
# reasoning-token cost by ~10x (measured 227 -> 14 tokens on a real batch).
MODELO_SELECTOR = "openai/gpt-oss-20b"  # cheaper/faster than the generation model

ProveedorContexto = Callable[[str], str]


class ErrorMemoria(RuntimeError):
    """Raised when the memory root itself is absent/unreadable."""


# --- Directory resolution -------------------------------------------------


def resolver_directorio(directorio: Optional[str] = None) -> Path:
    """Resolve the memory root: explicit arg > `MEMORY_DIR` env var > `./memory`."""
    valor = directorio if directorio is not None else os.environ.get("MEMORY_DIR", "").strip()
    if not valor:
        valor = "./memory"
    return Path(valor)


def _verificar_directorio(raiz: Path) -> Path:
    """Raise ErrorMemoria if `raiz` is missing/unreadable; else return its resolved form."""
    try:
        es_directorio = raiz.is_dir()
    except OSError as exc:
        raise ErrorMemoria(f"No se pudo acceder a la carpeta de memoria: {exc}") from exc
    if not es_directorio:
        raise ErrorMemoria(f"La carpeta de memoria no existe o no es un directorio: {raiz}")
    try:
        return raiz.resolve()
    except OSError as exc:
        raise ErrorMemoria(f"No se pudo resolver la carpeta de memoria: {exc}") from exc


def _resolver_seguro(raiz_resuelta: Path, candidato: Path) -> Optional[Path]:
    """Return `candidato.resolve()` iff it stays under `raiz_resuelta`, else None.

    Rejects symlink escapes: a symlinked folder/file whose real target
    lands outside the memory root is silently excluded, never fatal.
    """
    try:
        candidato_resuelto = candidato.resolve()
    except OSError:
        return None
    try:
        candidato_resuelto.relative_to(raiz_resuelta)
    except ValueError:
        return None
    return candidato_resuelto


def _vista_previa(texto: str, limite: int = LONGITUD_VISTA_PREVIA) -> str:
    return " ".join(texto.split())[:limite]


# --- Discovery: any .md file, any layout -----------------------------------


def listar_documentos(directorio: Optional[str] = None) -> list[tuple[str, str]]:
    """List every `.md` file under `directorio`, however it's organized.

    Returns `(ruta_relativa_posix, vista_previa)` pairs, sorted for
    determinism. Raises `ErrorMemoria` if the root itself is missing or
    unreadable; individual unreadable files are skipped, never fatal.
    Capped at `MAX_DOCUMENTOS_LISTADOS` as a volume safety valve, not a
    structural requirement.
    """
    raiz = resolver_directorio(directorio)
    raiz_resuelta = _verificar_directorio(raiz)

    try:
        candidatos = sorted(raiz.rglob("*.md"))
    except OSError as exc:
        raise ErrorMemoria(f"No se pudo recorrer la carpeta de memoria: {exc}") from exc

    documentos: list[tuple[str, str]] = []
    for ruta in candidatos:
        ruta_segura = _resolver_seguro(raiz_resuelta, ruta)
        if ruta_segura is None:
            continue  # symlink escape: silently excluded
        try:
            if not ruta_segura.is_file():
                continue
            texto = ruta_segura.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        ruta_relativa = ruta_segura.relative_to(raiz_resuelta).as_posix()
        documentos.append((ruta_relativa, _vista_previa(texto)))
        if len(documentos) >= MAX_DOCUMENTOS_LISTADOS:
            break

    return documentos


def nombres_conocidos(directorio: Optional[str] = None) -> list[str]:
    """Folder/file names found under MEMORY_DIR, for use as transcription
    `keyterms` (vocabulary hints) — schema-free: whatever names exist.
    Total: returns `[]` on any failure, never raises."""
    try:
        documentos = listar_documentos(directorio)
    except ErrorMemoria:
        return []

    vistos: set[str] = set()
    nombres: list[str] = []
    for ruta_relativa, _ in documentos:
        for parte in Path(ruta_relativa).parts:
            base = Path(parte).stem.replace("_", " ").replace("-", " ").strip()
            clave = base.lower()
            if base and clave not in vistos:
                vistos.add(clave)
                nombres.append(base)
    return nombres


# --- Health check ---------------------------------------------------------


def diagnosticar(directorio: Optional[str] = None) -> Optional[str]:
    """Return a Spanish non-blocking notice if the memory root is
    missing/unreadable, else `None`."""
    try:
        _verificar_directorio(resolver_directorio(directorio))
    except ErrorMemoria as exc:
        return (
            "No se pudo acceder a la carpeta de memoria (memory/): "
            f"{exc}. La descripción se generará solo a partir de la transcripción."
        )
    return None


# --- Budget / truncation ---------------------------------------------------


def _truncar_bloque(bloque: str, disponible: int) -> str:
    espacio_marcador = len(MARCADOR_TRUNCADO) + 1  # + newline before marker
    limite = max(disponible - espacio_marcador, 0)
    corte = bloque.rfind("\n", 0, limite)
    if corte <= 0:
        corte = limite
    contenido = bloque[:corte].rstrip("\n")
    if contenido:
        return contenido + "\n" + MARCADOR_TRUNCADO
    return MARCADOR_TRUNCADO


def _ensamblar_contexto(bloques: list[str], presupuesto: int) -> str:
    separador = "\n\n"
    resultado: list[str] = []
    usado = 0

    for bloque in bloques:
        sep_len = len(separador) if resultado else 0
        disponible = presupuesto - usado - sep_len
        if disponible <= 0:
            break
        if len(bloque) <= disponible:
            resultado.append(bloque)
            usado += sep_len + len(bloque)
        else:
            recortado = _truncar_bloque(bloque, disponible)
            resultado.append(recortado)
            usado += sep_len + len(recortado)
            break

    return separador.join(resultado)


# --- Groq-assisted relevance selection --------------------------------------

# Real corpora (e.g. the actual Kawak PHP docs, 273 files) can exceed
# Groq's free-tier TPM limit for MODELO_SELECTOR in a single request
# (confirmed live: gpt-oss-20b free tier is 8000 TPM; a 273-doc listing at
# the old preview length needed ~14000). The listing is chunked into
# batches so this scales to a corpus of any size, not just today's.
CARACTERES_POR_LOTE = 12000


def _construir_listado(documentos: list[tuple[str, str]]) -> str:
    return "\n".join(f"- {ruta}: {vista_previa}" for ruta, vista_previa in documentos)


def _lotes_de_documentos(documentos: list[tuple[str, str]], presupuesto: Optional[int] = None):
    """Yield successive batches of `documentos` whose formatted listing
    stays within `presupuesto` characters each (default: `CARACTERES_POR_LOTE`,
    read at call time — not a bound default — so tests can monkeypatch it)."""
    if presupuesto is None:
        presupuesto = CARACTERES_POR_LOTE
    lote: list[tuple[str, str]] = []
    tamano = 0
    for doc in documentos:
        costo = len(doc[0]) + len(doc[1]) + 4  # "- {ruta}: {vista_previa}\n"
        if lote and tamano + costo > presupuesto:
            yield lote
            lote, tamano = [], 0
        lote.append(doc)
        tamano += costo
    if lote:
        yield lote


def _preguntar_selector(transcripcion: str, documentos: list[tuple[str, str]], cliente) -> list[str]:
    """One Groq call over a single (already budget-sized) document listing."""
    from generar_descripcion import _crear_completion_con_reintento
    from prompts import ENTRADA_SELECTOR_DOCUMENTOS, SELECTOR_DOCUMENTOS_RELEVANTES

    respuesta = _crear_completion_con_reintento(
        cliente,
        model=MODELO_SELECTOR,
        messages=[
            {"role": "system", "content": SELECTOR_DOCUMENTOS_RELEVANTES},
            {
                "role": "user",
                "content": ENTRADA_SELECTOR_DOCUMENTOS.format(
                    transcripcion=transcripcion,
                    listado=_construir_listado(documentos),
                ),
            },
        ],
        temperature=0.0,
        max_tokens=500,
        reasoning_effort="low",
        response_format={"type": "json_object"},
    )
    datos = json.loads(respuesta.choices[0].message.content)
    return datos.get("archivos", [])


def elegir_documentos_relevantes(
    transcripcion: str, documentos: list[tuple[str, str]], cliente
) -> list[str]:
    """Ask Groq which of `documentos` (if any) are relevant to `transcripcion`.

    The listing is sent in budget-bounded batches (see `CARACTERES_POR_LOTE`)
    — every batch is scanned (no early stop: a batch is evaluated in
    isolation from the others, so a plausible-but-wrong pick in an early
    batch must never silently outrank a better match only visible in a
    later one — confirmed live against the real Kawak docs, where an
    unrelated `aud_auditoria` file beat the real `gst_documental` match
    this way). When more than `MAX_ARCHIVOS_SELECCIONADOS` candidates
    survive across all batches, one final cross-batch call re-ranks just
    that short list. Returns a list of chosen `ruta_relativa` values,
    always a subset of `documentos`' own paths (never trusts an unlisted
    path the model might invent). May raise — callers must handle
    degradation.
    """
    if not documentos:
        return []

    rutas_validas = {ruta for ruta, _ in documentos}
    candidatos: list[str] = []

    for lote in _lotes_de_documentos(documentos):
        for ruta in _preguntar_selector(transcripcion, lote, cliente):
            if ruta in rutas_validas and ruta not in candidatos:
                candidatos.append(ruta)

    if not candidatos or len(candidatos) <= MAX_ARCHIVOS_SELECCIONADOS:
        return candidatos

    documentos_por_ruta = dict(documentos)
    candidatos_documentos = [(ruta, documentos_por_ruta[ruta]) for ruta in candidatos]
    seleccion_final = _preguntar_selector(transcripcion, candidatos_documentos, cliente)
    return [ruta for ruta in seleccion_final if ruta in candidatos][:MAX_ARCHIVOS_SELECCIONADOS]


# --- Total provider ---------------------------------------------------------


def buscar_contexto(
    transcripcion: str, *, directorio: Optional[str] = None, cliente=None
) -> str:
    """Total provider: returns bounded document context, or `""`. Never raises.

    `cliente` is injected for testing; when None, resolves lazily to
    `generar_descripcion._crear_cliente()` (same lazy-fail-on-missing-key
    behavior as the generation client).
    """
    try:
        documentos = listar_documentos(directorio)
        if not documentos:
            return ""

        if cliente is None:
            from generar_descripcion import _crear_cliente

            cliente = _crear_cliente()

        seleccionados = elegir_documentos_relevantes(transcripcion, documentos, cliente)
        if not seleccionados:
            return ""

        raiz = resolver_directorio(directorio)
        bloques = []
        for ruta_relativa in seleccionados:
            try:
                bloques.append((raiz / ruta_relativa).read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue

        if not bloques:
            return ""

        return _ensamblar_contexto(bloques, PRESUPUESTO_CARACTERES)
    except Exception as exc:
        logger.warning(
            "buscar_contexto degradó a sin-contexto (directorio=%s): %s: %s",
            directorio, type(exc).__name__, exc,
        )
        return ""
