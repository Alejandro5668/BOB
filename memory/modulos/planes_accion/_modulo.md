# Módulo: Planes de Acción

## Propósito

Da seguimiento a los planes de acción derivados de hallazgos de auditoría
interna o de riesgos identificados en el módulo de gestión de riesgos.
Cada plan tiene tareas, responsables, fechas límite y evidencia de cierre.

## Comportamiento documentado

- Un plan de acción puede originarse desde un hallazgo de auditoría o
  desde un riesgo; el origen queda registrado y no se puede editar luego
  de creado el plan.
- Cada tarea del plan tiene un estado individual (pendiente, en progreso,
  cerrada); el plan completo solo pasa a "cerrado" cuando todas sus
  tareas están cerradas y tienen evidencia adjunta.
- El sistema envía un recordatorio automático al responsable cuando una
  tarea se acerca a su fecha límite, según la configuración de
  notificaciones del usuario.
- La vista de tablero agrupa los planes por estado y por responsable,
  no por fecha de vencimiento.

## Notas de soporte conocidas

- Si una tarea no permite adjuntar evidencia, normalmente el plan ya fue
  marcado como cerrado por otro usuario y quedó en modo de solo lectura.
- Los recordatorios automáticos dependen del servicio de notificaciones;
  si un analista no los recibe, primero se revisa su configuración
  personal de notificaciones antes de escalar como una falla del módulo.
