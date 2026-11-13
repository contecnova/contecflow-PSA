/**
 * WorkflowDesignerPage — diseñador visual de workflows para Service Desk.
 *
 * Reescrito sobre ReactFlow (`@xyflow/react`):
 *   • Lista de blueprints: búsqueda + filtro por process_type + clonar/archivar.
 *   • Catálogo de plantillas (incident triage, change approval, vacaciones).
 *   • Editor con paleta extensible (start/end/state/decision/approval/wait/notify/
 *     http_call/create_ticket), panel de propiedades, mini-map, snap-to-grid,
 *     validación en vivo (errors/warnings) y autosave manual.
 *   • Versiones: guardar, publicar, indicador del último publicado.
 *
 * URL state: `/sd/workflow-designer?id=<blueprint_id>` selecciona el editor.
 */
import { useCallback, useEffect, useMemo, useState, useId } from 'react'
import type { CSSProperties } from 'react'
import type { AxiosError } from 'axios'
import { useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ReactFlow, ReactFlowProvider, addEdge, useNodesState, useEdgesState,
  Background, Controls, MiniMap, MarkerType, Handle, Position, useReactFlow,
} from '@xyflow/react'
import type { Connection, Edge, Node, NodeProps, XYPosition } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import {
  GitBranch, Plus, Search, Trash2, Copy, ArrowLeft, Save, CheckCircle,
  AlertTriangle, Sparkles, X, Layers, Clock, Bell, Globe, Ticket,
  Play, XCircle, Activity,
} from 'lucide-react'
import { sdWorkflowDesignerApi, type ApiError } from '../../services/api'
import { useToast } from '../../context/ToastContext'
import { Button, Spinner, Page, StatusBadge, Modal, EmptyState } from '../../components/ui'
import { useAppLang } from '../../i18n/AppLangContext'
import { localeActivo } from '../../utils/helpers'

// ── Catálogo visual de los nodos (color + icono por tipo) ────────────────────
const NODE_VISUAL: Record<string, { color: string; icon: string; label: string }> = {
  start:         { color: 'var(--success)', icon: '▶', label: 'Inicio' },
  end:           { color: 'var(--danger)', icon: '■', label: 'Fin' },
  state:         { color: 'var(--accent)', icon: '●', label: 'Estado' },
  decision:      { color: 'var(--warning)', icon: '◆', label: 'Decisión' },
  approval:      { color: 'var(--purple)', icon: '✓', label: 'Aprobación' },
  wait:          { color: 'var(--text-3)', icon: '⏱', label: 'Espera' },
  notify:        { color: 'var(--chart-teal)', icon: '🔔', label: 'Notificar' },
  http_call:     { color: 'var(--chart-pink)', icon: '🌐', label: 'HTTP' },
  create_ticket: { color: 'var(--sky-blue)', icon: '🎫', label: 'Ticket' },
}

// ── Tipos (app/services/service_desk/workflow_designer_service.py y workflow_engine.py) ──
type ValorConfig = string | number | null | undefined
type ConfigNodo = Record<string, ValorConfig>
type DatosNodo = { label?: string; type: string; config?: ConfigNodo }
type NodoFlujo = Node<DatosNodo>
type AristaFlujo = Edge<{ branch?: string }>

/** Nodo y arista tal como se guardan en `graph_json`. */
interface NodoGuardado { id: string; type: string; position?: XYPosition; data?: DatosNodo; label?: string; config?: ConfigNodo }
interface AristaGuardada { id: string; source: string; target: string; branch?: string; label?: string }
interface GrafoGuardado { nodes?: NodoGuardado[]; edges?: AristaGuardada[] }

/** `serialize_blueprint`. */
interface Blueprint {
  id: string
  name: string
  description: string | null
  process_type: string
  scope: string | null
  status: string
  latest_version: number
  published_version: number | null
  is_active: boolean
  created_at: string
  updated_at: string | null
}
/** `serialize_version`. */
interface VersionBlueprint {
  id: string
  blueprint_id: string
  version: number
  graph: GrafoGuardado
  is_published: boolean
  published_at: string | null
  created_at: string
}
interface DetalleBlueprint { blueprint: Blueprint; versions: VersionBlueprint[] }
/** `builtin_templates`. */
interface PlantillaFlujo { id: string; name: string; description: string; process_type: string; graph: GrafoGuardado }
/** `workflow_engine.serialize_run`. */
interface EjecucionFlujo {
  id: string
  blueprint_id: string
  blueprint_version: number
  target_entity_type: string | null
  target_entity_id: string | null
  status: string
  current_node_id: string | null
  wake_at: string | null
  last_error: string | null
  context: Record<string, unknown>
  created_by_user_id: string | null
  started_at: string | null
  completed_at: string | null
}
/** `workflow_engine.serialize_step`. */
interface PasoFlujo {
  id: string
  node_id: string
  node_type: string
  status: string
  branch_taken: string | null
  payload: Record<string, unknown>
  error: string | null
  created_at: string | null
  completed_at: string | null
}
interface DetalleEjecucion { run: EjecucionFlujo; steps: PasoFlujo[] }
/** `validate_graph`. */
interface ValidacionGrafo { valid: boolean; errors?: string[]; warnings?: string[] }

/** `detail` de un error del diseñador: texto, o `{message, errors}` si el grafo no valida. */
type DetalleError = string | { message?: string; errors?: string[] }
type ErrorDeFlujo = AxiosError<{ detail?: DetalleError }>
const mensajeDelDetalle = (d: DetalleError | undefined) => (typeof d === 'object' ? d?.message : undefined)

const PROCESS_LABEL: Record<string, string> = { ticket: 'Ticket', change: 'Cambio', approval: 'Aprobación' }

// Estilos compartidos
const inputStyle: CSSProperties = {
  width: '100%', boxSizing: 'border-box',
  background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
  borderRadius: 8, padding: '8px 10px',
  color: 'var(--text-1)', fontSize: 'var(--text-sm)',
  outline: 'none', fontFamily: 'inherit',
}
const labelStyle: CSSProperties = {
  fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--text-2)',
  textTransform: 'uppercase', letterSpacing: '0.06em',
  display: 'block', marginBottom: 4,
}

// ── Custom node para ReactFlow ───────────────────────────────────────────────
function WorkflowNode({ data, selected }: NodeProps<NodoFlujo>) {
  const v = NODE_VISUAL[data.type] || NODE_VISUAL.state
  const showInput = data.type !== 'start'
  const showOutput = data.type !== 'end'
  return (
    <div style={{
      background: 'var(--surface-2)', border: `2px solid ${selected ? 'var(--accent)' : v.color}`,
      borderRadius: 'var(--radius-md)', padding: '8px 12px', minWidth: 140, maxWidth: 220,
      boxShadow: selected ? '0 0 0 3px rgba(59,130,246,0.18)' : '0 2px 6px rgba(0,0,0,0.18)',
      color: 'var(--text-1)', fontSize: 'var(--text-sm)', cursor: 'grab',
    }}>
      {showInput && <Handle type="target" position={Position.Left} style={{ background: v.color, width: 8, height: 8 }} />}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
        <span style={{ color: v.color, fontSize: 14, lineHeight: 1 }}>{v.icon}</span>
        <span style={{ fontSize: 9, fontWeight: 700, color: v.color, textTransform: 'uppercase', letterSpacing: 0.5 }}>{v.label}</span>
      </div>
      <div style={{ fontWeight: 600, lineHeight: 1.3, wordBreak: 'break-word' }}>
        {data.label || '(sin nombre)'}
      </div>
      {showOutput && <Handle type="source" position={Position.Right} style={{ background: v.color, width: 8, height: 8 }} />}
    </div>
  )
}
const nodeTypes = { wf: WorkflowNode }

