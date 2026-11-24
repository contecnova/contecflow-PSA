// Modales de proveedor de IA (alta/edicion y prueba). 23-11-2026: troceado de AIHubPage sin cambio de comportamiento.
import { extractErr, fmtNumber } from '../utils/helpers'
import { useId, useState, type ChangeEvent } from 'react'
import { useToast } from '../context/ToastContext'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { aiProvidersApi } from '../services/api'
import type { ProveedorIa as AiProvider, ModeloDelCatalogoIa as CatalogModel, EntradaCatalogoIa as CatalogEntry, CatalogoIa as ProviderCatalog } from '../services/api/tipos-grc'
import { Button, Modal, Drawer, Pulsable, Select, Checkbox, Input, IconButton } from '../components/ui'
import { sanitizeUrl } from '../utils/security'
import { useAppT } from '../i18n/AppLangContext'
import { Cpu, X, Plug, ExternalLink, CheckCircle2, XCircle } from 'lucide-react'
import { PMETA, type ProviderForm, colorVar } from './AIHubComun'

/** Detalle de error de FastAPI cuando es una lista de validación. */


export function ProviderModal({ provider, catalog, onClose }: { provider: Partial<AiProvider> | null; catalog: ProviderCatalog; onClose: () => void }) {
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
          <IconButton variante="caja" onClick={onClose} ariaLabel={t('common.close')} data-cierra-dialogo="">
            <X size={16} aria-hidden="true" />
          </IconButton>
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
              <Pulsable key={key} type="button" aria-pressed={providerType === key} aria-label={`${t('ai.select_provider')} ${meta.name}`} onClick={() => handleProviderChange(key)}
                className="aih-provider-pick" style={colorVar(meta.color)}>
                <div className="aih-provider-pick-icon" aria-hidden="true"><Cpu size={18} /></div>
                <div className="aih-provider-pick-name">{meta.name}</div>
              </Pulsable>
            ))}
          </div>
        </div>
      )}

      <div className="u-grid2-14">
        <div className="u-col-full">
          <Input label={<>{t('ai.config_name')}*</>} id={`${idPrefix}-name`} value={form.name} onChange={s('name')} placeholder={`${catEntry.name || ''} — ${t('ai.config_name_placeholder')}`} />
        </div>

        {providerType !== 'ollama' && (
          <div className="u-col-full">
            <Input label={<>{t('aihub.api_key')}{catEntry.key_hint && <span className="aih-label-hint">({catEntry.key_hint})</span>}</>} id={`${idPrefix}-api-key`} type="password" value={form.api_key} onChange={s('api_key')} placeholder={isEdit ? t('ai.keep_api_key_placeholder') : t('ai.enter_api_key_placeholder')} />
            {catEntry.docs_url && (
              <a href={sanitizeUrl(catEntry.docs_url)} target="_blank" rel="noreferrer"
                className="aih-link aih-link--block">
                <ExternalLink size={12} aria-hidden="true" /> {t('ai.get_api_key_at')} {catEntry.docs_url}
              </a>
            )}
          </div>
        )}

        {(providerType === 'ollama' || providerType === 'azure') && (
          <div className="u-col-full">
            <Input label={<>{t('ai.base_url')}{providerType === 'ollama' ? `(${t('ai.base_url_example')} http://localhost:11434)` : ''}</>} id={`${idPrefix}-api-base-url`} value={form.api_base_url} onChange={s('api_base_url')} placeholder={catEntry.base_url || 'https://...'} />
          </div>
        )}

        <div>
          <label id={`${idPrefix}-default-model-et`} htmlFor={`${idPrefix}-default-model`} className="aih-label">{t('ai.default_model')}</label>
          {models.length > 0 ? (
            <>
              <Select suelto placeholder={false}
                id={`${idPrefix}-default-model`}
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
                <option value="__custom__">{t('ai.custom_model')}</option>
              </Select>
              {!models.some(m => m.id === form.default_model) && (
                <Input
                  aria-label={t('ai.custom_model_id')}
                  value={form.default_model}
                  onChange={s('default_model')}
                  inputClassName="aih-input aih-input--mt"
                  placeholder={t('ai.model_custom_placeholder')}
                />
              )}
            </>
          ) : (
            <Input id={`${idPrefix}-default-model`} aria-labelledby={`${idPrefix}-default-model-et`} value={form.default_model} onChange={s('default_model')} placeholder={t('ai.model_name_placeholder')} inputClassName="aih-input" />
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

        <Input label={t('ai.max_response_tokens')} id={`${idPrefix}-max-tokens`} type="number" value={form.max_tokens} onChange={s('max_tokens')} />

        <Input label={t('ai.temperature')} id={`${idPrefix}-temperature`} type="number" step="0.1" min="0" max="2" value={form.temperature} onChange={s('temperature')} />

        <Input label={t('aihub.fallback_order')} id={`${idPrefix}-priority`} type="number" min="0" value={form.priority} onChange={s('priority')} title={t('aihub.fallback_order_help')} />

        <div className="aih-default-check">
          <Checkbox id={`${idPrefix}-is-default`} checked={form.is_default}
            onChange={(_, e) => setForm(f => ({ ...f, is_default: e.target.checked }))} />
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

export function TestModal({ provider, onClose }: { provider: AiProvider; onClose: () => void }) {
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
      // 23-11-2026: texto traducido con extractErr; el `message` técnico de axios solo como último recurso.
      setResult({ ok: false, error: extractErr(e, (e as { message?: string })?.message || t('ai.test_error')) })
    } finally {
      setTesting(false)
    }
  }

  return (
    <Modal open onClose={onClose} title={`${t('ai.testing_provider')} — ${provider.name}`} width={480}>
      <p className="u-text2-base-mb20">
        {t('ai.connection_help')}
      </p>
      <Button onClick={runTest} disabled={testing} loading={testing} icon={<Plug size={14} />}>
        {testing ? t('ai.test_running') : t('ai.test_connection')}
      </Button>
      {result && (
        <div role="status" className={`aih-test-result ${result.ok ? 'aih-test-result--ok' : 'aih-test-result--ko'}`}>
          {result.ok ? (
            <>
              <div className="aih-test-head"><CheckCircle2 size={16} aria-hidden="true" /> {t('ai.test_success')}</div>
              <div className="u-text2-sm">{t('ai.test_response')}: &quot;{result.response}&quot;</div>
              <div className="u-text2-sm aih-mt4">{t('ai.test_latency_model')}: {result.latency_ms != null ? fmtNumber(result.latency_ms, 0) : '—'} ms · {result.model}</div>
            </>
          ) : (
            <>
              <div className="aih-test-head"><XCircle size={16} aria-hidden="true" /> {t('ai.test_error')}</div>
              <pre className="ds-codigo ds-codigo--bloque aih-test-error">{result.error}</pre>
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
