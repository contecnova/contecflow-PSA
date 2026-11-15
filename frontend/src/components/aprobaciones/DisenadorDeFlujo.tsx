/**
 * Diseñador gráfico del flujo de aprobación e información (tarea #26).
 *
 * Nodos: inicio, aprobar (persona, rol, responsable, N-ésimo responsable,
 * departamento o grupo; quórum, caducidad y escalado), informar, condición
 * (sí/no con el catálogo del dominio), dividir en paralelo y unir, fin. Al
 * guardar, el servidor valida y lo compila a los pasos del motor de
 * aprobaciones de siempre (no hay un segundo motor).
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { ReactFlowProvider, addEdge, useEdgesState, useNodesState } from '@xyflow/react'
import type { Connection, Edge, Node, NodeProps } from '@xyflow/react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Bell, CheckCircle, GitBranch, GitMerge, Play, Save, Split, Square, UserCheck } from 'lucide-react'
import { politicasApi } from '../../services/api'
import type { DatosDeNodoDeFlujo, GrupoDeCondiciones, TipoDeNodoDeFlujo } from '../../services/api/tipos-politicas'
import { Button, Spinner } from '../ui'
import { useToast } from '../../context/ToastContext'
import { extractErr } from '../../utils/helpers'
import { LienzoDeFlujo, NodoDeFlujo } from '../flujos/LienzoDeFlujo'
import ConstructorDeCondiciones, { grupoVacio } from '../politicas/ConstructorDeCondiciones'
import { SelectorDeAprobador } from '../politicas/EditorDeResultados'
import { UserSelect } from '../ui/EntitySelect'
import { useCatalogo, useTextos } from '../politicas/comun'
import '../politicas/politicas.css'

type DatosNodo = DatosDeNodoDeFlujo & { tipo: TipoDeNodoDeFlujo; error?: string | null }
type NodoAp = Node<DatosNodo>

const VISUAL: Record<TipoDeNodoDeFlujo, { color: string; icono: JSX.Element }> = {
  start: { color: 'var(--success)', icono: <Play size={12} /> },
  end: { color: 'var(--danger)', icono: <Square size={12} /> },
  approve: { color: 'var(--purple, var(--accent))', icono: <UserCheck size={12} /> },
  inform: { color: 'var(--chart-teal, var(--accent))', icono: <Bell size={12} /> },
  condition: { color: 'var(--warning)', icono: <GitBranch size={12} /> },
  split: { color: 'var(--sky-blue, var(--accent))', icono: <Split size={12} /> },
  join: { color: 'var(--sky-blue, var(--accent))', icono: <GitMerge size={12} /> },
}
const PALETA: TipoDeNodoDeFlujo[] = ['approve', 'inform', 'condition', 'split', 'join', 'end']

function Nodo({ data, selected }: NodeProps<NodoAp>) {
  const { t } = useTextos()
  const v = VISUAL[data.tipo]
  const salidas = data.tipo === 'end' ? []
    : data.tipo === 'condition' ? [{ id: 'si', etiqueta: t('pol.si') }, { id: 'no', etiqueta: t('pol.no') }]
    : [{ id: '', etiqueta: '' }]
  return <NodoDeFlujo color={v.color} icono={v.icono} tipo={t(`pol.nodo_${data.tipo}`)} nombre={data.nombre || t(`pol.nodo_${data.tipo}`)}
    seleccionado={selected} entrada={data.tipo !== 'start'} salidas={salidas} error={data.error} />
}
const TIPOS_DE_NODO = { ap: Nodo }

export default function DisenadorDeFlujo(props: { workflowId: string; onCerrar: () => void }) {
  return <ReactFlowProvider><Editor {...props} /></ReactFlowProvider>
}

function Editor({ workflowId, onCerrar }: { workflowId: string; onCerrar: () => void }) {
  const { t } = useTextos()
  const toast = useToast()
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['approval-diagram', workflowId], queryFn: () => politicasApi.diagrama(workflowId) })
  const [nodes, setNodes, onNodesChange] = useNodesState<NodoAp>([])
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([])
  const [selId, setSelId] = useState<string | null>(null)
  const [errores, setErrores] = useState<{ nodo: string | null; mensaje: string }[]>([])

  useEffect(() => {
    if (!q.data) return
    setNodes(q.data.nodos.map(n => ({ id: n.id, type: 'ap', position: n.position, data: { ...n.data, tipo: n.type } })))
    setEdges(q.data.aristas.map(a => ({ ...a, sourceHandle: a.sourceHandle ?? null, label: a.sourceHandle ? t(`pol.${a.sourceHandle}`) : undefined })))
  }, [q.data, setNodes, setEdges, t])

  const marcar = useCallback((errs: { nodo: string | null; mensaje: string }[]) => {
    setErrores(errs)
    setNodes(ns => ns.map(n => ({ ...n, data: { ...n.data, error: errs.find(e => e.nodo === n.id)?.mensaje ?? null } })))
  }, [setNodes])

  const aDiagrama = () => ({
    nodos: nodes.map(n => {
      const { tipo, error: _e, ...data } = n.data
      return { id: n.id, type: tipo, position: n.position, data }
    }),
    aristas: edges.map(e => ({ id: e.id, source: e.source, target: e.target, sourceHandle: (e.sourceHandle as 'si' | 'no' | null) || null })),
  })
  const alFallar = (e: unknown) => {
    const d = (e as { response?: { data?: { detail?: { errors?: { nodo: string | null; mensaje: string }[] } } } })?.response?.data?.detail
    if (d && typeof d === 'object' && Array.isArray(d.errors)) marcar(d.errors)
    toast.error(extractErr(e, t('pol.error_guardar')))
  }
  const comprobar = useMutation({
    mutationFn: () => politicasApi.comprobarDiagrama(workflowId, aDiagrama()),
    onSuccess: r => { marcar(r.errores); if (r.valido) toast.success(t('pol.diagrama_valido', { n: r.pasos.length })) },
    onError: alFallar,
  })
  const guardar = useMutation({
    mutationFn: () => politicasApi.guardarDiagrama(workflowId, aDiagrama()),
    onSuccess: r => {
      marcar([]); toast.success(t('pol.diagrama_guardado', { n: r.pasos ?? 0 }))
      qc.invalidateQueries({ queryKey: ['approval-workflow', workflowId] })
      qc.invalidateQueries({ queryKey: ['approval-diagram', workflowId] })
    },
    onError: alFallar,
  })
  const onConnect = useCallback((c: Connection) => setEdges(es => addEdge({
    ...c, id: `e-${c.source}-${c.sourceHandle ?? ''}-${c.target}`, label: c.sourceHandle ? t(`pol.${c.sourceHandle}`) : undefined,
  }, es.filter(e => !(e.source === c.source && (e.sourceHandle ?? null) === (c.sourceHandle ?? null)
      && !['split'].includes(nodes.find(n => n.id === c.source)?.data.tipo ?? ''))))), [setEdges, nodes, t])

  const anadir = (tipo: TipoDeNodoDeFlujo) => {
    const id = `${tipo}-${Math.random().toString(36).slice(2, 8)}`
    const base: DatosNodo = { tipo }
    if (tipo === 'approve' || tipo === 'inform') Object.assign(base, { nombre: '', approver_type: 'role', required_approvals: 1, timeout_hours: 72, on_timeout: 'escalate' })
    if (tipo === 'condition') Object.assign(base, { nombre: '', arbol: grupoVacio() })
    const x = Math.max(0, ...nodes.map(n => n.position.x)) + 200
    setNodes(ns => [...ns, { id, type: 'ap', position: { x, y: 120 }, data: base }])
    setSelId(id)
  }
  const sel = useMemo(() => nodes.find(n => n.id === selId) ?? null, [nodes, selId])
  const cambiar = (patch: Partial<DatosNodo>) => setNodes(ns => ns.map(n => (n.id === selId ? { ...n, data: { ...n.data, ...patch } } : n)))

  if (q.isLoading) return <Spinner label={t('pol.cargando')} />
  if (q.isError) return <div role="alert" className="pol-error">{extractErr(q.error, t('pol.error_cargar'))}</div>
  return (
    <div className="u-stack-10">
      <div className="pol-fila">
        <Button variant="ghost" icon={<ArrowLeft size={14} />} onClick={onCerrar}>{t('pol.volver')}</Button>
        <span className="pol-titulo">{t('pol.disenador')}</span>
        {q.data?.generado && <span className="pol-chip">{t('pol.generado_de_pasos')}</span>}
        {!!q.data?.solicitudes_pendientes && <span className="pol-chip pol-chip--review">{t('pol.pendientes_afectadas', { n: q.data.solicitudes_pendientes })}</span>}
        <span className="u-flex1" />
        <Button variant="secondary" icon={<CheckCircle size={14} />} loading={comprobar.isPending} onClick={() => comprobar.mutate()}>{t('pol.validar')}</Button>
        <Button icon={<Save size={14} />} loading={guardar.isPending} onClick={() => guardar.mutate()}>{t('pol.guardar_diagrama')}</Button>
      </div>
      <p className="pol-ayuda">{t('pol.disenador_ayuda')}</p>
      <div className="flujo-editor">
        <nav className="flujo-paleta" aria-label={t('pol.paleta')}>
          {PALETA.map(tipo => (
            <button key={tipo} type="button" style={{ ['--flujo-color' as string]: VISUAL[tipo].color }} onClick={() => anadir(tipo)}>
              {VISUAL[tipo].icono} {t(`pol.nodo_${tipo}`)}
            </button>
          ))}
          <p className="pol-ayuda">{t('pol.paleta_ayuda')}</p>
        </nav>
        <LienzoDeFlujo nodes={nodes} edges={edges} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} onConnect={onConnect}
          nodeTypes={TIPOS_DE_NODO as never} onSeleccion={n => setSelId(n?.id ?? null)} etiqueta={t('pol.lienzo')}
          colorDeNodo={n => VISUAL[n.data.tipo]?.color ?? 'var(--text-3)'}>
          {errores.length > 0 && (
            <ul className="flujo-aviso" role="alert" aria-label={t('pol.hay_errores', { n: errores.length })}>
              {errores.map((e, i) => <li key={i}>{e.mensaje}</li>)}
            </ul>
          )}
        </LienzoDeFlujo>
        <aside className="flujo-propiedades" aria-label={t('pol.propiedades')}>
          {sel ? <Propiedades nodo={sel} dominio={q.data?.dominio ?? null} onChange={cambiar} />
            : <p className="pol-ayuda">{t('pol.elige_un_nodo')}</p>}
        </aside>
      </div>
    </div>
  )
}

function Propiedades({ nodo, dominio, onChange }: { nodo: NodoAp; dominio: string | null; onChange: (p: Partial<DatosNodo>) => void }) {
  const { t } = useTextos()
  const catalogo = useCatalogo().data
  const d = nodo.data
  const dom = catalogo?.dominios.find(x => x.clave === dominio)
  if (d.tipo === 'start' || d.tipo === 'end' || d.tipo === 'split' || d.tipo === 'join') {
    return <p className="pol-ayuda">{t(`pol.ayuda_nodo_${d.tipo}`)}</p>
  }
  return (
    <div className="u-stack-10">
      <label><span className="pol-etiqueta">{t('pol.nombre')}</span>
        <input className="pol-campo pol-campo--ancho" value={d.nombre ?? ''} onChange={e => onChange({ nombre: e.target.value })} /></label>
      {d.tipo === 'condition' ? (
        dom ? <ConstructorDeCondiciones dominio={dom} valor={d.arbol ?? null} onChange={(g: GrupoDeCondiciones) => onChange({ arbol: g })} />
          : <p className="pol-error">{t('pol.sin_catalogo')}</p>
      ) : (
        <>
          <span className="pol-etiqueta">{d.tipo === 'approve' ? t('pol.quien_aprueba') : t('pol.a_quien_se_informa')}</span>
          <SelectorDeAprobador paso={{ approver_type: d.approver_type ?? 'role', approver_role: d.approver_role, approver_user_id: d.approver_user_id,
            approver_department: d.approver_department, approver_group_id: d.approver_group_id, approver_level: d.approver_level }}
            onChange={p => onChange({ ...p })} />
          {d.tipo === 'approve' && (
            <>
              <label className="pol-fila"><span className="pol-ayuda">{t('pol.quorum')}</span>
                <input type="number" min={1} className="pol-campo pol-campo--corto" value={d.required_approvals ?? 1}
                  onChange={e => onChange({ required_approvals: Number(e.target.value) || 1 })} /></label>
              <label className="pol-fila"><span className="pol-ayuda">{t('pol.caduca_en_horas')}</span>
                <input type="number" min={1} className="pol-campo pol-campo--corto" value={d.timeout_hours ?? 72}
                  onChange={e => onChange({ timeout_hours: Number(e.target.value) || 72 })} /></label>
              <label className="pol-fila"><span className="pol-ayuda">{t('pol.al_caducar')}</span>
                <select className="pol-campo" value={d.on_timeout ?? 'escalate'} onChange={e => onChange({ on_timeout: e.target.value as DatosNodo['on_timeout'] })}>
                  {(['escalate', 'auto_approve', 'reject'] as const).map(o => <option key={o} value={o}>{t(`pol.caducar_${o}`)}</option>)}
                </select></label>
              {d.on_timeout === 'escalate' && (
                <div><span className="pol-etiqueta">{t('pol.escalar_a')}</span>
                  <UserSelect value={d.escalate_to_user_id ?? ''} onChange={id => onChange({ escalate_to_user_id: id || null })} placeholder={t('pol.elige_persona')} /></div>
              )}
              <label className="pol-fila"><span className="pol-ayuda">{t('pol.recordar_cada')}</span>
                <input type="number" min={0} className="pol-campo pol-campo--corto" value={d.reminder_hours ?? ''}
                  onChange={e => onChange({ reminder_hours: e.target.value ? Number(e.target.value) : null })} /></label>
              <label className="pol-chip"><input type="checkbox" checked={!!d.requires_attachment}
                onChange={e => onChange({ requires_attachment: e.target.checked })} />{t('pol.exige_adjunto')}</label>
            </>
          )}
        </>
      )}
    </div>
  )
}
