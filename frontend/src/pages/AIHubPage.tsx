import { PROVIDER_META } from '../constants/api'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr, localeActivo } from '../utils/helpers'
import { Fragment, useId, useState, type ChangeEvent } from 'react'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { predictiveObservabilityApi, aiProvidersApi, aiGovernanceApi, apiUrl } from '../services/api'
import { PROVIDER_DOCS } from '../constants/api'
import { Button, Spinner, Modal, Tabs, Page, Drawer } from '../components/ui'
import { useAppLang, useAppT } from '../i18n/AppLangContext'
import { Cpu, X, Search, Plus, Activity } from 'lucide-react'
import { alpha } from '../constants/theme'
import useMediaQuery from '../hooks/useMediaQuery'
import { POLL_DEFAULT_MS, STALE_DEFAULT_MS, STALE_REFERENCE_DATA_MS, STALE_SHORT_MS } from '../constants/timings'
import { AUDIT_LOG_PAGE_SIZE } from '../constants/pagination'

const PMETA = PROVIDER_META as Record<string, { name: string; icon: string; color: string }>
const PDOCS = PROVIDER_DOCS as Record<string, string>

const getStatusCfg = (t: (k: string) => string): Record<string, { label: string; color: string }> => ({
  active:   { label: t('ai.provider_status_active'), color: 'var(--success)' },
  inactive: { label: t('ai.provider_status_inactive'), color: 'var(--text-2)' },
  error:    { label: t('ai.provider_status_error'), color: 'var(--danger)' },
})

/** Proveedor tal como lo devuelve `_out` (app/api/v1/endpoints/ai_providers.py); `source: 'env'` es el del `.env`. */
interface AiProvider {
  id: string
  source?: 'env'
  name: string
  provider: string
  status: string
  is_default: boolean
  default_model?: string | null
  available_models: string[]
  api_base_url?: string | null
  has_api_key: boolean
  max_tokens?: number | null
  temperature?: number | null
  priority?: number | null
  total_requests: number
  total_cost_usd: number
  last_error?: string | null
}

interface CatalogModel { id: string; name: string; cost_in: number; cost_out: number }
interface CatalogEntry { name?: string; models?: CatalogModel[]; base_url?: string; key_hint?: string; docs_url?: string }
type ProviderCatalog = Record<string, CatalogEntry>

interface ProviderForm {
  name: string
  provider: string
  api_key: string
  api_base_url: string
  default_model: string
  max_tokens: number
  temperature: number
  is_default: boolean
  priority: number
}

interface ModuleUsage { module: string; calls?: number; tokens?: number; cost?: number }
interface AiStats { providers?: unknown[]; total_requests?: number; total_cost?: number; by_module?: ModuleUsage[] }

interface DiagProvider {
  id: string
  name: string
  provider_type?: string
  status: string
  latency_ms?: number | null
  models_found?: number
  error?: string | null
}
interface Diagnostics { healthy?: number; total?: number; error?: number; warning?: number; providers?: DiagProvider[] }

interface AiPolicy { id: string; name: string; is_active?: boolean; scope?: string; action?: string; applies_to_roles?: string[] }
interface AiAuditEntry {
  id: string
  evaluated_at?: string | null
  module?: string | null
  scope?: string
  was_blocked?: boolean
  action_taken?: string | null
  pii_types_found?: string[]
}

/** Detalle de error de FastAPI cuando es una lista de validación. */
interface ValidationDetail { msg?: string }

