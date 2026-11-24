"""Árbol, cuadernos, secciones, páginas, orden, papelera, búsqueda, tareas y etiquetas.

Permisos en `acceso` (privado por defecto, compartido expreso, 404 fuera).
Lo relevante queda en `audit_logs` (crear, borrar, restaurar, purgar, mover
entre cuadernos); el texto de las notas nunca va a la auditoría. No confirma.
"""
from __future__ import annotations
import logging

import json
import re
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.codigos_de_error import error
from app.services.audit import audit_log
from app.services.cuaderno import acceso, contenido
from app.services.cuaderno.acceso import DUENO, EDITAR, LEER

COLORES = ("blue", "green", "amber", "red", "purple", "teal", "pink", "gray", "orange")
_COLOR = re.compile(r"^[a-z]{3,10}$")


def ahora() -> datetime:
    return datetime.now(timezone.utc)


def _org(u):
    return getattr(u, "organization_id", None)


def _color(v) -> Optional[str]:
    return v if isinstance(v, str) and v in COLORES else None


def _titulo(v, defecto: str, maximo: int = 200) -> str:
    t = str(v or "").strip()[:maximo]
    return t or defecto


def _iso(v) -> Optional[str]:
    return v.isoformat() if v else None


# ── Cuaderno inicial ─────────────────────────────────────────────────────────

def asegurar_inicial(db: Session, usuario) -> None:
    """Quien entra por primera vez tiene «Mi cuaderno» (sección «General») y «Notas rápidas»."""
    from app.models.cuaderno import Notebook, NotebookSection
    hay = db.query(Notebook.id).filter(Notebook.owner_id == usuario.id, Notebook.organization_id == _org(usuario)).first()
    if hay:
        return
    from app.services.formato_regional import idioma_de_salida
    idioma = idioma_de_salida(db, user_id=usuario.id, org_id=_org(usuario))
    nombres = {"es": ("Mi cuaderno", "General", "Notas rápidas", "Rápidas"),
               "en": ("My notebook", "General", "Quick notes", "Quick"),
               "zh": ("我的笔记本", "常规", "快速笔记", "快速")}.get(idioma, ("Mi cuaderno", "General", "Notas rápidas",
                                                                           "Rápidas"))
    for titulo, seccion, rapido, orden in ((nombres[0], nombres[1], False, 0), (nombres[2], nombres[3], True, 1)):
        nb = Notebook(organization_id=_org(usuario), owner_id=usuario.id, title=titulo, color="blue" if not rapido
                      else "amber", sort_order=orden, is_quick=rapido)
        db.add(nb)
        db.flush()
        db.add(NotebookSection(organization_id=_org(usuario), notebook_id=nb.id, owner_id=usuario.id, title=seccion,
                               color="blue" if not rapido else "amber", sort_order=0))
    db.flush()


def cuaderno_rapido(db: Session, usuario):
    """(cuaderno, sección) de las notas rápidas de la persona (lo crea si falta)."""
    from app.models.cuaderno import Notebook, NotebookSection
    asegurar_inicial(db, usuario)
    nb = db.query(Notebook).filter(Notebook.owner_id == usuario.id, Notebook.organization_id == _org(usuario),
                                   Notebook.is_quick.is_(True), Notebook.deleted_at.is_(None)).first()
    if nb is None:
        nb = Notebook(organization_id=_org(usuario), owner_id=usuario.id, title="Notas rápidas", color="amber",
                      sort_order=99, is_quick=True)
        db.add(nb)
        db.flush()
    sec = db.query(NotebookSection).filter(NotebookSection.notebook_id == nb.id,
                                           NotebookSection.deleted_at.is_(None)).order_by(NotebookSection.sort_order).first()
    if sec is None:
        sec = NotebookSection(organization_id=_org(usuario), notebook_id=nb.id, owner_id=usuario.id, title="Notas",
                              color="amber", sort_order=0)
        db.add(sec)
        db.flush()
    return nb, sec


# ── Árbol ────────────────────────────────────────────────────────────────────

def _pagina_corta(p) -> dict:
    return {"id": p.id, "title": p.title, "parent_id": p.parent_id, "sort_order": p.sort_order,
            "updated_at": _iso(p.updated_at or p.created_at), "created_at": _iso(p.created_at)}


def _seccion_dict(s, permiso: str, paginas: list) -> dict:
    return {"id": s.id, "notebook_id": s.notebook_id, "title": s.title, "color": s.color, "sort_order": s.sort_order,
            "permission": permiso, "pages": [_pagina_corta(p) for p in paginas]}


