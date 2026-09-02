# Auditorías internas

## Propósito

Programa, ejecuta y cierra auditorías internas institucionales. Cada
auditoría agrupa hallazgos con su evidencia asociada y, opcionalmente,
planes de acción de seguimiento en el módulo correspondiente.

## Comportamiento documentado

- Una auditoría pasa por los estados: programada, en ejecución, en
  revisión y cerrada; el cambio de estado solo lo puede hacer el
  responsable asignado o un administrador.
- Cada hallazgo requiere al menos una evidencia adjunta antes de poder
  marcarse como "confirmado".
- El cronograma de auditorías se construye a partir del plan anual
  cargado al inicio de año; auditorías fuera de plan requieren
  aprobación adicional antes de programarse.
- El cierre de una auditoría genera automáticamente un resumen en PDF
  con los hallazgos confirmados y su estado de seguimiento.

## Notas de soporte conocidas

- Si el resumen en PDF no se genera al cerrar, normalmente hay un
  hallazgo sin evidencia confirmada bloqueando la generación.
- Las auditorías fuera de plan que no fueron aprobadas quedan visibles
  solo para el responsable que las creó, no para todo el equipo.
