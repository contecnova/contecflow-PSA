"""Revisión posterior a la implantación (PIR) común a cambios y proyectos (migración 206, 23-11-2026).

Docs: docs/PIR.md.

ITIL 4 (gestión de cambios) y PMBOK (cierre y transición) piden lo mismo con
nombres distintos: después de implantar, alguien revisa si se consiguió lo que
se buscaba, qué se rompió, qué se aprende y qué se mejora. Antes la PIR eran
tres columnas sueltas del cambio (`pir_notes`, `pir_success`, `pir_date`) que
solo rellenaba la semilla; en proyectos no existía.

Cuatro tablas:

- `pir_revisiones`: la revisión. Cuelga de un cambio ITSM (`change_id`) o de un
  proyecto (`project_id`, y si nace de una puesta en marcha, del hito
  `milestone_id`). Estado `programado → en_curso → enviado → aprobado → cerrado`
  (o `descartado` si no era obligatoria); «vencida» se calcula (fecha prevista
  pasada sin enviar). Guarda el cuestionario de la plantilla con sus respuestas
  (criterios sí/no/parcial con comentario, preguntas), resultado global,
  incidencias provocadas (tickets), marcha atrás, KPIs antes/después y, en
  proyectos, beneficios conseguidos frente a previstos y satisfacción de los
  interesados.
- `pir_acciones`: acciones de mejora con responsable y fecha; cada una crea una
  tarea enlazada (`task_id`) en el proyecto que corresponda.
- `pir_plantillas`: por empresa, ámbito (`change`/`project`) y tipo (tipo de
  cambio o clave de tipo de proyecto; vacío = cualquiera): preguntas, criterios,
  plazo en días y obligatoriedad.
- `pir_configuracion`: una fila por empresa con los plazos por defecto, el aviso
  previo, la segregación (quien implantó no aprueba) y cuándo se programa.

Las lecciones aprendidas que salen de una PIR viven en `lecciones`
(`origen_tipo = "pir"`, `origen_id` = la revisión).
"""
import uuid

from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.sql import func

from app.db.base import Base


def _id() -> str:
    return str(uuid.uuid4())


class PirRevision(Base):
    __tablename__ = "pir_revisiones"

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    codigo = Column(String(30), nullable=False)                       # PIR-0001 (PIR-H0001: migradas)
    titulo = Column(String(300), nullable=False)

    # Origen
    origen_tipo = Column(String(10), nullable=False, index=True)      # change | project
    change_id = Column(String(36), ForeignKey("sd_change_requests.id", ondelete="CASCADE"), nullable=True, index=True)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
    milestone_id = Column(String(36), ForeignKey("project_milestones.id", ondelete="SET NULL"), nullable=True, index=True)
    motivo = Column(String(15), nullable=False, default="manual")     # implantacion | cierre | go_live | manual | migrada
    tipo = Column(String(50), nullable=True)                          # tipo de cambio o de proyecto al crearla
    plantilla_id = Column(String(36), ForeignKey("pir_plantillas.id", ondelete="SET NULL"), nullable=True, index=True)

    # Estado y plazos
    estado = Column(String(12), nullable=False, default="programado", index=True)
    obligatorio = Column(Boolean, nullable=False, default=False, server_default="0")
    fecha_prevista = Column(Date, nullable=True, index=True)
    fecha_real = Column(Date, nullable=True)
    responsable_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    participantes = Column(Text, nullable=True)                       # JSON [user_id]

    # Contenido
    objetivos_cumplidos = Column(String(10), nullable=True)           # si | no | parcial
    resultado = Column(String(15), nullable=True, index=True)         # exito | exito_parcial | fallo
    resumen = Column(Text, nullable=True)
    criterios = Column(Text, nullable=True)                           # JSON [{clave, texto, resultado, comentario}]
    preguntas = Column(Text, nullable=True)                           # JSON [{clave, texto, respuesta}]
    kpis = Column(Text, nullable=True)                                # JSON [{nombre, unidad, antes, despues, objetivo}]
    incidencias = Column(Text, nullable=True)                         # JSON [ticket_id]
    hubo_marcha_atras = Column(Boolean, nullable=True)
    marcha_atras_detalle = Column(Text, nullable=True)
    beneficios = Column(Text, nullable=True)                          # JSON [{benefit_id, nombre, previsto, conseguido, comentario}]
    satisfaccion = Column(Text, nullable=True)                        # JSON [{interesado, rol, puntuacion, comentario}]
    satisfaccion_media = Column(Float, nullable=True)

    # Flujo
    enviado_por = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    enviado_en = Column(DateTime(timezone=True), nullable=True)
    aprobado_por = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    aprobado_en = Column(DateTime(timezone=True), nullable=True)
    comentario_aprobacion = Column(Text, nullable=True)
    cerrado_por = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    cerrado_en = Column(DateTime(timezone=True), nullable=True)
    reaperturas = Column(Integer, nullable=False, default=0, server_default="0")
    #: Un PIR «fallo» de un cambio estándar ya sumó un fallo a su modelo del catálogo.
    cuenta_en_modelo = Column(Boolean, nullable=False, default=False, server_default="0")
    aviso_previo_en = Column(DateTime(timezone=True), nullable=True)
    aviso_vencido_en = Column(DateTime(timezone=True), nullable=True)

    creado_por = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index("uq_pir_revisiones_org_codigo", "organization_id", "codigo", unique=True),
        Index("ix_pir_revisiones_estado_fecha", "estado", "fecha_prevista"),
    )


