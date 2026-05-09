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
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ReactFlow, ReactFlowProvider, addEdge, useNodesState, useEdgesState,
  Background, Controls, MiniMap, MarkerType, Handle, Position, useReactFlow,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import {
  GitBranch, Plus, Search, Trash2, Copy, ArrowLeft, Save, CheckCircle,
  AlertTriangle, Sparkles, X, Layers, Clock, Bell, Globe, Ticket,
  Play, XCircle, Activity,
} from 'lucide-react'
import { sdWorkflowDesignerApi } from '../../services/api'
import { useToast } from '../../context/ToastContext'
import { Button, Spinner } from '../../components/ui'
import PageHeader from '../../components/layout/PageHeader'
import PageShell from '../../components/layout/PageShell'

// ── Catálogo visual de los nodos (color + icono por tipo) ────────────────────
const NODE_VISUAL = {
  start:         { color: '#10b981', icon: '▶', label: 'Inicio' },
  end:           { color: '#ef4444', icon: '■', label: 'Fin' },
  state:         { color: '#3b82f6', icon: '●', label: 'Estado' },
  decision:      { color: '#f59e0b', icon: '◆', label: 'Decisión' },
  approval:      { color: '#8b5cf6', icon: '✓', label: 'Aprobación' },
  wait:          { color: '#6b7280', icon: '⏱', label: 'Espera' },
  notify:        { color: '#14b8a6', icon: '🔔', label: 'Notificar' },
  http_call:     { color: '#ec4899', icon: '🌐', label: 'HTTP' },
  create_ticket: { color: '#0ea5e9', icon: '🎫', label: 'Ticket' },
}

const PROCESS_LABEL = { ticket: 'Ticket', change: 'Cambio', approval: 'Aprobación' }

// Estilos compartidos
const inputStyle = {
  width: '100%', boxSizing: 'border-box',
  background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
  borderRadius: 8, padding: '8px 10px',
  color: 'var(--text-1)', fontSize: 'var(--text-sm)',
  outline: 'none', fontFamily: 'inherit',
}
const labelStyle = {
  fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--text-2)',
  textTransform: 'uppercase', letterSpacing: '0.06em',
  display: 'block', marginBottom: 4,
}

