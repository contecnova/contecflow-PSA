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
 *
 * 16-11-2026 (pasada de diseño): título del menú y sin "blueprints" en los
 * textos (ahora "flujos"); acciones principales en la cabecera (Nuevo flujo,
 * Desde plantilla); pestañas Editor/Ejecuciones con Tabs del kit; iconos de
 * nodo lucide (antes emojis); vacíos con EmptyState; estados con StatusBadge;
 * botones con la prop `icon`; campos con ds-input; tipo de entidad con selector
 * y ramas (approved, next…) traducidas en el lienzo y en el historial.
 */
import { useCallback, useEffect, useMemo, useState, useId } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import type { AxiosError } from 'axios'
import { useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ReactFlowProvider, addEdge, useNodesState, useEdgesState, MarkerType, useReactFlow,
} from '@xyflow/react'
import type { Connection, Edge, Node, NodeProps } from '@xyflow/react'
import { LienzoDeFlujo, NodoDeFlujo } from '../../components/flujos/LienzoDeFlujo'
import {
  GitBranch, Plus, Search, Trash2, Copy, ArrowLeft, Save, CheckCircle,
  AlertTriangle, Sparkles, Layers, Clock, Bell, Globe, Ticket,
  Play, XCircle, Activity, Square, Circle, Diamond, PauseCircle, MousePointerClick,
} from 'lucide-react'
import { sdWorkflowDesignerApi, type ApiError } from '../../services/api'
import type { SdBlueprint, SdDetalleDeEjecucion, SdGrafoDeFlujo, SdPlantillaDeFlujo, SdValidacionDeFlujo, SdValorDeConfigDeNodo } from '../../services/api/tipos-sd'
import { useToast } from '../../context/ToastContext'
import { Button, Spinner, Page, StatusBadge, Modal, EmptyState, Tabs, IconButton, Pulsable, Select, TablaSimple } from '../../components/ui'
import type { StatusBadgeKind } from '../../components/ui/StatusBadge'
import { useAppLang } from '../../i18n/AppLangContext'
import { fmtDateTime } from '../../utils/helpers'
import { ANIMATION_NORMAL_MS, FIT_VIEW_DELAY_MS, LIVE_VALIDATION_DEBOUNCE_MS, POLL_RUN_DETAIL_MS, POLL_RUN_LIST_MS } from '../../constants/timings'
import './WorkflowDesignerPage.css'

// ── Catálogo visual de los nodos (color + icono por tipo) ────────────────────
// El nombre de cada tipo se traduce al pintarlo: `workflowdesigner.nodo_<tipo>`.
// Iconos lucide (antes emojis y símbolos de texto), los mismos en paleta y lienzo.
const NODE_VISUAL: Record<string, { color: string; icon: ReactNode }> = {
  start:         { color: 'var(--success)', icon: <Play size={12} /> },
  end:           { color: 'var(--danger)', icon: <Square size={12} /> },
  state:         { color: 'var(--accent)', icon: <Circle size={12} /> },
  decision:      { color: 'var(--warning)', icon: <Diamond size={12} /> },
  approval:      { color: 'var(--purple)', icon: <CheckCircle size={12} /> },
  wait:          { color: 'var(--text-3)', icon: <Clock size={12} /> },
  notify:        { color: 'var(--chart-teal)', icon: <Bell size={12} /> },
  http_call:     { color: 'var(--chart-pink)', icon: <Globe size={12} /> },
  create_ticket: { color: 'var(--sky-blue)', icon: <Ticket size={12} /> },
}
type Traducir = (clave: string, params?: Record<string, string | number>) => string
/** Nombre del tipo de nodo en el idioma activo (o el codigo si es un tipo desconocido). */
const nombreDeNodo = (tipo: string, traducir: Traducir) =>
  NODE_VISUAL[tipo] ? traducir(`workflowdesigner.nodo_${tipo}`) : tipo
/** Color del dato (tipo de nodo, estado) para las clases `.wfd-*` que lo leen. */
const colorVar = (c: string) => ({ '--wfd-c': c } as CSSProperties)

// ── Tipos: respuestas en services/api/tipos-sd.ts; aquí, los del lienzo ──
type ValorConfig = SdValorDeConfigDeNodo
type ConfigNodo = Record<string, ValorConfig>
type DatosNodo = { label?: string; type: string; config?: ConfigNodo }
type NodoFlujo = Node<DatosNodo>
type AristaFlujo = Edge<{ branch?: string }>

type GrafoGuardado = SdGrafoDeFlujo
type Blueprint = SdBlueprint
type PlantillaFlujo = SdPlantillaDeFlujo
type DetalleEjecucion = SdDetalleDeEjecucion
type ValidacionGrafo = SdValidacionDeFlujo

/** `detail` de un error del diseñador: texto, o `{message, errors}` si el grafo no valida. */
type DetalleError = string | { message?: string; errors?: string[] }
type ErrorDeFlujo = AxiosError<{ detail?: DetalleError }>
const mensajeDelDetalle = (d: DetalleError | undefined) => (typeof d === 'object' ? d?.message : undefined)

