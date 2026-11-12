"""BI Data Storytelling — generates executive narrative from OLAP KPIs.

Flow:
  1. Pull KPI context from OLAP (or PostgreSQL fallback)
  2. Check Redis cache (TTL 1h)
  3. Call AI provider (provider-agnostic: Claude, GPT-4, Gemini, etc.)
  4. Cache and return

Resolution order for AI provider:
  - Default configured provider for organization
  - Fallback to any available provider (if primary fails)
  - Error message if no providers available

Public API:
    generate_narrative(org_id, lang=None, user_id=None) -> dict

Auditoria 2026-11 (hallazgo 30): sin `lang`, el idioma es el del usuario / la
organizacion (`formato_regional.idioma`, `"es"` solo de ultimo respaldo), y los
importes van en la moneda de la organizacion, no en `€` fijo.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

STORYTELLING_PROMPT = """Eres el analista de negocio de una empresa de consultoría IT.
Tu trabajo es escribir un resumen ejecutivo conciso (máximo 5 párrafos) en {lang}
basándote exclusivamente en los siguientes KPIs del período actual.

No inventes datos. Si un valor es None o 0, indícalo como "sin datos".
Los importes están en {moneda} (símbolo «{simbolo}»).
Usa un tono profesional, orientado a decisiones. Incluye:
  1. Estado general del portfolio de proyectos
  2. Rendimiento financiero (costes, margen, facturabilidad)
  3. Pipeline comercial (oportunidades, revenue ponderado)
  4. Riesgos o alertas relevantes
  5. Recomendación ejecutiva de 1 frase

KPIs:
{kpis_json}
"""

_LANG_LABELS = {"es": "español", "en": "English", "ca": "català"}


def _to_number(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        logger.debug("Storytelling _to_number coercion failed for value=%r; using default", value, exc_info=True)
        return default


def _build_cache_key(org_id: Optional[str], lang: str) -> str:
    # Versioned key to invalidate stale narratives after KPI/LLM improvements.
    # v3 (revisión 2026-11): con el idioma, y fuera las narrativas cortadas a
    # media frase que guardó la v2.
    raw = f"bi_narrative:v3:{org_id or 'global'}:{lang}"
    return hashlib.md5(raw.encode()).hexdigest()  # noqa: S324


def _get_kpi_context(org_id: Optional[str]) -> dict:
    """Fetch KPIs from OLAP or PostgreSQL fallback."""
    try:
        from app.services.olap.query_engine import get_kpi_summary
        kpis = get_kpi_summary(org_id)
        return kpis
    except Exception as exc:
        logger.warning("OLAP KPI fetch failed, using minimal context: %s", exc)
        return {"source": "unavailable", "error": str(exc)}


def _regional(org_id: Optional[str], user_id: Optional[str], lang: Optional[str]) -> tuple[str, str, str]:
    """(idioma, codigo de moneda, simbolo) de la organizacion / el usuario."""
    from app.services.formato_regional import codigo_de_moneda, idioma, simbolo_de_moneda
    try:
        from app.db.session import SessionLocal
        db = SessionLocal()
    except Exception:
        logger.debug("_regional: sin sesion; ajustes globales", exc_info=True)
        db = None
    try:
        return (lang or idioma(db, user_id=user_id, org_id=org_id),
                codigo_de_moneda(db, org_id), simbolo_de_moneda(db, org_id))
    finally:
        if db is not None:
            db.close()


def generate_narrative(
    org_id: Optional[str] = None,
    lang: Optional[str] = None,
    force_refresh: bool = False,
    user_id: Optional[str] = None,
) -> dict:
    """Generate (or return cached) executive narrative for the given org.

    Returns:
        {
            "narrative": "...",
            "kpis": {...},
            "lang": "es",
            "cached": True/False,
            "source": "olap" | "postgresql" | "unavailable"
        }
    """
    from app.services.analytics_service import cache_get, cache_set

    lang, moneda, simbolo = _regional(org_id, user_id, lang)
    cache_key = _build_cache_key(org_id, lang)

    if not force_refresh:
        cached = cache_get(cache_key)
        if cached:
            logger.debug("Storytelling cache hit for org=%s", org_id)
            return {**cached, "cached": True}

    kpis = _get_kpi_context(org_id)

    # Build prompt
    lang_label = _LANG_LABELS.get(lang, lang)
    prompt_text = STORYTELLING_PROMPT.format(
        lang=lang_label,
        moneda=moneda,
        simbolo=simbolo,
        kpis_json=json.dumps(kpis, ensure_ascii=False, indent=2),
    )

    narrative_text = ""
    try:
        from app.db.session import SessionLocal
        from app.services.ai_provider_service import call_ai

        db = SessionLocal()
        try:
            narrative_text = call_ai(
                db,
                messages=[{"role": "user", "content": prompt_text}],
                system="Eres un analista financiero ejecutivo. Responde en el idioma solicitado.",
                module="bi_storytelling",
                user_id=None,
                max_tokens=800,
                is_superadmin=False,
                organization_id=org_id,
            )
        finally:
            db.close()

        # Revisión 2026-11: cualquier aviso de la IA (sin proveedor, error del
        # proveedor…) va a la plantilla; antes sólo se reconocía uno y el texto
        # del error se enseñaba y se guardaba una hora como si fuera el resumen.
        from app.services.ai_provider_service import es_aviso_de_ia
        if not narrative_text or es_aviso_de_ia(narrative_text):
            raise RuntimeError("La IA no dio un resumen")
    except Exception as exc:
        logger.warning("LLM narrative generation failed: %s", exc)
        narrative_text = _fallback_narrative(kpis, lang, simbolo)

    result = {
        "narrative": narrative_text,
        "kpis": kpis,
        "lang": lang,
        "cached": False,
        "source": kpis.get("source", "unknown"),
    }

    try:
        cache_set(cache_key, result, ttl_seconds=3600)
    except Exception as exc:
        logger.debug("Cache write failed (non-fatal): %s", exc)

    return result


def _fallback_narrative(kpis: dict, lang: str, simbolo: str) -> str:
    """Simple template fallback when LLM is unavailable."""
    from app.services.formato_regional import formatear_importe
    projects = int(_to_number(kpis.get("active_projects"), 0))
    margin = round(_to_number(kpis.get("avg_margin_pct"), 0.0), 1)
    pipeline = round(_to_number(kpis.get("pipeline_weighted"), 0.0), 0)
    opps = int(_to_number(kpis.get("open_opps"), 0))
    high_risk = int(_to_number(kpis.get("high_risk_projects"), 0))

    if lang == "es":
        return (
            f"**Resumen ejecutivo** (generado automáticamente)\n\n"
            f"El portfolio activo cuenta con {projects} proyectos en curso, con un margen medio "
            f"del {margin}%. El pipeline comercial presenta {opps} oportunidades abiertas "
            f"con un revenue ponderado de {formatear_importe(pipeline, simbolo)}.\n\n"
            f"{'⚠ Atención: hay ' + str(high_risk) + ' proyectos en riesgo alto.' if high_risk else ''}"
        )
    return (
        f"**Executive Summary** (auto-generated)\n\n"
        f"Active portfolio: {projects} projects with avg margin {margin}%. "
        f"Pipeline: {opps} open opportunities, weighted revenue {formatear_importe(pipeline, simbolo)}."
    )