// ── Custom node para ReactFlow ───────────────────────────────────────────────
function WorkflowNode({ data, selected }) {
  const v = NODE_VISUAL[data.type] || NODE_VISUAL.state
  const showInput = data.type !== 'start'
  const showOutput = data.type !== 'end'
  return (
    <div style={{
      background: 'var(--surface-2)', border: `2px solid ${selected ? 'var(--accent)' : v.color}`,
      borderRadius: 10, padding: '8px 12px', minWidth: 140, maxWidth: 220,
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
    <PageShell>
      <PageHeader
        icon={<GitBranch size={20} />}
        title="Workflow Designer"
        subtitle="Diseña procesos visuales reutilizables (tickets, cambios, aprobaciones)"
      />
      {activeId
        ? <BlueprintEditor id={activeId} onBack={() => setSearchParams({})} />
        : <BlueprintList onOpen={(id) => setSearchParams({ id })} />}
    </PageShell>
  )
}

// ── Listado de blueprints ────────────────────────────────────────────────────
function BlueprintList({ onOpen }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [showTemplates, setShowTemplates] = useState(false)

  const { data: blueprints = [], isLoading } = useQuery({
    queryKey: ['sd-wf-blueprints', filter],
    queryFn: () => sdWorkflowDesignerApi.blueprints(filter ? { process_type: filter } : undefined).then(r => r.data),
  })

  const archive = useMutation({
    mutationFn: (id) => sdWorkflowDesignerApi.archive(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sd-wf-blueprints'] })
      toast.success('Blueprint archivado')
    },
    onError: (e) => toast.error(e?.response?.data?.detail || 'Error al archivar'),
  })

  const clone = useMutation({
    mutationFn: ({ id, name }) => sdWorkflowDesignerApi.clone(id, { name }),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ['sd-wf-blueprints'] })
      toast.success('Blueprint clonado')
      onOpen(r.data.id)
    },
    onError: (e) => toast.error(e?.response?.data?.detail || 'Error al clonar'),
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
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Toolbar */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <div style={{ position: 'relative', flex: '1 1 280px', maxWidth: 360 }}>
          <Search size={14} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-3)' }} />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Buscar blueprints…"
            style={{ ...inputStyle, paddingLeft: 32 }}
          />
        </div>
        <select value={filter} onChange={e => setFilter(e.target.value)}
          style={{ ...inputStyle, width: 'auto', minWidth: 160 }}>
          <option value="">Todos los procesos</option>
          <option value="ticket">Ticket</option>
          <option value="change">Cambio</option>
          <option value="approval">Aprobación</option>
        </select>
        <div style={{ flex: 1 }} />
        <Button variant="secondary" onClick={() => setShowTemplates(true)}>
          <Sparkles size={14} /> Plantilla
        </Button>
        <Button onClick={() => setShowCreate(true)}>
          <Plus size={14} /> Nuevo blueprint
        </Button>
      </div>

      {/* Grid */}
      {isLoading ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: 60 }}><Spinner /></div>
      ) : filtered.length === 0 ? (
        <EmptyState search={search} filter={filter} />
      ) : (
        <div style={{ display: 'grid', gap: 14, gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))' }}>
          {filtered.map(bp => (
            <BlueprintCard key={bp.id} bp={bp}
              onOpen={() => onOpen(bp.id)}
              onClone={() => {
                const name = prompt(`Nombre para la copia de "${bp.name}":`, `${bp.name} (copia)`)
                if (name?.trim()) clone.mutate({ id: bp.id, name: name.trim() })
              }}
              onArchive={() => {
                if (confirm(`¿Archivar "${bp.name}"? Podrás verlo activando "Mostrar archivados" en el futuro.`)) archive.mutate(bp.id)
              }}
            />
          ))}
        </div>
      )}

      {showCreate && (
        <CreateBlueprintModal
          onClose={() => setShowCreate(false)}
          onCreated={(bp) => { setShowCreate(false); onOpen(bp.id) }}
        />
      )}
      {showTemplates && (
        <TemplatePickerModal
          onClose={() => setShowTemplates(false)}
          onPicked={(bp) => { setShowTemplates(false); onOpen(bp.id) }}
        />
      )}
    </div>
  )
}

function EmptyState({ search, filter }) {
  return (
    <div style={{
      padding: 60, textAlign: 'center',
      background: 'var(--surface-2)', border: '1px dashed var(--surface-4)', borderRadius: 12,
      color: 'var(--text-2)',
    }}>
      <GitBranch size={36} style={{ color: 'var(--text-3)', marginBottom: 8 }} />
      <div style={{ fontWeight: 600, marginBottom: 4 }}>
        {search || filter ? 'No hay blueprints que coincidan' : 'Aún no hay blueprints'}
      </div>
      <div style={{ fontSize: 'var(--text-sm)' }}>
        {search || filter ? 'Prueba con otros términos.' : 'Crea uno desde cero o parte de una plantilla.'}
      </div>
    </div>
  )
}

