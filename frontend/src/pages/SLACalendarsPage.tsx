/**
 * SLACalendarsPage — calendarios laborables y festivos para el cómputo de SLA.
 *
 * 16-11-2026: vacío con EmptyState (antes emoji grande suelto en una caja);
 * acción principal con icono y sin "+" en el texto; cada calendario es una
 * Card con iconos lucide en lugar de emojis y Button del kit; la comprobación
 * de fecha muestra la fecha y el día con el formato del idioma (antes ISO y el
 * nombre del día tal como llegaba del servidor) e iconos en lugar de emojis.
 */
import { useState, useId } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr, fmtDate, localeActivo } from '../utils/helpers'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { slaCalendarsApi, type SlaCalendar } from '../services/api'
import type { SdComprobacionDeDia } from '../services/api/tipos-sd'
import { Button, Card, EmptyState, IconButton, Spinner, Modal, Select, Pulsable, Checkbox, useErroresDeCampo, Input } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { CalendarClock, CalendarDays, Check, CheckCircle2, Clock, Globe, Pencil, Plus, Trash2, X, XCircle } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import { useOrgSettings } from '../hooks/useOrgSettings'
import { timezoneOptions } from '../constants/timezones'
import DateInput from '../components/ui/DateInput'
import { CampoFecha } from '../components/ui/SelectorDeFecha'
import './SLACalendarsPage.css'

/** Días ISO (1 = lunes … 7 = domingo) con su nombre corto en el idioma activo. */
const DIAS_ISO = [1, 2, 3, 4, 5, 6, 7]
function nombreCortoDelDia(d: number): string {
  // 2024-01-01 fue lunes: el día ISO d cae el 2024-01-d.
  return new Intl.DateTimeFormat(localeActivo(), { weekday: 'short' }).format(new Date(2024, 0, d))
}
/** Nombre largo del día de una fecha ISO (AAAA-MM-DD) en el idioma activo. */
function nombreDelDia(iso: string): string {
  const [y, m, d] = iso.split('-').map(Number)
  if (!y || !m || !d) return ''
  return new Intl.DateTimeFormat(localeActivo(), { weekday: 'long' }).format(new Date(y, m - 1, d))
}

