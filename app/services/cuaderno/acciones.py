"""Enlaces vivos y «de nota a acción» (docs/CUADERNO.md §Conectado con la herramienta).

- `buscar`: lo que ofrece `#` (tareas, tickets, proyectos, clientes) y `@`
  (personas), con el MISMO alcance que el listado de cada entidad
  (`cab_service.busqueda.consulta_de_*`): nadie encuentra lo que no ve.
- `resolver`: el estado actual de cada chip para quien lee la nota; lo que no
  puede ver sale `hidden` (sin título ni estado).
- `redactar`: quita la etiqueta de los chips que el lector no puede ver (una
  nota compartida no enseña el título de un ticket ajeno).
- `convertir`: crea una tarea, ticket, solicitud de demanda, idea de cartera o
  recordatorio de calendario desde el texto o una casilla, con vínculo en los
  dos sentidos: el objeto lleva el enlace a la nota (descripción) y la nota
  guarda el vínculo (`notebook_links`, `relation=created`) e inserta el chip.
- `vinculos_de`: las notas (que el lector puede leer) que enlazan un objeto.
"""
from __future__ import annotations
import logging

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core.codigos_de_error import error
from app.services.audit import audit_log
from app.services.cuaderno import acceso
from app.services.cuaderno.acceso import EDITAR

TIPOS_DE_ACCION = ("task", "ticket", "demand", "proposal", "event")
TIPOS_DE_ALMOHADILLA = ("task", "ticket", "project", "client")


def _org(u):
    return getattr(u, "organization_id", None)


def _puede(db: Session, usuario, capacidad: str) -> bool:
    from app.core import capacidades
    return getattr(usuario, "is_superadmin", False) or capacidades.tiene(db, usuario, capacidad)


def _url_de_nota(page_id: str) -> str:
    return f"/notebook?page={page_id}"


# ── Búsqueda para # y @ ──────────────────────────────────────────────────────

def _consulta_de_clientes(db: Session, usuario, patron: Optional[str]):
    if not _puede(db, usuario, "finanzas.ver"):
        return None
    from sqlalchemy import func, or_
    from app.models.clients import Client
    q = db.query(Client).filter(Client.organization_id == _org(usuario))
    if patron:
        # `Client` no tiene `code` ni `is_active`: el alias corto hace de código.
        q = q.filter(or_(func.lower(Client.name).like(patron), func.lower(Client.short_name).like(patron)))
    return q


def buscar(db: Session, usuario, q: str, tipos: Optional[list] = None, limite: int = 8) -> list[dict]:
    """Candidatos para un chip. `tipos`: subconjunto de task, ticket, project, client, user."""
    from app.services.cab_service import busqueda
    q = (q or "").strip()
    patron = f"%{q.lower()}%"
    tipos = [t for t in (tipos or list(TIPOS_DE_ALMOHADILLA)) if t in TIPOS_DE_ALMOHADILLA + ("user",)]
    salida: list[dict] = []
    if "task" in tipos:
        for t in busqueda.consulta_de_tareas(db, usuario, patron).limit(limite):
            salida.append({"type": "task", "id": t.id, "label": f"{t.code or ''} {t.title}".strip(),
                           "status": t.status, "subtitle": getattr(t.project, "name", None)})
    if "ticket" in tipos:
        for t in busqueda.consulta_de_tickets(db, usuario, patron).limit(limite):
            salida.append({"type": "ticket", "id": t.id, "label": f"{t.number} {t.title}",
                           "status": str(getattr(t.status, "value", t.status)), "subtitle": None})
    if "project" in tipos:
        for p in busqueda.consulta_de_proyectos(db, usuario, patron).limit(limite):
            salida.append({"type": "project", "id": p.id, "label": p.name, "status": p.status,
                           "subtitle": p.code})
    if "client" in tipos:
        consulta = _consulta_de_clientes(db, usuario, patron)
        if consulta is not None:
            for c in consulta.limit(limite):
                salida.append({"type": "client", "id": c.id, "label": c.name, "status": None, "subtitle": None})
    if "user" in tipos:
        for u in busqueda.consulta_de_personas(db, usuario, patron).limit(limite):
            salida.append({"type": "user", "id": u.id, "label": u.full_name, "status": None,
                           "subtitle": u.job_title if hasattr(u, "job_title") else None})
    return salida