def arbol(db: Session, usuario) -> dict:
    """Los cuadernos que la persona ve: los suyos y lo compartido con ella."""
    from app.models.cuaderno import Notebook, NotebookPage, NotebookSection, NotebookShare
    from app.models.user import User
    asegurar_inicial(db, usuario)
    org = _org(usuario)
    por_cuaderno, por_seccion = acceso.permisos_compartidos(db, usuario)
    ids_secciones_sueltas = set(por_seccion)
    if ids_secciones_sueltas:
        sueltas = db.query(NotebookSection).filter(NotebookSection.id.in_(list(ids_secciones_sueltas))).all()
    else:
        sueltas = []
    ids = set(por_cuaderno) | {s.notebook_id for s in sueltas}
    cuadernos = db.query(Notebook).filter(Notebook.organization_id == org, Notebook.deleted_at.is_(None),
                                          or_(Notebook.owner_id == usuario.id, Notebook.id.in_(list(ids) or [""]))) \
        .order_by(Notebook.sort_order, Notebook.created_at).all()
    nb_ids = [n.id for n in cuadernos]
    secciones = db.query(NotebookSection).filter(NotebookSection.notebook_id.in_(nb_ids or [""]),
                                                 NotebookSection.deleted_at.is_(None)) \
        .order_by(NotebookSection.sort_order, NotebookSection.created_at).all()
    paginas = db.query(NotebookPage.id, NotebookPage.title, NotebookPage.parent_id, NotebookPage.sort_order,
                       NotebookPage.updated_at, NotebookPage.created_at, NotebookPage.section_id) \
        .filter(NotebookPage.notebook_id.in_(nb_ids or [""]), NotebookPage.deleted_at.is_(None)) \
        .order_by(NotebookPage.sort_order, NotebookPage.created_at).all()
    por_sec: dict = {}
    for p in paginas:
        por_sec.setdefault(p.section_id, []).append(p)
    compartidos = {n for (n,) in db.query(NotebookShare.notebook_id).filter(NotebookShare.notebook_id.in_(nb_ids or [""]))}
    duenos = {u.id: u.full_name for u in db.query(User.id, User.full_name).filter(
        User.id.in_({n.owner_id for n in cuadernos if n.owner_id != usuario.id} or {""}))}
    salida = []
    for nb in cuadernos:
        permiso_nb = DUENO if nb.owner_id == usuario.id else por_cuaderno.get(nb.id)
        secs = []
        for s in (x for x in secciones if x.notebook_id == nb.id):
            permiso = acceso.mayor(permiso_nb, por_seccion.get(s.id))
            if permiso is None:
                continue
            secs.append(_seccion_dict(s, permiso, por_sec.get(s.id, [])))
        salida.append({"id": nb.id, "title": nb.title, "color": nb.color, "sort_order": nb.sort_order,
                       "is_quick": bool(nb.is_quick), "permission": permiso_nb or LEER,
                       "owner_id": nb.owner_id, "owner_name": duenos.get(nb.owner_id),
                       "shared": nb.id in compartidos, "transferred_from": nb.transferred_from,
                       "sections": secs})
    papelera = sum(db.query(func.count(M.id)).filter(M.owner_id == usuario.id, M.organization_id == org,
                                                     M.deleted_at.isnot(None)).scalar() or 0
                   for M in (Notebook, NotebookSection, NotebookPage))
    return {"notebooks": salida, "trash_count": papelera}


# ── Cuadernos ────────────────────────────────────────────────────────────────

def crear_cuaderno(db: Session, usuario, datos: dict):
    from app.models.cuaderno import Notebook, NotebookSection
    orden = (db.query(func.max(Notebook.sort_order)).filter(Notebook.owner_id == usuario.id).scalar() or 0) + 1
    nb = Notebook(organization_id=_org(usuario), owner_id=usuario.id, title=_titulo(datos.get("title"), "—"),
                  color=_color(datos.get("color")) or "blue", sort_order=orden)
    db.add(nb)
    db.flush()
    db.add(NotebookSection(organization_id=_org(usuario), notebook_id=nb.id, owner_id=usuario.id,
                           title=_titulo(datos.get("section_title"), "General"), color=nb.color, sort_order=0))
    audit_log(db, usuario, "CREATE", "notebook", nb.id, nb.title)
    db.flush()
    return nb


