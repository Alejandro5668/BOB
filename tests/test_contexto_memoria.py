"""Unit tests for contexto_memoria.py — schema-free discovery, budget,
path-safety, and Groq-assisted relevance selection.

`memory/` under `MEMORY_DIR` is treated as ANY folder of .md documentation
(no fixed index file, no required subfolder layout) — see CLAUDE.md
"Context retrieval decision". Tests build synthetic trees under `tmp_path`
rather than relying on any particular real-world layout.
"""

from pathlib import Path

import pytest

import contexto_memoria as cm


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
    def __init__(self, archivos_elegidos=None, error=None):
        self.calls = []
        self._archivos_elegidos = archivos_elegidos if archivos_elegidos is not None else []
        self._error = error

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        import json

        return FakeResponse(json.dumps({"archivos": self._archivos_elegidos}))


class FakeChat:
    def __init__(self, archivos_elegidos=None, error=None):
        self.completions = FakeCompletions(archivos_elegidos, error)


class FakeGroq:
    def __init__(self, archivos_elegidos=None, error=None):
        self.chat = FakeChat(archivos_elegidos, error)


def _crear_arbol(raiz: Path, archivos: dict) -> Path:
    """Build an arbitrary tree of .md files under `raiz` from a
    {ruta_relativa: contenido} dict — any nesting, any naming."""
    raiz.mkdir(parents=True, exist_ok=True)
    for ruta_relativa, contenido in archivos.items():
        ruta = raiz / ruta_relativa
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(contenido, encoding="utf-8")
    return raiz


# --- resolver_directorio ----------------------------------------------------


