"""Certificaciones y cumplimiento continuo (24-11-2026, docs/CERTIFICACIONES.md).

Propuesta y decisiones: docs/propuestas/CERTIFICACIONES.md (§3 y §4).

Tablas nuevas (21), todas con `organization_id` NOT NULL y sus únicos con la
empresa delante (la RLS la aplica `env.py` tras el `upgrade`). Las mismas que
`app/models/certificaciones.py`:

- biblioteca: `cert_marcos`, `cert_controles`, `cert_correspondencias`;
- configuración: `cert_configuracion` (una fila por empresa);
- programa: `cert_programas`, `cert_aplicabilidad`, `cert_control_tareas`,
  `cert_pruebas`, `cert_evidencias`;
- auditoría: `cert_entidades`, `cert_auditores`, `cert_accesos`,
  `cert_accesos_registro`, `cert_auditorias`, `cert_hallazgos`, `cert_acciones`;
- ciclo de vida y obligaciones: `cert_certificados`, `cert_incidentes`,
  `cert_comunicaciones`, `cert_proveedores`, `cert_paquetes`.

Datos: ninguno aquí. La biblioteca se siembra por empresa desde
`app/data/certificaciones/` (`app/services/certificaciones/catalogo.py`,
idempotente), y en esa siembra los marcos ISO 27001 y SOC 2 del GRC actual
(`app/core/marcos_de_cumplimiento.py`) entran en la biblioteca y cada fila de
`compliance_evidence` queda enlazada como evidencia de su control
(`cert_evidencias.compliance_evidence_id`), sin tocar ni borrar la tabla del
GRC: no se pierde nada y no hay dos copias que diverjan.

Compatible con SQLite y Postgres. Idempotente: mira antes cada tabla e índice.

Deshacer real: borra las 21 tablas (con sus filas) en orden inverso. Las tareas,
proyectos y documentos que se generaron desde el módulo se quedan (son de sus
módulos); `compliance_evidence` no se toca.

Revision ID: 212_certificaciones
Revises: 211_chat_en_vivo_completo
"""
import logging

import sqlalchemy as sa
from alembic import op

revision = "212_certificaciones"
down_revision = "211_chat_en_vivo_completo"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.212")

_TZ = sa.DateTime(timezone=True)

TABLAS = (
    "cert_marcos", "cert_controles", "cert_correspondencias", "cert_configuracion", "cert_programas",
    "cert_aplicabilidad", "cert_control_tareas", "cert_pruebas", "cert_evidencias", "cert_entidades",
    "cert_auditores", "cert_accesos", "cert_accesos_registro", "cert_auditorias", "cert_hallazgos",
    "cert_acciones", "cert_certificados", "cert_incidentes", "cert_comunicaciones", "cert_proveedores",
    "cert_paquetes",
)


def _insp():
    return sa.inspect(op.get_bind())


def _tablas() -> set:
    return set(_insp().get_table_names())


def _indices(tabla: str) -> set:
    if tabla not in _tablas():
        return set()
    return {i["name"] for i in _insp().get_indexes(tabla)}


def _id():
    return sa.Column("id", sa.String(36), primary_key=True)


def _org():
    return sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                     nullable=False)


def _fk(nombre: str, destino: str, ondelete: str = "SET NULL", nullable: bool = True):
    return sa.Column(nombre, sa.String(36), sa.ForeignKey(f"{destino}.id", ondelete=ondelete), nullable=nullable)


def _u(nombre: str):
    return _fk(nombre, "users")


def _s(nombre: str, n: int, nullable: bool = True, defecto=None):
    return sa.Column(nombre, sa.String(n), nullable=nullable, server_default=defecto)


def _t(nombre: str, nullable: bool = True):
    return sa.Column(nombre, sa.Text(), nullable=nullable)


def _b(nombre: str, defecto: bool):
    return sa.Column(nombre, sa.Boolean(), nullable=False, server_default=sa.true() if defecto else sa.false())


