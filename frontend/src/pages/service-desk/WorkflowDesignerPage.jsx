/**
 * WorkflowDesignerPage – Visual workflow blueprint designer for Service Desk
 *
 * Features:
 * - List / create / publish blueprints via GET/POST /sd/workflow-designer/blueprints
 * - SVG canvas: drag nodes, add edges, delete selected
 * - Node types: start, state, decision, end  (color-coded)
 * - Validates graph server-side before publishing
 * - Auto-save graph to backend versions on "Guardar"
 */
import { useState, useRef, useCallback, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../../services/api'
import { useToast } from '../../context/ToastContext'
import { Button, Spinner } from '../../components/ui'
import PageHeader from '../../components/layout/PageHeader'
import { GitBranch } from 'lucide-react'

// ─── constants ────────────────────────────────────────────────────────────────
const NODE_W = 120
const NODE_H = 40
const NODE_TYPES = ['start', 'state', 'decision', 'end']

const NODE_STYLE = {
  start:    { fill: '#22c55e', stroke: '#16a34a', text: '#fff', shape: 'oval' },
  end:      { fill: '#ef4444', stroke: '#dc2626', text: '#fff', shape: 'oval' },
  state:    { fill: 'var(--surface-2)', stroke: 'var(--accent)', text: 'var(--text-1)', shape: 'rect' },
  decision: { fill: '#f59e0b', stroke: '#d97706', text: '#fff', shape: 'diamond' },
}

const ps = { background:'var(--surface-2)', border:'1px solid var(--surface-4)', borderRadius:12, padding:'20px 24px' }
const is = { width:'100%', background:'var(--surface-3)', border:'1px solid var(--surface-4)', borderRadius:8, padding:'8px 12px', color:'var(--text-1)', fontSize:13, outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
const ls = { fontSize:11, fontWeight:600, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'0.07em', display:'block', marginBottom:5 }

// ─── helpers ──────────────────────────────────────────────────────────────────
function newNode(type, x, y) {
  return { id: `n_${Date.now()}_${Math.random().toString(36).slice(2,7)}`, type, label: type, x, y }
}

function buildSVGGraph(nodes, edges) {
  return {
    nodes: nodes.map(n => ({ id: n.id, type: n.type, label: n.label, x: n.x, y: n.y })),
    edges: edges.map(e => ({ source: e.source, target: e.target, label: e.label || '' })),
  }
}

// ─── NodeShape ────────────────────────────────────────────────────────────────
function NodeShape({ node, selected, onMouseDown, onConnectStart }) {
  const { fill, stroke, text, shape } = NODE_STYLE[node.type] || NODE_STYLE.state
  const cx = node.x + NODE_W / 2
  const cy = node.y + NODE_H / 2
  const rx = NODE_W / 2
  const ry = NODE_H / 2
  const outlineWidth = selected ? 3 : 1.5

  const shapeEl = shape === 'oval'
    ? <ellipse cx={cx} cy={cy} rx={rx} ry={ry} fill={fill} stroke={stroke} strokeWidth={outlineWidth} />
    : shape === 'diamond'
    ? <polygon
        points={`${cx},${node.y} ${node.x + NODE_W},${cy} ${cx},${node.y + NODE_H} ${node.x},${cy}`}
        fill={fill} stroke={stroke} strokeWidth={outlineWidth}
      />
    : <rect x={node.x} y={node.y} width={NODE_W} height={NODE_H} rx={8} fill={fill} stroke={stroke} strokeWidth={outlineWidth} />

  return (
    <g
      style={{ cursor: 'grab' }}
      onMouseDown={e => { e.stopPropagation(); onMouseDown(e, node) }}
    >
      {shapeEl}
      <text
        x={cx} y={cy} textAnchor="middle" dominantBaseline="middle"
        fill={text} fontSize={11} fontWeight={600} fontFamily="inherit"
        style={{ userSelect: 'none', pointerEvents: 'none' }}
      >
        {node.label.length > 14 ? node.label.slice(0, 13) + '…' : node.label}
      </text>
      {/* Connection port */}
      <circle
        cx={node.x + NODE_W} cy={cy} r={6}
        fill={stroke} opacity={0.7}
        style={{ cursor: 'crosshair' }}
        onMouseDown={e => { e.stopPropagation(); onConnectStart(e, node) }}
        title="Conectar →"
      />
    </g>
  )
}

// ─── Canvas ───────────────────────────────────────────────────────────────────
function DesignerCanvas({ nodes, edges, setNodes, setEdges }) {
  const svgRef = useRef(null)
  const [selected, setSelected] = useState(null)   // node id
  const [dragging, setDragging] = useState(null)    // { node, offX, offY }
  const [connecting, setConnecting] = useState(null) // { sourceId, curX, curY }
  const [editingNode, setEditingNode] = useState(null)

  const getSVGPos = (e) => {
    const svg = svgRef.current
    const rect = svg.getBoundingClientRect()
    const scaleX = 800 / rect.width
    const scaleY = 600 / rect.height
    return {
      x: (e.clientX - rect.left) * scaleX,
      y: (e.clientY - rect.top) * scaleY,
    }
  }

  const handleNodeMouseDown = useCallback((e, node) => {
    setSelected(node.id)
    const pos = getSVGPos(e)
    setDragging({ node, offX: pos.x - node.x, offY: pos.y - node.y })
  }, [])

  const handleConnectStart = useCallback((e, node) => {
    const pos = getSVGPos(e)
    setConnecting({ sourceId: node.id, curX: pos.x, curY: pos.y })
  }, [])

  const handleSVGMouseMove = useCallback((e) => {
    if (dragging) {
      const pos = getSVGPos(e)
      setNodes(prev => prev.map(n => n.id === dragging.node.id
        ? { ...n, x: pos.x - dragging.offX, y: pos.y - dragging.offY }
        : n))
    }
    if (connecting) {
      const pos = getSVGPos(e)
      setConnecting(c => ({ ...c, curX: pos.x, curY: pos.y }))
    }
  }, [dragging, connecting, setNodes])

  const handleSVGMouseUp = useCallback((e) => {
    setDragging(null)
    if (connecting) {
      // find target node under cursor
      const pos = getSVGPos(e)
      const target = nodes.find(n =>
        pos.x >= n.x && pos.x <= n.x + NODE_W &&
        pos.y >= n.y && pos.y <= n.y + NODE_H
      )
      if (target && target.id !== connecting.sourceId) {
        const exists = edges.some(e2 => e2.source === connecting.sourceId && e2.target === target.id)
        if (!exists) {
          setEdges(prev => [...prev, { id: `e_${Date.now()}`, source: connecting.sourceId, target: target.id, label: '' }])
        }
      }
      setConnecting(null)
    }
  }, [connecting, nodes, edges, setEdges])

  const handleCanvasClick = useCallback((e) => {
    if (e.target === svgRef.current) {
      setSelected(null)
    }
  }, [])

  // Rename on double click
  const handleNodeDblClick = useCallback((node) => {
    setEditingNode({ id: node.id, label: node.label })
  }, [])

  const commitRename = useCallback(() => {
    if (editingNode) {
      setNodes(prev => prev.map(n => n.id === editingNode.id ? { ...n, label: editingNode.label } : n))
      setEditingNode(null)
    }
  }, [editingNode, setNodes])

  // Delete selected node/edge with Backspace
  useEffect(() => {
    const handler = (e) => {
      if ((e.key === 'Delete' || e.key === 'Backspace') && selected && !editingNode) {
        setNodes(prev => prev.filter(n => n.id !== selected))
        setEdges(prev => prev.filter(e2 => e2.source !== selected && e2.target !== selected))
        setSelected(null)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [selected, editingNode, setNodes, setEdges])

  return (
    <div style={{ position: 'relative' }}>
      {editingNode && (
        <div style={{
          position: 'absolute', top: 0, left: 0, right: 0, zIndex: 20,
          display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px',
          background: 'var(--surface-2)', borderBottom: '1px solid var(--surface-4)',
        }}>
          <label style={{ fontSize: 12, color: 'var(--text-2)' }}>Nombre del nodo:</label>
          <input
            autoFocus
            value={editingNode.label}
            onChange={e => setEditingNode(x => ({ ...x, label: e.target.value }))}
            onBlur={commitRename}
            onKeyDown={e => e.key === 'Enter' && commitRename()}
            style={{ ...is, width: 200, padding: '4px 10px' }}
          />
        </div>
      )}
      <svg
        ref={svgRef}
        viewBox="0 0 800 600"
        style={{
          width: '100%', height: 520, borderRadius: 10,
          background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
          cursor: 'default',
        }}
        onMouseMove={handleSVGMouseMove}
        onMouseUp={handleSVGMouseUp}
        onClick={handleCanvasClick}
      >
        {/* Grid */}
        <defs>
          <pattern id="wd-grid" width="20" height="20" patternUnits="userSpaceOnUse">
            <path d="M 20 0 L 0 0 0 20" fill="none" stroke="var(--surface-4)" strokeWidth="0.5" opacity="0.5" />
          </pattern>
          <marker id="wd-arrow" markerWidth="8" markerHeight="8" refX="16" refY="3" orient="auto">
            <path d="M0,0 L0,6 L8,3 z" fill="var(--accent)" opacity="0.8" />
          </marker>
        </defs>
        <rect width="800" height="600" fill="url(#wd-grid)" />

        {/* Edges */}
        {edges.map(edge => {
          const src = nodes.find(n => n.id === edge.source)
          const tgt = nodes.find(n => n.id === edge.target)
          if (!src || !tgt) return null
          const x1 = src.x + NODE_W
          const y1 = src.y + NODE_H / 2
          const x2 = tgt.x
          const y2 = tgt.y + NODE_H / 2
          const mx = (x1 + x2) / 2
          return (
            <g key={edge.id}>
              <path
                d={`M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`}
                fill="none" stroke="var(--accent)" strokeWidth={1.5} opacity={0.7}
                markerEnd="url(#wd-arrow)"
              />
              {edge.label && (
                <text x={mx} y={(y1 + y2) / 2 - 6} textAnchor="middle"
                  fill="var(--text-2)" fontSize={10} fontFamily="inherit">
                  {edge.label}
                </text>
              )}
            </g>
          )
        })}

        {/* Connecting line preview */}
        {connecting && (() => {
          const src = nodes.find(n => n.id === connecting.sourceId)
          if (!src) return null
          return (
            <line
              x1={src.x + NODE_W} y1={src.y + NODE_H / 2}
              x2={connecting.curX} y2={connecting.curY}
              stroke="var(--accent)" strokeWidth={1.5} strokeDasharray="6 3" opacity={0.8}
            />
          )
        })()}

        {/* Nodes */}
        {nodes.map(node => (
          <g key={node.id} onDoubleClick={() => handleNodeDblClick(node)}>
            <NodeShape
              node={node}
              selected={selected === node.id}
              onMouseDown={handleNodeMouseDown}
              onConnectStart={handleConnectStart}
            />
          </g>
        ))}
      </svg>
      {selected && (
        <div style={{ marginTop: 6, fontSize: 11, color: 'var(--text-2)' }}>
          Nodo seleccionado: <strong>{nodes.find(n=>n.id===selected)?.label}</strong>
          {' · '}
          <span
            style={{ color: 'var(--danger)', cursor: 'pointer', textDecoration: 'underline' }}
            onClick={() => {
              setNodes(prev => prev.filter(n => n.id !== selected))
              setEdges(prev => prev.filter(e2 => e2.source !== selected && e2.target !== selected))
              setSelected(null)
            }}
          >
            Eliminar
          </span>
          {' · Doble clic para renombrar · Arrastra el puerto ● para conectar'}
        </div>
      )}
    </div>
  )
}

// ─── Main Page ────────────────────────────────────────────────────────────────
export default function WorkflowDesignerPage() {
  const toast = useToast()
  const qc = useQueryClient()
  const [view, setView] = useState('list')   // 'list' | 'editor'
  const [activeBP, setActiveBP] = useState(null)  // selected blueprint
  const [nodes, setNodes] = useState([])
  const [edges, setEdges] = useState([])
  const [newBPName, setNewBPName] = useState('')
  const [newBPType, setNewBPType] = useState('incident')
  const [showCreate, setShowCreate] = useState(false)

  const PROCESS_TYPES = ['incident', 'request', 'change', 'problem', 'onboarding', 'custom']

  const { data: blueprints = [], isLoading } = useQuery({
    queryKey: ['wd-blueprints'],
    queryFn: () => api.get('/sd/workflow-designer/blueprints').then(r => r.data).catch(() => []),
  })

  const { mutate: createBP, isPending: creating } = useMutation({
    mutationFn: (payload) => api.post('/sd/workflow-designer/blueprints', payload).then(r => r.data),
    onSuccess: (bp) => {
      qc.invalidateQueries(['wd-blueprints'])
      setNewBPName(''); setShowCreate(false)
      toast.success(`Blueprint "${bp.name}" creado`)
      openEditor(bp, [])
    },
    onError: (e) => toast.error(e?.response?.data?.detail || 'Error al crear blueprint'),
  })

  const { mutate: saveVersion, isPending: saving } = useMutation({
    mutationFn: ({ id, graph, change_summary }) =>
      api.post(`/sd/workflow-designer/blueprints/${id}/versions`, { graph, change_summary }).then(r => r.data),
    onSuccess: (ver) => {
      qc.invalidateQueries(['wd-blueprints'])
      toast.success(`Versión ${ver.version_number} guardada`)
    },
    onError: (e) => toast.error(e?.response?.data?.detail || 'Error al guardar'),
  })

  const { mutate: publishBP, isPending: publishing } = useMutation({
    mutationFn: ({ id, versionNum }) =>
      api.post(`/sd/workflow-designer/blueprints/${id}/publish/${versionNum}`).then(r => r.data),
    onSuccess: (bp) => {
      qc.invalidateQueries(['wd-blueprints'])
      toast.success(`Blueprint publicado (v${bp.published_version})`)
      if (activeBP) setActiveBP(prev => ({ ...prev, ...bp }))
    },
    onError: (e) => toast.error(e?.response?.data?.detail || 'Error al publicar'),
  })

  const { mutate: validateGraph } = useMutation({
    mutationFn: (graph) => api.post('/sd/workflow-designer/validate', { graph }).then(r => r.data),
    onSuccess: (res) => {
      if (res.valid) toast.success('Grafo válido ✓')
      else toast.error(`Inválido: ${(res.errors || []).join('; ')}`)
    },
    onError: (e) => toast.error(e?.response?.data?.detail || 'Error al validar'),
  })

  const { data: versions = [] } = useQuery({
    queryKey: ['wd-versions', activeBP?.id],
    queryFn: () => activeBP
      ? api.get(`/sd/workflow-designer/blueprints/${activeBP.id}/versions`).then(r => r.data).catch(() => [])
      : Promise.resolve([]),
    enabled: !!activeBP,
  })

  function openEditor(bp, initialNodes = [], initialEdges = []) {
    setActiveBP(bp)
    setNodes(initialNodes)
    setEdges(initialEdges)
    setView('editor')
  }

  function openExistingBP(bp) {
    // Load from latest version graph if available
    const latestVersion = bp.published_version
    if (latestVersion) {
      api.get(`/sd/workflow-designer/blueprints/${bp.id}/versions`)
        .then(r => r.data)
        .then(vers => {
          const published = vers.find(v => v.version_number === latestVersion)
          const graph = published?.graph || { nodes: [], edges: [] }
          const ns = (graph.nodes || []).map(n => ({
            id: n.id, type: n.type || 'state', label: n.label || n.id,
            x: n.x || 100, y: n.y || 100,
          }))
          const es = (graph.edges || []).map((e, i) => ({
            id: e.id || `e_${i}`, source: e.source, target: e.target, label: e.label || '',
          }))
          openEditor(bp, ns, es)
        })
        .catch(() => openEditor(bp, [], []))
    } else {
      openEditor(bp, [], [])
    }
  }

  function addNode(type) {
    const x = 80 + (nodes.length % 5) * 140
    const y = 80 + Math.floor(nodes.length / 5) * 120
    setNodes(prev => [...prev, newNode(type, x, y)])
  }

  function handleSave() {
    if (!activeBP) return
    const graph = buildSVGGraph(nodes, edges)
    saveVersion({ id: activeBP.id, graph, change_summary: 'Guardado desde diseñador visual' })
  }

  function handleValidate() {
    validateGraph(buildSVGGraph(nodes, edges))
  }

  function handlePublish() {
    if (!activeBP) return
    const latestVersion = versions.length ? versions[versions.length - 1].version_number : null
    if (!latestVersion) { toast.error('Guarda el diseño antes de publicar'); return }
    publishBP({ id: activeBP.id, versionNum: latestVersion })
  }

  // ── LIST VIEW ────────────────────────────────────────────────────────────────
  if (view === 'list') return (
    <div style={{ padding: 32 }}>
      <PageHeader
        icon={<GitBranch size={18} />}
        title="Workflow Designer"
        subtitle="Diseña procesos de Service Desk de forma visual"
        actions={<Button onClick={() => setShowCreate(true)}>+ Nuevo blueprint</Button>}
      />

      {showCreate && (
        <div style={{ ...ps, marginBottom: 20 }}>
          <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 14 }}>Nuevo blueprint de proceso</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 180px auto', gap: 12, alignItems: 'flex-end' }}>
            <div>
              <label style={ls}>Nombre</label>
              <input value={newBPName} onChange={e => setNewBPName(e.target.value)}
                placeholder="Ej: Gestión de incidentes P1" style={is} />
            </div>
            <div>
              <label style={ls}>Tipo de proceso</label>
              <select value={newBPType} onChange={e => setNewBPType(e.target.value)} style={is}>
                {PROCESS_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <Button disabled={!newBPName.trim() || creating}
                onClick={() => createBP({ name: newBPName.trim(), process_type: newBPType })}>
                {creating ? 'Creando…' : 'Crear'}
              </Button>
              <button onClick={() => setShowCreate(false)}
                style={{ padding: '8px 14px', borderRadius: 8, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--text-2)', cursor: 'pointer', fontFamily: 'inherit', fontSize: 13 }}>
                Cancelar
              </button>
            </div>
          </div>
        </div>
      )}

      {isLoading ? <Spinner /> : blueprints.length === 0 ? (
        <div style={{ ...ps, textAlign: 'center', padding: '48px 24px' }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>🔀</div>
          <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 8 }}>Sin blueprints de proceso</div>
          <div style={{ fontSize: 13, color: 'var(--text-2)', marginBottom: 20 }}>Crea un blueprint para diseñar visualmente los flujos de trabajo de Service Desk.</div>
          <Button onClick={() => setShowCreate(true)}>+ Crear primer blueprint</Button>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(280px,1fr))', gap: 16 }}>
          {blueprints.map(bp => (
            <div key={bp.id} style={{ ...ps, cursor: 'pointer', transition: 'border-color .15s' }}
              onClick={() => openExistingBP(bp)}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                <div style={{ fontSize: 15, fontWeight: 700 }}>🔀 {bp.name}</div>
                <div style={{
                  fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 20, textTransform: 'uppercase',
                  background: bp.status === 'published' ? 'var(--success)' : 'var(--surface-4)',
                  color: bp.status === 'published' ? '#fff' : 'var(--text-2)',
                }}>
                  {bp.status}
                </div>
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-2)', marginBottom: 6 }}>
                Proceso: <strong>{bp.process_type}</strong>
                {bp.published_version && ` · v${bp.published_version} publicada`}
              </div>
              {bp.description && (
                <div style={{ fontSize: 12, color: 'var(--text-2)' }}>{bp.description}</div>
              )}
              <div style={{ marginTop: 12, fontSize: 11, color: 'var(--accent)', fontWeight: 600 }}>
                Abrir diseñador →
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )

  // ── EDITOR VIEW ──────────────────────────────────────────────────────────────
  return (
    <div style={{ padding: 32 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
        <button onClick={() => setView('list')}
          style={{ padding: '6px 12px', borderRadius: 8, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--text-2)', cursor: 'pointer', fontFamily: 'inherit', fontSize: 13 }}>
          ← Blueprints
        </button>
        <div style={{ fontSize: 18, fontWeight: 700 }}>
          🔀 {activeBP?.name}
        </div>
        <div style={{
          fontSize: 10, fontWeight: 700, padding: '3px 10px', borderRadius: 20, textTransform: 'uppercase',
          background: activeBP?.status === 'published' ? 'var(--success)' : 'var(--surface-4)',
          color: activeBP?.status === 'published' ? '#fff' : 'var(--text-2)',
        }}>
          {activeBP?.status}
        </div>
        <div style={{ flex: 1 }} />
        <button onClick={handleValidate}
          style={{ padding: '7px 16px', borderRadius: 8, border: '1px solid var(--accent)', background: 'transparent', color: 'var(--accent)', cursor: 'pointer', fontFamily: 'inherit', fontSize: 13, fontWeight: 600 }}>
          ✓ Validar
        </button>
        <button onClick={handleSave} disabled={saving}
          style={{ padding: '7px 16px', borderRadius: 8, border: 'none', background: 'var(--surface-4)', color: 'var(--text-1)', cursor: 'pointer', fontFamily: 'inherit', fontSize: 13, fontWeight: 600, opacity: saving ? 0.5 : 1 }}>
          {saving ? 'Guardando…' : '💾 Guardar'}
        </button>
        <Button disabled={publishing} onClick={handlePublish}>
          {publishing ? 'Publicando…' : '🚀 Publicar'}
        </Button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '160px 1fr', gap: 16 }}>
        {/* Palette */}
        <div style={{ ...ps, padding: '14px 12px' }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '.07em', marginBottom: 10 }}>Nodos</div>
          {NODE_TYPES.map(type => {
            const { fill, stroke } = NODE_STYLE[type]
            return (
              <button key={type} onClick={() => addNode(type)}
                style={{
                  width: '100%', marginBottom: 8, padding: '8px 10px', borderRadius: 8, cursor: 'pointer',
                  background: fill, border: `2px solid ${stroke}`, color: '#fff',
                  fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
                  transition: 'opacity .15s', opacity: 0.9,
                }}
                onMouseEnter={e => e.currentTarget.style.opacity = '1'}
                onMouseLeave={e => e.currentTarget.style.opacity = '0.9'}
              >
                + {type}
              </button>
            )
          })}
          <div style={{ marginTop: 14, fontSize: 10, color: 'var(--text-2)', lineHeight: 1.5 }}>
            <div><strong>●</strong> Arrastra el puerto derecho para conectar</div>
            <div><strong>⌫</strong> Delete para eliminar nodo</div>
            <div><strong>↑↑</strong> Doble clic para renombrar</div>
          </div>

          {/* Versions panel */}
          {versions.length > 0 && (
            <div style={{ marginTop: 20 }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '.07em', marginBottom: 8 }}>Versiones</div>
              {[...versions].reverse().slice(0, 5).map(v => (
                <div key={v.id} style={{ fontSize: 11, color: 'var(--text-2)', marginBottom: 4, display: 'flex', justifyContent: 'space-between' }}>
                  <span>v{v.version_number}</span>
                  <span style={{ color: v.is_published ? 'var(--success)' : 'var(--text-2)' }}>
                    {v.is_published ? '✓ pub' : 'draft'}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Canvas */}
        <DesignerCanvas nodes={nodes} edges={edges} setNodes={setNodes} setEdges={setEdges} />
      </div>
    </div>
  )
}
