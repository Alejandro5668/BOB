# Gestión de riesgos

## Propósito

Permite registrar, valorar y hacer seguimiento a los riesgos institucionales
de la organización. Cada riesgo se documenta con su probabilidad e impacto,
y el módulo calcula automáticamente su nivel de exposición según la matriz
de riesgos configurada.

## Comportamiento documentado

- La pantalla principal muestra un listado de riesgos con filtros por
  proceso, responsable y nivel de exposición.
- La matriz de riesgos (mapa de calor probabilidad/impacto) se recalcula
  cada vez que se guarda una valoración nueva o editada.
- Cada riesgo puede tener uno o más planes de acción asociados; el estado
  del riesgo no cambia automáticamente cuando un plan de acción se cierra.
- La exportación a Excel incluye todos los riesgos visibles según el
  filtro activo, no solo la página actual.
- El módulo depende de que el catálogo de procesos institucionales esté
  cargado; sin catálogo, la creación de un riesgo nuevo queda deshabilitada.

## Notas de soporte conocidas

- Si la matriz no carga, suele deberse a un riesgo con probabilidad o
  impacto sin valorar (campo vacío rompe el cálculo de color de celda).
- El listado pagina de a 25 riesgos; si un analista busca uno que no
  aparece, primero se debe revisar si hay un filtro de proceso activo.
