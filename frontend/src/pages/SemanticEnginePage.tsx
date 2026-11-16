/*
 * SemanticEnginePage — asignación de tareas y tickets con IA.
 *
 * 16-11-2026: pasada de diseño. Título como el menú ("Asignación IA"); KPIs
 * con KpiCard e icono lucide (antes emojis); pestañas con Tabs (antes control
 * segmentado propio con emojis); modos, tipo de prueba, estado del sistema y
 * resolución por modo con iconos lucide; botones del kit con icono; modo y
 * método mostrados con su etiqueta traducida (antes "hybrid", "tfidf"...);
 * textos sin emojis ni jerga ("embeddings", "backend", "expert cache").
 */
import type { CSSProperties, ReactNode } from 'react'
import type { AxiosError } from 'axios'
import { useState, useEffect, useId } from 'react'
import { extractErr } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { semanticApi, usersApi } from '../services/api'
import type { ConfigDelMotorSemantico, EstadisticasDelMotorSemantico, PerfilSemantico, SugerenciaDeAsignacionDeTicket } from '../services/api/tipos-analitica'
import { Button, EmptyState, KpiCard, Modal, Tabs } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { AlertTriangle, BarChart3, Bot, Brain, Check, CheckCircle2, CheckSquare, FlaskConical, Info, Layers, ListChecks, Loader2, Pencil, RefreshCw, Settings, Sparkles, Target, Ticket, UserCheck, Users, Wand2, XCircle, Zap } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import { CLOCK_TICK_MS } from '../constants/timings'
import './SemanticEnginePage.css'

const fs = 'ds-input sem-input'
const ls = 'sem-label'
const cVar = (color: string) => ({ '--sem-c': color } as CSSProperties)

// Textos: claves de i18n del bloque `semanticengine`.
const ENGINE_MODES: Record<string, { label: string; icon: ReactNode; desc: string }> = {
  hybrid:     { label: 'semanticengine.modo_hybrid',     icon: <Zap size={16} />,        desc: 'semanticengine.modo_hybrid_desc' },
  semantic:   { label: 'semanticengine.modo_semantic',   icon: <Brain size={16} />,      desc: 'semanticengine.modo_semantic_desc' },
  llm:        { label: 'semanticengine.modo_llm',        icon: <Bot size={16} />,        desc: 'semanticengine.modo_llm_desc' },
  rules_only: { label: 'semanticengine.modo_rules_only', icon: <ListChecks size={16} />, desc: 'semanticengine.modo_rules_only_desc' },
}

const EMBEDDINGS_BACKENDS: Record<string, { label: string; desc: string }> = {
  tfidf:       { label: 'semanticengine.backend_tfidf',       desc: 'semanticengine.backend_tfidf_desc' },
  transformer: { label: 'semanticengine.backend_transformer', desc: 'semanticengine.backend_transformer_desc' },
}

type SemProfile = PerfilSemantico
type SemConfig = ConfigDelMotorSemantico
type SemStats = EstadisticasDelMotorSemantico

/** Fila de la tabla de perfiles: cada usuario, tenga perfil o no. */
type ProfileRow = Partial<SemProfile> & { user_id: string; user_name: string; has_profile: boolean }

/** La sugerencia pedida, o el error al pedirla. */
type TestResult = Partial<SugerenciaDeAsignacionDeTicket> & { error?: string }

/** FastAPI devuelve `detail` como texto o, en un 422, como lista de errores. */
type ErrorDeValidacion = AxiosError<{ detail?: string | Array<{ msg?: string }> }>