function BlueprintCard({ bp, onOpen, onClone, onArchive }) {
  return (
    <div role="button" tabIndex={0}
      style={{
        background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12,
        padding: 16, display: 'flex', flexDirection: 'column', gap: 8,
        cursor: 'pointer', transition: 'border-color 0.15s, transform 0.15s',
      }}
      onClick={onOpen}
      onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onOpen() } }}
      onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--accent)' }}
      onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--surface-4)' }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8 }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontWeight: 700, color: 'var(--text-1)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{bp.name}</div>
          {bp.description && (
            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', marginTop: 2,
              display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
              {bp.description}
            </div>
          )}
        </div>
        <span style={{
          fontSize: 'var(--text-xs)', fontWeight: 700,
          padding: '2px 8px', borderRadius: 12,
          background: bp.status === 'published' ? 'rgba(16,185,129,0.15)' : 'rgba(245,158,11,0.15)',
          color: bp.status === 'published' ? '#10b981' : '#f59e0b',
          flexShrink: 0,
        }}>
          {bp.status === 'published' ? 'Publicado' : bp.status === 'draft' ? 'Borrador' : 'Archivado'}
        </span>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 'var(--text-xs)', color: 'var(--text-2)' }}>
        <span style={{ background: 'var(--surface-3)', padding: '2px 6px', borderRadius: 4 }}>
          {PROCESS_LABEL[bp.process_type] || bp.process_type}
        </span>
        <span>v{bp.latest_version}</span>
        {bp.published_version && <span style={{ color: '#10b981' }}>· publicada v{bp.published_version}</span>}
      </div>
      <div style={{ display: 'flex', gap: 6, marginTop: 4 }}
        role="presentation"
        onClick={e => e.stopPropagation()}
        onKeyDown={e => e.stopPropagation()}>

        <Button size="sm" variant="secondary" onClick={onClone}><Copy size={12} /> Clonar</Button>
        <Button size="sm" variant="secondary" onClick={onArchive}><Trash2 size={12} /> Archivar</Button>
      </div>
    </div>
  )
}

