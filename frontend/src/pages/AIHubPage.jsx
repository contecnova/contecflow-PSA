import { CHART } from '../constants/theme'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr } from '../utils/helpers'
import { useState } from 'react'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../services/api'
import { PROVIDER_DOCS } from '../constants/api'
import { Button, Spinner, Modal } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import { useAppT } from '../i18n/AppLangContext'

const PROVIDER_META = {
  anthropic: { icon: '🟠', color: CHART.orange, name: 'Anthropic' },
  openai:    { icon: '🟢', color: 'var(--success)', name: 'OpenAI' },
  gemini:    { icon: '🔵', color: 'var(--accent)', name: 'Google' },
  deepseek:  { icon: '🐋', color: 'var(--accent-dim)', name: 'DeepSeek' },
  groq:      { icon: '⚡', color: 'var(--danger)', name: 'Groq' },
  mistral:   { icon: '🌪', color: CHART.orange, name: 'Mistral' },
  ollama:    { icon: '🦙', color: 'var(--success)', name: 'Ollama (local)' },
  azure:     { icon: '☁️', color: 'var(--accent)', name: 'Azure OpenAI' },
}

const STATUS_CFG = {
  active:   { label: 'Activo',   color: 'var(--success)' },
  inactive: { label: 'Inactivo', color: 'var(--text-2)' },
  error:    { label: 'Error',    color: 'var(--danger)' },
}

