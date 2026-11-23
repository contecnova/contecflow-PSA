"""Flujo de demanda configurable por empresa (22-11-2026, docs/FLUJO_DE_DEMANDA.md).

Tablas nuevas (8), todas con `organization_id`:

- `demand_request_types`: tipos de solicitud (canales, alcances, flujo).
- `demand_flows`: definición JSON versionada del flujo.
- `demand_requests`: el expediente (estado, fase, ronda, datos, foto del flujo,
  plazo, pausa, comité, resultado y acciones ejecutadas).
- `demand_step_states`: estado de cada paso por fase y ronda (votos).
- `demand_transitions`: log inmutable con hash encadenado.
- `demand_field_versions`: versiones de campos críticos (append-only).
- `demand_documents`: repositorio documental por fase (fichero en el almacén).
- `demand_comments`: comentarios internos o visibles para el cliente.

Datos personales: nombres de autores (copiados para que el log no cambie si
cambia el usuario), textos de la ficha y adjuntos (`personal_data` los marca).
Retención: tipo `demand_requests` (cerrados, desde el cierre) con bloqueo legal.

Datos: si existe la empresa de demostración (`contecflow-demo`) y no tiene
flujos de demanda, se le instala la plantilla piloto (grupos aprobadores
vacíos, flujo «Demanda Digital (piloto)» y tres tipos). Si falla, la migración
sigue: la plantilla se puede cargar luego desde Configuración.

Idempotente: cada tabla e índice se crea solo si no existe. Downgrade: borra
las 8 tablas (y con ellas los expedientes).

Revision ID: 195_flujo_de_demanda
Revises: 194_indice_de_riesgo
"""
import sqlalchemy as sa
from alembic import op

revision = "195_flujo_de_demanda"
down_revision = "194_indice_de_riesgo"
branch_labels = None
depends_on = None

_TZ = sa.DateTime(timezone=True)


def _id():
    return sa.Column("id", sa.String(36), primary_key=True)


def _org():
    return sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                     nullable=True)


def _req():
    return sa.Column("request_id", sa.String(36), sa.ForeignKey("demand_requests.id", ondelete="CASCADE"),
                     nullable=False)


