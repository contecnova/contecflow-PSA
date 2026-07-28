import { PROVIDER_META } from '../constants/api'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr } from '../utils/helpers'
import { useId, useState } from 'react'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { predictiveObservabilityApi, aiProvidersApi } from '../services/api'
import { PROVIDER_DOCS } from '../constants/api'
import { Button, Spinner, Modal, Tabs, Page } from '../components/ui'
import { useAppLang, useAppT } from '../i18n/AppLangContext'
import { Cpu, X, Search, Plus, Activity } from 'lucide-react'

const PMETA = PROVIDER_META as Record<string, { name: string; icon: string; color: string }>
const PDOCS = PROVIDER_DOCS as Record<string, string>

const getStatusCfg = (t: (k: string) => string): Record<string, { label: string; color: string }> => ({
  active:   { label: t('ai.provider_status_active'), color: 'var(--success)' },
  inactive: { label: t('ai.provider_status_inactive'), color: 'var(--text-2)' },
  error:    { label: t('ai.provider_status_error'), color: 'var(--danger)' },
})

const card = { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12 }
const fs = { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', width: '100%' }
const ls = { fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', display: 'block', marginBottom: 5 }

function ProviderModal({ provider, catalog, onClose }: { provider: any; catalog: any; onClose: () => void }) {
  const t = useAppT()
  const idPrefix = useId()
  const qc = useQueryClient()
  const toast = useToast()
  const isEdit = !!provider?.id
  const [providerType, setProviderType] = useState(provider?.provider || 'anthropic')
  const [liveModels, setLiveModels] = useState<any[]>(provider?.available_models || [])
  const [form, setForm] = useState({
    name: provider?.name || '',
    provider: provider?.provider || 'anthropic',
    api_key: '',
    api_base_url: provider?.api_base_url || '',
    default_model: provider?.default_model || '',
    max_tokens: provider?.max_tokens || 2000,
    temperature: provider?.temperature || 0.7,
    is_default: provider?.is_default || false,
  })
  const s = (k: string) => (e: any) => setForm(f => ({ ...f, [k]: e.target.value }))

  const catEntry = catalog[providerType] || {}
  const catalogModels = catEntry.models || []
  const models = liveModels.length > 0
    ? liveModels.map((id: any) => {
      const known = catalogModels.find((m: any) => m.id === id)
      return known || { id, name: id, cost_in: 0, cost_out: 0 }
    })
    : catalogModels

  const { mutate, isPending } = useMutation({
    mutationFn: (d: any) => isEdit ? aiProvidersApi.update(provider.id, d) : aiProvidersApi.create(d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['ai-providers'] }); onClose() },
    onError: e => toast.error(extractErr(e, t('ai.save_error'))),
  })

  const { mutate: syncModels, isPending: isSyncingModels } = useMutation({
    mutationFn: () => aiProvidersApi.syncModels(provider.id).then(r => r.data),
    onSuccess: (data) => {
      const synced = Array.isArray(data?.models) ? data.models : []
      setLiveModels(synced)
      if (data?.default_model) {
        setForm(f => ({ ...f, default_model: data.default_model }))
      }
      qc.invalidateQueries({ queryKey: ['ai-providers'] })
      toast.success('Modelos sincronizados desde el proveedor')
    },
    onError: e => toast.error(extractErr(e, 'No se pudieron sincronizar modelos del proveedor')),
  })

  const handleProviderChange = (type: any) => {
    setProviderType(type)
    setLiveModels([])
    const cat = catalog[type] || {}
    setForm(f => ({
      ...f,
      provider: type,
      name: f.name || `${PMETA[type]?.name || type}`,
      api_base_url: cat.base_url || '',
      default_model: cat.models?.[0]?.id || '',
    }))
  }

  const title = isEdit ? `${t('ai.edit_provider')} — ${provider.name}` : t('ai.add_provider')

  return (
    <>
      <div role="presentation" onMouseDown={onClose}
        style={{ position: 'fixed', inset: 0, zIndex: 200, background: 'rgba(0,0,0,0.35)' }} />
      <div role="dialog" aria-modal="true" aria-label={title}
        style={{ position: 'fixed', top: 12, right: 12, width: 640, maxWidth: 'calc(100vw - 24px)',
          maxHeight: 'calc(100vh - 24px)',
          background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 12,
          zIndex: 201, display: 'flex', flexDirection: 'column',
          boxShadow: '-8px 0 32px rgba(0,0,0,0.4)' }}>
        {/* Drawer header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '14px 20px', borderBottom: '1px solid var(--surface-4)', flexShrink: 0 }}>
          <span style={{ fontSize: "var(--text-lg)", fontWeight: 700, color: 'var(--text-1)' }}>{title}</span>
          <button onClick={onClose} aria-label="Cerrar" style={{ background: 'none', border: 'none', cursor: 'pointer',
            color: 'var(--text-3)', display: 'flex', padding: 4, borderRadius: 6 }}>
            <X size={16} />
          </button>
        </div>
        {/* Body */}
        <div style={{ padding: '20px', overflowY: 'auto', flex: 1, minHeight: 0 }}>
      <form onSubmit={e => { e.preventDefault(); mutate(form) }}>
      {/* Selector de proveedor */}
      {!isEdit && (
        <div style={{ marginBottom: 20 }}>
          <label style={ls}>{t('ai.provider')}</label>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8 }}>
            {Object.entries(PMETA).map(([key, meta]) => (
              <button key={key} type="button" aria-pressed={providerType === key} aria-label={`${t('ai.select_provider')} ${meta.name}`} onClick={() => handleProviderChange(key)}
                style={{ padding: '10px 8px', borderRadius: 8, border: `2px solid ${providerType === key ? meta.color + '80' : 'var(--surface-4)'}`, background: providerType === key ? meta.color + '15' : 'transparent', cursor: 'pointer', fontFamily: 'inherit', transition: 'all 0.15s' }}>
                <div style={{ fontSize: "var(--text-lg-em)", marginBottom: 4 }}>{meta.icon}</div>
                <div style={{ fontSize: "var(--text-xs)", fontWeight: 600, color: providerType === key ? meta.color : 'var(--text-2)' }}>{meta.name}</div>
              </button>
            ))}
          </div>
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
        <div style={{ gridColumn: '1/-1' }}>
          <label htmlFor={`${idPrefix}-name`} style={ls}>{t('ai.config_name')} *</label>
          <input id={`${idPrefix}-name`} value={form.name} onChange={s('name')} style={fs} placeholder={`${catEntry.name || ''} — ${t('ai.config_name_placeholder')}`} />
        </div>

        {providerType !== 'ollama' && (
          <div style={{ gridColumn: '1/-1' }}>
            <label htmlFor={`${idPrefix}-api-key`} style={ls}>
              API Key {catEntry.key_hint && <span style={{ color: 'var(--text-3)', fontWeight: 400, textTransform: 'none' }}>({catEntry.key_hint})</span>}
            </label>
            <input id={`${idPrefix}-api-key`} type="password" value={form.api_key} onChange={s('api_key')} style={fs}
              placeholder={isEdit ? t('ai.keep_api_key_placeholder') : t('ai.enter_api_key_placeholder')} />
            {catEntry.docs_url && (
              <a href={catEntry.docs_url} target="_blank" rel="noreferrer"
                style={{ fontSize: "var(--text-xs)", color: 'var(--accent)', marginTop: 4, display: 'block' }}>
                🔗 {t('ai.get_api_key_at')} {catEntry.docs_url}
              </a>
            )}
          </div>
        )}

        {(providerType === 'ollama' || providerType === 'azure') && (
          <div style={{ gridColumn: '1/-1' }}>
            <label htmlFor={`${idPrefix}-api-base-url`} style={ls}>{t('ai.base_url')} {providerType === 'ollama' ? `(${t('ai.base_url_example')} http://localhost:11434)` : ''}</label>
            <input id={`${idPrefix}-api-base-url`} value={form.api_base_url} onChange={s('api_base_url')} style={fs}
              placeholder={catEntry.base_url || 'https://...'} />
          </div>
        )}

        <div>
          <label htmlFor={`${idPrefix}-default-model`} style={ls}>{t('ai.default_model')}</label>
          {models.length > 0 ? (
            <>
              <select
                id={`${idPrefix}-default-model`}
                value={models.some((m: any) => m.id === form.default_model) ? form.default_model : '__custom__'}
                onChange={e => {
                  if (e.target.value === '__custom__') {
                    setForm(f => ({ ...f, default_model: '' }))
                  } else {
                    setForm(f => ({ ...f, default_model: e.target.value }))
                  }
                }}
                style={fs}
              >
                <option value="">{t('ai.select_option')}</option>
                {models.map((m: any) => (
                  <option key={m.id} value={m.id}>
                    {m.name} {m.cost_in > 0 ? `· $${m.cost_in}/M in` : '· Gratis'}
                  </option>
                ))}
                <option value="__custom__">✏️ {t('ai.custom_model')}</option>
              </select>
              {!models.some((m: any) => m.id === form.default_model) && (
                <input
                  aria-label={t('ai.custom_model_id')}
                  value={form.default_model}
                  onChange={s('default_model')}
                  style={{ ...fs, marginTop: 6 }}
                  placeholder={t('ai.model_custom_placeholder')}
                />
              )}
            </>
          ) : (
            <input id={`${idPrefix}-default-model`} value={form.default_model} onChange={s('default_model')} style={fs}
              placeholder={t('ai.model_name_placeholder')} />
          )}
          {isEdit && (
            <div style={{ marginTop: 8 }}>
              <Button
                variant="secondary"
                onClick={() => syncModels()}
                disabled={isSyncingModels}
                loading={isSyncingModels}
              >
                {isSyncingModels ? 'Sincronizando modelos...' : 'Sincronizar modelos desde proveedor'}
              </Button>
            </div>
          )}
        </div>

        <div>
          <label htmlFor={`${idPrefix}-max-tokens`} style={ls}>{t('ai.max_response_tokens')}</label>
          <input id={`${idPrefix}-max-tokens`} type="number" value={form.max_tokens} onChange={s('max_tokens')} style={fs} />
        </div>

        <div>
          <label htmlFor={`${idPrefix}-temperature`} style={ls}>{t('ai.temperature')}</label>
          <input id={`${idPrefix}-temperature`} type="number" step="0.1" min="0" max="2" value={form.temperature} onChange={s('temperature')} style={fs} />
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10, paddingTop: 20 }}>
          <input type="checkbox" id={`${idPrefix}-is-default`} checked={form.is_default}
            onChange={e => setForm(f => ({ ...f, is_default: e.target.checked }))} />
          <label htmlFor={`${idPrefix}-is-default`} style={{ fontSize: "var(--text-base)", cursor: 'pointer' }}>
            {t('ai.set_global_default')}
          </label>
        </div>
      </div>

      {/* Info del proveedor seleccionado */}
      {models.length > 0 && (
        <div style={{ marginTop: 16, padding: '12px 14px', background: 'var(--surface-1)', borderRadius: 8, fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>
          <div style={{ fontWeight: 700, marginBottom: 8, color: 'var(--text-1)' }}>{t('ai.available_models')}:</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 6, maxHeight: 220, overflowY: 'auto', paddingRight: 4 }}>
            {models.map((m: any) => (
              <div key={m.id} style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-2)' }}>{m.name}</span>
                <span style={{ color: m.cost_in === 0 ? 'var(--success)' : 'var(--warning)' }}>
                  {m.cost_in === 0 ? t('ai.free') : `$${m.cost_in}/${m.cost_out}`}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      </form>
        </div>
        {/* Fixed footer */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10,
          padding: '12px 20px', borderTop: '1px solid var(--surface-4)',
          background: 'var(--surface-1)', flexShrink: 0 }}>
          <Button variant="secondary" onClick={onClose} type="button">{t('common.cancel')}</Button>
          <Button onClick={() => mutate(form)} disabled={isPending || !form.name || !form.provider} loading={isPending}>
            {isPending ? t('common.saving') : isEdit ? t('ai.save_changes') : t('ai.add_provider_action')}
          </Button>
        </div>
      </div>
    </>
  )
}

function TestModal({ provider, onClose }: { provider: any; onClose: () => void }) {
  const t = useAppT()
  const [result, setResult] = useState<{ ok?: boolean; error?: string; response?: string; latency_ms?: number; model?: string } | null>(null)
  const [testing, setTesting] = useState(false)

  const runTest = async () => {
    setTesting(true)
    setResult(null)
    try {
      const res = await aiProvidersApi.test(provider.id)
      setResult(res.data)
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: unknown } }; message?: string }
      const raw = err?.response?.data?.detail
      setResult({ ok: false, error: Array.isArray(raw) ? raw.map((d: any) => d.msg).join(', ') : ((raw as string) || err.message) })
    } finally {
      setTesting(false)
    }
  }

  return (
    <Modal open onClose={onClose} title={`${t('ai.testing_provider')} — ${provider.name}`} width={480}>
      <p style={{ color: 'var(--text-2)', fontSize: "var(--text-base)", marginBottom: 20 }}>
        {t('ai.connection_help')}
      </p>
      <Button onClick={runTest} disabled={testing}>
        {testing ? `⏳ ${t('ai.test_running')}` : `🔌 ${t('ai.test_connection')}`}
      </Button>
      {result && (
        <div style={{ marginTop: 16, padding: '14px 16px', background: result.ok ? 'var(--success-bg)' : 'var(--danger-bg)',
          border: `1px solid ${result.ok ? 'var(--success-border)' : 'var(--danger-border)'}`, borderRadius: 8 }}>
          {result.ok ? (
            <>
              <div style={{ color: 'var(--success)', fontWeight: 700, marginBottom: 8 }}>✅ {t('ai.test_success')}</div>
              <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>{t('ai.test_response')}: &quot;{result.response}&quot;</div>
              <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginTop: 4 }}>{t('ai.test_latency_model')}: {result.latency_ms}ms · {result.model}</div>
            </>
          ) : (
            <>
              <div style={{ color: 'var(--danger)', fontWeight: 700, marginBottom: 8 }}>❌ {t('ai.test_error')}</div>
              <pre style={{ fontSize: "var(--text-sm)", color: 'var(--warning)', whiteSpace: 'pre-wrap', margin: 0 }}>{result.error}</pre>
            </>
          )}
        </div>
      )}
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 16 }}>
        <Button variant="secondary" onClick={onClose}>{t('common.close')}</Button>
      </div>
    </Modal>
  )
}