function CreateBlueprintModal({ onClose, onCreated }) {
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
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ['sd-wf-blueprints'] })
      toast.success('Blueprint creado')
      onCreated?.(r.data)
    },
    onError: (e) => toast.error(e?.response?.data?.detail?.message || e?.response?.data?.detail || 'Error'),
  })

  return (
    <Modal title="Nuevo blueprint" onClose={onClose}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div>
          <label style={labelStyle}>Nombre</label>
          <input autoFocus value={name} onChange={e => setName(e.target.value)} style={inputStyle} placeholder="p.ej. Triaje de incidentes" />
        </div>
        <div>
          <label style={labelStyle}>Tipo de proceso</label>
          <select value={processType} onChange={e => setProcessType(e.target.value)} style={inputStyle}>
            <option value="ticket">Ticket</option>
            <option value="change">Cambio</option>
            <option value="approval">Aprobación</option>
          </select>
        </div>
        <div>
          <label style={labelStyle}>Descripción (opcional)</label>
          <textarea rows={3} value={description} onChange={e => setDescription(e.target.value)} style={{ ...inputStyle, resize: 'vertical' }} />
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

function TemplatePickerModal({ onClose, onPicked }) {
  const toast = useToast()
  const qc = useQueryClient()
  const { data: templates = [], isLoading } = useQuery({
    queryKey: ['sd-wf-templates'],
    queryFn: () => sdWorkflowDesignerApi.templates().then(r => r.data),
  })

  const useTemplate = useMutation({
    mutationFn: (tpl) => sdWorkflowDesignerApi.createBlueprint({
      name: tpl.name, process_type: tpl.process_type, description: tpl.description,
      graph: tpl.graph,
    }),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ['sd-wf-blueprints'] })
      toast.success('Blueprint creado desde plantilla')
      onPicked?.(r.data)
    },
    onError: (e) => toast.error(e?.response?.data?.detail?.message || 'Error al crear'),
  })

  return (
    <Modal title="Elegir plantilla" onClose={onClose} width={620}>
      {isLoading ? <Spinner /> : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
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
              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-2)' }}>{tpl.description}</div>
              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', marginTop: 4 }}>
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
function BlueprintEditor({ id, onBack }) {
  return (
    <ReactFlowProvider>
      <BlueprintEditorInner id={id} onBack={onBack} />
    </ReactFlowProvider>
  )
}

function BlueprintEditorInner({ id, onBack }) {
  const qc = useQueryClient()
  const toast = useToast()
  const { fitView } = useReactFlow()
  const [tab, setTab] = useState('editor')   // editor | runs
  const [showRunModal, setShowRunModal] = useState(false)

  const { data: detail, isLoading } = useQuery({
    queryKey: ['sd-wf-blueprint', id],
    queryFn: () => sdWorkflowDesignerApi.blueprint(id).then(r => r.data),
  })

  const blueprint = detail?.blueprint
  const versions = detail?.versions || []
  const head = versions[0]  // Order by version desc en backend

  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])
  const [selected, setSelected] = useState(null)
  const [validation, setValidation] = useState(null)

  // Carga inicial
  useEffect(() => {
    if (!head) return
    const g = head.graph || {}
    const n = (g.nodes || []).map(node => ({
      ...node,
      type: 'wf',
      position: node.position || { x: 100, y: 100 },
      data: node.data || { label: node.label || node.type, type: node.type, config: node.config || {} },
    }))
    // Aseguramos que data.type siga existiendo (es el tipo lógico)
    n.forEach(nn => {
      if (!nn.data.type) nn.data.type = (g.nodes || []).find(o => o.id === nn.id)?.type || 'state'
    })
    const e = (g.edges || []).map(edge => ({
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

  const onConnect = useCallback((params) => {
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

  const addNode = (type) => {
    const id = `${type}_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`
    const v = NODE_VISUAL[type]
    setNodes(n => [...n, {
      id, type: 'wf',
      position: { x: 200 + Math.random() * 200, y: 200 + Math.random() * 80 },
      data: { label: v.label, type, config: {} },
    }])
  }

  const updateSelectedNode = (patch) => {
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
    onError: (e) => {
      const detail = e?.response?.data?.detail
      const msg = detail?.errors?.length ? detail.errors.join(' · ') : (detail?.message || detail || 'Error al guardar')
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
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 'var(--text-md)', fontWeight: 700, color: 'var(--text-1)' }}>{blueprint.name}</div>
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>
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
                color: tab === t ? '#fff' : 'var(--text-2)',
                border: 'none', padding: '6px 14px', borderRadius: 6,
                cursor: 'pointer', fontSize: 'var(--text-xs)', fontWeight: 600,
                display: 'inline-flex', alignItems: 'center', gap: 4,
              }}>
              {t === 'editor' ? <Layers size={12} /> : <Activity size={12} />}
              {t === 'editor' ? 'Editor' : 'Ejecuciones'}
            </button>
          ))}
        </div>
        <div style={{ flex: 1 }} />
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
            <MiniMap pannable zoomable
              nodeColor={(n) => NODE_VISUAL[n.data?.type]?.color || '#94a3b8'}
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
function RunsTab({ blueprintId }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [activeRunId, setActiveRunId] = useState(null)

  const { data: runs = [], isLoading } = useQuery({
    queryKey: ['sd-wf-runs', blueprintId],
    queryFn: () => sdWorkflowDesignerApi.runs({ blueprint_id: blueprintId }).then(r => r.data),
    refetchInterval: 8_000,
  })
  const { data: runDetail } = useQuery({
    queryKey: ['sd-wf-run', activeRunId],
    queryFn: () => sdWorkflowDesignerApi.run(activeRunId).then(r => r.data),
    enabled: !!activeRunId,
    refetchInterval: 4_000,
  })

  const resume = useMutation({
    mutationFn: ({ runId, branch }) => sdWorkflowDesignerApi.resumeRun(runId, { branch }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sd-wf-runs', blueprintId] })
      qc.invalidateQueries({ queryKey: ['sd-wf-run', activeRunId] })
      toast.success('Ejecución reanudada')
    },
    onError: (e) => toast.error(e?.response?.data?.detail || 'Error al reanudar'),
  })
  const cancel = useMutation({
    mutationFn: (runId) => sdWorkflowDesignerApi.cancelRun(runId, 'cancelled by user'),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sd-wf-runs', blueprintId] })
      qc.invalidateQueries({ queryKey: ['sd-wf-run', activeRunId] })
      toast.success('Ejecución cancelada')
    },
  })

  const fmtDate = (iso) => iso ? new Date(iso).toLocaleString() : ''
  const statusColor = (s) => ({
    running: '#3b82f6', waiting: '#f59e0b', completed: '#10b981',
    cancelled: 'var(--text-3)', error: '#ef4444',
  }[s] || 'var(--text-3)')

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
            <div style={{ fontWeight: 600 }}>Aún no hay ejecuciones</div>
            <div style={{ fontSize: 'var(--text-sm)' }}>
              Pulsa "Ejecutar" para iniciar una nueva.
            </div>
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-sm)' }}>
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
          <div style={{ color: 'var(--text-3)', fontSize: 'var(--text-sm)' }}>
            Selecciona una ejecución para ver su historial.
          </div>
        ) : !runDetail ? (
          <Spinner />
        ) : (
          <>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div>
                <div style={{ fontWeight: 700 }}>{runDetail.run.id.slice(0, 8)}</div>
                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>
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
              <div style={{ background: 'rgba(239,68,68,0.12)', color: '#ef4444',
                border: '1px solid rgba(239,68,68,0.3)', borderRadius: 6,
                padding: '6px 10px', fontSize: 'var(--text-xs)' }}>
                {runDetail.run.last_error}
              </div>
            )}

            {runDetail.run.status === 'waiting' && (
              <ResumeBranchPicker
                runDetail={runDetail}
                onResume={(branch) => resume.mutate({ runId: runDetail.run.id, branch })}
                pending={resume.isPending}
              />
            )}

            <div style={{ marginTop: 6 }}>
              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', textTransform: 'uppercase', fontWeight: 700, letterSpacing: '0.07em', marginBottom: 6 }}>
                Historial ({runDetail.steps.length})
              </div>
              {runDetail.steps.length === 0 ? (
                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>Sin pasos aún.</div>
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
                  <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>{s.node_id}</div>
                  {s.error && <div style={{ color: '#ef4444', fontSize: 'var(--text-xs)' }}>{s.error}</div>}
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
                  borderRadius: 6, padding: 8, fontSize: 'var(--text-xs)', overflowX: 'auto',
                }}>{JSON.stringify(runDetail.run.context, null, 2)}</pre>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

