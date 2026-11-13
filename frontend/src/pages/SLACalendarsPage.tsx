import { useState, useId } from 'react'
import type { CSSProperties } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { slaCalendarsApi, type SlaCalendar } from '../services/api'
import { Button, Spinner, Modal } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { CalendarClock } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import { useOrgSettings } from '../hooks/useOrgSettings'
import { timezoneOptions } from '../constants/timezones'
import DateInput from '../components/ui/DateInput'

interface HolidayItem {
  id: string | number
  holiday_date: string
  name?: string | null
}

interface CheckDateResult {
  date: string
  day_of_week: string
  is_business_day: boolean
  is_weekend?: boolean
  is_holiday?: boolean
  holiday_name?: string | null
}

const ps: CSSProperties = { background:'var(--surface-2)', border:'1px solid var(--surface-4)', borderRadius:12, padding:'20px 24px' }
const is: CSSProperties = { width:'100%', background:'var(--surface-3)', border:'1px solid var(--surface-4)', borderRadius:8, padding: '9px 13px', color:'var(--text-1)', fontSize: "var(--text-base)", outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
const ls: CSSProperties = { fontSize: "var(--text-xs)", fontWeight:600, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'0.07em', display:'block', marginBottom:5 }

const DAYS_MAP  = {1:'Lunes',2:'Martes',3:'Miércoles',4:'Jueves',5:'Viernes',6:'Sábado',7:'Domingo'}

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
  const set = (k: 'name' | 'timezone' | 'work_start' | 'work_end' | 'work_days') => (v: string | Set<number>) => setForm((f) => ({ ...f, [k]: v }))
  const toggleDay = (d: number) => {
    const s = new Set(form.work_days)
    if (s.has(d)) { if(s.size>1) s.delete(d) } else s.add(d)
    set('work_days')(s)
  }

  const { mutate, isPending } = useMutation({
    mutationFn: () => {
      const d = {...form, work_days: [...form.work_days].sort().join(',')}
      return isEdit
        ? slaCalendarsApi.update(cal.id, d).then(r=>r.data)
        : slaCalendarsApi.create(d).then(r=>r.data)
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['sla-calendars'] }); onClose() },
    onError: (e: unknown) => toast.error(extractErr(e, 'Error al guardar')),
  })

  return (
    <Modal open onClose={onClose} title={isEdit ? 'Editar calendario SLA' : 'Nuevo calendario SLA'}>
      <div className="u-stack-14">
        <div>
          <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={ls}>Nombre</label>
          <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} style={is} value={form.name} onChange={e => set('name')(e.target.value)}
            placeholder="Ej: Horario laboral estandar" />
        </div>
        <div>
          <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} style={ls}>Zona horaria</label>
          <select id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} style={is} value={form.timezone} onChange={e => set('timezone')(e.target.value)}>
            {timezoneOptions(form.timezone).map(tz => <option key={tz} value={tz}>{tz}</option>)}
          </select>
        </div>
        <div className="u-grid2-12">
          <div>
            <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} style={ls}>Inicio jornada</label>
            <input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} type="time" style={is} value={form.work_start}
              onChange={e => set('work_start')(e.target.value)} />
          </div>
          <div>
            <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} style={ls}>Fin jornada</label>
            <input id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} type="time" style={is} value={form.work_end}
              onChange={e => set('work_end')(e.target.value)} />
          </div>
        </div>
        <div>
          <label style={ls}>{t('slacalendars.dias_laborables')}</label>
          <div className="u-wrap-8">
            {Object.entries(DAYS_MAP).map(([d,name]) => {
              const active = form.work_days.has(+d)
              return (
                <button key={d} onClick={() => toggleDay(+d)}
                  style={{padding:'6px 12px',borderRadius:8,cursor:'pointer',fontFamily:'inherit',fontSize: "var(--text-sm)",
                    border:`1px solid ${active?'var(--accent-glow)':'var(--surface-4)'}`,
                    background:active?'var(--accent-muted)':'transparent',
                    color:active?'var(--accent)':'var(--text-2)'}}>
                  {name.slice(0,3)}
                </button>
              )
            })}
          </div>
        </div>
        <div style={{display:'flex',justifyContent:'flex-end',gap:10,marginTop:8}}>
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={() => mutate()} disabled={isPending || !form.name.trim()} loading={isPending}>
            {isPending ? t('common.saving') : isEdit ? t('common.save') : 'Crear calendario'}
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
  const [checkResult, setCheckResult] = useState<CheckDateResult | null>(null)
  const [editingId, setEditingId] = useState<string | number | null>(null)
  const [editForm, setEditForm] = useState({ holiday_date: '', name: '' })

  const { data: holidaysRaw = [] } = useQuery({
    queryKey: ['holidays', cal.id],
    queryFn: () => slaCalendarsApi.holidays(cal.id).then(r => r.data?.items ?? r.data ?? []).catch(() => []),
  })
  const holidays = holidaysRaw as HolidayItem[]

  const { mutate: addH, isPending } = useMutation({
    mutationFn: () => slaCalendarsApi.createHoliday(cal.id, {holiday_date:date, name:name||null}).then(r=>r.data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['holidays', cal.id] }); setDate(''); setName('') },
    onError: (e: unknown) => toast.error(extractErr(e, 'Error al añadir')),
  })
  const { mutate: updateH } = useMutation({
    mutationFn: (id: string | number) => slaCalendarsApi.updateHoliday(cal.id, id, { holiday_date: editForm.holiday_date, name: editForm.name || null }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['holidays', cal.id] }); setEditingId(null) },
    onError: (e: unknown) => toast.error(extractErr(e, 'Error al editar')),
  })
  const { mutate: delH } = useMutation({
    mutationFn: (id: string | number) => slaCalendarsApi.deleteHoliday(cal.id, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['holidays', cal.id] }),
    onError: (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const checkBusinessDay = async () => {
    try {
      const r = await slaCalendarsApi.checkDate(cal.id, checkDate)
      setCheckResult(r.data as CheckDateResult)
    } catch(e: unknown) {
      const message = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Error al verificar'
      toast.error(message)
    }
  }

  return (
    <Modal open onClose={onClose} title={`Festivos — ${cal.name}`}>
      <div className="u-stack-14">
        {/* Añadir festivo */}
        <div style={{display:'grid',gridTemplateColumns:'1fr 1fr auto',gap:8,alignItems:'flex-end'}}>
          <div>
            <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={ls}>Fecha</label>
            <DateInput id={`${idCampo}-1`} style={is} value={date} onChange={e => setDate(e.target.value)} />
          </div>
          <div>
            <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} style={ls}>Nombre (opcional)</label>
            <input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} style={is} value={name} onChange={e => setName(e.target.value)} placeholder="Ej: Navidad" />
          </div>
          <Button onClick={() => addH()} disabled={isPending || !date}>
            {isPending ? '...' : 'Añadir'}
          </Button>
        </div>

        {/* Lista de festivos */}
        <div style={{maxHeight:200,overflowY:'auto',border:'1px solid var(--surface-4)',borderRadius:8}}>
          {holidays.length === 0 ? (
            <div style={{padding:'16px',textAlign:'center',color:'var(--text-3)',fontSize: "var(--text-sm)"}}>{t('slacalendars.sin_festivos_registrados')}</div>
          ) : holidays.map((h,i) => (
            <div key={h.id} style={{borderBottom:'1px solid var(--surface-4)',background:i%2===0?'transparent':'rgba(255,255,255,0.02)'}}>
              {editingId === h.id ? (
                <div style={{display:'flex',alignItems:'center',gap:6,padding:'6px 10px'}}>
                  <DateInput value={editForm.holiday_date}
                    onChange={e => setEditForm(f => ({...f, holiday_date: e.target.value}))}
                    style={{background:'var(--surface-3)',border:'1px solid var(--surface-4)',borderRadius:5,
                      padding:'3px 7px',color:'var(--text-1)',fontSize: "var(--text-sm)",fontFamily:'inherit'}} />
                  <input aria-label={t('slacalendars.nombre_del_festivo')} value={editForm.name}
                    onChange={e => setEditForm(f => ({...f, name: e.target.value}))}
                    placeholder={t('slacalendars.nombre_del_festivo')}
                    style={{flex:1,background:'var(--surface-3)',border:'1px solid var(--surface-4)',borderRadius:5,
                      padding:'3px 7px',color:'var(--text-1)',fontSize: "var(--text-sm)",fontFamily:'inherit'}} />
                  <button onClick={() => updateH(h.id)}
                    style={{background:'var(--accent)',border:'none',borderRadius:5,padding:'3px 10px',
                      color:'var(--on-accent-light)',cursor:'pointer',fontSize: "var(--text-xs)",fontFamily:'inherit'}}>✓</button>
                  <button onClick={() => setEditingId(null)}
                    style={{background:'none',border:'1px solid var(--surface-4)',borderRadius:5,padding:'3px 8px',
                      color:'var(--text-2)',cursor:'pointer',fontSize: "var(--text-xs)"}}>✕</button>
                </div>
              ) : (
                <div style={{display:'flex',alignItems:'center',gap:10,padding:'8px 12px',fontSize: "var(--text-sm)"}}>
                  <span style={{fontFamily:'var(--font-mono)',color:'var(--accent)',flexShrink:0}}>{h.holiday_date}</span>
                  <span style={{flex:1,color:'var(--text-1)'}}>{h.name || '(sin nombre)'}</span>
                  <button onClick={() => { setEditingId(h.id); setEditForm({ holiday_date: h.holiday_date, name: h.name || '' }) }}
                    style={{background:'none',border:'none',color:'var(--text-3)',cursor:'pointer',fontSize: "var(--text-xs)"}}>✏</button>
                  <button onClick={() => { openConfirmGlobal({ message: '¿Eliminar este festivo?', onConfirm: () => delH(h.id), danger: true }) }}
                    style={{background:'none',border:'none',color:'var(--danger)',cursor:'pointer',fontSize: "var(--text-sm)"}}>✕</button>
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Verificar fecha */}
        <div style={{borderTop:'1px solid var(--surface-4)',paddingTop:14}}>
          <div style={{fontSize: "var(--text-sm)",fontWeight:600,color:'var(--text-2)',marginBottom:10}}>VERIFICAR FECHA</div>
          <div className="u-row-8">
            <DateInput style={is} value={checkDate} onChange={e => setCheckDate(e.target.value)} />
            <Button variant="secondary" onClick={checkBusinessDay} disabled={!checkDate}>Verificar</Button>
          </div>
          {checkResult && (
            <div style={{marginTop:10,padding:'10px 14px',borderRadius:8,border:'1px solid var(--surface-4)',
              background:checkResult.is_business_day?'var(--success-bg)':'var(--danger-bg)',fontSize: "var(--text-base)"}}>
              <strong style={{color:checkResult.is_business_day?'var(--success)':'var(--danger)'}}>
                {checkResult.date} ({checkResult.day_of_week}) —
                {checkResult.is_business_day ? ' ✅ Día laborable' : ' ❌ No laborable'}
              </strong>
              {checkResult.is_weekend && <div className="u-text2-sm">{t('slacalendars.fin_de_semana')}</div>}
              {checkResult.is_holiday  && <div style={{color:'var(--warning)',fontSize: "var(--text-sm)"}}>Festivo: {checkResult.holiday_name||'(sin nombre)'}</div>}
            </div>
          )}
        </div>

        <div className="u-row-end">
          <Button variant="secondary" onClick={onClose}>Cerrar</Button>
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
    queryFn: () => slaCalendarsApi.list().then(r => r.data ?? []).catch((): SlaCalendar[] => []),
  })

  const { mutate: deleteCal } = useMutation({
    mutationFn: (id: string | number) => slaCalendarsApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sla-calendars'] }),
    onError: (e: unknown) => toast.error(extractErr(e, 'Error al eliminar')),
  })

  const formatDays = (days: string) => days.split(',').map((d) => DAYS_MAP[+d as keyof typeof DAYS_MAP]?.slice(0,3)||d).join(', ')

  return (
    <PageShell>
      <PageHeader icon={<CalendarClock size={18} />} title={t('sla_calendars.title')} subtitle={t('sla_calendars.subtitle')}
        actions={<Button onClick={() => { setEditing(null); setShowForm(true) }}>{t('slacalendars.nuevo_calendario')}</Button>} />

      {isLoading ? <Spinner /> : calendars.length === 0 ? (
        <div style={{...ps,textAlign:'center',padding:'48px 24px'}}>
          <div className="u-empty-icon">📅</div>
          <div style={{fontSize: "var(--text-md-em)",fontWeight:600,marginBottom:8}}>{t('slacalendars.sin_calendarios_sla')}</div>
          <div className="u-text2-base-mb20">
            {t('slacalendars.los_calendarios_definen_cuando_se_cuenta_el')}
          </div>
          <Button onClick={() => { setEditing(null); setShowForm(true) }}>+ Crear primer calendario</Button>
        </div>
      ) : (
        <div className="u-stack-12">
          {calendars.map(cal => (
            <div key={cal.id} style={{...ps,padding:'16px 20px'}}>
              <div style={{display:'flex',alignItems:'center',gap:14}}>
                <div className="u-flex1">
                  <div style={{fontWeight:600,fontSize: "var(--text-md)",marginBottom:4}}>{cal.name}</div>
                  <div style={{display:'flex',gap:16,fontSize: "var(--text-sm)",color:'var(--text-2)',flexWrap:'wrap'}}>
                    <span>🌍 {cal.timezone}</span>
                    <span>⏰ {cal.work_start} — {cal.work_end}</span>
                    <span>📆 {formatDays(cal.work_days)}</span>
                    <span>🎌 {cal.holiday_count} festivos</span>
                  </div>
                </div>
                <div className="u-row-8">
                  <button onClick={() => setHolidaysCal(cal)}
                    style={{padding:'5px 12px',borderRadius:8,border:'1px solid var(--surface-4)',background:'transparent',
                      color:'var(--text-2)',cursor:'pointer',fontFamily:'inherit',fontSize: "var(--text-sm)"}}>
                    🎌 Festivos
                  </button>
                  <button onClick={() => { setEditing(cal); setShowForm(true) }}
                    style={{padding:'5px 12px',borderRadius:8,border:'1px solid var(--surface-4)',background:'transparent',
                      color:'var(--text-2)',cursor:'pointer',fontFamily:'inherit',fontSize: "var(--text-sm)"}}>
                    ✏ Editar
                  </button>
                  <button onClick={() => { openConfirmGlobal({ message: `¿Eliminar "${cal.name}"?`, onConfirm: () => deleteCal(cal.id), danger: true }) }}
                    style={{padding:'5px 8px',borderRadius:8,border:'1px solid var(--danger-border)',background:'transparent',
                      color:'var(--danger)',cursor:'pointer',fontSize: "var(--text-sm)"}}>
                    🗑
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {showForm && <CalendarForm cal={editing} onClose={() => { setShowForm(false); setEditing(null) }} />}
      {holidaysCal && <HolidaysModal cal={holidaysCal} onClose={() => setHolidaysCal(null)} />}
    </PageShell>
  )
}
