"""Certificaciones y cumplimiento continuo (migración 212, 24-11-2026).

Docs: docs/CERTIFICACIONES.md (manual) y docs/propuestas/CERTIFICACIONES.md
(propuesta y decisiones). Funciona como Licencias, pero para cumplimiento: un
punto de control con trazabilidad completa de TISAX, NIS2, ISO/IEC 27001,
SOX/J-SOX, IEC 62443 y los marcos que se añadan.

Todas las tablas llevan `organization_id` NOT NULL y sus únicos empiezan por la
empresa. Grupos:

- **Biblioteca** (sembrada desde `app/data/certificaciones/*.yaml` por empresa,
  idempotente; al arrancar se pone al día lo sembrado que nadie ha editado):
  `cert_marcos`, `cert_controles` (biblioteca ÚNICA con descripción propia) y
  `cert_correspondencias` (control ↔ identificador de cada marco, con el texto
  oficial con licencia que importe la empresa). Los marcos ISO 27001 y SOC 2
  del GRC (`app/core/marcos_de_cumplimiento.py`) entran aquí y sus evidencias
  (`compliance_evidence`) se leen como evidencias del control, sin copiarlas
  fuera de su tabla (se enlazan por `compliance_evidence_id`).
- **Programa**: `cert_programas` (alcance, objetivos por marco y nivel,
  gobierno), `cert_aplicabilidad` (declaración de aplicabilidad y matriz: una
  fila por control y sede; sede vacía = toda la organización),
  `cert_control_tareas` (tareas que implantan el control), `cert_pruebas`
  (diseño y eficacia operativa al estilo SOX) y `cert_evidencias`.
- **Auditoría**: `cert_auditorias`, `cert_hallazgos`, `cert_acciones` (CAPA,
  cada una con su tarea), `cert_entidades` (empresas colaboradoras),
  `cert_auditores` (personas: dato personal, RGPD propio), `cert_accesos`
  (acceso temporal de solo lectura por enlace del portal) y
  `cert_accesos_registro` (todo lo que consultan).
- **Ciclo de vida y obligaciones**: `cert_certificados` (como una licencia, con
  avisos), `cert_incidentes` (NIS2, relojes de 24 h / 72 h / 1 mes),
  `cert_comunicaciones` (registro de lo enviado a la autoridad),
  `cert_proveedores` (evaluación de proveedores críticos), `cert_paquetes`
  (paquetes del auditor firmados) y `cert_configuracion` (una fila por empresa).
"""
import uuid

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.sql import func

from app.db.base import Base


def _id() -> str:
    return str(uuid.uuid4())


def _org():
    return Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)


def _usuario():
    return Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)


# ── Biblioteca ───────────────────────────────────────────────────────────────

