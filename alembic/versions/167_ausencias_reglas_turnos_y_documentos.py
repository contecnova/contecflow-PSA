"""Ausencias gobernadas por reglas: tipos, turnos, cupos y documentos (tarea #25).

Esquema (ver `app/models/ausencias.py`):
  · tipos_de_ausencia (sustituye al enum `absencetype`), tipos_de_documento_de_ausencia,
    requisitos_documentales_de_tipo;
  · turnos, patrones_de_turnos, miembros_de_patron, asignaciones_de_turno (cuadrante);
  · huecos_de_cupo, reservas_de_cupo (cupos con bloqueo de fila y lista de espera);
  · requisitos_de_ausencia, documentos_de_ausencia, eventos_de_ausencia,
    acceso_especial_ausencias;
  · absences: `type` pasa de enum a VARCHAR(50) (la clave del tipo) y entran
    absence_type_id, shift_id, substitute_id, unit, amount, half_day_start,
    half_day_end, hours y requested_at; `absencestatus` gana `waitlisted`.

Datos: en cada empresa se crean los siete tipos del enum antiguo (`de_sistema`,
mismas claves: el API antiguo sigue valiendo) y tres tipos de documento; cada
ausencia existente apunta a su tipo (por la empresa de la ausencia o, si no la
tiene, la de su persona), con `unit = dias`, `amount = working_days` y
`requested_at = created_at`. No se crean requisitos ni cupos: eso lo decide
cada empresa (o la acción «Cargar ejemplos», que nunca se aplica sola).

Idempotente: cada tabla y columna solo si falta; los tipos solo si la empresa
no tiene ya esa clave.
"""
from __future__ import annotations

import json
import uuid
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "167_ausencias_reglas_turnos_y_documentos"
down_revision: Union[str, None] = "166_gastos_sobre_el_motor_de_politicas"
branch_labels = None
depends_on = None

#: (clave, es, en, zh, color, icono, descuenta, saldo, visibilidad, especiales, orden)
TIPOS = (
    ("vacation", "Vacaciones", "Vacation", "休假", "#2fb37f", "sun", True, "vacaciones", "equipo", False, 10),
    ("sick", "Baja médica", "Sick leave", "病假", "#e5534b", "stethoscope", False, None, "privada", True, 20),
    ("personal", "Asunto personal", "Personal", "事假", "#8b6cf6", "user", False, None, "equipo", False, 30),
    ("training", "Formación", "Training", "培训", "#3b82f6", "graduation", False, None, "todos", False, 40),
    ("maternity", "Maternidad", "Maternity", "产假", "#ec4899", "baby", False, None, "privada", True, 50),
    ("paternity", "Paternidad", "Paternity", "陪产假", "#06b6d4", "baby", False, None, "privada", False, 60),
    ("other", "Otro", "Other", "其他", "#7a8aaa", "circle", False, None, "equipo", False, 70),
)
#: (clave, es, en, zh, categoria_especial, orden)
DOCUMENTOS = (
    ("parte_de_baja", "Parte de baja", "Sick-leave certificate", "病假证明", True, 10),
    ("parte_de_confirmacion", "Parte de confirmación", "Extension report", "续假证明", True, 20),
    ("justificante", "Justificante", "Supporting document", "证明文件", False, 30),
)


def _insp():
    return sa.inspect(op.get_bind())


def _tablas() -> set:
    return set(_insp().get_table_names())


def _columnas(tabla) -> set:
    return {c["name"] for c in _insp().get_columns(tabla)}


def _org():
    return sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)


def _usuario(nombre, ondelete="SET NULL", nullable=True):
    return sa.Column(nombre, sa.String(36), sa.ForeignKey("users.id", ondelete=ondelete), nullable=nullable)


def _indices(tabla, *columnas):
    for c in columnas:
        op.create_index(f"ix_{tabla}_{c}", tabla, [c])


def _crear(nombre, *columnas, indices=(), extra=()):
    if nombre in _tablas():
        return
    op.create_table(nombre, sa.Column("id", sa.String(36), primary_key=True), _org(), *columnas, *extra)
    _indices(nombre, "organization_id", *indices)