def editar_cuaderno(db: Session, usuario, nb_id: str, datos: dict):
    nb, _ = acceso.cuaderno(db, usuario, nb_id, DUENO)
    if "title" in datos:
        nb.title = _titulo(datos["title"], nb.title)
    if "color" in datos:
        nb.color = _color(datos["color"]) or nb.color
    return nb


def borrar_cuaderno(db: Session, usuario, nb_id: str) -> None:
    """A la papelera (lo compartido deja de verse)."""
    nb, _ = acceso.cuaderno(db, usuario, nb_id, DUENO)
    nb.deleted_at, nb.deleted_by = ahora(), usuario.id
    audit_log(db, usuario, "DELETE", "notebook", nb.id, nb.title, new_values={"to": "trash"})


# ── Secciones ────────────────────────────────────────────────────────────────

def crear_seccion(db: Session, usuario, nb_id: str, datos: dict):
    from app.models.cuaderno import NotebookSection
    nb, _ = acceso.cuaderno(db, usuario, nb_id, EDITAR)
    orden = (db.query(func.max(NotebookSection.sort_order)).filter(NotebookSection.notebook_id == nb.id).scalar() or 0) + 1
    s = NotebookSection(organization_id=nb.organization_id, notebook_id=nb.id, owner_id=nb.owner_id,
                        title=_titulo(datos.get("title"), "—"), color=_color(datos.get("color")) or "gray",
                        sort_order=orden)
    db.add(s)
    db.flush()
    audit_log(db, usuario, "CREATE", "notebook_section", s.id, s.title, metadata={"notebook_id": nb.id})
    return s


def editar_seccion(db: Session, usuario, sec_id: str, datos: dict):
    s, permiso = acceso.seccion(db, usuario, sec_id, EDITAR)
    if "title" in datos:
        s.title = _titulo(datos["title"], s.title)
    if "color" in datos:
        s.color = _color(datos["color"]) or s.color
    if datos.get("notebook_id") and datos["notebook_id"] != s.notebook_id:
        # Mover a otro cuaderno: dueño de los dos.
        if permiso != DUENO:
            raise error(403, "cuaderno_sin_permiso")
        destino, _ = acceso.cuaderno(db, usuario, datos["notebook_id"], DUENO)
        from app.models.cuaderno import NotebookItem, NotebookPage
        origen = s.notebook_id
        s.notebook_id = destino.id
        db.query(NotebookPage).filter(NotebookPage.section_id == s.id).update(
            {"notebook_id": destino.id}, synchronize_session=False)
        db.query(NotebookItem).filter(NotebookItem.page_id.in_(
            db.query(NotebookPage.id).filter(NotebookPage.section_id == s.id))).update(
            {"notebook_id": destino.id}, synchronize_session=False)
        # Las comparticiones de la sección eran del cuaderno de origen: se quitan.
        from app.models.cuaderno import NotebookShare
        db.query(NotebookShare).filter(NotebookShare.section_id == s.id).delete(synchronize_session=False)
        audit_log(db, usuario, "UPDATE", "notebook_section", s.id, s.title,
                  old_values={"notebook_id": origen}, new_values={"notebook_id": destino.id})
    return s


def borrar_seccion(db: Session, usuario, sec_id: str) -> None:
    s, _ = acceso.seccion(db, usuario, sec_id, EDITAR)
    s.deleted_at, s.deleted_by = ahora(), usuario.id
    audit_log(db, usuario, "DELETE", "notebook_section", s.id, s.title, new_values={"to": "trash"})


# ── Páginas ──────────────────────────────────────────────────────────────────

def crear_pagina(db: Session, usuario, sec_id: str, datos: dict):
    from app.models.cuaderno import NotebookPage
    s, _ = acceso.seccion(db, usuario, sec_id, EDITAR)
    padre = datos.get("parent_id")
    if padre:
        p_padre, _ = acceso.pagina(db, usuario, padre, LEER)
        if p_padre.section_id != s.id:
            raise error(422, "cuaderno_padre_no_valido")
    doc = contenido.validar(datos.get("content")) if datos.get("content") else None
    plantilla = datos.get("template_key")
    if doc is None and plantilla:
        from app.services.cuaderno import plantillas
        from app.services.formato_regional import idioma_de_salida
        doc = plantillas.contenido_de(db, s.organization_id, plantilla,
                                      idioma_de_salida(db, user_id=usuario.id, org_id=_org(usuario)))
    doc = doc or contenido.cargar(None)
    orden = (db.query(func.max(NotebookPage.sort_order)).filter(NotebookPage.section_id == s.id).scalar() or 0) + 1
    p = NotebookPage(organization_id=s.organization_id, section_id=s.id, notebook_id=s.notebook_id, owner_id=s.owner_id,
                     parent_id=padre or None, title=_titulo(datos.get("title"), "", 300), sort_order=orden,
                     content=json.dumps(doc, ensure_ascii=False), content_text=contenido.texto_plano(doc),
                     template_key=plantilla or None, created_by=usuario.id, updated_by=usuario.id, version=1)
    db.add(p)
    db.flush()
    reindexar(db, p, doc)
    audit_log(db, usuario, "CREATE", "notebook_page", p.id, p.title or "—",
              metadata={"section_id": s.id, "template": plantilla})
    return p


