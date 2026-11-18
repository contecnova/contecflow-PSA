"""Contacto principal correlacionado con los contactos del cliente (18-11-2026).

Antes, el contacto principal de la ficha (`clients.contact_*`) y los contactos
(`client_contacts`) no se relacionaban: el principal podía no existir como
contacto, o haber varios contactos «principales». Ahora el contacto con
`is_primary` es la fuente y `contact_*` su espejo
(`app/services/client_service.py`, `sincronizar_contacto_principal`).

Datos, por cada cliente activo:

1. Si la ficha tiene `contact_name` o `contact_email` y no hay contacto activo
   con ese email (sin mayúsculas) —o, sin email, con ese nombre—, se crea como
   contacto con la empresa del cliente.
2. Un único principal: el que coincide con la ficha; si ninguno coincide, el
   principal más antiguo. Los demás dejan de serlo (y su rol `primary` pasa a
   `other`).
3. La ficha refleja al principal (nombre, email, teléfono y cargo); si no hay
   ninguno, se queda como estaba (sin principal no se vacía nada).

Usuarios del portal ↔ contactos: columna nueva `client_contacts.portal_user_id`
(→ `client_users.id`, SET NULL). Cada usuario del portal con empresa cliente
queda enlazado a un contacto de esa empresa: el activo con su email (sin
mayúsculas) o uno nuevo con su nombre, email, teléfono y cargo.

GRC: `client_contacts.deactivated_at` (desde cuándo está desactivado; de ahí
cuenta la retención del tipo `client_contacts`, ver `app/db/bloqueo_legal.py`).

Idempotente: la segunda vez no cambia nada.

Empresa: columnas nuevas `clients.phone` y `clients.email` (centralita y email
general), vacías: no se copian los del contacto principal, que es una persona.
`contact_*` queda como reflejo de solo lectura del contacto principal.

Downgrade: quita `portal_user_id` (solo el enlace) y `clients.phone/email`. No se borran contactos ni
se tocan fichas (los datos siguen siendo válidos con el esquema anterior).

Revision ID: 183_contacto_principal_correlacionado
Revises: 182_comentarios_de_canal_y_festivos_por_empresa
"""
import uuid

import sqlalchemy as sa
from alembic import op

revision = "183_contacto_principal_correlacionado"
down_revision = "182_comentarios_de_canal_y_festivos_por_empresa"
branch_labels = None
depends_on = None


def _t(v) -> str:
    return (v or "").strip()


def _rol(v) -> str:
    """El rol reflejado puede llegar como texto o como enum."""
    return getattr(v, "value", v) or ""


def correlacionar(con) -> dict:
    """Aplica los tres pasos. Devuelve cuántos contactos se han creado y
    cuántas filas (contactos o clientes) se han cambiado."""
    tablas = set(sa.inspect(con).get_table_names())
    if "clients" not in tablas or "client_contacts" not in tablas:
        return {"creados": 0, "cambiados": 0}
    md = sa.MetaData()
    clientes = sa.Table("clients", md, autoload_with=con)
    contactos = sa.Table("client_contacts", md, autoload_with=con)
    creados = cambiados = 0

    filas = con.execute(sa.select(
        clientes.c.id, clientes.c.organization_id, clientes.c.contact_name, clientes.c.contact_email,
        clientes.c.contact_phone, clientes.c.contact_role,
    ).where(clientes.c.is_active == sa.true())).fetchall()

    for cli in filas:
        nombre, email = _t(cli.contact_name), _t(cli.contact_email)

        def activos():
            return con.execute(sa.select(
                contactos.c.id, contactos.c.full_name, contactos.c.email, contactos.c.phone,
                contactos.c.job_title, contactos.c.role, contactos.c.is_primary, contactos.c.created_at,
            ).where(contactos.c.client_id == cli.id, contactos.c.is_active == sa.true())).fetchall()

        def coincide(ct) -> bool:
            if email:
                return _t(ct.email).lower() == email.lower()
            if nombre:
                return _t(ct.full_name).lower() == nombre.lower()
            return False

        lista = activos()
        de_ficha = next((ct for ct in lista if coincide(ct)), None)
        if (nombre or email) and de_ficha is None:
            con.execute(contactos.insert().values(
                id=str(uuid.uuid4()), organization_id=cli.organization_id, client_id=cli.id,
                full_name=nombre or email, email=email or None,
                phone=_t(cli.contact_phone) or None, job_title=_t(cli.contact_role) or None,
                role="primary", is_primary=True, is_active=True,
            ))
            creados += 1
            lista = activos()
            de_ficha = next((ct for ct in lista if coincide(ct)), None)

        principales = [ct for ct in lista if ct.is_primary]
        if de_ficha is not None:
            elegido = de_ficha
        elif principales:
            elegido = min(principales, key=lambda ct: (ct.created_at is None, ct.created_at or 0, ct.id))
        else:
            continue

        if elegido is de_ficha:
            # Lo escrito en la ficha manda; lo vacío no borra lo que ya tenía el contacto.
            datos = {k: v for k, v in (("full_name", nombre), ("email", email),
                                        ("phone", _t(cli.contact_phone)), ("job_title", _t(cli.contact_role)))
                     if v and v != getattr(elegido, k)}
            if datos:
                con.execute(contactos.update().where(contactos.c.id == elegido.id).values(**datos))
                cambiados += 1
                elegido = next(ct for ct in activos() if ct.id == elegido.id)

        for ct in lista:
            if ct.id == elegido.id:
                if not ct.is_primary or _rol(ct.role) != "primary":
                    con.execute(contactos.update().where(contactos.c.id == ct.id)
                                .values(is_primary=True, role="primary"))
                    cambiados += 1
            elif ct.is_primary or _rol(ct.role) == "primary":
                con.execute(contactos.update().where(contactos.c.id == ct.id).values(
                    is_primary=False, role="other" if _rol(ct.role) == "primary" else ct.role))
                cambiados += 1

        espejo = {"contact_name": elegido.full_name, "contact_email": elegido.email,
                  "contact_phone": elegido.phone, "contact_role": elegido.job_title}
        actual = {"contact_name": cli.contact_name, "contact_email": cli.contact_email,
                  "contact_phone": cli.contact_phone, "contact_role": cli.contact_role}
        if espejo != actual:
            con.execute(clientes.update().where(clientes.c.id == cli.id).values(**espejo))
            cambiados += 1

    return {"creados": creados, "cambiados": cambiados}