// ── Top-level page ───────────────────────────────────────────────────────────
export default function WorkflowDesignerPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const activeId = searchParams.get('id')

  return (
    <Page
      icon={<GitBranch size={20} />}
      title="Workflow Designer"
      subtitle="Diseña procesos visuales reutilizables (tickets, cambios, aprobaciones)"
    >
      {activeId
        ? <BlueprintEditor id={activeId} onBack={() => setSearchParams({})} />
        : <BlueprintList onOpen={(id: string) => setSearchParams({ id })} />}
    </Page>
  )
}

// ── Listado de blueprints ────────────────────────────────────────────────────
function BlueprintList({ onOpen }: { onOpen: (id: string) => void }) {
  const { t: traducir } = useAppLang()
  const qc = useQueryClient()
  const toast = useToast()
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [showTemplates, setShowTemplates] = useState(false)
  const [cloneTarget, setCloneTarget] = useState<{ id: string; name: string } | null>(null)
  const [archiveTarget, setArchiveTarget] = useState<{ id: string; name: string } | null>(null)

  const { data: blueprints = [], isLoading } = useQuery({
    queryKey: ['sd-wf-blueprints', filter],
    queryFn: () => sdWorkflowDesignerApi.blueprints(filter ? { process_type: filter } : undefined).then((r): Blueprint[] => r.data),
  })

  const archive = useMutation({
    mutationFn: (id: string) => sdWorkflowDesignerApi.archive(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sd-wf-blueprints'] })
      toast.success('Blueprint archivado')
    },
    onError: (e: ApiError) => toast.error(e?.response?.data?.detail || 'Error al archivar'),
  })

  const clone = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) => sdWorkflowDesignerApi.clone(id, { name }),
    onSuccess: r => {
      qc.invalidateQueries({ queryKey: ['sd-wf-blueprints'] })
      toast.success('Blueprint clonado')
      onOpen(r.data.id)
    },
    onError: (e: ApiError) => toast.error(e?.response?.data?.detail || 'Error al clonar'),
  })

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return blueprints
    return blueprints.filter(b =>
      (b.name || '').toLowerCase().includes(q) ||
      (b.description || '').toLowerCase().includes(q),
    )
  }, [blueprints, search])

  return (
    <>
      {/* Toolbar */}
      <div className="ds-toolbar">
        <div style={{ position: 'relative', flex: '1 1 280px', maxWidth: 360 }}>
          <Search size={14} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-3)' }} />
          <input aria-label="Buscar blueprints…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Buscar blueprints…"
            className="ds-input"
            style={{ paddingLeft: 32 }}
          />
        </div>
        <select value={filter} onChange={e => setFilter(e.target.value)}
          className="ds-input" style={{ width: 'auto', minWidth: 160 }}>
          <option value="">{traducir('workflowdesigner.todos_los_procesos')}</option>
          <option value="ticket">Ticket</option>
          <option value="change">Cambio</option>
          <option value="approval">{traducir('workflowdesigner.aprobacion')}</option>
        </select>
        <div className="ds-toolbar__spacer" />
        <Button variant="secondary" onClick={() => setShowTemplates(true)}>
          <Sparkles size={14} /> Plantilla
        </Button>
        <Button onClick={() => setShowCreate(true)}>
          <Plus size={14} /> {traducir('workflowdesigner.nuevo_blueprint')}
        </Button>
      </div>

      {/* Grid */}
      {isLoading ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: 60 }}><Spinner /></div>
      ) : filtered.length === 0 ? (
        <EmptyState svgIcon={<GitBranch size={36} />}
          title={search || filter ? 'No hay blueprints que coincidan' : 'Aún no hay blueprints'}
          description={search || filter ? 'Prueba con otros términos.' : 'Crea uno desde cero o parte de una plantilla.'} />
      ) : (
        <div className="ds-grid-cards">
          {filtered.map(bp => (
            <BlueprintCard key={bp.id} bp={bp}
              onOpen={() => onOpen(bp.id)}
              onClone={() => setCloneTarget({ id: bp.id, name: bp.name })}
              onArchive={() => setArchiveTarget({ id: bp.id, name: bp.name })}
            />
          ))}
        </div>
      )}

      {showCreate && (
        <CreateBlueprintModal
          onClose={() => setShowCreate(false)}
          onCreated={bp => { setShowCreate(false); onOpen(bp.id) }}
        />
      )}
      {showTemplates && (
        <TemplatePickerModal
          onClose={() => setShowTemplates(false)}
          onPicked={bp => { setShowTemplates(false); onOpen(bp.id) }}
        />
      )}
      {cloneTarget && (
        <CloneBlueprintModal
          bp={cloneTarget}
          onClose={() => setCloneTarget(null)}
          onConfirm={(name: string) => { setCloneTarget(null); clone.mutate({ id: cloneTarget.id, name }) }}
        />
      )}
      {archiveTarget && (
        <ConfirmModal
          title="Archivar blueprint"
          message={`¿Archivar "${archiveTarget.name}"? Podrás recuperarlo activando "Mostrar archivados".`}
          confirmLabel="Archivar"
          onClose={() => setArchiveTarget(null)}
          onConfirm={() => { setArchiveTarget(null); archive.mutate(archiveTarget.id) }}
        />
      )}
    </>
  )
}

