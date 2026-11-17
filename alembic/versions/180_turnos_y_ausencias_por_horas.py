"""Turnos en el planificador y ausencias por horas (17-11-2026).

El horario efectivo de cada persona y día (`app/services/horario/`) pasa a ser
la única fuente para el planificador, las cargas, reservas, capacidad,
previsión, ausencias y saldos. Ver DOCS.md › «Horario efectivo y ausencias por
horas».

Tablas nuevas:

- `jornadas_laborales`: jornadas con sus tramos por día de la semana y pausa.
- `asignaciones_de_jornada`: a quién se aplica cada jornada (empresa, sede,
  departamento, equipo, grupo o persona), con vigencia (o cada año: verano) y
  prioridad.
- `movimientos_de_saldo`: ajustes de RRHH y horas de la bolsa (idempotentes
  por persona, saldo, origen y referencia).

Columnas nuevas:

- `users`: `office_id` (sede), `hire_date` (alta: antigüedad y prorrateo),
  `employment_type` (tipo de contrato).
- `turnos`: `tramos` (turno partido) y `pausa_minutos`.
- `tipos_de_ausencia`: `modos`, `retribuido`, `periodo_saldo`,
  `inicio_periodo_mes`, `arrastre_max`, `arrastre_caduca_meses`,
  `caduca_meses`, `prorratear_alta`, `derecho_tabla_id`, `bolsa`.
- `absences`: `modo`, `start_time`, `end_time` (franja de una ausencia por
  horas) y `scheduled_hours` (horas de su horario que cubre).
- `holidays`: `office_id` (festivo de una sede).

Datos: las ausencias que ya había quedan con `modo` = «horas» si su tipo era
por horas y «dias» si no, y `scheduled_hours` sin valor (el saldo en horas
usa entonces sus horas o sus días por la jornada media de la persona).

Downgrade: quita lo añadido.

Revision ID: 180_turnos_y_ausencias_por_horas
Revises: 179_canales_tiempo_real
"""
import sqlalchemy as sa
from alembic import op

revision = "180_turnos_y_ausencias_por_horas"
down_revision = "179_canales_tiempo_real"
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _tablas() -> set:
    return set(_insp().get_table_names())


def _columnas(tabla) -> set:
    return {c["name"] for c in _insp().get_columns(tabla)}


def _org():
    return sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)


def _crear(nombre, *columnas, indices=(), extra=()):
    if nombre in _tablas():
        return
    op.create_table(nombre, sa.Column("id", sa.String(36), primary_key=True), _org(), *columnas, *extra)
    for c in ("organization_id", *indices):
        op.create_index(f"ix_{nombre}_{c}", nombre, [c])


def _anadir(tabla, columnas, indices=()):
    existentes = _columnas(tabla)
    nuevas = [c for c in columnas if c.name not in existentes]
    if not nuevas:
        return
    with op.batch_alter_table(tabla) as b:
        for c in nuevas:
            b.add_column(c)
    for c in indices:
        if c in {x.name for x in nuevas}:
            op.create_index(f"ix_{tabla}_{c}", tabla, [c])


