"""Plantilla OPCIONAL «Nueva funcionalidad con CAB y comité» del flujo de demanda.

Seis fases (docs/FLUJO_DE_DEMANDA.md §2.3): Solicitud con triaje → Estudio →
CAB → Normativa (Legal y Compliance en paralelo) → Gobernanza (puerta: vía
rápida o comité) → Comité de dirección.

23-11-2026: antes se llamaba «piloto», llevaba los nombres de un cliente concreto
(flujo, grupos y comités) y se sembraba en la empresa de demostración y en la migración 195. Ahora es una plantilla de la biblioteca
(`biblioteca.PLANTILLAS["nueva_funcionalidad"]`) que el administrador elige instalar
(`POST /demanda/plantillas/...`): no se crea nada por defecto. Los nombres de los
grupos son genéricos y salen en el idioma de la empresa. La clave antigua
`piloto_digital` sigue valiendo (alias) para las empresas que ya la instalaron.

`sembrar_plantilla_piloto(db, org_id, usuario_id)` es idempotente: crea los
grupos aprobadores que falten (vacíos: la empresa pone a las personas), el
flujo si no existe y los tres tipos de solicitud si no existen. No commitea:
lo hace quien llama.
"""
from __future__ import annotations

import json
from typing import Optional

from sqlalchemy.orm import Session

from app.services.formato_regional import IDIOMA_DE_RESPALDO

CLAVE_FLUJO = "nueva_funcionalidad"
#: Claves con las que una empresa pudo instalarla antes (se reconocen para no duplicarla).
CLAVES_ANTIGUAS = ("piloto_digital",)


def _t(es: str, en: str, zh: str) -> dict:
    return {"es": es, "en": en, "zh": zh}


#: clave del grupo → (nombre, descripción) en es/en/zh; se escriben en el idioma de la empresa.
GRUPOS = {
    "triaje": (_t("Triaje de solicitudes", "Request triage", "请求分诊"),
               _t("Responsable de servicio / propietario de producto: triaje de solicitudes",
                  "Service manager / product owner: request triage", "服务经理 / 产品负责人：请求分诊")),
    "digital": (_t("Equipo de análisis", "Analysis team", "分析团队"),
                _t("Estudio técnico y business case de las solicitudes",
                   "Technical study and business case of the requests", "请求的技术研究与业务案例")),
    "cab": (_t("CAB", "CAB", "变更顾问委员会"),
            _t("Revisión de pares: seguridad, viabilidad y dimensionamiento",
               "Peer review: security, feasibility and sizing", "同行评审：安全、可行性与规模")),
    "legal": (_t("Legal", "Legal", "法务"),
              _t("Dictamen legal: contratos, licencias, riesgos regulatorios",
                 "Legal opinion: contracts, licences, regulatory risks", "法律意见：合同、许可、监管风险")),
    "compliance": (_t("Compliance", "Compliance", "合规"),
                   _t("Dictamen de cumplimiento: RGPD, normativa sectorial",
                      "Compliance opinion: GDPR, sector regulation", "合规意见：GDPR、行业法规")),
    "comite": (_t("Comité de dirección", "Steering committee", "指导委员会"),
               _t("Decisión sobre iniciativas por presupuesto, impacto o transversalidad",
                  "Decision on initiatives by budget, impact or cross-cutting scope", "按预算、影响或跨部门范围决定倡议")),
}


def nombre_de_grupo(clave: str, idioma: Optional[str] = None) -> str:
    """Nombre del grupo aprobador `clave` en `idioma` (castellano si no hay)."""
    nombres = GRUPOS[clave][0]
    return nombres.get(idioma or IDIOMA_DE_RESPALDO) or nombres[IDIOMA_DE_RESPALDO]


def _campo(key, es, en, zh, tipo="textarea", owner="client", critical=False, policy=None, options=None) -> dict:
    c = {"key": key, "label": _t(es, en, zh), "type": tipo, "owner": owner, "critical": critical,
         "client_visible": True}
    if policy:
        c["policy_field"] = policy
    if options:
        c["options"] = options
    return c


def _opcion(valor, es, en, zh) -> dict:
    return {"value": valor, "label": _t(es, en, zh)}


def _grupo(ids: dict, clave: str, etiqueta: str) -> dict:
    return {"type": "group", "value": ids[clave], "label": etiqueta}