function BlueprintCard({ bp, onOpen, onClone, onArchive }: { bp: Blueprint; onOpen: () => void; onClone: () => void; onArchive: () => void }) {
  const statusKind = bp.status === 'published' ? 'success'
                    : bp.status === 'draft' ? 'warning' : 'neutral'
  const statusLabel = bp.status === 'published' ? 'Publicado'
                     : bp.status === 'draft' ? 'Borrador' : 'Archivado'
  return (
    <div role="button" tabIndex={0}
      className="ds-card ds-card--clickable"
      onClick={onOpen}
      onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onOpen() } }}
    >
      <div className="ds-row-between" style={{ alignItems: 'flex-start' }}>
        <div className="u-min0">
          <div style={{ fontWeight: 700, color: 'var(--text-1)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{bp.name}</div>
          {bp.description && (
            <div className="ds-muted" style={{ marginTop: 2,
              display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
              {bp.description}
            </div>
          )}
        </div>
        <StatusBadge kind={statusKind}>{statusLabel}</StatusBadge>
      </div>
      <div className="ds-row u-text2-xs">
        <span style={{ background: 'var(--surface-3)', padding: '2px 6px', borderRadius: 'var(--radius-sm)' }}>
          {PROCESS_LABEL[bp.process_type] || bp.process_type}
        </span>
        <span>v{bp.latest_version}</span>
        {bp.published_version && <span className="u-success">· publicada v{bp.published_version}</span>}
      </div>
      <div className="ds-row"
        role="presentation"
        onClick={e => e.stopPropagation()}
        onKeyDown={e => e.stopPropagation()}>
        <Button size="sm" variant="secondary" onClick={onClone}><Copy size={12} /> Clonar</Button>
        <Button size="sm" variant="secondary" onClick={onArchive}><Trash2 size={12} /> Archivar</Button>
      </div>
    </div>
  )
}

function CloneBlueprintModal({ bp, onClose, onConfirm }: { bp: { name: string }; onClose: () => void; onConfirm: (name: string) => void }) {
  const idCampo = useId()
  const { t: traducir } = useAppLang()
  const [name, setName] = useState(`${bp.name} (copia)`)
  return (
    <Modal open width={480} title="Clonar blueprint" onClose={onClose}>
      <div className="u-stack-12">
        <div>
          <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={labelStyle}>{traducir('workflowdesigner.nombre_de_la_copia')}</label>
          <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} autoFocus value={name} onChange={e => setName(e.target.value)} style={inputStyle} />
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 8 }}>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={() => onConfirm(name.trim())} disabled={!name.trim()}>Clonar</Button>
        </div>
      </div>
    </Modal>
  )
}

function ConfirmModal({ title, message, confirmLabel = 'Confirmar', onClose, onConfirm }: { title: string; message: string; confirmLabel?: string; onClose: () => void; onConfirm: () => void }) {
  return (
    <Modal open width={480} title={title} onClose={onClose}>
      <div className="u-stack-16">
        <p style={{ color: 'var(--text-1)', margin: 0 }}>{message}</p>
        <div className="u-actions-8">
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={onConfirm}>{confirmLabel}</Button>
        </div>
      </div>
    </Modal>
  )
}

function CreateBlueprintModal({ onClose, onCreated }: { onClose: () => void; onCreated?: (bp: Blueprint) => void }) {
  const idCampo = useId()
  const { t: traducir } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const [name, setName] = useState('')
  const [processType, setProcessType] = useState('ticket')
  const [description, setDescription] = useState('')
  const create = useMutation({
    mutationFn: () => sdWorkflowDesignerApi.createBlueprint({
      name, process_type: processType, description: description || null,
      graph: {
        nodes: [
          { id: 'start_1', type: 'start', position: { x: 100, y: 200 }, data: { label: 'Inicio' } },
          { id: 'end_1', type: 'end', position: { x: 500, y: 200 }, data: { label: 'Fin' } },
        ],
        edges: [{ id: 'e1', source: 'start_1', target: 'end_1', branch: 'next' }],
      },
    }),
    onSuccess: r => {
      qc.invalidateQueries({ queryKey: ['sd-wf-blueprints'] })
      toast.success('Blueprint creado')
      onCreated?.(r.data)
    },
    onError: (e: ErrorDeFlujo) => toast.error(mensajeDelDetalle(e?.response?.data?.detail) || e?.response?.data?.detail || 'Error'),
  })

  return (
    <Modal open width={480} title={traducir('workflowdesigner.nuevo_blueprint')} onClose={onClose}>
      <div className="u-stack-12">
        <div>
          <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={labelStyle}>Nombre</label>
          <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} autoFocus value={name} onChange={e => setName(e.target.value)} style={inputStyle} placeholder={traducir('workflowdesigner.p_ej_triaje_de_incidentes')} />
        </div>
        <div>
          <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} style={labelStyle}>{traducir('workflowdesigner.tipo_de_proceso')}</label>
          <select id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={processType} onChange={e => setProcessType(e.target.value)} style={inputStyle}>
            <option value="ticket">Ticket</option>
            <option value="change">Cambio</option>
            <option value="approval">{traducir('workflowdesigner.aprobacion')}</option>
          </select>
        </div>
        <div>
          <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} style={labelStyle}>{traducir('workflowdesigner.descripcion_opcional')}</label>
          <textarea id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} rows={3} value={description} onChange={e => setDescription(e.target.value)} style={{ ...inputStyle, resize: 'vertical' }} />
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 8 }}>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={() => create.mutate()} disabled={!name.trim() || create.isPending}>
            {create.isPending ? <Spinner /> : 'Crear y abrir'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

function TemplatePickerModal({ onClose, onPicked }: { onClose: () => void; onPicked?: (bp: Blueprint) => void }) {
  const toast = useToast()
  const qc = useQueryClient()
  const { data: templates = [], isLoading } = useQuery({
    queryKey: ['sd-wf-templates'],
    queryFn: () => sdWorkflowDesignerApi.templates().then((r): PlantillaFlujo[] => r.data),
  })

  const useTemplate = useMutation({
    mutationFn: (tpl: PlantillaFlujo) => sdWorkflowDesignerApi.createBlueprint({
      name: tpl.name, process_type: tpl.process_type, description: tpl.description,
      graph: tpl.graph,
    }),
    onSuccess: r => {
      qc.invalidateQueries({ queryKey: ['sd-wf-blueprints'] })
      toast.success('Blueprint creado desde plantilla')
      onPicked?.(r.data)
    },
    onError: (e: ErrorDeFlujo) => toast.error(mensajeDelDetalle(e?.response?.data?.detail) || 'Error al crear'),
  })

  return (
    <Modal open title="Elegir plantilla" onClose={onClose} width={620}>
      {isLoading ? <Spinner /> : (
        <div className="u-stack-8">
          {templates.map(tpl => (
            <button key={tpl.id} onClick={() => useTemplate.mutate(tpl)}
              style={{
                textAlign: 'left', cursor: 'pointer',
                background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8,
                padding: 14, color: 'var(--text-1)',
              }}
              onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--accent)' }}
              onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--surface-4)' }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 2 }}>
                <span style={{ fontWeight: 700 }}>{tpl.name}</span>
                <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', background: 'var(--surface-2)', padding: '1px 6px', borderRadius: 4 }}>
                  {PROCESS_LABEL[tpl.process_type] || tpl.process_type}
                </span>
              </div>
              <div className="u-text2-xs">{tpl.description}</div>
              <div className="u-hint">
                {tpl.graph.nodes.length} nodos · {tpl.graph.edges.length} aristas
              </div>
            </button>
          ))}
        </div>
      )}
    </Modal>
  )
}

// ── Editor ──────────────────────────────────────────────────────────────────
function BlueprintEditor({ id, onBack }: { id: string; onBack: () => void }) {
  return (
    <ReactFlowProvider>
      <BlueprintEditorInner id={id} onBack={onBack} />
    </ReactFlowProvider>
  )
}

