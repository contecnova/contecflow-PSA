"""Ausencias gobernadas por reglas: tipos, turnos, cupos y documentos (tarea #25, revisión 167).

Tablas:

- `tipos_de_ausencia`: los tipos configurables (antes el enum `AbsenceType`).
  Nombre por idioma, color, icono, si descuenta saldo (de vacaciones o con un
  cupo anual propio) y en qué unidad (días, medios días, horas), visibilidad,
  flujo por defecto, si exige sustituto y si sus datos son de categoría
  especial (RGPD art. 9: bajas médicas).
- `tipos_de_documento_de_ausencia` y `requisitos_documentales_de_tipo`: qué
  documentos pide cada tipo, con su plazo, recordatorio, repetición (el parte
  de confirmación cada N días) y a quién se escala si falta.
- `turnos`, `patrones_de_turnos`, `miembros_de_patron`, `asignaciones_de_turno`:
  definición de turnos, rotaciones y cambios puntuales por día (el cuadrante).
- `huecos_de_cupo` y `reservas_de_cupo`: el contador por (cupo, día, turno,
  grupo) que se bloquea con `SELECT … FOR UPDATE` al asignar plazas, y quién
  ocupa o espera en cada uno (lista de espera por orden de petición).
- `documentos_de_ausencia`, `requisitos_de_ausencia`: los documentos adjuntos
  durante toda la vida de la ausencia (versionados, sobre el almacén de
  documentos de siempre) y lo que se pide con su vencimiento.
- `eventos_de_ausencia`: la línea de tiempo (pedida, en espera, promovida,
  aprobada, documento, recordatorio, escalado…).
- `acceso_especial_ausencias`: quién, además de la persona y RRHH, puede ver
  los documentos de categoría especial (un administrador solo si está aquí).

Las configuraciones se editan SOLO desde la pantalla de Ausencias; los pocos
campos JSON (días de la semana, ciclo de una rotación, nombres por idioma,
destinatarios de escalado) los escribe la pantalla, nunca una persona.
"""
import uuid

from sqlalchemy import (Boolean, Column, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, Time,
                        UniqueConstraint)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


def _id():
    return Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))


def _org():
    return Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)


class TipoDeAusencia(Base):
    __tablename__ = "tipos_de_ausencia"
    __table_args__ = (UniqueConstraint("organization_id", "clave", name="uq_tipos_de_ausencia_org_clave"),)

    id = _id()
    organization_id = _org()
    clave = Column(String(50), nullable=False)                 # lo que guarda `absences.type` (compatibilidad)
    nombre = Column(String(120), nullable=False)
    nombres = Column(Text, nullable=True)                      # JSON {es, en, zh}
    color = Column(String(9), nullable=False, default="#4f8cff")
    icono = Column(String(40), nullable=False, default="umbrella")
    descuenta_saldo = Column(Boolean, nullable=False, default=False)
    saldo = Column(String(12), nullable=True)                  # vacaciones | propio
    cupo_anual = Column(Float, nullable=True)                  # con saldo «propio», en la unidad del tipo
    unidad = Column(String(12), nullable=False, default="dias")  # dias | medios_dias | horas
    visibilidad = Column(String(12), nullable=False, default="equipo")  # todos | equipo | privada
    workflow_id = Column(String(36), ForeignKey("approval_workflows.id", ondelete="SET NULL"), nullable=True, index=True)
    requiere_aprobacion = Column(Boolean, nullable=False, default=True)
    requiere_sustituto = Column(Boolean, nullable=False, default=False)
    datos_especiales = Column(Boolean, nullable=False, default=False)   # RGPD art. 9 (salud)
    activo = Column(Boolean, nullable=False, default=True)
    orden = Column(Integer, nullable=False, default=100)
    de_sistema = Column(Boolean, nullable=False, default=False)         # vino del enum antiguo
    # Rev. 180: modos de petición, retribución, periodo del saldo, arrastre,
    # caducidad, prorrateo por fecha de alta, derecho desde una tabla de
    # referencia (país/convenio) y reglas de la bolsa de horas.
    modos = Column(Text, nullable=True)                                  # JSON ["dias","medio_dia","horas"]
    retribuido = Column(Boolean, nullable=False, default=True)
    periodo_saldo = Column(String(12), nullable=False, default="anual")  # anual|semestral|trimestral|mensual|sin_periodo
    inicio_periodo_mes = Column(Integer, nullable=False, default=1)
    arrastre_max = Column(Float, nullable=True)                          # sin valor: no se arrastra
    arrastre_caduca_meses = Column(Integer, nullable=True)
    caduca_meses = Column(Integer, nullable=True)                        # apuntes (bolsa, ajustes) caducan a los N meses
    prorratear_alta = Column(Boolean, nullable=False, default=False)
    derecho_tabla_id = Column(String(36), ForeignKey("tablas_de_referencia.id", ondelete="SET NULL"), nullable=True,
                              index=True)
    bolsa = Column(Text, nullable=True)                                  # JSON reglas de la bolsa de horas
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    requisitos = relationship("RequisitoDocumentalDeTipo", cascade="all, delete-orphan",
                              order_by="RequisitoDocumentalDeTipo.orden", lazy="selectin")


