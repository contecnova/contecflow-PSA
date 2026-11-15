import React, { useState, useRef, useCallback } from 'react'
import { extractErr } from '../utils/helpers'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { aiProvidersApi, nexusAgentApi, apiStream } from '../services/api'
import type { EjecucionDelAgente, EjecucionDelAgenteResumen, PasoDelAgente } from '../services/api/tipos-analitica'
import { Button, Spinner, EmptyState } from '../components/ui'
import MarkdownText from '../components/ui/MarkdownText'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Bot } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import { alpha } from '../constants/theme'
import useMediaQuery from '../hooks/useMediaQuery'
import { POLL_JOB_STATUS_MS } from '../constants/timings'
import './NexusAgentPage.css'

const card = { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12 }
const STATUS_CFG: Record<string, { color: string; bg: string }> = {
  done:    { color: 'var(--success)', bg: 'var(--success-bg)' },
  failed:  { color: 'var(--danger)', bg: 'var(--danger-bg)' },
  running: { color: 'var(--warning)', bg: 'var(--warning-bg)' },
  pending: { color: 'var(--text-2)', bg: 'color-mix(in srgb, var(--text-2) 9%, transparent)' },
}
// Tools alineados con los nombres reales del backend (AGENT_TOOLS en
// app/services/ai_chat/tool_execution_service.py). Antes los 10 mostrados
// aquí no coincidían con los 37 reales del backend → user confundido.
const TOOLS = [
  { icon: '📁', name: 'search_projects',         desc: 'nexusagent.herramienta_search_projects' },
  { icon: '📊', name: 'get_project_status',      desc: 'nexusagent.herramienta_get_project_status' },
  { icon: '🎯', name: 'get_dashboard_summary',   desc: 'nexusagent.herramienta_get_dashboard_summary' },
  { icon: '💰', name: 'get_budget_status',       desc: 'nexusagent.herramienta_get_budget_status' },
  { icon: '⚠️', name: 'get_project_risks',        desc: 'nexusagent.herramienta_get_project_risks' },
  { icon: '⏰', name: 'get_overdue_tasks',        desc: 'nexusagent.herramienta_get_overdue_tasks' },
  { icon: '🎫', name: 'get_open_tickets',        desc: 'nexusagent.herramienta_get_open_tickets' },
  { icon: '👥', name: 'get_users_list',          desc: 'nexusagent.herramienta_get_users_list' },
  { icon: '📅', name: 'get_imputations',         desc: 'nexusagent.herramienta_get_imputations' },
  { icon: '📈', name: 'get_profitability',       desc: 'nexusagent.herramienta_get_profitability' },
  { icon: '➕', name: 'create_task',              desc: 'nexusagent.herramienta_create_task' },
  { icon: '✏️', name: 'update_task',              desc: 'nexusagent.herramienta_update_task' },
  { icon: '🚨', name: 'create_risk',             desc: 'nexusagent.herramienta_create_risk' },
  { icon: '🔁', name: 'reassign_tickets',        desc: 'nexusagent.herramienta_reassign_tickets' },
  { icon: '🔍', name: 'search_all',              desc: 'nexusagent.herramienta_search_all' },
]
const EXAMPLES = [
  { icon: '📊', text: 'nexusagent.ejemplo_1' },
  { icon: '⚠️', text: 'nexusagent.ejemplo_2' },
  { icon: '➕', text: 'nexusagent.ejemplo_3' },
  { icon: '👥', text: 'nexusagent.ejemplo_4' },
  { icon: '🎫', text: 'nexusagent.ejemplo_5' },
  { icon: '📈', text: 'nexusagent.ejemplo_6' },
]


/** Un paso que el agente ejecuto: el del detalle (`/ai/agent/{id}`) o el del flujo SSE. */
type PasoDeAgente = Partial<PasoDelAgente>

/** Lo que se pinta como resultado: la ejecución en cola, su detalle o el final del flujo. */
type ResultadoDeAgente = Omit<Partial<EjecucionDelAgente>, 'steps'> & { steps?: PasoDeAgente[] }