const PROCESOS = ['ticket', 'change', 'approval']
const nombreDeProceso = (p: string, traducir: Traducir) =>
  PROCESOS.includes(p) ? traducir(`workflowdesigner.proc_${p}`) : p

// Estados de una ejecucion y de sus pasos que tienen traduccion.
const ESTADOS_DE_EJECUCION = ['running', 'waiting', 'completed', 'cancelled', 'error', 'done']
const nombreDeEstado = (s: string, traducir: Traducir) =>
  ESTADOS_DE_EJECUCION.includes(s) ? traducir(`workflowdesigner.run_${s}`) : s
const ESTADO_KIND: Record<string, StatusBadgeKind> = {
  running: 'accent', waiting: 'warning', completed: 'success', done: 'success', cancelled: 'neutral', error: 'danger',
}

// Ramas de una arista (valor del servidor) -> etiqueta legible.
const RAMAS = ['next', 'true', 'false', 'approved', 'rejected', 'success', 'failure']
const nombreDeRama = (b: string, traducir: Traducir) =>
  RAMAS.includes(b) ? traducir(`workflowdesigner.rama_${b}`) : b

// Tipo de entidad de una ejecución: los procesos más «manual».
const nombreDeEntidad = (e: string, traducir: Traducir) =>
  e === 'manual' ? traducir('workflowdesigner.manual') : nombreDeProceso(e, traducir)

// Clases compartidas de los formularios
const inputStyle = 'ds-input wfd-input'
const labelStyle = 'wfd-label'

// ── Custom node para ReactFlow ───────────────────────────────────────────────
function WorkflowNode({ data, selected }: NodeProps<NodoFlujo>) {
  // Tarjeta compartida con el diseñador de aprobaciones (components/flujos, tarea #26).
  const { t: traducir } = useAppLang()
  const v = NODE_VISUAL[data.type] || NODE_VISUAL.state
  return <NodoDeFlujo color={v.color} icono={v.icon} tipo={nombreDeNodo(NODE_VISUAL[data.type] ? data.type : 'state', traducir)} nombre={data.label || traducir('workflowdesigner.sin_nombre')}
    seleccionado={selected} entrada={data.type !== 'start'} salidas={data.type === 'end' ? [] : undefined} />
}
const nodeTypes = { wf: WorkflowNode }

// ── Top-level page ───────────────────────────────────────────────────────────
export default function WorkflowDesignerPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const activeId = searchParams.get('id')
  const { t: traducir } = useAppLang()
  const [showCreate, setShowCreate] = useState(false)
  const [showTemplates, setShowTemplates] = useState(false)
  const abrir = (id: string) => setSearchParams({ id })

  return (
    <Page
      icon={<GitBranch size={18} />}
      title={traducir('workflowdesigner.titulo')}
      subtitle={traducir('workflowdesigner.subtitulo')}
      actions={activeId ? undefined : (
        <>
          <Button variant="secondary" icon={<Sparkles size={14} />} onClick={() => setShowTemplates(true)}>
            {traducir('workflowdesigner.plantilla')}
          </Button>
          <Button icon={<Plus size={14} />} onClick={() => setShowCreate(true)}>
            {traducir('workflowdesigner.nuevo_blueprint')}
          </Button>
        </>
      )}
    >
      {activeId
        ? <BlueprintEditor id={activeId} onBack={() => setSearchParams({})} />
        : <BlueprintList onOpen={abrir} onNew={() => setShowCreate(true)} />}
      {showCreate && (
        <CreateBlueprintModal
          onClose={() => setShowCreate(false)}
          onCreated={bp => { setShowCreate(false); abrir(bp.id) }}
        />
      )}
      {showTemplates && (
        <TemplatePickerModal
          onClose={() => setShowTemplates(false)}
          onPicked={bp => { setShowTemplates(false); abrir(bp.id) }}
        />
      )}
    </Page>
  )
}

