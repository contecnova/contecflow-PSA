"""Horario efectivo de una persona en un día (rev. 180): la única fuente de verdad.

  · tramos.py   — aritmética pura de tramos horarios (partidos, que cruzan la medianoche)
  · efectivo.py — el horario de cada persona y día: cuadrante > rotación > jornada > empresa,
                  menos festivos (empresa y sede), fuera de contrato y ausencias (también por horas)
  · jornadas.py — jornadas laborales y a quién se aplican, ficha laboral (sede, alta, contrato)
                  y la rejilla persona×día

Lo usan el planificador (CPM, carga, nivelación), reservas, capacidad, previsión,
ausencias (días que cuentan, horas de una petición), cupos por franja y saldos.
"""