class PirAccion(Base):
    __tablename__ = "pir_acciones"

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    pir_id = Column(String(36), ForeignKey("pir_revisiones.id", ondelete="CASCADE"), nullable=False, index=True)
    descripcion = Column(Text, nullable=False)
    responsable_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    fecha_limite = Column(Date, nullable=True)
    estado = Column(String(12), nullable=False, default="abierta", index=True)  # abierta | hecha | descartada
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    task_id = Column(String(36), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    creado_por = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PirPlantilla(Base):
    __tablename__ = "pir_plantillas"

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    nombre = Column(String(200), nullable=False)
    ambito = Column(String(10), nullable=False, index=True)          # change | project
    tipo = Column(String(50), nullable=True)                          # standard|normal|emergency o clave de tipo de proyecto
    obligatorio = Column(Boolean, nullable=True)                      # None: lo de la configuración
    dias = Column(Integer, nullable=True)                             # None: lo de la configuración
    criterios = Column(Text, nullable=True)                           # JSON [{clave, texto}]
    preguntas = Column(Text, nullable=True)                           # JSON [{clave, texto}]
    activo = Column(Boolean, nullable=False, default=True, server_default="1")
    creado_por = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (Index("ix_pir_plantillas_org_ambito_tipo", "organization_id", "ambito", "tipo"),)


class PirConfiguracion(Base):
    __tablename__ = "pir_configuracion"

    id = Column(String(36), primary_key=True, default=_id)
    organization_id = Column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True,
                             unique=True, index=True)
    dias_cambio = Column(Integer, nullable=False, default=7, server_default="7")
    dias_proyecto = Column(Integer, nullable=False, default=30, server_default="30")
    aviso_dias_antes = Column(Integer, nullable=False, default=2, server_default="2")
    #: Quien implantó o gestionó el cambio o proyecto no aprueba su PIR.
    segregacion = Column(Boolean, nullable=False, default=True, server_default="1")
    #: Cambios: al implantarlo (`implantacion`) o al cerrarlo (`cierre`).
    momento_cambio = Column(String(15), nullable=False, default="implantacion", server_default="implantacion")
    #: Proyectos: en la puesta en marcha (`go_live`), en el cierre (`cierre`) o en ambos (`ambos`).
    momento_proyecto = Column(String(15), nullable=False, default="ambos", server_default="ambos")
    #: Obligatoriedad por tipo de cambio (sin plantilla que lo diga).
    obligatorio_normal = Column(Boolean, nullable=False, default=True, server_default="1")
    obligatorio_emergencia = Column(Boolean, nullable=False, default=True, server_default="1")
    obligatorio_estandar = Column(Boolean, nullable=False, default=False, server_default="0")
    #: Proyectos sin plantilla de su tipo.
    obligatorio_proyecto = Column(Boolean, nullable=False, default=False, server_default="0")
    #: Proyecto donde nacen las tareas de las acciones de mejora de PIR de cambios sin proyecto.
    proyecto_acciones_id = Column(String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    updated_por = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
