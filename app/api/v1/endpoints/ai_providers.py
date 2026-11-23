"""AI Providers — CRUD y despacho multi-proveedor"""
import logging
import time

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.constantes import NOMBRE_DEL_PRODUCTO
from app.core.deps import get_current_user, requiere_capacidad
from app.db.session import get_db
from app.core.config import settings
from app.models.user import User
from app.core.abac_enforce import enforce_abac
from app.core.responses import APIListResponse, APIResponse
from app.services.ai_provider_service import (
    PROVIDER_CATALOG,
    call_ai,
    call_provider as _call_provider,
    create_provider as svc_create_provider,
    delete_provider as svc_delete_provider,
    diagnose_provider as svc_diagnose_provider,
    get_provider,
    get_stats as svc_get_stats,
    list_providers as svc_list_providers,
    sync_provider_models as svc_sync_provider_models,
    set_default_provider as svc_set_default_provider,
    update_provider as svc_update_provider,
    update_provider_test_result,
)
from app.services import ai_provider_service as _ia
from app.core.codigos_de_error import error_http, desde_valor

_logger = logging.getLogger("ai_providers")

router = APIRouter()


def _out(p):
    return {
        "id": p.id, "name": p.name, "provider": p.provider,
        "status": p.status, "is_default": p.is_default,
        "default_model": p.default_model,
        "available_models": p.available_models.split(",") if p.available_models else [],
        "api_base_url": p.api_base_url,
        "has_api_key": bool(p.api_key),
        "max_tokens": p.max_tokens, "temperature": p.temperature,
        "priority": getattr(p, "priority", 100),
        "total_requests": p.total_requests,
        "total_cost_usd": round(p.total_cost_usd, 4),
        "last_used_at": str(p.last_used_at) if p.last_used_at else None,
        "last_error": p.last_error,
        "created_at": str(p.created_at),
    }


# ── Endpoints de gestión ──────────────────────────────────────────────────────
@router.get("/catalog")
def get_catalog(_=Depends(get_current_user)):
    """Catálogo completo de proveedores y modelos disponibles."""
    return APIResponse.ok(data=PROVIDER_CATALOG)


# 18-11-2026 (auditoria de textos fijos): la prueba de conexion no depende del
# idioma de nadie; se pide en ingles y neutra para que la respuesta («OK») sea
# la misma con cualquier modelo.
_MENSAJE_DE_PRUEBA = "Reply with exactly: OK"
_SISTEMA_DE_PRUEBA = "You are a connectivity test. Answer only what is asked."

