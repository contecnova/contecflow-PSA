"""Compartir un cuaderno o una sección (docs/CUADERNO.md §Compartir).

Solo el dueño comparte y cambia permisos. Destinatarios: una persona de la
empresa (activa y no externa a la empresa), un equipo (`users.team`) o un
departamento (`users.department`) que existan en la empresa; lo permitido lo
decide la configuración (`sharing`). Permiso `read` o `edit`. Cada alta, cambio
y baja queda en `audit_logs` (`SHARE`, `UPDATE`, `UNSHARE`).

23-11-2026 (MCP, docs/integraciones/MCP.md): destinatario `agents` = los
agentes de código del propio dueño (OpenCode, Claude Code… por el servidor
MCP). Solo lectura, sin aviso y solo si la empresa tiene encendidas las
herramientas de Mi cuaderno por MCP (`MCP_NOTEBOOK_ENABLED`). No da acceso a
ninguna otra persona (`acceso.condicion_de_destinatario` no lo mira); el
servidor MCP solo lee páginas de cuadernos propios con esa fila.
"""
from __future__ import annotations
import logging

from typing import Optional

from sqlalchemy.orm import Session

from app.core.codigos_de_error import error
from app.services.audit import audit_log
from app.services.cuaderno import acceso, config
from app.services.cuaderno.acceso import DUENO

TIPOS = ("user", "team", "department")
#: Los agentes de código (MCP) del propio dueño (`target_id` = el dueño).
AGENTES = "agents"
PERMISOS = ("read", "edit")
_CLAVE_CFG = {"user": "users", "team": "teams", "department": "departments"}


def _org(u):
    return getattr(u, "organization_id", None)


def _nombre_de(db: Session, tipo: str, destino: str) -> str:
    if tipo == AGENTES:
        return AGENTES          # la pantalla lo traduce por `target_type`
    if tipo == "user":
        from app.models.user import User
        u = db.get(User, destino)
        return u.full_name if u else destino
    return destino


def _exigir_destino(db: Session, usuario, tipo: str, destino: str) -> None:
    from app.models.user import User
    org = _org(usuario)
    if tipo == "user":
        u = db.get(User, destino)
        if u is None or u.organization_id != org or not u.is_active:
            raise error(404, "no_encontrado", que="usuario")
        if u.id == usuario.id:
            raise error(422, "cuaderno_compartir_contigo")
    else:
        col = User.team if tipo == "team" else User.department
        if not db.query(User.id).filter(User.organization_id == org, col == destino, User.is_active.is_(True)).first():
            raise error(404, "no_encontrado", que="equipo" if tipo == "team" else "departamento")


def _a_dict(db: Session, s) -> dict:
    return {"id": s.id, "notebook_id": s.notebook_id, "section_id": s.section_id, "target_type": s.target_type,
            "target_id": s.target_id, "target_name": _nombre_de(db, s.target_type, s.target_id),
            "permission": s.permission, "created_at": s.created_at.isoformat() if s.created_at else None}


def listar(db: Session, usuario, nb_id: str) -> list[dict]:
    from app.models.cuaderno import NotebookShare
    nb, _ = acceso.cuaderno(db, usuario, nb_id, DUENO)
    return [_a_dict(db, s) for s in db.query(NotebookShare).filter(NotebookShare.notebook_id == nb.id)
            .order_by(NotebookShare.created_at)]


