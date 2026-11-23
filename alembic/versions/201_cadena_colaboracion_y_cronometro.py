"""Cadena de colaboración con HMAC del llavero y un solo cronómetro activo (23-11-2026).

1. C5 (informe `docs/auditoria/2026-11-22/02_servicios_a_l.md`):
   `collaboration_audit_events.hmac` y `key_id` (VARCHAR(64), NULL). Las filas
   nuevas guardan el HMAC de la fila con la clave ACTIVA del llavero
   (`app/services/key_management.py`) y el `kid` de esa clave; la verificación
   usa la clave de ese `kid`. Las filas anteriores se quedan con NULL y se
   verifican como antes (`hash_version` v1/v2 de la 196): no se rellenan, porque
   un HMAC calculado hoy sobre una fila de ayer no prueba nada de ayer.
2. M31 (informe 02): índice único parcial
   `uq_timer_sessions_un_activo_por_usuario` sobre `timer_sessions(user_id)
   WHERE ended_at IS NULL`. Antes de crearlo se cierran los duplicados: de cada
   persona con varios cronómetros abiertos se deja abierto el más reciente
   (`started_at`, desempate por `id`) y al resto se le pone `ended_at` = ahora
   (sin imputación: no se inventan horas). El número se registra en el log.

Deshacer real: quita el índice y las dos columnas (el HMAC de las filas
escritas entre medias se pierde; la huella `integrity_hash` sigue intacta y la
cadena se sigue verificando con ella). Los cronómetros cerrados no se reabren
(no se sabe cuál era el bueno).

Idempotente: cada paso mira antes si ya está hecho.

Revision ID: 201_cadena_colaboracion_y_cronometro
Revises: 200_esquema_pendiente_auditoria
"""
import logging
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "201_cadena_colaboracion_y_cronometro"
down_revision = "200_esquema_pendiente_auditoria"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.201")

_T_CADENA = "collaboration_audit_events"
_T_CRONO = "timer_sessions"
_IX_CRONO = "uq_timer_sessions_un_activo_por_usuario"
_SOLO_ABIERTOS = "ended_at IS NULL"


def _insp():
    return sa.inspect(op.get_bind())


def _columnas(tabla: str) -> set:
    return {c["name"] for c in _insp().get_columns(tabla)}


def _indices(tabla: str) -> set:
    return {i["name"] for i in _insp().get_indexes(tabla)}


def _cerrar_duplicados() -> int:
    """Cierra los cronómetros abiertos sobrantes; devuelve cuántos cerró."""
    bind = op.get_bind()
    filas = bind.execute(sa.text(
        "SELECT id, user_id FROM timer_sessions WHERE ended_at IS NULL "
        "AND user_id IN (SELECT user_id FROM timer_sessions WHERE ended_at IS NULL "
        "GROUP BY user_id HAVING COUNT(*) > 1) "
        "ORDER BY user_id, started_at DESC, id DESC"
    )).fetchall()
    vistos: set = set()
    sobran: list = []
    for fila_id, usuario in filas:
        if usuario in vistos:
            sobran.append(fila_id)
        else:
            vistos.add(usuario)        # el primero de cada persona es el más reciente
    ahora = datetime.now(timezone.utc)
    for fila_id in sobran:
        bind.execute(sa.text("UPDATE timer_sessions SET ended_at = :ahora WHERE id = :id"),
                     {"ahora": ahora, "id": fila_id})
    if sobran:
        logger.warning("201: %s cronómetros abiertos duplicados cerrados (%s personas)",
                       len(sobran), len(vistos))
    else:
        logger.info("201: sin cronómetros abiertos duplicados")
    return len(sobran)


def upgrade() -> None:
    hay = _columnas(_T_CADENA)
    nuevas = [c for c in ("hmac", "key_id") if c not in hay]
    if nuevas:
        with op.batch_alter_table(_T_CADENA) as b:
            for nombre in nuevas:
                b.add_column(sa.Column(nombre, sa.String(64), nullable=True))

    if _IX_CRONO not in _indices(_T_CRONO):
        _cerrar_duplicados()
        op.create_index(_IX_CRONO, _T_CRONO, ["user_id"], unique=True,
                        sqlite_where=sa.text(_SOLO_ABIERTOS),
                        postgresql_where=sa.text(_SOLO_ABIERTOS))


def downgrade() -> None:
    if _IX_CRONO in _indices(_T_CRONO):
        op.drop_index(_IX_CRONO, table_name=_T_CRONO)

    hay = _columnas(_T_CADENA)
    sobran = [c for c in ("key_id", "hmac") if c in hay]
    if sobran:
        with op.batch_alter_table(_T_CADENA) as b:
            for nombre in sobran:
                b.drop_column(nombre)