const card = { background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 12 }
const fs = { background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 8, padding: '8px 12px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', width: '100%' }
const ls = { fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', display: 'block', marginBottom: 5 }

function ProviderModal({ provider, catalog, onClose }) {
  const qc = useQueryClient()
  const toast = useToast()
  const isEdit = !!provider?.id
  const [providerType, setProviderType] = useState(provider?.provider || 'anthropic')
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
  const s = k => e => setForm(f => ({ ...f, [k]: e.target.value }))

  const catEntry = catalog[providerType] || {}
  const models = catEntry.models || []

  const { mutate, isPending } = useMutation({
    mutationFn: d => isEdit ? api.patch(`/ai-providers/${provider.id}`, d) : api.post('/ai-providers', d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['ai-providers'] }); onClose() },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const handleProviderChange = (type) => {
    setProviderType(type)
    const cat = catalog[type] || {}
    setForm(f => ({
      ...f,
      provider: type,
      name: f.name || `${PROVIDER_META[type]?.name || type}`,
      api_base_url: cat.base_url || '',
      default_model: cat.models?.[0]?.id || '',
    }))
  }

  return (
    <Modal open onClose={onClose} title={isEdit ? `Editar — ${provider.name}` : 'Añadir proveedor de IA'} width={660}>
      {/* Selector de proveedor */}
      {!isEdit && (
        <div style={{ marginBottom: 20 }}>
          <label style={ls}>Proveedor</label>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8 }}>
            {Object.entries(PROVIDER_META).map(([key, meta]) => (
              <button key={key} onClick={() => handleProviderChange(key)}
                style={{ padding: '10px 8px', borderRadius: 8, border: `2px solid ${providerType === key ? meta.color + '80' : 'var(--surface-4)'}`, background: providerType === key ? meta.color + '15' : 'transparent', cursor: 'pointer', fontFamily: 'inherit', transition: 'all 0.15s' }}>
                <div style={{ fontSize: 18, marginBottom: 4 }}>{meta.icon}</div>
                <div style={{ fontSize: 11, fontWeight: 600, color: providerType === key ? meta.color : 'var(--text-2)' }}>{meta.name}</div>
              </button>
            ))}
          </div>
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
        <div style={{ gridColumn: '1/-1' }}>
          <label style={ls}>Nombre de esta configuración *</label>
          <input value={form.name} onChange={s('name')} style={fs} placeholder={`${catEntry.name || ''} — Producción`} />
        </div>

        {providerType !== 'ollama' && (
          <div style={{ gridColumn: '1/-1' }}>
            <label style={ls}>
              API Key {catEntry.key_hint && <span style={{ color: 'var(--text-3)', fontWeight: 400, textTransform: 'none' }}>({catEntry.key_hint})</span>}
            </label>
            <input type="password" value={form.api_key} onChange={s('api_key')} style={fs}
              placeholder={isEdit ? '(sin cambios — dejar vacío para conservar)' : 'Introduce tu API key'} />
            {catEntry.docs_url && (
              <a href={catEntry.docs_url} target="_blank" rel="noreferrer"
                style={{ fontSize: 11, color: 'var(--accent)', marginTop: 4, display: 'block' }}>
                🔗 Obtener API key en {catEntry.docs_url}
              </a>
            )}
          </div>
        )}

        {(providerType === 'ollama' || providerType === 'azure') && (
          <div style={{ gridColumn: '1/-1' }}>
            <label style={ls}>URL base {providerType === 'ollama' ? '(ej: http://localhost:11434)' : ''}</label>
            <input value={form.api_base_url} onChange={s('api_base_url')} style={fs}
              placeholder={catEntry.base_url || 'https://...'} />
          </div>
        )}

        <div>
          <label style={ls}>Modelo por defecto</label>
          {models.length > 0 ? (
            <>
              <select
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
                <option value="">Seleccionar...</option>
                {models.map(m => (
                  <option key={m.id} value={m.id}>
                    {m.name} {m.cost_in > 0 ? `· $${m.cost_in}/M in` : '· Gratis'}
                  </option>
                ))}
                <option value="__custom__">✏️ Personalizado (escribir ID)...</option>
              </select>
              {!models.some(m => m.id === form.default_model) && (
                <input
                  value={form.default_model}
                  onChange={s('default_model')}
                  style={{ ...fs, marginTop: 6 }}
                  placeholder="Escribe el ID del modelo (ej: gpt-4o-2024-11-20)"
                />
              )}
            </>
          ) : (
            <input value={form.default_model} onChange={s('default_model')} style={fs}
              placeholder="nombre-del-modelo" />
          )}
        </div>

        <div>
          <label style={ls}>Max tokens respuesta</label>
          <input type="number" value={form.max_tokens} onChange={s('max_tokens')} style={fs} />
        </div>

        <div>
          <label style={ls}>Temperatura (0 = preciso, 1 = creativo)</label>
          <input type="number" step="0.1" min="0" max="2" value={form.temperature} onChange={s('temperature')} style={fs} />
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10, paddingTop: 20 }}>
          <input type="checkbox" id="is_default" checked={form.is_default}
            onChange={e => setForm(f => ({ ...f, is_default: e.target.checked }))} />
          <label htmlFor="is_default" style={{ fontSize: 13, cursor: 'pointer' }}>
            Usar como proveedor por defecto en toda la app
          </label>
        </div>
      </div>

      {/* Info del proveedor seleccionado */}
      {models.length > 0 && (
        <div style={{ marginTop: 16, padding: '12px 14px', background: 'var(--surface-1)', borderRadius: 8, fontSize: 12, color: 'var(--text-2)' }}>
          <div style={{ fontWeight: 700, marginBottom: 8, color: 'var(--text-1)' }}>Modelos disponibles:</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 6 }}>
            {models.map(m => (
              <div key={m.id} style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-2)' }}>{m.name}</span>
                <span style={{ color: m.cost_in === 0 ? 'var(--success)' : 'var(--warning)' }}>
                  {m.cost_in === 0 ? 'Gratis' : `$${m.cost_in}/${m.cost_out}`}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 20 }}>
        <Button variant="secondary" onClick={onClose}>Cancelar</Button>
        <Button onClick={() => mutate(form)} disabled={isPending || !form.name || !form.provider} loading={isPending}>
          {isPending ? 'Guardando...' : isEdit ? 'Guardar cambios' : 'Añadir proveedor'}
        </Button>
      </div>
    </Modal>
  )
}

