"""Configuración del asistente de reuniones por empresa (`app_settings`, clave `reuniones.config`).

Mismo patrón que `bi_o365_service`: un JSON por empresa; los secretos se
guardan cifrados (`encrypt_value`) y la API solo dice si están puestos
(`*_set`). Todo nace apagado: ningún conector ni proveedor externo recibe
nada hasta que la empresa lo activa, y el bot (encargado de tratamiento) y
la transcripción externa exigen además la referencia del contrato.
"""
from __future__ import annotations

import copy
import json
import logging
import secrets
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.codigos_de_error import ErrorConCodigo

logger = logging.getLogger(__name__)

CLAVE = "reuniones.config"
MAX_DIAS = 3650
PROVEEDORES_DE_BOTS = ("recall",)
REGIONES_RECALL = ("us-east-1", "us-west-2", "eu-central-1", "ap-northeast-1")
STT_LOCALES = ("whisper_local",)

#: Secretos por bloque: (bloque, campo). Nunca salen por la API.
SECRETOS: tuple[tuple[str, str], ...] = (
    ("teams", "client_secret"), ("teams", "client_state"),
    ("zoom", "client_secret"), ("zoom", "webhook_secret"),
    ("meet", "service_account_key"),
    ("bots", "api_key"), ("bots", "webhook_secret"),
)

POR_DEFECTO: dict[str, dict[str, Any]] = {
    "consent": {"notice_required": True, "require_consent": False,
                "notice_text": "", "bot_message": ""},
    "retention": {"audio_days": 7, "transcript_days": 365},
    "translation": {"per_person": True},
    "linking": {"auto": True},
    "transcription": {"allow_external_stt": False, "external_stt_contract": ""},
    "teams": {"enabled": False, "tenant_id": "", "client_id": "", "mode": "polling",
              "subscription_id": None, "subscription_expires_at": None},
    "zoom": {"enabled": False, "account_id": "", "client_id": ""},
    "meet": {"enabled": False, "service_account_email": ""},
    # 19-11-2026: el bot invitado viene ACTIVADO por defecto (decisión del usuario).
    # Activado no es «enviando datos»: invitarlo sigue exigiendo la referencia del
    # contrato de encargado (RGPD art. 28) y la clave del proveedor (`bots.proveedor`).
    "bots": {"enabled": True, "provider": "recall", "region": "eu-central-1", "bot_name": "",
             "contract_reference": "", "contract_accepted_by": None, "contract_accepted_at": None},
}

#: Textos por defecto (castellano; la pantalla los ofrece editables).
AVISO_POR_DEFECTO = ("Esta reunión se graba y se transcribe para generar el acta y las tareas. "
                     "Si no estás de acuerdo, dilo ahora.")


def _fila(db: Session, org: Optional[str]):
    from app.models.settings import AppSetting
    q = db.query(AppSetting).filter(AppSetting.key == CLAVE)
    q = q.filter(AppSetting.organization_id == org) if org else q.filter(AppSetting.organization_id.is_(None))
    return q.first()


def _crudo(db: Session, org: Optional[str]) -> dict:
    fila = _fila(db, org)
    guardado: dict = {}
    if fila is not None and fila.value:
        try:
            guardado = json.loads(fila.value) or {}
        except ValueError:
            logger.warning("reuniones.config ilegible en la empresa %s", org)
    cfg = copy.deepcopy(POR_DEFECTO)
    for bloque, valores in guardado.items():
        if isinstance(valores, dict):
            cfg.setdefault(bloque, {}).update(valores)
    return cfg


def secreto(db: Session, org: Optional[str], bloque: str, campo: str) -> str:
    """El secreto descifrado (o '')."""
    valor = (_crudo(db, org).get(bloque) or {}).get(campo)
    if not valor:
        return ""
    from app.core.encryption import decrypt_value
    return decrypt_value(valor) or ""


def leer(db: Session, org: Optional[str]) -> dict:
    """La configuración efectiva SIN secretos (para el código y la API)."""
    cfg = _crudo(db, org)
    for bloque, campo in SECRETOS:
        b = cfg.setdefault(bloque, {})
        b[f"{campo}_set"] = bool(b.pop(campo, None))
    return cfg


def _url_base() -> str:
    from app.core.config import settings
    return (getattr(settings, "PUBLIC_API_URL", None) or getattr(settings, "BACKEND_URL", None)
            or getattr(settings, "FRONTEND_URL", None) or "").rstrip("/")


def url_de_webhook(proveedor: str, org: Optional[str]) -> str:
    return f"{_url_base()}/api/v1/webhooks/meetings/{proveedor}/{org or ''}"


def para_la_api(db: Session, org: Optional[str]) -> dict:
    """Lo que ve la pantalla de Configuración: sin secretos, con las URL y los STT."""
    cfg = leer(db, org)
    cfg["teams"]["webhook_url"] = url_de_webhook("teams", org)
    cfg["zoom"]["webhook_url"] = url_de_webhook("zoom", org)
    cfg["bots"]["webhook_url"] = url_de_webhook("recall", org)
    cfg["bots"]["providers"] = list(PROVEEDORES_DE_BOTS)
    from app.services.reuniones.transcripcion import proveedores_permitidos, proveedores_configurados
    cfg["transcription"]["stt_providers"] = proveedores_configurados(db, org)
    permitidos = proveedores_permitidos(db, org)
    cfg["transcription"]["stt_effective"] = permitidos[0] if permitidos else None
    return cfg


