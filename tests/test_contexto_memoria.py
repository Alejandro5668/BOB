"""Unit tests for contexto_memoria.py — scoring, threshold, budget, degrade,
path-safety, and sentinel-scope, per design.md and tasks.md Phase 8.

Uses `tmp_path` fixtures for fully-controlled scoring/threshold/budget/
path-safety scenarios, plus the real repo `memory/` fixture (relative to
this file, independent of pytest's cwd) for the worked example and the
sentinel-scope assertions that tie directly to the shipped fixture.
"""

from pathlib import Path

import pytest

import contexto_memoria as cm

REPO_MEMORY_DIR = Path(__file__).resolve().parent.parent / "memory"


def _crear_memoria(raiz: Path, modulos: dict) -> Path:
    """Build a minimal memory/ tree under `raiz` from a {nombre: {...}} dict.

    Each value may have "alias" (str) and "descripcion" (str, default a
    generic sentence) and "contenido" (str, default a per-module marker).
    """
    raiz.mkdir(parents=True, exist_ok=True)
    (raiz / "modulos").mkdir(exist_ok=True)

    lineas = ["# Índice de prueba", ""]
    for nombre, datos in modulos.items():
        alias = datos.get("alias", "")
        descripcion = datos.get("descripcion", "Descripción genérica de módulo de prueba.")
        alias_parte = f" (alias: {alias})" if alias else ""
        lineas.append(f"- **{nombre}**{alias_parte} — {descripcion}")

        carpeta_modulo = raiz / "modulos" / nombre
        carpeta_modulo.mkdir(parents=True, exist_ok=True)
        contenido = datos.get("contenido", f"Contenido de prueba: {nombre}")
        (carpeta_modulo / "_modulo.md").write_text(contenido, encoding="utf-8")

    (raiz / "MEMORY.md").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return raiz


# --- Scoring: worked example against the real fixture -----------------------


def test_worked_example_ranks_gestion_riesgos_first():
    transcripcion = "el módulo donde se ven los riesgos no carga la matriz"

    modulos = cm.cargar_modulos(str(REPO_MEMORY_DIR))
    puntuados = {m.nombre: s for m, s in cm.puntuar(transcripcion, modulos)}

    assert puntuados["gestion_riesgos"] == pytest.approx(0.8667, abs=1e-3)
    assert puntuados["gestion_riesgos"] > puntuados["planes_accion"]
    assert puntuados["gestion_riesgos"] > puntuados["auditorias_internas"]
    assert puntuados["gestion_riesgos"] >= cm.UMBRAL


def test_worked_example_buscar_contexto_returns_gestion_riesgos_content():
    transcripcion = "el módulo donde se ven los riesgos no carga la matriz"

    contexto = cm.buscar_contexto(transcripcion, directorio=str(REPO_MEMORY_DIR))

    esperado = (REPO_MEMORY_DIR / "modulos" / "gestion_riesgos" / "_modulo.md").read_text(
        encoding="utf-8"
    )
    assert contexto == esperado


# --- No match ----------------------------------------------------------------


def test_no_recognizable_reference_returns_empty_string():
    transcripcion = (
        "el usuario reporta que la aplicacion se cierra sola al abrir "
        "un archivo adjunto en el correo"
    )

    contexto = cm.buscar_contexto(transcripcion, directorio=str(REPO_MEMORY_DIR))

    assert contexto == ""


def test_no_recognizable_reference_every_module_below_threshold():
    transcripcion = (
        "el usuario reporta que la aplicacion se cierra sola al abrir "
        "un archivo adjunto en el correo"
    )
    modulos = cm.cargar_modulos(str(REPO_MEMORY_DIR))

    puntuados = cm.puntuar(transcripcion, modulos)

    assert all(score < cm.UMBRAL for _, score in puntuados)


# --- Top-N / threshold / tie-break, fully controlled -------------------------


def test_single_module_clears_threshold_only_that_context_returned(tmp_path):
    raiz = _crear_memoria(
        tmp_path / "memory",
        {
            "modulo_alfa": {"alias": "alfa", "descripcion": "cosas de alfa y beta"},
            "modulo_zeta": {"alias": "zeta", "descripcion": "cosas totalmente distintas"},
        },
    )

    contexto = cm.buscar_contexto("hablo del modulo alfa", directorio=str(raiz))

    assert contexto == "Contenido de prueba: modulo_alfa"