function TestModal({ provider, onClose }) {
  const [result, setResult] = useState(null)
  const [testing, setTesting] = useState(false)

  const runTest = async () => {
    setTesting(true)
    setResult(null)
    try {
      const res = await api.post(`/ai-providers/${provider.id}/test`)
      setResult(res.data)
    } catch (e) {
      const raw = e?.response?.data?.detail
      setResult({ ok: false, error: Array.isArray(raw) ? raw.map(d => d.msg).join(', ') : (raw || e.message) })
    } finally {
      setTesting(false)
    }
  }

  return (
    <Modal open onClose={onClose} title={`Probar — ${provider.name}`} width={480}>
      <p style={{ color: 'var(--text-2)', fontSize: 13, marginBottom: 20 }}>
        Envía un mensaje de prueba al proveedor para verificar la conexión y la API key.
      </p>
      <Button onClick={runTest} disabled={testing}>
        {testing ? '⏳ Probando...' : '🔌 Ejecutar test de conexión'}
      </Button>
      {result && (
        <div style={{ marginTop: 16, padding: '14px 16px', background: result.ok ? 'var(--success-bg)' : 'var(--danger-bg)',
          border: `1px solid ${result.ok ? 'var(--success-border)' : 'var(--danger-border)'}`, borderRadius: 8 }}>
          {result.ok ? (
            <>
              <div style={{ color: 'var(--success)', fontWeight: 700, marginBottom: 8 }}>✅ Conexión exitosa</div>
              <div style={{ fontSize: 12, color: 'var(--text-2)' }}>Respuesta: &quot;{result.response}&quot;</div>
              <div style={{ fontSize: 12, color: 'var(--text-2)', marginTop: 4 }}>Latencia: {result.latency_ms}ms · Modelo: {result.model}</div>
            </>
          ) : (
            <>
              <div style={{ color: 'var(--danger)', fontWeight: 700, marginBottom: 8 }}>❌ Error de conexión</div>
              <pre style={{ fontSize: 12, color: 'var(--warning)', whiteSpace: 'pre-wrap', margin: 0 }}>{result.error}</pre>
            </>
          )}
        </div>
      )}
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 16 }}>
        <Button variant="secondary" onClick={onClose}>Cerrar</Button>
      </div>
    </Modal>
  )
}