# ── Estado de los chips ──────────────────────────────────────────────────────

def _uno(db: Session, usuario, tipo: str, oid: str) -> Optional[dict]:
    """El estado visible de un objeto para `usuario` (o None si no lo ve)."""
    from app.services.cab_service import busqueda
    if tipo == "task":
        from app.models.task import Task
        t = busqueda.consulta_de_tareas(db, usuario, "%").filter(Task.id == oid).first()
        return t and {"label": f"{t.code or ''} {t.title}".strip(), "status": t.status,
                      "url": f"/tasks?task={t.id}", "due_date": t.due_date.isoformat() if t.due_date else None}
    if tipo == "ticket":
        from app.models.service_desk import Ticket
        t = busqueda.consulta_de_tickets(db, usuario, "%").filter(Ticket.id == oid).first()
        return t and {"label": f"{t.number} {t.title}", "status": str(getattr(t.status, "value", t.status)),
                      "url": f"/service-desk?ticket={t.id}"}
    if tipo == "project":
        from app.models.project import Project
        p = busqueda.consulta_de_proyectos(db, usuario, "%").filter(Project.id == oid).first()
        return p and {"label": p.name, "status": p.status, "url": f"/projects/{p.id}"}
    if tipo == "client":
        consulta = _consulta_de_clientes(db, usuario, None)
        if consulta is None:
            return None
        from app.models.clients import Client
        c = consulta.filter(Client.id == oid).first()
        return c and {"label": c.name, "status": str(getattr(c.status, "value", c.status) or "") or None,
                      "url": f"/clients?client={c.id}"}
    if tipo == "user":
        from app.models.user import User
        u = busqueda.consulta_de_personas(db, usuario, "%").filter(User.id == oid).first()
        return u and {"label": u.full_name, "status": "active" if u.is_active else "inactive", "url": None}
    if tipo == "demand":
        from app.models.demanda import DemandRequest
        r = db.get(DemandRequest, oid)
        if r is None or r.organization_id != _org(usuario):
            return None
        if r.requester_user_id != usuario.id and r.created_by_user_id != usuario.id \
                and not _puede(db, usuario, "demanda.ver"):
            return None
        return {"label": f"{r.code} {r.title}", "status": r.status, "url": f"/demand?request={r.id}"}
    if tipo == "proposal":
        from app.models.portfolio import PortfolioProposal
        p = db.get(PortfolioProposal, oid)
        if p is None or p.organization_id != _org(usuario):
            return None
        if p.requested_by != usuario.id and not _puede(db, usuario, "cartera.gestionar"):
            return None
        return {"label": p.title, "status": p.status, "url": "/portfolio/intake"}
    if tipo == "event":
        from app.models.cab import CalendarEvent
        e = db.get(CalendarEvent, oid)
        if e is None or e.organization_id != _org(usuario) or e.user_id != usuario.id:
            return None
        return {"label": e.title, "status": e.start_dt.isoformat() if e.start_dt else None, "url": "/calendar"}
    return None


def resolver(db: Session, usuario, refs: list) -> list[dict]:
    """[{type, id}] → [{type, id, hidden, label, status, url}] (máximo 200)."""
    salida = []
    for r in (refs or [])[:200]:
        if not isinstance(r, dict):
            continue
        tipo, oid = r.get("type"), str(r.get("id") or "")[:36]
        try:
            datos = _uno(db, usuario, tipo, oid) if oid else None
        except Exception:  # noqa: BLE001 - un chip roto no tumba la página
            logging.getLogger(__name__).debug("resolver: excepcion ignorada", exc_info=True)
            datos = None
        salida.append({"type": tipo, "id": oid, "hidden": datos is None, **(datos or {})})
    return salida


