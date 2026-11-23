/**
 * ChatAdminPage — administración collaboration (mockup 6.3 del documento).
 *
 * Tabs: Retención · Legal Hold · Moderación · Integraciones · Auditoría · Webhooks · eDiscovery
 */
import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ShieldCheck, Scale, Plug, ScrollText, Webhook, Search, Plus, RefreshCcw, X, Download, ClipboardCopy,
  type LucideIcon,
} from 'lucide-react'
import { useToast } from '../context/ToastContext'
import { collabApi } from '../services/collaborationApi'
import { apiUrl } from '../services/api'
import { useAppT } from '../i18n/AppLangContext'
import { Table, Pulsable, Select, Tabs, Input, Textarea, Spinner, EstadoDeError } from '../components/ui'
import DateInput from '../components/ui/DateInput'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { POLL_FREQUENT_MS } from '../constants/timings'
import { CHAT_AUDIT_LIMIT } from '../constants/pagination'
import { fmtDate, fmtDateTime } from '../utils/helpers'
import { usePropuestas } from '../hooks/useOrgSettings'
import { RuntimeGroupEditor, CLAVE_RETENCION_PROPUESTA_CHAT } from './settings-sections/SettingsAdvancedSections'
import './ChatAdminPage.css'

type TabId = 'retention' | 'legal_hold' | 'integrations' | 'webhooks' | 'audit' | 'ediscovery'
type ButtonVariant = 'primary' | 'secondary' | 'danger'

type RetentionScope = 'workspace' | 'team' | 'channel'
type RetentionApplyTo = 'all' | 'messages' | 'attachments' | 'calls'
type IntegrationKind = 'jira' | 'github' | 'gitlab' | 'google_calendar' | 'microsoft_365' | 'service_desk' | 'nexus_ai' | 'custom_webhook'
type WebhookDirection = 'incoming' | 'outgoing'

type RetentionPolicy = {
  id: string | number
  name: string
  scope: RetentionScope | string
  apply_to: RetentionApplyTo | string
  retention_months: number
  is_active?: boolean
}

type LegalHoldCase = {
  id: string | number
  case_reference: string
  description?: string
  is_active?: boolean
  started_at?: string
  ended_at?: string
}

type IntegrationItem = {
  id: string | number
  kind?: string
  name?: string
  is_enabled?: boolean
}

type WebhookItem = {
  id: string | number
  direction?: WebhookDirection | string
  name?: string
  url?: string
  secret_token?: string
  events?: string[]
}

type AuditEventItem = {
  id: string | number
  created_at?: string
  action?: string
  entity_type?: string
  entity_id?: string
  actor_user_id?: string
}

type AuditVerifyResult = {
  is_valid?: boolean
  total?: number
  chains?: number
  breaks?: unknown[]
}

type EdiscoveryExportResult = {
  total?: number
  [key: string]: unknown
}

type RetentionFormState = {
  name: string
  scope: RetentionScope
  retention_months: number
  apply_to: RetentionApplyTo
}

type LegalHoldFormState = {
  case_reference: string
  description: string
  custodian_user_ids: string
  channel_ids: string
}

type IntegrationFormState = {
  kind: IntegrationKind
  name: string
  config: string
}

type WebhookFormState = {
  direction: WebhookDirection
  name: string
  url: string
  target_channel_id: string
  events: string
}

type EdiscoveryFormState = {
  case_reference: string
  user_ids: string
  keywords: string
  date_from: string
  date_to: string
}

