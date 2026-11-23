"""Configuración de «Mi cuaderno» por empresa (`app_settings`, clave `cuaderno.config`).

Se cambia en Configuración › Personas › Mi cuaderno (capacidad `cuaderno.config`):

- `tags`: etiquetas por defecto (clave, nombre, color, icono). Cada persona
  puede crear además las suyas (`notebook_tags`).
- `offboarding`: qué pasa con los cuadernos de quien se da de baja
  (`transfer` a su responsable, `trash` a la papelera, `keep`); lo aplica
  `app/db/cuaderno_baja.py`.
- `trash_days`: días en la papelera antes de borrarse (salvo bloqueo legal).
- `ai_enabled`: ofrecer la IA (resumir, extraer tareas, ordenar ideas). Además
  manda el interruptor del módulo `notebook` en Gobierno de IA.
- `voice_enabled`: grabar y transcribir con la transcripción de la empresa.
- `sharing`: a quién se puede compartir (`users`, `teams`, `departments`).
"""
from __future__ import annotations

import copy
import json
import logging
import re
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.codigos_de_error import error

logger = logging.getLogger(__name__)

CLAVE = "cuaderno.config"
POLITICAS_DE_BAJA = ("transfer", "trash", "keep")
COLORES = ("blue", "green", "amber", "red", "purple", "teal", "pink", "gray")
ICONOS = ("circle-dot", "star", "help-circle", "lightbulb", "phone", "flag", "bookmark", "alert-triangle",
          "check-circle", "calendar", "mail", "user")
_CLAVE_DE_ETIQUETA = re.compile(r"^[a-z][a-z0-9_]{0,39}$")

#: Etiquetas de fábrica (los nombres se traducen en la pantalla por su clave: `cuaderno.tag_<clave>`).
ETIQUETAS_DE_FABRICA: list[dict] = [
    {"key": "todo", "label": "Pendiente", "color": "blue", "icon": "circle-dot"},
    {"key": "important", "label": "Importante", "color": "amber", "icon": "star"},
    {"key": "question", "label": "Pregunta", "color": "purple", "icon": "help-circle"},
    {"key": "idea", "label": "Idea", "color": "green", "icon": "lightbulb"},
    {"key": "call", "label": "Llamar a…", "color": "teal", "icon": "phone"},
    {"key": "critical", "label": "Crítico", "color": "red", "icon": "alert-triangle"},
]

POR_DEFECTO: dict[str, Any] = {
    "tags": ETIQUETAS_DE_FABRICA,
    "offboarding": "transfer",
    "trash_days": 30,
    "ai_enabled": True,
    "voice_enabled": True,
    "sharing": {"users": True, "teams": True, "departments": True},
}


def _fila(db: Session, org: Optional[str]):
    from app.models.settings import AppSetting
    q = db.query(AppSetting).filter(AppSetting.key == CLAVE)
    q = q.filter(AppSetting.organization_id == org) if org else q.filter(AppSetting.organization_id.is_(None))
    return q.first()


def leer(db: Session, org: Optional[str]) -> dict:
    """La configuración de la empresa sobre los valores de fábrica."""
    cfg = copy.deepcopy(POR_DEFECTO)
    fila = _fila(db, org)
    if fila is not None and fila.value:
        try:
            guardado = json.loads(fila.value) or {}
        except ValueError:
            logger.warning("cuaderno.config ilegible en la empresa %s", org)
            guardado = {}
        for k, v in guardado.items():
            if k in cfg and isinstance(cfg[k], dict) and isinstance(v, dict):
                cfg[k].update(v)
            elif k in cfg:
                cfg[k] = v
    return cfg


def _etiquetas(valor) -> list[dict]:
    if not isinstance(valor, list) or len(valor) > 40:
        raise error(422, "cuaderno_config_no_valida", campo="tags")
    salida, vistas = [], set()
    for e in valor:
        if not isinstance(e, dict):
            raise error(422, "cuaderno_config_no_valida", campo="tags")
        clave = str(e.get("key") or "").strip().lower()
        if not _CLAVE_DE_ETIQUETA.match(clave) or clave in vistas:
            raise error(422, "cuaderno_etiqueta_no_valida", clave=clave)
        vistas.add(clave)
        salida.append({"key": clave, "label": str(e.get("label") or clave).strip()[:80],
                       "color": e.get("color") if e.get("color") in COLORES else "gray",
                       "icon": e.get("icon") if e.get("icon") in ICONOS else "circle-dot"})
    return salida


def validar(datos: dict) -> dict:
    """Solo las claves conocidas, con su tipo y sus límites."""
    if not isinstance(datos, dict):
        raise error(422, "cuaderno_config_no_valida", campo="*")
    limpio: dict = {}
    if "tags" in datos:
        limpio["tags"] = _etiquetas(datos["tags"])
    if "offboarding" in datos:
        if datos["offboarding"] not in POLITICAS_DE_BAJA:
            raise error(422, "cuaderno_config_no_valida", campo="offboarding")
        limpio["offboarding"] = datos["offboarding"]
    if "trash_days" in datos:
        try:
            dias = int(datos["trash_days"])
        except (TypeError, ValueError):
            raise error(422, "cuaderno_config_no_valida", campo="trash_days")
        if not 1 <= dias <= 3650:
            raise error(422, "cuaderno_config_no_valida", campo="trash_days")
        limpio["trash_days"] = dias
    for campo in ("ai_enabled", "voice_enabled"):
        if campo in datos:
            limpio[campo] = bool(datos[campo])
    if "sharing" in datos:
        s = datos["sharing"] if isinstance(datos["sharing"], dict) else {}
        limpio["sharing"] = {k: bool(s.get(k, True)) for k in ("users", "teams", "departments")}
    return limpio


def guardar(db: Session, org: Optional[str], usuario, datos: dict) -> dict:
    """Guarda (auditado, antes y después). No confirma."""
    from app.models.settings import AppSetting
    from app.services.audit import audit_log
    antes = leer(db, org)
    nuevo = {**antes, **validar(datos)}
    fila = _fila(db, org)
    if fila is None:
        fila = AppSetting(key=CLAVE, organization_id=org, description="Mi cuaderno (docs/CUADERNO.md)")
        db.add(fila)
    fila.value = json.dumps(nuevo, ensure_ascii=False)
    audit_log(db, usuario, "UPDATE", "notebook_config", org, CLAVE, old_values=antes, new_values=nuevo)
    return nuevo