class CertMarco(Base):
    __tablename__ = "cert_marcos"
    __table_args__ = (Index("uq_cert_marcos_org_clave", "organization_id", "clave", unique=True),)

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = _org()
    clave = Column(String(60), nullable=False)
    nombre = Column(String(200), nullable=False)
    version = Column(String(40), nullable=True)
    version_anterior = Column(String(40), nullable=True)      # la que había antes del último cambio de versión
    publico = Column(Boolean, nullable=False, default=False)   # texto público (NIS2, SOX) o con derechos de autor
    niveles = Column(Text, nullable=True)                      # JSON ["AL2", "AL3"] (orden creciente)
    descripcion = Column(Text, nullable=True)
    sembrado = Column(Boolean, nullable=False, default=False)
    editado = Column(Boolean, nullable=False, default=False)   # alguien lo tocó: la semilla ya no lo pisa
    huella_semilla = Column(String(64), nullable=True)
    activo = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class CertControl(Base):
    __tablename__ = "cert_controles"
    __table_args__ = (Index("uq_cert_controles_org_clave", "organization_id", "clave_comun", unique=True),)

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = _org()
    clave_comun = Column(String(80), nullable=False)
    titulo = Column(String(300), nullable=False)
    descripcion = Column(Text, nullable=True)                  # redacción propia (nunca el texto de la norma)
    dominio = Column(String(80), nullable=True, index=True)
    evidencia_sugerida = Column(Text, nullable=True)           # JSON [str]
    medible_por_plataforma = Column(String(60), nullable=True)  # id de medida (ver catalogo.MEDIDAS)
    sembrado = Column(Boolean, nullable=False, default=False)
    editado = Column(Boolean, nullable=False, default=False)
    huella_semilla = Column(String(64), nullable=True)
    activo = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class CertCorrespondencia(Base):
    __tablename__ = "cert_correspondencias"
    __table_args__ = (Index("uq_cert_correspondencias", "organization_id", "marco_id", "id_control", "control_id",
                            unique=True),)

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = _org()
    control_id = Column(String(36), ForeignKey("cert_controles.id", ondelete="CASCADE"), nullable=False, index=True)
    marco_id = Column(String(36), ForeignKey("cert_marcos.id", ondelete="CASCADE"), nullable=False, index=True)
    id_control = Column(String(60), nullable=False)            # identificador en el marco («A.5.17», «CC6.1»)
    # El que trae la semilla: si la importación del texto con licencia corrige el id
    # (TISAX ISA 6, 62443-4-2 por tipo), `id_control` cambia y este no, así la
    # sincronización no lo vuelve a crear ni se pierde el enlace al control.
    id_semilla = Column(String(60), nullable=True)
    nivel = Column(String(30), nullable=True)                  # nivel mínimo que lo exige (AL3, SL2…)
    version_marco = Column(String(40), nullable=True)
    texto_oficial = Column(Text, nullable=True)                # importado por la empresa con su licencia
    sembrado = Column(Boolean, nullable=False, default=False)
    afectado_por_version = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class CertConfiguracion(Base):
    __tablename__ = "cert_configuracion"

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False,
                             unique=True, index=True)
    aviso_certificado_dias = Column(Integer, nullable=False, default=90)
    aviso_auditoria_dias = Column(Integer, nullable=False, default=30)
    caducidad_evidencia_dias = Column(Integer, nullable=False, default=365)
    aviso_evidencia_dias = Column(Integer, nullable=False, default=30)
    exigir_evidencia_aprobada = Column(Boolean, nullable=False, default=True)
    acceso_auditor_max_dias = Column(Integer, nullable=False, default=30)
    autoridad_nis2 = Column(String(200), nullable=True)
    nis2_alerta_horas = Column(Integer, nullable=False, default=24)
    nis2_notificacion_horas = Column(Integer, nullable=False, default=72)
    nis2_informe_final_dias = Column(Integer, nullable=False, default=30)
    proyecto_capa_id = Column(String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    updated_por = _usuario()
    updated_at = Column(DateTime(timezone=True), nullable=True)


# ── Programa, aplicabilidad, pruebas y evidencias ────────────────────────────

class CertPrograma(Base):
    __tablename__ = "cert_programas"
    __table_args__ = (Index("uq_cert_programas_org_codigo", "organization_id", "codigo", unique=True),)

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = _org()
    codigo = Column(String(30), nullable=False)                # CERT-0001
    nombre = Column(String(300), nullable=False)
    descripcion = Column(Text, nullable=True)
    estado = Column(String(15), nullable=False, default="borrador", index=True)
    alcance = Column(Text, nullable=True)                      # JSON {entidades, sedes, paises, plantas_ot, sistemas, procesos}
    objetivos = Column(Text, nullable=True)                    # JSON [{marco, nivel, sl_objetivo}]
    responsable_id = _usuario()
    patrocinador_id = _usuario()                               # dirección (NIS2: responsabilidad de la dirección)
    fecha_inicio = Column(Date, nullable=True)
    fecha_objetivo = Column(Date, nullable=True)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    plantilla_clave = Column(String(80), nullable=True)
    parametros = Column(Text, nullable=True)                   # JSON de los parámetros de alcance de la plantilla
    creado_por = _usuario()
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class CertAplicabilidad(Base):
    """Fila de la declaración de aplicabilidad (y de la matriz)."""
    __tablename__ = "cert_aplicabilidad"
    __table_args__ = (Index("uq_cert_aplicabilidad", "organization_id", "programa_id", "control_id", "sede",
                            unique=True),)

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = _org()
    programa_id = Column(String(36), ForeignKey("cert_programas.id", ondelete="CASCADE"), nullable=False, index=True)
    control_id = Column(String(36), ForeignKey("cert_controles.id", ondelete="CASCADE"), nullable=False, index=True)
    sede = Column(String(120), nullable=False, default="")    # "" = toda la organización
    aplica = Column(Boolean, nullable=False, default=True)
    justificacion = Column(Text, nullable=True)
    estado = Column(String(15), nullable=False, default="pendiente")       # pendiente | en_curso | implantado
    eficacia = Column(String(15), nullable=False, default="sin_evaluar")   # sin_evaluar | eficaz | parcial | no_eficaz
    responsable_id = _usuario()
    implantado_por = _usuario()
    implantado_en = Column(DateTime(timezone=True), nullable=True)
    eficacia_por = _usuario()
    eficacia_en = Column(DateTime(timezone=True), nullable=True)
    ultima_revision = Column(Date, nullable=True)
    medicion = Column(String(15), nullable=True)               # pass | attention | info | not_measurable
    medicion_en = Column(DateTime(timezone=True), nullable=True)
    medicion_detalle = Column(Text, nullable=True)             # JSON de lo medido
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class CertControlTarea(Base):
    __tablename__ = "cert_control_tareas"
    __table_args__ = (Index("uq_cert_control_tareas", "organization_id", "aplicabilidad_id", "task_id", unique=True),)

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = _org()
    aplicabilidad_id = Column(String(36), ForeignKey("cert_aplicabilidad.id", ondelete="CASCADE"), nullable=False,
                              index=True)
    task_id = Column(String(36), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class CertPrueba(Base):
    __tablename__ = "cert_pruebas"

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = _org()
    aplicabilidad_id = Column(String(36), ForeignKey("cert_aplicabilidad.id", ondelete="CASCADE"), nullable=False,
                              index=True)
    tipo = Column(String(20), nullable=False)                  # diseno | eficacia_operativa
    periodo_desde = Column(Date, nullable=True)
    periodo_hasta = Column(Date, nullable=True)
    poblacion = Column(Integer, nullable=True)
    muestra = Column(Integer, nullable=True)
    metodo = Column(Text, nullable=True)
    resultado = Column(String(20), nullable=False, default="pendiente")   # pendiente | superada | con_excepciones | fallida
    excepciones = Column(Text, nullable=True)
    probado_por = _usuario()
    probado_en = Column(DateTime(timezone=True), nullable=True)
    notas = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class CertEvidencia(Base):
    __tablename__ = "cert_evidencias"

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = _org()
    programa_id = Column(String(36), ForeignKey("cert_programas.id", ondelete="CASCADE"), nullable=True, index=True)
    aplicabilidad_id = Column(String(36), ForeignKey("cert_aplicabilidad.id", ondelete="CASCADE"), nullable=True,
                              index=True)
    control_id = Column(String(36), ForeignKey("cert_controles.id", ondelete="CASCADE"), nullable=False, index=True)
    titulo = Column(String(300), nullable=False)
    tipo = Column(String(20), nullable=False)                  # documento | informe_sistema | tarea | registro | enlace
    origen = Column(String(15), nullable=False, default="manual")  # manual | sistema | tarea | grc | plantilla
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True, index=True)
    task_id = Column(String(36), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    compliance_evidence_id = Column(String(36), ForeignKey("compliance_evidence.id", ondelete="SET NULL"),
                                    nullable=True, index=True)
    uri = Column(String(1000), nullable=True)
    sha256 = Column(String(64), nullable=True)
    contenido = Column(Text, nullable=True)                    # JSON (evidencia generada por el sistema)
    valida_desde = Column(Date, nullable=True)
    caduca_el = Column(Date, nullable=True, index=True)
    aviso_caducidad_en = Column(DateTime(timezone=True), nullable=True)
    creado_por = _usuario()
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


# ── Auditorías, hallazgos y CAPA ─────────────────────────────────────────────

class CertEntidad(Base):
    """Empresa colaboradora: entidad certificadora, proveedor de auditoría ENX, consultora, laboratorio…"""
    __tablename__ = "cert_entidades"
    __table_args__ = (Index("uq_cert_entidades_org_nombre", "organization_id", "nombre", unique=True),)

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = _org()
    nombre = Column(String(200), nullable=False)
    tipo = Column(String(30), nullable=False, default="otra")
    acreditaciones = Column(Text, nullable=True)               # JSON [str]
    subcontractor_id = Column(String(36), ForeignKey("subcontractors.id", ondelete="SET NULL"), nullable=True,
                              index=True)
    contacto_email = Column(String(255), nullable=True)
    web = Column(String(300), nullable=True)
    notas = Column(Text, nullable=True)
    activo = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class CertAuditor(Base):
    """Persona auditora o consultora externa (dato personal: RGPD en `certificaciones/rgpd.py`)."""
    __tablename__ = "cert_auditores"

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = _org()
    entidad_id = Column(String(36), ForeignKey("cert_entidades.id", ondelete="SET NULL"), nullable=True, index=True)
    nombre = Column(String(200), nullable=False)
    email = Column(String(255), nullable=True, index=True)
    cualificaciones = Column(Text, nullable=True)              # JSON [str]
    independencia_declarada = Column(Boolean, nullable=False, default=False)
    conflictos_interes = Column(Text, nullable=True)
    nda_firmado_el = Column(Date, nullable=True)
    nda_document_id = Column(String(36), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    desde = Column(Date, nullable=True)
    hasta = Column(Date, nullable=True)
    activo = Column(Boolean, nullable=False, default=True)
    suprimido_en = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class CertAcceso(Base):
    """Acceso temporal de solo lectura de un auditor a un programa (enlace del portal)."""
    __tablename__ = "cert_accesos"
    __table_args__ = (Index("uq_cert_accesos_org_token", "organization_id", "token_hash", unique=True),)

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = _org()
    auditor_id = Column(String(36), ForeignKey("cert_auditores.id", ondelete="CASCADE"), nullable=False, index=True)
    programa_id = Column(String(36), ForeignKey("cert_programas.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String(64), nullable=False, index=True)
    desde = Column(DateTime(timezone=True), nullable=False)
    hasta = Column(DateTime(timezone=True), nullable=False)
    revocado_en = Column(DateTime(timezone=True), nullable=True)
    revocado_por = _usuario()
    creado_por = _usuario()
    ultimo_uso_en = Column(DateTime(timezone=True), nullable=True)
    usos = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class CertAccesoRegistro(Base):
    __tablename__ = "cert_accesos_registro"

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = _org()
    acceso_id = Column(String(36), ForeignKey("cert_accesos.id", ondelete="CASCADE"), nullable=False, index=True)
    recurso = Column(String(60), nullable=False)
    detalle = Column(String(300), nullable=True)
    ip = Column(String(64), nullable=True)
    en = Column(DateTime(timezone=True), server_default=func.now(), index=True)


class CertAuditoria(Base):
    __tablename__ = "cert_auditorias"
    __table_args__ = (Index("uq_cert_auditorias_org_codigo", "organization_id", "codigo", unique=True),)

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = _org()
    programa_id = Column(String(36), ForeignKey("cert_programas.id", ondelete="CASCADE"), nullable=False, index=True)
    codigo = Column(String(30), nullable=False)                # AUD-0001
    tipo = Column(String(25), nullable=False)
    marco_id = Column(String(36), ForeignKey("cert_marcos.id", ondelete="SET NULL"), nullable=True)
    estado = Column(String(15), nullable=False, default="planificada", index=True)
    fecha_inicio = Column(Date, nullable=True)
    fecha_fin = Column(Date, nullable=True)
    entidad_id = Column(String(36), ForeignKey("cert_entidades.id", ondelete="SET NULL"), nullable=True)
    auditor_id = Column(String(36), ForeignKey("cert_auditores.id", ondelete="SET NULL"), nullable=True)
    responsable_id = _usuario()
    plan = Column(Text, nullable=True)
    agenda = Column(Text, nullable=True)                       # JSON [{fecha, hora, tema, asistentes}]
    muestras = Column(Text, nullable=True)                     # JSON [{descripcion, control, entregada}]
    resultado = Column(Text, nullable=True)
    conclusion = Column(String(20), nullable=True)             # favorable | con_condiciones | desfavorable
    creado_por = _usuario()
    cerrada_en = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class CertHallazgo(Base):
    __tablename__ = "cert_hallazgos"
    __table_args__ = (Index("uq_cert_hallazgos_org_codigo", "organization_id", "codigo", unique=True),)

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = _org()
    auditoria_id = Column(String(36), ForeignKey("cert_auditorias.id", ondelete="CASCADE"), nullable=False, index=True)
    programa_id = Column(String(36), ForeignKey("cert_programas.id", ondelete="CASCADE"), nullable=False, index=True)
    codigo = Column(String(30), nullable=False)                # HAL-0001
    tipo = Column(String(15), nullable=False)                  # nc_mayor | nc_menor | observacion | oportunidad
    control_id = Column(String(36), ForeignKey("cert_controles.id", ondelete="SET NULL"), nullable=True)
    titulo = Column(String(300), nullable=False)
    descripcion = Column(Text, nullable=True)
    estado = Column(String(15), nullable=False, default="abierto", index=True)  # abierto | en_correccion | corregido | cerrado
    fecha_limite = Column(Date, nullable=True)
    corregido_por = _usuario()
    corregido_en = Column(DateTime(timezone=True), nullable=True)
    cerrado_por = _usuario()
    cerrado_en = Column(DateTime(timezone=True), nullable=True)
    creado_por = _usuario()
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class CertAccion(Base):
    """Acción correctiva (CAPA): causa, plan, plazo, responsable, verificación de eficacia y cierre."""
    __tablename__ = "cert_acciones"

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = _org()
    hallazgo_id = Column(String(36), ForeignKey("cert_hallazgos.id", ondelete="CASCADE"), nullable=False, index=True)
    analisis_causa = Column(Text, nullable=True)
    plan = Column(Text, nullable=False)
    responsable_id = _usuario()
    fecha_limite = Column(Date, nullable=True)
    estado = Column(String(15), nullable=False, default="abierta")  # abierta | en_curso | hecha | verificada | no_eficaz
    task_id = Column(String(36), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    hecho_por = _usuario()
    hecho_en = Column(DateTime(timezone=True), nullable=True)
    verificacion = Column(Text, nullable=True)
    verificado_por = _usuario()
    verificado_en = Column(DateTime(timezone=True), nullable=True)
    aviso_vencida_en = Column(DateTime(timezone=True), nullable=True)
    creado_por = _usuario()
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


# ── Certificados, NIS2, proveedores críticos y paquetes ──────────────────────

class CertCertificado(Base):
    __tablename__ = "cert_certificados"
    __table_args__ = (Index("uq_cert_certificados_org_numero", "organization_id", "numero", unique=True),)

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = _org()
    programa_id = Column(String(36), ForeignKey("cert_programas.id", ondelete="SET NULL"), nullable=True, index=True)
    marco_id = Column(String(36), ForeignKey("cert_marcos.id", ondelete="SET NULL"), nullable=True)
    numero = Column(String(120), nullable=False)
    entidad_id = Column(String(36), ForeignKey("cert_entidades.id", ondelete="SET NULL"), nullable=True)
    alcance = Column(Text, nullable=True)
    nivel = Column(String(30), nullable=True)
    emitido_el = Column(Date, nullable=True)
    valido_hasta = Column(Date, nullable=True, index=True)
    estado = Column(String(15), nullable=False, default="vigente")   # vigente | suspendido | retirado | caducado
    enx_id = Column(String(60), nullable=True)                 # TISAX: identificador del portal ENX
    enx_ambito = Column(String(200), nullable=True)            # TISAX: identificador del alcance de la evaluación
    proxima_auditoria = Column(Date, nullable=True)
    tipo_proxima = Column(String(20), nullable=True)           # seguimiento_1 | seguimiento_2 | renovacion
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    aviso_vencimiento_en = Column(DateTime(timezone=True), nullable=True)
    aviso_auditoria_en = Column(DateTime(timezone=True), nullable=True)
    creado_por = _usuario()
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class CertIncidente(Base):
    """Incidente notificable NIS2 (art. 23), enlazado a un ticket del Service Desk."""
    __tablename__ = "cert_incidentes"
    __table_args__ = (Index("uq_cert_incidentes_org_codigo", "organization_id", "codigo", unique=True),)

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = _org()
    programa_id = Column(String(36), ForeignKey("cert_programas.id", ondelete="SET NULL"), nullable=True)
    ticket_id = Column(String(36), ForeignKey("sd_tickets.id", ondelete="SET NULL"), nullable=True, index=True)
    codigo = Column(String(30), nullable=False)                # NIS2-0001
    titulo = Column(String(300), nullable=False)
    descripcion = Column(Text, nullable=True)
    detectado_en = Column(DateTime(timezone=True), nullable=False)   # cuando se tuvo conocimiento
    significativo = Column(Boolean, nullable=False, default=True)
    transfronterizo = Column(Boolean, nullable=False, default=False)
    impacto = Column(Text, nullable=True)
    estado = Column(String(20), nullable=False, default="abierto", index=True)
    autoridad = Column(String(200), nullable=True)
    alerta_enviada_en = Column(DateTime(timezone=True), nullable=True)
    notificacion_enviada_en = Column(DateTime(timezone=True), nullable=True)
    informe_final_enviado_en = Column(DateTime(timezone=True), nullable=True)
    avisos = Column(Text, nullable=True)                       # JSON {"alerta_proxima": iso, "alerta_vencida": iso, …}
    responsable_id = _usuario()
    creado_por = _usuario()
    cerrado_en = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class CertComunicacion(Base):
    __tablename__ = "cert_comunicaciones"

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = _org()
    incidente_id = Column(String(36), ForeignKey("cert_incidentes.id", ondelete="CASCADE"), nullable=False, index=True)
    tipo = Column(String(25), nullable=False)    # alerta_temprana | notificacion | informe_intermedio | informe_final | otra
    destinatario = Column(String(200), nullable=True)
    asunto = Column(String(300), nullable=True)
    contenido = Column(Text, nullable=True)
    referencia = Column(String(120), nullable=True)
    enviado_en = Column(DateTime(timezone=True), nullable=False)
    enviado_por = _usuario()
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class CertProveedor(Base):
    """Evaluación de un proveedor crítico de la cadena de suministro (NIS2 art. 21.2.d)."""
    __tablename__ = "cert_proveedores"

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = _org()
    programa_id = Column(String(36), ForeignKey("cert_programas.id", ondelete="SET NULL"), nullable=True, index=True)
    subcontractor_id = Column(String(36), ForeignKey("subcontractors.id", ondelete="SET NULL"), nullable=True,
                              index=True)
    nombre = Column(String(200), nullable=False)
    criticidad = Column(String(10), nullable=False, default="alta")     # alta | media | baja
    servicios = Column(Text, nullable=True)
    resultado = Column(String(20), nullable=False, default="pendiente")  # pendiente | aceptable | con_condiciones | no_aceptable
    riesgo = Column(Text, nullable=True)
    evaluado_por = _usuario()
    evaluado_en = Column(Date, nullable=True)
    proxima_evaluacion = Column(Date, nullable=True)
    notas = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class CertPaquete(Base):
    """Paquete del auditor exportado y firmado (traza: quién, cuándo, huella)."""
    __tablename__ = "cert_paquetes"

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = _org()
    programa_id = Column(String(36), ForeignKey("cert_programas.id", ondelete="CASCADE"), nullable=False, index=True)
    generado_por = _usuario()
    acceso_id = Column(String(36), ForeignKey("cert_accesos.id", ondelete="SET NULL"), nullable=True)
    sha256 = Column(String(64), nullable=False)
    resumen = Column(Text, nullable=True)                      # JSON
    generado_en = Column(DateTime(timezone=True), server_default=func.now(), index=True)


#: Orden de creación (padres antes); el borrado va al revés. Lo usa la migración 212.
TABLAS = (
    "cert_marcos", "cert_controles", "cert_correspondencias", "cert_configuracion", "cert_programas",
    "cert_aplicabilidad", "cert_control_tareas", "cert_pruebas", "cert_evidencias", "cert_entidades",
    "cert_auditores", "cert_accesos", "cert_accesos_registro", "cert_auditorias", "cert_hallazgos",
    "cert_acciones", "cert_certificados", "cert_incidentes", "cert_comunicaciones", "cert_proveedores",
    "cert_paquetes",
)
