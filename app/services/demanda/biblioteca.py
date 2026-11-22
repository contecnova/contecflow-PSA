"""Biblioteca de plantillas de flujo de demanda (listas para instalar y editar).

Ninguna plantilla está «cableada» en el motor: son definiciones JSON como las
que escribe cualquier empresa en Configuración. Instalar una crea el flujo (y
sus tipos de solicitud si no existen) en la empresa; después se edita como
cualquier otro. Exportar/importar usa el mismo formato
(`contecflow-demand-flow/v1`).

Plantillas:
- `piloto_digital`: Nueva funcionalidad con CAB y comité (la de la empresa piloto).
- `cambio_itil`: petición de cambio ITIL estándar / normal / urgente (fases condicionales).
- `alta_proveedor`: alta de proveedor (compras, compliance y aprobación por importe).
- `compra_por_importe`: petición de compra con aprobación escalonada por importe.
- `acceso_permisos`: petición de acceso o permisos (responsable y propietario del sistema).
- `iniciativa_cartera`: iniciativa de cartera con business case (termina en Cartera).
- `peticion_rrhh`: petición a RR. HH.
"""
from __future__ import annotations

import json
from typing import Callable, Optional

from sqlalchemy.orm import Session

from app.core.codigos_de_error import error
from app.services.demanda import definicion as D
from app.services.demanda.plantillas import _campo, _opcion, _t
from app.services.formato_regional import IDIOMA_DE_RESPALDO

FORMATO = "contecflow-demand-flow/v1"


def _fase(key, es, en, zh, kind, pasos, **extra) -> dict:
    return {"key": key, "name": _t(es, en, zh), "kind": kind, "steps": pasos, **extra}


def _paso(key, es, en, zh, asignado: dict, mode="approval", **extra) -> dict:
    return {"key": key, "name": _t(es, en, zh), "mode": mode, "assignee": asignado, **extra}


ROL_ADMIN = {"type": "role", "value": "admin", "label": "Dirección"}
ROL_PM = {"type": "role", "value": "pm", "label": "Project Manager"}
ROL_JEFE = {"type": "role", "value": "team_lead", "label": "Team Lead"}
ROL_RRHH = {"type": "role", "value": "hr", "label": "RRHH"}
SU_RESPONSABLE = {"type": "requester_manager", "label": "Responsable de quien pide"}
AL_SOLICITANTE = {"event": "decision", "to": {"type": "requester"}}
A_RESPONSABLES = {"event": "enter", "to": {"type": "assignees"}}


def _cambio_itil() -> tuple[dict, list]:
    tipo = [_opcion("estandar", "Estándar", "Standard", "标准"), _opcion("normal", "Normal", "Normal", "常规"),
            _opcion("urgente", "Urgente", "Emergency", "紧急")]
    riesgo = [_opcion("bajo", "Bajo", "Low", "低"), _opcion("medio", "Medio", "Medium", "中"),
              _opcion("alto", "Alto", "High", "高")]
    defn = {
        "fields": [
            _campo("tipo_cambio", "Tipo de cambio", "Change type", "变更类型", tipo="select", options=tipo),
            _campo("descripcion", "Descripción del cambio", "Change description", "变更描述", critical=True),
            _campo("justificacion", "Justificación", "Justification", "理由", critical=True),
            _campo("riesgo", "Riesgo", "Risk", "风险", tipo="select", owner="internal", options=riesgo, critical=True),
            _campo("plan_implantacion", "Plan de implantación", "Implementation plan", "实施计划", owner="internal"),
            _campo("plan_marcha_atras", "Plan de marcha atrás", "Back-out plan", "回退计划", owner="internal"),
            _campo("ventana", "Ventana prevista", "Planned window", "计划窗口", tipo="date", owner="internal"),
        ],
        "submit_required": ["title", "tipo_cambio", "descripcion", "justificacion"],
        "phases": [
            _fase("evaluacion", "Evaluación", "Assessment", "评估", "work",
                  [_paso("evaluar", "Evaluar riesgo y planes", "Assess risk and plans", "评估风险和计划", ROL_PM,
                         mode="task")],
                  decisions=["complete", "request_info", "reject"],
                  required_fields=["riesgo", "plan_implantacion", "plan_marcha_atras"], sla_hours=24,
                  notify=[A_RESPONSABLES]),
            _fase("cab", "CAB", "CAB", "变更顾问委员会", "review",
                  [_paso("cab", "Aprobación del CAB", "CAB approval", "CAB 审批", ROL_ADMIN)],
                  condition={"conditions": [{"field": "tipo_cambio", "op": "eq", "value": "normal"}]},
                  decisions=["approve", "reject", "return", "hold"], return_targets=["evaluacion"],
                  lock_client_from_here=True, sla_hours=72, notify=[A_RESPONSABLES, AL_SOLICITANTE]),
            _fase("ecab", "CAB de emergencia", "Emergency CAB", "紧急变更委员会", "review",
                  [_paso("ecab", "Aprobación urgente", "Emergency approval", "紧急审批", ROL_ADMIN)],
                  condition={"conditions": [{"field": "tipo_cambio", "op": "eq", "value": "urgente"}]},
                  decisions=["approve", "reject"], sla_hours=4, escalation={"to": ROL_ADMIN},
                  notify=[A_RESPONSABLES, {"event": "sla_warning", "to": {"type": "assignees"}}]),
        ],
        "on_close_actions": [{"action": "create_itsm_change", "when": "approved"}],
        "notify": [{"event": "closed", "to": {"type": "requester"}}],
    }
    tipos = [("itil_change", _t("Petición de cambio (ITIL)", "Change request (ITIL)", "变更请求 (ITIL)"),
              ["operator", "internal_portal", "client_portal"], ["service", "asset", "project", "none"])]
    return defn, tipos


