"""
BPMN Process Service — CRUD + versioning + seeding for the in-app BPMN editor.

Seed catalogue: every business process the tool already implements is registered
here as a BPMN 2.0 diagram so users can open it in the editor, inspect it, or
redesign it. Adding a new entry to PROCESS_CATALOGUE auto-creates a new editable
process on the next seed run.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Optional
from xml.sax.saxutils import escape

from sqlalchemy.orm import Session

from app.models.bpmn_process import BPMNProcess, BPMNProcessVersion, BPMNProcessStatus


# ── Seed catalogue ────────────────────────────────────────────────────────────
# Each entry: (key, category, name, description, [steps...])
# `steps` is the linear flow: states/stages/activities. The first becomes the
# StartEvent, the last becomes the EndEvent, and middle items become Tasks.
PROCESS_CATALOGUE: list[dict] = [
    # ── Incident & Ticket Management ──────────────────────────────────────────
    {"key": "incident_management", "category": "incident", "icon": "🎫",
     "name": "Gestión de Incidencias",
     "description": "Ciclo de vida estándar de un ticket de incidencia.",
     "steps": ["Nuevo", "Asignado", "En progreso", "Pendiente cliente", "Resuelto", "Cerrado"]},
    {"key": "service_request", "category": "incident", "icon": "📥",
     "name": "Petición de Servicio",
     "description": "Flujo de petición desde el catálogo de servicios.",
     "steps": ["Solicitado", "Aprobación", "En curso", "Entregado", "Cerrado"]},
    {"key": "ticket_assignment_ml", "category": "ai-ml", "icon": "🤖",
     "name": "Asignación Inteligente (ML)",
     "description": "Routing automático del ticket al agente óptimo.",
     "steps": ["Ticket creado", "Extraer features", "Predecir agente", "Validar carga", "Asignar"]},
    {"key": "auto_resolution", "category": "ai-ml", "icon": "✨",
     "name": "Auto-Resolución",
     "description": "Sugerencia y aplicación automática de resolución vía IA.",
     "steps": ["Ticket entrante", "Buscar similares", "Confidence score", "Sugerir respuesta", "Auto-cerrar"]},
    {"key": "alert_correlation", "category": "ai-ml", "icon": "🔗",
     "name": "Correlación de Alertas",
     "description": "Agrupación de alertas relacionadas en un único incidente.",
     "steps": ["Alerta entrante", "Buscar correlación", "Agrupar", "Crear incidente padre", "Notificar"]},
    {"key": "voice_agent_ivr", "category": "ai-ml", "icon": "📞",
     "name": "Agente de Voz / IVR",
     "description": "Flujo conversacional del agente de voz para soporte.",
     "steps": ["Llamada entrante", "Identificar usuario", "Intent detection", "Resolver / escalar", "Cierre llamada"]},
    {"key": "multichannel_intake", "category": "incident", "icon": "📨",
     "name": "Intake Multi-Canal",
     "description": "Recepción de tickets desde email, chat, portal, móvil.",
     "steps": ["Mensaje entrante", "Normalizar canal", "Extraer datos", "Crear ticket", "Confirmación"]},
    {"key": "escalation_routing", "category": "incident", "icon": "🚨",
     "name": "Escalado",
     "description": "Reglas de escalado por SLA, prioridad y on-call.",
     "steps": ["Threshold check", "Identificar destino", "Notificar", "Re-asignar", "Auditar"]},
    {"key": "sla_monitoring", "category": "incident", "icon": "⏱️",
     "name": "Monitorización de SLA",
     "description": "Vigilancia continua de plazos SLA del ticket.",
     "steps": ["Ticket abierto", "OK", "At risk", "Breach", "Reportar"]},
    {"key": "major_incident", "category": "incident", "icon": "🔥",
     "name": "Incidencia Mayor",
     "description": "Gestión coordinada de incidencias críticas.",
     "steps": ["Declarar", "Convocar war-room", "Mitigar", "Resolver", "Post-mortem"]},
    {"key": "oncall_scheduling", "category": "operations", "icon": "📅",
     "name": "Planificación On-Call",
     "description": "Rotación y asignación de guardias.",
     "steps": ["Definir rotación", "Asignar turno", "Notificar", "Activar guardia", "Cierre turno"]},

    # ── Change Management ─────────────────────────────────────────────────────
    {"key": "change_management", "category": "change", "icon": "🔄",
     "name": "Gestión de Cambios",
     "description": "Workflow estándar de un cambio (RFC).",
     "steps": ["Borrador", "Enviado", "Revisión CAB", "Aprobado", "Programado", "Implementado", "Cerrado"]},
    {"key": "cab_review", "category": "change", "icon": "🧑‍⚖️",
     "name": "Comité CAB",
     "description": "Reunión de revisión y aprobación del CAB.",
     "steps": ["Cambios pendientes", "Convocar CAB", "Debate", "Votación", "Decisión registrada"]},
    {"key": "change_impact_analysis", "category": "change", "icon": "📊",
     "name": "Análisis de Impacto",
     "description": "Evaluación de impacto en CMDB y servicios.",
     "steps": ["Cambio propuesto", "Identificar CIs afectados", "Calcular riesgo", "Documentar", "Adjuntar al RFC"]},
    {"key": "change_rollout", "category": "change", "icon": "🚀",
     "name": "Despliegue Escalonado",
     "description": "Rollout por fases con puntos de control.",
     "steps": ["Aprobado", "Piloto", "Wave 1", "Wave 2", "Producción", "Cierre"]},

    # ── Problem Management & Knowledge ────────────────────────────────────────
    {"key": "problem_management", "category": "problem", "icon": "🧩",
     "name": "Gestión de Problemas",
     "description": "Análisis de causa raíz y errores conocidos.",
     "steps": ["Abierto", "Investigando", "Error conocido", "Resuelto", "Cerrado"]},
    {"key": "rca_wizard", "category": "problem", "icon": "🔍",
     "name": "Asistente RCA",
     "description": "Investigación guiada de causa raíz (5 Whys).",
     "steps": ["Definir problema", "Recopilar datos", "5 Whys", "Causa raíz", "Plan acción"]},
    {"key": "kedb_lookup", "category": "knowledge", "icon": "📚",
     "name": "Base de Errores Conocidos",
     "description": "Consulta y sugerencia de soluciones existentes.",
     "steps": ["Síntomas detectados", "Buscar KEDB", "Match score", "Aplicar workaround", "Feedback"]},
    {"key": "kb_authoring", "category": "knowledge", "icon": "✍️",
     "name": "Creación de Artículos KB",
     "description": "Ciclo editorial de artículos de la base de conocimiento.",
     "steps": ["Borrador", "Revisión", "Publicado", "Mantenimiento", "Archivado"]},
    {"key": "smart_catalog", "category": "service", "icon": "🛍️",
     "name": "Catálogo Inteligente",
     "description": "Catálogo de servicios con sugerencias contextuales.",
     "steps": ["Cliente busca", "Recomendaciones IA", "Selección", "Solicitud", "Tracking"]},

    # ── Project Delivery & Tasks ──────────────────────────────────────────────
    {"key": "project_lifecycle", "category": "project", "icon": "📋",
     "name": "Ciclo de Vida de Proyecto",
     "description": "Estados de un proyecto desde planificación a cierre.",
     "steps": ["Planificación", "Activo", "On hold", "Pausado", "Completado", "Cerrado"]},
    {"key": "task_workflow", "category": "project", "icon": "✅",
     "name": "Workflow de Tareas",
     "description": "Estados estándar de una tarea ágil.",
     "steps": ["Backlog", "To-do", "En progreso", "Bloqueada", "Revisión", "Hecha"]},
    {"key": "project_phase", "category": "project", "icon": "🏁",
     "name": "Fases de Proyecto",
     "description": "Hitos por fase y aprobación de paso de gate.",
     "steps": ["Inicio", "Diseño", "Construcción", "Pruebas", "Aceptación", "Cierre"]},
    {"key": "task_auto_assignment", "category": "ai-ml", "icon": "🎯",
     "name": "Auto-Asignación de Tareas",
     "description": "ML asigna la tarea al miembro más adecuado del equipo.",
     "steps": ["Tarea creada", "Extraer skills requeridos", "Score por usuario", "Capacidad", "Asignar"]},
    {"key": "sprint_planning", "category": "project", "icon": "🏃",
     "name": "Planificación de Sprint",
     "description": "Ciclo Scrum: planning, ejecución, review, retro.",
     "steps": ["Refinement", "Planning", "En curso", "Review", "Retrospectiva", "Cerrado"]},

    # ── Approvals & Finance ───────────────────────────────────────────────────
    {"key": "multi_level_approval", "category": "governance", "icon": "✔️",
     "name": "Aprobación Multinivel",
     "description": "Cadena de aprobaciones con escalado y delegación.",
     "steps": ["Solicitud", "Nivel 1", "Nivel 2", "Decisión final", "Notificación"]},
    {"key": "timesheet_approval", "category": "finance", "icon": "🕒",
     "name": "Aprobación de Timesheets",
     "description": "Envío de partes y aprobación por manager/PM.",
     "steps": ["Imputar horas", "Enviar", "Revisión PM", "Aprobado / rechazado", "Cierre semanal"]},
    {"key": "expense_approval", "category": "finance", "icon": "🧾",
     "name": "Aprobación de Gastos",
     "description": "Reembolso de gastos con justificantes.",
     "steps": ["Borrador", "Enviado", "Aprobado", "Rechazado", "Reembolsado"]},
    {"key": "document_approval", "category": "governance", "icon": "📄",
     "name": "Aprobación de Documentos",
     "description": "Firma y aprobación documental.",
     "steps": ["Pendiente", "En revisión", "Aprobado", "Publicado", "Archivado"]},
    {"key": "invoice_workflow", "category": "finance", "icon": "💶",
     "name": "Workflow de Facturas",
     "description": "Emisión, envío y conciliación de facturas.",
     "steps": ["Borrador", "Emitida", "Enviada", "Pagada", "Cerrada"]},
    {"key": "milestone_billing", "category": "finance", "icon": "🎯",
     "name": "Facturación por Hitos",
     "description": "Generación de factura al cumplir un hito SOW.",
     "steps": ["Hito definido", "Completado", "Aprobación cliente", "Generar factura", "Cobro"]},
    {"key": "revenue_recognition", "category": "finance", "icon": "📈",
     "name": "Reconocimiento de Ingresos (ASC606)",
     "description": "Reconocimiento de ingresos por obligación de desempeño.",
     "steps": ["Identificar contrato", "POBs", "Asignar precio", "Cumplir obligación", "Reconocer"]},

    # ── AI/ML & Analytics Workflows ───────────────────────────────────────────
    {"key": "churn_prediction", "category": "ai-ml", "icon": "📉",
     "name": "Predicción de Churn",
     "description": "Detección temprana de clientes en riesgo.",
     "steps": ["Recoger features", "Inferencia ML", "Score", "Alerta CSM", "Plan retención"]},
    {"key": "anomaly_detection", "category": "security", "icon": "🛡️",
     "name": "Detección de Anomalías de Login",
     "description": "Identificación de patrones inusuales de acceso.",
     "steps": ["Login event", "Baseline check", "Anomaly score", "Alertar SecOps", "Bloquear"]},
    {"key": "revenue_forecast", "category": "ai-ml", "icon": "🔮",
     "name": "Forecasting de Ingresos",
     "description": "Proyección de ingresos basada en pipeline.",
     "steps": ["Snapshot pipeline", "Ponderar oportunidades", "Modelo predictivo", "Generar forecast", "Publicar"]},
    {"key": "incident_predictions", "category": "ai-ml", "icon": "📊",
     "name": "Predicciones de Incidencias",
     "description": "Predicción de MTTR y volumen de tickets.",
     "steps": ["Datos históricos", "Entrenar", "Inferencia", "Dashboard", "Reentrenar"]},
    {"key": "semantic_feedback", "category": "ai-ml", "icon": "🧠",
     "name": "Loop de Feedback Semántico",
     "description": "Aprendizaje continuo a partir del feedback del usuario.",
     "steps": ["Predicción IA", "Recibir feedback", "Etiquetar", "Reentrenar", "Desplegar v+1"]},
    {"key": "project_overrun_ml", "category": "ai-ml", "icon": "⚠️",
     "name": "Predicción de Sobrecoste",
     "description": "ML para anticipar desviaciones de proyecto.",
     "steps": ["Snapshot proyecto", "Inferencia", "Riesgo", "Alerta PM", "Mitigación"]},

    # ── Workforce & HR ────────────────────────────────────────────────────────
    {"key": "performance_review", "category": "hr", "icon": "🌟",
     "name": "Ciclo de Performance Review",
     "description": "Evaluación semestral/anual de desempeño.",
     "steps": ["Apertura ciclo", "Auto-evaluación", "Manager review", "360°", "Calibración", "Cierre"]},
    {"key": "review_360", "category": "hr", "icon": "🔄",
     "name": "Review 360°",
     "description": "Recogida de feedback de pares, manager y reportes.",
     "steps": ["Solicitud", "Pendiente respuestas", "Enviado", "Consolidado", "Aprobado"]},
    {"key": "absence_request", "category": "hr", "icon": "🏖️",
     "name": "Solicitud de Ausencia",
     "description": "Vacaciones, baja, permisos.",
     "steps": ["Solicitud", "Validar saldo", "Aprobación manager", "Aprobado", "Calendario"]},
    {"key": "resource_forecast", "category": "resources", "icon": "📆",
     "name": "Forecast de Recursos",
     "description": "Proyección de capacidad vs. demanda.",
     "steps": ["Capacidad actual", "Demanda prevista", "Gap analysis", "Plan staffing", "Publicar"]},
    {"key": "training_plan", "category": "hr", "icon": "🎓",
     "name": "Plan de Formación",
     "description": "Asignación y seguimiento de cursos.",
     "steps": ["Detectar gap", "Asignar curso", "En progreso", "Completado", "Certificado"]},
    {"key": "onboarding", "category": "hr", "icon": "🚪",
     "name": "Onboarding de Empleado",
     "description": "Alta y formación inicial.",
     "steps": ["Pre-boarding", "Día 1", "Semana 1", "Mes 1", "Confirmación"]},

    # ── Governance, GDPR, Compliance ──────────────────────────────────────────
    {"key": "gdpr_request", "category": "governance", "icon": "🔐",
     "name": "Solicitud GDPR",
     "description": "Acceso, rectificación o supresión de datos personales.",
     "steps": ["Recibir solicitud", "Verificar identidad", "Procesando", "Completar", "Notificar"]},
    {"key": "governance_compliance", "category": "governance", "icon": "🏛️",
     "name": "Compliance de Gobernanza",
     "description": "Verificación periódica de controles de gobernanza.",
     "steps": ["Definir control", "Auditar", "Hallazgos", "Remediación", "Cierre"]},
    {"key": "esign_workflow", "category": "governance", "icon": "🖋️",
     "name": "Firma Electrónica",
     "description": "Solicitud, firma y archivo de documento.",
     "steps": ["Preparar", "Enviar a firmar", "Firmado", "Archivar", "Notificar"]},
    {"key": "grc_audit", "category": "governance", "icon": "📋",
     "name": "Auditoría GRC",
     "description": "Programa de auditorías GRC y seguimiento.",
     "steps": ["Plan", "Ejecución", "Hallazgos", "Plan de acción", "Cierre"]},
    {"key": "uat_acceptance", "category": "project", "icon": "🧪",
     "name": "UAT — User Acceptance Testing",
     "description": "Aceptación de entregables por el cliente.",
     "steps": ["Plan UAT", "Ejecución", "Defectos", "Re-test", "Aceptado"]},

    # ── Configuration, Integration, Data ──────────────────────────────────────
    {"key": "workflow_blueprint", "category": "config", "icon": "🧱",
     "name": "Blueprint de Workflow",
     "description": "Diseño visual de workflows declarativos del Service Desk.",
     "steps": ["Borrador", "Compilar reglas", "Publicar", "En uso", "Archivado"]},
    {"key": "automation_workflow", "category": "config", "icon": "⚙️",
     "name": "Workflow de Automatización",
     "description": "Triggers + condiciones + acciones programáticas.",
     "steps": ["Borrador", "Activo", "Disparado", "Pausado", "Archivado"]},
    {"key": "data_import", "category": "data", "icon": "📥",
     "name": "Importación de Datos",
     "description": "Carga masiva CSV / Excel.",
     "steps": ["Subir archivo", "Validación", "Procesando", "Completado", "Reporte"]},
    {"key": "jira_sync", "category": "integration", "icon": "🔁",
     "name": "Sincronización con Jira",
     "description": "Sync continuo bidireccional con Jira.",
     "steps": ["Pull Jira", "Diff", "Push local", "Reconciliar", "Próximo ciclo"]},
    {"key": "etl_pipeline", "category": "data", "icon": "🛠️",
     "name": "Pipeline ETL",
     "description": "Extracción, transformación y carga en el data warehouse.",
     "steps": ["Extract", "Transform", "Validate", "Load", "Quality check"]},
    {"key": "data_governance_review", "category": "data", "icon": "📊",
     "name": "Revisión Data Governance",
     "description": "Aprobación de datasets y políticas de acceso.",
     "steps": ["Catalogar", "Clasificar", "Aprobación", "Publicado", "Auditoría"]},
]


# ── BPMN XML generator ────────────────────────────────────────────────────────
def clave_unica(db, clave: str, organization_id) -> str:
    """Una clave de proceso libre en esa organizacion, con sufijo si hace falta.

    Auditoria 2026-08 (hallazgo 22): estaba en el endpoint. El filtro por
    organizacion ya estaba y es el correcto — la unicidad de la clave es **por
    organizacion**, no global, asi que dos clientes pueden tener cada uno un
    proceso `aprobacion`.
    """
    from app.models.bpmn_process import BPMNProcess

    base = clave
    n = 1
    while (db.query(BPMNProcess)
             .filter(BPMNProcess.key == clave,
                     BPMNProcess.organization_id == organization_id)
             .first()):
        n += 1
        clave = f"{base}_{n}"
    return clave


#: Tamaños de los elementos del diagrama, en píxeles. Los eventos son círculos
#: pequeños; las tareas, cajas.
_TAMANO_EVENTO = (36, 36)
_TAMANO_TAREA = (110, 80)

#: Separación horizontal entre elementos.
_SEPARACION = 60


def _elementos_bpmn(steps: list[str]) -> list[tuple[str, str, str]]:
    """Convierte la lista de pasos en `(id, tipo, etiqueta)`.

    El primero es el evento de inicio y el último el de fin; los de en medio,
    tareas. Es una convención de esta función, no de BPMN: el formato admite
    grafos, y aquí se genera siempre una cadena lineal.
    """
    elementos = []
    for idx, etiqueta in enumerate(steps):
        if idx == 0:
            tipo, eid = "startEvent", f"StartEvent_{idx + 1}"
        elif idx == len(steps) - 1:
            tipo, eid = "endEvent", f"EndEvent_{idx + 1}"
        else:
            tipo, eid = "task", f"Activity_{idx + 1}"
        elementos.append((eid, tipo, etiqueta))
    return elementos


def _proceso_bpmn(elementos: list[tuple[str, str, str]],
                  flujos: list[tuple[str, str, str]]) -> str:
    """Los nodos y las transiciones del proceso.

    Cada nodo declara sus flujos de entrada y salida: BPMN lo exige aunque la
    información esté también en el propio `sequenceFlow`.
    """
    partes = []
    for eid, tipo, etiqueta in elementos:
        entradas = "".join(f"<bpmn:incoming>{f[0]}</bpmn:incoming>" for f in flujos if f[2] == eid)
        salidas = "".join(f"<bpmn:outgoing>{f[0]}</bpmn:outgoing>" for f in flujos if f[1] == eid)
        partes.append(
            f'<bpmn:{tipo} id="{eid}" name="{escape(etiqueta)}">{entradas}{salidas}</bpmn:{tipo}>'
        )
    partes += [
        f'<bpmn:sequenceFlow id="{fid}" sourceRef="{src}" targetRef="{tgt}" />'
        for fid, src, tgt in flujos
    ]
    return "".join(partes)


def _diagrama_bpmn(elementos: list[tuple[str, str, str]],
                   flujos: list[tuple[str, str, str]]) -> tuple[str, str]:
    """Las formas y las líneas del diagrama, colocadas en una fila horizontal.

    Sin esto el diagrama se abre sin posiciones y el editor lo apila todo en la
    esquina, que es lo mismo que no tener diagrama.

    Los eventos se bajan 22 px para que su centro quede alineado con el de las
    tareas, que son más altas.
    """
    y = 120
    formas, lineas = [], []
    x = 180

    for indice, (eid, tipo, _) in enumerate(elementos):
        ancho, alto = _TAMANO_EVENTO if tipo in ("startEvent", "endEvent") else _TAMANO_TAREA
        forma_y = y + 22 if tipo in ("startEvent", "endEvent") else y
        formas.append(
            f'<bpmndi:BPMNShape id="{eid}_di" bpmnElement="{eid}">'
            f'<dc:Bounds x="{x}" y="{forma_y}" width="{ancho}" height="{alto}" />'
            f"</bpmndi:BPMNShape>"
        )

        if indice < len(flujos):
            fid = flujos[indice][0]
            centro_y = y + 60 if tipo == "task" else y + 40
            lineas.append(
                f'<bpmndi:BPMNEdge id="{fid}_di" bpmnElement="{fid}">'
                f'<di:waypoint x="{x + ancho}" y="{centro_y}" />'
                f'<di:waypoint x="{x + ancho + _SEPARACION}" y="{centro_y}" />'
                f"</bpmndi:BPMNEdge>"
            )
        x += ancho + _SEPARACION

    return "".join(formas), "".join(lineas)


def build_bpmn_xml(process_key: str, process_name: str, steps: list[str]) -> str:
    """Diagrama BPMN 2.0 válido a partir de una lista lineal de pasos.

    El primer paso es el evento de inicio, el último el de fin, y los de en
    medio tareas. Incluye la capa de diagrama (BPMNDI) para que se abra
    colocado y no haya que maquetarlo a mano.
    """
    # Un proceso necesita al menos un principio y un final: con menos, el XML
    # sería válido y el diagrama no diría nada.
    if not steps:
        steps = ["Start", "End"]
    if len(steps) == 1:
        steps = [steps[0], "Done"]

    proc_id = f"Process_{process_key}"
    elementos = _elementos_bpmn(steps)
    flujos = [
        (f"Flow_{i + 1}", elementos[i][0], elementos[i + 1][0])
        for i in range(len(elementos) - 1)
    ]
    formas, lineas = _diagrama_bpmn(elementos, flujos)

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"
                  xmlns:dc="http://www.omg.org/spec/DD/20100524/DC"
                  xmlns:di="http://www.omg.org/spec/DD/20100524/DI"
                  id="Definitions_{process_key}"
                  targetNamespace="http://contecflow/bpmn">
  <bpmn:process id="{proc_id}" name="{escape(process_name)}" isExecutable="false">
    {_proceso_bpmn(elementos, flujos)}
  </bpmn:process>
  <bpmndi:BPMNDiagram id="BPMNDiagram_1">
    <bpmndi:BPMNPlane id="BPMNPlane_1" bpmnElement="{proc_id}">
      {formas}
      {lineas}
    </bpmndi:BPMNPlane>
  </bpmndi:BPMNDiagram>
</bpmn:definitions>"""


