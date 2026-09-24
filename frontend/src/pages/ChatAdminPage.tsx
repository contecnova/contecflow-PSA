/**
 * ChatAdminPage — administración collaboration (mockup 6.3 del documento).
 *
 * Tabs: Retención · Legal Hold · Moderación · Integraciones · Auditoría · Webhooks · eDiscovery
 */
import { useState } from 'react'
import type { ComponentType, CSSProperties, ReactNode } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ShieldCheck, Scale, Plug, ScrollText, Webhook, Search, Plus, RefreshCcw, X, Download,
} from 'lucide-react'
import { useToast } from '../context/ToastContext'
import { collabApi } from '../services/collaborationApi'
import { useAppT } from '../i18n/AppLangContext'

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

  const TABS: Array<{ id: TabId; label: string; icon: ComponentType<any> }> = [
    { id: 'retention', label: t('chat_admin.tab_retention'), icon: ShieldCheck as ComponentType<any> },
    { id: 'legal_hold', label: t('chat_admin.tab_legal_hold'), icon: Scale as ComponentType<any> },
    { id: 'integrations', label: t('chat_admin.tab_integrations'), icon: Plug as ComponentType<any> },
    { id: 'webhooks', label: t('chat_admin.tab_webhooks'), icon: Webhook as ComponentType<any> },
    { id: 'audit', label: t('chat_admin.tab_audit'), icon: ScrollText as ComponentType<any> },
    { id: 'ediscovery', label: t('chat_admin.tab_ediscovery'), icon: Search as ComponentType<any> },
  ]

  return (
    <div style={{ padding: '20px 26px' }}>
      <h1 style={{ fontSize: 22, fontWeight: 800, margin: '0 0 6px' }}>{t('chat_admin.title')}</h1>
      <p style={{ color: 'var(--text-2)', margin: '0 0 18px', fontSize: 'var(--text-sm)' }}>{t('chat_admin.subtitle')}</p>

      <div role="tablist" style={{ display: 'flex', gap: 4, marginBottom: 22, borderBottom: '1px solid var(--surface-4)', flexWrap: 'wrap' }}>
        {TABS.map((tabItem) => {
          const Icon = tabItem.icon
          const active = tab === tabItem.id
          return (
            <button
              key={tabItem.id}
              role="tab"
              aria-selected={active}
              onClick={() => setTab(tabItem.id)}
              style={{
                background: 'transparent',
                border: 'none',
                borderBottom: `2px solid ${active ? 'var(--accent)' : 'transparent'}`,
                padding: '10px 14px',
                cursor: 'pointer',
                fontFamily: 'inherit',
                fontSize: 'var(--text-sm)',
                fontWeight: active ? 700 : 500,
                color: active ? 'var(--accent)' : 'var(--text-2)',
                display: 'inline-flex',
                alignItems: 'center',
                gap: 6,
              }}
            >
              <Icon size={13} /> {tabItem.label}
            </button>
          )
        })}
      </div>

      {tab === 'retention' && <RetentionTab />}
      {tab === 'legal_hold' && <LegalHoldTab />}
      {tab === 'integrations' && <IntegrationsTab />}
      {tab === 'webhooks' && <WebhooksTab />}
      {tab === 'audit' && <AuditTab />}
      {tab === 'ediscovery' && <EdiscoveryTab />}
    </div>
  )
}

function Card({ children, style = {} }: { children: ReactNode; style?: CSSProperties }) {
  return (
    <div
      style={{
        background: 'var(--surface-2)',
        border: '1px solid var(--surface-4)',
        borderRadius: 12,
        padding: 18,
        ...style,
      }}
    >
      {children}
    </div>
  )
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
  icon?: ComponentType<any>
  disabled?: boolean
}) {
  const v: Record<ButtonVariant, CSSProperties> = {
    primary: { background: 'var(--accent)', color: '#fff', border: '1px solid var(--accent)' },
    secondary: { background: 'var(--surface-3)', color: 'var(--text-1)', border: '1px solid var(--surface-4)' },
    danger: { background: 'rgba(239,68,68,0.12)', color: 'var(--danger)', border: '1px solid rgba(239,68,68,0.3)' },
  }
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        padding: '8px 14px',
        borderRadius: 8,
        fontFamily: 'inherit',
        fontSize: 'var(--text-sm)',
        fontWeight: 600,
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.5 : 1,
        ...v[variant],
      }}
    >
      {Icon && <Icon size={13} />} {children}
    </button>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <label style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{label}</label>
      {children}
    </div>
  )
}

