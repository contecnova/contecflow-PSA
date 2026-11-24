// Procesos del catálogo que son una cadena lineal de pasos (los que el backend
// siembra con `PROCESS_CATALOGUE` en app/services/bpmn_process_service.py y que
// no tienen diagrama propio en ./estructura.ts). Aquí solo va lo que NO depende
// del idioma; los textos (nombre, descripción y pasos) están en
// ./textosLineales/{es,en,zh}.ts y se cargan por idioma con import().
//
// El diagrama es el que genera el backend: el primer paso es el evento de inicio,
// el último el de fin y los de en medio, tareas.
import type { EstructuraLineal } from './tipos'

export const ESTRUCTURA_LINEAL: readonly EstructuraLineal[] = [
  { id: 'ticket_assignment_ml', category: 'servicedesk', pasos: 5 },
  { id: 'auto_resolution', category: 'servicedesk', pasos: 5 },
  { id: 'alert_correlation', category: 'servicedesk', pasos: 5 },
  { id: 'voice_agent_ivr', category: 'servicedesk', pasos: 5 },
  { id: 'multichannel_intake', category: 'servicedesk', pasos: 6 },
  { id: 'portal_conversation', category: 'servicedesk', pasos: 8 },
  { id: 'escalation_routing', category: 'servicedesk', pasos: 5 },
  { id: 'sla_monitoring', category: 'servicedesk', pasos: 5 },
  { id: 'oncall_scheduling', category: 'servicedesk', pasos: 5 },
  { id: 'cab_review', category: 'servicedesk', pasos: 5 },
  { id: 'change_impact_analysis', category: 'servicedesk', pasos: 5 },
  { id: 'change_rollout', category: 'servicedesk', pasos: 6 },
  { id: 'rca_wizard', category: 'servicedesk', pasos: 5 },
  { id: 'kedb_lookup', category: 'servicedesk', pasos: 5 },
  { id: 'kb_authoring', category: 'servicedesk', pasos: 5 },
  { id: 'smart_catalog', category: 'servicedesk', pasos: 5 },
  { id: 'project_lifecycle', category: 'proyectos', pasos: 6 },
  { id: 'task_workflow', category: 'proyectos', pasos: 6 },
  { id: 'project_phase', category: 'proyectos', pasos: 6 },
  { id: 'task_auto_assignment', category: 'proyectos', pasos: 5 },
  { id: 'multi_level_approval', category: 'admin', pasos: 5 },
  { id: 'invoice_workflow', category: 'finanzas', pasos: 5 },
  { id: 'churn_prediction', category: 'crm', pasos: 5 },
  { id: 'anomaly_detection', category: 'admin', pasos: 5 },
  { id: 'revenue_forecast', category: 'finanzas', pasos: 5 },
  { id: 'incident_predictions', category: 'servicedesk', pasos: 5 },
  { id: 'semantic_feedback', category: 'servicedesk', pasos: 5 },
  { id: 'project_overrun_ml', category: 'proyectos', pasos: 5 },
  { id: 'resource_forecast', category: 'rrhh', pasos: 5 },
  { id: 'training_plan', category: 'rrhh', pasos: 5 },
  { id: 'onboarding', category: 'rrhh', pasos: 5 },
  { id: 'governance_compliance', category: 'admin', pasos: 5 },
  { id: 'esign_workflow', category: 'admin', pasos: 5 },
  { id: 'uat_acceptance', category: 'proyectos', pasos: 5 },
  { id: 'workflow_blueprint', category: 'servicedesk', pasos: 5 },
  { id: 'automation_workflow', category: 'admin', pasos: 5 },
  { id: 'data_import', category: 'admin', pasos: 5 },
  { id: 'jira_sync', category: 'admin', pasos: 5 },
  { id: 'etl_pipeline', category: 'admin', pasos: 5 },
  { id: 'data_governance_review', category: 'admin', pasos: 5 },
]