def empty_bpmn_xml(process_name: str = "New Process") -> str:
    """Minimal empty BPMN diagram for newly created custom processes."""
    return build_bpmn_xml("new_process", process_name, ["Start", "End"])


# ── Service helpers ───────────────────────────────────────────────────────────
def serialize_process(p: BPMNProcess, include_versions: bool = False) -> dict:
    out = {
        "id": p.id,
        "key": p.key,
        "name": p.name,
        "description": p.description,
        "category": p.category,
        "icon": p.icon,
        "source_kind": p.source_kind,
        "source_ref": p.source_ref,
        "latest_version": p.latest_version,
        "status": p.status.value if p.status else "draft",
        "is_seeded": p.is_seeded,
        "is_active": p.is_active,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }
    if include_versions:
        out["versions"] = [serialize_version(v, include_xml=False) for v in p.versions]
    return out


def serialize_version(v: BPMNProcessVersion, include_xml: bool = True) -> dict:
    out = {
        "id": v.id,
        "process_id": v.process_id,
        "version": v.version,
        "is_published": v.is_published,
        "notes": v.notes,
        "published_at": v.published_at.isoformat() if v.published_at else None,
        "created_at": v.created_at.isoformat() if v.created_at else None,
        "created_by_user_id": v.created_by_user_id,
    }
    if include_xml:
        out["bpmn_xml"] = v.bpmn_xml
    return out