const inputStyle: CSSProperties = {
  background: 'var(--surface-3)',
  border: '1px solid var(--surface-4)',
  borderRadius: 8,
  padding: '8px 10px',
  color: 'var(--text-1)',
  fontSize: 'var(--text-sm)',
  outline: 'none',
  fontFamily: 'inherit',
}

function RetentionTab() {
  const t = useAppT() as (key: string, params?: Record<string, unknown>) => string
  const qc = useQueryClient()
  const toast = useToast()
  const { data = [] } = useQuery<RetentionPolicy[]>({ queryKey: ['retention'], queryFn: () => collabApi.listRetention() as Promise<RetentionPolicy[]> })
  const [form, setForm] = useState<RetentionFormState>({ name: '', scope: 'workspace', retention_months: 24, apply_to: 'all' })

  const create = useMutation({
    mutationFn: () => collabApi.createRetention(form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['retention'] })
      toast.success(t('chat_admin.policy_created'))
      setForm({ name: '', scope: 'workspace', retention_months: 24, apply_to: 'all' })
    },
  })
  const run = useMutation({
    mutationFn: () => collabApi.runRetention(),
    onSuccess: (d: { deleted?: number }) => toast.success(t('chat_admin.executed_purged', { deleted: d.deleted || 0 })),
  })

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 360px', gap: 18 }}>
      <Card>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
          <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700 }}>{t('chat_admin.retention_policies')}</h3>
          <Btn variant="secondary" icon={RefreshCcw} onClick={() => run.mutate()}>{t('chat_admin.run_sweep')}</Btn>
        </div>
        {data.length === 0 ? <Empty text={t('chat_admin.no_policies_hint')} /> : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-sm)' }}>
            <thead><tr style={{ borderBottom: '1px solid var(--surface-4)', textAlign: 'left' }}>
              <th style={th}>{t('chat_admin.col_name')}</th><th style={th}>{t('chat_admin.col_scope')}</th><th style={th}>{t('chat_admin.col_apply_to')}</th><th style={th}>{t('chat_admin.col_months')}</th><th style={th}>{t('chat_admin.col_active')}</th>
            </tr></thead>
            <tbody>{data.map((r) => (
              <tr key={r.id} style={{ borderBottom: '1px solid var(--surface-4)' }}>
                <td style={td}>{r.name}</td><td style={td}>{r.scope}</td><td style={td}>{r.apply_to}</td><td style={td}>{r.retention_months}</td>
                <td style={td}>{r.is_active ? '✓' : '—'}</td>
              </tr>
            ))}</tbody>
          </table>
        )}
      </Card>
      <Card>
        <h4 style={{ margin: '0 0 12px', fontSize: 14, fontWeight: 700 }}>{t('chat_admin.new_policy')}</h4>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <Field label={t('chat_admin.col_name')}><input style={inputStyle} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
          <Field label={t('chat_admin.col_scope')}>
            <select style={inputStyle} value={form.scope} onChange={(e) => setForm({ ...form, scope: e.target.value as RetentionScope })}>
              <option value="workspace">{t('chat_admin.scope_workspace')}</option>
              <option value="team">{t('chat_admin.scope_team')}</option>
              <option value="channel">{t('chat_admin.scope_channel')}</option>
            </select>
          </Field>
          <Field label={t('chat_admin.col_apply_to')}>
            <select style={inputStyle} value={form.apply_to} onChange={(e) => setForm({ ...form, apply_to: e.target.value as RetentionApplyTo })}>
              <option value="all">{t('chat_admin.apply_all')}</option>
              <option value="messages">{t('chat_admin.apply_messages')}</option>
              <option value="attachments">{t('chat_admin.apply_attachments')}</option>
              <option value="calls">{t('chat_admin.apply_calls')}</option>
            </select>
          </Field>
          <Field label={t('chat_admin.retention_months_label')}><input type="number" min={1} max={120} style={inputStyle} value={form.retention_months} onChange={(e) => setForm({ ...form, retention_months: parseInt(e.target.value, 10) || 24 })} /></Field>
          <Btn icon={Plus} onClick={() => create.mutate()} disabled={!form.name}>{t('chat_admin.create_policy')}</Btn>
        </div>
      </Card>
    </div>
  )
}

