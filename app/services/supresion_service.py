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
   correo, su nombre completo o su usuario (de las empresas a las que pertenece),
   menos `audit_logs`: es la evidencia encadenada y reescribirla rompe la cadena.
3. Sus credenciales: las filas suyas de las tablas de sesiones, MFA, passkeys,
   tokens, claves de API y suscripciones push.
4. `dim_user` del almacén analítico. Si no se puede, el informe lo dice.

Segunda auditoría 2026-11:

- `audit_logs` queda fuera A PROPÓSITO (RGPD art. 17.3.b/e: obligación legal y
  defensa de reclamaciones; además `user_name` entra en la huella encadenada y
  reescribirlo rompería la cadena de la empresa). Es una decisión, no un olvido.
- Bloqueo legal: si hay un bloqueo legal activo sobre la persona (un
  `LegalHold` de alguna de sus empresas cuyo valor es su id, su correo o su
  usuario), la supresión se rechaza con 409 y la lista de casos, ANTES de
  reescribir nada (`exigir_sin_bloqueo_legal`).
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


def _empresas_de(db: Session, user) -> set:
    empresas = {user.organization_id} if user.organization_id else set()
    try:
        from app.services.entrada_service import organizaciones_del_usuario
        empresas |= {o.id for o in organizaciones_del_usuario(db, user)}
    except Exception:   # sin membresías: su empresa de ficha
        logger.debug("sin membresías para %s", user.id, exc_info=True)
    return empresas


def bloqueos_de_la_persona(db: Session, user) -> list:
    """Bloqueos legales activos, en sus empresas, cuyo valor la identifica (id, correo o usuario)."""
    from app.db.bloqueo_legal import bloqueos_activos
    valores = {str(v) for v in (user.id, user.email, user.username) if v}
    return [b for org in sorted(_empresas_de(db, user)) for b in bloqueos_activos(db, org)
            if b.value in valores]


def exigir_sin_bloqueo_legal(db: Session, user) -> None:
    """409 con los casos si la persona está bajo bloqueo legal: no se suprime nada."""
    from app.core.errores import ErrorDeDominio
    casos = sorted({b.case_reference for b in bloqueos_de_la_persona(db, user)})
    if casos:
        raise ErrorDeDominio(409, "La persona está bajo bloqueo legal y no se puede suprimir: " + ", ".join(casos))


def suprimir_persona(db: Session, user) -> dict:
    """Borra los datos personales de `user`. Devuelve qué se tocó, tabla a tabla. No hace commit.

    Bajo bloqueo legal activo lanza 409 sin tocar nada.
    """
    from app.db.base import Base
    from app.db.session import sin_filtro_de_tenant

    exigir_sin_bloqueo_legal(db, user)
    originales = {}
    if user.email:
        originales[user.email] = _seudonimo(user.email) + "@erased.invalid"
    for v in (user.full_name, user.username):
        if v and len(v.strip()) >= 3:
            originales.setdefault(v, BORRADO)
    empresas = _empresas_de(db, user)

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
    # Su segundo factor: el secreto TOTP vive en la ficha (auditoria 2026-11).
    user.mfa_secret = None
    user.mfa_enabled = False
    db.flush()

    with sin_filtro_de_tenant(db):
        for nombre, tabla in Base.metadata.tables.items():
            # Revisión GRC 2026-11b: `audit_logs` es la evidencia encadenada
            # (app/db/cadena_auditoria.py) y `user_name` entra en la huella:
            # reescribirlo rompía la cadena de la empresa y el informe de
            # cumplimiento pasaba a «attention». Se conserva, como en la
            # retención (RGPD art. 17.3.b/e: obligación legal y defensa).
            if nombre in ("users", "audit_logs"):
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