def detalle(db: Session, usuario, page_id: str) -> dict:
    from app.models.cuaderno import NotebookAttachment, NotebookShare
    from app.models.user import User
    p, permiso = acceso.pagina(db, usuario, page_id, LEER)
    s = p.section
    nb = s.notebook if s else None
    compartida = db.query(NotebookShare.id).filter(NotebookShare.notebook_id == p.notebook_id).first() is not None
    adjuntos = db.query(NotebookAttachment).filter(NotebookAttachment.page_id == p.id) \
        .order_by(NotebookAttachment.created_at).all()
    autor = db.get(User, p.updated_by) if p.updated_by else None
    return {
        "id": p.id, "title": p.title, "section_id": p.section_id, "notebook_id": p.notebook_id,
        "parent_id": p.parent_id, "section_title": s.title if s else None, "notebook_title": nb.title if nb else None,
        "section_color": s.color if s else None,
        "content": contenido.cargar(p.content), "version": p.version, "permission": permiso,
        "shared": compartida, "owner_id": p.owner_id,
        "created_at": _iso(p.created_at), "updated_at": _iso(p.updated_at or p.created_at),
        "updated_by_name": autor.full_name if autor else None, "deleted_at": _iso(p.deleted_at),
        "attachments": [{"id": a.id, "kind": a.kind, "file_name": a.file_name, "mime_type": a.mime_type,
                         "size_bytes": a.size_bytes, "url": f"/api/v1/notebook/attachments/{a.id}/file",
                         "created_at": _iso(a.created_at)} for a in adjuntos],
    }


def reindexar(db: Session, pagina, doc: dict) -> None:
    """Rehace las casillas, etiquetas y enlaces `@`/`#` de la página (los creados desde la nota se quedan)."""
    from app.models.cuaderno import NotebookItem, NotebookLink
    previos = {(i.block_id, i.remind_at): i.reminded_at for i in
               db.query(NotebookItem).filter(NotebookItem.page_id == pagina.id, NotebookItem.block_id.isnot(None))}
    db.query(NotebookItem).filter(NotebookItem.page_id == pagina.id).delete(synchronize_session=False)
    for pos, e in enumerate(contenido.elementos(doc)):
        if e["kind"] == "tag" and not e.get("tag_key"):
            continue
        db.add(NotebookItem(organization_id=pagina.organization_id, page_id=pagina.id, notebook_id=pagina.notebook_id,
                            owner_id=pagina.owner_id, kind=e["kind"], tag_key=e.get("tag_key"),
                            block_id=e.get("block_id"), text=e.get("text") or "", checked=bool(e.get("checked")),
                            due_date=e.get("due_date"), remind_at=e.get("remind_at"),
                            reminded_at=previos.get((e.get("block_id"), e.get("remind_at"))), position=pos))
    db.query(NotebookLink).filter(NotebookLink.page_id == pagina.id, NotebookLink.relation == "mention") \
        .delete(synchronize_session=False)
    creados = {(t, i) for t, i in db.query(NotebookLink.object_type, NotebookLink.object_id)
               .filter(NotebookLink.page_id == pagina.id)}
    for tipo, oid in contenido.enlaces(doc):
        if (tipo, oid) not in creados:
            db.add(NotebookLink(organization_id=pagina.organization_id, page_id=pagina.id, object_type=tipo,
                                object_id=oid, relation="mention", created_by=pagina.updated_by))