const card = { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12 }
const fs = { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', width: '100%' }
const ls = { fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', display: 'block', marginBottom: 5 }

function ProviderModal({ provider, catalog, onClose }: { provider: Partial<AiProvider> | null; catalog: ProviderCatalog; onClose: () => void }) {
  const t = useAppT()
  const idPrefix = useId()
  const qc = useQueryClient()
  const toast = useToast()
  const isEdit = !!provider?.id
  const [providerType, setProviderType] = useState(provider?.provider || 'anthropic')
  const [liveModels, setLiveModels] = useState<string[]>(provider?.available_models || [])
  const [form, setForm] = useState<ProviderForm>({
    name: provider?.name || '',
    provider: provider?.provider || 'anthropic',
    api_key: '',
    api_base_url: provider?.api_base_url || '',
    default_model: provider?.default_model || '',
    max_tokens: provider?.max_tokens || 2000,
    temperature: provider?.temperature ?? 0.7,
    is_default: provider?.is_default || false,
    priority: provider?.priority ?? 100,
  })
  // Probar / descubrir con lo escrito, sin guardar (revisión 2026-11, de contecmind).
  const [probando, setProbando] = useState(false)
  const [descubriendo, setDescubriendo] = useState(false)
  async function probarSinGuardar() {
    setProbando(true)
    try {
      const r = await aiProvidersApi.testConfig(form)
      toast.success(`Responde (${r.data?.latency_ms ?? '?'} ms, ${r.data?.model ?? form.default_model})`)
    } catch (e) { toast.error(extractErr(e, 'No responde con esta configuración')) }
    finally { setProbando(false) }
  }
  async function descubrirModelos() {
    setDescubriendo(true)
    try {
      const r = await aiProvidersApi.discoverModels(form)
      const lista = Array.isArray(r.data?.models) ? r.data.models : []
      setLiveModels(lista)
      toast.success(`${lista.length} modelos disponibles`)
    } catch (e) { toast.error(extractErr(e, 'No se pudieron obtener los modelos')) }
    finally { setDescubriendo(false) }
  }
  // Los campos numéricos guardan el texto del input, como siempre: el backend lo convierte.
  const s = (k: string) => (e: ChangeEvent<HTMLInputElement>) => setForm(f => ({ ...f, [k]: e.target.value }))

  const catEntry: CatalogEntry = catalog[providerType] || {}
  const catalogModels = catEntry.models || []
  const models: CatalogModel[] = liveModels.length > 0
    ? liveModels.map(id => {
      const known = catalogModels.find(m => m.id === id)
      return known || { id, name: id, cost_in: 0, cost_out: 0 }
    })
    : catalogModels

  const { mutate, isPending } = useMutation({
    mutationFn: (d: ProviderForm) => isEdit ? aiProvidersApi.update(provider.id, d) : aiProvidersApi.create(d),
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

  const handleProviderChange = (type: string) => {
    setProviderType(type)
    setLiveModels([])
    const cat: CatalogEntry = catalog[type] || {}
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
    <Drawer onClose={onClose} ariaLabel={title} width={640} zIndex={200}>
        {/* Drawer header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '14px 20px', borderBottom: '1px solid var(--surface-4)', flexShrink: 0 }}>
          <span style={{ fontSize: "var(--text-lg)", fontWeight: 700, color: 'var(--text-1)' }}>{title}</span>
          <button onClick={onClose} aria-label="Cerrar" style={{ background: 'none', border: 'none', cursor: 'pointer',
            color: 'var(--text-3)', display: 'flex', padding: 4, borderRadius: 'var(--radius-sm)' }}>
            <X size={16} />
          </button>
        </div>
        {/* Body */}
        <div style={{ padding: '20px', overflowY: 'auto', flex: 1, minHeight: 0 }}>
      <form onSubmit={e => { e.preventDefault(); mutate(form) }}>
      {/* Selector de proveedor */}
      {!isEdit && (
        <div className="u-mb-20">
          <label style={ls}>{t('ai.provider')}</label>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8 }}>
            {Object.entries(PMETA).map(([key, meta]) => (
              <button key={key} type="button" aria-pressed={providerType === key} aria-label={`${t('ai.select_provider')} ${meta.name}`} onClick={() => handleProviderChange(key)}
                style={{ padding: '10px 8px', borderRadius: 8, border: `2px solid ${providerType === key ? alpha(meta.color, '80') : 'var(--surface-4)'}`, background: providerType === key ? alpha(meta.color, '15') : 'transparent', cursor: 'pointer', fontFamily: 'inherit', transition: 'all 0.15s' }}>
                <div style={{ fontSize: "var(--text-lg-em)", marginBottom: 4 }}>{meta.icon}</div>
                <div style={{ fontSize: "var(--text-xs)", fontWeight: 600, color: providerType === key ? meta.color : 'var(--text-2)' }}>{meta.name}</div>
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="u-grid2-14">
        <div className="u-col-full">
          <label id={`${idPrefix}-name-et`} htmlFor={`${idPrefix}-name`} style={ls}>{t('ai.config_name')} *</label>
          <input id={`${idPrefix}-name`} aria-labelledby={`${idPrefix}-name-et`} value={form.name} onChange={s('name')} style={fs} placeholder={`${catEntry.name || ''} — ${t('ai.config_name_placeholder')}`} />
        </div>

        {providerType !== 'ollama' && (
          <div className="u-col-full">
            <label id={`${idPrefix}-api-key-et`} htmlFor={`${idPrefix}-api-key`} style={ls}>
              API Key {catEntry.key_hint && <span style={{ color: 'var(--text-3)', fontWeight: 400, textTransform: 'none' }}>({catEntry.key_hint})</span>}
            </label>
            <input id={`${idPrefix}-api-key`} aria-labelledby={`${idPrefix}-api-key-et`} type="password" value={form.api_key} onChange={s('api_key')} style={fs}
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
          <div className="u-col-full">
            <label id={`${idPrefix}-api-base-url-et`} htmlFor={`${idPrefix}-api-base-url`} style={ls}>{t('ai.base_url')} {providerType === 'ollama' ? `(${t('ai.base_url_example')} http://localhost:11434)` : ''}</label>
            <input id={`${idPrefix}-api-base-url`} aria-labelledby={`${idPrefix}-api-base-url-et`} value={form.api_base_url} onChange={s('api_base_url')} style={fs}
              placeholder={catEntry.base_url || 'https://...'} />
          </div>
        )}

        <div>
          <label id={`${idPrefix}-default-model-et`} htmlFor={`${idPrefix}-default-model`} style={ls}>{t('ai.default_model')}</label>
          {models.length > 0 ? (
            <>
              <select
                id={`${idPrefix}-default-model`} aria-labelledby={`${idPrefix}-default-model-et`}
                value={models.some(m => m.id === form.default_model) ? form.default_model : '__custom__'}
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
                {models.map(m => (
                  <option key={m.id} value={m.id}>
                    {m.name} {m.cost_in > 0 ? `· $${m.cost_in}/M in` : '· Gratis'}
                  </option>
                ))}
                <option value="__custom__">✏️ {t('ai.custom_model')}</option>
              </select>
              {!models.some(m => m.id === form.default_model) && (
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
            <input id={`${idPrefix}-default-model`} aria-labelledby={`${idPrefix}-default-model-et`} value={form.default_model} onChange={s('default_model')} style={fs}
              placeholder={t('ai.model_name_placeholder')} />
          )}
          {(!isEdit || form.api_key || providerType === 'ollama') && (
            <div style={{ marginTop: 8 }}>
              <Button variant="secondary" onClick={() => { void descubrirModelos() }} disabled={descubriendo} loading={descubriendo}>
                {descubriendo ? 'Buscando modelos…' : 'Descubrir modelos con esta clave'}
              </Button>
            </div>
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
          <label id={`${idPrefix}-max-tokens-et`} htmlFor={`${idPrefix}-max-tokens`} style={ls}>{t('ai.max_response_tokens')}</label>
          <input id={`${idPrefix}-max-tokens`} aria-labelledby={`${idPrefix}-max-tokens-et`} type="number" value={form.max_tokens} onChange={s('max_tokens')} style={fs} />
        </div>

        <div>
          <label id={`${idPrefix}-temperature-et`} htmlFor={`${idPrefix}-temperature`} style={ls}>{t('ai.temperature')}</label>
          <input id={`${idPrefix}-temperature`} aria-labelledby={`${idPrefix}-temperature-et`} type="number" step="0.1" min="0" max="2" value={form.temperature} onChange={s('temperature')} style={fs} />
        </div>

        <div>
          <label id={`${idPrefix}-priority-et`} htmlFor={`${idPrefix}-priority`} style={ls}>Orden de respaldo</label>
          <input id={`${idPrefix}-priority`} aria-labelledby={`${idPrefix}-priority-et`} type="number" min="0" value={form.priority} onChange={s('priority')} style={fs}
            title="Si el proveedor elegido falla, se prueban los demás de menor a mayor" />
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10, paddingTop: 20 }}>
          <input type="checkbox" id={`${idPrefix}-is-default`} aria-labelledby={`${idPrefix}-is-default-et`} checked={form.is_default}
            onChange={e => setForm(f => ({ ...f, is_default: e.target.checked }))} />
          <label id={`${idPrefix}-is-default-et`} htmlFor={`${idPrefix}-is-default`} style={{ fontSize: "var(--text-base)", cursor: 'pointer' }}>
            {t('ai.set_global_default')}
          </label>
        </div>
      </div>

      {/* Info del proveedor seleccionado */}
      {models.length > 0 && (
        <div style={{ marginTop: 16, padding: '12px 14px', background: 'var(--surface-1)', borderRadius: 8, fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>
          <div style={{ fontWeight: 700, marginBottom: 8, color: 'var(--text-1)' }}>{t('ai.available_models')}:</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 6, maxHeight: 220, overflowY: 'auto', paddingRight: 4 }}>
            {models.map(m => (
              <div key={m.id} style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span className="u-text2">{m.name}</span>
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
          <Button variant="secondary" type="button" onClick={() => { void probarSinGuardar() }} disabled={probando || !form.provider} loading={probando}>
            Probar sin guardar
          </Button>
          <Button onClick={() => mutate(form)} disabled={isPending || !form.name || !form.provider} loading={isPending}>
            {isPending ? t('common.saving') : isEdit ? t('ai.save_changes') : t('ai.add_provider_action')}
          </Button>
        </div>
    </Drawer>
  )
}

function TestModal({ provider, onClose }: { provider: AiProvider; onClose: () => void }) {
  const t = useAppT()
  const [result, setResult] = useState<{ ok?: boolean; error?: string; response?: string; latency_ms?: number; model?: string } | null>(null)
  const [testing, setTesting] = useState(false)

  const runTest = async () => {
    setTesting(true)
    setResult(null)
    try {
      const res = provider.source === 'env' ? await aiProvidersApi.testEnv() : await aiProvidersApi.test(provider.id)
      setResult(res.data)
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: unknown } }; message?: string }
      const raw = err?.response?.data?.detail
      setResult({ ok: false, error: Array.isArray(raw) ? raw.map((d: ValidationDetail) => d.msg).join(', ') : ((raw as string) || err.message) })
    } finally {
      setTesting(false)
    }
  }

  return (
    <Modal open onClose={onClose} title={`${t('ai.testing_provider')} — ${provider.name}`} width={480}>
      <p className="u-text2-base-mb20">
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
              <div className="u-text2-sm">{t('ai.test_response')}: &quot;{result.response}&quot;</div>
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
  const traducir = useAppT()
  // Read-only viewer del audit log + stats. El CRUD de policies se gestiona
  // vía API directa hasta que se complete la UI dedicada (decisión ARCH).
  // Por el cliente API (refresco de sesión y desenvoltorio {data,meta}/{items,meta}).
  // Si falla se pinta vacío, como antes.
  // TODO: añadir queryKeys.aiGovernance.* en constants/queryKeys.js
  const { data: policiesRaw = [], isLoading: loadingPolicies } = useQuery<AiPolicy[] | { items?: AiPolicy[] }>({
    queryKey: ['ai-governance', 'policies'],
    queryFn: () => aiGovernanceApi.policies().then(r => r.data).catch(() => []),
    staleTime: STALE_DEFAULT_MS,
  })
  const { data: auditLogRaw = [], isLoading: loadingAudit } = useQuery<AiAuditEntry[] | { items?: AiAuditEntry[] }>({
    queryKey: ['ai-governance', 'audit-log', { limit: AUDIT_LOG_PAGE_SIZE }],
    queryFn: () => aiGovernanceApi.auditLog({ limit: AUDIT_LOG_PAGE_SIZE }).then(r => r.data).catch(() => []),
    staleTime: STALE_SHORT_MS,
  })
  const { data: stats = null, isLoading: loadingStats } = useQuery({
    queryKey: ['ai-governance', 'audit-log-stats'],
    queryFn: () => aiGovernanceApi.auditLogStats().then(r => r.data).catch(() => null),
    staleTime: STALE_DEFAULT_MS,
  })

  const policies = Array.isArray(policiesRaw) ? policiesRaw : (policiesRaw.items || [])
  const auditLog = Array.isArray(auditLogRaw) ? auditLogRaw : (auditLogRaw.items || [])
  const loading = loadingPolicies || loadingAudit || loadingStats

  if (loading) return <div style={{ padding: 24 }}><Spinner /></div>

  return (
    <div id="aihub-panel-governance" role="tabpanel" className="u-stack-20">
      {/* Stats summary */}
      {stats && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(140px, 100%), 1fr))', gap: 12 }}>
          {[
            { label: 'Evaluaciones', value: stats.total_evaluations || 0, color: 'var(--accent)' },
            // Auditoría 2026-11: leía blocked/redacted/pii_total, que la API no
            // devuelve; las tarjetas salían siempre a 0.
            { label: 'Bloqueadas', value: stats.total_blocked || 0, color: 'var(--danger)' },
            { label: 'Redacted', value: stats.total_redacted || 0, color: 'var(--warning)' },
            { label: 'PII detectado', value: (stats.top_pii_types || []).reduce((n: number, x: { count?: number }) => n + (x.count || 0), 0), color: 'var(--purple)' },
          ].map(k => (
            <div key={k.label} style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-md)', padding: '14px 18px' }}>
              <div style={{ fontSize: 'var(--text-xl)', fontWeight: 800, color: k.color }}>{k.value}</div>
              <div className="u-text2-xs">{k.label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Policies list */}
      <div className="ds-card ds-card--plano">
        <div style={{ padding: '12px 18px', borderBottom: '1px solid var(--surface-4)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
          <div style={{ fontWeight: 700 }}>{traducir('aihub.politicas_configuradas')}{policies.length})</div>
          <div className="u-text3-xs">
            CRUD via <code>POST {apiUrl('/ai-governance/policies')}</code> · UI completa pendiente
          </div>
        </div>
        {policies.length === 0 ? (
          <div style={{ padding: 24, textAlign: 'center', color: 'var(--text-3)', fontSize: 'var(--text-sm)' }}>
            {traducir('aihub.sin_policies_activas_los_guardrails_deteccion_pii')}
          </div>
        ) : (
          <div style={{ maxHeight: 240, overflowY: 'auto' }}>
            {policies.map(p => (
              <div key={p.id} style={{ padding: '10px 18px', borderBottom: '1px solid var(--surface-4)', fontSize: 'var(--text-sm)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span className="u-600">{p.name}</span>
                  <span style={{ fontSize: 'var(--text-xs)', padding: '2px 8px', borderRadius: 4, background: p.is_active ? 'var(--success-bg)' : 'var(--surface-3)', color: p.is_active ? 'var(--success)' : 'var(--text-3)' }}>
                    {p.is_active ? 'Activa' : 'Inactiva'}
                  </span>
                </div>
                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', marginTop: 2, overflowWrap: 'anywhere' }}>
                  scope={p.scope} · action={p.action} · roles=[{(p.applies_to_roles || []).join(',')}]
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Audit log */}
      <div className="ds-card ds-card--plano">
        <div style={{ padding: '12px 18px', borderBottom: '1px solid var(--surface-4)', fontWeight: 700 }}>
          {traducir('aihub.audit_log_ultimas_50_evaluaciones')}
        </div>
        {auditLog.length === 0 ? (
          <div style={{ padding: 24, textAlign: 'center', color: 'var(--text-3)' }}>{traducir('aihub.sin_actividad_reciente')}</div>
        ) : (
          <div style={{ maxHeight: 360, overflowY: 'auto' }}>
            {auditLog.map(l => (
              <div key={l.id} style={{ padding: '8px 18px', borderBottom: '1px solid var(--surface-4)', fontSize: 'var(--text-xs)', display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'center' }}>
                <span style={{ minWidth: 100, color: 'var(--text-3)' }}>{(l.evaluated_at || '').slice(0, 16)}</span>
                <span style={{ minWidth: 80, fontWeight: 600 }}>{l.module || '—'}</span>
                <span style={{ minWidth: 60 }}>{l.scope}</span>
                <span style={{ padding: '1px 6px', borderRadius: 4, background: l.was_blocked ? 'var(--danger-bg)' : l.action_taken === 'redacted' ? 'var(--warning-bg)' : 'var(--surface-3)', color: l.was_blocked ? 'var(--danger)' : l.action_taken === 'redacted' ? 'var(--warning)' : 'var(--text-2)' }}>
                  {l.action_taken || 'none'}
                </span>
                {(l.pii_types_found || []).length > 0 && (
                  <span className="u-warning">PII: {l.pii_types_found.join(',')}</span>
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
  const isNarrow = useMediaQuery('(max-width: 900px)')
  const traducir = useAppT()
  const { lang } = useAppLang()
  const t = useAppT()
  const statusCfg = getStatusCfg(t)
  const toast = useToast()
  const qc = useQueryClient()
  // `{}` abre el alta; un proveedor abre la edición.
  const [modal, setModal] = useState<Partial<AiProvider> | null>(null)
  const [testModal, setTestModal] = useState<AiProvider | null>(null)
  const [tab, setTab] = useState('providers')
  const [diagResults, setDiagResults] = useState<Diagnostics | null>(null)

  const { mutate: importarEntorno } = useMutation({
    mutationFn: () => aiProvidersApi.importEnv(),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['ai-providers'] }); toast.success('Importado: ya se puede editar') },
    onError: e => toast.error(extractErr(e, 'No se pudo importar')),
  })
  const { data: providers = [], isLoading } = useQuery<AiProvider[]>({
    queryKey: ['ai-providers'],
    queryFn: () => aiProvidersApi.list().then(r => r.data),
    select: d => (Array.isArray(d) ? d : []),
  })
  const { data: catalog = {} } = useQuery<ProviderCatalog>({
    queryKey: ['ai-providers-catalog'],
    queryFn: () => aiProvidersApi.catalog().then(r => r.data),
    staleTime: Infinity,
  })
  const { data: stats = {} } = useQuery<AiStats>({
    queryKey: ['ai-stats'],
    queryFn: () => aiProvidersApi.stats().then(r => r.data),
    enabled: tab === 'stats',
  })
  const { data: obsHealth, isLoading: obsLoading } = useQuery({
    queryKey: ['predictive-obs-health'],
    queryFn: () => predictiveObservabilityApi.health({}).then(r => r.data).catch(() => null),
    enabled: tab === 'observability',
    staleTime: STALE_REFERENCE_DATA_MS,
  })
  const { mutate: triggerRetrain, isPending: retraining } = useMutation({
    mutationFn: () => predictiveObservabilityApi.triggerRetrain(),
    onSuccess: () => { toast.success('Ciclo de reentrenamiento completado'); qc.invalidateQueries({ queryKey: ['predictive-obs-health'] }) },
    onError: e => toast.error(extractErr(e, 'Error al reentrenar')),
  })

  const { mutate: setDefault } = useMutation({
    mutationFn: (id: string) => aiProvidersApi.setDefault(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['ai-providers'] }),
    onError: e => toast.error(extractErr(e, t('ai.reset_error'))),
  })
  const { mutate: del } = useMutation({
    mutationFn: (id: string) => aiProvidersApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['ai-providers'] }),
    onError: e => toast.error(extractErr(e, t('ai.generic_error'))),
  })

  const { mutate: diagnoseAll, isPending: diagnosing } = useMutation({
    mutationFn: () => aiProvidersApi.diagnostics().then(r => r.data),
    onSuccess: (data: Diagnostics) => {
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

  const defaultProvider = providers.find(p => p.is_default)
  const byModule = stats.by_module || []
  // USD a proposito (auditoria 2026-11, #18): los proveedores de IA facturan y
  // publican precios en dolares y el backend guarda el gasto en `*_cost_usd`
  // (presupuesto AI_DAILY_BUDGET_USD). Convertirlo a la moneda de la empresa
  // seria inventar un tipo de cambio.
  const moneyFmt = new Intl.NumberFormat(localeActivo(lang), { style: 'currency', currency: 'USD', minimumFractionDigits: 4, maximumFractionDigits: 4 })
  const intFmt = new Intl.NumberFormat(localeActivo(lang))

  return (
    <Page
      icon={<Cpu size={18} />}
      title={t('ai.hub_title')}
      subtitle={t('ai.hub_subtitle')}
      rightActions={(
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-2)' }}>
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
      <GastoDeHoy />
      {/* Tabs */}
      <Tabs
        items={[
          { id: 'providers',     label: t('ai.providers') },
          { id: 'routing',       label: 'Por función' },
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
      {tab === 'routing' && <RoutingTab providers={providers} />}

      {/* PROVIDERS TAB */}
      {tab === 'providers' && (
        <div id="aihub-panel-providers" role="tabpanel" aria-labelledby="aihub-tab-providers">

          {/* Panel de diagnóstico */}
          {diagResults && (
            <div style={{ ...card, padding: '16px 20px', marginBottom: 20, borderColor: diagResults.error > 0 ? 'var(--danger)' : diagResults.warning > 0 ? 'var(--warning)' : 'var(--success)' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, marginBottom: 12 }}>
                <div className="u-md-700">
                  {traducir('aihub.diagnostico')} {diagResults.healthy}/{diagResults.total} operativos
                </div>
                <button onClick={() => setDiagResults(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-2)', fontSize: "var(--text-lg)" }}>✕</button>
              </div>
              <div className="u-stack-8">
                {(diagResults.providers || []).map(pr => {
                  const dotKind = pr.status === 'ok' ? 'success' : pr.status === 'warning' ? 'warning' : 'danger'
                  return (
                    <div key={pr.id} style={{ display: 'flex', alignItems: 'flex-start', gap: 10, fontSize: "var(--text-base)" }}>
                      <span className={`ds-status-dot ds-status-dot--${dotKind}`} style={{ marginTop: 7, flexShrink: 0 }} />
                      <div className="u-flex1-min0">
                        <span className="u-600">{pr.name}</span>
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
            <div style={{ ...card, padding: '16px 20px', marginBottom: 20, borderColor: alpha(PMETA[defaultProvider.provider]?.color, '50') || 'var(--surface-4)', background: alpha(PMETA[defaultProvider.provider]?.color, '08') || 'var(--surface-2)' }}>
              <div className="u-row-center-12">
                <span style={{ fontSize: "var(--text-3xl)" }}>{PMETA[defaultProvider.provider]?.icon}</span>
                <div className="u-min0">
                  <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{t('ai.provider_active_default')}</div>
                  <div style={{ fontSize: "var(--text-lg)", fontWeight: 800 }}>{defaultProvider.name}</div>
                  <div className="u-text2-sm">{t('ai.model_label')}: {defaultProvider.default_model} · {intFmt.format(defaultProvider.total_requests || 0)} {t('ai.requests').toLowerCase()} · {moneyFmt.format(defaultProvider.total_cost_usd || 0)} {t('ai.spent')}</div>
                </div>
              </div>
            </div>
          )}

          {isLoading ? <Spinner /> : providers.length === 0 ? (
            <div style={{ ...card, padding: '48px 24px', textAlign: 'center' }}>
              <div className="u-empty-icon">🤖</div>
              <div style={{ fontSize: "var(--text-lg-em)", fontWeight: 700, marginBottom: 8 }}>{t('ai.no_providers_title')}</div>
              <div style={{ fontSize: "var(--text-md)", color: 'var(--text-2)', marginBottom: 24, maxWidth: 500, margin: '0 auto 24px' }}>
                {t('ai.no_providers_desc')}
              </div>
              <Button onClick={() => setModal({})}><Plus size={13} /> {t('ai.add_first_provider')}</Button>
            </div>
          ) : (
            <div data-export-table="ai-providers-list" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(min(320px, 100%), 1fr))', gap: 14 }}>
              {providers.map(p => {
                const meta: { name?: string; icon: string; color: string } = PMETA[p.provider] || { icon: '🤖', color: 'var(--text-2)' }
                const st   = statusCfg[p.status] || statusCfg.inactive
                return (
                  <div key={p.id} style={{ ...card, padding: '18px 20px', borderColor: p.is_default ? alpha(meta.color, '50') : 'var(--surface-4)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, marginBottom: 12 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
                        <div style={{ width: 40, height: 40, borderRadius: 'var(--radius-md)', background: alpha(meta.color, '20'), display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: "var(--text-xl)" }}>
                          {meta.icon}
                        </div>
                        <div>
                          <div className="u-md-700">{p.name}</div>
                          <div className="u-text2-xs">{meta.name} · {p.default_model || t('ai.model_none')}</div>
                        </div>
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4 }}>
                        <span style={{ fontSize: "var(--text-xs)", fontWeight: 700, padding: '2px 8px', borderRadius: 20, background: alpha(st.color, '20'), color: st.color, border: `1px solid ${alpha(st.color, '40')}` }}>{st.label}</span>
                        {p.is_default && <span style={{ fontSize: "var(--text-2xs)", color: 'var(--accent)', fontWeight: 700 }}>⭐ {t('ai.default_badge')}</span>}
                        {p.source === 'env' && <span title="Configurado en el fichero .env del servidor; se usa si no hay ninguno en la aplicación" style={{ fontSize: "var(--text-2xs)", color: 'var(--text-2)', fontWeight: 700 }}>Desde .env</span>}
                      </div>
                    </div>

                    <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginBottom: 12 }}>
                      {p.has_api_key ? `🔑 ${t('ai.api_key_configured')}` : p.provider === 'ollama' ? `🦙 ${t('ai.local_no_key')}` : `⚠️ ${t('ai.no_api_key')}`}
                      {p.last_error && <span style={{ color: 'var(--danger)', marginLeft: 8 }}>· {t('common.error')}: {p.last_error.slice(0, 40)}...</span>}
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 12, padding: '10px 12px', background: 'var(--surface-1)', borderRadius: 8, fontSize: "var(--text-sm)" }}>
                      <div><span className="u-text2">{t('ai.requests')}:</span> <strong>{p.total_requests}</strong></div>
                      <div><span className="u-text2">{t('ai.total_cost')}:</span> <strong className="u-warning">{moneyFmt.format(Number(p.total_cost_usd || 0))}</strong></div>
                    </div>

                    <div className="u-wrap-6">
                      <button aria-label={`${t('ai.provider_test_aria')} ${p.name}`} onClick={() => setTestModal(p)}
                        style={{ flex: 1, padding: '7px', borderRadius: 7, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--accent)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>
                        🔌 {t('ai.provider_test_action')}
                      </button>
                      {p.source === 'env' && (
                        <button aria-label={`Importar ${p.name} a la aplicación`} onClick={() => importarEntorno()}
                          title="Lo crea como proveedor de la aplicación (clave cifrada) para poder editarlo"
                          style={{ flex: 1, padding: '7px', borderRadius: 7, border: '1px solid var(--accent-border)', background: 'transparent', color: 'var(--accent)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>
                          ⬇ Importar a la aplicación
                        </button>
                      )}
                      {p.source !== 'env' && !p.is_default && (
                        <button aria-label={`${t('ai.provider_default_aria')} ${p.name}`} onClick={() => setDefault(p.id)}
                          style={{ flex: 1, padding: '7px', borderRadius: 7, border: '1px solid var(--accent-border)', background: 'transparent', color: 'var(--accent)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>
                          ⭐ {t('ai.provider_default_action')}
                        </button>
                      )}
                      {p.source !== 'env' && <>
                      <button aria-label={`${t('ai.provider_edit_aria')} ${p.name}`} onClick={() => setModal(p)}
                        style={{ padding: '7px 10px', borderRadius: 7, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>
                        {t('ai.provider_edit_action')}
                      </button>
                      <button aria-label={`${t('ai.provider_delete_action')} ${p.name}`} onClick={() => { openConfirmGlobal({ message: `${t('ai.delete_confirm')} "${p.name}"?`, onConfirm: () => del(p.id), danger: true }) }}
                        style={{ padding: '7px 10px', borderRadius: 7, border: '1px solid var(--danger-border)', background: 'transparent', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>
                        {t('ai.provider_delete_action')}
                      </button>
                      </>}
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
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(min(200px, 100%), 1fr))', gap: 14, marginBottom: 24 }}>
            {[
              { icon: '🤖', label: t('ai.providers_count'), value: (stats.providers || []).length, color: 'var(--accent)' },
              { icon: '💬', label: t('ai.total_requests'), value: stats.total_requests || 0, color: 'var(--success)' },
              { icon: '💰', label: t('ai.total_cost'), value: moneyFmt.format(stats.total_cost || 0), color: 'var(--warning)' },
            ].map(k => (
              <div key={k.label} style={{ ...card, padding: '18px 20px' }}>
                <div style={{ fontSize: "var(--text-2xl)", marginBottom: 8 }}>{k.icon}</div>
                <div style={{ fontSize: "var(--text-xl-em)", fontWeight: 800, color: k.color }}>{k.value}</div>
                <div className="u-text2-sm">{k.label}</div>
              </div>
            ))}
          </div>

          {byModule.length > 0 && (
            <div style={card}>
              <div style={{ padding: '16px 20px 12px', borderBottom: '1px solid var(--surface-4)', fontWeight: 700, fontSize: "var(--text-md)" }}>{t('ai.module_usage')}</div>
              {byModule.map(r => (
                <div key={r.module} style={{ padding: '12px 20px', borderBottom: '1px solid color-mix(in srgb, var(--surface-4) 19%, transparent)', display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8, fontSize: "var(--text-base)" }}>
                  <span className="u-600">{r.module}</span>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 20, color: 'var(--text-2)' }}>
                    <span>{r.calls} {t('ai.calls')}</span>
                    <span>{intFmt.format(r.tokens || 0)} {t('ai.tokens_label')}</span>
                    <span className="u-warning">{moneyFmt.format(r.cost || 0)}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* OBSERVABILITY TAB */}
      {tab === 'observability' && (
        <div className="u-stack-16">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
            <div className="u-text2-base">{traducir('aihub.estado_de_salud_de_los_modelos_predictivos')}</div>
            <Button onClick={() => triggerRetrain()} disabled={retraining}>
              {retraining ? '⏳ Reentrenando...' : '▶ Forzar reentrenamiento'}
            </Button>
          </div>

          {obsLoading ? <Spinner /> : !obsHealth ? (
            <div style={{ ...card, padding: '32px', textAlign: 'center', color: 'var(--text-3)' }}>
              {traducir('aihub.sin_datos_de_observabilidad_requiere_permisos_de')}
            </div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: isNarrow ? 'minmax(0, 1fr)' : '1fr 1fr', gap: 16 }}>
              {[
                { key: 'itsm', label: 'Modelo ITSM', data: obsHealth.itsm },
                { key: 'bi',   label: 'Modelo BI',   data: obsHealth.bi },
              ].map(({ key, label, data }) => {
                if (!data) return null
                const statusColor = data.status === 'healthy' ? 'var(--success)' : data.status === 'attention' ? 'var(--warning)' : 'var(--text-3)'
                return (
                  <div key={key} style={{ ...card, padding: '18px 20px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                      <div className="u-md-600">{label}</div>
                      <span style={{ fontSize: "var(--text-xs)", padding: '2px 9px', borderRadius: 20, background: alpha(statusColor, '18'), color: statusColor, fontWeight: 600 }}>
                        {data.status || 'unknown'}
                      </span>
                    </div>
                    {data.score != null && (
                      <div className="u-mb-10">
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4, fontSize: "var(--text-sm)" }}>
                          <span className="u-text2">{traducir('aihub.score_de_salud')}</span>
                          <span style={{ fontWeight: 700, color: statusColor }}>{(data.score * 100).toFixed(0)}%</span>
                        </div>
                        <div style={{ height: 6, background: 'var(--surface-4)', borderRadius: 3, overflow: 'hidden' }}>
                          <div style={{ height: '100%', borderRadius: 3, width: `${Math.min(data.score * 100, 100)}%`, background: statusColor, transition: 'width .4s' }} />
                        </div>
                      </div>
                    )}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: "var(--text-sm)" }}>
                      {/* Auditoría 2026-11: leía total_predictions/accuracy, que no
                          existen; la API da samples, severity_accuracy y mae_minutes. */}
                      {(data.samples ?? data.total_predictions) != null && (
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span className="u-text3">Predicciones</span>
                          <span>{data.samples ?? data.total_predictions}</span>
                        </div>
                      )}
                      {(data.severity_accuracy ?? data.accuracy) != null && (
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span className="u-text3">{traducir('aihub.precision')}</span>
                          <span>{((data.severity_accuracy ?? data.accuracy) * 100).toFixed(1)}%</span>
                        </div>
                      )}
                      {data.mae_minutes != null && (
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span className="u-text3">MAE</span>
                          <span>{data.mae_minutes} min</span>
                        </div>
                      )}
                      {data.status && (
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span className="u-text3">Estado</span>
                          <span>{data.status}</span>
                        </div>
                      )}
                      {data.drift_detected != null && (
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <span className="u-text3">Drift detectado</span>
                          <span style={{ color: data.drift_detected ? 'var(--warning)' : 'var(--success)' }}>
                            {data.drift_detected ? '⚠ Sí' : '✓ No'}
                          </span>
                        </div>
                      )}
                      {data.reason && (
                        <div style={{ marginTop: 6, padding: '6px 10px', background: 'var(--surface-3)', borderRadius: 'var(--radius-sm)', color: 'var(--text-2)', lineHeight: 1.4 }}>
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
                <div className="u-base-600">Estado global: {obsHealth.overall_status}</div>
                <div className="u-text2-sm-mt2">
                  Score combinado: {obsHealth.overall_score != null ? `${(obsHealth.overall_score * 100).toFixed(0)}%` : '—'}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* GUIDE TAB */}
      {tab === 'guide' && (
        <div style={{ display: 'grid', gridTemplateColumns: isNarrow ? 'minmax(0, 1fr)' : '1fr 1fr', gap: 16 }}>
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
                  <div className="u-md-700">{p.title}</div>
                  <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginTop: 4, lineHeight: 1.5 }}>{p.desc}</div>
                </div>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8, marginTop: 10 }}>
                <span className="u-text3-mono-xs">{p.hint}</span>
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


/** Proveedor y modelo por función (revisión 2026-11, de contecmind). Vacío = el proveedor por defecto. */
function RoutingTab({ providers }: { providers: AiProvider[] }) {
  const isNarrow = useMediaQuery('(max-width: 900px)')
  const qc = useQueryClient()
  const toast = useToast()
  const { data } = useQuery({ queryKey: ['ai-routing'], queryFn: () => aiProvidersApi.getRouting().then(r => r.data) })
  const [rutas, setRutas] = useState<Record<string, { provider_id?: string | null; model?: string | null }> | null>(null)
  const actuales = rutas ?? data?.routes ?? {}
  const { mutate: guardar, isPending } = useMutation({
    mutationFn: () => aiProvidersApi.saveRouting(actuales),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['ai-routing'] }); setRutas(null); toast.success('Guardado') },
    onError: e => toast.error(extractErr(e, 'No se pudo guardar')),
  })
  const cambiar = (k: string, campo: 'provider_id' | 'model', v: string) =>
    setRutas({ ...actuales, [k]: { ...(actuales[k] || {}), [campo]: v || null } })
  return (
    <div style={{ maxWidth: 900 }}>
      <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text-2)', margin: '0 0 12px' }}>
        Qué proveedor y modelo usa cada función. Sin elegir, la función usa el proveedor por defecto; si el elegido
        falla o está apartado por errores, se cae al por defecto y luego al orden de respaldo.
      </p>
      <div style={{ display: 'grid', gridTemplateColumns: isNarrow ? 'minmax(0, 1fr) minmax(0, 1fr)' : 'minmax(220px, 1.4fr) 1fr 1fr', gap: 8, alignItems: 'center' }}>
        {(data?.modules || []).map((m: { key: string; label: string }) => {
          const ruta = actuales[m.key] || {}
          const prov = providers.find(p => p.id === ruta.provider_id)
          const lista = `modelos-${m.key}`
          return (
            <Fragment key={m.key}>
              <label id={`ruta-${m.key}-et`} htmlFor={`ruta-${m.key}`} style={{ fontSize: 'var(--text-sm)', color: 'var(--text-1)', ...(isNarrow ? { gridColumn: '1 / -1', marginTop: 6 } : {}) }}>{m.label}</label>
              <select id={`ruta-${m.key}`} aria-labelledby={`ruta-${m.key}-et`} value={ruta.provider_id || ''} onChange={e => cambiar(m.key, 'provider_id', e.target.value)} style={fs}>
                <option value="">Por defecto</option>
                {providers.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
              <input aria-label={`Modelo para ${m.label}`} list={lista} value={ruta.model || ''}
                placeholder={prov?.default_model || 'Modelo por defecto'} onChange={e => cambiar(m.key, 'model', e.target.value)} style={fs} />
              <datalist id={lista}>{(prov?.available_models || []).map((x: string) => <option key={x} value={x} aria-label={x} />)}</datalist>
            </Fragment>
          )
        })}
      </div>
      <div style={{ marginTop: 14 }}>
        <Button onClick={() => guardar()} disabled={isPending || rutas === null} loading={isPending}>Guardar</Button>
      </div>
    </div>
  )
}


// Revisión 2026-11: gasto de IA de hoy frente al tope diario de la empresa
// (AI_DAILY_BUDGET_USD). Avisa desde AI_DAILY_BUDGET_WARN_PCT; al llegar, las
// llamadas se cortan hasta las 00:00 UTC.
function GastoDeHoy() {
  const t = useAppT()
  const { data } = useQuery<{ spent_usd: number; budget_usd: number; warn_pct: number; used_pct: number | null; blocked: boolean }>({
    queryKey: ['ai-spend-today'],
    queryFn: () => aiProvidersApi.spendToday().then(r => r.data),
    refetchInterval: POLL_DEFAULT_MS,
  })
  if (!data) return null
  const avisa = data.used_pct !== null && data.used_pct >= data.warn_pct
  const color = data.blocked ? 'var(--danger)' : avisa ? 'var(--warning)' : 'var(--text-2)'
  return (
    <div role={data.blocked || avisa ? 'alert' : undefined} style={{ marginBottom: 12, fontSize: 'var(--text-sm)', color }}>
      {data.budget_usd > 0
        ? t('ai.gasto_con_tope', { gastado: data.spent_usd.toFixed(2), tope: data.budget_usd.toFixed(2), pct: data.used_pct ?? 0 })
        : t('ai.gasto_sin_tope', { gastado: data.spent_usd.toFixed(2) })}
      {data.blocked && ` · ${t('ai.gasto_cortado')}`}
    </div>
  )
}
