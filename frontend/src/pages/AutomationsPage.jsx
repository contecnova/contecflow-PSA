/**
 * AutomationsPage — Visual no-code rule builder + Workflows multi-paso + RPA
 * SI [trigger] [condiciones] ENTONCES [acciones]
 */
import { useId, useState } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr } from '../utils/helpers'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api, { projectsApi } from '../services/api'
import { Button, Modal, Spinner, EmptyState } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import { Bot } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'



// ── Triggers — exhaustive catalog ────────────────────────────────────────────
const TRIGGERS = {
  // Tareas
  task_status_changed:      { label: 'Tarea cambia de estado',             icon: '🔄', category: 'Tareas' },
  task_created:             { label: 'Tarea creada',                        icon: '🆕', category: 'Tareas' },
  task_deleted:             { label: 'Tarea eliminada',                     icon: '🗑️', category: 'Tareas' },
  task_assigned:            { label: 'Tarea asignada a usuario',            icon: '👤', category: 'Tareas' },
  task_unassigned:          { label: 'Tarea desasignada',                   icon: '👤', category: 'Tareas' },
  task_completed:           { label: 'Tarea completada',                    icon: '✅', category: 'Tareas' },
  task_overdue:             { label: 'Tarea vencida sin completar',         icon: '⏰', category: 'Tareas' },
  task_deadline_approaching:{ label: 'Fecha límite de tarea próxima (N días)', icon: '📅', category: 'Tareas' },
  task_priority_changed:    { label: 'Prioridad de tarea modificada',       icon: '🔺', category: 'Tareas' },
  task_blocked:             { label: 'Tarea marcada como bloqueada',        icon: '🚫', category: 'Tareas' },
  task_comment_added:       { label: 'Comentario añadido a tarea',          icon: '💬', category: 'Tareas' },
  task_moved_to_sprint:     { label: 'Tarea movida a sprint',               icon: '⚡', category: 'Tareas' },
  // Proyectos
  project_status_changed:   { label: 'Proyecto cambia de estado',           icon: '📁', category: 'Proyectos' },
  project_created:          { label: 'Proyecto creado',                     icon: '🆕', category: 'Proyectos' },
  project_deadline_approaching: { label: 'Fecha fin de proyecto próxima',   icon: '📅', category: 'Proyectos' },
  budget_threshold:         { label: 'Presupuesto supera umbral (%)',        icon: '💰', category: 'Proyectos' },
  budget_overspent:         { label: 'Presupuesto agotado / sobrepasado',   icon: '🚨', category: 'Proyectos' },
  risk_score_high:          { label: 'Riesgo con puntuación alta',          icon: '⚠️', category: 'Proyectos' },
  risk_created:             { label: 'Riesgo nuevo registrado',             icon: '⚠️', category: 'Proyectos' },
  phase_completed:          { label: 'Fase de proyecto completada',         icon: '🏁', category: 'Proyectos' },
  deliverable_overdue:      { label: 'Entregable vencido',                  icon: '📦', category: 'Proyectos' },
  change_request_created:   { label: 'Solicitud de cambio creada',          icon: '⇄',  category: 'Proyectos' },
  member_added:             { label: 'Miembro añadido al proyecto',         icon: '➕', category: 'Proyectos' },
  member_removed:           { label: 'Miembro eliminado del proyecto',      icon: '➖', category: 'Proyectos' },
  // Sprints
  sprint_started:           { label: 'Sprint iniciado',                     icon: '⚡', category: 'Sprints' },
  sprint_ended:             { label: 'Sprint finalizado',                   icon: '🏁', category: 'Sprints' },
  sprint_goal_missed:       { label: 'Objetivo de sprint no alcanzado',     icon: '❌', category: 'Sprints' },
  sprint_capacity_exceeded: { label: 'Capacidad de sprint excedida',        icon: '📈', category: 'Sprints' },
  // Tiempo & Imputaciones
  timesheet_not_submitted:  { label: 'Timesheet no enviado al cierre semanal', icon: '📋', category: 'Tiempo' },
  timesheet_submitted:      { label: 'Timesheet enviado',                   icon: '✅', category: 'Tiempo' },
  timesheet_rejected:       { label: 'Timesheet rechazado',                 icon: '❌', category: 'Tiempo' },
  overtime_detected:        { label: 'Horas extras detectadas',             icon: '⏱', category: 'Tiempo' },
  imputation_lockout_warning:{ label: 'Período de bloqueo de imputaciones próximo', icon: '🔒', category: 'Tiempo' },
  date_reached:             { label: 'Fecha/hora programada (cron)',         icon: '📅', category: 'Tiempo' },
  end_of_week:              { label: 'Fin de semana laboral',                icon: '📆', category: 'Tiempo' },
  end_of_month:             { label: 'Fin de mes',                          icon: '📆', category: 'Tiempo' },
  // Equipo & RRHH
  absence_requested:        { label: 'Ausencia solicitada',                 icon: '🌴', category: 'Equipo' },
  absence_approved:         { label: 'Ausencia aprobada',                   icon: '✅', category: 'Equipo' },
  absence_rejected:         { label: 'Ausencia rechazada',                  icon: '❌', category: 'Equipo' },
  user_created:             { label: 'Usuario creado en el sistema',        icon: '👤', category: 'Equipo' },
  capacity_threshold:       { label: 'Carga de recurso supera umbral',      icon: '📈', category: 'Equipo' },
  performance_review_due:   { label: 'Evaluación de rendimiento pendiente', icon: '🌟', category: 'Equipo' },
  certification_expiring:   { label: 'Certificación próxima a caducar',    icon: '🎒', category: 'Equipo' },
  okr_deadline_approaching: { label: 'OKR con fecha límite próxima',        icon: '🏆', category: 'Equipo' },
  // Service Desk & ITSM
  ticket_created:           { label: 'Ticket creado en Service Desk',       icon: '🎫', category: 'Service Desk' },
  ticket_sla_at_risk:       { label: 'Ticket con SLA en riesgo',            icon: '🚨', category: 'Service Desk' },
  ticket_sla_breached:      { label: 'SLA de ticket incumplido',            icon: '🔴', category: 'Service Desk' },
  ticket_escalated:         { label: 'Ticket escalado de nivel',            icon: '↑',  category: 'Service Desk' },
  ticket_resolved:          { label: 'Ticket resuelto',                     icon: '✅', category: 'Service Desk' },
  ticket_reopened:          { label: 'Ticket reabierto por el cliente',     icon: '🔄', category: 'Service Desk' },
  ticket_no_response:       { label: 'Ticket sin respuesta (N días)',        icon: '⏰', category: 'Service Desk' },
  cmdb_asset_expiring:      { label: 'Activo CMDB próximo a vencer',         icon: '🖥️', category: 'Service Desk' },
  // Finanzas
  expense_submitted:        { label: 'Gasto enviado para aprobación',       icon: '💸', category: 'Finanzas' },
  expense_approved:         { label: 'Gasto aprobado',                      icon: '✅', category: 'Finanzas' },
  invoice_created:          { label: 'Factura creada',                      icon: '🧾', category: 'Finanzas' },
  invoice_overdue:          { label: 'Factura vencida sin pagar',           icon: '💳', category: 'Finanzas' },
  contract_expiring:        { label: 'Contrato próximo a vencer',           icon: '📝', category: 'Finanzas' },
  milestone_reached:        { label: 'Hito de facturación alcanzado',       icon: '◎',  category: 'Finanzas' },
  nps_score_low:            { label: 'NPS / salud cliente bajo umbral',     icon: '⭐', category: 'Finanzas' },
  // Integraciones & Webhooks
  webhook_received:         { label: 'Webhook recibido (sistema externo)',  icon: '🔗', category: 'Integraciones' },
  git_pr_merged:            { label: 'Pull Request mergeado en Git',        icon: '⎇',  category: 'Integraciones' },
  git_pipeline_failed:      { label: 'Pipeline CI/CD fallido',              icon: '❌', category: 'Integraciones' },
  email_received:           { label: 'Email recibido con etiqueta',         icon: '📧', category: 'Integraciones' },
  form_submitted:           { label: 'Formulario externo enviado',          icon: '📝', category: 'Integraciones' },
  api_event:                { label: 'Evento arbitrario vía API externa',   icon: '🔌', category: 'Integraciones' },
}


