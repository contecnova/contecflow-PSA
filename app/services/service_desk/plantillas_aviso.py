"""Textos por defecto de los avisos del Service Desk, en español e inglés.

Son el respaldo: una organizacion los sustituye creando una plantilla de correo
con el mismo `code` (y, si quiere, un idioma), o los apaga con esa plantilla
inactiva. Viven en el codigo y no en una semilla porque el modo limpio del
setup vacia todas las tablas: un aviso cuyo texto estuviese solo en la base se
quedaria mudo tras un reseteo.

Las variables van entre llaves dobles y se escapan al sustituir, porque llevan
texto que escribe el cliente (titulo, comentario).
"""
from __future__ import annotations

#: Variables que cualquier plantilla del Service Desk puede usar.
VARIABLES = (
    "ticket_number", "ticket_title", "ticket_status", "ticket_priority",
    "requester_name", "assignee_name", "group_name", "comment_author",
    "comment_body", "resolution", "sla_due", "link", "org_name",
)

_PIE_ES = (
    '<p style="color:#667085;font-size:12px;margin-top:24px">'
    "Responde a este correo para añadir un comentario al ticket {{ticket_number}}.</p>"
)
_PIE_EN = (
    '<p style="color:#667085;font-size:12px;margin-top:24px">'
    "Reply to this email to add a comment to ticket {{ticket_number}}.</p>"
)
_BOTON_ES = '<p><a href="{{link}}">Ver el ticket</a></p>'
_BOTON_EN = '<p><a href="{{link}}">View the ticket</a></p>'

