// Politicas SLA del Service Desk: lista, asignacion y formulario. 23-11-2026: troceado de ConfigTab sin cambio de comportamiento.
import { useState, useId, useEffect } from 'react'
import type { ChangeEvent } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { openConfirmGlobal } from '../../context/ConfirmContext'
import { extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { useToast } from '../../context/ToastContext'
import { useAppT } from '../../i18n/AppLangContext'
import { CalendarDays, Pencil, Plus, Timer, Trash2 } from 'lucide-react'
import { AvisoDeConfiguracion, Button, Spinner, EmptyState, Modal, StatusBadge, Pulsable, Select, Checkbox, Input } from '../../components/ui'
import { settingsApi, sdSlaPoliciesApi, slaCalendarsApi, clientsApi, contractsApi } from '../../services/api'
import { PBadge } from './sdUtils'
import { SELECTOR_LIST_SIZE } from '../../constants/pagination'
import { type Calendario, LS_BASE, PRIORITY_LABEL_MAP, type Policy } from './ConfigTabComun'

// ── SLA Config ────────────────────────────────────────────────────────────────
export function SLAConfig() {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [showNew, setShowNew] = useState(false)

  const { data: policies = [], isLoading } = useQuery<Policy[]>({
    queryKey: ['sd-sla-policies'],
    queryFn: () => sdSlaPoliciesApi.list().then(r => r.data),
  })
  const { data: calendarios = [] } = useQuery<Calendario[]>({
    queryKey: ['sla-calendars'],
    queryFn: () => slaCalendarsApi.list().then(r => r.data),
  })
  const [editing, setEditing] = useState<Policy | null>(null)
  const [asignando, setAsignando] = useState<Policy | null>(null)
  const { mutate: create, isPending } = useMutation({
    mutationFn: (d: Record<string, unknown>) => sdSlaPoliciesApi.create(d),
    onSuccess: () => { qc.invalidateQueries({queryKey:['sd-sla-policies']}); setShowNew(false); toast.success(t('service_desk.sla_created')) },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
  })
  const { mutate: update } = useMutation({
    mutationFn: ({id, ...d}: { id: string } & Record<string, unknown>) => sdSlaPoliciesApi.update(id, d),
    onSuccess: () => { qc.invalidateQueries({queryKey:['sd-sla-policies']}); setEditing(null); toast.success(t('service_desk.sla_updated')) },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: remove } = useMutation({
    mutationFn: (id: string) => sdSlaPoliciesApi.delete(id),
    onSuccess: () => { qc.invalidateQueries({queryKey:['sd-sla-policies']}); toast.success(t('service_desk.sla_deleted')) },
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const LS = LS_BASE

  return (
    <div>
      <div className="sdcfg-head">
        <div className="sdcfg-head__desc">{policies.length > 0 && t('service_desk.sla_empty_desc')}</div>
        <Button icon={<Plus size={14} />} onClick={() => setShowNew(true)}>{t('sd_cfg.cfg_sla_new')}</Button>
      </div>

      {isLoading ? <Spinner /> :
       policies.length === 0 ? <EmptyState icon={<Timer size={28} />} title={t('service_desk.sla_empty')} description={t('sd_cfg.cfg_sla_empty_desc')} /> :
      <div className="u-stack-12">
        {policies.map((p: Policy) => (
          <div key={p.id} className="ds-card">
            <div className="sdcfg-sla-head">
              <span className="sdcfg-name">{p.name}</span>
              {p.is_default && <StatusBadge kind="accent" caps={false}>{t('service_desk.sla_default_policy')}</StatusBadge>}
              <StatusBadge caps={false}>
                {p.business_hours_only === false ? t('config.horario_24x7')
                  : p.calendar_id ? <span className="u-row-center-6"><CalendarDays size={12} aria-hidden="true" />{calendarios.find(c => c.id === p.calendar_id)?.name ?? t('sd_cfg.schedule_calendars')}</span>
                  : `${p.business_start ?? ''}–${p.business_end ?? ''} h${p.timezone ? ` · ${p.timezone}` : ''}`}
              </StatusBadge>
              <div className="sdcfg-push-right">
                <Button size="xs" variant="secondary" icon={<Pencil size={12} />} onClick={() => setEditing(p)}>{t('common.edit')}</Button>
                <Button size="xs" variant="ghost" icon={<Trash2 size={12} />} onClick={() => { openConfirmGlobal({ message: t('config.confirmar_eliminar_sla'), onConfirm: () => remove(p.id), danger: true }) }}>{t('common.delete')}</Button>
              </div>
            </div>
            <div className="sdcfg-used-by">
              <span><strong>{t('sd_cfg.sla_used_by')}:</strong> {[...(p.clients ?? []), ...(p.contracts ?? [])].map(x => x.name).join(', ') || t('sd_cfg.sla_nobody')}</span>
              <Button size="xs" variant="secondary" onClick={() => setAsignando(p)}>{t('sd_cfg.sla_assign')}</Button>
            </div>
            <div className="sdcfg-prio-grid">
              {[['p1_critical', 'p1'], ['p2_high', 'p2'], ['p3_medium', 'p3'], ['p4_low', 'p4']].map(([prio, key]) => (
                <div key={key} className="sdcfg-prio">
                  <div className="sdcfg-prio__label"><PBadge v={prio} /></div>
                  <div className="u-text2-sm">
                    <div>{t('sd_cfg.cfg_response')} <strong className="u-text1">{p[`${key}_response_hours`] as number} h</strong></div>
                    <div>{t('sd_cfg.cfg_resolution')} <strong className="u-text1">{p[`${key}_resolution_hours`] as number} h</strong></div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>}

      {showNew && (
        <Modal open title={t('sd_cfg.cfg_sla_new')} onClose={() => setShowNew(false)} size="lg">
          <NewSLAForm LS={LS} onSave={d => create(d)} isPending={isPending} onClose={() => setShowNew(false)} />
        </Modal>
      )}
      {asignando && (
        <Modal open title={`${t('sd_cfg.sla_assign')} · ${asignando.name}`} onClose={() => setAsignando(null)}>
          <AsignarPolitica politica={asignando} LS={LS} onHecho={() => { qc.invalidateQueries({queryKey:['sd-sla-policies']}); setAsignando(null) }} />
        </Modal>
      )}
      {editing && (
        <Modal open title={t('sd_cfg.cfg_sla_edit')} onClose={() => setEditing(null)} size="lg">
          <NewSLAForm LS={LS} initial={editing}
            onSave={d => update({id: editing.id, ...d})}
            isPending={false} onClose={() => setEditing(null)} />
        </Modal>
      )}
    </div>
  )
}

function AsignarPolitica({ politica, LS: _LS, onHecho }: { politica: Policy; LS: string; onHecho: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const [tipo, setTipo] = useState<'client' | 'contract'>('client')
  const [destino, setDestino] = useState('')
  const { data: opciones = [] } = useQuery<{ id: string; name?: string; title?: string }[]>({
    queryKey: ['sla-assign-targets', tipo],
    queryFn: () => (tipo === 'client' ? clientsApi.list() : contractsApi.list({ page_size: SELECTOR_LIST_SIZE }))
      .then(r => r.data as { id: string; name?: string; title?: string }[]),
  })
  const asignar = useMutation({
    mutationFn: () => sdSlaPoliciesApi.assign(tipo, destino, politica.id),
    onSuccess: onHecho,
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  return (
    <div className="u-stack-12">
      <Select label={t('sd_cfg.sla_target_type')} placeholder={false} id="sla-asig-tipo" aria-label={t('sd_cfg.sla_target_type')} value={tipo} onChange={e => { setTipo(e.target.value as 'client' | 'contract'); setDestino('') }}>
          <option value="client">{t('sd_cfg.sla_target_client')}</option>
          <option value="contract">{t('sd_cfg.sla_target_contract')}</option>
        </Select>
      <Select label={tipo === 'client' ? t('sd_cfg.sla_target_client') : t('sd_cfg.sla_target_contract')} placeholder={false} id="sla-asig-destino" aria-label={t('sd_cfg.sla_target_client')} value={destino} onChange={e => setDestino(e.target.value)}>
          <option value="">—</option>
          {opciones.map(o => <option key={o.id} value={o.id}>{o.name ?? o.title ?? o.id}</option>)}
        </Select>
      <div className="u-row-end">
        <Button disabled={!destino || asignar.isPending} loading={asignar.isPending} onClick={() => asignar.mutate()}>{t('common.save')}</Button>
      </div>
    </div>
  )
}

const ZONAS: string[] = (() => {
  try { return (Intl as unknown as { supportedValuesOf: (k: string) => string[] }).supportedValuesOf('timeZone') } catch { /* accesorio: navegador sin Intl.supportedValuesOf; la zona horaria se teclea a mano */ return [] }
})()

function horarioDe(p?: Policy | null): string {
  if (!p) return 'own'
  if (p.business_hours_only === false) return '247'
  return p.calendar_id ? `cal:${p.calendar_id}` : 'own'
}

function NewSLAForm({ LS, onSave, isPending, onClose, initial }: { LS: string; onSave: (d: Record<string, unknown>) => void; isPending: boolean; onClose: () => void; initial?: Policy | null }) {
  const idCampo = useId()
  const t = useAppT()
  const { data: calendarios = [] } = useQuery<Calendario[]>({
    queryKey: ['sla-calendars'],
    queryFn: () => slaCalendarsApi.list().then(r => r.data),
  })
  const [form, setForm] = useState({
    name: initial?.name || '', description: initial?.description || '',
    is_default: initial?.is_default || false,
    p1_response_hours: initial?.p1_response_hours ?? 1, p1_resolution_hours: initial?.p1_resolution_hours ?? 4,
    p2_response_hours: initial?.p2_response_hours ?? 4, p2_resolution_hours: initial?.p2_resolution_hours ?? 8,
    p3_response_hours: initial?.p3_response_hours ?? 8, p3_resolution_hours: initial?.p3_resolution_hours ?? 24,
    p4_response_hours: initial?.p4_response_hours ?? 24, p4_resolution_hours: initial?.p4_resolution_hours ?? 72,
    business_start: initial?.business_start ?? 9, business_end: initial?.business_end ?? 18,
    timezone: initial?.timezone || '',
  })
  const [horario, setHorario] = useState(horarioDe(initial))
  const [dias, setDias] = useState<number[]>(
    (initial?.business_days || '1,2,3,4,5').split(',').map(Number).filter(Boolean))
  // 19-11-2026: una política nueva parte de los SLA de la empresa (grupo `sla`:
  // SLA_P*_*_HOURS, SLA_BUSINESS_START/END_HOUR, SLA_BUSINESS_DAYS) y no de unos
  // valores escritos aquí (9-18 frente al 8-18 del ajuste). Sin permiso para
  // leerlos (403) se queda con los de siempre.
  const { data: slaEmpresa } = useQuery({
    queryKey: ['runtime-flags', 'sla'],
    queryFn: () => settingsApi.runtimeGroup('sla').then(r => r.data),
    enabled: !initial, retry: false,
  })
  const [tocado, setTocado] = useState(false)
  useEffect(() => {
    if (initial || tocado || !slaEmpresa?.items) return
    const v = Object.fromEntries(slaEmpresa.items.map(i => [i.key, i.value]))
    const num = (k: string) => (v[k] == null || v[k] === '' ? undefined : Number(v[k]))
    setForm(f => {
      const nuevo: Record<string, unknown> = { ...f }
      for (const p of [1, 2, 3, 4]) {
        for (const tipo of ['response', 'resolution']) {
          const valor = num(`SLA_P${p}_${tipo.toUpperCase()}_HOURS`)
          if (valor != null) nuevo[`p${p}_${tipo}_hours`] = valor
        }
      }
      if (num('SLA_BUSINESS_START_HOUR') != null) nuevo.business_start = num('SLA_BUSINESS_START_HOUR')
      if (num('SLA_BUSINESS_END_HOUR') != null) nuevo.business_end = num('SLA_BUSINESS_END_HOUR')
      return nuevo as typeof f
    })
    const diasEmpresa = String(v.SLA_BUSINESS_DAYS ?? '').split(',').map(Number).filter(d => d >= 1 && d <= 7)
    if (diasEmpresa.length) setDias(diasEmpresa)
  }, [slaEmpresa, initial, tocado])
  const set = (k: string) => (e: ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    setTocado(true)
    setForm(f => ({...f, [k]: (e.target as HTMLInputElement).type==='checkbox' ? (e.target as HTMLInputElement).checked : e.target.value}))
  }
  const formRec = form as Record<string, unknown>
  const nombresDias = t('sd_cfg.days_short').split(',')
  const propio = horario === 'own'
  const valido = !!form.name && (!propio || (dias.length > 0 && Number(form.business_end) > Number(form.business_start)))

  const enviar = () => {
    const horas = Object.fromEntries(['p1','p2','p3','p4'].flatMap(k => [
      [`${k}_response_hours`, Number(formRec[`${k}_response_hours`])],
      [`${k}_resolution_hours`, Number(formRec[`${k}_resolution_hours`])],
    ]))
    onSave({
      name: form.name, description: form.description, is_default: form.is_default, ...horas,
      business_hours_only: horario !== '247',
      calendar_id: horario.startsWith('cal:') ? horario.slice(4) : null,
      business_start: Number(form.business_start), business_end: Number(form.business_end),
      business_days: [...dias].sort().join(','), timezone: form.timezone || null,
    })
  }

  return (
    <div className="u-grid2-14">
      <div className="u-col-full"><Input label={<>{t('common.name')} *</>} id={`${idCampo}-1`} value={form.name} onChange={set('name')} /></div>
      {[['p1_critical', 'p1'], ['p2_high', 'p2'], ['p3_medium', 'p3'], ['p4_low', 'p4']].map(([prio, key]) => (
        <div key={key} className="sdcfg-box">
          <div className="sdcfg-box__title">{PRIORITY_LABEL_MAP[prio]}</div>
          <div className="sdcfg-grid2-8">
            <div><Input label={t('service_desk.sla_response_h')} id={`${idCampo}-${key}-resp`} type="number" min={0} step="0.25" value={formRec[`${key}_response_hours`] as number} onChange={set(`${key}_response_hours`)} /></div>
            <div><Input label={t('service_desk.sla_resolution_h')} id={`${idCampo}-${key}-resol`} type="number" min={0} step="0.25" value={formRec[`${key}_resolution_hours`] as number} onChange={set(`${key}_resolution_hours`)} /></div>
          </div>
        </div>
      ))}
      <div className="sdcfg-box sdcfg-box--full">
        <div>
          <Select label={t('sd_cfg.schedule')} placeholder={false} id="sla-horario" value={horario} onChange={e => setHorario(e.target.value)}>
            <option value="247">{t('sd_cfg.schedule_247')}</option>
            {calendarios.length > 0 && (
              <optgroup label={t('sd_cfg.schedule_calendars')}>
                {calendarios.map(c => <option key={c.id} value={`cal:${c.id}`}>{c.name} · {c.work_start}–{c.work_end} · {c.timezone}</option>)}
              </optgroup>
            )}
            <option value="own">{t('sd_cfg.schedule_own')}</option>
          </Select>
          <div className="sdcfg-hint">
            {t('sd_cfg.schedule_hint')} <AvisoDeConfiguracion seccion="sla-calendars" variante="enlace" texto={t('sd_cfg.manage_calendars')} />
          </div>
        </div>
        {propio && (
          <div className="sdcfg-hours-grid">
            <div><Input label={t('sd_cfg.start_hour')} id="sla-ini" type="number" min={0} max={23} value={form.business_start} onChange={set('business_start')} /></div>
            <div><Input label={t('sd_cfg.end_hour')} id="sla-fin" type="number" min={1} max={24} value={form.business_end} onChange={set('business_end')} /></div>
            <div className="sdcfg-span2"><Input label={t('sd_cfg.timezone')} id="sla-zona" list="sla-zonas" value={form.timezone} placeholder={t('sd_cfg.timezone_org')} onChange={set('timezone')} />
              <datalist id="sla-zonas">{ZONAS.map(z => <option key={z} value={z} aria-label={z} />)}</datalist></div>
            <div className="u-col-full" role="group" aria-labelledby="sla-dias-et">
              <span id="sla-dias-et" className={LS}>{t('sd_cfg.workdays')}</span>
              <div className="u-wrap-6">
                {nombresDias.map((nombre, i) => {
                  const d = i + 1
                  const on = dias.includes(d)
                  return (
                    <Pulsable key={d} aria-pressed={on}
                      onClick={() => setDias(on ? dias.filter(x => x !== d) : [...dias, d])}
                      className="sdcfg-day">{nombre}</Pulsable>
                  )
                })}
              </div>
            </div>
          </div>
        )}
      </div>
      <div className="sdcfg-full-row">
        <Checkbox className="sdcfg-check-row" aria-label={t('service_desk.sla_default_policy')} checked={!!form.is_default} onChange={v => setForm(f => ({...f, is_default: v}))} label={t('service_desk.sla_default_policy')} />
      </div>
      <div className="sdcfg-full-actions">
        <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
        <Button onClick={enviar} disabled={isPending || !valido} loading={isPending}>{initial ? t('common.save') : t('sd_cfg.cfg_sla_new')}</Button>
      </div>
    </div>
  )
}
