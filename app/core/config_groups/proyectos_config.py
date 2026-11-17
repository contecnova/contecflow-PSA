"""
Proyectos: planificador (calendario laboral, camino crítico), nivelación de
recursos, curva S de valor ganado y cartera.

Referenced by:
  - app/services/planificador (CPM, calendarios, cascada, nivelación)
  - app/services/evm_service (valor ganado y snapshots de la curva S)
  - app/services/cartera_service (intake y puntuación de propuestas)

Todos se pueden cambiar en caliente por empresa desde Configuración (grupo
«proyectos» de `settings_service/_catalogo.py`); el valor de aquí es el de la
instalación cuando la empresa no ha dicho nada.

NOTE: This is a *mixin* — see `app.core.config_groups` package docstring.
"""
from pydantic import Field


class ProyectosSettingsMixin:
    # ── Calendario laboral de la empresa ──────────────────────────────────────
    # Días laborables ISO (1 = lunes … 7 = domingo), separados por comas. Las
    # horas por día salen de DEFAULT_WORKING_HOURS_PER_DAY y los festivos de la
    # tabla `holidays` (los que no llevan `applies_to`).
    PLANNING_WORKDAYS: str = Field(default="1,2,3,4,5", env="PLANNING_WORKDAYS")
    # Rev. 180: días hacia delante con el horario efectivo de cada persona (turnos,
    # jornadas, festivos de su sede, ausencias) en su calendario; más allá, el
    # patrón de la empresa con su jornada media.
    PLANNING_SCHEDULE_HORIZON_DAYS: int = Field(default=400, env="PLANNING_SCHEDULE_HORIZON_DAYS")

    # ── Camino crítico ────────────────────────────────────────────────────────
    # Una tarea es crítica con holgura total <= este valor (días laborables).
    PLANNING_CRITICAL_FLOAT_DAYS: float = Field(default=0.0, env="PLANNING_CRITICAL_FLOAT_DAYS")
    # «Casi crítica»: holgura total <= este valor (se marca en el Gantt).
    PLANNING_NEAR_CRITICAL_FLOAT_DAYS: float = Field(default=3.0, env="PLANNING_NEAR_CRITICAL_FLOAT_DAYS")
    # Recalcular el plan al mover fechas, dependencias o estimaciones.
    PLANNING_AUTO_RECALCULATE: bool = Field(default=True, env="PLANNING_AUTO_RECALCULATE")

    # ── Nivelación de recursos ────────────────────────────────────────────────
    # Sobreasignación: carga diaria por encima de este % de la jornada de la persona.
    LEVELING_OVERALLOCATION_PCT: float = Field(default=100.0, env="LEVELING_OVERALLOCATION_PCT")
    # Ventana (días naturales) que mira la nivelación hacia delante.
    LEVELING_HORIZON_DAYS: int = Field(default=120, env="LEVELING_HORIZON_DAYS")

    # ── Alertas de recursos ───────────────────────────────────────────────────
    # Infrautilización: carga media por debajo de este % de la capacidad.
    RESOURCE_UNDERUSE_PCT: float = Field(default=50.0, env="RESOURCE_UNDERUSE_PCT")
    # Semanas que miran las pantallas de disponibilidad y alertas.
    RESOURCE_AVAILABILITY_WEEKS: int = Field(default=8, env="RESOURCE_AVAILABILITY_WEEKS")

    # ── Valor ganado (EVM) ────────────────────────────────────────────────────
    # Guardar cada día un punto de la curva S de cada proyecto activo.
    EVM_SNAPSHOTS_ENABLED: bool = Field(default=True, env="EVM_SNAPSHOTS_ENABLED")
    # Puntos de la curva S que devuelve la API (los más recientes).
    EVM_CURVE_MAX_POINTS: int = Field(default=365, env="EVM_CURVE_MAX_POINTS")

    # ── Cartera ───────────────────────────────────────────────────────────────
    # Puntuación mínima (0-100) para que una propuesta pueda pasar de fase.
    PORTFOLIO_MIN_SCORE_TO_ADVANCE: float = Field(default=50.0, env="PORTFOLIO_MIN_SCORE_TO_ADVANCE")
