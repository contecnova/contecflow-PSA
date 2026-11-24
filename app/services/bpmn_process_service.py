"""
BPMN Process Service — CRUD + versioning + seeding for the in-app BPMN editor.

Seed catalogue: every business process the tool already implements is registered
here as a BPMN 2.0 diagram so users can open it in the editor, inspect it, or
redesign it. Adding a new entry to PROCESS_CATALOGUE auto-creates a new editable
process on the next seed run.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional
from xml.sax.saxutils import escape

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.bpmn_process import BPMNProcess, BPMNProcessVersion, BPMNProcessStatus
from app.core.asignacion import es_asignable
from app.core.codigos_de_error import error


# ── Seed catalogue ────────────────────────────────────────────────────────────
# Each entry: (key, category, name, description, [steps...])
# `steps` is the linear flow: states/stages/activities. The first becomes the
# StartEvent, the last becomes the EndEvent, and middle items become Tasks.
#
# Revision BPM 2026-11-16: `category` usa los mismos identificadores que el
# catalogo del frontend (`frontend/src/pages/bpm/catalogo/estructura*.ts`:
# proyectos, finanzas, rrhh, servicedesk, crm, admin). Antes eran otros
# (incident, ai-ml, governance…): lo sembrado no caia en ninguna categoria de
# la barra lateral. `tests/test_bpm_catalogo_traducible.py` lo comprueba.
PROCESS_CATALOGUE: list[dict] = [
    # ── Incident & Ticket Management ──────────────────────────────────────────
    {"key": "incident_management", "category": "servicedesk", "icon": "🎫",
     "name": "Gestión de Incidencias",
     "description": "Ciclo de vida estándar de un ticket de incidencia.",
     "steps": ["Nuevo", "Asignado", "En progreso", "Pendiente cliente", "Resuelto", "Cerrado"]},
    {"key": "service_request", "category": "servicedesk", "icon": "📥",
     "name": "Petición de Servicio",
     "description": "Flujo de petición desde el catálogo de servicios.",
     "steps": ["Solicitado", "Aprobación", "En curso", "Entregado", "Cerrado"]},
    {"key": "ticket_assignment_ml", "category": "servicedesk", "icon": "🤖",
     "name": "Asignación Inteligente (ML)",
     "description": "Routing automático del ticket al agente óptimo.",
     "steps": ["Ticket creado", "Extraer features", "Predecir agente", "Validar carga", "Asignar"]},
    {"key": "auto_resolution", "category": "servicedesk", "icon": "✨",
     "name": "Auto-Resolución",
     "description": "Sugerencia y aplicación automática de resolución vía IA.",
     "steps": ["Ticket entrante", "Buscar similares", "Confidence score", "Sugerir respuesta", "Auto-cerrar"]},
    {"key": "alert_correlation", "category": "servicedesk", "icon": "🔗",
     "name": "Correlación de Alertas",
     "description": "Agrupación de alertas relacionadas en un único incidente.",
     "steps": ["Alerta entrante", "Buscar correlación", "Agrupar", "Crear incidente padre", "Notificar"]},
    {"key": "voice_agent_ivr", "category": "servicedesk", "icon": "📞",
     "name": "Agente de Voz / IVR",
     "description": "Flujo conversacional del agente de voz para soporte.",
     "steps": ["Llamada entrante", "Identificar usuario", "Intent detection", "Resolver / escalar", "Cierre llamada"]},
    {"key": "multichannel_intake", "category": "servicedesk", "icon": "📨",
     "name": "Intake Multi-Canal",
     "description": "Recepción de tickets desde email, chat, portal, móvil.",
     "steps": ["Mensaje entrante", "Normalizar canal", "Extraer datos", "Crear ticket", "Confirmación"]},
    {"key": "escalation_routing", "category": "servicedesk", "icon": "🚨",
     "name": "Escalado",
     "description": "Reglas de escalado por SLA, prioridad y on-call.",
     "steps": ["Threshold check", "Identificar destino", "Notificar", "Re-asignar", "Auditar"]},
    {"key": "sla_monitoring", "category": "servicedesk", "icon": "⏱️",
     "name": "Monitorización de SLA",
     "description": "Vigilancia continua de plazos SLA del ticket.",
     "steps": ["Ticket abierto", "OK", "At risk", "Breach", "Reportar"]},
    {"key": "major_incident", "category": "servicedesk", "icon": "🔥",
     "name": "Incidencia Mayor",
     "description": "Gestión coordinada de incidencias críticas.",
     "steps": ["Declarar", "Convocar war-room", "Mitigar", "Resolver", "Post-mortem"]},
    {"key": "oncall_scheduling", "category": "servicedesk", "icon": "📅",
     "name": "Planificación On-Call",
     "description": "Rotación y asignación de guardias.",
     "steps": ["Definir rotación", "Asignar turno", "Notificar", "Activar guardia", "Cierre turno"]},

    # ── Change Management ─────────────────────────────────────────────────────
    {"key": "change_management", "category": "servicedesk", "icon": "🔄",
     "name": "Gestión de Cambios",
     "description": "Workflow estándar de un cambio (RFC).",
     "steps": ["Borrador", "Enviado", "Revisión CAB", "Aprobado", "Programado", "Implementado", "Cerrado"]},
    {"key": "cab_review", "category": "servicedesk", "icon": "🧑‍⚖️",
     "name": "Comité CAB",
     "description": "Reunión de revisión y aprobación del CAB.",
     "steps": ["Cambios pendientes", "Convocar CAB", "Debate", "Votación", "Decisión registrada"]},
    {"key": "change_impact_analysis", "category": "servicedesk", "icon": "📊",
     "name": "Análisis de Impacto",
     "description": "Evaluación de impacto en CMDB y servicios.",
     "steps": ["Cambio propuesto", "Identificar CIs afectados", "Calcular riesgo", "Documentar", "Adjuntar al RFC"]},
    {"key": "change_rollout", "category": "servicedesk", "icon": "🚀",
     "name": "Despliegue Escalonado",
     "description": "Rollout por fases con puntos de control.",
     "steps": ["Aprobado", "Piloto", "Wave 1", "Wave 2", "Producción", "Cierre"]},

    # ── Problem Management & Knowledge ────────────────────────────────────────
    {"key": "problem_management", "category": "servicedesk", "icon": "🧩",
     "name": "Gestión de Problemas",
     "description": "Análisis de causa raíz y errores conocidos.",
     "steps": ["Abierto", "Investigando", "Error conocido", "Resuelto", "Cerrado"]},
    {"key": "rca_wizard", "category": "servicedesk", "icon": "🔍",
     "name": "Asistente RCA",
     "description": "Investigación guiada de causa raíz (5 Whys).",
     "steps": ["Definir problema", "Recopilar datos", "5 Whys", "Causa raíz", "Plan acción"]},
    {"key": "kedb_lookup", "category": "servicedesk", "icon": "📚",
     "name": "Base de Errores Conocidos",
     "description": "Consulta y sugerencia de soluciones existentes.",
     "steps": ["Síntomas detectados", "Buscar KEDB", "Match score", "Aplicar workaround", "Feedback"]},
    {"key": "kb_authoring", "category": "servicedesk", "icon": "✍️",
     "name": "Creación de Artículos KB",
     "description": "Ciclo editorial de artículos de la base de conocimiento.",
     "steps": ["Borrador", "Revisión", "Publicado", "Mantenimiento", "Archivado"]},
    {"key": "smart_catalog", "category": "servicedesk", "icon": "🛍️",
     "name": "Catálogo Inteligente",
     "description": "Catálogo de servicios con sugerencias contextuales.",
     "steps": ["Cliente busca", "Recomendaciones IA", "Selección", "Solicitud", "Tracking"]},

    # ── Project Delivery & Tasks ──────────────────────────────────────────────
    {"key": "project_lifecycle", "category": "proyectos", "icon": "📋",
     "name": "Ciclo de Vida de Proyecto",
     "description": "Estados de un proyecto desde planificación a cierre.",
     "steps": ["Planificación", "Activo", "On hold", "Pausado", "Completado", "Cerrado"]},
    {"key": "task_workflow", "category": "proyectos", "icon": "✅",
     "name": "Workflow de Tareas",
     "description": "Estados estándar de una tarea ágil.",
     "steps": ["Backlog", "To-do", "En progreso", "Bloqueada", "Revisión", "Hecha"]},
    {"key": "project_phase", "category": "proyectos", "icon": "🏁",
     "name": "Fases de Proyecto",
     "description": "Hitos por fase y aprobación de paso de gate.",
     "steps": ["Inicio", "Diseño", "Construcción", "Pruebas", "Aceptación", "Cierre"]},
    {"key": "task_auto_assignment", "category": "proyectos", "icon": "🎯",
     "name": "Auto-Asignación de Tareas",
     "description": "ML asigna la tarea al miembro más adecuado del equipo.",
     "steps": ["Tarea creada", "Extraer skills requeridos", "Score por usuario", "Capacidad", "Asignar"]},
    {"key": "sprint_planning", "category": "proyectos", "icon": "🏃",
     "name": "Planificación de Sprint",
     "description": "Ciclo Scrum: planning, ejecución, review, retro.",
     "steps": ["Refinement", "Planning", "En curso", "Review", "Retrospectiva", "Cerrado"]},

    # ── Approvals & Finance ───────────────────────────────────────────────────
    {"key": "multi_level_approval", "category": "admin", "icon": "✔️",
     "name": "Aprobación Multinivel",
     "description": "Cadena de aprobaciones con escalado y delegación.",
     "steps": ["Solicitud", "Nivel 1", "Nivel 2", "Decisión final", "Notificación"]},
    {"key": "timesheet_approval", "category": "rrhh", "icon": "🕒",
     "name": "Aprobación de Timesheets",
     "description": "Envío de partes y aprobación por manager/PM.",
     "steps": ["Imputar horas", "Enviar", "Revisión PM", "Aprobado / rechazado", "Cierre semanal"]},
    {"key": "expense_approval", "category": "finanzas", "icon": "🧾",
     "name": "Aprobación de Gastos",
     "description": "Reembolso de gastos con justificantes.",
     "steps": ["Borrador", "Enviado", "Aprobado", "Rechazado", "Reembolsado"]},
    {"key": "document_approval", "category": "admin", "icon": "📄",
     "name": "Aprobación de Documentos",
     "description": "Firma y aprobación documental.",
     "steps": ["Pendiente", "En revisión", "Aprobado", "Publicado", "Archivado"]},
    {"key": "invoice_workflow", "category": "finanzas", "icon": "💶",
     "name": "Workflow de Facturas",
     "description": "Emisión, envío y conciliación de facturas.",
     "steps": ["Borrador", "Emitida", "Enviada", "Pagada", "Cerrada"]},
    {"key": "milestone_billing", "category": "finanzas", "icon": "🎯",
     "name": "Facturación por Hitos",
     "description": "Generación de factura al cumplir un hito SOW.",
     "steps": ["Hito definido", "Completado", "Aprobación cliente", "Generar factura", "Cobro"]},
    {"key": "revenue_recognition", "category": "finanzas", "icon": "📈",
     "name": "Reconocimiento de Ingresos (ASC606)",
     "description": "Reconocimiento de ingresos por obligación de desempeño.",
     "steps": ["Identificar contrato", "POBs", "Asignar precio", "Cumplir obligación", "Reconocer"]},

    # ── AI/ML & Analytics Workflows ───────────────────────────────────────────
    {"key": "churn_prediction", "category": "crm", "icon": "📉",
     "name": "Predicción de Churn",
     "description": "Detección temprana de clientes en riesgo.",
     "steps": ["Recoger features", "Inferencia ML", "Score", "Alerta CSM", "Plan retención"]},
    {"key": "anomaly_detection", "category": "admin", "icon": "🛡️",
     "name": "Detección de Anomalías de Login",
     "description": "Identificación de patrones inusuales de acceso.",
     "steps": ["Login event", "Baseline check", "Anomaly score", "Alertar SecOps", "Bloquear"]},
    {"key": "revenue_forecast", "category": "finanzas", "icon": "🔮",
     "name": "Forecasting de Ingresos",
     "description": "Proyección de ingresos basada en pipeline.",
     "steps": ["Snapshot pipeline", "Ponderar oportunidades", "Modelo predictivo", "Generar forecast", "Publicar"]},
    {"key": "incident_predictions", "category": "servicedesk", "icon": "📊",
     "name": "Predicciones de Incidencias",
     "description": "Predicción de MTTR y volumen de tickets.",
     "steps": ["Datos históricos", "Entrenar", "Inferencia", "Dashboard", "Reentrenar"]},
    {"key": "semantic_feedback", "category": "servicedesk", "icon": "🧠",
     "name": "Loop de Feedback Semántico",
     "description": "Aprendizaje continuo a partir del feedback del usuario.",
     "steps": ["Predicción IA", "Recibir feedback", "Etiquetar", "Reentrenar", "Desplegar v+1"]},
    {"key": "project_overrun_ml", "category": "proyectos", "icon": "⚠️",
     "name": "Predicción de Sobrecoste",
     "description": "ML para anticipar desviaciones de proyecto.",
     "steps": ["Snapshot proyecto", "Inferencia", "Riesgo", "Alerta PM", "Mitigación"]},

    # ── Workforce & HR ────────────────────────────────────────────────────────
    {"key": "performance_review", "category": "rrhh", "icon": "🌟",
     "name": "Ciclo de Performance Review",
     "description": "Evaluación semestral/anual de desempeño.",
     "steps": ["Apertura ciclo", "Auto-evaluación", "Manager review", "360°", "Calibración", "Cierre"]},
    {"key": "review_360", "category": "rrhh", "icon": "🔄",
     "name": "Review 360°",
     "description": "Recogida de feedback de pares, manager y reportes.",
     "steps": ["Solicitud", "Pendiente respuestas", "Enviado", "Consolidado", "Aprobado"]},
    {"key": "absence_request", "category": "rrhh", "icon": "🏖️",
     "name": "Solicitud de Ausencia",
     "description": "Vacaciones, baja, permisos.",
     "steps": ["Solicitud", "Validar saldo", "Aprobación manager", "Aprobado", "Calendario"]},
    {"key": "resource_forecast", "category": "rrhh", "icon": "📆",
     "name": "Forecast de Recursos",
     "description": "Proyección de capacidad vs. demanda.",
     "steps": ["Capacidad actual", "Demanda prevista", "Gap analysis", "Plan staffing", "Publicar"]},
    {"key": "training_plan", "category": "rrhh", "icon": "🎓",
     "name": "Plan de Formación",
     "description": "Asignación y seguimiento de cursos.",
     "steps": ["Detectar gap", "Asignar curso", "En progreso", "Completado", "Certificado"]},
    {"key": "onboarding", "category": "rrhh", "icon": "🚪",
     "name": "Onboarding de Empleado",
     "description": "Alta y formación inicial.",
     "steps": ["Pre-boarding", "Día 1", "Semana 1", "Mes 1", "Confirmación"]},

    # ── Governance, GDPR, Compliance ──────────────────────────────────────────
    {"key": "gdpr_request", "category": "admin", "icon": "🔐",
     "name": "Solicitud GDPR",
     "description": "Acceso, rectificación o supresión de datos personales.",
     "steps": ["Recibir solicitud", "Verificar identidad", "Procesando", "Completar", "Notificar"]},
    {"key": "governance_compliance", "category": "admin", "icon": "🏛️",
     "name": "Compliance de Gobernanza",
     "description": "Verificación periódica de controles de gobernanza.",
     "steps": ["Definir control", "Auditar", "Hallazgos", "Remediación", "Cierre"]},
    {"key": "esign_workflow", "category": "admin", "icon": "🖋️",
     "name": "Firma Electrónica",
     "description": "Solicitud, firma y archivo de documento.",
     "steps": ["Preparar", "Enviar a firmar", "Firmado", "Archivar", "Notificar"]},
    {"key": "grc_audit", "category": "admin", "icon": "📋",
     "name": "Auditoría GRC",
     "description": "Programa de auditorías GRC y seguimiento.",
     "steps": ["Plan", "Ejecución", "Hallazgos", "Plan de acción", "Cierre"]},
    {"key": "uat_acceptance", "category": "proyectos", "icon": "🧪",
     "name": "UAT — User Acceptance Testing",
     "description": "Aceptación de entregables por el cliente.",
     "steps": ["Plan UAT", "Ejecución", "Defectos", "Re-test", "Aceptado"]},

    # ── Configuration, Integration, Data ──────────────────────────────────────
    {"key": "workflow_blueprint", "category": "servicedesk", "icon": "🧱",
     "name": "Blueprint de Workflow",
     "description": "Diseño visual de workflows declarativos del Service Desk.",
     "steps": ["Borrador", "Compilar reglas", "Publicar", "En uso", "Archivado"]},
    {"key": "automation_workflow", "category": "admin", "icon": "⚙️",
     "name": "Workflow de Automatización",
     "description": "Triggers + condiciones + acciones programáticas.",
     "steps": ["Borrador", "Activo", "Disparado", "Pausado", "Archivado"]},
    {"key": "data_import", "category": "admin", "icon": "📥",
     "name": "Importación de Datos",
     "description": "Carga masiva CSV / Excel.",
     "steps": ["Subir archivo", "Validación", "Procesando", "Completado", "Reporte"]},
    {"key": "jira_sync", "category": "admin", "icon": "🔁",
     "name": "Sincronización con Jira",
     "description": "Sync continuo bidireccional con Jira.",
     "steps": ["Pull Jira", "Diff", "Push local", "Reconciliar", "Próximo ciclo"]},
    {"key": "etl_pipeline", "category": "admin", "icon": "🛠️",
     "name": "Pipeline ETL",
     "description": "Extracción, transformación y carga en el data warehouse.",
     "steps": ["Extract", "Transform", "Validate", "Load", "Quality check"]},
    {"key": "data_governance_review", "category": "admin", "icon": "📊",
     "name": "Revisión Data Governance",
     "description": "Aprobación de datasets y políticas de acceso.",
     "steps": ["Catalogar", "Clasificar", "Aprobación", "Publicado", "Auditoría"]},
]


# ── BPMN XML generator ────────────────────────────────────────────────────────
#: `targetNamespace` de los diagramas generados; el frontend usa el mismo
#: (`frontend/src/constants/bpmn.ts`). Barrido 2026-11.
BPMN_TARGET_NAMESPACE = "http://contecflow/bpmn"


def _filtro_de_claves_visibles(organization_id):
    """Las filas cuya clave ocupa el espacio de nombres de esa organizacion.

    Una organizacion ve sus procesos y los globales del catalogo
    (`organization_id` NULL, como en `list_processes`). Las dos cosas comparten
    espacio de claves: una fila propia con la clave de una global es la
    **personalizacion** de esa global, y no puede haber dos.
    """
    from app.models.bpmn_process import BPMNProcess

    if organization_id is None:
        return BPMNProcess.organization_id.is_(None)
    return ((BPMNProcess.organization_id == organization_id)
            | BPMNProcess.organization_id.is_(None))


def clave_unica(db, clave: str, organization_id) -> str:
    """Una clave de proceso libre en esa organizacion, con sufijo si hace falta.

    Auditoria 2026-08 (hallazgo 22): estaba en el endpoint. La unicidad de la
    clave es **por organizacion**, no global, asi que dos clientes pueden tener
    cada uno un proceso `aprobacion`.

    Segunda auditoria 2026-11: solo se miraban las filas de la organizacion,
    no las globales del catalogo que esa organizacion tambien ve. Crear un
    proceso propio con la clave de uno global daba dos procesos con la misma
    clave en el listado. Ahora la regla es la de `_filtro_de_claves_visibles`;
    personalizar un proceso del catalogo va por `seed_catalogue`.
    """
    from app.models.bpmn_process import BPMNProcess

    base = clave
    n = 1
    while (db.query(BPMNProcess.id)
             .filter(BPMNProcess.key == clave, _filtro_de_claves_visibles(organization_id))
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
                  targetNamespace="{BPMN_TARGET_NAMESPACE}">
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


def slugify(text: str) -> str:
    """Clave estable a partir de un nombre (estaba en el endpoint)."""
    s = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip().lower())
    return s.strip("_")[:120] or "process"


def validar_xml(db: Session, organization_id, xml: str) -> None:
    """Rechaza un diagrama que no es BPMN 2.0 o que pasa del tamaño maximo.

    Revision BPM 2026-11-16: `POST /versions` guardaba cualquier texto, sin
    tope. Un XML roto se guardaba como ultima version y el editor ya no podia
    abrir el proceso. Se parsea con `defusedxml` (sin DTD ni entidades). No se
    exige que sea *ejecutable*: un diagrama puede ser solo documentacion; eso
    se exige al publicar (`publish_version`) y al arrancar.
    """
    from defusedxml.ElementTree import fromstring
    from app.services.settings_service import get_runtime_int

    tope = get_runtime_int(db, "BPMN_MAX_XML_BYTES", organization_id)
    tamano = len((xml or "").encode("utf8"))
    if tope and tamano > tope:
        raise error(413, "bpm_diagrama_demasiado_grande", bytes=tamano, max=tope)
    try:
        # Revision 23-11-2026: tambien sin DTD (antes solo sin entidades): un
        # BPMN no necesita DOCTYPE y asi no hay ni XXE ni expansiones.
        raiz = fromstring(xml or "", forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except Exception as exc:   # ParseError y los rechazos de defusedxml
        raise error(422, "bpm_xml_no_valido", detail=f"El diagrama no es un XML válido: {exc}") from exc
    if raiz.tag != "{http://www.omg.org/spec/BPMN/20100524/MODEL}definitions":
        raise error(422, "bpm_no_es_bpmn")
    if raiz.find("{http://www.omg.org/spec/BPMN/20100524/MODEL}process") is None \
            and raiz.find("{http://www.omg.org/spec/BPMN/20100524/MODEL}collaboration") is None:
        raise error(422, "bpm_sin_procesos")


# ── Service helpers ───────────────────────────────────────────────────────────
def serialize_process(p: BPMNProcess, include_versions: bool = False) -> dict:
    out = {
        "id": p.id,
        "key": p.key,
        "name": p.name,
        "description": p.description,
        "category": p.category,
        "icon": p.icon,
        "owner": p.owner,
        "sla": p.sla,
        "variables_schema": _esquema(p),
        "source_kind": p.source_kind,
        "source_ref": p.source_ref,
        "latest_version": p.latest_version,
        "published_version": getattr(p, "_published_version", None),
        "status": p.status.value if p.status else "draft",
        "is_seeded": p.is_seeded,
        "is_active": p.is_active,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }
    if include_versions:
        out["versions"] = [serialize_version(v, include_xml=False) for v in p.versions]
        publicadas = [v.version for v in p.versions if v.is_published]
        out["published_version"] = max(publicadas) if publicadas else None
    return out


def anotar_versiones(db: Session, procesos: list[BPMNProcess], *, con_xml: bool = False) -> dict[str, str]:
    """Version publicada de cada proceso (y el XML de su ultima version).

    Revision BPM 2026-11-16: el frontend pedia `GET /bpmn-processes/{id}` uno
    por uno para tener el XML (N+1: 56 peticiones con el catalogo sembrado).
    Dos consultas para toda la lista. Devuelve `{process_id: xml}`.
    """
    ids = [p.id for p in procesos]
    if not ids:
        return {}
    publicadas = dict(
        db.query(BPMNProcessVersion.process_id, func.max(BPMNProcessVersion.version))
        .filter(BPMNProcessVersion.process_id.in_(ids), BPMNProcessVersion.is_published.is_(True))
        .group_by(BPMNProcessVersion.process_id).all())
    for p in procesos:
        p._published_version = publicadas.get(p.id)
    if not con_xml:
        return {}
    filas = (db.query(BPMNProcessVersion.process_id, BPMNProcessVersion.bpmn_xml)
             .join(BPMNProcess, BPMNProcess.id == BPMNProcessVersion.process_id)
             .filter(BPMNProcessVersion.process_id.in_(ids),
                     BPMNProcessVersion.version == BPMNProcess.latest_version)
             .all())
    return dict(filas)


def _esquema(p: BPMNProcess) -> list:
    from app.services.bpmn_engine import esquema
    return esquema(p)


def estado_de_version(v: BPMNProcessVersion) -> str:
    """Ciclo de una version: draft (borrador) -> published -> retired."""
    if v.is_published:
        return "published"
    return "retired" if v.retired_at else "draft"


def serialize_version(v: BPMNProcessVersion, include_xml: bool = True) -> dict:
    out = {
        "id": v.id,
        "process_id": v.process_id,
        "version": v.version,
        "is_published": v.is_published,
        "state": estado_de_version(v),
        "notes": v.notes,
        "published_at": v.published_at.isoformat() if v.published_at else None,
        "published_by_user_id": v.published_by_user_id,
        "retired_at": v.retired_at.isoformat() if v.retired_at else None,
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
        q = q.filter(_filtro_de_claves_visibles(organization_id))
    if category:
        q = q.filter(BPMNProcess.category == category)
    if not include_inactive:
        q = q.filter(BPMNProcess.is_active.is_(True))
    filas = q.order_by(BPMNProcess.category, BPMNProcess.name).all()
    if organization_id is None:
        return filas
    # Segunda auditoria 2026-11: la copia de la organizacion (p. ej. la que
    # crea `seed_catalogue`) personaliza la global de la misma clave; se
    # devuelve una sola, la propia.
    claves_propias = {p.key for p in filas if p.organization_id == organization_id}
    return [p for p in filas
            if p.organization_id is not None or p.key not in claves_propias]


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
    if get_process(db, process_id) is None:
        return None   # borrado o de otra organizacion: 404 como el detalle
    return (db.query(BPMNProcessVersion)
              .filter(BPMNProcessVersion.process_id == process_id,
                      BPMNProcessVersion.version == version)
              .first())


def create_process(db: Session, *, name: str, category: str, key: str,
                   description: Optional[str] = None, icon: Optional[str] = None,
                   owner: Optional[str] = None, sla: Optional[str] = None,
                   bpmn_xml: Optional[str] = None,
                   organization_id: Optional[str] = None,
                   created_by_user_id: Optional[str] = None,
                   is_seeded: bool = False, source_kind: str = "custom",
                   source_ref: Optional[str] = None) -> BPMNProcess:
    if bpmn_xml:
        validar_xml(db, organization_id, bpmn_xml)
    proc = BPMNProcess(
        organization_id=organization_id, key=key, name=name,
        description=description, category=category, icon=icon, owner=owner, sla=sla,
        is_seeded=is_seeded, source_kind=source_kind, source_ref=source_ref,
        created_by_user_id=created_by_user_id, latest_version=1,
        status=BPMNProcessStatus.draft,
    )
    db.add(proc)
    try:
        db.flush()
    except IntegrityError as exc:
        # Carrera perdida: `clave_unica` miro antes y otra alta ocupo la clave
        # entre medias; la rechazan los indices unicos (#33). Es un conflicto
        # (409), no un fallo del servidor.
        db.rollback()
        raise error(409, "bpm_clave_proceso_duplicada", detail=f"Ya existe un proceso con la clave '{key}'. Reintenta la operación.", clave=key) from exc
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
        raise error(404, "no_encontrado", detail="Process not found", que="proceso")
    validar_xml(db, proc.organization_id, bpmn_xml)
    # Auditoría 22-11-2026 (baja): la fila del proceso se bloquea antes de
    # numerar (dos guardados a la vez daban la misma versión).
    from app.db.session import is_postgres
    if is_postgres():
        db.refresh(proc, with_for_update=True)
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
        if k == "variables_schema":
            proc.variables_schema = validar_esquema(val)
            continue
        if k == "status":
            proc.status = BPMNProcessStatus(val)
        elif es_asignable(proc, k):
            setattr(proc, k, val)
    proc.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(proc)
    return proc


def validar_esquema(campos) -> Optional[str]:
    """Las variables declaradas de un proceso (lista), validadas; JSON para guardar."""
    import json
    from app.services.bpmn_engine import leer_formulario
    if not campos:
        return None
    try:
        lista = leer_formulario(json.dumps(campos))
    except (ValueError, TypeError) as exc:
        raise error(422, "bpm_esquema_no_valido", detail=f"Variables declaradas no válidas: {exc}") from exc
    nombres = [c["name"] for c in lista or []]
    if len(nombres) != len(set(nombres)):
        raise error(422, "bpm_esquema_no_valido", detail="Variables declaradas repetidas")
    return json.dumps(lista)


def publish_version(db: Session, process_id: str, version: int,
                    user_id: Optional[str] = None) -> Optional[BPMNProcessVersion]:
    """Publica una version: la que ejecutan las instancias nuevas.

    Revision BPM 2026-11-16:
    - solo se publica un diagrama **ejecutable** (422 con los problemas): la
      version publicada es la que arranca el motor, y publicar una que no
      arranca dejaba el proceso sin poder iniciarse;
    - queda **una** publicada: se despublican las demas (antes se acumulaban
      y la vigente solo se deducia por ser la mayor);
    - un proceso de otra organizacion o borrado da 404 como el resto.
    """
    from app.services import bpmn_engine as motor

    if get_process(db, process_id) is None:
        return None
    v = get_version(db, process_id, version)
    if not v:
        return None
    problemas = motor.leer(v.bpmn_xml).problemas
    if problemas:
        raise error(422, "bpm_diagrama_no_ejecutable", problemas="; ".join(map(str, problemas[:20])))
    (db.query(BPMNProcessVersion)
     .filter(BPMNProcessVersion.process_id == process_id, BPMNProcessVersion.id != v.id,
             BPMNProcessVersion.is_published.is_(True))
     .update({BPMNProcessVersion.is_published: False}, synchronize_session="fetch"))
    v.is_published = True
    v.published_at = datetime.now(timezone.utc)
    v.published_by_user_id = user_id
    v.retired_at = None
    v.retired_by_user_id = None
    proc = v.process
    proc.status = BPMNProcessStatus.published
    proc.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(v)
    return v


def retire_version(db: Session, process_id: str, version: int,
                   user_id: Optional[str] = None) -> Optional[BPMNProcessVersion]:
    """Retira una version: no arranca instancias nuevas; las que corren en ella siguen.

    Si era la publicada, el proceso se queda sin version que arrancar hasta
    que se publique otra (`version_ejecutable` da 409).
    """
    v = get_version(db, process_id, version)
    if not v:
        return None
    if v.retired_at and not v.is_published:
        raise error(409, "bpm_version_ya_retirada")
    v.is_published = False
    v.retired_at = datetime.now(timezone.utc)
    v.retired_by_user_id = user_id
    proc = v.process
    db.flush()
    if not any(x.is_published for x in proc.versions):
        proc.status = BPMNProcessStatus.draft
    proc.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(v)
    return v


def delete_process(db: Session, process_id: str) -> bool:
    proc = get_process(db, process_id)
    if not proc:
        return False
    proc.is_active = False
    proc.updated_at = datetime.now(timezone.utc)
    # M75 (auditoría 22-11-2026): borrar un proceso cancela sus instancias en
    # curso (como Camunda con «cascade»); antes seguían vivas y con tareas en
    # bandejas de un proceso que ya no existía.
    # Revision 23-11-2026: con el motor (cierra tambien aprobaciones abiertas
    # e instancias hijas) y tambien las suspendidas.
    from app.models.bpmn_process import BPMNInstance
    from app.services.bpmn_engine import _cancelar_instancia
    for inst in db.query(BPMNInstance).filter(BPMNInstance.process_id == proc.id,
                                              BPMNInstance.status.in_(("running", "suspended"))).all():
        _cancelar_instancia(db, inst)
    db.commit()
    return True


def duplicate_process(db: Session, process_id: str, *, new_name: str,
                      organization_id: Optional[str] = None,
                      created_by_user_id: Optional[str] = None) -> Optional[BPMNProcess]:
    """Copia un proceso (su ultima version) como proceso propio.

    Revision BPM 2026-11-16: la copia heredaba la organizacion del ORIGEN (una
    copia de un proceso global del catalogo quedaba global, visible para todas
    las organizaciones), la clave era `<clave>_copy_<timestamp>` sin pasar por
    `clave_unica`, y se perdian responsable y SLA.
    """
    src = get_process(db, process_id)
    if not src:
        return None
    src_xml = get_latest_version(db, process_id)
    copia = create_process(
        db, name=new_name, category=src.category,
        key=clave_unica(db, slugify(new_name), organization_id),
        description=src.description, icon=src.icon, owner=src.owner, sla=src.sla,
        bpmn_xml=src_xml.bpmn_xml if src_xml else None,
        organization_id=organization_id,
        created_by_user_id=created_by_user_id,
        is_seeded=False, source_kind="custom", source_ref=src.key,
    )
    if src.variables_schema:
        copia.variables_schema = src.variables_schema
        db.commit()
    return copia


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

