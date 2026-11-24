/**
 * Clientes internos (22-11-2026): ficha de gestión de una unidad interna.
 *
 * - Personas deducidas de RR. HH. (no se copian) y designaciones
 *   (usuario clave, finanzas, delegado).
 * - Coste por fuente y líneas del periodo, presupuesto del año y TCO de sus aplicaciones.
 * - SLA/OLA medido y satisfacción NPS/CSAT (sin nombres de quien responde).
 * - Plan de adopción y formación (CRUD).
 * Ver docs/CLIENTES_INTERNOS.md §3, §4 y §6.
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Pencil, Plus, Trash2, X } from 'lucide-react'
import { Button, Card, IconButton, Input, KpiCard, Modal, Select, Spinner, TablaSimple } from '../../components/ui'
import StatusBadge from '../../components/ui/StatusBadge'
import { confirmar } from '../../context/ConfirmContext'
import { useToast } from '../../context/ToastContext'
import { clientesInternosApi } from '../../services/api/clientesInternos'
import type { AdopcionIn, ElementoDeAdopcion, RolDesignable } from '../../services/api/clientesInternos'
import { useFormatoMoneda } from '../../hooks/useFormatoMoneda'
import { extractErr, fmtDate, fmtNumber } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { Semaforo, useOpcionesInternas, useT } from './comunes'
import {
  ESTADOS_DE_ADOPCION, FUENTES_DE_COSTE, ROLES_DESIGNABLES, TIPOS_DE_ADOPCION, TONO_ADOPCION, etiquetaInterna, numeroONull,
} from './logica'

const inicioDeAnio = (y: number) => `${y}-01-01`
const finDeAnio = (y: number) => `${y}-12-31`

function Personas({ cid }: { cid: string }) {
  const t = useT()
  const toast = useToast()
  const qc = useQueryClient()
  const op = useOpcionesInternas()
  const [nuevo, setNuevo] = useState<{ user_id: string; role: RolDesignable }>({ user_id: '', role: 'usuario_clave' })
  const { data: miembros = [], isLoading } = useQuery({ queryKey: ['internal-clients', 'members', cid], queryFn: () => clientesInternosApi.miembros(cid) })
  const err = (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
  const designar = useMutation({
    mutationFn: () => clientesInternosApi.designar(cid, nuevo.user_id, nuevo.role),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['internal-clients', 'members', cid] }); setNuevo(n => ({ ...n, user_id: '' })); toast.success(t('internos.designacion_hecha')) },
    onError: err,
  })
  const quitar = useMutation({
    mutationFn: (rid: string) => clientesInternosApi.quitarDesignacion(cid, rid),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['internal-clients', 'members', cid] }),
    onError: err,
  })
  return (
    <Card className="int-bloque">
      <div className="int-bloque__titulo">{t('internos.personas')}</div>
      <p className="int-nota">{t('internos.personas_d')}</p>
      <div className="int-barra__filtros int-mt">
        <Select label={t('internos.persona')} value={nuevo.user_id} onChange={e => setNuevo(n => ({ ...n, user_id: e.target.value }))}
          placeholder={t('internos.elegir')} options={op.users.map(u => ({ value: u.id, label: u.full_name }))} />
        <Select label={t('internos.designacion')} value={nuevo.role} placeholder={false} onChange={e => setNuevo(n => ({ ...n, role: e.target.value as RolDesignable }))}
          options={ROLES_DESIGNABLES.map(r => ({ value: r, label: etiquetaInterna(t, 'rol_', r) }))} />
        <Button size="sm" icon={<Plus size={14} />} disabled={!nuevo.user_id || designar.isPending} loading={designar.isPending} onClick={() => designar.mutate()}>
          {t('internos.designar')}
        </Button>
      </div>
      {isLoading ? <Spinner /> : miembros.length === 0 ? <p className="u-text2-sm int-mt">{t('internos.sin_personas')}</p> : (
        <div className="u-scroll-x int-mt">
          <TablaSimple claseTabla="u-table" etiqueta={t('internos.personas')}>
            <thead>
              <tr>
                {[t('internos.persona'), t('internos.col_puesto'), t('internos.col_papel'), t('internos.designaciones')].map(h => <th key={h} scope="col" className="int-th">{h}</th>)}
              </tr>
            </thead>
            <tbody>
              {miembros.map(m => (
                <tr key={m.user_id}>
                  <td className="int-td"><strong>{m.full_name}</strong><div className="int-sub">{m.email || ''}</div></td>
                  <td className="int-td int-td--muted">{[m.job_title, m.department].filter(Boolean).join(' · ') || '—'}</td>
                  <td className="int-td">{etiquetaInterna(t, 'rol_', m.role)}</td>
                  <td className="int-td">
                    <div className="u-wrap-8">
                      {m.designations.map(d => (
                        <span key={d.id} className="u-row-6">
                          <StatusBadge kind="accent" caps={false}>{etiquetaInterna(t, 'rol_', d.role)}</StatusBadge>
                          <IconButton ariaLabel={t('internos.quitar_designacion')} title={t('internos.quitar_designacion')}
                            onClick={async () => { if (await confirmar({ message: t('internos.quitar_designacion_confirmar', { nombre: m.full_name }), danger: true })) quitar.mutate(d.id) }}>
                            <X size={12} aria-hidden />
                          </IconButton>
                        </span>
                      ))}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </TablaSimple>
        </div>
      )}
    </Card>
  )
}

function CosteYPresupuesto({ cid, year }: { cid: string; year: number }) {
  const t = useT()
  const fmtMoneda = useFormatoMoneda()
  const [desde, setDesde] = useState(inicioDeAnio(year))
  const [hasta, setHasta] = useState(finDeAnio(year))
  const { data: coste, isLoading } = useQuery({
    queryKey: ['internal-clients', 'cost', cid, desde, hasta],
    queryFn: () => clientesInternosApi.coste(cid, desde, hasta),
    enabled: !!desde && !!hasta,
  })
  const { data: presupuesto } = useQuery({ queryKey: ['internal-clients', 'budget', cid, year], queryFn: () => clientesInternosApi.presupuesto(cid, year), retry: false })
  const { data: tco } = useQuery({ queryKey: ['internal-clients', 'tco', cid, year], queryFn: () => clientesInternosApi.tco(cid, year), retry: false })
  const m = (n: number | null | undefined, moneda?: string) => (n == null ? '—' : fmtMoneda(n, { moneda: moneda || coste?.currency }))
  return (
    <Card className="int-bloque">
      <div className="int-bloque__titulo">{t('internos.coste_y_presupuesto')}</div>
      {presupuesto && (
        <div className="ds-grid-stats">
          <KpiCard label={t('internos.presupuesto_anio', { anio: presupuesto.year })} value={m(presupuesto.budget, presupuesto.currency)} />
          <KpiCard label={t('internos.consumido')} value={m(presupuesto.consumed, presupuesto.currency)} />
          <KpiCard label={t('internos.col_pct')} value={<Semaforo pct={presupuesto.pct} tono={presupuesto.tone} />} />
        </div>
      )}
      <div className="int-barra__filtros int-mt">
        <Input label={t('internos.desde')} type="date" value={desde} onChange={e => setDesde(e.target.value)} />
        <Input label={t('internos.hasta')} type="date" value={hasta} onChange={e => setHasta(e.target.value)} />
      </div>
      {isLoading ? <Spinner /> : coste && (
        <>
          <div className="ds-grid-stats int-mt">
            <KpiCard label={t('internos.coste_total')} value={m(coste.total)} accent />
            {FUENTES_DE_COSTE.filter(s => (coste.by_source[s] ?? 0) !== 0).map(s => (
              <KpiCard key={s} label={etiquetaInterna(t, 'fuente_', s)} value={m(coste.by_source[s])} />
            ))}
          </div>
          {coste.lines.length > 0 && (
            <div className="u-scroll-x int-mt">
              <TablaSimple claseTabla="u-table" densidad="compacta" etiqueta={t('internos.lineas')}>
                <thead>
                  <tr>
                    {[t('internos.col_fuente'), t('internos.col_descripcion'), t('internos.col_proyecto'), t('internos.col_cantidad'), t('internos.col_importe')].map(h => <th key={h} scope="col" className="int-th">{h}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {coste.lines.map((l, i) => (
                    <tr key={`${l.source}-${l.source_ref || i}`}>
                      <td className="int-td">{etiquetaInterna(t, 'fuente_', l.source)}</td>
                      <td className="int-td int-td--muted">{l.description || '—'}</td>
                      <td className="int-td int-td--muted">{l.project_name || '—'}</td>
                      <td className="int-td int-td--num">{l.quantity != null ? fmtNumber(l.quantity, 2) : '—'}</td>
                      <td className="int-td int-td--num">{m(l.amount)}</td>
                    </tr>
                  ))}
                </tbody>
              </TablaSimple>
            </div>
          )}
        </>
      )}
      {tco && tco.items.length > 0 && (
        <>
          <div className="int-bloque__titulo int-mt">{t('internos.tco_titulo', { anio: tco.year })}</div>
          <div className="u-scroll-x">
            <TablaSimple claseTabla="u-table" densidad="compacta" etiqueta={t('internos.tco_titulo', { anio: tco.year })}>
              <thead>
                <tr>
                  {[t('internos.col_aplicacion'), t('internos.col_instancias'), t('internos.col_licencias'), t('internos.col_horas'), t('internos.total')].map(h => <th key={h} scope="col" className="int-th">{h}</th>)}
                </tr>
              </thead>
              <tbody>
                {tco.items.map(x => (
                  <tr key={x.product_id}>
                    <td className="int-td">{x.name}</td>
                    <td className="int-td int-td--num">{x.instances}</td>
                    <td className="int-td int-td--num">{x.licenses}</td>
                    <td className="int-td int-td--num">{fmtNumber(x.hours, 1)}</td>
                    <td className="int-td int-td--num">{m(x.total, tco.currency)}</td>
                  </tr>
                ))}
              </tbody>
            </TablaSimple>
          </div>
        </>
      )}
    </Card>
  )
}

function SlaYSatisfaccion({ cid }: { cid: string }) {
  const t = useT()
  const { data: sla } = useQuery({ queryKey: ['internal-clients', 'sla', cid], queryFn: () => clientesInternosApi.sla(cid), retry: false })
  const { data: sat } = useQuery({ queryKey: ['internal-clients', 'satisfaction', cid], queryFn: () => clientesInternosApi.satisfaccion(cid), retry: false })
  return (
    <Card className="int-bloque">
      <div className="int-bloque__titulo">{t('internos.sla_y_satisfaccion')}</div>
      <div className="ds-grid-stats">
        <KpiCard label={t('internos.sla_en_plazo')} value={<Semaforo pct={sla?.pct} tono={sla?.tone} />}
          sub={sla ? t('internos.sla_n_de_m', { n: sla.on_time, m: sla.resolved }) : undefined} />
        <KpiCard label={t('internos.ola_incumplidos')} value={sla?.ola_breached ?? '—'} danger={!!sla?.ola_breached} />
        <KpiCard label={t('internos.nps')} value={sat?.nps != null ? <Semaforo pct={sat.nps} tono={sat.tone}>{fmtNumber(sat.nps, 0)}</Semaforo> : '—'} />
        <KpiCard label={t('internos.csat')} value={sat?.csat != null ? fmtNumber(sat.csat, 1) : '—'} sub={sat ? t('internos.n_respuestas', { n: sat.responses }) : undefined} />
      </div>
      {sla && sla.by_priority.length > 0 && (
        <div className="u-scroll-x int-mt">
          <TablaSimple claseTabla="u-table" densidad="compacta" etiqueta={t('internos.sla_por_prioridad')}>
            <thead><tr>{[t('internos.col_prioridad'), t('internos.col_tickets'), t('internos.col_en_plazo'), t('internos.col_pct')].map(h => <th key={h} scope="col" className="int-th">{h}</th>)}</tr></thead>
            <tbody>
              {sla.by_priority.map(p => (
                <tr key={p.priority}>
                  <td className="int-td">{p.priority}</td>
                  <td className="int-td int-td--num">{p.total}</td>
                  <td className="int-td int-td--num">{p.on_time}</td>
                  <td className="int-td int-td--num">{p.pct != null ? `${fmtNumber(p.pct, 0)}%` : '—'}</td>
                </tr>
              ))}
            </tbody>
          </TablaSimple>
        </div>
      )}
      {sat && sat.items.length > 0 && (
        <div className="u-stack-8 int-mt">
          {sat.items.filter(i => i.comment).slice(0, 10).map(i => (
            <div key={i.id} className="int-sub">
              <StatusBadge kind="neutral" caps={false}>{`${i.survey_type.toUpperCase()} ${i.score}`}</StatusBadge> {i.comment} · {fmtDate(i.created_at)}
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}

function FormularioDeAdopcion({ cid, item, onClose }: { cid: string; item: ElementoDeAdopcion | null; onClose: () => void }) {
  const t = useT()
  const toast = useToast()
  const qc = useQueryClient()
  const [f, setF] = useState<Record<string, string>>({
    kind: item?.kind || 'formacion', title: item?.title || '', due_date: item?.due_date || '', status: item?.status || 'pendiente',
    target_users: item?.target_users != null ? String(item.target_users) : '', reached_users: item?.reached_users != null ? String(item.reached_users) : '',
  })
  const set = (k: string) => (e: { target: { value: string } }) => setF(x => ({ ...x, [k]: e.target.value }))
  const guardar = useMutation({
    mutationFn: () => {
      const d: AdopcionIn = {
        kind: f.kind as AdopcionIn['kind'], title: f.title.trim(), due_date: f.due_date || null, status: f.status as AdopcionIn['status'],
        target_users: numeroONull(f.target_users), reached_users: numeroONull(f.reached_users),
      }
      return item ? clientesInternosApi.editarAdopcion(item.id, d) : clientesInternosApi.crearAdopcion(cid, d)
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['internal-clients', 'adoption', cid] }); toast.success(t('internos.guardado')); onClose() },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  return (
    <Modal open onClose={onClose} width={560} title={item ? t('internos.editar_adopcion') : t('internos.nueva_adopcion')}>
      <div className="u-stack-8">
        <div className="int-rejilla">
          <Select label={t('internos.col_tipo')} value={f.kind} placeholder={false} onChange={set('kind')}
            options={TIPOS_DE_ADOPCION.map(k => ({ value: k, label: etiquetaInterna(t, 'adopcion_', k) }))} />
          <Select label={t('internos.col_estado')} value={f.status} placeholder={false} onChange={set('status')}
            options={ESTADOS_DE_ADOPCION.map(k => ({ value: k, label: etiquetaInterna(t, 'adopcion_estado_', k) }))} />
          <Input label={t('internos.fecha_objetivo')} type="date" value={f.due_date} onChange={set('due_date')} />
          <Input label={t('internos.usuarios_objetivo')} type="number" min={0} value={f.target_users} onChange={set('target_users')} />
          <Input label={t('internos.usuarios_alcanzados')} type="number" min={0} value={f.reached_users} onChange={set('reached_users')} />
        </div>
        <Input label={t('internos.titulo')} required value={f.title} onChange={set('title')} />
        <div className="u-actions-8">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={() => guardar.mutate()} loading={guardar.isPending} disabled={!f.title.trim() || guardar.isPending}>{t('common.save')}</Button>
        </div>
      </div>
    </Modal>
  )
}

/** Plan de adopción: lista; editable en la gestión, de lectura en el portal. */
export function ListaDeAdopcion({ items, onEditar, onBorrar }: { items: ElementoDeAdopcion[]; onEditar?: (i: ElementoDeAdopcion) => void; onBorrar?: (i: ElementoDeAdopcion) => void }) {
  const t = useT()
  if (!items.length) return <p className="u-text2-sm">{t('internos.sin_adopcion')}</p>
  return (
    <div className="u-stack-8">
      {items.map(i => (
        <div key={i.id} className="int-item ds-card">
          <div className="u-min0">
            <div className="u-row-center-8">
              <span className="int-item__titulo">{i.title}</span>
              <StatusBadge kind="neutral" caps={false}>{etiquetaInterna(t, 'adopcion_', i.kind)}</StatusBadge>
              <StatusBadge kind={TONO_ADOPCION[i.status] || 'neutral'} caps={false}>{etiquetaInterna(t, 'adopcion_estado_', i.status)}</StatusBadge>
            </div>
            <div className="int-sub">
              {[
                i.project_name,
                i.due_date && t('internos.para_el', { fecha: fmtDate(i.due_date) }),
                i.target_users != null && t('internos.alcance_n_de_m', { n: i.reached_users ?? 0, m: i.target_users }),
              ].filter(Boolean).join(' · ')}
            </div>
          </div>
          {(onEditar || onBorrar) && (
            <div className="u-row-6">
              {onEditar && <IconButton variante="caja" ariaLabel={t('internos.editar')} title={t('internos.editar')} onClick={() => onEditar(i)}><Pencil size={14} aria-hidden /></IconButton>}
              {onBorrar && <IconButton variante="caja" tono="peligro" ariaLabel={t('internos.borrar')} title={t('internos.borrar')} onClick={() => onBorrar(i)}><Trash2 size={14} aria-hidden /></IconButton>}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

function Adopcion({ cid }: { cid: string }) {
  const t = useT()
  const toast = useToast()
  const qc = useQueryClient()
  const [editando, setEditando] = useState<ElementoDeAdopcion | null | 'nuevo'>(null)
  const { data: items = [], isLoading } = useQuery({ queryKey: ['internal-clients', 'adoption', cid], queryFn: () => clientesInternosApi.adopcion(cid) })
  const borrar = useMutation({
    mutationFn: (id: string) => clientesInternosApi.borrarAdopcion(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['internal-clients', 'adoption', cid] }),
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  return (
    <Card className="int-bloque">
      <div className="int-barra">
        <div className="int-bloque__titulo">{t('internos.adopcion')}</div>
        <Button size="sm" icon={<Plus size={14} />} onClick={() => setEditando('nuevo')}>{t('internos.nueva_adopcion')}</Button>
      </div>
      {isLoading ? <Spinner /> : (
        <ListaDeAdopcion items={items} onEditar={setEditando}
          onBorrar={async i => { if (await confirmar({ message: t('internos.borrar_confirmar', { titulo: i.title }), danger: true })) borrar.mutate(i.id) }} />
      )}
      {editando && <FormularioDeAdopcion cid={cid} item={editando === 'nuevo' ? null : editando} onClose={() => setEditando(null)} />}
    </Card>
  )
}

export default function FichaDeUnidad({ cid }: { cid: string }) {
  const year = new Date().getFullYear()
  return (
    <div className="u-stack-8">
      <CosteYPresupuesto cid={cid} year={year} />
      <SlaYSatisfaccion cid={cid} />
      <Personas cid={cid} />
      <Adopcion cid={cid} />
    </div>
  )
}

