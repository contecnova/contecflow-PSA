import { PROVIDER_META } from '../constants/api'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr, fmtDateTime, fmtNumber, localeActivo } from '../utils/helpers'
import { Fragment, useId, useState, type ChangeEvent, type CSSProperties } from 'react'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { predictiveObservabilityApi, aiProvidersApi, aiGovernanceApi, apiUrl } from '../services/api'
import type {
  ProveedorIa as AiProvider, ModeloDelCatalogoIa as CatalogModel, EntradaCatalogoIa as CatalogEntry, CatalogoIa as ProviderCatalog,
  EstadisticasIa as AiStats, DiagnosticoIa as Diagnostics,
} from '../services/api/tipos-grc'
import { PROVIDER_DOCS } from '../constants/api'
import { Button, Spinner, Modal, Tabs, Page, Drawer } from '../components/ui'
import { useAppLang, useAppT } from '../i18n/AppLangContext'
import { Cpu, X, Search, Plus, Activity } from 'lucide-react'
import './AIHubPage.css'
import { POLL_DEFAULT_MS, STALE_DEFAULT_MS, STALE_REFERENCE_DATA_MS, STALE_SHORT_MS } from '../constants/timings'
import { AUDIT_LOG_PAGE_SIZE } from '../constants/pagination'

const PMETA = PROVIDER_META as Record<string, { name: string; icon: string; color: string }>
const PDOCS = PROVIDER_DOCS as Record<string, string>

