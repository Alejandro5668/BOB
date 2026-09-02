"""Module context retrieval from the read-only `memory/` fixture.

Reads `MEMORY.md` and `modulos/<carpeta>/_modulo.md` under `MEMORY_DIR`
(default `./memory`), scores each module against an approved transcript
using stdlib-only lexical matching (`difflib` for fuzzy name matching plus
normalized token overlap for description matching), and returns bounded,
literal context for the top matching module(s) — or `""` when nothing
clears the confidence threshold, or the memory root is missing/unreadable.

Never imports Streamlit (see spec "Standalone Testable Module"). Never
writes, creates, or deletes anything under `MEMORY_DIR`: only `is_dir`,
`is_file`, `iterdir`, `resolve`, and `read_text` are used.
"""

from __future__ import annotations

import logging
import os
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# --- Pinned constants (see design.md "Pinned Values") ------------------

TOP_N = 2
UMBRAL = 0.35
PESO_NOMBRE = 0.6
PESO_DESCRIPCION = 0.4
PISO_DIFUSO = 0.80
SATURACION_DESCRIPCION = 3
PRESUPUESTO_CARACTERES = 6000

MARCADOR_TRUNCADO = "[contenido truncado]"

ProveedorContexto = Callable[[str], str]

# Small, deliberately conservative Spanish stopword list: only words that
# would otherwise dilute lexical matching (articles, prepositions,
# conjunctions, common connectors). Domain words are never added here.
_STOPWORDS_ES = frozenset(
    {
        "los", "las", "del", "por", "con", "sin", "como", "donde", "cuando",
        "que", "son", "hay", "muy", "sus", "para", "una", "uno", "unos",
        "unas", "este", "esta", "esos", "esas", "ese", "esa", "todo", "toda",
        "todos", "todas", "tambien", "entre", "sobre", "pero", "mas", "nos",
        "les", "cada", "otra", "otro", "otras", "otros", "desde", "hasta",
        "solo", "aun", "the", "and",
    }
)

_PATRON_INDICE = re.compile(
    r"^-\s*\*\*(?P<nombre>[^*]+)\*\*\s*"
    r"(?:\(\s*alias\s*:\s*(?P<alias>[^)]*)\))?\s*[—-]\s*(?P<desc>.+)$"
)


@dataclass(frozen=True)
class Modulo:
    nombre: str
    alias: tuple[str, ...]
    descripcion: str
    ruta: Path


class ErrorMemoria(RuntimeError):
    """Raised by the strict loader when the memory root is absent/unreadable."""


# --- Normalization / tokenization ---------------------------------------


def _normalizar(texto: str) -> str:
    forma = unicodedata.normalize("NFKD", texto)
    sin_diacriticos = "".join(c for c in forma if not unicodedata.combining(c))
    return sin_diacriticos.lower()


def _tokenizar(texto: str) -> list[str]:
    normalizado = _normalizar(texto)
    crudos = re.findall(r"[a-z0-9]+", normalizado)
    return [t for t in crudos if len(t) >= 3 and t not in _STOPWORDS_ES]


# --- Directory resolution + strict loader -------------------------------


def resolver_directorio(directorio: Optional[str] = None) -> Path:
    """Resolve the memory root: explicit arg > `MEMORY_DIR` env var > `./memory`."""
    valor = directorio if directorio is not None else os.environ.get("MEMORY_DIR", "").strip()
    if not valor:
        valor = "./memory"
    return Path(valor)


def _parsear_indice(texto: str) -> dict[str, tuple[str, tuple[str, ...], str]]:
    indice: dict[str, tuple[str, tuple[str, ...], str]] = {}
    for linea in texto.splitlines():
        coincidencia = _PATRON_INDICE.match(linea.strip())
        if not coincidencia:
            continue
        nombre = coincidencia.group("nombre").strip()
        alias_bruto = coincidencia.group("alias") or ""
        alias = tuple(a.strip() for a in alias_bruto.split(",") if a.strip())
        descripcion = coincidencia.group("desc").strip()
        indice[nombre] = (nombre, alias, descripcion)
    return indice


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


