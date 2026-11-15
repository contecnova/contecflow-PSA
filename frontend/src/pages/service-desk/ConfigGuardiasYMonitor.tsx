/**
 * Guardias (quién atiende fuera de horas, por cola) y entrada de alertas de
 * monitorización. Las dos existían solo en el servidor.
 */
import { useState } from 'react'
import type { CSSProperties } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { openConfirmGlobal } from '../../context/ConfirmContext'
import { extractErr } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { Button, EmptyState, Modal, Spinner } from '../../components/ui'
import { COLOR } from '../../constants/theme'
import { sdGroupsApi, sdMonitoringApi, sdOnCallApi, usersApi, apiUrlAbsoluta, type UserListItem } from '../../services/api'
import type { SdCalendarioDeGuardia } from '../../services/api/tipos-sd'
import DateInput from '../../components/ui/DateInput'
import { POLL_DEFAULT_MS } from '../../constants/timings'
import { MONITORING_ALERTS_LIMIT } from '../../constants/pagination'
import './ConfigGuardiasYMonitor.css'

type Calendario = SdCalendarioDeGuardia
type Persona = UserListItem
type Cola = { id: string; name: string }

const IS: CSSProperties = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8,
  padding: '9px 13px', color: 'var(--text-1)', fontSize: 'var(--text-base)', outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
