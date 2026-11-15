"""Gastos sobre el motor de politicas (tarea #27).

Esquema:
  · expenses.attendees (asistentes: comidas por persona) y expenses.trip (viaje);
  · expense_attachments.document_type (tipo de documento del justificante);
  · users.grade (grado o categoria profesional, para ambito y condiciones);
  · tablas_de_referencia.uso (para que la usa su dominio ademas de las reglas:
    gastos «kilometraje» = tarifa por km por pais y ciudad).

Datos: cada fila de `expense_policies` pasa a ser una politica PUBLICADA del
dominio `gastos` con el MISMO comportamiento (ver `_reglas`):
  · tope por gasto / tope diario: `bloquear` -> resultado `block`, `avisar` -> `warn`;
  · justificante desde X: `bloquear` -> `require_attachment` (sin el, no se
    envia), `avisar` -> `warn` si no hay ninguno adjunto;
  · justificacion desde X: `bloquear` -> `require_justification`, `avisar` ->
    `warn` si las notas estan vacias.
Los importes se comparan en la moneda por defecto de la empresa
(`DEFAULT_CURRENCY`), convirtiendo el del gasto al tipo de cambio de su fecha:
antes se comparaba la cifra sin mirar la moneda.

Idempotente: la politica conserva el id de la fila (si ya existe, no se toca) y
la tabla se borra solo si existe. El downgrade rehace `expense_policies` desde
las politicas migradas (marca `NOTA`) y las borra.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Optional, Union

import sqlalchemy as sa
from alembic import op

revision: str = "166_gastos_sobre_el_motor_de_politicas"
down_revision: Union[str, None] = "165_motor_de_politicas_y_flujos"
branch_labels = None
depends_on = None

#: Marca de las politicas que vienen de `expense_policies` (la usa el downgrade).
NOTA = "Migrada de las políticas de gasto anteriores (rev. 166)"
R_GASTO, R_DIA, R_JUSTIFICANTE, R_JUSTIFICACION = (
    "Tope por gasto", "Tope diario", "Justificante obligatorio", "Justificación obligatoria")


def _columnas(tabla) -> set:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(tabla)}


def _tablas() -> set:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _anadir(tabla, columna: sa.Column) -> None:
    """Idempotente: la 089 crea algunas tablas desde los modelos ACTUALES."""
    if columna.name not in _columnas(tabla):
        op.add_column(tabla, columna)


def _quitar(tabla, columna) -> None:
    if columna in _columnas(tabla):
        with op.batch_alter_table(tabla) as b:
            b.drop_column(columna)


def _moneda(conn, org: Optional[str]) -> str:
    for filtro, params in (("organization_id = :o", {"o": org}), ("organization_id IS NULL", {})):
        if filtro.startswith("organization_id =") and not org:
            continue
        v = conn.execute(sa.text(f"SELECT value FROM app_settings WHERE key = 'DEFAULT_CURRENCY' AND {filtro}"),
                         params).scalar()
        if v:
            return str(v).upper()[:3]
    try:
        from app.core.config import settings
        return str(settings.DEFAULT_CURRENCY).upper()[:3]
    except Exception:
        return (os.environ.get("DEFAULT_CURRENCY") or "EUR").upper()[:3]


def _c(campo, operador, valor=None) -> dict:
    d = {"tipo": "condicion", "campo": campo, "operador": operador}
    if valor is not None:
        d["valor"] = valor
    return d


def _y(*hijos) -> dict:
    return {"tipo": "grupo", "op": "and", "negar": False, "hijos": [h for h in hijos if h]}


def _reglas(p: dict, moneda: str) -> list[dict]:
    """Las reglas del motor equivalentes a una fila de `expense_policies`."""
    bloquea = p["accion"] != "avisar"
    cat = _c("categoria", "eq", p["categoria"]) if p["categoria"] else None
    nombre = p["nombre"]

    def importe(op_, n):
        return _c("importe", op_, {"cantidad": float(n), "moneda": moneda})

    def efecto(mensaje):
        return {"tipo": "block" if bloquea else "warn", "mensaje": mensaje}

    reglas = []
    if p["limite_por_gasto"] is not None:
        reglas.append((R_GASTO, _y(cat, importe("gt", p["limite_por_gasto"])),
                       [efecto(f"{nombre}: supera el tope de {p['limite_por_gasto']:.2f} {moneda} por gasto")]))
    if p["limite_diario"] is not None:
        campo = "importe_dia_categoria" if p["categoria"] else "importe_dia"
        reglas.append((R_DIA, _y(cat, _c(campo, "gt", {"cantidad": float(p["limite_diario"]), "moneda": moneda})),
                       [efecto(f"{nombre}: el total del día supera el tope diario de {p['limite_diario']:.2f} {moneda}")]))
    if p["justificante_desde"] is not None:
        msg = f"{nombre}: desde {p['justificante_desde']:.2f} {moneda} hay que adjuntar el justificante"
        if bloquea:
            reglas.append((R_JUSTIFICANTE, _y(cat, importe("gte", p["justificante_desde"])),
                           [{"tipo": "require_attachment", "tipos_de_documento": [], "mensaje": msg}]))
        else:
            reglas.append((R_JUSTIFICANTE, _y(cat, importe("gte", p["justificante_desde"]), _c("justificantes", "eq", 0)),
                           [{"tipo": "warn", "mensaje": msg}]))
    if p["justificacion_desde"] is not None:
        msg = f"{nombre}: desde {p['justificacion_desde']:.2f} {moneda} hay que explicar el gasto (notas)"
        if bloquea:
            reglas.append((R_JUSTIFICACION, _y(cat, importe("gte", p["justificacion_desde"])),
                           [{"tipo": "require_justification", "mensaje": msg}]))
        else:
            reglas.append((R_JUSTIFICACION, _y(cat, importe("gte", p["justificacion_desde"]), _c("notas", "empty")),
                           [{"tipo": "warn", "mensaje": msg}]))
    return [{"nombre": n, "condicion": c, "resultados": r} for n, c, r in reglas]


def _datos(conn) -> int:
    """Pasa las filas de `expense_policies` a politicas. Devuelve cuantas creo."""
    if "expense_policies" not in set(sa.inspect(conn).get_table_names()):
        return 0
    filas = conn.execute(sa.text(
        "SELECT id, organization_id, nombre, categoria, limite_por_gasto, limite_diario, justificante_desde, "
        "justificacion_desde, accion, activa, created_by, created_at FROM expense_policies")).mappings().all()
    ahora = datetime.now(timezone.utc)
    politicas = sa.table("politicas", *[sa.column(c) for c in (
        "id", "organization_id", "familia_id", "version", "estado", "dominio", "nombre", "descripcion", "prioridad",
        "activa", "ambito", "nota_de_version", "created_by", "publicada_por", "publicada_en", "created_at", "updated_at")])
    reglas_t = sa.table("politica_reglas", *[sa.column(c) for c in (
        "id", "organization_id", "politica_id", "orden", "nombre", "activa", "condicion", "resultados", "exceso",
        "detener")])
    import uuid
    creadas = 0
    for p in filas:
        if conn.execute(sa.text("SELECT 1 FROM politicas WHERE id = :i"), {"i": p["id"]}).first():
            continue
        creadas += 1
        moneda = _moneda(conn, p["organization_id"])
        conn.execute(politicas.insert().values(
            id=p["id"], organization_id=p["organization_id"], familia_id=p["id"], version=1, estado="publicada",
            dominio="gastos", nombre=(p["nombre"] or "Política de gasto")[:200],
            descripcion="Política de gasto anterior al motor de políticas: mismos topes y misma acción.",
            prioridad=100, activa=bool(p["activa"]), ambito=None, nota_de_version=NOTA,
            created_by=p["created_by"], publicada_por=p["created_by"], publicada_en=ahora,
            created_at=p["created_at"] or ahora, updated_at=ahora))
        for i, r in enumerate(_reglas(dict(p), moneda)):
            conn.execute(reglas_t.insert().values(
                id=str(uuid.uuid4()), organization_id=p["organization_id"], politica_id=p["id"], orden=i + 1,
                nombre=r["nombre"], activa=True, detener=False, exceso=None,
                condicion=json.dumps(r["condicion"], ensure_ascii=False),
                resultados=json.dumps(r["resultados"], ensure_ascii=False)))
    return creadas


def upgrade() -> None:
    _anadir("expenses", sa.Column("attendees", sa.Integer(), nullable=True))
    _anadir("expenses", sa.Column("trip", sa.String(120), nullable=True))
    _anadir("expense_attachments", sa.Column("document_type", sa.String(40), nullable=True))
    _anadir("users", sa.Column("grade", sa.String(60), nullable=True))
    _anadir("tablas_de_referencia", sa.Column("uso", sa.String(40), nullable=True))
    conn = op.get_bind()
    _datos(conn)
    if "expense_policies" in _tablas():
        op.drop_table("expense_policies")


# ── Downgrade ────────────────────────────────────────────────────────────────

def _cantidad(nodo: dict, campos: tuple) -> Optional[float]:
    for h in (nodo or {}).get("hijos") or []:
        if h.get("campo") in campos and isinstance(h.get("valor"), dict):
            return float(h["valor"].get("cantidad") or 0)
    return None


def _categoria(nodo: dict) -> Optional[str]:
    return next((h.get("valor") for h in (nodo or {}).get("hijos") or [] if h.get("campo") == "categoria"), None)


def downgrade() -> None:
    conn = op.get_bind()
    if "expense_policies" not in _tablas():
        op.create_table(
            "expense_policies",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                      nullable=True, index=True),
            sa.Column("nombre", sa.String(200), nullable=False),
            sa.Column("categoria", sa.String(30), nullable=True),
            sa.Column("limite_por_gasto", sa.Float(), nullable=True),
            sa.Column("limite_diario", sa.Float(), nullable=True),
            sa.Column("justificante_desde", sa.Float(), nullable=True),
            sa.Column("justificacion_desde", sa.Float(), nullable=True),
            sa.Column("accion", sa.String(10), nullable=False, server_default="bloquear"),
            sa.Column("activa", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
                      index=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
    _deshacer(conn)
    _quitar("tablas_de_referencia", "uso")
    _quitar("users", "grade")
    _quitar("expense_attachments", "document_type")
    _quitar("expenses", "trip")
    _quitar("expenses", "attendees")


def _deshacer(conn) -> int:
    """Rehace las filas de `expense_policies` desde las politicas migradas y las borra."""
    migradas = conn.execute(sa.text(
        "SELECT id, organization_id, nombre, activa, created_by, created_at FROM politicas "
        "WHERE dominio = 'gastos' AND nota_de_version = :n"), {"n": NOTA}).mappings().all()
    destino = sa.table("expense_policies", *[sa.column(c) for c in (
        "id", "organization_id", "nombre", "categoria", "limite_por_gasto", "limite_diario", "justificante_desde",
        "justificacion_desde", "accion", "activa", "created_by", "created_at")])
    for p in migradas:
        fila = {"id": p["id"], "organization_id": p["organization_id"], "nombre": p["nombre"], "categoria": None,
                "limite_por_gasto": None, "limite_diario": None, "justificante_desde": None,
                "justificacion_desde": None, "accion": "avisar", "activa": bool(p["activa"]),
                "created_by": p["created_by"], "created_at": p["created_at"]}
        for r in conn.execute(sa.text("SELECT nombre, condicion, resultados FROM politica_reglas "
                                      "WHERE politica_id = :p"), {"p": p["id"]}).mappings():
            cond = json.loads(r["condicion"] or "{}")
            tipos = {x.get("tipo") for x in json.loads(r["resultados"] or "[]")}
            if tipos & {"block", "require_attachment", "require_justification"}:
                fila["accion"] = "bloquear"
            fila["categoria"] = fila["categoria"] or _categoria(cond)
            clave = {R_GASTO: ("limite_por_gasto", ("importe",)),
                     R_DIA: ("limite_diario", ("importe_dia", "importe_dia_categoria")),
                     R_JUSTIFICANTE: ("justificante_desde", ("importe",)),
                     R_JUSTIFICACION: ("justificacion_desde", ("importe",))}.get(r["nombre"])
            if clave:
                fila[clave[0]] = _cantidad(cond, clave[1])
        if not conn.execute(sa.text("SELECT 1 FROM expense_policies WHERE id = :i"), {"i": p["id"]}).first():
            conn.execute(destino.insert().values(**fila))
        conn.execute(sa.text("DELETE FROM politica_reglas WHERE politica_id = :p"), {"p": p["id"]})
        conn.execute(sa.text("DELETE FROM politicas WHERE id = :p"), {"p": p["id"]})
    return len(migradas)
