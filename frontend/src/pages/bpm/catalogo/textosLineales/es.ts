// Textos de los procesos lineales del catálogo BPM — es. Misma forma en los tres
// idiomas (ver tipos.ts): nombre, descripción y un texto por paso. El castellano
// es el de PROCESS_CATALOGUE (backend); un test comprueba que no se desvían.
import type { TextosLineales } from '../tipos'

const textos: TextosLineales = {
  "ticket_assignment_ml": {
    "name": "Asignación Inteligente (ML)",
    "description": "Routing automático del ticket al agente óptimo.",
    "steps": [
      "Ticket creado",
      "Extraer features",
      "Predecir agente",
      "Validar carga",
      "Asignar"
    ]
  },
  "auto_resolution": {
    "name": "Auto-Resolución",
    "description": "Sugerencia y aplicación automática de resolución vía IA.",
    "steps": [
      "Ticket entrante",
      "Buscar similares",
      "Confidence score",
      "Sugerir respuesta",
      "Auto-cerrar"
    ]
  },
  "alert_correlation": {
    "name": "Correlación de Alertas",
    "description": "Agrupación de alertas relacionadas en un único incidente.",
    "steps": [
      "Alerta entrante",
      "Buscar correlación",
      "Agrupar",
      "Crear incidente padre",
      "Notificar"
    ]
  },
  "voice_agent_ivr": {
    "name": "Agente de Voz / IVR",
    "description": "Flujo conversacional del agente de voz para soporte.",
    "steps": [
      "Llamada entrante",
      "Identificar usuario",
      "Intent detection",
      "Resolver / escalar",
      "Cierre llamada"
    ]
  },
  "multichannel_intake": {
    "name": "Intake Multi-Canal",
    "description": "Recepción de tickets desde email, chat, portal, móvil. Sin empresa destinataria (dirección o número de ninguna empresa, con varias empresas) el mensaje se ignora y no se abre ticket.",
    "steps": [
      "Mensaje entrante",
      "Identificar empresa destinataria (sin ella, se ignora)",
      "Normalizar canal",
      "Extraer datos",
      "Crear ticket",
      "Confirmación"
    ]
  },
  "escalation_routing": {
    "name": "Escalado",
    "description": "Reglas de escalado por SLA, prioridad y on-call.",
    "steps": [
      "Threshold check",
      "Identificar destino",
      "Notificar",
      "Re-asignar",
      "Auditar"
    ]
  },
  "sla_monitoring": {
    "name": "Monitorización de SLA",
    "description": "Vigilancia continua de plazos SLA del ticket.",
    "steps": [
      "Ticket abierto",
      "OK",
      "At risk",
      "Breach",
      "Reportar"
    ]
  },
  "oncall_scheduling": {
    "name": "Planificación On-Call",
    "description": "Rotación y asignación de guardias.",
    "steps": [
      "Definir rotación",
      "Asignar turno",
      "Notificar",
      "Activar guardia",
      "Cierre turno"
    ]
  },
  "cab_review": {
    "name": "Comité CAB",
    "description": "Reunión de revisión y aprobación del CAB.",
    "steps": [
      "Cambios pendientes",
      "Convocar CAB",
      "Debate",
      "Votación",
      "Decisión registrada"
    ]
  },
  "change_impact_analysis": {
    "name": "Análisis de Impacto",
    "description": "Evaluación de impacto en CMDB y servicios.",
    "steps": [
      "Cambio propuesto",
      "Identificar CIs afectados",
      "Calcular riesgo",
      "Documentar",
      "Adjuntar al RFC"
    ]
  },
  "change_rollout": {
    "name": "Despliegue Escalonado",
    "description": "Rollout por fases con puntos de control.",
    "steps": [
      "Aprobado",
      "Piloto",
      "Wave 1",
      "Wave 2",
      "Producción",
      "Cierre"
    ]
  },
  "rca_wizard": {
    "name": "Asistente RCA",
    "description": "Investigación guiada de causa raíz (5 Whys).",
    "steps": [
      "Definir problema",
      "Recopilar datos",
      "5 Whys",
      "Causa raíz",
      "Plan acción"
    ]
  },
  "kedb_lookup": {
    "name": "Base de Errores Conocidos",
    "description": "Consulta y sugerencia de soluciones existentes.",
    "steps": [
      "Síntomas detectados",
      "Buscar KEDB",
      "Match score",
      "Aplicar workaround",
      "Feedback"
    ]
  },
  "kb_authoring": {
    "name": "Creación de Artículos KB",
    "description": "Ciclo editorial de artículos de la base de conocimiento.",
    "steps": [
      "Borrador",
      "Revisión",
      "Publicado",
      "Mantenimiento",
      "Archivado"
    ]
  },
  "smart_catalog": {
    "name": "Catálogo Inteligente",
    "description": "Catálogo de servicios con sugerencias contextuales.",
    "steps": [
      "Cliente busca",
      "Recomendaciones IA",
      "Selección",
      "Solicitud",
      "Tracking"
    ]
  },
  "project_lifecycle": {
    "name": "Ciclo de Vida de Proyecto",
    "description": "Estados de un proyecto desde planificación a cierre.",
    "steps": [
      "Planificación",
      "Activo",
      "On hold",
      "Pausado",
      "Completado",
      "Cerrado"
    ]
  },
  "task_workflow": {
    "name": "Workflow de Tareas",
    "description": "Estados estándar de una tarea ágil.",
    "steps": [
      "Backlog",
      "To-do",
      "En progreso",
      "Bloqueada",
      "Revisión",
      "Hecha"
    ]
  },
  "project_phase": {
    "name": "Fases de Proyecto",
    "description": "Hitos por fase y aprobación de paso de gate.",
    "steps": [
      "Inicio",
      "Diseño",
      "Construcción",
      "Pruebas",
      "Aceptación",
      "Cierre"
    ]
  },
  "task_auto_assignment": {
    "name": "Auto-Asignación de Tareas",
    "description": "ML asigna la tarea al miembro más adecuado del equipo.",
    "steps": [
      "Tarea creada",
      "Extraer skills requeridos",
      "Score por usuario",
      "Capacidad",
      "Asignar"
    ]
  },
  "multi_level_approval": {
    "name": "Aprobación Multinivel",
    "description": "Cadena de aprobaciones con escalado y delegación.",
    "steps": [
      "Solicitud",
      "Nivel 1",
      "Nivel 2",
      "Decisión final",
      "Notificación"
    ]
  },
  "invoice_workflow": {
    "name": "Workflow de Facturas",
    "description": "Emisión, envío y conciliación de facturas.",
    "steps": [
      "Borrador",
      "Emitida",
      "Enviada",
      "Pagada",
      "Cerrada"
    ]
  },
  "churn_prediction": {
    "name": "Predicción de Churn",
    "description": "Detección temprana de clientes en riesgo.",
    "steps": [
      "Recoger features",
      "Inferencia ML",
      "Score",
      "Alerta CSM",
      "Plan retención"
    ]
  },
  "anomaly_detection": {
    "name": "Detección de Anomalías de Login",
    "description": "Identificación de patrones inusuales de acceso.",
    "steps": [
      "Login event",
      "Baseline check",
      "Anomaly score",
      "Alertar SecOps",
      "Bloquear"
    ]
  },
  "revenue_forecast": {
    "name": "Forecasting de Ingresos",
    "description": "Proyección de ingresos basada en pipeline.",
    "steps": [
      "Snapshot pipeline",
      "Ponderar oportunidades",
      "Modelo predictivo",
      "Generar forecast",
      "Publicar"
    ]
  },
  "incident_predictions": {
    "name": "Predicciones de Incidencias",
    "description": "Predicción de MTTR y volumen de tickets.",
    "steps": [
      "Datos históricos",
      "Entrenar",
      "Inferencia",
      "Dashboard",
      "Reentrenar"
    ]
  },
  "semantic_feedback": {
    "name": "Loop de Feedback Semántico",
    "description": "Aprendizaje continuo a partir del feedback del usuario.",
    "steps": [
      "Predicción IA",
      "Recibir feedback",
      "Etiquetar",
      "Reentrenar",
      "Desplegar v+1"
    ]
  },
  "project_overrun_ml": {
    "name": "Predicción de Sobrecoste",
    "description": "ML para anticipar desviaciones de proyecto.",
    "steps": [
      "Snapshot proyecto",
      "Inferencia",
      "Riesgo",
      "Alerta PM",
      "Mitigación"
    ]
  },
  "resource_forecast": {
    "name": "Forecast de Recursos",
    "description": "Proyección de capacidad vs. demanda.",
    "steps": [
      "Capacidad actual",
      "Demanda prevista",
      "Gap analysis",
      "Plan staffing",
      "Publicar"
    ]
  },
  "training_plan": {
    "name": "Plan de Formación",
    "description": "Asignación y seguimiento de cursos.",
    "steps": [
      "Detectar gap",
      "Asignar curso",
      "En progreso",
      "Completado",
      "Certificado"
    ]
  },
  "onboarding": {
    "name": "Onboarding de Empleado",
    "description": "Alta y formación inicial.",
    "steps": [
      "Pre-boarding",
      "Día 1",
      "Semana 1",
      "Mes 1",
      "Confirmación"
    ]
  },
  "governance_compliance": {
    "name": "Compliance de Gobernanza",
    "description": "Verificación periódica de controles de gobernanza.",
    "steps": [
      "Definir control",
      "Auditar",
      "Hallazgos",
      "Remediación",
      "Cierre"
    ]
  },
  "esign_workflow": {
    "name": "Firma Electrónica",
    "description": "Solicitud, firma y archivo de documento.",
    "steps": [
      "Preparar",
      "Enviar a firmar",
      "Firmado",
      "Archivar",
      "Notificar"
    ]
  },
  "uat_acceptance": {
    "name": "UAT — User Acceptance Testing",
    "description": "Aceptación de entregables por el cliente.",
    "steps": [
      "Plan UAT",
      "Ejecución",
      "Defectos",
      "Re-test",
      "Aceptado"
    ]
  },
  "workflow_blueprint": {
    "name": "Blueprint de Workflow",
    "description": "Diseño visual de workflows declarativos del Service Desk.",
    "steps": [
      "Borrador",
      "Compilar reglas",
      "Publicar",
      "En uso",
      "Archivado"
    ]
  },
  "automation_workflow": {
    "name": "Workflow de Automatización",
    "description": "Triggers + condiciones + acciones programáticas.",
    "steps": [
      "Borrador",
      "Activo",
      "Disparado",
      "Pausado",
      "Archivado"
    ]
  },
  "data_import": {
    "name": "Importación de Datos",
    "description": "Carga masiva CSV / Excel.",
    "steps": [
      "Subir archivo",
      "Validación",
      "Procesando",
      "Completado",
      "Reporte"
    ]
  },
  "jira_sync": {
    "name": "Sincronización con Jira",
    "description": "Sync continuo bidireccional con Jira.",
    "steps": [
      "Pull Jira",
      "Diff",
      "Push local",
      "Reconciliar",
      "Próximo ciclo"
    ]
  },
  "etl_pipeline": {
    "name": "Pipeline ETL",
    "description": "Extracción, transformación y carga en el data warehouse.",
    "steps": [
      "Extract",
      "Transform",
      "Validate",
      "Load",
      "Quality check"
    ]
  },
  "data_governance_review": {
    "name": "Revisión Data Governance",
    "description": "Aprobación de datasets y políticas de acceso.",
    "steps": [
      "Catalogar",
      "Clasificar",
      "Aprobación",
      "Publicado",
      "Auditoría"
    ]
  },
  "portal_conversation": {
    "name": "Conversación del portal (chat y llamadas)",
    "description": "Chat operador-cliente (conversaciones formales, chat de colaboración y chat en vivo de Soporte): adjuntos validados (contenido, AV/DLP, tipos y tamaño por empresa); llamada o videollamada solo iniciada por el operador, el cliente acepta o rechaza; sin grabación.",
    "steps": [
      "Mensaje del cliente",
      "Validar adjuntos (contenido, AV/DLP)",
      "Política GRC y aprobación",
      "Respuesta del operador",
      "Operador inicia llamada o videollamada",
      "Cliente acepta o rechaza",
      "Llamada (sin grabación) y cierre",
      "Conversación atendida"
    ]
  },
  "cert_program": {
    "name": "Programa de certificación",
    "description": "Alcance, declaración de aplicabilidad, implantación, pruebas independientes, auditorías y certificado (ISO 27001, TISAX, NIS2, SOX, J-SOX, IEC 62443).",
    "steps": [
      "Alcance y objetivos",
      "Análisis de carencias y riesgos",
      "Declaración de aplicabilidad",
      "Implantación de controles",
      "Pruebas de eficacia (otra persona)",
      "Auditoría interna",
      "Revisión por la dirección",
      "Auditoría de certificación",
      "Certificado vigente"
    ]
  },
  "cert_audit_capa": {
    "name": "Auditoría, hallazgo y acción correctiva",
    "description": "De la auditoría al cierre del hallazgo: acción correctiva como tarea, verificación de eficacia y cierre por otra persona.",
    "steps": [
      "Auditoría planificada",
      "Muestras y trabajo de campo",
      "Hallazgo registrado",
      "Acción correctiva (tarea)",
      "Acción hecha",
      "Verificación de eficacia (otra persona)",
      "Hallazgo corregido",
      "Cierre (no quien corrigió)"
    ]
  },
  "nis2_incident": {
    "name": "Incidente notificable NIS2",
    "description": "Incidente significativo desde el Service Desk con los relojes de 24 h, 72 h y 1 mes y el registro de comunicaciones a la autoridad.",
    "steps": [
      "Incidente detectado (ticket)",
      "Evaluación de significatividad",
      "Alerta temprana (24 h)",
      "Notificación (72 h)",
      "Informes intermedios",
      "Informe final (1 mes)",
      "Cierre y lecciones"
    ]
  }
}

export default textos