export default function ChatAdminPage(): JSX.Element {
  const t = useAppT() as (key: string, params?: Record<string, unknown>) => string
  const [tab, setTab] = useState<TabId>('retention')

  const TABS: Array<{ id: TabId; label: string; icon: LucideIcon }> = [
    { id: 'retention', label: t('chat_admin.tab_retention'), icon: ShieldCheck },
    { id: 'legal_hold', label: t('chat_admin.tab_legal_hold'), icon: Scale },
    { id: 'integrations', label: t('chat_admin.tab_integrations'), icon: Plug },
    { id: 'webhooks', label: t('chat_admin.tab_webhooks'), icon: Webhook },
    { id: 'audit', label: t('chat_admin.tab_audit'), icon: ScrollText },
    { id: 'ediscovery', label: t('chat_admin.tab_ediscovery'), icon: Search },
  ]

  return (
    <div className="cadm-page">
      <h1 className="cadm-title">{t('chat_admin.title')}</h1>
      <p className="cadm-subtitle">{t('chat_admin.subtitle')}</p>

      <Tabs ariaLabel={t('chat_admin.title')} className="cadm-tabs" active={tab} onChange={id => setTab(id as TabId)}
        items={TABS.map(x => { const Icon = x.icon; return { id: x.id, label: x.label, icon: <Icon size={13} aria-hidden="true" /> } })} />

      {tab === 'retention' && <RetentionTab />}
      {tab === 'legal_hold' && <LegalHoldTab />}
      {tab === 'integrations' && <IntegrationsTab />}
      {tab === 'webhooks' && <WebhooksTab />}
      {tab === 'audit' && <AuditTab />}
      {tab === 'ediscovery' && <EdiscoveryTab />}
    </div>
  )
}

function Card({ children }: { children: ReactNode }) {
  return <div className="cadm-card">{children}</div>
}

function Btn({
  children,
  onClick,
  variant = 'primary',
  icon: Icon,
  disabled,
}: {
  children: ReactNode
  onClick?: () => void
  variant?: ButtonVariant
  icon?: LucideIcon
  disabled?: boolean
}) {
  return (
    <Pulsable type="button" onClick={onClick} disabled={disabled} className={`cadm-btn cadm-btn--${variant}`}>
      {Icon && <Icon size={13} aria-hidden="true" />} {children}
    </Pulsable>
  )
}

/** Campo con etiqueta asociada (el <label> envuelve al control). */
function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="cadm-field">
      <span className="cadm-field__label">{label}</span>
      {children}
    </label>
  )
}

const INPUT = 'cadm-input'

const SCOPE_KEYS: Record<string, string> = {
  workspace: 'chat_admin.scope_workspace', team: 'chat_admin.scope_team', channel: 'chat_admin.scope_channel',
}
const APPLY_KEYS: Record<string, string> = {
  all: 'chat_admin.apply_all', messages: 'chat_admin.apply_messages',
  attachments: 'chat_admin.apply_attachments', calls: 'chat_admin.apply_calls',
}