// ── Listado de blueprints ────────────────────────────────────────────────────
function BlueprintList({ onOpen, onNew }: { onOpen: (id: string) => void; onNew: () => void }) {
  const { t: traducir } = useAppLang()
  const qc = useQueryClient()
  const toast = useToast()
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState('')
  const [cloneTarget, setCloneTarget] = useState<{ id: string; name: string } | null>(null)
  const [archiveTarget, setArchiveTarget] = useState<{ id: string; name: string } | null>(null)

  const { data: blueprints = [], isLoading } = useQuery({
    queryKey: ['sd-wf-blueprints', filter],
    queryFn: () => sdWorkflowDesignerApi.blueprints(filter ? { process_type: filter } : undefined).then(r => r.data),
  })

  const archive = useMutation({
    mutationFn: (id: string) => sdWorkflowDesignerApi.archive(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sd-wf-blueprints'] })
      toast.success(traducir('workflowdesigner.bp_archivado'))
    },
    onError: (e: ApiError) => toast.error(e?.response?.data?.detail || traducir('workflowdesigner.error_archivar')),
  })

  const clone = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) => sdWorkflowDesignerApi.clone(id, { name }),
    onSuccess: r => {
      qc.invalidateQueries({ queryKey: ['sd-wf-blueprints'] })
      toast.success(traducir('workflowdesigner.bp_clonado'))
      onOpen(r.data.id)
    },
    onError: (e: ApiError) => toast.error(e?.response?.data?.detail || traducir('workflowdesigner.error_clonar')),
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
        <div className="wfd-search">
          <Search size={14} className="wfd-search__icon" aria-hidden="true" />
          <input aria-label={traducir('workflowdesigner.buscar')}
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder={traducir('workflowdesigner.buscar')}
            className="ds-input wfd-search__input"
          />
        </div>
        <Select suelto placeholder={false} value={filter} onChange={e => setFilter(e.target.value)} aria-label={traducir('workflowdesigner.tipo_de_proceso')}
          className="wfd-filter">
          <option value="">{traducir('workflowdesigner.todos_los_procesos')}</option>
          {PROCESOS.map(p => <option key={p} value={p}>{nombreDeProceso(p, traducir)}</option>)}
        </Select>
      </div>

      {/* Grid */}
      {isLoading ? (
        <div className="wfd-loading-flex"><Spinner /></div>
      ) : filtered.length === 0 ? (
        <EmptyState icon={<GitBranch size={28} />}
          title={search || filter ? traducir('workflowdesigner.no_coinciden') : traducir('workflowdesigner.aun_no_hay')}
          description={search || filter ? traducir('workflowdesigner.prueba_otros') : traducir('workflowdesigner.crea_uno')}
          action={search || filter ? undefined : (
            <Button icon={<Plus size={14} />} onClick={onNew}>{traducir('workflowdesigner.nuevo_blueprint')}</Button>
          )} />
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

      {cloneTarget && (
        <CloneBlueprintModal
          bp={cloneTarget}
          onClose={() => setCloneTarget(null)}
          onConfirm={(name: string) => { setCloneTarget(null); clone.mutate({ id: cloneTarget.id, name }) }}
        />
      )}
      {archiveTarget && (
        <ConfirmModal
          title={traducir('workflowdesigner.archivar_titulo')}
          message={traducir('workflowdesigner.confirmar_archivar', { name: archiveTarget.name })}
          confirmLabel={traducir('workflowdesigner.archivar')}
          onClose={() => setArchiveTarget(null)}
          onConfirm={() => { setArchiveTarget(null); archive.mutate(archiveTarget.id) }}
        />
      )}
    </>
  )
}

function BlueprintCard({ bp, onOpen, onClone, onArchive }: { bp: Blueprint; onOpen: () => void; onClone: () => void; onArchive: () => void }) {
  const { t: traducir } = useAppLang()
  const statusKind = bp.status === 'published' ? 'success'
                    : bp.status === 'draft' ? 'warning' : 'neutral'
  const statusLabel = bp.status === 'published' ? traducir('workflowdesigner.st_published')
                     : bp.status === 'draft' ? traducir('workflowdesigner.st_draft') : traducir('workflowdesigner.st_archived')
  return (
    <div role="button" tabIndex={0}
      className="ds-card ds-card--clickable"
      onClick={onOpen}
      onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onOpen() } }}
    >
      <div className="ds-row-between wfd-card-top">
        <div className="u-min0">
          <div className="wfd-card-name">{bp.name}</div>
          {bp.description && (
            <div className="ds-muted wfd-card-desc">
              {bp.description}
            </div>
          )}
        </div>
        <StatusBadge kind={statusKind}>{statusLabel}</StatusBadge>
      </div>
      <div className="ds-row u-text2-xs">
        <span className="wfd-tag">
          {nombreDeProceso(bp.process_type, traducir)}
        </span>
        <span>v{bp.latest_version}</span>
        {bp.published_version && <span className="u-success">· {traducir('workflowdesigner.publicada_v', { n: bp.published_version })}</span>}
      </div>
      <div className="ds-row"
        role="presentation"
        onClick={e => e.stopPropagation()}
        onKeyDown={e => e.stopPropagation()}>
        <Button size="sm" variant="secondary" icon={<Copy size={12} />} onClick={onClone}>{traducir('workflowdesigner.clonar')}</Button>
        <Button size="sm" variant="secondary" icon={<Trash2 size={12} />} onClick={onArchive}>{traducir('workflowdesigner.archivar')}</Button>
      </div>
    </div>
  )
}

