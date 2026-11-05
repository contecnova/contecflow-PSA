import React, { useState, useRef, useCallback } from 'react'
import { extractErr } from '../utils/helpers'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { aiProvidersApi, nexusAgentApi } from '../services/api'
import { Button, Spinner, EmptyState } from '../components/ui'
import MarkdownText from '../components/ui/MarkdownText'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Bot } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import { alpha } from '../constants/theme'

const card = { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12 }
const STATUS_CFG: Record<string, { label: string; color: string; bg: string }> = {
  done:    { label: 'Completado', color: 'var(--success)', bg: 'var(--success-bg)' },
  failed:  { label: 'Error',      color: 'var(--danger)', bg: 'var(--danger-bg)' },
  running: { label: 'Ejecutando', color: 'var(--warning)', bg: 'var(--warning-bg)' },
  pending: { label: 'Pendiente',  color: 'var(--text-2)', bg: 'rgba(120,138,170,0.09)' },
}
// Tools alineados con los nombres reales del backend (AGENT_TOOLS en
// app/services/ai_chat/tool_execution_service.py). Antes los 10 mostrados
// aquí no coincidían con los 37 reales del backend → user confundido.
const TOOLS = [
  { icon: '📁', name: 'search_projects',         desc: 'Buscar proyectos por filtros' },
  { icon: '📊', name: 'get_project_status',      desc: 'Estado completo de un proyecto' },
  { icon: '🎯', name: 'get_dashboard_summary',   desc: 'Resumen ejecutivo del sistema' },
  { icon: '💰', name: 'get_budget_status',       desc: 'Estado presupuestario' },
  { icon: '⚠️', name: 'get_project_risks',        desc: 'Riesgos de un proyecto' },
  { icon: '⏰', name: 'get_overdue_tasks',        desc: 'Tareas vencidas' },
  { icon: '🎫', name: 'get_open_tickets',        desc: 'Tickets abiertos de soporte' },
  { icon: '👥', name: 'get_users_list',          desc: 'Listado de usuarios y rol' },
  { icon: '📅', name: 'get_imputations',         desc: 'Imputaciones de horas' },
  { icon: '📈', name: 'get_profitability',       desc: 'Rentabilidad por proyecto' },
  { icon: '➕', name: 'create_task',              desc: 'Crear tarea (acción de escritura)' },
  { icon: '✏️', name: 'update_task',              desc: 'Actualizar tarea' },
  { icon: '🚨', name: 'create_risk',             desc: 'Crear riesgo en proyecto' },
  { icon: '🔁', name: 'reassign_tickets',        desc: 'Reasignar tickets en masa' },
  { icon: '🔍', name: 'search_all',              desc: 'Búsqueda transversal' },
]
const EXAMPLES = [
  { icon: '📊', text: 'Muéstrame un resumen del estado de todos los proyectos activos' },
  { icon: '⚠️', text: 'Lista las tareas vencidas y dime qué proyectos están en riesgo' },
  { icon: '➕', text: 'Crea una tarea "Revisión QA final" en el primer proyecto activo con prioridad alta' },
  { icon: '👥', text: '¿Qué recursos tienen menos del 50% de utilización esta semana?' },
  { icon: '🎫', text: 'Lista los tickets urgentes sin resolver y asigna los huérfanos' },
  { icon: '📈', text: 'Dame el análisis de productividad del equipo del último mes' },
]


// ─────────────────────────────────────────────────────────────────────────────
// Las formas que esta pagina consume
//
// Auditoria 2026-09 (modo estricto): el cliente de API devuelve `any` —esta sin
// tipar de origen— y de ahi salian 23 errores en este fichero. Declararlas aqui,
// al lado de donde se usan, es lo correcto mientras la capa de API no tenga
// tipos: describe **lo que esta pagina lee**, ni mas ni menos, y se rompe sola
// si el backend deja de mandar algo que aqui se pinta. Los campos van
// opcionales a proposito: el backend los envia, pero prometer que siempre
// vienen seria afirmar algo que este fichero no puede garantizar.
// ─────────────────────────────────────────────────────────────────────────────

/** Un paso que el agente ejecuto: que herramienta y que devolvio. */
interface PasoDeAgente {
  step?: number
  tool?: string
  output?: string
}

/** Una ejecucion del agente, tal como la lista el historial. */
interface EjecucionDeAgente {
  id?: string
  status?: string
  instruction?: string
  result?: string
  created_at?: string
  steps?: PasoDeAgente[]
}

