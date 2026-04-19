import { useState, useMemo, useId } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { extractErr } from '../../utils/helpers'
import { Button, Modal } from '../../components/ui'
import AIInlineEditor from '../../components/AIInlineEditor'
import { useFormValidation } from '../../hooks/useFormValidation'
import api from '../../services/api'
import { z } from 'zod'
import { PBadge, PRIORITY_LABEL, INPUT_STYLE, LABEL_STYLE } from './sdUtils'

function getCreateTicketSchema(t) {
  return z.object({
    ticket_type: z.enum(['incident', 'service_request', 'change', 'problem', 'question']),
    title: z.string().trim().min(1, t('service_desk.zod_title_required')),
    description: z.string().trim().min(1, t('service_desk.zod_description_required')),
    priority: z.enum(['p1_critical', 'p2_high', 'p3_medium', 'p4_low']),
    urgency: z.enum(['critical', 'high', 'medium', 'low']),
    impact: z.enum(['enterprise', 'department', 'user', 'minimal']),
    assigned_to_user_id: z.string().optional(),
    client_id: z.string().optional(),
    service_item_id: z.string().optional(),
  })
}

export default function CreateTicketModal({ onClose, onCreated }) {
  const t = useAppT()
  const idPrefix = useId()
  const qc = useQueryClient()
  const toast = useToast()

  const { data: catalog = [] } = useQuery({
    queryKey: ['sd-catalog'],
    queryFn: () => api.get('/sd/catalog').then(r => r.data),
  })
  const { data: users = [] } = useQuery({
    queryKey: ['users'],
    queryFn: () => api.get('/users').then(r => r.data),
  })
  const { data: clients = [] } = useQuery({
    queryKey: ['clients'],
    queryFn: () => api.get('/clients').then(r => r.data),
  })

  const [form, setForm] = useState({
    ticket_type: 'incident', title: '', description: '',
    priority: 'p3_medium', urgency: 'medium', impact: 'user',
    assigned_to_user_id: '', client_id: '', service_item_id: '',
  })
  const validation = useFormValidation(getCreateTicketSchema(t))

  const suggestedPrio = useMemo(() => {
    const matrix = {
      critical_enterprise: 'p1_critical', critical_department: 'p1_critical', critical_user: 'p2_high',
      high_enterprise: 'p1_critical', high_department: 'p2_high', high_user: 'p2_high',
      medium_enterprise: 'p2_high', medium_department: 'p3_medium', medium_user: 'p3_medium',
      low_enterprise: 'p3_medium', low_department: 'p4_low', low_user: 'p4_low',
    }
    return matrix[`${form.urgency}_${form.impact}`] || 'p3_medium'
  }, [form.urgency, form.impact])

  const set = k => e => {
    setForm(f => ({ ...f, [k]: e.target.value }))
    validation.clearFieldError(k)
  }

  const buildPayload = raw => {
    const payload = {
      ticket_type: raw.ticket_type,
      title: raw.title?.trim(),
      description: raw.description?.trim(),
      priority: raw.priority,
      urgency: raw.urgency,
      impact: raw.impact,
    }
    if (raw.assigned_to_user_id) payload.assigned_to_user_id = raw.assigned_to_user_id
    if (raw.client_id) payload.client_id = raw.client_id
    if (raw.service_item_id) payload.service_item_id = raw.service_item_id
    return payload
  }

  const { mutate, isPending } = useMutation({
    mutationFn: data => api.post('/sd/tickets', data),
    onSuccess: res => {
      validation.setErrors({})
      qc.invalidateQueries({ queryKey: ['sd-tickets'] })
      toast.success(`${t('service_desk.ticket_created_success')} ${res.data?.number || ''}`)
      onCreated?.(res.data)
      onClose()
    },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const IS = INPUT_STYLE
  const LS = LABEL_STYLE

  const submit = () => {
    const result = validation.validateForm(form)
    if (!result.success) return
    mutate(buildPayload(result.data))
  }

  return (
    <Modal open title={t('service_desk.ticket_create_btn')} onClose={onClose} size="lg">
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <div>
          <label htmlFor={`${idPrefix}-ticket-type`} style={LS}>{t('service_desk.ticket_type')} *</label>
          <select id={`${idPrefix}-ticket-type`} value={form.ticket_type} onChange={set('ticket_type')} style={validation.inputStyle(IS, 'ticket_type')}>
            {[['incident', t('service_desk.type_incident')], ['service_request', t('service_desk.type_service_request')],
              ['change', t('service_desk.type_change')], ['problem', t('service_desk.type_problem')], ['question', t('service_desk.type_question')]
            ].map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          {validation.errors.ticket_type && <div style={{ color: 'var(--danger)', fontSize: 11, marginTop: 4 }}>{validation.errors.ticket_type}</div>}
        </div>
        <div>
          <label htmlFor={`${idPrefix}-service-item`} style={LS}>{t('service_desk.svc_ticket_type')}</label>
          <select id={`${idPrefix}-service-item`} value={form.service_item_id} onChange={set('service_item_id')} style={IS}>
            <option value="">{t('service_desk.ticket_no_service')}</option>
            {catalog.flatMap(cat => cat.services?.map(s => (
              <option key={s.id} value={s.id}>{cat.name} → {s.name}</option>
            )) || [])}
          </select>
        </div>
        <div style={{ gridColumn: '1/-1' }}>
          <label htmlFor={`${idPrefix}-title`} style={LS}>{t('service_desk.ticket_title')} *</label>
          <input id={`${idPrefix}-title`} value={form.title} onChange={set('title')}
            style={validation.inputStyle(IS, 'title')} placeholder={t(modulo.clave)} />
          {validation.errors.title && <div style={{ color: 'var(--danger)', fontSize: 11, marginTop: 4 }}>{validation.errors.title}</div>}
        </div>
        <div style={{ gridColumn: '1/-1' }}>
          <label htmlFor={`${idPrefix}-description`} style={LS}>{t('common.description')} *</label>
          <AIInlineEditor
            inputId={`${idPrefix}-description`}
            ariaLabel={t('common.description')}
            value={form.description}
            onChange={val => set('description')({ target: { value: val } })}
            rows={4}
            style={{ ...validation.inputStyle(IS, 'description'), resize: 'vertical' }}
          />
          {validation.errors.description && <div style={{ color: 'var(--danger)', fontSize: 11, marginTop: 4 }}>{validation.errors.description}</div>}
        </div>

        <div>
          <label htmlFor={`${idPrefix}-urgency`} style={LS}>{t('service_desk.edit_urgency')}</label>
          <select id={`${idPrefix}-urgency`} value={form.urgency} onChange={set('urgency')} style={validation.inputStyle(IS, 'urgency')}>
            {[['critical', t('service_desk.urgency_critical')], ['high', t('service_desk.urgency_high')],
              ['medium', t('service_desk.urgency_medium')], ['low', t('service_desk.urgency_low')]
            ].map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          {validation.errors.urgency && <div style={{ color: 'var(--danger)', fontSize: 11, marginTop: 4 }}>{validation.errors.urgency}</div>}
        </div>
        <div>
          <label htmlFor={`${idPrefix}-impact`} style={LS}>{t('service_desk.edit_impact')}</label>
          <select id={`${idPrefix}-impact`} value={form.impact} onChange={set('impact')} style={validation.inputStyle(IS, 'impact')}>
            {[['enterprise', t('service_desk.impact_enterprise')], ['department', t('service_desk.impact_department')],
              ['user', t('service_desk.impact_user')], ['minimal', t('service_desk.impact_minimal')]
            ].map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          {validation.errors.impact && <div style={{ color: 'var(--danger)', fontSize: 11, marginTop: 4 }}>{validation.errors.impact}</div>}
        </div>

        <div style={{ gridColumn: '1/-1', display: 'flex', alignItems: 'center', gap: 12, background: 'var(--surface-1)', borderRadius: 8, padding: '10px 14px' }}>
          <span style={{ fontSize: 12, color: 'var(--text-3)' }}>{t('service_desk.ticket_auto_routing')}:</span>
          <PBadge v={suggestedPrio} />
          <button onClick={() => setForm(f => ({ ...f, priority: suggestedPrio }))}
            style={{ fontSize: 11, color: 'var(--accent)', background: 'none', border: 'none', cursor: 'pointer' }}>
            {t('common.save')}
          </button>
          <select aria-label={t(modulo.clave)} value={form.priority} onChange={set('priority')}
            style={{ ...validation.inputStyle(IS, 'priority'), width: 'auto', flex: 1 }}>
            {['p1_critical', 'p2_high', 'p3_medium', 'p4_low'].map(p =>
              <option key={p} value={p}>{PRIORITY_LABEL[p]}</option>)}
          </select>
        </div>

        <div>
          <label htmlFor={`${idPrefix}-assigned-to`} style={LS}>{t('common.assigned_to')}</label>
          <select id={`${idPrefix}-assigned-to`} value={form.assigned_to_user_id} onChange={set('assigned_to_user_id')} style={IS}>
            <option value="">{t('service_desk.ticket_auto_routing')}</option>
            {users.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
          </select>
        </div>
        <div>
          <label htmlFor={`${idPrefix}-client`} style={LS}>{t('service_desk.detail_requester')}</label>
          <select id={`${idPrefix}-client`} value={form.client_id} onChange={set('client_id')} style={IS}>
            <option value="">{t('service_desk.ticket_no_client')}</option>
            {(Array.isArray(clients) ? clients : clients?.items || []).map(c =>
              <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>

        <div style={{ gridColumn: '1/-1', display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 8 }}>
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={submit} disabled={isPending} loading={isPending}>
            {t('service_desk.ticket_create_btn')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}
