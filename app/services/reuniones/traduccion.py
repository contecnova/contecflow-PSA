"""La reunión en el idioma de quien la mira (canal de traducción `meetings`).

Traduce de una vez resumen, decisiones, riesgos, preguntas, acciones y
segmentos con `traduccion.servicio.traducir` (caché, glosario, tope de gasto)
y guarda el resultado en `ai_meeting_translations` (una fila por idioma; se
borra al reanalizar). Si la empresa no traduce o no tiene el canal activado,
se devuelve el original y el motivo.
"""
from __future__ import annotations

import json
from typing import Optional

from sqlalchemy.orm import Session


def _sin(language: str, estado: str, motivo: Optional[str]) -> dict:
    return {"language": language, "translation": {"status": estado, "reason": motivo}}


def traducir_reunion(db: Session, reunion, idioma: Optional[str], usuario=None) -> Optional[dict]:
    """El bloque traducido para `consultas.detalle`, o None si no hace falta."""
    from app.models.reuniones import AIMeetingTranslation
    from app.services.reuniones.config import leer
    from app.services.reuniones.consultas import _json, consentimiento_completo
    from app.services.traduccion.idiomas import normalizar

    destino = normalizar(idioma) if idioma else None
    if not destino or not reunion.original_language or destino == normalizar(reunion.original_language):
        return None
    if not leer(db, reunion.organization_id)["translation"]["per_person"]:
        return _sin(reunion.original_language, "disabled", "per_person_disabled")
    if reunion.consent_required and not consentimiento_completo(reunion):
        return _sin(reunion.original_language, "unavailable", "consent_pending")
    guardada = next((t for t in reunion.traducciones if t.language == destino), None)
    if guardada is not None:
        datos = _json(guardada.contenido, {})
        datos.update({"language": destino, "translation": {"status": "translated", "reason": None}})
        return datos

    decisiones, riesgos, preguntas = _json(reunion.decisions), _json(reunion.risks_mentioned), _json(reunion.open_questions)
    textos: list[str] = [reunion.summary or ""] + decisiones + riesgos + preguntas
    textos += [a.description for a in reunion.actions] + [s.text for s in reunion.segmentos]
    from app.services.traduccion.servicio import DESACTIVADA, NO_DISPONIBLE, traducir
    resultados = traducir(db, reunion.organization_id, textos, destino, canal="meetings",
                          origen=reunion.original_language, user_id=getattr(usuario, "id", None))
    if any(r.estado == DESACTIVADA for r in resultados):
        motivo = next(r.motivo for r in resultados if r.estado == DESACTIVADA)
        return _sin(reunion.original_language, "disabled",
                    "channel_disabled" if motivo == "channel_disabled" else "translation_disabled")
    fallidos = [r for r in resultados if r.estado == NO_DISPONIBLE]
    if fallidos:
        motivo = "budget_exceeded" if fallidos[0].motivo == "budget_exhausted" else "provider_error"
        return _sin(reunion.original_language, "unavailable", motivo)
    salida = [r.texto or "" for r in resultados]
    i = 0
    resumen = salida[i]; i += 1  # noqa: E702
    d = salida[i:i + len(decisiones)]; i += len(decisiones)  # noqa: E702
    r_ = salida[i:i + len(riesgos)]; i += len(riesgos)  # noqa: E702
    p = salida[i:i + len(preguntas)]; i += len(preguntas)  # noqa: E702
    acciones = [{"id": a.id, "description": salida[i + k]} for k, a in enumerate(reunion.actions)]
    i += len(reunion.actions)
    segmentos = [{"id": s.id, "text": salida[i + k]} for k, s in enumerate(reunion.segmentos)]
    contenido = {"summary": resumen or reunion.summary, "decisions": d, "risks": r_, "open_questions": p,
                 "actions": acciones, "segments": segmentos}
    reunion.traducciones.append(AIMeetingTranslation(
        organization_id=reunion.organization_id, language=destino,
        contenido=json.dumps(contenido, ensure_ascii=False),
        provider=next((x.proveedor for x in resultados if x.proveedor), None)))
    from app.services.reuniones.eventos import evento
    evento(db, reunion, "translated", usuario, {"language": destino})
    db.flush()
    contenido.update({"language": destino, "translation": {"status": "translated", "reason": None}})
    return contenido