function BlueprintEditorInner({ id, onBack }: { id: string; onBack: () => void }) {
  const qc = useQueryClient()
  const toast = useToast()
  const { fitView } = useReactFlow()
  const [tab, setTab] = useState('editor')   // editor | runs
  const [showRunModal, setShowRunModal] = useState(false)

  const { data: detail, isLoading } = useQuery({
    queryKey: ['sd-wf-blueprint', id],
    queryFn: () => sdWorkflowDesignerApi.blueprint(id).then((r): DetalleBlueprint => r.data),
  })

  const blueprint = detail?.blueprint
  const versions = detail?.versions || []
  const head = versions[0]  // Order by version desc en backend

  const [nodes, setNodes, onNodesChange] = useNodesState<NodoFlujo>([])
  const [edges, setEdges, onEdgesChange] = useEdgesState<AristaFlujo>([])
  const [selected, setSelected] = useState<NodoFlujo | null>(null)
  const [validation, setValidation] = useState<ValidacionGrafo | null>(null)

  // Carga inicial
  useEffect(() => {
    if (!head) return
    const g: GrafoGuardado = head.graph || {}
    const n = (g.nodes || []).map((node): NodoFlujo => ({
      ...node,
      type: 'wf',
      position: node.position || { x: 100, y: 100 },
      data: node.data || { label: node.label || node.type, type: node.type, config: node.config || {} },
    }))
    // Aseguramos que data.type siga existiendo (es el tipo lógico)
    n.forEach(nn => {
      if (!nn.data.type) nn.data.type = (g.nodes || []).find(o => o.id === nn.id)?.type || 'state'
    })
    const e = (g.edges || []).map((edge): AristaFlujo => ({
      ...edge,
      type: 'smoothstep',
      animated: true,
      label: edge.branch || edge.label || '',
      markerEnd: { type: MarkerType.ArrowClosed, color: 'var(--accent)' },
      style: { stroke: 'var(--accent)' },
    }))
    setNodes(n)
    setEdges(e)
    setTimeout(() => fitView({ padding: 0.25, duration: 200 }), 100)
  }, [head, setNodes, setEdges, fitView])

  // Validación en vivo (debounced)
  useEffect(() => {
    const t = setTimeout(async () => {
      const graph = serializeGraph(nodes, edges)
      try {
        const r = await sdWorkflowDesignerApi.validate(graph)
        setValidation(r.data)
      } catch { /* noop */ }
    }, 600)
    return () => clearTimeout(t)
  }, [nodes, edges])

  const onConnect = useCallback((params: Connection) => {
    const sourceNode = nodes.find(n => n.id === params.source)
    const branch = sourceNode?.data?.type === 'decision' ? 'true'
      : sourceNode?.data?.type === 'approval' ? 'approved'
      : sourceNode?.data?.type === 'http_call' ? 'success'
      : 'next'
    setEdges(eds => addEdge({
      ...params, type: 'smoothstep', animated: true, label: branch,
      data: { branch },
      markerEnd: { type: MarkerType.ArrowClosed, color: 'var(--accent)' },
      style: { stroke: 'var(--accent)' },
    }, eds))
  }, [nodes, setEdges])

  const addNode = (type: string) => {
    const id = `${type}_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`
    const v = NODE_VISUAL[type]
    setNodes(n => [...n, {
      id, type: 'wf',
      position: { x: 200 + Math.random() * 200, y: 200 + Math.random() * 80 },
      data: { label: v.label, type, config: {} },
    }])
  }

  const updateSelectedNode = (patch: Partial<DatosNodo>) => {
    if (!selected) return
    setNodes(ns => ns.map(n => n.id === selected.id ? { ...n, data: { ...n.data, ...patch } } : n))
    setSelected(s => s ? { ...s, data: { ...s.data, ...patch } } : s)
  }

  const deleteSelected = () => {
    if (!selected) return
    setNodes(ns => ns.filter(n => n.id !== selected.id))
    setEdges(es => es.filter(e => e.source !== selected.id && e.target !== selected.id))
    setSelected(null)
  }

  const save = useMutation({
    mutationFn: () => sdWorkflowDesignerApi.createVersion(id, { graph: serializeGraph(nodes, edges) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sd-wf-blueprint', id] })
      qc.invalidateQueries({ queryKey: ['sd-wf-blueprints'] })
      toast.success('Versión guardada')
    },
    onError: (e: ErrorDeFlujo) => {
      const detail = e?.response?.data?.detail
      const obj = typeof detail === 'object' ? detail : undefined
      const msg = obj?.errors?.length ? obj.errors.join(' · ') : (obj?.message || detail || 'Error al guardar')
      toast.error(msg)
    },
  })

  const publishLatest = useMutation({
    mutationFn: () => sdWorkflowDesignerApi.publish(id, blueprint.latest_version),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sd-wf-blueprint', id] })
      qc.invalidateQueries({ queryKey: ['sd-wf-blueprints'] })
      toast.success(`Publicada v${blueprint.latest_version}`)
    },
    onError: () => toast.error('Error al publicar'),
  })

  if (isLoading || !blueprint) return <div style={{ padding: 60, textAlign: 'center' }}><Spinner /></div>

  const isPublished = !!blueprint.published_version

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, height: 'calc(100vh - 180px)', minHeight: 540 }}>
      {/* Toolbar */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <Button variant="secondary" onClick={onBack}><ArrowLeft size={14} /> Volver</Button>
        <div className="u-min0">
          <div style={{ fontSize: 'var(--text-md)', fontWeight: 700, color: 'var(--text-1)' }}>{blueprint.name}</div>
          <div className="u-text3-xs">
            {PROCESS_LABEL[blueprint.process_type]} · v{blueprint.latest_version}
            {blueprint.published_version && ` · publicada v${blueprint.published_version}`}
          </div>
        </div>
        {/* Tabs */}
        <div style={{ display: 'inline-flex', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: 2 }}>
          {['editor', 'runs'].map(t => (
            <button key={t} onClick={() => setTab(t)}
              style={{
                background: tab === t ? 'var(--accent)' : 'transparent',
                color: tab === t ? 'var(--on-accent-light)' : 'var(--text-2)',
                border: 'none', padding: '6px 14px', borderRadius: 'var(--radius-sm)',
                cursor: 'pointer', fontSize: 'var(--text-xs)', fontWeight: 600,
                display: 'inline-flex', alignItems: 'center', gap: 4,
              }}>
              {t === 'editor' ? <Layers size={12} /> : <Activity size={12} />}
              {t === 'editor' ? 'Editor' : 'Ejecuciones'}
            </button>
          ))}
        </div>
        <div className="u-flex1" />
        {tab === 'editor' && <ValidationBadge validation={validation} />}
        {tab === 'editor' && (
          <Button variant="secondary" onClick={() => save.mutate()} disabled={save.isPending || !validation?.valid}>
            <Save size={14} /> {save.isPending ? 'Guardando…' : 'Guardar versión'}
          </Button>
        )}
        {tab === 'editor' && (
          <Button onClick={() => publishLatest.mutate()} disabled={publishLatest.isPending || !validation?.valid}>
            <CheckCircle size={14} /> Publicar v{blueprint.latest_version}
          </Button>
        )}
        {tab === 'runs' && (
          <Button onClick={() => setShowRunModal(true)} disabled={!isPublished}
            title={isPublished ? 'Iniciar nueva ejecución' : 'Publica una versión para poder ejecutar'}>
            <Play size={14} /> Ejecutar
          </Button>
        )}
      </div>
      {showRunModal && (
        <StartRunModal blueprint={blueprint} onClose={() => setShowRunModal(false)}
          onStarted={() => { setShowRunModal(false); qc.invalidateQueries({ queryKey: ['sd-wf-runs', id] }) }} />
      )}

      {tab === 'runs' ? (
        <RunsTab blueprintId={id} />
      ) : (
      /* Layout: paleta · canvas · propiedades */
      <div style={{
        flex: 1, minHeight: 0, display: 'grid',
        gridTemplateColumns: '180px 1fr 280px', gap: 12,
      }}>
        <Palette onAdd={addNode} />
        <div style={{
          position: 'relative',
          background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12,
          overflow: 'hidden',
        }}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            nodeTypes={nodeTypes}
            onSelectionChange={({ nodes: sel }) => setSelected(sel?.[0] || null)}
            onNodeClick={(_, n) => setSelected(n)}
            onPaneClick={() => setSelected(null)}
            deleteKeyCode={['Delete', 'Backspace']}
            snapToGrid
            snapGrid={[16, 16]}
            fitView
            proOptions={{ hideAttribution: true }}
          >
            <Background gap={16} color="var(--surface-4)" />
            <Controls showInteractive={false} />
            <MiniMap<NodoFlujo> pannable zoomable
              nodeColor={n => NODE_VISUAL[n.data?.type]?.color || 'var(--text-3)'}
              maskColor="rgba(0,0,0,0.45)" />
          </ReactFlow>
          {validation && (validation.errors?.length || validation.warnings?.length) ? (
            <ValidationBanner validation={validation} />
          ) : null}
        </div>
        <PropertiesPanel
          node={selected}
          onChange={updateSelectedNode}
          onDelete={deleteSelected}
        />
      </div>
      )}
    </div>
  )
}

