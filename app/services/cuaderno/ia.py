"""IA opcional de «Mi cuaderno»: resumir la página, extraer tareas y ordenar ideas.

Pasa por la puerta común de la IA (`ai_modules._base.call_ai_unified`):
proveedor y modelo de la empresa (ruta del módulo `notebook` en Gobierno de
IA), guardarraíles, registro de uso y tope de gasto. Antes de llamar se
comprueba el interruptor y el tope diario del módulo (`modulos_ia.comprobar_modulo`)
y la configuración del cuaderno (`ai_enabled`). Solo se manda el texto de la
página que la persona puede leer (nunca otras páginas) y la respuesta no se
guarda sola: la pantalla la inserta si la persona quiere.
"""
from __future__ import annotations
import logging

import json
import time

from sqlalchemy.orm import Session

from app.core.codigos_de_error import error
from app.services.cuaderno import acceso
from app.services.cuaderno.acceso import LEER

MODULO = "notebook"
ACCIONES = ("summarize", "extract_tasks", "organize")

_SISTEMA = {
    "summarize": "Resumes notas de trabajo en 3-7 viñetas claras y fieles. No inventes nada que no esté en la nota.",
    "extract_tasks": ("Extraes de una nota las tareas accionables. Responde SOLO un JSON: "
                      '{"tasks": [{"text": "...", "due_date": "AAAA-MM-DD o null"}]}. Sin tareas: {"tasks": []}.'),
    "organize": ("Ordenas las ideas de una nota por temas: títulos cortos y viñetas debajo. Conserva todas las "
                 "ideas, sin añadir ninguna. Responde en Markdown sencillo (## y -)."),
}


def ejecutar(db: Session, usuario, page_id: str, accion: str) -> dict:
    from app.core.modulos_ia import comprobar_modulo
    from app.services.ai_modules._base import _parse_llm_json, call_ai_unified, log_action
    from app.services.cuaderno import config
    from app.services.formato_regional import instruccion_de_idioma_para
    if accion not in ACCIONES:
        raise error(422, "cuaderno_ia_accion_no_valida")
    org = getattr(usuario, "organization_id", None)
    if not config.leer(db, org).get("ai_enabled", True):
        raise error(403, "cuaderno_ia_desactivada")
    comprobar_modulo(db, org, MODULO, usuario.id)
    p, _ = acceso.pagina(db, usuario, page_id, LEER)
    texto = (p.content_text or "").strip()
    if not texto:
        raise error(422, "cuaderno_pagina_vacia")
    sistema = _SISTEMA[accion] + " " + instruccion_de_idioma_para(db, user_id=usuario.id, org_id=org)
    contenido = f"Título: {p.title or '—'}\n\nNota:\n{texto[:24000]}"
    t0 = time.time()
    try:
        respuesta = call_ai_unified(db, [{"role": "user", "content": contenido}], system=sistema, module=MODULO,
                                    user_id=usuario.id, organization_id=org)
    except Exception:  # noqa: BLE001 - proveedor caído o bloqueado por guardarraíles
        raise error(503, "ia_no_disponible")
    try:
        log_action(db, usuario.id, MODULO, accion, input_s=f"page:{p.id}", output_s=f"{len(respuesta)} chars",
                   latency=int((time.time() - t0) * 1000))
    except Exception:  # noqa: BLE001 - el registro no impide la respuesta
        logging.getLogger(__name__).debug("ejecutar: excepcion ignorada", exc_info=True)
    if accion == "extract_tasks":
        try:
            datos = _parse_llm_json(respuesta) or {}
        except (ValueError, json.JSONDecodeError):
            datos = {}
        tareas = [{"text": str(t.get("text") or "").strip()[:500], "due_date": t.get("due_date") or None}
                  for t in (datos.get("tasks") or []) if isinstance(t, dict) and str(t.get("text") or "").strip()]
        return {"action": accion, "tasks": tareas[:50], "text": None}
    return {"action": accion, "text": respuesta.strip()[:20000], "tasks": []}
