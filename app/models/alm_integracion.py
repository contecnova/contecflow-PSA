"""Licencias y hardware — fase 4: integración en toda la plataforma (16-11-2026).

Lo que une ALM con personas, proyectos y el service desk. Todo por empresa
(`organization_id`).

- `ALMKit` / `ALMKitElemento`: el «kit de alta» de una empresa. Un kit aplica a
  quien cumple su criterio (rol, puesto, departamento, equipo, o a todos) y
  dice qué licencias y qué tipos de equipo le corresponden.
- `ALMPropuestaDeKit`: al dar de alta a una persona se le propone la unión de
  los kits que le aplican; su responsable la confirma con un clic, y entonces
  se reservan asientos y equipos disponibles o se piden por compra. Guarda lo
  propuesto y lo que pasó con cada elemento.
- `ALMBaja`: el expediente de baja de una persona (manual, SCIM, fin de
  contrato o programada): cuándo se liberan sus licencias según la regla de la
  empresa, qué equipos tiene que devolver y si queda algo pendiente.
- `ALMDevolucion`: la devolución de un equipo (por baja o pedida por la
  persona), con su ticket del service desk y su seguimiento hasta el acta de
  devolución firmada.
- `ALMItemDeCatalogo`: qué ítems del catálogo del service desk son «pedir
  licencia» o «pedir equipo» (y, si el ítem es de un producto concreto, cuál).
- `ALMPeticion`: una petición de licencia o equipo hecha desde el catálogo, con
  su ticket, y lo que se le dio al aprobarse (asignación, equipo o compra).
"""
import uuid

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from app.db.base import Base


def _id():
    return Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))


def _org():
    return Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)


def _fk(tabla: str, ondelete: str = "SET NULL", nullable: bool = True):
    return Column(String(36), ForeignKey(f"{tabla}.id", ondelete=ondelete), nullable=nullable, index=True)


#: Criterios con los que un kit elige a quién aplica.
CRITERIOS_DE_KIT = ("todos", "rol", "puesto", "departamento", "equipo")
#: Tipos de elemento de un kit y de una petición.
TIPOS_DE_ELEMENTO = ("licencia", "equipo")
#: Por qué se abre una baja.
MOTIVOS_DE_BAJA = ("manual", "scim", "fin_contrato", "programada")
#: Estados de una baja.
ESTADOS_DE_BAJA = ("programada", "pendiente_devolucion", "cerrada", "anulada")
#: Estados de una devolución.
ESTADOS_DE_DEVOLUCION = ("pendiente", "recibida", "cerrada", "perdida", "anulada")
#: Estados de una propuesta de kit.
ESTADOS_DE_PROPUESTA = ("pendiente", "confirmada", "descartada")
#: Estados de una petición del catálogo.
ESTADOS_DE_PETICION = ("pendiente", "cumplida", "en_compra", "rechazada", "error")


