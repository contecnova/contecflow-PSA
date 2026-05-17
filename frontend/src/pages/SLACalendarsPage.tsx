// @ts-nocheck
import { useState } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { slaCalendarsApi } from '../services/api'
import { Button, Spinner, Modal } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { CalendarClock } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import { useOrgSettings } from '../hooks/useOrgSettings'

const ps = { background:'var(--surface-2)', border:'1px solid var(--surface-4)', borderRadius:12, padding:'20px 24px' }
const is = { width:'100%', background:'var(--surface-3)', border:'1px solid var(--surface-4)', borderRadius:8, padding: '9px 13px', color:'var(--text-1)', fontSize: "var(--text-base)", outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
const ls = { fontSize: "var(--text-xs)", fontWeight:600, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'0.07em', display:'block', marginBottom:5 }

const TIMEZONES = ['Europe/Madrid','Europe/London','America/New_York','America/Chicago',
                   'America/Los_Angeles','America/Sao_Paulo','Asia/Tokyo','Asia/Singapore',
                   'Australia/Sydney','UTC']
const DAYS_MAP  = {1:'Lunes',2:'Martes',3:'Miércoles',4:'Jueves',5:'Viernes',6:'Sábado',7:'Domingo'}

function CalendarForm({ cal, onClose }) {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const { timezone: defaultTimezone } = useOrgSettings()
  const isEdit = !!cal?.id
  const parseDays = s => new Set((s||'1,2,3,4,5').split(',').map(Number))
  const [form, setForm] = useState({
    name:      cal?.name       || '',
    timezone:  cal?.timezone   || defaultTimezone,
    work_start:cal?.work_start || '09:00',
    work_end:  cal?.work_end   || '18:00',
    work_days: parseDays(cal?.work_days),
  })
  const set = k => v => setForm(f => ({...f, [k]: v}))
  const toggleDay = d => {
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
    onSuccess: () => { qc.invalidateQueries(['sla-calendars']); onClose() },
    onError: e => toast.error(extractErr(e, 'Error al guardar')),
  })

  return (
    <Modal open onClose={onClose} title={isEdit ? 'Editar calendario SLA' : 'Nuevo calendario SLA'}>
      <div style={{display:'flex',flexDirection:'column',gap:14}}>
        <div>
          <label style={ls}>Nombre</label>
          <input style={is} value={form.name} onChange={e => set('name')(e.target.value)}
            placeholder="Ej: Horario laboral estandar" />
        </div>
        <div>
          <label style={ls}>Zona horaria</label>
          <select style={is} value={form.timezone} onChange={e => set('timezone')(e.target.value)}>
            {TIMEZONES.map(tz => <option key={tz} value={tz}>{tz}</option>)}
          </select>
        </div>
        <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:12}}>
          <div>
            <label style={ls}>Inicio jornada</label>
            <input type="time" style={is} value={form.work_start}
              onChange={e => set('work_start')(e.target.value)} />
          </div>
          <div>
            <label style={ls}>Fin jornada</label>
            <input type="time" style={is} value={form.work_end}
              onChange={e => set('work_end')(e.target.value)} />
          </div>
        </div>
        <div>
          <label style={ls}>Días laborables</label>
          <div style={{display:'flex',gap:8,flexWrap:'wrap'}}>
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