def definicion_piloto(ids_de_grupo: dict, idioma: Optional[str] = None) -> dict:
    """La definición JSON del flujo con los ids de sus grupos (etiquetas de grupo en `idioma`)."""
    impacto = [_opcion("bajo", "Bajo", "Low", "低"), _opcion("medio", "Medio", "Medium", "中"),
               _opcion("alto", "Alto", "High", "高")]
    prioridad = [_opcion("baja", "Baja", "Low", "低"), _opcion("media", "Media", "Medium", "中"),
                 _opcion("alta", "Alta", "High", "高"), _opcion("critica", "Crítica", "Critical", "紧急")]
    campos = [
        _campo("descripcion_funcional", "Descripción funcional", "Functional description", "功能描述", critical=True),
        _campo("justificacion", "Justificación de negocio", "Business justification", "业务理由", critical=True),
        _campo("retorno_esperado", "Retorno esperado (ROI o beneficio)", "Expected return (ROI or benefit)",
               "预期回报（ROI 或收益）", critical=True),
        _campo("roi_estimado", "ROI estimado (%)", "Estimated ROI (%)", "预计投资回报率 (%)", tipo="number",
               critical=True, policy="roi"),
        _campo("area_afectada", "Área o sistema afectado", "Affected area or system", "受影响的领域或系统", tipo="text"),
        _campo("prioridad", "Prioridad", "Priority", "优先级", tipo="select", options=prioridad),
        _campo("viabilidad_tecnica", "Viabilidad técnica", "Technical feasibility", "技术可行性", owner="internal"),
        _campo("arquitectura", "Arquitectura", "Architecture", "架构", owner="internal"),
        _campo("impacto_legados", "Impacto en sistemas legados", "Impact on legacy systems", "对遗留系统的影响",
               owner="internal"),
        _campo("ciberseguridad", "Ciberseguridad", "Cybersecurity", "网络安全", owner="internal"),
        _campo("solucion_tecnica", "Solución técnica", "Technical solution", "技术方案", owner="internal",
               critical=True),
        _campo("esfuerzo_horas", "Esfuerzo (horas)", "Effort (hours)", "工作量（小时）", tipo="number",
               owner="internal", critical=True, policy="esfuerzo"),
        _campo("equipo", "Equipo", "Team", "团队", tipo="text", owner="internal"),
        _campo("coste", "Coste estimado", "Estimated cost", "预计成本", tipo="money", owner="internal",
               critical=True, policy="coste"),
        _campo("cronograma", "Cronograma tentativo", "Tentative schedule", "初步时间表", owner="internal",
               critical=True),
        _campo("retorno_ajustado", "Retorno ajustado", "Adjusted return", "调整后回报", owner="internal",
               critical=True),
        _campo("impacto_estrategico", "Impacto estratégico", "Strategic impact", "战略影响", tipo="select",
               owner="internal", policy="impacto", options=impacto),
        _campo("transversal", "Transversal (varias áreas)", "Cross-cutting (several areas)", "跨部门",
               tipo="boolean", owner="internal", policy="transversal"),
    ]
    al_solicitante = {"type": "requester"}
    a_los_responsables = {"type": "assignees"}
    fases = [
        {
            "key": "solicitud", "name": _t("Solicitud", "Request", "申请"), "kind": "intake",
            "steps": [{"key": "triaje", "name": _t("Triaje", "Triage", "分诊"), "mode": "approval",
                       "assignee": _grupo(ids_de_grupo, "triaje", nombre_de_grupo("triaje", idioma))}],
            "decisions": ["approve", "request_info", "reject"],
            "on_approve": "next", "on_reject": "end:rejected",
            "required_fields": ["descripcion_funcional", "justificacion", "retorno_esperado"],
            "client_editable": True, "sla_hours": 48, "sla_warn_pct": 75, "pause_on_info": True,
            "documents_tag": "presentation",
            "notify": [{"event": "enter", "to": a_los_responsables},
                       {"event": "info_requested", "to": al_solicitante}],
        },
        {
            "key": "estudio", "name": _t("Estudio", "Study", "研究"), "kind": "work",
            "steps": [{"key": "estudio_digital", "name": _t("Estudio técnico y business case",
                                                             "Technical study and business case", "技术研究与业务案例"),
                       "mode": "task", "assignee": _grupo(ids_de_grupo, "digital", nombre_de_grupo("digital", idioma))}],
            "decisions": ["complete", "request_info", "return"],
            "return_targets": ["solicitud"], "on_approve": "next",
            "required_fields": ["viabilidad_tecnica", "arquitectura", "ciberseguridad", "solucion_tecnica",
                                "esfuerzo_horas", "coste", "cronograma", "retorno_ajustado"],
            "client_editable": True, "sla_hours": 240, "sla_warn_pct": 80, "pause_on_info": True,
            "documents_tag": "technical_study",
            "notify": [{"event": "enter", "to": a_los_responsables}],
        },
        {
            "key": "cab", "name": _t("CAB", "CAB", "变更顾问委员会"), "kind": "review",
            "steps": [{"key": "revision_cab", "name": _t("Revisión de pares", "Peer review", "同行评审"),
                       "mode": "approval", "quorum": "majority",
                       "assignee": {"type": "committee", "value": ids_de_grupo["cab"], "label": nombre_de_grupo("cab", idioma)}}],
            "decisions": ["approve", "reject", "return"],
            "on_approve": "next", "on_reject": "estudio", "return_targets": ["estudio"],
            "lock_client_from_here": True, "client_editable": False,
            "segregation": {"not_requester": True, "not_actor_of_phases": ["estudio"]},
            "sla_hours": 120, "sla_warn_pct": 80, "documents_tag": "cab_security_report",
            "notify": [{"event": "enter", "to": a_los_responsables}, {"event": "decision", "to": al_solicitante}],
        },
        {
            "key": "normativa", "name": _t("Normativa", "Regulatory", "合规审查"), "kind": "approval",
            "parallel": True,
            "steps": [
                {"key": "legal", "name": _t("Dictamen legal", "Legal opinion", "法律意见"), "mode": "approval",
                 "assignee": _grupo(ids_de_grupo, "legal", "Legal")},
                {"key": "compliance", "name": _t("Dictamen de compliance", "Compliance opinion", "合规意见"),
                 "mode": "approval", "assignee": _grupo(ids_de_grupo, "compliance", "Compliance")},
            ],
            "decisions": ["approve", "reject", "return", "request_info"],
            "on_approve": "next", "on_reject": "end:rejected", "return_targets": ["estudio"],
            "client_editable": False, "sla_hours": 120, "sla_warn_pct": 80, "pause_on_info": True,
            "documents_tag": "legal_opinion",
            "notify": [{"event": "enter", "to": a_los_responsables}],
        },
        {
            "key": "gobernanza", "name": _t("Gobernanza", "Governance", "治理"), "kind": "gate",
            "steps": [{"key": "decision_gobernanza", "name": _t("¿Requiere comité?", "Committee required?",
                                                                 "是否需要委员会？"),
                       "mode": "approval", "assignee": _grupo(ids_de_grupo, "digital", nombre_de_grupo("digital", idioma))}],
            "decisions": ["fast_track", "to_committee"],
            "gate": {"conditions": [{"field": "coste", "op": "gt", "value": 50000},
                                    {"field": "esfuerzo_horas", "op": "gt", "value": 800},
                                    {"field": "impacto_estrategico", "op": "eq", "value": "alto"},
                                    {"field": "transversal", "op": "true"}],
                     "match": "any", "use_policies": True, "if_true": "comite", "if_false": "end:approved",
                     "allow_bypass": True},
            "client_editable": False, "sla_hours": 48, "sla_warn_pct": 75,
            "notify": [{"event": "enter", "to": a_los_responsables}],
        },
        {
            "key": "comite", "name": _t("Comité de dirección", "Steering committee", "指导委员会"),
            "kind": "committee",
            "steps": [{"key": "resolucion_comite", "name": _t("Resolución del comité", "Committee resolution",
                                                               "委员会决议"),
                       "mode": "approval", "assignee": {"type": "committee", "value": ids_de_grupo["comite"],
                                                        "label": nombre_de_grupo("comite", idioma)}}],
            "decisions": ["approve", "reject", "hold"],
            "on_approve": "end:approved", "on_reject": "end:rejected",
            "committee": {"executive_summary": True},
            "client_editable": False, "sla_hours": 720, "sla_warn_pct": 80, "documents_tag": "committee_minutes",
            "notify": [{"event": "enter", "to": a_los_responsables}, {"event": "decision", "to": al_solicitante}],
        },
    ]
    return {
        "fields": campos,
        "submit_required": ["title", "descripcion_funcional", "justificacion", "retorno_esperado"],
        "phases": fases,
        "execution": ["backlog", "new_project", "portfolio"],
        "notify": [{"event": "closed", "to": al_solicitante}, {"event": "submitted", "to": al_solicitante},
                   {"event": "sla_breach", "to": a_los_responsables}],
    }


