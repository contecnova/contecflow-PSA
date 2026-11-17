"""Horario efectivo: jornadas laborales, a quién se aplican y movimientos de saldo (revisión 180).

Tablas:

- `jornadas_laborales`: una jornada (normal, de verano, reducida, partida…)
  con sus tramos por día de la semana (`semana`: JSON {"1": [["09:00",
  "14:00"], ["15:00", "18:00"]], …, "7": []}) y la pausa no retribuida.
- `asignaciones_de_jornada`: a quién se aplica una jornada (empresa, sede,
  departamento, equipo, grupo o persona), con vigencia (desde/hasta, o cada
  año entre esas fechas: la jornada de verano) y prioridad. Gana la de mayor
  prioridad; a igualdad, la más concreta (persona > grupo > equipo >
  departamento > sede > empresa) y, después, la temporal sobre la permanente.
- `movimientos_de_saldo`: lo que suma o resta a un saldo fuera de las
  ausencias: ajustes manuales de RRHH, horas que entran en la bolsa por exceso
  imputado (`origen = bolsa`, una fila por persona, tipo y día: idempotente) y
  su caducidad.

El horario de cada persona y día lo calcula `app/services/horario/` (la única
fuente: planificador, cargas, reservas, previsión, ausencias y saldos). Los
campos JSON los escribe la pantalla, nunca una persona.
"""
import uuid

from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


def _id():
    return Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))


def _org():
    return Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)


class JornadaLaboral(Base):
    __tablename__ = "jornadas_laborales"

    id = _id()
    organization_id = _org()
    nombre = Column(String(120), nullable=False)
    nombres = Column(Text, nullable=True)                       # JSON {es, en, zh}
    color = Column(String(9), nullable=False, default="#4f8cff")
    semana = Column(Text, nullable=False)                       # JSON {"1".."7": [[inicio, fin], …]}
    pausa_minutos = Column(Integer, nullable=False, default=0)  # no retribuida, por día con horario
    activo = Column(Boolean, nullable=False, default=True)
    orden = Column(Integer, nullable=False, default=100)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    asignaciones = relationship("AsignacionDeJornada", cascade="all, delete-orphan", lazy="selectin",
                                back_populates="jornada")


class AsignacionDeJornada(Base):
    __tablename__ = "asignaciones_de_jornada"

    id = _id()
    organization_id = _org()
    jornada_id = Column(String(36), ForeignKey("jornadas_laborales.id", ondelete="CASCADE"), nullable=False, index=True)
    ambito = Column(String(14), nullable=False, default="empresa")  # empresa|sede|departamento|equipo|grupo|persona
    valor = Column(String(160), nullable=True)                      # id de sede, grupo o persona; nombre de dpto./equipo
    desde = Column(Date, nullable=True)
    hasta = Column(Date, nullable=True)
    recurrente_anual = Column(Boolean, nullable=False, default=False)  # cada año entre desde y hasta (mes/día)
    prioridad = Column(Integer, nullable=False, default=0)
    nota = Column(String(255), nullable=True)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    jornada = relationship("JornadaLaboral", back_populates="asignaciones")


class MovimientoDeSaldo(Base):
    """Un apunte en un saldo: `saldo_clave` = «vacaciones» o el id del tipo de ausencia."""
    __tablename__ = "movimientos_de_saldo"
    __table_args__ = (
        UniqueConstraint("user_id", "saldo_clave", "origen", "referencia", name="uq_movimientos_de_saldo_ref"),
    )

    id = _id()
    organization_id = _org()
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    saldo_clave = Column(String(60), nullable=False, index=True)
    fecha = Column(Date, nullable=False, index=True)              # desde cuándo cuenta
    cantidad = Column(Float, nullable=False)                      # en la unidad del saldo (+ suma, − resta)
    unidad = Column(String(8), nullable=False, default="dias")   # dias | horas
    origen = Column(String(12), nullable=False, default="manual")  # manual | bolsa
    referencia = Column(String(80), nullable=True)                # bolsa: «tipo:fecha» (idempotente)
    caduca = Column(Date, nullable=True)
    nota = Column(String(500), nullable=True)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
