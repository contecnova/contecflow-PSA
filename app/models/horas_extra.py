"""Horas extra y trabajo fuera de horario, aprobados por flujos (18-11-2026, rev. 184).

Tablas:

- `config_horas_extra`: una fila por empresa. Si el módulo está activo, qué
  pasa al imputar fuera de horario sin autorización (`control_imputacion`:
  ninguno | avisar | regularizar | bloquear), la tolerancia en minutos, las
  compensaciones que se pueden elegir (pago, bolsa, ninguna) y la de por
  defecto, el flujo de aprobación (`approval_workflows`, tipo `overtime`), el
  tipo de ausencia que hace de bolsa de horas, si un responsable puede pedir
  para su equipo y si el motivo es obligatorio. Los LÍMITES no están aquí: son
  reglas del motor de políticas (dominio `horas_extra`), editables en pantalla.
- `peticiones_de_horas_extra`: cada petición. `origen` previa (autorización
  antes de hacerlas) o posterior (exceso detectado en la imputación que queda
  pendiente de regularizar). Guarda lo pedido, lo autorizado, la compensación
  y su factor, el estado, quién decidió y la liquidación del pago.
- `eventos_de_horas_extra`: la línea de tiempo (creada, declarada, en
  aprobación, voto, aprobada, rechazada, cancelada, recalculada, anulada,
  incumple, compensada en bolsa, liquidada).
- `presupuestos_de_horas_extra`: horas extra disponibles por empresa,
  departamento, equipo o proyecto, al mes o al año.

Toda la lógica vive en `app/services/horas_extra/`.
"""
import uuid

from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Text, Time, UniqueConstraint
from sqlalchemy.sql import func

from app.db.base import Base


def _id():
    return Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))


def _org():
    return Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)


class ConfigDeHorasExtra(Base):
    __tablename__ = "config_horas_extra"
    __table_args__ = (UniqueConstraint("organization_id", name="uq_config_horas_extra_org"),)

    id = _id()
    organization_id = _org()
    activo = Column(Boolean, nullable=False, default=True)  # activado por defecto (18-11-2026)
    control_imputacion = Column(String(12), nullable=False, default="avisar")   # ninguno|avisar|regularizar|bloquear
    tolerancia_minutos = Column(Integer, nullable=False, default=15)
    compensaciones = Column(Text, nullable=True)                                 # JSON ["pago","bolsa","ninguna"]
    compensacion_por_defecto = Column(String(10), nullable=False, default="bolsa")
    workflow_id = Column(String(36), ForeignKey("approval_workflows.id", ondelete="SET NULL"), nullable=True,
                         index=True)
    tipo_bolsa_id = Column(String(36), ForeignKey("tipos_de_ausencia.id", ondelete="SET NULL"), nullable=True,
                           index=True)
    pedir_en_nombre = Column(Boolean, nullable=False, default=True)
    exigir_motivo = Column(Boolean, nullable=False, default=True)
    updated_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PeticionDeHorasExtra(Base):
    __tablename__ = "peticiones_de_horas_extra"

    id = _id()
    organization_id = _org()
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    solicitante_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    origen = Column(String(10), nullable=False, default="previa")              # previa | posterior
    tipo = Column(String(16), nullable=False)                                   # laborable|fuera_de_franja|festivo|no_laborable|guardia
    clase_dia = Column(String(14), nullable=True)                               # laborable | festivo | no_laborable
    fecha = Column(Date, nullable=False, index=True)
    hora_inicio = Column(Time, nullable=True)
    hora_fin = Column(Time, nullable=True)
    horas = Column(Float, nullable=False)
    horas_autorizadas = Column(Float, nullable=True)
    motivo = Column(Text, nullable=True)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    ticket_id = Column(String(36), nullable=True)
    sustituto_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    compensacion = Column(String(10), nullable=False, default="bolsa")          # pago | bolsa | ninguna
    factor = Column(Float, nullable=False, default=1.0)
    estado = Column(String(12), nullable=False, default="pendiente", index=True)  # pendiente|aprobada|rechazada|cancelada
    avisos = Column(Text, nullable=True)                                        # JSON {avisos:[], bloqueos:[]}
    decidido_por = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    decidido_en = Column(DateTime(timezone=True), nullable=True)
    motivo_rechazo = Column(String(500), nullable=True)
    liquidada_en = Column(DateTime(timezone=True), nullable=True)
    liquidada_por = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    referencia_pago = Column(String(120), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class EventoDeHorasExtra(Base):
    __tablename__ = "eventos_de_horas_extra"

    id = _id()
    organization_id = _org()
    peticion_id = Column(String(36), ForeignKey("peticiones_de_horas_extra.id", ondelete="CASCADE"), nullable=False,
                         index=True)
    tipo = Column(String(30), nullable=False)
    actor_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    datos = Column(Text, nullable=True)                                         # JSON
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


class PresupuestoDeHorasExtra(Base):
    __tablename__ = "presupuestos_de_horas_extra"

    id = _id()
    organization_id = _org()
    ambito = Column(String(14), nullable=False)                                  # empresa|departamento|equipo|proyecto
    valor = Column(String(160), nullable=True)
    periodo = Column(String(6), nullable=False, default="anio")                 # mes | anio
    anio = Column(Integer, nullable=True)                                        # vacío: todos los años
    horas = Column(Float, nullable=False)
    nota = Column(String(255), nullable=True)
    activo = Column(Boolean, nullable=False, default=True)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