class ALMKit(Base):
    __tablename__ = "alm_kits"

    id = _id()
    organization_id = _org()
    nombre = Column(String(200), nullable=False)
    descripcion = Column(Text, nullable=True)
    criterio = Column(String(20), nullable=False, default="todos")
    valor = Column(String(200), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_by = _fk("users")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class ALMKitElemento(Base):
    __tablename__ = "alm_kit_elementos"

    id = _id()
    organization_id = _org()
    kit_id = _fk("alm_kits", "CASCADE", nullable=False)
    tipo = Column(String(10), nullable=False)
    license_id = _fk("alm_licenses", "CASCADE")
    asset_type = Column(String(20), nullable=True)
    cantidad = Column(Integer, nullable=False, default=1)
    notas = Column(String(500), nullable=True)


class ALMPropuestaDeKit(Base):
    __tablename__ = "alm_propuestas_de_kit"

    id = _id()
    organization_id = _org()
    user_id = _fk("users", "CASCADE", nullable=False)
    responsable_id = _fk("users")
    estado = Column(String(15), nullable=False, default="pendiente")
    #: Ids de los kits que aplicaron, en JSON.
    kits = Column(Text, nullable=True)
    #: Lo propuesto, en JSON: [{clave, tipo, license_id, asset_type, cantidad, nombre}].
    elementos = Column(Text, nullable=False)
    #: Lo que pasó con cada elemento al confirmar, en JSON.
    resultado = Column(Text, nullable=True)
    decidida_por = _fk("users")
    decidida_en = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ALMBaja(Base):
    __tablename__ = "alm_bajas"

    id = _id()
    organization_id = _org()
    user_id = _fk("users", "CASCADE", nullable=False)
    motivo = Column(String(15), nullable=False)
    estado = Column(String(25), nullable=False, default="pendiente_devolucion")
    #: Cuándo deja de trabajar (para una baja programada o un fin de contrato).
    fecha_efectiva = Column(Date, nullable=False)
    #: Cuándo se liberan sus licencias (regla de la empresa: ya o tras N días).
    licencias_liberar_en = Column(Date, nullable=True)
    licencias_liberadas_en = Column(DateTime(timezone=True), nullable=True)
    licencias_liberadas = Column(Integer, nullable=False, default=0)
    #: El equipo sin devolver se confirmó a sabiendas (política «confirmar»).
    confirmada_con_pendientes = Column(Boolean, nullable=False, default=False)
    notas = Column(Text, nullable=True)
    creada_por = _fk("users")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    cerrada_en = Column(DateTime(timezone=True), nullable=True)


class ALMDevolucion(Base):
    __tablename__ = "alm_devoluciones"

    id = _id()
    organization_id = _org()
    baja_id = _fk("alm_bajas", "CASCADE")
    asset_id = _fk("alm_assets", "CASCADE", nullable=False)
    user_id = _fk("users")
    ticket_id = _fk("sd_tickets")
    origen = Column(String(15), nullable=False, default="baja")  # baja | autoservicio | gestion
    estado = Column(String(15), nullable=False, default="pendiente")
    fecha_limite = Column(Date, nullable=True)
    #: El acta de devolución (la crea el ciclo del equipo al registrar la recepción).
    acta_id = Column(String(36), nullable=True, index=True)
    condicion = Column(String(10), nullable=True)
    notas = Column(Text, nullable=True)
    solicitada_por = _fk("users")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    recibida_en = Column(DateTime(timezone=True), nullable=True)
    recibida_por = _fk("users")
    cerrada_en = Column(DateTime(timezone=True), nullable=True)


class ALMItemDeCatalogo(Base):
    __tablename__ = "alm_items_de_catalogo"
    __table_args__ = (UniqueConstraint("organization_id", "service_item_id", name="uq_alm_item_catalogo_org_item"),)

    id = _id()
    organization_id = _org()
    service_item_id = _fk("sd_service_items", "CASCADE", nullable=False)
    tipo = Column(String(10), nullable=False)
    #: Si el ítem es de un producto concreto («Pedir Visio»): esa licencia.
    license_id = _fk("alm_licenses")
    #: Si el ítem es de un tipo de equipo concreto («Pedir portátil»).
    asset_type = Column(String(20), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ALMPeticion(Base):
    __tablename__ = "alm_peticiones"
    __table_args__ = (UniqueConstraint("ticket_id", name="uq_alm_peticion_ticket"),)

    id = _id()
    organization_id = _org()
    ticket_id = _fk("sd_tickets", "CASCADE", nullable=False)
    tipo = Column(String(10), nullable=False)
    beneficiario_id = _fk("users")
    solicitante_id = _fk("users")
    license_id = _fk("alm_licenses")
    asset_type = Column(String(20), nullable=True)
    project_id = _fk("projects")
    motivo = Column(Text, nullable=True)
    estado = Column(String(15), nullable=False, default="pendiente")
    #: Lo que se dio al aprobarse.
    asignacion_id = Column(String(36), nullable=True, index=True)
    asset_id = _fk("alm_assets")
    compra_ticket_id = _fk("sd_tickets")
    detalle = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    cumplida_en = Column(DateTime(timezone=True), nullable=True)
