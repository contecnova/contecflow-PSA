"""
ABAC resource enforcement helpers.

Call `enforce_abac(db, user, resource_type, resource_id)` at the start of any
endpoint that needs ABAC-level access control in addition to RBAC.

If the user has no active ABAC policies for this org, access is allowed by
default (fail-open) so existing RBAC guards remain in effect.  If at least one
ABAC policy matches, the usual allow/deny evaluation applies.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.user import User
from app.services.abac import ABACService

logger = logging.getLogger("contecflow.abac.enforce")


def enforce_abac(
    db: Session,
    user: User,
    resource_type: str,
    resource_id: Optional[str] = None,
    action: str = "read",
) -> None:
    """
    Raise HTTP 403 if the current user is denied by ABAC policies.

    This is a no-op when:
    - The user has no organization (local dev / seed data)
    - There are no ABAC policies for the org (fail-open)
    - The user is a superadmin
    - The resource is a collaboration domain resource (chat tiene su propio
      modelo de membresía por canal/conversación que es la fuente de verdad)

    Any exception from the ABAC service is logged and results in a 403
    (fail-closed) to avoid granting access when policy evaluation is broken.
    """
    if getattr(user, "is_superadmin", False):
        return

    # Collaboration: la membresía por canal/conversación ya es la autoridad.
    # ABAC adicional aquí no aplica porque introduce 403 falsos cuando el
    # resource_type no está registrado en las políticas activas.
    if resource_type and resource_type.startswith("collaboration_"):
        return

    org_id = getattr(user, "organization_id", None)
    if not org_id:
        return

    try:
        svc = ABACService(db=db, org_id=str(org_id))

        # Early-out: si la organización no tiene ninguna política activa, el
        # resultado sería fail-open de todas formas. Salir aquí evita cargar los
        # atributos del usuario y, sobre todo, evita el INSERT+COMMIT de auditoría.
        # Importa desde que ABAC_ROUTE_REGISTRY cubre toda la API (auditoría
        # 2026-07 §1.5): sin este corte, CADA request autenticada escribiría una
        # fila en PolicyAudit.
        if not svc.list_policies(active_only=True):
            return

        user_role = user.role.value if hasattr(user.role, "value") else str(user.role or "employee")
        user_roles = [user_role]

        allowed, matched_policies, details = svc.evaluate_access(
            user_id       = str(user.id),
            user_roles    = user_roles,
            resource_type = resource_type,
            resource_id   = resource_id,
        )

        # Auditar solo cuando alguna política ha aplicado de verdad. Un
        # "access_allowed" con matched_policies=[] es el camino fail-open: no
        # aporta señal de seguridad y, con cobertura total del registro, generaría
        # una fila de auditoría por request. Las denegaciones siempre se auditan,
        # porque una denegación implica que hubo política que matcheó.
        if matched_policies:
            svc.audit_access_decision(
                user_id         = str(user.id),
                decision        = allowed,
                matched_policies= matched_policies,
                resource_type   = resource_type,
                resource_id     = resource_id,
                details         = details,
            )

        if not allowed:
            # Fail-open: if no policies matched at all, RBAC already guards the endpoint
            if not matched_policies:
                return
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
            raise HTTPException(
                status_code=403,
                detail="Access denied",
            )

    # intentional: chained re-raise preserves context
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "ABAC evaluation error for %s/%s — denying by default: %s",
            resource_type, resource_id, exc, exc_info=True,
        )
        raise HTTPException(
            status_code=403,
            detail="Access temporarily unavailable — please try again or contact support",
        )