def test_resolver_directorio_explicit_arg_wins(monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", "/env/path")
    assert cm.resolver_directorio("/explicit/path") == Path("/explicit/path")


def test_resolver_directorio_env_var_used_when_no_explicit_arg(monkeypatch):
    monkeypatch.setenv("MEMORY_DIR", "/env/path")
    assert cm.resolver_directorio() == Path("/env/path")


def test_resolver_directorio_defaults_to_dot_memory(monkeypatch):
    monkeypatch.delenv("MEMORY_DIR", raising=False)
    assert cm.resolver_directorio() == Path("./memory")


# --- listar_documentos: schema-free discovery -------------------------------


def test_listar_documentos_finds_any_md_file_any_nesting(tmp_path):
    raiz = _crear_arbol(
        tmp_path / "memory",
        {
            "PROYECTO.md": "Documento raíz del proyecto.",
            "gsr_riesgos_v3/index.md": "Resumen del módulo de riesgos v3.",
            "gsr_riesgos_v3/control/crg_control_evaluar.md": "Detalle de evaluación de control.",
            "no_es_markdown.txt": "esto no debe aparecer",
        },
    )

    documentos = cm.listar_documentos(str(raiz))
    rutas = {ruta for ruta, _ in documentos}

    assert rutas == {
        "PROYECTO.md",
        "gsr_riesgos_v3/index.md",
        "gsr_riesgos_v3/control/crg_control_evaluar.md",
    }


def test_listar_documentos_preview_is_collapsed_and_bounded(tmp_path):
    contenido = "Línea uno.\n\nLínea   con    espacios.\n" + ("x" * 500)
    raiz = _crear_arbol(tmp_path / "memory", {"doc.md": contenido})

    documentos = cm.listar_documentos(str(raiz))

    assert len(documentos) == 1
    _, vista_previa = documentos[0]
    assert len(vista_previa) <= cm.LONGITUD_VISTA_PREVIA
    assert "\n" not in vista_previa


def test_listar_documentos_raises_error_memoria_when_root_missing(tmp_path):
    with pytest.raises(cm.ErrorMemoria):
        cm.listar_documentos(str(tmp_path / "no_existe"))


def test_listar_documentos_skips_symlink_escape(tmp_path):
    raiz = tmp_path / "memory"
    raiz.mkdir()
    fuera = tmp_path / "fuera"
    fuera.mkdir()
    (fuera / "secreto.md").write_text("no debería aparecer", encoding="utf-8")

    enlace = raiz / "enlace.md"
    try:
        enlace.symlink_to(fuera / "secreto.md")
    except OSError:
        pytest.skip("symlinks no soportados en este entorno")

    documentos = cm.listar_documentos(str(raiz))
    assert documentos == []


def test_listar_documentos_caps_at_max_documentos_listados(tmp_path, monkeypatch):
    monkeypatch.setattr(cm, "MAX_DOCUMENTOS_LISTADOS", 3)
    archivos = {f"doc{i}.md": f"contenido {i}" for i in range(10)}
    raiz = _crear_arbol(tmp_path / "memory", archivos)

    documentos = cm.listar_documentos(str(raiz))
    assert len(documentos) == 3


# --- nombres_conocidos -------------------------------------------------------


def test_nombres_conocidos_derives_from_paths_no_schema_needed(tmp_path):
    raiz = _crear_arbol(
        tmp_path / "memory",
        {"gsr_riesgos_v3/index.md": "contenido", "cfg_configuracion/index.md": "contenido"},
    )

    nombres = cm.nombres_conocidos(str(raiz))

    normalizados = {n.lower() for n in nombres}
    assert "gsr riesgos v3" in normalizados
    assert "cfg configuracion" in normalizados
    assert "index" in normalizados


def test_nombres_conocidos_empty_on_missing_directory():
    assert cm.nombres_conocidos(directorio="ruta/que/no/existe") == []


def test_nombres_conocidos_deduplicates_case_insensitively(tmp_path):
    raiz = _crear_arbol(
        tmp_path / "memory",
        {"riesgos/index.md": "a", "RIESGOS/otro.md": "b"},
    )
    nombres = cm.nombres_conocidos(str(raiz))
    normalizados = [n.lower() for n in nombres]
    assert normalizados.count("riesgos") == 1


# --- diagnosticar ------------------------------------------------------------


def test_diagnosticar_returns_none_when_directory_ok(tmp_path):
    raiz = _crear_arbol(tmp_path / "memory", {"doc.md": "contenido"})
    assert cm.diagnosticar(directorio=str(raiz)) is None


def test_diagnosticar_returns_spanish_notice_when_missing():
    aviso = cm.diagnosticar(directorio="ruta/que/no/existe")
    assert aviso is not None
    assert isinstance(aviso, str)
    assert "memoria" in aviso.lower() or "transcripción" in aviso.lower()


# --- elegir_documentos_relevantes: Groq-assisted selection -------------------


def test_elegir_documentos_relevantes_returns_empty_for_empty_listing():
    cliente = FakeGroq()
    assert cm.elegir_documentos_relevantes("transcripción", [], cliente) == []


def test_elegir_documentos_relevantes_filters_to_known_paths(tmp_path):
    documentos = [("real.md", "vista"), ("otro_real.md", "vista")]
    cliente = FakeGroq(archivos_elegidos=["real.md", "inventado_por_el_modelo.md"])

    seleccionados = cm.elegir_documentos_relevantes("transcripción", documentos, cliente)

    assert seleccionados == ["real.md"]


def test_elegir_documentos_relevantes_caps_at_max_archivos():
    documentos = [(f"doc{i}.md", "vista") for i in range(10)]
    cliente = FakeGroq(archivos_elegidos=[f"doc{i}.md" for i in range(10)])

    seleccionados = cm.elegir_documentos_relevantes("transcripción", documentos, cliente)

    assert len(seleccionados) == cm.MAX_ARCHIVOS_SELECCIONADOS


def test_elegir_documentos_relevantes_batches_large_listings(tmp_path):
    """A listing larger than CARACTERES_POR_LOTE must split into multiple
    Groq calls — confirmed against a real 273-file corpus that exceeded
    Groq's free-tier TPM limit in a single request."""
    documentos = [(f"doc{i}.md", "x" * 100) for i in range(300)]
    cliente = FakeGroq(archivos_elegidos=[])

    cm.elegir_documentos_relevantes("transcripción", documentos, cliente)

    assert len(cliente.chat.completions.calls) > 1


def test_elegir_documentos_relevantes_stops_early_once_max_reached(tmp_path):
    documentos = [(f"doc{i}.md", "x" * 100) for i in range(300)]
    # The 3 fixed picks all fall within the first batch (~115 docs at this
    # per-doc size) — once MAX_ARCHIVOS_SELECCIONADOS is hit there, later
    # batches must never be called.
    cliente = FakeGroq(archivos_elegidos=["doc0.md", "doc1.md", "doc2.md"])

    seleccionados = cm.elegir_documentos_relevantes("transcripción", documentos, cliente)

    assert seleccionados == ["doc0.md", "doc1.md", "doc2.md"]
    assert len(cliente.chat.completions.calls) == 1


def test_elegir_documentos_relevantes_sends_listing_and_transcript(tmp_path):
    documentos = [("modulo/index.md", "resumen breve")]
    cliente = FakeGroq(archivos_elegidos=[])
    transcripcion = "El cliente reporta un error en el módulo."

    cm.elegir_documentos_relevantes(transcripcion, documentos, cliente)

    kwargs = cliente.chat.completions.calls[0]
    assert kwargs["model"] == cm.MODELO_SELECTOR
    assert kwargs["response_format"] == {"type": "json_object"}
    user_msg = kwargs["messages"][1]["content"]
    assert transcripcion in user_msg
    assert "modulo/index.md" in user_msg
    assert "resumen breve" in user_msg


# --- buscar_contexto: total provider ----------------------------------------


def test_buscar_contexto_empty_when_no_documents(tmp_path):
    raiz = tmp_path / "memory"
    raiz.mkdir()
    cliente = FakeGroq()

    assert cm.buscar_contexto("transcripción", directorio=str(raiz), cliente=cliente) == ""
    assert cliente.chat.completions.calls == []  # never called with nothing to pick from


def test_buscar_contexto_empty_when_selector_picks_nothing(tmp_path):
    raiz = _crear_arbol(tmp_path / "memory", {"doc.md": "contenido"})
    cliente = FakeGroq(archivos_elegidos=[])

    assert cm.buscar_contexto("transcripción", directorio=str(raiz), cliente=cliente) == ""


def test_buscar_contexto_returns_selected_file_content_verbatim(tmp_path):
    raiz = _crear_arbol(
        tmp_path / "memory",
        {"riesgos/index.md": "Documentación real de riesgos.", "otro.md": "irrelevante"},
    )
    cliente = FakeGroq(archivos_elegidos=["riesgos/index.md"])

    contexto = cm.buscar_contexto("transcripción", directorio=str(raiz), cliente=cliente)

    assert contexto == "Documentación real de riesgos."


def test_buscar_contexto_degrades_to_empty_on_missing_directory():
    cliente = FakeGroq()
    assert cm.buscar_contexto("transcripción", directorio="ruta/que/no/existe", cliente=cliente) == ""


def test_buscar_contexto_degrades_to_empty_on_selector_failure(tmp_path):
    raiz = _crear_arbol(tmp_path / "memory", {"doc.md": "contenido"})
    cliente = FakeGroq(error=RuntimeError("fallo de red simulado"))

    assert cm.buscar_contexto("transcripción", directorio=str(raiz), cliente=cliente) == ""


def test_buscar_contexto_never_raises_on_malformed_json(tmp_path):
    raiz = _crear_arbol(tmp_path / "memory", {"doc.md": "contenido"})

    class CompletionsRespuestaInvalida:
        def create(self, **kwargs):
            return FakeResponse("esto no es json")

    class ClienteRespuestaInvalida:
        def __init__(self):
            self.chat = type("Chat", (), {"completions": CompletionsRespuestaInvalida()})()

    assert cm.buscar_contexto(
        "transcripción", directorio=str(raiz), cliente=ClienteRespuestaInvalida()
    ) == ""


# --- Budget / truncation (unchanged generic logic) --------------------------


def test_ensamblar_contexto_within_budget_included_unmodified():
    bloques = ["contenido corto uno", "contenido corto dos"]
    resultado = cm._ensamblar_contexto(bloques, presupuesto=1000)
    assert resultado == "contenido corto uno\n\ncontenido corto dos"


def test_ensamblar_contexto_oversized_truncated_at_line_boundary():
    bloque = "línea uno\nlínea dos\n" + ("x" * 100)
    resultado = cm._ensamblar_contexto([bloque], presupuesto=20)
    assert cm.MARCADOR_TRUNCADO in resultado
    assert len(resultado) <= 20 + len(cm.MARCADOR_TRUNCADO) + 5


# --- Path safety --------------------------------------------------------


def test_resolver_seguro_rejects_path_outside_root(tmp_path):
    raiz = tmp_path / "memory"
    raiz.mkdir()
    raiz_resuelta = raiz.resolve()
    fuera = tmp_path / "fuera.md"
    fuera.write_text("contenido", encoding="utf-8")

    assert cm._resolver_seguro(raiz_resuelta, fuera) is None


def test_resolver_seguro_accepts_path_inside_root(tmp_path):
    raiz = tmp_path / "memory"
    raiz.mkdir()
    raiz_resuelta = raiz.resolve()
    adentro = raiz / "doc.md"
    adentro.write_text("contenido", encoding="utf-8")

    assert cm._resolver_seguro(raiz_resuelta, adentro) == adentro.resolve()
