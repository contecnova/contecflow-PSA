"""Registro de uso, tope diario de gasto por empresa, coste estimado y turnos gobernados del agente.

Parte de `app.services.ai_provider_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.ai_providers import AIUsageLog
from app.services.ai_provider_service.catalogo import PROVIDER_CATALOG

_logger = logging.getLogger("ai_provider_service")


def _registrar_uso(db: Session, p, result: dict, *, user_id, module,
                   latency: int, error_msg, organization_id=None) -> None:
    """Escribe la fila de `AIUsageLog`. Un fallo al registrar no rompe la llamada.

    El `rollback` del `except` no es opcional: sin el, una sesion en transaccion
    abortada haria fallar todo lo que viene despues, incluido el aviso de coste.
    Revisión 2026-11: con la empresa de la llamada explícita (antes dependía del
    sellado de la sesión, vacío en los trabajos de fondo); es lo que suma el
    gasto diario de cada empresa.
    """
    db.add(AIUsageLog(
        organization_id=organization_id,
        provider_id=p.id if p else None,
        user_id=user_id,
        module=module,
        model=result.get("model"),
        tokens_in=result.get("tokens_in", 0),
        tokens_out=result.get("tokens_out", 0),
        cost_usd=result.get("cost_usd", 0),
        latency_ms=latency,
        success=error_msg is None,
        error_msg=error_msg,
    ))
    try:
        db.commit()
    except Exception:
        _logger.warning("Failed to persist AIUsageLog entry; rolling back", exc_info=True)
        db.rollback()


class PresupuestoDeIAAgotado(RuntimeError):
    """La empresa ha llegado a su tope diario de gasto en IA (`AI_DAILY_BUDGET_USD`)."""


def _inicio_de_hoy() -> datetime:
    return datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


def gasto_de_hoy(db: Session, organization_id) -> float:
    """Coste (USD) de las llamadas con éxito de la empresa desde las 00:00 UTC."""
    from app.db.session import sin_filtro_de_tenant
    with sin_filtro_de_tenant(db):
        return float(db.query(func.sum(AIUsageLog.cost_usd)).filter(
            AIUsageLog.organization_id == organization_id,
            AIUsageLog.created_at >= _inicio_de_hoy(),
            AIUsageLog.success == True,   # noqa: E712 — comparación SQL
        ).scalar() or 0)


def presupuesto_diario(db: Session, organization_id) -> float:
    """Tope diario de la empresa (0: sin tope)."""
    from app.services.settings_service import get_runtime_float
    return float(get_runtime_float(db, "AI_DAILY_BUDGET_USD", organization_id) or 0)


def _exigir_presupuesto(db: Session, organization_id) -> None:
    """Revisión 2026-11 (lo que contecintelligence tenía): un tope real, que la
    empresa decide. Sin tope (0, por defecto) no corta nada."""
    if not organization_id:
        return
    tope = presupuesto_diario(db, organization_id)
    if tope > 0 and gasto_de_hoy(db, organization_id) >= tope:
        raise PresupuestoDeIAAgotado(
            f"La empresa ha alcanzado su límite diario de gasto en IA ({tope:.2f} USD). "
            "Se restablece a las 00:00 UTC o lo puede subir un administrador (AI_DAILY_BUDGET_USD).")


def coste_estimado(proveedor: str, modelo, tokens_in: int, tokens_out: int) -> float:
    """Coste (USD) según el catálogo de modelos; 0 si el modelo no está en él."""
    modelos = PROVIDER_CATALOG.get(proveedor, {}).get("models", [])
    m = next((m for m in modelos if m["id"] == modelo), None)
    if not m:
        return 0.0
    return tokens_in / 1_000_000 * m["cost_in"] + tokens_out / 1_000_000 * m["cost_out"]


def turno_de_agente(db: Session, usuario, *, module: str = "nexusagent", **pedido):
    """Un turno del agente con herramientas, GOBERNADO como `call_ai`.

    Revisión 2026-11: el agente pedía sus turnos directamente al proveedor
    (`ai_tools.pedir_turno`), así que el tope diario de la empresa no lo frenaba
    y su gasto no se registraba. Ahora cada turno exige el tope antes y apunta
    tokens y coste después (también si falla).
    """
    import time
    from app.services import ai_tools
    org = _org_de_la_llamada(db, getattr(usuario, "organization_id", None), getattr(usuario, "id", None))
    _exigir_presupuesto(db, org)
    proveedor, modelo = (pedido.get("proveedor") or "").strip().lower(), pedido.get("modelo")
    inicio = time.time()
    try:
        turno = ai_tools.pedir_turno(**pedido)
    except Exception as e:
        _registrar_uso(db, None, {"model": modelo}, user_id=getattr(usuario, "id", None), module=module,
                       latency=int((time.time() - inicio) * 1000), error_msg=str(e)[:500], organization_id=org)
        raise
    tin, tout = ai_tools.uso_del_turno(proveedor, turno.crudo)
    _registrar_uso(db, None, {"model": modelo, "tokens_in": tin, "tokens_out": tout,
                              "cost_usd": coste_estimado(proveedor, modelo, tin, tout)},
                   user_id=getattr(usuario, "id", None), module=module,
                   latency=int((time.time() - inicio) * 1000), error_msg=None, organization_id=org)
    return turno


def _org_de_la_llamada(db: Session, organization_id, user_id):
    if organization_id:
        return organization_id
    if db.info.get("organization_id"):
        return db.info["organization_id"]
    if user_id:
        from app.models.user import User
        from app.db.session import sin_filtro_de_tenant
        with sin_filtro_de_tenant(db):
            usuario = db.get(User, user_id)
        return getattr(usuario, "organization_id", None)
    return None


def _avisar_si_el_coste_diario_se_pasa(db: Session, result: dict, organization_id=None) -> None:
    """Avisa en el log si el gasto acumulado del dia supera el umbral.

    Es un aviso y no un corte: cortar la IA a media jornada por un umbral de
    coste dejaria la aplicacion a medias sin que nadie lo hubiera decidido.
    """
    if result.get("cost_usd", 0) <= 0:
        return
    try:
        from app.services.settings_service import get_runtime_float
        threshold = (get_runtime_float(db, "AI_COST_ALERT_USD_PER_DAY", organization_id)
                     or settings.AI_COST_ALERT_USD_PER_DAY)
        # Revisión 2026-11: por empresa (antes sumaba el gasto de todas).
        today_cost = gasto_de_hoy(db, organization_id)
        if today_cost > threshold:
            _logger.warning(
                "AI_COST_ALERT: empresa %s, coste diario acumulado $%.4f supera el umbral $%.2f.",
                organization_id, today_cost, threshold,
            )
    except Exception as alert_exc:
        _logger.debug("Cost alert check failed (non-critical): %s", alert_exc)
