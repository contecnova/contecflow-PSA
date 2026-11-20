"""Proveedores y externalizacion (19-11-2026).

Diseno: docs/PROVEEDORES_Y_EXTERNALIZACION.md. Servicios: app/services/proveedores/.

Esquema:

- `subcontractors`: kind (freelance | company), engagement_modes (JSON),
  lifecycle_status, freelancer_worker_id, alm_vendor_id, internal_owner_id,
  legal_name, website, address, training_enabled, data_access,
  data_categories, systems_access, risk_level, risk_score, next_review_date,
  suspended_at, offboarded_at, offboarding_reason.
- `tasks`: supplier_id y supplier_work_package_id (tarea externalizada).
- `subcontractor_invoices`: created_by (segregacion) y contract_id.
- Tablas nuevas: supplier_contracts, supplier_services, supplier_work_packages,
  supplier_pricing_lines, supplier_reports, supplier_statements,
  supplier_usage_records, supplier_documents, supplier_risk_assessments,
  supplier_access_grants; catalogos custom_supplier_service_types y
  custom_supplier_billing_units (con los valores del sistema).

Datos existentes (conservados y clasificados):

- Freelance si tiene exactamente una persona activa y su nombre coincide con el
  del proveedor (sin mayusculas ni acentos) o el NIF es de persona fisica
  (DNI/NIE). `freelancer_worker_id` = esa persona. Si no, empresa.
- Modos: staff_augmentation si tiene personas; outsourcing si tiene
  asignaciones sin persona; freelance sin modos -> staff_augmentation.
- lifecycle_status: active, u offboarded si `is_active` es falso.
- Un contrato «migrado» por proveedor con tarifas, asignaciones o facturas,
  con una linea por recurso (hora) por tarifa activa.
- Cada asignacion SIN persona pasa a un paquete de trabajo de alcance proyecto
  (precio = importe del pedido) y queda inactiva: desde ahora a una empresa
  solo se le asigna trabajo como paquete.

Las tablas nuevas se crean desde su modelo (`checkfirst`): idempotente. La
politica RLS de cada tabla la aplica env.py.

Downgrade: reactiva las asignaciones convertidas, borra tablas y columnas.

Revision ID: 189_proveedores_y_externalizacion
Revises: 188_asistente_de_reuniones
"""
import json
import re
import unicodedata
import uuid

import sqlalchemy as sa
from alembic import op

revision = "189_proveedores_y_externalizacion"
down_revision = "188_asistente_de_reuniones"
branch_labels = None
depends_on = None

SERVICIOS = (("soc", "SOC / monitorización de seguridad", "#ec4899"), ("service_desk", "Service desk", "#00d4ff"),
             ("helpdesk_l1", "Soporte de primer nivel", "#38bdf8"), ("infrastructure", "Infraestructura", "#7c3aed"),
             ("network", "Redes y comunicaciones", "#2dd4bf"), ("cloud_ops", "Operación cloud", "#00e5a0"),
             ("backup", "Copias de seguridad", "#84cc16"), ("payroll", "Nóminas", "#ffb800"),
             ("development", "Desarrollo", "#f97316"), ("other", "Otro", "#7a8aaa"))
UNIDADES = (("hour", "Hora", "#00d4ff"), ("day", "Día", "#38bdf8"), ("month", "Mes", "#7c3aed"),
            ("ticket", "Ticket", "#00e5a0"), ("incident", "Incidente", "#ec4899"), ("request", "Petición", "#2dd4bf"),
            ("device_month", "Dispositivo al mes", "#ffb800"), ("user_month", "Usuario al mes", "#f97316"),
            ("call", "Llamada", "#84cc16"), ("expense", "Gasto", "#7a8aaa"))

#: Orden de creacion (dependencias entre ellas).
TABLAS = ("supplier_contracts", "supplier_services", "supplier_work_packages", "supplier_pricing_lines",
          "supplier_reports", "supplier_statements", "supplier_usage_records", "supplier_documents",
          "supplier_risk_assessments", "supplier_access_grants")

_DNI = re.compile(r"^\d{8}[A-Z]$")
_NIE = re.compile(r"^[XYZ]\d{7}[A-Z]$")


def _tablas(con) -> set:
    return set(sa.inspect(con).get_table_names())


def _columnas(con, tabla: str) -> set:
    return {c["name"] for c in sa.inspect(con).get_columns(tabla)}


