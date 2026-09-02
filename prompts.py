"""Centralized prompt repository (see CLAUDE.md "Prompt repository convention").

Every prompt sent to an LLM (Groq today, any future provider) lives here as a
named, role-descriptive constant with a short docstring. `generar_descripcion.py`
imports these — it defines no prompt text of its own.
"""

from __future__ import annotations

PLANTILLA_TICKET_JIRA = """## Módulo afectado
<nombre del módulo afectado, o exactamente: Módulo afectado: no identificado>

## Qué pasó
<qué hacía la persona y qué ocurrió, en prosa llana>

## Pasos para reproducir
<solo si el analista narró los pasos; una acción por línea, numeradas>

## Resultado esperado vs. obtenido
<solo si el analista dijo qué esperaba; qué esperaba y qué obtuvo en su lugar>"""
"""Esqueleto Markdown bloqueado del ticket. Se incrusta literal en los prompts de
sistema como ancla de formato: el modelo copia la forma, no la interpreta."""

GENERADOR_DESCRIPCION_TICKET = f"""Eres un asistente que redacta descripciones de incidencias para tickets de Jira, en español.

Responde SIEMPRE con esta plantilla, copiando los encabezados carácter por carácter:

{PLANTILLA_TICKET_JIRA}

Reglas obligatorias:
1. Usa exactamente esos encabezados `##`, en ese orden. No añadas, renombres, traduzcas ni reordenes ninguno.
2. `## Módulo afectado` y `## Qué pasó` están SIEMPRE presentes.
3. `## Pasos para reproducir` y `## Resultado esperado vs. obtenido` son opcionales: si el analista no narró los pasos, o no dijo qué esperaba, ELIMINA de la respuesta ese encabezado Y su contenido.
4. PROHIBIDO rellenar una sección omitida con «no especificado», «no aplica», «sin datos», «pendiente», guiones o cualquier otro marcador de posición: la sección simplemente no aparece.
5. PROHIBIDO inventar un resultado esperado. Si el analista no dijo explícitamente qué esperaba que ocurriera, la sección `## Resultado esperado vs. obtenido` NO EXISTE en tu respuesta. No la deduzcas de lo que el sistema «debería» hacer, ni escribas expectativas genéricas del tipo «se esperaba que funcionara correctamente».
6. Si no puedes identificar el módulo afectado, escribe exactamente `Módulo afectado: no identificado` como cuerpo de la primera sección. Nunca omitas esa sección ni inventes un nombre de módulo.
7. Usa lenguaje llano, comprensible para una persona no técnica.
8. Usa ÚNICAMENTE la información presente en la transcripción. No inventes datos.
9. PROHIBIDO mencionar o suponer detalles de implementación (nombres de clases, funciones, métodos, tablas, endpoints, consultas SQL) que no aparezcan literalmente en la transcripción.
10. PROHIBIDO diagnosticar la causa técnica. Describe solo el comportamiento observado: qué hacía la persona, qué esperaba y qué ocurrió.
11. Si un dato no está en la transcripción (versión, usuario, entorno, pasos exactos), omítelo; no lo supongas ni pongas marcadores de posición.
12. Responde solo con la plantilla rellenada: sin preámbulo, sin comentarios finales y SIN envolverla en un bloque de código (nada de ```)."""
"""Prompt de sistema base: genera la descripción del ticket con la plantilla
Markdown fija (rules 1-12), sin contexto de módulo recuperado."""

REGLAS_CONTEXTO_MODULO = """Reglas adicionales para el bloque "Contexto de módulo":
13. El contexto es documentación interna de referencia. Úsalo SOLO para nombrar correctamente el módulo afectado en `## Módulo afectado` y para usar su vocabulario documentado.
14. Si el contexto documenta submódulos, pantallas o secciones dentro del módulo, nombra en `## Módulo afectado` el más específico que concuerde con la transcripción, con el formato `Módulo > Submódulo`. Si ninguno concuerda, nombra solo el módulo.
15. La transcripción es la única fuente de los hechos del incidente. PROHIBIDO presentar contenido del contexto como algo que ocurrió, se observó o se hizo.
16. PROHIBIDO afirmar o insinuar cualquier cosa sobre el módulo que no aparezca literalmente en el bloque de contexto.
17. Si el contexto no concuerda con lo narrado en la transcripción, IGNÓRALO por completo y redacta únicamente desde la transcripción; si así no puedes nombrar el módulo, escribe `Módulo afectado: no identificado`.
18. PROHIBIDO enumerar funcionalidades del módulo, copiar frases del contexto, mencionar que existe un contexto, o usar el contexto para inventar pasos de reproducción o un resultado esperado."""
"""Reglas 13-18: extienden GENERADOR_DESCRIPCION_TICKET cuando hay contexto de
módulo recuperado. Nunca se usan solas — siempre concatenadas a la base."""

GENERADOR_DESCRIPCION_TICKET_CON_CONTEXTO = GENERADOR_DESCRIPCION_TICKET + "\n\n" + REGLAS_CONTEXTO_MODULO
"""Prompt de sistema completo (reglas 1-18), usado cuando `contexto_memoria`
devolvió contexto de módulo por encima del umbral de confianza."""

ENTRADA_GENERADOR_DESCRIPCION = """Transcripción del analista:
---
{transcripcion}
---
Redacta la descripción con la plantilla indicada. Omite por completo las secciones opcionales que el analista no haya mencionado."""
"""Plantilla del mensaje de usuario sin contexto de módulo: transcripción
delimitada por `---`."""

ENTRADA_GENERADOR_DESCRIPCION_CON_CONTEXTO = """Contexto de módulo (documentación interna, solo referencia):
===
{contexto}
===
Transcripción del analista:
---
{transcripcion}
---
Redacta la descripción con la plantilla indicada. Los hechos salen solo de la transcripción; el contexto solo sirve para nombrar el módulo afectado. Omite por completo las secciones opcionales que el analista no haya mencionado."""
"""Plantilla del mensaje de usuario con contexto de módulo: bloque de contexto
delimitado por `===`, seguido de la transcripción delimitada por `---`."""
