"""Proveedor y modelo por funcion (`MODULOS_DE_IA` y sus rutas por empresa).

Parte de `app.services.ai_provider_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

# Funciones de la aplicacion que llaman a la IA (el `module` de `call_ai`).
MODULOS_DE_IA = {
    "nexusassist": "Asistente (NexusAssist) y editor en línea",
    "nexusagent": "Agente (NexusAgent)",
    "ai_planning": "Planificación y estimación",
    "smart_schedule": "Planificación inteligente de tareas",
    "service_desk": "Service Desk: borradores de respuesta",
    "auto_resolution": "Service Desk: autorresolución",
    "change_management": "Gestión de cambios",
    "knowledge_base": "Base de conocimiento",
    "document_summary": "Resumen de documentos",
    "contract_intelligence": "Contratos",
    "meeting_assistant": "Reuniones",
    "bi_storytelling": "Narrativa de BI",
    "ask_the_data": "Preguntas sobre los datos (SQL)",
    "semantic_assign": "Asignación semántica (desempate)",
    "client_portal": "Chat del portal de cliente",
    "voice": "Comandos de voz",
    "v16": "Módulos de IA (RCA, KB, previsiones)",
    "lessons_learned": "Lecciones aprendidas: borrador desde los hechos",
}
_CLAVE_RUTAS = "ai_routing"


def rutas_por_modulo(db: Session, organization_id) -> dict:
    """{modulo: {"provider_id", "model"}} de la empresa (o las globales)."""
    from app.models.settings import AppSetting
    fila = None
    if organization_id:
        fila = db.query(AppSetting).filter(AppSetting.key == _CLAVE_RUTAS,
                                           AppSetting.organization_id == organization_id).first()
    if fila is None:
        fila = db.query(AppSetting).filter(AppSetting.key == _CLAVE_RUTAS,
                                           AppSetting.organization_id.is_(None)).first()
    try:
        datos = json.loads(fila.value) if fila and fila.value else {}
    except ValueError:
        datos = {}
    return {k: v for k, v in datos.items() if k in MODULOS_DE_IA and isinstance(v, dict)}


def guardar_rutas(db: Session, organization_id, rutas: dict) -> dict:
    from app.models.settings import AppSetting
    limpias = {k: {"provider_id": v.get("provider_id") or None, "model": (v.get("model") or "").strip() or None}
               for k, v in (rutas or {}).items() if k in MODULOS_DE_IA and (v.get("provider_id") or v.get("model"))}
    fila = db.query(AppSetting).filter(AppSetting.key == _CLAVE_RUTAS,
                                       AppSetting.organization_id == organization_id).first()
    if fila is None:
        fila = AppSetting(key=_CLAVE_RUTAS, organization_id=organization_id,
                          description="IA: proveedor y modelo por funcion")
        db.add(fila)
    fila.value = json.dumps(limpias)
    db.commit()
    return limpias
