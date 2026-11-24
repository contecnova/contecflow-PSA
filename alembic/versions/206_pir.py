"""PIR común a cambios y proyectos (revisión posterior a la implantación, 23-11-2026, docs/PIR.md).

Tablas nuevas (todas con `organization_id`; la RLS la aplica `env.py` tras el
`upgrade`):

- `pir_plantillas`: preguntas y criterios por empresa, ámbito (`change`/
  `project`) y tipo, con plazo y obligatoriedad.
- `pir_configuracion`: una fila por empresa (plazos, aviso previo, segregación,
  cuándo se programa, obligatoriedad por tipo, proyecto de las acciones).
- `pir_revisiones`: la revisión (de un cambio o de un proyecto/hito).
- `pir_acciones`: acciones de mejora con su tarea enlazada.

Columna nueva: `project_milestones.is_go_live` (booleano, por defecto falso):
el hito de puesta en marcha programa la PIR del proyecto al completarse.

Datos: cada cambio con algo en `pir_notes`, `pir_success` o `pir_date` pasa a
una fila de `pir_revisiones` (motivo `migrada`, estado `cerrado`, código
`PIR-H0001`… por empresa para no chocar con la numeración nueva; resultado
`exito` si `pir_success` era verdadero, `fallo` si falso; resumen = `pir_notes`;
fechas = `pir_date`; responsable = dueño del cambio; obligatoria si el cambio
era normal o de emergencia). Después se RETIRAN las tres columnas del cambio
(la API sigue devolviendo `pir_notes`/`pir_success`/`pir_date` calculados desde
la PIR más reciente).

Compatible con SQLite y Postgres: `batch_alter_table` para las columnas (en
SQLite el `DROP COLUMN` recrea la tabla). Idempotente: mira antes cada tabla,
índice y columna.

Deshacer real: vuelve a crear las tres columnas del cambio y les copia la PIR
más reciente de cada cambio (resumen, éxito = resultado distinto de `fallo`,
fecha real o de cierre), quita `is_go_live` y borra las cuatro tablas (con sus
filas: las PIR nuevas, sus acciones, plantillas y configuración se pierden; las
tareas creadas por acciones se quedan).

Revision ID: 206_pir
Revises: 205_portal_usuarios
"""
import logging
import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "206_pir"
down_revision = "205_portal_usuarios"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.206")

_TZ = sa.DateTime(timezone=True)
#: Orden de creación (padres antes); el borrado va al revés.
TABLAS = ("pir_plantillas", "pir_configuracion", "pir_revisiones", "pir_acciones")
CAMBIOS = "sd_change_requests"
HITOS = "project_milestones"
COLUMNAS_VIEJAS = ("pir_notes", "pir_success", "pir_date")


def _insp():
    return sa.inspect(op.get_bind())


def _tablas() -> set:
    return set(_insp().get_table_names())


def _cols(tabla: str) -> set:
    if tabla not in _tablas():
        return set()
    return {c["name"] for c in _insp().get_columns(tabla)}


def _org():
    return sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                     nullable=True)


