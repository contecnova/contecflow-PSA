/**
 * Pestaña «Recursos técnicos» de la ficha de proyecto (licencias y hardware, fase 4).
 *
 * La bolsa de asientos del proyecto y su reparto, lo asignado al proyecto, lo
 * que tiene su equipo y el coste del periodo (fase 3: coste por titular y día).
 * El PM del proyecto y administración asignan y liberan; el resto solo mira
 * (quien no ve fichas ajenas, solo lo suyo del equipo).
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Boxes, Euro, KeyRound, Laptop, Plus, Users } from 'lucide-react'
import { almIntegracionApi } from '../../services/api/almIntegracion'
import type { AsignacionAlm, CosteAgrupado, RecursosDelProyecto } from '../../services/api/almIntegracion'
import { assetsApi, licensesApi } from '../../services/api'
import { Button, DataTable, EmptyState, KpiCard, Modal, Section, Select, SelectorDePeriodo, Spinner, useErroresDeCampo } from '../ui'
import { usePeriodo } from '../../hooks/usePeriodo'
import { SIN_HORA, codigoDeErrorDePeriodo } from '../../utils/periodo'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { fmtCurrency, fmtDate } from '../../utils/helpers'
import DateInput from '../ui/DateInput'
import { Estado, etiqueta, mensajeDeError } from './almComun'
import './almIntegracion.css'

export default function RecursosTecnicosDelProyecto({ projectId }: { projectId: string }) {
  const t = useAppT()
  // Periodo libre (16-11-2026): antes dos <input type="date"> propios. El coste es
  // por día de calendario: sin hora. Prefijo para no chocar con otros selectores de la ficha.
  const periodo = usePeriodo({ defecto: '30d', granularidades: SIN_HORA, prefijo: 'rt_' })
  const [asignar, setAsignar] = useState(false)
  const q = useQuery({
    queryKey: ['alm-proyecto', projectId, periodo.params],
    queryFn: () => almIntegracionApi.recursosDelProyecto(projectId, periodo.params),
  })
  const selector = <SelectorDePeriodo {...periodo.selector} />
  if (q.isLoading) return <Spinner />
  if (q.isError) {
    const errorDePeriodo = codigoDeErrorDePeriodo(q.error)
    return <div className="almint-lista">
      <div className="almint-filtros">{selector}</div>
      <EmptyState title={errorDePeriodo ? t(`periodo_err.${errorDePeriodo.motivo}`, errorDePeriodo.params) : mensajeDeError(t, q.error)} />
    </div>
  }
  const d = q.data as RecursosDelProyecto
  const moneda = d.coste?.moneda ?? undefined
  const vacio = !d.bolsas.length && !d.asignaciones.length && d.equipo.every(p => !p.licencias.length && !p.equipos.length)
  return (
    <div className="almint-lista">
      <div className="almint-filtros">
        {selector}
        {d.puedo_gestionar && <Button icon={<Plus size={14} />} onClick={() => setAsignar(true)}>{t('almint.asignar')}</Button>}
      </div>
      {d.coste && <div className="almint-kpis">
        <KpiCard icon={<Euro size={16} />} label={t('almint.coste_imputado')} value={fmtCurrency(d.coste.imputado, moneda)} accent />
        <KpiCard icon={<Users size={16} />} label={t('almint.coste_equipo_fuera')} value={fmtCurrency(d.coste.del_equipo_fuera, moneda)} />
        <KpiCard icon={<Boxes size={16} />} label={t('almint.coste_ocioso')} value={fmtCurrency(d.coste.ocioso, moneda)} warning={d.coste.ocioso > 0} />
        <KpiCard icon={<Euro size={16} />} label={t('almint.coste_refacturable')} value={fmtCurrency(d.coste.rebillable, moneda)} />
      </div>}
      {vacio && <EmptyState icon={<Laptop size={28} />} title={t('almint.proyecto_sin_recursos')} description={t('almint.proyecto_sin_recursos_desc')} />}
      {d.bolsas.map(b => (
        <Section key={b.id} title={t('almint.bolsa_de', { nombre: b.resource_name ?? '' })}
          subtitle={t('almint.bolsa_uso', { usados: b.used_in_pool ?? 0, total: b.quantity })}
          actions={d.puedo_gestionar ? <Liberar projectId={projectId} a={b} /> : undefined}>
          <TablaDeAsignaciones filas={b.hijas} gestionar={d.puedo_gestionar} projectId={projectId} titular />
        </Section>
      ))}
      {d.asignaciones.length > 0 && <Section title={t('almint.asignado_al_proyecto')}>
        <TablaDeAsignaciones filas={d.asignaciones} gestionar={d.puedo_gestionar} projectId={projectId} titular />
      </Section>}
      {d.equipo.some(p => p.licencias.length || p.equipos.length) && <Section title={t('almint.del_equipo')} subtitle={t('almint.del_equipo_sub')}>
        <TablaDeAsignaciones projectId={projectId} gestionar={false} titular
          filas={d.equipo.flatMap(p => [...p.licencias, ...p.equipos])} />
      </Section>}
      {d.coste && d.coste.por_recurso.length > 0 && <Section title={t('almint.coste_por_recurso')}>
        <TablaDeCoste filas={d.coste.por_recurso} />
      </Section>}
      {d.coste && d.coste.del_equipo_por_recurso.length > 0 && <Section title={t('almint.coste_equipo_fuera')}>
        <TablaDeCoste filas={d.coste.del_equipo_por_recurso} />
      </Section>}
      {asignar && <AsignarModal projectId={projectId} datos={d} onClose={() => setAsignar(false)} />}
    </div>
  )
}

function TablaDeAsignaciones({ filas, gestionar, projectId, titular }: { filas: AsignacionAlm[]; gestionar: boolean; projectId: string; titular?: boolean }) {
  const t = useAppT()
  return <DataTable<AsignacionAlm> data={filas} emptyTitle={t('almint.sin_asignaciones')} columns={[
    { key: 'resource_name', label: t('almint.col_recurso'), render: (_v, f) => <span className="almint-pastillas">
      {f.resource_type === 'license' ? <KeyRound size={14} aria-hidden /> : <Laptop size={14} aria-hidden />}
      <span>{f.resource_name}{f.asset_tag ? ` · ${f.asset_tag}` : ''}</span></span> },
    ...(titular ? [{ key: 'holder_name', label: t('almint.col_titular') }] : []),
    { key: 'mode', label: t('almint.col_modo'), render: (_v, f) => etiqueta(t, 'modo', f.mode) },
    { key: 'quantity', label: t('almint.col_cantidad') },
    { key: 'status', label: t('almint.col_estado'), render: (_v, f) => <span className="almint-pastillas"><Estado t={t} codigo={f.status} />{f.overdue && <Estado t={t} codigo="vencido" />}</span> },
    { key: 'valid_from', label: t('almint.desde'), render: (_v, f) => fmtDate(f.valid_from) },
    { key: 'valid_to', label: t('almint.hasta'), render: (_v, f) => fmtDate(f.valid_to) },
    ...(gestionar ? [{ key: 'acciones', label: '', sortable: false, render: (_v: never, f: AsignacionAlm) => <Liberar projectId={projectId} a={f} /> }] : []),
  ]} />
}

function TablaDeCoste({ filas }: { filas: CosteAgrupado[] }) {
  const t = useAppT()
  return <DataTable<CosteAgrupado> data={filas} columns={[
    { key: 'resource_name', label: t('almint.col_recurso') },
    { key: 'kind', label: t('almint.col_tipo_coste'), render: (_v, f) => etiqueta(t, 'tipo_coste', f.kind) },
    { key: 'days', label: t('almint.col_dias') },
    { key: 'amount', label: t('almint.col_importe'), render: (_v, f) => fmtCurrency(f.amount, f.currency) },
  ]} />
}

function Liberar({ projectId, a }: { projectId: string; a: AsignacionAlm }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const m = useMutation({
    mutationFn: () => almIntegracionApi.liberarDelProyecto(projectId, a.id),
    onSuccess: () => { toast.success(t('almint.liberada')); qc.invalidateQueries({ queryKey: ['alm-proyecto', projectId] }) },
    onError: e => toast.error(mensajeDeError(t, e)),
  })
  if (a.status !== 'active' && a.status !== 'pending') return null
  return <Button size="xs" variant="ghost" loading={m.isPending} onClick={() => m.mutate()}>{t('almint.liberar')}</Button>
}

function AsignarModal({ projectId, datos, onClose }: { projectId: string; datos: RecursosDelProyecto; onClose: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [f, setF] = useState({ recurso: 'license', id: '', holder_type: 'project', holder_id: '', parent_id: '', quantity: '1', valid_to: '', reason: '' })
  const licencias = useQuery({ queryKey: ['alm-licencias-para-asignar'], queryFn: () => licensesApi.list({ page_size: 200 }).then(r => r.data) })
  const activos = useQuery({ queryKey: ['alm-activos-disponibles'], queryFn: () => assetsApi.list({ status: 'available', page_size: 200 }).then(r => r.data) })
  const bolsas = datos.bolsas.filter(b => b.license_id === f.id && b.status === 'active')
  const campos = useErroresDeCampo()
  const msg = (k: string) => campos.de(k) ? <div className="u-field-error">{campos.de(k)}</div> : null
  const m = useMutation({
    onMutate: () => campos.limpiar(),
    mutationFn: () => almIntegracionApi.asignarAlProyecto(projectId, {
      holder_type: f.holder_type as 'project' | 'user', holder_id: f.holder_type === 'user' ? f.holder_id : undefined,
      license_id: f.recurso === 'license' ? f.id : undefined, asset_id: f.recurso === 'asset' ? f.id : undefined,
      mode: f.recurso === 'asset' && f.valid_to ? 'loan' : undefined,
      quantity: Number(f.quantity) || 1, parent_id: f.parent_id || undefined, valid_to: f.valid_to || undefined, reason: f.reason || undefined,
    }),
    onSuccess: r => {
      toast.success(r.status === 'pending' ? t('almint.asignacion_pendiente') : t('almint.asignado_ok'))
      qc.invalidateQueries({ queryKey: ['alm-proyecto', projectId] }); onClose()
    },
    onError: (e: unknown) => { if (!campos.recoger(e)) toast.error(mensajeDeError(t, e)) },
  })
  const listo = !!f.id && (f.holder_type === 'project' || !!f.holder_id)
  return (
    <Modal open onClose={onClose} title={t('almint.asignar')} subtitle={t('almint.asignar_sub')}>
      <div className="almint-form">
        <div className="almint-fila">
          <Select error={campos.de('recurso')} label={t('almint.que_asignar')} value={f.recurso} onChange={e => setF({ ...f, recurso: e.target.value, id: '', parent_id: '' })}
            options={[{ value: 'license', label: t('almint.una_licencia') }, { value: 'asset', label: t('almint.un_equipo') }]} />
          <Select error={campos.de('holder_type')} label={t('almint.a_quien')} value={f.holder_type} onChange={e => setF({ ...f, holder_type: e.target.value, holder_id: '', parent_id: '' })}
            options={[{ value: 'project', label: t('almint.al_proyecto') }, { value: 'user', label: t('almint.a_una_persona_del_equipo') }]} />
        </div>
        {f.recurso === 'license'
          ? <Select error={campos.de('id')} label={t('almint.col_licencia')} value={f.id} onChange={e => setF({ ...f, id: e.target.value, parent_id: '' })}
              options={(licencias.data ?? []).map(l => ({ value: String(l.id), label: String(l.name) }))} />
          : <Select error={campos.de('id')} label={t('almint.col_equipo')} value={f.id} onChange={e => setF({ ...f, id: e.target.value })}
              options={(activos.data ?? []).map(a => ({ value: String(a.id), label: [a.name, a.asset_tag].filter(Boolean).join(' · ') }))} />}
        {f.holder_type === 'user' && <Select error={campos.de('holder_id')} label={t('almint.persona')} value={f.holder_id} onChange={e => setF({ ...f, holder_id: e.target.value })}
          options={datos.equipo.map(p => ({ value: p.user_id, label: p.user_name }))} />}
        {f.holder_type === 'user' && f.recurso === 'license' && bolsas.length > 0 &&
          <Select error={campos.de('parent_id')} label={t('almint.de_la_bolsa')} value={f.parent_id} onChange={e => setF({ ...f, parent_id: e.target.value })}
            options={bolsas.map(b => ({ value: b.id, label: t('almint.bolsa_uso', { usados: b.used_in_pool ?? 0, total: b.quantity }) }))} />}
        <div className="almint-fila">
          {f.recurso === 'license' && f.holder_type === 'project' && <label className="almint-campo">{t('almint.asientos')}
            <input type="number" min={1} className="ds-input" value={f.quantity} onChange={e => setF({ ...f, quantity: e.target.value })} />{msg('quantity')}</label>}
          <label className="almint-campo">{f.recurso === 'asset' ? t('almint.devolver_antes_de') : t('almint.hasta')}
            <DateInput className="ds-input" value={f.valid_to} onChange={e => setF({ ...f, valid_to: e.target.value })} />{msg('valid_to')}</label>
        </div>
        <label className="almint-campo">{t('almint.motivo')}
          <textarea className="ds-input" rows={2} value={f.reason} onChange={e => setF({ ...f, reason: e.target.value })} />{msg('reason')}</label>
        <div className="almint-acciones almint-acciones--fin">
          <Button variant="ghost" onClick={onClose}>{t('common.cancel')}</Button>
          <Button disabled={!listo} loading={m.isPending} onClick={() => m.mutate()}>{t('almint.asignar')}</Button>
        </div>
      </div>
    </Modal>
  )
}