def _alta_proveedor() -> tuple[dict, list]:
    defn = {
        "fields": [
            _campo("razon_social", "Razón social", "Company name", "公司名称", tipo="text", critical=True),
            _campo("cif", "CIF / NIF", "Tax ID", "税号", tipo="text", critical=True),
            _campo("servicio", "Servicio que prestará", "Service to provide", "提供的服务"),
            _campo("importe_anual", "Importe anual previsto", "Expected annual amount", "预计年度金额", tipo="money",
                   critical=True, policy="coste"),
            _campo("trata_datos", "Tratará datos personales", "Will process personal data", "将处理个人数据",
                   tipo="boolean"),
            _campo("dpa_firmado", "Contrato de encargo (DPA) firmado", "DPA signed", "已签署数据处理协议",
                   tipo="boolean", owner="internal"),
            _campo("evaluacion_riesgo", "Evaluación de riesgo", "Risk assessment", "风险评估", owner="internal"),
        ],
        "submit_required": ["title", "razon_social", "cif", "servicio"],
        "phases": [
            _fase("compras", "Compras", "Procurement", "采购", "work",
                  [_paso("revision", "Revisión de compras", "Procurement review", "采购审核", ROL_PM, mode="task")],
                  decisions=["complete", "request_info", "reject"], required_fields=["evaluacion_riesgo"],
                  sla_hours=72, notify=[A_RESPONSABLES]),
            _fase("rgpd", "Protección de datos", "Data protection", "数据保护", "approval",
                  [_paso("dpo", "Revisión RGPD", "GDPR review", "GDPR 审核", ROL_ADMIN)],
                  condition={"conditions": [{"field": "trata_datos", "op": "true"}]},
                  decisions=["approve", "reject", "request_info"], required_fields=["dpa_firmado"], sla_hours=72),
            _fase("direccion", "Aprobación por importe", "Approval by amount", "按金额审批", "approval",
                  [_paso("direccion", "Dirección", "Management", "管理层", ROL_ADMIN)],
                  condition={"conditions": [{"field": "importe_anual", "op": "gt", "value": 50000}],
                             "use_policies": True},
                  decisions=["approve", "reject", "hold"], sla_hours=120, notify=[AL_SOLICITANTE]),
        ],
        "on_close_actions": [{"action": "create_task", "when": "approved",
                              "params": {"title": "Dar de alta al proveedor aprobado"}}],
        "notify": [{"event": "closed", "to": {"type": "requester"}}],
    }
    tipos = [("supplier_onboarding", _t("Alta de proveedor", "Supplier onboarding", "供应商准入"),
              ["operator", "supplier_portal"], ["none"])]
    return defn, tipos


