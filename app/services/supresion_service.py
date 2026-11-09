"""Derecho de supresión: borrar los datos personales de una persona (revisión 2026-11).

Medido antes: había dos borrados distintos —`bi_gdpr_service.execute_erasure`
(Gobierno del dato) y `cab_service._gdpr_erase_user` (Enterprise)— y ninguno
tocaba las copias del nombre o del correo en otras tablas, ni las credenciales,
ni el almacén analítico. El de Enterprise además guardaba el correo original en
la propia solicitud.

Uno solo, y genérico (sin lista de tablas a mano):

1. La ficha de `users`: correo y usuario seudónimos, nombre «[ERASED]», el resto
   de datos de contacto vacíos, desactivada y sin contraseña. El `id` se queda:
   horas, gastos y facturas siguen cuadrando, ya sin nadie identificable.
2. Cualquier columna de texto de cualquier tabla cuyo valor sea EXACTAMENTE su
   correo, su nombre completo o su usuario (de las empresas a las que pertenece).
3. Sus credenciales: las filas suyas de las tablas de sesiones, MFA, passkeys,
   tokens, claves de API y suscripciones push.
4. `dim_user` del almacén analítico. Si no se puede, el informe lo dice.
"""
from __future__ import annotations

import hashlib
import logging
import re

from sqlalchemy import String, Text, delete, or_, update
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

BORRADO = "[ERASED]"
_CREDENCIALES = re.compile(r"mfa|passkey|webauthn|oauth_token|api_key|user_session|push_subscription|refresh_token")


def _seudonimo(valor: str) -> str:
    return hashlib.sha256((valor or "").encode()).hexdigest()[:16]


def suprimir_persona(db: Session, user) -> dict:
    """Borra los datos personales de `user`. Devuelve qué se tocó, tabla a tabla. No hace commit."""
    from app.db.base import Base
    from app.db.session import sin_filtro_de_tenant

    originales = {}
    if user.email:
        originales[user.email] = _seudonimo(user.email) + "@erased.invalid"
    for v in (user.full_name, user.username):
        if v and len(v.strip()) >= 3:
            originales.setdefault(v, BORRADO)
    empresas = {user.organization_id} if user.organization_id else set()
    try:
        from app.services.entrada_service import organizaciones_del_usuario
        empresas |= {o.id for o in organizaciones_del_usuario(db, user)}
    except Exception:   # sin membresías: su empresa de ficha
        logger.debug("sin membresías para %s", user.id, exc_info=True)

    informe: dict = {"user_id": user.id, "tablas": {}, "credenciales": {}, "almacen": None}
    # 1. La ficha.
    user.email = originales.get(user.email) or f"{_seudonimo(user.id)}@erased.invalid"
    user.username = f"deleted_{_seudonimo(user.id)}"
    user.full_name = BORRADO
    for campo in ("first_name", "last_name", "phone", "avatar_url", "job_title", "bio", "linkedin_url"):
        if hasattr(user, campo):
            setattr(user, campo, None)
    user.is_active = False
    if hasattr(user, "hashed_password"):
        user.hashed_password = None
    db.flush()

    with sin_filtro_de_tenant(db):
        for nombre, tabla in Base.metadata.tables.items():
            if nombre == "users":
                continue
            cols = tabla.columns
            # 3. Credenciales.
            if "user_id" in cols and _CREDENCIALES.search(nombre):
                n = db.execute(delete(tabla).where(cols["user_id"] == user.id)).rowcount
                if n:
                    informe["credenciales"][nombre] = n
                continue
            # 2. Copias exactas de su correo, nombre o usuario.
            textos = [c for c in cols if isinstance(c.type, (String, Text)) and not c.primary_key and not c.foreign_keys]
            if not textos or not originales:
                continue
            ambito = None
            if "organization_id" in cols and empresas:
                ambito = or_(cols["organization_id"].in_(empresas), cols["organization_id"].is_(None))
            for c in textos:
                largo = getattr(c.type, "length", None)
                for original, nuevo in originales.items():
                    if largo and len(original) > largo:
                        continue
                    valor = nuevo if not largo or len(nuevo) <= largo else BORRADO[:largo]
                    cond = c == original if ambito is None else (c == original) & ambito
                    n = db.execute(update(tabla).where(cond).values({c.name: valor})).rowcount
                    if n:
                        informe["tablas"][f"{nombre}.{c.name}"] = informe["tablas"].get(f"{nombre}.{c.name}", 0) + n
    # 4. Almacén analítico.
    try:
        from app.services.olap.etl import get_duckdb_conn
        conn = get_duckdb_conn()
        try:
            conn.execute("DELETE FROM dim_user WHERE user_id = ?", [user.id])
            informe["almacen"] = "dim_user: borrada"
        finally:
            conn.close()
    except Exception as exc:
        informe["almacen"] = f"dim_user: NO se pudo borrar ({type(exc).__name__}); sale en la próxima carga"
        logger.warning("supresión de %s: no se pudo tocar dim_user", user.id, exc_info=True)
    return informe
