"""Usuarios del portal: contraseña puesta a mano, eliminar o archivar y restaurar (23-11-2026).

Docs: docs/seguridad/politicas_de_cuenta.md §«Portal de clientes: contraseña a mano,
eliminar y archivar».

- **Contraseña a mano** (`establecer_contrasena`): la escribe (o la genera la
  pantalla) alguien con `clientes.gestionar`. Pasa la política de contraseñas de
  la empresa (`validar_puesta_por_el_equipo`), se guarda solo con hash, cierra
  todas las sesiones del portal de ese usuario y, si se pide, va por correo al
  titular. Nunca vuelve en una respuesta ni se escribe en logs ni en auditoría:
  la auditoría guarda quién, a quién, si obliga a cambiarla y si se envió.
- **Eliminar** (`eliminar_o_archivar`): el servidor decide. Sin historial
  (`historial_de`: ninguna fila de negocio apunta al usuario) se borra de
  verdad; con historial se ARCHIVA: no entra, se cierran sus sesiones, sale de
  las listas por defecto y conserva su historial con su nombre.
- **Restaurar** (`restaurar`): vuelve a estar activo (respeta el tope de
  usuarios del portal del cliente).

Distinto de la supresión RGPD (`datos_personales_de_contactos.anonimizar`), que
anonimiza a la persona y que se pide aparte (Enterprise › RGPD).
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.codigos_de_error import error
from app.models.client_portal import ClientUser

#: Tablas que apuntan a `client_users` y NO son historial: permisos, sesiones,
#: preferencias técnicas y avisos que recibe. Todas las demás (tickets y sus
#: comentarios, mensajes, documentos subidos o firmados, peticiones, UAT,
#: encuestas, demanda, conversaciones, llamadas, acciones del asistente,
#: auditoría de colaboración...) cuentan como historial, también las que se
#: añadan en el futuro: lo seguro por defecto es archivar.
NO_SON_HISTORIAL = frozenset({
    "client_user_projects",            # a qué proyectos tiene acceso (ORM: `projects`)
    "client_sessions",                 # sesiones (ORM: `sessions`, cascade)
    "client_contacts",                 # su ficha de contacto: se queda, sin enlace
    "collaboration_presence_states",   # «en línea»
    "collaboration_push_subscriptions",
    "collaboration_reads",             # qué ha leído
    "collaboration_notifications",     # avisos recibidos
    "collaboration_conversation_members",
    "collaboration_mentions",          # le mencionaron (lo hizo otro)
})

#: Las que se borran a mano antes de borrar al usuario (sin relación ORM).
_SE_BORRAN_CON_EL_USUARIO = NO_SON_HISTORIAL - {"client_user_projects", "client_sessions", "client_contacts"}
#: Al archivar: lo que le permitiría seguir recibiendo o entrando.
_SE_BORRAN_AL_ARCHIVAR = frozenset({"collaboration_push_subscriptions", "collaboration_presence_states"})


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def referencias_a_usuarios_del_portal(db: Optional[Session] = None) -> list[tuple[str, str]]:
    """(tabla, columna) de cada clave ajena a `client_users.id` en los modelos.

    Con `db`, solo las tablas que existen en esa base (una tabla de un modelo
    aún sin migrar no rompe el borrado)."""
    import app.models  # noqa: F401  (todas las tablas registradas)
    from app.db.base import Base
    refs = []
    for tabla in Base.metadata.sorted_tables:
        for fk in tabla.foreign_keys:
            if fk.column.table.name == "client_users" and fk.column.name == "id":
                refs.append((tabla.name, fk.parent.name))
    if db is not None:
        existentes = set(sa.inspect(db.get_bind()).get_table_names())
        refs = [r for r in refs if r[0] in existentes]
    return sorted(set(refs))


def historial_de(db: Session, client_id: str) -> dict[str, int]:
    """Filas de negocio que apuntan al usuario, por `tabla.columna` (solo las > 0)."""
    from app.db.base import Base
    from app.db.session import sin_filtro_de_tenant
    cuenta: dict[str, int] = {}
    with sin_filtro_de_tenant(db):
        for tabla, columna in referencias_a_usuarios_del_portal(db):
            if tabla in NO_SON_HISTORIAL:
                continue
            t = Base.metadata.tables[tabla]
            n = db.execute(sa.select(sa.func.count()).select_from(t).where(t.c[columna] == client_id)).scalar() or 0
            if n:
                cuenta[f"{tabla}.{columna}"] = int(n)
    return cuenta


def _borrar_filas(db: Session, client_id: str, tablas: frozenset) -> None:
    from app.db.base import Base
    from app.db.session import sin_filtro_de_tenant
    with sin_filtro_de_tenant(db):
        for tabla, columna in referencias_a_usuarios_del_portal(db):
            if tabla in tablas:
                t = Base.metadata.tables[tabla]
                db.execute(t.delete().where(t.c[columna] == client_id))


def usuario_de_la_empresa(db: Session, actor, client_id: str) -> ClientUser:
    """El usuario del portal si es de la empresa de quien actúa (404 si no)."""
    org = (getattr(db, "info", None) or {}).get("organization_id") or getattr(actor, "organization_id", None)
    cliente = db.query(ClientUser).filter(ClientUser.id == client_id).first()
    if cliente is None or (not getattr(actor, "is_superadmin", False) and cliente.organization_id != org):
        raise error(404, "no_encontrado", que="cliente")
    return cliente


def esta_archivado(cliente) -> bool:
    return getattr(cliente, "archived_at", None) is not None


# ── Contraseña puesta a mano ─────────────────────────────────────────────────

def validar_puesta_por_el_equipo(db: Session, cliente, clave: str) -> None:
    """Política de contraseñas de la empresa para una contraseña que pone el equipo.

    Longitud (la mayor entre la de la empresa y `MIN_PASSWORD_LENGTH` del
    portal), máximo, complejidad, comunes, datos personales del usuario del
    portal y distinta de la actual (el portal no guarda historial de
    contraseñas: la actual es su historial). Errores con código del OPERADOR
    (es/en/zh), no del portal: los ve quien la escribe.
    """
    from app.core.config import settings
    from app.core.errores import ErrorDeDominio
    from app.services.client_portal_service.autenticacion import verify_password
    from app.services.seguridad_de_cuentas.contrasenas import comprobar_reglas
    from app.services.seguridad_de_cuentas.politica import leer
    p = leer(db, getattr(cliente, "organization_id", None))
    clave = clave or ""
    minimo = max(int(p.MIN_PASSWORD_LENGTH), int(getattr(settings, "MIN_PASSWORD_LENGTH", 0) or 0))
    if len(clave) < minimo:
        raise error(400, "contrasena_min_caracteres", n=minimo)
    try:
        comprobar_reglas(clave, p, (getattr(cliente, "email", None), getattr(cliente, "full_name", None)))
    except ErrorDeDominio as e:
        if getattr(e, "code", None) == "contrasena_con_datos_personales":
            raise error(400, "portal_usuario_contrasena_con_datos_personales") from e
        raise
    actual = getattr(cliente, "hashed_password", None)
    if actual:
        try:
            igual = verify_password(clave, actual)
        except ValueError:
            igual = False
        if igual:
            raise error(400, "portal_usuario_contrasena_igual_a_la_actual")


def validar_alta_con_contrasena(db: Session, *, email: str, full_name: str, organization_id: Optional[str],
                                clave: str) -> None:
    """La misma validación en el alta (aún no hay usuario)."""
    validar_puesta_por_el_equipo(db, SimpleNamespace(email=email, full_name=full_name,
                                                     organization_id=organization_id, hashed_password=None), clave)


def establecer_contrasena(db: Session, actor, client_id: str, clave: str, *, obligar_cambio: bool = True,
                          enviar: bool = False, origen=None) -> dict:
    """Pone la contraseña escrita por el equipo. Confirma. Nunca devuelve la contraseña."""
    from app.services.client_portal_service.autenticacion import hash_password
    from app.services.client_portal_service.clientes import enviar_acceso
    from app.services.seguridad_de_cuentas.auditoria import auditar
    from app.services.seguridad_de_cuentas.restablecimiento import cerrar_sesiones_del_portal
    cliente = usuario_de_la_empresa(db, actor, client_id)
    if esta_archivado(cliente):
        raise error(409, "portal_usuario_archivado")
    validar_puesta_por_el_equipo(db, cliente, clave)
    cliente.hashed_password = hash_password(clave)
    cliente.must_change_password = bool(obligar_cambio)
    # Las sesiones abiertas con la contraseña anterior dejan de valer.
    cerrar_sesiones_del_portal(cliente.id)
    for s in list(cliente.sessions or []):
        db.delete(s)
    enviado = bool(enviar and cliente.is_active and enviar_acceso(cliente, clave))
    auditar(db, actor, "PORTAL_PASSWORD_SET", cliente, org_id=cliente.organization_id, origen=origen,
            recurso="client_user",
            datos={"must_change_password": bool(obligar_cambio), "send_requested": bool(enviar),
                   "sent": enviado, "sessions_revoked": "all"})
    db.commit()
    return {"id": cliente.id, "email": cliente.email, "must_change_password": bool(cliente.must_change_password),
            "credenciales_enviadas": enviado if enviar else None}


# ── Eliminar, archivar y restaurar ───────────────────────────────────────────

def eliminar_o_archivar(db: Session, actor, client_id: str, *, origen=None) -> dict:
    """Borra al usuario si no tiene historial; si lo tiene, lo archiva. Confirma.

    Devuelve `{"resultado": "eliminado" | "archivado", "historial": {...}, "total": n}`.
    """
    from app.services.client_service import desvincular_usuario_del_portal
    from app.services.seguridad_de_cuentas.auditoria import auditar
    from app.services.seguridad_de_cuentas.restablecimiento import cerrar_sesiones_del_portal
    cliente = usuario_de_la_empresa(db, actor, client_id)
    historial = historial_de(db, cliente.id)
    total = sum(historial.values())
    cerrar_sesiones_del_portal(cliente.id)
    if not historial:
        foto = {"email": cliente.email, "full_name": cliente.full_name, "client_org_id": cliente.client_org_id}
        _borrar_filas(db, cliente.id, _SE_BORRAN_CON_EL_USUARIO)
        desvincular_usuario_del_portal(db, cliente.id)
        auditar(db, actor, "PORTAL_USER_DELETED", cliente, org_id=cliente.organization_id, origen=origen,
                recurso="client_user", antes=foto, datos={"history": {}})
        db.delete(cliente)
        db.commit()
        return {"id": client_id, "resultado": "eliminado", "historial": {}, "total": 0}
    ya = esta_archivado(cliente)
    if not ya:
        cliente.is_active = False
        cliente.archived_at = _ahora()
        cliente.archived_by = getattr(actor, "id", None)
        for s in list(cliente.sessions or []):
            db.delete(s)
        _borrar_filas(db, cliente.id, _SE_BORRAN_AL_ARCHIVAR)
        auditar(db, actor, "PORTAL_USER_ARCHIVED", cliente, org_id=cliente.organization_id, origen=origen,
                recurso="client_user", datos={"history": historial, "sessions_revoked": "all"})
    db.commit()
    return {"id": cliente.id, "resultado": "archivado", "historial": historial, "total": total,
            "ya_estaba_archivado": ya}


def restaurar(db: Session, actor, client_id: str, *, origen=None) -> dict:
    """Desarchiva al usuario: vuelve a poder entrar con su contraseña. Confirma."""
    from app.models.clients import ClientPortalConfig
    from app.services.seguridad_de_cuentas.auditoria import auditar
    cliente = usuario_de_la_empresa(db, actor, client_id)
    if not esta_archivado(cliente):
        raise error(409, "portal_usuario_no_archivado")
    if cliente.client_org_id:
        cfg = db.query(ClientPortalConfig).filter(ClientPortalConfig.client_id == cliente.client_org_id).first()
        if cfg and cfg.max_portal_users:
            activos = db.query(ClientUser).filter(ClientUser.client_org_id == cliente.client_org_id,
                                                  ClientUser.is_active == True).count()  # noqa: E712
            if activos >= cfg.max_portal_users:
                raise error(409, "portal_limite_usuarios", max=cfg.max_portal_users)
    antes = {"archived_at": cliente.archived_at.isoformat() if cliente.archived_at else None,
             "archived_by": cliente.archived_by}
    cliente.is_active = True
    cliente.archived_at = None
    cliente.archived_by = None
    auditar(db, actor, "PORTAL_USER_RESTORED", cliente, org_id=cliente.organization_id, origen=origen,
            recurso="client_user", antes=antes)
    db.commit()
    return {"id": cliente.id, "resultado": "restaurado", "is_active": True}