def _compra() -> tuple[dict, list]:
    defn = {
        "fields": [
            _campo("concepto", "Concepto", "Item", "采购内容", critical=True),
            _campo("importe", "Importe", "Amount", "金额", tipo="money", critical=True, policy="coste"),
            _campo("proveedor", "Proveedor propuesto", "Proposed supplier", "建议供应商", tipo="text"),
            _campo("centro_coste", "Centro de coste", "Cost centre", "成本中心", tipo="text"),
        ],
        "submit_required": ["title", "concepto", "importe"],
        "phases": [
            _fase("responsable", "Responsable", "Manager", "主管", "approval",
                  [_paso("responsable", "Su responsable", "Line manager", "直属主管", SU_RESPONSABLE)],
                  decisions=["approve", "reject", "request_info"], sla_hours=48, notify=[A_RESPONSABLES]),
            _fase("finanzas", "Finanzas", "Finance", "财务", "approval",
                  [_paso("finanzas", "Control de gestión", "Controlling", "财务控制", ROL_ADMIN)],
                  condition={"conditions": [{"field": "importe", "op": "gt", "value": 3000}]},
                  decisions=["approve", "reject", "request_info"], sla_hours=72),
            _fase("direccion", "Dirección", "Management", "管理层", "approval",
                  [_paso("direccion", "Dirección general", "General management", "总经理", ROL_ADMIN)],
                  condition={"conditions": [{"field": "importe", "op": "gt", "value": 20000}], "use_policies": True},
                  decisions=["approve", "reject", "hold"], sla_hours=120, notify=[AL_SOLICITANTE]),
        ],
        "on_close_actions": [{"action": "create_purchase", "when": "approved"}],
        "notify": [{"event": "closed", "to": {"type": "requester"}}],
    }
    tipos = [("purchase", _t("Petición de compra", "Purchase request", "采购申请"), ["operator", "internal_portal"],
              ["project", "none"])]
    return defn, tipos


def _acceso() -> tuple[dict, list]:
    nivel = [_opcion("lectura", "Lectura", "Read", "只读"), _opcion("escritura", "Escritura", "Write", "读写"),
             _opcion("admin", "Administración", "Administration", "管理员")]
    defn = {
        "fields": [
            _campo("sistema", "Sistema o aplicación", "System or application", "系统或应用", tipo="text"),
            _campo("nivel", "Nivel de acceso", "Access level", "访问级别", tipo="select", options=nivel, critical=True),
            _campo("motivo", "Motivo", "Reason", "原因"),
            _campo("fecha_fin", "Hasta (si es temporal)", "Until (if temporary)", "截止日期（临时）", tipo="date"),
        ],
        "submit_required": ["title", "sistema", "nivel", "motivo"],
        "phases": [
            _fase("responsable", "Responsable", "Manager", "主管", "approval",
                  [_paso("responsable", "Su responsable", "Line manager", "直属主管", SU_RESPONSABLE)],
                  decisions=["approve", "reject", "request_info"], sla_hours=24, notify=[A_RESPONSABLES]),
            _fase("seguridad", "Seguridad", "Security", "安全", "approval",
                  [_paso("seguridad", "Propietario del sistema / seguridad", "System owner / security", "系统所有者/安全",
                         ROL_ADMIN)],
                  condition={"conditions": [{"field": "nivel", "op": "eq", "value": "admin"}]},
                  decisions=["approve", "reject"], segregation={"not_requester": True,
                                                                "not_actor_of_phases": ["responsable"]},
                  sla_hours=24),
        ],
        "on_close_actions": [{"action": "create_ticket", "when": "approved",
                              "params": {"ticket_type": "service_request"}}],
        "notify": [{"event": "closed", "to": {"type": "requester"}}],
    }
    tipos = [("access_request", _t("Petición de acceso", "Access request", "访问申请"), ["operator", "internal_portal",
                                                                                         "supplier_portal"],
              ["service", "asset", "none"])]
    return defn, tipos


def _iniciativa() -> tuple[dict, list]:
    defn = {
        "fields": [
            _campo("descripcion", "Descripción", "Description", "描述", critical=True),
            _campo("business_case", "Business case", "Business case", "业务案例", critical=True),
            _campo("presupuesto", "Presupuesto", "Budget", "预算", tipo="money", critical=True, policy="coste"),
            _campo("horas", "Horas estimadas", "Estimated hours", "预计工时", tipo="number", critical=True,
                   policy="esfuerzo"),
            _campo("beneficios", "Beneficios esperados", "Expected benefits", "预期收益", critical=True),
        ],
        "submit_required": ["title", "descripcion", "business_case"],
        "phases": [
            _fase("evaluacion", "Evaluación", "Assessment", "评估", "work",
                  [_paso("pmo", "PMO", "PMO", "项目管理办公室", ROL_PM, mode="task")],
                  decisions=["complete", "request_info", "reject"], required_fields=["presupuesto", "horas"],
                  sla_hours=120),
            _fase("comite_cartera", "Comité de cartera", "Portfolio board", "项目组合委员会", "committee",
                  [_paso("comite", "Resolución", "Resolution", "决议", ROL_ADMIN)],
                  decisions=["approve", "reject", "hold"], lock_client_from_here=True,
                  committee={"executive_summary": True}, sla_hours=480, notify=[AL_SOLICITANTE]),
        ],
        "execution": ["portfolio", "new_project"],
        "on_close_actions": [{"action": "create_portfolio_proposal", "when": "approved"}],
        "notify": [{"event": "closed", "to": {"type": "requester"}}],
    }
    tipos = [("portfolio_initiative", _t("Iniciativa de cartera", "Portfolio initiative", "项目组合倡议"),
              ["operator", "internal_portal"], ["none"])]
    return defn, tipos