def guardar_contenido(db: Session, usuario, page_id: str, datos: dict) -> dict:
    """Guardado automático. `base_version` detecta conflictos (sin red); en edición
    simultánea (`collab`) el documento ya llega fusionado por Yjs y no se compara."""
    p, _ = acceso.pagina(db, usuario, page_id, EDITAR)
    base = datos.get("base_version")
    if base is not None and not datos.get("collab") and int(base) != int(p.version or 1):
        raise error(409, "cuaderno_conflicto_de_version", version=p.version)
    if "content" in datos:
        doc = contenido.validar(datos["content"])
        p.content = json.dumps(doc, ensure_ascii=False)
        p.content_text = contenido.texto_plano(doc)
        reindexar(db, p, doc)
    if "title" in datos:
        p.title = _titulo(datos["title"], "", 300)
    p.version = int(p.version or 1) + 1
    p.updated_by = usuario.id
    p.updated_at = ahora()
    if datos.get("yjs_state"):
        from app.services.cuaderno import colaboracion
        colaboracion.guardar(db, usuario, p, datos["yjs_state"])
    return {"id": p.id, "version": p.version, "updated_at": _iso(p.updated_at)}


def mover_pagina(db: Session, usuario, page_id: str, datos: dict):
    """Cambia de sección (en el mismo cuaderno o a otro del que se es dueño) o de padre."""
    from app.models.cuaderno import NotebookItem, NotebookPage
    p, permiso = acceso.pagina(db, usuario, page_id, EDITAR)
    destino_sec = datos.get("section_id") or p.section_id
    s, permiso_destino = acceso.seccion(db, usuario, destino_sec, EDITAR)
    if s.notebook_id != p.notebook_id and (permiso != DUENO or permiso_destino != DUENO):
        raise error(403, "cuaderno_sin_permiso")
    padre = datos.get("parent_id") if "parent_id" in datos else p.parent_id
    if padre:
        if padre == p.id:
            raise error(422, "cuaderno_padre_no_valido")
        pp, _ = acceso.pagina(db, usuario, padre, LEER)
        if pp.section_id != s.id:
            raise error(422, "cuaderno_padre_no_valido")
        # Sin ciclos: el padre no puede colgar de esta página.
        actual, vistos = pp, set()
        while actual is not None and actual.parent_id and actual.id not in vistos:
            vistos.add(actual.id)
            if actual.parent_id == p.id:
                raise error(422, "cuaderno_padre_no_valido")
            actual = db.get(NotebookPage, actual.parent_id)
    origen = (p.section_id, p.notebook_id)
    if s.id != p.section_id:
        # Las subpáginas se van con ella.
        hijas = [p.id]
        cola = [p.id]
        while cola:
            ids = [i for (i,) in db.query(NotebookPage.id).filter(NotebookPage.parent_id.in_(cola))]
            hijas.extend(ids)
            cola = ids
        db.query(NotebookPage).filter(NotebookPage.id.in_(hijas)).update(
            {"section_id": s.id, "notebook_id": s.notebook_id, "owner_id": s.owner_id}, synchronize_session=False)
        db.query(NotebookItem).filter(NotebookItem.page_id.in_(hijas)).update(
            {"notebook_id": s.notebook_id, "owner_id": s.owner_id}, synchronize_session=False)
        db.refresh(p)
    p.parent_id = padre or None
    if "sort_order" in datos and datos["sort_order"] is not None:
        p.sort_order = int(datos["sort_order"])
    if origen[1] != s.notebook_id:
        audit_log(db, usuario, "UPDATE", "notebook_page", p.id, p.title or "—",
                  old_values={"section_id": origen[0], "notebook_id": origen[1]},
                  new_values={"section_id": s.id, "notebook_id": s.notebook_id})
    return p


def reordenar(db: Session, usuario, tipo: str, ids: list[str]) -> None:
    """Orden libre (arrastrar o botones): `ids` en el orden nuevo, todos del mismo padre."""
    from app.models.cuaderno import Notebook, NotebookPage, NotebookSection
    if not isinstance(ids, list) or len(ids) > 2000:
        raise error(422, "cuaderno_orden_no_valido")
    modelos = {"notebook": (Notebook, acceso.cuaderno, DUENO), "section": (NotebookSection, acceso.seccion, EDITAR),
               "page": (NotebookPage, acceso.pagina, EDITAR)}
    if tipo not in modelos:
        raise error(422, "cuaderno_orden_no_valido")
    M, comprobar, minimo = modelos[tipo]
    padres = set()
    for i, oid in enumerate(ids):
        obj, _ = comprobar(db, usuario, oid, minimo)
        padres.add({"notebook": lambda o: o.owner_id, "section": lambda o: o.notebook_id,
                    "page": lambda o: (o.section_id, o.parent_id)}[tipo](obj))
        obj.sort_order = i
    if len(padres) > 1:
        raise error(422, "cuaderno_orden_no_valido")


