# Arquitectura interna — NO INYECTAR

SENTINEL: CORE_NUNCA_INYECTAR

Este archivo documenta detalles internos de arquitectura (capas, stack,
decisiones de infraestructura) para uso exclusivo del equipo de
desarrollo. El asistente de voz NUNCA debe leer ni inyectar este
contenido como contexto de generación: solo `modulos/<nombre>/_modulo.md`
es una fuente válida de contexto para `generar_descripcion.py`.

Si esta cadena (`CORE_NUNCA_INYECTAR`) aparece alguna vez en un prompt
enviado a Groq, hay un error grave de alcance en `contexto_memoria.py`.