def _rrhh() -> tuple[dict, list]:
    tipo = [_opcion("certificado", "Certificado", "Certificate", "证明"),
            _opcion("datos", "Cambio de datos", "Data change", "资料变更"),
            _opcion("formacion", "Formación", "Training", "培训"), _opcion("otro", "Otro", "Other", "其他")]
    defn = {
        "fields": [_campo("tipo", "Tipo de petición", "Request type", "申请类型", tipo="select", options=tipo),
                   _campo("detalle", "Detalle", "Details", "详情")],
        "submit_required": ["title", "tipo", "detalle"],
        "phases": [_fase("rrhh", "RR. HH.", "HR", "人力资源", "work",
                         [_paso("rrhh", "Atender", "Handle", "处理", ROL_RRHH, mode="task")],
                         decisions=["complete", "request_info", "reject"], sla_hours=72, notify=[A_RESPONSABLES])],
        "notify": [{"event": "closed", "to": {"type": "requester"}}],
    }
    tipos = [("hr_request", _t("Petición a RR. HH.", "HR request", "人力资源申请"), ["operator", "internal_portal"],
              ["none"])]
    return defn, tipos


#: clave → (nombre, descripción, constructor). El piloto se instala con sus grupos.
PLANTILLAS: dict[str, tuple[dict, dict, Optional[Callable]]] = {
    "piloto_digital": (_t("Nueva funcionalidad con CAB y comité", "New feature with CAB and committee",
                          "带 CAB 和委员会的新功能"),
                       _t("Triaje, estudio, CAB, Legal y Compliance en paralelo, gobernanza y comité",
                          "Triage, study, CAB, parallel Legal and Compliance, governance and committee",
                          "分诊、研究、CAB、法务与合规并行、治理和委员会"), None),
    "cambio_itil": (_t("Petición de cambio ITIL", "ITIL change request", "ITIL 变更请求"),
                    _t("Estándar sin CAB, normal con CAB, urgente con CAB de emergencia",
                       "Standard without CAB, normal with CAB, emergency with ECAB", "标准无需 CAB，常规需 CAB，紧急需 ECAB"),
                    _cambio_itil),
    "alta_proveedor": (_t("Alta de proveedor", "Supplier onboarding", "供应商准入"),
                       _t("Compras, protección de datos si aplica y dirección por importe",
                          "Procurement, data protection if applicable and management by amount",
                          "采购、数据保护（如适用）和按金额审批"), _alta_proveedor),
    "compra_por_importe": (_t("Petición de compra", "Purchase request", "采购申请"),
                           _t("Responsable, finanzas y dirección según el importe",
                              "Manager, finance and management by amount", "主管、财务和管理层按金额审批"), _compra),
    "acceso_permisos": (_t("Petición de acceso o permisos", "Access request", "访问权限申请"),
                        _t("Responsable y, si es administración, seguridad", "Manager and, for admin access, security",
                           "主管审批，管理员权限需安全审批"), _acceso),
    "iniciativa_cartera": (_t("Iniciativa de cartera con business case", "Portfolio initiative with business case",
                              "带业务案例的项目组合倡议"),
                           _t("Evaluación de la PMO y comité de cartera; termina en Cartera",
                              "PMO assessment and portfolio board; ends in Portfolio", "PMO 评估和项目组合委员会"),
                           _iniciativa),
    "peticion_rrhh": (_t("Petición a RR. HH.", "HR request", "人力资源申请"),
                      _t("Una fase de atención por RR. HH.", "One handling phase by HR", "由人力资源处理"), _rrhh),
}


def listar(idioma: str = "es") -> list[dict]:
    return [{"key": k, "name": D.nombre(n, idioma), "description": D.nombre(d, idioma), "name_i18n": n}
            for k, (n, d, _c) in PLANTILLAS.items()]


