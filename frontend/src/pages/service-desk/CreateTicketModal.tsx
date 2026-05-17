// @ts-nocheck
import { useState, useMemo, useId, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { Button, Modal } from '../../components/ui'
import AIInlineEditor from '../../components/AIInlineEditor'
import { useFormValidation } from '../../hooks/useFormValidation'
import { sdCatalogApi, usersApi, clientsApi, ticketsApi, sdDynamicFormsApi } from '../../services/api'
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

  const [form, setForm] = useState({
    ticket_type: 'incident', title: '', description: '',
    priority: 'p3_medium', urgency: 'medium', impact: 'user',
    assigned_to_user_id: '', client_id: '', service_item_id: '',
  })

  const { data: catalog = [] } = useQuery({
    queryKey: ['sd-catalog'],
    queryFn: () => sdCatalogApi.list().then(r => r.data),
  })
  const { data: users = [] } = useQuery({
    queryKey: ['users'],
    queryFn: () => usersApi.list().then(r => r.data),
  })
  const { data: clients = [] } = useQuery({
    queryKey: ['clients'],
    queryFn: () => clientsApi.list().then(r => r.data?.items ?? r.data ?? []),
  })
  const { data: dynamicFormRules } = useQuery({
    queryKey: ['sd-dynamic-forms'],
    queryFn: () => sdDynamicFormsApi.get().then(r => r.data),
  })
  const { data: dynamicHistory = { items: [] } } = useQuery({
    queryKey: ['sd-dynamic-forms-history'],
    queryFn: () => sdDynamicFormsApi.history().then(r => r.data),
  })
  const { data: contextOptions = { clients: [], services: [], cis: [] } } = useQuery({
    queryKey: ['sd-dynamic-forms-context', form.client_id, form.service_item_id],
    queryFn: () => sdDynamicFormsApi.contextOptions({
      client_id: form.client_id || undefined,
      service_item_id: form.service_item_id || undefined,
      limit: 60,
    }).then(r => r.data),
  })
  const [dynamicValues, setDynamicValues] = useState({})
  const [wizardOpen, setWizardOpen] = useState(false)
  const [wizardStep, setWizardStep] = useState(1)
  const [csvText, setCsvText] = useState('')
  const [generatedFields, setGeneratedFields] = useState([])
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

  const visibleDynamicFields = useMemo(() => {
    const fields = dynamicFormRules?.fields || []
    const source = { ...form, ...dynamicValues }
    return fields.filter(f => {
      const cond = f?.visible_when
      if (!cond || !cond.field) return true
      const current = source[cond.field]
      if (Object.prototype.hasOwnProperty.call(cond, 'equals')) return current === cond.equals
      if (Array.isArray(cond.in)) return cond.in.includes(current)
      return true
    })
  }, [dynamicFormRules, form, dynamicValues])

  useEffect(() => {
    const visibleIds = new Set(visibleDynamicFields.map(f => f.id))
    setDynamicValues(prev => {
      let changed = false
      const next = {}
      for (const [k, v] of Object.entries(prev)) {
        if (visibleIds.has(k)) next[k] = v
        else changed = true
      }
      return changed ? next : prev
    })
  }, [visibleDynamicFields])

  const routingHint = useMemo(() => {
    const hints = dynamicFormRules?.routing_hints || []
    for (const h of hints) {
      const w = h?.when || {}
      if (!w.field) continue
      const current = form[w.field]
      if ((Object.prototype.hasOwnProperty.call(w, 'equals') && current === w.equals) ||
          (Array.isArray(w.in) && w.in.includes(current))) {
        return h?.set || null
      }
    }
    return null
  }, [dynamicFormRules, form])

  const buildPayload = raw => {
    const dynamicPayload = Object.fromEntries(
      Object.entries(dynamicValues).filter(([, v]) => (v ?? '').toString().trim() !== '')
    )

    const payload = {
      ticket_type: raw.ticket_type,
      title: raw.title?.trim(),
      description: raw.description?.trim(),
      priority: raw.priority,
      urgency: raw.urgency,
      impact: raw.impact,
      dynamic_fields: dynamicPayload,
    }
    if (raw.assigned_to_user_id) payload.assigned_to_user_id = raw.assigned_to_user_id
    if (raw.client_id) payload.client_id = raw.client_id
    if (raw.service_item_id) payload.service_item_id = raw.service_item_id
    return payload
  }

  const { mutate, isPending } = useMutation({
    mutationFn: data => ticketsApi.create(data),
    onSuccess: res => {
      validation.setErrors({})
      qc.invalidateQueries({ queryKey: ['sd-tickets'] })
      toast.success(`${t('service_desk.ticket_created_success')} ${res.data?.number || ''}`)
      onCreated?.(res.data)
      onClose()
    },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const previewImport = useMutation({
    mutationFn: () => sdDynamicFormsApi.importPreview({ csv_text: csvText, mapping: {} }),
    onSuccess: (res) => {
      setGeneratedFields(res?.data?.generated_fields || [])
      setWizardStep(2)
    },
    onError: (e) => toast.error(extractErr(e, 'No se pudo previsualizar el CSV')),
  })

  const applyImport = useMutation({
    mutationFn: () => sdDynamicFormsApi.importApply({ generated_fields: generatedFields, merge_mode: 'upsert' }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sd-dynamic-forms'] })
      qc.invalidateQueries({ queryKey: ['sd-dynamic-forms-history'] })
      toast.success('Campos dinámicos importados')
      setWizardOpen(false)
      setWizardStep(1)
      setCsvText('')
      setGeneratedFields([])
    },
    onError: (e) => toast.error(extractErr(e, 'No se pudo aplicar la importación')),
  })

  const rollbackConfig = useMutation({
    mutationFn: (snapshotId) => sdDynamicFormsApi.rollback(snapshotId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sd-dynamic-forms'] })
      qc.invalidateQueries({ queryKey: ['sd-dynamic-forms-history'] })
      toast.success('Configuración restaurada')
    },
    onError: (e) => toast.error(extractErr(e, 'No se pudo restaurar configuración')),
  })

  const IS = INPUT_STYLE
  const LS = LABEL_STYLE

  const contextSuggestionsForField = (f) => {
    const source = f?.data_source || (f?.type || '').replace('context_', '')
    if (source === 'ci') {
      const attr = (f?.data_attribute || 'name').toLowerCase()
      return (contextOptions.cis || []).map(ci => String(ci[attr] || ci.name || ci.code || ''))
    }
    if (source === 'service') {
      const attr = (f?.data_attribute || 'name').toLowerCase()
      return (contextOptions.services || []).map(s => String(s[attr] || s.name || ''))
    }
    if (source === 'client') {
      const attr = (f?.data_attribute || 'name').toLowerCase()
      return (contextOptions.clients || []).map(c => String(c[attr] || c.name || ''))
    }
    return []
  }

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
          {validation.errors.ticket_type && <div style={{ color: 'var(--danger)', fontSize: "var(--text-xs)", marginTop: 4 }}>{validation.errors.ticket_type}</div>}
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
            style={validation.inputStyle(IS, 'title')} placeholder={t('service_desk.ticket_title')} />
          {validation.errors.title && <div style={{ color: 'var(--danger)', fontSize: "var(--text-xs)", marginTop: 4 }}>{validation.errors.title}</div>}
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
          {validation.errors.description && <div style={{ color: 'var(--danger)', fontSize: "var(--text-xs)", marginTop: 4 }}>{validation.errors.description}</div>}
        </div>

        <div>
          <label htmlFor={`${idPrefix}-urgency`} style={LS}>{t('service_desk.edit_urgency')}</label>
          <select id={`${idPrefix}-urgency`} value={form.urgency} onChange={set('urgency')} style={validation.inputStyle(IS, 'urgency')}>
            {[['critical', t('service_desk.urgency_critical')], ['high', t('service_desk.urgency_high')],
              ['medium', t('service_desk.urgency_medium')], ['low', t('service_desk.urgency_low')]
            ].map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          {validation.errors.urgency && <div style={{ color: 'var(--danger)', fontSize: "var(--text-xs)", marginTop: 4 }}>{validation.errors.urgency}</div>}
        </div>
        <div>
          <label htmlFor={`${idPrefix}-impact`} style={LS}>{t('service_desk.edit_impact')}</label>
          <select id={`${idPrefix}-impact`} value={form.impact} onChange={set('impact')} style={validation.inputStyle(IS, 'impact')}>
            {[['enterprise', t('service_desk.impact_enterprise')], ['department', t('service_desk.impact_department')],
              ['user', t('service_desk.impact_user')], ['minimal', t('service_desk.impact_minimal')]
            ].map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          {validation.errors.impact && <div style={{ color: 'var(--danger)', fontSize: "var(--text-xs)", marginTop: 4 }}>{validation.errors.impact}</div>}
        </div>

        <div style={{ gridColumn: '1/-1', display: 'flex', alignItems: 'center', gap: 12, background: 'var(--surface-1)', borderRadius: 8, padding: '10px 14px' }}>
          <span style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)' }}>{t('service_desk.ticket_auto_routing')}:</span>
          <PBadge v={suggestedPrio} />
          <button onClick={() => setForm(f => ({ ...f, priority: suggestedPrio }))}
            style={{ fontSize: "var(--text-xs)", color: 'var(--accent)', background: 'none', border: 'none', cursor: 'pointer' }}>
            {t('common.save')}
          </button>
          <select aria-label={t('service_desk.ticket_priority')} value={form.priority} onChange={set('priority')}
            style={{ ...validation.inputStyle(IS, 'priority'), width: 'auto', flex: 1 }}>
            {['p1_critical', 'p2_high', 'p3_medium', 'p4_low'].map(p =>
              <option key={p} value={p}>{PRIORITY_LABEL[p]}</option>)}
          </select>
        </div>

        {routingHint && (
          <div style={{ gridColumn: '1/-1', background: 'var(--info-bg)', border: '1px solid var(--info-border)', borderRadius: 8, padding: '8px 10px', color: 'var(--info)' }}>
            Hint de routing aplicado: {Object.entries(routingHint).map(([k, v]) => `${k}=${v}`).join(', ')}
          </div>
        )}

        {visibleDynamicFields.map((f) => (
          <div key={f.id} style={{ gridColumn: f.type === 'textarea' ? '1/-1' : 'auto' }}>
            <label htmlFor={`${idPrefix}-${f.id}`} style={LS}>{f.label}{f.required ? ' *' : ''}</label>
            {f.type === 'select' ? (
              <select
                id={`${idPrefix}-${f.id}`}
                value={dynamicValues[f.id] || ''}
                onChange={(e) => setDynamicValues(v => ({ ...v, [f.id]: e.target.value }))}
                style={IS}
              >
                <option value="">Seleccionar</option>
                {(f.options || []).map((op) => <option key={op} value={op}>{op}</option>)}
              </select>
            ) : f.type === 'textarea' ? (
              <textarea
                id={`${idPrefix}-${f.id}`}
                value={dynamicValues[f.id] || ''}
                onChange={(e) => setDynamicValues(v => ({ ...v, [f.id]: e.target.value }))}
                style={{ ...IS, resize: 'vertical', minHeight: 88 }}
              />
            ) : (f.type || '').startsWith('context_') ? (
              <>
                <input
                  id={`${idPrefix}-${f.id}`}
                  type="text"
                  list={`${idPrefix}-${f.id}-options`}
                  value={dynamicValues[f.id] || ''}
                  onChange={(e) => setDynamicValues(v => ({ ...v, [f.id]: e.target.value }))}
                  style={IS}
                />
                <datalist id={`${idPrefix}-${f.id}-options`}>
                  {contextSuggestionsForField(f).map((op, idx) => <option key={`${f.id}-${idx}`} value={op} />)}
                </datalist>
              </>
            ) : (
              <input
                id={`${idPrefix}-${f.id}`}
                type={f.type === 'date' ? 'date' : 'text'}
                value={dynamicValues[f.id] || ''}
                onChange={(e) => setDynamicValues(v => ({ ...v, [f.id]: e.target.value }))}
                style={IS}
              />
            )}
          </div>
        ))}

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
          <Button variant="secondary" onClick={() => setWizardOpen(true)}>Wizard campos</Button>
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={submit} disabled={isPending} loading={isPending}>
            {t('service_desk.ticket_create_btn')}
          </Button>
        </div>
      </div>

      <Modal open={wizardOpen} onClose={() => setWizardOpen(false)} title="Wizard de campos dinámicos" size="lg">
        {wizardStep === 1 && (
          <div style={{ display: 'grid', gap: 12 }}>
            <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-2)' }}>
              Pega CSV con cabeceras para generar campos dinámicos.
            </div>
            <textarea
              value={csvText}
              onChange={(e) => setCsvText(e.target.value)}
              placeholder={'campo_a,campo_b\nvalor1,valor2'}
              style={{ ...IS, minHeight: 140, resize: 'vertical' }}
            />
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>También puedes restaurar snapshots previos</div>
              <Button onClick={() => previewImport.mutate()} disabled={!csvText.trim()} loading={previewImport.isPending}>Previsualizar</Button>
            </div>
            <div style={{ borderTop: '1px solid var(--surface-4)', paddingTop: 10, display: 'grid', gap: 8 }}>
              {(dynamicHistory.items || []).slice(0, 5).map((h) => (
                <div key={h.snapshot_id} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 10px' }}>
                  <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-2)' }}>
                    {h.created_at} · {h.reason || 'update'}
                  </div>
                  <Button variant="secondary" onClick={() => rollbackConfig.mutate(h.snapshot_id)} loading={rollbackConfig.isPending}>Restaurar</Button>
                </div>
              ))}
            </div>
          </div>
        )}

        {wizardStep === 2 && (
          <div style={{ display: 'grid', gap: 10 }}>
            <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-2)' }}>Previsualización de campos detectados</div>
            <div style={{ maxHeight: 280, overflowY: 'auto', border: '1px solid var(--surface-4)', borderRadius: 8 }}>
              {generatedFields.map((f, idx) => (
                <div key={`${f.id}-${idx}`} style={{ display: 'grid', gridTemplateColumns: '1fr 120px 1fr', gap: 8, padding: '8px 10px', borderBottom: '1px solid var(--surface-4)' }}>
                  <input value={f.label || ''} onChange={(e) => {
                    const v = [...generatedFields]
                    v[idx] = { ...v[idx], label: e.target.value }
                    setGeneratedFields(v)
                  }} style={IS} />
                  <select value={f.type || 'text'} onChange={(e) => {
                    const v = [...generatedFields]
                    v[idx] = { ...v[idx], type: e.target.value }
                    setGeneratedFields(v)
                  }} style={IS}>
                    <option value="text">text</option>
                    <option value="textarea">textarea</option>
                    <option value="select">select</option>
                    <option value="date">date</option>
                  </select>
                  <input value={f.id || ''} onChange={(e) => {
                    const v = [...generatedFields]
                    v[idx] = { ...v[idx], id: e.target.value }
                    setGeneratedFields(v)
                  }} style={IS} />
                </div>
              ))}
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10 }}>
              <Button variant="secondary" onClick={() => setWizardStep(1)}>Atrás</Button>
              <Button onClick={() => applyImport.mutate()} loading={applyImport.isPending}>Aplicar importación</Button>
            </div>
          </div>
        )}
      </Modal>
    </Modal>
  )
}
