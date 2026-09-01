# Decisiones técnicas — NO INYECTAR

SENTINEL: DECISIONES_NUNCA_INYECTAR

Bitácora interna de decisiones técnicas del equipo (elección de stack,
proveedores, convenciones de código). No describe comportamiento de un
módulo y NUNCA debe inyectarse como contexto de generación.

Si esta cadena (`DECISIONES_NUNCA_INYECTAR`) aparece alguna vez en un
prompt enviado a Groq, hay un error grave de alcance en
`contexto_memoria.py`.
