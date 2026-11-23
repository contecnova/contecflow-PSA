// Editor de un blueprint (lienzo, paleta y validacion) del disenador de flujos. 23-11-2026: troceado de WorkflowDesignerPage sin cambio de comportamiento.
import { useCallback, useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ReactFlowProvider, addEdge, useNodesState, useEdgesState, MarkerType, useReactFlow } from '@xyflow/react'
import type { Connection } from '@xyflow/react'
import { LienzoDeFlujo } from '../../components/flujos/LienzoDeFlujo'
import { ArrowLeft, Save, CheckCircle, AlertTriangle, Layers, Play, Activity } from 'lucide-react'
import { sdWorkflowDesignerApi } from '../../services/api'
import { useToast } from '../../context/ToastContext'
import { Button, Spinner, StatusBadge, Tabs, Pulsable } from '../../components/ui'
import { useAppLang } from '../../i18n/AppLangContext'
import { extractErr } from '../../utils/helpers'
import { ANIMATION_NORMAL_MS, FIT_VIEW_DELAY_MS, LIVE_VALIDATION_DEBOUNCE_MS } from '../../constants/timings'
import { type AristaFlujo, type DatosNodo, type ErrorDeFlujo, type GrafoGuardado, NODE_VISUAL, type NodoFlujo, type ValidacionGrafo, colorVar, nodeTypes, nombreDeNodo, nombreDeProceso, nombreDeRama } from './WorkflowDesignerComun'
import { RunsTab, StartRunModal } from './WorkflowDesignerEjecuciones'
import { PropertiesPanel } from './WorkflowDesignerPropiedades'

// ── Editor ──────────────────────────────────────────────────────────────────
export function BlueprintEditor({ id, onBack }: { id: string; onBack: () => void }) {
  return (
    <ReactFlowProvider>
      <BlueprintEditorInner id={id} onBack={onBack} />
    </ReactFlowProvider>
  )
}

