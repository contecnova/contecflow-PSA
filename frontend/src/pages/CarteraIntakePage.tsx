/**
 * CarteraIntakePage — /portfolio/intake (rev. 173).
 *
 * Intake de propuestas → puntuación por criterios configurables → fases
 * (stage-gate, decididas por el motor de aprobaciones o, sin flujo, por admin
 * o PM) → proyecto. Cada propuesta enseña la capacidad que pide frente a la
 * libre del equipo en su ventana de fechas.
 */
import { Fragment, useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowRightCircle, CheckCircle2, FolderPlus, Inbox, Plus, Settings2, XCircle } from 'lucide-react'
import Page from '../components/ui/Page'
import { Button, EmptyState, Modal, Spinner, StatusBadge, Tabs } from '../components/ui'
import { approvalsApi, carteraApi, type Criterio, type Fase, type Propuesta } from '../services/api'
import { useAppT } from '../i18n/AppLangContext'
import { useToast } from '../context/ToastContext'
import { useAuth } from '../context/AuthContext'
import { useFormatoMoneda } from '../hooks/useFormatoMoneda'
import { extractErr, fmtDate } from '../utils/helpers'
import '../components/planificador/planificador.css'

const KIND: Record<string, 'neutral' | 'warning' | 'info' | 'success' | 'danger' | 'accent'> = {
  draft: 'neutral', in_review: 'warning', in_progress: 'info', approved: 'success', rejected: 'danger', converted: 'accent',
}

export default function CarteraIntakePage() {
  const t = useAppT()
  const gestiona = useAuth().hasRole('admin', 'pm')
  const [tab, setTab] = useState('proposals')
  const [editando, setEditando] = useState<Propuesta | 'nueva' | null>(null)
  return (
    <Page icon={<Inbox size={18} />} title={t('cartera.titulo')} subtitle={t('cartera.subtitulo')}
      actions={<Button icon={<Plus size={13} />} onClick={() => setEditando('nueva')}>{t('cartera.nueva_propuesta')}</Button>}>
      <Tabs items={[
        { id: 'proposals', label: t('cartera.propuestas'), icon: <Inbox size={13} /> },
        ...(gestiona ? [{ id: 'config', label: t('cartera.configuracion'), icon: <Settings2 size={13} /> }] : []),
      ]} active={tab} onChange={setTab} ariaLabel={t('cartera.titulo')} />
      {tab === 'proposals' ? <ListaDePropuestas onEditar={setEditando} /> : <Configuracion />}
      {editando && <FormularioDePropuesta propuesta={editando === 'nueva' ? null : editando} onClose={() => setEditando(null)} />}
    </Page>
  )
}

