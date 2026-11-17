/**
 * NexusAgentPage — el agente que ejecuta instrucciones en lenguaje natural.
 *
 * 16-11-2026: título = el del menú; tarjetas con Card/Section del kit (antes
 * cajas propias); ejemplos y herramientas con iconos lucide en vez de emojis;
 * las herramientas ya no enseñan su nombre técnico (search_projects…), solo la
 * descripción traducida; el proveedor sintético del servidor ya no enseña
 * "(.env)": se dice en llano que lo configura el administrador; estados con
 * StatusBadge; fechas con fmtDateTime según idioma; vacío con icono lucide;
 * campo de instrucción con ds-input.
 */
import React, { useState, useRef, useCallback } from 'react'
import type { ReactNode } from 'react'
import { extractErr, fmtDateTime } from '../utils/helpers'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation } from '@tanstack/react-query'
import { aiProvidersApi, nexusAgentApi, apiStream } from '../services/api'
import type { EjecucionDelAgente, EjecucionDelAgenteResumen, PasoDelAgente } from '../services/api/tipos-analitica'
import { Button, Card, Checkbox, EmptyState, Pulsable, Section, Spinner } from '../components/ui'
import StatusBadge from '../components/ui/StatusBadge'
import type { StatusBadgeKind } from '../components/ui/StatusBadge'
import MarkdownText from '../components/ui/MarkdownText'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import {
  Activity, AlarmClock, AlertTriangle, BarChart3, Bot, ChevronRight, Clock, FolderSearch, History, LayoutDashboard,
  ListPlus, Pencil, Play, Repeat, Search, ShieldAlert, Ticket, TrendingUp, Users, Wallet, Wrench, Zap,
} from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import useMediaQuery from '../hooks/useMediaQuery'
import { POLL_JOB_STATUS_MS } from '../constants/timings'
import './NexusAgentPage.css'

const STATUS_KIND: Record<string, StatusBadgeKind> = {
  done: 'success',
  failed: 'danger',
  running: 'warning',
  pending: 'neutral',
}
// Tools alineados con los nombres reales del backend (AGENT_TOOLS en
// app/services/ai_chat/tool_execution_service.py). Antes los 10 mostrados
// aquí no coincidían con los 37 reales del backend → user confundido.
const TOOLS: { icon: ReactNode; name: string; desc: string }[] = [
  { icon: <FolderSearch size={14} />,    name: 'search_projects',       desc: 'nexusagent.herramienta_search_projects' },
  { icon: <Activity size={14} />,        name: 'get_project_status',    desc: 'nexusagent.herramienta_get_project_status' },
  { icon: <LayoutDashboard size={14} />, name: 'get_dashboard_summary', desc: 'nexusagent.herramienta_get_dashboard_summary' },
  { icon: <Wallet size={14} />,          name: 'get_budget_status',     desc: 'nexusagent.herramienta_get_budget_status' },
  { icon: <AlertTriangle size={14} />,   name: 'get_project_risks',     desc: 'nexusagent.herramienta_get_project_risks' },
  { icon: <AlarmClock size={14} />,      name: 'get_overdue_tasks',     desc: 'nexusagent.herramienta_get_overdue_tasks' },
  { icon: <Ticket size={14} />,          name: 'get_open_tickets',      desc: 'nexusagent.herramienta_get_open_tickets' },
  { icon: <Users size={14} />,           name: 'get_users_list',        desc: 'nexusagent.herramienta_get_users_list' },
  { icon: <Clock size={14} />,           name: 'get_imputations',       desc: 'nexusagent.herramienta_get_imputations' },
  { icon: <TrendingUp size={14} />,      name: 'get_profitability',     desc: 'nexusagent.herramienta_get_profitability' },
  { icon: <ListPlus size={14} />,        name: 'create_task',           desc: 'nexusagent.herramienta_create_task' },
  { icon: <Pencil size={14} />,          name: 'update_task',           desc: 'nexusagent.herramienta_update_task' },
  { icon: <ShieldAlert size={14} />,     name: 'create_risk',           desc: 'nexusagent.herramienta_create_risk' },
  { icon: <Repeat size={14} />,          name: 'reassign_tickets',      desc: 'nexusagent.herramienta_reassign_tickets' },
  { icon: <Search size={14} />,          name: 'search_all',            desc: 'nexusagent.herramienta_search_all' },
]
const EXAMPLES: { icon: ReactNode; text: string }[] = [
  { icon: <BarChart3 size={14} />,     text: 'nexusagent.ejemplo_1' },
  { icon: <AlertTriangle size={14} />, text: 'nexusagent.ejemplo_2' },
  { icon: <ListPlus size={14} />,      text: 'nexusagent.ejemplo_3' },
  { icon: <Users size={14} />,         text: 'nexusagent.ejemplo_4' },
  { icon: <Ticket size={14} />,        text: 'nexusagent.ejemplo_5' },
  { icon: <TrendingUp size={14} />,    text: 'nexusagent.ejemplo_6' },
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
  const t = useAppT()
  const herramienta = TOOLS.find(x => x.name === step.tool)
  return (
    <div className="nexus-paso">
      <span className="nexus-paso__num">{step.step}</span>
      <div className="u-flex1-min0">
        <div className="nexus-paso__herramienta">
          {herramienta ? <>{herramienta.icon}{t(herramienta.desc)}</> : <><Wrench size={14} />{step.tool}</>}
        </div>
        {step.output != null && step.output !== '' && (
          <div className="nexus-paso__salida">
            {typeof step.output === 'string' ? step.output.slice(0, 120) : JSON.stringify(step.output).slice(0, 120)}
          </div>
        )}
      </div>
    </div>
  )
}