function BlueprintEditorInner({ id, onBack }: { id: string; onBack: () => void }) {
  const { t: traducir } = useAppLang()
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
    const e = (g.edges || []).map((edge): AristaFlujo => {
      // La rama (valor del servidor) va en data.branch; la etiqueta solo se ve.
      const branch = edge.branch || edge.label || 'next'
      return {
        ...edge,
        type: 'smoothstep',
        animated: true,
        data: { branch },
        label: nombreDeRama(branch, traducir),
        markerEnd: { type: MarkerType.ArrowClosed, color: 'var(--accent)' },
        style: { stroke: 'var(--accent)' },
      }
    })
    setNodes(n)
    setEdges(e)
    setTimeout(() => fitView({ padding: 0.25, duration: ANIMATION_NORMAL_MS }), FIT_VIEW_DELAY_MS)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- cambiar de idioma no debe recargar el grafo
  }, [head, setNodes, setEdges, fitView])

  // Validación en vivo (debounced)
  useEffect(() => {
    const t = setTimeout(async () => {
      const graph = serializeGraph(nodes, edges)
      try {
        const r = await sdWorkflowDesignerApi.validate(graph)
        setValidation(r.data)
      } catch { /* accesorio: validación en vivo mientras se dibuja; al guardar el servidor valida y avisa */ }
    }, LIVE_VALIDATION_DEBOUNCE_MS)
    return () => clearTimeout(t)
  }, [nodes, edges])

  const onConnect = useCallback((params: Connection) => {
    const sourceNode = nodes.find(n => n.id === params.source)
    const branch = sourceNode?.data?.type === 'decision' ? 'true'
      : sourceNode?.data?.type === 'approval' ? 'approved'
      : sourceNode?.data?.type === 'http_call' ? 'success'
      : 'next'
    setEdges(eds => addEdge({
      ...params, type: 'smoothstep', animated: true, label: nombreDeRama(branch, traducir),
      data: { branch },
      markerEnd: { type: MarkerType.ArrowClosed, color: 'var(--accent)' },
      style: { stroke: 'var(--accent)' },
    }, eds))
  }, [nodes, setEdges, traducir])

  const addNode = (type: string) => {
    const id = `${type}_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`
    setNodes(n => [...n, {
      id, type: 'wf',
      position: { x: 200 + Math.random() * 200, y: 200 + Math.random() * 80 },
      data: { label: nombreDeNodo(type, traducir), type, config: {} },
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
      toast.success(traducir('workflowdesigner.version_guardada'))
    },
    onError: (e: ErrorDeFlujo) => {
      const detail = e?.response?.data?.detail
      const obj = typeof detail === 'object' ? detail : undefined
      const msg = obj?.errors?.length ? obj.errors.join(' · ') : (obj?.message || extractErr(e, traducir('workflowdesigner.error_guardar')))
      toast.error(msg)
    },
  })

  const publishLatest = useMutation({
    mutationFn: () => sdWorkflowDesignerApi.publish(id, blueprint.latest_version),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sd-wf-blueprint', id] })
      qc.invalidateQueries({ queryKey: ['sd-wf-blueprints'] })
      toast.success(traducir('workflowdesigner.publicada_toast', { n: blueprint.latest_version }))
    },
    onError: () => toast.error(traducir('workflowdesigner.error_publicar')),
  })

  if (isLoading || !blueprint) return <div className="wfd-loading"><Spinner /></div>

  const isPublished = !!blueprint.published_version

  return (
    <div className="wfd-editor">
      {/* Toolbar */}
      <div className="wfd-toolbar">
        <Button variant="secondary" icon={<ArrowLeft size={14} />} onClick={onBack}>{traducir('workflowdesigner.volver')}</Button>
        <div className="u-min0">
          <div className="wfd-name">{blueprint.name}</div>
          <div className="u-text3-xs">
            {nombreDeProceso(blueprint.process_type, traducir)} · v{blueprint.latest_version}
            {blueprint.published_version && ` · ${traducir('workflowdesigner.publicada_v', { n: blueprint.published_version })}`}
          </div>
        </div>
        {/* Tabs */}
        <Tabs
          ariaLabel={traducir('workflowdesigner.vistas')}
          items={[
            { id: 'editor', label: traducir('workflowdesigner.tab_editor'), icon: <Layers size={14} /> },
            { id: 'runs', label: traducir('workflowdesigner.tab_runs'), icon: <Activity size={14} /> },
          ]}
          active={tab}
          onChange={setTab}
        />
        <div className="u-flex1" />
        {tab === 'editor' && <ValidationBadge validation={validation} />}
        {tab === 'editor' && (
          <Button variant="secondary" icon={<Save size={14} />} onClick={() => save.mutate()} disabled={save.isPending || !validation?.valid}>
            {save.isPending ? traducir('workflowdesigner.guardando') : traducir('workflowdesigner.guardar_version')}
          </Button>
        )}
        {tab === 'editor' && (
          <Button icon={<CheckCircle size={14} />} onClick={() => publishLatest.mutate()} disabled={publishLatest.isPending || !validation?.valid}>
            {traducir('workflowdesigner.publicar_v', { n: blueprint.latest_version })}
          </Button>
        )}
        {tab === 'runs' && (
          <Button icon={<Play size={14} />} onClick={() => setShowRunModal(true)} disabled={!isPublished}
            title={isPublished ? traducir('workflowdesigner.iniciar_nueva') : traducir('workflowdesigner.publica_para')}>
            {traducir('workflowdesigner.ejecutar')}
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
      <div className="wfd-layout">
        <Palette onAdd={addNode} />
        <div className="wfd-canvas">
          <LienzoDeFlujo<NodoFlujo, AristaFlujo>
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            nodeTypes={nodeTypes as never}
            onSeleccion={setSelected}
            etiqueta={traducir('workflowdesigner.lienzo')}
            colorDeNodo={n => NODE_VISUAL[n.data?.type]?.color || 'var(--text-3)'}
          />
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

// ── Sub-componentes del editor ───────────────────────────────────────────────
function Palette({ onAdd }: { onAdd: (type: string) => void }) {
  const { t: traducir } = useAppLang()
  // El icono es el mismo que lleva el nodo en el lienzo (NODE_VISUAL).
  const items = ['start', 'state', 'decision', 'approval', 'wait', 'notify', 'http_call', 'create_ticket', 'end']
    .map(type => ({ type, icon: NODE_VISUAL[type].icon }))
  return (
    <div className="wfd-palette">
      <div className="wfd-palette__title">
        {traducir('workflowdesigner.paleta')}
      </div>
      {items.map(it => {
        const v = NODE_VISUAL[it.type]
        return (
          <Pulsable key={it.type} onClick={() => onAdd(it.type)}
            className="wfd-pal-item" style={colorVar(v.color)}
          >
            <span className="wfd-pal-item__icon" aria-hidden="true">{it.icon}</span>
            <span className="u-flex1">{nombreDeNodo(it.type, traducir)}</span>
          </Pulsable>
        )
      })}
    </div>
  )
}

function ValidationBadge({ validation }: { validation: ValidacionGrafo | null }) {
  const { t: traducir } = useAppLang()
  if (!validation) return null
  const errs = validation.errors?.length || 0
  const warns = validation.warnings?.length || 0
  if (errs === 0 && warns === 0) {
    return <StatusBadge kind="success" caps={false}>
      <CheckCircle size={12} aria-hidden="true" /> {traducir('workflowdesigner.valido')}
    </StatusBadge>
  }
  if (errs > 0) {
    return <StatusBadge kind="danger" caps={false}>
      <AlertTriangle size={12} aria-hidden="true" /> {traducir(errs === 1 ? 'workflowdesigner.n_error' : 'workflowdesigner.n_errores', { n: errs })}
    </StatusBadge>
  }
  return <StatusBadge kind="warning" caps={false}>
    <AlertTriangle size={12} aria-hidden="true" /> {traducir(warns === 1 ? 'workflowdesigner.n_aviso' : 'workflowdesigner.n_avisos', { n: warns })}
  </StatusBadge>
}

function ValidationBanner({ validation }: { validation: ValidacionGrafo }) {
  const msgs = [
    ...(validation.errors || []).map(m => ({ kind: 'error', text: m })),
    ...(validation.warnings || []).map(m => ({ kind: 'warn', text: m })),
  ].slice(0, 4)
  return (
    <div className="wfd-banner" role="status">
      {msgs.map((m, i) => (
        <div key={i} className="wfd-banner__row">
          <AlertTriangle size={11} aria-hidden="true" className={m.kind === 'error' ? 'wfd-banner__icon wfd-banner__icon--error' : 'wfd-banner__icon'} />
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
      branch: e.data?.branch || 'next',
    })),
  }
}