class TipoDeDocumentoDeAusencia(Base):
    __tablename__ = "tipos_de_documento_de_ausencia"
    __table_args__ = (UniqueConstraint("organization_id", "clave", name="uq_tipos_doc_ausencia_org_clave"),)

    id = _id()
    organization_id = _org()
    clave = Column(String(50), nullable=False)
    nombre = Column(String(120), nullable=False)
    nombres = Column(Text, nullable=True)                      # JSON {es, en, zh}
    categoria_especial = Column(Boolean, nullable=False, default=False)  # médico: acceso restringido
    activo = Column(Boolean, nullable=False, default=True)
    orden = Column(Integer, nullable=False, default=100)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class RequisitoDocumentalDeTipo(Base):
    """Un documento que pide un tipo de ausencia, con su plazo."""
    __tablename__ = "requisitos_documentales_de_tipo"

    id = _id()
    organization_id = _org()
    tipo_de_ausencia_id = Column(String(36), ForeignKey("tipos_de_ausencia.id", ondelete="CASCADE"), nullable=False, index=True)
    tipo_de_documento_id = Column(String(36), ForeignKey("tipos_de_documento_de_ausencia.id", ondelete="CASCADE"),
                                  nullable=False, index=True)
    obligatorio = Column(Boolean, nullable=False, default=True)
    plazo_dias = Column(Integer, nullable=False, default=3)
    plazo_desde = Column(String(12), nullable=False, default="inicio")   # solicitud | inicio | fin
    repetir_cada_dias = Column(Integer, nullable=True)                   # parte de confirmación cada N días
    recordar_dias_antes = Column(Integer, nullable=False, default=1)
    escalar_dias_despues = Column(Integer, nullable=True)                # sin valor: no se escala
    escalar_a = Column(Text, nullable=True)                              # JSON [{tipo, valor}] (destinatarios del motor)
    orden = Column(Integer, nullable=False, default=1)

    tipo_de_documento = relationship("TipoDeDocumentoDeAusencia", lazy="joined")


class Turno(Base):
    __tablename__ = "turnos"

    id = _id()
    organization_id = _org()
    nombre = Column(String(80), nullable=False)
    color = Column(String(9), nullable=False, default="#4f8cff")
    hora_inicio = Column(Time, nullable=False)
    hora_fin = Column(Time, nullable=False)                    # <= inicio: cruza la medianoche
    # Rev. 180: turno partido (JSON [[inicio, fin], …]; vacío = inicio–fin) y pausa no retribuida.
    tramos = Column(Text, nullable=True)
    pausa_minutos = Column(Integer, nullable=False, default=0)
    dias_semana = Column(Text, nullable=True)                  # JSON [1..7] (ISO); vacío = todos
    equipo = Column(String(120), nullable=True)
    departamento = Column(String(100), nullable=True)
    office_id = Column(String(36), ForeignKey("offices.id", ondelete="SET NULL"), nullable=True, index=True)
    personas_requeridas = Column(Integer, nullable=False, default=0)   # cobertura mínima
    trabaja_festivos = Column(Boolean, nullable=False, default=False)
    activo = Column(Boolean, nullable=False, default=True)
    orden = Column(Integer, nullable=False, default=100)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PatronDeTurnos(Base):
    """Una rotación: qué turno toca cada día de un ciclo de N días."""
    __tablename__ = "patrones_de_turnos"

    id = _id()
    organization_id = _org()
    nombre = Column(String(120), nullable=False)
    ciclo = Column(Text, nullable=False)                        # JSON [turno_id | null] (null = libre)
    inicio = Column(Date, nullable=False)                       # día 0 del ciclo
    activo = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    miembros = relationship("MiembroDePatron", cascade="all, delete-orphan", lazy="selectin")


