import type { CSSProperties } from 'react'
import { useState, useEffect } from 'react'
import { extractErr } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { semanticApi, usersApi } from '../services/api'
import { Button, EmptyState, Modal } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Brain } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import useMediaQuery from '../hooks/useMediaQuery'

const card: CSSProperties = { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12 }
const fs: CSSProperties = { background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 12px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', width: '100%' }
const ls: CSSProperties = { fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', display: 'block', marginBottom: 5 }

const ENGINE_MODES: Record<string, { label: string; icon: string; desc: string }> = {
  hybrid:     { label: 'Híbrido',       icon: '⚡', desc: 'Semántico primero, LLM como desempate. Recomendado.' },
  semantic:   { label: 'Solo semántico', icon: '🧠', desc: 'Sin API key necesaria. Usa embeddings locales (TF-IDF o sentence-transformers).' },
  llm:        { label: 'Solo LLM',       icon: '🤖', desc: 'Usa el proveedor IA configurado en IA & Conectores.' },
  rules_only: { label: 'Solo reglas',    icon: '📋', desc: 'Sin IA, solo reglas de negocio y carga de trabajo.' },
}

const EMBEDDINGS_BACKENDS: Record<string, { label: string; desc: string }> = {
  tfidf: {
    label: 'TF-IDF (ligero)',
    desc: 'Sin descarga de modelos. Menor precision, arranque inmediato.',
  },
  transformer: {
    label: 'Transformer (Hugging Face)',
    desc: 'Mejor precision semantica. Requiere dependencias ML y descarga de modelo.',
  },
}

const _COMPLEXITY_CFG = {
  simple:  { label: 'Simple',   color: 'var(--success)', bg: 'var(--success-bg)' },
  medium:  { label: 'Media',    color: 'var(--warning)', bg: 'var(--warning-bg)' },
  complex: { label: 'Compleja', color: 'var(--danger)', bg: 'var(--danger-bg)' },
}

function ProfileModal({ user, onClose }: { user: any; onClose: () => void }) {
  const traducir = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [text, setText] = useState<string>(user?.profile_text || '')
  const [maxLoad, setMaxLoad] = useState<number>(user?.max_load || 10)

  const { mutate, isPending } = useMutation({
    mutationFn: (d: Record<string, unknown>) => semanticApi.createProfile(d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sem-profiles'] }); onClose() },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  return (
    <Modal open onClose={onClose} title={`Perfil semántico — ${user?.user_name || 'Usuario'}`} width={600}>
      <p style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginBottom: 16, lineHeight: 1.6 }}>
        {traducir('semanticengine.describe_las_capacidades_rol_tecnologias_y_area')}
      </p>
      <div style={{ marginBottom: 14 }}>
        <label style={ls}>{traducir('semanticengine.texto_del_perfil')}</label>
        <textarea value={text} onChange={e => setText(e.target.value)} rows={6}
          style={{ ...fs, resize: 'vertical', lineHeight: 1.6 }}
          placeholder={traducir('semanticengine.describe_las_capacidades_rol_tecnologias_y_area_2')} />
      </div>
      <div style={{ marginBottom: 20 }}>
        <label style={ls}>{traducir('semanticengine.carga_maxima_simultanea_tickets_tareas')}</label>
        <input type="number" value={maxLoad} onChange={e => setMaxLoad(parseInt(e.target.value))}
          style={{ ...fs, width: 100 }} min={1} max={50} />
      </div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
        <Button variant="secondary" onClick={onClose}>Cancelar</Button>
        <Button onClick={() => mutate({ user_id: user.user_id, profile_text: text, max_load: maxLoad })}
          disabled={isPending || !text.trim()} loading={isPending}>
          {isPending ? 'Guardando...' : 'Guardar perfil'}
        </Button>
      </div>
    </Modal>
  )
}

function TestPanel() {
  const traducir = useAppT()
  const [type, setType] = useState('ticket')
  const [title, setTitle] = useState('')
  const [desc, setDesc] = useState('')
  const [result, setResult] = useState<any>(null)
  const [testing, setTesting] = useState(false)

  const runTest = async () => {
    if (!title.trim()) return
    setTesting(true)
    setResult(null)
    try {
      const fn = type === 'ticket' ? semanticApi.suggestTicket : semanticApi.suggestTask
      const res = await fn({ title, description: desc })
      setResult(res.data)
    } catch (e) {
      const raw = (e as any)?.response?.data?.detail
      setResult({ error: Array.isArray(raw) ? raw.map((d: any) => d.msg).join(', ') : (raw || 'Error') })
    } finally { setTesting(false) }
  }

  return (
    <div style={{ ...card, padding: '20px 24px' }}>
      <div style={{ fontSize: "var(--text-md)", fontWeight: 600, marginBottom: 16 }}>{traducir('semanticengine.probar_asignacion')}</div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 20 , borderBottom: '1px solid var(--surface-4)', paddingBottom: 12 }}>
        {['ticket', 'task'].map(t => (
          <button key={t} onClick={() => setType(t)}
            style={{ padding: '6px 16px', borderRadius: 8, border: `1px solid ${type === t ? 'var(--accent)' : 'var(--surface-4)'}`, background: type === t ? 'var(--accent-muted)' : 'transparent', color: type === t ? 'var(--accent)' : 'var(--text-2)', fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}>
            {t === 'ticket' ? '🎫 Ticket' : '✅ Tarea'}
          </button>
        ))}
      </div>
      <div style={{ display: 'grid', gap: 12, marginBottom: 14 }}>
        <div>
          <label style={ls}>{traducir('semanticengine.titulo')}</label>
          <input value={title} onChange={e => setTitle(e.target.value)} style={fs}
            placeholder={type === 'ticket' ? 'Error al iniciar sesión en el portal' : 'Implementar endpoint de autenticación JWT'} />
        </div>
        <div>
          <label style={ls}>{traducir('semanticengine.descripcion_opcional')}</label>
          <textarea value={desc} onChange={e => setDesc(e.target.value)} rows={3}
            style={{ ...fs, resize: 'vertical' }} placeholder={traducir('semanticengine.descripcion_opcional_del_ticket_o_tarea')} />
        </div>
      </div>
      <Button onClick={runTest} disabled={testing || !title.trim()}>
        {testing ? '⏳ Analizando...' : '▶ Sugerir asignación'}
      </Button>

      {result && (
        <div style={{ marginTop: 16, padding: '14px 16px', background: 'var(--surface-1)', borderRadius: 10 }}>
          {result.error ? (
            <div style={{ color: 'var(--danger)' }}>❌ {result.error}</div>
          ) : (
            <>
              <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10, marginBottom: 12 }}>
                <div>
                  <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginBottom: 4 }}>{traducir('semanticengine.asignacion_sugerida')}</div>
                  <div style={{ fontSize: "var(--text-lg)", fontWeight: 800, color: result.needs_review ? 'var(--warning)' : 'var(--success)' }}>
                    {result.suggested_user_name || result.suggested_user_id || '— Sin candidato —'}
                  </div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginBottom: 4 }}>Confianza</div>
                  <div style={{ fontSize: "var(--text-xl)", fontWeight: 800, color: result.confidence > 0.7 ? 'var(--success)' : result.confidence > 0.5 ? 'var(--warning)' : 'var(--danger)' }}>
                    {Math.round((result.confidence || 0) * 100)}%
                  </div>
                </div>
              </div>
              <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginBottom: 10 }}>
                <span style={{ marginRight: 12 }}>Motor: <strong style={{ color: 'var(--text-1)' }}>{result.engine_mode}</strong></span>
                {result.needs_review && <span style={{ color: 'var(--warning)' }}>⚠ Revisar manualmente</span>}
              </div>
              {result.reasoning && (
                <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginBottom: 10, fontStyle: 'italic' }}>
                  {result.reasoning}
                </div>
              )}
              {result.top_candidates && Object.keys(result.top_candidates).length > 0 && (
                <div>
                  <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginBottom: 6, fontWeight: 700, textTransform: 'uppercase' }}>Top candidatos</div>
                  {Object.entries(result.top_candidates).map(([uid, info]: [string, any]) => (
                    <div key={uid} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', fontSize: "var(--text-sm)" }}>
                      <span>{info.name}</span>
                      <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent)' }}>{Math.round(info.score * 100)}%</span>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}

export default function SemanticEnginePage() {
  const isNarrow = useMediaQuery('(max-width: 900px)')
  const traducir = useAppT()
  const _t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [tab, setTab] = useState('overview')
  const [editProfile, setEditProfile] = useState<any>(null)
  const [opStatus, setOpStatus] = useState<{ type: string; startedAt: number | null }>({ type: 'idle', startedAt: null })
  const [opElapsed, setOpElapsed] = useState(0)
  const [hfModelDraft, setHfModelDraft] = useState('')

  useEffect(() => {
    if (!opStatus.startedAt) {
      setOpElapsed(0)
      return
    }
    const startedAt = opStatus.startedAt
    const id = setInterval(() => {
      setOpElapsed(Math.floor((Date.now() - startedAt) / 1000))
    }, 1000)
    return () => clearInterval(id)
  }, [opStatus.startedAt])

  const { data: config = {}, isLoading: _loadingCfg } = useQuery<Record<string, any>>({
    queryKey: ['sem-config'],
    queryFn: () => semanticApi.config().then((r: { data: Record<string, any> }) => r.data),
  })

  useEffect(() => {
    setHfModelDraft(config.local_model_name && config.local_model_name !== 'tfidf' ? config.local_model_name : 'all-MiniLM-L6-v2')
  }, [config.local_model_name])
  const { data: profiles = [], isLoading: _loadingProfiles } = useQuery<any[]>({
    queryKey: ['sem-profiles'],
    queryFn: () => semanticApi.profiles().then((r: { data: any[] }) => r.data),
    enabled: tab === 'profiles' || tab === 'overview',
  })
  const { data: stats = {} } = useQuery<Record<string, any>>({
    queryKey: ['sem-stats'],
    queryFn: () => semanticApi.stats().then((r: { data: Record<string, any> }) => r.data),
  })
  const { data: users = [] } = useQuery<any[]>({
    queryKey: ['users'],
    queryFn: () => usersApi.list().then((r: { data: any[] }) => r.data),
    enabled: tab === 'profiles',
  })

  const { mutate: saveConfig, isPending: savingConfig } = useMutation({
    mutationFn: (d: Record<string, unknown>) => semanticApi.updateConfig(d).then((r: { data: unknown }) => r.data),
    onMutate: async (patch) => {
      await qc.cancelQueries({ queryKey: ['sem-config'] })
      const previous = qc.getQueryData(['sem-config'])
      qc.setQueryData(['sem-config'], (current: any) => ({ ...(current || {}), ...patch }))
      return { previous }
    },
    onSuccess: (data: any) => {
      if (data?.config) qc.setQueryData(['sem-config'], data.config)
      toast.success('Configuración del motor actualizada')
    },
    onError: (e, _patch, ctx) => {
      if (ctx?.previous) qc.setQueryData(['sem-config'], ctx.previous)
      toast.error(extractErr(e, 'Error al actualizar el motor de asignación'))
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ['sem-config'] }),
  })
  const { mutate: autoGenerate, isPending: generating } = useMutation({
    mutationFn: () => semanticApi.autoGenerate(),
    onMutate: () => setOpStatus({ type: 'generating', startedAt: Date.now() }),
    onSuccess: d => {
      qc.invalidateQueries({ queryKey: ['sem-profiles'] })
      toast.success(`✅ ${d.data.created} creados, ${d.data.updated} actualizados`)
      setOpStatus({ type: 'done', startedAt: null })
    },
    onError: e => {
      toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
      setOpStatus({ type: 'failed', startedAt: null })
    },
  })
  const { mutate: rebuildEmb, isPending: rebuilding } = useMutation({
    mutationFn: () => semanticApi.rebuildEmbeddings(),
    onMutate: () => setOpStatus({ type: 'rebuilding', startedAt: Date.now() }),
    onSuccess: d => {
      toast.success(`✅ ${d.data.rebuilt} embeddings reconstruidos`)
      setOpStatus({ type: 'done', startedAt: null })
    },
    onError: e => {
      toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
      setOpStatus({ type: 'failed', startedAt: null })
    },
  })

  const profilesWithUsers = users.map(u => {
    const p = profiles.find(p => p.user_id === u.id)
    return { ...p, user_id: u.id, user_name: u.full_name, has_profile: !!p }
  })

  return (
    <PageShell>
      <PageHeader
        icon={<Brain size={18} />}
        title={_t('semantic_engine.title')}
        subtitle={_t('semantic_engine.subtitle')}
        actions={
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center' }}>
            {(generating || rebuilding || opStatus.type === 'failed' || opStatus.type === 'done') && (
              <div style={{
                fontSize: "var(--text-sm)",
                color: generating || rebuilding ? 'var(--warning)' : opStatus.type === 'failed' ? 'var(--danger)' : 'var(--success)'
              }}>
                {generating ? `Generando perfiles… ${opElapsed}s` : rebuilding ? `Reconstruyendo embeddings… ${opElapsed}s` : opStatus.type === 'failed' ? 'Última operación: fallo' : 'Última operación: completada'}
              </div>
            )}
            <Button variant="secondary" onClick={() => rebuildEmb()} disabled={rebuilding}>
              {rebuilding ? 'Reconstruyendo...' : '🔄 Reconstruir embeddings'}
            </Button>
            <Button onClick={() => autoGenerate()} disabled={generating}>
              {generating ? 'Generando...' : '✨ Auto-generar perfiles'}
            </Button>
          </div>
        }
      showListExport={false}
      />

      {/* KPIs */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(120px, 100%), 1fr))', gap: 12, marginBottom: 24 }}>
        {[
          { icon: '🎯', label: 'Sugerencias', value: stats.total_suggestions || 0, color: 'var(--accent)' },
          { icon: '✅', label: 'Aceptadas', value: stats.accepted || 0, color: 'var(--success)' },
          { icon: '❌', label: 'Rechazadas', value: stats.rejected || 0, color: 'var(--danger)' },
          { icon: '📊', label: 'Precisión', value: stats.accuracy_pct != null ? `${stats.accuracy_pct}%` : '—', color: 'var(--warning)' },
          { icon: '🧠', label: 'Perfiles', value: stats.profiles || 0, color: 'var(--purple)' },
        ].map(k => (
          <div key={k.label} style={{ ...card, padding: '14px 18px' }}>
            <div style={{ fontSize: "var(--text-xl-em)", marginBottom: 4 }}>{k.icon}</div>
            <div style={{ fontSize: "var(--text-xl)", fontWeight: 800, color: k.color }}>{k.value}</div>
            <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>{k.label}</div>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 24, borderBottom: '1px solid var(--surface-4)', paddingBottom: 12 }}>
        {[['overview','⚙️ Configuración'],['profiles','👥 Perfiles'],['test','🧪 Probar'],['stats','📊 Estadísticas']].map(([id, label]) => (
          <button key={id} onClick={() => setTab(id)}
            style={{ padding: '5px 14px', borderRadius: 6, border: `1px solid ${tab === id ? 'var(--accent)' : 'var(--surface-4)'}`, background: tab === id ? 'var(--accent-muted)' : 'transparent', color: tab === id ? 'var(--accent)' : 'var(--text-2)', fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}>
            {label}
          </button>
        ))}
      </div>

      {/* CONFIG TAB */}
      {tab === 'overview' && (
        <div style={{ display: 'grid', gridTemplateColumns: isNarrow ? 'minmax(0, 1fr)' : '1fr 1fr', gap: 20 }}>
          <div style={{ ...card, padding: '20px 24px' }}>
            <div style={{ fontSize: "var(--text-md)", fontWeight: 600, marginBottom: 16 }}>{traducir('semanticengine.modo_del_motor')}</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {Object.entries(ENGINE_MODES).map(([key, meta]) => (
                <button key={key} onClick={() => saveConfig({ engine_mode: key })} disabled={savingConfig}
                  style={{ padding: '12px 16px', borderRadius: 8, border: `2px solid ${config.engine_mode === key ? 'var(--accent)' : 'var(--surface-4)'}`, background: config.engine_mode === key ? 'var(--accent-muted)' : 'transparent', cursor: savingConfig ? 'wait' : 'pointer', fontFamily: 'inherit', textAlign: 'left', transition: 'all 0.15s', opacity: savingConfig ? 0.7 : 1 }}>
                  <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                    <span style={{ fontSize: "var(--text-xl)" }}>{meta.icon}</span>
                    <div>
                      <div style={{ fontSize: "var(--text-xs)", color: config.engine_mode === key ? 'var(--accent)' : 'var(--text-1)' }}>{meta.label}</div>
                      <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginTop: 2 }}>{meta.desc}</div>
                    </div>
                    {config.engine_mode === key && <span style={{ marginLeft: 'auto', color: 'var(--accent)', fontSize: "var(--text-lg-em)" }}>{savingConfig ? '⟳' : '✓'}</span>}
                  </div>
                </button>
              ))}
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div style={{ ...card, padding: '20px 24px' }}>
              <div style={{ fontSize: "var(--text-md)", fontWeight: 700, marginBottom: 16 }}>Embeddings y modelo</div>

              <div style={{ marginBottom: 14 }}>
                <label style={ls}>{traducir('semanticengine.backend_de_embeddings')}</label>
                <select
                  value={config.embeddings_backend || 'tfidf'}
                  onChange={e => {
                    const backend = e.target.value
                    if (backend === 'transformer') {
                      const modelName = (hfModelDraft || config.local_model_name || 'all-MiniLM-L6-v2').trim()
                      saveConfig({ embeddings_backend: 'transformer', local_model_name: modelName || 'all-MiniLM-L6-v2' })
                      return
                    }
                    saveConfig({ embeddings_backend: 'tfidf', local_model_name: 'tfidf' })
                  }}
                  style={fs}
                  disabled={savingConfig}
                >
                  {Object.entries(EMBEDDINGS_BACKENDS).map(([key, meta]) => (
                    <option key={key} value={key}>{meta.label}</option>
                  ))}
                </select>
                <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginTop: 6 }}>
                  {EMBEDDINGS_BACKENDS[config.embeddings_backend || 'tfidf']?.desc}
                </div>
              </div>

              <div style={{ marginBottom: 10 }}>
                <label style={ls}>Modelo Hugging Face</label>
                <div style={{ display: 'flex', gap: 8 }}>
                  <input
                    value={hfModelDraft}
                    onChange={e => setHfModelDraft(e.target.value)}
                    placeholder="all-MiniLM-L6-v2 o sentence-transformers/all-MiniLM-L6-v2"
                    style={{ ...fs, minWidth: 0 }}
                    disabled={(config.embeddings_backend || 'tfidf') !== 'transformer' || savingConfig}
                  />
                  <Button
                    variant="secondary"
                    disabled={(config.embeddings_backend || 'tfidf') !== 'transformer' || savingConfig || !hfModelDraft.trim()}
                    onClick={() => saveConfig({ embeddings_backend: 'transformer', local_model_name: hfModelDraft.trim() })}
                  >
                    Guardar
                  </Button>
                </div>
              </div>

              <div style={{ marginTop: 12, padding: '10px 12px', background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 8, fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>
                <div>Backend activo: <strong style={{ color: 'var(--text-1)' }}>{config.embeddings_backend || 'tfidf'}</strong></div>
                <div>Modelo efectivo: <strong style={{ color: 'var(--text-1)' }}>{config.effective_model_name || (config.local_model_name || 'all-MiniLM-L6-v2')}</strong></div>
              </div>
            </div>

            <div style={{ ...card, padding: '20px 24px' }}>
              <div style={{ fontSize: "var(--text-md)", fontWeight: 700, marginBottom: 16 }}>{traducir('semanticengine.umbrales_de_confianza')}</div>
              {[
                { key: 'threshold_ticket', label: 'Tickets (mín. para auto-asignar)', val: config.threshold_ticket },
                { key: 'threshold_task',   label: 'Tareas (mín. para auto-asignar)',  val: config.threshold_task },
                { key: 'threshold_expert_cache', label: 'Expert cache semántico (sim. coseno)', val: config.threshold_expert_cache },
                { key: 'load_balance_weight', label: 'Peso balanceo de carga (0-1)', val: config.load_balance_weight },
              ].map(f => (
                <div key={f.key} style={{ marginBottom: 12 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                    <label style={{ ...ls, marginBottom: 0 }}>{f.label}</label>
                    <span style={{ fontSize: "var(--text-base)", fontWeight: 700, color: 'var(--accent)', fontFamily: 'var(--font-mono)' }}>{f.val}</span>
                  </div>
                  <input type="range" min={f.key === 'load_balance_weight' ? '0.0' : '0.3'} max="0.99" step="0.01"
                    value={f.val || 0.6}
                    onChange={e => saveConfig({ [f.key]: parseFloat(e.target.value) })}
                    style={{ width: '100%', accentColor: 'var(--accent)' }} />
                </div>
              ))}
            </div>

            <div style={{ ...card, padding: '20px 24px' }}>
              <div style={{ fontSize: "var(--text-md)", fontWeight: 700, marginBottom: 16 }}>{traducir('semanticengine.auto_asignacion')}</div>
              {[
                { key: 'auto_assign_tickets', label: 'Auto-asignar tickets (sin confirmación)', val: config.auto_assign_tickets },
                { key: 'auto_assign_tasks',   label: 'Auto-asignar tareas (sin confirmación)',  val: config.auto_assign_tasks },
              ].map(f => (
                <div key={f.key} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 0', borderBottom: '1px solid color-mix(in srgb, var(--surface-4) 19%, transparent)' }}>
                  <span style={{ fontSize: "var(--text-base)" }}>{f.label}</span>
                  <button onClick={() => saveConfig({ [f.key]: !f.val })}
                    style={{ width: 44, height: 24, borderRadius: 12, background: f.val ? 'var(--success-border)' : 'var(--surface-4)', border: `1px solid ${f.val ? 'rgba(52,211,153,0.38)' : 'var(--surface-4)'}`, cursor: 'pointer', position: 'relative', transition: 'all 0.2s' }}>
                    <div style={{ width: 18, height: 18, borderRadius: 9, background: f.val ? 'var(--success)' : 'var(--text-2)', position: 'absolute', top: 2, left: f.val ? 22 : 2, transition: 'all 0.2s' }} />
                  </button>
                </div>
              ))}
              <div style={{ marginTop: 12, padding: '10px 12px', background: 'var(--warning-bg)', border: '1px solid var(--warning-border)', borderRadius: 8, fontSize: "var(--text-xs)", color: 'var(--warning)' }}>
                {traducir('semanticengine.con_auto_asignacion_activada_los_items_se')}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* PROFILES TAB */}
      {tab === 'profiles' && (
        <div>
          <div style={{ ...card, overflow: 'hidden' }}>
            <div style={{ overflowX: 'auto' }}>
            <div style={{ minWidth: 900 }}>
            <div style={{ padding: '12px 20px', borderBottom: '1px solid var(--surface-4)', display: 'grid', gridTemplateColumns: '1fr 200px 80px 80px 120px 100px', gap: 16, fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase' }}>
              <span>Usuario</span><span>Perfil</span><span>Tickets</span><span>Tareas</span><span>Estado</span><span>{traducir('semanticengine.accion')}</span>
            </div>
            {profilesWithUsers.length === 0 ? (
              <div style={{ padding: 32, textAlign: 'center' }}>
                <EmptyState icon="👥" title={traducir('semanticengine.sin_perfiles_semanticos')} description="Configura perfiles para habilitar la asignacion automatica" />
              </div>
            ) : profilesWithUsers.map(u => (
              <div key={u.user_id} style={{ padding: '12px 20px', borderBottom: '1px solid color-mix(in srgb, var(--surface-4) 19%, transparent)', display: 'grid', gridTemplateColumns: '1fr 200px 80px 80px 120px 100px', gap: 16, alignItems: 'center', fontSize: "var(--text-base)" }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontWeight: 600 }}>{u.user_name}</div>
                  {u.profile_text && <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{u.profile_text}</div>}
                </div>
                <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                  <span style={{ width: 8, height: 8, borderRadius: '50%', background: u.has_embedding ? 'var(--success)' : u.has_profile ? 'var(--warning)' : 'var(--danger)', flexShrink: 0 }} />
                  <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>
                    {u.has_embedding ? 'Embedding OK' : u.has_profile ? 'Sin embedding' : 'Sin perfil'}
                  </span>
                </div>
                <span style={{ color: 'var(--accent)', fontWeight: 600 }}>{u.open_tickets || 0}</span>
                <span style={{ color: 'var(--warning)', fontWeight: 600 }}>{u.open_tasks || 0}</span>
                <span style={{ fontSize: "var(--text-xs)", padding: '2px 8px', borderRadius: 12, background: u.is_available !== false ? 'var(--success-bg)' : 'var(--danger-bg)', color: u.is_available !== false ? 'var(--success)' : 'var(--danger)', fontWeight: 700 }}>
                  {u.is_available !== false ? 'Disponible' : 'No disponible'}
                </span>
                <button onClick={() => setEditProfile(u)}
                  style={{ padding: '5px 12px', borderRadius: 6, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--accent)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>
                  ✏️ Editar
                </button>
              </div>
            ))}
            </div>
            </div>
          </div>
        </div>
      )}

      {/* TEST TAB */}
      {tab === 'test' && <TestPanel />}

      {/* STATS TAB */}
      {tab === 'stats' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

          {/* Top row: acceptance gauge + pipeline bar */}
          <div style={{ display: 'grid', gridTemplateColumns: isNarrow ? 'minmax(0, 1fr)' : '1fr 2fr', gap: 16 }}>
            {/* Acceptance gauge */}
            <div style={{ ...card, padding: '20px 24px', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
              <div style={{ fontSize: "var(--text-base)", fontWeight: 700, marginBottom: 16, alignSelf: 'flex-start' }}>{traducir('semanticengine.tasa_de_aceptacion')}</div>
              {(() => {
                const acc = stats.accepted || 0
                const rej = stats.rejected || 0
                const tot = acc + rej
                const pct = tot > 0 ? Math.round(acc / tot * 100) : null
                const r = 44, circ = 2 * Math.PI * r
                const offset = pct != null ? circ * (1 - pct / 100) : circ
                return (
                  <div style={{ position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <svg width={116} height={116} viewBox="0 0 116 116">
                      <circle cx={58} cy={58} r={r} fill="none" stroke="var(--surface-4)" strokeWidth={10} />
                      <circle cx={58} cy={58} r={r} fill="none"
                        stroke={pct == null ? 'var(--surface-4)' : pct >= 70 ? 'var(--success)' : pct >= 40 ? 'var(--warning)' : 'var(--danger)'}
                        strokeWidth={10} strokeLinecap="round"
                        strokeDasharray={circ} strokeDashoffset={offset}
                        transform="rotate(-90 58 58)" style={{ transition: 'stroke-dashoffset 0.6s ease' }} />
                    </svg>
                    <div style={{ position: 'absolute', textAlign: 'center' }}>
                      <div style={{ fontSize: "var(--text-xl-em)", fontWeight: 900, color: 'var(--text-1)' }}>
                        {pct != null ? `${pct}%` : '—'}
                      </div>
                      <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)' }}>{tot} evaluadas</div>
                    </div>
                  </div>
                )
              })()}
              <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'center', gap: 12, marginTop: 12, fontSize: "var(--text-xs)" }}>
                {[['✅', stats.accepted || 0, 'var(--success)', 'Aceptadas'],
                  ['❌', stats.rejected || 0, 'var(--danger)', 'Rechazadas'],
                  ['⏳', stats.pending || 0, 'var(--text-3)', 'Pendientes']].map(([_ic, v, c, l]) => (
                  <div key={l} style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: "var(--text-lg)", fontWeight: 800, color: c }}>{v}</div>
                    <div style={{ color: 'var(--text-3)' }}>{l}</div>
                  </div>
                ))}
              </div>
            </div>

            {/* Stacked breakdown */}
            <div style={{ ...card, padding: '20px 24px' }}>
              <div style={{ fontSize: "var(--text-base)", fontWeight: 700, marginBottom: 16 }}>{traducir('semanticengine.distribucion_de_sugerencias')}</div>
              {(() => {
                const tot = (stats.accepted||0) + (stats.rejected||0) + (stats.pending||0)
                if (tot === 0) return <div style={{ color: 'var(--text-2)', fontSize: "var(--text-base)" }}>{traducir('semanticengine.sin_datos_todavia_procesa_algunas_tareas_o')}</div>
                const bars = [
                  { label: 'Aceptadas', val: stats.accepted||0, color: 'var(--success)' },
                  { label: 'Rechazadas', val: stats.rejected||0, color: 'var(--danger)' },
                  { label: 'Sin evaluar', val: stats.pending||0, color: 'var(--surface-5)' },
                ]
                return (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                    {/* Single stacked bar */}
                    <div style={{ display: 'flex', height: 24, borderRadius: 6, overflow: 'hidden', gap: 2 }}>
                      {bars.map(b => b.val > 0 && (
                        <div key={b.label} style={{ flex: b.val / tot, background: b.color, transition: 'flex 0.4s ease' }} title={`${b.label}: ${b.val}`} />
                      ))}
                    </div>
                    {/* Legend rows */}
                    {bars.map(b => (
                      <div key={b.label} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <div style={{ width: 10, height: 10, borderRadius: 3, background: b.color, flexShrink: 0 }} />
                        <div style={{ flex: 1 }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
                            <span style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>{b.label}</span>
                            <span style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: b.color }}>{b.val} ({tot > 0 ? Math.round(b.val/tot*100) : 0}%)</span>
                          </div>
                          <div style={{ height: 4, borderRadius: 2, background: 'var(--surface-4)', overflow: 'hidden' }}>
                            <div style={{ height: '100%', width: `${tot > 0 ? b.val/tot*100 : 0}%`, background: b.color, transition: 'width 0.4s ease' }} />
                          </div>
                        </div>
                      </div>
                    ))}
                    {/* By mode */}
                    {Object.keys(stats.by_mode || {}).length > 0 && (
                      <div style={{ marginTop: 8, borderTop: '1px solid var(--surface-4)', paddingTop: 12 }}>
                        <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', marginBottom: 8 }}>{traducir('semanticengine.pipeline_de_resolucion')}</div>
                        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                          {Object.entries(stats.by_mode).map(([mode, count]: [string, any]) => (
                            <div key={mode} style={{ padding: '4px 10px', borderRadius: 20, background: 'var(--surface-3)', fontSize: "var(--text-xs)", color: 'var(--text-1)' }}>
                              {ENGINE_MODES[mode]?.icon} {ENGINE_MODES[mode]?.label || mode}: <strong>{count}</strong>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )
              })()}
            </div>
          </div>

          {/* Bottom row: system status */}
          <div style={{ ...card, padding: '20px 24px' }}>
            <div style={{ fontSize: "var(--text-base)", fontWeight: 700, marginBottom: 16 }}>{traducir('semanticengine.estado_del_sistema')}</div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(180px, 100%), 1fr))', gap: 12 }}>
              {[
                { label: 'Expert cache', value: stats.cache_size || 0, icon: '⚡', hint: 'Items en caché exacta', color: 'var(--accent)' },
                { label: 'Feedback experto', value: stats.expert_feedback || 0, icon: '🧓', hint: 'Correcciones manuales', color: 'var(--success)' },
                { label: 'Perfiles con vector', value: profiles.filter(p => p.has_embedding).length, icon: '🧬', hint: `de ${profiles.length} perfiles`, color: 'var(--purple)' },
              ].map(s => (
                <div key={s.label} style={{ padding: '14px 16px', background: 'var(--surface-1)', borderRadius: 10, display: 'flex', gap: 12, alignItems: 'center' }}>
                  <span style={{ fontSize: "var(--text-2xl)" }}>{s.icon}</span>
                  <div>
                    <div style={{ fontSize: "var(--text-xl-em)", fontWeight: 900, color: s.color }}>{s.value}</div>
                    <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--text-1)' }}>{s.label}</div>
                    <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)' }}>{s.hint}</div>
                  </div>
                </div>
              ))}
            </div>
            <div style={{ marginTop: 14, padding: '12px 14px', background: 'var(--surface-1)', borderRadius: 8, fontSize: "var(--text-sm)", color: 'var(--text-2)', lineHeight: 1.6 }}>
              {traducir('semanticengine.para_mejorar_la_precision_genera_perfiles_automaticos')}
            </div>
          </div>
        </div>
      )}

      {editProfile && (
        <ProfileModal user={editProfile} onClose={() => setEditProfile(null)} />
      )}
    </PageShell>
  )
}