/** Un proveedor de IA configurado. */
interface ProveedorDeIa {
  id?: string
  name?: string
  is_default?: boolean
  default_model?: string
}

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
    <div style={{ display: 'flex', gap: 10, padding: '10px 14px', background: 'var(--surface-1)', borderRadius: 8, marginBottom: 6 }}>
      <div style={{ width: 24, height: 24, borderRadius: 6, background: alpha(c, '20'), border: `1px solid ${alpha(c, '40')}`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: "var(--text-xs)", fontWeight: 700, color: c, flexShrink: 0 }}>
        {step.step}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: "var(--text-sm)", fontWeight: 600, color: c, marginBottom: 2 }}>{step.tool}</div>
        {step.output && (
          <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
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
function FilaDeHistorial({ ejecucion: e, seleccionada, onAbrir }: { ejecucion: EjecucionDeAgente; seleccionada: boolean; onAbrir: () => void }) {
  const t = useAppT()
  const [encima, setEncima] = useState(false)
  const estado = e.status && STATUS_CFG[e.status] ? e.status : 'pending'
  const sc = STATUS_CFG[estado]
  const pasos = e.steps?.length ?? 0
  const fecha = e.created_at ? new Date(e.created_at) : null
  return (
    <button type="button" role="listitem" onClick={onAbrir} aria-current={seleccionada || undefined}
      onMouseEnter={() => setEncima(true)} onMouseLeave={() => setEncima(false)}
      style={{
        display: 'flex', alignItems: 'center', gap: 14, width: '100%', textAlign: 'left', fontFamily: 'inherit',
        color: 'var(--text-1)', padding: '12px 14px', margin: 0, borderRadius: 10, cursor: 'pointer',
        border: `1px solid ${seleccionada ? alpha(sc.color, '55') : 'transparent'}`,
        background: seleccionada ? alpha(sc.color, '12') : encima ? 'var(--surface-3)' : 'transparent',
        transition: 'background 0.15s, border-color 0.15s',
      }}>
      <span aria-hidden style={{ width: 32, height: 32, borderRadius: 9, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: sc.bg, color: sc.color, border: `1px solid ${alpha(sc.color, '40')}`, fontWeight: 700, fontSize: "var(--text-sm)" }}>
        {ICONO_DE_ESTADO[estado]}
      </span>
      <span style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 3 }}>
        <span style={{ fontSize: "var(--text-base)", fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {e.instruction}
        </span>
        {e.result && (
          <span style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', lineHeight: 1.45, overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>
            {sinMarkdown(e.result)}
          </span>
        )}
        <span style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: "var(--text-xs)", color: 'var(--text-3)', marginTop: 2 }}>
          <span style={{ color: sc.color, fontWeight: 600 }}>{t(`nexusagent.estado_${estado}`)}</span>
          {fecha && !isNaN(fecha.getTime()) && <><span aria-hidden>·</span><time dateTime={e.created_at}>{fecha.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}</time></>}
          {pasos > 0 && <><span aria-hidden>·</span><span>{t('nexusagent.n_pasos', { n: pasos })}</span></>}
        </span>
      </span>
      <span aria-hidden style={{ color: seleccionada || encima ? 'var(--accent)' : 'var(--text-3)', fontSize: "var(--text-lg)", flexShrink: 0, transition: 'color 0.15s' }}>›</span>
    </button>
  )
}