const fecha = (iso?: string | null) => iso ? new Date(iso).toLocaleString(undefined, { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—'

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
  const { data: personas = [] } = useQuery({ queryKey: ['users'], queryFn: () => usersApi.list().then(r => r.data) })
  const refrescar = () => { qc.invalidateQueries({ queryKey: ['sd-oncall'] }); qc.invalidateQueries({ queryKey: ['sd-oncall-now'] }) }
  const err = (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
  const crear = useMutation({ mutationFn: (d: unknown) => sdOnCallApi.createSchedule(d), onSuccess: () => { refrescar(); setNuevo(false) }, onError: err })
  const borrar = useMutation({ mutationFn: (id: string) => sdOnCallApi.deleteSchedule(id), onSuccess: refrescar, onError: err })
  const añadir = useMutation({ mutationFn: ({ id, ...d }: Record<string, unknown>) => sdOnCallApi.addShift(String(id), d), onSuccess: () => { refrescar(); setTurnoPara(null) }, onError: err })
  const quitar = useMutation({ mutationFn: (id: string) => sdOnCallApi.deleteShift(id), onSuccess: refrescar, onError: err })

  return (
    <div className="coguym-stack-1">
      <div className="coguym-box-1">{t('sd_cfg.oc_help')}</div>
      <div className="ds-card coguym-sp-1">
        <div className="coguym-ls2">{t('sd_cfg.oc_now')}</div>
        {ahora.length === 0 ? <div className="coguym-txt-2 config-guardias-ymonitor-e1" style={{ '--config-guardias-ymonitor-color': COLOR.warning } as CSSProperties}>{t('sd_cfg.oc_none_now')}</div>
          : ahora.map(a => (
            <div key={`${a.schedule_id}-${a.user_name}`} className="coguym-row-1">
              <strong>{a.user_name}</strong><span className="u-text2">{a.group_name}</span>
              <span className="u-text3">{t('sd_cfg.oc_until', { when: fecha(a.until) })}</span>
            </div>
          ))}
      </div>
      <div className="u-row-end"><Button onClick={() => setNuevo(true)}>+ {t('sd_cfg.oc_new')}</Button></div>
      {isLoading ? <Spinner /> : calendarios.length === 0 ? <EmptyState icon="🌙" title={t('sd_cfg.oc_empty')} description={t('sd_cfg.oc_help')} /> : calendarios.map(c => (
        <div key={c.id} className="ds-card coguym-stack-2">
          <div className="coguym-row-2">
            <strong className="u-flex1">{c.name}</strong>
            <span className="u-text2-sm">{c.group_name}</span>
            <Button variant="secondary" onClick={() => setTurnoPara(c)}>+ {t('sd_cfg.oc_add_shift')}</Button>
            <Button variant="secondary" onClick={() => openConfirmGlobal({ message: t('sd_cfg.chg_delete_confirm'), onConfirm: () => borrar.mutate(c.id), danger: true })}>
              <span className="config-guardias-ymonitor-e1" style={{ '--config-guardias-ymonitor-color': COLOR.danger } as CSSProperties}>{t('common.delete')}</span></Button>
          </div>
          {c.entries.length === 0 ? <div className="u-text3-sm">{t('sd_cfg.oc_no_shifts')}</div>
            : [...c.entries].sort((a, b) => a.start_dt.localeCompare(b.start_dt)).map(e => (
              <div key={e.id} className="coguym-row-3">
                <span className="coguym-box-2">{e.user_name}</span>
                <span className="coguym-box-3">{fecha(e.start_dt)} → {fecha(e.end_dt)}</span>
                <button className="coguym-box-5 config-guardias-ymonitor-e1" type="button" aria-label={t('common.delete')} onClick={() => quitar.mutate(e.id)}
                  style={{ '--config-guardias-ymonitor-color': COLOR.danger } as CSSProperties}>✕</button>
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
      <div><label className="coguym-ls" htmlFor="oc-name">{t('sd_cfg.chg_name')} *</label><input id="oc-name" aria-label={t('sd_cfg.chg_name')} value={nombre} onChange={e => setNombre(e.target.value)} className="coguym-is" /></div>
      <div><label className="coguym-ls" htmlFor="oc-queue">{t('sd_cfg.oc_queue')} *</label>
        <select id="oc-queue" aria-label={t('sd_cfg.oc_queue')} value={cola} onChange={e => setCola(e.target.value)} className="coguym-is">
          {colas.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select></div>
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
      <div><label className="coguym-ls" htmlFor="oc-person">{t('sd_cfg.oc_person')} *</label>
        <select id="oc-person" aria-label={t('sd_cfg.oc_person')} value={persona} onChange={e => setPersona(e.target.value)} className="coguym-is">
          {personas.map(p => <option key={p.id} value={p.id}>{p.full_name}</option>)}
        </select></div>
      <div className="u-grid2-10">
        <div><label className="coguym-ls" htmlFor="oc-from">{t('sd_cfg.chg_from')} *</label><DateInput id="oc-from" aria-label={t('sd_cfg.chg_from')} withTime value={desde} onChange={e => setDesde(e.target.value)} style={IS} /></div>
        <div><label className="coguym-ls" htmlFor="oc-to">{t('sd_cfg.chg_to')} *</label><DateInput id="oc-to" aria-label={t('sd_cfg.chg_to')} withTime value={hasta} onChange={e => setHasta(e.target.value)} style={IS} /></div>
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
      <div className="coguym-box-1">{t('sd_cfg.mon_intro')}</div>
      <div className="ds-card coguym-stack-3">
        <span className="coguym-ls">{t('sd_cfg.mon_url')}</span>
        <div className="u-row-8">
          <input readOnly value={url} aria-label={t('sd_cfg.mon_url')} className="coguym-is2" />
          <Button variant="secondary" onClick={() => { navigator.clipboard.writeText(url); toast.success(t('sd_cfg.mail_copy')) }}>{t('sd_cfg.mail_copy')}</Button>
        </div>
        <div className="u-text2-sm">{t('sd_cfg.mon_url_help')}</div>
        <div className="u-text2-sm">
          {t('sd_cfg.mon_token')} <a href="/settings?tab=integrations" className="u-accent">{t('sd_cfg.mail_credentials')}</a>
        </div>
      </div>
      <div>
        <span className="coguym-ls">{t('sd_cfg.mon_log')}</span>
        {isLoading ? <Spinner /> : alertas.length === 0 ? <div className="u-text3-sm">{t('sd_cfg.mon_empty')}</div> : (
          <div className="u-scroll-x">
            <table className="u-table-sm">
              <tbody>
                {alertas.map(a => (
                  <tr key={a.id} className="u-border-b">
                    <td className="coguym-box-4">{fecha(a.last_seen_at)}</td>
                    <td className="coguym-box-6 config-guardias-ymonitor-e1" style={{ '--config-guardias-ymonitor-color': a.status === 'firing' ? COLOR.danger : COLOR.success } as CSSProperties}>
                      {t(a.status === 'firing' ? 'sd_cfg.mon_firing' : 'sd_cfg.mon_resolved')}
                    </td>
                    <td className="coguym-sp-2">{a.title}<span className="u-text3"> · {a.source}{a.severity ? ` · ${a.severity}` : ''}</span></td>
                    <td className="coguym-box-4">{t('sd_cfg.mon_repeats', { n: a.occurrences })}</td>
                    <td className="coguym-sp-2">{a.ticket_id && <a href={`/service-desk?ticket=${a.ticket_id}`} className="coguym-txt-1">{a.ticket_number}</a>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
