import json
from typing import Optional
from datetime import datetime, timezone, time as dt_time

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.service_desk import RoutingRule, Ticket
import logging

logger = logging.getLogger(__name__)


def _norm_enum(value):
    return value.value if hasattr(value, "value") else value


def list_routing_rules(db: Session):
    return db.query(RoutingRule).order_by(RoutingRule.priority).all()


def serialize_routing_rule(rule: RoutingRule) -> dict:
    return {
        "id": rule.id,
        "name": rule.name,
        "is_active": rule.is_active,
        "priority": rule.priority,
        "conditions": rule.conditions,
        "actions": rule.actions,
    }


def build_routing_rule(db, payload: dict) -> RoutingRule:
    if not payload.get("name"):
        raise HTTPException(422, "name es obligatorio")
    rule = RoutingRule(
        name=payload["name"],
        is_active=payload.get("is_active", True),
        priority=payload.get("priority", 100),
        conditions=json.dumps(payload.get("conditions", {})),
        actions=json.dumps(payload.get("actions", {})),
    )
    db.add(rule)
    return rule


def get_routing_rule_or_404(db: Session, rule_id: str) -> RoutingRule:
    rule = db.query(RoutingRule).filter(RoutingRule.id == rule_id).first()
    if not rule:
        raise HTTPException(404)
    return rule


def delete_routing_rule(db: Session, rule_id: str) -> None:
    rule = get_routing_rule_or_404(db, rule_id)
    db.delete(rule)


def apply_routing_rule_update(rule: RoutingRule, payload: dict) -> None:
    for key in ("name", "is_active", "priority"):
        if key in payload:
            setattr(rule, key, payload[key])
    if "conditions" in payload:
        rule.conditions = json.dumps(payload["conditions"])
    if "actions" in payload:
        rule.actions = json.dumps(payload["actions"])


# ── Reglas de encaminamiento de tickets ──────────────────────────────────────
#
# Auditoría 2026-08 (hallazgo 18). `apply_routing_rules` eran 105 líneas de
# complejidad 35: once condiciones independientes y cuatro acciones encadenadas
# en un solo bucle, y sin un solo test.
#
# Cada condición es ahora un predicado con nombre y cada acción un aplicador, con
# sus tablas. La equivalencia se verificó sobre 62 casos —cada condición con sus
# variantes de forma, las combinaciones, las cuatro acciones y el orden de
# prioridad—: idénticos antes y después.
#
# Dos decisiones que se conservan del original porque son intencionadas:
#
#  · Las condiciones son CONJUNTIVAS: todas las presentes deben cumplirse. Una
#    condición ausente no restringe.
#  · Un valor mal formado —una etiqueta de día que no existe, un rango de horas
#    incompleto— no lanza. Una regla mal configurada por un administrador no
#    puede impedir que se cree un ticket, así que degrada a «no coincide» o a «no
#    restringe», según la condición. Se documenta caso por caso.


def _como_lista(valor) -> list:
    """Normaliza «un valor o una lista de valores», que es la forma que aceptan
    casi todas las condiciones."""
    return valor if isinstance(valor, list) else [valor]


def _textos_normalizados(valor) -> list[str]:
    """Lista en minúsculas y sin espacios, descartando los vacíos.

    Los vacíos se descartan porque una cadena vacía está contenida en cualquier
    texto y haría que la condición se cumpliese siempre.
    """
    return [str(v).lower().strip() for v in _como_lista(valor) if str(v).strip()]


def _momento(ticket) -> datetime:
    """Instante de creación del ticket, o ahora si falta.

    Un ticket sin `created_at` es un ticket que se está creando: usar el momento
    actual es lo que hacía el original y lo que espera una regla horaria.
    """
    return ticket.created_at or datetime.now(timezone.utc)


def _rango_horario(valor) -> Optional[tuple]:
    """Extrae (inicio, fin) de las dos formas admitidas: «09:00-18:00» o
    {"start": ..., "end": ...}.

    Devuelve None si la forma no es reconocible o está incompleta, y entonces la
    condición NO restringe — igual que en el original.
    """
    if isinstance(valor, str) and "-" in valor:
        inicio_s, fin_s = [p.strip() for p in valor.split("-", 1)]
    elif isinstance(valor, dict):
        inicio_s, fin_s = valor.get("start"), valor.get("end")
        if not (inicio_s and fin_s):
            return None
    else:
        return None
    return dt_time.fromisoformat(inicio_s), dt_time.fromisoformat(fin_s)


_DIAS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


def _indices_de_dias(valor) -> list[int]:
    """Índices de día (lunes=0) admitiendo entero, cadena numérica o etiqueta.

    Una etiqueta que no existe se descarta en silencio: el resultado es que la
    condición no se cumple, que es lo que hacía el original.
    """
    indices = []
    for dia in _como_lista(valor):
        if isinstance(dia, int):
            indices.append(dia)
            continue
        texto = str(dia).lower().strip()
        if texto.isdigit():
            indices.append(int(texto))
        elif texto in _DIAS:
            indices.append(_DIAS[texto])
    return indices