function ResumeBranchPicker({ runDetail, onResume, pending }) {
  // Branch options según el tipo del nodo actual
  const nodeType = runDetail.steps?.find(s => s.status === 'waiting')?.node_type || 'approval'
  const branches = {
    approval: [{ b: 'approved', label: 'Aprobar', color: '#10b981' }, { b: 'rejected', label: 'Rechazar', color: '#ef4444' }],
    decision: [{ b: 'true', label: 'Verdadero' }, { b: 'false', label: 'Falso' }],
    wait: [{ b: 'next', label: 'Continuar' }],
    http_call: [{ b: 'success', label: 'Éxito' }, { b: 'failure', label: 'Fallo' }],
  }[nodeType] || [{ b: 'next', label: 'Continuar' }]

  return (
    <div style={{
      background: 'rgba(245,158,11,0.10)', border: '1px solid rgba(245,158,11,0.4)',
      borderRadius: 8, padding: 10,
    }}>
      <div style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: '#f59e0b', marginBottom: 6 }}>
        ⏸ Esperando intervención · {NODE_VISUAL[nodeType]?.label || nodeType}
      </div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        {branches.map(({ b, label, color }) => (
          <button key={b} onClick={() => onResume(b)} disabled={pending}
            style={{
              cursor: 'pointer', border: 'none', borderRadius: 6,
              background: color || 'var(--accent)', color: '#fff',
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

function StartRunModal({ blueprint, onClose, onStarted }) {
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
    onError: (e) => toast.error(e?.response?.data?.detail || e?.message || 'Error'),
  })
  return (
    <Modal title="Iniciar ejecución" onClose={onClose} width={520}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ display: 'flex', gap: 10 }}>
          <div style={{ flex: 1 }}>
            <label style={labelStyle}>Tipo de entidad</label>
            <input value={targetType} onChange={e => setTargetType(e.target.value)} style={inputStyle} placeholder="ticket / change / manual" />
          </div>
          <div style={{ flex: 1 }}>
            <label style={labelStyle}>ID de entidad (opcional)</label>
            <input value={targetId} onChange={e => setTargetId(e.target.value)} style={inputStyle} placeholder="123e4567-…" />
          </div>
        </div>
        <div>
          <label style={labelStyle}>Contexto inicial (JSON)</label>
          <textarea value={contextJson} onChange={e => setContextJson(e.target.value)} rows={6}
            style={{ ...inputStyle, fontFamily: 'monospace', fontSize: 'var(--text-xs)', resize: 'vertical' }} />
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', marginTop: 4 }}>
            Las decisiones del workflow lo evaluarán (p.ej. <code>priority == 'P1'</code>).
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
function Palette({ onAdd }) {
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
            <span style={{ flex: 1 }}>{v.label}</span>
          </button>
        )
      })}
    </div>
  )
}

