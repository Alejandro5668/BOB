# Índice de módulos — memory/

Este archivo es el índice de módulos disponibles para el asistente de voz.
Cada línea describe un módulo real de Kawak: nombre de carpeta (debe
coincidir con `modulos/<nombre>/`), alias en lenguaje natural que un
analista podría usar al hablar, y una descripción breve en prosa. El
contenido completo de cada módulo vive en `modulos/<nombre>/_modulo.md`;
este índice NUNCA se inyecta como contexto de generación, solo se usa
para localizar y puntuar módulos.

Formato de cada línea (una por módulo):

```
- **<nombre_carpeta>** (alias: <alias 1>, <alias 2>, ...) — <descripción>
```

- **gestion_riesgos** (alias: riesgos, matriz de riesgos, mapa de riesgos) — Registro, valoración y seguimiento de riesgos institucionales por probabilidad e impacto, con matriz de riesgos consolidada.
- **planes_accion** (alias: planes de acción, plan de accion, seguimiento de acciones) — Seguimiento de planes de acción y tareas derivadas de hallazgos de auditoría o de la gestión de riesgos.
- **auditorias_internas** (alias: auditorias, auditoria interna, programa de auditoria) — Programación, ejecución y cierre de auditorías internas, con hallazgos y evidencias asociadas.
