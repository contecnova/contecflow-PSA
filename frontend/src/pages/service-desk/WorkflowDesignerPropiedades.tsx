// Panel de propiedades de un nodo del disenador de flujos y sus campos. 23-11-2026: troceado de WorkflowDesignerPage sin cambio de comportamiento.
import { useId } from 'react'
import { Trash2, MousePointerClick } from 'lucide-react'
import { IconButton, Select, Input, Textarea } from '../../components/ui'
import { useAppLang } from '../../i18n/AppLangContext'
import { ESTADOS_DE_TICKET } from '../../constants/catalogos'
import { type DatosNodo, NODE_VISUAL, type NodoFlujo, type ValorConfig, colorVar, labelStyle, nombreDeNodo } from './WorkflowDesignerComun'

// Los mismos que `workflow_triggers.DISPARADORES` y `TicketStatus` del servidor.
const DISPARADORES_DE_FLUJO = ['created', 'assigned', 'group_assigned', 'status_changed', 'priority_changed',
  'commented', 'sla_warning', 'sla_breached', 'ola_breached', 'uc_breached', 'escalated']

// 19-11-2026: `ESTADOS_DE_TICKET` viene de `constants/catalogos` (una sola fuente).
// Clave de traduccion de cada estado (las mismas que SBadge, en `service_desk`).
const TICKET_STATUS_KEY: Record<string, string> = {
  new: 'status_new', assigned: 'status_assigned', in_progress: 'status_in_progress',
  pending_client: 'status_waiting_client', pending_third: 'status_pending_third',
  resolved: 'status_resolved', closed: 'status_closed', cancelled: 'status_cancelled',
}

export function PropertiesPanel({ node, onChange, onDelete }: { node: NodoFlujo | null; onChange: (patch: Partial<DatosNodo>) => void; onDelete: () => void }) {
  const idCampo = useId()
  const { t: traducir } = useAppLang()
  if (!node) {
    return (
      <div className="wfd-props wfd-props--empty">
        <MousePointerClick size={20} aria-hidden="true" />
        <span>{traducir('workflowdesigner.selecciona_un_nodo_para_editar_sus_propiedades')}</span>
      </div>
    )
  }
  const t = node.data.type
  const config = node.data.config || {}
  const setConfig = (k: string, v: ValorConfig) => onChange({ config: { ...config, [k]: v } })

  return (
    <div className="wfd-props">
      <div className="u-row-between">
        <div className="wfd-bold wfd-c" style={colorVar(NODE_VISUAL[t]?.color ?? 'inherit')}>
          {nombreDeNodo(t, traducir)} <span className="u-text3-xs">· {node.id.slice(0, 10)}</span>
        </div>
        <IconButton variante="caja" tono="peligro" ariaLabel={traducir('workflowdesigner.eliminar_nodo')} onClick={onDelete}>
          <Trash2 size={14} aria-hidden="true" />
        </IconButton>
      </div>
      <div>
        <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className={labelStyle}>{traducir('workflowdesigner.etiqueta')}</label>
        <Input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={node.data.label || ''} onChange={e => onChange({ label: e.target.value })} inputClassName="wfd-input" />
      </div>

      {/* Campos por tipo */}
      {t === 'start' && <>
        <FieldSelect label={traducir('sd_cfg.wf_trigger')} value={config.trigger || ''} onChange={v => setConfig('trigger', v || null)} options={[
          { v: '', l: traducir('sd_cfg.wf_trigger_manual') },
          ...DISPARADORES_DE_FLUJO.map(d => ({ v: d, l: traducir(`sd_cfg.ev_${d}`) })),
        ]} />
        {config.trigger && <>
          <FieldText label={traducir('sd_cfg.wf_condition')} value={config.condition} onChange={v => setConfig('condition', v)} placeholder={traducir('sd_cfg.wf_condition_hint')} />
          <div className="u-text3-xs">{traducir('sd_cfg.wf_condition_help')}</div>
        </>}
      </>}
      {t === 'state' && <>
        <FieldSelect label={traducir('workflowdesigner.th_estado')} value={config.status || ''} onChange={v => setConfig('status', v)} options={[
          { v: '', l: '—' },
          ...ESTADOS_DE_TICKET.map(e => ({ v: e, l: traducir(`service_desk.${TICKET_STATUS_KEY[e]}`) })),
        ]} />
        <FieldText label={traducir('workflowdesigner.asignar_al_rol')} value={config.assignee_role} onChange={v => setConfig('assignee_role', v)} placeholder="support_l1" />
        <FieldNumber label={traducir('workflowdesigner.sla_horas')} value={config.sla_hours} onChange={v => setConfig('sla_hours', v)} />
      </>}
      {t === 'decision' && <>
        <FieldText label={traducir('workflowdesigner.expresion')} value={config.expression} onChange={v => setConfig('expression', v)} placeholder="priority == 'P1'" />
      </>}
      {t === 'approval' && <>
        <FieldText label={traducir('workflowdesigner.rol_que_aprueba')} value={config.approver_role} onChange={v => setConfig('approver_role', v)} placeholder={traducir('workflowdesigner.ph_rol_aprobador')} />
        <FieldNumber label={traducir('workflowdesigner.plazo_horas')} value={config.deadline_hours} onChange={v => setConfig('deadline_hours', v)} />
      </>}
      {t === 'wait' && <>
        <FieldNumber label={traducir('workflowdesigner.esperar_minutos')} value={config.wait_minutes} onChange={v => setConfig('wait_minutes', v)} />
        <FieldText label={traducir('workflowdesigner.o_hasta_el_campo')} value={config.until_field} onChange={v => setConfig('until_field', v)} placeholder="due_date" />
      </>}
      {t === 'notify' && <>
        <FieldSelect label={traducir('workflowdesigner.canal')} value={config.channel || 'in_app'} onChange={v => setConfig('channel', v)} options={[
          { v: 'in_app', l: traducir('workflowdesigner.campana') }, { v: 'email', l: traducir('workflowdesigner.campana_correo') },
        ]} />
        <FieldText label={traducir('workflowdesigner.titulo_campo')} value={config.title ?? config.template_id} onChange={v => setConfig('title', v)} placeholder={traducir('workflowdesigner.ph_titulo_aviso')} />
        <FieldTextarea label={traducir('workflowdesigner.mensaje')} value={config.body} onChange={v => setConfig('body', v)} />
        <FieldText label={traducir('workflowdesigner.destinatarios')} value={config.recipients} onChange={v => setConfig('recipients', v)} placeholder="$assignee, $group" />
      </>}
      {t === 'http_call' && <>
        <FieldSelect label={traducir('workflowdesigner.metodo')} value={config.method || 'POST'} onChange={v => setConfig('method', v)} options={[
          { v: 'GET', l: 'GET' }, { v: 'POST', l: 'POST' }, { v: 'PATCH', l: 'PATCH' }, { v: 'DELETE', l: 'DELETE' },
        ]} />
        <FieldText label="URL" value={config.url} onChange={v => setConfig('url', v)} placeholder="https://api.x.com/foo" />
        <FieldTextarea label={traducir('workflowdesigner.cuerpo_json')} value={config.body_template} onChange={v => setConfig('body_template', v)} />
      </>}
      {t === 'create_ticket' && <>
        <FieldText label={traducir('workflowdesigner.cola')} value={config.queue} onChange={v => setConfig('queue', v)} placeholder={traducir('workflowdesigner.ph_cola')} />
        <FieldText label={traducir('workflowdesigner.plantilla_de_titulo')} value={config.title_template} onChange={v => setConfig('title_template', v)} placeholder={traducir('workflowdesigner.ph_titulo_ticket')} />
        {/* La descripción es obligatoria en el modelo de ticket y no había campo
            para escribirla: el motor se cae al título si se deja en blanco. */}
        <FieldText label={traducir('workflowdesigner.plantilla_de_descripcion')} value={config.description_template} onChange={v => setConfig('description_template', v)} placeholder={traducir('workflowdesigner.creado_por_el_flujo_desde_title')} />
        <FieldSelect label={traducir('workflowdesigner.prioridad')} value={config.priority || 'P3'} onChange={v => setConfig('priority', v)} options={
          ['P1', 'P2', 'P3', 'P4'].map(p => ({ v: p, l: traducir(`workflowdesigner.prio_${p.toLowerCase()}`) }))
        } />
      </>}
    </div>
  )
}