function RetentionTab() {
  const t = useAppT() as (key: string, params?: Record<string, unknown>) => string
  const qc = useQueryClient()
  const toast = useToast()
  const q = useQuery<RetentionPolicy[]>({ queryKey: ['retention'], queryFn: () => collabApi.listRetention() as Promise<RetentionPolicy[]> })
  const data = q.data ?? []
  // 19-11-2026: los meses propuestos son el ajuste de la empresa (CHAT_RETENTION_PROPOSED_MONTHS,
  // antes 24 fijos), que el servidor ya deja dentro del mínimo de retención y del tope del chat.
  const propuestos = usePropuestas().chat_retention_proposed_months
  const vacio = (): RetentionFormState => ({ name: '', scope: 'workspace', retention_months: propuestos, apply_to: 'all' })
  const [form, setForm] = useState<RetentionFormState>(vacio)
  const [tocado, setTocado] = useState(false)
  // El ajuste llega después del primer pintado: se aplica mientras no se haya tocado el campo.
  useEffect(() => { if (!tocado) setForm(f => ({ ...f, retention_months: propuestos })) }, [propuestos, tocado])

  const create = useMutation({
    mutationFn: () => collabApi.createRetention(form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['retention'] })
      toast.success(t('chat_admin.policy_created'))
      setForm(vacio())
      setTocado(false)
    },
  })
  const run = useMutation({
    mutationFn: () => collabApi.runRetention(),
    onSuccess: (d: { deleted?: number }) => toast.success(t('chat_admin.executed_purged', { deleted: d.deleted || 0 })),
  })

  return (
    <div className="cadm-split">
      <Card>
        <div className="cadm-card-head">
          <h3 className="cadm-h3">{t('chat_admin.retention_policies')}</h3>
          {/* 23-11-2026: la purga borra mensajes de forma irreversible: pide confirmación. */}
          <Btn variant="secondary" icon={RefreshCcw} onClick={() => openConfirmGlobal({
            title: t('chat_admin.confirm_purge_title'), message: t('chat_admin.confirm_purge_msg'),
            confirmLabel: t('chat_admin.run_sweep'), danger: true, onConfirm: () => run.mutate(),
          })}>{t('chat_admin.run_sweep')}</Btn>
        </div>
        {q.isLoading || q.isError ? <EstadoDeConsulta q={q} /> : data.length === 0 ? <Empty text={t('chat_admin.no_policies_hint')} /> : (
          <Table
            data={data}
            columns={[
              { key: 'name', label: t('chat_admin.col_name') },
              { key: 'scope', label: t('chat_admin.col_scope'), render: (_v, r) => SCOPE_KEYS[r.scope] ? t(SCOPE_KEYS[r.scope]) : r.scope },
              { key: 'apply_to', label: t('chat_admin.col_apply_to'), render: (_v, r) => APPLY_KEYS[r.apply_to] ? t(APPLY_KEYS[r.apply_to]) : r.apply_to },
              { key: 'retention_months', label: t('chat_admin.col_months') },
              { key: 'is_active', label: t('chat_admin.col_active'), render: (_v, r) => (r.is_active ? '✓' : '—') },
            ]}
          />
        )}
      </Card>
      <Card>
        <h4 className="cadm-h4">{t('chat_admin.new_policy')}</h4>
        <div className="u-stack-10">
          <Field label={t('chat_admin.col_name')}><Input aria-label={t('chat_admin.col_name')} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} inputClassName="cadm-input" /></Field>
          <Field label={t('chat_admin.col_scope')}>
            <Select suelto placeholder={false} className={INPUT} value={form.scope} onChange={(e) => setForm({ ...form, scope: e.target.value as RetentionScope })}>
              <option value="workspace">{t('chat_admin.scope_workspace')}</option>
              <option value="team">{t('chat_admin.scope_team')}</option>
              <option value="channel">{t('chat_admin.scope_channel')}</option>
            </Select>
          </Field>
          <Field label={t('chat_admin.col_apply_to')}>
            <Select suelto placeholder={false} className={INPUT} value={form.apply_to} onChange={(e) => setForm({ ...form, apply_to: e.target.value as RetentionApplyTo })}>
              <option value="all">{t('chat_admin.apply_all')}</option>
              <option value="messages">{t('chat_admin.apply_messages')}</option>
              <option value="attachments">{t('chat_admin.apply_attachments')}</option>
              <option value="calls">{t('chat_admin.apply_calls')}</option>
            </Select>
          </Field>
          <Field label={t('chat_admin.retention_months_label')}><Input aria-label={t('chat_admin.retention_months_label')} type="number" min={1} max={120} value={form.retention_months} onChange={(e) => { setTocado(true); setForm({ ...form, retention_months: parseInt(e.target.value, 10) || propuestos }) }} inputClassName="cadm-input" /></Field>
          <Btn icon={Plus} onClick={() => create.mutate()} disabled={!form.name}>{t('chat_admin.create_policy')}</Btn>
        </div>
        <RuntimeGroupEditor groupId="audit" solo={[CLAVE_RETENCION_PROPUESTA_CHAT]} />
      </Card>
    </div>
  )
}