const STATUS_KEYS = ['active', 'inactive', 'error'] as const
/** Color de marca del proveedor como variable CSS (--aih-color); lo consumen las clases aih-*. */
const colorVar = (color?: string | null): CSSProperties | undefined =>
  color ? ({ '--aih-color': color } as CSSProperties) : undefined

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
      toast.success(t('aihub.test_config_ok', { ms: r.data?.latency_ms != null ? fmtNumber(r.data.latency_ms, 0) : '?', model: r.data?.model ?? form.default_model }))
    } catch (e) { toast.error(extractErr(e, t('aihub.test_config_ko'))) }
    finally { setProbando(false) }
  }
  async function descubrirModelos() {
    setDescubriendo(true)
    try {
      const r = await aiProvidersApi.discoverModels(form)
      const lista = Array.isArray(r.data?.models) ? r.data.models : []
      setLiveModels(lista)
      toast.success(t('aihub.models_available', { count: lista.length }))
    } catch (e) { toast.error(extractErr(e, t('aihub.models_discover_error'))) }
    finally { setDescubriendo(false) }
  }
  // Los campos numéricos guardan el texto del input, como siempre: el backend lo convierte.
  const s = (k: string) => (e: ChangeEvent<HTMLInputElement>) => setForm(f => ({ ...f, [k]: e.target.value }))

  const catEntry: Partial<CatalogEntry> = catalog[providerType] || {}
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
      const modelo = data?.default_model
      if (modelo) {
        setForm(f => ({ ...f, default_model: modelo }))
      }
      qc.invalidateQueries({ queryKey: ['ai-providers'] })
      toast.success(t('aihub.models_synced'))
    },
    onError: e => toast.error(extractErr(e, t('aihub.models_sync_error'))),
  })

  const handleProviderChange = (type: string) => {
    setProviderType(type)
    setLiveModels([])
    const cat: Partial<CatalogEntry> = catalog[type] || {}
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
        <div className="aih-drawer-head">
          <span className="aih-drawer-title">{title}</span>
          <button type="button" onClick={onClose} aria-label={t('common.close')} className="aih-close">
            <X size={16} aria-hidden="true" />
          </button>
        </div>
        {/* Body */}
        <div className="aih-drawer-body">
      <form onSubmit={e => { e.preventDefault(); mutate(form) }}>
      {/* Selector de proveedor */}
      {!isEdit && (
        <div className="u-mb-20">
          <label className="aih-label">{t('ai.provider')}</label>
          <div className="aih-provider-grid">
            {Object.entries(PMETA).map(([key, meta]) => (
              <button key={key} type="button" aria-pressed={providerType === key} aria-label={`${t('ai.select_provider')} ${meta.name}`} onClick={() => handleProviderChange(key)}
                className="aih-provider-pick" style={colorVar(meta.color)}>
                <div className="aih-provider-pick-icon" aria-hidden="true">{meta.icon}</div>
                <div className="aih-provider-pick-name">{meta.name}</div>
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="u-grid2-14">
        <div className="u-col-full">
          <label id={`${idPrefix}-name-et`} htmlFor={`${idPrefix}-name`} className="aih-label">{t('ai.config_name')} *</label>
          <input id={`${idPrefix}-name`} aria-labelledby={`${idPrefix}-name-et`} value={form.name} onChange={s('name')} className="aih-input" placeholder={`${catEntry.name || ''} — ${t('ai.config_name_placeholder')}`} />
        </div>

        {providerType !== 'ollama' && (
          <div className="u-col-full">
            <label id={`${idPrefix}-api-key-et`} htmlFor={`${idPrefix}-api-key`} className="aih-label">
              {t('aihub.api_key')} {catEntry.key_hint && <span className="aih-label-hint">({catEntry.key_hint})</span>}
            </label>
            <input id={`${idPrefix}-api-key`} aria-labelledby={`${idPrefix}-api-key-et`} type="password" value={form.api_key} onChange={s('api_key')} className="aih-input"
              placeholder={isEdit ? t('ai.keep_api_key_placeholder') : t('ai.enter_api_key_placeholder')} />
            {catEntry.docs_url && (
              <a href={catEntry.docs_url} target="_blank" rel="noreferrer"
                className="aih-link aih-link--block">
                🔗 {t('ai.get_api_key_at')} {catEntry.docs_url}
              </a>
            )}
          </div>
        )}

        {(providerType === 'ollama' || providerType === 'azure') && (
          <div className="u-col-full">
            <label id={`${idPrefix}-api-base-url-et`} htmlFor={`${idPrefix}-api-base-url`} className="aih-label">{t('ai.base_url')} {providerType === 'ollama' ? `(${t('ai.base_url_example')} http://localhost:11434)` : ''}</label>
            <input id={`${idPrefix}-api-base-url`} aria-labelledby={`${idPrefix}-api-base-url-et`} value={form.api_base_url} onChange={s('api_base_url')} className="aih-input"
              placeholder={catEntry.base_url || 'https://...'} />
          </div>
        )}

        <div>
          <label id={`${idPrefix}-default-model-et`} htmlFor={`${idPrefix}-default-model`} className="aih-label">{t('ai.default_model')}</label>
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
                className="aih-input"
              >
                <option value="">{t('ai.select_option')}</option>
                {models.map(m => (
                  <option key={m.id} value={m.id}>
                    {m.name} · {m.cost_in > 0 ? t('aihub.price_per_m_in', { cost: m.cost_in }) : t('ai.free')}
                  </option>
                ))}
                <option value="__custom__">✏️ {t('ai.custom_model')}</option>
              </select>
              {!models.some(m => m.id === form.default_model) && (
                <input
                  aria-label={t('ai.custom_model_id')}
                  value={form.default_model}
                  onChange={s('default_model')}
                  className="aih-input aih-input--mt"
                  placeholder={t('ai.model_custom_placeholder')}
                />
              )}
            </>
          ) : (
            <input id={`${idPrefix}-default-model`} aria-labelledby={`${idPrefix}-default-model-et`} value={form.default_model} onChange={s('default_model')} className="aih-input"
              placeholder={t('ai.model_name_placeholder')} />
          )}
          {(!isEdit || form.api_key || providerType === 'ollama') && (
            <div className="aih-mt8">
              <Button variant="secondary" onClick={() => { void descubrirModelos() }} disabled={descubriendo} loading={descubriendo}>
                {descubriendo ? t('aihub.discovering_models') : t('aihub.discover_models')}
              </Button>
            </div>
          )}
          {isEdit && (
            <div className="aih-mt8">
              <Button
                variant="secondary"
                onClick={() => syncModels()}
                disabled={isSyncingModels}
                loading={isSyncingModels}
              >
                {isSyncingModels ? t('aihub.syncing_models') : t('aihub.sync_models_provider')}
              </Button>
            </div>
          )}
        </div>

        <div>
          <label id={`${idPrefix}-max-tokens-et`} htmlFor={`${idPrefix}-max-tokens`} className="aih-label">{t('ai.max_response_tokens')}</label>
          <input id={`${idPrefix}-max-tokens`} aria-labelledby={`${idPrefix}-max-tokens-et`} type="number" value={form.max_tokens} onChange={s('max_tokens')} className="aih-input" />
        </div>

        <div>
          <label id={`${idPrefix}-temperature-et`} htmlFor={`${idPrefix}-temperature`} className="aih-label">{t('ai.temperature')}</label>
          <input id={`${idPrefix}-temperature`} aria-labelledby={`${idPrefix}-temperature-et`} type="number" step="0.1" min="0" max="2" value={form.temperature} onChange={s('temperature')} className="aih-input" />
        </div>

        <div>
          <label id={`${idPrefix}-priority-et`} htmlFor={`${idPrefix}-priority`} className="aih-label">{t('aihub.fallback_order')}</label>
          <input id={`${idPrefix}-priority`} aria-labelledby={`${idPrefix}-priority-et`} type="number" min="0" value={form.priority} onChange={s('priority')} className="aih-input"
            title={t('aihub.fallback_order_help')} />
        </div>

        <div className="aih-default-check">
          <input type="checkbox" id={`${idPrefix}-is-default`} aria-labelledby={`${idPrefix}-is-default-et`} checked={form.is_default}
            onChange={e => setForm(f => ({ ...f, is_default: e.target.checked }))} />
          <label id={`${idPrefix}-is-default-et`} htmlFor={`${idPrefix}-is-default`}>
            {t('ai.set_global_default')}
          </label>
        </div>
      </div>

      {/* Info del proveedor seleccionado */}
      {models.length > 0 && (
        <div className="aih-models">
          <div className="aih-models-title">{t('ai.available_models')}:</div>
          <div className="aih-models-grid">
            {models.map(m => (
              <div key={m.id} className="aih-models-row">
                <span className="u-text2">{m.name}</span>
                <span className={m.cost_in === 0 ? 'u-success' : 'u-warning'}>
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
        <div className="aih-drawer-foot">
          <Button variant="secondary" onClick={onClose} type="button">{t('common.cancel')}</Button>
          <Button variant="secondary" type="button" onClick={() => { void probarSinGuardar() }} disabled={probando || !form.provider} loading={probando}>
            {t('aihub.test_without_saving')}
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
  const [result, setResult] = useState<{ ok?: boolean; error?: string; response?: string; latency_ms?: number; model?: string | null } | null>(null)
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
        <div role="status" className={`aih-test-result ${result.ok ? 'aih-test-result--ok' : 'aih-test-result--ko'}`}>
          {result.ok ? (
            <>
              <div className="aih-test-head">✅ {t('ai.test_success')}</div>
              <div className="u-text2-sm">{t('ai.test_response')}: &quot;{result.response}&quot;</div>
              <div className="u-text2-sm aih-mt4">{t('ai.test_latency_model')}: {result.latency_ms != null ? fmtNumber(result.latency_ms, 0) : '—'} ms · {result.model}</div>
            </>
          ) : (
            <>
              <div className="aih-test-head">❌ {t('ai.test_error')}</div>
              <pre className="aih-test-error">{result.error}</pre>
            </>
          )}
        </div>
      )}
      <div className="aih-foot">
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

  if (loading) return <div className="aih-pad24"><Spinner /></div>

  return (
    <div id="aihub-panel-governance" role="tabpanel" className="u-stack-20">
      {/* Stats summary */}
      {stats && (
        <div className="aih-kpis">
          {[
            { label: traducir('aihub.kpi_evaluations'), value: stats.total_evaluations || 0, tone: 'accent' },
            // Auditoría 2026-11: leía blocked/redacted/pii_total, que la API no
            // devuelve; las tarjetas salían siempre a 0.
            { label: traducir('aihub.kpi_blocked'), value: stats.total_blocked || 0, tone: 'danger' },
            { label: traducir('aihub.kpi_redacted'), value: stats.total_redacted || 0, tone: 'warning' },
            { label: traducir('aihub.kpi_pii'), value: (stats.top_pii_types || []).reduce((n: number, x: { count?: number }) => n + (x.count || 0), 0), tone: 'purple' },
          ].map(k => (
            <div key={k.label} className={`aih-kpi aih-tone--${k.tone}`}>
              <div className="aih-kpi-value">{fmtNumber(k.value, 0)}</div>
              <div className="u-text2-xs">{k.label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Policies list */}
      <div className="ds-card ds-card--plano">
        <div className="aih-panel-head">
          <div>{traducir('aihub.politicas_configuradas')}{policies.length})</div>
          <div className="u-text3-xs aih-panel-head-note">
            {traducir('aihub.crud_via')} <code>POST {apiUrl('/ai-governance/policies')}</code> · {traducir('aihub.ui_pending')}
          </div>
        </div>
        {policies.length === 0 ? (
          <div className="aih-panel-empty aih-panel-empty--sm">
            {traducir('aihub.sin_policies_activas_los_guardrails_deteccion_pii')}
          </div>
        ) : (
          <div className="aih-scroll aih-scroll--240">
            {policies.map(p => (
              <div key={p.id} className="aih-policy">
                <div className="aih-policy-head">
                  <span className="u-600">{p.name}</span>
                  <span className={p.is_active ? 'aih-tag aih-tag--on' : 'aih-tag'}>
                    {p.is_active ? traducir('aihub.policy_active') : traducir('aihub.policy_inactive')}
                  </span>
                </div>
                <div className="aih-policy-meta">
                  scope={p.scope} · action={p.action} · roles=[{(p.applies_to_roles || []).join(',')}]
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Audit log */}
      <div className="ds-card ds-card--plano">
        <div className="aih-panel-head">
          {traducir('aihub.audit_log_ultimas_50_evaluaciones')}
        </div>
        {auditLog.length === 0 ? (
          <div className="aih-panel-empty">{traducir('aihub.sin_actividad_reciente')}</div>
        ) : (
          <div className="aih-scroll aih-scroll--360">
            {auditLog.map(l => (
              <div key={l.id} className="aih-audit">
                <span className="aih-audit-date">{l.evaluated_at ? fmtDateTime(l.evaluated_at) : ''}</span>
                <span className="aih-audit-module">{l.module || '—'}</span>
                <span className="aih-audit-scope">{l.scope}</span>
                <span className={`aih-audit-action${l.was_blocked ? ' aih-audit-action--blocked' : l.action_taken === 'redacted' ? ' aih-audit-action--redacted' : ''}`}>
                  {l.action_taken || traducir('aihub.action_none')}
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
  const traducir = useAppT()
  const { lang } = useAppLang()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  // `{}` abre el alta; un proveedor abre la edición.
  const [modal, setModal] = useState<Partial<AiProvider> | null>(null)
  const [testModal, setTestModal] = useState<AiProvider | null>(null)
  const [tab, setTab] = useState('providers')
  const [diagResults, setDiagResults] = useState<Diagnostics | null>(null)

  const { mutate: importarEntorno } = useMutation({
    mutationFn: () => aiProvidersApi.importEnv(),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['ai-providers'] }); toast.success(t('aihub.imported')) },
    onError: e => toast.error(extractErr(e, t('aihub.import_error'))),
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
  const { data: stats } = useQuery<AiStats>({
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
    onSuccess: () => { toast.success(t('aihub.retrain_done')); qc.invalidateQueries({ queryKey: ['predictive-obs-health'] }) },
    onError: e => toast.error(extractErr(e, t('aihub.retrain_error'))),
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
        toast.success(t('aihub.diag_ok', { total }))
      } else {
        toast.error(t('aihub.diag_partial', { healthy, total }))
      }
    },
    onError: e => toast.error(extractErr(e, t('aihub.diag_error'))),
  })

  const { mutate: syncAllModels, isPending: syncingAllModels } = useMutation({
    mutationFn: () => aiProvidersApi.syncAll().then(r => r.data),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['ai-providers'] })
      const failed = Number(data?.failed || 0)
      const total = Number(data?.total || 0)
      if (failed > 0) {
        toast.error(t('aihub.sync_partial', { ok: total - failed, total }))
      } else {
        toast.success(t('aihub.sync_all_ok', { total }))
      }
    },
    onError: e => toast.error(extractErr(e, t('aihub.sync_all_error'))),
  })

  const defaultProvider = providers.find(p => p.is_default)
  const byModule = stats?.by_module || []
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
        <div className="aih-header-actions">
          <Button
            variant="secondary"
            onClick={() => diagnoseAll()}
            disabled={diagnosing}
            loading={diagnosing}
          >
            <Search size={13} aria-hidden="true" /> {diagnosing ? t('aihub.diagnosing') : t('aihub.diagnose')}
          </Button>
          <Button
            variant="secondary"
            onClick={() => syncAllModels()}
            disabled={syncingAllModels}
            loading={syncingAllModels}
          >
            {syncingAllModels ? t('aihub.syncing_models') : t('aihub.sync_all_models')}
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
          { id: 'routing',       label: t('aihub.tab_routing') },
          { id: 'stats',         label: t('ai.usage') },
          { id: 'governance',    label: <span className="aih-tab-label"><span aria-hidden="true">🛡</span> {t('aihub.tab_governance')}</span> },
          { id: 'observability', label: <span className="aih-tab-label"><Activity size={11} aria-hidden="true" /> {t('aihub.tab_observability')}</span> },
          { id: 'guide',         label: t('ai.guide') },
        ]}
        active={tab}
        onChange={setTab}
        ariaLabel={t('ai.hub_title')}
        className="aih-tabs"
      />

      {tab === 'governance' && <GovernanceTab />}
      {tab === 'routing' && <RoutingTab providers={providers} />}

      {/* PROVIDERS TAB */}
      {tab === 'providers' && (
        <div id="aihub-panel-providers" role="tabpanel" aria-labelledby="aihub-tab-providers">

          {/* Panel de diagnóstico */}
          {diagResults && (
            <div role="status" className={`aih-card aih-card--pad-md aih-diag aih-tone--${diagResults.error > 0 ? 'danger' : diagResults.warning > 0 ? 'warning' : 'success'}`}>
              <div className="aih-diag-head">
                <div className="u-md-700">
                  {traducir('aihub.diagnostico_resumen', { healthy: diagResults.healthy, total: diagResults.total })}
                </div>
                <button type="button" onClick={() => setDiagResults(null)} aria-label={t('common.close')} className="aih-close aih-close--lg"><span aria-hidden="true">✕</span></button>
              </div>
              <div className="u-stack-8">
                {(diagResults.providers || []).map(pr => {
                  const dotKind = pr.status === 'ok' ? 'success' : pr.status === 'warning' ? 'warning' : 'danger'
                  return (
                    <div key={pr.id} className="aih-diag-row">
                      <span className={`ds-status-dot ds-status-dot--${dotKind}`} aria-hidden="true" />
                      <div className="u-flex1-min0">
                        <span className="u-600">{pr.name}</span>
                        <span className="aih-diag-meta">{pr.provider_type}</span>
                        {pr.latency_ms != null && (
                          <span className="aih-diag-meta">{fmtNumber(pr.latency_ms, 0)} ms</span>
                        )}
                        {pr.models_found > 0 && (
                          <span className="aih-diag-meta">{t('aihub.n_models', { count: pr.models_found })}</span>
                        )}
                        {pr.error && (
                          <div className={pr.status === 'warning' ? 'aih-diag-error aih-diag-error--warning' : 'aih-diag-error'}>{pr.error}</div>
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
            <div className="aih-card aih-card--pad-md aih-active" style={colorVar(PMETA[defaultProvider.provider]?.color)}>
              <div className="u-row-center-12">
                <span className="aih-active-icon" aria-hidden="true">{PMETA[defaultProvider.provider]?.icon}</span>
                <div className="u-min0">
                  <div className="aih-active-eyebrow">{t('ai.provider_active_default')}</div>
                  <div className="aih-active-name">{defaultProvider.name}</div>
                  <div className="u-text2-sm">{t('ai.provider_resumen', { modelo: defaultProvider.default_model, n: intFmt.format(defaultProvider.total_requests || 0), coste: moneyFmt.format(defaultProvider.total_cost_usd || 0) })}</div>
                </div>
              </div>
            </div>
          )}

          {isLoading ? <Spinner /> : providers.length === 0 ? (
            <div className="aih-card aih-empty">
              <div className="u-empty-icon" aria-hidden="true">🤖</div>
              <div className="aih-empty-title">{t('ai.no_providers_title')}</div>
              <div className="aih-empty-desc">
                {t('ai.no_providers_desc')}
              </div>
              <Button onClick={() => setModal({})}><Plus size={13} /> {t('ai.add_first_provider')}</Button>
            </div>
          ) : (
            <div data-export-table="ai-providers-list" className="aih-providers">
              {providers.map(p => {
                const meta: { name?: string; icon: string; color: string } = PMETA[p.provider] || { icon: '🤖', color: 'var(--text-2)' }
                const st = (STATUS_KEYS as readonly string[]).includes(p.status) ? p.status : 'inactive'
                return (
                  <div key={p.id} className={`aih-card aih-card--pad${p.is_default ? ' aih-provider--default' : ''}`} style={colorVar(meta.color)}>
                    <div className="aih-provider-head">
                      <div className="aih-provider-id">
                        <div className="aih-provider-logo" aria-hidden="true">
                          {meta.icon}
                        </div>
                        <div className="u-min0">
                          <div className="u-md-700">{p.name}</div>
                          <div className="u-text2-xs">{meta.name} · {p.default_model || t('ai.model_none')}</div>
                        </div>
                      </div>
                      <div className="aih-provider-badges">
                        <span className={`aih-status aih-status--${st}`}>{t(`ai.provider_status_${st}`)}</span>
                        {p.is_default && <span className="aih-flag aih-flag--accent">⭐ {t('ai.default_badge')}</span>}
                        {p.source === 'env' && <span title={t('aihub.from_env_help')} className="aih-flag">{t('aihub.from_env')}</span>}
                      </div>
                    </div>

                    <div className="aih-provider-key">
                      {p.has_api_key ? `🔑 ${t('ai.api_key_configured')}` : p.provider === 'ollama' ? `🦙 ${t('ai.local_no_key')}` : `⚠️ ${t('ai.no_api_key')}`}
                      {p.last_error && <span className="aih-provider-key-error">· {t('common.error')}: {p.last_error.slice(0, 40)}...</span>}
                    </div>

                    <div className="aih-provider-usage">
                      <div><span className="u-text2">{t('ai.requests')}:</span> <strong>{intFmt.format(p.total_requests || 0)}</strong></div>
                      <div><span className="u-text2">{t('ai.total_cost')}:</span> <strong className="u-warning">{moneyFmt.format(Number(p.total_cost_usd || 0))}</strong></div>
                    </div>

                    <div className="u-wrap-6">
                      <button type="button" aria-label={`${t('ai.provider_test_aria')} ${p.name}`} onClick={() => setTestModal(p)}
                        className="aih-btn aih-btn--grow aih-btn--accent">
                        🔌 {t('ai.provider_test_action')}
                      </button>
                      {p.source === 'env' && (
                        <button type="button" aria-label={t('aihub.import_aria', { name: p.name })} onClick={() => importarEntorno()}
                          title={t('aihub.import_help')}
                          className="aih-btn aih-btn--grow aih-btn--accent-border">
                          ⬇ {t('aihub.import_btn')}
                        </button>
                      )}
                      {p.source !== 'env' && !p.is_default && (
                        <button type="button" aria-label={`${t('ai.provider_default_aria')} ${p.name}`} onClick={() => setDefault(p.id)}
                          className="aih-btn aih-btn--grow aih-btn--accent-border">
                          ⭐ {t('ai.provider_default_action')}
                        </button>
                      )}
                      {p.source !== 'env' && <>
                      <button type="button" aria-label={`${t('ai.provider_edit_aria')} ${p.name}`} onClick={() => setModal(p)}
                        className="aih-btn">
                        {t('ai.provider_edit_action')}
                      </button>
                      <button type="button" aria-label={`${t('ai.provider_delete_action')} ${p.name}`} onClick={() => { openConfirmGlobal({ message: `${t('ai.delete_confirm')} "${p.name}"?`, onConfirm: () => del(p.id), danger: true }) }}
                        className="aih-btn aih-btn--danger">
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
          <div className="aih-stats">
            {[
              { icon: '🤖', label: t('ai.providers_count'), value: intFmt.format((stats?.providers || []).length), tone: 'accent' },
              { icon: '💬', label: t('ai.total_requests'), value: intFmt.format(stats?.total_requests || 0), tone: 'success' },
              { icon: '💰', label: t('ai.total_cost'), value: moneyFmt.format(stats?.total_cost || 0), tone: 'warning' },
            ].map(k => (
              <div key={k.label} className={`aih-card aih-card--pad aih-tone--${k.tone}`}>
                <div className="aih-stat-icon" aria-hidden="true">{k.icon}</div>
                <div className="aih-stat-value">{k.value}</div>
                <div className="u-text2-sm">{k.label}</div>
              </div>
            ))}
          </div>

          {byModule.length > 0 && (
            <div className="aih-card">
              <div className="aih-module-head">{t('ai.module_usage')}</div>
              {byModule.map(r => (
                <div key={r.module} className="aih-module-row">
                  <span className="u-600">{r.module}</span>
                  <div className="aih-module-nums">
                    <span>{intFmt.format(r.calls || 0)} {t('ai.calls')}</span>
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
          <div className="aih-obs-head">
            <div className="u-text2-base">{traducir('aihub.estado_de_salud_de_los_modelos_predictivos')}</div>
            <Button onClick={() => triggerRetrain()} disabled={retraining}>
              {retraining ? `⏳ ${t('aihub.retraining')}` : `▶ ${t('aihub.force_retrain')}`}
            </Button>
          </div>

          {obsLoading ? <Spinner /> : !obsHealth ? (
            <div className="aih-card aih-obs-empty">
              {traducir('aihub.sin_datos_de_observabilidad_requiere_permisos_de')}
            </div>
          ) : (
            <div className="aih-two-cols">
              {[
                { key: 'itsm', label: t('aihub.model_itsm'), data: obsHealth.itsm },
                { key: 'bi',   label: t('aihub.model_bi'),   data: obsHealth.bi },
              ].map(({ key, label, data }) => {
                if (!data) return null
                const salud = data.status === 'healthy' || data.status === 'attention' ? data.status : 'other'
                const estado = data.status ? t(`aihub.health_${data.status}`, data.status) : t('aihub.health_unknown')
                return (
                  <div key={key} className={`aih-card aih-card--pad aih-health--${salud}`}>
                    <div className="aih-model-head">
                      <div className="u-md-600">{label}</div>
                      <span className="aih-health-pill">
                        {estado}
                      </span>
                    </div>
                    {data.score != null && (
                      <div className="u-mb-10">
                        <div className="aih-score-head">
                          <span className="u-text2">{traducir('aihub.score_de_salud')}</span>
                          <span className="aih-score-value">{fmtNumber(data.score * 100, 0)}%</span>
                        </div>
                        <div className="aih-bar" role="progressbar" aria-label={traducir('aihub.score_de_salud')} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(Math.min(data.score * 100, 100))}>
                          <div className="aih-bar-fill" style={{ '--pct': `${Math.min(data.score * 100, 100)}%` } as CSSProperties} />
                        </div>
                      </div>
                    )}
                    <div className="aih-facts">
                      {/* Auditoría 2026-11: la API da samples, severity_accuracy y mae_minutes
                          (ITSM) e history_months y motores (BI); no total_predictions/accuracy. */}
                      {data.samples != null && (
                        <div className="aih-fact">
                          <span className="u-text3">{t('aihub.fact_predictions')}</span>
                          <span>{fmtNumber(data.samples, 0)}</span>
                        </div>
                      )}
                      {data.severity_accuracy != null && (
                        <div className="aih-fact">
                          <span className="u-text3">{traducir('aihub.precision')}</span>
                          <span>{fmtNumber(data.severity_accuracy * 100, 1)}%</span>
                        </div>
                      )}
                      {data.mae_minutes != null && (
                        <div className="aih-fact">
                          <span className="u-text3">{t('aihub.fact_mae')}</span>
                          <span>{t('aihub.minutes_short', { n: fmtNumber(data.mae_minutes, 1) })}</span>
                        </div>
                      )}
                      {data.status && (
                        <div className="aih-fact">
                          <span className="u-text3">{t('common.status')}</span>
                          <span>{estado}</span>
                        </div>
                      )}
                      {/* Revisión 2026-11: leía drift_detected y reason, que la API no da; el modelo BI da
                          meses de historia y el motor usado (los «fallback»/«heuristic» bajan la nota). */}
                      {data.history_months != null && (
                        <div className="aih-fact">
                          <span className="u-text3">{t('aihub.fact_history_months')}</span>
                          <span>{fmtNumber(data.history_months, 0)}</span>
                        </div>
                      )}
                      {data.forecast_engine && (
                        <div className="aih-fact">
                          <span className="u-text3">{t('aihub.fact_engines')}</span>
                          <span>{data.forecast_engine} · {data.overrun_engine}</span>
                        </div>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          )}

          {obsHealth && (
            <div className="aih-card aih-overall">
              <div className="aih-overall-icon" aria-hidden="true">
                {obsHealth.overall_status === 'healthy' ? '✅' : obsHealth.overall_status === 'attention' ? '⚠️' : '❓'}
              </div>
              <div>
                <div className="u-base-600">{t('aihub.overall_status')}: {obsHealth.overall_status ? t(`aihub.health_${obsHealth.overall_status}`, obsHealth.overall_status) : t('aihub.health_unknown')}</div>
                <div className="u-text2-sm-mt2">
                  {t('aihub.overall_score')}: {obsHealth.overall_score != null ? `${fmtNumber(obsHealth.overall_score * 100, 0)}%` : '—'}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* GUIDE TAB */}
      {tab === 'guide' && (
        <div className="aih-two-cols">
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
            <div key={p.title} className="aih-card aih-card--pad">
              <div className="aih-guide-head">
                <span className="aih-guide-icon" aria-hidden="true">{p.icon}</span>
                <div>
                  <div className="u-md-700">{p.title}</div>
                  <div className="aih-guide-desc">{p.desc}</div>
                </div>
              </div>
              <div className="aih-guide-foot">
                <span className="u-text3-mono-xs">{p.hint}</span>
                <a href={p.link} target="_blank" rel="noreferrer" className="aih-link">{t('ai.get_key')} →</a>
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
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const { data } = useQuery({ queryKey: ['ai-routing'], queryFn: () => aiProvidersApi.getRouting().then(r => r.data) })
  const [rutas, setRutas] = useState<Record<string, { provider_id?: string | null; model?: string | null }> | null>(null)
  const actuales = rutas ?? data?.routes ?? {}
  const { mutate: guardar, isPending } = useMutation({
    mutationFn: () => aiProvidersApi.saveRouting(actuales),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['ai-routing'] }); setRutas(null); toast.success(t('aihub.routing_saved')) },
    onError: e => toast.error(extractErr(e, t('aihub.routing_save_error'))),
  })
  const cambiar = (k: string, campo: 'provider_id' | 'model', v: string) =>
    setRutas({ ...actuales, [k]: { ...(actuales[k] || {}), [campo]: v || null } })
  return (
    <div id="aihub-panel-routing" role="tabpanel" className="aih-routing">
      <p className="aih-routing-help">
        {t('aihub.routing_help')}
      </p>
      <div className="aih-routing-grid">
        {(data?.modules || []).map((m: { key: string; label: string }) => {
          const ruta = actuales[m.key] || {}
          const prov = providers.find(p => p.id === ruta.provider_id)
          const lista = `modelos-${m.key}`
          return (
            <Fragment key={m.key}>
              <label id={`ruta-${m.key}-et`} htmlFor={`ruta-${m.key}`} className="aih-routing-label">{m.label}</label>
              <select id={`ruta-${m.key}`} aria-labelledby={`ruta-${m.key}-et`} value={ruta.provider_id || ''} onChange={e => cambiar(m.key, 'provider_id', e.target.value)} className="aih-input">
                <option value="">{t('aihub.routing_default')}</option>
                {providers.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
              <input aria-label={t('aihub.routing_model_for', { label: m.label })} list={lista} value={ruta.model || ''}
                placeholder={prov?.default_model || t('aihub.routing_default_model')} onChange={e => cambiar(m.key, 'model', e.target.value)} className="aih-input" />
              <datalist id={lista}>{(prov?.available_models || []).map((x: string) => <option key={x} value={x} aria-label={x} />)}</datalist>
            </Fragment>
          )
        })}
      </div>
      <div className="aih-routing-foot">
        <Button onClick={() => guardar()} disabled={isPending || rutas === null} loading={isPending}>{t('common.save')}</Button>
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
  const usd = new Intl.NumberFormat(localeActivo(), { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return (
    <div role={data.blocked || avisa ? 'alert' : undefined} className={`aih-spend${data.blocked ? ' aih-spend--blocked' : avisa ? ' aih-spend--warn' : ''}`}>
      {data.budget_usd > 0
        ? t('ai.gasto_con_tope', { gastado: usd.format(data.spent_usd), tope: usd.format(data.budget_usd), pct: fmtNumber(data.used_pct ?? 0, 0) })
        : t('ai.gasto_sin_tope', { gastado: usd.format(data.spent_usd) })}
      {data.blocked && ` · ${t('ai.gasto_cortado')}`}
    </div>
  )
}
