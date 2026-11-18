"""Horas extra y trabajo fuera de horario, aprobados por flujos (18-11-2026, rev. 184).

Nada es un motor nuevo: se apoya en lo que ya existe.

  · config.py      — configuración por empresa (activo, control al imputar, tolerancia,
                     compensaciones, flujo, tipo de bolsa) y presupuestos de horas
  · calculo.py     — el día de la persona sobre el horario efectivo (`app/services/horario`):
                     clase de día, horas fuera de horario, exceso imputado, acumulados,
                     descanso entre jornadas, días seguidos y presupuesto restante
  · reglas.py      — el CONTEXTO del dominio `horas_extra` del motor de políticas
                     (`app/services/politicas/dominios/horas_extra.py`): los límites
                     (diarios, semanales, mensuales, anuales —el máximo legal español de
                     80 h/año es una regla de ejemplo editable—), antelación, descanso,
                     días seguidos, presupuesto, quién pide, factores, motivo, sustituto
                     y niveles extra de aprobación se escriben en pantalla, sin código
  · solicitudes.py — el ciclo: pedir (previa), declarar (posterior), vista previa,
                     aprobar por el motor de aprobaciones (`overtime`: niveles, grupos,
                     escalado por timeout, aprobación por correo), revisar, cancelar,
                     editar, compensar (bolsa de horas o pago) y liquidar
  · control.py     — lo que pasa al imputar fuera de horario sin autorización (bloquear,
                     avisar o dejar una declaración pendiente de regularizar)
  · consultas.py   — visibilidad (mínimo privilegio), listas, ciclo completo, bandeja,
                     resumen frente a límites, horas sin autorizar y nómina
  · ejemplos.py    — reglas de ejemplo (BORRADORES: nunca se aplican solas)

GRC: todo cambio de estado deja evento y `audit_log`; las reglas se auditan en
Políticas; segregación (nadie aprueba lo suyo ni lo que pidió para otro);
retención y bloqueo legal (`overtime_requests` en `app/db/bloqueo_legal.py`);
RGPD acceso/portabilidad (`cab_service/gdpr.py`); dos controles en el informe
de cumplimiento (`overtime_limits`, `overtime_unauthorized`).
"""