function LegalHoldTab() {
  const t = useAppT() as (key: string, params?: Record<string, unknown>) => string
  const qc = useQueryClient()
  const toast = useToast()
  const q = useQuery<LegalHoldCase[]>({ queryKey: ['legal-holds'], queryFn: () => collabApi.listLegalHolds() as Promise<LegalHoldCase[]> })
  const data = q.data ?? []
  const [form, setForm] = useState<LegalHoldFormState>({ case_reference: '', description: '', custodian_user_ids: '', channel_ids: '' })
  const create = useMutation({
    mutationFn: () => collabApi.createLegalHold({
      case_reference: form.case_reference,
      description: form.description,
      custodian_user_ids: form.custodian_user_ids.split(',').map((s) => s.trim()).filter(Boolean),
      channel_ids: form.channel_ids.split(',').map((s) => s.trim()).filter(Boolean),
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['legal-holds'] })
      toast.success(t('chat_admin.hold_created'))
      setForm({ case_reference: '', description: '', custodian_user_ids: '', channel_ids: '' })
    },
  })
  const release = useMutation({
    mutationFn: (id: string | number) => collabApi.releaseLegalHold(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['legal-holds'] })
      toast.success(t('chat_admin.hold_released'))
    },
  })
  return (
    <div className="cadm-split">
      <Card>
        <h3 className="cadm-h3">{t('chat_admin.legal_hold_cases')} ({data.length})</h3>
        {q.isLoading || q.isError ? <EstadoDeConsulta q={q} /> : data.length === 0 ? <Empty text={t('chat_admin.no_holds')} /> : (
          <div className="u-stack-10">
            {data.map((h) => (
              <div key={h.id} className="cadm-item">
                <div className="u-row-between">
                  <div>
                    <div className="cadm-item__name">{h.case_reference}</div>
                    <div className="u-text3-xs">{h.description}</div>
                  </div>
                  {h.is_active && <Btn variant="danger" icon={X} onClick={() => openConfirmGlobal({
                    title: t('chat_admin.confirm_release_title'), message: t('chat_admin.confirm_release_msg', { case: h.case_reference }),
                    confirmLabel: t('chat_admin.release'), danger: true, onConfirm: () => release.mutate(h.id),
                  })}>{t('chat_admin.release')}</Btn>}
                </div>
                <div className="cadm-item__meta">
                  {t('chat_admin.started_label')}: {fmtDate(h.started_at)} {h.ended_at && `· ${t('chat_admin.closed_label')}: ${fmtDate(h.ended_at)}`}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
      <Card>
        <h4 className="cadm-h4">{t('chat_admin.new_case')}</h4>
        <div className="u-stack-10">
          <Field label={t('chat_admin.case_reference_label')}><Input aria-label={t('chat_admin.case_reference_label')} value={form.case_reference} onChange={(e) => setForm({ ...form, case_reference: e.target.value })} placeholder={t('chat_admin.case_reference_placeholder')} inputClassName="cadm-input" /></Field>
          <Field label={t('chat_admin.description_label')}><Textarea aria-label={t('chat_admin.description_label')} rows={2} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} inputClassName="cadm-input" /></Field>
          <Field label={t('chat_admin.custodians_label')}><Input aria-label={t('chat_admin.custodians_label')} value={form.custodian_user_ids} onChange={(e) => setForm({ ...form, custodian_user_ids: e.target.value })} inputClassName="cadm-input" /></Field>
          <Field label={t('chat_admin.channels_label')}><Input aria-label={t('chat_admin.channels_label')} value={form.channel_ids} onChange={(e) => setForm({ ...form, channel_ids: e.target.value })} inputClassName="cadm-input" /></Field>
          <Btn icon={Plus} onClick={() => create.mutate()} disabled={!form.case_reference}>{t('chat_admin.create_hold')}</Btn>
        </div>
      </Card>
    </div>
  )
}

function IntegrationsTab() {
  const t = useAppT() as (key: string, params?: Record<string, unknown>) => string
  const qc = useQueryClient()
  const toast = useToast()
  // 23-11-2026 (04 A8): clave propia; `['integrations']` la compartía con otras pantallas con otra forma de datos.
  const q = useQuery<IntegrationItem[]>({ queryKey: ['chat-admin', 'integraciones'], queryFn: () => collabApi.listIntegrations() as Promise<IntegrationItem[]> })
  const data = q.data ?? []
  const [form, setForm] = useState<IntegrationFormState>({ kind: 'jira', name: '', config: '{}' })
  const create = useMutation({
    mutationFn: () => collabApi.createIntegration({ kind: form.kind, name: form.name, config: tryJson(form.config) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['chat-admin', 'integraciones'] })
      toast.success(t('chat_admin.integration_created'))
    },
  })
  const remove = useMutation({
    mutationFn: (id: string | number) => collabApi.deleteIntegration(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['chat-admin', 'integraciones'] })
      toast.success(t('chat_admin.deleted'))
    },
  })
  return (
    <div className="cadm-split">
      <Card>
        <h3 className="cadm-h3">{t('chat_admin.integrations')} ({data.length})</h3>
        {q.isLoading || q.isError ? <EstadoDeConsulta q={q} /> : data.length === 0 ? <Empty text={t('chat_admin.no_integrations')} /> : (
          <div className="u-stack-10">
            {data.map((it) => (
              <div key={it.id} className="cadm-item cadm-item--row">
                <div>
                  <div className="cadm-item__name">{it.name}</div>
                  <div className="u-text3-xs">{it.kind}{!it.is_enabled && ` · ${t('chat_admin.disabled')}`}</div>
                </div>
                <Btn variant="danger" icon={X} onClick={() => openConfirmGlobal({
                  title: t('chat_admin.confirm_delete_integration_title'), message: t('chat_admin.confirm_delete_integration_msg', { name: it.name ?? '' }),
                  confirmLabel: t('chat_admin.delete'), danger: true, onConfirm: () => remove.mutate(it.id),
                })}>{t('chat_admin.delete')}</Btn>
              </div>
            ))}
          </div>
        )}
      </Card>
      <Card>
        <h4 className="cadm-h4">{t('chat_admin.connect_integration')}</h4>
        <div className="u-stack-10">
          <Field label={t('chat_admin.kind_label')}>
            <Select suelto placeholder={false} className={INPUT} value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value as IntegrationKind })}>
              <option value="jira">Jira</option>
              <option value="github">GitHub</option>
              <option value="gitlab">GitLab</option>
              <option value="google_calendar">Google Calendar</option>
              <option value="microsoft_365">Microsoft 365</option>
              <option value="service_desk">{t('chat_admin.integracion_service_desk')}</option>
              <option value="nexus_ai">Nexus AI</option>
              <option value="custom_webhook">{t('chat_admin.custom_webhook')}</option>
            </Select>
          </Field>
          <Field label={t('chat_admin.col_name')}><Input aria-label={t('chat_admin.col_name')} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} inputClassName="cadm-input" /></Field>
          <Field label={t('chat_admin.config_json_label')}><Textarea aria-label={t('chat_admin.config_json_label')} rows={3} value={form.config} onChange={(e) => setForm({ ...form, config: e.target.value })} inputClassName="cadm-input" /></Field>
          <Btn icon={Plus} onClick={() => create.mutate()} disabled={!form.name}>{t('chat_admin.create')}</Btn>
        </div>
      </Card>
    </div>
  )
}

