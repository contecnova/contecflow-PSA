from datetime import date
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator


class AbsenceIn(BaseModel):
    """Una petición de ausencia. `type` (clave, API antiguo) o `absence_type_id` (tipo configurable, rev. 167)."""
    type: Optional[str] = Field(None, description="Clave del tipo (vacation, sick… o una propia)")
    absence_type_id: Optional[str] = Field(None, description="Id del tipo configurable")
    start_date: date = Field(..., description="Fecha de inicio de la ausencia")
    end_date: date = Field(..., description="Fecha de fin de la ausencia")
    reason: Optional[str] = Field(None, description="Motivo o justificación de la ausencia")
    shift_id: Optional[str] = Field(None, description="Turno (si se pide para un turno concreto)")
    substitute_id: Optional[str] = Field(None, description="Sustituto")
    half_day_start: bool = Field(False, description="Medio día el primer día")
    half_day_end: bool = Field(False, description="Medio día el último día")
    hours: Optional[float] = Field(None, gt=0, description="Horas sin franja (compatibilidad; mejor start_time/end_time)")
    modo: Optional[str] = Field(None, description="dias | horas (rev. 180); por defecto, según la franja o la unidad del tipo")
    start_time: Optional[str] = Field(None, description="Por horas: hora de inicio de la franja de cada día (HH:MM)")
    end_time: Optional[str] = Field(None, description="Por horas: hora de fin (HH:MM; menor que el inicio = cruza la medianoche)")
    id: Optional[str] = Field(None, description="Solo en la vista previa de una edición")

    @model_validator(mode="after")
    def _un_tipo(self):
        if not self.type and not self.absence_type_id:
            raise ValueError("Indica el tipo de ausencia")
        return self


class AbsenceReview(BaseModel):
    approved: bool = Field(..., description="Indica si la ausencia ha sido aprobada")
    rejection_reason: Optional[str] = Field(None, description="Motivo del rechazo en caso de no ser aprobada")


class TipoDeAusenciaIn(BaseModel):
    clave: str
    nombre: Optional[str] = None
    nombres: dict[str, str] = Field(default_factory=dict)
    color: Optional[str] = None
    icono: Optional[str] = None
    descuenta_saldo: bool = False
    saldo: Optional[str] = None
    cupo_anual: Optional[float] = None
    unidad: str = "dias"
    visibilidad: str = "equipo"
    workflow_id: Optional[str] = None
    requiere_aprobacion: bool = True
    requiere_sustituto: bool = False
    datos_especiales: bool = False
    activo: bool = True
    orden: Optional[int] = None
    requisitos: Optional[list[dict[str, Any]]] = None
    # Rev. 180: modos de petición, retribución, periodo, arrastre, caducidad, prorrateo, tabla y bolsa.
    modos: list[str] = Field(default_factory=list)
    retribuido: bool = True
    periodo_saldo: Optional[str] = None
    inicio_periodo_mes: Optional[int] = None
    arrastre_max: Optional[float] = None
    arrastre_caduca_meses: Optional[int] = None
    caduca_meses: Optional[int] = None
    prorratear_alta: bool = False
    derecho_tabla_id: Optional[str] = None
    bolsa: Optional[dict[str, Any]] = None


class TipoDeDocumentoIn(BaseModel):
    clave: str
    nombre: Optional[str] = None
    nombres: dict[str, str] = Field(default_factory=dict)
    categoria_especial: bool = False
    activo: bool = True
    orden: Optional[int] = None


class TurnoIn(BaseModel):
    nombre: str
    color: Optional[str] = None
    hora_inicio: Optional[str] = None
    hora_fin: Optional[str] = None
    tramos: list[list[str]] = Field(default_factory=list, description="Turno partido: [[inicio, fin], …]")
    pausa_minutos: int = Field(0, ge=0)
    dias_semana: list[int] = Field(default_factory=list)
    equipo: Optional[str] = None
    departamento: Optional[str] = None
    office_id: Optional[str] = None
    personas_requeridas: int = 0
    trabaja_festivos: bool = False
    activo: bool = True
    orden: Optional[int] = None


class MiembroIn(BaseModel):
    user_id: str
    desde: date
    hasta: Optional[date] = None
    desfase: int = 0


class PatronIn(BaseModel):
    nombre: str
    ciclo: list[Optional[str]]
    inicio: date
    activo: bool = True
    miembros: list[MiembroIn] = Field(default_factory=list)


class CambioDeTurnoIn(BaseModel):
    user_id: str
    fecha: date
    turno_id: Optional[str] = None
    quitar: bool = False
    nota: Optional[str] = None


class CuadranteIn(BaseModel):
    cambios: list[CambioDeTurnoIn]


class PedirDocumentoIn(BaseModel):
    tipo_id: str
    vence: date
    nota: Optional[str] = None


class NotaIn(BaseModel):
    nota: Optional[str] = None


class AmpliarIn(BaseModel):
    end_date: date
    nota: Optional[str] = None


class AccesoEspecialIn(BaseModel):
    user_id: str


# ── Rev. 180: jornadas, ficha laboral, ajustes de saldo, bolsa ───────────────

class JornadaIn(BaseModel):
    nombre: Optional[str] = None
    nombres: dict[str, str] = Field(default_factory=dict)
    color: Optional[str] = None
    semana: dict[str, list[list[str]]] = Field(default_factory=dict, description='{"1": [["09:00","14:00"], …], …, "7": []}')
    pausa_minutos: int = Field(0, ge=0)
    activo: bool = True
    orden: Optional[int] = None


class AsignacionDeJornadaIn(BaseModel):
    jornada_id: str
    ambito: str = Field("empresa", description="empresa | sede | departamento | equipo | grupo | persona")
    valor: Optional[str] = None
    desde: Optional[date] = None
    hasta: Optional[date] = None
    recurrente_anual: bool = False
    prioridad: int = 0
    nota: Optional[str] = None


class FichaLaboralIn(BaseModel):
    office_id: Optional[str] = None
    hire_date: Optional[date] = None
    employment_type: Optional[str] = Field(None, max_length=40)


class MovimientoDeSaldoIn(BaseModel):
    user_id: str
    saldo_clave: str = Field(..., description="«vacaciones» o el id del tipo con saldo propio o bolsa")
    cantidad: float
    unidad: Optional[str] = None
    fecha: Optional[date] = None
    caduca: Optional[date] = None
    nota: str = Field(..., min_length=1, max_length=500)


class RecalcularBolsaIn(BaseModel):
    desde: date
    hasta: date
    user_ids: Optional[list[str]] = None