function LegalHoldTab() {
  const t = useAppT() as (key: string, params?: Record<string, unknown>) => string
  const qc = useQueryClient()
  const toast = useToast()
  const { data = [] } = useQuery<LegalHoldCase[]>({ queryKey: ['legal-holds'], queryFn: () => collabApi.listLegalHolds() as Promise<LegalHoldCase[]> })
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
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 360px', gap: 18 }}>
      <Card>
        <h3 style={{ margin: '0 0 14px', fontSize: 16, fontWeight: 700 }}>{t('chat_admin.legal_hold_cases')} ({data.length})</h3>
        {data.length === 0 ? <Empty text={t('chat_admin.no_holds')} /> : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {data.map((h) => (
              <div key={h.id} style={{ padding: 12, background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <div style={{ fontWeight: 700 }}>{h.case_reference}</div>
                    <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{h.description}</div>
                  </div>
                  {h.is_active && <Btn variant="danger" icon={X} onClick={() => release.mutate(h.id)}>{t('chat_admin.release')}</Btn>}
                </div>
                <div style={{ marginTop: 6, fontSize: 'var(--text-xs)', color: 'var(--text-2)' }}>
                  {t('chat_admin.started_label')}: {h.started_at?.slice(0, 10)} {h.ended_at && `· ${t('chat_admin.closed_label')}: ${h.ended_at.slice(0, 10)}`}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
      <Card>
        <h4 style={{ margin: '0 0 12px', fontSize: 14, fontWeight: 700 }}>{t('chat_admin.new_case')}</h4>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <Field label={t('chat_admin.case_reference_label')}><input style={inputStyle} value={form.case_reference} onChange={(e) => setForm({ ...form, case_reference: e.target.value })} placeholder="CASO-2026-001" /></Field>
          <Field label={t('chat_admin.description_label')}><textarea rows={2} style={inputStyle} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></Field>
          <Field label={t('chat_admin.custodians_label')}><input style={inputStyle} value={form.custodian_user_ids} onChange={(e) => setForm({ ...form, custodian_user_ids: e.target.value })} /></Field>
          <Field label={t('chat_admin.channels_label')}><input style={inputStyle} value={form.channel_ids} onChange={(e) => setForm({ ...form, channel_ids: e.target.value })} /></Field>
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
  const { data = [] } = useQuery<IntegrationItem[]>({ queryKey: ['integrations'], queryFn: () => collabApi.listIntegrations() as Promise<IntegrationItem[]> })
  const [form, setForm] = useState<IntegrationFormState>({ kind: 'jira', name: '', config: '{}' })
  const create = useMutation({
    mutationFn: () => collabApi.createIntegration({ kind: form.kind, name: form.name, config: tryJson(form.config) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['integrations'] })
      toast.success(t('chat_admin.integration_created'))
    },
  })
  const remove = useMutation({
    mutationFn: (id: string | number) => collabApi.deleteIntegration(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['integrations'] })
      toast.success(t('chat_admin.deleted'))
    },
  })
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 360px', gap: 18 }}>
      <Card>
        <h3 style={{ margin: '0 0 14px', fontSize: 16, fontWeight: 700 }}>{t('chat_admin.integrations')} ({data.length})</h3>
        {data.length === 0 ? <Empty text={t('chat_admin.no_integrations')} /> : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {data.map((it) => (
              <div key={it.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: 12, background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8 }}>
                <div>
                  <div style={{ fontWeight: 700 }}>{it.name}</div>
                  <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{it.kind}{!it.is_enabled && ` · ${t('chat_admin.disabled')}`}</div>
                </div>
                <Btn variant="danger" icon={X} onClick={() => remove.mutate(it.id)}>{t('chat_admin.delete')}</Btn>
              </div>
            ))}
          </div>
        )}
      </Card>
      <Card>
        <h4 style={{ margin: '0 0 12px', fontSize: 14, fontWeight: 700 }}>{t('chat_admin.connect_integration')}</h4>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <Field label={t('chat_admin.kind_label')}>
            <select style={inputStyle} value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value as IntegrationKind })}>
              <option value="jira">Jira</option>
              <option value="github">GitHub</option>
              <option value="gitlab">GitLab</option>
              <option value="google_calendar">Google Calendar</option>
              <option value="microsoft_365">Microsoft 365</option>
              <option value="service_desk">Service Desk</option>
              <option value="nexus_ai">Nexus AI</option>
              <option value="custom_webhook">{t('chat_admin.custom_webhook')}</option>
            </select>
          </Field>
          <Field label={t('chat_admin.col_name')}><input style={inputStyle} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
          <Field label={t('chat_admin.config_json_label')}><textarea rows={3} style={inputStyle} value={form.config} onChange={(e) => setForm({ ...form, config: e.target.value })} /></Field>
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
  const { data = [] } = useQuery<WebhookItem[]>({ queryKey: ['webhooks'], queryFn: () => collabApi.listWebhooks() as Promise<WebhookItem[]> })
  const [form, setForm] = useState<WebhookFormState>({ direction: 'incoming', name: '', url: '', target_channel_id: '', events: '' })
  const create = useMutation({
    mutationFn: () => collabApi.createWebhook({
      direction: form.direction,
      name: form.name,
      url: form.url || null,
      target_channel_id: form.target_channel_id || null,
      events: form.events.split(',').map((s) => s.trim()).filter(Boolean),
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['webhooks'] })
      toast.success(t('chat_admin.webhook_created'))
    },
  })
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 360px', gap: 18 }}>
      <Card>
        <h3 style={{ margin: '0 0 14px', fontSize: 16, fontWeight: 700 }}>{t('chat_admin.tab_webhooks')} ({data.length})</h3>
        {data.length === 0 ? <Empty text={t('chat_admin.no_webhooks')} /> : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {data.map((w) => (
              <div key={w.id} style={{ padding: 12, background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8 }}>
                <div style={{ fontWeight: 700 }}>{w.name} <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>({w.direction})</span></div>
                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-2)', wordBreak: 'break-all' }}>
                  {w.direction === 'incoming' ? `POST /api/v1/collaboration/webhooks/incoming/${w.secret_token}` : (w.url || '—')}
                </div>
                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', marginTop: 4 }}>
                  {t('chat_admin.events_label')}: {w.events?.join(', ') || '—'}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
      <Card>
        <h4 style={{ margin: '0 0 12px', fontSize: 14, fontWeight: 700 }}>{t('chat_admin.new_webhook')}</h4>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <Field label={t('chat_admin.direction_label')}>
            <select style={inputStyle} value={form.direction} onChange={(e) => setForm({ ...form, direction: e.target.value as WebhookDirection })}>
              <option value="incoming">{t('chat_admin.direction_incoming')}</option>
              <option value="outgoing">{t('chat_admin.direction_outgoing')}</option>
            </select>
          </Field>
          <Field label={t('chat_admin.col_name')}><input style={inputStyle} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
          {form.direction === 'outgoing' && <Field label={t('chat_admin.target_url_label')}><input style={inputStyle} value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} /></Field>}
          <Field label={t('chat_admin.target_channel_label')}><input style={inputStyle} value={form.target_channel_id} onChange={(e) => setForm({ ...form, target_channel_id: e.target.value })} /></Field>
          <Field label={t('chat_admin.events_input_label')}><input style={inputStyle} value={form.events} onChange={(e) => setForm({ ...form, events: e.target.value })} placeholder="message.created,channel.created" /></Field>
          <Btn icon={Plus} onClick={() => create.mutate()} disabled={!form.name}>{t('chat_admin.create')}</Btn>
        </div>
      </Card>
    </div>
  )
}

