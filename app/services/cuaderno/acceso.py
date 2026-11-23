"""Quién lee o edita qué en «Mi cuaderno» (docs/CUADERNO.md §Permisos y privacidad).

Privado por defecto: un cuaderno solo lo ve su dueño. Se ve además lo que se
comparte expresamente (cuaderno entero o una sección) con la persona, con su
equipo (`users.team`) o con su departamento (`users.department`), en lectura o
en edición. **Nadie más**: ni dirección, ni el superadministrador, ni quien
tenga cualquier otra capacidad. Lo que no se puede ver responde 404 (no se
revela que existe). El único acceso a cuadernos ajenos es el excepcional de
`rgpd.acceso_excepcional` (bloqueo legal o solicitud RGPD, auditado).

Lo de la papelera solo lo ve su dueño (para restaurarlo).
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import and_, false, or_
from sqlalchemy.orm import Session

from app.core.codigos_de_error import error

LEER, EDITAR, DUENO = "read", "edit", "owner"
_RANGO = {None: 0, LEER: 1, EDITAR: 2, DUENO: 3}


def mayor(a: Optional[str], b: Optional[str]) -> Optional[str]:
    return a if _RANGO.get(a, 0) >= _RANGO.get(b, 0) else b


def _org(u):
    return getattr(u, "organization_id", None)


def condicion_de_destinatario(usuario):
    """Filtro SQL: la compartición va dirigida a `usuario` (persona, su equipo o su departamento)."""
    from app.models.cuaderno import NotebookShare as S
    conds = [and_(S.target_type == "user", S.target_id == usuario.id)]
    if getattr(usuario, "team", None):
        conds.append(and_(S.target_type == "team", S.target_id == usuario.team))
    if getattr(usuario, "department", None):
        conds.append(and_(S.target_type == "department", S.target_id == usuario.department))
    return or_(*conds)


def comparticiones_para(db: Session, usuario) -> list:
    """Las comparticiones dirigidas a `usuario` en su empresa."""
    from app.models.cuaderno import NotebookShare as S
    return db.query(S).filter(S.organization_id == _org(usuario), condicion_de_destinatario(usuario)).all()


def permisos_compartidos(db: Session, usuario) -> tuple[dict, dict]:
    """({cuaderno_id: permiso}, {seccion_id: permiso}) de lo compartido con `usuario`."""
    por_cuaderno: dict = {}
    por_seccion: dict = {}
    for s in comparticiones_para(db, usuario):
        if s.section_id:
            por_seccion[s.section_id] = mayor(por_seccion.get(s.section_id), s.permission)
        else:
            por_cuaderno[s.notebook_id] = mayor(por_cuaderno.get(s.notebook_id), s.permission)
    return por_cuaderno, por_seccion


def permiso_en_cuaderno(db: Session, usuario, nb) -> Optional[str]:
    if nb is None or nb.organization_id != _org(usuario):
        return None
    if nb.owner_id == usuario.id:
        return DUENO
    if nb.deleted_at is not None:
        return None
    por_cuaderno, _ = permisos_compartidos(db, usuario)
    return por_cuaderno.get(nb.id)


def permiso_en_seccion(db: Session, usuario, seccion, nb=None) -> Optional[str]:
    if seccion is None:
        return None
    nb = nb or seccion.notebook
    if nb is None or nb.organization_id != _org(usuario):
        return None
    if nb.owner_id == usuario.id:
        return DUENO
    if nb.deleted_at is not None or seccion.deleted_at is not None:
        return None
    por_cuaderno, por_seccion = permisos_compartidos(db, usuario)
    return mayor(por_cuaderno.get(nb.id), por_seccion.get(seccion.id))


def permiso_en_pagina(db: Session, usuario, pagina) -> Optional[str]:
    if pagina is None or pagina.organization_id != _org(usuario):
        return None
    if pagina.owner_id == usuario.id:
        return DUENO
    if pagina.deleted_at is not None:
        return None
    return permiso_en_seccion(db, usuario, pagina.section)


def _exigir(permiso: Optional[str], minimo: str, que: str):
    if permiso is None:
        raise error(404, "no_encontrado", que=que)
    if _RANGO[permiso] < _RANGO[minimo]:
        raise error(403, "cuaderno_sin_permiso")
    return permiso


def cuaderno(db: Session, usuario, nb_id: str, minimo: str = LEER):
    from app.models.cuaderno import Notebook
    nb = db.get(Notebook, nb_id)
    return nb, _exigir(permiso_en_cuaderno(db, usuario, nb), minimo, "cuaderno")


def seccion(db: Session, usuario, sec_id: str, minimo: str = LEER):
    from app.models.cuaderno import NotebookSection
    s = db.get(NotebookSection, sec_id)
    return s, _exigir(permiso_en_seccion(db, usuario, s), minimo, "seccion_de_cuaderno")


def pagina(db: Session, usuario, page_id: str, minimo: str = LEER):
    from app.models.cuaderno import NotebookPage
    p = db.get(NotebookPage, page_id)
    return p, _exigir(permiso_en_pagina(db, usuario, p), minimo, "pagina_de_cuaderno")


def filtro_paginas_legibles(db: Session, usuario, incluir_papelera: bool = False):
    """Filtro SQL de las páginas que `usuario` puede leer (suyas o compartidas)."""
    from app.models.cuaderno import Notebook, NotebookPage as P, NotebookSection
    por_cuaderno, por_seccion = permisos_compartidos(db, usuario)
    propias = P.owner_id == usuario.id
    if not incluir_papelera:
        propias = and_(propias, P.deleted_at.is_(None))
    partes = [propias]
    vivas = and_(P.deleted_at.is_(None),
                 P.section_id.in_(db.query(NotebookSection.id).filter(NotebookSection.deleted_at.is_(None))),
                 P.notebook_id.in_(db.query(Notebook.id).filter(Notebook.deleted_at.is_(None))))
    if por_cuaderno:
        partes.append(and_(vivas, P.notebook_id.in_(list(por_cuaderno))))
    if por_seccion:
        partes.append(and_(vivas, P.section_id.in_(list(por_seccion))))
    return and_(P.organization_id == _org(usuario), or_(*partes) if partes else false())


def paginas_legibles(db: Session, usuario):
    from app.models.cuaderno import NotebookPage
    return db.query(NotebookPage).filter(filtro_paginas_legibles(db, usuario))