def _esquema() -> None:
    ahora = sa.func.now()
    _crear("tipos_de_documento_de_ausencia",
           sa.Column("clave", sa.String(50), nullable=False),
           sa.Column("nombre", sa.String(120), nullable=False),
           sa.Column("nombres", sa.Text(), nullable=True),
           sa.Column("categoria_especial", sa.Boolean(), nullable=False),
           sa.Column("activo", sa.Boolean(), nullable=False),
           sa.Column("orden", sa.Integer(), nullable=False),
           sa.Column("created_at", sa.DateTime(timezone=True), server_default=ahora, nullable=True),
           extra=(sa.UniqueConstraint("organization_id", "clave", name="uq_tipos_doc_ausencia_org_clave"),))
    _crear("tipos_de_ausencia",
           sa.Column("clave", sa.String(50), nullable=False),
           sa.Column("nombre", sa.String(120), nullable=False),
           sa.Column("nombres", sa.Text(), nullable=True),
           sa.Column("color", sa.String(9), nullable=False),
           sa.Column("icono", sa.String(40), nullable=False),
           sa.Column("descuenta_saldo", sa.Boolean(), nullable=False),
           sa.Column("saldo", sa.String(12), nullable=True),
           sa.Column("cupo_anual", sa.Float(), nullable=True),
           sa.Column("unidad", sa.String(12), nullable=False),
           sa.Column("visibilidad", sa.String(12), nullable=False),
           sa.Column("workflow_id", sa.String(36), sa.ForeignKey("approval_workflows.id", ondelete="SET NULL"), nullable=True),
           sa.Column("requiere_aprobacion", sa.Boolean(), nullable=False),
           sa.Column("requiere_sustituto", sa.Boolean(), nullable=False),
           sa.Column("datos_especiales", sa.Boolean(), nullable=False),
           sa.Column("activo", sa.Boolean(), nullable=False),
           sa.Column("orden", sa.Integer(), nullable=False),
           sa.Column("de_sistema", sa.Boolean(), nullable=False),
           sa.Column("created_at", sa.DateTime(timezone=True), server_default=ahora, nullable=True),
           sa.Column("updated_at", sa.DateTime(timezone=True), server_default=ahora, nullable=True),
           indices=("workflow_id",),
           extra=(sa.UniqueConstraint("organization_id", "clave", name="uq_tipos_de_ausencia_org_clave"),))
    _crear("requisitos_documentales_de_tipo",
           sa.Column("tipo_de_ausencia_id", sa.String(36), sa.ForeignKey("tipos_de_ausencia.id", ondelete="CASCADE"), nullable=False),
           sa.Column("tipo_de_documento_id", sa.String(36),
                     sa.ForeignKey("tipos_de_documento_de_ausencia.id", ondelete="CASCADE"), nullable=False),
           sa.Column("obligatorio", sa.Boolean(), nullable=False),
           sa.Column("plazo_dias", sa.Integer(), nullable=False),
           sa.Column("plazo_desde", sa.String(12), nullable=False),
           sa.Column("repetir_cada_dias", sa.Integer(), nullable=True),
           sa.Column("recordar_dias_antes", sa.Integer(), nullable=False),
           sa.Column("escalar_dias_despues", sa.Integer(), nullable=True),
           sa.Column("escalar_a", sa.Text(), nullable=True),
           sa.Column("orden", sa.Integer(), nullable=False),
           indices=("tipo_de_ausencia_id", "tipo_de_documento_id"))
    _crear("turnos",
           sa.Column("nombre", sa.String(80), nullable=False),
           sa.Column("color", sa.String(9), nullable=False),
           sa.Column("hora_inicio", sa.Time(), nullable=False),
           sa.Column("hora_fin", sa.Time(), nullable=False),
           sa.Column("dias_semana", sa.Text(), nullable=True),
           sa.Column("equipo", sa.String(120), nullable=True),
           sa.Column("departamento", sa.String(100), nullable=True),
           sa.Column("office_id", sa.String(36), sa.ForeignKey("offices.id", ondelete="SET NULL"), nullable=True),
           sa.Column("personas_requeridas", sa.Integer(), nullable=False),
           sa.Column("trabaja_festivos", sa.Boolean(), nullable=False),
           sa.Column("activo", sa.Boolean(), nullable=False),
           sa.Column("orden", sa.Integer(), nullable=False),
           sa.Column("created_at", sa.DateTime(timezone=True), server_default=ahora, nullable=True),
           sa.Column("updated_at", sa.DateTime(timezone=True), server_default=ahora, nullable=True),
           indices=("office_id",))
    _crear("patrones_de_turnos",
           sa.Column("nombre", sa.String(120), nullable=False),
           sa.Column("ciclo", sa.Text(), nullable=False),
           sa.Column("inicio", sa.Date(), nullable=False),
           sa.Column("activo", sa.Boolean(), nullable=False),
           sa.Column("created_at", sa.DateTime(timezone=True), server_default=ahora, nullable=True),
           sa.Column("updated_at", sa.DateTime(timezone=True), server_default=ahora, nullable=True))
    _crear("miembros_de_patron",
           sa.Column("patron_id", sa.String(36), sa.ForeignKey("patrones_de_turnos.id", ondelete="CASCADE"), nullable=False),
           _usuario("user_id", "CASCADE", False),
           sa.Column("desde", sa.Date(), nullable=False),
           sa.Column("hasta", sa.Date(), nullable=True),
           sa.Column("desfase", sa.Integer(), nullable=False),
           indices=("patron_id", "user_id"))
    _crear("asignaciones_de_turno",
           _usuario("user_id", "CASCADE", False),
           sa.Column("fecha", sa.Date(), nullable=False),
           sa.Column("turno_id", sa.String(36), sa.ForeignKey("turnos.id", ondelete="CASCADE"), nullable=True),
           sa.Column("nota", sa.String(255), nullable=True),
           _usuario("created_by"),
           sa.Column("created_at", sa.DateTime(timezone=True), server_default=ahora, nullable=True),
           indices=("user_id", "fecha", "turno_id", "created_by"),
           extra=(sa.UniqueConstraint("user_id", "fecha", name="uq_asignaciones_de_turno_user_fecha"),))
    _crear("huecos_de_cupo",
           sa.Column("clave", sa.String(64), nullable=False),
           sa.Column("fecha", sa.Date(), nullable=False),
           sa.Column("turno", sa.String(36), nullable=False),
           sa.Column("grupo", sa.String(160), nullable=False),
           sa.Column("capacidad", sa.Integer(), nullable=False),
           sa.Column("ocupadas", sa.Integer(), nullable=False),
           sa.Column("version", sa.Integer(), nullable=False),
           sa.Column("updated_at", sa.DateTime(timezone=True), server_default=ahora, nullable=True),
           extra=(sa.UniqueConstraint("organization_id", "clave", "fecha", "turno", "grupo", name="uq_huecos_de_cupo"),))
    _crear("reservas_de_cupo",
           sa.Column("hueco_id", sa.String(36), sa.ForeignKey("huecos_de_cupo.id", ondelete="CASCADE"), nullable=False),
           sa.Column("absence_id", sa.String(36), sa.ForeignKey("absences.id", ondelete="CASCADE"), nullable=False),
           sa.Column("estado", sa.String(10), nullable=False),
           sa.Column("pedida_en", sa.DateTime(timezone=True), nullable=False),
           sa.Column("por_encima", sa.Boolean(), nullable=False),
           sa.Column("created_at", sa.DateTime(timezone=True), server_default=ahora, nullable=True),
           sa.Column("updated_at", sa.DateTime(timezone=True), server_default=ahora, nullable=True),
           indices=("hueco_id", "absence_id"),
           extra=(sa.UniqueConstraint("hueco_id", "absence_id", name="uq_reservas_de_cupo_hueco_ausencia"),))
    if "ix_reservas_de_cupo_hueco_estado" not in {i["name"] for i in _insp().get_indexes("reservas_de_cupo")}:
        op.create_index("ix_reservas_de_cupo_hueco_estado", "reservas_de_cupo", ["hueco_id", "estado", "pedida_en"])
    _crear("requisitos_de_ausencia",
           sa.Column("absence_id", sa.String(36), sa.ForeignKey("absences.id", ondelete="CASCADE"), nullable=False),
           sa.Column("tipo_id", sa.String(36), sa.ForeignKey("tipos_de_documento_de_ausencia.id", ondelete="CASCADE"), nullable=False),
           sa.Column("regla_id", sa.String(36), sa.ForeignKey("requisitos_documentales_de_tipo.id", ondelete="SET NULL"), nullable=True),
           sa.Column("origen", sa.String(10), nullable=False),
           sa.Column("secuencia", sa.Integer(), nullable=False),
           sa.Column("vence", sa.Date(), nullable=False),
           sa.Column("estado", sa.String(12), nullable=False),
           sa.Column("recordado_en", sa.DateTime(timezone=True), nullable=True),
           sa.Column("escalado_en", sa.DateTime(timezone=True), nullable=True),
           sa.Column("nota", sa.String(500), nullable=True),
           _usuario("pedido_por"),
           sa.Column("created_at", sa.DateTime(timezone=True), server_default=ahora, nullable=True),
           indices=("absence_id", "tipo_id", "regla_id", "vence", "pedido_por"))
    _crear("documentos_de_ausencia",
           sa.Column("absence_id", sa.String(36), sa.ForeignKey("absences.id", ondelete="CASCADE"), nullable=False),
           _usuario("user_id", "CASCADE", False),
           sa.Column("tipo_id", sa.String(36), sa.ForeignKey("tipos_de_documento_de_ausencia.id", ondelete="SET NULL"), nullable=True),
           sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
           sa.Column("version", sa.Integer(), nullable=False),
           sa.Column("estado", sa.String(12), nullable=False),
           sa.Column("sustituye_a", sa.String(36), sa.ForeignKey("documentos_de_ausencia.id", ondelete="SET NULL"), nullable=True),
           sa.Column("requisito_id", sa.String(36), sa.ForeignKey("requisitos_de_ausencia.id", ondelete="SET NULL"), nullable=True),
           sa.Column("especial", sa.Boolean(), nullable=False),
           sa.Column("nota", sa.String(500), nullable=True),
           _usuario("subido_por"),
           sa.Column("subido_en", sa.DateTime(timezone=True), server_default=ahora, nullable=False),
           indices=("absence_id", "user_id", "tipo_id", "document_id", "sustituye_a", "requisito_id", "subido_por"))
    _crear("eventos_de_ausencia",
           sa.Column("absence_id", sa.String(36), sa.ForeignKey("absences.id", ondelete="CASCADE"), nullable=False),
           sa.Column("tipo", sa.String(30), nullable=False),
           _usuario("actor_id"),
           sa.Column("datos", sa.Text(), nullable=True),
           sa.Column("created_at", sa.DateTime(timezone=True), server_default=ahora, nullable=True),
           indices=("absence_id", "actor_id", "created_at"))
    _crear("acceso_especial_ausencias",
           _usuario("user_id", "CASCADE", False),
           _usuario("concedido_por"),
           sa.Column("created_at", sa.DateTime(timezone=True), server_default=ahora, nullable=True),
           indices=("user_id", "concedido_por"),
           extra=(sa.UniqueConstraint("organization_id", "user_id", name="uq_acceso_especial_ausencias"),))


