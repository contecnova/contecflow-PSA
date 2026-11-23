"""Textos por defecto de los avisos del Service Desk, en español, inglés y chino.

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
    "comment_body", "resolution", "sla_due", "link", "org_name", "vendor_name",
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
_PIE_ZH = (
    '<p style="color:#667085;font-size:12px;margin-top:24px">'
    "回复此邮件即可为工单 {{ticket_number}} 添加评论。</p>"
)
_BOTON_ZH = '<p><a href="{{link}}">查看工单</a></p>'

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
    "sd.ola_breached.agent": {
        "es": ("OLA incumplido en {{group_name}}: {{ticket_number}}",
               "<p><strong>{{ticket_number}}</strong> ({{ticket_priority}}, {{assignee_name}}) "
               "ha superado el tiempo interno de la cola {{group_name}}, que vencía {{sla_due}}.</p>" + _BOTON_ES),
        "en": ("OLA breached in {{group_name}}: {{ticket_number}}",
               "<p><strong>{{ticket_number}}</strong> ({{ticket_priority}}, {{assignee_name}}) "
               "missed the internal target of the {{group_name}} queue, due {{sla_due}}.</p>" + _BOTON_EN),
    },
    "sd.uc_breached.agent": {
        "es": ("UC incumplido: {{ticket_number}} ({{vendor_name}})",
               "<p><strong>{{ticket_number}}</strong> ({{ticket_priority}}, {{assignee_name}}) "
               "lleva esperando al proveedor más de lo que fija su contrato ({{vendor_name}}); "
               "vencía {{sla_due}}.</p>" + _BOTON_ES),
        "en": ("UC breached: {{ticket_number}} ({{vendor_name}})",
               "<p><strong>{{ticket_number}}</strong> ({{ticket_priority}}, {{assignee_name}}) "
               "has waited on the vendor longer than its contract allows ({{vendor_name}}); "
               "due {{sla_due}}.</p>" + _BOTON_EN),
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

#: 23-11-2026: el chino (zh) de cada aviso; los operadores son es/en/zh. Se añade
#: aquí, junto a su código, para no tocar las entradas es/en de arriba.
_ZH: dict[str, tuple[str, str]] = {
    "sd.created.requester": (
        "我们已收到您的请求：{{ticket_title}}",
        "<p>您好 {{requester_name}}，</p><p>我们已将您的请求登记为 <strong>{{ticket_number}}</strong>。"
        "有任何进展都会通知您。</p><blockquote>{{ticket_title}}</blockquote>" + _BOTON_ZH + _PIE_ZH),
    "sd.created.agent": (
        "新的 {{ticket_priority}} 工单：{{ticket_title}}",
        "<p>{{requester_name}} 在 {{group_name}} 中创建了 <strong>{{ticket_number}}</strong>"
        "（{{ticket_priority}}）。</p><blockquote>{{ticket_title}}</blockquote>" + _BOTON_ZH),
    "sd.assigned.agent": (
        "已分配给您 {{ticket_number}}：{{ticket_title}}",
        "<p>您被分配了 <strong>{{ticket_number}}</strong>（{{ticket_priority}}），由 {{requester_name}} 创建。"
        "到期：{{sla_due}}。</p><blockquote>{{ticket_title}}</blockquote>" + _BOTON_ZH),
    "sd.group_assigned.agent": (
        "{{group_name}} 队列有新工单：{{ticket_title}}",
        "<p><strong>{{ticket_number}}</strong>（{{ticket_priority}}）已进入 {{group_name}} 队列，"
        "尚未指派处理人。</p>" + _BOTON_ZH),
    "sd.commented.requester": (
        "您的请求有回复：{{ticket_title}}",
        "<p>您好 {{requester_name}}，</p><p>{{comment_author}} 回复了 <strong>{{ticket_number}}</strong>：</p>"
        "<blockquote>{{comment_body}}</blockquote>" + _BOTON_ZH + _PIE_ZH),
    "sd.commented.agent": (
        "{{ticket_number}} 有新评论：{{ticket_title}}",
        "<p>{{comment_author}} 在 <strong>{{ticket_number}}</strong> 中留言：</p>"
        "<blockquote>{{comment_body}}</blockquote>" + _BOTON_ZH),
    "sd.resolved.requester": (
        "请求已解决：{{ticket_title}}",
        "<p>您好 {{requester_name}}，</p><p><strong>{{ticket_number}}</strong> 已解决。</p>"
        "<blockquote>{{resolution}}</blockquote><p>如果问题仍未解决，请回复此邮件，我们会重新打开。"
        "您也可以在工单中对服务进行评价。</p>" + _BOTON_ZH),
    "sd.updated.agent": (
        "{{ticket_number}} 已更新：{{ticket_status}}，{{ticket_priority}}",
        "<p><strong>{{ticket_number}}</strong> — {{ticket_title}} 现在为 {{ticket_status}}"
        "（{{ticket_priority}}，{{assignee_name}}）。</p>" + _BOTON_ZH),
    "sd.sla_warning.agent": (
        "SLA 有风险：{{ticket_number}} 到期 {{sla_due}}",
        "<p><strong>{{ticket_number}}</strong>（{{ticket_priority}}，{{assignee_name}}）"
        "已用掉大部分 SLA 时间。到期：{{sla_due}}。</p>" + _BOTON_ZH),
    "sd.sla_breached.agent": (
        "SLA 已违约：{{ticket_number}}",
        "<p><strong>{{ticket_number}}</strong>（{{ticket_priority}}，{{assignee_name}}）"
        "已超出 SLA 时限，到期时间为 {{sla_due}}。</p>" + _BOTON_ZH),
    "sd.ola_breached.agent": (
        "{{group_name}} 的 OLA 已违约：{{ticket_number}}",
        "<p><strong>{{ticket_number}}</strong>（{{ticket_priority}}，{{assignee_name}}）"
        "已超出 {{group_name}} 队列的内部时限，到期时间为 {{sla_due}}。</p>" + _BOTON_ZH),
    "sd.uc_breached.agent": (
        "UC 已违约：{{ticket_number}}（{{vendor_name}}）",
        "<p><strong>{{ticket_number}}</strong>（{{ticket_priority}}，{{assignee_name}}）"
        "等待供应商的时间已超过其合同约定（{{vendor_name}}）；到期时间为 {{sla_due}}。</p>" + _BOTON_ZH),
    "sd.escalated.agent": (
        "已升级：{{ticket_number}} {{ticket_title}}",
        "<p><strong>{{ticket_number}}</strong>（{{ticket_priority}}，{{assignee_name}}）"
        "已升级：{{comment_body}}</p>" + _BOTON_ZH),
    "sd.approval_requested.approver": (
        "待审批：{{ticket_title}}",
        "<p>{{requester_name}} 申请了 <strong>{{ticket_title}}</strong>（{{ticket_number}}），"
        "需要您的批准。</p>" + _BOTON_ZH),
    "sd.approval_decided.requester": (
        "您的请求已{{resolution}}：{{ticket_title}}",
        "<p>您好 {{requester_name}}，</p><p><strong>{{ticket_number}}</strong> 的审批结果："
        "{{resolution}}。</p><blockquote>{{comment_body}}</blockquote>" + _BOTON_ZH),
}
for _code, _textos in _ZH.items():
    POR_DEFECTO[_code]["zh"] = _textos

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
    "zh": {
        "status": {"new": "新建", "assigned": "已分配", "in_progress": "处理中",
                   "pending_client": "等待您", "pending_third": "等待第三方",
                   "resolved": "已解决", "closed": "已关闭", "cancelled": "已取消"},
        "priority": {"p1_critical": "P1 紧急", "p2_high": "P2 高",
                     "p3_medium": "P3 中", "p4_low": "P4 低"},
        "approved": "批准", "rejected": "拒绝",
        "unassigned": "未分配", "no_group": "无队列", "system": "支持团队",
    },
}

IDIOMAS = tuple(ETIQUETAS)