def redactar(db: Session, usuario, doc: dict) -> dict:
    """Quita la etiqueta de los chips que `usuario` no puede ver (in situ)."""
    cache: dict = {}

    def ir(n: dict):
        if n.get("type") in ("objectRef", "mention"):
            a = n.get("attrs") or {}
            tipo = a.get("type") if n["type"] == "objectRef" else "user"
            clave = (tipo, a.get("id"))
            if clave not in cache:
                try:
                    cache[clave] = _uno(db, usuario, tipo, a.get("id") or "") is not None
                except Exception:  # noqa: BLE001
                    logging.getLogger(__name__).warning("ir: excepcion ignorada", exc_info=True)
                    cache[clave] = False
            if not cache[clave]:
                a["label"] = ""
        for h in n.get("content") or []:
            ir(h)

    ir(doc)
    return doc


# ── De nota a acción ─────────────────────────────────────────────────────────

def _fecha(v) -> Optional[date]:
    if not v:
        return None
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        raise error(422, "cuaderno_fecha_no_valida")


def _instante(v) -> Optional[datetime]:
    if not v:
        return None
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        raise error(422, "cuaderno_fecha_no_valida")
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _crear_tarea(db: Session, usuario, titulo: str, descripcion: str, datos: dict) -> tuple[str, str]:
    from app.models.project import Project
    from app.models.task import Task
    from app.services.cab_service import busqueda
    from app.services.numbering import next_numbered_code
    if not (_puede(db, usuario, "tareas.usar") or _puede(db, usuario, "tareas.crear")):
        raise error(403, "capacidad_requerida", capacidad="tareas.usar")
    pid = datos.get("project_id")
    if not pid:
        raise error(422, "cuaderno_proyecto_obligatorio")
    if busqueda.consulta_de_proyectos(db, usuario, "%").filter(Project.id == pid).first() is None:
        raise error(404, "proyecto_no_encontrado")
    tarea = Task(code=next_numbered_code(db, "task", prefix="TSK", padding=5), project_id=pid, title=titulo[:255],
                 description=descripcion, status="todo", priority=datos.get("priority") or "medium",
                 assignee_id=datos.get("assignee_id") or usuario.id, due_date=_fecha(datos.get("due_date")),
                 created_by=usuario.id, reporter_id=usuario.id)
    db.add(tarea)
    db.flush()
    return tarea.id, f"{tarea.code} {tarea.title}"


def _crear_ticket(db: Session, usuario, titulo: str, descripcion: str, datos: dict) -> tuple[str, str]:
    from app.models.service_desk import Ticket, TicketPriority, TicketType
    from app.services.sla_service import next_ticket_number
    if not _puede(db, usuario, "sd.trabajar"):
        raise error(403, "capacidad_requerida", capacidad="sd.trabajar")
    ticket = Ticket(organization_id=_org(usuario), number=next_ticket_number(TicketType.service_request.value, db),
                    ticket_type=TicketType.service_request, title=titulo[:500], description=descripcion,
                    status="new", priority=TicketPriority.p3_medium, source="notebook",
                    project_id=datos.get("project_id") or None, requester_user_id=usuario.id,
                    requester_name=usuario.full_name, created_by_user_id=usuario.id)
    db.add(ticket)
    db.flush()
    return ticket.id, f"{ticket.number} {ticket.title}"


def _crear_demanda(db: Session, usuario, titulo: str, descripcion: str, datos: dict) -> tuple[str, str]:
    from app.services.demanda import entrada
    s = entrada.Solicitante(kind="employee", user=usuario)
    r = entrada.crear(db, s, {"title": titulo[:255], "description": descripcion, "submit": False,
                              "type_key": datos.get("type_key") or None, "project_id": datos.get("project_id")},
                      org_id=_org(usuario))
    return r["id"], f"{r.get('code') or ''} {r.get('title') or titulo}".strip()