def normalizar(texto) -> str:
    t = unicodedata.normalize("NFD", str(texto or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def es_nif_de_persona(nif) -> bool:
    n = re.sub(r"[\s\-.]", "", str(nif or "").upper())
    if n.startswith("ES"):
        n = n[2:]
    return bool(_DNI.match(n) or _NIE.match(n))


def clasificar(nombre, nif, personas: list, asignaciones_sin_persona: int) -> tuple[str, list, object]:
    """(kind, modos, freelancer_worker_id) de un proveedor existente.

    `personas`: [(id, nombre)] activas."""
    freelance = len(personas) == 1 and (normalizar(personas[0][1]) == normalizar(nombre) or es_nif_de_persona(nif))
    modos = []
    if personas:
        modos.append("staff_augmentation")
    if asignaciones_sin_persona and not freelance:
        modos.append("outsourcing")
    if freelance:
        return "freelance", modos or ["staff_augmentation"], personas[0][0]
    return "company", modos, None


def _crear_tablas(con) -> None:
    from app.models import proveedores, settings as _s  # noqa: F401  (registra los modelos)
    from app.db.base import Base
    for nombre in ("custom_supplier_service_types", "custom_supplier_billing_units") + TABLAS:
        Base.metadata.tables[nombre].create(con, checkfirst=True)


def _sembrar(con, tabla: str, valores) -> None:
    if con.execute(sa.text(f"SELECT 1 FROM {tabla}")).first() is not None:
        return
    for i, (v, l, c) in enumerate(valores):
        con.execute(sa.text(f"INSERT INTO {tabla} (id, organization_id, value, label, color, is_active, sort_order) "
                            "VALUES (:id, NULL, :v, :l, :c, :a, :o)"),
                    {"id": str(uuid.uuid4()), "v": v, "l": l, "c": c, "a": True, "o": i})


def _columnas_nuevas(con) -> None:
    cs = _columnas(con, "subcontractors")
    nuevas = [
        ("kind", sa.String(20), {"nullable": False, "server_default": "company"}),
        ("engagement_modes", sa.JSON(), {}), ("lifecycle_status", sa.String(20),
                                              {"nullable": False, "server_default": "active"}),
        ("freelancer_worker_id", sa.String(36), {}), ("alm_vendor_id", sa.String(36), {}),
        ("internal_owner_id", sa.String(36), {}), ("legal_name", sa.String(255), {}),
        ("website", sa.String(500), {}), ("address", sa.Text(), {}),
        ("training_enabled", sa.Boolean(), {"nullable": False, "server_default": sa.false()}),
        ("data_access", sa.Boolean(), {"nullable": False, "server_default": sa.false()}),
        ("data_categories", sa.String(500), {}), ("systems_access", sa.String(500), {}),
        ("risk_level", sa.String(20), {}), ("risk_score", sa.Float(), {}), ("next_review_date", sa.Date(), {}),
        ("suspended_at", sa.Date(), {}), ("offboarded_at", sa.Date(), {}), ("offboarding_reason", sa.String(255), {}),
    ]
    with op.batch_alter_table("subcontractors") as t:
        for nombre, tipo, kw in nuevas:
            if nombre not in cs:
                t.add_column(sa.Column(nombre, tipo, nullable=kw.get("nullable", True),
                                       server_default=kw.get("server_default")))
        if "freelancer_worker_id" not in cs:
            t.create_foreign_key("fk_subcontractors_freelancer_worker", "subcontractor_workers",
                                 ["freelancer_worker_id"], ["id"], ondelete="SET NULL")
        if "alm_vendor_id" not in cs:
            t.create_foreign_key("fk_subcontractors_alm_vendor", "alm_vendors", ["alm_vendor_id"], ["id"],
                                 ondelete="SET NULL")
            t.create_index("ix_subcontractors_alm_vendor_id", ["alm_vendor_id"])
        if "internal_owner_id" not in cs:
            t.create_foreign_key("fk_subcontractors_internal_owner", "users", ["internal_owner_id"], ["id"],
                                 ondelete="SET NULL")
            t.create_index("ix_subcontractors_internal_owner_id", ["internal_owner_id"])

    ct = _columnas(con, "tasks")
    with op.batch_alter_table("tasks") as t:
        if "supplier_id" not in ct:
            t.add_column(sa.Column("supplier_id", sa.String(36), nullable=True))
            t.create_foreign_key("fk_tasks_supplier", "subcontractors", ["supplier_id"], ["id"], ondelete="SET NULL")
            t.create_index("ix_tasks_supplier_id", ["supplier_id"])
        if "supplier_work_package_id" not in ct:
            t.add_column(sa.Column("supplier_work_package_id", sa.String(36), nullable=True))
            t.create_foreign_key("fk_tasks_supplier_work_package", "supplier_work_packages",
                                 ["supplier_work_package_id"], ["id"], ondelete="SET NULL")
            t.create_index("ix_tasks_supplier_work_package_id", ["supplier_work_package_id"])

    ci = _columnas(con, "subcontractor_invoices")
    with op.batch_alter_table("subcontractor_invoices") as t:
        if "created_by" not in ci:
            t.add_column(sa.Column("created_by", sa.String(36), nullable=True))
            t.create_foreign_key("fk_subcontractor_invoices_created_by", "users", ["created_by"], ["id"],
                                 ondelete="SET NULL")
            t.create_index("ix_subcontractor_invoices_created_by", ["created_by"])
        if "contract_id" not in ci:
            t.add_column(sa.Column("contract_id", sa.String(36), nullable=True))
            t.create_foreign_key("fk_subcontractor_invoices_contract", "supplier_contracts", ["contract_id"],
                                 ["id"], ondelete="SET NULL")
            t.create_index("ix_subcontractor_invoices_contract_id", ["contract_id"])


def _migrar_datos(con) -> None:
    # JSON en Postgres exige el tipo; en SQLite es texto (un CAST AS JSON lo volveria numero).
    j = "CAST(:m AS JSON)" if con.dialect.name == "postgresql" else ":m"
    subs = con.execute(sa.text("SELECT id, name, vat_number, is_active, currency, organization_id "
                               "FROM subcontractors")).fetchall()
    for sid, nombre, nif, activo, moneda, org in subs:
        if con.execute(sa.text("SELECT 1 FROM supplier_contracts WHERE subcontractor_id = :s"), {"s": sid}).first():
            continue  # ya migrado
        personas = [tuple(r) for r in con.execute(sa.text(
            "SELECT id, name FROM subcontractor_workers WHERE subcontractor_id = :s AND is_active = :t"),
            {"s": sid, "t": True}).fetchall()]
        sin_persona = con.execute(sa.text(
            "SELECT a.id, a.project_id, a.po_amount, a.start_date, a.end_date, a.is_active, a.notes, p.name "
            "FROM subcontractor_assignments a LEFT JOIN projects p ON p.id = a.project_id "
            "WHERE a.subcontractor_id = :s AND a.worker_id IS NULL"), {"s": sid}).fetchall()
        kind, modos, freelancer = clasificar(nombre, nif, personas, len(sin_persona))
        con.execute(sa.text(
            f"UPDATE subcontractors SET kind = :k, engagement_modes = {j}, freelancer_worker_id = :f, "
            "lifecycle_status = :l WHERE id = :s"),
            {"k": kind, "m": json.dumps(modos), "f": freelancer, "l": "active" if activo is not False else "offboarded",
             "s": sid})
        tarifas = con.execute(sa.text(
            "SELECT id, description, cost_rate, currency, valid_from, valid_until FROM subcontractor_rates "
            "WHERE subcontractor_id = :s AND is_active = :t"), {"s": sid, "t": True}).fetchall()
        n_asig = con.execute(sa.text("SELECT COUNT(*) FROM subcontractor_assignments WHERE subcontractor_id = :s"),
                             {"s": sid}).scalar() or 0
        n_fact = con.execute(sa.text("SELECT COUNT(*) FROM subcontractor_invoices WHERE subcontractor_id = :s"),
                             {"s": sid}).scalar() or 0
        if not (tarifas or n_asig or n_fact):
            continue
        cid = str(uuid.uuid4())
        con.execute(sa.text(
            "INSERT INTO supplier_contracts (id, organization_id, subcontractor_id, is_template, title, contract_type, "
            f"modes, status, currency, auto_renew, expenses_rebillable, notes) VALUES (:id, :org, :s, :f, :t, :ct, {j}, "
            ":st, :cur, :f, :f, :n)"),
            {"id": cid, "org": org, "s": sid, "f": False, "t": f"Contrato marco (migrado) · {nombre}"[:255],
             "ct": "freelance" if kind == "freelance" else "framework", "m": json.dumps(modos),
             "st": "active" if activo is not False else "terminated", "cur": moneda,
             "n": "Creado por la migración 189 a partir de tarifas, asignaciones y facturas existentes."})
        for rid, desc, coste, cur, desde, hasta in tarifas:
            con.execute(sa.text(
                "INSERT INTO supplier_pricing_lines (id, organization_id, contract_id, model, unit, description, "
                "rate_id, unit_price, valid_from, valid_until, is_active) VALUES (:id, :org, :c, 'per_resource', "
                "'hour', :d, :r, :p, :vf, :vu, :a)"),
                {"id": str(uuid.uuid4()), "org": org, "c": cid, "d": desc, "r": rid, "p": coste, "vf": desde,
                 "vu": hasta, "a": True})
        for aid, pid, po, ini, fin, a_activa, notas, proyecto in sin_persona:
            con.execute(sa.text(
                "INSERT INTO supplier_work_packages (id, organization_id, subcontractor_id, contract_id, project_id, "
                "scope_type, title, description, status, planned_start, planned_end, price, currency, rejections, "
                "legacy_assignment_id) VALUES (:id, :org, :s, :c, :p, 'project', :t, :d, :st, :i, :f, :pr, :cur, 0, :a)"),
                {"id": str(uuid.uuid4()), "org": org, "s": sid, "c": cid, "p": pid,
                 "t": f"Asignación migrada · {proyecto or pid}"[:255], "d": notas,
                 "st": "in_progress" if a_activa is not False else "accepted", "i": ini, "f": fin, "pr": po,
                 "cur": moneda, "a": aid})
            con.execute(sa.text("UPDATE subcontractor_assignments SET is_active = :f WHERE id = :a"),
                        {"f": False, "a": aid})


def upgrade() -> None:
    con = op.get_bind()
    if "subcontractors" not in _tablas(con):
        return
    _crear_tablas(con)
    _sembrar(con, "custom_supplier_service_types", SERVICIOS)
    _sembrar(con, "custom_supplier_billing_units", UNIDADES)
    _columnas_nuevas(con)
    _migrar_datos(con)


def downgrade() -> None:
    con = op.get_bind()
    tablas = _tablas(con)
    if "supplier_work_packages" in tablas:
        con.execute(sa.text(
            "UPDATE subcontractor_assignments SET is_active = :t WHERE id IN (SELECT legacy_assignment_id FROM "
            "supplier_work_packages WHERE legacy_assignment_id IS NOT NULL AND status <> 'accepted')"), {"t": True})
    with op.batch_alter_table("subcontractor_invoices") as t:
        for idx, fk, col in (("ix_subcontractor_invoices_contract_id", "fk_subcontractor_invoices_contract", "contract_id"),
                             ("ix_subcontractor_invoices_created_by", "fk_subcontractor_invoices_created_by", "created_by")):
            t.drop_index(idx)
            t.drop_constraint(fk, type_="foreignkey")
            t.drop_column(col)
    with op.batch_alter_table("tasks") as t:
        for idx, fk, col in (("ix_tasks_supplier_work_package_id", "fk_tasks_supplier_work_package",
                              "supplier_work_package_id"), ("ix_tasks_supplier_id", "fk_tasks_supplier", "supplier_id")):
            t.drop_index(idx)
            t.drop_constraint(fk, type_="foreignkey")
            t.drop_column(col)
    with op.batch_alter_table("subcontractors") as t:
        t.drop_constraint("fk_subcontractors_freelancer_worker", type_="foreignkey")
        t.drop_index("ix_subcontractors_alm_vendor_id")
        t.drop_constraint("fk_subcontractors_alm_vendor", type_="foreignkey")
        t.drop_index("ix_subcontractors_internal_owner_id")
        t.drop_constraint("fk_subcontractors_internal_owner", type_="foreignkey")
        for c in ("kind", "engagement_modes", "lifecycle_status", "freelancer_worker_id", "alm_vendor_id",
                  "internal_owner_id", "legal_name", "website", "address", "training_enabled", "data_access",
                  "data_categories", "systems_access", "risk_level", "risk_score", "next_review_date",
                  "suspended_at", "offboarded_at", "offboarding_reason"):
            t.drop_column(c)
    for nombre in reversed(TABLAS):
        if nombre in tablas:
            op.drop_table(nombre)
    for nombre in ("custom_supplier_billing_units", "custom_supplier_service_types"):
        if nombre in tablas:
            op.drop_table(nombre)