def _absences() -> None:
    bind = op.get_bind()
    pg = bind.dialect.name == "postgresql"
    tipo = next(c for c in _insp().get_columns("absences") if c["name"] == "type")
    if pg:
        with op.get_context().autocommit_block():
            op.execute("ALTER TYPE absencestatus ADD VALUE IF NOT EXISTS 'waitlisted'")
        if not isinstance(tipo["type"], sa.String) or isinstance(tipo["type"], sa.Enum):
            op.execute("ALTER TABLE absences ALTER COLUMN type TYPE VARCHAR(50) USING type::text")
            op.execute("DROP TYPE IF EXISTS absencetype")
    else:
        with op.batch_alter_table("absences") as b:
            # En SQLite el enum es texto sin CHECK (SQLAlchemy 2): `waitlisted` ya cabe.
            b.alter_column("type", type_=sa.String(50), existing_nullable=False)
    nuevas = (
        sa.Column("absence_type_id", sa.String(36), sa.ForeignKey("tipos_de_ausencia.id", ondelete="SET NULL", name="absences_absence_type_id_fkey"), nullable=True),
        sa.Column("shift_id", sa.String(36), sa.ForeignKey("turnos.id", ondelete="SET NULL", name="absences_shift_id_fkey"), nullable=True),
        sa.Column("substitute_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL", name="absences_substitute_id_fkey"), nullable=True),
        sa.Column("unit", sa.String(12), nullable=True),
        sa.Column("amount", sa.Float(), nullable=True),
        sa.Column("half_day_start", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("half_day_end", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("hours", sa.Float(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=True),
    )
    existentes = _columnas("absences")
    faltan = [c for c in nuevas if c.name not in existentes]
    if faltan:
        with op.batch_alter_table("absences") as b:
            for c in faltan:
                b.add_column(c)
    indices = {i["name"] for i in _insp().get_indexes("absences")}
    for c in ("absence_type_id", "shift_id", "substitute_id"):
        if f"ix_absences_{c}" not in indices:
            op.create_index(f"ix_absences_{c}", "absences", [c])


def _datos() -> None:
    conn = op.get_bind()
    orgs = [o for (o,) in conn.execute(sa.text("SELECT id FROM organizations"))]
    for org in orgs:
        tienen = {c for (c,) in conn.execute(sa.text("SELECT clave FROM tipos_de_ausencia WHERE organization_id = :o"), {"o": org})}
        for clave, es, en, zh, color, icono, descuenta, saldo, vis, especiales, orden in TIPOS:
            if clave in tienen:
                continue
            conn.execute(sa.text(
                "INSERT INTO tipos_de_ausencia (id, organization_id, clave, nombre, nombres, color, icono, descuenta_saldo,"
                " saldo, cupo_anual, unidad, visibilidad, workflow_id, requiere_aprobacion, requiere_sustituto,"
                " datos_especiales, activo, orden, de_sistema)"
                " VALUES (:id, :o, :clave, :nombre, :nombres, :color, :icono, :descuenta, :saldo, NULL, 'dias', :vis,"
                " NULL, :aprob, :sust, :esp, :activo, :orden, :sistema)"),
                {"id": str(uuid.uuid4()), "o": org, "clave": clave, "nombre": es,
                 "nombres": json.dumps({"es": es, "en": en, "zh": zh}, ensure_ascii=False), "color": color,
                 "icono": icono, "descuenta": descuenta, "saldo": saldo, "vis": vis, "aprob": True, "sust": False,
                 "esp": especiales, "activo": True, "orden": orden, "sistema": True})
        hay = {c for (c,) in conn.execute(sa.text(
            "SELECT clave FROM tipos_de_documento_de_ausencia WHERE organization_id = :o"), {"o": org})}
        for clave, es, en, zh, especial, orden in DOCUMENTOS:
            if clave in hay:
                continue
            conn.execute(sa.text(
                "INSERT INTO tipos_de_documento_de_ausencia (id, organization_id, clave, nombre, nombres,"
                " categoria_especial, activo, orden) VALUES (:id, :o, :clave, :nombre, :nombres, :esp, :activo, :orden)"),
                {"id": str(uuid.uuid4()), "o": org, "clave": clave, "nombre": es,
                 "nombres": json.dumps({"es": es, "en": en, "zh": zh}, ensure_ascii=False), "esp": especial,
                 "activo": True, "orden": orden})
    # Cada ausencia a su tipo: por su empresa o, si no la tiene, por la de su persona.
    conn.execute(sa.text("""
        UPDATE absences SET absence_type_id = (
            SELECT t.id FROM tipos_de_ausencia t
            WHERE t.clave = absences.type
              AND t.organization_id = COALESCE(absences.organization_id,
                    (SELECT u.organization_id FROM users u WHERE u.id = absences.user_id)))
        WHERE absence_type_id IS NULL"""))
    conn.execute(sa.text("UPDATE absences SET unit = 'dias' WHERE unit IS NULL"))
    conn.execute(sa.text("UPDATE absences SET amount = working_days WHERE amount IS NULL"))
    conn.execute(sa.text("UPDATE absences SET requested_at = created_at WHERE requested_at IS NULL"))


def upgrade() -> None:
    _esquema()
    _absences()
    _datos()


def downgrade() -> None:
    bind = op.get_bind()
    pg = bind.dialect.name == "postgresql"
    # Las claves nuevas no caben en el enum antiguo: pasan a «other». Las que
    # estaban en espera vuelven a pendientes.
    claves = "('vacation', 'sick', 'personal', 'training', 'maternity', 'paternity', 'other')"
    op.execute(f"UPDATE absences SET type = 'other' WHERE type NOT IN {claves}")
    op.execute("UPDATE absences SET status = 'pending' WHERE status = 'waitlisted'")
    for c in ("absence_type_id", "shift_id", "substitute_id"):
        op.drop_index(f"ix_absences_{c}", table_name="absences")
    with op.batch_alter_table("absences") as b:
        for c in ("requested_at", "hours", "half_day_end", "half_day_start", "amount", "unit", "substitute_id",
                  "shift_id", "absence_type_id"):
            b.drop_column(c)
    if pg:
        op.execute("CREATE TYPE absencetype AS ENUM " + claves)
        op.execute("ALTER TABLE absences ALTER COLUMN type TYPE absencetype USING type::absencetype")
    else:
        with op.batch_alter_table("absences") as b:
            b.alter_column("type", type_=sa.Enum("vacation", "sick", "personal", "training", "maternity", "paternity",
                                                 "other", name="absencetype"), existing_nullable=False)
    for tabla in ("acceso_especial_ausencias", "eventos_de_ausencia", "documentos_de_ausencia", "requisitos_de_ausencia",
                  "reservas_de_cupo", "huecos_de_cupo", "asignaciones_de_turno", "miembros_de_patron",
                  "patrones_de_turnos", "turnos", "requisitos_documentales_de_tipo", "tipos_de_ausencia",
                  "tipos_de_documento_de_ausencia"):
        if tabla in _tablas():
            op.drop_table(tabla)