TIPOS = (
    ("project_change", _t("Cambio en un proyecto", "Change in a project", "项目变更"), True, False, 1, ["project"]),
    ("new_feature", _t("Nueva funcionalidad", "New feature", "新功能"), False, True, 2, ["project", "none"]),
    ("service", _t("Servicio", "Service", "服务"), False, True, 3, ["service", "none"]),
)


def _grupos(db: Session, org_id: Optional[str], usuario_id: Optional[str], idioma: Optional[str] = None) -> dict:
    from app.models.billing_reports import ApprovalGroup
    ids = {}
    for clave, (nombres, descripciones) in GRUPOS.items():
        nombre_ = nombres.get(idioma or IDIOMA_DE_RESPALDO) or nombres[IDIOMA_DE_RESPALDO]
        descripcion = descripciones.get(idioma or IDIOMA_DE_RESPALDO) or descripciones[IDIOMA_DE_RESPALDO]
        g = db.query(ApprovalGroup).filter(ApprovalGroup.organization_id == org_id,
                                           ApprovalGroup.name == nombre_).first()
        if g is None:
            g = ApprovalGroup(organization_id=org_id, name=nombre_, description=descripcion, member_ids="[]",
                              created_by=usuario_id)
            db.add(g)
            db.flush()
        ids[clave] = g.id
    return ids