def _i(nombre: str, defecto=None, nullable: bool = True):
    return sa.Column(nombre, sa.Integer(), nullable=nullable,
                     server_default=str(defecto) if defecto is not None else None)


def _d(nombre: str):
    return sa.Column(nombre, sa.Date(), nullable=True)


def _f(nombre: str, nullable: bool = True, ahora: bool = False):
    return sa.Column(nombre, _TZ, nullable=nullable, server_default=sa.func.now() if ahora else None)


def _alta():
    return [_f("created_at", ahora=True), _f("updated_at")]


def _definicion() -> dict:
    """Columnas de cada tabla (las mismas que el modelo)."""
    return {
        "cert_marcos": [
            _id(), _org(), _s("clave", 60, False), _s("nombre", 200, False), _s("version", 40),
            _s("version_anterior", 40), _b("publico", False), _t("niveles"), _t("descripcion"),
            _b("sembrado", False), _b("editado", False), _s("huella_semilla", 64), _b("activo", True), *_alta(),
        ],
        "cert_controles": [
            _id(), _org(), _s("clave_comun", 80, False), _s("titulo", 300, False), _t("descripcion"),
            _s("dominio", 80), _t("evidencia_sugerida"), _s("medible_por_plataforma", 60),
            _b("sembrado", False), _b("editado", False), _s("huella_semilla", 64), _b("activo", True), *_alta(),
        ],
        "cert_correspondencias": [
            _id(), _org(), _fk("control_id", "cert_controles", "CASCADE", False),
            _fk("marco_id", "cert_marcos", "CASCADE", False), _s("id_control", 60, False), _s("id_semilla", 60), _s("nivel", 30),
            _s("version_marco", 40), _t("texto_oficial"), _b("sembrado", False), _b("afectado_por_version", False),
            _f("created_at", ahora=True),
        ],
        "cert_configuracion": [
            _id(), _org(), _i("aviso_certificado_dias", 90, False), _i("aviso_auditoria_dias", 30, False),
            _i("caducidad_evidencia_dias", 365, False), _i("aviso_evidencia_dias", 30, False),
            _b("exigir_evidencia_aprobada", True), _i("acceso_auditor_max_dias", 30, False),
            _s("autoridad_nis2", 200), _i("nis2_alerta_horas", 24, False), _i("nis2_notificacion_horas", 72, False),
            _i("nis2_informe_final_dias", 30, False), _fk("proyecto_capa_id", "projects"), _u("updated_por"),
            _f("updated_at"),
        ],
        "cert_programas": [
            _id(), _org(), _s("codigo", 30, False), _s("nombre", 300, False), _t("descripcion"),
            _s("estado", 15, False, "borrador"), _t("alcance"), _t("objetivos"), _u("responsable_id"),
            _u("patrocinador_id"), _d("fecha_inicio"), _d("fecha_objetivo"), _fk("project_id", "projects"),
            _s("plantilla_clave", 80), _t("parametros"), _u("creado_por"), *_alta(),
        ],
        "cert_aplicabilidad": [
            _id(), _org(), _fk("programa_id", "cert_programas", "CASCADE", False),
            _fk("control_id", "cert_controles", "CASCADE", False), _s("sede", 120, False, ""), _b("aplica", True),
            _t("justificacion"), _s("estado", 15, False, "pendiente"), _s("eficacia", 15, False, "sin_evaluar"),
            _u("responsable_id"), _u("implantado_por"), _f("implantado_en"), _u("eficacia_por"), _f("eficacia_en"),
            _d("ultima_revision"), _s("medicion", 15), _f("medicion_en"), _t("medicion_detalle"), *_alta(),
        ],
        "cert_control_tareas": [
            _id(), _org(), _fk("aplicabilidad_id", "cert_aplicabilidad", "CASCADE", False),
            _fk("task_id", "tasks", "CASCADE", False), _f("created_at", ahora=True),
        ],
        "cert_pruebas": [
            _id(), _org(), _fk("aplicabilidad_id", "cert_aplicabilidad", "CASCADE", False),
            _s("tipo", 20, False), _d("periodo_desde"), _d("periodo_hasta"), _i("poblacion"), _i("muestra"),
            _t("metodo"), _s("resultado", 20, False, "pendiente"), _t("excepciones"), _u("probado_por"),
            _f("probado_en"), _t("notas"), _f("created_at", ahora=True),
        ],
        "cert_evidencias": [
            _id(), _org(), _fk("programa_id", "cert_programas", "CASCADE"),
            _fk("aplicabilidad_id", "cert_aplicabilidad", "CASCADE"),
            _fk("control_id", "cert_controles", "CASCADE", False), _s("titulo", 300, False), _s("tipo", 20, False),
            _s("origen", 15, False, "manual"), _fk("document_id", "documents"), _fk("task_id", "tasks"),
            _fk("compliance_evidence_id", "compliance_evidence"), _s("uri", 1000), _s("sha256", 64),
            _t("contenido"), _d("valida_desde"), _d("caduca_el"), _f("aviso_caducidad_en"), _u("creado_por"),
            _f("created_at", ahora=True),
        ],
        "cert_entidades": [
            _id(), _org(), _s("nombre", 200, False), _s("tipo", 30, False, "otra"), _t("acreditaciones"),
            _fk("subcontractor_id", "subcontractors"), _s("contacto_email", 255), _s("web", 300), _t("notas"),
            _b("activo", True), *_alta(),
        ],
        "cert_auditores": [
            _id(), _org(), _fk("entidad_id", "cert_entidades"), _s("nombre", 200, False), _s("email", 255),
            _t("cualificaciones"), _b("independencia_declarada", False), _t("conflictos_interes"),
            _d("nda_firmado_el"), _fk("nda_document_id", "documents"), _d("desde"), _d("hasta"), _b("activo", True),
            _f("suprimido_en"), *_alta(),
        ],
        "cert_accesos": [
            _id(), _org(), _fk("auditor_id", "cert_auditores", "CASCADE", False),
            _fk("programa_id", "cert_programas", "CASCADE", False), _s("token_hash", 64, False),
            _f("desde", False), _f("hasta", False), _f("revocado_en"), _u("revocado_por"), _u("creado_por"),
            _f("ultimo_uso_en"), _i("usos", 0, False), _f("created_at", ahora=True),
        ],
        "cert_accesos_registro": [
            _id(), _org(), _fk("acceso_id", "cert_accesos", "CASCADE", False), _s("recurso", 60, False),
            _s("detalle", 300), _s("ip", 64), _f("en", ahora=True),
        ],
        "cert_auditorias": [
            _id(), _org(), _fk("programa_id", "cert_programas", "CASCADE", False), _s("codigo", 30, False),
            _s("tipo", 25, False), _fk("marco_id", "cert_marcos"), _s("estado", 15, False, "planificada"),
            _d("fecha_inicio"), _d("fecha_fin"), _fk("entidad_id", "cert_entidades"),
            _fk("auditor_id", "cert_auditores"), _u("responsable_id"), _t("plan"), _t("agenda"), _t("muestras"),
            _t("resultado"), _s("conclusion", 20), _u("creado_por"), _f("cerrada_en"), *_alta(),
        ],
        "cert_hallazgos": [
            _id(), _org(), _fk("auditoria_id", "cert_auditorias", "CASCADE", False),
            _fk("programa_id", "cert_programas", "CASCADE", False), _s("codigo", 30, False), _s("tipo", 15, False),
            _fk("control_id", "cert_controles"), _s("titulo", 300, False), _t("descripcion"),
            _s("estado", 15, False, "abierto"), _d("fecha_limite"), _u("corregido_por"), _f("corregido_en"),
            _u("cerrado_por"), _f("cerrado_en"), _u("creado_por"), *_alta(),
        ],
        "cert_acciones": [
            _id(), _org(), _fk("hallazgo_id", "cert_hallazgos", "CASCADE", False), _t("analisis_causa"),
            _t("plan", False), _u("responsable_id"), _d("fecha_limite"), _s("estado", 15, False, "abierta"),
            _fk("task_id", "tasks"), _fk("project_id", "projects"), _u("hecho_por"), _f("hecho_en"),
            _t("verificacion"), _u("verificado_por"), _f("verificado_en"), _f("aviso_vencida_en"),
            _u("creado_por"), *_alta(),
        ],
        "cert_certificados": [
            _id(), _org(), _fk("programa_id", "cert_programas"), _fk("marco_id", "cert_marcos"),
            _s("numero", 120, False), _fk("entidad_id", "cert_entidades"), _t("alcance"), _s("nivel", 30),
            _d("emitido_el"), _d("valido_hasta"), _s("estado", 15, False, "vigente"), _s("enx_id", 60),
            _s("enx_ambito", 200), _d("proxima_auditoria"), _s("tipo_proxima", 20), _fk("document_id", "documents"),
            _f("aviso_vencimiento_en"), _f("aviso_auditoria_en"), _u("creado_por"), *_alta(),
        ],
        "cert_incidentes": [
            _id(), _org(), _fk("programa_id", "cert_programas"), _fk("ticket_id", "sd_tickets"),
            _s("codigo", 30, False), _s("titulo", 300, False), _t("descripcion"), _f("detectado_en", False),
            _b("significativo", True), _b("transfronterizo", False), _t("impacto"),
            _s("estado", 20, False, "abierto"), _s("autoridad", 200), _f("alerta_enviada_en"),
            _f("notificacion_enviada_en"), _f("informe_final_enviado_en"), _t("avisos"), _u("responsable_id"),
            _u("creado_por"), _f("cerrado_en"), *_alta(),
        ],
        "cert_comunicaciones": [
            _id(), _org(), _fk("incidente_id", "cert_incidentes", "CASCADE", False), _s("tipo", 25, False),
            _s("destinatario", 200), _s("asunto", 300), _t("contenido"), _s("referencia", 120),
            _f("enviado_en", False), _u("enviado_por"), _f("created_at", ahora=True),
        ],
        "cert_proveedores": [
            _id(), _org(), _fk("programa_id", "cert_programas"), _fk("subcontractor_id", "subcontractors"),
            _s("nombre", 200, False), _s("criticidad", 10, False, "alta"), _t("servicios"),
            _s("resultado", 20, False, "pendiente"), _t("riesgo"), _u("evaluado_por"), _d("evaluado_en"),
            _d("proxima_evaluacion"), _t("notas"), *_alta(),
        ],
        "cert_paquetes": [
            _id(), _org(), _fk("programa_id", "cert_programas", "CASCADE", False), _u("generado_por"),
            _fk("acceso_id", "cert_accesos"), _s("sha256", 64, False), _t("resumen"), _f("generado_en", ahora=True),
        ],
    }


