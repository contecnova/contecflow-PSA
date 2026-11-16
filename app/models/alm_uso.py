"""Licencias y hardware — fase 2: uso real (16-11-2026).

Lo que las fuentes externas e internas dicen de QUIÉN USA cada licencia y cada
equipo, y lo que se decide con ello. Todo por empresa (`organization_id`).

- `ALMUsoConexion`: una fuente de uso configurada en una empresa (Microsoft 365,
  Intune, Google Workspace, Okta, Jamf, los accesos propios de contecflow, el
  agente de inventario). Las credenciales NO viven aquí: van cifradas en
  `integration_credentials` (proveedores `alm_*` del registro).
- `ALMUsoSincronizacion`: cada lectura de una conexión (programada o manual),
  con lo que leyó y sus errores.
- `ALMUsoEvidencia`: una evidencia de uso — fuente, titular (persona o
  dispositivo), producto/SKU, último uso, frecuencia, fiabilidad y fecha de
  lectura. Una fila por (fuente, titular, producto): cada lectura la pone al día.
- `ALMUsoMapeo`: qué licencia de ALM es un producto/SKU de una fuente.
- `ALMUsoDerecho`: lo comprado según la fuente (p. ej. `subscribedSkus`).
- El pico de las licencias concurrentes NO vive aquí: se registra con
  `alm_asignaciones.registrar_pico` (tabla `alm_picos_concurrencia`, fase 1).
- `ALMUsoNivel`: regla de ajuste de nivel (licencia superior → inferior y los
  servicios que justifican la superior).
- `ALMUsoAjusteDecision`: lo que se decidió de una propuesta de ajuste.
- `ALMUsoRecuperacion`: el proceso de recuperación (harvesting) de una
  asignación sin uso: avisos escalonados, aprobación y liberación.
- `ALMSoftwareNoControlado`: software visto en gastos, accesos o inventario que
  no está en ALM, con su propuesta de alta.
"""
import uuid

from sqlalchemy import (Boolean, Column, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text,
                        UniqueConstraint)
from sqlalchemy.sql import func

from app.db.base import Base


def _id():
    return Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))


def _org():
    return Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)


class ALMUsoConexion(Base):
    """Una fuente de uso configurada en una empresa."""
    __tablename__ = "alm_uso_conexiones"
    __table_args__ = (UniqueConstraint("organization_id", "proveedor", name="uq_alm_uso_conexion_org_proveedor"),)

    id = _id()
    organization_id = _org()
    proveedor = Column(String(30), nullable=False)          # clave del registro de proveedores de uso
    activa = Column(Boolean, nullable=False, default=True)
    # alta | media | baja. Vacío: la del proveedor.
    fiabilidad = Column(String(10), nullable=True)
    configuracion = Column(Text, nullable=True)            # JSON: opciones no secretas del proveedor
    ultima_sincronizacion_at = Column(DateTime(timezone=True), nullable=True)
    ultimo_estado = Column(String(20), nullable=False, default="nunca")   # nunca | ok | parcial | error | en_curso
    ultimo_error = Column(Text, nullable=True)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class ALMUsoSincronizacion(Base):
    """Una lectura de una conexión."""
    __tablename__ = "alm_uso_sincronizaciones"
    __table_args__ = (Index("ix_alm_uso_sinc_conexion_inicio", "conexion_id", "iniciada_at"),)

    id = _id()
    organization_id = _org()
    conexion_id = Column(String(36), ForeignKey("alm_uso_conexiones.id", ondelete="CASCADE"), nullable=False, index=True)
    proveedor = Column(String(30), nullable=False)
    origen = Column(String(15), nullable=False, default="programada")   # programada | manual | agente
    estado = Column(String(15), nullable=False, default="en_curso")     # en_curso | ok | parcial | error
    iniciada_at = Column(DateTime(timezone=True), server_default=func.now())
    terminada_at = Column(DateTime(timezone=True), nullable=True)
    leidos = Column(Integer, nullable=False, default=0)
    nuevas = Column(Integer, nullable=False, default=0)
    actualizadas = Column(Integer, nullable=False, default=0)
    sin_titular = Column(Integer, nullable=False, default=0)            # titulares que no son de la empresa
    sin_licencia = Column(Integer, nullable=False, default=0)           # productos sin licencia de ALM
    dispositivos = Column(Integer, nullable=False, default=0)
    errores = Column(Text, nullable=True)                              # JSON: [{codigo, mensaje}]
    avisos = Column(Text, nullable=True)                               # JSON: [{codigo, mensaje}]
    iniciada_por = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)