/** Un evento del flujo SSE del agente. Los cuatro tipos llevan campos
 *  distintos, y por eso la union esta discriminada por `type`: sin eso el
 *  codigo tendria que confiar en que el campo que lee existe en el evento que
 *  llego. */
type EventoDeAgente =
  | { type: 'token'; text: string }
  | { type: 'step'; step?: number; tool?: string; output?: string }
  | { type: 'done'; result?: string; steps?: PasoDeAgente[] }
  | { type: 'error'; message?: string }

function StepBadge({ step }: { step: PasoDeAgente }) {
  const colors: Record<string, string> = { list_projects:'var(--accent)', list_tasks:'var(--success)', create_task:'var(--warning)',
                   update_task:'var(--warning)', list_tickets:'var(--purple)', get_project_stats:'var(--accent)' }
  const c = (step.tool && colors[step.tool]) || 'var(--text-2)'
  return (
    <div className="nexus-row">
      <div className="nexus-row-2" style={{ borderRadius: 'var(--radius-sm)', background: alpha(c, '20'), border: `1px solid ${alpha(c, '40')}`, color: c }}>
        {step.step}
      </div>
      <div className="u-flex1-min0">
        <div className="nexus-box" style={{ color: c }}>{step.tool}</div>
        {step.output != null && step.output !== '' && (
          <div className="nexus-box-2">
            {typeof step.output === 'string' ? step.output.slice(0, 120) : JSON.stringify(step.output).slice(0, 120)}
          </div>
        )}
      </div>
    </div>
  )
}