function AuditTab() {
  const t = useAppT() as (key: string, params?: Record<string, unknown>) => string
  const { data = [] } = useQuery<AuditEventItem[]>({ queryKey: ['audit'], queryFn: () => collabApi.listAudit(200) as Promise<AuditEventItem[]>, refetchInterval: 30000 })
  const verify = useMutation<AuditVerifyResult>({
    mutationFn: () => collabApi.verifyAudit() as Promise<AuditVerifyResult>,
  })
  return (
    <Card>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
        <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700 }}>{t('chat_admin.audit_events')} ({data.length})</h3>
        <Btn variant="secondary" icon={ShieldCheck} onClick={() => verify.mutate()}>{t('chat_admin.verify_chain')}</Btn>
      </div>
      {verify.data && (
        <div style={{ marginBottom: 12, padding: '10px 14px', background: verify.data.is_valid ? 'rgba(16,185,129,0.12)' : 'rgba(239,68,68,0.12)', border: `1px solid ${verify.data.is_valid ? 'rgba(16,185,129,0.3)' : 'rgba(239,68,68,0.3)'}`, borderRadius: 8, fontSize: 'var(--text-sm)' }}>
          {verify.data.is_valid
            ? t('chat_admin.chain_ok', { total: verify.data.total || 0, chains: verify.data.chains || 0 })
            : t('chat_admin.chain_broken', { breaks: verify.data.breaks?.length || 0 })}
        </div>
      )}
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-sm)' }}>
        <thead><tr style={{ borderBottom: '1px solid var(--surface-4)', textAlign: 'left' }}>
          <th style={th}>{t('chat_admin.col_date')}</th><th style={th}>{t('chat_admin.col_action')}</th><th style={th}>{t('chat_admin.col_type')}</th><th style={th}>{t('chat_admin.col_entity')}</th><th style={th}>{t('chat_admin.col_actor')}</th>
        </tr></thead>
        <tbody>{data.map((e) => (
          <tr key={e.id} style={{ borderBottom: '1px solid var(--surface-4)' }}>
            <td style={{ ...td, fontFamily: 'var(--font-mono)', fontSize: 11 }}>{e.created_at?.replace('T', ' ').slice(0, 19)}</td>
            <td style={td}>{e.action}</td><td style={td}>{e.entity_type}</td>
            <td style={{ ...td, fontFamily: 'var(--font-mono)', fontSize: 11 }}>{e.entity_id?.slice(0, 8) || '—'}</td>
            <td style={{ ...td, fontSize: 11 }}>{e.actor_user_id?.slice(0, 8) || '—'}</td>
          </tr>
        ))}</tbody>
      </table>
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
      <h3 style={{ margin: '0 0 14px', fontSize: 16, fontWeight: 700 }}>{t('chat_admin.ediscovery_title')}</h3>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 16 }}>
        <Field label={t('chat_admin.case_short_label')}><input style={inputStyle} value={form.case_reference} onChange={(e) => setForm({ ...form, case_reference: e.target.value })} /></Field>
        <Field label={t('chat_admin.custodians_label')}><input style={inputStyle} value={form.user_ids} onChange={(e) => setForm({ ...form, user_ids: e.target.value })} /></Field>
        <Field label={t('chat_admin.keywords_label')}><input style={inputStyle} value={form.keywords} onChange={(e) => setForm({ ...form, keywords: e.target.value })} /></Field>
        <div />
        <Field label={t('chat_admin.from_label')}><input type="datetime-local" style={inputStyle} value={form.date_from} onChange={(e) => setForm({ ...form, date_from: e.target.value })} /></Field>
        <Field label={t('chat_admin.to_label')}><input type="datetime-local" style={inputStyle} value={form.date_to} onChange={(e) => setForm({ ...form, date_to: e.target.value })} /></Field>
      </div>
      <Btn icon={Download} onClick={() => exp.mutate()} disabled={exp.isPending}>{exp.isPending ? t('chat_admin.exporting') : t('chat_admin.export_json')}</Btn>
    </Card>
  )
}

const th: CSSProperties = { padding: '8px 10px', fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em' }
const td: CSSProperties = { padding: '10px', color: 'var(--text-1)' }

function tryJson(s: string): Record<string, unknown> {
  try {
    return JSON.parse(s || '{}') as Record<string, unknown>
  } catch {
    return {}
  }
}

function Empty({ text }: { text: string }) {
  return <div style={{ padding: 24, textAlign: 'center', color: 'var(--text-3)', fontSize: 'var(--text-sm)' }}>{text}</div>
}
