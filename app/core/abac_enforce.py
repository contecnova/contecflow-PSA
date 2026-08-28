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

logger = logging.getLogger("contecflow.abac.enforce")


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

    Es un no-op cuando:
    - la organización no tiene políticas ABAC activas  ← EL CASO POR DEFECTO
    - el usuario no tiene organización (dev local / datos de seed)
    - el usuario es superadmin
    - el recurso es del dominio de colaboración (chat tiene su propio modelo de
      membresía por canal/conversación, que es la fuente de verdad)

    Cuando SÍ hay políticas y alguna matchea, se aplica la evaluación
    allow/deny normal y una denegación lanza 403. Si la evaluación de políticas
    revienta, se deniega (fail-closed): un motor de políticas roto no debe
    conceder acceso.
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
        # Importa desde que la cobertura ABAC abarca toda la API (auditoría
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
    except Exception as exc:
        logger.error(
            "ABAC evaluation error for %s/%s — denying by default: %s",
            resource_type, resource_id, exc, exc_info=True,
        )
        raise HTTPException(
            status_code=403,
            detail="Access temporarily unavailable — please try again or contact support",
        )
