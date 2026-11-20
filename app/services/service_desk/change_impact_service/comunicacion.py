"""Plan de comunicacion del cambio: audiencias, canales y avisos.

Parte de `app.services.service_desk.change_impact_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from app.models.service_desk import ITSMChangeRequest

from app.services.service_desk.change_impact_service.planes import _set_json_setting
from app.services.service_desk.change_impact_service.riesgo import (
    score_change_risk,
    suggest_maintenance_window,
)
from app.core.codigos_de_error import error
from app.services.service_desk.change_impact_service.textos import (
    con_textos,
    diferido,
    idioma_de,
    pintar_datos,
    riesgo_diferido,
    ventana_diferida,
)


# ══════════════════════════════════════════════════════════════════════════════
# Communications Plan — audiences, channels, timing
# ══════════════════════════════════════════════════════════════════════════════

_COMMS_AUDIENCES: dict[str, dict[str, list[str]]] = {
    # risk_label → {timing_bucket → [audience_dicts]}
    "low": {
        "pre_change": ["IT Operations Team"],
        "post_change": ["IT Operations Team"],
    },
    "medium": {
        "pre_change": ["IT Operations Team", "Service Desk", "Line Manager"],
        "post_change": ["IT Operations Team", "Service Desk"],
    },
    "high": {
        "pre_change": ["IT Operations Team", "Service Desk", "Line Manager", "End Users (affected services)"],
        "during_change": ["IT Operations Team", "Service Desk"],
        "post_change": ["IT Operations Team", "Service Desk", "Line Manager", "End Users (affected services)"],
    },
    "critical": {
        "pre_change": ["IT Operations Team", "Service Desk", "Line Manager", "End Users (affected services)", "Executive Team"],
        "during_change": ["IT Operations Team", "Service Desk", "Executive Team"],
        "post_change": ["IT Operations Team", "Service Desk", "Line Manager", "End Users (affected services)", "Executive Team"],
        "post_incident": ["Executive Team", "Key Stakeholders"],
    },
}

#: Público -> canal por defecto (clave `cambio.canal.<código>`). El público
#: sigue en inglés: es un código que la interfaz traduce (`sd_informes.publico`).
_CHANNEL_MAP: dict[str, str] = {
    "IT Operations Team": "ops",
    "Service Desk": "service_desk",
    "Line Manager": "correo",
    "End Users (affected services)": "usuarios",
    "Executive Team": "direccion",
    "Key Stakeholders": "correo",
    "NOC": "noc",
}


#: El plan de comunicación, declarado. Cada fila es un aviso:
#:
#:    (cuándo, horas antes, público, canal, aviso, responsable, condición)
#:
#: `condición` es `None` —siempre—, `"alto"` —riesgo alto o crítico— o
#: `"critico"`. `canal` a `None` significa «el canal por defecto de ese
#: público», que vive en `_CHANNEL_MAP`.
#:
#: 19-11-2026: asunto y mensaje son textos por clave
#: (`cambio.aviso.<aviso>.asunto|mensaje` en `textos_de_salida_itsm.py`), el
#: canal `cambio.canal.<canal>` y el responsable `cambio.rol.<rol>`: salen en el
#: idioma de quien lee el plan, no en castellano fijo.
#:
#: Auditoría 2026-09 (hallazgo 18): eran 260 líneas de llamadas a un ayudante
#: anidado con las condiciones repartidas entre ellas. Un plan de comunicación
#: **es** una tabla, y verla entera es lo que hace falta para revisarla con
#: quien la va a enviar: quién recibe qué, cuándo, y por qué canal.
#:
#: Las llaves dobles `{{...}}` de los mensajes son huecos que rellena quien
#: envía el aviso en el momento; las simples se sustituyen aquí.
_AVISOS_DEL_PLAN: tuple[tuple, ...] = (
    # ── Antes del cambio ─────────────────────────────────────────────────────
    ("T-7d", 168, "Executive Team", None, "t7d_direccion", "gestor", "critico"),
    ("T-72h", 72, "End Users (affected services)", None, "t72h_usuarios", "comunicacion", "critico"),
    ("T-48h", 48, "Service Desk", None, "t48h_service_desk", "gestor", "alto"),
    ("T-48h", 48, "Line Manager", None, "t48h_responsable", "gestor", "alto"),
    ("T-24h", 24, "IT Operations Team", None, "t24h_operaciones", "gestor", None),
    ("T-24h", 24, "End Users (affected services)", None, "t24h_usuarios", "comunicacion", "alto"),
    ("T-1h", 1, "IT Operations Team", "im_operaciones", "t1h_operaciones", "gestor", None),
    ("T-1h", 1, "Service Desk", "im_service_desk", "t1h_service_desk", "gestor", "alto"),

    # ── Durante el cambio ────────────────────────────────────────────────────
    ("change_start", 0, "IT Operations Team", "im_operaciones", "inicio_operaciones", "gestor", "alto"),
    ("change_midpoint", None, "Executive Team", None, "mitad_direccion", "gestor", "critico"),

    # ── Después del cambio ───────────────────────────────────────────────────
    ("post_change_success", None, "IT Operations Team", None, "exito_operaciones", "gestor", None),
    ("post_change_success", None, "End Users (affected services)", None, "exito_usuarios", "comunicacion", "alto"),
    ("post_change_failure_rollback", None, "IT Operations Team", "im_operaciones_urgente",
     "vuelta_operaciones", "gestor", None),
    ("post_change_failure_rollback", None, "End Users (affected services)", None,
     "vuelta_usuarios", "comunicacion", "alto"),
    ("post_pir", None, "Executive Team", None, "pir_direccion", "gestor", "critico"),
)


def _avisos_aplicables(ctx: dict, idioma: Optional[str] = None) -> list[dict]:
    """Los avisos de la tabla que aplican a este cambio, ya numerados y pintados en `idioma`."""
    avisos: list[dict] = []
    datos = {k: ctx[k] for k in ("number", "title", "ventana", "parada", "riesgo")}
    for cuando, horas, publico, canal, aviso, responsable, condicion in _AVISOS_DEL_PLAN:
        if condicion and not ctx[condicion]:
            continue
        avisos.append(con_textos({
            "id": len(avisos) + 1,
            "timing": cuando,
            "hours_before_change": horas,
            "audience": publico,
        }, idioma,
            channel=diferido(f"cambio.canal.{canal or _CHANNEL_MAP[publico]}"),
            subject=diferido(f"cambio.aviso.{aviso}.asunto", **datos),
            message_template=diferido(f"cambio.aviso.{aviso}.mensaje", **datos),
            responsible=diferido(f"cambio.rol.{responsable}"),
        ))
    return avisos


def generate_comms_plan(
    db: Session,
    change_id: str,
    current_user_id: Optional[str] = None,
    idioma: Optional[str] = None,
) -> dict:
    """Plan de comunicación con públicos, canales y momentos.

    Cubre el antes, el durante —sólo en riesgo alto o crítico— y el después.
    Las plantillas de mensaje se adaptan al nivel de riesgo. Se guarda en
    `AppSetting` para poder consultarlo luego. Sale en `idioma` (sin el, el de
    `current_user_id`); lo guardado lleva sus textos por clave (`textos.py`).
    """
    change = db.query(ITSMChangeRequest).filter(ITSMChangeRequest.id == change_id).first()
    if not change:
        raise error(404, "no_encontrado", detail=f"Change {change_id} not found", que="cambio")

    idioma = idioma_de(db, user_id=current_user_id, idioma=idioma)
    riesgo = score_change_risk(db, change)
    etiqueta = riesgo["risk_label"]
    ventana = suggest_maintenance_window(db, change, riesgo["ci_ids_expanded"])
    # La etiqueta (en ingles) es la que interpreta la interfaz; en los mensajes
    # la ventana va por clave, en el idioma de quien lee.
    ventana_texto = ventana.get("window_label")

    ctx = {
        "number": change.number,
        "title": change.title or "",
        "ventana": ventana_diferida(ventana),
        "parada": change.downtime_minutes or 0,
        "riesgo": riesgo_diferido(etiqueta),
        "alto": etiqueta in ("high", "critical"),
        "critico": etiqueta == "critical",
    }
    avisos = _avisos_aplicables(ctx, idioma)

    comms_plan = {
        "change_id": change_id,
        "change_number": change.number,
        "change_title": change.title,
        "risk_label": etiqueta,
        "suggested_window": ventana_texto,
        "total_notifications": len(avisos),
        "timeline_buckets": {
            "pre_change": [
                a for a in avisos
                if a["timing"].startswith("T-") or a["timing"] == "change_start"
            ],
            "during_change": [
                a for a in avisos if a["timing"] in ("change_start", "change_midpoint")
            ],
            "post_change": [a for a in avisos if a["timing"].startswith("post_")],
        },
        "notifications": avisos,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "generated_by": current_user_id,
    }

    _set_json_setting(db, f"sd.change.comms.{change_id}", comms_plan)
    db.commit()
    return pintar_datos(comms_plan, idioma)