def _usuario(nombre):
    return sa.Column(nombre, sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


def _cliente(nombre):
    return sa.Column(nombre, sa.String(36), sa.ForeignKey("client_users.id", ondelete="SET NULL"), nullable=True)


def _creado():
    return sa.Column("created_at", _TZ, server_default=sa.func.now())


TABLAS = {
    "demand_flows": lambda: [
        _id(), _org(), sa.Column("key", sa.String(60)), sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text()), sa.Column("definition", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        _usuario("created_by"), _usuario("updated_by"), _creado(), sa.Column("updated_at", _TZ)],
    "demand_request_types": lambda: [
        _id(), _org(), sa.Column("key", sa.String(60), nullable=False), sa.Column("name", sa.String(200), nullable=False),
        sa.Column("name_i18n", sa.Text()), sa.Column("channels", sa.Text()), sa.Column("scopes", sa.Text()),
        sa.Column("description", sa.Text()),
        sa.Column("requires_project", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("allows_standalone", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("flow_id", sa.String(36), sa.ForeignKey("demand_flows.id", ondelete="SET NULL")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        _creado(), sa.Column("updated_at", _TZ)],
    "demand_requests": lambda: [
        _id(), _org(), sa.Column("code", sa.String(30), nullable=False),
        sa.Column("type_id", sa.String(36), sa.ForeignKey("demand_request_types.id", ondelete="SET NULL")),
        sa.Column("type_key", sa.String(60), nullable=False),
        sa.Column("flow_id", sa.String(36), sa.ForeignKey("demand_flows.id", ondelete="SET NULL")),
        sa.Column("flow_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("flow_snapshot", sa.Text(), nullable=False),
        sa.Column("origin", sa.String(30), nullable=False, server_default="operator"),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="SET NULL")),
        sa.Column("standalone", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("scope_kind", sa.String(20)), sa.Column("scope_ref_id", sa.String(36)),
        sa.Column("executed_actions", sa.Text()),
        sa.Column("client_id", sa.String(36), sa.ForeignKey("clients.id", ondelete="SET NULL")),
        _cliente("client_user_id"), _usuario("requester_user_id"), _usuario("created_by_user_id"),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("current_phase_key", sa.String(60)),
        sa.Column("phase_round", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("phase_entered_at", _TZ), sa.Column("sla_due_at", _TZ),
        sa.Column("sla_warned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sla_breached", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("paused_since", _TZ), sa.Column("paused_seconds", sa.Float(), nullable=False, server_default="0"),
        sa.Column("data", sa.Text()),
        sa.Column("client_locked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("committee_required", sa.Boolean()), sa.Column("committee_reasons", sa.Text()),
        sa.Column("committee_date", _TZ), sa.Column("result_kind", sa.String(20)),
        sa.Column("result_project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="SET NULL")),
        sa.Column("result_change_request_id", sa.String(36), sa.ForeignKey("change_requests.id", ondelete="SET NULL")),
        sa.Column("result_proposal_id", sa.String(36), sa.ForeignKey("portfolio_proposals.id", ondelete="SET NULL")),
        sa.Column("submitted_at", _TZ), sa.Column("closed_at", _TZ), _creado(), sa.Column("updated_at", _TZ)],
    "demand_step_states": lambda: [
        _id(), _org(), _req(), sa.Column("phase_key", sa.String(60), nullable=False),
        sa.Column("round", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("step_key", sa.String(60), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("votes", sa.Text()), _usuario("decided_by"), sa.Column("decided_at", _TZ),
        sa.Column("note", sa.Text()), sa.Column("approval_request_id", sa.String(36)), _creado()],
    "demand_transitions": lambda: [
        _id(), _org(), _req(), sa.Column("seq", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("from_phase", sa.String(60)), sa.Column("to_phase", sa.String(60)),
        sa.Column("step_key", sa.String(60)), sa.Column("decision", sa.String(30), nullable=False),
        sa.Column("from_status", sa.String(20)), sa.Column("to_status", sa.String(20)),
        _usuario("actor_user_id"), _cliente("actor_client_id"), sa.Column("actor_name", sa.String(255)),
        sa.Column("actor_role", sa.String(60)), sa.Column("justification", sa.Text()),
        sa.Column("is_bypass", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("payload", sa.Text()), sa.Column("prev_hash", sa.String(64)), sa.Column("hash", sa.String(64)),
        _creado()],
    "demand_field_versions": lambda: [
        _id(), _org(), _req(), sa.Column("field", sa.String(60), nullable=False), sa.Column("value", sa.Text()),
        sa.Column("source", sa.String(20), nullable=False), sa.Column("phase_key", sa.String(60)),
        _usuario("author_user_id"), _cliente("author_client_id"), sa.Column("author_name", sa.String(255)),
        sa.Column("note", sa.Text()), _creado()],
    "demand_documents": lambda: [
        _id(), _org(), _req(),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("file_key", sa.String(500)), sa.Column("phase_key", sa.String(60)),
        sa.Column("tag", sa.String(40), nullable=False, server_default="other"),
        sa.Column("file_name", sa.String(255), nullable=False), sa.Column("mime", sa.String(120)),
        sa.Column("size", sa.Integer()),
        sa.Column("is_annex", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("personal_data", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("internal", sa.Boolean(), nullable=False, server_default=sa.false()),
        _usuario("uploaded_by_user_id"), _cliente("uploaded_by_client_id"),
        sa.Column("uploaded_by_name", sa.String(255)), _creado()],
    "demand_comments": lambda: [
        _id(), _org(), _req(), sa.Column("phase_key", sa.String(60)), sa.Column("body", sa.Text(), nullable=False),
        sa.Column("internal", sa.Boolean(), nullable=False, server_default=sa.false()),
        _usuario("author_user_id"), _cliente("author_client_id"), sa.Column("author_name", sa.String(255)),
        _creado()],
}

#: (tabla, columnas) de los índices; el nombre es ix_<tabla>_<columna> como en los modelos (index=True).
INDICES = (
    ("demand_flows", ("organization_id",)),
    ("demand_request_types", ("organization_id",)), ("demand_request_types", ("flow_id",)),
    ("demand_requests", ("organization_id",)), ("demand_requests", ("code",)), ("demand_requests", ("type_id",)),
    ("demand_requests", ("flow_id",)), ("demand_requests", ("project_id",)), ("demand_requests", ("client_id",)),
    ("demand_requests", ("client_user_id",)), ("demand_requests", ("requester_user_id",)),
    ("demand_requests", ("status",)), ("demand_requests", ("current_phase_key",)),
    ("demand_requests", ("sla_due_at",)), ("demand_requests", ("scope_ref_id",)),
    ("demand_step_states", ("organization_id",)), ("demand_step_states", ("request_id",)),
    ("demand_step_states", ("approval_request_id",)),
    ("demand_transitions", ("organization_id",)), ("demand_transitions", ("request_id",)),
    ("demand_transitions", ("decision",)), ("demand_transitions", ("created_at",)),
    ("demand_field_versions", ("organization_id",)), ("demand_field_versions", ("request_id",)),
    ("demand_documents", ("organization_id",)), ("demand_documents", ("request_id",)),
    ("demand_comments", ("organization_id",)), ("demand_comments", ("request_id",)),
)


def _tablas() -> set:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _indices(tabla: str) -> set:
    return {i["name"] for i in sa.inspect(op.get_bind()).get_indexes(tabla)}


def _sembrar_demo() -> None:
    """Ya no siembra nada (23-11-2026): la plantilla es opcional y se instala desde la biblioteca de Demanda."""
    return
    bind = op.get_bind()
    org = bind.execute(sa.text("SELECT id FROM organizations WHERE slug = 'contecflow-demo'")).scalar()
    if not org:
        return
    if bind.execute(sa.text("SELECT COUNT(*) FROM demand_flows WHERE organization_id = :o"), {"o": org}).scalar():
        return
    from sqlalchemy.orm import Session
    from app.services.demanda.plantillas import sembrar_plantilla_piloto
    sesion = Session(bind=bind)
    try:
        sesion.info["organization_id"] = org
        sembrar_plantilla_piloto(sesion, org, None)
        sesion.flush()
    finally:
        sesion.close()


def upgrade() -> None:
    existentes = _tablas()
    for tabla, columnas in TABLAS.items():
        if tabla not in existentes:
            op.create_table(tabla, *columnas())
    for tabla, cols in INDICES:
        nombre = f"ix_{tabla}_{'_'.join(cols)}"
        if nombre not in _indices(tabla):
            op.create_index(nombre, tabla, list(cols))
    try:
        _sembrar_demo()
    except Exception as exc:  # la plantilla se puede cargar desde Configuración
        print(f"  195: no se sembró la plantilla piloto en la demo ({exc})")


def downgrade() -> None:
    existentes = _tablas()
    for tabla in reversed(list(TABLAS)):
        if tabla in existentes:
            op.drop_table(tabla)