export default function AIHubPage() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [modal, setModal] = useState(null)
  const [testModal, setTestModal] = useState(null)
  const [tab, setTab] = useState('providers')

  const { data: providers = [], isLoading } = useQuery({
    queryKey: ['ai-providers'],
    queryFn: () => api.get('/ai-providers').then(r => r.data),
    select: d => (Array.isArray(d) ? d : []),
  })
  const { data: catalog = {} } = useQuery({
    queryKey: ['ai-providers-catalog'],
    queryFn: () => api.get('/ai-providers/catalog').then(r => r.data),
    staleTime: Infinity,
  })
  const { data: stats = {} } = useQuery({
    queryKey: ['ai-stats'],
    queryFn: () => api.get('/ai-providers/stats').then(r => r.data),
    enabled: tab === 'stats',
  })

  const { mutate: setDefault } = useMutation({
    mutationFn: id => api.post(`/ai-providers/${id}/set-default`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['ai-providers'] }),
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: del } = useMutation({
    mutationFn: id => api.delete(`/ai-providers/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['ai-providers'] }),
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const defaultProvider = providers.find(p => p.is_default)
  const byModule = stats.by_module || []

  return (
    <div style={{ padding: 32 }}>
      <PageHeader
        title={t('ai.hub_title')}
        subtitle="Configura los proveedores de IA y gestiona integraciones"
        actions={<Button onClick={() => setModal({})} icon="＋">Añadir proveedor</Button>}
      />

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 24, borderBottom: '1px solid #1e2d45', paddingBottom: 12 }}>
        {[['providers','🤖 Proveedores'],['stats','📊 Uso y costes'],['guide','📖 Guía']].map(([id, label]) => (
          <button key={id} onClick={() => setTab(id)}
            style={{ padding: '7px 16px', borderRadius: 8, border: `1px solid ${tab === id ? 'var(--accent-glow)' : 'var(--surface-4)'}`, background: tab === id ? 'var(--accent-muted)' : 'transparent', color: tab === id ? 'var(--accent)' : 'var(--text-2)', fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>
            {label}
          </button>
        ))}
      </div>

      {/* PROVIDERS TAB */}
      {tab === 'providers' && (
        <>
          {/* Proveedor activo */}
          {defaultProvider && (
            <div style={{ ...card, padding: '16px 20px', marginBottom: 20, borderColor: PROVIDER_META[defaultProvider.provider]?.color + '50' || 'var(--surface-4)', background: PROVIDER_META[defaultProvider.provider]?.color + '08' || 'var(--surface-2)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <span style={{ fontSize: 28 }}>{PROVIDER_META[defaultProvider.provider]?.icon}</span>
                <div>
                  <div style={{ fontSize: 11, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Proveedor activo por defecto</div>
                  <div style={{ fontSize: 16, fontWeight: 800 }}>{defaultProvider.name}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-2)' }}>Modelo: {defaultProvider.default_model} · {defaultProvider.total_requests} peticiones · ${defaultProvider.total_cost_usd.toFixed(4)} gastados</div>
                </div>
              </div>
            </div>
          )}

          {isLoading ? <Spinner /> : providers.length === 0 ? (
            <div style={{ ...card, padding: '48px 24px', textAlign: 'center' }}>
              <div style={{ fontSize: 48, marginBottom: 16 }}>🤖</div>
              <div style={{ fontSize: 18, fontWeight: 700, marginBottom: 8 }}>Sin proveedores de IA configurados</div>
              <div style={{ fontSize: 14, color: 'var(--text-2)', marginBottom: 24, maxWidth: 500, margin: '0 auto 24px' }}>
                Añade un proveedor para activar NexusAgent, NexusOracle, Sprint Planning IA y el resto de funciones de IA.
                Puedes usar Claude, GPT-4, Gemini, DeepSeek, Llama local y más.
              </div>
              <Button onClick={() => setModal({})}>＋ Añadir primer proveedor</Button>
            </div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 14 }}>
              {providers.map(p => {
                const meta = PROVIDER_META[p.provider] || { icon: '🤖', color: 'var(--text-2)' }
                const st   = STATUS_CFG[p.status] || STATUS_CFG.inactive
                return (
                  <div key={p.id} style={{ ...card, padding: '18px 20px', borderColor: p.is_default ? meta.color + '50' : 'var(--surface-4)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <div style={{ width: 40, height: 40, borderRadius: 10, background: meta.color + '20', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20 }}>
                          {meta.icon}
                        </div>
                        <div>
                          <div style={{ fontSize: 14, fontWeight: 700 }}>{p.name}</div>
                          <div style={{ fontSize: 11, color: 'var(--text-2)' }}>{meta.name} · {p.default_model || 'sin modelo'}</div>
                        </div>
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4 }}>
                        <span style={{ fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 20, background: st.color + '20', color: st.color, border: `1px solid ${st.color}40` }}>{st.label}</span>
                        {p.is_default && <span style={{ fontSize: 10, color: 'var(--accent)', fontWeight: 700 }}>⭐ DEFAULT</span>}
                      </div>
                    </div>

                    <div style={{ fontSize: 12, color: 'var(--text-2)', marginBottom: 12 }}>
                      {p.has_api_key ? '🔑 API key configurada' : p.provider === 'ollama' ? '🦙 Sin key (local)' : '⚠️ Sin API key'}
                      {p.last_error && <span style={{ color: 'var(--danger)', marginLeft: 8 }}>· Error: {p.last_error.slice(0, 40)}...</span>}
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 12, padding: '10px 12px', background: 'var(--surface-1)', borderRadius: 8, fontSize: 12 }}>
                      <div><span style={{ color: 'var(--text-2)' }}>Peticiones:</span> <strong>{p.total_requests}</strong></div>
                      <div><span style={{ color: 'var(--text-2)' }}>Coste:</span> <strong style={{ color: 'var(--warning)' }}>${p.total_cost_usd.toFixed(4)}</strong></div>
                    </div>

                    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                      <button onClick={() => setTestModal(p)}
                        style={{ flex: 1, padding: '7px', borderRadius: 7, border: '1px solid #1e2d45', background: 'transparent', color: 'var(--accent)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}>
                        🔌 Test
                      </button>
                      {!p.is_default && (
                        <button onClick={() => setDefault(p.id)}
                          style={{ flex: 1, padding: '7px', borderRadius: 7, border: '1px solid #00d4ff30', background: 'transparent', color: 'var(--accent)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}>
                          ⭐ Default
                        </button>
                      )}
                      <button onClick={() => setModal(p)}
                        style={{ padding: '7px 10px', borderRadius: 7, border: '1px solid #1e2d45', background: 'transparent', color: 'var(--text-2)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}>
                        ✏️
                      </button>
                      <button onClick={() => { openConfirmGlobal({ message: `¿Eliminar "${p.name}"?`, onConfirm: () => del(p.id), danger: true }) }}
                        style={{ padding: '7px 10px', borderRadius: 7, border: '1px solid #ff475730', background: 'transparent', color: 'var(--danger)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}>
                        🗑
                      </button>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </>
      )}

      {/* STATS TAB */}
      {tab === 'stats' && (
        <div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 14, marginBottom: 24 }}>
            {[
              { icon: '🤖', label: 'Proveedores', value: (stats.providers || []).length, color: 'var(--accent)' },
              { icon: '💬', label: 'Total peticiones', value: stats.total_requests || 0, color: 'var(--success)' },
              { icon: '💰', label: 'Coste total', value: `$${(stats.total_cost || 0).toFixed(4)}`, color: 'var(--warning)' },
            ].map(k => (
              <div key={k.label} style={{ ...card, padding: '18px 20px' }}>
                <div style={{ fontSize: 24, marginBottom: 8 }}>{k.icon}</div>
                <div style={{ fontSize: 22, fontWeight: 800, color: k.color }}>{k.value}</div>
                <div style={{ fontSize: 12, color: 'var(--text-2)' }}>{k.label}</div>
              </div>
            ))}
          </div>

          {byModule.length > 0 && (
            <div style={card}>
              <div style={{ padding: '16px 20px 12px', borderBottom: '1px solid #1e2d45', fontWeight: 700, fontSize: 14 }}>Uso por módulo</div>
              {byModule.map(r => (
                <div key={r.module} style={{ padding: '12px 20px', borderBottom: '1px solid #1e2d4530', display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
                  <span style={{ fontWeight: 600 }}>{r.module}</span>
                  <div style={{ display: 'flex', gap: 20, color: 'var(--text-2)' }}>
                    <span>{r.calls} llamadas</span>
                    <span>{(r.tokens || 0).toLocaleString()} tokens</span>
                    <span style={{ color: 'var(--warning)' }}>${r.cost.toFixed(4)}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* GUIDE TAB */}
      {tab === 'guide' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          {[
            { icon: '🟠', title: 'Anthropic (Claude)', desc: 'Los modelos Claude son los más capaces para análisis de proyectos y razonamiento complejo. Recomendado para NexusOracle y Sprint Planning IA.', link: PROVIDER_DOCS.anthropic, hint: 'sk-ant-...' },
            { icon: '🟢', title: 'OpenAI (GPT)', desc: 'GPT-4o es excelente para generación de texto y análisis. GPT-4o mini ofrece gran calidad a bajo coste para uso intensivo.', link: PROVIDER_DOCS.openai, hint: 'sk-...' },
            { icon: '🔵', title: 'Google Gemini', desc: 'Gemini 2.5 Pro tiene la ventana de contexto más grande (1M tokens), ideal para analizar proyectos muy grandes.', link: PROVIDER_DOCS.gemini, hint: 'AIza...' },
            { icon: '🐋', title: 'DeepSeek', desc: 'DeepSeek-V3 ofrece rendimiento comparable a GPT-4 a un precio 10x menor. DeepSeek-R1 es especialista en razonamiento.', link: PROVIDER_DOCS.deepseek, hint: 'sk-...' },
            { icon: '⚡', title: 'Groq (ultra-rápido)', desc: 'Groq ejecuta modelos open-source (Llama 4, QwQ) a velocidades extremas. Ideal para respuestas en tiempo real.', link: PROVIDER_DOCS.groq, hint: 'gsk_...' },
            { icon: '🌪', title: 'Mistral AI', desc: 'Mistral Large y Codestral ofrecen gran rendimiento en razonamiento y código. Modelos open-weight disponibles también via Ollama.', link: PROVIDER_DOCS.mistral, hint: '...' },
            { icon: '🦙', title: 'Ollama (local)', desc: 'Ejecuta Llama, Mistral, Phi, Gemma y otros modelos en tu propio hardware. Sin coste por token y con total privacidad de datos.', link: PROVIDER_DOCS.ollama, hint: 'Sin API key' },
            { icon: '☁️', title: 'Azure OpenAI', desc: 'Accede a modelos GPT-4o y o-series a través de Azure con cumplimiento empresarial, SLA y datos en tu región.', link: PROVIDER_DOCS.azure, hint: '(Azure API key)' },
          ].map(p => (
            <div key={p.title} style={{ ...card, padding: '18px 20px' }}>
              <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start', marginBottom: 10 }}>
                <span style={{ fontSize: 24 }}>{p.icon}</span>
                <div>
                  <div style={{ fontSize: 14, fontWeight: 700 }}>{p.title}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-2)', marginTop: 4, lineHeight: 1.5 }}>{p.desc}</div>
                </div>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 10 }}>
                <span style={{ fontSize: 11, color: 'var(--text-3)', fontFamily: 'monospace' }}>{p.hint}</span>
                <a href={p.link} target="_blank" rel="noreferrer" style={{ fontSize: 12, color: 'var(--accent)' }}>Obtener key →</a>
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
    </div>
  )
}
