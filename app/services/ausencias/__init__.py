"""Ausencias gobernadas por reglas (tarea #25, revisión 167).

Piezas:

- `catalogo`: tipos de ausencia y de documento, requisitos documentales,
  acceso especial (RGPD art. 9).
- `turnos`: turnos, rotaciones, cambios por día, festivos y cobertura.
- `cupos`: plazas por (cupo, día, turno, grupo) con bloqueo de fila y lista de
  espera por orden de llegada.
- `solicitudes`: el ciclo de vida (vista previa, pedir, decidir, cancelar,
  ampliar), sobre el motor de políticas (`dominio ausencias`) y el motor de
  aprobaciones (`leave`).
- `documentos`: documentos adjuntos durante toda la vida de la ausencia,
  plazos, recordatorios y escalado, con acceso restringido y auditado.
- `ejemplos`: el ejemplo de tres turnos con cupo de dos y lista de espera
  (se carga a mano; nunca se aplica solo).

El dominio del motor está en `app/services/politicas/dominios/ausencias.py`.
"""
