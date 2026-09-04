<p align="center">
  <img src="assets/bob_logo.png" width="140" alt="BOB">
</p>

<h1 align="center">BOB</h1>

<p align="center">
  Asistente de voz para analistas — del audio al ticket de Jira, sin escribir nada a mano.
</p>

---

Un analista graba un audio contando un problema que le reportó un cliente
(o haciendo una pregunta sobre cómo funciona algo). BOB lo transcribe, busca
la documentación interna relevante, y arma con **Claude Haiku 4.5** una
descripción lista para pegar en Jira — o responde la consulta directo — en
lenguaje llano, sin necesidad de saber programar.

- 🎙️ **Voz a texto** con la API de ElevenLabs, transcripción automática al terminar de grabar.
- 🎫 **Descripción de ticket lista para Jira**, plantilla fija (módulo afectado, qué pasó, pasos, resultado esperado) — nunca prosa libre ni relleno genérico.
- 💬 **Modo consulta**: responde preguntas sobre cómo funciona el sistema, y pide una aclaración en vez de adivinar cuando la pregunta es ambigua.
- 📚 **RAG sin estructura fija**: encuentra cualquier `.md` en la carpeta de documentación, sin índice ni convención de carpetas — la propia IA elige qué documentos son relevantes.
- 🛡️ **Guardrails anti-alucinación**: cada nombre de módulo y cada precisión que viene de la documentación se verifica por separado antes de mostrarse; si no tiene base real, se descarta en vez de inventarse.

## Arrancar el proyecto

Si estás usando Claude Code, lo más simple es pedirle directamente:

> "Levantame el proyecto"

`CLAUDE.md` ya tiene la instrucción exacta, así que Claude Code corre
`./scripts/setup.sh` por vos — reconstruye la imagen de Docker desde cero y
levanta el contenedor, para que nunca quede sirviendo una versión vieja
por accidente.

Si preferís hacerlo vos mismo, es el mismo comando:

```bash
./scripts/setup.sh
```

Al terminar, la app queda en `http://localhost:8501`. Es seguro correr este
script de nuevo en cualquier momento, incluso después de traer cambios
nuevos.

### Variables de entorno

El script crea `.env` a partir de `.env.example` si todavía no existe.
Completá:

| Variable | Requerida | Para qué |
|---|---|---|
| `ANTHROPIC_API_KEY` | Sí | Selección de documentos, generación, verificación y modo consulta (Claude Haiku 4.5). |
| `ELEVENLABS_API_KEY` | Sí | Transcripción de audio a texto. |
| `MEMORY_DIR` | No | Carpeta con la documentación real a usar como contexto. Sin ella, se usa el fixture de ejemplo incluido en `memory/`. |

## Cómo funciona por dentro

- `contexto_memoria.py` — encuentra los `.md` disponibles y le pregunta a
  Haiku cuáles son relevantes para el caso, sin scoring propio ni
  estructura de carpetas fija.
- `generar_descripcion.py` / `consultar_documentacion.py` — arman la
  respuesta con la plantilla fija y la pasan por los verificadores
  anti-alucinación antes de mostrarla.
- `cliente_anthropic.py` — el único punto de contacto con la API de
  Anthropic (cliente, reintentos, helper de JSON).
- `prompts.py` — todos los prompts del proyecto, centralizados y
  documentados ahí, nunca inline en el código que los usa.

El detalle completo de cada decisión de arquitectura (por qué RAG sin
estructura fija, por qué los guardrails funcionan así, cómo se despliega)
está en `CLAUDE.md`.

## Tests

```bash
pytest
```

Sin llamadas de red — todo corre contra clientes falsos, no hace falta
ninguna clave de API para que pasen.