function FieldText({ label, value, onChange, placeholder }: { label: string; value: ValorConfig; onChange: (v: string) => void; placeholder?: string }) {
  const idCampo = useId()
  return (
    <div>
      <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className={labelStyle}>{label}</label>
      <Input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={value || ''} onChange={e => onChange(e.target.value)} placeholder={placeholder} inputClassName="wfd-input" />
    </div>
  )
}

function FieldNumber({ label, value, onChange }: { label: string; value: ValorConfig; onChange: (v: number | null) => void }) {
  const idCampo = useId()
  return (
    <div>
      <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className={labelStyle}>{label}</label>
      <Input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} type="number" value={value ?? ''} onChange={e => onChange(e.target.value === '' ? null : Number(e.target.value))} inputClassName="wfd-input" />
    </div>
  )
}

function FieldSelect({ label, value, onChange, options }: { label: string; value: ValorConfig; onChange: (v: string) => void; options: { v: string; l: string }[] }) {
  const idCampo = useId()
  return (
    <div>
      <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className={labelStyle}>{label}</label>
      <Select suelto placeholder={false} id={`${idCampo}-1`} value={value || ''} onChange={e => onChange(e.target.value)} className="wfd-sel">
        {options.map((o) => <option key={o.v} value={o.v}>{o.l}</option>)}
      </Select>
    </div>
  )
}

function FieldTextarea({ label, value, onChange }: { label: string; value: ValorConfig; onChange: (v: string) => void }) {
  const idCampo = useId()
  return (
    <div>
      <Textarea label={label} id={`${idCampo}-1`} rows={3} value={value || ''} onChange={e => onChange(e.target.value)} inputClassName="wfd-input--mono ds-campo-codigo" />
    </div>
  )
}