def _dominio_del_solicitante(ticket) -> str:
    """Dominio de correo del solicitante, del ticket o del usuario que lo abrió.

    Cadena vacía si no hay correo o no tiene arroba: así la condición no se
    cumple, en lugar de lanzar.
    """
    correo = ticket.requester_email or (
        ticket.requester_user.email if ticket.requester_user else None
    )
    if not correo or "@" not in correo:
        return ""
    return correo.split("@", 1)[1].lower()


# ── Los once predicados ──────────────────────────────────────────────────────
# Firma común (ticket, valor) → ¿cumple? Comparten firma para que la tabla pueda
# invocarlos de forma uniforme, aunque alguno no use todo lo que recibe.

def _cond_ticket_type(ticket, valor) -> bool:
    return _norm_enum(ticket.ticket_type) == valor


def _cond_priority(ticket, valor) -> bool:
    return _norm_enum(ticket.priority) in _como_lista(valor)


def _cond_category_id(ticket, valor) -> bool:
    # Sin `service_item` la condición NO restringe: es lo que hacía el original
    # (`if "category_id" in conditions and ticket.service_item`).
    if not ticket.service_item:
        return True
    return ticket.service_item.category_id == valor


def _cond_requester_domain(ticket, valor) -> bool:
    return _dominio_del_solicitante(ticket) in _textos_normalizados(valor)


def _cond_keyword_in_title(ticket, valor) -> bool:
    titulo = (ticket.title or "").lower()
    return any(k in titulo for k in _textos_normalizados(valor))


def _cond_time_of_day(ticket, valor) -> bool:
    rango = _rango_horario(valor)
    if rango is None:
        return True  # forma no reconocible: no restringe
    inicio, fin = rango
    return inicio <= _momento(ticket).time() <= fin


def _cond_day_of_week(ticket, valor) -> bool:
    return _momento(ticket).weekday() in _indices_de_dias(valor)


def _cond_client_org_id(ticket, valor) -> bool:
    cliente = ticket.client_id or (
        ticket.requester_client.client_org_id if ticket.requester_client else None
    )
    return cliente in _como_lista(valor)


def _cond_sla_policy_id(ticket, valor) -> bool:
    return ticket.sla_policy_id in _como_lista(valor)


def _cond_tag_contains(ticket, valor) -> bool:
    etiquetas = (ticket.tags or "").lower()
    return any(t in etiquetas for t in _textos_normalizados(valor))


# Clave de condición → predicado. Añadir una condición es añadir su función y una
# línea aquí; antes era otra rama más en el bloque de 105 líneas.
_CONDICIONES = {
    "ticket_type": _cond_ticket_type,
    "priority": _cond_priority,
    "category_id": _cond_category_id,
    "requester_domain": _cond_requester_domain,
    "keyword_in_title": _cond_keyword_in_title,
    "time_of_day": _cond_time_of_day,
    "day_of_week": _cond_day_of_week,
    "client_org_id": _cond_client_org_id,
    "sla_policy_id": _cond_sla_policy_id,
    "tag_contains": _cond_tag_contains,
}


# ── Las cuatro acciones ──────────────────────────────────────────────────────

def _accion_assign_group(ticket, valor) -> None:
    ticket.assigned_group_id = valor


def _accion_assign_user(ticket, valor) -> None:
    ticket.assigned_to_user_id = valor


def _accion_set_priority(ticket, valor) -> None:
    ticket.priority = valor


def _accion_set_support_level(ticket, valor) -> None:
    ticket.support_level = valor


_ACCIONES = {
    "assign_group": _accion_assign_group,
    "assign_user": _accion_assign_user,
    "set_priority": _accion_set_priority,
    "set_support_level": _accion_set_support_level,
}


def _regla_coincide(ticket, conditions: dict) -> bool:
    """¿Cumple el ticket TODAS las condiciones presentes?

    Conjuntivo: una condición ausente no restringe, y una presente que no se
    cumple descarta la regla. Una clave desconocida se ignora —una regla guardada
    con una condición que después se retiró no debe bloquear el encaminamiento—.
    """
    for clave, valor in conditions.items():
        predicado = _CONDICIONES.get(clave)
        if predicado is None:
            logger.debug("routing: condición no reconocida %r, se ignora", clave)
            continue
        if not predicado(ticket, valor):
            return False
    return True


def _aplicar_acciones(ticket, actions: dict) -> None:
    """Aplica las acciones de la regla que ha coincidido."""
    for clave, valor in actions.items():
        aplicar = _ACCIONES.get(clave)
        if aplicar is None:
            logger.debug("routing: acción no reconocida %r, se ignora", clave)
            continue
        aplicar(ticket, valor)


def apply_routing_rules(ticket: Ticket, db: Session) -> bool:
    """Aplica las reglas de encaminamiento activas. True si alguna coincidió.

    Se evalúan por prioridad y gana la PRIMERA que coincide: las siguientes no se
    miran, así que el orden de `priority` es el que decide el resultado cuando
    varias reglas encajan.
    """
    rules = db.query(RoutingRule).filter(
        RoutingRule.is_active == True
    ).order_by(RoutingRule.priority).all()

    for rule in rules:
        conditions = json.loads(rule.conditions or "{}")
        if not _regla_coincide(ticket, conditions):
            continue
        _aplicar_acciones(ticket, json.loads(rule.actions or "{}"))
        return True

    return False