class ALMUsoEvidencia(Base):
    """Lo que una fuente dice del uso de un producto por un titular."""
    __tablename__ = "alm_uso_evidencias"
    __table_args__ = (
        UniqueConstraint("organization_id", "fuente", "titular_tipo", "titular_externo", "producto",
                         name="uq_alm_uso_evidencia"),
        Index("ix_alm_uso_evidencia_licencia_usuario", "license_id", "user_id"),
        Index("ix_alm_uso_evidencia_licencia_activo", "license_id", "asset_id"),
    )

    id = _id()
    organization_id = _org()
    conexion_id = Column(String(36), ForeignKey("alm_uso_conexiones.id", ondelete="CASCADE"), nullable=True, index=True)
    fuente = Column(String(30), nullable=False)                 # clave del proveedor
    titular_tipo = Column(String(12), nullable=False)          # persona | dispositivo
    titular_externo = Column(String(320), nullable=False)      # UPN/correo, o nº de serie / nombre del equipo
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    asset_id = Column(String(36), ForeignKey("alm_assets.id", ondelete="SET NULL"), nullable=True, index=True)
    producto = Column(String(255), nullable=False)             # clave del producto en la fuente (SKU, app…)
    nombre_producto = Column(String(255), nullable=True)
    sku = Column(String(120), nullable=True)
    license_id = Column(String(36), ForeignKey("alm_licenses.id", ondelete="SET NULL"), nullable=True, index=True)
    assignment_id = Column(String(36), ForeignKey("alm_license_assignments.id", ondelete="SET NULL"), nullable=True,
                           index=True)
    install_id = Column(String(36), ForeignKey("alm_software_installs.id", ondelete="SET NULL"), nullable=True)
    asignada_en_fuente = Column(Boolean, nullable=True)       # la fuente dice que la tiene asignada
    ultimo_uso_at = Column(DateTime(timezone=True), nullable=True)
    frecuencia = Column(Integer, nullable=True)                # días con uso en el periodo
    periodo_dias = Column(Integer, nullable=True)
    servicios = Column(Text, nullable=True)                    # JSON: {servicio: fecha ISO del último uso}
    fiabilidad = Column(String(10), nullable=False, default="media")
    leido_at = Column(DateTime(timezone=True), nullable=False)   # fecha de lectura
    vista_en_ultima_lectura = Column(Boolean, nullable=False, default=True)
    detalle = Column(Text, nullable=True)                      # JSON: lo que la fuente dio (sin secretos)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ALMUsoMapeo(Base):
    """Qué licencia de ALM es un producto/SKU de una fuente."""
    __tablename__ = "alm_uso_mapeos"
    __table_args__ = (UniqueConstraint("organization_id", "fuente", "producto", name="uq_alm_uso_mapeo"),)

    id = _id()
    organization_id = _org()
    fuente = Column(String(30), nullable=False)
    producto = Column(String(255), nullable=False)
    license_id = Column(String(36), ForeignKey("alm_licenses.id", ondelete="CASCADE"), nullable=True, index=True)
    ignorar = Column(Boolean, nullable=False, default=False)   # producto que no se controla (no es candidato)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ALMUsoDerecho(Base):
    """Lo comprado de un SKU según la fuente (derechos del fabricante)."""
    __tablename__ = "alm_uso_derechos"
    __table_args__ = (UniqueConstraint("organization_id", "fuente", "sku", name="uq_alm_uso_derecho"),)

    id = _id()
    organization_id = _org()
    conexion_id = Column(String(36), ForeignKey("alm_uso_conexiones.id", ondelete="CASCADE"), nullable=True, index=True)
    fuente = Column(String(30), nullable=False)
    sku = Column(String(255), nullable=False)
    nombre = Column(String(255), nullable=True)
    comprados = Column(Integer, nullable=True)
    consumidos = Column(Integer, nullable=True)
    suspendidos = Column(Integer, nullable=True)
    license_id = Column(String(36), ForeignKey("alm_licenses.id", ondelete="SET NULL"), nullable=True, index=True)
    detalle = Column(Text, nullable=True)
    leido_at = Column(DateTime(timezone=True), nullable=False)