def _crear_propuesta(db: Session, usuario, titulo: str, descripcion: str, datos: dict) -> tuple[str, str]:
    from app.services import cartera_service
    if not _puede(db, usuario, "cartera.usar"):
        raise error(403, "capacidad_requerida", capacidad="cartera.usar")
    p = cartera_service.guardar(db, usuario, {"title": titulo[:255], "description": descripcion})
    return p["id"], p.get("title") or titulo


def _crear_evento(db: Session, usuario, titulo: str, descripcion: str, datos: dict) -> tuple[str, str]:
    from app.models.cab import CalendarEvent
    inicio = _instante(datos.get("start")) or (datetime.now(timezone.utc) + timedelta(hours=1))
    fin = _instante(datos.get("end")) or inicio + timedelta(minutes=int(datos.get("duration_min") or 30))
    if fin <= inicio:
        raise error(422, "cuaderno_fecha_no_valida")
    e = CalendarEvent(organization_id=_org(usuario), user_id=usuario.id, title=titulo[:500], start_dt=inicio,
                      end_dt=fin, all_day=False, description=descripcion, sync_direction="push")
    db.add(e)
    db.flush()
    return e.id, e.title


_CREADORES = {"task": _crear_tarea, "ticket": _crear_ticket, "demand": _crear_demanda,
              "proposal": _crear_propuesta, "event": _crear_evento}


def convertir(db: Session, usuario, page_id: str, datos: dict) -> dict:
    """Crea el objeto desde la nota. `datos`: kind, text, title?, project_id?, due_date?, start?, end?."""
    from app.models.cuaderno import NotebookLink
    p, _ = acceso.pagina(db, usuario, page_id, EDITAR)
    tipo = datos.get("kind")
    if tipo not in TIPOS_DE_ACCION:
        raise error(422, "cuaderno_accion_no_valida")
    texto = str(datos.get("text") or "").strip()
    titulo = str(datos.get("title") or texto.split("\n")[0]).strip()[:255]
    if not titulo:
        raise error(422, "cuaderno_accion_sin_texto")
    descripcion = (texto + "\n\n" if texto and texto != titulo else "") + \
        f"— {p.title or 'Nota'}: {_url_de_nota(p.id)}"
    oid, etiqueta = _CREADORES[tipo](db, usuario, titulo, descripcion, datos)
    db.add(NotebookLink(organization_id=p.organization_id, page_id=p.id, object_type=tipo, object_id=oid,
                        relation="created", created_by=usuario.id))
    audit_log(db, usuario, "CREATE", f"notebook_action_{tipo}", oid, etiqueta[:255],
              metadata={"page_id": p.id, "block_id": datos.get("block_id")})
    estado = _uno(db, usuario, tipo, oid) or {}
    return {"type": tipo, "id": oid, "label": etiqueta, "status": estado.get("status"), "url": estado.get("url")}


def vinculos_de(db: Session, usuario, tipo: str, oid: str) -> list[dict]:
    """Notas que enlazan el objeto y que `usuario` puede leer (el enlace de vuelta)."""
    from app.models.cuaderno import NotebookLink, NotebookPage
    paginas = acceso.paginas_legibles(db, usuario).with_entities(NotebookPage.id)
    filas = db.query(NotebookLink, NotebookPage.title).join(NotebookPage, NotebookPage.id == NotebookLink.page_id) \
        .filter(NotebookLink.object_type == tipo, NotebookLink.object_id == oid,
                NotebookLink.page_id.in_(paginas)).limit(50).all()
    return [{"page_id": link.page_id, "page_title": titulo, "relation": link.relation,
             "url": _url_de_nota(link.page_id)} for link, titulo in filas]
