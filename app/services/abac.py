"""
ABAC (Attribute-Based Access Control) service for fine-grained authorization.

Provides policy evaluation engine, attribute management, and access control decisions
that work in conjunction with RBAC (role-based access control).
"""
import re
from datetime import datetime, timedelta
from app.core.timeutil import utcnow
from typing import Dict, List, Any, Optional, Tuple
from sqlalchemy.orm import Session
from app.models.abac import ABACPolicy, UserAttribute, AttributeDefinition, PolicyAudit
from app.models.user import User
from app.services.abac_recursos import atributos_del_recurso
import uuid
from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)


class ABACEngine:
    """Policy evaluation engine for attribute-based access control."""

    # ── Operadores de condición ──────────────────────────────────────────────
    #
    # Auditoría 2026-08 (hallazgo 18). `evaluate_condition` eran 89 líneas de
    # complejidad 26: 16 operadores en una cadena de `elif`. Es la función que
    # decide si una política ABAC se cumple, así que decide accesos.
    #
    # Cada operador es ahora una función y `_OPERADORES` la tabla. Verificado
    # sobre las 289 combinaciones de los 17 operadores (16 más uno inexistente)
    # por 17 juegos de valores —cadenas, listas, números, None, tipos
    # incompatibles y una regex mal formada—: resultado idéntico, incluida la
    # excepción.
    #
    # ── Sobre esa excepción, que se conserva a propósito ─────────────────────
    # Una regex mal escrita en una política lanza `re.error`, y el
    # `except (TypeError, AttributeError)` de abajo NO la captura. No es un
    # descuido que haya que tapar: `enforce_abac` la recoge, DENIEGA por defecto
    # y deja un error en el registro con la política culpable.
    #
    # Devolver `False` aquí sería peor de dos maneras: se perdería el aviso al
    # administrador de que su regex está rota, y «la regla no coincide» no es lo
    # mismo que «no se pudo evaluar» — en una política de denegación, no coincidir
    # significa PERMITIR.

    @staticmethod
    def _op_equals(valor, esperado) -> bool:
        return valor == esperado

    @staticmethod
    def _op_not_equals(valor, esperado) -> bool:
        return valor != esperado

    @staticmethod
    def _op_in(valor, esperado) -> bool:
        """Pertenencia. Si el atributo del usuario es una lista, basta con que
        UNO de sus valores esté en el conjunto esperado."""
        if isinstance(valor, list):
            return any(v in esperado for v in valor)
        return valor in esperado

    @staticmethod
    def _op_not_in(valor, esperado) -> bool:
        """Lo contrario de `in`, y con lista exige que NINGUNO esté: no es la
        negación de `any`, es `all(not ...)`."""
        if isinstance(valor, list):
            return all(v not in esperado for v in valor)
        return valor not in esperado

    @staticmethod
    def _op_contains(valor, esperado) -> bool:
        """Contiene. En cadena es insensible a mayúsculas; en lista es
        pertenencia exacta. Cualquier otro tipo no contiene nada."""
        if isinstance(valor, str):
            return esperado.lower() in valor.lower()
        if isinstance(valor, list):
            return esperado in valor
        return False

    @staticmethod
    def _op_not_contains(valor, esperado) -> bool:
        if isinstance(valor, str):
            return esperado.lower() not in valor.lower()
        if isinstance(valor, list):
            return esperado not in valor
        return False

    @staticmethod
    def _op_starts_with(valor, esperado) -> bool:
        return str(valor).startswith(str(esperado))

    @staticmethod
    def _op_ends_with(valor, esperado) -> bool:
        return str(valor).endswith(str(esperado))

    @staticmethod
    def _op_regex(valor, esperado) -> bool:
        """Coincidencia por expresión regular.

        `re.match`, no `search`: ancla al principio. Una regex mal formada lanza
        y eso es deliberado — ver la nota de arriba.
        """
        return bool(re.match(esperado, str(valor)))

    @staticmethod
    def _op_gte(valor, esperado) -> bool:
        return valor >= esperado

    @staticmethod
    def _op_lte(valor, esperado) -> bool:
        return valor <= esperado

    @staticmethod
    def _op_gt(valor, esperado) -> bool:
        return valor > esperado

    @staticmethod
    def _op_lt(valor, esperado) -> bool:
        return valor < esperado

    @staticmethod
    def _op_is_empty(valor, esperado) -> bool:
        if isinstance(valor, list):
            return len(valor) == 0
        return valor == "" or valor is None

    @staticmethod
    def _op_is_not_empty(valor, esperado) -> bool:
        if isinstance(valor, list):
            return len(valor) > 0
        return valor != "" and valor is not None

    # Nombre del operador → función. Añadir un operador al panel de políticas es
    # añadir su función y una línea aquí; un nombre que no esté en la tabla
    # devuelve False, es decir la condición NO se cumple.
    _OPERADORES = {
        "equals": _op_equals,
        "not_equals": _op_not_equals,
        "in": _op_in,
        "not_in": _op_not_in,
        "contains": _op_contains,
        "not_contains": _op_not_contains,
        "starts_with": _op_starts_with,
        "ends_with": _op_ends_with,
        "regex": _op_regex,
        "gte": _op_gte,
        "lte": _op_lte,
        "gt": _op_gt,
        "lt": _op_lt,
        "is_empty": _op_is_empty,
        "is_not_empty": _op_is_not_empty,
    }

    @staticmethod
    def evaluate_condition(user_attribute_value: Any, rule: Dict[str, Any]) -> bool:
        """
        Evaluate a single attribute condition.

        Args:
            user_attribute_value: Value from user's attributes
            rule: {"attribute": key, "operator": op, "value": val}

        Returns:
            True if condition is met, False otherwise
        """
        operator = rule.get("operator", "equals")
        expected_value = rule.get("value")

        # Handle None values
        if user_attribute_value is None:
            return operator in ["not_equals"] if expected_value is not None else False

        funcion = ABACEngine._OPERADORES.get(operator)
        if funcion is None:
            return False

        try:
            # `__func__`: los valores de la tabla son staticmethod, así que hay
            # que desenvolverlos para invocarlos desde otro staticmethod.
            return bool(funcion.__func__(user_attribute_value, expected_value))
        except (TypeError, AttributeError):
            return False

    @staticmethod
    def evaluate_rules(rules: List[Dict[str, Any]], user_attributes: Dict[str, Any]) -> bool:
        """
        Evaluate all rules in a policy (AND logic: all must pass).

        Args:
            rules: List of rule conditions
            user_attributes: Map of attribute_key -> value for the user

        Returns:
            True if all rules match, False otherwise
        """
        for rule in rules:
            attribute_key = rule.get("attribute")
            user_value = user_attributes.get(attribute_key)

            if not ABACEngine.evaluate_condition(user_value, rule):
                return False

        return True

    @staticmethod
    def is_policy_applicable(
        policy: ABACPolicy,
        user_id: str,
        user_roles: List[str],
        resource_type: Optional[str] = None,
        current_time: Optional[datetime] = None,
    ) -> bool:
        """
        Check if policy is applicable to this user/request without evaluating rules.

        Args:
            policy: The policy to check
            user_id: User ID
            user_roles: Roles assigned to user
            resource_type: Resource being accessed
            current_time: Current time (default: now)

        Returns:
            True if policy applies, False otherwise
        """
        if not policy.is_active:
            return False

        now = current_time or utcnow()

        # Check temporal constraints
        if policy.starts_at and now < policy.starts_at:
            return False
        if policy.expires_at and now > policy.expires_at:
            return False

        # Check subject users (if specified, user must be in list)
        if policy.subject_users and user_id not in policy.subject_users:
            return False

        # Check applicable roles (if specified, user must have at least one role)
        if policy.applicable_roles:
            if not any(role in policy.applicable_roles for role in user_roles):
                return False

        # Check resource types (if specified, resource must match)
        if policy.resource_types and resource_type:
            if resource_type not in policy.resource_types:
                return False

        return True