def cargar_modulos(directorio: Optional[str] = None) -> list[Modulo]:
    """Strict loader: parse `MEMORY.md` and load modules from `modulos/`.

    Raises `ErrorMemoria` when the memory root or `MEMORY.md` is missing
    or unreadable. A folder under `modulos/` absent from `MEMORY.md` is
    indexed with its folder name only; an index entry with no
    `_modulo.md` (or one that resolves outside the memory root) is
    skipped, never fatal.
    """
    raiz = resolver_directorio(directorio)

    try:
        es_directorio = raiz.is_dir()
    except OSError as exc:
        raise ErrorMemoria(f"No se pudo acceder a la carpeta de memoria: {exc}") from exc
    if not es_directorio:
        raise ErrorMemoria(f"La carpeta de memoria no existe o no es un directorio: {raiz}")

    try:
        raiz_resuelta = raiz.resolve()
    except OSError as exc:
        raise ErrorMemoria(f"No se pudo resolver la carpeta de memoria: {exc}") from exc

    ruta_indice = raiz / "MEMORY.md"
    try:
        existe_indice = ruta_indice.is_file()
    except OSError as exc:
        raise ErrorMemoria(f"No se pudo acceder a MEMORY.md: {exc}") from exc
    if not existe_indice:
        raise ErrorMemoria(f"No se encontró MEMORY.md en {raiz}")

    try:
        texto_indice = ruta_indice.read_text(encoding="utf-8")
    except OSError as exc:
        raise ErrorMemoria(f"No se pudo leer MEMORY.md: {exc}") from exc

    indice = _parsear_indice(texto_indice)

    carpeta_modulos = raiz / "modulos"
    try:
        hay_modulos = carpeta_modulos.is_dir()
    except OSError as exc:
        raise ErrorMemoria(f"No se pudo acceder a la carpeta modulos/: {exc}") from exc
    if not hay_modulos:
        return []

    try:
        entradas = sorted(carpeta_modulos.iterdir(), key=lambda p: p.name)
    except OSError as exc:
        raise ErrorMemoria(f"No se pudo leer la carpeta modulos/: {exc}") from exc

    modulos: list[Modulo] = []
    for entrada in entradas:
        try:
            if not entrada.is_dir():
                continue
        except OSError:
            continue

        carpeta = entrada.name
        ruta_modulo = entrada / "_modulo.md"
        ruta_modulo_segura = _resolver_seguro(raiz_resuelta, ruta_modulo)
        if ruta_modulo_segura is None:
            continue  # symlink escape or unreadable: silently rejected

        try:
            if not ruta_modulo_segura.is_file():
                continue  # index entry with no _modulo.md: skipped
        except OSError:
            continue

        nombre_indice, alias_indice, descripcion = indice.get(carpeta, (carpeta, (), ""))
        carpeta_normalizada = re.sub(r"[_-]+", " ", carpeta).strip()
        alias_completo = tuple(a for a in (carpeta_normalizada, *alias_indice) if a)

        modulos.append(
            Modulo(
                nombre=nombre_indice,
                alias=alias_completo,
                descripcion=descripcion,
                ruta=ruta_modulo_segura,
            )
        )

    return modulos


# --- Scoring -------------------------------------------------------------


def _puntuar_modulo(modulo: Modulo, tokens_transcripcion: set[str]) -> float:
    s_nombre = 0.0
    for alias in modulo.alias:
        tokens_alias = _tokenizar(alias)
        if not tokens_alias:
            continue
        ratios = [
            max(
                (SequenceMatcher(None, ta, tt).ratio() for tt in tokens_transcripcion),
                default=0.0,
            )
            for ta in tokens_alias
        ]
        r = sum(ratios) / len(ratios)
        if r >= PISO_DIFUSO:
            s_nombre = max(s_nombre, r)

    tokens_descripcion = set(_tokenizar(modulo.descripcion))
    comunes = len(tokens_descripcion & tokens_transcripcion)
    s_desc = min(comunes, SATURACION_DESCRIPCION) / SATURACION_DESCRIPCION

    return PESO_NOMBRE * s_nombre + PESO_DESCRIPCION * s_desc


def puntuar(transcripcion: str, modulos: list[Modulo]) -> list[tuple[Modulo, float]]:
    """Score every module against the transcript. Order matches `modulos`."""
    tokens_transcripcion = set(_tokenizar(transcripcion))
    return [(modulo, _puntuar_modulo(modulo, tokens_transcripcion)) for modulo in modulos]


# --- Health check ---------------------------------------------------------


def diagnosticar(directorio: Optional[str] = None) -> Optional[str]:
    """Return a Spanish non-blocking notice if the memory root is
    missing/unreadable, else `None`."""
    try:
        cargar_modulos(directorio)
    except ErrorMemoria as exc:
        return (
            "No se pudo cargar el contexto de módulos (memory/): "
            f"{exc}. La descripción se generará solo a partir de la transcripción."
        )
    return None


def nombres_conocidos(directorio: Optional[str] = None) -> list[str]:
    """Known module names/aliases, for use as transcription `keyterms`
    (vocabulary hints). Total: returns `[]` on any failure, never raises."""
    try:
        modulos = cargar_modulos(directorio)
    except ErrorMemoria:
        return []
    nombres: list[str] = []
    for modulo in modulos:
        nombres.append(modulo.nombre)
        nombres.extend(modulo.alias)
    return nombres


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


# --- Total provider ---------------------------------------------------------


def buscar_contexto(transcripcion: str, *, directorio: Optional[str] = None) -> str:
    """Total provider: returns bounded module context, or `""`. Never raises."""
    try:
        modulos = cargar_modulos(directorio)
        if not modulos:
            return ""

        puntuados = puntuar(transcripcion, modulos)
        calificados = [(m, s) for m, s in puntuados if s >= UMBRAL]
        calificados.sort(key=lambda par: (-par[1], par[0].nombre))
        seleccionados = calificados[:TOP_N]
        if not seleccionados:
            return ""

        bloques = []
        for modulo, _ in seleccionados:
            try:
                bloques.append(modulo.ruta.read_text(encoding="utf-8"))
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
