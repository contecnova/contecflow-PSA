/**
 * Guardias (quién atiende fuera de horas, por cola) y entrada de alertas de
 * monitorización. Las dos existían solo en el servidor.
 *
 * 16-11-2026 (pasada de diseño): acción principal en la barra con icono Plus,
 * vacíos con EmptyState e icono lucide, quitar turno/borrar con Button ghost,
 * estados con StatusBadge, campos con `ds-input` y fechas con fmtDateTime
 * (antes toLocaleString sin idioma de la app).
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Activity, CalendarClock, Copy, Plus, Trash2, X } from 'lucide-react'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { Link } from 'react-router-dom'
import { openConfirmGlobal } from '../../context/ConfirmContext'
import { useListaDeUsuarios } from '../../hooks/useListas'
import { extractErr, fmtDateTime } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { AvisoDeConfiguracion, Button, EmptyState, Modal, Select, Spinner, StatusBadge, TablaSimple, Input, IconButton } from '../../components/ui'
import { sdGroupsApi, sdMonitoringApi, sdOnCallApi, apiUrlAbsoluta, type UserListItem } from '../../services/api'
import type { SdCalendarioDeGuardia } from '../../services/api/tipos-sd'
import DateInput from '../../components/ui/DateInput'
import { POLL_DEFAULT_MS } from '../../constants/timings'
import { MONITORING_ALERTS_LIMIT } from '../../constants/pagination'
import './ConfigGuardiasYMonitor.css'

type Calendario = SdCalendarioDeGuardia
type Persona = UserListItem
type Cola = { id: string; name: string }

const fecha = (iso?: string | null) => iso ? fmtDateTime(iso) : '—'

export function GuardiasConfig() {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [nuevo, setNuevo] = useState(false)
  const [turnoPara, setTurnoPara] = useState<Calendario | null>(null)
  const { data: calendarios = [], isLoading } = useQuery({
    queryKey: ['sd-oncall'], queryFn: () => sdOnCallApi.schedules().then(r => r.data),
  })
  const { data: ahora = [] } = useQuery({
    queryKey: ['sd-oncall-now'], queryFn: () => sdOnCallApi.current().then(r => r.data), refetchInterval: POLL_DEFAULT_MS,
  })
  const { data: colas = [] } = useQuery<Cola[]>({ queryKey: ['sd-groups'], queryFn: () => sdGroupsApi.list().then(r => r.data) })
  const { data: personas = [] } = useListaDeUsuarios()
  const refrescar = () => { qc.invalidateQueries({ queryKey: ['sd-oncall'] }); qc.invalidateQueries({ queryKey: ['sd-oncall-now'] }) }
  const err = (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
  const crear = useMutation({ mutationFn: (d: unknown) => sdOnCallApi.createSchedule(d), onSuccess: () => { refrescar(); setNuevo(false) }, onError: err })
  const borrar = useMutation({ mutationFn: (id: string) => sdOnCallApi.deleteSchedule(id), onSuccess: refrescar, onError: err })
  const añadir = useMutation({ mutationFn: ({ id, ...d }: Record<string, unknown>) => sdOnCallApi.addShift(String(id), d), onSuccess: () => { refrescar(); setTurnoPara(null) }, onError: err })
  const quitar = useMutation({ mutationFn: (id: string) => sdOnCallApi.deleteShift(id), onSuccess: refrescar, onError: err })

  return (
    <div className="coguym-stack-1">
      <div className="coguym-head">
        <div className="coguym-intro">{t('sd_cfg.oc_help')}</div>
        <Button icon={<Plus size={14} />} onClick={() => setNuevo(true)}>{t('sd_cfg.oc_new')}</Button>
      </div>
      <div className="ds-card">
        <div className="coguym-ls">{t('sd_cfg.oc_now')}</div>
        {ahora.length === 0 ? <div><StatusBadge kind="warning" caps={false}>{t('sd_cfg.oc_none_now')}</StatusBadge></div>
          : ahora.map(a => (
            <div key={`${a.schedule_id}-${a.user_name}`} className="coguym-row-1">
              <strong>{a.user_name}</strong><span className="u-text2">{a.group_name}</span>
              <span className="u-text2">{t('sd_cfg.oc_until', { when: fecha(a.until) })}</span>
            </div>
          ))}
      </div>
      {isLoading ? <Spinner /> : calendarios.length === 0 ? <EmptyState icon={<CalendarClock size={28} />} title={t('sd_cfg.oc_empty')} description={t('sd_cfg.cfg_oc_empty_desc')} /> : calendarios.map(c => (
        <div key={c.id} className="ds-card">
          <div className="coguym-row-2">
            <strong className="u-flex1-min0">{c.name}</strong>
            <StatusBadge caps={false}>{c.group_name}</StatusBadge>
            <Button size="xs" variant="secondary" icon={<Plus size={12} />} onClick={() => setTurnoPara(c)}>{t('sd_cfg.oc_add_shift')}</Button>
            <Button size="xs" variant="ghost" icon={<Trash2 size={12} />} onClick={() => openConfirmGlobal({ message: t('sd_cfg.chg_delete_confirm'), onConfirm: () => borrar.mutate(c.id), danger: true })}>
              {t('common.delete')}</Button>
          </div>
          {c.entries.length === 0 ? <div className="u-text2-sm">{t('sd_cfg.oc_no_shifts')}</div>
            : [...c.entries].sort((a, b) => a.start_dt.localeCompare(b.start_dt)).map(e => (
              <div key={e.id} className="coguym-row-3">
                <span className="coguym-persona">{e.user_name}</span>
                <span className="coguym-tramo">{fecha(e.start_dt)} – {fecha(e.end_dt)}</span>
                <IconButton variante="caja" tono="peligro" ariaLabel={t('common.delete')} onClick={() => openConfirmGlobal({ message: t('sd_cfg.oc_confirmar_quitar_turno', { name: e.user_name }), confirmLabel: t('common.delete'), onConfirm: () => quitar.mutate(e.id), danger: true })}><X size={12} /></IconButton>
              </div>
            ))}
        </div>
      ))}
      {nuevo && (
        <Modal open title={t('sd_cfg.oc_new')} onClose={() => setNuevo(false)}>
          <FormCalendario colas={colas} pendiente={crear.isPending} onCancelar={() => setNuevo(false)} onGuardar={d => crear.mutate(d)} />
        </Modal>
      )}
      {turnoPara && (
        <Modal open title={`${t('sd_cfg.oc_add_shift')} · ${turnoPara.name}`} onClose={() => setTurnoPara(null)}>
          <FormTurno personas={personas} pendiente={añadir.isPending} onCancelar={() => setTurnoPara(null)}
            onGuardar={d => añadir.mutate({ id: turnoPara.id, ...d })} />
        </Modal>
      )}
    </div>
  )
}

function FormCalendario({ colas, pendiente, onCancelar, onGuardar }: { colas: Cola[]; pendiente: boolean; onCancelar: () => void; onGuardar: (d: Record<string, unknown>) => void }) {
  const t = useAppT()
  const [nombre, setNombre] = useState('')
  const [cola, setCola] = useState(colas[0]?.id ?? '')
  return (
    <div className="u-stack-12">
      <Input label={<>{t('sd_cfg.chg_name')}*</>} id="oc-name" aria-label={t('sd_cfg.chg_name')} value={nombre} onChange={e => setNombre(e.target.value)} />
      <Select label={<>{t('sd_cfg.oc_queue')}*</>} placeholder={false} id="oc-queue" aria-label={t('sd_cfg.oc_queue')} value={cola} onChange={e => setCola(e.target.value)}>
          {colas.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
        </Select>
      <div className="u-actions-10">
        <Button variant="secondary" onClick={onCancelar}>{t('common.cancel')}</Button>
        <Button disabled={!nombre.trim() || !cola || pendiente} loading={pendiente} onClick={() => onGuardar({ name: nombre.trim(), group_id: cola })}>{t('common.save')}</Button>
      </div>
    </div>
  )
}

function FormTurno({ personas, pendiente, onCancelar, onGuardar }: { personas: Persona[]; pendiente: boolean; onCancelar: () => void; onGuardar: (d: Record<string, unknown>) => void }) {
  const t = useAppT()
  const [persona, setPersona] = useState(personas[0]?.id ?? '')
  const [desde, setDesde] = useState('')
  const [hasta, setHasta] = useState('')
  const valido = persona && desde && hasta && hasta > desde
  return (
    <div className="u-stack-12">
      <Select label={<>{t('sd_cfg.oc_person')}*</>} placeholder={false} id="oc-person" aria-label={t('sd_cfg.oc_person')} value={persona} onChange={e => setPersona(e.target.value)}>
          {personas.map(p => <option key={p.id} value={p.id}>{p.full_name}</option>)}
        </Select>
      <div className="u-grid2-10">
        <DateInput label={<>{t('sd_cfg.chg_from')}*</>} id="oc-from" aria-label={t('sd_cfg.chg_from')} withTime value={desde} onChange={e => setDesde(e.target.value)} />
        <DateInput label={<>{t('sd_cfg.chg_to')}*</>} id="oc-to" aria-label={t('sd_cfg.chg_to')} withTime value={hasta} onChange={e => setHasta(e.target.value)} />
      </div>
      <div className="u-actions-10">
        <Button variant="secondary" onClick={onCancelar}>{t('common.cancel')}</Button>
        <Button disabled={!valido || pendiente} loading={pendiente}
          onClick={() => onGuardar({ user_id: persona, start_dt: new Date(desde).toISOString(), end_dt: new Date(hasta).toISOString() })}>{t('common.save')}</Button>
      </div>
    </div>
  )
}

export function MonitorizacionConfig() {
  const t = useAppT()
  const toast = useToast()
  const url = apiUrlAbsoluta('/sd/events/prometheus')
  const { data: alertas = [], isLoading } = useQuery({
    queryKey: ['sd-monitoring-alerts'], queryFn: () => sdMonitoringApi.alerts(MONITORING_ALERTS_LIMIT).then(r => r.data), refetchInterval: POLL_DEFAULT_MS,
  })
  return (
    <div className="coguym-stack-1">
      <div className="coguym-intro">{t('sd_cfg.mon_intro')}</div>
      <div className="ds-card">
        <span className="coguym-ls">{t('sd_cfg.mon_url')}</span>
        <div className="coguym-copy">
          <Input readOnly value={url} aria-label={t('sd_cfg.mon_url')} className="coguym-url" inputClassName="ds-campo-codigo" />
          <Button variant="secondary" icon={<Copy size={14} />} onClick={() => { navigator.clipboard.writeText(url).then(() => toast.success(t('sd_cfg.cfg_copied')), () => toast.error(t('sd_cfg.cfg_copy_failed'))) }}>{t('sd_cfg.mail_copy')}</Button>
        </div>
        <div className="u-text2-sm">{t('sd_cfg.mon_url_help')}</div>
        <div className="u-text2-sm">
          {t('sd_cfg.mon_token')} <AvisoDeConfiguracion seccion="integrations" variante="enlace" texto={t('sd_cfg.mail_credentials')} />
        </div>
      </div>
      <div>
        <span className="coguym-ls">{t('sd_cfg.mon_log')}</span>
        {isLoading ? <Spinner /> : alertas.length === 0 ? <EmptyState icon={<Activity size={28} />} title={t('sd_cfg.mon_empty')} /> : (
          <div className="u-scroll-x">
            <TablaSimple claseTabla="u-table-sm">
              <tbody>
                {alertas.map(a => (
                  <tr key={a.id} className="u-border-b">
                    <td className="coguym-fecha">{fecha(a.last_seen_at)}</td>
                    <td className="coguym-celda">
                      <StatusBadge kind={a.status === 'firing' ? 'danger' : 'success'} caps={false}>
                        {t(a.status === 'firing' ? 'sd_cfg.mon_firing' : 'sd_cfg.mon_resolved')}
                      </StatusBadge>
                    </td>
                    <td className="coguym-celda">{a.title}<span className="u-text2"> · {a.source}{a.severity ? ` · ${a.severity}` : ''}</span></td>
                    <td className="coguym-fecha">{t('sd_cfg.mon_repeats', { n: a.occurrences })}</td>
                    <td className="coguym-celda">{a.ticket_id && <Link to={`/service-desk?ticket=${a.ticket_id}`} className="coguym-enlace">{a.ticket_number}</Link>}</td>
                  </tr>
                ))}
              </tbody>
            </TablaSimple>
          </div>
        )}
      </div>
    </div>
  )
}