class ALMUsoNivel(Base):
    """Regla de ajuste de nivel: quien no usa ninguno de `servicios` cabe en la licencia inferior."""
    __tablename__ = "alm_uso_niveles"
    __table_args__ = (UniqueConstraint("organization_id", "license_superior_id", "license_inferior_id",
                                       name="uq_alm_uso_nivel"),)

    id = _id()
    organization_id = _org()
    license_superior_id = Column(String(36), ForeignKey("alm_licenses.id", ondelete="CASCADE"), nullable=False, index=True)
    license_inferior_id = Column(String(36), ForeignKey("alm_licenses.id", ondelete="CASCADE"), nullable=False, index=True)
    servicios = Column(Text, nullable=False)        # JSON: servicios de la evidencia que justifican la superior
    activa = Column(Boolean, nullable=False, default=True)
    notas = Column(String(500), nullable=True)
    created_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ALMUsoAjusteDecision(Base):
    """La decisión sobre una propuesta de ajuste de nivel (una por asignación y regla)."""
    __tablename__ = "alm_uso_ajustes"
    __table_args__ = (UniqueConstraint("organization_id", "nivel_id", "assignment_id", name="uq_alm_uso_ajuste"),)

    id = _id()
    organization_id = _org()
    nivel_id = Column(String(36), ForeignKey("alm_uso_niveles.id", ondelete="CASCADE"), nullable=False, index=True)
    assignment_id = Column(String(36), ForeignKey("alm_license_assignments.id", ondelete="CASCADE"), nullable=False,
                           index=True)
    decision = Column(String(15), nullable=False)          # aceptada | descartada
    nueva_asignacion_id = Column(String(36), ForeignKey("alm_license_assignments.id", ondelete="SET NULL"),
                                 nullable=True)
    ahorro_estimado = Column(Float, nullable=True)
    motivo = Column(String(500), nullable=True)
    decidido_por = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    decidido_at = Column(DateTime(timezone=True), server_default=func.now())


class ALMUsoRecuperacion(Base):
    """Recuperación de una asignación sin uso: avisos escalonados → liberar."""
    __tablename__ = "alm_uso_recuperaciones"
    __table_args__ = (Index("ix_alm_uso_recup_asignacion_estado", "assignment_id", "estado"),)

    id = _id()
    organization_id = _org()
    assignment_id = Column(String(36), ForeignKey("alm_license_assignments.id", ondelete="CASCADE"), nullable=False,
                           index=True)
    license_id = Column(String(36), ForeignKey("alm_licenses.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    asset_id = Column(String(36), ForeignKey("alm_assets.id", ondelete="SET NULL"), nullable=True, index=True)
    # aviso_persona | aviso_responsable | pendiente_aprobacion | liberada | conservada | cancelada | rechazada
    estado = Column(String(25), nullable=False, default="aviso_persona", index=True)
    politica_id = Column(String(36), nullable=True)
    politica = Column(String(255), nullable=True)
    parametros = Column(Text, nullable=True)        # JSON: el resultado «recuperar» que encajó
    dias_sin_uso = Column(Integer, nullable=True)
    coste_anual = Column(Float, nullable=True)      # coste unitario anual (ahorro si se libera)
    iniciada_at = Column(DateTime(timezone=True), server_default=func.now())
    ultimo_paso_at = Column(DateTime(timezone=True), nullable=True)
    siguiente_paso_at = Column(DateTime(timezone=True), nullable=True)
    conservar_hasta = Column(Date, nullable=True)
    cerrada_at = Column(DateTime(timezone=True), nullable=True)
    cerrada_por = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    motivo = Column(String(500), nullable=True)
    historial = Column(Text, nullable=True)         # JSON: [{at, paso, detalle, por}]


class ALMSoftwareNoControlado(Base):
    """Software visto fuera de ALM (gastos, accesos SSO, inventario) con su propuesta de alta."""
    __tablename__ = "alm_software_no_controlado"
    __table_args__ = (UniqueConstraint("organization_id", "clave", name="uq_alm_software_no_controlado"),)

    id = _id()
    organization_id = _org()
    clave = Column(String(255), nullable=False)        # nombre normalizado
    nombre = Column(String(255), nullable=False)
    origenes = Column(Text, nullable=True)             # JSON: {origen: apariciones}
    usuarios = Column(Integer, nullable=False, default=0)
    dispositivos = Column(Integer, nullable=False, default=0)
    importe = Column(Float, nullable=True)             # gasto acumulado en la moneda de la empresa
    moneda = Column(String(3), nullable=True)
    primera_vez = Column(Date, nullable=True)
    ultima_vez = Column(Date, nullable=True)
    referencias = Column(Text, nullable=True)          # JSON: ejemplos (gastos, dispositivos, apps)
    estado = Column(String(15), nullable=False, default="nuevo")   # nuevo | dado_de_alta | descartado
    license_id = Column(String(36), ForeignKey("alm_licenses.id", ondelete="SET NULL"), nullable=True, index=True)
    revisado_por = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    revisado_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