def list_processes(db: Session, organization_id: Optional[str] = None,
                   category: Optional[str] = None,
                   include_inactive: bool = False) -> list[BPMNProcess]:
    q = db.query(BPMNProcess)
    if organization_id is not None:
        q = q.filter((BPMNProcess.organization_id == organization_id) |
                     (BPMNProcess.organization_id.is_(None)))
    if category:
        q = q.filter(BPMNProcess.category == category)
    if not include_inactive:
        q = q.filter(BPMNProcess.is_active.is_(True))
    return q.order_by(BPMNProcess.category, BPMNProcess.name).all()


def get_process(db: Session, process_id: str) -> Optional[BPMNProcess]:
    return db.query(BPMNProcess).filter(
        BPMNProcess.id == process_id,
        BPMNProcess.is_active.is_(True),
    ).first()


def get_latest_version(db: Session, process_id: str) -> Optional[BPMNProcessVersion]:
    p = get_process(db, process_id)
    if not p:
        return None
    return (db.query(BPMNProcessVersion)
              .filter(BPMNProcessVersion.process_id == process_id,
                      BPMNProcessVersion.version == p.latest_version)
              .first())


def get_version(db: Session, process_id: str, version: int) -> Optional[BPMNProcessVersion]:
    return (db.query(BPMNProcessVersion)
              .filter(BPMNProcessVersion.process_id == process_id,
                      BPMNProcessVersion.version == version)
              .first())