// ── Governance Tab ───────────────────────────────────────────────────────────
function GovernanceTab() {
  // Read-only viewer del audit log + stats. El CRUD de policies se gestiona
  // vía API directa hasta que se complete la UI dedicada (decisión ARCH).
  // #45: converted fetch() → useQuery (read-only GETs, no side-effects).
  // TODO: añadir queryKeys.aiGovernance.* en constants/queryKeys.js
  const { data: policiesRaw = [], isLoading: loadingPolicies } = useQuery({
    queryKey: ['ai-governance', 'policies'],
    queryFn: () => fetch('/api/v1/ai-governance/policies', { credentials: 'include' })
      .then(r => r.ok ? r.json() : []),
    staleTime: 60_000,
  })
  const { data: auditLogRaw = [], isLoading: loadingAudit } = useQuery({
    queryKey: ['ai-governance', 'audit-log', { limit: 50 }],
    queryFn: () => fetch('/api/v1/ai-governance/audit-log?limit=50', { credentials: 'include' })
      .then(r => r.ok ? r.json() : []),
    staleTime: 30_000,
  })
  const { data: stats = null, isLoading: loadingStats } = useQuery({
    queryKey: ['ai-governance', 'audit-log-stats'],
    queryFn: () => fetch('/api/v1/ai-governance/audit-log/stats', { credentials: 'include' })
      .then(r => r.ok ? r.json() : null),
    staleTime: 60_000,
  })

  const policies = Array.isArray(policiesRaw) ? policiesRaw : (policiesRaw.items || [])
  const auditLog = Array.isArray(auditLogRaw) ? auditLogRaw : (auditLogRaw.items || [])
  const loading = loadingPolicies || loadingAudit || loadingStats

  if (loading) return <div style={{ padding: 24 }}><Spinner /></div>

  return (
    <div id="aihub-panel-governance" role="tabpanel" style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Stats summary */}
      {stats && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
          {[
            { label: 'Evaluaciones', value: stats.total_evaluations || 0, color: 'var(--accent)' },
            { label: 'Bloqueadas', value: stats.blocked || 0, color: 'var(--danger)' },
            { label: 'Redacted', value: stats.redacted || 0, color: 'var(--warning)' },
            { label: 'PII detectado', value: stats.pii_total || 0, color: 'var(--purple)' },
          ].map(k => (
            <div key={k.label} style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 10, padding: '14px 18px' }}>
              <div style={{ fontSize: 'var(--text-xl)', fontWeight: 800, color: k.color }}>{k.value}</div>
              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-2)' }}>{k.label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Policies list */}
      <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, overflow: 'hidden' }}>
        <div style={{ padding: '12px 18px', borderBottom: '1px solid var(--surface-4)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ fontWeight: 700 }}>🛡 Políticas configuradas ({policies.length})</div>
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>
            CRUD via <code>POST /api/v1/ai-governance/policies</code> · UI completa pendiente
          </div>
        </div>
        {policies.length === 0 ? (
          <div style={{ padding: 24, textAlign: 'center', color: 'var(--text-3)', fontSize: 'var(--text-sm)' }}>
            Sin policies activas. Los guardrails (detección PII, keywords prohibidas) están listos pero requieren al menos una policy configurada vía API.
          </div>
        ) : (
          <div style={{ maxHeight: 240, overflowY: 'auto' }}>
            {policies.map((p: any) => (
              <div key={p.id} style={{ padding: '10px 18px', borderBottom: '1px solid var(--surface-4)', fontSize: 'var(--text-sm)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ fontWeight: 600 }}>{p.name}</span>
                  <span style={{ fontSize: 'var(--text-xs)', padding: '2px 8px', borderRadius: 4, background: p.is_active ? 'var(--success-bg)' : 'var(--surface-3)', color: p.is_active ? 'var(--success)' : 'var(--text-3)' }}>
                    {p.is_active ? 'Activa' : 'Inactiva'}
                  </span>
                </div>
                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', marginTop: 2 }}>
                  scope={p.scope} · action={p.action} · roles=[{(p.applies_to_roles || []).join(',')}]
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Audit log */}
      <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, overflow: 'hidden' }}>
        <div style={{ padding: '12px 18px', borderBottom: '1px solid var(--surface-4)', fontWeight: 700 }}>
          📋 Audit log — últimas 50 evaluaciones
        </div>
        {auditLog.length === 0 ? (
          <div style={{ padding: 24, textAlign: 'center', color: 'var(--text-3)' }}>Sin actividad reciente</div>
        ) : (
          <div style={{ maxHeight: 360, overflowY: 'auto' }}>
            {auditLog.map((l: any) => (
              <div key={l.id} style={{ padding: '8px 18px', borderBottom: '1px solid var(--surface-4)', fontSize: 'var(--text-xs)', display: 'flex', gap: 12, alignItems: 'center' }}>
                <span style={{ minWidth: 100, color: 'var(--text-3)' }}>{(l.evaluated_at || '').slice(0, 16)}</span>
                <span style={{ minWidth: 80, fontWeight: 600 }}>{l.module || '—'}</span>
                <span style={{ minWidth: 60 }}>{l.scope}</span>
                <span style={{ padding: '1px 6px', borderRadius: 4, background: l.was_blocked ? 'var(--danger-bg)' : l.action_taken === 'redacted' ? 'var(--warning-bg)' : 'var(--surface-3)', color: l.was_blocked ? 'var(--danger)' : l.action_taken === 'redacted' ? 'var(--warning)' : 'var(--text-2)' }}>
                  {l.action_taken || 'none'}
                </span>
                {(l.pii_types_found || []).length > 0 && (
                  <span style={{ color: 'var(--warning)' }}>PII: {l.pii_types_found.join(',')}</span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export default function AIHubPage(): JSX.Element {
  const { lang } = useAppLang()
  const t = useAppT()
  const statusCfg = getStatusCfg(t)
  const toast = useToast()
  const qc = useQueryClient()
  const [modal, setModal] = useState<any>(null)
  const [testModal, setTestModal] = useState<any>(null)
  const [tab, setTab] = useState('providers')
  const [diagResults, setDiagResults] = useState<any>(null)

  const { data: providers = [], isLoading } = useQuery({
    queryKey: ['ai-providers'],
    queryFn: () => aiProvidersApi.list().then(r => r.data),
    select: d => (Array.isArray(d) ? d : []),
  })
  const { data: catalog = {} } = useQuery({
    queryKey: ['ai-providers-catalog'],
    queryFn: () => aiProvidersApi.catalog().then(r => r.data),
    staleTime: Infinity,
  })
  const { data: stats = {} } = useQuery({
    queryKey: ['ai-stats'],
    queryFn: () => aiProvidersApi.stats().then(r => r.data),
    enabled: tab === 'stats',
  })
  const { data: obsHealth, isLoading: obsLoading } = useQuery({
    queryKey: ['predictive-obs-health'],
    queryFn: () => predictiveObservabilityApi.health({}).then(r => r.data).catch(() => null),
    enabled: tab === 'observability',
    staleTime: 120_000,
  })
  const { mutate: triggerRetrain, isPending: retraining } = useMutation({
    mutationFn: () => predictiveObservabilityApi.triggerRetrain(),
    onSuccess: () => { toast.success('Ciclo de reentrenamiento completado'); qc.invalidateQueries({ queryKey: ['predictive-obs-health'] }) },
    onError: e => toast.error(extractErr(e, 'Error al reentrenar')),
  })

  const { mutate: setDefault } = useMutation({
    mutationFn: (id: any) => aiProvidersApi.setDefault(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['ai-providers'] }),
    onError: e => toast.error(extractErr(e, t('ai.reset_error'))),
  })
  const { mutate: del } = useMutation({
    mutationFn: (id: any) => aiProvidersApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['ai-providers'] }),
    onError: e => toast.error(extractErr(e, t('ai.generic_error'))),
  })

  const { mutate: diagnoseAll, isPending: diagnosing } = useMutation({
    mutationFn: () => aiProvidersApi.diagnostics().then(r => r.data),
    onSuccess: (data) => {
      setDiagResults(data)
      const healthy = Number(data?.healthy || 0)
      const total = Number(data?.total || 0)
      if (healthy === total) {
        toast.success(`Diagnóstico OK: ${total} proveedor(es) operativos`)
      } else {
        toast.error(`Diagnóstico: ${healthy}/${total} operativos`)
      }
    },
    onError: e => toast.error(extractErr(e, 'Error ejecutando diagnóstico')),
  })

  const { mutate: syncAllModels, isPending: syncingAllModels } = useMutation({
    mutationFn: () => aiProvidersApi.syncAll().then(r => r.data),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['ai-providers'] })
      const failed = Number(data?.failed || 0)
      const total = Number(data?.total || 0)
      if (failed > 0) {
        toast.error(`Sincronización parcial: ${total - failed}/${total} proveedores actualizados`) 
      } else {
        toast.success(`Modelos sincronizados en ${total} proveedor(es)`) 
      }
    },
    onError: e => toast.error(extractErr(e, 'No se pudieron sincronizar los modelos de los proveedores')),
  })

  const defaultProvider = providers.find((p: any) => p.is_default)
  const byModule = stats.by_module || []
  const moneyFmt = new Intl.NumberFormat(lang === 'en' ? 'en-US' : 'es-ES', { style: 'currency', currency: 'USD', minimumFractionDigits: 4, maximumFractionDigits: 4 })
  const intFmt = new Intl.NumberFormat(lang === 'en' ? 'en-US' : 'es-ES')

  return (
    <Page
      icon={<Cpu size={18} />}
      title={t('ai.hub_title')}
      subtitle={t('ai.hub_subtitle')}
      rightActions={(
        <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
          <Button
            variant="secondary"
            onClick={() => diagnoseAll()}
            disabled={diagnosing}
            loading={diagnosing}
          >
            <Search size={13} /> {diagnosing ? 'Diagnosticando...' : 'Diagnóstico'}
          </Button>
          <Button
            variant="secondary"
            onClick={() => syncAllModels()}
            disabled={syncingAllModels}
            loading={syncingAllModels}
          >
            {syncingAllModels ? 'Sincronizando modelos...' : 'Sincronizar todos los modelos'}
          </Button>
          <Button onClick={() => setModal({})}>
            <Plus size={13} /> {t('ai.add_provider')}
          </Button>
        </div>
      )}
    >
      {/* Tabs */}
      <Tabs
        items={[
          { id: 'providers',     label: t('ai.providers') },
          { id: 'stats',         label: t('ai.usage') },
          { id: 'governance',    label: <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>🛡 Governance</span> },
          { id: 'observability', label: <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}><Activity size={11} /> Observabilidad</span> },
          { id: 'guide',         label: t('ai.guide') },
        ]}
        active={tab}
        onChange={setTab}
        ariaLabel={t('ai.hub_title')}
        style={{ marginBottom: 'var(--space-5)', paddingBottom: 'var(--space-3)', borderBottom: '1px solid var(--surface-4)' }}
      />

      {tab === 'governance' && <GovernanceTab />}

      {/* PROVIDERS TAB */}
      {tab === 'providers' && (
        <div id="aihub-panel-providers" role="tabpanel" aria-labelledby="aihub-tab-providers">

          {/* Panel de diagnóstico */}
          {diagResults && (
            <div style={{ ...card, padding: '16px 20px', marginBottom: 20, borderColor: diagResults.error > 0 ? 'var(--danger)' : diagResults.warning > 0 ? 'var(--warning)' : 'var(--success)' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                <div style={{ fontWeight: 700, fontSize: "var(--text-md)" }}>
                  Diagnóstico — {diagResults.healthy}/{diagResults.total} operativos
                </div>
                <button onClick={() => setDiagResults(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-2)', fontSize: "var(--text-lg)" }}>✕</button>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {(diagResults.providers || []).map((pr: any) => {
                  const dotKind = pr.status === 'ok' ? 'success' : pr.status === 'warning' ? 'warning' : 'danger'
                  return (
                    <div key={pr.id} style={{ display: 'flex', alignItems: 'flex-start', gap: 10, fontSize: "var(--text-base)" }}>
                      <span className={`ds-status-dot ds-status-dot--${dotKind}`} style={{ marginTop: 7, flexShrink: 0 }} />
                      <div style={{ flex: 1 }}>
                        <span style={{ fontWeight: 600 }}>{pr.name}</span>
                        <span style={{ color: 'var(--text-2)', marginLeft: 8, fontSize: "var(--text-sm)" }}>{pr.provider_type}</span>
                        {pr.latency_ms != null && (
                          <span style={{ color: 'var(--text-2)', marginLeft: 8, fontSize: "var(--text-sm)" }}>{pr.latency_ms} ms</span>
                        )}
                        {pr.models_found > 0 && (
                          <span style={{ color: 'var(--text-2)', marginLeft: 8, fontSize: "var(--text-sm)" }}>{pr.models_found} modelos</span>
                        )}
                        {pr.error && (
                          <div style={{ color: pr.status === 'warning' ? 'var(--warning)' : 'var(--danger)', fontSize: "var(--text-sm)", marginTop: 2 }}>{pr.error}</div>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Proveedor activo */}
          {defaultProvider && (
            <div style={{ ...card, padding: '16px 20px', marginBottom: 20, borderColor: PMETA[defaultProvider.provider]?.color + '50' || 'var(--surface-4)', background: PMETA[defaultProvider.provider]?.color + '08' || 'var(--surface-2)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <span style={{ fontSize: "var(--text-3xl)" }}>{PMETA[defaultProvider.provider]?.icon}</span>
                <div>
                  <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{t('ai.provider_active_default')}</div>
                  <div style={{ fontSize: "var(--text-lg)", fontWeight: 800 }}>{defaultProvider.name}</div>
                  <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>{t('ai.model_label')}: {defaultProvider.default_model} · {intFmt.format(defaultProvider.total_requests || 0)} {t('ai.requests').toLowerCase()} · {moneyFmt.format(defaultProvider.total_cost_usd || 0)} {t('ai.spent')}</div>
                </div>
              </div>
            </div>
          )}

          {isLoading ? <Spinner /> : providers.length === 0 ? (
            <div style={{ ...card, padding: '48px 24px', textAlign: 'center' }}>
              <div style={{ fontSize: "var(--text-6xl)", marginBottom: 16 }}>🤖</div>
              <div style={{ fontSize: "var(--text-lg-em)", fontWeight: 700, marginBottom: 8 }}>{t('ai.no_providers_title')}</div>
              <div style={{ fontSize: "var(--text-md)", color: 'var(--text-2)', marginBottom: 24, maxWidth: 500, margin: '0 auto 24px' }}>
                {t('ai.no_providers_desc')}
              </div>
              <Button onClick={() => setModal({})}><Plus size={13} /> {t('ai.add_first_provider')}</Button>
            </div>
          ) : (
            <div data-export-table="ai-providers-list" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 14 }}>
              {providers.map((p: any) => {
                const meta: { name?: string; icon: string; color: string } = PMETA[p.provider] || { icon: '🤖', color: 'var(--text-2)' }
                const st   = statusCfg[p.status] || statusCfg.inactive
                return (
                  <div key={p.id} style={{ ...card, padding: '18px 20px', borderColor: p.is_default ? meta.color + '50' : 'var(--surface-4)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <div style={{ width: 40, height: 40, borderRadius: 10, background: meta.color + '20', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: "var(--text-xl)" }}>
                          {meta.icon}
                        </div>
                        <div>
                          <div style={{ fontSize: "var(--text-md)", fontWeight: 700 }}>{p.name}</div>
                          <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>{meta.name} · {p.default_model || t('ai.model_none')}</div>
                        </div>
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4 }}>
                        <span style={{ fontSize: "var(--text-xs)", fontWeight: 700, padding: '2px 8px', borderRadius: 20, background: st.color + '20', color: st.color, border: `1px solid ${st.color}40` }}>{st.label}</span>
                        {p.is_default && <span style={{ fontSize: "var(--text-2xs)", color: 'var(--accent)', fontWeight: 700 }}>⭐ {t('ai.default_badge')}</span>}
                      </div>
                    </div>

                    <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginBottom: 12 }}>
                      {p.has_api_key ? `🔑 ${t('ai.api_key_configured')}` : p.provider === 'ollama' ? `🦙 ${t('ai.local_no_key')}` : `⚠️ ${t('ai.no_api_key')}`}
                      {p.last_error && <span style={{ color: 'var(--danger)', marginLeft: 8 }}>· {t('common.error')}: {p.last_error.slice(0, 40)}...</span>}
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 12, padding: '10px 12px', background: 'var(--surface-1)', borderRadius: 8, fontSize: "var(--text-sm)" }}>
                      <div><span style={{ color: 'var(--text-2)' }}>{t('ai.requests')}:</span> <strong>{p.total_requests}</strong></div>
                      <div><span style={{ color: 'var(--text-2)' }}>{t('ai.total_cost')}:</span> <strong style={{ color: 'var(--warning)' }}>${p.total_cost_usd.toFixed(4)}</strong></div>
                    </div>

                    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                      <button aria-label={`${t('ai.provider_test_aria')} ${p.name}`} onClick={() => setTestModal(p)}
                        style={{ flex: 1, padding: '7px', borderRadius: 7, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--accent)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>
                        🔌 {t('ai.provider_test_action')}
                      </button>
                      {!p.is_default && (
                        <button aria-label={`${t('ai.provider_default_aria')} ${p.name}`} onClick={() => setDefault(p.id)}
                          style={{ flex: 1, padding: '7px', borderRadius: 7, border: '1px solid var(--accent-border)', background: 'transparent', color: 'var(--accent)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>
                          ⭐ {t('ai.provider_default_action')}
                        </button>
                      )}
                      <button aria-label={`${t('ai.provider_edit_aria')} ${p.name}`} onClick={() => setModal(p)}
                        style={{ padding: '7px 10px', borderRadius: 7, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>
                        {t('ai.provider_edit_action')}
                      </button>
                      <button aria-label={`${t('ai.provider_delete_action')} ${p.name}`} onClick={() => { openConfirmGlobal({ message: `${t('ai.delete_confirm')} "${p.name}"?`, onConfirm: () => del(p.id), danger: true }) }}
                        style={{ padding: '7px 10px', borderRadius: 7, border: '1px solid var(--danger-border)', background: 'transparent', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>
                        {t('ai.provider_delete_action')}
                      </button>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* STATS TAB */}
      {tab === 'stats' && (
        <div id="aihub-panel-stats" role="tabpanel" aria-labelledby="aihub-tab-stats">
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 14, marginBottom: 24 }}>
            {[
              { icon: '🤖', label: t('ai.providers_count'), value: (stats.providers || []).length, color: 'var(--accent)' },
              { icon: '💬', label: t('ai.total_requests'), value: stats.total_requests || 0, color: 'var(--success)' },
              { icon: '💰', label: t('ai.total_cost'), value: moneyFmt.format(stats.total_cost || 0), color: 'var(--warning)' },
            ].map(k => (
              <div key={k.label} style={{ ...card, padding: '18px 20px' }}>
                <div style={{ fontSize: "var(--text-2xl)", marginBottom: 8 }}>{k.icon}</div>
                <div style={{ fontSize: "var(--text-xl-em)", fontWeight: 800, color: k.color }}>{k.value}</div>
                <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>{k.label}</div>
              </div>
            ))}
          </div>

          {byModule.length > 0 && (
            <div style={card}>
              <div style={{ padding: '16px 20px 12px', borderBottom: '1px solid var(--surface-4)', fontWeight: 700, fontSize: "var(--text-md)" }}>{t('ai.module_usage')}</div>
              {byModule.map((r: any) => (
                <div key={r.module} style={{ padding: '12px 20px', borderBottom: '1px solid var(--surface-4)30', display: 'flex', justifyContent: 'space-between', fontSize: "var(--text-base)" }}>
                  <span style={{ fontWeight: 600 }}>{r.module}</span>
                  <div style={{ display: 'flex', gap: 20, color: 'var(--text-2)' }}>
                    <span>{r.calls} {t('ai.calls')}</span>
                    <span>{intFmt.format(r.tokens || 0)} {t('ai.tokens_label')}</span>
                    <span style={{ color: 'var(--warning)' }}>{moneyFmt.format(r.cost || 0)}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* OBSERVABILITY TAB */}
      {tab === 'observability' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ fontSize: "var(--text-base)", color: 'var(--text-2)' }}>Estado de salud de los modelos predictivos ITSM y BI (solo admins)</div>
            <Button onClick={() => triggerRetrain()} disabled={retraining}>
              {retraining ? '⏳ Reentrenando...' : '▶ Forzar reentrenamiento'}
            </Button>
          </div>

          {obsLoading ? <Spinner /> : !obsHealth ? (
            <div style={{ ...card, padding: '32px', textAlign: 'center', color: 'var(--text-3)' }}>
              Sin datos de observabilidad — requiere permisos de administrador
            </div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
              {[
                { key: 'itsm', label: 'Modelo ITSM', data: obsHealth.itsm },
                { key: 'bi',   label: 'Modelo BI',   data: obsHealth.bi },
              ].map(({ key, label, data }) => {
                if (!data) return null
                const statusColor = data.status === 'healthy' ? 'var(--success)' : data.status === 'attention' ? 'var(--warning)' : 'var(--text-3)'
                return (
                  <div key={key} style={{ ...card, padding: '18px 20px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                      <div style={{ fontSize: "var(--text-md)", fontWeight: 600 }}>{label}</div>
                      <span style={{ fontSize: "var(--text-xs)", padding: '2px 9px', borderRadius: 20, background: `${statusColor}18`, color: statusColor, fontWeight: 600 }}>
                        {data.status || 'unknown'}
                      </span>
                    </div>
                    {data.score != null && (
                      <div style={{ marginBottom: 10 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4, fontSize: "var(--text-sm)" }}>
                          <span style={{ color: 'var(--text-2)' }}>Score de salud</span>
                          <span style={{ fontWeight: 700, color: statusColor }}>{(data.score * 100).toFixed(0)}%</span>
                        </div>
                        <div style={{ height: 6, background: 'var(--surface-4)', borderRadius: 3, overflow: 'hidden' }}>
                          <div style={{ height: '100%', borderRadius: 3, width: `${Math.min(data.score * 100, 100)}%`, background: statusColor, transition: 'width .4s' }} />
                        </div>
                      </div>
                    )}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: "var(--text-sm)" }}>
                      {data.total_predictions != null && (
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span style={{ color: 'var(--text-3)' }}>Predicciones</span>
                          <span>{data.total_predictions}</span>
                        </div>
                      )}
                      {data.accuracy != null && (
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span style={{ color: 'var(--text-3)' }}>Precisión</span>
                          <span>{(data.accuracy * 100).toFixed(1)}%</span>
                        </div>
                      )}
                      {data.drift_detected != null && (
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span style={{ color: 'var(--text-3)' }}>Drift detectado</span>
                          <span style={{ color: data.drift_detected ? 'var(--warning)' : 'var(--success)' }}>
                            {data.drift_detected ? '⚠ Sí' : '✓ No'}
                          </span>
                        </div>
                      )}
                      {data.reason && (
                        <div style={{ marginTop: 6, padding: '6px 10px', background: 'var(--surface-3)', borderRadius: 6, color: 'var(--text-2)', lineHeight: 1.4 }}>
                          {data.reason}
                        </div>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          )}

          {obsHealth && (
            <div style={{ ...card, padding: '14px 18px', display: 'flex', alignItems: 'center', gap: 12 }}>
              <div style={{ fontSize: "var(--text-3xl)" }}>
                {obsHealth.overall_status === 'healthy' ? '✅' : obsHealth.overall_status === 'attention' ? '⚠️' : '❓'}
              </div>
              <div>
                <div style={{ fontSize: "var(--text-base)", fontWeight: 600 }}>Estado global: {obsHealth.overall_status}</div>
                <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginTop: 2 }}>
                  Score combinado: {obsHealth.overall_score != null ? `${(obsHealth.overall_score * 100).toFixed(0)}%` : '—'}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* GUIDE TAB */}
      {tab === 'guide' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          {[
            { icon: '🟠', title: t('ai.guide_anthropic'), desc: t('ai.guide_anthropic_desc'), link: PDOCS.anthropic, hint: 'sk-ant-...' },
            { icon: '🟢', title: t('ai.guide_openai'), desc: t('ai.guide_openai_desc'), link: PDOCS.openai, hint: 'sk-...' },
            { icon: '🔵', title: t('ai.guide_gemini'), desc: t('ai.guide_gemini_desc'), link: PDOCS.gemini, hint: 'AIza...' },
            { icon: '🐋', title: t('ai.guide_deepseek'), desc: t('ai.guide_deepseek_desc'), link: PDOCS.deepseek, hint: 'sk-...' },
            { icon: '⚡', title: t('ai.guide_groq'), desc: t('ai.guide_groq_desc'), link: PDOCS.groq, hint: 'gsk_...' },
            { icon: '🌪', title: t('ai.guide_mistral'), desc: t('ai.guide_mistral_desc'), link: PDOCS.mistral, hint: '...' },
            { icon: '🦙', title: t('ai.guide_ollama'), desc: t('ai.guide_ollama_desc'), link: PDOCS.ollama, hint: t('ai.no_api_key') },
            { icon: '☁️', title: t('ai.guide_azure'), desc: t('ai.guide_azure_desc'), link: PDOCS.azure, hint: `(${t('ai.azure_api_key_hint')})` },
          ].map(p => (
            <div key={p.title} style={{ ...card, padding: '18px 20px' }}>
              <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start', marginBottom: 10 }}>
                <span style={{ fontSize: "var(--text-2xl)" }}>{p.icon}</span>
                <div>
                  <div style={{ fontSize: "var(--text-md)", fontWeight: 700 }}>{p.title}</div>
                  <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginTop: 4, lineHeight: 1.5 }}>{p.desc}</div>
                </div>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 10 }}>
                <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', fontFamily: 'var(--font-mono)' }}>{p.hint}</span>
                <a href={p.link} target="_blank" rel="noreferrer" style={{ fontSize: "var(--text-sm)", color: 'var(--accent)' }}>{t('ai.get_key')} →</a>
              </div>
            </div>
          ))}
        </div>
      )}

      {modal !== null && (
        <ProviderModal
          provider={Object.keys(modal).length ? modal : null}
          catalog={catalog}
          onClose={() => setModal(null)}
        />
      )}
      {testModal && <TestModal provider={testModal} onClose={() => setTestModal(null)} />}
    </Page>
  )
}