const ACTIONS = {
  // Notificaciones
  create_alert:           { label: 'Crear alerta en el sistema',          icon: '🔔', category: 'Notificaciones' },
  notify_role:            { label: 'Notificar a un rol',                  icon: '👥', category: 'Notificaciones' },
  notify_user:            { label: 'Notificar a usuario específico',      icon: '👤', category: 'Notificaciones' },
  send_email:             { label: 'Enviar email',                        icon: '📧', category: 'Notificaciones' },
  // Integraciones
  send_webhook:           { label: 'Llamar webhook externo (HTTP POST)',  icon: '🔗', category: 'Integraciones' },
  send_teams_message:     { label: 'Enviar mensaje a MS Teams',           icon: 'Ⓜ',  category: 'Integraciones' },
  send_slack_message:     { label: 'Enviar mensaje a Slack',              icon: '💬', category: 'Integraciones' },
  create_jira_issue:      { label: 'Crear issue en Jira',                 icon: '🔵', category: 'Integraciones' },
  // Tareas
  change_task_status:     { label: 'Cambiar estado de la tarea',          icon: '🔄', category: 'Tareas' },
  change_task_priority:   { label: 'Cambiar prioridad de la tarea',       icon: '🔺', category: 'Tareas' },
  assign_task:            { label: 'Asignar tarea a usuario/rol',         icon: '👤', category: 'Tareas' },
  create_task:            { label: 'Crear nueva tarea',                   icon: '🆕', category: 'Tareas' },
  // Proyectos / Tickets / Finanzas
  change_project_status:  { label: 'Cambiar estado del proyecto',         icon: '📁', category: 'Proyectos' },
  escalate_ticket:        { label: 'Escalar ticket al siguiente nivel',   icon: '↑',  category: 'Service Desk' },
  change_ticket_status:   { label: 'Cambiar estado del ticket',           icon: '🎫', category: 'Service Desk' },
  assign_ticket:          { label: 'Asignar ticket a agente',             icon: '👤', category: 'Service Desk' },
  approve_expense:        { label: 'Aprobar / rechazar gasto',            icon: '💸', category: 'Finanzas' },
  // RPA
  rpa_power_automate:     { label: 'Disparar Power Automate Flow',        icon: '🔵', category: 'RPA' },
  rpa_uipath:             { label: 'Disparar job en UiPath Orchestrator', icon: '🤖', category: 'RPA' },
  rpa_zapier:             { label: 'Disparar Zap en Zapier',              icon: '⚡', category: 'RPA' },
  rpa_make:               { label: 'Disparar escenario en Make',          icon: '🔧', category: 'RPA' },
  rpa_n8n:                { label: 'Disparar workflow en n8n',            icon: '🔀', category: 'RPA' },
  rpa_custom_http:        { label: 'Petición HTTP personalizada',         icon: '🌐', category: 'RPA' },
}

const OPERATORS = [
  { value: 'equals',       label: 'es igual a' },
  { value: 'not_equals',   label: 'no es igual a' },
  { value: 'greater_than', label: 'mayor que' },
  { value: 'less_than',    label: 'menor que' },
  { value: 'contains',     label: 'contiene' },
]

const TRIGGER_FIELDS = {
  task_status_changed:    ['status', 'priority', 'project_id'],
  budget_threshold:       ['budget_pct', 'project_id'],
  risk_score_high:        ['risk_score', 'project_id'],
  ticket_created:         ['priority', 'ticket_type', 'support_level'],
  project_status_changed: ['status'],
}

const ACTION_PARAMS = {
  create_alert:         [{ key: 'message', label: 'Mensaje', type: 'text' }, { key: 'severity', label: 'Severidad', type: 'select', options: ['info','warning','critical'] }],
  notify_role:          [{ key: 'role', label: 'Rol', type: 'select', options: ['admin','pm','employee','hr','team_lead'] }, { key: 'message', label: 'Mensaje', type: 'text' }, { key: 'severity', label: 'Severidad', type: 'select', options: ['info','warning','critical'] }],
  notify_user:          [{ key: 'message', label: 'Mensaje', type: 'text' }],
  send_email:           [{ key: 'to_role', label: 'Enviar a (rol)', type: 'select', options: ['admin','pm','employee','hr'] }, { key: 'subject', label: 'Asunto', type: 'text' }, { key: 'body', label: 'Cuerpo del email', type: 'text' }],
  send_webhook:         [{ key: 'url', label: 'URL del webhook', type: 'text' }, { key: 'payload_template', label: 'Payload JSON (template)', type: 'text' }],
  send_teams_message:   [{ key: 'teams_webhook_url', label: 'Webhook URL de Teams', type: 'text' }, { key: 'message', label: 'Mensaje', type: 'text' }],
  send_slack_message:   [{ key: 'slack_webhook_url', label: 'Webhook URL de Slack', type: 'text' }, { key: 'channel', label: 'Canal (#general)', type: 'text' }, { key: 'message', label: 'Mensaje', type: 'text' }],
  create_jira_issue:    [{ key: 'jira_project_key', label: 'Key proyecto Jira', type: 'text' }, { key: 'issue_type', label: 'Tipo issue', type: 'select', options: ['Bug','Task','Story','Epic'] }, { key: 'summary', label: 'Resumen / título', type: 'text' }],
  change_task_status:   [{ key: 'status', label: 'Nuevo estado', type: 'select', options: ['todo','in_progress','in_review','done','blocked'] }],
  change_task_priority: [{ key: 'priority', label: 'Nueva prioridad', type: 'select', options: ['critical','high','medium','low'] }],
  assign_task:          [{ key: 'assign_to_role', label: 'Asignar al rol', type: 'select', options: ['pm','team_lead','employee'] }],
  create_task:          [{ key: 'task_title', label: 'Título de la tarea', type: 'text' }, { key: 'priority', label: 'Prioridad', type: 'select', options: ['critical','high','medium','low'] }, { key: 'assign_to_role', label: 'Asignar a', type: 'select', options: ['pm','team_lead','employee'] }],
  change_project_status:[{ key: 'status', label: 'Nuevo estado', type: 'select', options: ['active','on_hold','completed','cancelled'] }],
  escalate_ticket:      [{ key: 'to_level', label: 'Escalar a', type: 'select', options: ['l2','l3'] }],
  change_ticket_status: [{ key: 'status', label: 'Nuevo estado', type: 'select', options: ['assigned','in_progress','resolved','closed'] }],
  assign_ticket:        [{ key: 'to_role', label: 'Asignar al rol', type: 'select', options: ['l1','l2','l3'] }],
  approve_expense:      [{ key: 'decision', label: 'Decisión', type: 'select', options: ['approved','rejected'] }, { key: 'comment', label: 'Comentario (opcional)', type: 'text' }],
  rpa_power_automate:   [{ key: 'flow_url', label: 'URL del Flow (trigger HTTP)', type: 'text' }, { key: 'payload', label: 'Payload adicional (JSON)', type: 'text' }],
  rpa_uipath:           [{ key: 'orchestrator_url', label: 'URL Orchestrator', type: 'text' }, { key: 'process_key', label: 'Clave del proceso', type: 'text' }, { key: 'robot_name', label: 'Robot (vacío = cualquiera)', type: 'text' }],
  rpa_zapier:           [{ key: 'zap_webhook_url', label: 'Webhook URL del Zap', type: 'text' }, { key: 'payload', label: 'Datos adicionales (JSON)', type: 'text' }],
  rpa_make:             [{ key: 'make_webhook_url', label: 'Webhook URL de Make', type: 'text' }, { key: 'payload', label: 'Datos adicionales (JSON)', type: 'text' }],
  rpa_n8n:              [{ key: 'n8n_webhook_url', label: 'Webhook URL de n8n', type: 'text' }, { key: 'payload', label: 'Datos adicionales (JSON)', type: 'text' }],
  rpa_custom_http:      [{ key: 'url', label: 'URL endpoint', type: 'text' }, { key: 'method', label: 'Método HTTP', type: 'select', options: ['POST','GET','PUT','PATCH'] }, { key: 'headers', label: 'Headers (JSON)', type: 'text' }, { key: 'body', label: 'Body (JSON)', type: 'text' }],
}