def _usuario(nombre: str):
    return sa.Column(nombre, sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


def _definicion() -> dict:
    """La misma que `app/models/pir.py`."""
    return {
        "pir_plantillas": [
            sa.Column("id", sa.String(36), primary_key=True), _org(),
            sa.Column("nombre", sa.String(200), nullable=False),
            sa.Column("ambito", sa.String(10), nullable=False),
            sa.Column("tipo", sa.String(50), nullable=True),
            sa.Column("obligatorio", sa.Boolean(), nullable=True),
            sa.Column("dias", sa.Integer(), nullable=True),
            sa.Column("criterios", sa.Text(), nullable=True),
            sa.Column("preguntas", sa.Text(), nullable=True),
            sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
            _usuario("creado_por"),
            sa.Column("created_at", _TZ, server_default=sa.func.now(), nullable=True),
            sa.Column("updated_at", _TZ, nullable=True),
        ],
        "pir_configuracion": [
            sa.Column("id", sa.String(36), primary_key=True), _org(),
            sa.Column("dias_cambio", sa.Integer(), nullable=False, server_default="7"),
            sa.Column("dias_proyecto", sa.Integer(), nullable=False, server_default="30"),
            sa.Column("aviso_dias_antes", sa.Integer(), nullable=False, server_default="2"),
            sa.Column("segregacion", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("momento_cambio", sa.String(15), nullable=False, server_default="implantacion"),
            sa.Column("momento_proyecto", sa.String(15), nullable=False, server_default="ambos"),
            sa.Column("obligatorio_normal", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("obligatorio_emergencia", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("obligatorio_estandar", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("obligatorio_proyecto", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("proyecto_acciones_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="SET NULL"),
                      nullable=True),
            _usuario("updated_por"),
            sa.Column("updated_at", _TZ, nullable=True),
        ],
        "pir_revisiones": [
            sa.Column("id", sa.String(36), primary_key=True), _org(),
            sa.Column("codigo", sa.String(30), nullable=False),
            sa.Column("titulo", sa.String(300), nullable=False),
            sa.Column("origen_tipo", sa.String(10), nullable=False),
            sa.Column("change_id", sa.String(36), sa.ForeignKey("sd_change_requests.id", ondelete="CASCADE"),
                      nullable=True),
            sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=True),
            sa.Column("milestone_id", sa.String(36), sa.ForeignKey("project_milestones.id", ondelete="SET NULL"),
                      nullable=True),
            sa.Column("motivo", sa.String(15), nullable=False),
            sa.Column("tipo", sa.String(50), nullable=True),
            sa.Column("plantilla_id", sa.String(36), sa.ForeignKey("pir_plantillas.id", ondelete="SET NULL"),
                      nullable=True),
            sa.Column("estado", sa.String(12), nullable=False),
            sa.Column("obligatorio", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("fecha_prevista", sa.Date(), nullable=True),
            sa.Column("fecha_real", sa.Date(), nullable=True),
            _usuario("responsable_id"),
            sa.Column("participantes", sa.Text(), nullable=True),
            sa.Column("objetivos_cumplidos", sa.String(10), nullable=True),
            sa.Column("resultado", sa.String(15), nullable=True),
            sa.Column("resumen", sa.Text(), nullable=True),
            sa.Column("criterios", sa.Text(), nullable=True),
            sa.Column("preguntas", sa.Text(), nullable=True),
            sa.Column("kpis", sa.Text(), nullable=True),
            sa.Column("incidencias", sa.Text(), nullable=True),
            sa.Column("hubo_marcha_atras", sa.Boolean(), nullable=True),
            sa.Column("marcha_atras_detalle", sa.Text(), nullable=True),
            sa.Column("beneficios", sa.Text(), nullable=True),
            sa.Column("satisfaccion", sa.Text(), nullable=True),
            sa.Column("satisfaccion_media", sa.Float(), nullable=True),
            _usuario("enviado_por"),
            sa.Column("enviado_en", _TZ, nullable=True),
            _usuario("aprobado_por"),
            sa.Column("aprobado_en", _TZ, nullable=True),
            sa.Column("comentario_aprobacion", sa.Text(), nullable=True),
            _usuario("cerrado_por"),
            sa.Column("cerrado_en", _TZ, nullable=True),
            sa.Column("reaperturas", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("cuenta_en_modelo", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("aviso_previo_en", _TZ, nullable=True),
            sa.Column("aviso_vencido_en", _TZ, nullable=True),
            _usuario("creado_por"),
            sa.Column("created_at", _TZ, server_default=sa.func.now(), nullable=True),
            sa.Column("updated_at", _TZ, nullable=True),
        ],
        "pir_acciones": [
            sa.Column("id", sa.String(36), primary_key=True), _org(),
            sa.Column("pir_id", sa.String(36), sa.ForeignKey("pir_revisiones.id", ondelete="CASCADE"), nullable=False),
            sa.Column("descripcion", sa.Text(), nullable=False),
            _usuario("responsable_id"),
            sa.Column("fecha_limite", sa.Date(), nullable=True),
            sa.Column("estado", sa.String(12), nullable=False, server_default="abierta"),
            sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True),
            sa.Column("task_id", sa.String(36), sa.ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True),
            _usuario("creado_por"),
            sa.Column("created_at", _TZ, server_default=sa.func.now(), nullable=True),
        ],
    }


#: Índices de una columna (`ix_<tabla>_<col>`, como `index=True` en el modelo).
INDICES = {
    "pir_plantillas": ("organization_id", "ambito", "creado_por"),
    "pir_configuracion": (),
    "pir_revisiones": ("organization_id", "origen_tipo", "change_id", "project_id", "milestone_id", "plantilla_id",
                       "estado", "fecha_prevista", "responsable_id", "resultado", "enviado_por", "aprobado_por",
                       "cerrado_por", "creado_por"),
    "pir_acciones": ("organization_id", "pir_id", "responsable_id", "estado", "project_id", "task_id", "creado_por"),
}
COMPUESTOS = {
    "pir_configuracion": (("ix_pir_configuracion_organization_id", ("organization_id",), True),),
    "pir_plantillas": (("ix_pir_plantillas_org_ambito_tipo", ("organization_id", "ambito", "tipo"), False),),
    "pir_revisiones": (("uq_pir_revisiones_org_codigo", ("organization_id", "codigo"), True),
                       ("ix_pir_revisiones_estado_fecha", ("estado", "fecha_prevista"), False)),
}


def _crear_tablas() -> None:
    hay = _tablas()
    definicion = _definicion()
    for tabla in TABLAS:
        if tabla not in hay:
            op.create_table(tabla, *definicion[tabla])
        existentes = {i["name"] for i in _insp().get_indexes(tabla)}
        for col in INDICES[tabla]:
            nombre = f"ix_{tabla}_{col}"
            if nombre not in existentes:
                op.create_index(nombre, tabla, [col])
        for nombre, cols, unico in COMPUESTOS.get(tabla, ()):
            if nombre not in existentes:
                op.create_index(nombre, tabla, list(cols), unique=unico)


def _copiar_pir_de_los_cambios() -> int:
    """Una PIR `migrada` por cada cambio con datos en las columnas viejas."""
    bind = op.get_bind()
    cambios = sa.table(CAMBIOS, sa.column("id", sa.String), sa.column("organization_id", sa.String),
                       sa.column("number", sa.String), sa.column("title", sa.String),
                       sa.column("change_type", sa.String), sa.column("owner_id", sa.String),
                       sa.column("pir_notes", sa.Text), sa.column("pir_success", sa.Boolean),
                       sa.column("pir_date", _TZ))
    ya = {r[0] for r in bind.execute(sa.text("SELECT change_id FROM pir_revisiones WHERE motivo = 'migrada'"))}
    filas = bind.execute(sa.select(cambios).where(sa.or_(cambios.c.pir_notes.isnot(None),
                                                         cambios.c.pir_success.isnot(None),
                                                         cambios.c.pir_date.isnot(None)))
                         .order_by(cambios.c.organization_id, cambios.c.number)).mappings().all()
    # Siguiente número histórico por empresa (si ya hay PIR-H…, se sigue).
    contador: dict = {}
    for org, codigo in bind.execute(sa.text("SELECT organization_id, codigo FROM pir_revisiones "
                                            "WHERE codigo LIKE 'PIR-H%'")):
        try:
            contador[org] = max(contador.get(org, 0), int(codigo[5:]))
        except ValueError:
            pass
    ahora = datetime.now(timezone.utc)
    nuevas = []
    for c in filas:
        if c["id"] in ya:
            continue
        org = c["organization_id"]
        contador[org] = contador.get(org, 0) + 1
        fecha = c["pir_date"]
        tipo = str(c["change_type"] or "normal").split(".")[-1]
        exito = c["pir_success"]
        nuevas.append({
            "id": str(uuid.uuid4()), "organization_id": org, "codigo": f"PIR-H{contador[org]:04d}",
            "titulo": f"PIR de {c['number']}: {c['title'] or ''}"[:300], "origen_tipo": "change",
            "change_id": c["id"], "motivo": "migrada", "tipo": tipo, "estado": "cerrado",
            "obligatorio": tipo in ("normal", "emergency"),
            "fecha_prevista": fecha.date() if fecha else None, "fecha_real": fecha.date() if fecha else None,
            "responsable_id": c["owner_id"], "resultado": None if exito is None else ("exito" if exito else "fallo"),
            "resumen": c["pir_notes"], "cerrado_en": fecha, "reaperturas": 0, "cuenta_en_modelo": False,
            "created_at": ahora,
        })
    if nuevas:
        # Tipos explícitos para que SQLite y Postgres reciban fechas y booleanos correctos.
        destino = sa.table("pir_revisiones", sa.column("id", sa.String), sa.column("organization_id", sa.String),
                           sa.column("codigo", sa.String), sa.column("titulo", sa.String),
                           sa.column("origen_tipo", sa.String), sa.column("change_id", sa.String),
                           sa.column("motivo", sa.String), sa.column("tipo", sa.String), sa.column("estado", sa.String),
                           sa.column("obligatorio", sa.Boolean), sa.column("fecha_prevista", sa.Date),
                           sa.column("fecha_real", sa.Date), sa.column("responsable_id", sa.String),
                           sa.column("resultado", sa.String), sa.column("resumen", sa.Text),
                           sa.column("cerrado_en", _TZ), sa.column("reaperturas", sa.Integer),
                           sa.column("cuenta_en_modelo", sa.Boolean), sa.column("created_at", _TZ))
        op.bulk_insert(destino, nuevas)
    return len(nuevas)


def upgrade() -> None:
    _crear_tablas()

    if "is_go_live" not in _cols(HITOS) and _cols(HITOS):
        with op.batch_alter_table(HITOS) as b:
            b.add_column(sa.Column("is_go_live", sa.Boolean(), nullable=False, server_default=sa.false()))

    viejas = [c for c in COLUMNAS_VIEJAS if c in _cols(CAMBIOS)]
    if len(viejas) == len(COLUMNAS_VIEJAS):
        n = _copiar_pir_de_los_cambios()
        logger.info("206: %s PIR copiadas de las columnas del cambio", n)
    if viejas:
        with op.batch_alter_table(CAMBIOS) as b:
            for c in viejas:
                b.drop_column(c)
    logger.info("206: PIR lista")


def downgrade() -> None:
    bind = op.get_bind()
    faltan = [c for c in COLUMNAS_VIEJAS if c not in _cols(CAMBIOS)]
    if faltan and _cols(CAMBIOS):
        with op.batch_alter_table(CAMBIOS) as b:
            if "pir_notes" in faltan:
                b.add_column(sa.Column("pir_notes", sa.Text(), nullable=True))
            if "pir_success" in faltan:
                b.add_column(sa.Column("pir_success", sa.Boolean(), nullable=True))
            if "pir_date" in faltan:
                b.add_column(sa.Column("pir_date", _TZ, nullable=True))
    if "pir_revisiones" in _tablas():
        origen = sa.table("pir_revisiones", sa.column("change_id", sa.String), sa.column("resumen", sa.Text),
                          sa.column("resultado", sa.String), sa.column("fecha_real", sa.Date),
                          sa.column("cerrado_en", _TZ), sa.column("estado", sa.String),
                          sa.column("created_at", _TZ))
        cambios = sa.table(CAMBIOS, sa.column("id", sa.String), sa.column("pir_notes", sa.Text),
                           sa.column("pir_success", sa.Boolean), sa.column("pir_date", _TZ))
        ultima: dict = {}
        for r in bind.execute(sa.select(origen).where(origen.c.change_id.isnot(None), origen.c.estado != "descartado")
                              .order_by(origen.c.created_at)).mappings():
            ultima[r["change_id"]] = r
        for cid, r in ultima.items():
            fecha = r["cerrado_en"] or (datetime(r["fecha_real"].year, r["fecha_real"].month, r["fecha_real"].day,
                                                 tzinfo=timezone.utc) if r["fecha_real"] else None)
            bind.execute(cambios.update().where(cambios.c.id == cid).values(
                pir_notes=r["resumen"], pir_success=None if r["resultado"] is None else r["resultado"] != "fallo",
                pir_date=fecha))
        logger.info("206 (deshacer): %s cambios recuperan su PIR en las columnas", len(ultima))

    if "is_go_live" in _cols(HITOS):
        with op.batch_alter_table(HITOS) as b:
            b.drop_column("is_go_live")

    hay = _tablas()
    for tabla in reversed(TABLAS):
        if tabla in hay:
            for i in _insp().get_indexes(tabla):
                if i["name"] and (i["name"].startswith("ix_") or i["name"].startswith("uq_")):
                    op.drop_index(i["name"], table_name=tabla)
            op.drop_table(tabla)