// ── Runs tab ────────────────────────────────────────────────────────────────
function RunsTab({ blueprintId }: { blueprintId: string }) {
  const { t: traducir } = useAppLang()
  const qc = useQueryClient()
  const toast = useToast()
  const [activeRunId, setActiveRunId] = useState<string | null>(null)

  const { data: runs = [], isLoading } = useQuery({
    queryKey: ['sd-wf-runs', blueprintId],
    queryFn: () => sdWorkflowDesignerApi.runs({ blueprint_id: blueprintId }).then((r): EjecucionFlujo[] => r.data),
    refetchInterval: 8_000,
  })
  const { data: runDetail } = useQuery({
    queryKey: ['sd-wf-run', activeRunId],
    queryFn: () => sdWorkflowDesignerApi.run(activeRunId).then((r): DetalleEjecucion => r.data),
    enabled: !!activeRunId,
    refetchInterval: 4_000,
  })

  const resume = useMutation({
    mutationFn: ({ runId, branch }: { runId: string; branch: string }) => sdWorkflowDesignerApi.resumeRun(runId, { branch }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sd-wf-runs', blueprintId] })
      qc.invalidateQueries({ queryKey: ['sd-wf-run', activeRunId] })
      toast.success('Ejecución reanudada')
    },
    onError: (e: ApiError) => toast.error(e?.response?.data?.detail || 'Error al reanudar'),
  })
  const cancel = useMutation({
    mutationFn: (runId: string) => sdWorkflowDesignerApi.cancelRun(runId, 'cancelled by user'),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sd-wf-runs', blueprintId] })
      qc.invalidateQueries({ queryKey: ['sd-wf-run', activeRunId] })
      toast.success('Ejecución cancelada')
    },
  })

  const fmtDate = (iso: string | null) => iso ? new Date(iso).toLocaleString(localeActivo()) : ''
  const statusColor = (s: string): string => (({
    running: 'var(--accent)', waiting: 'var(--warning)', completed: 'var(--success)',
    cancelled: 'var(--text-3)', error: 'var(--danger)',
  } as Record<string, string>)[s] || 'var(--text-3)')

  return (
    <div style={{ flex: 1, minHeight: 0, display: 'grid', gridTemplateColumns: '1fr 380px', gap: 12 }}>
      <div style={{
        background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12,
        overflowY: 'auto',
      }}>
        {isLoading ? (
          <div style={{ padding: 60, textAlign: 'center' }}><Spinner /></div>
        ) : runs.length === 0 ? (
          <div style={{ padding: 60, textAlign: 'center', color: 'var(--text-3)' }}>
            <Activity size={32} style={{ marginBottom: 8 }} />
            <div className="u-600">{traducir('workflowdesigner.aun_no_hay_ejecuciones')}</div>
            <div className="u-sm">
              {traducir('workflowdesigner.pulsa_ejecutar_para_iniciar_una_nueva')}
            </div>
          </div>
        ) : (
          <table className="u-table-sm">
            <thead style={{ position: 'sticky', top: 0, background: 'var(--surface-2)', zIndex: 1 }}>
              <tr style={{ textAlign: 'left', color: 'var(--text-3)', fontSize: 'var(--text-xs)' }}>
                <th style={{ padding: '10px 12px', borderBottom: '1px solid var(--surface-4)', fontWeight: 600 }}>Estado</th>
                <th style={{ padding: '10px 12px', borderBottom: '1px solid var(--surface-4)', fontWeight: 600 }}>Nodo actual</th>
                <th style={{ padding: '10px 12px', borderBottom: '1px solid var(--surface-4)', fontWeight: 600 }}>Entidad</th>
                <th style={{ padding: '10px 12px', borderBottom: '1px solid var(--surface-4)', fontWeight: 600 }}>Iniciado</th>
                <th style={{ padding: '10px 12px', borderBottom: '1px solid var(--surface-4)', fontWeight: 600 }}>v</th>
              </tr>
            </thead>
            <tbody>
              {runs.map(r => (
                <tr key={r.id} onClick={() => setActiveRunId(r.id)}
                  style={{
                    cursor: 'pointer',
                    background: r.id === activeRunId ? 'var(--accent-muted)' : 'transparent',
                    borderBottom: '1px solid var(--surface-4)',
                  }}>
                  <td style={{ padding: '8px 12px' }}>
                    <span style={{
                      display: 'inline-block', padding: '2px 8px', borderRadius: 12,
                      fontSize: 'var(--text-xs)', fontWeight: 600,
                      color: statusColor(r.status),
                      background: `color-mix(in srgb, ${statusColor(r.status)} 15%, transparent)`,
                    }}>{r.status}</span>
                  </td>
                  <td style={{ padding: '8px 12px', color: 'var(--text-2)' }}>{r.current_node_id || '—'}</td>
                  <td style={{ padding: '8px 12px', color: 'var(--text-2)' }}>
                    {r.target_entity_type ? `${r.target_entity_type} ${(r.target_entity_id || '').slice(0, 8)}` : 'manual'}
                  </td>
                  <td style={{ padding: '8px 12px', color: 'var(--text-3)', fontSize: 'var(--text-xs)' }}>{fmtDate(r.started_at)}</td>
                  <td style={{ padding: '8px 12px', color: 'var(--text-3)' }}>v{r.blueprint_version}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      {/* Detail panel */}
      <div style={{
        background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12,
        padding: 14, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 10,
      }}>
        {!activeRunId ? (
          <div className="u-text3-sm">
            {traducir('workflowdesigner.selecciona_una_ejecucion_para_ver_su_historial')}
          </div>
        ) : !runDetail ? (
          <Spinner />
        ) : (
          <>
            <div className="u-row-between">
              <div>
                <div style={{ fontWeight: 700 }}>{runDetail.run.id.slice(0, 8)}</div>
                <div className="u-text3-xs">
                  {runDetail.run.status} · v{runDetail.run.blueprint_version}
                </div>
              </div>
              {runDetail.run.status === 'running' || runDetail.run.status === 'waiting' ? (
                <Button size="sm" variant="secondary" onClick={() => cancel.mutate(runDetail.run.id)}>
                  <XCircle size={12} /> Cancelar
                </Button>
              ) : null}
            </div>

            {runDetail.run.last_error && (
              <div style={{ background: 'var(--danger-bg)', color: 'var(--danger)',
                border: '1px solid rgba(239,68,68,0.3)', borderRadius: 'var(--radius-sm)',
                padding: '6px 10px', fontSize: 'var(--text-xs)' }}>
                {runDetail.run.last_error}
              </div>
            )}

            {runDetail.run.status === 'waiting' && (
              <ResumeBranchPicker
                runDetail={runDetail}
                onResume={(branch: string) => resume.mutate({ runId: runDetail.run.id, branch })}
                pending={resume.isPending}
              />
            )}

            <div style={{ marginTop: 6 }}>
              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', textTransform: 'uppercase', fontWeight: 700, letterSpacing: '0.07em', marginBottom: 6 }}>
                Historial ({runDetail.steps.length})
              </div>
              {runDetail.steps.length === 0 ? (
                <div className="u-text3-xs">{traducir('workflowdesigner.sin_pasos_aun')}</div>
              ) : runDetail.steps.map((s, i) => (
                <div key={s.id} style={{
                  borderLeft: `2px solid ${NODE_VISUAL[s.node_type]?.color || 'var(--text-3)'}`,
                  paddingLeft: 10, marginBottom: 8,
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                    <span style={{ fontWeight: 600, fontSize: 'var(--text-sm)' }}>
                      {i + 1}. {NODE_VISUAL[s.node_type]?.label || s.node_type}
                    </span>
                    <span style={{ fontSize: 'var(--text-xs)', color: statusColor(s.status === 'done' ? 'completed' : s.status) }}>
                      {s.status}{s.branch_taken ? ` → ${s.branch_taken}` : ''}
                    </span>
                  </div>
                  <div className="u-text3-xs">{s.node_id}</div>
                  {s.error && <div style={{ color: 'var(--danger)', fontSize: 'var(--text-xs)' }}>{s.error}</div>}
                </div>
              ))}
            </div>

            {Object.keys(runDetail.run.context || {}).length > 0 && (
              <div>
                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', textTransform: 'uppercase', fontWeight: 700, letterSpacing: '0.07em', marginBottom: 4 }}>
                  Contexto
                </div>
                <pre style={{
                  margin: 0, background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
                  borderRadius: 'var(--radius-sm)', padding: 8, fontSize: 'var(--text-xs)', overflowX: 'auto',
                }}>{JSON.stringify(runDetail.run.context, null, 2)}</pre>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

function ResumeBranchPicker({ runDetail, onResume, pending }: { runDetail: DetalleEjecucion; onResume: (branch: string) => void; pending: boolean }) {
  const { t: traducir } = useAppLang()
  // Branch options según el tipo del nodo actual
  const nodeType = runDetail.steps?.find(s => s.status === 'waiting')?.node_type || 'approval'
  const branches: { b: string; label: string; color?: string }[] = ({
    approval: [{ b: 'approved', label: 'Aprobar', color: 'var(--success)' }, { b: 'rejected', label: 'Rechazar', color: 'var(--danger)' }],
    decision: [{ b: 'true', label: 'Verdadero' }, { b: 'false', label: 'Falso' }],
    wait: [{ b: 'next', label: 'Continuar' }],
    http_call: [{ b: 'success', label: 'Éxito' }, { b: 'failure', label: 'Fallo' }],
  } as Record<string, { b: string; label: string; color?: string }[]>)[nodeType] || [{ b: 'next', label: 'Continuar' }]

  return (
    <div style={{
      background: 'rgba(245,158,11,0.10)', border: '1px solid rgba(245,158,11,0.4)',
      borderRadius: 8, padding: 10,
    }}>
      <div style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--warning)', marginBottom: 6 }}>
        {traducir('workflowdesigner.esperando_intervencion')} {NODE_VISUAL[nodeType]?.label || nodeType}
      </div>
      <div className="u-wrap-6">
        {branches.map(({ b, label, color }) => (
          <button key={b} onClick={() => onResume(b)} disabled={pending}
            style={{
              cursor: 'pointer', border: 'none', borderRadius: 'var(--radius-sm)',
              background: color || 'var(--accent)', color: 'var(--on-accent-light)',
              padding: '6px 12px', fontSize: 'var(--text-xs)', fontWeight: 600,
              opacity: pending ? 0.6 : 1,
            }}>
            {label}
          </button>
        ))}
      </div>
    </div>
  )
}

function StartRunModal({ blueprint, onClose, onStarted }: { blueprint: Blueprint; onClose: () => void; onStarted?: () => void }) {
  const idCampo = useId()
  const { t: traducir } = useAppLang()
  const toast = useToast()
  const [contextJson, setContextJson] = useState('{\n  "priority": "P3"\n}')
  const [targetType, setTargetType] = useState(blueprint.process_type || 'manual')
  const [targetId, setTargetId] = useState('')
  const start = useMutation({
    mutationFn: () => {
      let ctx = {}
      try { ctx = contextJson.trim() ? JSON.parse(contextJson) : {} }
      catch { throw new Error('El contexto debe ser JSON válido') }
      return sdWorkflowDesignerApi.startRun(blueprint.id, {
        target_entity_type: targetType || null,
        target_entity_id: targetId || null,
        context: ctx,
      })
    },
    onSuccess: () => { toast.success('Ejecución iniciada'); onStarted?.() },
    onError: (e: ApiError) => toast.error(e?.response?.data?.detail || e?.message || 'Error'),
  })
  return (
    <Modal open title={traducir('workflowdesigner.iniciar_ejecucion')} onClose={onClose} width={520}>
      <div className="u-stack-12">
        <div className="u-row-10">
          <div className="u-flex1">
            <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={labelStyle}>{traducir('workflowdesigner.tipo_de_entidad')}</label>
            <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={targetType} onChange={e => setTargetType(e.target.value)} style={inputStyle} placeholder="ticket / change / manual" />
          </div>
          <div className="u-flex1">
            <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} style={labelStyle}>{traducir('workflowdesigner.id_de_entidad_opcional')}</label>
            <input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={targetId} onChange={e => setTargetId(e.target.value)} style={inputStyle} placeholder="123e4567-…" />
          </div>
        </div>
        <div>
          <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} style={labelStyle}>Contexto inicial (JSON)</label>
          <textarea id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={contextJson} onChange={e => setContextJson(e.target.value)} rows={6}
            style={{ ...inputStyle, fontFamily: 'monospace', fontSize: 'var(--text-xs)', resize: 'vertical' }} />
          <div className="u-hint">
            {traducir('workflowdesigner.las_decisiones_del_workflow_lo_evaluaran_p')} <code>priority == 'P1'</code>).
          </div>
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 4 }}>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={() => start.mutate()} disabled={start.isPending}>
            {start.isPending ? <Spinner /> : <><Play size={12} /> Ejecutar</>}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

// ── Sub-componentes del editor ───────────────────────────────────────────────
function Palette({ onAdd }: { onAdd: (type: string) => void }) {
  const items = [
    { type: 'start',         icon: <Sparkles size={14} /> },
    { type: 'state',         icon: <Layers size={14} /> },
    { type: 'decision',      icon: <GitBranch size={14} /> },
    { type: 'approval',      icon: <CheckCircle size={14} /> },
    { type: 'wait',          icon: <Clock size={14} /> },
    { type: 'notify',        icon: <Bell size={14} /> },
    { type: 'http_call',     icon: <Globe size={14} /> },
    { type: 'create_ticket', icon: <Ticket size={14} /> },
    { type: 'end',           icon: <X size={14} /> },
  ]
  return (
    <div style={{
      background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12,
      padding: 10, display: 'flex', flexDirection: 'column', gap: 6, overflowY: 'auto',
    }}>
      <div style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.07em', padding: '4px 6px' }}>
        Paleta
      </div>
      {items.map(it => {
        const v = NODE_VISUAL[it.type]
        return (
          <button key={it.type} onClick={() => onAdd(it.type)}
            style={{
              display: 'flex', alignItems: 'center', gap: 8,
              background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8,
              padding: '7px 10px', color: 'var(--text-1)', cursor: 'pointer',
              fontSize: 'var(--text-sm)', textAlign: 'left',
            }}
            onMouseEnter={e => { e.currentTarget.style.borderColor = v.color }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--surface-4)' }}
          >
            <span style={{ color: v.color, display: 'inline-flex' }}>{it.icon}</span>
            <span className="u-flex1">{v.label}</span>
          </button>
        )
      })}
    </div>
  )
}

// Los mismos que `workflow_triggers.DISPARADORES` y `TicketStatus` del servidor.
const DISPARADORES_DE_FLUJO = ['created', 'assigned', 'group_assigned', 'status_changed', 'priority_changed',
  'commented', 'sla_warning', 'sla_breached', 'ola_breached', 'uc_breached', 'escalated']
const ESTADOS_DE_TICKET = ['new', 'assigned', 'in_progress', 'pending_client', 'pending_third', 'resolved', 'closed', 'cancelled']

function PropertiesPanel({ node, onChange, onDelete }: { node: NodoFlujo | null; onChange: (patch: Partial<DatosNodo>) => void; onDelete: () => void }) {
  const idCampo = useId()
  const { t: traducir } = useAppLang()
  if (!node) {
    return (
      <div style={{
        background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12,
        padding: 14, color: 'var(--text-3)', fontSize: 'var(--text-sm)',
      }}>
        {traducir('workflowdesigner.selecciona_un_nodo_para_editar_sus_propiedades')}
      </div>
    )
  }
  const t = node.data.type
  const config = node.data.config || {}
  const setConfig = (k: string, v: ValorConfig) => onChange({ config: { ...config, [k]: v } })

  return (
    <div style={{
      background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12,
      padding: 14, display: 'flex', flexDirection: 'column', gap: 10, overflowY: 'auto',
    }}>
      <div className="u-row-between">
        <div style={{ fontWeight: 700, color: NODE_VISUAL[t]?.color }}>
          {NODE_VISUAL[t]?.label} <span className="u-text3-xs">· {node.id.slice(0, 10)}</span>
        </div>
        <button aria-label="Eliminar nodo (Backspace)" onClick={onDelete} title="Eliminar nodo (Backspace)"
          style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--danger)' }}>
          <Trash2 size={14} />
        </button>
      </div>
      <div>
        <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={labelStyle}>Etiqueta</label>
        <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={node.data.label || ''} onChange={e => onChange({ label: e.target.value })} style={inputStyle} />
      </div>

      {/* Campos por tipo */}
      {t === 'start' && <>
        <FieldSelect label={traducir('sd_cfg.wf_trigger')} value={config.trigger || ''} onChange={v => setConfig('trigger', v || null)} options={[
          { v: '', l: traducir('sd_cfg.wf_trigger_manual') },
          ...DISPARADORES_DE_FLUJO.map(d => ({ v: d, l: traducir(`sd_cfg.ev_${d}`) })),
        ]} />
        {config.trigger && <>
          <FieldText label={traducir('sd_cfg.wf_condition')} value={config.condition} onChange={v => setConfig('condition', v)} placeholder={traducir('sd_cfg.wf_condition_hint')} />
          <div className="u-text3-xs">{traducir('sd_cfg.wf_condition_help')}</div>
        </>}
      </>}
      {t === 'state' && <>
        <FieldSelect label="Status" value={config.status || ''} onChange={v => setConfig('status', v)} options={[
          { v: '', l: '—' },
          ...ESTADOS_DE_TICKET.map(e => ({ v: e, l: e.replace(/_/g, ' ') })),
        ]} />
        <FieldText label={traducir('workflowdesigner.asignar_al_rol')} value={config.assignee_role} onChange={v => setConfig('assignee_role', v)} placeholder="support_l1" />
        <FieldNumber label="SLA (horas)" value={config.sla_hours} onChange={v => setConfig('sla_hours', v)} />
      </>}
      {t === 'decision' && <>
        <FieldText label={traducir('workflowdesigner.expresion')} value={config.expression} onChange={v => setConfig('expression', v)} placeholder="priority == 'P1'" />
      </>}
      {t === 'approval' && <>
        <FieldText label={traducir('workflowdesigner.rol_que_aprueba')} value={config.approver_role} onChange={v => setConfig('approver_role', v)} placeholder="manager" />
        <FieldNumber label="Plazo (horas)" value={config.deadline_hours} onChange={v => setConfig('deadline_hours', v)} />
      </>}
      {t === 'wait' && <>
        <FieldNumber label="Esperar (minutos)" value={config.wait_minutes} onChange={v => setConfig('wait_minutes', v)} />
        <FieldText label={traducir('workflowdesigner.o_hasta_el_campo')} value={config.until_field} onChange={v => setConfig('until_field', v)} placeholder="due_date" />
      </>}
      {t === 'notify' && <>
        <FieldSelect label="Canal" value={config.channel || 'in_app'} onChange={v => setConfig('channel', v)} options={[
          { v: 'in_app', l: 'Campana' }, { v: 'email', l: 'Campana + correo' },
        ]} />
        <FieldText label="Título" value={config.title ?? config.template_id} onChange={v => setConfig('title', v)} placeholder="P1 sin atender: {number}" />
        <FieldTextarea label="Mensaje" value={config.body} onChange={v => setConfig('body', v)} />
        <FieldText label="Destinatarios" value={config.recipients} onChange={v => setConfig('recipients', v)} placeholder="$assignee, $group" />
      </>}
      {t === 'http_call' && <>
        <FieldSelect label={traducir('workflowdesigner.metodo')} value={config.method || 'POST'} onChange={v => setConfig('method', v)} options={[
          { v: 'GET', l: 'GET' }, { v: 'POST', l: 'POST' }, { v: 'PATCH', l: 'PATCH' }, { v: 'DELETE', l: 'DELETE' },
        ]} />
        <FieldText label="URL" value={config.url} onChange={v => setConfig('url', v)} placeholder="https://api.x.com/foo" />
        <FieldTextarea label="Cuerpo (JSON)" value={config.body_template} onChange={v => setConfig('body_template', v)} />
      </>}
      {t === 'create_ticket' && <>
        <FieldText label="Cola" value={config.queue} onChange={v => setConfig('queue', v)} placeholder="support" />
        <FieldText label={traducir('workflowdesigner.plantilla_de_titulo')} value={config.title_template} onChange={v => setConfig('title_template', v)} placeholder="Seguimiento: ${title}" />
        {/* La descripción es obligatoria en el modelo de ticket y no había campo
            para escribirla: el motor se cae al título si se deja en blanco. */}
        <FieldText label={traducir('workflowdesigner.plantilla_de_descripcion')} value={config.description_template} onChange={v => setConfig('description_template', v)} placeholder={traducir('workflowdesigner.creado_por_el_flujo_desde_title')} />
        <FieldSelect label="Prioridad" value={config.priority || 'P3'} onChange={v => setConfig('priority', v)} options={[
          { v: 'P1', l: 'P1 — Crítica' }, { v: 'P2', l: 'P2 — Alta' }, { v: 'P3', l: 'P3 — Normal' }, { v: 'P4', l: 'P4 — Baja' },
        ]} />
      </>}
    </div>
  )
}

function FieldText({ label, value, onChange, placeholder }: { label: string; value: ValorConfig; onChange: (v: string) => void; placeholder?: string }) {
  const idCampo = useId()
  return (
    <div>
      <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={labelStyle}>{label}</label>
      <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={value || ''} onChange={e => onChange(e.target.value)} placeholder={placeholder} style={inputStyle} />
    </div>
  )
}
function FieldNumber({ label, value, onChange }: { label: string; value: ValorConfig; onChange: (v: number | null) => void }) {
  const idCampo = useId()
  return (
    <div>
      <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={labelStyle}>{label}</label>
      <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} type="number" value={value ?? ''} onChange={e => onChange(e.target.value === '' ? null : Number(e.target.value))} style={inputStyle} />
    </div>
  )
}
function FieldSelect({ label, value, onChange, options }: { label: string; value: ValorConfig; onChange: (v: string) => void; options: { v: string; l: string }[] }) {
  const idCampo = useId()
  return (
    <div>
      <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={labelStyle}>{label}</label>
      <select id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={value || ''} onChange={e => onChange(e.target.value)} style={inputStyle}>
        {options.map((o) => <option key={o.v} value={o.v}>{o.l}</option>)}
      </select>
    </div>
  )
}
function FieldTextarea({ label, value, onChange }: { label: string; value: ValorConfig; onChange: (v: string) => void }) {
  const idCampo = useId()
  return (
    <div>
      <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={labelStyle}>{label}</label>
      <textarea id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} rows={3} value={value || ''} onChange={e => onChange(e.target.value)} style={{ ...inputStyle, resize: 'vertical', fontFamily: 'monospace', fontSize: 'var(--text-xs)' }} />
    </div>
  )
}

function ValidationBadge({ validation }: { validation: ValidacionGrafo | null }) {
  const { t: traducir } = useAppLang()
  if (!validation) return null
  const errs = validation.errors?.length || 0
  const warns = validation.warnings?.length || 0
  if (errs === 0 && warns === 0) {
    return <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, color: 'var(--success)', fontSize: 'var(--text-xs)' }}>
      <CheckCircle size={12} /> {traducir('workflowdesigner.valido')}
    </span>
  }
  if (errs > 0) {
    return <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, color: 'var(--danger)', fontSize: 'var(--text-xs)' }}>
      <AlertTriangle size={12} /> {errs} error{errs !== 1 ? 'es' : ''}
    </span>
  }
  return <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, color: 'var(--warning)', fontSize: 'var(--text-xs)' }}>
    <AlertTriangle size={12} /> {warns} aviso{warns !== 1 ? 's' : ''}
  </span>
}