function ProfileModal({ user, onClose }: { user: ProfileRow; onClose: () => void }) {
  const idCampo = useId()
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
    <Modal open onClose={onClose} title={traducir('semanticengine.perfil_titulo', { name: user?.user_name || traducir('semanticengine.usuario') })} width={600}>
      <p className="sem-intro">
        {traducir('semanticengine.describe_las_capacidades_rol_tecnologias_y_area')}
      </p>
      <div className="u-mb-14">
        <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className={ls}>{traducir('semanticengine.texto_del_perfil')}</label>
        <textarea id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={text} onChange={e => setText(e.target.value)} rows={6}
          className={`${fs} sem-textarea sem-textarea--lh`}
          placeholder={traducir('semanticengine.describe_las_capacidades_rol_tecnologias_y_area_2')} />
      </div>
      <div className="u-mb-20">
        <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className={ls}>{traducir('semanticengine.carga_maxima_simultanea_tickets_tareas')}</label>
        <input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} type="number" value={maxLoad} onChange={e => setMaxLoad(parseInt(e.target.value))}
          className={`${fs} sem-input--narrow`} min={1} max={50} />
      </div>
      <div className="u-actions-10">
        <Button variant="secondary" onClick={onClose}>{traducir('common.cancel')}</Button>
        <Button onClick={() => mutate({ user_id: user.user_id, profile_text: text, max_load: maxLoad })}
          disabled={isPending || !text.trim()} loading={isPending}>
          {isPending ? traducir('semanticengine.guardando') : traducir('semanticengine.guardar_perfil')}
        </Button>
      </div>
    </Modal>
  )
}