def create_process(db: Session, *, name: str, category: str, key: str,
                   description: Optional[str] = None, icon: Optional[str] = None,
                   bpmn_xml: Optional[str] = None,
                   organization_id: Optional[str] = None,
                   created_by_user_id: Optional[str] = None,
                   is_seeded: bool = False, source_kind: str = "custom",
                   source_ref: Optional[str] = None) -> BPMNProcess:
    proc = BPMNProcess(
        organization_id=organization_id, key=key, name=name,
        description=description, category=category, icon=icon,
        is_seeded=is_seeded, source_kind=source_kind, source_ref=source_ref,
        created_by_user_id=created_by_user_id, latest_version=1,
        status=BPMNProcessStatus.draft,
    )
    db.add(proc)
    db.flush()
    xml = bpmn_xml or empty_bpmn_xml(name)
    v = BPMNProcessVersion(
        process_id=proc.id, version=1, bpmn_xml=xml,
        notes="initial", created_by_user_id=created_by_user_id,
    )
    db.add(v)
    db.commit()
    db.refresh(proc)
    return proc


def save_new_version(db: Session, *, process_id: str, bpmn_xml: str,
                     notes: Optional[str] = None,
                     created_by_user_id: Optional[str] = None) -> BPMNProcessVersion:
    proc = get_process(db, process_id)
    if not proc:
        raise ValueError(f"process {process_id} not found")
    next_version = (proc.latest_version or 0) + 1
    v = BPMNProcessVersion(
        process_id=process_id, version=next_version, bpmn_xml=bpmn_xml,
        notes=notes, created_by_user_id=created_by_user_id,
    )
    db.add(v)
    proc.latest_version = next_version
    proc.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(v)
    return v


