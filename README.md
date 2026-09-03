# BOB — Asistente de Voz para Analistas

Aplicación Streamlit de una sola pantalla: graba un audio, lo transcribe
con la API de ElevenLabs, permite editar la transcripción, y según el
modo elegido genera una descripción lista para Jira o responde una
consulta usando la documentación disponible — todo con Claude Haiku 4.5.
La transcripción se auto-inicia al parar de grabar (sin clic extra).

**Nota de privacidad:** el audio se envía a la API de ElevenLabs para
transcribirse, y la transcripción/documentación seleccionada se envía a
la API de Anthropic para generar la respuesta (decisiones explícitas,
ver `CLAUDE.md` "Transcription provider decision" y "Migración a
Claude Haiku 4.5").

## Producción

**https://bob-vjwv.onrender.com** — deploy en Render con la documentación
real de Kawak. Sin autenticación (decisión explícita, ver `CLAUDE.md`
"Deploying after a merge"): compartir el link solo con quien ya deba
tener acceso a esa documentación. No hace auto-deploy en cada push —
correr `./scripts/deploy-render.sh` para actualizar código o documentación
(ver esa misma sección de `CLAUDE.md` para el porqué).

## Arrancar el proyecto (recomendado)

```bash
./scripts/setup.sh
```

Idempotente — seguro correrlo de nuevo en cualquier momento, incluso
después de un merge. Siempre reconstruye la imagen y recrea el
contenedor desde cero, así que nunca deja sirviendo en silencio un
build viejo. Si `.env` no existe, lo crea a partir de `.env.example` y
avisa qué claves completar.

## Variables de entorno

Copia `.env.example` a `.env` y completa:

| Variable | Requerida | Descripción |
|---|---|---|
| `ANTHROPIC_API_KEY` | Sí | Clave de la API de Anthropic usada por selección, generación, verificación y consulta (Claude Haiku 4.5). Sin ella, la generación y la consulta fallan con un error de configuración claro antes de cualquier llamada de red. |
| `ELEVENLABS_API_KEY` | Sí | Clave de la API de ElevenLabs usada por `transcribir.py`. Sin ella, la transcripción falla con un error de configuración claro (`ErrorConfiguracionAudio`) antes de cualquier llamada de red. |
| `MEMORY_DIR` | No | Ruta a una carpeta de documentación cualquiera (ver `memory/` abajo). Por defecto `./memory`. Si no existe o no es legible, la app degrada de forma automática: la generación sigue funcionando solo con la transcripción y se muestra un aviso no bloqueante (`st.info`). |
| `BOB_HOST_PORT` | No | Puerto publicado en el host (Docker), por defecto `8501`. Útil si `8501` ya está ocupado por otro proceso o contenedor. |

`.env` es opcional para Docker: si no existe, `docker compose up` funciona
igual (`env_file` con `required: false`).

## Ejecutar manualmente (sin el script)

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Ejecutar con Docker manualmente

```bash
docker compose up --build
```

Para detener:

```bash
docker compose down
```

La imagen no incluye ningún modelo horneado — tanto la transcripción
(ElevenLabs) como la generación (Anthropic) necesitan salida a internet
desde el primer uso.

### Usar documentación real en producción

Por defecto la imagen usa el `memory/` fixture versionado en el repo.
Para apuntar a cualquier carpeta de documentación real en solo lectura,
agrega un override en `docker-compose.yml` (o un
`docker-compose.override.yml`, gitignored):

```yaml
services:
  app:
    volumes:
      - /ruta/al/memory/real:/app/memory_real:ro
    environment:
      MEMORY_DIR: /app/memory_real
```

### Seguridad

El puerto publicado no tiene autenticación. Este empaquetado está
pensado para `localhost` o una red interna de confianza; un proxy
reverso con autenticación queda como opción futura, fuera de alcance
de esta fase.

## Generación (ticket y consulta)

`generar_descripcion.py` devuelve una plantilla Markdown fija, no prosa
libre:

```markdown
## Módulo afectado
<módulo detectado, o "Módulo afectado: no identificado">

## Contexto del módulo
<solo si se encontró documentación relevante>

## Qué pasó
<qué hacía la persona y qué ocurrió>

## Pasos para reproducir
<solo si el analista narró los pasos>

## Resultado esperado vs. obtenido
<solo si el analista dijo qué esperaba>
```

`## Módulo afectado` y `## Qué pasó` están siempre presentes; las demás
secciones se omiten por completo (encabezado y cuerpo) cuando el
analista no mencionó esa información o no se encontró documentación
relevante — nunca se rellenan con texto genérico tipo "no
especificado". Todo el texto de los prompts vive en `prompts.py` (ver
`CLAUDE.md` "Prompt repository convention").

`consultar_documentacion.py` (modo "Consultar documentación") responde
en lenguaje llano, no técnico, y distingue tres estados: una respuesta
directa, una pregunta aclaratoria (cuando la consulta es ambigua o
falta contexto para responder con confianza), o el aviso fijo de "sin
información" (cuando no se encontró documentación relacionada).

## `memory/` — contexto de documentación (sin estructura fija)

`contexto_memoria.py` encuentra **cualquier archivo `.md`** bajo
`MEMORY_DIR`, sin importar su nombre o en qué subcarpeta esté — no
requiere ningún índice ni convención de carpetas particular. Puede
apuntarse a la documentación real de cualquier proyecto, tal cual está.

En vez de un algoritmo de coincidencia de texto propio, la selección de
qué documentos son relevantes para una transcripción la hace **Claude
Haiku 4.5 mismo**: se le manda la transcripción más una lista liviana
(ruta + vista previa breve) de los documentos disponibles, y el modelo
elige cuáles (como máximo 3) conviene inyectar — completos, no
resumidos — como contexto para la generación. Es de **solo lectura**:
la app nunca escribe, crea ni borra nada bajo `MEMORY_DIR`.

Para carpetas grandes, la lista se envía en lotes acotados en tamaño
(`CARACTERES_POR_LOTE`), no todo de una vez, y se re-evalúa entre lotes
para no perder el mejor candidato — verificado contra la documentación
real de Kawak PHP (273 archivos).

La carpeta `memory/` versionada en este repo es un **fixture de
desarrollo/pruebas** (tres documentos de ejemplo:
`gestion_riesgos.md`, `planes_accion.md`, `auditorias_internas.md`, sin
ninguna estructura especial). En un entorno real, `MEMORY_DIR` debe
apuntar a la carpeta de documentación real del proyecto — no se
versiona ni se sube al repo.

Ver `CLAUDE.md` "Context retrieval decision" y "Migración a Claude
Haiku 4.5" para el detalle de las decisiones de arquitectura.

## Tests

```bash
pytest
```

Cubre `transcribir.py`, `generar_descripcion.py`, `contexto_memoria.py`,
`consultar_documentacion.py` y `cliente_anthropic.py` con
clientes/proveedores falsos — sin llamadas de red, sin
`ELEVENLABS_API_KEY` ni `ANTHROPIC_API_KEY` requeridas.