def enlazar_usuarios_del_portal(con) -> int:
    """Enlaza cada usuario del portal con un contacto de su empresa cliente
    (reutiliza el de su email o lo crea). Devuelve cuántos contactos se han creado."""
    tablas = set(sa.inspect(con).get_table_names())
    if "client_users" not in tablas or "client_contacts" not in tablas:
        return 0
    md = sa.MetaData()
    usuarios = sa.Table("client_users", md, autoload_with=con)
    contactos = sa.Table("client_contacts", md, autoload_with=con)
    creados = 0
    filas = con.execute(sa.select(
        usuarios.c.id, usuarios.c.organization_id, usuarios.c.client_org_id, usuarios.c.full_name,
        usuarios.c.email, usuarios.c.phone, usuarios.c.job_title,
    ).where(usuarios.c.client_org_id.isnot(None))).fetchall()
    for u in filas:
        ya = con.execute(sa.select(contactos.c.id).where(contactos.c.portal_user_id == u.id)).first()
        if ya:
            continue
        email = _t(u.email)
        ct = con.execute(sa.select(contactos.c.id).where(
            contactos.c.client_id == u.client_org_id, contactos.c.is_active == sa.true(),
            contactos.c.portal_user_id.is_(None),
            sa.func.lower(contactos.c.email) == email.lower(),
        )).first() if email else None
        if ct:
            con.execute(contactos.update().where(contactos.c.id == ct.id).values(portal_user_id=u.id))
        else:
            con.execute(contactos.insert().values(
                id=str(uuid.uuid4()), organization_id=u.organization_id, client_id=u.client_org_id,
                full_name=_t(u.full_name) or email, email=email or None, phone=_t(u.phone) or None,
                job_title=_t(u.job_title) or None, role="other", is_primary=False, is_active=True,
                portal_user_id=u.id,
            ))
            creados += 1
    return creados


def _columnas(tabla) -> set:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(tabla)}


def upgrade() -> None:
    # Datos propios de la empresa: centralita y email general. Vacíos: NO se
    # copian los del contacto principal (son de una persona, no de la empresa).
    hay = _columnas("clients")
    for nombre, tipo in (("phone", sa.String(50)), ("email", sa.String(200))):
        if nombre not in hay:
            with op.batch_alter_table("clients") as b:
                b.add_column(sa.Column(nombre, tipo, nullable=True))
    if "portal_user_id" not in _columnas("client_contacts"):
        with op.batch_alter_table("client_contacts") as b:
            b.add_column(sa.Column("portal_user_id", sa.String(36), nullable=True))
            b.create_foreign_key("fk_client_contacts_portal_user_id", "client_users",
                                 ["portal_user_id"], ["id"], ondelete="SET NULL")
            b.create_index("ix_client_contacts_portal_user_id", ["portal_user_id"])
    if "deactivated_at" not in _columnas("client_contacts"):
        with op.batch_alter_table("client_contacts") as b:
            b.add_column(sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True))
    con = op.get_bind()
    correlacionar(con)
    enlazar_usuarios_del_portal(con)


def downgrade() -> None:
    # Sin pérdida de personas: los contactos creados y los principales elegidos
    # se quedan; solo desaparece el enlace con el usuario del portal.
    if "deactivated_at" in _columnas("client_contacts"):
        with op.batch_alter_table("client_contacts") as b:
            b.drop_column("deactivated_at")
    if "portal_user_id" in _columnas("client_contacts"):
        with op.batch_alter_table("client_contacts") as b:
            b.drop_index("ix_client_contacts_portal_user_id")
            b.drop_constraint("fk_client_contacts_portal_user_id", type_="foreignkey")
            b.drop_column("portal_user_id")
    hay = _columnas("clients")
    for nombre in ("phone", "email"):
        if nombre in hay:
            with op.batch_alter_table("clients") as b:
                b.drop_column(nombre)