def instalar(db: Session, usuario, clave: str) -> dict:
    """Crea en la empresa el flujo de la plantilla y sus tipos (si no existen). Commitea."""
    from app.models.demanda import DemandFlow, DemandRequestType
    from app.services.audit import audit_log
    if clave not in PLANTILLAS:
        raise error(404, "dem_plantilla_no_encontrada", plantilla=clave)
    org = getattr(usuario, "organization_id", None)
    if clave == "piloto_digital":
        from app.services.demanda.plantillas import sembrar_plantilla_piloto
        res = sembrar_plantilla_piloto(db, org, usuario.id)
        audit_log(db, usuario, "INSTALL_TEMPLATE", "demand_flow", res["flow_id"], clave)
        db.commit()
        return res
    nombre_, descripcion, constructor = PLANTILLAS[clave]
    flujo = db.query(DemandFlow).filter(DemandFlow.organization_id == org, DemandFlow.key == clave).first()
    creado = flujo is None
    defn, tipos = constructor()
    if creado:
        flujo = DemandFlow(organization_id=org, key=clave, name=nombre_[IDIOMA_DE_RESPALDO], description=descripcion[IDIOMA_DE_RESPALDO],
                           definition=json.dumps(defn, ensure_ascii=False), version=1, is_active=True,
                           created_by=usuario.id)
        db.add(flujo)
        db.flush()
    for i, (k, nombres, canales, alcances) in enumerate(tipos):
        if db.query(DemandRequestType.id).filter(DemandRequestType.organization_id == org,
                                                 DemandRequestType.key == k).first():
            continue
        db.add(DemandRequestType(organization_id=org, key=k, name=nombres[IDIOMA_DE_RESPALDO],
                                 name_i18n=json.dumps(nombres, ensure_ascii=False), channels=json.dumps(canales),
                                 scopes=json.dumps(alcances), requires_project=alcances == ["project"],
                                 allows_standalone="none" in alcances, flow_id=flujo.id, sort_order=10 + i))
    audit_log(db, usuario, "INSTALL_TEMPLATE", "demand_flow", flujo.id, clave, new_values={"created": creado})
    db.commit()
    return {"flow_id": flujo.id, "created": creado}


def exportar(db: Session, flujo, tipos: list) -> dict:
    return {"format": FORMATO, "flow": {"key": flujo.key, "name": flujo.name, "description": flujo.description,
                                        "version": flujo.version, "definition": D.cargar(flujo.definition)},
            "types": [{"key": t.key, "name": t.name, "name_i18n": json.loads(t.name_i18n or "{}"),
                       "channels": json.loads(t.channels or "[]"), "scopes": json.loads(t.scopes or "[]"),
                       "requires_project": bool(t.requires_project), "allows_standalone": bool(t.allows_standalone)}
                      for t in tipos]}


def importar(db: Session, usuario, doc: dict) -> dict:
    """Importa un flujo exportado (siempre como flujo nuevo). Commitea."""
    from app.models.demanda import DemandFlow, DemandRequestType
    from app.services.audit import audit_log
    if not isinstance(doc, dict) or doc.get("format") != FORMATO or not isinstance(doc.get("flow"), dict):
        raise error(422, "dem_importacion_no_valida")
    defn = doc["flow"].get("definition") or {}
    errores = D.validar(defn)
    if errores:
        raise error(422, "dem_definicion_invalida", n=len(errores))
    org = getattr(usuario, "organization_id", None)
    flujo = DemandFlow(organization_id=org, key=None, name=str(doc["flow"].get("name") or "Importado")[:200],
                       description=doc["flow"].get("description"), definition=json.dumps(defn, ensure_ascii=False),
                       version=1, is_active=True, created_by=usuario.id)
    db.add(flujo)
    db.flush()
    creados = []
    for t in doc.get("types") or []:
        k = str(t.get("key") or "")
        if not k or db.query(DemandRequestType.id).filter(DemandRequestType.organization_id == org,
                                                          DemandRequestType.key == k).first():
            continue
        db.add(DemandRequestType(organization_id=org, key=k[:60], name=str(t.get("name") or k)[:200],
                                 name_i18n=json.dumps(t.get("name_i18n") or {}, ensure_ascii=False),
                                 channels=json.dumps(t.get("channels") or ["operator"]),
                                 scopes=json.dumps(t.get("scopes") or ["none"]),
                                 requires_project=bool(t.get("requires_project")),
                                 allows_standalone=bool(t.get("allows_standalone", True)), flow_id=flujo.id))
        creados.append(k)
    audit_log(db, usuario, "IMPORT", "demand_flow", flujo.id, flujo.name, new_values={"types": creados})
    db.commit()
    return {"flow_id": flujo.id, "types": creados}