function PropertiesPanel({ node, onChange, onDelete }) {
  if (!node) {
    return (
      <div style={{
        background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12,
        padding: 14, color: 'var(--text-3)', fontSize: 'var(--text-sm)',
      }}>
        Selecciona un nodo para editar sus propiedades.
      </div>
    )
  }
  const t = node.data.type
  const config = node.data.config || {}
  const setConfig = (k, v) => onChange({ config: { ...config, [k]: v } })

  return (
    <div style={{
      background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12,
      padding: 14, display: 'flex', flexDirection: 'column', gap: 10, overflowY: 'auto',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ fontWeight: 700, color: NODE_VISUAL[t]?.color }}>
          {NODE_VISUAL[t]?.label} <span style={{ color: 'var(--text-3)', fontSize: 'var(--text-xs)' }}>· {node.id.slice(0, 10)}</span>
        </div>
        <button onClick={onDelete} title="Eliminar nodo (Backspace)"
          style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--danger)' }}>
          <Trash2 size={14} />
        </button>
      </div>
      <div>
        <label style={labelStyle}>Etiqueta</label>
        <input value={node.data.label || ''} onChange={e => onChange({ label: e.target.value })} style={inputStyle} />
      </div>

      {/* Campos por tipo */}
      {t === 'state' && <>
        <FieldText label="Status" value={config.status} onChange={v => setConfig('status', v)} placeholder="open / in_progress / done" />
        <FieldText label="Asignar al rol" value={config.assignee_role} onChange={v => setConfig('assignee_role', v)} placeholder="support_l1" />
        <FieldNumber label="SLA (horas)" value={config.sla_hours} onChange={v => setConfig('sla_hours', v)} />
      </>}
      {t === 'decision' && <>
        <FieldText label="Expresión" value={config.expression} onChange={v => setConfig('expression', v)} placeholder="priority == 'P1'" />
      </>}
      {t === 'approval' && <>
        <FieldText label="Rol que aprueba" value={config.approver_role} onChange={v => setConfig('approver_role', v)} placeholder="manager" />
        <FieldNumber label="Plazo (horas)" value={config.deadline_hours} onChange={v => setConfig('deadline_hours', v)} />
      </>}
      {t === 'wait' && <>
        <FieldNumber label="Esperar (minutos)" value={config.wait_minutes} onChange={v => setConfig('wait_minutes', v)} />
        <FieldText label="O hasta el campo" value={config.until_field} onChange={v => setConfig('until_field', v)} placeholder="due_date" />
      </>}
      {t === 'notify' && <>
        <FieldSelect label="Canal" value={config.channel || 'email'} onChange={v => setConfig('channel', v)} options={[
          { v: 'email', l: 'Email' }, { v: 'in_app', l: 'In-app' }, { v: 'slack', l: 'Slack' }, { v: 'sms', l: 'SMS' },
        ]} />
        <FieldText label="Plantilla" value={config.template_id} onChange={v => setConfig('template_id', v)} placeholder="ticket_assigned" />
        <FieldText label="Destinatarios" value={config.recipients} onChange={v => setConfig('recipients', v)} placeholder="$assignee" />
      </>}
      {t === 'http_call' && <>
        <FieldSelect label="Método" value={config.method || 'POST'} onChange={v => setConfig('method', v)} options={[
          { v: 'GET', l: 'GET' }, { v: 'POST', l: 'POST' }, { v: 'PATCH', l: 'PATCH' }, { v: 'DELETE', l: 'DELETE' },
        ]} />
        <FieldText label="URL" value={config.url} onChange={v => setConfig('url', v)} placeholder="https://api.x.com/foo" />
        <FieldTextarea label="Cuerpo (JSON)" value={config.body_template} onChange={v => setConfig('body_template', v)} />
      </>}
      {t === 'create_ticket' && <>
        <FieldText label="Cola" value={config.queue} onChange={v => setConfig('queue', v)} placeholder="support" />
        <FieldText label="Plantilla de título" value={config.title_template} onChange={v => setConfig('title_template', v)} placeholder="Seguimiento: ${title}" />
        <FieldSelect label="Prioridad" value={config.priority || 'P3'} onChange={v => setConfig('priority', v)} options={[
          { v: 'P1', l: 'P1 — Crítica' }, { v: 'P2', l: 'P2 — Alta' }, { v: 'P3', l: 'P3 — Normal' }, { v: 'P4', l: 'P4 — Baja' },
        ]} />
      </>}
    </div>
  )
}