def test_two_qualifying_modules_both_returned_alphabetical_tie_break(tmp_path):
    # Both modules share the exact same alias/description shape so they
    # score identically; only the module name differs.
    raiz = _crear_memoria(
        tmp_path / "memory",
        {
            "modulo_b": {"alias": "comun", "descripcion": "elemento comun compartido"},
            "modulo_a": {"alias": "comun", "descripcion": "elemento comun compartido"},
        },
    )
    modulos = cm.cargar_modulos(str(raiz))
    puntuados = cm.puntuar("hay un elemento comun compartido", modulos)

    puntajes = {m.nombre: s for m, s in puntuados}
    assert puntajes["modulo_a"] == puntajes["modulo_b"]
    assert puntajes["modulo_a"] >= cm.UMBRAL

    contexto = cm.buscar_contexto("hay un elemento comun compartido", directorio=str(raiz))

    pos_a = contexto.find("Contenido de prueba: modulo_a")
    pos_b = contexto.find("Contenido de prueba: modulo_b")
    assert pos_a != -1 and pos_b != -1
    assert pos_a < pos_b  # alphabetical tie-break: modulo_a before modulo_b


def test_top_n_caps_at_two_even_when_three_modules_qualify(tmp_path):
    raiz = _crear_memoria(
        tmp_path / "memory",
        {
            "modulo_uno": {"alias": "primero", "descripcion": "primero segundo tercero"},
            "modulo_dos": {"alias": "segundo", "descripcion": "primero segundo tercero"},
            "modulo_tres": {"alias": "tercero", "descripcion": "primero segundo tercero"},
        },
    )

    contexto = cm.buscar_contexto(
        "primero segundo tercero", directorio=str(raiz)
    )

    incluidos = sum(
        1
        for nombre in ("modulo_uno", "modulo_dos", "modulo_tres")
        if f"Contenido de prueba: {nombre}" in contexto
    )
    assert incluidos == cm.TOP_N == 2


# --- Budget / truncation ------------------------------------------------------


def test_within_budget_content_included_unmodified(tmp_path):
    raiz = _crear_memoria(
        tmp_path / "memory",
        {"modulo_pequeno": {"alias": "pequeno", "contenido": "contenido corto y simple"}},
    )

    contexto = cm.buscar_contexto("hablemos del modulo pequeno", directorio=str(raiz))

    assert contexto == "contenido corto y simple"


def test_oversized_content_truncated_within_budget_at_line_boundary(tmp_path):
    linea = "x" * 50 + "\n"
    contenido_grande = linea * 200  # well over PRESUPUESTO_CARACTERES
    raiz = _crear_memoria(
        tmp_path / "memory",
        {"modulo_grande": {"alias": "grande", "contenido": contenido_grande}},
    )

    contexto = cm.buscar_contexto("hablemos del modulo grande", directorio=str(raiz))

    assert len(contexto) <= cm.PRESUPUESTO_CARACTERES
    assert contexto.endswith(cm.MARCADOR_TRUNCADO)
    # Cut on a line boundary: everything before the marker is whole lines.
    cuerpo = contexto[: -len(cm.MARCADOR_TRUNCADO)].rstrip("\n")
    assert all(l == "x" * 50 for l in cuerpo.splitlines())


# --- Degrade: unset/missing/unreadable MEMORY_DIR ----------------------------


def test_missing_memory_dir_returns_empty_string_never_raises():
    contexto = cm.buscar_contexto("cualquier transcripcion", directorio="ruta/que/no/existe")
    assert contexto == ""


def test_unset_memory_dir_env_defaults_and_degrades_gracefully(monkeypatch, tmp_path):
    monkeypatch.delenv("MEMORY_DIR", raising=False)
    monkeypatch.chdir(tmp_path)  # "./memory" won't exist here

    contexto = cm.buscar_contexto("cualquier transcripcion")

    assert contexto == ""


def test_diagnosticar_returns_none_when_memory_ok():
    assert cm.diagnosticar(directorio=str(REPO_MEMORY_DIR)) is None


def test_diagnosticar_returns_spanish_notice_when_missing():
    aviso = cm.diagnosticar(directorio="ruta/que/no/existe")
    assert aviso is not None
    assert isinstance(aviso, str)
    assert "memory" in aviso.lower() or "transcripción" in aviso.lower()