// Derived category lists (referenced by both RuleModal and WorkflowModal)
const TRIGGER_CATEGORIES = [...new Set(Object.values(TRIGGERS).map(t => t.category))]
const ACTION_CATEGORIES  = [...new Set(Object.values(ACTIONS).map(a => a.category))]

const card = { background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 12 }
const fs = { width: '100%', background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 8, padding: '9px 12px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
const ls = { fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }

// ── Rule card ─────────────────────────────────────────────────────────────────
function RuleCard({ rule, onEdit, onDelete, onTest, onToggle }) {
  const trigger = TRIGGERS[rule.trigger_type] || { label: rule.trigger_type, icon: '⚙️' }
  const actions = Array.isArray(rule.actions) ? rule.actions : []

  return (
    <div style={{ background: 'var(--surface-2)', border: `1px solid ${rule.is_active ? 'var(--surface-4)' : 'var(--danger-border)'}`, borderRadius: 12, padding: '16px 20px', opacity: rule.is_active ? 1 : 0.6 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 4 }}>
            <span style={{ fontSize: 16 }}>{trigger.icon}</span>
            <span style={{ fontSize: 14, fontWeight: 700 }}>{rule.name}</span>
            {rule.is_global && <span style={{ fontSize: 10, fontWeight: 700, padding: '1px 6px', borderRadius: 4, background: 'var(--purple-bg)', color: 'var(--purple)' }}>GLOBAL</span>}
            {rule.project_name && <span style={{ fontSize: 11, color: 'var(--text-2)' }}>· {rule.project_name}</span>}
          </div>
          {rule.description && <div style={{ fontSize: 12, color: 'var(--text-2)', marginBottom: 8 }}>{rule.description}</div>}
        </div>
        <div style={{ display: 'flex', gap: 6, flexShrink: 0, marginLeft: 12 }}>
          <button aria-pressed={rule.is_active} aria-label={`${rule.is_active ? 'Pausar' : 'Activar'} regla ${rule.name}`} onClick={() => onToggle(rule)}
            style={{ background: rule.is_active ? 'var(--warning-bg)' : 'var(--success-bg)', border: `1px solid ${rule.is_active ? 'rgba(245,158,11,0.25)' : 'rgba(52,211,153,0.25)'}`, borderRadius: 6, padding: '4px 10px', color: rule.is_active ? 'var(--warning)' : 'var(--success)', cursor: 'pointer', fontSize: 11, fontFamily: 'inherit' }}>
            {rule.is_active ? '⏸ Pausar' : '▶ Activar'}
          </button>
          <button aria-label={`Probar regla ${rule.name}`} onClick={() => onTest(rule)}
            style={{ background: 'var(--accent-muted)', border: '1px solid #00d4ff40', borderRadius: 6, padding: '4px 10px', color: 'var(--accent)', cursor: 'pointer', fontSize: 11, fontFamily: 'inherit' }}>
            ▷ Probar
          </button>
          <button aria-label={`Editar regla ${rule.name}`} onClick={() => onEdit(rule)}
            style={{ background: 'none', border: '1px solid #1e2d45', borderRadius: 6, padding: '4px 10px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 11 }}>✏</button>
          <button aria-label={`Eliminar regla ${rule.name}`} onClick={() => { openConfirmGlobal({ message: '¿Eliminar esta regla?', onConfirm: () => onDelete(rule.id), danger: true }) }}
            style={{ background: 'none', border: '1px solid #ff475730', borderRadius: 6, padding: '4px 10px', color: 'var(--danger)', cursor: 'pointer', fontSize: 11 }}>🗑</button>
        </div>
      </div>

      {/* Visual rule display */}
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
        <div style={{ background: 'var(--purple-bg)', border: '1px solid #7c3aed40', borderRadius: 8, padding: '6px 12px', fontSize: 12 }}>
          <span style={{ color: 'var(--purple)', fontWeight: 700 }}>SI </span>
          <span style={{ color: 'var(--text-1)' }}>{trigger.icon} {trigger.label}</span>
          {rule.trigger_conditions && (
            <span style={{ color: 'var(--text-2)' }}>
              {' '}· {rule.trigger_conditions.field} {OPERATORS.find(o => o.value === rule.trigger_conditions.operator)?.label} <strong style={{ color: 'var(--text-1)' }}>{rule.trigger_conditions.value}</strong>
            </span>
          )}
        </div>
        <span style={{ fontSize: 18, color: 'var(--text-3)' }}>→</span>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {actions.map((a, i) => {
            const aCfg = ACTIONS[a.type] || { label: a.type, icon: '⚙️' }
            return (
              <div key={i} style={{ background: 'var(--accent-muted)', border: '1px solid #00d4ff30', borderRadius: 8, padding: '6px 12px', fontSize: 12 }}>
                <span style={{ color: 'var(--accent)', fontWeight: 700 }}>ENTONCES </span>
                <span style={{ color: 'var(--text-1)' }}>{aCfg.icon} {aCfg.label}</span>
                {a.params?.message && <span style={{ color: 'var(--text-2)' }}> · &quot;{a.params.message.slice(0, 40)}&quot;</span>}
              </div>
            )
          })}
        </div>
      </div>

      <div style={{ display: 'flex', gap: 16, marginTop: 10, fontSize: 11, color: 'var(--text-3)' }}>
        <span>⚡ {rule.run_count || 0} ejecuciones</span>
        {rule.last_run_at && <span>Última: {rule.last_run_at}</span>}
        {rule.last_error && <span style={{ color: 'var(--danger)' }}>⚠ {rule.last_error.slice(0, 60)}</span>}
      </div>
    </div>
  )
}

// ── Rule editor modal ─────────────────────────────────────────────────────────
function RuleModal({ rule, onClose }) {
  const idPrefix = useId()
  const qc = useQueryClient()
  const toast = useToast()
  const isEdit = !!rule
  const [form, setForm] = useState({
    name: rule?.name || '',
    description: rule?.description || '',
    project_id: rule?.project_id || '',
    is_global: rule?.is_global ?? false,
    trigger_type: rule?.trigger_type || 'task_status_changed',
    trigger_conditions: rule?.trigger_conditions || null,
    actions: rule?.actions || [{ type: 'create_alert', params: { message: '', severity: 'warning' } }],
  })
  const [hasCondition, setHasCondition] = useState(!!rule?.trigger_conditions)
  const [condition, setCondition] = useState(rule?.trigger_conditions || { field: '', operator: 'equals', value: '' })

  const { data: projRaw = [] } = useQuery({ queryKey: ['projects'], queryFn: () => projectsApi.list().then(r => r.data) })
  const projects = Array.isArray(projRaw) ? projRaw : []

  const { mutate, isPending } = useMutation({
    mutationFn: d => isEdit ? api.patch(`/automations/${rule.id}`, d) : api.post('/automations', d),
    onSuccess: () => { qc.invalidateQueries(['automations']); onClose() },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const addAction = () => setForm(f => ({ ...f, actions: [...f.actions, { type: 'create_alert', params: { message: '', severity: 'info' } }] }))
  const removeAction = i => setForm(f => ({ ...f, actions: f.actions.filter((_, idx) => idx !== i) }))
  const updateAction = (i, field, value) => setForm(f => {
    const actions = [...f.actions]
    if (field === 'type') actions[i] = { type: value, params: {} }
    else {
      actions[i] = { ...actions[i], params: { ...actions[i].params, [field]: value } }
    }
    return { ...f, actions }
  })

  const fields = TRIGGER_FIELDS[form.trigger_type] || []

  const handleSave = () => {
    const payload = {
      ...form,
      trigger_conditions: hasCondition && condition.field ? condition : null,
    }
    mutate(payload)
  }

  return (
    <Modal open title={isEdit ? 'Editar regla' : 'Nueva regla de automatización'} onClose={onClose} width={680}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {/* Basic info */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
          <div style={{ gridColumn: '1/-1' }}>
            <label htmlFor={`${idPrefix}-name`} style={ls}>Nombre de la regla *</label>
            <input id={`${idPrefix}-name`} value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} style={fs} placeholder="Ej: Alerta cuando presupuesto supera 85%" />
          </div>
          <div>
            <label htmlFor={`${idPrefix}-description`} style={ls}>Descripción</label>
            <input id={`${idPrefix}-description`} value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} style={fs} />
          </div>
          <div>
            <label htmlFor={`${idPrefix}-project`} style={ls}>Proyecto (vacío = global)</label>
            <select id={`${idPrefix}-project`} value={form.project_id} onChange={e => setForm(f => ({ ...f, project_id: e.target.value, is_global: !e.target.value }))} style={fs}>
              <option value="">Global — todos los proyectos</option>
              {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
            </select>
          </div>
        </div>

        {/* TRIGGER */}
        <div style={{ background: 'var(--purple-bg)', border: '1px solid #7c3aed30', borderRadius: 10, padding: '14px 16px' }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--purple)', marginBottom: 12, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            🔵 SI — Cuando ocurre este evento
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 10 }}>
            <div>
              <label htmlFor={`${idPrefix}-trigger`} style={ls}>Disparador</label>
              <select id={`${idPrefix}-trigger`} value={form.trigger_type} onChange={e => setForm(f => ({ ...f, trigger_type: e.target.value }))} style={fs}>
                {TRIGGER_CATEGORIES.map(cat => (
                  <optgroup key={cat} label={cat}>
                    {Object.entries(TRIGGERS).filter(([, v]) => v.category === cat).map(([k, v]) => (
                      <option key={k} value={k}>{v.icon} {v.label}</option>
                    ))}
                  </optgroup>
                ))}
              </select>
            </div>

            {/* Condition */}
            <div>
              <label htmlFor={`${idPrefix}-has-condition`} style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13, color: 'var(--text-2)' }}>
                <input id={`${idPrefix}-has-condition`} type="checkbox" checked={hasCondition} onChange={e => setHasCondition(e.target.checked)} />
                Añadir condición (opcional)
              </label>
            </div>
            {hasCondition && (
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10, padding: '10px 14px', background: 'var(--surface-3)', borderRadius: 8 }}>
                <div>
                  <label htmlFor={`${idPrefix}-condition-field`} style={ls}>Campo</label>
                  <select id={`${idPrefix}-condition-field`} value={condition.field} onChange={e => setCondition(c => ({ ...c, field: e.target.value }))} style={fs}>
                    <option value="">Seleccionar...</option>
                    {fields.map(f => <option key={f} value={f}>{f}</option>)}
                    <option value="budget_pct">budget_pct (%)</option>
                    <option value="risk_score">risk_score</option>
                    <option value="priority">priority</option>
                    <option value="status">status</option>
                  </select>
                </div>
                <div>
                  <label htmlFor={`${idPrefix}-condition-operator`} style={ls}>Operador</label>
                  <select id={`${idPrefix}-condition-operator`} value={condition.operator} onChange={e => setCondition(c => ({ ...c, operator: e.target.value }))} style={fs}>
                    {OPERATORS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                </div>
                <div>
                  <label htmlFor={`${idPrefix}-condition-value`} style={ls}>Valor</label>
                  <input id={`${idPrefix}-condition-value`} value={condition.value} onChange={e => setCondition(c => ({ ...c, value: e.target.value }))} style={fs} placeholder="Ej: 85, done, p1_critical..." />
                </div>
              </div>
            )}
          </div>
        </div>

        {/* ACTIONS */}
        <div style={{ background: 'var(--accent-muted)', border: '1px solid #00d4ff30', borderRadius: 10, padding: '14px 16px' }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--accent)', marginBottom: 12, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            🟦 ENTONCES — Ejecutar estas acciones
          </div>
          {form.actions.map((action, i) => {
            const paramDefs = ACTION_PARAMS[action.type] || []
            return (
              <div key={i} style={{ background: 'var(--surface-3)', borderRadius: 8, padding: '12px 14px', marginBottom: 10, position: 'relative' }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: 10, marginBottom: paramDefs.length > 0 ? 10 : 0 }}>
                  <div>
                    <label style={ls}>Acción {i + 1}</label>
                    <select value={action.type} onChange={e => updateAction(i, 'type', e.target.value)} style={fs}>
                      {ACTION_CATEGORIES.map(cat => (
                        <optgroup key={cat} label={cat}>
                          {Object.entries(ACTIONS).filter(([,v]) => v.category === cat).map(([k, v]) => (
                            <option key={k} value={k}>{v.icon} {v.label}</option>
                          ))}
                        </optgroup>
                      ))}
                    </select>
                  </div>
                  {form.actions.length > 1 && (
                    <button aria-label={`Eliminar acción ${i + 1}`} onClick={() => removeAction(i)}
                      style={{ background: 'none', border: 'none', color: 'var(--text-3)', cursor: 'pointer', fontSize: 16, alignSelf: 'flex-end', paddingBottom: 8 }}>×</button>
                  )}
                </div>
                {paramDefs.length > 0 && (
                  <div style={{ display: 'grid', gridTemplateColumns: paramDefs.length > 1 ? `repeat(${Math.min(paramDefs.length, 3)}, 1fr)` : '1fr', gap: 10 }}>
                    {paramDefs.map(param => (
                      <div key={param.key}>
                        <label style={ls}>{param.label}</label>
                        {param.type === 'select' ? (
                          <select value={action.params?.[param.key] || ''} onChange={e => updateAction(i, param.key, e.target.value)} style={fs}>
                            <option value="">Seleccionar...</option>
                            {param.options.map(o => <option key={o} value={o}>{o}</option>)}
                          </select>
                        ) : (
                          <input value={action.params?.[param.key] || ''} onChange={e => updateAction(i, param.key, e.target.value)} style={fs} placeholder={param.label} />
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )
          })}
          <button aria-label="Añadir una nueva acción" onClick={addAction}
            style={{ background: 'transparent', border: '1px dashed #00d4ff40', borderRadius: 8, padding: '7px 16px', color: 'var(--accent)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit', width: '100%' }}>
            + Añadir acción
          </button>
        </div>

        {/* Save */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={handleSave} loading={isPending} disabled={isPending || !form.name || form.actions.length === 0}>
            {isPending ? 'Guardando...' : isEdit ? 'Guardar cambios' : 'Crear regla'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ── Executions modal ──────────────────────────────────────────────────────────
function ExecutionsModal({ rule, onClose }) {
  const { data = [], isLoading } = useQuery({
    queryKey: ['auto-executions', rule.id],
    queryFn: () => api.get(`/automations/${rule.id}/executions`).then(r => r.data),
  })
  return (
    <Modal open title={`Historial — ${rule.name}`} onClose={onClose} width={600}>
      {isLoading ? <Spinner /> : data.length === 0 ? (
        <EmptyState icon="📭" title="Sin ejecuciones" description="Esta regla aún no se ha ejecutado" />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxHeight: 400, overflowY: 'auto' }}>
          {data.map(e => (
            <div key={e.id} style={{ padding: '10px 14px', background: 'var(--surface-2)', border: `1px solid ${e.success ? 'var(--success-border)' : 'var(--danger-border)'}`, borderRadius: 8 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                <span style={{ fontSize: 12, fontWeight: 700, color: e.success ? 'var(--success)' : 'var(--danger)' }}>{e.success ? '✓ Éxito' : '✗ Error'}</span>
                <span style={{ fontSize: 11, color: 'var(--text-3)' }}>{e.executed_at}</span>
              </div>
              {e.trigger_context && <div style={{ fontSize: 11, color: 'var(--text-3)' }}>Contexto: {JSON.stringify(e.trigger_context).slice(0, 80)}</div>}
              {e.error && <div style={{ fontSize: 11, color: 'var(--danger)', marginTop: 4 }}>{e.error}</div>}
            </div>
          ))}
        </div>
      )}
    </Modal>
  )
}

// ── WorkflowModal (create + edit) ─────────────────────────────────────────────
const STEP_ICONS = { action:'⚡', condition:'🔀', wait:'⏱', webhook:'🔗', notify:'🔔', rpa:'🤖' }

function StepConfig({ step, idx, onChange, onRemove }) {
  const { step_type, name = '', config = {} } = step
  const paramDefs  = ACTION_PARAMS[config.action_type] || []

  return (
    <div style={{ background: 'var(--surface-3)', borderRadius: 8, padding: '12px 14px', marginBottom: 8 }}>
      <div style={{ display: 'grid', gridTemplateColumns: '100px 1fr auto', gap: 10, alignItems: 'center', marginBottom: 10 }}>
        <select value={step_type} onChange={e => onChange(idx, { ...step, step_type: e.target.value, config: {} })} style={{ ...fs, padding: '6px 8px', fontSize: 12 }}>
          {Object.keys(STEP_ICONS).map(t => <option key={t} value={t}>{STEP_ICONS[t]} {t}</option>)}
        </select>
        <input value={name} onChange={e => onChange(idx, { ...step, name: e.target.value })} style={{ ...fs, padding: '6px 10px', fontSize: 12 }} placeholder="Nombre del paso" />
        <button aria-label={`Eliminar paso ${idx + 1}`} onClick={() => onRemove(idx)} style={{ background: 'none', border: 'none', color: 'var(--text-3)', cursor: 'pointer', fontSize: 18 }}>×</button>
      </div>

      {/* Per-type config */}
      {step_type === 'action' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div>
            <label style={ls}>Acción a ejecutar</label>
            <select value={config.action_type || ''} onChange={e => onChange(idx, { ...step, config: { action_type: e.target.value } })} style={fs}>
              <option value="">Seleccionar acción...</option>
              {ACTION_CATEGORIES.map(cat => (
                <optgroup key={cat} label={cat}>
                  {Object.entries(ACTIONS).filter(([,v]) => v.category === cat).map(([k, v]) => (
                    <option key={k} value={k}>{v.icon} {v.label}</option>
                  ))}
                </optgroup>
              ))}
            </select>
          </div>
          {paramDefs.length > 0 && (
            <div style={{ display: 'grid', gridTemplateColumns: `repeat(${Math.min(paramDefs.length, 3)}, 1fr)`, gap: 10 }}>
              {paramDefs.map(p => (
                <div key={p.key}>
                  <label style={ls}>{p.label}</label>
                  {p.type === 'select' ? (
                    <select value={config[p.key] || ''} onChange={e => onChange(idx, { ...step, config: { ...config, [p.key]: e.target.value } })} style={fs}>
                      <option value="">—</option>
                      {p.options.map(o => <option key={o} value={o}>{o}</option>)}
                    </select>
                  ) : (
                    <input value={config[p.key] || ''} onChange={e => onChange(idx, { ...step, config: { ...config, [p.key]: e.target.value } })} style={fs} placeholder={p.label} />
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {step_type === 'rpa' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div>
            <label style={ls}>Plataforma RPA</label>
            <select value={config.platform || ''} onChange={e => onChange(idx, { ...step, config: { platform: e.target.value } })} style={fs}>
              <option value="">Seleccionar plataforma...</option>
              {['rpa_power_automate','rpa_uipath','rpa_zapier','rpa_make','rpa_n8n','rpa_custom_http'].map(k => (
                <option key={k} value={k}>{ACTIONS[k].icon} {ACTIONS[k].label}</option>
              ))}
            </select>
          </div>
          {config.platform && (ACTION_PARAMS[config.platform] || []).map(p => (
            <div key={p.key}>
              <label style={ls}>{p.label}</label>
              {p.type === 'select' ? (
                <select value={config[p.key] || ''} onChange={e => onChange(idx, { ...step, config: { ...config, [p.key]: e.target.value } })} style={fs}>
                  <option value="">—</option>
                  {p.options.map(o => <option key={o} value={o}>{o}</option>)}
                </select>
              ) : (
                <input value={config[p.key] || ''} onChange={e => onChange(idx, { ...step, config: { ...config, [p.key]: e.target.value } })} style={fs} placeholder={p.label} />
              )}
            </div>
          ))}
        </div>
      )}

      {step_type === 'condition' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10 }}>
          <div>
            <label style={ls}>Campo</label>
            <input value={config.field || ''} onChange={e => onChange(idx, { ...step, config: { ...config, field: e.target.value } })} style={fs} placeholder="budget_pct, risk_score…" />
          </div>
          <div>
            <label style={ls}>Operador</label>
            <select value={config.operator || 'equals'} onChange={e => onChange(idx, { ...step, config: { ...config, operator: e.target.value } })} style={fs}>
              {OPERATORS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
          <div>
            <label style={ls}>Valor</label>
            <input value={config.value || ''} onChange={e => onChange(idx, { ...step, config: { ...config, value: e.target.value } })} style={fs} placeholder="80, critical…" />
          </div>
        </div>
      )}

      {step_type === 'wait' && (
        <div style={{ display: 'grid', gridTemplateColumns: '120px 100px', gap: 10 }}>
          <div>
            <label style={ls}>Duración</label>
            <input type="number" min="1" value={config.duration || 1} onChange={e => onChange(idx, { ...step, config: { ...config, duration: +e.target.value } })} style={fs} />
          </div>
          <div>
            <label style={ls}>Unidad</label>
            <select value={config.unit || 'hours'} onChange={e => onChange(idx, { ...step, config: { ...config, unit: e.target.value } })} style={fs}>
              <option value="minutes">minutos</option>
              <option value="hours">horas</option>
              <option value="days">días</option>
            </select>
          </div>
        </div>
      )}

      {step_type === 'webhook' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div>
            <label style={ls}>URL del webhook</label>
            <input value={config.url || ''} onChange={e => onChange(idx, { ...step, config: { ...config, url: e.target.value } })} style={fs} placeholder="https://…" />
          </div>
          <div>
            <label style={ls}>Payload JSON (template)</label>
            <input value={config.payload_template || ''} onChange={e => onChange(idx, { ...step, config: { ...config, payload_template: e.target.value } })} style={fs} placeholder='{"event": "{{trigger}}", "id": "{{entity_id}}"}' />
          </div>
        </div>
      )}

      {step_type === 'notify' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          <div>
            <label style={ls}>Notificar a (rol)</label>
            <select value={config.role || ''} onChange={e => onChange(idx, { ...step, config: { ...config, role: e.target.value } })} style={fs}>
              <option value="">—</option>
              {['admin','pm','employee','hr','team_lead'].map(r => <option key={r} value={r}>{r}</option>)}
            </select>
          </div>
          <div>
            <label style={ls}>Mensaje</label>
            <input value={config.message || ''} onChange={e => onChange(idx, { ...step, config: { ...config, message: e.target.value } })} style={fs} placeholder="Mensaje a enviar" />
          </div>
        </div>
      )}
    </div>
  )
}

function WorkflowModal({ workflow, onClose }) {
  const idPrefix = useId()
  const qc = useQueryClient()
  const toast = useToast()
  const isEdit = !!workflow
  const [form, setForm] = useState({
    name:         workflow?.name || '',
    description:  workflow?.description || '',
    trigger_type: workflow?.trigger_type || 'task_status_changed',
    is_global:    workflow?.is_global ?? true,
    steps:        workflow?.steps?.map(s => ({ ...s, config: s.config || {} })) || [],
  })

  const { mutate, isPending } = useMutation({
    mutationFn: d => isEdit ? api.patch(`/automation-workflows/${workflow.id}`, d) : api.post('/automation-workflows', d),
    onSuccess: () => { qc.invalidateQueries(['workflows']); onClose() },
    onError: e => toast.error(extractErr(e, 'Error al guardar')),
  })

  const addStep = () => setForm(f => ({
    ...f,
    steps: [...f.steps, { step_type: 'action', name: `Paso ${f.steps.length + 1}`, config: {} }],
  }))
  const updateStep = (i, updated) => setForm(f => { const s = [...f.steps]; s[i] = updated; return { ...f, steps: s } })
  const removeStep = i => setForm(f => ({ ...f, steps: f.steps.filter((_, j) => j !== i) }))

  return (
    <Modal open title={isEdit ? `Editar workflow — ${workflow.name}` : 'Nuevo workflow multi-paso'} onClose={onClose} width={660}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14, maxHeight: '80vh', overflowY: 'auto', paddingRight: 4 }}>
        {/* Info banner */}
        <div style={{ background: 'var(--purple-bg)', border: '1px solid #7c3aed30', borderRadius: 8, padding: '10px 14px', fontSize: 12, color: 'var(--text-2)' }}>
          <strong style={{ color: 'var(--purple)' }}>⚡ Workflows multi-paso</strong> — Encadena condiciones, esperas, acciones y llamadas a sistemas RPA (Power Automate, UiPath, Zapier, Make, n8n o cualquier endpoint HTTP).
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div style={{ gridColumn: '1/-1' }}>
            <label htmlFor={`${idPrefix}-name`} style={ls}>Nombre *</label>
            <input id={`${idPrefix}-name`} value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} style={fs} />
          </div>
          <div>
            <label htmlFor={`${idPrefix}-description`} style={ls}>Descripción</label>
            <input id={`${idPrefix}-description`} value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} style={fs} />
          </div>
          <div>
            <label htmlFor={`${idPrefix}-trigger`} style={ls}>Trigger de entrada</label>
            <select id={`${idPrefix}-trigger`} value={form.trigger_type} onChange={e => setForm(f => ({ ...f, trigger_type: e.target.value }))} style={fs}>
              {TRIGGER_CATEGORIES.map(cat => (
                <optgroup key={cat} label={cat}>
                  {Object.entries(TRIGGERS).filter(([,v]) => v.category === cat).map(([k, v]) => (
                    <option key={k} value={k}>{v.icon} {v.label}</option>
                  ))}
                </optgroup>
              ))}
            </select>
          </div>
        </div>

        {/* Steps */}
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
            <label style={{ ...ls, display: 'inline', marginBottom: 0 }}>Pasos del workflow ({form.steps.length})</label>
            <button aria-label="Añadir un nuevo paso al workflow" onClick={addStep} style={{ background: 'transparent', border: '1px dashed #00d4ff40', borderRadius: 6, padding: '4px 12px', color: 'var(--accent)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}>+ Añadir paso</button>
          </div>
          {form.steps.length === 0 && (
            <div style={{ textAlign: 'center', padding: '20px 0', color: 'var(--text-3)', fontSize: 13 }}>Sin pasos aún — añade al menos uno</div>
          )}
          {form.steps.map((step, i) => (
            <StepConfig key={i} step={step} idx={i} onChange={updateStep} onRemove={removeStep} />
          ))}
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, paddingTop: 4 }}>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={() => mutate(form)} loading={isPending} disabled={isPending || !form.name || form.steps.length === 0}>
            {isPending ? 'Guardando...' : isEdit ? 'Guardar cambios' : 'Crear workflow'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ── Workflows Tab ─────────────────────────────────────────────────────────────
function WorkflowsTab() {
  const toast = useToast()
  const qc = useQueryClient()
  const [showModal, setShowModal] = useState(false)
  const [editingWf, setEditingWf] = useState(null)

  const { data: workflows = [], isLoading } = useQuery({
    queryKey: ['workflows'],
    queryFn: () => api.get('/automation-workflows').then(r => r.data),
  })

  const { mutate: update } = useMutation({
    mutationFn: ({ id, data }) => api.patch(`/automation-workflows/${id}`, data),
    onSuccess: () => qc.invalidateQueries(['workflows']),
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: del } = useMutation({
    mutationFn: id => api.delete(`/automation-workflows/${id}`),
    onSuccess: () => qc.invalidateQueries(['workflows']),
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const STATUS_CFG = { draft:{ label:'Borrador', color:'var(--text-2)' }, active:{ label:'Activo', color:'var(--success)' }, paused:{ label:'Pausado', color:'var(--warning)' }, archived:{ label:'Archivado', color:'var(--text-3)' } }

  return (
    <div>
      <div style={{ background: 'var(--purple-bg)', border: '1px solid #7c3aed30', borderRadius: 10, padding: '14px 18px', marginBottom: 20, fontSize: 13 }}>
        <div style={{ fontWeight: 700, color: 'var(--purple)', marginBottom: 4 }}>⚡ Workflows multi-paso con soporte RPA</div>
        <div style={{ color: 'var(--text-2)' }}>
          Encadena condiciones, esperas temporales, notificaciones y acciones de negocio. Los pasos de tipo <strong style={{ color: 'var(--text-1)' }}>🤖 RPA</strong> permiten disparar
          flujos externos: <em>Power Automate, UiPath Orchestrator, Zapier, Make/Integromat, n8n</em> o cualquier endpoint HTTP. Los datos de contexto del evento (id entidad, usuario, etc.) se inyectan automáticamente en el payload.
        </div>
      </div>

      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 16 }}>
        <Button onClick={() => setShowModal(true)}>+ Nuevo workflow</Button>
      </div>

      {isLoading ? <Spinner /> : workflows.length === 0 ? (
        <EmptyState icon="⚡" title="Sin workflows" description="Crea flujos multi-paso con ramificaciones, esperas y llamadas a sistemas RPA" />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {workflows.map(wf => {
            const cfg = STATUS_CFG[wf.status] || { label: wf.status, color: 'var(--text-2)' }
            const triggerCfg = TRIGGERS[wf.trigger_type] || { icon: '⚙️', label: wf.trigger_type }
            return (
              <div key={wf.id} style={{ ...card, padding: '18px 22px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 }}>
                  <div>
                    <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 4 }}>
                      <span style={{ fontSize: 15, fontWeight: 700 }}>{wf.name}</span>
                      <span style={{ fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 20, background: cfg.color + '20', color: cfg.color }}>{cfg.label}</span>
                      {wf.is_global && <span style={{ fontSize: 10, padding: '2px 6px', background: 'var(--purple-bg)', color: 'var(--purple)', borderRadius: 4 }}>GLOBAL</span>}
                    </div>
                    {wf.description && <div style={{ fontSize: 12, color: 'var(--text-2)' }}>{wf.description}</div>}
                    <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 4 }}>
                      {triggerCfg.icon} {triggerCfg.label} · {wf.steps?.length || 0} pasos · {wf.run_count || 0} ejecuciones
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button aria-pressed={wf.status === 'active'} aria-label={`${wf.status === 'active' ? 'Pausar' : 'Activar'} workflow ${wf.name}`} onClick={() => update({ id: wf.id, data: { status: wf.status === 'active' ? 'paused' : 'active' } })}
                      style={{ background: wf.status === 'active' ? 'var(--warning-bg)' : 'var(--success-bg)', border: `1px solid ${wf.status === 'active' ? 'rgba(245,158,11,0.25)' : 'rgba(52,211,153,0.25)'}`, borderRadius: 6, padding: '4px 10px', color: wf.status === 'active' ? 'var(--warning)' : 'var(--success)', cursor: 'pointer', fontSize: 11, fontFamily: 'inherit' }}>
                      {wf.status === 'active' ? '⏸ Pausar' : '▶ Activar'}
                    </button>
                    <button aria-label={`Editar workflow ${wf.name}`} onClick={() => setEditingWf(wf)}
                      style={{ background: 'none', border: '1px solid #1e2d45', borderRadius: 6, padding: '4px 10px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 11 }}>✏ Editar</button>
                    <button aria-label={`Eliminar workflow ${wf.name}`} onClick={() => { openConfirmGlobal({ message: '¿Eliminar este workflow?', onConfirm: () => del(wf.id), danger: true }) }}
                      style={{ background: 'none', border: '1px solid #ff475730', borderRadius: 6, padding: '4px 10px', color: 'var(--danger)', cursor: 'pointer', fontSize: 11 }}>🗑</button>
                  </div>
                </div>

                {/* Steps visual */}
                <div style={{ display: 'flex', gap: 4, alignItems: 'center', flexWrap: 'wrap', marginTop: 8 }}>
                  {wf.steps?.map((s, i) => (
                    <div key={s.id || i} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                      <div style={{ background: 'var(--surface-4)', borderRadius: 6, padding: '4px 10px', fontSize: 12, color: 'var(--text-1)' }}>
                        {STEP_ICONS[s.step_type] || '⚡'} {s.name || s.step_type}
                      </div>
                      {i < wf.steps.length - 1 && <span style={{ color: 'var(--text-3)', fontSize: 14 }}>→</span>}
                    </div>
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {showModal && <WorkflowModal onClose={() => setShowModal(false)} />}
      {editingWf && <WorkflowModal workflow={editingWf} onClose={() => setEditingWf(null)} />}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function AutomationsPage() {
  const _t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [tab, setTab] = useState('rules')  // rules | workflows
  const [editing, setEditing] = useState(null)
  const [showCreate, setShowCreate] = useState(false)
  const [showTemplates, setShowTemplates] = useState(false)
  const [execHistory, setExecHistory] = useState(null)
  const [filterActive, setFilterActive] = useState(null)
  const [testResult, setTestResult] = useState(null)

  const { data: raw = [], isLoading } = useQuery({
    queryKey: ['automations'],
    queryFn: () => api.get('/automations').then(r => r.data),
    refetchInterval: 60000,
  })
  const rules = Array.isArray(raw) ? raw : []

  const { data: templates = [] } = useQuery({
    queryKey: ['auto-templates'],
    queryFn: () => api.get('/automations/templates/list').then(r => r.data),
    enabled: showTemplates,
  })

  const { mutate: del } = useMutation({
    mutationFn: id => api.delete(`/automations/${id}`),
    onSuccess: () => qc.invalidateQueries(['automations']),
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: toggle } = useMutation({
    mutationFn: ({ id, active }) => api.patch(`/automations/${id}`, { is_active: active }),
    onSuccess: () => qc.invalidateQueries(['automations']),
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: test } = useMutation({
    mutationFn: id => api.post(`/automations/${id}/test`).then(r => r.data),
    onSuccess: (data) => setTestResult(data),
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: createFromTemplate } = useMutation({
    mutationFn: tpl => api.post('/automations', {
      name: tpl.name,
      trigger_type: tpl.trigger_type,
      trigger_conditions: tpl.trigger_conditions,
      actions: tpl.actions,
      is_global: true,
    }),
    onSuccess: () => { qc.invalidateQueries(['automations']); setShowTemplates(false) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const filtered = filterActive === null ? rules : rules.filter(r => r.is_active === filterActive)
  const active = rules.filter(r => r.is_active).length

  return (
    <div style={{ padding: 32 }}>
      <PageHeader
        icon={<Bot size={18} />}
        title="Automatizaciones"
        subtitle={`Motor de reglas no-code — SI [evento] ENTONCES [acción]`}
        actions={
          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={() => setShowTemplates(true)}
              style={{ background: 'transparent', border: '1px solid #7c3aed40', borderRadius: 8, padding: '9px 16px', color: 'var(--purple)', cursor: 'pointer', fontSize: 13, fontFamily: 'inherit', fontWeight: 600 }}>
              📋 Plantillas
            </button>
            <Button onClick={() => setShowCreate(true)}>＋ Nueva regla</Button>
          </div>
        }
      />

      {/* Tab selector */}
      <div role="tablist" aria-label="Secciones de automatizaciones" style={{ display: 'flex', gap: 8, marginBottom: 24 }}>
        {[['rules', '⚙️ Reglas simples'], ['workflows', '⚡ Workflows multi-paso']].map(([id, label]) => (
          <button key={id} role="tab" aria-selected={tab === id} aria-controls={`automations-panel-${id}`} id={`automations-tab-${id}`} onClick={() => setTab(id)}
            style={{ padding: '8px 16px', borderRadius: 8, border: `1px solid ${tab === id ? 'var(--accent-glow)' : 'var(--surface-4)'}`, background: tab === id ? 'var(--accent-muted)' : 'transparent', color: tab === id ? 'var(--accent)' : 'var(--text-2)', fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>
            {label}
          </button>
        ))}
      </div>

      {tab === 'workflows' && <div id="automations-panel-workflows" role="tabpanel" aria-labelledby="automations-tab-workflows"><WorkflowsTab /></div>}

      {tab === 'rules' && <div id="automations-panel-rules" role="tabpanel" aria-labelledby="automations-tab-rules">
      {/* Stats */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14, marginBottom: 24 }}>
        {[
          { label: 'Reglas activas', value: active, color: 'var(--accent)', icon: '⚡' },
          { label: 'Reglas pausadas', value: rules.length - active, color: 'var(--text-2)', icon: '⏸' },
          { label: 'Total ejecuciones', value: rules.reduce((s, r) => s + (r.run_count || 0), 0), color: 'var(--success)', icon: '▷' },
          { label: 'Total reglas', value: rules.length, color: 'var(--purple)', icon: '⚙️' },
        ].map(({ label, value, color, icon }) => (
          <div key={label} style={{ background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 12, padding: '14px 18px' }}>
            <div style={{ fontSize: 20, marginBottom: 6 }}>{icon}</div>
            <div style={{ fontSize: 24, fontWeight: 800, color }}>{value}</div>
            <div style={{ fontSize: 12, color: 'var(--text-2)', marginTop: 4 }}>{label}</div>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
        {[[null,'Todas'],[true,'Activas'],[false,'Pausadas']].map(([val, label]) => (
          <button key={String(val)} aria-pressed={filterActive === val} onClick={() => setFilterActive(val)}
            style={{ padding: '6px 14px', borderRadius: 8, border: `1px solid ${filterActive === val ? 'var(--accent-glow)' : 'var(--surface-4)'}`, background: filterActive === val ? 'var(--accent-muted)' : 'transparent', color: filterActive === val ? 'var(--accent)' : 'var(--text-2)', fontSize: 12, cursor: 'pointer', fontFamily: 'inherit' }}>
            {label}
          </button>
        ))}
      </div>

      {/* Rules list */}
      {isLoading ? <Spinner /> : filtered.length === 0 ? (
        <EmptyState
          icon="⚙️"
          title="Sin reglas de automatización"
          description="Crea tu primera regla o usa una plantilla predefinida"
          action={<Button onClick={() => setShowTemplates(true)}>Ver plantillas</Button>}
        />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {filtered.map(rule => (
            <RuleCard key={rule.id} rule={rule}
              onEdit={r => setEditing(r)}
              onDelete={id => del(id)}
              onTest={r => test(r.id)}
              onToggle={r => toggle({ id: r.id, active: !r.is_active })}
            />
          ))}
        </div>
      )}

      {/* Modals */}
      {showCreate && <RuleModal onClose={() => setShowCreate(false)} />}
      {editing && <RuleModal rule={editing} onClose={() => setEditing(null)} />}
      {execHistory && <ExecutionsModal rule={execHistory} onClose={() => setExecHistory(null)} />}

      {/* Test result */}
      {testResult && (
        <Modal open title="Resultado del test" onClose={() => setTestResult(null)} width={500}>
          <div style={{ padding: 4 }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--success)', marginBottom: 12 }}>✓ Regla ejecutada correctamente</div>
            <div style={{ background: 'var(--surface-3)', borderRadius: 8, padding: 14 }}>
              {(testResult.results || []).map((r, i) => (
                <div key={i} style={{ fontSize: 12, padding: '4px 0', borderBottom: '1px solid #1e2d4530', color: r.ok ? 'var(--success)' : 'var(--danger)' }}>
                  {r.ok ? '✓' : '✗'} {r.action}: {r.ok ? 'ejecutado' : r.error}
                </div>
              ))}
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 14 }}>
              <Button onClick={() => setTestResult(null)}>Cerrar</Button>
            </div>
          </div>
        </Modal>
      )}

      {/* Templates modal */}
      {showTemplates && (
        <Modal open title="Plantillas de automatización" onClose={() => setShowTemplates(false)} width={680}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            {templates.map(tpl => {
              const trigger = TRIGGERS[tpl.trigger_type] || { icon: '⚙️', label: tpl.trigger_type }
              return (
                <div key={tpl.id} style={{ background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 10, padding: '14px 16px' }}>
                  <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 4 }}>{tpl.name}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-2)', marginBottom: 10 }}>
                    {trigger.icon} {trigger.label}
                    {tpl.trigger_conditions && ` · ${tpl.trigger_conditions.field} ${tpl.trigger_conditions.operator} ${tpl.trigger_conditions.value}`}
                  </div>
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 12 }}>
                    {tpl.actions.map((a, i) => {
                      const aCfg = ACTIONS[a.type] || { icon: '⚙️', label: a.type }
                      return <span key={i} style={{ fontSize: 11, padding: '2px 7px', borderRadius: 4, background: 'var(--accent-muted)', color: 'var(--accent)' }}>{aCfg.icon} {aCfg.label}</span>
                    })}
                  </div>
                  <button aria-label={`Usar plantilla ${tpl.name}`} onClick={() => createFromTemplate(tpl)}
                    style={{ background: 'linear-gradient(135deg,#00d4ff,#7c3aed)', border: 'none', borderRadius: 6, padding: '6px 14px', color: '#fff', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit', fontWeight: 600, width: '100%' }}>
                    Usar esta plantilla
                  </button>
                </div>
              )
            })}
          </div>
        </Modal>
      )}
      </div>
      }
    </div>
  )
}