function HolidaysModal({ cal, onClose }) {
  const toast = useToast()
  const qc = useQueryClient()
  const [date, setDate] = useState('')
  const [name, setName] = useState('')
  const [checkDate, setCheckDate] = useState('')
  const [checkResult, setCheckResult] = useState(null)
  const [editingId, setEditingId] = useState(null)
  const [editForm, setEditForm] = useState({ holiday_date: '', name: '' })

  const { data: holidays = [] } = useQuery({
    queryKey: ['holidays', cal.id],
    queryFn: () => slaCalendarsApi.holidays(cal.id).then(r => r.data?.items ?? r.data ?? []).catch(() => []),
  })

  const { mutate: addH, isPending } = useMutation({
    mutationFn: () => slaCalendarsApi.createHoliday(cal.id, {holiday_date:date, name:name||null}).then(r=>r.data),
    onSuccess: () => { qc.invalidateQueries(['holidays', cal.id]); setDate(''); setName('') },
    onError: e => toast.error(extractErr(e, 'Error al añadir')),
  })
  const { mutate: updateH } = useMutation({
    mutationFn: id => slaCalendarsApi.updateHoliday(cal.id, id, { holiday_date: editForm.holiday_date, name: editForm.name || null }),
    onSuccess: () => { qc.invalidateQueries(['holidays', cal.id]); setEditingId(null) },
    onError: e => toast.error(extractErr(e, 'Error al editar')),
  })
  const { mutate: delH } = useMutation({
    mutationFn: id => slaCalendarsApi.deleteHoliday(cal.id, id),
    onSuccess: () => qc.invalidateQueries(['holidays', cal.id]),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const checkBusinessDay = async () => {
    try {
      const r = await slaCalendarsApi.checkDate(cal.id, checkDate)
      setCheckResult(r.data)
    } catch(e) {
      toast.error(e?.response?.data?.detail || 'Error al verificar')
    }
  }

  return (
    <Modal open onClose={onClose} title={`Festivos — ${cal.name}`}>
      <div style={{display:'flex',flexDirection:'column',gap:14}}>
        {/* Añadir festivo */}
        <div style={{display:'grid',gridTemplateColumns:'1fr 1fr auto',gap:8,alignItems:'flex-end'}}>
          <div>
            <label style={ls}>Fecha</label>
            <input type="date" style={is} value={date} onChange={e => setDate(e.target.value)} />
          </div>
          <div>
            <label style={ls}>Nombre (opcional)</label>
            <input style={is} value={name} onChange={e => setName(e.target.value)} placeholder="Ej: Navidad" />
          </div>
          <Button onClick={() => addH()} disabled={isPending || !date}>
            {isPending ? '...' : 'Añadir'}
          </Button>
        </div>

        {/* Lista de festivos */}
        <div style={{maxHeight:200,overflowY:'auto',border:'1px solid var(--surface-4)',borderRadius:8}}>
          {holidays.length === 0 ? (
            <div style={{padding:'16px',textAlign:'center',color:'var(--text-3)',fontSize: "var(--text-sm)"}}>Sin festivos registrados</div>
          ) : holidays.map((h,i) => (
            <div key={h.id} style={{borderBottom:'1px solid var(--surface-4)',background:i%2===0?'transparent':'rgba(255,255,255,0.02)'}}>
              {editingId === h.id ? (
                <div style={{display:'flex',alignItems:'center',gap:6,padding:'6px 10px'}}>
                  <input type="date" value={editForm.holiday_date}
                    onChange={e => setEditForm(f => ({...f, holiday_date: e.target.value}))}
                    style={{background:'var(--surface-3)',border:'1px solid var(--surface-4)',borderRadius:5,
                      padding:'3px 7px',color:'var(--text-1)',fontSize: "var(--text-sm)",fontFamily:'inherit'}} />
                  <input value={editForm.name}
                    onChange={e => setEditForm(f => ({...f, name: e.target.value}))}
                    placeholder="Nombre del festivo"
                    style={{flex:1,background:'var(--surface-3)',border:'1px solid var(--surface-4)',borderRadius:5,
                      padding:'3px 7px',color:'var(--text-1)',fontSize: "var(--text-sm)",fontFamily:'inherit'}} />
                  <button onClick={() => updateH(h.id)}
                    style={{background:'var(--accent)',border:'none',borderRadius:5,padding:'3px 10px',
                      color:'#fff',cursor:'pointer',fontSize: "var(--text-xs)",fontFamily:'inherit'}}>✓</button>
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
          <div style={{display:'flex',gap:8}}>
            <input type="date" style={is} value={checkDate} onChange={e => setCheckDate(e.target.value)} />
            <Button variant="secondary" onClick={checkBusinessDay} disabled={!checkDate}>Verificar</Button>
          </div>
          {checkResult && (
            <div style={{marginTop:10,padding:'10px 14px',borderRadius:8,border:'1px solid var(--surface-4)',
              background:checkResult.is_business_day?'var(--success-bg)':'var(--danger-bg)',fontSize: "var(--text-base)"}}>
              <strong style={{color:checkResult.is_business_day?'var(--success)':'var(--danger)'}}>
                {checkResult.date} ({checkResult.day_of_week}) —
                {checkResult.is_business_day ? ' ✅ Día laborable' : ' ❌ No laborable'}
              </strong>
              {checkResult.is_weekend && <div style={{color:'var(--text-2)',fontSize: "var(--text-sm)"}}>Fin de semana</div>}
              {checkResult.is_holiday  && <div style={{color:'var(--warning)',fontSize: "var(--text-sm)"}}>Festivo: {checkResult.holiday_name||'(sin nombre)'}</div>}
            </div>
          )}
        </div>

        <div style={{display:'flex',justifyContent:'flex-end'}}>
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
  const [editing, setEditing] = useState(null)
  const [holidaysCal, setHolidaysCal] = useState(null)

  const { data: calendars = [], isLoading } = useQuery({
    queryKey: ['sla-calendars'],
    queryFn: () => slaCalendarsApi.list().then(r => r.data?.items ?? r.data ?? []).catch(() => []),
  })

  const { mutate: deleteCal } = useMutation({
    mutationFn: id => slaCalendarsApi.delete(id),
    onSuccess: () => qc.invalidateQueries(['sla-calendars']),
    onError: e => toast.error(extractErr(e, 'Error al eliminar')),
  })

  const formatDays = days => days.split(',').map(d => DAYS_MAP[+d]?.slice(0,3)||d).join(', ')

  return (
    <PageShell>
      <PageHeader icon={<CalendarClock size={18} />} title={t('sla_calendars.title')} subtitle={t('sla_calendars.subtitle')}
        actions={<Button onClick={() => { setEditing(null); setShowForm(true) }}>+ Nuevo calendario</Button>} />

      {isLoading ? <Spinner /> : calendars.length === 0 ? (
        <div style={{...ps,textAlign:'center',padding:'48px 24px'}}>
          <div style={{fontSize: "var(--text-6xl)",marginBottom:16}}>📅</div>
          <div style={{fontSize: "var(--text-md-em)",fontWeight:600,marginBottom:8}}>Sin calendarios SLA</div>
          <div style={{fontSize: "var(--text-base)",color:'var(--text-2)',marginBottom:20}}>
            Los calendarios definen cuándo se cuenta el tiempo de SLA.
            Los festivos y fines de semana pueden excluirse del cómputo.
          </div>
          <Button onClick={() => { setEditing(null); setShowForm(true) }}>+ Crear primer calendario</Button>
        </div>
      ) : (
        <div style={{display:'flex',flexDirection:'column',gap:12}}>
          {calendars.map(cal => (
            <div key={cal.id} style={{...ps,padding:'16px 20px'}}>
              <div style={{display:'flex',alignItems:'center',gap:14}}>
                <div style={{flex:1}}>
                  <div style={{fontWeight:600,fontSize: "var(--text-md)",marginBottom:4}}>{cal.name}</div>
                  <div style={{display:'flex',gap:16,fontSize: "var(--text-sm)",color:'var(--text-2)',flexWrap:'wrap'}}>
                    <span>🌍 {cal.timezone}</span>
                    <span>⏰ {cal.work_start} — {cal.work_end}</span>
                    <span>📆 {formatDays(cal.work_days)}</span>
                    <span>🎌 {cal.holiday_count} festivos</span>
                  </div>
                </div>
                <div style={{display:'flex',gap:8}}>
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
