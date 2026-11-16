/**
 * ConfigSlaYCiclos — SLA condicionales, OLA por prioridad y ciclos de vida por
 * tipo de ticket (mejoras de mercado 16-11-2026, migración 174).
 * 16-11-2026 (pasada de diseño): vacíos con icono lucide y botones de editar con icono.
 */
import { useEffect, useState } from 'react'
import type { ChangeEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { GitBranch, ListChecks, Pencil, Plus, Trash2, Users } from 'lucide-react'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { useAuth } from '../../context/AuthContext'
import { confirmar } from '../../context/ConfirmContext'
import { extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { Button, EmptyState, Modal, Section, Spinner, StatusBadge } from '../../components/ui'
import { etiquetaCodigo } from '../../i18n/etiquetaCodigo'
import { clientsApi, contractsApi, sdCatalogApi, sdGroupsApi, sdSlaPoliciesApi } from '../../services/api'
import { slaAvanzadoApi } from '../../services/api/serviceDeskMercado'
import type { CicloDeVida, EstadoDeCiclo, ReglaSla } from '../../services/api/serviceDeskMercado'
import { etiquetaSd } from './sdUtils'
import '../../components/servicedesk/sdMercado.css'

const PRIORIDADES = ['p1_critical', 'p2_high', 'p3_medium', 'p4_low']
const TIPOS = ['incident', 'service_request', 'change', 'problem', 'question']
const ESTADOS_BASE = ['new', 'assigned', 'in_progress', 'pending_client', 'pending_third', 'resolved', 'closed', 'cancelled']
const VACIA: ReglaSla = { name: '', is_active: true, sort_order: 0, service_item_id: null, ticket_type: null, client_id: null, contract_id: null, priority: null, response_hours: null, resolution_hours: null, sla_policy_id: null }

function useErr() {
  const toast = useToast()
  return (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
}

type Opcion = { id: string; name?: string; title?: string; full_name?: string }

export function ReglasSlaYOla() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const err = useErr()
  const { user } = useAuth()
  const esAdmin = user?.role === 'admin'
  const [editando, setEditando] = useState<ReglaSla | null>(null)
  const reglas = useQuery({ queryKey: ['sdm-sla-rules'], queryFn: slaAvanzadoApi.reglas })
  const catalogo = useQuery({ queryKey: ['sd-catalog'], queryFn: () => sdCatalogApi.list().then(r => r.data) })
  const servicios: Opcion[] = (catalogo.data ?? []).flatMap((c: { services?: Opcion[] }) => c.services ?? [])
  const clientes = useQuery({ queryKey: ['clients-min'], queryFn: () => clientsApi.list().then(r => r.data as Opcion[]) })
  const contratos = useQuery({ queryKey: ['contracts-min'], queryFn: () => contractsApi.list().then(r => r.data as Opcion[]) })
  const politicas = useQuery({ queryKey: ['sd-sla-policies'], queryFn: () => sdSlaPoliciesApi.list().then(r => r.data as Opcion[]) })
  const nombre = (lista: Opcion[] | undefined, id: string | null) => !id ? t('sd_mercado.cualquiera') : (lista ?? []).find(x => x.id === id)?.name || (lista ?? []).find(x => x.id === id)?.title || id
  const borrar = useMutation({ mutationFn: slaAvanzadoApi.borrarRegla, onSuccess: () => qc.invalidateQueries({ queryKey: ['sdm-sla-rules'] }), onError: err })
  const guardar = useMutation({
    mutationFn: (r: ReglaSla) => r.id ? slaAvanzadoApi.editarRegla(r.id, r) : slaAvanzadoApi.crearRegla(r),
    onSuccess: () => { setEditando(null); qc.invalidateQueries({ queryKey: ['sdm-sla-rules'] }); toast.success(t('sd_mercado.guardado')) },
    onError: err,
  })
  return (
    <div className="u-stack-20">
      <Section title={t('sd_mercado.sla_reglas_titulo')} subtitle={t('sd_mercado.sla_reglas_desc')}
        actions={esAdmin ? <Button icon={<Plus size={14} />} onClick={() => setEditando({ ...VACIA, sort_order: (reglas.data?.length ?? 0) * 10 })}>{t('sd_mercado.regla_nueva')}</Button> : null}>
        {reglas.isLoading ? <Spinner /> : (reglas.data ?? []).length === 0 ? <EmptyState icon={<ListChecks size={28} />} title={t('sd_mercado.sin_reglas')} /> : (
          <div className="sdm-table-wrap">
            <table className="u-table">
              <thead><tr>
                <th>{t('sd_mercado.orden')}</th><th>{t('sd_mercado.nombre')}</th><th>{t('sd_mercado.condiciones')}</th>
                <th>{t('sd_mercado.objetivos')}</th><th />
              </tr></thead>
              <tbody>
                {(reglas.data ?? []).map(r => (
                  <tr key={r.id} className="u-border-b">
                    <td>{r.sort_order}</td>
                    <td><span className="u-600">{r.name}</span> {!r.is_active && <StatusBadge caps={false}>{t('sd_mercado.apagado')}</StatusBadge>}</td>
                    <td className="u-text2-xs sdm-wrap">
                      {[r.service_item_id && `${t('sd_mercado.servicio')}: ${nombre(servicios, r.service_item_id)}`,
                        r.ticket_type && `${t('sd_mercado.tipo')}: ${etiquetaSd('type', r.ticket_type)}`,
                        r.client_id && `${t('sd_mercado.cliente')}: ${nombre(clientes.data, r.client_id)}`,
                        r.contract_id && `${t('sd_mercado.contrato')}: ${nombre(contratos.data, r.contract_id)}`,
                        r.priority && `${t('sd_mercado.prioridad')}: ${etiquetaCodigo(t, 'estado', r.priority)}`,
                      ].filter(Boolean).join(' · ') || t('sd_mercado.cualquiera')}
                    </td>
                    <td className="u-text2-xs">{t('sd_mercado.respuesta_h', { h: r.response_hours ?? '—' })} · {t('sd_mercado.resolucion_h', { h: r.resolution_hours ?? '—' })}</td>
                    <td>{esAdmin && <div className="u-actions-8">
                      <Button size="xs" variant="secondary" icon={<Pencil size={12} />} onClick={() => setEditando(r)}>{t('sd_mercado.editar')}</Button>
                      <Button size="xs" variant="ghost" icon={<Trash2 size={12} />} onClick={async () => { if (await confirmar({ message: t('sd_mercado.regla_borrar', { n: r.name }), danger: true })) borrar.mutate(r.id as string) }}>{t('sd_mercado.quitar')}</Button>
                    </div>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>
      <OlaPorPrioridad esAdmin={esAdmin} />
      {editando && (
        <Modal open size="lg" title={editando.id ? t('sd_mercado.regla_editar') : t('sd_mercado.regla_nueva')} onClose={() => setEditando(null)}>
          <FormRegla inicial={editando} servicios={servicios} clientes={clientes.data ?? []} contratos={contratos.data ?? []} politicas={politicas.data ?? []}
            onCancel={() => setEditando(null)} onSave={r => guardar.mutate(r)} guardando={guardar.isPending} />
        </Modal>
      )}
    </div>
  )
}

function FormRegla({ inicial, servicios, clientes, contratos, politicas, onCancel, onSave, guardando }: {
  inicial: ReglaSla; servicios: Opcion[]; clientes: Opcion[]; contratos: Opcion[]; politicas: Opcion[]
  onCancel: () => void; onSave: (r: ReglaSla) => void; guardando: boolean
}) {
  const t = useAppT()
  const [r, setR] = useState<ReglaSla>(inicial)
  const sel = (k: keyof ReglaSla) => (e: ChangeEvent<HTMLSelectElement>) => setR({ ...r, [k]: e.target.value || null })
  const num = (k: keyof ReglaSla) => (e: ChangeEvent<HTMLInputElement>) => setR({ ...r, [k]: e.target.value === '' ? null : Number(e.target.value) })
  const lista = (k: keyof ReglaSla, ops: Opcion[], etiqueta: string) => (
    <label className="sdm-field"><span>{etiqueta}</span>
      <select className="ds-input" value={(r[k] as string) || ''} onChange={sel(k)}>
        <option value="">{t('sd_mercado.cualquiera')}</option>
        {ops.map(o => <option key={o.id} value={o.id}>{o.name || o.title || o.full_name || o.id}</option>)}
      </select></label>
  )
  const valida = r.name.trim().length >= 2 && (r.response_hours != null || r.resolution_hours != null)
  return (
    <div className="u-stack-12">
      <div className="sdm-form">
        <label className="sdm-field"><span>{t('sd_mercado.nombre')}</span><input className="ds-input" value={r.name} onChange={e => setR({ ...r, name: e.target.value })} /></label>
        <label className="sdm-field"><span>{t('sd_mercado.orden')}</span><input className="ds-input" type="number" min={0} value={r.sort_order} onChange={e => setR({ ...r, sort_order: Number(e.target.value) || 0 })} /></label>
        <label className="u-row-center-8"><input type="checkbox" checked={r.is_active} onChange={e => setR({ ...r, is_active: e.target.checked })} />{t('sd_mercado.activo')}</label>
      </div>
      <div className="ds-eyebrow">{t('sd_mercado.condiciones')}</div>
      <div className="sdm-form">
        {lista('service_item_id', servicios, t('sd_mercado.servicio'))}
        <label className="sdm-field"><span>{t('sd_mercado.tipo')}</span>
          <select className="ds-input" value={r.ticket_type || ''} onChange={sel('ticket_type')}>
            <option value="">{t('sd_mercado.cualquiera')}</option>
            {TIPOS.map(x => <option key={x} value={x}>{etiquetaSd('type', x)}</option>)}
          </select></label>
        {lista('client_id', clientes, t('sd_mercado.cliente'))}
        {lista('contract_id', contratos, t('sd_mercado.contrato'))}
        <label className="sdm-field"><span>{t('sd_mercado.prioridad')}</span>
          <select className="ds-input" value={r.priority || ''} onChange={sel('priority')}>
            <option value="">{t('sd_mercado.cualquiera')}</option>
            {PRIORIDADES.map(x => <option key={x} value={x}>{etiquetaCodigo(t, 'estado', x)}</option>)}
          </select></label>
      </div>
      <div className="ds-eyebrow">{t('sd_mercado.objetivos')}</div>
      <div className="sdm-form">
        <label className="sdm-field"><span>{t('sd_mercado.horas_respuesta')}</span><input className="ds-input" type="number" min={0} step={0.25} value={r.response_hours ?? ''} onChange={num('response_hours')} /></label>
        <label className="sdm-field"><span>{t('sd_mercado.horas_resolucion')}</span><input className="ds-input" type="number" min={0} step={0.25} value={r.resolution_hours ?? ''} onChange={num('resolution_hours')} /></label>
        {lista('sla_policy_id', politicas, t('sd_mercado.calendario_de_politica'))}
      </div>
      <div className="u-text3-xs">{t('sd_mercado.regla_hint')}</div>
      <div className="u-actions-10">
        <Button variant="secondary" onClick={onCancel}>{t('common.cancel')}</Button>
        <Button onClick={() => onSave(r)} loading={guardando} disabled={!valida}>{t('common.save')}</Button>
      </div>
    </div>
  )
}

function OlaPorPrioridad({ esAdmin }: { esAdmin: boolean }) {
  const t = useAppT()
  const toast = useToast()
  const err = useErr()
  const colas = useQuery({ queryKey: ['sd-groups'], queryFn: () => sdGroupsApi.list().then(r => r.data as Opcion[]) })
  const [cola, setCola] = useState('')
  const elegida = cola || colas.data?.[0]?.id || ''
  const ola = useQuery({ queryKey: ['sdm-ola', elegida], queryFn: () => slaAvanzadoApi.ola(elegida), enabled: !!elegida })
  const [objetivos, setObjetivos] = useState<Record<string, string>>({})
  useEffect(() => {
    if (ola.data) setObjetivos(Object.fromEntries(PRIORIDADES.map(p => [p, ola.data.targets[p] == null ? '' : String(ola.data.targets[p])])))
  }, [ola.data])
  const guardar = useMutation({
    mutationFn: () => slaAvanzadoApi.guardarOla(elegida, Object.fromEntries(PRIORIDADES.map(p => [p, objetivos[p] === '' || objetivos[p] == null ? null : Number(objetivos[p])]))),
    onSuccess: () => toast.success(t('sd_mercado.guardado')),
    onError: err,
  })
  return (
    <Section title={t('sd_mercado.ola_titulo')} subtitle={t('sd_mercado.ola_desc')}>
      {(colas.data ?? []).length === 0 ? <EmptyState icon={<Users size={28} />} title={t('sd_mercado.sin_colas')} /> : (
        <div className="u-stack-12">
          <label className="sdm-field"><span>{t('sd_mercado.cola')}</span>
            <select className="ds-input" value={elegida} onChange={e => setCola(e.target.value)}>
              {(colas.data ?? []).map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select></label>
          {ola.data && <div className="u-text3-xs">{t('sd_mercado.ola_por_defecto', { h: ola.data.default_hours ?? '—' })}</div>}
          <div className="sdm-form">
            {PRIORIDADES.map(p => (
              <label key={p} className="sdm-field"><span>{etiquetaCodigo(t, 'estado', p)} (h)</span>
                <input className="ds-input" type="number" min={0} step={0.25} disabled={!esAdmin} value={objetivos[p] ?? ''}
                  placeholder={ola.data?.default_hours != null ? String(ola.data.default_hours) : ''}
                  onChange={e => setObjetivos({ ...objetivos, [p]: e.target.value })} /></label>
            ))}
          </div>
          {esAdmin && <div className="u-row-end"><Button onClick={() => guardar.mutate()} loading={guardar.isPending}>{t('common.save')}</Button></div>}
        </div>
      )}
    </Section>
  )
}

export function CiclosDeVida() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const err = useErr()
  const { user } = useAuth()
  const esAdmin = user?.role === 'admin'
  const { data = [], isLoading } = useQuery({ queryKey: ['sdm-lifecycles'], queryFn: slaAvanzadoApi.ciclos })
  const [editando, setEditando] = useState<CicloDeVida | null>(null)
  const borrar = useMutation({ mutationFn: slaAvanzadoApi.borrarCiclo, onSuccess: () => qc.invalidateQueries({ queryKey: ['sdm-lifecycles'] }), onError: err })
  const guardar = useMutation({
    mutationFn: slaAvanzadoApi.guardarCiclo,
    onSuccess: () => { setEditando(null); qc.invalidateQueries({ queryKey: ['sdm-lifecycles'] }); toast.success(t('sd_mercado.guardado')) },
    onError: err,
  })
  const libres = TIPOS.filter(tp => !data.some(c => c.ticket_type === tp))
  const nuevo = (tipo: string): CicloDeVida => ({
    ticket_type: tipo, name: etiquetaSd('type', tipo), is_active: true, restrict_transitions: false, transitions: [],
    states: ESTADOS_BASE.map((b, i) => ({ key: b, label: etiquetaCodigo(t, 'estado', b), base_status: b, is_initial: i === 0 })),
  })
  return (
    <Section title={t('sd_mercado.ciclos_titulo')} subtitle={t('sd_mercado.ciclos_desc')}
      actions={esAdmin && libres.length > 0 ? (
        <select className="ds-input sdm-select-accion" aria-label={t('sd_mercado.ciclo_nuevo')} value="" onChange={e => e.target.value && setEditando(nuevo(e.target.value))}>
          <option value="">{t('sd_mercado.ciclo_nuevo')}</option>
          {libres.map(tp => <option key={tp} value={tp}>{etiquetaSd('type', tp)}</option>)}
        </select>
      ) : null}>
      {isLoading ? <Spinner /> : data.length === 0 ? <EmptyState icon={<GitBranch size={28} />} title={t('sd_mercado.sin_ciclos')} description={t('sd_mercado.sin_ciclos_desc')} /> : (
        <ul className="sdm-list">
          {data.map(c => (
            <li key={c.id} className="sdm-list__item">
              <div className="u-flex1-min0 u-stack-6">
                <div className="u-wrap-8"><span className="u-text1-sm-600">{c.name}</span><StatusBadge caps={false}>{etiquetaSd('type', c.ticket_type)}</StatusBadge>
                  {!c.is_active && <StatusBadge caps={false}>{t('sd_mercado.apagado')}</StatusBadge>}
                  {c.restrict_transitions && <StatusBadge kind="info" caps={false}>{t('sd_mercado.transiciones_restringidas')}</StatusBadge>}</div>
                <div className="u-wrap-6">{c.states.map(s => <StatusBadge key={s.key} caps={false} color={s.color || undefined}>{s.label}</StatusBadge>)}</div>
              </div>
              {esAdmin && <div className="u-actions-8">
                <Button size="xs" variant="secondary" icon={<Pencil size={12} />} onClick={() => setEditando(c)}>{t('sd_mercado.editar')}</Button>
                <Button size="xs" variant="ghost" icon={<Trash2 size={12} />} onClick={async () => { if (await confirmar({ message: t('sd_mercado.ciclo_borrar'), danger: true })) borrar.mutate(c.id as string) }}>{t('sd_mercado.quitar')}</Button>
              </div>}
            </li>
          ))}
        </ul>
      )}
      {editando && (
        <Modal open size="lg" title={`${t('sd_mercado.ciclo_de')} ${etiquetaSd('type', editando.ticket_type)}`} onClose={() => setEditando(null)}>
          <EditorDeCiclo inicial={editando} onCancel={() => setEditando(null)} onSave={c => guardar.mutate(c)} guardando={guardar.isPending} />
        </Modal>
      )}
    </Section>
  )
}

function EditorDeCiclo({ inicial, onCancel, onSave, guardando }: { inicial: CicloDeVida; onCancel: () => void; onSave: (c: CicloDeVida) => void; guardando: boolean }) {
  const t = useAppT()
  const [c, setC] = useState<CicloDeVida>(inicial)
  const setEstado = (i: number, p: Partial<EstadoDeCiclo>) => setC({ ...c, states: c.states.map((s, j) => j === i ? { ...s, ...p } : (p.is_initial ? { ...s, is_initial: false } : s)) })
  const claves = c.states.map(s => s.key)
  const tiene = (a: string, b: string) => c.transitions.some(x => x.from_key === a && x.to_key === b)
  const alternar = (a: string, b: string) => setC({ ...c, transitions: tiene(a, b) ? c.transitions.filter(x => !(x.from_key === a && x.to_key === b)) : [...c.transitions, { from_key: a, to_key: b }] })
  const valido = c.name.trim().length >= 2 && c.states.length > 0 && c.states.every(s => /^[a-z0-9_]+$/.test(s.key) && s.label.trim()) && new Set(claves).size === claves.length
  return (
    <div className="u-stack-12">
      <div className="sdm-form">
        <label className="sdm-field"><span>{t('sd_mercado.nombre')}</span><input className="ds-input" value={c.name} onChange={e => setC({ ...c, name: e.target.value })} /></label>
        <label className="u-row-center-8"><input type="checkbox" checked={c.is_active} onChange={e => setC({ ...c, is_active: e.target.checked })} />{t('sd_mercado.activo')}</label>
        <label className="u-row-center-8"><input type="checkbox" checked={c.restrict_transitions} onChange={e => setC({ ...c, restrict_transitions: e.target.checked })} />{t('sd_mercado.transiciones_restringidas')}</label>
      </div>
      <div className="u-text3-xs">{t('sd_mercado.ciclo_hint')}</div>
      <div className="sdm-steps">
        {c.states.map((s, i) => (
          <div key={i} className="u-wrap-8">
            <input className="ds-input" aria-label={t('sd_mercado.clave')} placeholder={t('sd_mercado.clave')} value={s.key} onChange={e => setEstado(i, { key: e.target.value.toLowerCase() })} />
            <input className="ds-input" aria-label={t('sd_mercado.nombre')} placeholder={t('sd_mercado.nombre')} value={s.label} onChange={e => setEstado(i, { label: e.target.value })} />
            <select className="ds-input" aria-label={t('sd_mercado.estado_base')} value={s.base_status} onChange={e => setEstado(i, { base_status: e.target.value })}>
              {ESTADOS_BASE.map(b => <option key={b} value={b}>{etiquetaCodigo(t, 'estado', b)}</option>)}
            </select>
            <label className="u-row-center-6"><input type="radio" name="sdm-inicial" checked={!!s.is_initial} onChange={() => setEstado(i, { is_initial: true })} />{t('sd_mercado.inicial')}</label>
            <Button size="xs" variant="ghost" icon={<Trash2 size={12} />} onClick={() => setC({ ...c, states: c.states.filter((_, j) => j !== i), transitions: c.transitions.filter(x => x.from_key !== s.key && x.to_key !== s.key) })}>{t('sd_mercado.quitar')}</Button>
          </div>
        ))}
      </div>
      <div><Button size="sm" variant="secondary" icon={<Plus size={12} />} onClick={() => setC({ ...c, states: [...c.states, { key: '', label: '', base_status: 'in_progress' }] })}>{t('sd_mercado.anadir_estado')}</Button></div>
      {c.restrict_transitions && (
        <div className="sdm-table-wrap">
          <div className="ds-eyebrow">{t('sd_mercado.transiciones')}</div>
          <table className="u-table u-table-sm">
            <thead><tr><th>{t('sd_mercado.desde_hasta')}</th>{c.states.map(s => <th key={s.key} className="sdm-wrap">{s.label}</th>)}</tr></thead>
            <tbody>
              {c.states.map(a => (
                <tr key={a.key}><td className="u-600 sdm-wrap">{a.label}</td>
                  {c.states.map(b => <td key={b.key}>{a.key !== b.key && <input type="checkbox" aria-label={`${a.label} → ${b.label}`} checked={tiene(a.key, b.key)} onChange={() => alternar(a.key, b.key)} />}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="u-actions-10">
        <Button variant="secondary" onClick={onCancel}>{t('common.cancel')}</Button>
        <Button onClick={() => onSave(c)} loading={guardando} disabled={!valido}>{t('common.save')}</Button>
      </div>
    </div>
  )
}