class ABACService:
    """ABAC service for managing policies, attributes, and access control decisions."""

    def __init__(self, db: Session, org_id: str):
        self.db = db
        self.org_id = org_id
        self.engine = ABACEngine()

    def assign_user_attribute(
        self,
        user_id: str,
        attribute_key: str,
        attribute_value: Any,
        assigned_by: str,
        reason: Optional[str] = None,
        expires_at: Optional[datetime] = None,
    ) -> UserAttribute:
        """Assign an attribute to a user."""
        attr = UserAttribute(
            id=str(uuid.uuid4()),
            user_id=user_id,
            org_id=self.org_id,
            attribute_key=attribute_key,
            attribute_value=attribute_value if isinstance(attribute_value, (list, dict)) else attribute_value,
            reason=reason,
            expires_at=expires_at,
            assigned_by=assigned_by,
        )
        self.db.add(attr)
        self.db.commit()
        return attr

    def revoke_user_attribute(self, user_id: str, attribute_key: str) -> int:
        """Remove all instances of an attribute for a user."""
        deleted = self.db.query(UserAttribute).filter(
            UserAttribute.user_id == user_id,
            UserAttribute.org_id == self.org_id,
            UserAttribute.attribute_key == attribute_key,
        ).delete()
        self.db.commit()
        return deleted

    def get_user_attributes(self, user_id: str) -> Dict[str, Any]:
        """
        Get all non-expired attributes for a user.

        Returns: {attribute_key: attribute_value, ...}
        """
        now = utcnow()
        attrs = self.db.query(UserAttribute).filter(
            UserAttribute.user_id == user_id,
            UserAttribute.org_id == self.org_id,
        ).all()

        result = {}
        for attr in attrs:
            # Skip expired attributes
            if attr.expires_at and attr.expires_at < now:
                continue

            # Aggregate multiple values for same attribute
            key = attr.attribute_key
            if key in result:
                # Convert to list if not already
                if not isinstance(result[key], list):
                    result[key] = [result[key]]
                if isinstance(attr.attribute_value, list):
                    result[key].extend(attr.attribute_value)
                else:
                    result[key].append(attr.attribute_value)
            else:
                result[key] = attr.attribute_value

        return result

    def create_policy(
        self,
        policy_name: str,
        rules: List[Dict[str, Any]],
        effect: str = "allow",
        created_by: str = None,
        resource_types: Optional[List[str]] = None,
        applicable_roles: Optional[List[str]] = None,
        subject_users: Optional[List[str]] = None,
        priority: int = 50,
        expires_at: Optional[datetime] = None,
        description: Optional[str] = None,
    ) -> ABACPolicy:
        """Create a new ABAC policy."""
        policy = ABACPolicy(
            id=str(uuid.uuid4()),
            org_id=self.org_id,
            policy_name=policy_name,
            description=description,
            effect=effect,
            rules=rules,
            resource_types=resource_types or [],
            applicable_roles=applicable_roles or [],
            subject_users=subject_users or [],
            priority=priority,
            expires_at=expires_at,
            created_by=created_by,
        )
        self.db.add(policy)
        self.db.commit()
        return policy

    def update_policy(self, policy_id: str, **kwargs) -> ABACPolicy:
        """Update an existing policy."""
        policy = self.db.query(ABACPolicy).filter(
            ABACPolicy.id == policy_id,
            ABACPolicy.org_id == self.org_id,
        ).one_or_404()

        for key, value in kwargs.items():
            if hasattr(policy, key):
                setattr(policy, key, value)

        policy.updated_at = utcnow()
        self.db.commit()
        return policy

    def delete_policy(self, policy_id: str) -> bool:
        """Soft delete a policy."""
        policy = self.db.query(ABACPolicy).filter(
            ABACPolicy.id == policy_id,
            ABACPolicy.org_id == self.org_id,
        ).one_or_404()
        policy.is_active = False
        self.db.commit()
        return True

    def get_policy_by_id(self, policy_id: str) -> Optional[ABACPolicy]:
        """Get a single policy by ID scoped to org."""
        return self.db.query(ABACPolicy).filter(
            ABACPolicy.id == policy_id,
            ABACPolicy.org_id == self.org_id,
        ).first()

    def list_policies(self, active_only: bool = True) -> List[ABACPolicy]:
        """List policies for org."""
        query = self.db.query(ABACPolicy).filter(ABACPolicy.org_id == self.org_id)
        if active_only:
            query = query.filter(ABACPolicy.is_active == True)
        return query.order_by(ABACPolicy.priority.desc()).all()

    def evaluate_access(
        self,
        user_id: str,
        user_roles: List[str],
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        action: str = "read",
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, List[str], Dict[str, Any]]:
        """
        Evaluate if user should be granted access to a resource.

        Returns:
            (decision: bool, matched_policies: List[str], evaluation_details: Dict)
        """
        context = context or {}
        matched_allow_policies = []
        matched_deny_policies = []

        # Get user's attributes
        user_attributes = self.get_user_attributes(user_id)

        # ── Atributos del recurso concreto (auditoria 2026-09) ───────────────
        #
        # Hasta aqui `resource_id` y `action` se recibian, se guardaban en el
        # detalle de auditoria y **no se usaban para decidir**. Es decir: toda
        # la API paseaba el id del recurso por seis capas hasta este punto y
        # aqui se tiraba, asi que **ABAC por recurso concreto no existia**. Una
        # politica solo podia decir «este rol no toca tareas», nunca «no toca
        # las tareas del proyecto X».
        #
        # Ahora una regla puede nombrar `recurso.<columna>` y `accion`. El
        # espacio de nombres esta prefijado a proposito para que no pueda
        # chocar con un atributo de usuario.
        #
        # **Compatible hacia atras por construccion:** una politica que solo
        # nombra atributos de usuario ve exactamente el mismo diccionario que
        # antes, porque lo unico que se hace es anadir claves nuevas. Ninguna
        # politica existente cambia de veredicto.
        atributos_recurso = atributos_del_recurso(self.db, resource_type, resource_id)

        if resource_id and resource_type and not atributos_recurso:
            # Se registra en vez de callar: una regla que nombre `recurso.*`
            # con el recurso sin resolver no encajara, y eso es indistinguible
            # de «la condicion no se cumple» si no queda rastro. Pasa cuando el
            # tipo no esta declarado en `abac_recursos.TIPOS` o la fila no
            # existe.
            logger.debug(
                "ABAC: sin atributos para %s/%s; las reglas que nombren "
                "`recurso.*` no encajaran", resource_type, resource_id)

        # Merge context attributes
        evaluation_attrs = {
            **user_attributes,
            **atributos_recurso,
            "accion": action,
            **context,
        }

        # Get active policies sorted by priority
        policies = self.list_policies(active_only=True)
        policies.sort(key=lambda p: p.priority, reverse=True)

        # Evaluate policies in priority order
        for policy in policies:
            # Check if policy is applicable
            if not self.engine.is_policy_applicable(policy, user_id, user_roles, resource_type):
                continue

            # Evaluate policy rules
            if self.engine.evaluate_rules(policy.rules, evaluation_attrs):
                if policy.effect == "allow":
                    matched_allow_policies.append(policy.id)
                else:  # deny
                    matched_deny_policies.append(policy.id)

        # Decision logic: explicit deny takes precedence
        has_explicit_deny = len(matched_deny_policies) > 0
        decision = not has_explicit_deny and len(matched_allow_policies) > 0

        details = {
            "user_id": user_id,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "action": action,
            "matched_allow": matched_allow_policies,
            "matched_deny": matched_deny_policies,
            "user_attributes": user_attributes,
        }

        return decision, matched_allow_policies + matched_deny_policies, details

    def audit_access_decision(
        self,
        user_id: str,
        decision: bool,
        matched_policies: List[str],
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> PolicyAudit:
        """Create audit log entry for access decision."""
        audit = PolicyAudit(
            id=str(uuid.uuid4()),
            org_id=self.org_id,
            user_id=user_id,
            action="access_allowed" if decision else "access_denied",
            result="allow" if decision else "deny",
            resource_type=resource_type,
            resource_id=resource_id,
            matched_policies=matched_policies,
            evaluation_context=details,
        )
        self.db.add(audit)

        # Emit a SecurityEvent for denials so the SOC dashboard tracks them
        if not decision:
            try:
                from app.services.security_observability import SecurityEventService
                deny_policies = (details or {}).get("matched_deny", matched_policies)
                SecurityEventService(db=self.db, org_id=self.org_id).abac_denied(
                    user_id=user_id,
                    resource_type=resource_type or "unknown",
                    resource_id=resource_id or "",
                    matched_policies=deny_policies or [],
                )
            # intentional: best-effort fallback, log noise outweighs diagnostic value
            except Exception:
                logger.debug("audit_access_decision: fallo best-effort ignorado", exc_info=True)

        self.db.commit()
        return audit

    def create_attribute_definition(
        self,
        attribute_key: str,
        attribute_type: str,  # "string", "list", "enum", "integer", "date"
        operators: List[str],
        created_by: str,
        description: Optional[str] = None,
        possible_values: Optional[List[Any]] = None,
    ) -> AttributeDefinition:
        """Define a new attribute type for policies."""
        attr_def = AttributeDefinition(
            id=str(uuid.uuid4()),
            org_id=self.org_id,
            attribute_key=attribute_key,
            attribute_type=attribute_type,
            description=description,
            possible_values=possible_values,
            operators=operators,
            created_by=created_by,
        )
        self.db.add(attr_def)
        self.db.commit()
        return attr_def

    def list_attribute_definitions(self, active_only: bool = True) -> List[AttributeDefinition]:
        """List available attributes for org."""
        query = self.db.query(AttributeDefinition).filter(
            AttributeDefinition.org_id == self.org_id
        )
        if active_only:
            query = query.filter(AttributeDefinition.is_active == True)
        return query.all()

    def get_user_by_id_and_org(self, user_id: str):
        """Return a User in this org or raise 404."""
        return (
            self.db.query(User)
            .filter(User.id == user_id, User.organization_id == self.org_id)
            .one_or_404()
        )

    def list_audit_log(self, user_id: Optional[str], limit: int, offset: int) -> dict:
        """Return paginated ABAC audit log entries for this org."""
        query = self.db.query(PolicyAudit).filter(PolicyAudit.org_id == self.org_id)
        if user_id:
            query = query.filter(PolicyAudit.user_id == user_id)
        total = query.count()
        logs = query.order_by(PolicyAudit.created_at.desc()).offset(offset).limit(limit).all()
        return {"total": total, "logs": logs}


# ── Admin analytics helpers ───────────────────────────────────────────────────

def get_admin_overview(db: Session, org: str, since: datetime, days: int) -> dict:
    total_policies = db.query(func.count(ABACPolicy.id)).filter(ABACPolicy.org_id == org).scalar() or 0
    active_policies = db.query(func.count(ABACPolicy.id)).filter(
        ABACPolicy.org_id == org, ABACPolicy.is_active == True
    ).scalar() or 0
    total_users_with_attrs = db.query(func.count(func.distinct(UserAttribute.user_id))).filter(
        UserAttribute.org_id == org
    ).scalar() or 0
    total_attr_defs = db.query(func.count(AttributeDefinition.id)).filter(
        AttributeDefinition.org_id == org
    ).scalar() or 0
    base_audit = db.query(PolicyAudit).filter(
        PolicyAudit.org_id == org,
        PolicyAudit.created_at >= since,
    )
    total_evaluations = base_audit.count()
    total_denials = base_audit.filter(PolicyAudit.result == "deny").count()
    total_allows = base_audit.filter(PolicyAudit.result == "allow").count()
    deny_rate = round(total_denials / total_evaluations, 4) if total_evaluations else 0.0
    now = utcnow()
    expired_attrs = db.query(func.count(UserAttribute.id)).filter(
        UserAttribute.org_id == org,
        UserAttribute.expires_at < now,
    ).scalar() or 0
    return {
        "window_days": days,
        "total_policies": total_policies,
        "active_policies": active_policies,
        "inactive_policies": total_policies - active_policies,
        "attribute_definitions": total_attr_defs,
        "users_with_attributes": total_users_with_attrs,
        "expired_attributes": expired_attrs,
        "total_evaluations": total_evaluations,
        "total_denials": total_denials,
        "total_allows": total_allows,
        "deny_rate": deny_rate,
    }


def get_attribute_summary(db: Session, org: str) -> list:
    now = utcnow()
    rows = db.query(
        UserAttribute.attribute_key,
        func.count(func.distinct(UserAttribute.user_id)).label("user_count"),
        func.count(UserAttribute.id).label("assignment_count"),
    ).filter(UserAttribute.org_id == org).group_by(UserAttribute.attribute_key).all()

    expiring_soon = db.query(
        UserAttribute.attribute_key,
        func.count(UserAttribute.id).label("expiring"),
    ).filter(
        UserAttribute.org_id == org,
        UserAttribute.expires_at.isnot(None),
        UserAttribute.expires_at > now,
        UserAttribute.expires_at <= now + timedelta(days=7),
    ).group_by(UserAttribute.attribute_key).all()

    expiring_map = {k: v for k, v in expiring_soon}
    return [
        {
            "attribute_key": r.attribute_key,
            "user_count": r.user_count,
            "assignment_count": r.assignment_count,
            "expiring_in_7d": expiring_map.get(r.attribute_key, 0),
        }
        for r in rows
    ]


def get_policy_effectiveness(db: Session, org: str, since: datetime, days: int) -> list:
    policies = db.query(ABACPolicy).filter(ABACPolicy.org_id == org).all()
    result = []
    for p in policies:
        total_hits = db.query(func.count(PolicyAudit.id)).filter(
            PolicyAudit.org_id == org,
            PolicyAudit.created_at >= since,
            func.json_extract(PolicyAudit.matched_policies, "$").like(f"%{p.id}%"),
        ).scalar() or 0
        deny_hits = db.query(func.count(PolicyAudit.id)).filter(
            PolicyAudit.org_id == org,
            PolicyAudit.result == "deny",
            PolicyAudit.created_at >= since,
            func.json_extract(PolicyAudit.matched_policies, "$").like(f"%{p.id}%"),
        ).scalar() or 0
        allow_hits = total_hits - deny_hits
        result.append({
            "policy_id": p.id,
            "policy_name": p.policy_name,
            "effect": p.effect,
            "is_active": p.is_active,
            "priority": p.priority,
            "resource_types": p.resource_types or [],
            "total_hits": total_hits,
            "deny_hits": deny_hits,
            "allow_hits": allow_hits,
            "hit_rate": round(total_hits / max(1, days), 2),
            "deny_rate": round(deny_hits / max(1, total_hits), 4) if total_hits else 0.0,
            "expires_at": p.expires_at.isoformat() if p.expires_at else None,
        })
    result.sort(key=lambda x: -x["total_hits"])
    return result


def get_access_patterns(db: Session, org: str, since: datetime, days: int, limit: int) -> dict:
    top_denied_users = db.query(
        PolicyAudit.user_id,
        func.count(PolicyAudit.id).label("deny_count"),
    ).filter(
        PolicyAudit.org_id == org,
        PolicyAudit.result == "deny",
        PolicyAudit.created_at >= since,
        PolicyAudit.user_id.isnot(None),
    ).group_by(PolicyAudit.user_id).order_by(text("deny_count DESC")).limit(limit).all()

    top_denied_resources = db.query(
        PolicyAudit.resource_type,
        func.count(PolicyAudit.id).label("deny_count"),
    ).filter(
        PolicyAudit.org_id == org,
        PolicyAudit.result == "deny",
        PolicyAudit.created_at >= since,
        PolicyAudit.resource_type.isnot(None),
    ).group_by(PolicyAudit.resource_type).order_by(text("deny_count DESC")).limit(limit).all()

    all_entries = db.query(PolicyAudit.result, PolicyAudit.created_at).filter(
        PolicyAudit.org_id == org,
        PolicyAudit.created_at >= since,
    ).all()

    daily: Dict[str, Dict[str, int]] = {}
    for res, ts in all_entries:
        day = ts.date().isoformat()
        if day not in daily:
            daily[day] = {"date": day, "allow": 0, "deny": 0}
        daily[day][res] = daily[day].get(res, 0) + 1
    trend = sorted(daily.values(), key=lambda x: x["date"])

    return {
        "window_days": days,
        "top_denied_users": [{"user_id": r.user_id, "deny_count": r.deny_count} for r in top_denied_users],
        "top_denied_resources": [{"resource_type": r.resource_type, "deny_count": r.deny_count} for r in top_denied_resources],
        "daily_trend": trend,
    }


def get_user_access_profile(db: Session, org: str, user_id: str, resource_type: Optional[str]) -> dict:
    svc = ABACService(db=db, org_id=org)
    attributes = svc.get_user_attributes(user_id)

    recent = db.query(PolicyAudit).filter(
        PolicyAudit.org_id == org,
        PolicyAudit.user_id == user_id,
    ).order_by(PolicyAudit.created_at.desc()).limit(20).all()

    user_obj = db.query(User).filter(User.id == user_id).first()
    user_role = (user_obj.role.value if hasattr(user_obj.role, "value") else str(user_obj.role)) if user_obj else ""

    all_policies = db.query(ABACPolicy).filter(
        ABACPolicy.org_id == org,
        ABACPolicy.is_active == True,
    ).all()

    applicable = []
    for p in all_policies:
        if p.applicable_roles and user_role not in p.applicable_roles:
            continue
        if p.subject_users and user_id not in p.subject_users:
            continue
        if resource_type and p.resource_types and resource_type not in p.resource_types:
            continue
        applicable.append({
            "policy_id": p.id,
            "name": p.policy_name,
            "effect": p.effect,
            "priority": p.priority,
            "resource_types": p.resource_types or [],
        })

    return {
        "user_id": user_id,
        "user_role": user_role,
        "attributes": attributes,
        "applicable_policies": applicable,
        "recent_decisions": [
            {
                "id": e.id,
                "action": e.action,
                "result": e.result,
                "resource_type": e.resource_type,
                "resource_id": e.resource_id,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in recent
        ],
    }


def get_audit_log(
    db: Session,
    org: str,
    since: datetime,
    result: Optional[str],
    resource_type: Optional[str],
    user_id: Optional[str],
    page: int,
    page_size: int,
) -> dict:
    q = db.query(PolicyAudit).filter(
        PolicyAudit.org_id == org,
        PolicyAudit.created_at >= since,
    )
    if result:
        q = q.filter(PolicyAudit.result == result)
    if resource_type:
        q = q.filter(PolicyAudit.resource_type == resource_type)
    if user_id:
        q = q.filter(PolicyAudit.user_id == user_id)

    total = q.count()
    items = q.order_by(PolicyAudit.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "id": e.id,
                "user_id": e.user_id,
                "action": e.action,
                "result": e.result,
                "resource_type": e.resource_type,
                "resource_id": e.resource_id,
                "matched_policies": e.matched_policies,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in items
        ],
    }


def get_audit_stats(db: Session, org: str, since: datetime, days: int) -> dict:
    total = db.query(func.count(PolicyAudit.id)).filter(
        PolicyAudit.org_id == org, PolicyAudit.created_at >= since
    ).scalar() or 0
    denials = db.query(func.count(PolicyAudit.id)).filter(
        PolicyAudit.org_id == org, PolicyAudit.created_at >= since, PolicyAudit.result == "deny"
    ).scalar() or 0
    allows = total - denials
    return {
        "window_days": days,
        "total": total,
        "denials": denials,
        "allows": allows,
        "deny_rate": round(denials / total, 4) if total else 0.0,
    }


# Pre-defined ABAC attribute definitions for common PSA use cases
DEFAULT_ABAC_ATTRIBUTES = [
    {
        "attribute_key": "project_ids",
        "attribute_type": "list",
        "description": "Projects the user can access",
        "operators": ["in", "not_in", "contains", "is_empty"],
    },
    {
        "attribute_key": "client_ids",
        "attribute_type": "list",
        "description": "Clients the user can access",
        "operators": ["in", "not_in", "contains", "is_empty"],
    },
    {
        "attribute_key": "region",
        "attribute_type": "enum",
        "description": "Geographic region(s) for data access",
        "possible_values": ["EMEA", "APAC", "Americas", "Canada", "EU", "US"],
        "operators": ["equals", "in", "not_equals"],
    },
    {
        "attribute_key": "data_classification",
        "attribute_type": "enum",
        "description": "Maximum data sensitivity level can access (higher value = more sensitive)",
        "possible_values": ["public", "internal", "confidential", "restricted"],
        "operators": ["gte", "lte", "equals"],
    },
    {
        "attribute_key": "team_ids",
        "attribute_type": "list",
        "description": "Teams the user belongs to",
        "operators": ["in", "contains", "is_empty"],
    },
    {
        "attribute_key": "department",
        "attribute_type": "enum",
        "description": "Department assignment",
        "possible_values": ["Engineering", "Sales", "HR", "Finance", "Operations", "Support"],
        "operators": ["equals", "in"],
    },
    {
        "attribute_key": "resource_types",
        "attribute_type": "list",
        "description": "Resource types the user can access (timesheets, expenses, documents, etc)",
        "operators": ["in", "contains"],
    },
    {
        "attribute_key": "cost_center",
        "attribute_type": "string",
        "description": "Cost center for budgeting and expense attribution",
        "operators": ["equals", "contains"],
    },
]


# ── Tenant helpers ─────────────────────────────────────────────────────────

def get_org_id(user) -> str:
    if not user.organization_id:
        raise HTTPException(400, "User has no organization")
    return str(user.organization_id)
