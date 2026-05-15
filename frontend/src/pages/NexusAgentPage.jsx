import { useState, useRef, useCallback } from 'react'
import { extractErr } from '../utils/helpers'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { aiProvidersApi, nexusAgentApi } from '../services/api'
import { Button, Spinner, EmptyState } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Bot } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'

const card = { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12 }
const STATUS_CFG = {
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

function StepBadge({ step }) {
  const colors = { list_projects:'var(--accent)', list_tasks:'var(--success)', create_task:'var(--warning)',
                   update_task:'var(--warning)', list_tickets:'var(--purple)', get_project_stats:'var(--accent)' }
  const c = colors[step.tool] || 'var(--text-2)'
  return (
    <div style={{ display: 'flex', gap: 10, padding: '10px 14px', background: 'var(--surface-1)', borderRadius: 8, marginBottom: 6 }}>
      <div style={{ width: 24, height: 24, borderRadius: 6, background: c + '20', border: `1px solid ${c}40`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: "var(--text-xs)", fontWeight: 700, color: c, flexShrink: 0 }}>
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

export default function ContecflowAgentPage() {
  const t = useAppT()
  const _qc = useQueryClient()
  const toast = useToast()
  const [instruction, setInstruction] = useState('')
  const [result, setResult] = useState(null)
  const [_selectedExec, _setSelectedExec] = useState(null)
  const [showTools, setShowTools] = useState(false)
  const [streaming, setStreaming] = useState(true)
  const [liveSteps, setLiveSteps] = useState([])
  const [liveText, setLiveText] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const textareaRef = useRef(null)
  const abortRef = useRef(null)

  const { data: providers = [] } = useQuery({
    queryKey: ['ai-providers'],
    queryFn: () => aiProvidersApi.list().then(r => r.data),
  })
  const defaultProvider = providers.find(p => p.is_default) || providers[0]

  const { data: history = [], refetch } = useQuery({
    queryKey: ['agent-history'],
    queryFn: () => nexusAgentApi.history().then(r => r.data),
  })

  const { mutate: run, isPending } = useMutation({
    mutationFn: inst => nexusAgentApi.run(inst).then(r => r.data),
    onSuccess: data => { setResult(data); refetch() },
    onError: e => toast.error(extractErr(e, 'Error al ejecutar el agente')),
  })

  const runStream = useCallback(async (inst) => {
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
        body: JSON.stringify({ instruction: inst, auto_approve: true }),
        signal: ctrl.signal,
      })
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: 'Error' }))
        toast.error(err.detail || 'Error en streaming')
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
        buf = lines.pop()
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const evt = JSON.parse(line.slice(6))
            if (evt.type === 'token') {
              setLiveText(prev => prev + evt.text)
            } else if (evt.type === 'step') {
              setLiveSteps(prev => [...prev, evt])
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
      if (e.name !== 'AbortError') toast.error('Error de conexión en streaming')
    } finally {
      setIsStreaming(false)
    }
  }, [isStreaming, refetch, toast])

  const execute = () => {
    if (!instruction.trim()) return
    setResult(null); setLiveSteps([])
    if (streaming) runStream(instruction)
    else run(instruction)
  }

  const isRunning = isPending || isStreaming

  const handleKey = e => {
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
            <div style={{ fontSize: "var(--text-base)", fontWeight: 700, marginBottom: 10, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Instrucción</div>
            <textarea
              ref={textareaRef}
              value={instruction}
              onChange={e => setInstruction(e.target.value)}
              onKeyDown={handleKey}
              placeholder="Ej: Resume el estado de todos los proyectos activos..."
              rows={4}
              style={{ width: '100%', background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 10, padding: '12px 14px', fontSize: "var(--text-md)", fontFamily: 'inherit', resize: 'vertical', outline: 'none', color: 'var(--text-1)', boxSizing: 'border-box', lineHeight: 1.6 }}
            />
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 12 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)' }}>⌘+Enter para ejecutar</span>
                <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>
                  <button type="button" onClick={() => setStreaming(s => !s)}
                    style={{ width: 28, height: 16, borderRadius: 8, background: streaming ? 'var(--accent)' : 'var(--surface-4)', position: 'relative', transition: 'background 0.2s', cursor: 'pointer', border: 'none', padding: 0 }}>
                    <div style={{ position: 'absolute', top: 2, left: streaming ? 14 : 2, width: 12, height: 12, borderRadius: '50%', background: 'white', transition: 'left 0.2s' }} />
                  </button>
                  Streaming en vivo
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
                <div style={{ fontSize: "var(--text-base)", color: 'var(--text-2)' }}>Analizando instrucción…</div>
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
              <div style={{ marginTop: 12, fontSize: "var(--text-base)", color: 'var(--text-2)' }}>El agente está procesando tu instrucción...</div>
            </div>
          )}

          {result && !isPending && (
            <div style={{ ...card, padding: 24, marginBottom: 20 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                <div style={{ fontSize: "var(--text-md)", fontWeight: 700 }}>Resultado</div>
                <span style={{ fontSize: "var(--text-sm)", padding: '3px 10px', borderRadius: 20, background: STATUS_CFG[result.status]?.bg, color: STATUS_CFG[result.status]?.color, fontWeight: 600 }}>
                  {STATUS_CFG[result.status]?.label || result.status}
                </span>
              </div>
              <div style={{ background: 'var(--surface-1)', borderRadius: 10, padding: '14px 16px', fontSize: "var(--text-base)", lineHeight: 1.7, whiteSpace: 'pre-wrap', marginBottom: result.steps?.length ? 16 : 0, color: 'var(--text-1)' }}>
                {result.result}
              </div>
              {result.steps?.length > 0 && (
                <div>
                  <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 }}>
                    Pasos ejecutados ({result.steps.length})
                  </div>
                  {result.steps.map((s, i) => <StepBadge key={i} step={s} />)}
                </div>
              )}
            </div>
          )}

          {/* History */}
          <div style={card}>
            <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--surface-4)', fontSize: "var(--text-md)", fontWeight: 700 }}>
              Historial de ejecuciones
            </div>
            {history.length === 0 ? (
              <div style={{ padding: 32 }}>
                <EmptyState icon="⚡" title="Sin ejecuciones recientes" description="Ejecuta una instruccion para ver el historial" />
              </div>
            ) : history.map(e => {
              const sc = STATUS_CFG[e.status] || STATUS_CFG.pending
              return (
                <button key={e.id} type="button" onClick={() => setResult(e)}
                  style={{ padding: '14px 20px', borderBottom: '1px solid var(--surface-4)30', cursor: 'pointer', transition: 'background 0.15s' }}
                  onMouseEnter={ev => ev.currentTarget.style.background = 'var(--surface-3)'}
                  onMouseLeave={ev => ev.currentTarget.style.background = 'transparent'}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: "var(--text-base)", fontWeight: 600, marginBottom: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {e.instruction}
                      </div>
                      <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {e.result?.slice(0, 100)}
                      </div>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4, flexShrink: 0 }}>
                      <span style={{ fontSize: "var(--text-xs)", padding: '2px 8px', borderRadius: 12, background: sc.bg, color: sc.color, fontWeight: 600 }}>{sc.label}</span>
                      <span style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)' }}>{e.created_at?.slice(0, 16)?.replace('T', ' ')}</span>
                    </div>
                  </div>
                </button>
              )
            })}
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
                style={{ width: '100%', display: 'flex', gap: 8, padding: '8px 0', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit', borderBottom: i < EXAMPLES.length - 1 ? '1px solid var(--surface-4)30' : 'none', textAlign: 'left' }}>
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
              <div key={t.name} style={{ display: 'flex', gap: 8, padding: '6px 0', borderBottom: '1px solid var(--surface-4)20', alignItems: 'center' }}>
                <span style={{ fontSize: "var(--text-md)" }}>{t.icon}</span>
                <div>
                  <div style={{ fontSize: "var(--text-xs)", fontWeight: 600, color: 'var(--text-1)', fontFamily: 'var(--font-mono)' }}>{t.name}</div>
                  <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-2)' }}>{t.desc}</div>
                </div>
              </div>
            ))}
            {!showTools && TOOLS.length > 5 && (
              <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', marginTop: 6 }}>+{TOOLS.length - 5} más...</div>
            )}
          </div>
        </div>
      </div>
    </PageShell>
  )
}