function CalendarForm({ cal, onClose }: { cal?: SlaCalendar | null; onClose: () => void }) {
  const idCampo = useId()
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const { timezone: defaultTimezone } = useOrgSettings()
  const isEdit = !!cal?.id
  const parseDays = (s?: string) => new Set((s||'1,2,3,4,5').split(',').map(Number))
  const [form, setForm] = useState({
    name:      cal?.name       || '',
    timezone:  cal?.timezone   || defaultTimezone,
    work_start:cal?.work_start || '09:00',
    work_end:  cal?.work_end   || '18:00',
    work_days: parseDays(cal?.work_days),
  })
  // Festivos generales de la empresa (migración 174): cuentan en todos sus SLA.
  const [general, setGeneral] = useState<boolean>(!!cal?.applies_to_all)
  const set = (k: 'name' | 'timezone' | 'work_start' | 'work_end' | 'work_days') => (v: string | Set<number>) => setForm((f) => ({ ...f, [k]: v }))
  const toggleDay = (d: number) => {
    const s = new Set(form.work_days)
    if (s.has(d)) { if(s.size>1) s.delete(d) } else s.add(d)
    set('work_days')(s)
  }

  const campos = useErroresDeCampo()
  const msg = (k: string) => campos.de(k) ? <div className="u-field-error">{campos.de(k)}</div> : null
  const { mutate, isPending } = useMutation({
    onMutate: () => campos.limpiar(),
    mutationFn: () => {
      const d = {...form, work_days: [...form.work_days].sort().join(','), applies_to_all: general}
      return isEdit
        ? slaCalendarsApi.update(cal.id, d).then(r=>r.data)
        : slaCalendarsApi.create(d).then(r=>r.data)
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sla-calendars'] }); onClose() },
    onError: (e: unknown) => { if (!campos.recoger(e)) toast.error(extractErr(e, t('sla_calendars_page.error_guardar'))) },
  })

  return (
    <Modal open onClose={onClose} title={isEdit ? t('sla_calendars_page.editar_calendario') : t('sla_calendars_page.nuevo_calendario')}>
      <div className="u-stack-14">
        <div>
          <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="slac-label">{t('sla_calendars_page.nombre')}</label>
          <Input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.name} onChange={e => set('name')(e.target.value)} placeholder={t('sla_calendars_page.nombre_ph')} inputClassName="slac-input" />{msg('name')}
        </div>
        <div>
          <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="slac-label">{t('sla_calendars_page.zona_horaria')}</label>
          <Select suelto placeholder={false} id={`${idCampo}-2`} className="slac-input" value={form.timezone} onChange={e => set('timezone')(e.target.value)}>
            {timezoneOptions(form.timezone).map(tz => <option key={tz} value={tz}>{tz}</option>)}
          </Select>{msg('timezone')}
        </div>
        <div className="u-grid2-12">
          <div>
            <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="slac-label">{t('sla_calendars_page.inicio_jornada')}</label>
            <CampoFecha modo="hora" id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} className="slac-input" value={form.work_start}
              onChange={v => set('work_start')(v)} />{msg('work_start')}
          </div>
          <div>
            <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="slac-label">{t('sla_calendars_page.fin_jornada')}</label>
            <CampoFecha modo="hora" id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} className="slac-input" value={form.work_end}
              onChange={v => set('work_end')(v)} />{msg('work_end')}
          </div>
        </div>
        <fieldset className="slac-days ds-grupo-opciones">
          <legend className="slac-label">{t('slacalendars.dias_laborables')}</legend>
          <div className="u-wrap-8">
            {DIAS_ISO.map(d => {
              const active = form.work_days.has(d)
              return (
                <Pulsable key={d} type="button" onClick={() => toggleDay(d)} aria-pressed={active}
                  className={`slac-day${active ? ' slac-day--active' : ''}`}>
                  {nombreCortoDelDia(d)}
                </Pulsable>
              )
            })}
          </div>
        </fieldset>
        <Checkbox className="u-row-center-8" checked={!!general} onChange={setGeneral}
          label={t('sd_mercado.festivos_generales')} />
        <div className="u-text3-xs">{t('sd_mercado.festivos_generales_hint')}</div>
        <div className="slac-actions">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={() => mutate()} disabled={isPending || !form.name.trim()} loading={isPending}>
            {isPending ? t('common.saving') : isEdit ? t('common.save') : t('sla_calendars_page.crear_calendario')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

function HolidaysModal({ cal, onClose }: { cal: SlaCalendar; onClose: () => void }) {
  const idCampo = useId()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [date, setDate] = useState('')
  const [name, setName] = useState('')
  const [checkDate, setCheckDate] = useState('')
  const [checkResult, setCheckResult] = useState<SdComprobacionDeDia | null>(null)
  const [editingId, setEditingId] = useState<string | number | null>(null)
  const [editForm, setEditForm] = useState({ holiday_date: '', name: '' })

  const { data: holidays = [] } = useQuery({
    queryKey: ['holidays', cal.id],
    queryFn: () => slaCalendarsApi.holidays(cal.id).then(r => r.data),
  })

  const campos = useErroresDeCampo()
  const msg = (k: string) => campos.de(k) ? <div className="u-field-error">{campos.de(k)}</div> : null
  const { mutate: addH, isPending } = useMutation({
    onMutate: () => campos.limpiar(),
    mutationFn: () => slaCalendarsApi.createHoliday(cal.id, {holiday_date:date, name:name||null}).then(r=>r.data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['holidays', cal.id] }); setDate(''); setName('') },
    onError: (e: unknown) => { if (!campos.recoger(e)) toast.error(extractErr(e, t('sla_calendars_page.error_anadir'))) },
  })
  const camposB = useErroresDeCampo()
  const msgB = (k: string) => camposB.de(k) ? <div className="u-field-error">{camposB.de(k)}</div> : null
  const { mutate: updateH } = useMutation({
    onMutate: () => camposB.limpiar(),
    mutationFn: (id: string | number) => slaCalendarsApi.updateHoliday(cal.id, id, { holiday_date: editForm.holiday_date, name: editForm.name || null }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['holidays', cal.id] }); setEditingId(null) },
    onError: (e: unknown) => { if (!camposB.recoger(e)) toast.error(extractErr(e, t('sla_calendars_page.error_editar'))) },
  })
  const { mutate: delH } = useMutation({
    mutationFn: (id: string | number) => slaCalendarsApi.deleteHoliday(cal.id, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['holidays', cal.id] }),
    onError: (e: unknown) => toast.error(extractErr(e, t('sla_calendars_page.error_generico'))),
  })

  const checkBusinessDay = async () => {
    try {
      const r = await slaCalendarsApi.checkDate(cal.id, checkDate)
      setCheckResult(r.data)
    } catch(e: unknown) {
      toast.error(extractErr(e, t('sla_calendars_page.error_verificar')))
    }
  }

  const sinNombre = t('sla_calendars_page.sin_nombre')

  return (
    <Modal open onClose={onClose} title={t('sla_calendars_page.festivos_de', { nombre: cal.name })}>
      <div className="u-stack-14">
        {/* Añadir festivo */}
        <div className="slac-add">
          <div>
            <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="slac-label">{t('sla_calendars_page.fecha')}</label>
            <DateInput id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} className="slac-input" value={date} onChange={e => setDate(e.target.value)} />{msg('holiday_date')}
          </div>
          <div>
            <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="slac-label">{t('sla_calendars_page.nombre_opcional')}</label>
            <Input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={name} onChange={e => setName(e.target.value)} placeholder={t('sla_calendars_page.festivo_ph')} inputClassName="slac-input" />{msg('name')}
          </div>
          <Button icon={<Plus size={14} />} onClick={() => addH()} disabled={isPending || !date} loading={isPending}>
            {t('sla_calendars_page.anadir')}
          </Button>
        </div>

        {/* Lista de festivos */}
        <div className="slac-list">
          {holidays.length === 0 ? (
            <EmptyState icon={<CalendarDays size={28} />} title={t('slacalendars.sin_festivos_registrados')} description={t('sla_calendars_page.sin_festivos_desc')} />
          ) : holidays.map(h => (
            <div key={h.id} className="slac-list__item">
              {editingId === h.id ? (
                <div className="slac-edit-row">
                  <DateInput value={editForm.holiday_date} aria-label={t('sla_calendars_page.fecha')}
                    onChange={e => setEditForm(f => ({...f, holiday_date: e.target.value}))}
                    className="slac-input slac-input--sm" />{msgB('holiday_date')}
                  <Input aria-label={t('slacalendars.nombre_del_festivo')} value={editForm.name}
                    onChange={e => setEditForm(f => ({...f, name: e.target.value}))}
                    placeholder={t('slacalendars.nombre_del_festivo')}
                    inputClassName="slac-input slac-input--sm slac-input--grow" />{msgB('name')}
                  <IconButton onClick={() => updateH(h.id)}
                    ariaLabel={t('sla_calendars_page.guardar_festivo')} title={t('sla_calendars_page.guardar_festivo')}>
                    <Check size={15} aria-hidden />
                  </IconButton>
                  <IconButton onClick={() => setEditingId(null)}
                    ariaLabel={t('sla_calendars_page.cancelar_edicion')} title={t('sla_calendars_page.cancelar_edicion')}>
                    <X size={15} aria-hidden />
                  </IconButton>
                </div>
              ) : (
                <div className="slac-row">
                  <span className="slac-row__date">{fmtDate(h.holiday_date)}</span>
                  <span className="slac-row__name">{h.name || sinNombre}</span>
                  <IconButton onClick={() => { setEditingId(h.id); setEditForm({ holiday_date: h.holiday_date, name: h.name || '' }) }}
                    ariaLabel={t('sla_calendars_page.editar_festivo', { nombre: h.name || fmtDate(h.holiday_date) })} title={t('sla_calendars_page.editar')}>
                    <Pencil size={14} aria-hidden />
                  </IconButton>
                  <IconButton onClick={() => { openConfirmGlobal({ message: t('sla_calendars_page.confirmar_eliminar_festivo'), onConfirm: () => delH(h.id), danger: true }) }}
                    className="slac-borrar"
                    ariaLabel={t('sla_calendars_page.eliminar_festivo', { nombre: h.name || fmtDate(h.holiday_date) })} title={t('sla_calendars_page.eliminar')}>
                    <Trash2 size={14} aria-hidden />
                  </IconButton>
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Verificar fecha */}
        <div className="slac-check">
          <div className="slac-check__title" id={`${idCampo}-verificar`}>{t('sla_calendars_page.verificar_fecha')}</div>
          <div className="slac-check__row">
            <DateInput className="slac-input" value={checkDate} onChange={e => setCheckDate(e.target.value)} aria-labelledby={`${idCampo}-verificar`} />
            <Button variant="secondary" onClick={checkBusinessDay} disabled={!checkDate}>{t('sla_calendars_page.verificar')}</Button>
          </div>
          {checkResult && (
            <div className={`slac-result${checkResult.is_business_day ? ' slac-result--ok' : ''}`} role="status">
              <strong className="slac-result__title">
                {checkResult.is_business_day ? <CheckCircle2 size={15} aria-hidden /> : <XCircle size={15} aria-hidden />}
                <span>
                  {fmtDate(checkResult.date)}{nombreDelDia(checkResult.date) ? ` (${nombreDelDia(checkResult.date)})` : ''} —{' '}
                  {checkResult.is_business_day ? t('sla_calendars_page.dia_laborable') : t('sla_calendars_page.no_laborable')}
                </span>
              </strong>
              {checkResult.is_weekend && <div className="u-text2-sm">{t('slacalendars.fin_de_semana')}</div>}
              {checkResult.is_holiday  && <div className="slac-result__holiday">{t('sla_calendars_page.festivo_valor', { nombre: checkResult.holiday_name || sinNombre })}</div>}
            </div>
          )}
        </div>

        <div className="u-row-end">
          <Button variant="secondary" onClick={onClose}>{t('sla_calendars_page.cerrar')}</Button>
        </div>
      </div>
    </Modal>
  )
}

export default function SLACalendarsPage() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<SlaCalendar | null>(null)
  const [holidaysCal, setHolidaysCal] = useState<SlaCalendar | null>(null)

  // #24b: la lista llega tipada y ya desenvuelta por el interceptor.
  const { data: calendars = [], isLoading } = useQuery({
    queryKey: ['sla-calendars'],
    queryFn: () => slaCalendarsApi.list().then(r => r.data ?? []),
  })

  const { mutate: deleteCal } = useMutation({
    mutationFn: (id: string | number) => slaCalendarsApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sla-calendars'] }),
    onError: (e: unknown) => toast.error(extractErr(e, t('sla_calendars_page.error_eliminar'))),
  })

  const formatDays = (days: string) => days.split(',').map((d) => DIAS_ISO.includes(+d) ? nombreCortoDelDia(+d) : d).join(', ')

  return (
    <PageShell>
      <PageHeader icon={<CalendarClock size={18} />} title={t('sla_calendars.title')} subtitle={t('sla_calendars.subtitle')}
        actions={<Button icon={<Plus size={14} />} onClick={() => { setEditing(null); setShowForm(true) }}>{t('slacalendars.nuevo_calendario')}</Button>} />

      {isLoading ? <Spinner /> : calendars.length === 0 ? (
        <EmptyState
          icon={<CalendarDays size={28} />}
          title={t('slacalendars.sin_calendarios_sla')}
          description={t('slacalendars.los_calendarios_definen_cuando_se_cuenta_el')}
          action={<Button icon={<Plus size={14} />} onClick={() => { setEditing(null); setShowForm(true) }}>{t('sla_calendars_page.crear_primero')}</Button>}
        />
      ) : (
        <div className="u-stack-12">
          {calendars.map(cal => (
            <Card key={cal.id} className="slac-tarjeta">
              <div className="slac-cal">
                <div className="u-flex1-min0">
                  <div className="slac-cal__name">{cal.name}</div>
                  <div className="slac-cal__meta">
                    <span><Globe size={13} aria-hidden />{cal.timezone}</span>
                    <span><Clock size={13} aria-hidden />{cal.work_start} — {cal.work_end}</span>
                    <span><CalendarDays size={13} aria-hidden />{formatDays(cal.work_days)}</span>
                    <span><CalendarClock size={13} aria-hidden />{t('sla_calendars_page.n_festivos', { n: cal.holiday_count })}</span>
                  </div>
                </div>
                <div className="u-row-8">
                  <Button variant="secondary" size="sm" icon={<CalendarDays size={14} />} onClick={() => setHolidaysCal(cal)}>
                    {t('sla_calendars_page.festivos')}
                  </Button>
                  <Button variant="secondary" size="sm" icon={<Pencil size={14} />} onClick={() => { setEditing(cal); setShowForm(true) }}>
                    {t('sla_calendars_page.editar')}
                  </Button>
                  <IconButton onClick={() => { openConfirmGlobal({ message: t('sla_calendars_page.confirmar_eliminar', { nombre: cal.name }), onConfirm: () => deleteCal(cal.id), danger: true }) }}
                    className="slac-borrar"
                    ariaLabel={t('sla_calendars_page.eliminar_calendario', { nombre: cal.name })} title={t('sla_calendars_page.eliminar')}>
                    <Trash2 size={15} aria-hidden />
                  </IconButton>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      {showForm && <CalendarForm cal={editing} onClose={() => { setShowForm(false); setEditing(null) }} />}
      {holidaysCal && <HolidaysModal cal={holidaysCal} onClose={() => setHolidaysCal(null)} />}
    </PageShell>
  )
}
