"""Plantillas de página de «Mi cuaderno» (Configuración › Mi cuaderno › Plantillas).

Cuatro de fábrica (acta de reunión, seguimiento de cliente, 1:1 y lluvia de
ideas) en es/en/zh. La empresa puede editarlas, desactivarlas o crear otras
(`notebook_templates`); una de fábrica editada se guarda como fila con su clave
y manda sobre la del código.
"""
from __future__ import annotations

import json
import re
from typing import Optional

from sqlalchemy.orm import Session

from app.core.codigos_de_error import error
from app.services.cuaderno import contenido
from app.services.formato_regional import IDIOMA_DE_RESPALDO

_CLAVE = re.compile(r"^[a-z][a-z0-9_]{0,59}$")

_TEXTOS = {
    "es": {
        "meeting_minutes": ("Acta de reunión", ["Asistentes", "Orden del día", "Decisiones", "Acciones"]),
        "client_followup": ("Seguimiento de cliente", ["Contexto", "Situación actual", "Riesgos", "Próximos pasos"]),
        "one_on_one": ("1:1", ["Cómo va", "Objetivos", "Bloqueos", "Acuerdos"]),
        "brainstorming": ("Lluvia de ideas", ["Problema", "Ideas", "Favoritas", "Siguiente paso"]),
    },
    "en": {
        "meeting_minutes": ("Meeting minutes", ["Attendees", "Agenda", "Decisions", "Actions"]),
        "client_followup": ("Client follow-up", ["Context", "Current status", "Risks", "Next steps"]),
        "one_on_one": ("1:1", ["How it's going", "Goals", "Blockers", "Agreements"]),
        "brainstorming": ("Brainstorming", ["Problem", "Ideas", "Favourites", "Next step"]),
    },
    "zh": {
        "meeting_minutes": ("会议纪要", ["参会人员", "议程", "决定", "行动项"]),
        "client_followup": ("客户跟进", ["背景", "当前状况", "风险", "下一步"]),
        "one_on_one": ("一对一", ["近况", "目标", "阻碍", "约定"]),
        "brainstorming": ("头脑风暴", ["问题", "想法", "首选", "下一步"]),
    },
}
CLAVES_DE_FABRICA = tuple(_TEXTOS[IDIOMA_DE_RESPALDO])


def _doc_de_fabrica(clave: str, idioma: str) -> dict:
    nombre, apartados = _TEXTOS.get(idioma, _TEXTOS[IDIOMA_DE_RESPALDO])[clave]
    contenido_ = []
    for i, apartado in enumerate(apartados):
        contenido_.append({"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": apartado}]})
        if i == len(apartados) - 1 or clave == "one_on_one" and i == 2:
            contenido_.append({"type": "taskList", "content": [
                {"type": "taskItem", "attrs": {"checked": False}, "content": [{"type": "paragraph"}]}]})
        else:
            contenido_.append({"type": "bulletList", "content": [
                {"type": "listItem", "content": [{"type": "paragraph"}]}]})
    return {"type": "doc", "content": contenido_}


def _fila_a_dict(t) -> dict:
    return {"id": t.id, "key": t.key, "name": t.name, "description": t.description, "is_active": bool(t.is_active),
            "sort_order": t.sort_order, "builtin": t.key in CLAVES_DE_FABRICA, "custom": True,
            "content": contenido.cargar(t.content)}


def listar(db: Session, org: Optional[str], idioma: str = "es", solo_activas: bool = False) -> list[dict]:
    from app.models.cuaderno import NotebookTemplate
    filas = {t.key: t for t in db.query(NotebookTemplate).filter(NotebookTemplate.organization_id == org)}
    salida = []
    for i, clave in enumerate(CLAVES_DE_FABRICA):
        if clave in filas:
            continue
        salida.append({"id": None, "key": clave, "name": _TEXTOS.get(idioma, _TEXTOS[IDIOMA_DE_RESPALDO])[clave][0],
                       "description": None, "is_active": True, "sort_order": i, "builtin": True, "custom": False,
                       "content": _doc_de_fabrica(clave, idioma)})
    salida.extend(_fila_a_dict(t) for t in filas.values())
    if solo_activas:
        salida = [p for p in salida if p["is_active"]]
    return sorted(salida, key=lambda p: (p["sort_order"], p["name"]))


def contenido_de(db: Session, org: Optional[str], clave: str, idioma: str = "es") -> dict:
    for p in listar(db, org, idioma, solo_activas=True):
        if p["key"] == clave:
            return p["content"]
    raise error(404, "no_encontrado", que="plantilla_de_cuaderno")


def guardar(db: Session, org: Optional[str], usuario, datos: dict) -> dict:
    """Crea o cambia una plantilla (por su clave). Auditado. No confirma."""
    from app.models.cuaderno import NotebookTemplate
    from app.services.audit import audit_log
    clave = str(datos.get("key") or "").strip().lower()
    if not _CLAVE.match(clave):
        raise error(422, "cuaderno_plantilla_no_valida", campo="key")
    nombre = str(datos.get("name") or "").strip()[:200]
    if not nombre:
        raise error(422, "cuaderno_plantilla_no_valida", campo="name")
    doc = contenido.validar(datos.get("content"))
    t = db.query(NotebookTemplate).filter(NotebookTemplate.organization_id == org,
                                          NotebookTemplate.key == clave).first()
    nueva = t is None
    if nueva:
        t = NotebookTemplate(organization_id=org, key=clave, created_by=usuario.id)
        db.add(t)
    t.name = nombre
    t.description = (str(datos.get("description") or "").strip()[:500]) or None
    t.content = json.dumps(doc, ensure_ascii=False)
    t.is_active = bool(datos.get("is_active", True))
    t.sort_order = int(datos.get("sort_order") or 0)
    t.updated_by = usuario.id
    db.flush()
    audit_log(db, usuario, "CREATE" if nueva else "UPDATE", "notebook_template", t.id, nombre,
              new_values={"key": clave, "is_active": t.is_active})
    return _fila_a_dict(t)


def borrar(db: Session, org: Optional[str], usuario, clave: str) -> None:
    """Borra la plantilla propia (una de fábrica vuelve a su versión del código)."""
    from app.models.cuaderno import NotebookTemplate
    from app.services.audit import audit_log
    t = db.query(NotebookTemplate).filter(NotebookTemplate.organization_id == org,
                                          NotebookTemplate.key == clave).first()
    if t is None:
        raise error(404, "no_encontrado", que="plantilla_de_cuaderno")
    audit_log(db, usuario, "DELETE", "notebook_template", t.id, t.name)
    db.delete(t)