#: Índices simples (los `index=True` del modelo) y únicos con la empresa delante.
def _indices_de() -> dict:
    simples = {
        "cert_marcos": ["organization_id"],
        "cert_controles": ["organization_id", "dominio"],
        "cert_correspondencias": ["organization_id", "control_id", "marco_id"],
        "cert_programas": ["organization_id", "estado", "responsable_id", "patrocinador_id", "project_id",
                           "creado_por"],
        "cert_aplicabilidad": ["organization_id", "programa_id", "control_id", "responsable_id", "implantado_por",
                               "eficacia_por"],
        "cert_control_tareas": ["organization_id", "aplicabilidad_id", "task_id"],
        "cert_pruebas": ["organization_id", "aplicabilidad_id", "probado_por"],
        "cert_evidencias": ["organization_id", "programa_id", "aplicabilidad_id", "control_id", "document_id",
                            "task_id", "compliance_evidence_id", "caduca_el", "creado_por", "created_at"],
        "cert_entidades": ["organization_id", "subcontractor_id"],
        "cert_auditores": ["organization_id", "entidad_id", "email"],
        "cert_accesos": ["organization_id", "auditor_id", "programa_id", "token_hash", "revocado_por", "creado_por"],
        "cert_accesos_registro": ["organization_id", "acceso_id", "en"],
        "cert_auditorias": ["organization_id", "programa_id", "estado", "responsable_id", "creado_por"],
        "cert_hallazgos": ["organization_id", "auditoria_id", "programa_id", "estado", "corregido_por",
                           "cerrado_por", "creado_por"],
        "cert_acciones": ["organization_id", "hallazgo_id", "responsable_id", "task_id", "hecho_por",
                          "verificado_por", "creado_por"],
        "cert_certificados": ["organization_id", "programa_id", "valido_hasta", "creado_por"],
        "cert_incidentes": ["organization_id", "ticket_id", "estado", "responsable_id", "creado_por"],
        "cert_comunicaciones": ["organization_id", "incidente_id", "enviado_por"],
        "cert_proveedores": ["organization_id", "programa_id", "subcontractor_id", "evaluado_por"],
        "cert_paquetes": ["organization_id", "programa_id", "generado_por", "generado_en"],
        "cert_configuracion": ["updated_por"],
    }
    unicos = {
        "cert_marcos": [("uq_cert_marcos_org_clave", ["organization_id", "clave"])],
        "cert_controles": [("uq_cert_controles_org_clave", ["organization_id", "clave_comun"])],
        "cert_correspondencias": [("uq_cert_correspondencias",
                                   ["organization_id", "marco_id", "id_control", "control_id"])],
        "cert_configuracion": [("ix_cert_configuracion_organization_id", ["organization_id"])],
        "cert_programas": [("uq_cert_programas_org_codigo", ["organization_id", "codigo"])],
        "cert_aplicabilidad": [("uq_cert_aplicabilidad", ["organization_id", "programa_id", "control_id", "sede"])],
        "cert_control_tareas": [("uq_cert_control_tareas", ["organization_id", "aplicabilidad_id", "task_id"])],
        "cert_entidades": [("uq_cert_entidades_org_nombre", ["organization_id", "nombre"])],
        "cert_accesos": [("uq_cert_accesos_org_token", ["organization_id", "token_hash"])],
        "cert_auditorias": [("uq_cert_auditorias_org_codigo", ["organization_id", "codigo"])],
        "cert_hallazgos": [("uq_cert_hallazgos_org_codigo", ["organization_id", "codigo"])],
        "cert_certificados": [("uq_cert_certificados_org_numero", ["organization_id", "numero"])],
        "cert_incidentes": [("uq_cert_incidentes_org_codigo", ["organization_id", "codigo"])],
    }
    return {"simples": simples, "unicos": unicos}


def upgrade() -> None:
    definicion = _definicion()
    existentes = _tablas()
    for tabla in TABLAS:
        if tabla in existentes:
            logger.info("212: %s ya existe", tabla)
            continue
        op.create_table(tabla, *definicion[tabla])
    indices = _indices_de()
    for tabla, columnas in indices["simples"].items():
        hay = _indices(tabla)
        for col in columnas:
            nombre = f"ix_{tabla}_{col}"
            if nombre not in hay:
                op.create_index(nombre, tabla, [col])
    for tabla, lista in indices["unicos"].items():
        hay = _indices(tabla)
        for nombre, columnas in lista:
            if nombre not in hay:
                op.create_index(nombre, tabla, columnas, unique=True)


def downgrade() -> None:
    existentes = _tablas()
    for tabla in reversed(TABLAS):
        if tabla in existentes:
            op.drop_table(tabla)
