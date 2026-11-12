"""Despacho de una llamada (`call_ai`): eleccion de proveedor, llamada con respaldo y contabilidad del proveedor.

Parte de `app.services.ai_provider_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.ai_providers import AIProvider
from app.services.ai_provider_service.catalogo import PROVIDER_CATALOG
from app.services.ai_provider_service.clientes import call_provider
from app.services.ai_provider_service.resolucion import _disponible, get_default_provider
from app.services.ai_provider_service.rutas import rutas_por_modulo
from app.services.ai_provider_service.gobernanza import (
    _aplicar_guardrail_de_entrada,
    _aplicar_guardrail_de_salida,
    _resolver_usuario_de_gobernanza,
)
from app.services.ai_provider_service.gasto import (
    _avisar_si_el_coste_diario_se_pasa,
    _exigir_presupuesto,
    _org_de_la_llamada,
    _registrar_uso,
)

_logger = logging.getLogger("ai_provider_service")


def _try_fallback_providers(
    db: Session,
    messages: list,
    system: str,
    max_tokens: int,
    is_superadmin: bool,
    organization_id,
) -> "tuple[AIProvider | None, dict | None]":
    """
    Try any available provider as fallback (provider-agnostic).

    Devuelve `(proveedor, resultado)` del primero que responda, o
    `(None, None)` si fallan todos.

    Antes devolvia solo el resultado, y `call_ai` no podia saber quien habia
    atendido la llamada: la registraba con `provider_id = None`. El proveedor si
    actualizaba sus propios contadores aqui dentro, asi que los agregados por
    proveedor y `AIUsageLog` discrepaban justo para el trafico de respaldo — el
    coste contado en el proveedor y las filas del log sin poder agruparse por el.
    """
    # Get all available active providers
    query = db.query(AIProvider).filter(
        _disponible(db),
        AIProvider.is_active == True,  # audit #36 soft-delete
    )

    # Orden de respaldo configurable (`priority`), estable por fecha.
    query = query.order_by(AIProvider.priority.asc(), AIProvider.created_at.asc())
    if not is_superadmin and organization_id:
        # Try org-specific first, then shared
        org_providers = query.filter(AIProvider.organization_id == organization_id).all()
        shared_providers = query.filter(AIProvider.organization_id.is_(None)).all()
        all_providers = org_providers + shared_providers
    else:
        all_providers = query.all()

    # Try each provider in order
    for provider in all_providers:
        try:
            result = call_provider(
                provider,
                messages,
                system=system,
                model=None,  # Use provider's default model
                max_tokens=max_tokens,
            )

            # Update provider stats
            provider.total_requests   += 1
            provider.total_tokens_in  += result.get("tokens_in", 0)
            provider.total_tokens_out += result.get("tokens_out", 0)
            provider.last_used_at      = datetime.now(timezone.utc)

            # Calculate cost if model info available
            cat_models = PROVIDER_CATALOG.get(provider.provider, {}).get("models", [])
            m_info = next(
                (m for m in cat_models if m["id"] == (result.get("model"))),
                None
            )
            if m_info:
                cost = (
                    result.get("tokens_in", 0) / 1_000_000 * m_info["cost_in"] +
                    result.get("tokens_out", 0) / 1_000_000 * m_info["cost_out"]
                )
                provider.total_cost_usd += cost
                result["cost_usd"] = cost

            # La llamada YA se ha atendido y el proveedor YA la ha facturado,
            # asi que la contabilidad va en su propio `try`: si el `commit()` de
            # estadisticas falla, se deshace y la respuesta se devuelve IGUAL.
            #
            # Antes ese `commit()` estaba dentro del `try` de la llamada, de modo
            # que un fallo de NUESTRA base caia en el `except ... continue` de
            # abajo: se descartaba una respuesta ya pagada y, peor, la sesion
            # quedaba envenenada, asi que todos los proveedores siguientes del
            # bucle fallaban tambien y la funcion acababa devolviendo «todos los
            # proveedores han fallado» — el diagnostico contrario al real.
            # Auditoria 2026-08, hallazgo 22.
            try:
                db.commit()
            except Exception:
                db.rollback()
                _logger.warning(
                    "no se pudieron guardar las estadisticas del proveedor %s; "
                    "la respuesta se devuelve igual", provider.name,
                    exc_info=True,
                )
            _logger.info(
                "Fallback AI provider succeeded: %s (%s)",
                provider.name, provider.provider
            )
            return provider, result

        except Exception as exc:
            # Solo el fallo de la LLAMADA justifica probar el siguiente
            # proveedor. El de la contabilidad no llega aqui: lo atrapa el `try`
            # interior de arriba.
            _logger.debug(
                "Fallback provider %s failed: %s",
                provider.name, str(exc)
            )
            continue

    # All providers failed
    _logger.warning("All AI providers failed as fallback")
    return None, None


# ── Despacho de una llamada a un modelo ──────────────────────────────────────
#
# Auditoria 2026-08 (hallazgo 18 + hueco de observabilidad encontrado de paso).
# `call_ai` era complejidad 24 en siete fases mezcladas: gobernanza de entrada,
# eleccion de proveedor, llamada con respaldo, registro de uso, aviso de coste y
# gobernanza de salida. Ahora cada fase tiene nombre.
#
# ── El hueco ──────────────────────────────────────────────────────────────────
#
# `_try_fallback_providers` devolvia solo el resultado, no el proveedor que lo
# habia servido, y `call_ai` ponia `p = None` antes de llamarlo. Consecuencia:
# una llamada atendida por el respaldo se registraba en `AIUsageLog` con
# `provider_id = None`.
#
# El proveedor SI actualizaba sus propios contadores dentro del respaldo, asi que
# los agregados por proveedor y el registro de uso DISCREPABAN justo para ese
# trafico: el coste estaba contado en el proveedor pero las filas del log no se
# podian agrupar por el. Con un primario caido —que es cuando el respaldo
# actua— eso puede ser una parte grande del gasto sin atribuir.
#
# Arreglo: `_try_fallback_providers` devuelve `(proveedor, resultado)` y el
# registro apunta al proveedor que de verdad respondio. Es una funcion privada
# llamada solo desde aqui, asi que el cambio de contrato esta contenido.


def _seleccionar_proveedor(db: Session, provider_id, is_superadmin: bool, organization_id):
    """El proveedor primario: el pedido explicitamente, o el de la organizacion.

    El filtro por `organization_id` cuando no es superadmin es lo que impide que
    un identificador adivinado sirva para usar el proveedor —y la clave— de otro
    cliente.
    """
    if not provider_id:
        return get_default_provider(
            db, is_superadmin=is_superadmin, organization_id=organization_id
        )
    q = db.query(AIProvider).filter(AIProvider.id == provider_id)
    if not is_superadmin and organization_id:   # el de su empresa o uno global (compartido)
        q = q.filter(or_(AIProvider.organization_id == organization_id, AIProvider.organization_id.is_(None)))
    return q.first()


def _apuntar_uso_en_el_proveedor(p, result: dict, model) -> None:
    """Suma peticiones, tokens y coste al proveedor que ha respondido.

    Si estaba en error y ha respondido, vuelve a «activo».
    """
    if getattr(p, "status", None) == "error":
        p.status = "active"
    p.total_requests += 1
    p.total_tokens_in += result["tokens_in"]
    p.total_tokens_out += result["tokens_out"]
    p.last_used_at = datetime.now(timezone.utc)

    cat_models = PROVIDER_CATALOG.get(p.provider, {}).get("models", [])
    m_info = next((m for m in cat_models if m["id"] == (model or p.default_model)), None)
    if m_info:
        cost = (result["tokens_in"] / 1_000_000 * m_info["cost_in"] +
                result["tokens_out"] / 1_000_000 * m_info["cost_out"])
        p.total_cost_usd += cost
        result["cost_usd"] = cost


def _marcar_proveedor_en_error(p, error_msg: str) -> None:
    p.last_error = error_msg[:500]
    p.last_error_at = datetime.now(timezone.utc)
    p.status = "error"


SIN_PROVEEDOR = "no_ai_provider_configured"
AVISO_SIN_PROVEEDOR = (
    "⚠️ No hay ningún proveedor de IA configurado. "
    "Ve a Inteligencia IA → IA & Conectores para añadir uno."
)


def es_aviso_de_ia(texto) -> bool:
    """True si `call_ai` devolvio un aviso (sin proveedor o error) y no una respuesta."""
    return isinstance(texto, str) and texto.lstrip().startswith("⚠️")


def _llamar_con_respaldo(db: Session, p, messages: list, system, model, max_tokens,
                         is_superadmin: bool, organization_id):
    """Llama al primario y, si falla, a cualquier otro disponible.

    Devuelve `(proveedor_que_respondio, resultado, error)`. El proveedor
    devuelto es el que DE VERDAD atendio la llamada, que es lo que hace que el
    registro de uso quede atribuido — ver la nota de cabecera.
    """
    vacio = {"text": "", "tokens_in": 0, "tokens_out": 0, "model": "unknown"}

    if p:
        # El `try` cubre SOLO la llamada. Antes cubria tambien el `commit()` de
        # estadisticas, y eso hacia que un fallo de nuestra base marcase
        # `status = "error"` en un proveedor que HABIA FUNCIONADO —el valor que
        # lo excluye de futuras selecciones— y volviese a hacer `commit()` sobre
        # la sesion ya abortada. Auditoria 2026-08, hallazgo 22.
        try:
            result = call_provider(p, messages, system=system,
                                   model=model or p.default_model,
                                   max_tokens=max_tokens)
        except Exception as e:
            error_msg = str(e)
            _marcar_proveedor_en_error(p, error_msg)
            try:
                db.commit()
            except Exception:
                # Que no se pueda anotar el error del proveedor no debe tapar el
                # error del proveedor: se deshace y se sigue al respaldo.
                db.rollback()
                _logger.warning("no se pudo marcar el proveedor %s en error",
                                p.name, exc_info=True)
            respaldo, result = _try_fallback_providers(
                db, messages, system, max_tokens, is_superadmin, organization_id
            )
            if result:
                return respaldo, result, None
            # Se conserva el error del primario: es el informativo.
            return None, vacio, error_msg

        # La llamada ya se ha atendido y facturado: la contabilidad no puede
        # tirar la respuesta.
        try:
            _apuntar_uso_en_el_proveedor(p, result, model)
            db.commit()
        except Exception:
            db.rollback()
            _logger.warning(
                "no se pudieron guardar las estadisticas del proveedor %s; la "
                "respuesta se devuelve igual", p.name, exc_info=True,
            )
        return p, result, None

    respaldo, result = _try_fallback_providers(
        db, messages, system, max_tokens, is_superadmin, organization_id
    )
    if result:
        return respaldo, result, None

    vacio["text"] = AVISO_SIN_PROVEEDOR
    # Auditoria 2026-11: antes error=None, asi que el uso se registraba como
    # exito con 0 tokens y las funciones daban la llamada por buena.
    return None, vacio, SIN_PROVEEDOR


def call_ai(
    db: Session,
    messages: list,
    system: str = None,
    module: str = "general",
    user_id: str = None,
    model: str = None,
    max_tokens: int = None,
    provider_id: str = None,
    is_superadmin: bool = False,
    organization_id=None,
    skip_guardrails: bool = False,
) -> str:
    """
    Main AI dispatch function (provider-agnostic).

    Resolution order:
    1. Explicit provider_id (if provided)
    2. Default provider for organization
    3. Any available provider as fallback
    4. No provider available → error message

    Multi-tenant aware: filtra providers por ``organization_id`` cuando no es
    superadmin. Cost tracking real desde PROVIDER_CATALOG. Fallback automático
    si el primary provider falla.

    Governance: aplica ``check_prompt`` sobre el último mensaje de usuario
    antes de llamar al LLM y ``check_output`` sobre la respuesta. Pasa
    ``skip_guardrails=True`` SOLO para llamadas internas que no son
    user-facing (p. ej. construcción de embeddings, sondas de salud).
    Antes los guardrails sólo se aplicaban en ``ai_chat.py`` → 54% del
    tráfico IA bypasaba policies.
    """
    governance_user = _resolver_usuario_de_gobernanza(db, user_id, skip_guardrails)

    bloqueo = _aplicar_guardrail_de_entrada(
        db, messages, governance_user, module, skip_guardrails
    )
    if bloqueo:
        return bloqueo
    org_de_la_llamada = _org_de_la_llamada(db, organization_id, user_id)
    _exigir_presupuesto(db, org_de_la_llamada)
    # Revisión 2026-11: el proveedor se elige con la empresa de la llamada (la de
    # la sesión o la del usuario) y no como superadministrador por defecto. Antes
    # un trabajo de fondo sin filtro de empresa podía usar el proveedor —y la
    # clave— de otra.
    organization_id = organization_id or org_de_la_llamada

    # Proveedor y modelo por funcion (Hub de IA → «Por función»), si los hay y
    # la llamada no pide uno concreto. Si el elegido no esta disponible, el
    # de siempre.
    if not provider_id:
        ruta = rutas_por_modulo(db, organization_id).get(module) or {}
        if ruta.get("provider_id"):
            elegido = _seleccionar_proveedor(db, ruta["provider_id"], is_superadmin, organization_id)
            if elegido is not None and elegido.is_active and (
                    elegido.status != "error" or db.query(AIProvider.id).filter(
                        AIProvider.id == elegido.id, _disponible(db)).first()):
                provider_id = elegido.id
        model = model or ruta.get("model")
    p = _seleccionar_proveedor(db, provider_id, is_superadmin, organization_id)

    t0 = time.time()
    p, result, error_msg = _llamar_con_respaldo(
        db, p, messages, system, model, max_tokens, is_superadmin, organization_id
    )
    latency = int((time.time() - t0) * 1000)

    _registrar_uso(db, p, result, user_id=user_id, module=module,
                   latency=latency, error_msg=error_msg, organization_id=org_de_la_llamada)
    if error_msg is None:
        _avisar_si_el_coste_diario_se_pasa(db, result, org_de_la_llamada)

    final_text = _aplicar_guardrail_de_salida(
        db, result.get("text", "") or "", governance_user, module,
        skip_guardrails, error_msg,
    )

    # Si falló el provider, devolvemos un texto explícito de error que el
    # caller puede distinguir (#43): prefijo "⚠️". `es_aviso_de_ia()` lo detecta.
    if error_msg == SIN_PROVEEDOR:
        return AVISO_SIN_PROVEEDOR
    if error_msg is not None:
        return f"⚠️ AI provider error: {error_msg[:200]}"

    return final_text