function TestPanel() {
  const idCampo = useId()
  const traducir = useAppT()
  const [type, setType] = useState('ticket')
  const [title, setTitle] = useState('')
  const [desc, setDesc] = useState('')
  const [result, setResult] = useState<TestResult | null>(null)
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
      const raw = (e as ErrorDeValidacion)?.response?.data?.detail
      setResult({ error: Array.isArray(raw) ? raw.map(d => d.msg).join(', ') : (raw || traducir('semanticengine.error')) })
    } finally { setTesting(false) }
  }

  const conf = result?.confidence ?? 0

  return (
    <div className="sem-card sem-card--pad">
      <div className="sem-h sem-h--600">{traducir('semanticengine.probar_asignacion')}</div>
      <Tabs
        className="sem-tipo"
        ariaLabel={traducir('semanticengine.tipo')}
        items={[
          { id: 'ticket', label: traducir('semanticengine.ticket'), icon: <Ticket size={14} /> },
          { id: 'task', label: traducir('semanticengine.tarea'), icon: <CheckSquare size={14} /> },
        ]}
        active={type}
        onChange={setType}
      />
      <div className="sem-fields">
        <div>
          <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className={ls}>{traducir('semanticengine.titulo')}</label>
          <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={title} onChange={e => setTitle(e.target.value)} className={fs}
            placeholder={type === 'ticket' ? traducir('semanticengine.ejemplo_ticket') : traducir('semanticengine.ejemplo_tarea')} />
        </div>
        <div>
          <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className={ls}>{traducir('semanticengine.descripcion_opcional')}</label>
          <textarea id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={desc} onChange={e => setDesc(e.target.value)} rows={3}
            className={`${fs} sem-textarea`} placeholder={traducir('semanticengine.descripcion_opcional_del_ticket_o_tarea')} />
        </div>
      </div>
      <Button icon={<Wand2 size={14} />} onClick={runTest} disabled={!title.trim()} loading={testing}>
        {testing ? traducir('semanticengine.analizando') : traducir('semanticengine.sugerir_asignacion')}
      </Button>

      {result && (
        <div className="sem-result" aria-live="polite">
          {result.error ? (
            <div className="u-danger sem-con-icono" role="alert"><XCircle size={15} aria-hidden /> {result.error}</div>
          ) : (
            <>
              <div className="sem-result__head">
                <div>
                  <div className="sem-muted-sm">{traducir('semanticengine.asignacion_sugerida')}</div>
                  <div className={`sem-who${result.needs_review ? ' sem-who--review' : ''}`}>
                    {result.suggested_user_name || result.suggested_user_id || traducir('semanticengine.sin_candidato')}
                  </div>
                </div>
                <div className="sem-right">
                  <div className="sem-muted-sm">{traducir('semanticengine.confianza')}</div>
                  <div className="sem-conf" style={cVar(conf > 0.7 ? 'var(--success)' : conf > 0.5 ? 'var(--warning)' : 'var(--danger)')}>
                    {Math.round(conf * 100)}%
                  </div>
                </div>
              </div>
              <div className="sem-muted-sm sem-muted-sm--mb10">
                <span className="sem-mr12">{traducir('semanticengine.motor')} <strong className="u-text1">{result.engine_mode && ENGINE_MODES[result.engine_mode] ? traducir(ENGINE_MODES[result.engine_mode].label) : result.engine_mode}</strong></span>
                {result.needs_review && <span className="u-warning sem-con-icono"><AlertTriangle size={13} aria-hidden /> {traducir('semanticengine.revisar_manualmente')}</span>}
              </div>
              {result.reasoning && (
                <div className="sem-reasoning">
                  {result.reasoning}
                </div>
              )}
              {result.top_candidates && Object.keys(result.top_candidates).length > 0 && (
                <div>
                  <div className="sem-eyebrow">{traducir('semanticengine.top_candidatos')}</div>
                  {Object.entries(result.top_candidates).map(([uid, info]) => (
                    <div key={uid} className="sem-cand">
                      <span>{info.name}</span>
                      <span className="sem-cand__score">{Math.round(info.score * 100)}%</span>
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
  const idCampo = useId()
  const traducir = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [tab, setTab] = useState('overview')
  const [editProfile, setEditProfile] = useState<ProfileRow | null>(null)
  const [opStatus, setOpStatus] = useState<{ type: string; startedAt: number | null }>({ type: 'idle', startedAt: null })
  const [opElapsed, setOpElapsed] = useState(0)
  const [hfModelDraft, setHfModelDraft] = useState('')
  // Configurar el motor (perfiles, modo, embeddings) es de admin y hr en el
  // servidor; pm entra a probar sugerencias (revisión 2026-11: veía los botones y le daban 403).
  const puedeEditar = useAuth().hasRole('admin', 'hr')

  useEffect(() => {
    if (!opStatus.startedAt) {
      setOpElapsed(0)
      return
    }
    const startedAt = opStatus.startedAt
    const id = setInterval(() => {
      setOpElapsed(Math.floor((Date.now() - startedAt) / 1000))
    }, CLOCK_TICK_MS)
    return () => clearInterval(id)
  }, [opStatus.startedAt])

  const { data: config = {} } = useQuery<Partial<SemConfig>>({
    queryKey: ['sem-config'],
    queryFn: () => semanticApi.config().then(r => r.data),
  })

  useEffect(() => {
    setHfModelDraft(config.local_model_name && config.local_model_name !== 'tfidf' ? config.local_model_name : 'all-MiniLM-L6-v2')
  }, [config.local_model_name])
  const { data: profiles = [] } = useQuery<SemProfile[]>({
    queryKey: ['sem-profiles'],
    queryFn: () => semanticApi.profiles().then(r => r.data),
    enabled: tab === 'profiles' || tab === 'overview',
  })
  const { data: stats = {} } = useQuery<Partial<SemStats>>({
    queryKey: ['sem-stats'],
    queryFn: () => semanticApi.stats().then(r => r.data),
  })
  const { data: users = [] } = useQuery({
    queryKey: ['users'],
    queryFn: () => usersApi.list().then(r => r.data),
    enabled: tab === 'profiles',
  })

  const { mutate: saveConfig, isPending: savingConfig } = useMutation({
    mutationFn: (d: Record<string, unknown>) => semanticApi.updateConfig(d).then(r => r.data),
    onMutate: async (patch) => {
      await qc.cancelQueries({ queryKey: ['sem-config'] })
      const previous = qc.getQueryData(['sem-config'])
      qc.setQueryData(['sem-config'], (current: Partial<SemConfig> | undefined) => ({ ...(current || {}), ...patch }))
      return { previous }
    },
    onSuccess: data => {
      if (data?.config) qc.setQueryData(['sem-config'], data.config)
      toast.success(traducir('semanticengine.config_actualizada'))
    },
    onError: (e, _patch, ctx) => {
      if (ctx?.previous) qc.setQueryData(['sem-config'], ctx.previous)
      toast.error(extractErr(e, traducir('semanticengine.error_actualizar')))
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ['sem-config'] }),
  })
  const { mutate: autoGenerate, isPending: generating } = useMutation({
    mutationFn: () => semanticApi.autoGenerate(),
    onMutate: () => setOpStatus({ type: 'generating', startedAt: Date.now() }),
    onSuccess: d => {
      qc.invalidateQueries({ queryKey: ['sem-profiles'] })
      toast.success(traducir('semanticengine.toast_generados', { created: d.data.created, updated: d.data.updated }))
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
      toast.success(traducir('semanticengine.toast_reconstruidos', { n: d.data.rebuilt }))
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

  const modoLabel = (mode: string) => ENGINE_MODES[mode] ? traducir(ENGINE_MODES[mode].label) : mode
  const backendLabel = (b: string) => EMBEDDINGS_BACKENDS[b] ? traducir(EMBEDDINGS_BACKENDS[b].label) : b
  const backendActual = config.embeddings_backend || 'tfidf'

  return (
    <PageShell>
      <PageHeader
        icon={<Brain size={18} />}
        title={traducir('semantic_engine.title')}
        subtitle={traducir('semantic_engine.subtitle')}
        actions={
          <div className="sem-actions">
            {(generating || rebuilding || opStatus.type === 'failed' || opStatus.type === 'done') && (
              <div className={`sem-op${generating || rebuilding ? ' sem-op--busy' : opStatus.type === 'failed' ? ' sem-op--failed' : ''}`} role="status">
                {generating ? traducir('semanticengine.generando_perfiles_s', { s: opElapsed })
                  : rebuilding ? traducir('semanticengine.reconstruyendo_s', { s: opElapsed })
                  : opStatus.type === 'failed' ? traducir('semanticengine.ultima_fallo') : traducir('semanticengine.ultima_ok')}
              </div>
            )}
            {puedeEditar && <>
            <Button variant="secondary" icon={<RefreshCw size={14} />} onClick={() => rebuildEmb()} loading={rebuilding}>
              {rebuilding ? traducir('semanticengine.reconstruyendo') : traducir('semanticengine.reconstruir_embeddings')}
            </Button>
            <Button icon={<Sparkles size={14} />} onClick={() => autoGenerate()} loading={generating}>
              {generating ? traducir('semanticengine.generando') : traducir('semanticengine.auto_generar_perfiles')}
            </Button>
            </>}
          </div>
        }
      showListExport={false}
      />

      {/* KPIs */}
      <div className="ds-grid-stats sem-kpis">
        <KpiCard icon={<Target size={16} />} label={traducir('semanticengine.kpi_sugerencias')} value={stats.total_suggestions || 0} />
        <KpiCard icon={<CheckCircle2 size={16} />} label={traducir('semanticengine.kpi_aceptadas')} value={stats.accepted || 0} />
        <KpiCard icon={<XCircle size={16} />} label={traducir('semanticengine.kpi_rechazadas')} value={stats.rejected || 0} danger={(stats.rejected || 0) > 0} />
        <KpiCard icon={<BarChart3 size={16} />} label={traducir('semanticengine.kpi_precision')} value={stats.accuracy_pct != null ? `${stats.accuracy_pct}%` : '—'} />
        <KpiCard icon={<Brain size={16} />} label={traducir('semanticengine.kpi_perfiles')} value={stats.profiles || 0} />
      </div>

      <Tabs
        className="sem-tabs"
        ariaLabel={traducir('semantic_engine.title')}
        items={[
          { id: 'overview', label: traducir('semanticengine.tab_config'), icon: <Settings size={14} /> },
          { id: 'profiles', label: traducir('semanticengine.tab_perfiles'), icon: <Users size={14} /> },
          { id: 'test', label: traducir('semanticengine.tab_probar'), icon: <FlaskConical size={14} /> },
          { id: 'stats', label: traducir('semanticengine.tab_estadisticas'), icon: <BarChart3 size={14} /> },
        ]}
        active={tab}
        onChange={setTab}
      />

      {/* CONFIG TAB */}
      {tab === 'overview' && (
        <div className="sem-grid2">
          <div className="sem-card sem-card--pad">
            <div className="sem-h sem-h--600">{traducir('semanticengine.modo_del_motor')}</div>
            <div className="u-stack-10">
              {Object.entries(ENGINE_MODES).map(([key, meta]) => (
                <button key={key} type="button" onClick={() => saveConfig({ engine_mode: key })} disabled={savingConfig || !puedeEditar}
                  aria-pressed={config.engine_mode === key}
                  className={`sem-mode${savingConfig ? ' sem-mode--saving' : ''}`}>
                  <div className="u-row-center-10">
                    <span className="sem-mode__icon" aria-hidden="true">{meta.icon}</span>
                    <div>
                      <div className="sem-mode__label">{traducir(meta.label)}</div>
                      <div className="u-text2-xs-mt2">{traducir(meta.desc)}</div>
                    </div>
                    {config.engine_mode === key && <span className="sem-mode__check" aria-hidden="true">{savingConfig ? <Loader2 size={16} className="sem-girar" /> : <Check size={16} />}</span>}
                  </div>
                </button>
              ))}
            </div>
          </div>

          <div className="u-stack-16">
            <div className="sem-card sem-card--pad">
              <div className="sem-h">{traducir('semanticengine.embeddings_y_modelo')}</div>

              <div className="u-mb-14">
                <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className={ls}>{traducir('semanticengine.backend_de_embeddings')}</label>
                <select id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`}
                  value={backendActual}
                  onChange={e => {
                    const backend = e.target.value
                    if (backend === 'transformer') {
                      const modelName = (hfModelDraft || config.local_model_name || 'all-MiniLM-L6-v2').trim()
                      saveConfig({ embeddings_backend: 'transformer', local_model_name: modelName || 'all-MiniLM-L6-v2' })
                      return
                    }
                    saveConfig({ embeddings_backend: 'tfidf', local_model_name: 'tfidf' })
                  }}
                  className={fs}
                  disabled={savingConfig}
                >
                  {Object.entries(EMBEDDINGS_BACKENDS).map(([key, meta]) => (
                    <option key={key} value={key}>{traducir(meta.label)}</option>
                  ))}
                </select>
                <div className="sem-hint">
                  {EMBEDDINGS_BACKENDS[backendActual] ? traducir(EMBEDDINGS_BACKENDS[backendActual].desc) : ''}
                </div>
                {config.backend_en_uso && config.backend_en_uso !== backendActual && (
                  // Revisión 2026-11: el configurado no siempre es el que se usa.
                  <div className="sem-hint sem-hint--warning">
                    {traducir('semanticengine.backend_en_uso_distinto')} {backendLabel(config.backend_en_uso)}
                  </div>
                )}
              </div>

              <div className="u-mb-10">
                <label id={`${idCampo}-eta463`} htmlFor={`${idCampo}-a463`} className={ls}>{traducir('semanticengine.modelo_hf')}</label>
                <div className="u-row-8">
                  <input id={`${idCampo}-a463`} aria-labelledby={`${idCampo}-eta463`}
                    value={hfModelDraft}
                    onChange={e => setHfModelDraft(e.target.value)}
                    placeholder={traducir('semanticengine.modelo_hf_placeholder')}
                    className={`${fs} sem-input--min0`}
                    disabled={backendActual !== 'transformer' || savingConfig}
                  />
                  <Button
                    variant="secondary"
                    disabled={!puedeEditar || backendActual !== 'transformer' || savingConfig || !hfModelDraft.trim()}
                    onClick={() => saveConfig({ embeddings_backend: 'transformer', local_model_name: hfModelDraft.trim() })}
                  >
                    {traducir('common.save')}
                  </Button>
                </div>
              </div>

              <div className="sem-box">
                <div>{traducir('semanticengine.backend_activo')} <strong className="u-text1">{backendLabel(backendActual)}</strong></div>
                <div>{traducir('semanticengine.modelo_efectivo')} <strong className="u-text1">{config.effective_model_name || (config.local_model_name || 'all-MiniLM-L6-v2')}</strong></div>
              </div>
            </div>

            <div className="sem-card sem-card--pad">
              <div className="sem-h">{traducir('semanticengine.umbrales_de_confianza')}</div>
              {[
                { key: 'threshold_ticket', label: traducir('semanticengine.umbral_tickets'), val: config.threshold_ticket },
                { key: 'threshold_task',   label: traducir('semanticengine.umbral_tareas'),  val: config.threshold_task },
                { key: 'threshold_expert_cache', label: traducir('semanticengine.umbral_cache'), val: config.threshold_expert_cache },
                { key: 'load_balance_weight', label: traducir('semanticengine.peso_balanceo'), val: config.load_balance_weight },
              ].map(f => (
                <div key={f.key} className="u-mb-12">
                  <div className="sem-range-head">
                    <label htmlFor={`${idCampo}-${f.key}`} className={`${ls} sem-label--flush`}>{f.label}</label>
                    <span className="sem-range-val">{f.val}</span>
                  </div>
                  <input id={`${idCampo}-${f.key}`} aria-label={f.label} type="range" min={f.key === 'load_balance_weight' ? '0.0' : '0.3'} max="0.99" step="0.01"
                    value={f.val || 0.6}
                    onChange={e => saveConfig({ [f.key]: parseFloat(e.target.value) })}
                    className="sem-range" />
                </div>
              ))}
            </div>

            <div className="sem-card sem-card--pad">
              <div className="sem-h">{traducir('semanticengine.auto_asignacion')}</div>
              {[
                { key: 'auto_assign_tickets', label: traducir('semanticengine.auto_tickets'), val: config.auto_assign_tickets },
                { key: 'auto_assign_tasks',   label: traducir('semanticengine.auto_tareas'),  val: config.auto_assign_tasks },
              ].map(f => (
                <div key={f.key} className="sem-toggle-row">
                  <span className="sem-base">{f.label}</span>
                  <button type="button" aria-label={f.label} aria-pressed={!!f.val} onClick={() => saveConfig({ [f.key]: !f.val })} disabled={!puedeEditar} className="sem-switch">
                    <span className="sem-switch__knob" />
                  </button>
                </div>
              ))}
              <div className="sem-box sem-box--warning sem-con-icono">
                <AlertTriangle size={14} aria-hidden />
                <span>{traducir('semanticengine.con_auto_asignacion_activada_los_items_se')}</span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* PROFILES TAB */}
      {tab === 'profiles' && (
        <div>
          <div className="sem-card sem-card--clip">
            <div className="u-scroll-x">
            <div className="sem-table" role="table" aria-label={traducir('semanticengine.tab_perfiles')}>
            <div className="sem-row sem-row--head" role="row">
              <span role="columnheader">{traducir('semanticengine.col_usuario')}</span><span role="columnheader">{traducir('semanticengine.col_perfil')}</span><span role="columnheader">{traducir('semanticengine.col_tickets')}</span><span role="columnheader">{traducir('semanticengine.col_tareas')}</span><span role="columnheader">{traducir('semanticengine.col_estado')}</span><span role="columnheader">{traducir('semanticengine.accion')}</span>
            </div>
            {profilesWithUsers.length === 0 ? (
              <div className="sem-empty">
                <EmptyState icon={<Users size={28} />} title={traducir('semanticengine.sin_perfiles_semanticos')} description={traducir('semanticengine.sin_perfiles_desc')} />
              </div>
            ) : profilesWithUsers.map(u => (
              <div key={u.user_id} className="sem-row" role="row">
                <div className="u-min0" role="cell">
                  <div className="u-600">{u.user_name}</div>
                  {u.profile_text && <div className="sem-ellipsis" title={u.profile_text}>{u.profile_text}</div>}
                </div>
                <div className="u-row-center-6" role="cell">
                  <span className={`sem-dot${u.has_embedding ? ' sem-dot--success' : u.has_profile ? ' sem-dot--warning' : ''}`} aria-hidden="true" />
                  <span className="u-text2-xs">
                    {u.has_embedding ? traducir('semanticengine.embedding_ok') : u.has_profile ? traducir('semanticengine.sin_embedding') : traducir('semanticengine.sin_perfil')}
                  </span>
                </div>
                <span className="sem-count" role="cell">{u.open_tickets || 0}</span>
                <span className="sem-count sem-count--warning" role="cell">{u.open_tasks || 0}</span>
                <span role="cell"><span className={`sem-avail${u.is_available !== false ? '' : ' sem-avail--no'}`}>
                  {u.is_available !== false ? traducir('semanticengine.disponible') : traducir('semanticengine.no_disponible')}
                </span></span>
                <span role="cell">{puedeEditar && <Button variant="secondary" size="sm" icon={<Pencil size={13} />} onClick={() => setEditProfile(u)}>
                  {traducir('semanticengine.editar')}
                </Button>}</span>
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
        <div className="u-stack-16">

          {/* Top row: acceptance gauge + pipeline bar */}
          <div className="sem-grid12">
            {/* Acceptance gauge */}
            <div className="sem-card sem-card--pad sem-card--center">
              <div className="sem-h sem-h--base sem-h--start">{traducir('semanticengine.tasa_de_aceptacion')}</div>
              {(() => {
                const acc = stats.accepted || 0
                const rej = stats.rejected || 0
                const tot = acc + rej
                const pct = tot > 0 ? Math.round(acc / tot * 100) : null
                const r = 44, circ = 2 * Math.PI * r
                const offset = pct != null ? circ * (1 - pct / 100) : circ
                return (
                  <div className="sem-gauge" role="img" aria-label={`${traducir('semanticengine.tasa_de_aceptacion')}: ${pct != null ? `${pct}%` : '—'}`}>
                    <svg width={116} height={116} viewBox="0 0 116 116" aria-hidden="true">
                      <circle cx={58} cy={58} r={r} fill="none" stroke="var(--surface-4)" strokeWidth={10} />
                      <circle cx={58} cy={58} r={r} fill="none"
                        stroke={pct == null ? 'var(--surface-4)' : pct >= 70 ? 'var(--success)' : pct >= 40 ? 'var(--warning)' : 'var(--danger)'}
                        strokeWidth={10} strokeLinecap="round"
                        strokeDasharray={circ} strokeDashoffset={offset}
                        transform="rotate(-90 58 58)" className="sem-gauge__arc" />
                    </svg>
                    <div className="sem-gauge__center">
                      <div className="sem-gauge__pct">
                        {pct != null ? `${pct}%` : '—'}
                      </div>
                      <div className="u-text3-2xs">{traducir('semanticengine.n_evaluadas', { n: tot })}</div>
                    </div>
                  </div>
                )
              })()}
              <div className="sem-gauge__legend">
                {([['acc', stats.accepted || 0, 'var(--success)', traducir('semanticengine.kpi_aceptadas')],
                  ['rej', stats.rejected || 0, 'var(--danger)', traducir('semanticengine.kpi_rechazadas')],
                  ['pen', stats.pending || 0, 'var(--text-3)', traducir('semanticengine.pendientes')]] as const).map(([k, v, c, l]) => (
                  <div key={k} className="sem-center">
                    <div className="sem-legend-val" style={cVar(c)}>{v}</div>
                    <div className="u-text3">{l}</div>
                  </div>
                ))}
              </div>
            </div>

            {/* Stacked breakdown */}
            <div className="sem-card sem-card--pad">
              <div className="sem-h sem-h--base">{traducir('semanticengine.distribucion_de_sugerencias')}</div>
              {(() => {
                const tot = (stats.accepted||0) + (stats.rejected||0) + (stats.pending||0)
                if (tot === 0) return <div className="u-text2-base">{traducir('semanticengine.sin_datos_todavia_procesa_algunas_tareas_o')}</div>
                const bars = [
                  { key: 'acc', label: traducir('semanticengine.kpi_aceptadas'), val: stats.accepted||0, color: 'var(--success)' },
                  { key: 'rej', label: traducir('semanticengine.kpi_rechazadas'), val: stats.rejected||0, color: 'var(--danger)' },
                  { key: 'pen', label: traducir('semanticengine.sin_evaluar'), val: stats.pending||0, color: 'var(--surface-5)' },
                ]
                return (
                  <div className="u-stack-12">
                    {/* Single stacked bar */}
                    <div className="sem-stack" aria-hidden="true">
                      {bars.map(b => b.val > 0 && (
                        <div key={b.key} className="sem-stack__seg" style={{ '--sem-c': b.color, '--sem-f': b.val / tot } as CSSProperties} title={`${b.label}: ${b.val}`} />
                      ))}
                    </div>
                    {/* Legend rows */}
                    {bars.map(b => {
                      const pct = tot > 0 ? b.val / tot * 100 : 0
                      return (
                        <div key={b.key} className="u-row-center-10" style={{ '--sem-c': b.color, '--sem-pct': `${pct}%` } as CSSProperties}>
                          <div className="sem-swatch" />
                          <div className="u-flex1">
                            <div className="sem-bar-head">
                              <span className="u-text2-sm">{b.label}</span>
                              <span className="sem-bar-val">{b.val} ({Math.round(pct)}%)</span>
                            </div>
                            <div className="sem-bar">
                              <div className="sem-bar__fill" />
                            </div>
                          </div>
                        </div>
                      )
                    })}
                    {/* By mode */}
                    {Object.keys(stats.by_mode || {}).length > 0 && (
                      <div className="sem-by-mode">
                        <div className="sem-by-mode__title">{traducir('semanticengine.pipeline_de_resolucion')}</div>
                        <div className="u-wrap-8">
                          {Object.entries(stats.by_mode || {}).map(([mode, count]) => (
                            <div key={mode} className="sem-chip sem-con-icono">
                              {ENGINE_MODES[mode]?.icon} {modoLabel(mode)}: <strong>{count}</strong>
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
          <div className="sem-card sem-card--pad">
            <div className="sem-h sem-h--base">{traducir('semanticengine.estado_del_sistema')}</div>
            <div className="sem-sys">
              {[
                { key: 'cache', label: traducir('semanticengine.expert_cache'), value: stats.cache_size || 0, icon: <Zap size={20} />, hint: traducir('semanticengine.expert_cache_hint'), color: 'var(--accent)' },
                { key: 'fb', label: traducir('semanticengine.feedback_experto'), value: stats.expert_feedback || 0, icon: <UserCheck size={20} />, hint: traducir('semanticengine.feedback_hint'), color: 'var(--success)' },
                { key: 'vec', label: traducir('semanticengine.perfiles_con_vector'), value: profiles.filter(p => p.has_embedding).length, icon: <Layers size={20} />, hint: traducir('semanticengine.de_n_perfiles', { n: profiles.length }), color: 'var(--purple)' },
              ].map(s => (
                <div key={s.key} className="sem-sys__item">
                  <span className="sem-sys__icon" aria-hidden="true">{s.icon}</span>
                  <div>
                    <div className="sem-sys__value" style={cVar(s.color)}>{s.value}</div>
                    <div className="sem-sys__label">{s.label}</div>
                    <div className="u-text3-2xs">{s.hint}</div>
                  </div>
                </div>
              ))}
            </div>
            <div className="sem-box sem-box--info sem-con-icono">
              <Info size={14} aria-hidden />
              <span>{traducir('semanticengine.para_mejorar_la_precision_genera_perfiles_automaticos')}</span>
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