def upgrade() -> None:
    ahora = sa.func.now()
    _crear("jornadas_laborales",
           sa.Column("nombre", sa.String(120), nullable=False),
           sa.Column("nombres", sa.Text(), nullable=True),
           sa.Column("color", sa.String(9), nullable=False),
           sa.Column("semana", sa.Text(), nullable=False),
           sa.Column("pausa_minutos", sa.Integer(), nullable=False),
           sa.Column("activo", sa.Boolean(), nullable=False),
           sa.Column("orden", sa.Integer(), nullable=False),
           sa.Column("created_at", sa.DateTime(timezone=True), server_default=ahora, nullable=True),
           sa.Column("updated_at", sa.DateTime(timezone=True), server_default=ahora, nullable=True))
    _crear("asignaciones_de_jornada",
           sa.Column("jornada_id", sa.String(36), sa.ForeignKey("jornadas_laborales.id", ondelete="CASCADE"),
                     nullable=False),
           sa.Column("ambito", sa.String(14), nullable=False),
           sa.Column("valor", sa.String(160), nullable=True),
           sa.Column("desde", sa.Date(), nullable=True),
           sa.Column("hasta", sa.Date(), nullable=True),
           sa.Column("recurrente_anual", sa.Boolean(), nullable=False),
           sa.Column("prioridad", sa.Integer(), nullable=False),
           sa.Column("nota", sa.String(255), nullable=True),
           sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
           sa.Column("created_at", sa.DateTime(timezone=True), server_default=ahora, nullable=True),
           indices=("jornada_id", "created_by"))
    _crear("movimientos_de_saldo",
           sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
           sa.Column("saldo_clave", sa.String(60), nullable=False),
           sa.Column("fecha", sa.Date(), nullable=False),
           sa.Column("cantidad", sa.Float(), nullable=False),
           sa.Column("unidad", sa.String(8), nullable=False),
           sa.Column("origen", sa.String(12), nullable=False),
           sa.Column("referencia", sa.String(80), nullable=True),
           sa.Column("caduca", sa.Date(), nullable=True),
           sa.Column("nota", sa.String(500), nullable=True),
           sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
           sa.Column("created_at", sa.DateTime(timezone=True), server_default=ahora, nullable=True),
           indices=("user_id", "saldo_clave", "fecha", "created_by"),
           extra=(sa.UniqueConstraint("user_id", "saldo_clave", "origen", "referencia",
                                      name="uq_movimientos_de_saldo_ref"),))

    _anadir("users", [
        sa.Column("office_id", sa.String(36), sa.ForeignKey("offices.id", ondelete="SET NULL",
                                                             name="fk_users_office_id"), nullable=True),
        sa.Column("hire_date", sa.Date(), nullable=True),
        sa.Column("employment_type", sa.String(40), nullable=True),
    ], indices=("office_id",))
    _anadir("turnos", [
        sa.Column("tramos", sa.Text(), nullable=True),
        sa.Column("pausa_minutos", sa.Integer(), nullable=False, server_default="0"),
    ])
    _anadir("tipos_de_ausencia", [
        sa.Column("modos", sa.Text(), nullable=True),
        sa.Column("retribuido", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("periodo_saldo", sa.String(12), nullable=False, server_default="anual"),
        sa.Column("inicio_periodo_mes", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("arrastre_max", sa.Float(), nullable=True),
        sa.Column("arrastre_caduca_meses", sa.Integer(), nullable=True),
        sa.Column("caduca_meses", sa.Integer(), nullable=True),
        sa.Column("prorratear_alta", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("derecho_tabla_id", sa.String(36), sa.ForeignKey("tablas_de_referencia.id", ondelete="SET NULL",
                                                                    name="fk_tipos_de_ausencia_derecho_tabla_id"),
                  nullable=True),
        sa.Column("bolsa", sa.Text(), nullable=True),
    ], indices=("derecho_tabla_id",))
    _anadir("absences", [
        sa.Column("modo", sa.String(10), nullable=True),
        sa.Column("start_time", sa.Time(), nullable=True),
        sa.Column("end_time", sa.Time(), nullable=True),
        sa.Column("scheduled_hours", sa.Float(), nullable=True),
    ])
    _anadir("holidays", [
        sa.Column("office_id", sa.String(36), sa.ForeignKey("offices.id", ondelete="SET NULL",
                                                             name="fk_holidays_office_id"), nullable=True),
    ], indices=("office_id",))

    op.execute("UPDATE absences SET modo = 'horas' WHERE modo IS NULL AND unit = 'horas'")
    op.execute("UPDATE absences SET modo = 'dias' WHERE modo IS NULL")


def downgrade() -> None:
    for tabla, columnas, indices in (
        ("holidays", ("office_id",), ("office_id",)),
        ("absences", ("scheduled_hours", "end_time", "start_time", "modo"), ()),
        ("tipos_de_ausencia", ("bolsa", "derecho_tabla_id", "prorratear_alta", "caduca_meses", "arrastre_caduca_meses",
                               "arrastre_max", "inicio_periodo_mes", "periodo_saldo", "retribuido", "modos"),
         ("derecho_tabla_id",)),
        ("turnos", ("pausa_minutos", "tramos"), ()),
        ("users", ("employment_type", "hire_date", "office_id"), ("office_id",)),
    ):
        existentes = _columnas(tabla)
        for c in indices:
            if c in existentes:
                op.drop_index(f"ix_{tabla}_{c}", table_name=tabla)
        with op.batch_alter_table(tabla) as b:
            for c in columnas:
                if c in existentes:
                    b.drop_column(c)
    for tabla in ("movimientos_de_saldo", "asignaciones_de_jornada", "jornadas_laborales"):
        if tabla in _tablas():
            op.drop_table(tabla)