def test_permission_error_on_iterdir_degrades_without_raising(tmp_path, monkeypatch):
    raiz = _crear_memoria(
        tmp_path / "memory", {"modulo_x": {"alias": "equis"}}
    )

    original_iterdir = Path.iterdir

    def iterdir_falso(self):
        if self == raiz / "modulos":
            raise PermissionError("acceso denegado (simulado)")
        return original_iterdir(self)

    monkeypatch.setattr(Path, "iterdir", iterdir_falso)

    assert cm.buscar_contexto("equis", directorio=str(raiz)) == ""
    assert cm.diagnosticar(directorio=str(raiz)) is not None


def test_cargar_modulos_raises_error_memoria_on_missing_root():
    with pytest.raises(cm.ErrorMemoria):
        cm.cargar_modulos("ruta/que/no/existe")


# --- Path safety: symlink escape rejection (RED) -----------------------------


def test_symlink_escape_outside_memory_dir_is_rejected(tmp_path, monkeypatch):
    raiz = _crear_memoria(
        tmp_path / "memory", {"modulo_bueno": {"alias": "bueno"}}
    )
    (raiz / "modulos" / "evil").mkdir()

    afuera = tmp_path / "afuera"
    afuera.mkdir()
    (afuera / "secreto.txt").write_text("ESCAPADO_FUERA_DE_MEMORIA", encoding="utf-8")

    objetivo_evil = (raiz / "modulos" / "evil" / "_modulo.md").resolve()
    ruta_afuera = (afuera / "secreto.txt").resolve()

    original_resolve = Path.resolve

    def resolve_falso(self, *args, **kwargs):
        resultado = original_resolve(self, *args, **kwargs)
        if resultado == objetivo_evil:
            return ruta_afuera
        return resultado

    monkeypatch.setattr(Path, "resolve", resolve_falso)

    modulos = cm.cargar_modulos(str(raiz))

    nombres = {m.nombre for m in modulos}
    assert "evil" not in nombres
    assert nombres == {"modulo_bueno"}


# --- Path safety: zero write/create/delete filesystem calls ------------------


def test_retrieval_never_writes_to_memory_dir(tmp_path, monkeypatch):
    raiz = _crear_memoria(
        tmp_path / "memory", {"modulo_bueno": {"alias": "bueno"}}
    )

    def _prohibido(*args, **kwargs):
        raise AssertionError("retrieval must never write/create/delete under MEMORY_DIR")

    for nombre_metodo in ("write_text", "write_bytes", "unlink", "mkdir", "rmdir", "touch"):
        monkeypatch.setattr(Path, nombre_metodo, _prohibido)

    # Must run clean end-to-end without touching any of the patched methods.
    cm.cargar_modulos(str(raiz))
    cm.buscar_contexto("hablemos del modulo bueno", directorio=str(raiz))
    cm.diagnosticar(str(raiz))


# --- Scope: sentinel strings from shared files never leak -------------------


def test_shared_files_sentinels_never_appear_in_injected_context():
    transcripcion = "el módulo donde se ven los riesgos no carga la matriz"
    contexto = cm.buscar_contexto(transcripcion, directorio=str(REPO_MEMORY_DIR))

    assert "CORE_NUNCA_INYECTAR" not in contexto
    assert "ERRORES_NUNCA_INYECTAR" not in contexto
    assert "DECISIONES_NUNCA_INYECTAR" not in contexto
    assert "Índice de módulos" not in contexto  # MEMORY.md heading text


def test_shared_files_sentinels_never_appear_across_any_module_match():
    # Cross-check against every real fixture module, not just the top match.
    modulos = cm.cargar_modulos(str(REPO_MEMORY_DIR))
    for modulo in modulos:
        contenido = modulo.ruta.read_text(encoding="utf-8")
        assert "CORE_NUNCA_INYECTAR" not in contenido
        assert "ERRORES_NUNCA_INYECTAR" not in contenido
        assert "DECISIONES_NUNCA_INYECTAR" not in contenido


# --- Standalone testable, no Streamlit import --------------------------------


def test_module_does_not_import_streamlit():
    with open(cm.__file__, encoding="utf-8") as f:
        codigo_fuente = f.read()
    assert "streamlit" not in codigo_fuente