export default function ContecflowAgentPage() {
  const traducir = useAppT()
  const t = useAppT()
  const _qc = useQueryClient()
  const toast = useToast()
  const [instruction, setInstruction] = useState('')
  const [result, setResult] = useState<EjecucionDeAgente | null>(null)
  const [_selectedExec, _setSelectedExec] = useState<EjecucionDeAgente | null>(null)
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

  const { data: providers = [] } = useQuery<ProveedorDeIa[]>({
    queryKey: ['ai-providers'],
    queryFn: () => aiProvidersApi.list().then(r => r.data),
  })
  const defaultProvider = providers.find(p => p.is_default) || providers[0]

  const { data: history = [], refetch } = useQuery<EjecucionDeAgente[]>({
    queryKey: ['agent-history'],
    queryFn: () => nexusAgentApi.history().then(r => r.data),
  })

  const { mutate: run, isPending } = useMutation({
    mutationFn: (inst: string) => nexusAgentApi.run(inst, permitirEscritura).then(r => r.data),
    onSuccess: data => { setResult(data); refetch() },
    onError: e => toast.error(extractErr(e, 'Error al ejecutar el agente')),
  })

  const runStream = useCallback(async (inst: string) => {
    if (isStreaming) return
    setIsStreaming(true)
    setLiveSteps([])
    setLiveText('')
    setResult(null)

    const ctrl = new AbortController()
    abortRef.current = ctrl

    try {
      // #45: kept as fetch() — side-effects/realtime/optimistic
      const resp = await fetch('/api/v1/ai/agent/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ instruction: inst, auto_approve: permitirEscritura }),
        signal: ctrl.signal,
      })
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: 'Error' }))
        toast.error(err.detail || 'Error en streaming')
        setIsStreaming(false)
        return
      }

      if (!resp.body) {
        toast.error('El servidor no devolvio flujo de respuesta')
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
              toast.error(evt.message || 'Error en agente')
            }
          } catch { /* ignore parse errors */ }
        }
      }
    } catch (e) {
      if ((e as { name?: string })?.name !== 'AbortError') toast.error('Error de conexión en streaming')
    } finally {
      setIsStreaming(false)
    }
  }, [isStreaming, permitirEscritura, refetch, toast])

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
        subtitle="Ejecuta instrucciones en lenguaje natural sobre tus proyectos y datos"
      showListExport={false}
      />

      {/* Provider indicator */}
      {defaultProvider && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 20, fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>
          <span style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--success)', display: 'inline-block' }} />
          Usando <strong style={{ color: 'var(--text-1)' }}>{defaultProvider.name}</strong> — {defaultProvider.default_model}
          <span style={{ marginLeft: 8, color: 'var(--text-3)' }}>· Configura proveedores en IA & Conectores</span>
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 260px', gap: 20 }}>
        <div>
          {/* Input */}
          <div style={{ ...card, padding: 24, marginBottom: 20 }}>
            <div style={{ fontSize: "var(--text-base)", fontWeight: 700, marginBottom: 10, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{traducir('nexusagent.instruccion')}</div>
            <textarea
              ref={textareaRef}
              value={instruction}
              onChange={e => setInstruction(e.target.value)}
              onKeyDown={handleKey}
              placeholder={traducir('nexusagent.ej_resume_el_estado_de_todos_los')}
              rows={4}
              style={{ width: '100%', background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 10, padding: '12px 14px', fontSize: "var(--text-md)", fontFamily: 'inherit', resize: 'vertical', outline: 'none', color: 'var(--text-1)', boxSizing: 'border-box', lineHeight: 1.6 }}
            />
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 12 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)' }}>{traducir('nexusagent.enter_para_ejecutar')}</span>
                <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>
                  <button type="button" onClick={() => setStreaming(s => !s)}
                    style={{ width: 28, height: 16, borderRadius: 8, background: streaming ? 'var(--accent)' : 'var(--surface-4)', position: 'relative', transition: 'background 0.2s', cursor: 'pointer', border: 'none', padding: 0 }}>
                    <div style={{ position: 'absolute', top: 2, left: streaming ? 14 : 2, width: 12, height: 12, borderRadius: '50%', background: 'white', transition: 'left 0.2s' }} />
                  </button>
                  Streaming en vivo
                </label>
                <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>
                  <input type="checkbox" checked={permitirEscritura} onChange={e => setPermitirEscritura(e.target.checked)} />
                  {traducir('nexusagent.permitir_escritura')}
                </label>
              </div>
              <Button onClick={execute} disabled={!instruction.trim() || isRunning}>
                {isRunning ? '⏳ Ejecutando...' : '▶ Ejecutar agente'}
              </Button>
            </div>
          </div>

          {/* Streaming live steps */}
          {isStreaming && (
            <div style={{ ...card, padding: 24, marginBottom: 20 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
                <span style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--accent)', display: 'inline-block', animation: 'pulse 1s infinite' }} />
                <span style={{ fontSize: "var(--text-base)", fontWeight: 700, color: 'var(--accent)' }}>Agente ejecutando en tiempo real…</span>
              </div>
              {liveSteps.length === 0 && !liveText && (
                <div style={{ fontSize: "var(--text-base)", color: 'var(--text-2)' }}>{traducir('nexusagent.analizando_instruccion')}</div>
              )}
              {liveText && (
                <div style={{ background: 'var(--surface-1)', borderRadius: 10, padding: '14px 16px', fontSize: "var(--text-base)", lineHeight: 1.7, whiteSpace: 'pre-wrap', color: 'var(--text-1)' }}>
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
              <div style={{ marginTop: 12, fontSize: "var(--text-base)", color: 'var(--text-2)' }}>{traducir('nexusagent.el_agente_esta_procesando_tu_instruccion')}</div>
            </div>
          )}

          {result && !isPending && (
            <div style={{ ...card, padding: 24, marginBottom: 20 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                <div style={{ fontSize: "var(--text-md)", fontWeight: 700 }}>Resultado</div>
                <span style={{ fontSize: "var(--text-sm)", padding: '3px 10px', borderRadius: 20, background: STATUS_CFG[result.status ?? '']?.bg, color: STATUS_CFG[result.status ?? '']?.color, fontWeight: 600 }}>
                  {result.status && STATUS_CFG[result.status] ? t(`nexusagent.estado_${result.status}`) : result.status}
                </span>
              </div>
              <div style={{ background: 'var(--surface-1)', borderRadius: 10, padding: '14px 16px', fontSize: "var(--text-base)", lineHeight: 1.7, marginBottom: result.steps?.length ? 16 : 0, color: 'var(--text-1)' }}>
                <MarkdownText text={result.result ?? ''} />
              </div>
              {(result.steps?.length ?? 0) > 0 && (
                <div>
                  <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 }}>
                    Pasos ejecutados ({result.steps?.length ?? 0})
                  </div>
                  {(result.steps ?? []).map((s: PasoDeAgente, i: number) => <StepBadge key={i} step={s} />)}
                </div>
              )}
            </div>
          )}

          {/* History */}
          <div style={card}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '14px 20px', borderBottom: '1px solid var(--surface-4)' }}>
              <span style={{ fontSize: "var(--text-md)", fontWeight: 700, color: 'var(--text-1)' }}>{traducir('nexusagent.historial_de_ejecuciones')}</span>
              {history.length > 0 && (
                <span style={{ fontSize: "var(--text-xs)", fontWeight: 600, color: 'var(--text-2)', background: 'var(--surface-3)', borderRadius: 999, padding: '1px 8px' }}>{history.length}</span>
              )}
            </div>
            {history.length === 0 ? (
              <div style={{ padding: 32 }}>
                <EmptyState icon="⚡" title={traducir('nexusagent.sin_ejecuciones_recientes')} description={traducir('nexusagent.historial_vacio_ayuda')} />
              </div>
            ) : (
              <div role="list" style={{ padding: 6 }}>
                {history.map((e: EjecucionDeAgente, i: number) => (
                  <FilaDeHistorial key={e.id ?? i} ejecucion={e} seleccionada={!!e.id && e.id === result?.id}
                    onAbrir={() => setResult(e)} />
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Sidebar */}
        <div>
          {/* Examples */}
          <div style={{ ...card, padding: '16px 18px', marginBottom: 14 }}>
            <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 12 }}>
              Ejemplos
            </div>
            {EXAMPLES.map((ex, i) => (
              <button key={i} onClick={() => { setInstruction(ex.text); textareaRef.current?.focus() }}
                style={{ width: '100%', display: 'flex', gap: 8, padding: '8px 0', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit', borderBottom: i < EXAMPLES.length - 1 ? '1px solid color-mix(in srgb, var(--surface-4) 19%, transparent)' : 'none', textAlign: 'left' }}>
                <span style={{ flexShrink: 0 }}>{ex.icon}</span>
                <span style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', lineHeight: 1.4 }}>{ex.text}</span>
              </button>
            ))}
          </div>

          {/* Tools */}
          <div style={{ ...card, padding: '16px 18px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
              <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Herramientas</div>
              <button onClick={() => setShowTools(!showTools)}
                style={{ background: 'none', border: 'none', color: 'var(--accent)', fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}>
                {showTools ? 'Ocultar' : 'Ver todas'}
              </button>
            </div>
            {(showTools ? TOOLS : TOOLS.slice(0, 5)).map(t => (
              <div key={t.name} style={{ display: 'flex', gap: 8, padding: '6px 0', borderBottom: '1px solid color-mix(in srgb, var(--surface-4) 13%, transparent)', alignItems: 'center' }}>
                <span style={{ fontSize: "var(--text-md)" }}>{t.icon}</span>
                <div>
                  <div style={{ fontSize: "var(--text-xs)", fontWeight: 600, color: 'var(--text-1)', fontFamily: 'var(--font-mono)' }}>{t.name}</div>
                  <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-2)' }}>{t.desc}</div>
                </div>
              </div>
            ))}
            {!showTools && TOOLS.length > 5 && (
              <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', marginTop: 6 }}>+{TOOLS.length - 5} {traducir('nexusagent.mas')}</div>
            )}
          </div>
        </div>
      </div>
    </PageShell>
  )
}