function CloneBlueprintModal({ bp, onClose, onConfirm }: { bp: { name: string }; onClose: () => void; onConfirm: (name: string) => void }) {
  const idCampo = useId()
  const { t: traducir } = useAppLang()
  const [name, setName] = useState(traducir('workflowdesigner.copia', { name: bp.name }))
  return (
    <Modal open width={480} title={traducir('workflowdesigner.clonar_titulo')} onClose={onClose}>
      <div className="u-stack-12">
        <div>
          <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className={labelStyle}>{traducir('workflowdesigner.nombre_de_la_copia')}</label>
          <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} autoFocus value={name} onChange={e => setName(e.target.value)} className={inputStyle} />
        </div>
        <div className="wfd-actions">
          <Button variant="secondary" onClick={onClose}>{traducir('workflowdesigner.cancelar')}</Button>
          <Button onClick={() => onConfirm(name.trim())} disabled={!name.trim()}>{traducir('workflowdesigner.clonar')}</Button>
        </div>
      </div>
    </Modal>
  )
}

function ConfirmModal({ title, message, confirmLabel, onClose, onConfirm }: { title: string; message: string; confirmLabel?: string; onClose: () => void; onConfirm: () => void }) {
  const { t: traducir } = useAppLang()
  return (
    <Modal open width={480} title={title} onClose={onClose}>
      <div className="u-stack-16">
        <p className="wfd-confirm-text">{message}</p>
        <div className="u-actions-8">
          <Button variant="secondary" onClick={onClose}>{traducir('workflowdesigner.cancelar')}</Button>
          <Button onClick={onConfirm}>{confirmLabel ?? traducir('workflowdesigner.confirmar')}</Button>
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
          { id: 'start_1', type: 'start', position: { x: 100, y: 200 }, data: { label: nombreDeNodo('start', traducir) } },
          { id: 'end_1', type: 'end', position: { x: 500, y: 200 }, data: { label: nombreDeNodo('end', traducir) } },
        ],
        edges: [{ id: 'e1', source: 'start_1', target: 'end_1', branch: 'next' }],
      },
    }),
    onSuccess: r => {
      qc.invalidateQueries({ queryKey: ['sd-wf-blueprints'] })
      toast.success(traducir('workflowdesigner.bp_creado'))
      onCreated?.(r.data)
    },
    onError: (e: ErrorDeFlujo) => toast.error(mensajeDelDetalle(e?.response?.data?.detail) || e?.response?.data?.detail || traducir('workflowdesigner.error')),
  })

  return (
    <Modal open width={480} title={traducir('workflowdesigner.nuevo_blueprint')} onClose={onClose}>
      <div className="u-stack-12">
        <div>
          <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className={labelStyle}>{traducir('workflowdesigner.nombre')}</label>
          <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} autoFocus value={name} onChange={e => setName(e.target.value)} className={inputStyle} placeholder={traducir('workflowdesigner.p_ej_triaje_de_incidentes')} />
        </div>
        <div>
          <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className={labelStyle}>{traducir('workflowdesigner.tipo_de_proceso')}</label>
          <Select suelto placeholder={false} id={`${idCampo}-2`} value={processType} onChange={e => setProcessType(e.target.value)} className="wfd-sel">
            {PROCESOS.map(p => <option key={p} value={p}>{nombreDeProceso(p, traducir)}</option>)}
          </Select>
        </div>
        <div>
          <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className={labelStyle}>{traducir('workflowdesigner.descripcion_opcional')}</label>
          <textarea id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} rows={3} value={description} onChange={e => setDescription(e.target.value)} className={inputStyle} />
        </div>
        <div className="wfd-actions">
          <Button variant="secondary" onClick={onClose}>{traducir('workflowdesigner.cancelar')}</Button>
          <Button onClick={() => create.mutate()} disabled={!name.trim()} loading={create.isPending}>
            {traducir('workflowdesigner.crear_y_abrir')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

function TemplatePickerModal({ onClose, onPicked }: { onClose: () => void; onPicked?: (bp: Blueprint) => void }) {
  const { t: traducir } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const { data: templates = [], isLoading } = useQuery({
    queryKey: ['sd-wf-templates'],
    queryFn: () => sdWorkflowDesignerApi.templates().then(r => r.data),
  })

  const useTemplate = useMutation({
    mutationFn: (tpl: PlantillaFlujo) => sdWorkflowDesignerApi.createBlueprint({
      name: tpl.name, process_type: tpl.process_type, description: tpl.description,
      graph: tpl.graph,
    }),
    onSuccess: r => {
      qc.invalidateQueries({ queryKey: ['sd-wf-blueprints'] })
      toast.success(traducir('workflowdesigner.bp_creado_plantilla'))
      onPicked?.(r.data)
    },
    onError: (e: ErrorDeFlujo) => toast.error(mensajeDelDetalle(e?.response?.data?.detail) || traducir('workflowdesigner.error_crear')),
  })

  return (
    <Modal open title={traducir('workflowdesigner.elegir_plantilla')} onClose={onClose} width={620}>
      {isLoading ? <Spinner /> : (
        <div className="u-stack-8">
          {templates.map(tpl => (
            <Pulsable key={tpl.id} onClick={() => useTemplate.mutate(tpl)}
              className="wfd-tpl"
            >
              <div className="wfd-tpl__head">
                <span className="wfd-bold">{tpl.name}</span>
                <span className="wfd-tpl__tag">
                  {nombreDeProceso(tpl.process_type, traducir)}
                </span>
              </div>
              <div className="u-text2-xs">{tpl.description}</div>
              <div className="u-hint">
                {traducir('workflowdesigner.nodos_aristas', { n: tpl.graph.nodes.length, m: tpl.graph.edges.length })}
              </div>
            </Pulsable>
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
      } catch { /* noop */ }
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
      const msg = obj?.errors?.length ? obj.errors.join(' · ') : (obj?.message || detail || traducir('workflowdesigner.error_guardar'))
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

// ── Runs tab ────────────────────────────────────────────────────────────────
function RunsTab({ blueprintId }: { blueprintId: string }) {
  const { t: traducir } = useAppLang()
  const qc = useQueryClient()
  const toast = useToast()
  const [activeRunId, setActiveRunId] = useState<string | null>(null)

  const { data: runs = [], isLoading } = useQuery({
    queryKey: ['sd-wf-runs', blueprintId],
    queryFn: () => sdWorkflowDesignerApi.runs({ blueprint_id: blueprintId }).then(r => r.data),
    refetchInterval: POLL_RUN_LIST_MS,
  })
  const { data: runDetail } = useQuery({
    queryKey: ['sd-wf-run', activeRunId],
    queryFn: () => sdWorkflowDesignerApi.run(activeRunId).then(r => r.data),
    enabled: !!activeRunId,
    refetchInterval: POLL_RUN_DETAIL_MS,
  })

  const resume = useMutation({
    mutationFn: ({ runId, branch }: { runId: string; branch: string }) => sdWorkflowDesignerApi.resumeRun(runId, { branch }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sd-wf-runs', blueprintId] })
      qc.invalidateQueries({ queryKey: ['sd-wf-run', activeRunId] })
      toast.success(traducir('workflowdesigner.ejecucion_reanudada'))
    },
    onError: (e: ApiError) => toast.error(e?.response?.data?.detail || traducir('workflowdesigner.error_reanudar')),
  })
  const cancel = useMutation({
    mutationFn: (runId: string) => sdWorkflowDesignerApi.cancelRun(runId, 'cancelled by user'),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sd-wf-runs', blueprintId] })
      qc.invalidateQueries({ queryKey: ['sd-wf-run', activeRunId] })
      toast.success(traducir('workflowdesigner.ejecucion_cancelada'))
    },
  })

  const fmtDate = (iso: string | null) => iso ? fmtDateTime(iso) : ''

  return (
    <div className="wfd-runs">
      <div className="wfd-panel">
        {isLoading ? (
          <div className="wfd-loading"><Spinner /></div>
        ) : runs.length === 0 ? (
          <EmptyState icon={<Activity size={28} />}
            title={traducir('workflowdesigner.aun_no_hay_ejecuciones')}
            description={traducir('workflowdesigner.pulsa_ejecutar_para_iniciar_una_nueva')} />
        ) : (
          <TablaSimple claseTabla="u-table-sm">
            <thead className="wfd-thead">
              <tr className="wfd-thead-row">
                <th className="wfd-th">{traducir('workflowdesigner.th_estado')}</th>
                <th className="wfd-th">{traducir('workflowdesigner.th_nodo')}</th>
                <th className="wfd-th">{traducir('workflowdesigner.th_entidad')}</th>
                <th className="wfd-th">{traducir('workflowdesigner.th_iniciado')}</th>
                <th className="wfd-th"><abbr title={traducir('workflowdesigner.th_version')}>v</abbr></th>
              </tr>
            </thead>
            <tbody>
              {runs.map(r => (
                <tr key={r.id} onClick={() => setActiveRunId(r.id)}
                  tabIndex={0} aria-selected={r.id === activeRunId}
                  onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setActiveRunId(r.id) } }}
                  className={r.id === activeRunId ? 'wfd-run-row wfd-run-row--active' : 'wfd-run-row'}>
                  <td className="wfd-td">
                    <StatusBadge kind={ESTADO_KIND[r.status] ?? 'neutral'} caps={false}>{nombreDeEstado(r.status, traducir)}</StatusBadge>
                  </td>
                  <td className="wfd-td wfd-td--muted">{r.current_node_id || '—'}</td>
                  <td className="wfd-td wfd-td--muted">
                    {r.target_entity_type ? `${nombreDeEntidad(r.target_entity_type, traducir)} ${(r.target_entity_id || '').slice(0, 8)}`.trim() : traducir('workflowdesigner.manual')}
                  </td>
                  <td className="wfd-td wfd-td--dim wfd-td--xs">{fmtDate(r.started_at)}</td>
                  <td className="wfd-td wfd-td--dim">v{r.blueprint_version}</td>
                </tr>
              ))}
            </tbody>
          </TablaSimple>
        )}
      </div>
      {/* Detail panel */}
      <div className="wfd-panel wfd-panel--detail">
        {!activeRunId ? (
          <EmptyState icon={<MousePointerClick size={28} />}
            title={traducir('workflowdesigner.selecciona_una_ejecucion_para_ver_su_historial')} />
        ) : !runDetail ? (
          <Spinner />
        ) : (
          <>
            <div className="u-row-between">
              <div>
                <div className="wfd-bold">{runDetail.run.id.slice(0, 8)}</div>
                <div className="wfd-run-meta">
                  <StatusBadge kind={ESTADO_KIND[runDetail.run.status] ?? 'neutral'} caps={false}>{nombreDeEstado(runDetail.run.status, traducir)}</StatusBadge>
                  <span className="u-text3-xs">v{runDetail.run.blueprint_version}</span>
                </div>
              </div>
              {runDetail.run.status === 'running' || runDetail.run.status === 'waiting' ? (
                <Button size="sm" variant="secondary" icon={<XCircle size={12} />} onClick={() => cancel.mutate(runDetail.run.id)}>
                  {traducir('workflowdesigner.cancelar')}
                </Button>
              ) : null}
            </div>

            {runDetail.run.last_error && (
              <div className="wfd-error-box" role="alert">
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

            <div className="wfd-mt-6">
              <div className="wfd-heading">
                {traducir('workflowdesigner.historial', { n: runDetail.steps.length })}
              </div>
              {runDetail.steps.length === 0 ? (
                <div className="u-text3-xs">{traducir('workflowdesigner.sin_pasos_aun')}</div>
              ) : runDetail.steps.map((s, i) => (
                <div key={s.id} className="wfd-step" style={colorVar(NODE_VISUAL[s.node_type]?.color || 'var(--text-3)')}>
                  <div className="wfd-step__head">
                    <span className="wfd-step__name">
                      {i + 1}. {nombreDeNodo(s.node_type, traducir)}
                    </span>
                    <StatusBadge kind={ESTADO_KIND[s.status] ?? 'neutral'} caps={false}>
                      {nombreDeEstado(s.status, traducir)}{s.branch_taken ? ` · ${nombreDeRama(s.branch_taken, traducir)}` : ''}
                    </StatusBadge>
                  </div>
                  <div className="u-text3-xs">{s.node_id}</div>
                  {s.error && <div className="wfd-step__error">{s.error}</div>}
                </div>
              ))}
            </div>

            {Object.keys(runDetail.run.context || {}).length > 0 && (
              <div>
                <div className="wfd-heading wfd-heading--mb4">
                  {traducir('workflowdesigner.contexto')}
                </div>
                <pre className="wfd-pre">{JSON.stringify(runDetail.run.context, null, 2)}</pre>
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
  const branches: { b: string; label: string }[] = ({
    approval: [{ b: 'approved', label: traducir('workflowdesigner.br_aprobar') }, { b: 'rejected', label: traducir('workflowdesigner.br_rechazar') }],
    decision: [{ b: 'true', label: traducir('workflowdesigner.br_verdadero') }, { b: 'false', label: traducir('workflowdesigner.br_falso') }],
    wait: [{ b: 'next', label: traducir('workflowdesigner.br_continuar') }],
    http_call: [{ b: 'success', label: traducir('workflowdesigner.br_exito') }, { b: 'failure', label: traducir('workflowdesigner.br_fallo') }],
  } as Record<string, { b: string; label: string }[]>)[nodeType] || [{ b: 'next', label: traducir('workflowdesigner.br_continuar') }]

  return (
    <div className="wfd-resume">
      <div className="wfd-resume__title">
        <PauseCircle size={14} aria-hidden="true" />
        {traducir('workflowdesigner.esperando_intervencion', { nodo: nombreDeNodo(nodeType, traducir) })}
      </div>
      <div className="u-wrap-6">
        {branches.map(({ b, label }, i) => (
          <Button key={b} size="sm" variant={i === 0 ? 'primary' : 'secondary'} onClick={() => onResume(b)} disabled={pending}>
            {label}
          </Button>
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
      catch { throw new Error(traducir('workflowdesigner.contexto_json_invalido')) }
      return sdWorkflowDesignerApi.startRun(blueprint.id, {
        target_entity_type: targetType || null,
        target_entity_id: targetId || null,
        context: ctx,
      })
    },
    onSuccess: () => { toast.success(traducir('workflowdesigner.ejecucion_iniciada')); onStarted?.() },
    onError: (e: ApiError) => toast.error(e?.response?.data?.detail || e?.message || traducir('workflowdesigner.error')),
  })
  return (
    <Modal open title={traducir('workflowdesigner.iniciar_ejecucion')} onClose={onClose} width={520}>
      <div className="u-stack-12">
        <div className="u-row-10">
          <div className="u-flex1">
            <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className={labelStyle}>{traducir('workflowdesigner.tipo_de_entidad')}</label>
            <Select suelto placeholder={false} id={`${idCampo}-1`} value={targetType} onChange={e => setTargetType(e.target.value)} className="wfd-sel">
              {[...PROCESOS, 'manual'].map(p => <option key={p} value={p}>{nombreDeEntidad(p, traducir)}</option>)}
            </Select>
          </div>
          <div className="u-flex1">
            <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className={labelStyle}>{traducir('workflowdesigner.id_de_entidad_opcional')}</label>
            <input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={targetId} onChange={e => setTargetId(e.target.value)} className={inputStyle} placeholder="123e4567-…" />
          </div>
        </div>
        <div>
          <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className={labelStyle}>{traducir('workflowdesigner.contexto_inicial')}</label>
          <textarea id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={contextJson} onChange={e => setContextJson(e.target.value)} rows={6}
            className={`${inputStyle} wfd-input--mono ds-campo-codigo`} />
          <div className="u-hint">
            {traducir('workflowdesigner.las_decisiones_del_workflow_lo_evaluaran_p')} <code>priority == 'P1'</code>).
          </div>
        </div>
        <div className="wfd-actions wfd-actions--mt4">
          <Button variant="secondary" onClick={onClose}>{traducir('workflowdesigner.cancelar')}</Button>
          <Button icon={<Play size={12} />} onClick={() => start.mutate()} loading={start.isPending}>
            {traducir('workflowdesigner.ejecutar')}
          </Button>
        </div>
      </div>
    </Modal>
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

// Los mismos que `workflow_triggers.DISPARADORES` y `TicketStatus` del servidor.
const DISPARADORES_DE_FLUJO = ['created', 'assigned', 'group_assigned', 'status_changed', 'priority_changed',
  'commented', 'sla_warning', 'sla_breached', 'ola_breached', 'uc_breached', 'escalated']
const ESTADOS_DE_TICKET = ['new', 'assigned', 'in_progress', 'pending_client', 'pending_third', 'resolved', 'closed', 'cancelled']
// Clave de traduccion de cada estado (las mismas que SBadge, en `service_desk`).
const TICKET_STATUS_KEY: Record<string, string> = {
  new: 'status_new', assigned: 'status_assigned', in_progress: 'status_in_progress',
  pending_client: 'status_waiting_client', pending_third: 'status_pending_third',
  resolved: 'status_resolved', closed: 'status_closed', cancelled: 'status_cancelled',
}

function PropertiesPanel({ node, onChange, onDelete }: { node: NodoFlujo | null; onChange: (patch: Partial<DatosNodo>) => void; onDelete: () => void }) {
  const idCampo = useId()
  const { t: traducir } = useAppLang()
  if (!node) {
    return (
      <div className="wfd-props wfd-props--empty">
        <MousePointerClick size={20} aria-hidden="true" />
        <span>{traducir('workflowdesigner.selecciona_un_nodo_para_editar_sus_propiedades')}</span>
      </div>
    )
  }
  const t = node.data.type
  const config = node.data.config || {}
  const setConfig = (k: string, v: ValorConfig) => onChange({ config: { ...config, [k]: v } })

  return (
    <div className="wfd-props">
      <div className="u-row-between">
        <div className="wfd-bold wfd-c" style={colorVar(NODE_VISUAL[t]?.color ?? 'inherit')}>
          {nombreDeNodo(t, traducir)} <span className="u-text3-xs">· {node.id.slice(0, 10)}</span>
        </div>
        <IconButton ariaLabel={traducir('workflowdesigner.eliminar_nodo')} onClick={onDelete}>
          <Trash2 size={14} aria-hidden="true" />
        </IconButton>
      </div>
      <div>
        <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className={labelStyle}>{traducir('workflowdesigner.etiqueta')}</label>
        <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={node.data.label || ''} onChange={e => onChange({ label: e.target.value })} className={inputStyle} />
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
        <FieldSelect label={traducir('workflowdesigner.th_estado')} value={config.status || ''} onChange={v => setConfig('status', v)} options={[
          { v: '', l: '—' },
          ...ESTADOS_DE_TICKET.map(e => ({ v: e, l: traducir(`service_desk.${TICKET_STATUS_KEY[e]}`) })),
        ]} />
        <FieldText label={traducir('workflowdesigner.asignar_al_rol')} value={config.assignee_role} onChange={v => setConfig('assignee_role', v)} placeholder="support_l1" />
        <FieldNumber label={traducir('workflowdesigner.sla_horas')} value={config.sla_hours} onChange={v => setConfig('sla_hours', v)} />
      </>}
      {t === 'decision' && <>
        <FieldText label={traducir('workflowdesigner.expresion')} value={config.expression} onChange={v => setConfig('expression', v)} placeholder="priority == 'P1'" />
      </>}
      {t === 'approval' && <>
        <FieldText label={traducir('workflowdesigner.rol_que_aprueba')} value={config.approver_role} onChange={v => setConfig('approver_role', v)} placeholder="manager" />
        <FieldNumber label={traducir('workflowdesigner.plazo_horas')} value={config.deadline_hours} onChange={v => setConfig('deadline_hours', v)} />
      </>}
      {t === 'wait' && <>
        <FieldNumber label={traducir('workflowdesigner.esperar_minutos')} value={config.wait_minutes} onChange={v => setConfig('wait_minutes', v)} />
        <FieldText label={traducir('workflowdesigner.o_hasta_el_campo')} value={config.until_field} onChange={v => setConfig('until_field', v)} placeholder="due_date" />
      </>}
      {t === 'notify' && <>
        <FieldSelect label={traducir('workflowdesigner.canal')} value={config.channel || 'in_app'} onChange={v => setConfig('channel', v)} options={[
          { v: 'in_app', l: traducir('workflowdesigner.campana') }, { v: 'email', l: traducir('workflowdesigner.campana_correo') },
        ]} />
        <FieldText label={traducir('workflowdesigner.titulo_campo')} value={config.title ?? config.template_id} onChange={v => setConfig('title', v)} placeholder={traducir('workflowdesigner.ph_titulo_aviso')} />
        <FieldTextarea label={traducir('workflowdesigner.mensaje')} value={config.body} onChange={v => setConfig('body', v)} />
        <FieldText label={traducir('workflowdesigner.destinatarios')} value={config.recipients} onChange={v => setConfig('recipients', v)} placeholder="$assignee, $group" />
      </>}
      {t === 'http_call' && <>
        <FieldSelect label={traducir('workflowdesigner.metodo')} value={config.method || 'POST'} onChange={v => setConfig('method', v)} options={[
          { v: 'GET', l: 'GET' }, { v: 'POST', l: 'POST' }, { v: 'PATCH', l: 'PATCH' }, { v: 'DELETE', l: 'DELETE' },
        ]} />
        <FieldText label="URL" value={config.url} onChange={v => setConfig('url', v)} placeholder="https://api.x.com/foo" />
        <FieldTextarea label={traducir('workflowdesigner.cuerpo_json')} value={config.body_template} onChange={v => setConfig('body_template', v)} />
      </>}
      {t === 'create_ticket' && <>
        <FieldText label={traducir('workflowdesigner.cola')} value={config.queue} onChange={v => setConfig('queue', v)} placeholder="support" />
        <FieldText label={traducir('workflowdesigner.plantilla_de_titulo')} value={config.title_template} onChange={v => setConfig('title_template', v)} placeholder={traducir('workflowdesigner.ph_titulo_ticket')} />
        {/* La descripción es obligatoria en el modelo de ticket y no había campo
            para escribirla: el motor se cae al título si se deja en blanco. */}
        <FieldText label={traducir('workflowdesigner.plantilla_de_descripcion')} value={config.description_template} onChange={v => setConfig('description_template', v)} placeholder={traducir('workflowdesigner.creado_por_el_flujo_desde_title')} />
        <FieldSelect label={traducir('workflowdesigner.prioridad')} value={config.priority || 'P3'} onChange={v => setConfig('priority', v)} options={
          ['P1', 'P2', 'P3', 'P4'].map(p => ({ v: p, l: traducir(`workflowdesigner.prio_${p.toLowerCase()}`) }))
        } />
      </>}
    </div>
  )
}

function FieldText({ label, value, onChange, placeholder }: { label: string; value: ValorConfig; onChange: (v: string) => void; placeholder?: string }) {
  const idCampo = useId()
  return (
    <div>
      <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className={labelStyle}>{label}</label>
      <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={value || ''} onChange={e => onChange(e.target.value)} placeholder={placeholder} className={inputStyle} />
    </div>
  )
}
function FieldNumber({ label, value, onChange }: { label: string; value: ValorConfig; onChange: (v: number | null) => void }) {
  const idCampo = useId()
  return (
    <div>
      <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className={labelStyle}>{label}</label>
      <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} type="number" value={value ?? ''} onChange={e => onChange(e.target.value === '' ? null : Number(e.target.value))} className={inputStyle} />
    </div>
  )
}
function FieldSelect({ label, value, onChange, options }: { label: string; value: ValorConfig; onChange: (v: string) => void; options: { v: string; l: string }[] }) {
  const idCampo = useId()
  return (
    <div>
      <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className={labelStyle}>{label}</label>
      <Select suelto placeholder={false} id={`${idCampo}-1`} value={value || ''} onChange={e => onChange(e.target.value)} className="wfd-sel">
        {options.map((o) => <option key={o.v} value={o.v}>{o.l}</option>)}
      </Select>
    </div>
  )
}
function FieldTextarea({ label, value, onChange }: { label: string; value: ValorConfig; onChange: (v: string) => void }) {
  const idCampo = useId()
  return (
    <div>
      <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className={labelStyle}>{label}</label>
      <textarea id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} rows={3} value={value || ''} onChange={e => onChange(e.target.value)} className={`${inputStyle} wfd-input--mono ds-campo-codigo`} />
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