def compartir(db: Session, usuario, nb_id: str, datos: dict) -> dict:
    from app.models.cuaderno import NotebookSection, NotebookShare
    nb, _ = acceso.cuaderno(db, usuario, nb_id, DUENO)
    if nb.is_quick:
        raise error(422, "cuaderno_rapido_no_se_comparte")
    tipo, destino = datos.get("target_type"), str(datos.get("target_id") or "").strip()[:200]
    permiso = datos.get("permission") or "read"
    if tipo == AGENTES:
        _exigir_agentes(db, usuario)
        destino, permiso = usuario.id, "read"      # solo los suyos y solo lectura
    if (tipo not in TIPOS and tipo != AGENTES) or not destino or permiso not in PERMISOS:
        raise error(422, "cuaderno_compartir_no_valido")
    if tipo != AGENTES and not config.leer(db, _org(usuario)).get("sharing", {}).get(_CLAVE_CFG[tipo], True):
        raise error(403, "cuaderno_compartir_desactivado", tipo=tipo)
    seccion_id: Optional[str] = datos.get("section_id") or None
    if seccion_id:
        s = db.get(NotebookSection, seccion_id)
        if s is None or s.notebook_id != nb.id:
            raise error(404, "no_encontrado", que="seccion_de_cuaderno")
    if tipo != AGENTES:
        _exigir_destino(db, usuario, tipo, destino)
    fila = db.query(NotebookShare).filter(NotebookShare.notebook_id == nb.id, NotebookShare.target_type == tipo,
                                          NotebookShare.target_id == destino,
                                          NotebookShare.section_id.is_(None) if not seccion_id
                                          else NotebookShare.section_id == seccion_id).first()
    if fila is not None:
        antes = fila.permission
        fila.permission = permiso
        audit_log(db, usuario, "UPDATE", "notebook_share", fila.id, nb.title,
                  old_values={"permission": antes}, new_values={"permission": permiso, "target_type": tipo,
                                                               "target_id": destino, "section_id": seccion_id})
    else:
        fila = NotebookShare(organization_id=nb.organization_id, notebook_id=nb.id, section_id=seccion_id,
                             target_type=tipo, target_id=destino, permission=permiso, created_by=usuario.id)
        db.add(fila)
        db.flush()
        audit_log(db, usuario, "SHARE", "notebook", nb.id, nb.title,
                  new_values={"target_type": tipo, "target_id": destino, "permission": permiso,
                              "section_id": seccion_id})
        if tipo == "user":
            try:
                from app.services.notifications import notify_user
                notify_user(db, destino, "mention", f"{usuario.full_name} · {nb.title}", None,
                            resource="notebook", resource_id=nb.id, action_url=f"/notebook?notebook={nb.id}",
                            aviso={"titulo": "cuaderno.compartido", "params": {"persona": usuario.full_name,
                                                                                "cuaderno": nb.title}})
            except Exception:  # noqa: BLE001 - el aviso no impide compartir
                logging.getLogger(__name__).debug("compartir: excepcion ignorada", exc_info=True)
    db.flush()
    return _a_dict(db, fila)


def cambiar(db: Session, usuario, share_id: str, permiso: str) -> dict:
    from app.models.cuaderno import NotebookShare
    s = db.get(NotebookShare, share_id)
    if s is None:
        raise error(404, "no_encontrado", que="comparticion")
    nb, _ = acceso.cuaderno(db, usuario, s.notebook_id, DUENO)
    if permiso not in PERMISOS or (s.target_type == AGENTES and permiso != "read"):
        raise error(422, "cuaderno_compartir_no_valido")
    antes = s.permission
    s.permission = permiso
    audit_log(db, usuario, "UPDATE", "notebook_share", s.id, nb.title,
              old_values={"permission": antes}, new_values={"permission": permiso})
    return _a_dict(db, s)


def quitar(db: Session, usuario, share_id: str) -> None:
    from app.models.cuaderno import NotebookShare
    s = db.get(NotebookShare, share_id)
    if s is None:
        raise error(404, "no_encontrado", que="comparticion")
    nb, _ = acceso.cuaderno(db, usuario, s.notebook_id, DUENO)
    audit_log(db, usuario, "UNSHARE", "notebook", nb.id, nb.title,
              old_values={"target_type": s.target_type, "target_id": s.target_id, "permission": s.permission,
                          "section_id": s.section_id})
    db.delete(s)


def _exigir_agentes(db: Session, usuario) -> None:
    """Compartir con los agentes de código solo si la empresa lo permite."""
    from app.services.mcp_herramientas import cuaderno_por_mcp_encendido
    if not cuaderno_por_mcp_encendido(db, _org(usuario)):
        raise error(403, "mcp_cuaderno_apagado")


def destinos(db: Session, usuario, q: str = "") -> dict:
    """Equipos y departamentos de la empresa (para el selector); las personas van por el selector común."""
    from app.models.user import User
    org = _org(usuario)
    patron = f"%{(q or '').strip().lower()}%"
    from sqlalchemy import func
    equipos = [t for (t,) in db.query(User.team).filter(User.organization_id == org, User.team.isnot(None),
                                                         func.lower(User.team).like(patron)).distinct().limit(50)]
    deptos = [d for (d,) in db.query(User.department).filter(User.organization_id == org, User.department.isnot(None),
                                                              func.lower(User.department).like(patron)).distinct().limit(50)]
    return {"teams": sorted(t for t in equipos if t), "departments": sorted(d for d in deptos if d)}