/** Quita la marca de markdown para la vista previa de una línea. */
const sinMarkdown = (texto = '') => texto.replace(/[*_`#>]+/g, '').replace(/\s+/g, ' ').trim()

/** Una ejecución del historial. */
function FilaDeHistorial({ ejecucion: e, seleccionada, onAbrir }: { ejecucion: EjecucionDelAgenteResumen; seleccionada: boolean; onAbrir: () => void }) {
  const t = useAppT()
  const estado = e.status && STATUS_KIND[e.status] ? e.status : 'pending'
  const pasos = e.steps_count ?? 0
  return (
    <div role="listitem">
    <Pulsable onClick={onAbrir} aria-current={seleccionada || undefined}
      className={`nexus-hist${seleccionada ? ' nexus-hist--activa' : ''}`}>
      <span className="nexus-hist__cuerpo">
        <span className="nexus-hist__instruccion">{e.instruction}</span>
        {e.result && <span className="nexus-hist__resultado">{sinMarkdown(e.result)}</span>}
        <span className="nexus-hist__meta">
          <StatusBadge kind={STATUS_KIND[estado]} caps={false}>{t(`nexusagent.estado_${estado}`)}</StatusBadge>
          {e.created_at && <time dateTime={e.created_at}>{fmtDateTime(e.created_at)}</time>}
          {pasos > 0 && <><span aria-hidden>·</span><span>{t('nexusagent.n_pasos', { n: pasos })}</span></>}
        </span>
      </span>
      <ChevronRight size={16} aria-hidden className="nexus-hist__flecha" />
    </Pulsable>
    </div>
  )
}

export default function ContecflowAgentPage() {
  const t = useAppT()
  const isNarrow = useMediaQuery('(max-width: 900px)')
  const toast = useToast()
  const [instruction, setInstruction] = useState('')
  const [result, setResult] = useState<ResultadoDeAgente | null>(null)
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
  const proveedorDelServidor = defaultProvider?.source === 'env'
  const nombreProveedor = defaultProvider?.name ?? ''

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
    onError: e => toast.error(extractErr(e, t('nexusagent.error_ejecutar'))),
  })

  // El historial trae un resumen (instrucción recortada, sin pasos): se pinta
  // al momento y se sustituye por la ejecución completa en cuanto llega.
  const abrirEjecucion = (e: EjecucionDelAgenteResumen) => {
    setResult({ ...e, steps: [] })
    nexusAgentApi.detail(e.execution_id)
      .then(r => setResult(r.data))
      .catch(err => toast.error(extractErr(err, t('nexusagent.error_ejecutar'))))
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
        toast.error(err.detail || t('nexusagent.error_streaming'))
        setIsStreaming(false)
        return
      }

      if (!resp.body) {
        toast.error(t('nexusagent.error_sin_flujo'))
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
              toast.error(evt.message || t('nexusagent.error_agente'))
            }
          } catch { /* ignore parse errors */ }
        }
      }
    } catch (e) {
      if ((e as { name?: string })?.name !== 'AbortError') toast.error(t('nexusagent.error_conexion'))
    } finally {
      setIsStreaming(false)
    }
  }, [isStreaming, permitirEscritura, refetch, toast, t])

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

  const estadoResultado = result?.status && STATUS_KIND[result.status] ? result.status : null

  return (
    <PageShell>
      <PageHeader
        icon={<Bot size={18} />}
        title={t('nav.nexus_agent')}
        subtitle={t('nexusagent.subtitulo')}
        showListExport={false}
      />

      <div className="u-stack-16">
        {/* Proveedor en uso */}
        {defaultProvider && (
          <div className="nexus-proveedor">
            <span className="nexus-proveedor__punto" aria-hidden />
            <span>
              {t('nexusagent.usando')} <strong className="u-text1">{nombreProveedor}</strong>
              {defaultProvider.default_model && <> — {defaultProvider.default_model}</>}
              {proveedorDelServidor && <> ({t('nexusagent.config_servidor')})</>}
            </span>
            <span className="nexus-proveedor__pista">· {t('nexusagent.configura_proveedores')}</span>
          </div>
        )}

        <div className={`nexus-layout${isNarrow ? ' nexus-layout--estrecho' : ''}`}>
          <div className="u-stack-16 u-min0">
            {/* Instrucción */}
            <Card>
              <label htmlFor="nexus-instruccion" className="nexus-etiqueta">{t('nexusagent.instruccion')}</label>
              <textarea
                id="nexus-instruccion"
                ref={textareaRef}
                value={instruction}
                onChange={e => setInstruction(e.target.value)}
                onKeyDown={handleKey}
                placeholder={t('nexusagent.ej_resume_el_estado_de_todos_los')}
                rows={4}
                className="ds-input nexus-instruccion"
              />
              <div className="nexus-controles">
                <div className="nexus-opciones">
                  <span className="nexus-pista">{t('nexusagent.enter_para_ejecutar')}</span>
                  <Checkbox className="nexus-check" checked={!!streaming} onChange={setStreaming} label={t('nexusagent.streaming')} />
                  <Checkbox className="nexus-check" checked={!!permitirEscritura} onChange={setPermitirEscritura} label={t('nexusagent.permitir_escritura')} />
                </div>
                <Button icon={<Play size={14} />} onClick={execute} disabled={!instruction.trim()} loading={isRunning}>
                  {isRunning ? t('nexusagent.ejecutando') : t('nexusagent.ejecutar')}
                </Button>
              </div>
            </Card>

            {/* Pasos en directo */}
            {isStreaming && (
              <Card>
                <div className="nexus-directo">
                  <span className="nexus-directo__punto" aria-hidden />
                  <span>{t('nexusagent.en_tiempo_real')}</span>
                </div>
                {liveSteps.length === 0 && !liveText && (
                  <div className="nexus-pista">{t('nexusagent.analizando_instruccion')}</div>
                )}
                {liveText && <div className="nexus-texto-vivo">{liveText}</div>}
                {liveSteps.map((s, i) => <StepBadge key={i} step={s} />)}
              </Card>
            )}

            {/* Resultado */}
            {isPending && !isStreaming && (
              <Card>
                <div className="nexus-procesando">
                  <Spinner />
                  <div className="nexus-pista">{t('nexusagent.el_agente_esta_procesando_tu_instruccion')}</div>
                </div>
              </Card>
            )}

            {result && !isPending && (
              <Card>
                <Section
                  title={t('nexusagent.resultado')}
                  actions={result.status ? (
                    <StatusBadge kind={estadoResultado ? STATUS_KIND[estadoResultado] : 'neutral'} caps={false}>
                      {estadoResultado ? t(`nexusagent.estado_${estadoResultado}`) : result.status}
                    </StatusBadge>
                  ) : undefined}
                >
                  <div className="nexus-resultado">
                    <MarkdownText text={result.result ?? ''} />
                  </div>
                  {(result.steps?.length ?? 0) > 0 && (
                    <div className="nexus-pasos">
                      <div className="nexus-etiqueta">{t('nexusagent.pasos_ejecutados', { n: result.steps?.length ?? 0 })}</div>
                      {(result.steps ?? []).map((s: PasoDeAgente, i: number) => <StepBadge key={i} step={s} />)}
                    </div>
                  )}
                </Section>
              </Card>
            )}

            {/* Historial */}
            <Card>
              <Section title={<span className="nexus-titulo"><History size={16} aria-hidden />{t('nexusagent.historial_de_ejecuciones')}
                {history.length > 0 && <StatusBadge kind="neutral" caps={false}>{history.length}</StatusBadge>}</span>}>
                {history.length === 0 ? (
                  <EmptyState icon={<Zap size={28} />} title={t('nexusagent.sin_ejecuciones_recientes')} description={t('nexusagent.historial_vacio_ayuda')} />
                ) : (
                  <div role="list" className="nexus-historial">
                    {history.map(e => (
                      <FilaDeHistorial key={e.execution_id} ejecucion={e} seleccionada={e.execution_id === result?.execution_id}
                        onAbrir={() => abrirEjecucion(e)} />
                    ))}
                  </div>
                )}
              </Section>
            </Card>
          </div>

          {/* Lateral */}
          <div className="u-stack-16 u-min0">
            <Card>
              <Section title={t('nexusagent.ejemplos')}>
                <div className="nexus-ejemplos">
                  {EXAMPLES.map((ex, i) => (
                    <Pulsable key={i} className="nexus-ejemplo"
                      onClick={() => { setInstruction(t(ex.text)); textareaRef.current?.focus() }}>
                      <span className="nexus-ejemplo__icono" aria-hidden>{ex.icon}</span>
                      <span>{t(ex.text)}</span>
                    </Pulsable>
                  ))}
                </div>
              </Section>
            </Card>

            <Card>
              <Section title={t('nexusagent.herramientas')}
                actions={<Button size="sm" variant="ghost" onClick={() => setShowTools(!showTools)}>
                  {showTools ? t('nexusagent.ocultar') : t('nexusagent.ver_todas')}
                </Button>}>
                <ul className="nexus-herramientas">
                  {(showTools ? TOOLS : TOOLS.slice(0, 5)).map(tool => (
                    <li key={tool.name} className="nexus-herramienta">
                      <span className="nexus-herramienta__icono" aria-hidden>{tool.icon}</span>
                      <span>{t(tool.desc)}</span>
                    </li>
                  ))}
                </ul>
                {!showTools && TOOLS.length > 5 && (
                  <div className="nexus-pista">+{TOOLS.length - 5} {t('nexusagent.mas')}</div>
                )}
              </Section>
            </Card>
          </div>
        </div>
      </div>
    </PageShell>
  )
}
