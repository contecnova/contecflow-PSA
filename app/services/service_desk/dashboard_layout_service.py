"""Panel del service desk personalizable.

Mejoras de mercado 16-11-2026: el panel tenia un «layout» por rol que guardaba
cualquier lista de nombres (sin pantalla, y muchos no existian) y lo podia
cambiar cualquier agente para toda la empresa. Ahora:

- Cada persona guarda **su** panel (por rol de vista); si no tiene, ve el de su
  empresa para ese rol y, si tampoco, el de serie.
- El de la empresa solo lo guarda un administrador (`scope=org`).
- Solo se aceptan widgets del catalogo (`WIDGETS`), que son los que la
  pantalla sabe pintar con datos reales; los nombres viejos se ignoran.
"""
from __future__ import annotations

import json
from typing import Optional

from sqlalchemy.orm import Session

from app.models.settings import AppSetting
import logging
from app.core.codigos_de_error import error

logger = logging.getLogger(__name__)

#: Widgets que la pantalla sabe pintar, y de donde sale cada uno.
WIDGETS = {
    "my_queue_prioritized": "/sd/tickets/my-queue/prioritized",
    "sla_risk": "/sd/predictive/stats",
    "major_incidents": "/sd/major-incidents",
    "itil_metrics": "/sd/metrics/itil",
    "agent_performance": "/sd/metrics/agent-performance",
    "autonomous_agent": "/sd/autonomous/stats",
    "cab_pending": "/sd/changes/cab-dashboard",
    "my_approvals": "/sd/approvals/mine",
}
#: Como mucho cuantos widgets en un panel.
MAX_WIDGETS = len(WIDGETS)

_DEFAULT_LAYOUTS = {
    "operation": {"widgets": ["my_queue_prioritized", "sla_risk", "major_incidents", "my_approvals"]},
    "manager": {"widgets": ["itil_metrics", "agent_performance", "sla_risk", "cab_pending"]},
    "executive": {"widgets": ["itil_metrics", "major_incidents", "autonomous_agent", "cab_pending"]},
}


def _key(role: str, user_id: Optional[str] = None) -> str:
    if user_id:
        return f"service_desk.dashboard_layout.user.{user_id}.{role}"
    return f"service_desk.dashboard_layout.{role}"


def _leer(db: Session, organization_id: Optional[str], clave: str) -> Optional[dict]:
    fila = (db.query(AppSetting)
            .filter(AppSetting.organization_id == organization_id, AppSetting.key == clave).first())
    if not fila or not fila.value:
        return None
    try:
        valor = json.loads(fila.value)
    except ValueError:
        logger.debug("layout ilegible: %s", clave, exc_info=True)
        return None
    widgets = [w for w in (valor or {}).get("widgets", []) if w in WIDGETS]
    return {"widgets": widgets} if widgets else None


def get_layout(db: Session, organization_id: Optional[str], role: str, user_id: Optional[str] = None) -> dict:
    """El panel de la persona; si no, el de la empresa; si no, el de serie. Con `origin`."""
    if user_id:
        propio = _leer(db, organization_id, _key(role, user_id))
        if propio:
            return {**propio, "origin": "user"}
    empresa = _leer(db, organization_id, _key(role))
    if empresa:
        return {**empresa, "origin": "org"}
    return {**_DEFAULT_LAYOUTS.get(role, _DEFAULT_LAYOUTS["operation"]), "origin": "default"}


def save_layout(db: Session, organization_id: Optional[str], role: str, layout: dict,
                user_id: Optional[str] = None) -> dict:
    """Guarda el panel de la persona (`user_id`) o, sin el, el de la empresa."""
    widgets = (layout or {}).get("widgets")
    if not isinstance(widgets, list) or not widgets:
        raise error(422, "panel_sin_widgets")
    desconocidos = [w for w in widgets if w not in WIDGETS]
    if desconocidos:
        raise error(422, "widgets_desconocidos", widgets=', '.join(map(str, desconocidos)))
    limpio = {"widgets": list(dict.fromkeys(widgets))[:MAX_WIDGETS]}
    clave = _key(role, user_id)
    setting = (db.query(AppSetting)
               .filter(AppSetting.organization_id == organization_id, AppSetting.key == clave).first())
    if setting is None:
        db.add(AppSetting(organization_id=organization_id, key=clave, value=json.dumps(limpio),
                          description=f"Service Desk dashboard layout ({'user' if user_id else 'org'}, {role})"))
    else:
        setting.value = json.dumps(limpio)
    db.commit()
    return {**limpio, "origin": "user" if user_id else "org"}


def reset_layout(db: Session, organization_id: Optional[str], role: str, user_id: str) -> dict:
    """La persona vuelve al panel de su empresa (borra el suyo)."""
    db.query(AppSetting).filter(AppSetting.organization_id == organization_id,
                                AppSetting.key == _key(role, user_id)).delete()
    db.commit()
    return get_layout(db, organization_id, role, user_id)