def borrar_pagina(db: Session, usuario, page_id: str) -> None:
    """A la papelera, con sus subpáginas."""
    from app.models.cuaderno import NotebookPage
    p, _ = acceso.pagina(db, usuario, page_id, EDITAR)
    momento = ahora()
    ids, cola = [p.id], [p.id]
    while cola:
        hijas = [i for (i,) in db.query(NotebookPage.id).filter(NotebookPage.parent_id.in_(cola),
                                                               NotebookPage.deleted_at.is_(None))]
        ids.extend(hijas)
        cola = hijas
    db.query(NotebookPage).filter(NotebookPage.id.in_(ids)).update(
        {"deleted_at": momento, "deleted_by": usuario.id}, synchronize_session=False)
    audit_log(db, usuario, "DELETE", "notebook_page", p.id, p.title or "—",
              new_values={"to": "trash", "pages": len(ids)})


# ── Papelera ─────────────────────────────────────────────────────────────────

_PAPELERA = {"notebook": "Notebook", "section": "NotebookSection", "page": "NotebookPage"}


def _modelo(tipo: str):
    import app.models.cuaderno as m
    if tipo not in _PAPELERA:
        raise error(422, "cuaderno_tipo_no_valido")
    return getattr(m, _PAPELERA[tipo])


def papelera(db: Session, usuario) -> list[dict]:
    salida = []
    for tipo in _PAPELERA:
        M = _modelo(tipo)
        for o in db.query(M).filter(M.owner_id == usuario.id, M.organization_id == _org(usuario),
                                    M.deleted_at.isnot(None)).order_by(M.deleted_at.desc()).limit(500):
            salida.append({"kind": tipo, "id": o.id, "title": o.title, "deleted_at": _iso(o.deleted_at)})
    return sorted(salida, key=lambda x: x["deleted_at"] or "", reverse=True)


def _de_mi_papelera(db: Session, usuario, tipo: str, oid: str):
    M = _modelo(tipo)
    o = db.get(M, oid)
    if o is None or o.owner_id != usuario.id or o.organization_id != _org(usuario) or o.deleted_at is None:
        raise error(404, "no_encontrado", que="elemento_de_papelera")
    return o


def restaurar(db: Session, usuario, tipo: str, oid: str) -> None:
    from app.models.cuaderno import NotebookPage
    o = _de_mi_papelera(db, usuario, tipo, oid)
    momento = o.deleted_at
    o.deleted_at, o.deleted_by = None, None
    if tipo == "page":
        # Las subpáginas que se fueron con ella vuelven con ella.
        db.query(NotebookPage).filter(NotebookPage.deleted_at == momento, NotebookPage.owner_id == usuario.id,
                                      NotebookPage.section_id == o.section_id).update(
            {"deleted_at": None, "deleted_by": None}, synchronize_session=False)
    audit_log(db, usuario, "RESTORE", f"notebook_{tipo}" if tipo != "notebook" else "notebook", o.id, o.title or "—")


def purgar(db: Session, usuario, tipo: str, oid: str) -> None:
    """Borrado definitivo (respeta el bloqueo legal: 409)."""
    o = _de_mi_papelera(db, usuario, tipo, oid)
    audit_log(db, usuario, "PURGE", f"notebook_{tipo}" if tipo != "notebook" else "notebook", o.id, o.title or "—")
    db.delete(o)
    db.flush()


def vaciar_papelera(db: Session, usuario) -> int:
    n = 0
    for item in papelera(db, usuario):
        try:
            with db.begin_nested():
                purgar(db, usuario, item["kind"], item["id"])
            n += 1
        except Exception:  # noqa: BLE001 - lo bloqueado (o ya borrado en cascada) se queda
            logging.getLogger(__name__).debug("vaciar_papelera: excepcion ignorada", exc_info=True)
            continue
    return n


# ── Búsqueda ─────────────────────────────────────────────────────────────────

def _fragmento(texto: str, q: str, ancho: int = 80) -> str:
    if not texto:
        return ""
    i = texto.lower().find(q.lower())
    if i < 0:
        return texto[:ancho * 2]
    inicio = max(0, i - ancho)
    return ("…" if inicio else "") + texto[inicio:i + len(q) + ancho] + ("…" if i + len(q) + ancho < len(texto) else "")


