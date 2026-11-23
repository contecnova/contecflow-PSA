"""Avisos entrantes (sin sesión): Recall.ai, Zoom y Microsoft Graph.

La empresa va en la ruta (`/webhooks/meetings/{proveedor}/{empresa}`) y el
aviso se verifica con el secreto de ESA empresa; sin secreto configurado o con
firma mala, 403 y no se toca nada. Se procesa con el contexto de la empresa
publicado (`como_organizacion`): filtro de tenant y sellado como en una petición.
"""
from __future__ import annotations

import hmac
import json
import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.core.codigos_de_error import error
from app.services.reuniones import config

logger = logging.getLogger(__name__)


def _empresa(db: Session, org: str) -> str:
    from app.db.session import sin_filtro_de_tenant
    from app.models.mfa import Organization
    with sin_filtro_de_tenant(db):
        o = db.get(Organization, org)
    if o is None or not o.is_active:
        raise error(404, "no_encontrado", que="empresa", detail="Empresa no encontrada")
    return o.id


def _contexto(db: Session, org: str):
    from app.services.service_desk.ticket_events import como_organizacion
    return como_organizacion(db, org)


def _json(cuerpo: bytes) -> dict:
    try:
        return json.loads(cuerpo or b"{}")
    except ValueError:
        raise error(400, "json_no_valido", detail="Invalid JSON payload")


def recall(db: Session, org: str, cabeceras: dict, cuerpo: bytes) -> dict:
    from app.services.reuniones.bots import proveedor
    from app.services.reuniones.servicio import procesar_evento_de_bot
    org = _empresa(db, org)
    with _contexto(db, org):
        secreto = config.secreto(db, org, "bots", "webhook_secret")
        try:
            bots = proveedor(db, org, exigir_activo=False)
        except Exception:  # noqa: BLE001 - sin clave de API aún se puede verificar la firma
            logger.debug("recall: excepcion ignorada", exc_info=True)
            from app.services.reuniones.bots import RecallBots
            bots = RecallBots("", config.leer(db, org)["bots"]["region"])
        if not secreto or not bots.verificar_firma(cabeceras, cuerpo, secreto):
            raise error(403, "reuniones_firma_no_valida")
        ev = bots.interpretar_evento(_json(cuerpo))
        if ev is not None:
            procesar_evento_de_bot(db, org, ev)
            db.commit()
    return {"status": "ok"}


def zoom(db: Session, org: str, cabeceras: dict, cuerpo: bytes) -> dict:
    from app.services.reuniones.conectores import zoom as z
    from app.services.reuniones.servicio import guardar_importada
    org = _empresa(db, org)
    h = {k.lower(): v for k, v in cabeceras.items()}
    with _contexto(db, org):
        secreto = config.secreto(db, org, "zoom", "webhook_secret")
        if not secreto or not z.firma_valida(secreto, h.get("x-zm-request-timestamp", ""),
                                             h.get("x-zm-signature", ""), cuerpo):
            raise error(403, "reuniones_firma_no_valida")
        carga = _json(cuerpo)
        evento = carga.get("event")
        if evento == "endpoint.url_validation":
            return z.respuesta_de_validacion(secreto, (carga.get("payload") or {}).get("plainToken", ""))
        if evento != "recording.completed":
            return {"status": "ignored"}
        if not config.leer(db, org)["zoom"]["enabled"]:
            return {"status": "disabled"}
        imp = z.de_grabacion(db, org, (carga.get("payload") or {}).get("object") or {},
                             download_token=carga.get("download_token"))
        if imp is not None:
            guardar_importada(db, org, imp)
            db.commit()
    return {"status": "ok"}


def teams(db: Session, org: str, token_de_validacion: Optional[str], cuerpo: bytes):
    """Devuelve el `validationToken` (texto) al dar de alta la suscripción, o `{"status"}`."""
    from app.services.reuniones.conectores import teams as t
    from app.services.reuniones.servicio import guardar_importada
    org = _empresa(db, org)
    if token_de_validacion:
        return token_de_validacion
    with _contexto(db, org):
        estado = config.secreto(db, org, "teams", "client_state")
        if not estado:
            raise error(403, "reuniones_firma_no_valida")
        avisos = _json(cuerpo).get("value") or []
        if any(not hmac.compare_digest(str(a.get("clientState") or ""), estado) for a in avisos):
            raise error(403, "reuniones_firma_no_valida")
        if not config.leer(db, org)["teams"]["enabled"]:
            return {"status": "disabled"}
        for aviso in avisos:
            try:
                imp = t.de_aviso(db, org, aviso)
            except Exception:  # noqa: BLE001 - un aviso malo no impide los demás
                logger.warning("reuniones: aviso de Teams no procesable", exc_info=True)
                continue
            if imp is not None:
                guardar_importada(db, org, imp)
        db.commit()
    return {"status": "ok"}
