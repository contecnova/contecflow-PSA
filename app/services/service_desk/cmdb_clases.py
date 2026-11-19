"""Los datos propios de cada clase de CI, configurables por organizacion.

Auditoria 2026-11: estaban fijos en la pantalla (`CI_TYPE_FIELDS` de
`CMDBPage.tsx`). Ahora viven en `sd_ci_class_fields`. Una organizacion sin
ninguna fila usa los de fabrica de abajo, y la respuesta lo dice
(`por_defecto`); al guardar la primera clase se copian todos, asi que desde
entonces manda la tabla y los de fabrica no tapan nada.
"""
from __future__ import annotations

import re
from typing import Optional

from sqlalchemy.orm import Session

from app.models.service_desk import CIClassField, CIType
from app.core.codigos_de_error import error

TIPOS_DE_CAMPO = ("text", "number", "date")
CLAVE = re.compile(r"^[a-z][a-z0-9_]{0,49}$")

#: (clave, tipo). La etiqueta de fabrica es la traduccion `cmdb.f_<clave>`.
DE_FABRICA: dict[str, list[tuple[str, str]]] = {
    "server":          [("os", "text"), ("cpu_cores", "number"), ("ram_gb", "number"), ("serial_number", "text"), ("location", "text")],
    "virtual_machine": [("os", "text"), ("cpu_cores", "number"), ("ram_gb", "number"), ("cluster", "text"), ("resource_id", "text")],
    "application":     [("url", "text"), ("tech_stack", "text"), ("repo_url", "text"), ("owner_team", "text"), ("sla_tier", "text")],
    "database":        [("db_engine", "text"), ("port", "text"), ("size_gb", "number"), ("backup_schedule", "text")],
    "network":         [("vendor", "text"), ("model", "text"), ("serial_number", "text"), ("location", "text")],
    "service":         [("url", "text"), ("sla_tier", "text"), ("owner_team", "text"), ("dependencies", "text")],
    "container":       [("image", "text"), ("cluster", "text"), ("namespace", "text"), ("replicas", "number")],
    "cloud":           [("cloud_provider", "text"), ("region", "text"), ("resource_id", "text"), ("instance_type", "text"), ("monthly_cost", "number")],
    "endpoint":        [("os", "text"), ("serial_number", "text"), ("assigned_to", "text"), ("warranty_date", "date")],
    "storage":         [("capacity_tb", "number"), ("used_tb", "number"), ("protocol", "text"), ("vendor", "text")],
    "module":          [("repo_url", "text"), ("owner_team", "text")],
    "integration":     [("url", "text"), ("owner_team", "text")],
    "other":           [("serial_number", "text"), ("location", "text")],
}


def _de_la_organizacion(db: Session, org_id: Optional[str]):
    return db.query(CIClassField).filter(CIClassField.organization_id == org_id)


def campos(db: Session, org_id: Optional[str]) -> dict:
    """`{"por_defecto": bool, "clases": {ci_type: [{key, label, field_type}]}}`."""
    filas = _de_la_organizacion(db, org_id).order_by(CIClassField.ci_type, CIClassField.sort_order).all()
    if not filas:
        return {"por_defecto": True, "clases": {
            t: [{"key": k, "label": None, "field_type": ft} for k, ft in lista]
            for t, lista in DE_FABRICA.items()}}
    clases: dict[str, list[dict]] = {t.value: [] for t in CIType}
    for f in filas:
        clases.setdefault(f.ci_type, []).append({"key": f.key, "label": f.label, "field_type": f.field_type})
    return {"por_defecto": False, "clases": clases}


def _validar(ci_type: str, lista: list[dict]) -> list[dict]:
    if ci_type not in {t.value for t in CIType}:
        raise error(422, "ci_clase_desconocida", clase=ci_type)
    vistas, limpias = set(), []
    for c in lista:
        clave = str(c.get("key") or "").strip()
        if not CLAVE.match(clave):
            raise error(422, "clave_no_valida", clave=clave)
        if clave in vistas:
            raise error(422, "clave_repetida", clave=clave)
        if clave in ("hostname", "ip_address", "version"):
            raise error(422, "ci_campo_comun", clave=clave)
        tipo = c.get("field_type") or "text"
        if tipo not in TIPOS_DE_CAMPO:
            raise error(422, "tipo_no_valido_valor", detail=f"Tipo de campo no válido: {tipo}", tipo=tipo)
        etiqueta = (c.get("label") or "").strip()[:100] or None
        vistas.add(clave)
        limpias.append({"key": clave, "label": etiqueta, "field_type": tipo})
    return limpias


def guardar_clase(db: Session, org_id: Optional[str], ci_type: str, lista: list[dict]) -> dict:
    """Sustituye los campos de una clase. La primera vez copia los de fabrica del resto."""
    limpias = _validar(ci_type, lista)
    if not _de_la_organizacion(db, org_id).first():
        for t, de_fabrica in DE_FABRICA.items():
            if t == ci_type:
                continue
            for i, (k, ft) in enumerate(de_fabrica):
                db.add(CIClassField(organization_id=org_id, ci_type=t, key=k, field_type=ft, sort_order=i))
    _de_la_organizacion(db, org_id).filter(CIClassField.ci_type == ci_type).delete(synchronize_session=False)
    for i, c in enumerate(limpias):
        db.add(CIClassField(organization_id=org_id, ci_type=ci_type, sort_order=i, **c))
    db.flush()
    return campos(db, org_id)
