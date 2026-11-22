/**
 * CarteraIntakePage — /portfolio/intake (rev. 173).
 *
 * Intake de propuestas → puntuación por criterios configurables → fases
 * (stage-gate, decididas por el motor de aprobaciones o, sin flujo, por admin
 * o PM) → proyecto. Cada propuesta enseña la capacidad que pide frente a la
 * libre del equipo en su ventana de fechas.
 *
 * 16-11-2026: pasada de diseño. Título = el del menú; el filtro de estado va
 * en una barra bajo la cabecera con el campo del kit; vacío con icono y botón;
 * tarjetas `ds-card`; el formulario usa Input del kit (antes campos propios
 * pequeños); el enlace «Ver proyecto» toma el color de acento, no el azul del
 * navegador.
 *
 * 19-11-2026: la pestaña «Configuración» (criterios y fases) vive en
 * Configuración → Proyectos y trabajo → Entrada a la cartera
 * (`/settings/cartera`, components/cartera/ConfigCartera.tsx). Aquí no hay
 * botón «Configurar» y `?tab=config` redirige allí.
 */
import { Fragment, useState } from 'react'
import { Link, Navigate, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowRightCircle, CheckCircle2, FolderPlus, Inbox, Plus, XCircle } from 'lucide-react'
import Page from '../components/ui/Page'
import { Button, EmptyState, Input, Modal, Spinner, StatusBadge, Pulsable, Select, TablaSimple, useErroresDeCampo, Textarea } from '../components/ui'
import { carteraApi, type Propuesta } from '../services/api'
import { useAppT } from '../i18n/AppLangContext'
import { useToast } from '../context/ToastContext'
import { useConfirm } from '../context/ConfirmContext'
import { useAuth } from '../context/AuthContext'
import { useFormatoMoneda } from '../hooks/useFormatoMoneda'
import { extractErr, fmtDate } from '../utils/helpers'
import FiltroTipoDeCliente, { type TipoDeCliente } from '../components/FiltroTipoDeCliente'
import '../components/planificador/planificador.css'
import './CarteraIntakePage.css'

const KIND: Record<string, 'neutral' | 'warning' | 'info' | 'success' | 'danger' | 'accent'> = {
  draft: 'neutral', in_review: 'warning', in_progress: 'info', approved: 'success', rejected: 'danger', converted: 'accent',
}

export default function CarteraIntakePage() {
  const t = useAppT()
  const [searchParams] = useSearchParams()
  const [editando, setEditando] = useState<Propuesta | 'nueva' | null>(null)
  // La configuración vive en Configuración (19-11-2026): los enlaces antiguos redirigen.
  if (searchParams.get('tab') === 'config') return <Navigate to="/settings/cartera" replace />
  return (
    <Page icon={<Inbox size={18} />} title={t('nav.portfolio_intake')} subtitle={t('cartera.subtitulo')}
      actions={<Button icon={<Plus size={13} />} onClick={() => setEditando('nueva')}>{t('cartera.nueva_propuesta')}</Button>}>
      <ListaDePropuestas onEditar={setEditando} onNueva={() => setEditando('nueva')} />
      {editando && <FormularioDePropuesta propuesta={editando === 'nueva' ? null : editando} onClose={() => setEditando(null)} />}
    </Page>
  )
}