def buscar(db: Session, usuario, q: str, notebook_id: Optional[str] = None, limite: int = 50) -> list[dict]:
    """Páginas que la persona puede leer cuyo título o texto contiene `q`."""
    from app.models.cuaderno import Notebook, NotebookPage as P, NotebookSection
    q = (q or "").strip()
    if len(q) < 2:
        return []
    patron = f"%{q.lower()}%"
    consulta = acceso.paginas_legibles(db, usuario).filter(
        or_(func.lower(P.title).like(patron), func.lower(P.content_text).like(patron)))
    if notebook_id:
        consulta = consulta.filter(P.notebook_id == notebook_id)
    filas = consulta.order_by(P.updated_at.desc().nullslast(), P.created_at.desc()).limit(min(limite, 200)).all()
    secciones = {s.id: s for s in db.query(NotebookSection).filter(NotebookSection.id.in_({p.section_id for p in filas} or {""}))}
    cuadernos = {n.id: n for n in db.query(Notebook).filter(Notebook.id.in_({p.notebook_id for p in filas} or {""}))}
    return [{"id": p.id, "title": p.title, "section_id": p.section_id, "notebook_id": p.notebook_id,
             "section_title": getattr(secciones.get(p.section_id), "title", None),
             "notebook_title": getattr(cuadernos.get(p.notebook_id), "title", None),
             "snippet": _fragmento(p.content_text or "", q), "updated_at": _iso(p.updated_at or p.created_at)}
            for p in filas]


# ── Todas mis tareas y etiquetas ─────────────────────────────────────────────

def elementos(db: Session, usuario, tipo: Optional[str] = None, estado: str = "open",
              etiqueta: Optional[str] = None, limite: int = 500) -> list[dict]:
    """Casillas y etiquetas de todas las páginas que la persona puede leer."""
    from app.models.cuaderno import Notebook, NotebookItem as I, NotebookPage as P, NotebookSection
    paginas = acceso.paginas_legibles(db, usuario).with_entities(P.id)
    q = db.query(I).filter(I.page_id.in_(paginas))
    if tipo in ("todo", "tag"):
        q = q.filter(I.kind == tipo)
    if estado == "open":
        q = q.filter(or_(I.kind == "tag", I.checked.is_(False)))
    elif estado == "done":
        q = q.filter(I.kind == "todo", I.checked.is_(True))
    if etiqueta:
        q = q.filter(I.tag_key == etiqueta)
    filas = q.order_by(I.due_date.is_(None), I.due_date, I.created_at.desc()).limit(min(limite, 2000)).all()
    pags = {p.id: p for p in db.query(P.id, P.title, P.section_id, P.notebook_id).filter(
        P.id.in_({f.page_id for f in filas} or {""}))}
    secs = {s.id: s.title for s in db.query(NotebookSection.id, NotebookSection.title).filter(
        NotebookSection.id.in_({p.section_id for p in pags.values()} or {""}))}
    nbs = {n.id: n.title for n in db.query(Notebook.id, Notebook.title).filter(
        Notebook.id.in_({p.notebook_id for p in pags.values()} or {""}))}
    salida = []
    for f in filas:
        p = pags.get(f.page_id)
        salida.append({"id": f.id, "kind": f.kind, "tag_key": f.tag_key, "text": f.text, "checked": bool(f.checked),
                       "due_date": f.due_date.isoformat() if f.due_date else None, "remind_at": _iso(f.remind_at),
                       "block_id": f.block_id, "page_id": f.page_id, "page_title": getattr(p, "title", None),
                       "section_title": secs.get(getattr(p, "section_id", None)),
                       "notebook_title": nbs.get(getattr(p, "notebook_id", None))})
    return salida


def _cambiar_casilla(nodo: dict, bid: str, hecha: bool) -> bool:
    if nodo.get("type") == "taskItem" and (nodo.get("attrs") or {}).get("bid") == bid:
        nodo.setdefault("attrs", {})["checked"] = hecha
        return True
    return any(_cambiar_casilla(h, bid, hecha) for h in nodo.get("content") or [])