function ListaDePropuestas({ onEditar }: { onEditar: (p: Propuesta) => void }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const dinero = useFormatoMoneda()
  const gestiona = useAuth().hasRole('admin', 'pm')
  const [estado, setEstado] = useState('')
  const [abierta, setAbierta] = useState<string>('')
  const { data: propuestas = [], isLoading } = useQuery({ queryKey: ['propuestas', estado], queryFn: () => carteraApi.propuestas(estado || undefined) })
  const refrescar = () => qc.invalidateQueries({ queryKey: ['propuestas'] })
  const onError = (e: unknown) => toast.error(extractErr(e, t('cartera.error')))
  const enviar = useMutation({ mutationFn: (id: string) => carteraApi.enviar(id), onSuccess: () => { toast.success(t('cartera.enviada')); refrescar() }, onError })
  const decidir = useMutation({
    mutationFn: ({ id, ok }: { id: string; ok: boolean }) => carteraApi.decidir(id, ok, ok ? undefined : window.prompt(t('cartera.motivo')) ?? undefined),
    onSuccess: refrescar, onError,
  })
  const convertir = useMutation({ mutationFn: (id: string) => carteraApi.convertir(id, {}), onSuccess: () => { toast.success(t('cartera.convertida')); refrescar() }, onError })

  return (
    <div className="plan-stack">
      <div className="plan-row">
        <select className="plan-select" aria-label={t('cartera.filtrar_estado')} value={estado} onChange={e => setEstado(e.target.value)}>
          <option value="">{t('cartera.todos_los_estados')}</option>
          {Object.keys(KIND).map(k => <option key={k} value={k}>{t(`cartera.estado_${k}`)}</option>)}
        </select>
      </div>
      {isLoading ? <Spinner /> : propuestas.length === 0 ? <EmptyState title={t('cartera.sin_propuestas')} description={t('cartera.sin_propuestas_desc')} /> : (
        <div className="plan-card plan-tabla-scroll">
          <table className="plan-tabla">
            <thead>
              <tr>
                <th>{t('cartera.col_propuesta')}</th><th className="plan-num">{t('cartera.col_puntuacion')}</th>
                <th>{t('cartera.col_estado')}</th><th>{t('cartera.col_fase')}</th>
                <th className="plan-num">{t('cartera.col_presupuesto')}</th><th>{t('cartera.col_ventana')}</th><th />
              </tr>
            </thead>
            <tbody>
              {propuestas.map(p => (
                <Fragment key={p.id}>
                  <tr>
                    <td><button type="button" className="plan-chip" onClick={() => setAbierta(a => a === p.id ? '' : p.id)}>{p.title}</button></td>
                    <td className="plan-num">{p.score ?? '—'}</td>
                    <td><StatusBadge kind={KIND[p.status]}>{t(`cartera.estado_${p.status}`)}</StatusBadge></td>
                    <td>{p.current_gate ? `${p.gate_index + 1}/${p.gates_total} · ${p.current_gate.name}` : p.gates_total ? t('cartera.todas_superadas') : '—'}</td>
                    <td className="plan-num">{p.estimated_budget == null ? '—' : dinero(p.estimated_budget)}</td>
                    <td>{p.wanted_start ? `${fmtDate(p.wanted_start)} – ${fmtDate(p.wanted_end)}` : '—'}</td>
                    <td>
                      <span className="plan-row">
                        {['draft', 'in_progress', 'rejected'].includes(p.status) && <Button size="xs" variant="subtle" onClick={() => onEditar(p)}>{t('cartera.editar')}</Button>}
                        {['draft', 'in_progress'].includes(p.status) && <Button size="xs" icon={<ArrowRightCircle size={12} />} onClick={() => enviar.mutate(p.id)}>{t('cartera.enviar_a_fase')}</Button>}
                        {gestiona && p.status === 'in_review' && p.approval_status !== 'pending' && <>
                          <Button size="xs" variant="subtle" icon={<CheckCircle2 size={12} />} onClick={() => decidir.mutate({ id: p.id, ok: true })}>{t('cartera.aprobar_fase')}</Button>
                          <Button size="xs" variant="ghost" icon={<XCircle size={12} />} onClick={() => decidir.mutate({ id: p.id, ok: false })}>{t('cartera.rechazar')}</Button>
                        </>}
                        {p.status === 'in_review' && p.approval_status === 'pending' && <span className="plan-muted">{t('cartera.en_bandeja')}</span>}
                        {gestiona && p.status === 'approved' && <Button size="xs" icon={<FolderPlus size={12} />} onClick={() => convertir.mutate(p.id)}>{t('cartera.convertir')}</Button>}
                        {p.project_id && <Link to={`/projects/${p.project_id}`}>{t('cartera.ver_proyecto')}</Link>}
                      </span>
                    </td>
                  </tr>
                  {abierta === p.id && <tr><td colSpan={7}><CapacidadDePropuesta id={p.id} /></td></tr>}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function CapacidadDePropuesta({ id }: { id: string }) {
  const t = useAppT()
  const { data, isLoading } = useQuery({ queryKey: ['propuesta-capacidad', id], queryFn: () => carteraApi.capacidad(id) })
  if (isLoading) return <Spinner />
  if (!data || data.roles.length === 0) return <p className="plan-muted">{t('cartera.sin_roles')}</p>
  return (
    <div className="plan-stack">
      <div className={`plan-aviso${data.fits ? ' plan-aviso--ok' : ' plan-aviso--peligro'}`}>
        {data.fits ? t('cartera.cabe', { desde: fmtDate(data.from), hasta: fmtDate(data.to) }) : t('cartera.no_cabe', { desde: fmtDate(data.from), hasta: fmtDate(data.to) })}
      </div>
      <table className="plan-tabla">
        <thead><tr><th>{t('cartera.col_rol')}</th><th className="plan-num">{t('cartera.col_pedidas')}</th><th className="plan-num">{t('cartera.col_personas')}</th><th className="plan-num">{t('cartera.col_libres')}</th><th className="plan-num">{t('cartera.col_hueco')}</th></tr></thead>
        <tbody>
          {data.roles.map(r => (
            <tr key={r.role}><td>{r.role}</td><td className="plan-num">{r.needed_hours}</td><td className="plan-num">{r.people}</td>
              <td className="plan-num">{r.free_hours}</td><td className={`plan-num ${r.gap_hours > 0 ? 'plan-critica' : 'plan-ok'}`}>{r.gap_hours}</td></tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function FormularioDePropuesta({ propuesta, onClose }: { propuesta: Propuesta | null; onClose: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { data: criterios = [] } = useQuery({ queryKey: ['cartera-criterios'], queryFn: carteraApi.criterios })
  const [f, setF] = useState({
    title: propuesta?.title ?? '', description: propuesta?.description ?? '',
    estimated_budget: propuesta?.estimated_budget ?? '', estimated_hours: propuesta?.estimated_hours ?? '',
    wanted_start: propuesta?.wanted_start ?? '', wanted_end: propuesta?.wanted_end ?? '',
  })
  const [roles, setRoles] = useState(propuesta?.roles_needed ?? [])
  const [notas, setNotas] = useState<Record<string, number>>(propuesta?.scores ?? {})
  const guardar = useMutation({
    mutationFn: () => {
      const cuerpo = {
        title: f.title.trim(), description: f.description || null,
        estimated_budget: f.estimated_budget === '' ? null : Number(f.estimated_budget),
        estimated_hours: f.estimated_hours === '' ? null : Number(f.estimated_hours),
        wanted_start: f.wanted_start || null, wanted_end: f.wanted_end || null,
        roles_needed: roles.filter(r => r.role.trim()), scores: notas,
      }
      return propuesta ? carteraApi.editarPropuesta(propuesta.id, cuerpo) : carteraApi.crearPropuesta(cuerpo)
    },
    onSuccess: () => { toast.success(t('cartera.guardada')); qc.invalidateQueries({ queryKey: ['propuestas'] }); onClose() },
    onError: e => toast.error(extractErr(e, t('cartera.error'))),
  })
  const campo = (k: keyof typeof f, tipo = 'text') => (
    <input className="plan-input" type={tipo} value={String(f[k] ?? '')} onChange={e => setF(x => ({ ...x, [k]: e.target.value }))} />
  )
  return (
    <Modal open onClose={onClose} title={propuesta ? t('cartera.editar_propuesta') : t('cartera.nueva_propuesta')}>
      <form className="plan-stack" onSubmit={e => { e.preventDefault(); if (f.title.trim()) guardar.mutate() }}>
        <div className="plan-form">
          <label>{t('cartera.campo_titulo')}{campo('title')}</label>
          <label>{t('cartera.campo_presupuesto')}{campo('estimated_budget', 'number')}</label>
          <label>{t('cartera.campo_horas')}{campo('estimated_hours', 'number')}</label>
          <label>{t('cartera.campo_inicio')}{campo('wanted_start', 'date')}</label>
          <label>{t('cartera.campo_fin')}{campo('wanted_end', 'date')}</label>
        </div>
        <label className="plan-muted">{t('cartera.campo_descripcion')}
          <textarea className="plan-input plan-textarea" value={f.description} onChange={e => setF(x => ({ ...x, description: e.target.value }))} />
        </label>
        <div className="plan-card plan-stack">
          <h3 className="plan-card__titulo">{t('cartera.roles_que_pide')}</h3>
          {roles.map((r, i) => (
            <div key={i} className="plan-row">
              <input className="plan-input" aria-label={t('cartera.col_rol')} value={r.role} onChange={e => setRoles(rs => rs.map((x, j) => j === i ? { ...x, role: e.target.value } : x))} />
              <input type="number" min={0} className="plan-input plan-input--num" aria-label={t('cartera.col_pedidas')} value={r.hours}
                onChange={e => setRoles(rs => rs.map((x, j) => j === i ? { ...x, hours: Number(e.target.value) } : x))} />
              <Button size="xs" variant="ghost" onClick={() => setRoles(rs => rs.filter((_, j) => j !== i))}>{t('cartera.quitar')}</Button>
            </div>
          ))}
          <div><Button size="xs" variant="subtle" icon={<Plus size={12} />} onClick={() => setRoles(rs => [...rs, { role: '', hours: 0 }])}>{t('cartera.anadir_rol')}</Button></div>
        </div>
        {criterios.filter(c => c.is_active).length > 0 && (
          <div className="plan-card plan-stack">
            <h3 className="plan-card__titulo">{t('cartera.puntuacion')}</h3>
            {criterios.filter(c => c.is_active).map(c => (
              <label key={c.id} className="plan-row plan-row--between">
                <span>{c.name}{c.inverse ? ` · ${t('cartera.inverso')}` : ''} <span className="plan-muted">{t('cartera.peso', { n: c.weight })}</span></span>
                <input type="range" min={0} max={10} step={1} value={notas[c.id] ?? 0} aria-label={c.name}
                  onChange={e => setNotas(n => ({ ...n, [c.id]: Number(e.target.value) }))} />
                <span className="plan-num">{notas[c.id] ?? 0}</span>
              </label>
            ))}
          </div>
        )}
        <div className="plan-row"><Button type="submit" loading={guardar.isPending} disabled={!f.title.trim()}>{t('cartera.guardar')}</Button></div>
      </form>
    </Modal>
  )
}

function Configuracion() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { data: criterios = [] } = useQuery({ queryKey: ['cartera-criterios'], queryFn: carteraApi.criterios })
  const { data: fases = [] } = useQuery({ queryKey: ['cartera-fases'], queryFn: carteraApi.fases })
  const { data: flujos = [] } = useQuery({
    queryKey: ['approval-workflows', 'portfolio_gate'],
    queryFn: () => approvalsApi.listWorkflows({ entity_type: 'portfolio_gate' }).then(r => r.data),
  })
  const onError = (e: unknown) => toast.error(extractErr(e, t('cartera.error')))
  const guardarCriterio = useMutation({
    mutationFn: ({ id, b }: { id?: string; b: Partial<Criterio> }) => id ? carteraApi.editarCriterio(id, b) : carteraApi.crearCriterio(b),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['cartera-criterios'] }), onError,
  })
  const guardarFase = useMutation({
    mutationFn: ({ id, b }: { id?: string; b: Partial<Fase> }) => id ? carteraApi.editarFase(id, b) : carteraApi.crearFase(b),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['cartera-fases'] }), onError,
  })
  const nuevo = (clave: string) => window.prompt(t(clave))?.trim()
  return (
    <div className="plan-stack">
      <div className="plan-card plan-stack">
        <div className="plan-row plan-row--between">
          <h3 className="plan-card__titulo">{t('cartera.criterios')}</h3>
          <Button size="xs" icon={<Plus size={12} />} onClick={() => { const n = nuevo('cartera.nombre_criterio'); if (n) guardarCriterio.mutate({ b: { name: n, weight: 1 } }) }}>{t('cartera.anadir_criterio')}</Button>
        </div>
        <table className="plan-tabla">
          <thead><tr><th>{t('cartera.col_nombre')}</th><th className="plan-num">{t('cartera.col_peso')}</th><th>{t('cartera.inverso')}</th><th>{t('cartera.activo')}</th></tr></thead>
          <tbody>
            {criterios.map(c => (
              <tr key={c.id}>
                <td>{c.name}</td>
                <td className="plan-num"><input type="number" min={0} step={0.5} className="plan-input plan-input--num" aria-label={t('cartera.col_peso')} defaultValue={c.weight}
                  onBlur={e => Number(e.target.value) !== c.weight && guardarCriterio.mutate({ id: c.id, b: { weight: Number(e.target.value) } })} /></td>
                <td><input type="checkbox" aria-label={t('cartera.inverso')} checked={c.inverse} onChange={e => guardarCriterio.mutate({ id: c.id, b: { inverse: e.target.checked } })} /></td>
                <td><input type="checkbox" aria-label={t('cartera.activo')} checked={c.is_active} onChange={e => guardarCriterio.mutate({ id: c.id, b: { is_active: e.target.checked } })} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="plan-card plan-stack">
        <div className="plan-row plan-row--between">
          <h3 className="plan-card__titulo">{t('cartera.fases')}</h3>
          <Button size="xs" icon={<Plus size={12} />} onClick={() => { const n = nuevo('cartera.nombre_fase'); if (n) guardarFase.mutate({ b: { name: n, sort_order: fases.length + 1 } }) }}>{t('cartera.anadir_fase')}</Button>
        </div>
        <p className="plan-muted">{t('cartera.fases_ayuda')}</p>
        <table className="plan-tabla">
          <thead><tr><th>{t('cartera.col_orden')}</th><th>{t('cartera.col_nombre')}</th><th className="plan-num">{t('cartera.col_minimo')}</th><th>{t('cartera.col_flujo')}</th><th>{t('cartera.activo')}</th></tr></thead>
          <tbody>
            {fases.map(g => (
              <tr key={g.id}>
                <td className="plan-num">{g.sort_order}</td>
                <td>{g.name}</td>
                <td className="plan-num"><input type="number" min={0} max={100} className="plan-input plan-input--num" aria-label={t('cartera.col_minimo')} defaultValue={g.min_score ?? ''}
                  onBlur={e => guardarFase.mutate({ id: g.id, b: { min_score: e.target.value === '' ? null : Number(e.target.value) } })} /></td>
                <td>
                  <select className="plan-select" aria-label={t('cartera.col_flujo')} value={g.workflow_id ?? ''}
                    onChange={e => guardarFase.mutate({ id: g.id, b: { workflow_id: e.target.value || null } })}>
                    <option value="">{t('cartera.flujo_por_defecto')}</option>
                    {flujos.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
                  </select>
                </td>
                <td><input type="checkbox" aria-label={t('cartera.activo')} checked={g.is_active} onChange={e => guardarFase.mutate({ id: g.id, b: { is_active: e.target.checked } })} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