@router.get("")
def list_providers(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    providers = svc_list_providers(
        db, is_superadmin=current_user.is_superadmin, organization_id=current_user.organization_id
    )
    items = [_out(p) for p in providers]
    # Revision 2026-11: el proveedor del `.env` tambien se ve (antes funcionaba
    # sin aparecer en ningun sitio). No es una fila: se puede probar e importar.
    entorno = _ia.proveedor_desde_entorno()
    if entorno is not None:
        items.append({
            "id": "env", "source": "env", "name": entorno.name, "provider": entorno.provider,
            "status": "active", "is_default": not any(i["is_default"] for i in items),
            "default_model": entorno.default_model, "available_models": [],
            "api_base_url": entorno.api_base_url, "has_api_key": bool(entorno.api_key),
            "max_tokens": entorno.max_tokens, "temperature": entorno.temperature, "priority": None,
            "total_requests": 0, "total_cost_usd": 0, "last_used_at": None, "last_error": None, "created_at": None,
        })
    return APIListResponse.ok(items=items)


@router.post("/env/import", summary="Importar el proveedor del .env a la aplicación")
def import_env_provider(db: Session = Depends(get_db), cu=Depends(requiere_capacidad("ia.administrar"))):
    """Crea un proveedor editable con lo del `.env` (la clave se guarda cifrada)."""
    try:
        p = _ia.importar_proveedor_de_entorno(db, cu)
    except ValueError as e:
        raise desde_valor(409, e)
    return APIResponse.ok(data=_out(p))


@router.post("/env/test", summary="Probar el proveedor del .env")
def test_env_provider(_=Depends(requiere_capacidad("ia.administrar"))):
    p = _ia.proveedor_desde_entorno()
    if p is None:
        raise error_http(404, "ia_sin_proveedor", detail="No hay proveedor de IA en el .env")
    t0 = time.time()
    try:
        resultado = _ia.call_provider(p, [{"role": "user", "content": _MENSAJE_DE_PRUEBA}],
                                      system=_SISTEMA_DE_PRUEBA, max_tokens=settings.AI_TEST_MAX_TOKENS)
    except Exception as e:
        raise _http_del_error_de_proveedor(str(e))
    return APIResponse.ok(data={"ok": True, "response": resultado.get("text", ""),
                                "latency_ms": int((time.time() - t0) * 1000),
                                "model": resultado.get("model", p.default_model)})


@router.post("")
def create_provider(data: dict = Body(...), db: Session = Depends(get_db), cu=Depends(requiere_capacidad("ia.administrar"))):
    p = svc_create_provider(
        db,
        organization_id=cu.organization_id,
        created_by=cu.id,
        data=data,
        is_superadmin=cu.is_superadmin,
    )
    return APIResponse.ok(data=_out(p))


@router.patch("/{pid}")
def update_provider(pid: str, data: dict = Body(...), db: Session = Depends(get_db), _=Depends(requiere_capacidad("ia.administrar"))):
    p = get_provider(db, pid, is_superadmin=_.is_superadmin, organization_id=_.organization_id)
    if not p:
        raise error_http(404, "no_encontrado", detail="AI provider not found", que="proveedor_ia")
    p = svc_update_provider(db, p, data, is_superadmin=_.is_superadmin, organization_id=_.organization_id)
    return APIResponse.ok(data=_out(p))


@router.delete("/{pid}")
def delete_provider(pid: str, db: Session = Depends(get_db), _=Depends(requiere_capacidad("ia.administrar"))):
    enforce_abac(db, _, "ai_provider", pid, action="delete")
    p = get_provider(db, pid, is_superadmin=_.is_superadmin, organization_id=_.organization_id)
    if not p:
        raise error_http(404, "no_encontrado", detail="AI provider not found", que="proveedor_ia")
    svc_delete_provider(db, p)
    return APIResponse.ok(data={"ok": True})


@router.post("/{pid}/set-default")
def set_default(pid: str, db: Session = Depends(get_db), _=Depends(requiere_capacidad("ia.administrar"))):
    p = svc_set_default_provider(db, pid, is_superadmin=_.is_superadmin, organization_id=_.organization_id)
    if not p:
        raise error_http(404, "no_encontrado", detail="AI provider not found", que="proveedor_ia")
    return APIResponse.ok(data={"ok": True})


def _anotar_resultado_de_prueba(db, proveedor, *, ok: bool, error: str = "") -> None:
    """Deja constancia de la prueba, sin dejar que el registro tape el resultado.

    Auditoría 2026-09 (hallazgo 18): este `try/except` estaba escrito **cuatro
    veces, palabra por palabra** dentro de `test_provider` —una por rama de
    error—, y era la mitad de su complejidad.

    El fallo al anotar se traga a propósito: la prueba ya dio su veredicto, y
    perderlo porque no se pudo escribir en la base sería sustituir un
    diagnóstico bueno por uno peor.
    """
    try:
        if ok:
            update_provider_test_result(db, proveedor, success=True)
        else:
            update_provider_test_result(db, proveedor, success=False, error=error)
    except Exception as exc:
        _logger.error("Failed to update provider test result in DB: %s", exc)


#: Qué significa un error del proveedor, por las palabras que trae. Cada fila:
#: (marcas que lo identifican, código HTTP, mensaje).
#:
#: Se clasifica por subcadena porque **cada proveedor devuelve el error a su
#: manera** y ninguno expone un código estable. El orden importa: gana la
#: primera que encaje, y las credenciales van primero porque un 401 mal
#: clasificado como 502 manda a mirar el sitio equivocado.
_ERRORES_DE_PROVEEDOR: tuple[tuple[tuple[str, ...], int, str, str], ...] = (
    (("api key not valid", "api key invalid", "invalid api key", "unauthorized",
      " 401", "authentication", "permission denied", " 403", "forbidden"),
     401, "Credenciales inválidas en el proveedor", "ia_credenciales_no_validas"),
    (("rate limit", "rate_limit", " 429", "too many requests", "quota"),
     429, "Límite de uso alcanzado en el proveedor", "ia_limite_de_uso"),
    (("model not found", "not_found", " 404", "no such model"),
     404, "Modelo o endpoint no encontrado", "ia_modelo_no_encontrado"),
)


def _http_del_error_de_proveedor(mensaje: str) -> HTTPException:
    """Traduce un error del proveedor al código que le corresponde.

    Lo que no se reconoce es **502 y no 500**: el fallo es de un tercero, y
    devolver 500 haría pensar que el fallo es nuestro.
    """
    minusculas = mensaje.lower()
    for marcas, codigo, texto, clave in _ERRORES_DE_PROVEEDOR:
        if any(marca in minusculas for marca in marcas):
            return error_http(codigo, clave, detail=f"{texto}: {mensaje[:300]}")
    return error_http(502, "ia_proveedor_error", detail=f"El proveedor devolvió un error: {mensaje[:300]}")


@router.post("/test-config", summary="Probar una configuración sin guardarla")
def test_unsaved(data: dict = Body(...), _=Depends(requiere_capacidad("ia.administrar"))):
    """Revision 2026-11 (de contecmind): probar la clave escrita antes de guardarla."""
    try:
        p = _ia.proveedor_sin_guardar(data)
    except ValueError as e:
        raise desde_valor(400, e)
    t0 = time.time()
    try:
        resultado = _ia.call_provider(p, [{"role": "user", "content": _MENSAJE_DE_PRUEBA}],
                                      system=_SISTEMA_DE_PRUEBA, max_tokens=settings.AI_TEST_MAX_TOKENS)
    except Exception as e:
        raise _http_del_error_de_proveedor(str(e))
    return APIResponse.ok(data={"ok": True, "response": resultado.get("text", ""),
                                "latency_ms": int((time.time() - t0) * 1000),
                                "model": resultado.get("model", p.default_model)})


@router.post("/discover-models", summary="Modelos disponibles con la clave escrita (sin guardar)")
def discover_unsaved(data: dict = Body(...), _=Depends(requiere_capacidad("ia.administrar"))):
    try:
        modelos = _ia.list_models_for_provider(_ia.proveedor_sin_guardar(data))
    except ValueError as e:
        raise desde_valor(400, e)
    except Exception as e:
        raise _http_del_error_de_proveedor(str(e))
    return APIResponse.ok(data={"models": modelos})


@router.get("/spend-today", summary="Gasto en IA de hoy frente al tope diario de la empresa")
def gasto_de_hoy(db: Session = Depends(get_db), cu=Depends(requiere_capacidad("ia.administrar"))):
    from app.services.ai_provider_service import gasto_de_hoy as _gasto, presupuesto_diario
    from app.services.settings_service import get_runtime_float
    org = cu.organization_id
    tope = presupuesto_diario(db, org)
    gastado = _gasto(db, org)
    aviso = float(get_runtime_float(db, "AI_DAILY_BUDGET_WARN_PCT", org) or 0)
    return APIResponse.ok(data={
        "spent_usd": round(gastado, 4), "budget_usd": tope, "warn_pct": aviso,
        "used_pct": round(gastado / tope * 100, 1) if tope > 0 else None,
        "blocked": tope > 0 and gastado >= tope,
    })


@router.get("/routing", summary="Proveedor y modelo por función")
def get_routing(db: Session = Depends(get_db), cu=Depends(requiere_capacidad("ia.administrar"))):
    return APIResponse.ok(data={
        "modules": [{"key": k, "label": v} for k, v in _ia.MODULOS_DE_IA.items()],
        "routes": _ia.rutas_por_modulo(db, cu.organization_id),
    })


@router.put("/routing", summary="Guardar proveedor y modelo por función")
def put_routing(data: dict = Body(...), db: Session = Depends(get_db), cu=Depends(requiere_capacidad("ia.administrar"))):
    rutas = data.get("routes") or {}
    for ruta in rutas.values():
        pid = (ruta or {}).get("provider_id")
        if pid and not get_provider(db, pid, is_superadmin=cu.is_superadmin, organization_id=cu.organization_id):
            raise error_http(400, "ia_proveedor_ajeno", detail="Ese proveedor no es de esta empresa")
    return APIResponse.ok(data={"routes": _ia.guardar_rutas(db, cu.organization_id, rutas)})


@router.post("/{pid}/test")
def test_provider(pid: str, db: Session = Depends(get_db), _=Depends(requiere_capacidad("ia.administrar"))):
    """Probar la conexión con el proveedor enviando un mensaje de prueba."""
    p = get_provider(db, pid, is_superadmin=_.is_superadmin, organization_id=_.organization_id)
    if not p:
        raise error_http(404, "no_encontrado", detail="AI provider not found", que="proveedor_ia")

    t0 = time.time()
    try:
        resultado = _call_provider(
            p, [{"role": "user", "content": _MENSAJE_DE_PRUEBA}],
            system=_SISTEMA_DE_PRUEBA, max_tokens=settings.AI_TEST_MAX_TOKENS,
        )
    except ValueError as e:
        _anotar_resultado_de_prueba(db, p, ok=False, error=str(e))
        _logger.warning("Prueba de proveedor IA: error de datos: %s", e)
        raise error_http(400, "ia_error_datos")
    except ConnectionError as e:
        _anotar_resultado_de_prueba(db, p, ok=False, error=str(e))
        _logger.warning("Prueba de proveedor IA: sin conexion: %s", e)
        raise error_http(503, "ia_proveedor_sin_conexion")
    except Exception as e:
        _anotar_resultado_de_prueba(db, p, ok=False, error=str(e))
        raise _http_del_error_de_proveedor(str(e))

    _anotar_resultado_de_prueba(db, p, ok=True)
    return APIResponse.ok(data={
        "ok": True,
        "response": resultado.get("text", ""),
        "latency_ms": int((time.time() - t0) * 1000),
        "model": resultado.get("model", p.default_model),
    })


@router.post("/{pid}/sync-models")
def sync_provider_models(pid: str, db: Session = Depends(get_db), _=Depends(requiere_capacidad("ia.administrar"))):
    """Discover and persist the live model list from the upstream provider."""
    p = get_provider(db, pid, is_superadmin=_.is_superadmin, organization_id=_.organization_id)
    if not p:
        raise error_http(404, "no_encontrado", detail="AI provider not found", que="proveedor_ia")

    try:
        models = svc_sync_provider_models(db, p)
        return APIResponse.ok(data={
            "ok": True,
            "provider_id": p.id,
            "provider": p.provider,
            "models": models,
            "default_model": p.default_model,
        })
    except ValueError as e:
        raise desde_valor(400, e)
    except Exception as e:
        _logger.exception("svc_sync_provider_models failed for provider=%s", p.id)
        update_provider_test_result(db, p, success=False, error=str(e))
        raise error_http(500, "ia_modelos_no_sincronizados")


@router.post("/sync-models/all")
def sync_all_provider_models(db: Session = Depends(get_db), _=Depends(requiere_capacidad("ia.administrar"))):
    """Discover and persist live model lists for all configured providers in scope."""
    providers = svc_list_providers(
        db,
        is_superadmin=_.is_superadmin,
        organization_id=_.organization_id,
    )
    if not providers:
        return APIResponse.ok(data={"ok": True, "results": [], "message": "No hay proveedores configurados"})

    results = []
    failures = 0
    for p in providers:
        try:
            models = svc_sync_provider_models(db, p)
            results.append({
                "provider_id": p.id,
                "name": p.name,
                "provider": p.provider,
                "ok": True,
                "count": len(models),
                "default_model": p.default_model,
            })
        except Exception as e:
            _logger.exception("svc_sync_provider_models failed for provider=%s in bulk sync", p.id)
            failures += 1
            update_provider_test_result(db, p, success=False, error=str(e))
            results.append({
                "provider_id": p.id,
                "name": p.name,
                "provider": p.provider,
                "ok": False,
                "error": str(e),
            })

    return APIResponse.ok(data={
        "ok": failures == 0,
        "results": results,
        "total": len(results),
        "failed": failures,
    })


@router.get("/diagnostics")
def diagnose_all_providers(db: Session = Depends(get_db), _=Depends(requiere_capacidad("ia.administrar"))):
    """
    Ejecuta un diagnóstico de conectividad para cada proveedor IA configurado.
    Devuelve un semáforo (ok/warning/error) por proveedor con latencia y detalle de error.
    """
    providers = svc_list_providers(
        db,
        is_superadmin=_.is_superadmin,
        organization_id=_.organization_id,
    )
    if not providers:
        return APIResponse.ok(data={"total": 0, "healthy": 0, "warning": 0, "error": 0, "providers": []})

    results = [svc_diagnose_provider(p) for p in providers]
    healthy = sum(1 for r in results if r["status"] == "ok")
    warning = sum(1 for r in results if r["status"] == "warning")
    errors  = sum(1 for r in results if r["status"] == "error")
    return APIResponse.ok(data={
        "total": len(results),
        "healthy": healthy,
        "warning": warning,
        "error": errors,
        "providers": results,
    })


@router.get("/stats")
def get_stats(db: Session = Depends(get_db), _=Depends(get_current_user)):
    data = svc_get_stats(db, is_superadmin=_.is_superadmin, organization_id=_.organization_id)
    return APIResponse.ok(data={
        "providers": [_out(p) for p in data["providers"]],
        "by_module": [{"module": r.module, "calls": r.calls,
                       "tokens": r.tokens or 0, "cost": round(r.cost or 0, 4)} for r in data["logs"]],
        "total_cost": data["total_cost"],
        "total_requests": data["total_requests"],
    })


# ── Endpoint de chat unificado ────────────────────────────────────────────────
@router.post("/chat")
def unified_chat(data: dict = Body(...), db: Session = Depends(get_db),
    _rol: User = Depends(requiere_capacidad("ia.usar")),  # auditoria 2026-09: trabajo diario: la forma de la ruta manda sobre el fichero
                 cu=Depends(get_current_user)):
    """Chat unificado que usa el proveedor configurado."""
    messages = data.get("messages", [])
    if not messages:
        raise error_http(400, "campo_obligatorio", detail="messages requerido", campo="messages")
    system   = data.get("system", f"Eres NexusAssist, el asistente IA de {NOMBRE_DEL_PRODUCTO}.")
    module   = data.get("module", "chat")
    provider_id = data.get("provider_id")
    model    = data.get("model")

    text = call_ai(db, messages, system=system, module=module,
                   user_id=cu.id, model=model, provider_id=provider_id)
    return APIResponse.ok(data={"text": text, "module": module})