/** Quita la marca de markdown para la vista previa de una línea. */
const sinMarkdown = (texto = '') => texto.replace(/[*_`#>]+/g, '').replace(/\s+/g, ' ').trim()

const ICONO_DE_ESTADO: Record<string, string> = { done: '✓', failed: '✕', running: '…', pending: '○' }

/** Una ejecución del historial (rediseño 2026-11: era un <button> con el
 *  estilo del navegador, centrado y con borde en relieve). */
function FilaDeHistorial({ ejecucion: e, seleccionada, onAbrir }: { ejecucion: EjecucionDelAgenteResumen; seleccionada: boolean; onAbrir: () => void }) {
  const t = useAppT()
  const [encima, setEncima] = useState(false)
  const estado = e.status && STATUS_CFG[e.status] ? e.status : 'pending'
  const sc = STATUS_CFG[estado]
  const pasos = e.steps_count ?? 0
  const fecha = e.created_at ? new Date(e.created_at) : null
  return (
    <button type="button" role="listitem" onClick={onAbrir} aria-current={seleccionada || undefined}
      onMouseEnter={() => setEncima(true)} onMouseLeave={() => setEncima(false)}
      className="nexus-btn" style={{ borderRadius: 'var(--radius-md)', border: `1px solid ${seleccionada ? alpha(sc.color, '55') : 'transparent'}`, background: seleccionada ? alpha(sc.color, '12') : encima ? 'var(--surface-3)' : 'transparent' }}>
      <span aria-hidden className="nexus-row-3" style={{ borderRadius: 9, background: sc.bg, color: sc.color, border: `1px solid ${alpha(sc.color, '40')}` }}>
        {ICONO_DE_ESTADO[estado]}
      </span>
      <span className="nexus-stack">
        <span className="nexus-label">
          {e.instruction}
        </span>
        {e.result && (
          <span className="nexus-label-2">
            {sinMarkdown(e.result)}
          </span>
        )}
        <span className="nexus-row-4">
          <span className="u-600" style={{ color: sc.color }}>{t(`nexusagent.estado_${estado}`)}</span>
          {fecha && !isNaN(fecha.getTime()) && <><span aria-hidden>·</span><time dateTime={e.created_at}>{fecha.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}</time></>}
          {pasos > 0 && <><span aria-hidden>·</span><span>{t('nexusagent.n_pasos', { n: pasos })}</span></>}
        </span>
      </span>
      <span aria-hidden className="nexus-label-3" style={{ color: seleccionada || encima ? 'var(--accent)' : 'var(--text-3)' }}>›</span>
    </button>
  )
}

export default function ContecflowAgentPage() {
  const traducir = useAppT()
  const t = useAppT()
  const isNarrow = useMediaQuery('(max-width: 900px)')
  const _qc = useQueryClient()
  const toast = useToast()
  const [instruction, setInstruction] = useState('')
  const [result, setResult] = useState<ResultadoDeAgente | null>(null)
  const [_selectedExec, _setSelectedExec] = useState<ResultadoDeAgente | null>(null)
  const [showTools, setShowTools] = useState(false)
  // Auditoría 2026-11: las dos vías mandaban `auto_approve: true` siempre, así
  // que el agente escribía (crear, cambiar, borrar) sin que nadie lo pidiera.
  const [permitirEscritura, setPermitirEscritura] = useState(false)
  const [streaming, setStreaming] = useState(true)
  const [liveSteps, setLiveSteps] = useState<PasoDeAgente[]>([])
  const [liveText, setLiveText] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  const { data: providers = [] } = useQuery({
    queryKey: ['ai-providers'],
    queryFn: () => aiProvidersApi.list().then(r => r.data),
  })
  const defaultProvider = providers.find(p => p.is_default) || providers[0]

  const { data: history = [], refetch } = useQuery({
    queryKey: ['agent-history'],
    queryFn: () => nexusAgentApi.history().then(r => r.data),
  })

  // Revisión 2026-11: sin streaming la ejecución se encola y vuelve «queued»;
  // antes se pintaba eso como resultado y no se volvía a preguntar. Ahora se
  // sondea su estado hasta que termina y se abre la ejecución completa.
  const [enCola, setEnCola] = useState<string | null>(null)
  useQuery({
    queryKey: ['agent-status', enCola],
    enabled: !!enCola,
    refetchInterval: POLL_JOB_STATUS_MS,
    queryFn: async () => {
      const estado = (await nexusAgentApi.status(enCola as string)).data
      if (estado?.status === 'done' || estado?.status === 'failed') {
        setResult((await nexusAgentApi.detail(enCola as string)).data)
        setEnCola(null)
        refetch()
      }
      return estado
    },
  })
  const { mutate: run, isPending } = useMutation({
    mutationFn: (inst: string) => nexusAgentApi.run(inst, permitirEscritura).then(r => r.data),
    onSuccess: data => { setResult(data); if (data?.execution_id) setEnCola(String(data.execution_id)); refetch() },
    onError: e => toast.error(extractErr(e, traducir('nexusagent.error_ejecutar'))),
  })

  // El historial trae un resumen (instrucción recortada, sin pasos): se pinta
  // al momento y se sustituye por la ejecución completa en cuanto llega.
  const abrirEjecucion = (e: EjecucionDelAgenteResumen) => {
    setResult({ ...e, steps: [] })
    nexusAgentApi.detail(e.execution_id)
      .then(r => setResult(r.data))
      .catch(err => toast.error(extractErr(err, traducir('nexusagent.error_ejecutar'))))
  }

  const runStream = useCallback(async (inst: string) => {
    if (isStreaming) return
    setIsStreaming(true)
    setLiveSteps([])
    setLiveText('')
    setResult(null)

    const ctrl = new AbortController()
    abortRef.current = ctrl

    try {
      // apiStream: el cliente API en versión flujo (CSRF, cookies, refresco de sesión).
      const resp = await apiStream('/ai/agent/stream', {
        body: { instruction: inst, auto_approve: permitirEscritura },
        signal: ctrl.signal,
      })
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: t('pagina_nexus.error') }))
        toast.error(err.detail || traducir('nexusagent.error_streaming'))
        setIsStreaming(false)
        return
      }

      if (!resp.body) {
        toast.error(traducir('nexusagent.error_sin_flujo'))
        setIsStreaming(false)
        return
      }
      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      let buf = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const lines = buf.split('\n')
        buf = lines.pop() ?? ''
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const evt = JSON.parse(line.slice(6)) as EventoDeAgente
            if (evt.type === 'token') {
              setLiveText(prev => prev + evt.text)
            } else if (evt.type === 'step') {
              setLiveSteps(prev => [...prev, { step: evt.step, tool: evt.tool, output: evt.output }])
            } else if (evt.type === 'done') {
              setResult({ status: 'done', result: evt.result, steps: evt.steps || [] })
              refetch()
            } else if (evt.type === 'error') {
              toast.error(evt.message || traducir('nexusagent.error_agente'))
            }
          } catch { /* ignore parse errors */ }
        }
      }
    } catch (e) {
      if ((e as { name?: string })?.name !== 'AbortError') toast.error(traducir('nexusagent.error_conexion'))
    } finally {
      setIsStreaming(false)
    }
  }, [isStreaming, permitirEscritura, refetch, toast, traducir, t])

  const execute = () => {
    if (!instruction.trim()) return
    setResult(null); setLiveSteps([])
    if (streaming) runStream(instruction)
    else run(instruction)
  }

  const isRunning = isPending || isStreaming

  const handleKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey) && instruction.trim() && !isRunning) {
      execute()
    }
  }

  return (
    <PageShell>
      <PageHeader
        icon={<Bot size={18} />}
        title={t('ai.agent_title')}
        subtitle={traducir('nexusagent.subtitulo')}
      showListExport={false}
      />

      {/* Provider indicator */}
      {defaultProvider && (
        <div className="nexus-row-5">
          <span className="nexus-card" />
          {traducir('nexusagent.usando')} <strong className="u-text1">{defaultProvider.name}</strong> — {defaultProvider.default_model}
          <span className="nexus-label-4">· {traducir('nexusagent.configura_proveedores')}</span>
        </div>
      )}

      <div className="nexus-grid" style={{ gridTemplateColumns: isNarrow ? 'minmax(0, 1fr)' : 'minmax(0, 1fr) 260px' }}>
        <div className="u-min0">
          {/* Input */}
          <div style={{ ...card, padding: 24, marginBottom: 20 }}>
            <div className="nexus-box-3">{traducir('nexusagent.instruccion')}</div>
            <textarea
              ref={textareaRef}
              aria-label={traducir('nexusagent.instruccion')}
              value={instruction}
              onChange={e => setInstruction(e.target.value)}
              onKeyDown={handleKey}
              placeholder={traducir('nexusagent.ej_resume_el_estado_de_todos_los')}
              rows={4}
              className="nexus-input"
            />
            <div className="nexus-row-6">
              <div className="nexus-row-7">
                <span className="u-text3-xs">{traducir('nexusagent.enter_para_ejecutar')}</span>
                <label className="nexus-label-5">
                  <button type="button" aria-label={traducir('nexusagent.streaming')} aria-pressed={streaming} onClick={() => setStreaming(s => !s)}
                    className="nexus-btn-2" style={{ background: streaming ? 'var(--accent)' : 'var(--surface-4)' }}>
                    <div className="nexus-card-2" style={{ left: streaming ? 14 : 2 }} />
                  </button>
                  {traducir('nexusagent.streaming')}
                </label>
                <label className="nexus-label-5">
                  <input type="checkbox" aria-label={traducir('nexusagent.permitir_escritura')} checked={permitirEscritura} onChange={e => setPermitirEscritura(e.target.checked)} />
                  {traducir('nexusagent.permitir_escritura')}
                </label>
              </div>
              <Button onClick={execute} disabled={!instruction.trim() || isRunning}>
                {isRunning ? `⏳ ${traducir('nexusagent.ejecutando')}` : `▶ ${traducir('nexusagent.ejecutar')}`}
              </Button>
            </div>
          </div>

          {/* Streaming live steps */}
          {isStreaming && (
            <div style={{ ...card, padding: 24, marginBottom: 20 }}>
              <div className="nexus-row-8">
                <span className="nexus-card-3" />
                <span className="nexus-label-6">{traducir('nexusagent.en_tiempo_real')}</span>
              </div>
              {liveSteps.length === 0 && !liveText && (
                <div className="u-text2-base">{traducir('nexusagent.analizando_instruccion')}</div>
              )}
              {liveText && (
                <div className="nexus-card-4">
                  {liveText}
                </div>
              )}
              {liveSteps.map((s, i) => <StepBadge key={i} step={s} />)}
            </div>
          )}

          {/* Result */}
          {isPending && !isStreaming && (
            <div style={{ ...card, padding: 24, marginBottom: 20, textAlign: 'center' }}>
              <Spinner />
              <div className="nexus-box-4">{traducir('nexusagent.el_agente_esta_procesando_tu_instruccion')}</div>
            </div>
          )}

          {result && !isPending && (
            <div style={{ ...card, padding: 24, marginBottom: 20 }}>
              <div className="u-row-between-mb16">
                <div className="u-md-700">{traducir('nexusagent.resultado')}</div>
                <span className="nexus-label-7" style={{ background: STATUS_CFG[result.status ?? '']?.bg, color: STATUS_CFG[result.status ?? '']?.color }}>
                  {result.status && STATUS_CFG[result.status] ? t(`nexusagent.estado_${result.status}`) : result.status}
                </span>
              </div>
              <div className="nexus-card-5" style={{ marginBottom: result.steps?.length ? 16 : 0 }}>
                <MarkdownText text={result.result ?? ''} />
              </div>
              {(result.steps?.length ?? 0) > 0 && (
                <div>
                  <div className="nexus-box-5">
                    {traducir('nexusagent.pasos_ejecutados', { n: result.steps?.length ?? 0 })}
                  </div>
                  {(result.steps ?? []).map((s: PasoDeAgente, i: number) => <StepBadge key={i} step={s} />)}
                </div>
              )}
            </div>
          )}

          {/* History */}
          <div style={card}>
            <div className="nexus-row-9">
              <span className="nexus-label-8">{traducir('nexusagent.historial_de_ejecuciones')}</span>
              {history.length > 0 && (
                <span className="nexus-card-6">{history.length}</span>
              )}
            </div>
            {history.length === 0 ? (
              <div className="nexus-box-6">
                <EmptyState icon="⚡" title={traducir('nexusagent.sin_ejecuciones_recientes')} description={traducir('nexusagent.historial_vacio_ayuda')} />
              </div>
            ) : (
              <div role="list" className="nexus-box-7">
                {history.map(e => (
                  <FilaDeHistorial key={e.execution_id} ejecucion={e} seleccionada={e.execution_id === result?.execution_id}
                    onAbrir={() => abrirEjecucion(e)} />
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Sidebar */}
        <div>
          {/* Examples */}
          <div style={{ ...card, padding: '16px 18px', marginBottom: 14 }}>
            <div className="nexus-box-8">
              {traducir('nexusagent.ejemplos')}
            </div>
            {EXAMPLES.map((ex, i) => (
              <button key={i} onClick={() => { setInstruction(traducir(ex.text)); textareaRef.current?.focus() }}
                className="nexus-btn-3" style={{ border: 'none', borderBottom: i < EXAMPLES.length - 1 ? '1px solid color-mix(in srgb, var(--surface-4) 19%, transparent)' : 'none' }}>
                <span className="nexus-label-9">{ex.icon}</span>
                <span className="nexus-label-10">{traducir(ex.text)}</span>
              </button>
            ))}
          </div>

          {/* Tools */}
          <div style={{ ...card, padding: '16px 18px' }}>
            <div className="nexus-row-10">
              <div className="nexus-box-9">{traducir('nexusagent.herramientas')}</div>
              <button onClick={() => setShowTools(!showTools)}
                className="nexus-btn-4">
                {showTools ? traducir('nexusagent.ocultar') : traducir('nexusagent.ver_todas')}
              </button>
            </div>
            {(showTools ? TOOLS : TOOLS.slice(0, 5)).map(tool => (
              <div key={tool.name} className="nexus-row-11">
                <span className="nexus-label-11">{tool.icon}</span>
                <div>
                  <div className="nexus-box-10">{tool.name}</div>
                  <div className="u-text2-2xs">{traducir(tool.desc)}</div>
                </div>
              </div>
            ))}
            {!showTools && TOOLS.length > 5 && (
              <div className="nexus-box-11">+{TOOLS.length - 5} {traducir('nexusagent.mas')}</div>
            )}
          </div>
        </div>
      </div>
    </PageShell>
  )
}