#: code -> idioma -> (asunto, cuerpo html)
POR_DEFECTO: dict[str, dict[str, tuple[str, str]]] = {
    "sd.created.requester": {
        "es": ("Hemos recibido tu solicitud: {{ticket_title}}",
               "<p>Hola {{requester_name}},</p><p>Hemos registrado tu solicitud con el número "
               "<strong>{{ticket_number}}</strong>. Te avisaremos de cada novedad.</p>"
               "<blockquote>{{ticket_title}}</blockquote>" + _BOTON_ES + _PIE_ES),
        "en": ("We have received your request: {{ticket_title}}",
               "<p>Hello {{requester_name}},</p><p>Your request has been logged as "
               "<strong>{{ticket_number}}</strong>. We will keep you posted.</p>"
               "<blockquote>{{ticket_title}}</blockquote>" + _BOTON_EN + _PIE_EN),
    },
    "sd.created.agent": {
        "es": ("Nuevo ticket {{ticket_priority}}: {{ticket_title}}",
               "<p>{{requester_name}} ha abierto <strong>{{ticket_number}}</strong> "
               "({{ticket_priority}}) en {{group_name}}.</p>"
               "<blockquote>{{ticket_title}}</blockquote>" + _BOTON_ES),
        "en": ("New {{ticket_priority}} ticket: {{ticket_title}}",
               "<p>{{requester_name}} opened <strong>{{ticket_number}}</strong> "
               "({{ticket_priority}}) in {{group_name}}.</p>"
               "<blockquote>{{ticket_title}}</blockquote>" + _BOTON_EN),
    },
    "sd.assigned.agent": {
        "es": ("Te han asignado {{ticket_number}}: {{ticket_title}}",
               "<p>Tienes asignado <strong>{{ticket_number}}</strong> ({{ticket_priority}}), "
               "abierto por {{requester_name}}. Vence: {{sla_due}}.</p>"
               "<blockquote>{{ticket_title}}</blockquote>" + _BOTON_ES),
        "en": ("{{ticket_number}} has been assigned to you: {{ticket_title}}",
               "<p><strong>{{ticket_number}}</strong> ({{ticket_priority}}) from "
               "{{requester_name}} is now yours. Due: {{sla_due}}.</p>"
               "<blockquote>{{ticket_title}}</blockquote>" + _BOTON_EN),
    },
    "sd.group_assigned.agent": {
        "es": ("Nuevo en la cola {{group_name}}: {{ticket_title}}",
               "<p><strong>{{ticket_number}}</strong> ({{ticket_priority}}) ha entrado en la "
               "cola {{group_name}} sin agente asignado.</p>" + _BOTON_ES),
        "en": ("New in the {{group_name}} queue: {{ticket_title}}",
               "<p><strong>{{ticket_number}}</strong> ({{ticket_priority}}) is waiting in "
               "the {{group_name}} queue with no agent assigned.</p>" + _BOTON_EN),
    },
    "sd.commented.requester": {
        "es": ("Respuesta a tu solicitud: {{ticket_title}}",
               "<p>Hola {{requester_name}},</p><p>{{comment_author}} ha respondido a "
               "<strong>{{ticket_number}}</strong>:</p><blockquote>{{comment_body}}</blockquote>"
               + _BOTON_ES + _PIE_ES),
        "en": ("Reply to your request: {{ticket_title}}",
               "<p>Hello {{requester_name}},</p><p>{{comment_author}} replied to "
               "<strong>{{ticket_number}}</strong>:</p><blockquote>{{comment_body}}</blockquote>"
               + _BOTON_EN + _PIE_EN),
    },
    "sd.commented.agent": {
        "es": ("Comentario nuevo en {{ticket_number}}: {{ticket_title}}",
               "<p>{{comment_author}} ha escrito en <strong>{{ticket_number}}</strong>:</p>"
               "<blockquote>{{comment_body}}</blockquote>" + _BOTON_ES),
        "en": ("New comment on {{ticket_number}}: {{ticket_title}}",
               "<p>{{comment_author}} wrote on <strong>{{ticket_number}}</strong>:</p>"
               "<blockquote>{{comment_body}}</blockquote>" + _BOTON_EN),
    },
    "sd.resolved.requester": {
        "es": ("Solicitud resuelta: {{ticket_title}}",
               "<p>Hola {{requester_name}},</p><p>Hemos resuelto <strong>{{ticket_number}}</strong>."
               "</p><blockquote>{{resolution}}</blockquote><p>Si no queda resuelto, responde a "
               "este correo y lo reabrimos. Desde el ticket puedes valorar la atención.</p>"
               + _BOTON_ES),
        "en": ("Request resolved: {{ticket_title}}",
               "<p>Hello {{requester_name}},</p><p><strong>{{ticket_number}}</strong> has been "
               "resolved.</p><blockquote>{{resolution}}</blockquote><p>If it is not fixed, reply "
               "to this email and we will reopen it. You can rate the service from the ticket.</p>"
               + _BOTON_EN),
    },
    "sd.updated.agent": {
        "es": ("{{ticket_number}} actualizado: {{ticket_status}}, {{ticket_priority}}",
               "<p><strong>{{ticket_number}}</strong> — {{ticket_title}} está ahora "
               "{{ticket_status}} ({{ticket_priority}}, {{assignee_name}}).</p>" + _BOTON_ES),
        "en": ("{{ticket_number}} updated: {{ticket_status}}, {{ticket_priority}}",
               "<p><strong>{{ticket_number}}</strong> — {{ticket_title}} is now "
               "{{ticket_status}} ({{ticket_priority}}, {{assignee_name}}).</p>" + _BOTON_EN),
    },
    "sd.sla_warning.agent": {
        "es": ("SLA en riesgo: {{ticket_number}} vence {{sla_due}}",
               "<p><strong>{{ticket_number}}</strong> ({{ticket_priority}}, {{assignee_name}}) "
               "ha consumido la mayor parte de su SLA. Vence: {{sla_due}}.</p>" + _BOTON_ES),
        "en": ("SLA at risk: {{ticket_number}} due {{sla_due}}",
               "<p><strong>{{ticket_number}}</strong> ({{ticket_priority}}, {{assignee_name}}) "
               "has used most of its SLA. Due: {{sla_due}}.</p>" + _BOTON_EN),
    },
    "sd.sla_breached.agent": {
        "es": ("SLA incumplido: {{ticket_number}}",
               "<p><strong>{{ticket_number}}</strong> ({{ticket_priority}}, {{assignee_name}}) "
               "ha superado su SLA, que vencía {{sla_due}}.</p>" + _BOTON_ES),
        "en": ("SLA breached: {{ticket_number}}",
               "<p><strong>{{ticket_number}}</strong> ({{ticket_priority}}, {{assignee_name}}) "
               "missed its SLA, due {{sla_due}}.</p>" + _BOTON_EN),
    },
    "sd.escalated.agent": {
        "es": ("Escalado: {{ticket_number}} {{ticket_title}}",
               "<p>Se ha escalado <strong>{{ticket_number}}</strong> ({{ticket_priority}}, "
               "{{assignee_name}}): {{comment_body}}</p>" + _BOTON_ES),
        "en": ("Escalated: {{ticket_number}} {{ticket_title}}",
               "<p><strong>{{ticket_number}}</strong> ({{ticket_priority}}, {{assignee_name}}) "
               "was escalated: {{comment_body}}</p>" + _BOTON_EN),
    },
    "sd.approval_requested.approver": {
        "es": ("Aprobación pendiente: {{ticket_title}}",
               "<p>{{requester_name}} ha pedido <strong>{{ticket_title}}</strong> "
               "({{ticket_number}}) y necesita tu aprobación.</p>" + _BOTON_ES),
        "en": ("Approval needed: {{ticket_title}}",
               "<p>{{requester_name}} requested <strong>{{ticket_title}}</strong> "
               "({{ticket_number}}) and it needs your approval.</p>" + _BOTON_EN),
    },
    "sd.approval_decided.requester": {
        "es": ("Tu solicitud se ha {{resolution}}: {{ticket_title}}",
               "<p>Hola {{requester_name}},</p><p>La aprobación de <strong>{{ticket_number}}"
               "</strong> se ha resuelto: {{resolution}}.</p><blockquote>{{comment_body}}"
               "</blockquote>" + _BOTON_ES),
        "en": ("Your request was {{resolution}}: {{ticket_title}}",
               "<p>Hello {{requester_name}},</p><p>The approval for <strong>{{ticket_number}}"
               "</strong> was {{resolution}}.</p><blockquote>{{comment_body}}</blockquote>"
               + _BOTON_EN),
    },
}