function WebhooksTab() {
  const t = useAppT() as (key: string, params?: Record<string, unknown>) => string
  const qc = useQueryClient()
  const toast = useToast()
  // 23-11-2026: clave con prefijo de módulo (antes ['webhooks'], genérica; medido: sin colisión real).
  const q = useQuery<WebhookItem[]>({ queryKey: ['chat-admin', 'webhooks'], queryFn: () => collabApi.listWebhooks() as Promise<WebhookItem[]> })
  const data = q.data ?? []
  // El secreto solo llega entero en la respuesta del alta: se enseña una vez y no se guarda.
  const [recienCreado, setRecienCreado] = useState<WebhookItem | null>(null)
  const copiar = (texto: string) => navigator.clipboard.writeText(texto)
    .then(() => toast.success(t('chat_admin.webhook_copiado')), () => toast.error(t('chat_admin.webhook_error_copiar')))
  const [form, setForm] = useState<WebhookFormState>({ direction: 'incoming', name: '', url: '', target_channel_id: '', events: '' })
  const create = useMutation({
    mutationFn: () => collabApi.createWebhook({
      direction: form.direction,
      name: form.name,
      url: form.url || null,
      target_channel_id: form.target_channel_id || null,
      events: form.events.split(',').map((s) => s.trim()).filter(Boolean),
    }),
    onSuccess: (creado) => {
      setRecienCreado(creado as WebhookItem)
      qc.invalidateQueries({ queryKey: ['chat-admin', 'webhooks'] })
      toast.success(t('chat_admin.webhook_created'))
    },
  })
  return (
    <div className="cadm-split">
      <Card>
        <h3 className="cadm-h3">{t('chat_admin.tab_webhooks')} ({data.length})</h3>
        {recienCreado?.secret_token && (
          <div className="cadm-secreto" role="status">
            <div className="cadm-item__name">{t('chat_admin.webhook_secreto_una_vez', { nombre: recienCreado.name ?? '' })}</div>
            <code className="cadm-item__url">{`POST ${apiUrl(`/collaboration/webhooks/incoming/${recienCreado.secret_token}`)}`}</code>
            <div className="u-row-center-6">
              <Btn icon={ClipboardCopy} onClick={() => copiar(apiUrl(`/collaboration/webhooks/incoming/${recienCreado.secret_token}`))}>{t('chat_admin.webhook_copiar_url')}</Btn>
              <Btn icon={X} onClick={() => setRecienCreado(null)}>{t('chat_admin.webhook_ya_lo_guarde')}</Btn>
            </div>
          </div>
        )}
        {q.isLoading || q.isError ? <EstadoDeConsulta q={q} /> : data.length === 0 ? <Empty text={t('chat_admin.no_webhooks')} /> : (
          <div className="u-stack-10">
            {data.map((w) => (
              <div key={w.id} className="cadm-item">
                <div className="cadm-item__name">{w.name} <span className="u-text3-xs">({w.direction === 'incoming' ? t('chat_admin.direction_in_short') : w.direction === 'outgoing' ? t('chat_admin.direction_out_short') : w.direction})</span></div>
                <div className="cadm-item__url">
                  {w.direction === 'incoming'
                    ? `POST ${apiUrl('/collaboration/webhooks/incoming/')}${w.secret_token ?? '••••'} · ${t('chat_admin.webhook_secreto_oculto')}`
                    : (w.url || '—')}
                </div>
                <div className="u-hint">
                  {t('chat_admin.events_label')}: {w.events?.join(', ') || '—'}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
      <Card>
        <h4 className="cadm-h4">{t('chat_admin.new_webhook')}</h4>
        <div className="u-stack-10">
          <Field label={t('chat_admin.direction_label')}>
            <Select suelto placeholder={false} className={INPUT} value={form.direction} onChange={(e) => setForm({ ...form, direction: e.target.value as WebhookDirection })}>
              <option value="incoming">{t('chat_admin.direction_incoming')}</option>
              {/* Auditoría 22-11-2026: los salientes del chat no se entregaban; se retiran
                  (los avisos a URL externa: Integraciones → Webhooks de la empresa). */}
            </Select>
          </Field>
          <Field label={t('chat_admin.col_name')}><Input aria-label={t('chat_admin.col_name')} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} inputClassName="cadm-input" /></Field>
          {form.direction === 'outgoing' && <Field label={t('chat_admin.target_url_label')}><Input aria-label={t('chat_admin.target_url_label')} value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} inputClassName="cadm-input" /></Field>}
          <Field label={t('chat_admin.target_channel_label')}><Input aria-label={t('chat_admin.target_channel_label')} value={form.target_channel_id} onChange={(e) => setForm({ ...form, target_channel_id: e.target.value })} inputClassName="cadm-input" /></Field>
          <Field label={t('chat_admin.events_input_label')}><Input aria-label={t('chat_admin.events_input_label')} value={form.events} onChange={(e) => setForm({ ...form, events: e.target.value })} placeholder="message.created,channel.created" inputClassName="cadm-input" /></Field>
          <Btn icon={Plus} onClick={() => create.mutate()} disabled={!form.name}>{t('chat_admin.create')}</Btn>
        </div>
      </Card>
    </div>
  )
}

function AuditTab() {
  const t = useAppT() as (key: string, params?: Record<string, unknown>) => string
  const q = useQuery<AuditEventItem[]>({ queryKey: ['chat-admin', 'auditoria'], queryFn: () => collabApi.listAudit(CHAT_AUDIT_LIMIT) as Promise<AuditEventItem[]>, refetchInterval: POLL_FREQUENT_MS })
  const data = q.data ?? []
  const verify = useMutation<AuditVerifyResult>({
    mutationFn: () => collabApi.verifyAudit() as Promise<AuditVerifyResult>,
  })
  return (
    <Card>
      <div className="cadm-card-head">
        <h3 className="cadm-h3">{t('chat_admin.audit_events')} ({data.length})</h3>
        <Btn variant="secondary" icon={ShieldCheck} onClick={() => verify.mutate()}>{t('chat_admin.verify_chain')}</Btn>
      </div>
      {verify.data && (
        <div role="status" className={`cadm-verify ${verify.data.is_valid ? 'cadm-verify--ok' : 'cadm-verify--broken'}`}>
          {verify.data.is_valid
            ? t('chat_admin.chain_ok', { total: verify.data.total || 0, chains: verify.data.chains || 0 })
            : t('chat_admin.chain_broken', { breaks: verify.data.breaks?.length || 0 })}
        </div>
      )}
      {q.isLoading || q.isError ? <EstadoDeConsulta q={q} /> : <Table
        data={data}
        columns={[
          { key: 'created_at', label: t('chat_admin.col_date'), render: (_v, e) => <span className="cadm-mono-xs">{fmtDateTime(e.created_at)}</span> },
          { key: 'action', label: t('chat_admin.col_action') },
          { key: 'entity_type', label: t('chat_admin.col_type') },
          { key: 'entity_id', label: t('chat_admin.col_entity'), render: (_v, e) => <span className="ds-codigo cadm-mono-xs" title={e.entity_id}>{e.entity_id?.slice(0, 8) || '—'}</span> },
          { key: 'actor_user_id', label: t('chat_admin.col_actor'), render: (_v, e) => <span className="u-xs" title={e.actor_user_id}>{e.actor_user_id?.slice(0, 8) || '—'}</span> },
        ]}
      />}
    </Card>
  )
}

function EdiscoveryTab() {
  const t = useAppT() as (key: string, params?: Record<string, unknown>) => string
  const toast = useToast()
  const [form, setForm] = useState<EdiscoveryFormState>({ case_reference: '', user_ids: '', keywords: '', date_from: '', date_to: '' })
  const exp = useMutation<EdiscoveryExportResult>({
    mutationFn: () => collabApi.ediscoveryExport({
      case_reference: form.case_reference || null,
      user_ids: form.user_ids.split(',').map((s) => s.trim()).filter(Boolean),
      keywords: form.keywords.split(',').map((s) => s.trim()).filter(Boolean),
      date_from: form.date_from || null,
      date_to: form.date_to || null,
      include_attachments: true,
    }) as Promise<EdiscoveryExportResult>,
    onSuccess: (data) => {
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = `ediscovery_${form.case_reference || 'export'}_${Date.now()}.json`
      a.click()
      URL.revokeObjectURL(a.href)
      toast.success(t('chat_admin.exported_messages', { total: data.total || 0 }))
    },
  })
  return (
    <Card>
      <h3 className="cadm-h3">{t('chat_admin.ediscovery_title')}</h3>
      <div className="cadm-form-grid">
        <Field label={t('chat_admin.case_short_label')}><Input aria-label={t('chat_admin.case_short_label')} value={form.case_reference} onChange={(e) => setForm({ ...form, case_reference: e.target.value })} inputClassName="cadm-input" /></Field>
        <Field label={t('chat_admin.custodians_label')}><Input aria-label={t('chat_admin.custodians_label')} value={form.user_ids} onChange={(e) => setForm({ ...form, user_ids: e.target.value })} inputClassName="cadm-input" /></Field>
        <Field label={t('chat_admin.keywords_label')}><Input aria-label={t('chat_admin.keywords_label')} value={form.keywords} onChange={(e) => setForm({ ...form, keywords: e.target.value })} inputClassName="cadm-input" /></Field>
        <div />
        <Field label={t('chat_admin.from_label')}><DateInput withTime className={INPUT} value={form.date_from} onChange={(e) => setForm({ ...form, date_from: e.target.value })} /></Field>
        <Field label={t('chat_admin.to_label')}><DateInput withTime className={INPUT} value={form.date_to} onChange={(e) => setForm({ ...form, date_to: e.target.value })} /></Field>
      </div>
      <Btn icon={Download} onClick={() => exp.mutate()} disabled={exp.isPending}>{exp.isPending ? t('chat_admin.exporting') : t('chat_admin.export_json')}</Btn>
    </Card>
  )
}


function tryJson(s: string): Record<string, unknown> {
  try {
    return JSON.parse(s || '{}') as Record<string, unknown>
  } catch {
    return {}
  }
}

function Empty({ text }: { text: string }) {
  return <div className="cadm-empty">{text}</div>
}

/** Carga / error de una consulta (auditoría 23-11-2026, 04 A5: las 6 consultas no tenían ninguno de los dos). */
function EstadoDeConsulta({ q }: { q: { isLoading: boolean; isError: boolean; error: unknown; refetch: () => unknown } }) {
  if (q.isError) return <EstadoDeError error={q.error} onReintentar={() => { void q.refetch() }} />
  if (q.isLoading) return <Spinner />
  return null
}