def marcar_casilla(db: Session, usuario, item_id: str, hecha: bool) -> dict:
    """Marca o desmarca una casilla desde la vista agregada (cambia también la página)."""
    from app.models.cuaderno import NotebookItem
    item = db.get(NotebookItem, item_id)
    if item is None or item.kind != "todo":
        raise error(404, "no_encontrado", que="tarea_de_cuaderno")
    p, _ = acceso.pagina(db, usuario, item.page_id, EDITAR)
    doc = contenido.cargar(p.content)
    if not item.block_id or not _cambiar_casilla(doc, item.block_id, bool(hecha)):
        raise error(409, "cuaderno_casilla_no_encontrada")
    p.content = json.dumps(doc, ensure_ascii=False)
    item.checked = bool(hecha)
    p.version = int(p.version or 1) + 1
    p.updated_by, p.updated_at = usuario.id, ahora()
    from app.services.cuaderno import colaboracion
    colaboracion.invalidar(db, p.id)
    return {"id": item.id, "checked": item.checked, "page_id": p.id, "version": p.version}


# ── Etiquetas ────────────────────────────────────────────────────────────────

def etiquetas(db: Session, usuario) -> list[dict]:
    """Las de la empresa (Configuración) y las propias."""
    from app.models.cuaderno import NotebookTag
    from app.services.cuaderno import config
    salida = [{**e, "scope": "org"} for e in config.leer(db, _org(usuario)).get("tags") or []]
    claves = {e["key"] for e in salida}
    for t in db.query(NotebookTag).filter(NotebookTag.owner_id == usuario.id).order_by(NotebookTag.created_at):
        if t.key not in claves:
            salida.append({"key": t.key, "label": t.label, "color": t.color, "icon": t.icon, "scope": "mine", "id": t.id})
    return salida


def crear_etiqueta(db: Session, usuario, datos: dict) -> dict:
    from app.models.cuaderno import NotebookTag
    from app.services.cuaderno import config
    nombre = str(datos.get("label") or "").strip()[:80]
    if not nombre:
        raise error(422, "cuaderno_etiqueta_no_valida", clave="")
    base = re.sub(r"[^a-z0-9_]", "", re.sub(r"\s+", "_", nombre.lower()))[:30] or "tag"
    if not base[0].isalpha():
        base = "t_" + base
    clave, n = f"u_{base}"[:40], 1
    existentes = {e["key"] for e in etiquetas(db, usuario)}
    while clave in existentes:
        n += 1
        clave = f"u_{base}_{n}"[:40]
    if db.query(func.count(NotebookTag.id)).filter(NotebookTag.owner_id == usuario.id).scalar() >= 100:
        raise error(422, "cuaderno_demasiadas_etiquetas")
    t = NotebookTag(organization_id=_org(usuario), owner_id=usuario.id, key=clave, label=nombre,
                    color=datos.get("color") if datos.get("color") in config.COLORES else "gray",
                    icon=datos.get("icon") if datos.get("icon") in config.ICONOS else "bookmark")
    db.add(t)
    db.flush()
    return {"key": t.key, "label": t.label, "color": t.color, "icon": t.icon, "scope": "mine", "id": t.id}


def borrar_etiqueta(db: Session, usuario, tag_id: str) -> None:
    from app.models.cuaderno import NotebookTag
    t = db.get(NotebookTag, tag_id)
    if t is None or t.owner_id != usuario.id:
        raise error(404, "no_encontrado", que="etiqueta_de_cuaderno")
    db.delete(t)


def panel_rapido(db: Session, usuario) -> dict:
    """Notas rápidas (las 30 últimas) y páginas recientes legibles (10) del panel lateral.

    Prueba global 23-11-2026: la consulta vivía en la ruta `GET /notebook/quick`.
    Confirma porque `cuaderno_rapido` crea el cuaderno la primera vez.
    """
    from app.models.cuaderno import NotebookPage
    from app.services.cuaderno import acceso as _acceso
    from app.services.transaccion import confirmar
    nb, sec = cuaderno_rapido(db, usuario)
    paginas = db.query(NotebookPage).filter(NotebookPage.section_id == sec.id, NotebookPage.deleted_at.is_(None)) \
        .order_by(NotebookPage.updated_at.desc().nullslast(), NotebookPage.created_at.desc()).limit(30).all()
    recientes = _acceso.paginas_legibles(db, usuario).filter(NotebookPage.section_id != sec.id) \
        .order_by(NotebookPage.updated_at.desc().nullslast()).limit(10).all()

    def corta(p):
        cuando = p.updated_at or p.created_at
        return {"id": p.id, "title": p.title, "snippet": (p.content_text or "")[:140],
                "updated_at": cuando.isoformat() if cuando else None}
    salida = {"notebook_id": nb.id, "section_id": sec.id, "quick": [corta(p) for p in paginas],
              "recent": [corta(p) for p in recientes]}
    confirmar(db)
    return salida