function ListaDePropuestas({ onEditar, onNueva }: { onEditar: (p: Propuesta) => void; onNueva: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const { pedirTexto } = useConfirm()
  const qc = useQueryClient()
  const dinero = useFormatoMoneda()
  const gestiona = useAuth().puede('cartera.gestionar')
  const [estado, setEstado] = useState('')
  const [tipo, setTipo] = useState<TipoDeCliente>('')
  const [abierta, setAbierta] = useState<string>('')
  const { data: propuestas = [], isLoading } = useQuery({
    queryKey: ['propuestas', estado, tipo],
    queryFn: () => carteraApi.propuestas(estado || undefined, tipo || undefined),
  })
  const refrescar = () => qc.invalidateQueries({ queryKey: ['propuestas'] })
  const onError = (e: unknown) => toast.error(extractErr(e, t('cartera.error')))
  const enviar = useMutation({ mutationFn: (id: string) => carteraApi.enviar(id), onSuccess: () => { toast.success(t('cartera.enviada')); refrescar() }, onError })
  const decidir = useMutation({
    mutationFn: ({ id, ok, motivo }: { id: string; ok: boolean; motivo?: string }) => carteraApi.decidir(id, ok, motivo),
    onSuccess: refrescar, onError,
  })
  // Rechazar pide el motivo (opcional); cancelar el diálogo no rechaza.
  const rechazar = async (id: string) => {
    const motivo = await pedirTexto({ message: t('cartera.motivo') })
    if (motivo !== null) decidir.mutate({ id, ok: false, motivo: motivo.trim() || undefined })
  }
  const convertir = useMutation({ mutationFn: (id: string) => carteraApi.convertir(id, {}), onSuccess: () => { toast.success(t('cartera.convertida')); refrescar() }, onError })

  return (
    <div className="u-stack-16">
      <div className="ds-toolbar">
        <Select suelto placeholder={false} className="ds-input cit-filtro" aria-label={t('cartera.filtrar_estado')} value={estado} onChange={e => setEstado(e.target.value)}>
          <option value="">{t('cartera.todos_los_estados')}</option>
          {Object.keys(KIND).map(k => <option key={k} value={k}>{t(`cartera.estado_${k}`)}</option>)}
        </Select>
        <FiltroTipoDeCliente className="ds-input cit-filtro" value={tipo} onChange={setTipo} />
      </div>
      {isLoading ? <Spinner /> : propuestas.length === 0 ? (
        <EmptyState icon={<Inbox size={28} />} title={t('cartera.sin_propuestas')} description={t('cartera.sin_propuestas_desc')}
          ctaLabel={t('cartera.nueva_propuesta')} onCta={onNueva} />
      ) : (
        <div className="ds-card cit-tabla-card plan-tabla-scroll">
          <TablaSimple claseTabla="plan-tabla">
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
                    <td>
                      <Pulsable type="button" className="plan-chip" onClick={() => setAbierta(a => a === p.id ? '' : p.id)}>{p.title}</Pulsable>
                      {p.client_name && <div className="plan-muted">{p.client_name}{p.client_kind === 'interno' ? ` · ${t('internos.filtro_internos')}` : ''}</div>}
                    </td>
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
                          <Button size="xs" variant="ghost" icon={<XCircle size={12} />} onClick={() => rechazar(p.id)}>{t('cartera.rechazar')}</Button>
                        </>}
                        {p.status === 'in_review' && p.approval_status === 'pending' && <span className="plan-muted">{t('cartera.en_bandeja')}</span>}
                        {gestiona && p.status === 'approved' && <Button size="xs" icon={<FolderPlus size={12} />} onClick={() => convertir.mutate(p.id)}>{t('cartera.convertir')}</Button>}
                        {p.project_id && <Link className="cit-enlace" to={`/projects/${p.project_id}`}>{t('cartera.ver_proyecto')}</Link>}
                      </span>
                    </td>
                  </tr>
                  {abierta === p.id && <tr><td colSpan={7}><CapacidadDePropuesta id={p.id} /></td></tr>}
                </Fragment>
              ))}
            </tbody>
          </TablaSimple>
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
      <TablaSimple claseTabla="plan-tabla">
        <thead><tr><th>{t('cartera.col_rol')}</th><th className="plan-num">{t('cartera.col_pedidas')}</th><th className="plan-num">{t('cartera.col_personas')}</th><th className="plan-num">{t('cartera.col_libres')}</th><th className="plan-num">{t('cartera.col_hueco')}</th></tr></thead>
        <tbody>
          {data.roles.map(r => (
            <tr key={r.role}><td>{r.role}</td><td className="plan-num">{r.needed_hours}</td><td className="plan-num">{r.people}</td>
              <td className="plan-num">{r.free_hours}</td><td className={`plan-num ${r.gap_hours > 0 ? 'plan-critica' : 'plan-ok'}`}>{r.gap_hours}</td></tr>
          ))}
        </tbody>
      </TablaSimple>
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
  const camposB = useErroresDeCampo()
  const msgB = (k: string) => camposB.de(k) ? <div className="u-field-error">{camposB.de(k)}</div> : null
  const guardar = useMutation({
    onMutate: () => camposB.limpiar(),
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
    onError: (e: unknown) => { camposB.recoger(e); toast.error(extractErr(e, t('cartera.error'))) },
  })
  const campo = (k: keyof typeof f, etiqueta: string, tipo = 'text') => (
    <Input label={etiqueta} type={tipo} value={String(f[k] ?? '')} onChange={e => setF(x => ({ ...x, [k]: e.target.value }))} />
  )
  return (
    <Modal open onClose={onClose} title={propuesta ? t('cartera.editar_propuesta') : t('cartera.nueva_propuesta')}>
      <form className="plan-stack" onSubmit={e => { e.preventDefault(); if (f.title.trim()) guardar.mutate() }}>
        <div className="plan-form">
          {campo('title', t('cartera.campo_titulo'))}
          {campo('estimated_budget', t('cartera.campo_presupuesto'), 'number')}
          {campo('estimated_hours', t('cartera.campo_horas'), 'number')}
          {campo('wanted_start', t('cartera.campo_inicio'), 'date')}
          {campo('wanted_end', t('cartera.campo_fin'), 'date')}
        </div>
        <div className="ui-field">
          <label className="uiinde-estiloetiqueta" htmlFor="cit-descripcion">{t('cartera.campo_descripcion')}</label>
          <Textarea id="cit-descripcion" value={f.description} onChange={e => { camposB.limpiar('description'); setF(x => ({ ...x, description: e.target.value })) }} inputClassName="plan-textarea" />{msgB('description')}
        </div>
        <div className="ds-card plan-stack">
          <h3 className="plan-card__titulo">{t('cartera.roles_que_pide')}</h3>
          {roles.map((r, i) => (
            <div key={i} className="plan-row">
              <input className="ds-input cit-rol" aria-label={t('cartera.col_rol')} value={r.role} onChange={e => setRoles(rs => rs.map((x, j) => j === i ? { ...x, role: e.target.value } : x))} />{msgB('role')}
              <input type="number" min={0} className="ds-input cit-num" aria-label={t('cartera.col_pedidas')} value={r.hours}
                onChange={e => setRoles(rs => rs.map((x, j) => j === i ? { ...x, hours: Number(e.target.value) } : x))} />{msgB('hours')}
              <Button size="xs" variant="ghost" onClick={() => setRoles(rs => rs.filter((_, j) => j !== i))}>{t('cartera.quitar')}</Button>
            </div>
          ))}
          <div><Button size="xs" variant="subtle" icon={<Plus size={12} />} onClick={() => setRoles(rs => [...rs, { role: '', hours: 0 }])}>{t('cartera.anadir_rol')}</Button></div>
        </div>
        {criterios.filter(c => c.is_active).length > 0 && (
          <div className="ds-card plan-stack">
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
        <div className="cit-acciones"><Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button><Button type="submit" loading={guardar.isPending} disabled={!f.title.trim()}>{t('cartera.guardar')}</Button></div>
      </form>
    </Modal>
  )
}

