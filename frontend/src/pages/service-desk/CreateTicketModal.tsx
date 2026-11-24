/**
 * CreateTicketModal — alta de un ticket.
 *
 * 16-11-2026 (pasada de diseño): título «Nuevo ticket» y botón «Crear ticket»;
 * el campo del catálogo se llama «Servicio» (decía «Tipo de ticket») y el del
 * cliente «Cliente» (decía «Solicitante»); la prioridad sugerida por urgencia e
 * impacto se aplica con un botón «Aplicar» (era un «Guardar» suelto junto a
 * «Auto-routing / Sin asignar»); errores, tipos de campo y etiquetas del
 * asistente de campos traducidos; fechas del historial con el formateador.
 */
import { useState, useMemo, useId, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { extractErr, fmtDateTime } from '../../utils/helpers'
import { useListaDeUsuarios } from '../../hooks/useListas'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { Sparkles } from 'lucide-react'
import { Button, Modal, Select, useErroresDeCampo, Input, Textarea } from '../../components/ui'
import AIInlineEditor from '../../components/AIInlineEditor'
import DateInput from '../../components/ui/DateInput'
import { useFormValidation } from '../../hooks/useFormValidation'
import { sdCatalogApi, clientsApi, ticketsApi, sdDynamicFormsApi } from '../../services/api'
import type { SdCampoDinamico, SdTicket } from '../../services/api/tipos-sd'
import { z } from 'zod'
import { PBadge, PRIORITY_LABEL } from './sdUtils'
import { DYNAMIC_FORM_OPTIONS_LIMIT } from '../../constants/pagination'
import './CreateTicketModal.css'
import CatalogoInteligente from '../../components/servicedesk/CatalogoInteligente'
import { usePermiso } from '../../permisos/usePermiso'
import { etiquetaDeCampoDinamico, etiquetaDeOpcionDinamica, valorDePistaDeEnrutado } from './camposDinamicosSd'

type TicketType = 'incident' | 'service_request' | 'change' | 'problem' | 'question'
type TicketPriority = 'p1_critical' | 'p2_high' | 'p3_medium' | 'p4_low'
const PRIORIDADES: readonly TicketPriority[] = ['p1_critical', 'p2_high', 'p3_medium', 'p4_low']
const esPrioridad = (v: string | null | undefined): v is TicketPriority => !!v && (PRIORIDADES as readonly string[]).includes(v)
type TicketUrgency = 'critical' | 'high' | 'medium' | 'low'
type TicketImpact = 'enterprise' | 'department' | 'user' | 'minimal'

type CreateTicketForm = {
  ticket_type: TicketType
  title: string
  description: string
  priority: TicketPriority
  urgency: TicketUrgency
  impact: TicketImpact
  assigned_to_user_id?: string
  client_id?: string
  service_item_id?: string
}

type ModalProps = {
  onClose: () => void
  onCreated?: (ticket: SdTicket) => void
}

type CatalogService = { id: string | number; name: string }
type CatalogGroup = { name?: string; services?: CatalogService[] }
type ClientItem = { id: string | number; name?: string }

type DynamicField = SdCampoDinamico
/** Vista indexable de una opción de contexto: el campo dinámico elige el atributo por nombre. */
type ContextOption = { [k: string]: unknown; name?: string; code?: string }

type CreateTicketPayload = {
  ticket_type: TicketType
  title: string
  description: string
  priority: TicketPriority
  urgency: TicketUrgency
  impact: TicketImpact
  dynamic_fields: Record<string, unknown>
  assigned_to_user_id?: string
  client_id?: string
  service_item_id?: string
  requester_name?: string
  requester_email?: string
}

function getCreateTicketSchema(t: (key: string) => string) {
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

export default function CreateTicketModal({ onClose, onCreated }: ModalProps) {
  const traducir = useAppT()
  const t = useAppT() as (key: string) => string
  const idPrefix = useId()
  const qc = useQueryClient()
  const toast = useToast()

  const [form, setForm] = useState<CreateTicketForm>({
    ticket_type: 'incident', title: '', description: '',
    priority: 'p3_medium', urgency: 'medium', impact: 'user',
    assigned_to_user_id: '', client_id: '', service_item_id: '',
  })
  // Quien pide el ticket: sin correo seria el agente, y el cliente no
  // recibiria ningun aviso (auditoria 2026-11).
  const [solicitante, setSolicitante] = useState({ nombre: '', correo: '' })
  const { data: contactos = [] } = useQuery<{ id: string; full_name: string; email?: string | null }[]>({
    queryKey: ['client-contacts', form.client_id],
    queryFn: () => clientsApi.contacts(form.client_id).then(r => r.data as { id: string; full_name: string; email?: string | null }[]),
    enabled: !!form.client_id,
  })

  const { data: catalog = [] } = useQuery<CatalogGroup[]>({
    queryKey: ['sd-catalog'],
    queryFn: () => sdCatalogApi.list().then(r => r.data),
  })
  const { data: users = [] } = useListaDeUsuarios()
  const { data: clients = [] } = useQuery<ClientItem[]>({
    queryKey: ['clients'],
    queryFn: () => clientsApi.list({}).then(r => (r.data ?? []) as ClientItem[]),
  })
  const { data: dynamicFormRules } = useQuery({
    queryKey: ['sd-dynamic-forms'],
    queryFn: () => sdDynamicFormsApi.get().then(r => r.data),
  })
  // Incidencia 1 (23-11-2026): el historial y el asistente de campos son de
  // administración (`sd.administrar`); un operador que solo da de alta un
  // ticket no los pide (antes salía «Acceso denegado» al abrir el alta).
  const administraSd = usePermiso('sd.administrar')
  const { data: dynamicHistory = [] } = useQuery({
    queryKey: ['sd-dynamic-forms-history'],
    queryFn: () => sdDynamicFormsApi.history().then(r => r.data),
    enabled: administraSd,
    meta: { errorToast: false },
  })
  const { data: contextOptions = { clients: [], services: [], cis: [] } } = useQuery({
    queryKey: ['sd-dynamic-forms-context', form.client_id, form.service_item_id],
    queryFn: () => sdDynamicFormsApi.contextOptions({
      client_id: form.client_id || undefined,
      service_item_id: form.service_item_id || undefined,
      limit: DYNAMIC_FORM_OPTIONS_LIMIT,
    }).then(r => r.data),
  })
  const [dynamicValues, setDynamicValues] = useState<Record<string, unknown>>({})
  const [wizardOpen, setWizardOpen] = useState(false)
  const [wizardStep, setWizardStep] = useState(1)
  const [csvText, setCsvText] = useState('')
  const [generatedFields, setGeneratedFields] = useState<SdCampoDinamico[]>([])
  const validation = useFormValidation(getCreateTicketSchema(t))
  const campos = useErroresDeCampo()

  const suggestedPrio = useMemo<TicketPriority>(() => {
    const matrix: Record<string, TicketPriority> = {
      critical_enterprise: 'p1_critical', critical_department: 'p1_critical', critical_user: 'p2_high',
      high_enterprise: 'p1_critical', high_department: 'p2_high', high_user: 'p2_high',
      medium_enterprise: 'p2_high', medium_department: 'p3_medium', medium_user: 'p3_medium',
      low_enterprise: 'p3_medium', low_department: 'p4_low', low_user: 'p4_low',
    }
    return matrix[`${form.urgency}_${form.impact}`] ?? 'p3_medium'
  }, [form.urgency, form.impact])

  const set = <K extends keyof CreateTicketForm>(k: K) => (e: { target: { value: string } }) => {
    setForm(f => ({ ...f, [k]: e.target.value }))
    validation.clearFieldError(k)
    campos.limpiar(k)
  }

  const visibleDynamicFields = useMemo<DynamicField[]>(() => {
    const fields = dynamicFormRules?.fields || []
    const source = { ...form, ...dynamicValues }
    return fields.filter((f) => {
      const cond = f?.visible_when
      if (!cond || !cond.field) return true
      const current = source[cond.field as keyof typeof source]
      if (Object.prototype.hasOwnProperty.call(cond, 'equals')) return current === cond.equals
      if (Array.isArray(cond.in)) return cond.in.includes(current)
      return true
    })
  }, [dynamicFormRules, form, dynamicValues])

  useEffect(() => {
    const visibleIds = new Set(visibleDynamicFields.map(f => f.id))
    setDynamicValues((prev) => {
      let changed = false
      const next: Record<string, unknown> = {}
      for (const [k, v] of Object.entries(prev)) {
        if (visibleIds.has(k)) next[k] = v
        else changed = true
      }
      return changed ? next : prev
    })
  }, [visibleDynamicFields])

  const routingHint = useMemo<Record<string, unknown> | null>(() => {
    const hints = dynamicFormRules?.routing_hints || []
    for (const h of hints) {
      const w = h?.when || {}
      if (!w.field) continue
      const current = form[w.field as keyof CreateTicketForm]
      if ((Object.prototype.hasOwnProperty.call(w, 'equals') && current === w.equals) ||
          (Array.isArray(w.in) && w.in.includes(current))) {
        return h?.set || null
      }
    }
    return null
  }, [dynamicFormRules, form])

  const buildPayload = (raw: z.infer<ReturnType<typeof getCreateTicketSchema>>): CreateTicketPayload => {
    const dynamicPayload = Object.fromEntries(
      Object.entries(dynamicValues).filter(([, v]) => (v ?? '').toString().trim() !== '')
    )

    const payload: CreateTicketPayload = {
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
    if (solicitante.correo.trim()) {
      payload.requester_email = solicitante.correo.trim()
      payload.requester_name = solicitante.nombre.trim() || solicitante.correo.trim()
    }
    return payload
  }

  const { mutate, isPending } = useMutation({
    mutationFn: (data: CreateTicketPayload) => ticketsApi.create(data),
    onMutate: () => campos.limpiar(),
    onSuccess: res => {
      validation.setErrors({})
      qc.invalidateQueries({ queryKey: ['sd-tickets'] })
      toast.success(`${t('service_desk.ticket_created_success')} ${res.data.number}`)
      onCreated?.(res.data)
      onClose()
    },
    onError: e => { if (!campos.recoger(e)) toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) },
  })

  const previewImport = useMutation({
    mutationFn: () => sdDynamicFormsApi.importPreview({ csv_text: csvText, mapping: {} }),
    onSuccess: res => {
      setGeneratedFields(res.data.generated_fields)
      setWizardStep(2)
    },
    onError: (e) => toast.error(extractErr(e, traducir('createticket.error_previsualizar'))),
  })

  const applyImport = useMutation({
    mutationFn: () => sdDynamicFormsApi.importApply({ generated_fields: generatedFields, merge_mode: 'upsert' }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sd-dynamic-forms'] })
      qc.invalidateQueries({ queryKey: ['sd-dynamic-forms-history'] })
      toast.success(traducir('createticket.campos_dinamicos_importados'))
      setWizardOpen(false)
      setWizardStep(1)
      setCsvText('')
      setGeneratedFields([])
    },
    onError: (e) => toast.error(extractErr(e, traducir('createticket.error_aplicar'))),
  })

  const rollbackConfig = useMutation({
    mutationFn: (snapshotId: string) => sdDynamicFormsApi.rollback(snapshotId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sd-dynamic-forms'] })
      qc.invalidateQueries({ queryKey: ['sd-dynamic-forms-history'] })
      toast.success(traducir('createticket.configuracion_restaurada'))
    },
    onError: (e) => toast.error(extractErr(e, traducir('createticket.error_restaurar'))),
  })


  const contextSuggestionsForField = (f: DynamicField): string[] => {
    const source = f?.data_source || (f?.type || '').replace('context_', '')
    const filas: ContextOption[] | null = source === 'ci' ? contextOptions.cis
      : source === 'service' ? contextOptions.services
      : source === 'client' ? contextOptions.clients
      : null
    if (!filas) return []
    const attr = (f?.data_attribute || 'name').toLowerCase()
    return filas.map((o) => String(o[attr] || o.name || o.code || ''))
  }

  /** Nombre legible de un campo del formulario (para la pista de enrutado). */
  const etiquetaDeCampo = (k: string) => ({
    ticket_type: t('service_desk.ticket_type'), priority: t('service_desk.ticket_priority'),
    urgency: t('service_desk.edit_urgency'), impact: t('service_desk.edit_impact'),
    assigned_group_id: t('service_desk.assigned_group'), assigned_to_user_id: t('common.assigned_to'),
    support_level: t('service_desk.support_level'), queue: t('sd_campos_dinamicos.cola'),
  } as Record<string, string>)[k] ?? k

  /** Valor legible de la pista de enrutado (incidencia 3): nunca la clave cruda. */
  const valorDePista = (k: string, v: unknown) => valorDePistaDeEnrutado(t, k, v, {
    priority: PRIORITY_LABEL,
    ticket_type: {
      incident: t('service_desk.type_incident'), service_request: t('service_desk.type_service_request'),
      change: t('service_desk.type_change'), problem: t('service_desk.type_problem'), question: t('service_desk.type_question'),
    },
  })

  const submit = () => {
    const result = validation.validateForm(form)
    if (!result.success) return
    mutate(buildPayload(result.data))
  }

  return (
    <Modal open title={t('service_desk.new_ticket')} onClose={onClose} size="lg">
      <div className="crtimo-grid-1">
        <div>
          <Select label={<>{t('service_desk.ticket_type')}*</>} placeholder={false} id={`${idPrefix}-ticket-type`} value={form.ticket_type} onChange={set('ticket_type')} aria-invalid={!!validation.errors.ticket_type}>
            {[['incident', t('service_desk.type_incident')], ['service_request', t('service_desk.type_service_request')],
              ['change', t('service_desk.type_change')], ['problem', t('service_desk.type_problem')], ['question', t('service_desk.type_question')]
            ].map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </Select>
          {(validation.errors.ticket_type ?? campos.de('ticket_type')) && <div className="u-field-error">{validation.errors.ticket_type ?? campos.de('ticket_type')}</div>}
        </div>
        <div>
          <Select label={traducir('createticket.servicio')} placeholder={false} id={`${idPrefix}-service-item`} value={form.service_item_id} onChange={set('service_item_id')}>
            <option value="">{t('service_desk.ticket_no_service')}</option>
            {catalog.flatMap(cat => cat.services?.map(s => (
              <option key={s.id} value={String(s.id)}>{cat.name} → {s.name}</option>
            )) || [])}
          </Select>
          {campos.de('service_item_id') && <div className="u-field-error">{campos.de('service_item_id')}</div>}
        </div>
        <div className="u-col-full">
          <CatalogoInteligente texto={`${form.title} ${form.description}`.trim()} servicioId={form.service_item_id}
            onElegir={id => setForm(f => ({ ...f, service_item_id: id }))}
            onRellenar={r => setForm(f => ({
              ...f,
              title: f.title || r.suggested_title || '',
              priority: esPrioridad(r.suggested_priority) ? r.suggested_priority : f.priority,
            }))} />
        </div>
        <div className="u-col-full">
          <Input label={<>{t('service_desk.ticket_title')} *</>} id={`${idPrefix}-title`} value={form.title} onChange={set('title')} placeholder={t('service_desk.ticket_title')} />
          {(validation.errors.title ?? campos.de('title')) && <div className="u-field-error">{validation.errors.title ?? campos.de('title')}</div>}
        </div>
        <div className="u-col-full">
          <label htmlFor={`${idPrefix}-description`} className="campo-etiqueta">{t('common.description')} *</label>
          <AIInlineEditor
            inputId={`${idPrefix}-description`}
            ariaLabel={t('common.description')}
            placeholder={t('common.description')}
            disabled={isPending}
            value={form.description}
            onChange={val => set('description')({ target: { value: val } })}
            rows={4}
            className={validation.inputClass('campo-form create-ticket-modal-vertical', 'description')}
          />
          {(validation.errors.description ?? campos.de('description')) && <div className="u-field-error">{validation.errors.description ?? campos.de('description')}</div>}
        </div>

        <div>
          <Select label={t('service_desk.edit_urgency')} placeholder={false} id={`${idPrefix}-urgency`} value={form.urgency} onChange={set('urgency')} aria-invalid={!!validation.errors.urgency}>
            {[['critical', t('service_desk.urgency_critical')], ['high', t('service_desk.urgency_high')],
              ['medium', t('service_desk.urgency_medium')], ['low', t('service_desk.urgency_low')]
            ].map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </Select>
          {(validation.errors.urgency ?? campos.de('urgency')) && <div className="u-field-error">{validation.errors.urgency ?? campos.de('urgency')}</div>}
        </div>
        <div>
          <Select label={t('service_desk.edit_impact')} placeholder={false} id={`${idPrefix}-impact`} value={form.impact} onChange={set('impact')} aria-invalid={!!validation.errors.impact}>
            {[['enterprise', t('service_desk.impact_enterprise')], ['department', t('service_desk.impact_department')],
              ['user', t('service_desk.impact_user')], ['minimal', t('service_desk.impact_minimal')]
            ].map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </Select>
          {(validation.errors.impact ?? campos.de('impact')) && <div className="u-field-error">{validation.errors.impact ?? campos.de('impact')}</div>}
        </div>

        <div className="crtimo-row-1">
          <div className="crtimo-sugerida">
            <span className="u-text2-sm">{traducir('createticket.prioridad_sugerida')}</span>
            <PBadge v={suggestedPrio} />
            {form.priority !== suggestedPrio && (
              <Button size="xs" variant="secondary" icon={<Sparkles size={12} />} onClick={() => setForm(f => ({ ...f, priority: suggestedPrio }))}>
                {traducir('createticket.aplicar_sugerida')}
              </Button>
            )}
          </div>
          <div className="crtimo-prioridad">
            <Select label={t('service_desk.ticket_priority')} placeholder={false} id={`${idPrefix}-priority`} value={form.priority} onChange={set('priority')} aria-invalid={!!validation.errors.priority}>
              {['p1_critical', 'p2_high', 'p3_medium', 'p4_low'].map(p =>
                <option key={p} value={p}>{PRIORITY_LABEL[p]}</option>)}
            </Select>
          {campos.de('priority') && <div className="u-field-error">{campos.de('priority')}</div>}
          </div>
        </div>

        {routingHint && (
          <div className="crtimo-box-2">
            {traducir('createticketmodal.hint_de_routing_aplicado')} {Object.entries(routingHint).map(([k, v]) => `${etiquetaDeCampo(k)}: ${valorDePista(k, v)}`).join(' · ')}
          </div>
        )}

        {visibleDynamicFields.map((f) => (
          <div key={f.id} className={`${f.type === 'textarea' ? 'create-ticket-modal-m1' : 'create-ticket-modal-m2'}`}>
            <label id={`${idPrefix}-${f.id}-et`} htmlFor={`${idPrefix}-${f.id}`} className="campo-etiqueta">{etiquetaDeCampoDinamico(t, f)}{f.required ? ' *' : ''}</label>
            {f.type === 'select' ? (
              <Select
                suelto
                placeholder={false}
                id={`${idPrefix}-${f.id}`}
                value={String(dynamicValues[f.id] ?? '')}
                onChange={(e) => setDynamicValues(v => ({ ...v, [f.id]: e.target.value }))}
                className="campo-form"
              >
                <option value="">{t('sd_campos_dinamicos.seleccionar')}</option>
                {(f.options || []).map((op) => <option key={op} value={op}>{etiquetaDeOpcionDinamica(t, op)}</option>)}
              </Select>
            ) : f.type === 'textarea' ? (
              <Textarea id={`${idPrefix}-${f.id}`} aria-labelledby={`${idPrefix}-${f.id}-et`} value={String(dynamicValues[f.id] ?? '')} onChange={(e) => setDynamicValues(v => ({ ...v, [f.id]: e.target.value }))} className="create-ticket-modal-notas" />
            ) : (f.type || '').startsWith('context_') ? (
              <>
                <Input id={`${idPrefix}-${f.id}`} aria-labelledby={`${idPrefix}-${f.id}-et`} type="text" list={`${idPrefix}-${f.id}-options`} value={String(dynamicValues[f.id] ?? '')} onChange={(e) => setDynamicValues(v => ({ ...v, [f.id]: e.target.value }))} />
                <datalist id={`${idPrefix}-${f.id}-options`}>
                  {contextSuggestionsForField(f).map((op, idx) => <option key={`${f.id}-${idx}`} value={op} aria-label={op} />)}
                </datalist>
              </>
            ) : (
              f.type === 'date' ? (
                <DateInput
                  id={`${idPrefix}-${f.id}`}
                  aria-labelledby={`${idPrefix}-${f.id}-et`}
                  value={String(dynamicValues[f.id] ?? '')}
                  onChange={(e) => setDynamicValues(v => ({ ...v, [f.id]: e.target.value }))}
                  className="campo-form"
                />
              ) : (
                <Input id={`${idPrefix}-${f.id}`} aria-labelledby={`${idPrefix}-${f.id}-et`} type="text" value={String(dynamicValues[f.id] ?? '')} onChange={(e) => setDynamicValues(v => ({ ...v, [f.id]: e.target.value }))} />
              )
            )}
          </div>
        ))}

        <div>
          <Select label={t('common.assigned_to')} placeholder={false} id={`${idPrefix}-assigned-to`} value={form.assigned_to_user_id} onChange={set('assigned_to_user_id')}>
            <option value="">{t('service_desk.ticket_auto_routing')}</option>
            {users.map(u => <option key={u.id} value={String(u.id)}>{u.full_name}</option>)}
          </Select>
          {campos.de('assigned_to_user_id') && <div className="u-field-error">{campos.de('assigned_to_user_id')}</div>}
        </div>
        <div>
          <Select label={traducir('createticket.cliente')} placeholder={false} id={`${idPrefix}-client`} value={form.client_id} onChange={set('client_id')}>
            <option value="">{t('service_desk.ticket_no_client')}</option>
            {clients.map(c =>
              <option key={c.id} value={String(c.id)}>{c.name}</option>)}
          </Select>
          {campos.de('client_id') && <div className="u-field-error">{campos.de('client_id')}</div>}
        </div>
        {form.client_id && contactos.length > 0 && (
          <Select label={traducir('sd_cfg.req_contact')} placeholder={false} id={`${idPrefix}-contact`} aria-label={traducir('sd_cfg.req_contact')}
              value={contactos.find(x => x.full_name === solicitante.nombre && (x.email ?? '') === solicitante.correo)?.id ?? ''}
              onChange={e => { const c = contactos.find(x => x.id === e.target.value); if (c) setSolicitante({ nombre: c.full_name, correo: c.email ?? '' }) }}>
              <option value="">{traducir('sd_cfg.req_contact_none')}</option>
              {contactos.map(c => <option key={c.id} value={c.id}>{c.full_name}{c.email ? ` · ${c.email}` : ''}</option>)}
            </Select>
        )}
        <div>
          <Input label={traducir('sd_cfg.req_name')} id={`${idPrefix}-req-name`} aria-label={traducir('sd_cfg.req_name')} value={solicitante.nombre} onChange={e => { campos.limpiar('requester_name'); setSolicitante(s => ({ ...s, nombre: e.target.value })) }} />
          {campos.de('requester_name') && <div className="u-field-error">{campos.de('requester_name')}</div>}
        </div>
        <div>
          <Input label={traducir('sd_cfg.req_email')} id={`${idPrefix}-req-email`} aria-label={traducir('sd_cfg.req_email')} type="email" value={solicitante.correo} onChange={e => { campos.limpiar('requester_email'); setSolicitante(s => ({ ...s, correo: e.target.value })) }} />
          {campos.de('requester_email') && <div className="u-field-error">{campos.de('requester_email')}</div>}
        </div>
        {!solicitante.correo.trim() && (
          <div className="crtimo-box-3">{traducir('sd_cfg.req_hint')}</div>
        )}

        <div className="crtimo-row-2">
          {administraSd && <Button variant="secondary" onClick={() => setWizardOpen(true)}>{t('createticket.wizard_campos')}</Button>}
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={submit} disabled={isPending} loading={isPending}>
            {t('service_desk.ticket_create_btn')}
          </Button>
        </div>
      </div>

      <Modal open={administraSd && wizardOpen} onClose={() => setWizardOpen(false)} title={traducir('createticketmodal.wizard_de_campos_dinamicos')} size="lg">
        {wizardStep === 1 && (
          <div className="crtimo-grid-2">
            <div className="u-text2-sm">
              {traducir('createticketmodal.pega_csv_con_cabeceras_para_generar_campos')}
            </div>
            <Textarea aria-label={traducir('createticketmodal.pega_csv_con_cabeceras_para_generar_campos')} value={csvText} onChange={(e) => setCsvText(e.target.value)} placeholder={'campo_a,campo_b\nvalor1,valor2'} inputClassName="campo-form create-ticket-modal-extenso" />
            <div className="crtimo-row-3">
              <div className="u-text3-xs">{traducir('createticketmodal.tambien_puedes_restaurar_snapshots_previos')}</div>
              <Button onClick={() => previewImport.mutate()} disabled={!csvText.trim()} loading={previewImport.isPending}>{traducir('dataplatform.previsualizar')}</Button>
            </div>
            <div className="crtimo-grid-3">
              {dynamicHistory.slice(0, 5).map((h) => (
                <div key={h.snapshot_id} className="crtimo-row-4">
                  <div className="u-text2-xs">
                    {fmtDateTime(h.created_at)}{h.reason ? ` · ${h.reason}` : ''}
                  </div>
                  <Button variant="secondary" onClick={() => rollbackConfig.mutate(h.snapshot_id)} loading={rollbackConfig.isPending}>{traducir('wiki.restaurar')}</Button>
                </div>
              ))}
            </div>
          </div>
        )}

        {wizardStep === 2 && (
          <div className="crtimo-grid-4">
            <div className="u-text2-sm">{traducir('createticketmodal.previsualizacion_de_campos_detectados')}</div>
            <div className="crtimo-box-4">
              {generatedFields.map((f, idx) => (
                <div key={`${f.id}-${idx}`} className="crtimo-grid-5">
                  <Input aria-label={traducir('createticket.etiqueta_campo_n', { n: idx + 1 })} value={f.label || ''} onChange={(e) => {
                    const v = [...generatedFields]
                    v[idx] = { ...v[idx], label: e.target.value }
                    setGeneratedFields(v)
                  }} inputClassName="campo-form" />
                  <Select suelto placeholder={false} aria-label={traducir('createticket.tipo_campo_n', { n: idx + 1 })} value={f.type || 'text'} onChange={(e) => {
                    const v = [...generatedFields]
                    v[idx] = { ...v[idx], type: e.target.value }
                    setGeneratedFields(v)
                  }} className="campo-form">
                    <option value="text">{traducir('createticket.tipo_text')}</option>
                    <option value="textarea">{traducir('createticket.tipo_textarea')}</option>
                    <option value="select">{traducir('createticket.tipo_select')}</option>
                    <option value="date">{traducir('createticket.tipo_date')}</option>
                  </Select>
                  <Input aria-label={traducir('createticket.id_campo_n', { n: idx + 1 })} value={f.id || ''} onChange={(e) => {
                    const v = [...generatedFields]
                    v[idx] = { ...v[idx], id: e.target.value }
                    setGeneratedFields(v)
                  }} inputClassName="campo-form" />
                </div>
              ))}
            </div>
            <div className="crtimo-row-5">
              <Button variant="secondary" onClick={() => setWizardStep(1)}>{traducir('createticketmodal.atras')}</Button>
              <Button onClick={() => applyImport.mutate()} loading={applyImport.isPending}>{traducir('createticketmodal.aplicar_importacion')}</Button>
            </div>
          </div>
        )}
      </Modal>
    </Modal>
  )
}