def update_metadata(db: Session, process_id: str, **fields) -> Optional[BPMNProcess]:
    proc = get_process(db, process_id)
    if not proc:
        return None
    for k, val in fields.items():
        if val is None:
            continue
        if k == "status":
            proc.status = BPMNProcessStatus(val)
        elif hasattr(proc, k):
            setattr(proc, k, val)
    proc.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(proc)
    return proc


def publish_version(db: Session, process_id: str, version: int) -> Optional[BPMNProcessVersion]:
    v = get_version(db, process_id, version)
    if not v:
        return None
    v.is_published = True
    v.published_at = datetime.now(timezone.utc)
    proc = v.process
    proc.status = BPMNProcessStatus.published
    db.commit()
    db.refresh(v)
    return v


def delete_process(db: Session, process_id: str) -> bool:
    proc = get_process(db, process_id)
    if not proc:
        return False
    proc.is_active = False
    proc.updated_at = datetime.now(timezone.utc)
    db.commit()
    return True


def duplicate_process(db: Session, process_id: str, *, new_name: str,
                      created_by_user_id: Optional[str] = None) -> Optional[BPMNProcess]:
    src = get_process(db, process_id)
    if not src:
        return None
    src_xml = get_latest_version(db, process_id)
    new_key = f"{src.key}_copy_{int(datetime.now(timezone.utc).timestamp())}"
    return create_process(
        db, name=new_name, category=src.category, key=new_key,
        description=src.description, icon=src.icon,
        bpmn_xml=src_xml.bpmn_xml if src_xml else None,
        organization_id=src.organization_id,
        created_by_user_id=created_by_user_id,
        is_seeded=False, source_kind="custom",
    )