function ValidationBanner({ validation }: { validation: ValidacionGrafo }) {
  const msgs = [
    ...(validation.errors || []).map(m => ({ kind: 'error', text: m })),
    ...(validation.warnings || []).map(m => ({ kind: 'warn', text: m })),
  ].slice(0, 4)
  return (
    <div style={{
      position: 'absolute', left: 12, bottom: 12, right: 12, zIndex: 10,
      background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 8,
      padding: '8px 12px', fontSize: 'var(--text-xs)', color: 'var(--text-2)',
      maxHeight: 90, overflowY: 'auto',
    }}>
      {msgs.map((m, i) => (
        <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 6 }}>
          <AlertTriangle size={11} style={{ marginTop: 2, color: m.kind === 'error' ? 'var(--danger)' : 'var(--warning)' }} />
          <span>{m.text}</span>
        </div>
      ))}
    </div>
  )
}

// ── Helpers ─────────────────────────────────────────────────────────────────
function serializeGraph(nodes: NodoFlujo[], edges: AristaFlujo[]) {
  return {
    nodes: nodes.map(n => ({
      id: n.id,
      type: n.data.type,
      position: n.position,
      data: { label: n.data.label, type: n.data.type, config: n.data.config || {} },
    })),
    edges: edges.map(e => ({
      id: e.id, source: e.source, target: e.target,
      branch: e.data?.branch || e.label || 'next',
    })),
  }
}

