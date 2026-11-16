"""Ajustes en vivo de la traduccion (`TRANSLATION_*`, grupo `traduccion`).

Todos por empresa y en caliente (`settings_service.get_runtime_*`, cache de
60 s). Los valores por defecto viven en
`app/core/config_groups/traduccion_config.py`.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

#: Canales a los que se puede aplicar la traduccion (`TRANSLATION_CHANNELS`).
# `portal` (16-11-2026): contenido que escriben los operadores y lee el cliente
# del portal (avisos, paginas de la wiki del portal, catalogo de servicios).
CANALES = ("ticket", "email", "livechat", "whatsapp", "slack", "teams", "portal_assistant", "internal_chat",
           "kb", "editor", "portal")
#: Proveedores (`TRANSLATION_PROVIDER`).
PROVEEDORES = ("ai", "deepl", "azure")


def _ss():
    from app.services import settings_service
    return settings_service


def habilitada(db: Session, org_id: Optional[str]) -> bool:
    return bool(org_id) and bool(_ss().get_runtime_bool(db, "TRANSLATION_ENABLED", org_id))


def canales(db: Session, org_id: Optional[str]) -> set[str]:
    crudo = _ss().get_runtime_str(db, "TRANSLATION_CHANNELS", org_id) or ""
    return {c.strip().lower() for c in crudo.split(",") if c.strip().lower() in CANALES}


def habilitada_en(db: Session, org_id: Optional[str], canal: str) -> bool:
    return habilitada(db, org_id) and canal in canales(db, org_id)


def proveedor(db: Session, org_id: Optional[str]) -> str:
    p = (_ss().get_runtime_str(db, "TRANSLATION_PROVIDER", org_id) or "").strip().lower()
    return p if p in PROVEEDORES else PROVEEDORES[0]


def salida_automatica(db: Session, org_id: Optional[str]) -> bool:
    return bool(_ss().get_runtime_bool(db, "TRANSLATION_OUTBOUND_AUTO", org_id))


def incluir_original(db: Session, org_id: Optional[str]) -> bool:
    return bool(_ss().get_runtime_bool(db, "TRANSLATION_INCLUDE_ORIGINAL", org_id))


def confianza_minima(db: Session, org_id: Optional[str]) -> float:
    return float(_ss().get_runtime_float(db, "TRANSLATION_DETECT_MIN_CONFIDENCE", org_id) or 0)


def max_caracteres_por_lote(db: Session, org_id: Optional[str]) -> int:
    return max(1, int(_ss().get_runtime_int(db, "TRANSLATION_MAX_BATCH_CHARS", org_id) or 1))


def max_tokens_ia(db: Session, org_id: Optional[str]) -> int:
    return max(1, int(_ss().get_runtime_int(db, "TRANSLATION_AI_MAX_TOKENS", org_id) or 1))


def coste_por_millon(db: Session, org_id: Optional[str]) -> float:
    return max(0.0, float(_ss().get_runtime_float(db, "TRANSLATION_COST_PER_MILLION_CHARS_USD", org_id) or 0))


def dias_de_cache(db: Session, org_id: Optional[str]) -> int:
    return max(0, int(_ss().get_runtime_int(db, "TRANSLATION_CACHE_RETENTION_DAYS", org_id) or 0))


def idiomas_de_la_kb(db: Session, org_id: Optional[str]) -> list[str]:
    from app.services.traduccion.idiomas import IDIOMAS_DEL_PORTAL, normalizar
    crudo = _ss().get_runtime_str(db, "TRANSLATION_KB_LANGUAGES", org_id) or ""
    elegidos = [normalizar(c) for c in crudo.split(",") if c.strip()]
    elegidos = [c for c in elegidos if c in IDIOMAS_DEL_PORTAL]
    return list(dict.fromkeys(elegidos)) or list(IDIOMAS_DEL_PORTAL)


def idioma_por_defecto(db: Session, org_id: Optional[str]) -> str:
    """El idioma de la empresa (`DEFAULT_LANGUAGE`), normalizado; `es` si no hay."""
    from app.services.traduccion.idiomas import IDIOMAS_DE_OPERADOR, normalizar
    return normalizar(_ss().get_runtime_str(db, "DEFAULT_LANGUAGE", org_id)) or IDIOMAS_DE_OPERADOR[0]