# ── Seeding ───────────────────────────────────────────────────────────────────
def seed_catalogue(db: Session, organization_id: Optional[str] = None,
                   *, force: bool = False) -> dict:
    """
    Insert/update every process from PROCESS_CATALOGUE for the given org.
    - When `force=False`, existing seeded processes are left alone.
    - When `force=True`, the BPMN XML of each seeded process is regenerated
      (creating a new version). User-customised processes are never touched.
    """
    created = 0
    updated = 0
    skipped = 0
    for entry in PROCESS_CATALOGUE:
        existing = (db.query(BPMNProcess)
                    .filter(BPMNProcess.key == entry["key"],
                            BPMNProcess.organization_id == organization_id)
                    .first())
        xml = build_bpmn_xml(entry["key"], entry["name"], entry["steps"])
        if existing is None:
            create_process(
                db, name=entry["name"], category=entry["category"],
                key=entry["key"], description=entry.get("description"),
                icon=entry.get("icon"), bpmn_xml=xml,
                organization_id=organization_id, is_seeded=True,
                source_kind="seeded",
            )
            created += 1
        elif force and existing.is_seeded:
            save_new_version(db, process_id=existing.id, bpmn_xml=xml,
                             notes="re-seeded from catalogue")
            updated += 1
        else:
            skipped += 1
    return {"created": created, "updated": updated, "skipped": skipped,
            "total": len(PROCESS_CATALOGUE)}


def catalogue_keys() -> Iterable[str]:
    return [e["key"] for e in PROCESS_CATALOGUE]