_PLANTILLA_NOMBRE = _t("Nueva funcionalidad con CAB y comité", "New feature with CAB and committee",
                       "带 CAB 和委员会的新功能")
_PLANTILLA_DESCRIPCION = _t(
    "Solicitud → Estudio → CAB → Normativa (Legal y Compliance) → Gobernanza → Comité de dirección",
    "Request → Study → CAB → Regulation (Legal and Compliance) → Governance → Steering committee",
    "请求 → 研究 → CAB → 法规（法务与合规）→ 治理 → 指导委员会")


def sembrar_plantilla_piloto(db: Session, org_id: Optional[str], usuario_id: Optional[str] = None) -> dict:
    """Crea (si faltan) grupos, flujo piloto y tipos. Devuelve {flow_id, created}."""
    from app.models.demanda import DemandFlow, DemandRequestType
    from app.services.formato_regional import idioma_de_salida
    flujo = db.query(DemandFlow).filter(DemandFlow.organization_id == org_id,
                                        DemandFlow.key.in_((CLAVE_FLUJO, *CLAVES_ANTIGUAS))).first()
    creado = False
    if flujo is None:
        idioma = idioma_de_salida(db, org_id=org_id)
        ids = _grupos(db, org_id, usuario_id, idioma)
        flujo = DemandFlow(organization_id=org_id, key=CLAVE_FLUJO,
                           name=_PLANTILLA_NOMBRE.get(idioma) or _PLANTILLA_NOMBRE["es"],
                           description=_PLANTILLA_DESCRIPCION.get(idioma) or _PLANTILLA_DESCRIPCION["es"],
                           definition=json.dumps(definicion_piloto(ids, idioma), ensure_ascii=False), version=1,
                           is_active=True, created_by=usuario_id)
        db.add(flujo)
        db.flush()
        creado = True
    for clave, nombres, exige, independiente, orden, alcances in TIPOS:
        if db.query(DemandRequestType.id).filter(DemandRequestType.organization_id == org_id,
                                                 DemandRequestType.key == clave).first():
            continue
        db.add(DemandRequestType(organization_id=org_id, key=clave, name=nombres[IDIOMA_DE_RESPALDO],
                                 name_i18n=json.dumps(nombres, ensure_ascii=False),
                                 channels=json.dumps(["client_portal", "internal_portal", "operator"]),
                                 scopes=json.dumps(alcances), requires_project=exige, allows_standalone=independiente, flow_id=flujo.id,
                                 sort_order=orden, is_active=True))
    db.flush()
    return {"flow_id": flujo.id, "created": creado}
