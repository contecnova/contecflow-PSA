"""
ABAC — capa de política DISCRECIONAL. No es un control de autorización.

╔══════════════════════════════════════════════════════════════════════════════╗
║ `enforce_abac()` ES FAIL-OPEN. El nombre engaña: no "enforces" nada por sí.  ║
║ Si la organización no tiene políticas ABAC activas —el estado POR DEFECTO—   ║
║ retorna sin comprobar nada. Nunca es el único control de un endpoint.        ║
╚══════════════════════════════════════════════════════════════════════════════╝

Auditoría 2026-08 (hallazgo P1-25): el endpoint
`DELETE /organizations/{org_id}/remove-user/{user_id}` llamaba a `enforce_abac`
y era explotable entre tenants de todas formas. Alguien lo había puesto creyendo
que aislaba organizaciones. No lo hace, y esta cabecera existe para que no vuelva
a pasar.

── Dónde vive de verdad la autorización ──────────────────────────────────────
Tres capas, y hay que mirar las tres para saber si un endpoint está protegido:

1. AISLAMIENTO ENTRE TENANTS — estructural, automático y fail-closed.
   `app/db/session.py::TenantSession` filtra toda consulta ORM por organización.
   Cubre 390 de 391 modelos; el único exento (`Organization`) lo declara y sus
   rutas llevan guarda manual. Esta capa NO se puede olvidar: si un modelo no se
   puede aislar, la consulta lanza `TenantIsolationError`.

2. RBAC — explícito, por ruta o por servicio.
   `Depends(require_admin)` y compañía en la firma del endpoint, o bien una
   comprobación de rol dentro de la función de servicio (p. ej.
   `client_service.delete_client`). Las dos formas son válidas y ambas se usan;
   `tests/test_abac_coverage.py` mantiene el inventario de las rutas que sólo
   la tienen en el servicio, para que ese reparto sea deliberado.

3. ABAC — esta capa. Política de grano fino OPCIONAL que un cliente activa si
   quiere. Al no haber políticas, no restringe. Es correcto que sea así: es un
   añadido sobre 1 y 2, no un sustituto.

Uso: `enforce_abac(db, user, resource_type, resource_id, action=...)` al inicio
del endpoint, SIEMPRE además de 1 y 2 — nunca en lugar de ellas.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.user import User
from app.services.abac import ABACService
from app.core.errores import ErrorDeDominio

logger = logging.getLogger("contecflow.abac.enforce")


def _abac_no_aplica(user: User, resource_type: str) -> bool:
    """Los casos en los que ABAC no tiene nada que decir.

    - **Superadmin**: no pertenece a ninguna organización cuyas políticas
      aplicarle.
    - **Colaboración**: el chat tiene su propio modelo de pertenencia por canal
      y conversación, que es la fuente de verdad. Añadir ABAC encima produce
      403 falsos cuando el tipo de recurso no está registrado en las políticas
      activas.
    - **Sin organización**: desarrollo local y datos de arranque.
    """
    if getattr(user, "is_superadmin", False):
        return True
    if resource_type and resource_type.startswith("collaboration_"):
        return True
    return not getattr(user, "organization_id", None)


def _denegar(user: User, resource_type: str, resource_id, action: str,
             matched_policies: list) -> None:
    """Registra la denegación, cuenta la métrica y levanta el 403."""
    logger.info(
        "ABAC denied %s user=%s resource=%s/%s policies=%s",
        action, user.id, resource_type, resource_id, matched_policies,
    )
    try:
        from app.core.metrics import abac_denials_total

        abac_denials_total.labels(
            resource_type=resource_type or "unknown",
            action=action or "unknown",
        ).inc()
    except Exception:
        logger.debug("enforce_abac: fallo best-effort ignorado", exc_info=True)
    raise HTTPException(status_code=403, detail="Access denied")


def evaluar(db: Session, user: User, org_id, resource_type: str, resource_id, action: str,
            *, auditar: bool = True) -> tuple[bool, list, object]:
    """(permitido, políticas que aplicaron, detalle). Sin políticas activas: (True, [], None).

    Revisión 2026-11: la usan `enforce_abac` y el explicador de accesos (este
    con `auditar=False`, para no escribir decisiones que nadie tomó).
    """
    svc = ABACService(db=db, org_id=str(org_id))
    if not svc.list_policies(active_only=True):
        return True, [], None
    rol = user.role.value if hasattr(user.role, "value") else str(user.role or "employee")
    permitido, aplicadas, detalle = svc.evaluate_access(
        user_id=str(user.id), user_roles=[rol], resource_type=resource_type,
        resource_id=resource_id, action=action)
    if aplicadas and auditar:
        svc.audit_access_decision(user_id=str(user.id), decision=permitido, matched_policies=aplicadas,
                                  resource_type=resource_type, resource_id=resource_id, details=detalle)
    return permitido, aplicadas, detalle


def _evaluar_politicas(db: Session, user: User, org_id, resource_type: str,
                       resource_id, action: str) -> None:
    """Evalúa las políticas activas y levanta 403 si deniegan."""
    permitido, aplicadas, _detalle = evaluar(db, user, org_id, resource_type, resource_id, action)
    # Fail-open: sin políticas que encajen, el RBAC del endpoint ya es el guardia.
    if not permitido and aplicadas:
        _denegar(user, resource_type, resource_id, action, aplicadas)


def enforce_abac(
    db: Session,
    user: User,
    resource_type: str,
    resource_id: Optional[str] = None,
    action: str = "read",
) -> None:
    """Aplica las políticas ABAC de la organización, si tiene alguna activa.

    FAIL-OPEN: sin políticas activas no comprueba nada y deja pasar. No sirve
    como control de autorización por sí solo — ver la cabecera del módulo.

    Cuando SÍ hay políticas y alguna encaja, se aplica la evaluación
    permitir/denegar normal y una denegación lanza 403. Si la evaluación
    revienta, se **deniega** (fail-closed): un motor de políticas roto no debe
    conceder acceso.
    """
    if _abac_no_aplica(user, resource_type):
        return

    try:
        _evaluar_politicas(
            db, user, getattr(user, "organization_id", None),
            resource_type, resource_id, action,
        )
    except (HTTPException, ErrorDeDominio):
        raise
    except Exception as exc:
        logger.error(
            "ABAC evaluation error for %s/%s — denying by default: %s",
            resource_type, resource_id, exc, exc_info=True,
        )
        raise HTTPException(
            status_code=403,
            detail="Access temporarily unavailable — please try again or contact support",
        )