class MiembroDePatron(Base):
    __tablename__ = "miembros_de_patron"

    id = _id()
    organization_id = _org()
    patron_id = Column(String(36), ForeignKey("patrones_de_turnos.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    desde = Column(Date, nullable=False)
    hasta = Column(Date, nullable=True)
    desfase = Column(Integer, nullable=False, default=0)        # días de desplazamiento en el ciclo


class AsignacionDeTurno(Base):
    """El cambio puntual de un día (manda sobre la rotación). Sin turno = libre."""
    __tablename__ = "asignaciones_de_turno"
    __table_args__ = (UniqueConstraint("user_id", "fecha", name="uq_asignaciones_de_turno_user_fecha"),)

    id = _id()
    organization_id = _org()
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    fecha = Column(Date, nullable=False, index=True)
    turno_id = Column(String(36), ForeignKey("turnos.id", ondelete="CASCADE"), nullable=True, index=True)
    nota = Column(String(255), nullable=True)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class HuecoDeCupo(Base):
    """El contador de plazas de un cupo en un día, turno y grupo. Se bloquea su fila."""
    __tablename__ = "huecos_de_cupo"
    __table_args__ = (
        UniqueConstraint("organization_id", "clave", "fecha", "turno", "grupo", name="uq_huecos_de_cupo"),
    )

    id = _id()
    organization_id = _org()
    clave = Column(String(64), nullable=False)                 # la del resultado «cupo» de la política
    fecha = Column(Date, nullable=False)
    turno = Column(String(36), nullable=False, default="")     # "" = sin turno
    grupo = Column(String(160), nullable=False, default="")    # valor del grupo ("" = toda la empresa)
    capacidad = Column(Integer, nullable=False, default=0)
    ocupadas = Column(Integer, nullable=False, default=0)
    version = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ReservaDeCupo(Base):
    __tablename__ = "reservas_de_cupo"
    __table_args__ = (
        UniqueConstraint("hueco_id", "absence_id", name="uq_reservas_de_cupo_hueco_ausencia"),
        Index("ix_reservas_de_cupo_hueco_estado", "hueco_id", "estado", "pedida_en"),
    )

    id = _id()
    organization_id = _org()
    hueco_id = Column(String(36), ForeignKey("huecos_de_cupo.id", ondelete="CASCADE"), nullable=False, index=True)
    absence_id = Column(String(36), ForeignKey("absences.id", ondelete="CASCADE"), nullable=False, index=True)
    estado = Column(String(10), nullable=False, default="ocupa")   # ocupa | espera | liberada
    pedida_en = Column(DateTime(timezone=True), nullable=False)    # orden de llegada (FCFS)
    por_encima = Column(Boolean, nullable=False, default=False)    # cupo blando: ocupa sin plaza libre
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    hueco = relationship("HuecoDeCupo", lazy="joined")


class DocumentoDeAusencia(Base):
    """Un documento adjunto a una ausencia. El fichero vive en `documents` (almacén de siempre)."""
    __tablename__ = "documentos_de_ausencia"

    id = _id()
    organization_id = _org()
    absence_id = Column(String(36), ForeignKey("absences.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)  # dueño (bloqueo legal)
    tipo_id = Column(String(36), ForeignKey("tipos_de_documento_de_ausencia.id", ondelete="SET NULL"), nullable=True, index=True)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1)
    estado = Column(String(12), nullable=False, default="vigente")   # vigente | sustituido
    sustituye_a = Column(String(36), ForeignKey("documentos_de_ausencia.id", ondelete="SET NULL"), nullable=True, index=True)
    requisito_id = Column(String(36), ForeignKey("requisitos_de_ausencia.id", ondelete="SET NULL"), nullable=True, index=True)
    especial = Column(Boolean, nullable=False, default=False)        # categoría especial al subirlo
    nota = Column(String(500), nullable=True)
    subido_por = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    subido_en = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Borrar la fila (retención) borra el documento del almacén con sus versiones.
    documento = relationship("Document", single_parent=True, cascade="all, delete-orphan", lazy="joined")
    tipo = relationship("TipoDeDocumentoDeAusencia", lazy="joined")


class RequisitoDeAusencia(Base):
    """Un documento pedido a una ausencia concreta, con su vencimiento."""
    __tablename__ = "requisitos_de_ausencia"

    id = _id()
    organization_id = _org()
    absence_id = Column(String(36), ForeignKey("absences.id", ondelete="CASCADE"), nullable=False, index=True)
    tipo_id = Column(String(36), ForeignKey("tipos_de_documento_de_ausencia.id", ondelete="CASCADE"), nullable=False, index=True)
    regla_id = Column(String(36), ForeignKey("requisitos_documentales_de_tipo.id", ondelete="SET NULL"), nullable=True, index=True)
    origen = Column(String(10), nullable=False, default="tipo")      # tipo | politica | manual
    secuencia = Column(Integer, nullable=False, default=1)
    vence = Column(Date, nullable=False, index=True)
    estado = Column(String(12), nullable=False, default="pendiente")  # pendiente | entregado | vencido | dispensado
    recordado_en = Column(DateTime(timezone=True), nullable=True)
    escalado_en = Column(DateTime(timezone=True), nullable=True)
    nota = Column(String(500), nullable=True)
    pedido_por = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    tipo = relationship("TipoDeDocumentoDeAusencia", lazy="joined")


class EventoDeAusencia(Base):
    __tablename__ = "eventos_de_ausencia"

    id = _id()
    organization_id = _org()
    absence_id = Column(String(36), ForeignKey("absences.id", ondelete="CASCADE"), nullable=False, index=True)
    tipo = Column(String(30), nullable=False)
    actor_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    datos = Column(Text, nullable=True)                         # JSON
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


class AccesoEspecialAusencias(Base):
    """Quien, además de la persona y RRHH, ve documentos de categoría especial."""
    __tablename__ = "acceso_especial_ausencias"
    __table_args__ = (UniqueConstraint("organization_id", "user_id", name="uq_acceso_especial_ausencias"),)

    id = _id()
    organization_id = _org()
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    concedido_por = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