def _entero(valor, campo: str) -> int:
    try:
        n = int(valor)
    except (TypeError, ValueError):
        raise ErrorConCodigo("reuniones_retencion_no_valida", max=MAX_DIAS, detail=f"{campo}: número de días")
    if n < 1 or n > MAX_DIAS:
        raise ErrorConCodigo("reuniones_retencion_no_valida", max=MAX_DIAS)
    return n


def guardar(db: Session, org: Optional[str], cambios: dict, usuario) -> dict:
    """Aplica `cambios` (parcial, anidado). Secretos vacíos = no cambian. No confirma."""
    from app.core.encryption import encrypt_value
    from app.models.settings import AppSetting

    cfg = _crudo(db, org)
    solo_lectura = {"webhook_url", "providers", "stt_providers", "stt_effective", "contract_accepted_by",
                    "contract_accepted_at", "subscription_id", "subscription_expires_at"}
    for bloque, valores in (cambios or {}).items():
        if bloque not in POR_DEFECTO or not isinstance(valores, dict):
            continue
        destino = cfg.setdefault(bloque, {})
        for campo, valor in valores.items():
            if campo in solo_lectura or campo.endswith("_set"):
                continue
            if (bloque, campo) in SECRETOS:
                texto = (valor or "").strip() if isinstance(valor, str) else ""
                if texto:
                    destino[campo] = encrypt_value(texto)
                continue
            if campo not in POR_DEFECTO[bloque]:
                continue
            destino[campo] = valor

    # Validación.
    cfg["retention"]["audio_days"] = _entero(cfg["retention"]["audio_days"], "audio_days")
    cfg["retention"]["transcript_days"] = _entero(cfg["retention"]["transcript_days"], "transcript_days")
    if cfg["teams"].get("mode") not in ("polling", "subscription"):
        raise ErrorConCodigo("reuniones_formato_no_valido", detail="teams.mode: polling | subscription")
    if cfg["bots"].get("provider") not in PROVEEDORES_DE_BOTS:
        raise ErrorConCodigo("reuniones_formato_no_valido", detail="bots.provider")
    if cfg["bots"].get("region") not in REGIONES_RECALL:
        raise ErrorConCodigo("reuniones_formato_no_valido", detail="bots.region")
    for bloque in ("consent", "translation", "linking", "transcription", "teams", "zoom", "meet", "bots"):
        for campo in ("notice_required", "require_consent", "per_person", "auto", "allow_external_stt", "enabled"):
            if campo in cfg[bloque]:
                cfg[bloque][campo] = bool(cfg[bloque][campo])
    # Ningún tercero sin contrato (RGPD art. 28).
    bots = cfg["bots"]
    bots["contract_reference"] = (bots.get("contract_reference") or "").strip()
    # Activado sin contrato se puede guardar (es el valor por defecto); lo que no se
    # puede es INVITAR el bot sin contrato: lo impide `bots.proveedor` al usarlo y el
    # informe de cumplimiento lo señala.
    if bots["enabled"] and bots["contract_reference"] and not bots.get("contract_accepted_at"):
        bots["contract_accepted_by"] = getattr(usuario, "id", None)
        bots["contract_accepted_at"] = datetime.now(timezone.utc).isoformat()
    if not bots["contract_reference"]:
        bots["contract_accepted_by"] = bots["contract_accepted_at"] = None
    tr = cfg["transcription"]
    tr["external_stt_contract"] = (tr.get("external_stt_contract") or "").strip()
    if tr["allow_external_stt"] and not tr["external_stt_contract"]:
        raise ErrorConCodigo("reuniones_proveedor_sin_contrato")
    # El `clientState` de Graph lo genera el servidor si no hay.
    if cfg["teams"]["enabled"] and not cfg["teams"].get("client_state"):
        cfg["teams"]["client_state"] = encrypt_value(secrets.token_urlsafe(32))

    fila = _fila(db, org)
    valor = json.dumps(cfg, ensure_ascii=False, default=str)
    if fila is None:
        db.add(AppSetting(key=CLAVE, organization_id=org, value=valor,
                          description="Asistente de reuniones: conectores, bot, consentimiento y retención"))
    else:
        fila.value = valor
    db.flush()
    return para_la_api(db, org)


def guardar_campo_interno(db: Session, org: Optional[str], bloque: str, valores: dict) -> None:
    """Para el propio código (id de la suscripción de Graph...). No confirma."""
    from app.models.settings import AppSetting
    cfg = _crudo(db, org)
    cfg.setdefault(bloque, {}).update(valores)
    fila = _fila(db, org)
    valor = json.dumps(cfg, ensure_ascii=False, default=str)
    if fila is None:
        db.add(AppSetting(key=CLAVE, organization_id=org, value=valor))
    else:
        fila.value = valor
    db.flush()


def texto_del_aviso(cfg: dict) -> str:
    return (cfg["consent"].get("notice_text") or "").strip() or AVISO_POR_DEFECTO


def mensaje_del_bot(cfg: dict) -> str:
    return (cfg["consent"].get("bot_message") or "").strip() or texto_del_aviso(cfg)