#: Etiquetas para los valores que se cuelan en los textos.
ETIQUETAS = {
    "es": {
        "status": {"new": "Nuevo", "assigned": "Asignado", "in_progress": "En curso",
                   "pending_client": "Pendiente de ti", "pending_third": "Pendiente de un tercero",
                   "resolved": "Resuelto", "closed": "Cerrado", "cancelled": "Cancelado"},
        "priority": {"p1_critical": "P1 crítica", "p2_high": "P2 alta",
                     "p3_medium": "P3 media", "p4_low": "P4 baja"},
        "approved": "aprobado", "rejected": "rechazado",
        "unassigned": "sin asignar", "no_group": "sin cola", "system": "el equipo de soporte",
    },
    "en": {
        "status": {"new": "New", "assigned": "Assigned", "in_progress": "In progress",
                   "pending_client": "Waiting for you", "pending_third": "Waiting for a third party",
                   "resolved": "Resolved", "closed": "Closed", "cancelled": "Cancelled"},
        "priority": {"p1_critical": "P1 critical", "p2_high": "P2 high",
                     "p3_medium": "P3 medium", "p4_low": "P4 low"},
        "approved": "approved", "rejected": "rejected",
        "unassigned": "unassigned", "no_group": "no queue", "system": "the support team",
    },
}

IDIOMAS = tuple(ETIQUETAS)
