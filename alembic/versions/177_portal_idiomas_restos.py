"""Portal en 8 idiomas: comentarios automaticos con plantilla (16-11-2026).

Columnas nuevas en `sd_ticket_comments`:

- `system_template`: codigo de la plantilla de `textos_del_sistema.COMENTARIOS`
  (resolucion automatica por IA, escalado...) cuando el comentario lo escribe
  el propio sistema.
- `system_params`: sus datos (JSON).

El portal pinta esos comentarios en el idioma del cliente y el operador en el
suyo, como ya se hacia con los tickets que abre el sistema (migracion 175).

Datos:

- Los comentarios existentes quedan sin plantilla y se ven tal cual se
  escribieron.
- `TRANSLATION_CHANNELS` (`app_settings`): las empresas (o la fila global) que
  ya lo tenian guardado no recibian el canal nuevo `portal` (contenido de
  operadores que lee el cliente del portal), que solo llega por defecto a quien
  no lo ha tocado. Se anade `portal` a cada valor guardado no vacio que no lo
  tenga (un valor vacio es "ningun canal" y se respeta). El downgrade lo quita.

Revision ID: 177_portal_idiomas_restos
Revises: 175_traduccion_en_tiempo_real
"""
import sqlalchemy as sa
from alembic import op

revision = "177_portal_idiomas_restos"
down_revision = "175_traduccion_en_tiempo_real"
branch_labels = None
depends_on = None


def _columnas(con, tabla: str) -> set[str]:
    return {c["name"] for c in sa.inspect(con).get_columns(tabla)}


_AJUSTE = "TRANSLATION_CHANNELS"
_CANAL = "portal"


def _lista(valor) -> list[str]:
    return [c.strip() for c in str(valor or "").split(",") if c.strip()]


def con_canal(valor) -> str | None:
    """Valor con `portal` anadido; None si no hay que tocarlo (vacio o ya lo tiene)."""
    canales = _lista(valor)
    if not canales or _CANAL in {c.lower() for c in canales}:
        return None
    return ",".join(canales + [_CANAL])


def sin_canal(valor) -> str | None:
    """Valor sin `portal`; None si no lo tenia."""
    canales = _lista(valor)
    resto = [c for c in canales if c.lower() != _CANAL]
    if len(resto) == len(canales):
        return None
    return ",".join(resto)


def _reescribir(con, cambio) -> None:
    if "app_settings" not in sa.inspect(con).get_table_names():
        return
    filas = con.execute(sa.text("SELECT id, value FROM app_settings WHERE key = :k"), {"k": _AJUSTE}).fetchall()
    for fila_id, valor in filas:
        nuevo = cambio(valor)
        if nuevo is not None:
            con.execute(sa.text("UPDATE app_settings SET value = :v WHERE id = :i"), {"v": nuevo, "i": fila_id})


def upgrade() -> None:
    con = op.get_bind()
    _reescribir(con, con_canal)
    columnas = _columnas(con, "sd_ticket_comments")
    with op.batch_alter_table("sd_ticket_comments") as t:
        if "system_template" not in columnas:
            t.add_column(sa.Column("system_template", sa.String(60), nullable=True))
        if "system_params" not in columnas:
            t.add_column(sa.Column("system_params", sa.Text(), nullable=True))


def downgrade() -> None:
    con = op.get_bind()
    _reescribir(con, sin_canal)
    columnas = _columnas(con, "sd_ticket_comments")
    with op.batch_alter_table("sd_ticket_comments") as t:
        if "system_params" in columnas:
            t.drop_column("system_params")
        if "system_template" in columnas:
            t.drop_column("system_template")