function FieldText({ label, value, onChange, placeholder }) {
  return (
    <div>
      <label style={labelStyle}>{label}</label>
      <input value={value || ''} onChange={e => onChange(e.target.value)} placeholder={placeholder} style={inputStyle} />
    </div>
  )
}
function FieldNumber({ label, value, onChange }) {
  return (
    <div>
      <label style={labelStyle}>{label}</label>
      <input type="number" value={value ?? ''} onChange={e => onChange(e.target.value === '' ? null : Number(e.target.value))} style={inputStyle} />
    </div>
  )
}
function FieldSelect({ label, value, onChange, options }) {
  return (
    <div>
      <label style={labelStyle}>{label}</label>
      <select value={value || ''} onChange={e => onChange(e.target.value)} style={inputStyle}>
        {options.map(o => <option key={o.v} value={o.v}>{o.l}</option>)}
      </select>
    </div>
  )
}
function FieldTextarea({ label, value, onChange }) {
  return (
    <div>
      <label style={labelStyle}>{label}</label>
      <textarea rows={3} value={value || ''} onChange={e => onChange(e.target.value)} style={{ ...inputStyle, resize: 'vertical', fontFamily: 'monospace', fontSize: 'var(--text-xs)' }} />
    </div>
  )
}

function ValidationBadge({ validation }) {
  if (!validation) return null
  const errs = validation.errors?.length || 0
  const warns = validation.warnings?.length || 0
  if (errs === 0 && warns === 0) {
    return <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, color: '#10b981', fontSize: 'var(--text-xs)' }}>
      <CheckCircle size={12} /> Válido
    </span>
  }
  if (errs > 0) {
    return <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, color: '#ef4444', fontSize: 'var(--text-xs)' }}>
      <AlertTriangle size={12} /> {errs} error{errs !== 1 ? 'es' : ''}
    </span>
  }
  return <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, color: '#f59e0b', fontSize: 'var(--text-xs)' }}>
    <AlertTriangle size={12} /> {warns} aviso{warns !== 1 ? 's' : ''}
  </span>
}

function ValidationBanner({ validation }) {
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
          <AlertTriangle size={11} style={{ marginTop: 2, color: m.kind === 'error' ? '#ef4444' : '#f59e0b' }} />
          <span>{m.text}</span>
        </div>
      ))}
    </div>
  )
}

// ── Helpers ─────────────────────────────────────────────────────────────────
function serializeGraph(nodes, edges) {
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

function Modal({ title, onClose, width = 480, children }) {
  return (
    <div role="presentation" onClick={onClose} style={{
      position: 'fixed', inset: 0, background: 'rgba(8,12,20,0.78)', backdropFilter: 'blur(4px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
    }}>
      <div role="dialog" aria-modal="true" tabIndex={-1}
        onClick={e => e.stopPropagation()}
        onKeyDown={e => { if (e.key === 'Escape') onClose() }}
        style={{
          background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
          borderRadius: 12, padding: 20, width, maxWidth: '90vw', maxHeight: '85vh',
          display: 'flex', flexDirection: 'column', gap: 12,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ fontSize: 'var(--text-md)', fontWeight: 700 }}>{title}</div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-2)' }}>
            <X size={16} />
          </button>
        </div>
        <div style={{ overflowY: 'auto' }}>{children}</div>
      </div>
    </div>
  )
}
