import { useState } from 'react'
import { useToast } from '../context/ToastContext'
import ResourceHeatmap from '../components/ResourceHeatmap'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../services/api'
import { usersApi } from '../services/api'
import { Avatar, LoadBar, Button, Modal, Input, Select, Spinner, EmptyState, useSort, SortableTH, ViewToggle } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import { Users } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { ROLE_LABELS, extractErr } from '../utils/helpers'
import { useAppT } from '../i18n/AppLangContext'

const ROLES = Object.entries(ROLE_LABELS).map(([v, l]) => ({ value: v, label: l }))

const RISK_META = {
  green:  { label: 'Saludable',   color: 'var(--success)',  bg: 'rgba(74,222,128,0.1)',  border: 'rgba(74,222,128,0.3)'  },
  yellow: { label: 'Atención',    color: 'var(--warning)',  bg: 'rgba(251,191,36,0.1)',  border: 'rgba(251,191,36,0.3)'  },
  orange: { label: 'Riesgo',      color: '#f97316',         bg: 'rgba(249,115,22,0.1)',  border: 'rgba(249,115,22,0.3)'  },
  red:    { label: 'Crítico 🔴',  color: 'var(--danger)',   bg: 'rgba(248,113,113,0.1)', border: 'rgba(248,113,113,0.35)' },
}

function BurnoutRiskCard({ member }) {
  const m = RISK_META[member.risk_level] || RISK_META.green
  return (
    <div style={{
      background: 'var(--surface-2)', border: `1px solid ${m.border}`,
      borderRadius: 14, padding: 18, display: 'flex', gap: 14, alignItems: 'flex-start',
    }}>
      <Avatar name={member.full_name} size={38} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
          <div>
            <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-1)' }}>{member.full_name}</div>
            <div style={{ fontSize: 11, color: 'var(--text-3)' }}>{member.job_title || member.department}</div>
          </div>
          <span style={{
            fontSize: 11, fontWeight: 700, padding: '3px 10px', borderRadius: 20,
            background: m.bg, color: m.color, border: `1px solid ${m.border}`, whiteSpace: 'nowrap',
          }}>{m.label}</span>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8, marginBottom: 10 }}>
          {[
            { label: 'Carga actual', value: `${member.current_load_pct?.toFixed(0)}%`, color: member.current_load_pct > 100 ? 'var(--danger)' : 'var(--text-1)' },
            { label: 'Media 4sem',   value: `${member.avg_load_4w?.toFixed(0)}%`,      color: member.avg_load_4w > 90 ? 'var(--warning)' : 'var(--text-1)' },
            { label: 'Streak (sem)', value: member.overload_weeks_streak,              color: member.overload_weeks_streak >= 3 ? 'var(--danger)' : 'var(--text-1)' },
          ].map(s => (
            <div key={s.label} style={{ background: 'var(--surface-3)', borderRadius: 8, padding: '8px 10px', textAlign: 'center' }}>
              <div style={{ fontSize: 17, fontWeight: 800, fontFamily: "'Space Mono', monospace", color: s.color }}>{s.value}</div>
              <div style={{ fontSize: 9, color: 'var(--text-3)', textTransform: 'uppercase', marginTop: 2 }}>{s.label}</div>
            </div>
          ))}
        </div>
        {/* Sparkline mini-bar */}
        {member.weekly_history?.length > 0 && (
          <div style={{ display: 'flex', gap: 3, alignItems: 'flex-end', height: 28, marginBottom: 8 }}>
            {member.weekly_history.slice(0, 8).map((w, i) => {
              const h = Math.min(100, w.load_pct)
              const c = h > 100 ? 'var(--danger)' : h > 85 ? 'var(--warning)' : 'var(--success)'
              return (
                <div key={i} title={`Sem -${i}: ${w.load_pct?.toFixed(0)}%`}
                  style={{ flex: 1, background: c, opacity: 0.7 + i * 0.04, borderRadius: 2,
                    height: `${Math.max(8, h * 0.28)}px`, transition: 'height .2s' }} />
              )
            }).reverse()}
          </div>
        )}
        {member.factors?.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
            {member.factors.map((f, i) => (
              <span key={i} style={{ fontSize: 10, padding: '2px 8px', borderRadius: 10,
                background: 'var(--surface-3)', color: 'var(--text-2)' }}>{f}</span>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function BurnoutMonitorTab() {
  const [filter, setFilter] = useState('all')
  const { data, isLoading } = useQuery({
    queryKey: ['burnout-risk', filter],
    queryFn: () => api.get('/resources/burnout-risk', {
      params: filter !== 'all' ? { min_risk_level: filter } : undefined
    }).then(r => r.data),
    staleTime: 5 * 60 * 1000,
  })
  const { mutate: recompute, isPending } = useMutation({
    mutationFn: () => api.post('/resources/burnout-risk/compute'),
    onSuccess: () => {},
  })

  const members = data?.members || []
  const summary = data?.summary || {}

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div style={{ display: 'flex', gap: 6 }}>
          {[
            { id: 'all', label: 'Todos' },
            { id: 'yellow', label: '⚠️ Atención' },
            { id: 'orange', label: '🟠 Riesgo' },
            { id: 'red', label: '🔴 Crítico' },
          ].map(f => (
            <button key={f.id} onClick={() => setFilter(f.id)}
              style={{ padding: '5px 14px', borderRadius: 20, border: '1px solid var(--surface-4)',
                background: filter === f.id ? 'var(--accent-muted)' : 'var(--surface-2)',
                color: filter === f.id ? 'var(--accent)' : 'var(--text-2)',
                fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit', transition: 'all .15s' }}>
              {f.label}
            </button>
          ))}
        </div>
        <button onClick={() => recompute()} disabled={isPending}
          style={{ padding: '6px 16px', borderRadius: 8, border: '1px solid var(--surface-4)',
            background: 'var(--surface-2)', color: 'var(--text-2)', fontSize: 12, cursor: 'pointer',
            fontFamily: 'inherit', opacity: isPending ? 0.6 : 1 }}>
          {isPending ? 'Calculando...' : '↻ Recalcular'}
        </button>
      </div>

      {/* Summary pills */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 20 }}>
        {Object.entries(RISK_META).map(([k, m]) => (
          <div key={k} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '5px 12px',
            borderRadius: 20, background: m.bg, border: `1px solid ${m.border}` }}>
            <span style={{ fontSize: 12, fontWeight: 700, color: m.color }}>{summary[k] ?? 0}</span>
            <span style={{ fontSize: 11, color: 'var(--text-3)' }}>{m.label}</span>
          </div>
        ))}
      </div>

      {isLoading ? (
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', padding: '40px 0' }}>
          <Spinner /><span style={{ color: 'var(--text-2)' }}>{t('resources.analyzing_load_patterns')}</span>
        </div>
      ) : members.length === 0 ? (
        <EmptyState icon="🎉" title={t('resources.empty_title')} description={t('resources.empty_desc')} />
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(380px, 1fr))', gap: 14 }}>
          {members.map(m => <BurnoutRiskCard key={m.user_id} member={m} />)}
        </div>
      )}
    </div>
  )
}

function ResourceCard({ resource, onEdit, showRates }) {
  const load = resource.current_load_pct ?? 0
  const loadColor = load > 100 ? 'var(--danger)' : load > 85 ? 'var(--warning)' : load > 60 ? 'var(--accent)' : 'var(--success)'
  return (
    <div style={{
      background: 'var(--surface-2)',
      border: `1px solid ${load > 100 ? 'rgba(248,113,113,0.35)' : 'var(--surface-4)'}`,
      borderRadius: 14, padding: 20,
      boxShadow: load > 100 ? '0 0 20px rgba(248,113,113,0.08)' : '0 2px 8px rgba(0,0,0,0.15)',
      transition: 'border-color .15s, box-shadow .15s',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
          <Avatar name={resource.user?.full_name || resource.full_name} size={40} />
          <div>
            <div style={{ fontWeight: 700, fontSize: 14, color: 'var(--text-1)' }}>{resource.user?.full_name || resource.full_name}</div>
            <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 2 }}>
              {resource.user?.job_title || resource.job_title}
              {(resource.user?.department || resource.department) && (
                <> · <span style={{ color: 'var(--accent)', opacity: 0.8 }}>{resource.user?.department || resource.department}</span></>
              )}
            </div>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
          {load > 100 && <span title={t(modulo.clave)} style={{ fontSize: 16 }}>⚠️</span>}
          <button onClick={() => onEdit(resource)}
            style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 7, padding: '4px 12px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 11, fontFamily: 'inherit', transition: 'all .1s' }}
            onMouseEnter={e => { e.currentTarget.style.background = 'var(--surface-4)'; e.currentTarget.style.color = 'var(--text-1)' }}
            onMouseLeave={e => { e.currentTarget.style.background = 'var(--surface-3)'; e.currentTarget.style.color = 'var(--text-2)' }}>
            Editar
          </button>
        </div>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8, marginBottom: 16 }}>
        {[
          { label: 'Carga',     value: `${load.toFixed(0)}%`,                          color: loadColor },
          { label: 'Horas/sem', value: `${resource.hours_this_week?.toFixed(1) ?? 0}h`, color: 'var(--text-1)' },
          { label: 'Proyectos', value: resource.active_projects ?? 0,                   color: 'var(--text-1)' },
        ].map(m => (
          <div key={m.label} style={{ background: 'var(--surface-3)', borderRadius: 10, padding: '10px 12px', textAlign: 'center' }}>
            <div style={{ fontSize: 20, fontWeight: 800, fontFamily: "'Space Mono', monospace", color: m.color, lineHeight: 1.1 }}>{m.value}</div>
            <div style={{ fontSize: 10, color: 'var(--text-3)', marginTop: 3, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{m.label}</div>
          </div>
        ))}
      </div>
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--text-3)', marginBottom: 6 }}>
          <span>Utilización</span>
          <span style={{ color: loadColor, fontWeight: 700 }}>{load.toFixed(0)}%</span>
        </div>
        <LoadBar value={load} />
      </div>
      {showRates && resource.user?.hourly_rate && (
        <div style={{ marginTop: 12, padding: '8px 12px', background: 'var(--surface-3)', borderRadius: 8, fontSize: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ color: 'var(--text-3)' }}>Tarifa</span>
          <span style={{ fontFamily: "'Space Mono', monospace", color: 'var(--success)', fontWeight: 700 }}>{resource.user.hourly_rate}€/h</span>
        </div>
      )}
    </div>
  )
}

function EditUserModal({ user, open, onClose }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [form, setForm] = useState({
    full_name:             user?.user?.full_name             || user?.full_name             || '',
    job_title:             user?.user?.job_title             || user?.job_title             || '',
    department:            user?.user?.department            || user?.department            || '',
    role:                  user?.user?.role                  || user?.role                  || 'employee',
    weekly_capacity_hours: user?.user?.weekly_capacity_hours || 40,
    hourly_rate:           user?.user?.hourly_rate           || '',
  })
  const { hasRole } = useAuth()
  const userId = user?.user?.id || user?.id
  const { mutate, isPending } = useMutation({
    mutationFn: (data) => usersApi.update(userId, data),
    onSuccess: () => { qc.invalidateQueries(['resources']); qc.invalidateQueries(['users']); qc.invalidateQueries(['capacity-board']); qc.invalidateQueries(['forecast-heatmap']); qc.invalidateQueries(['forecast-summary']); onClose() },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.value }))
  return (
    <Modal open={open} onClose={onClose} title={t(modulo.clave)}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <Input label={t(modulo.clave)} value={form.full_name} onChange={set('full_name')} />
        <Input label={t(modulo.clave)} value={form.job_title} onChange={set('job_title')} />
        <Input label={t(modulo.clave)} value={form.department} onChange={set('department')} />
        <Select label={t(modulo.clave)} value={form.role} onChange={set('role')} options={ROLES} />
        <Input label={t(modulo.clave)} type="number" value={form.weekly_capacity_hours} onChange={set('weekly_capacity_hours')} />
        {hasRole('admin') && <Input label={t(modulo.clave)} type="number" value={form.hourly_rate} onChange={set('hourly_rate')} />}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 8 }}>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={() => mutate(form)} disabled={isPending} loading={isPending}>{isPending ? 'Guardando...' : 'Guardar cambios'}</Button>
        </div>
      </div>
    </Modal>
  )
}

function SmartMatchTab() {
  const toast = useToast()
  const [form, setForm] = useState({ skills: [], role: '', hours_needed: 40, start_date: '', end_date: '', max_hourly_rate: '' })
  const [skillInput, setSkillInput] = useState('')
  const [results, setResults] = useState(null)

  const { data: skillsRaw = [] } = useQuery({
    queryKey: ['skills-sm'],
    queryFn: () => api.get('/skills/catalog').then(r => r.data),
  })
  const allSkills = Array.isArray(skillsRaw) ? skillsRaw : []

  const { mutate: search, isPending } = useMutation({
    mutationFn: d => api.post('/smartmatch', d).then(r => r.data),
    onSuccess: data => setResults(data),
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const addSkill = (skill) => {
    const name = typeof skill === 'string' ? skill : skill.name
    if (name && !form.skills.includes(name)) setForm(f => ({ ...f, skills: [...f.skills, name] }))
    setSkillInput('')
  }
  const removeSkill = (s) => setForm(f => ({ ...f, skills: f.skills.filter(x => x !== s) }))
  const scoreColor  = (n) => n >= 75 ? 'var(--success)' : n >= 50 ? 'var(--warning)' : n >= 25 ? 'var(--warning)' : 'var(--danger)'

  const inputStyle = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 12px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
  const labelStyle = { fontSize: 11, fontWeight: 600, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }
  const panelStyle = { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 14 }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '340px 1fr', gap: 24 }}>
      <div>
        <div style={{ ...panelStyle, padding: '20px 24px' }}>
          <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 4 }}>🧠 SmartMatch</div>
          <div style={{ fontSize: 12, color: 'var(--text-2)', marginBottom: 20 }}>Encuentra los mejores recursos para tu proyecto</div>

          <div style={{ marginBottom: 14 }}>
            <label style={labelStyle}>Skills requeridos</label>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 8 }}>
              {form.skills.map(s => (
                <span key={s} style={{ background: 'var(--accent-muted)', border: '1px solid rgba(79,142,247,0.25)', borderRadius: 20, padding: '3px 10px', fontSize: 12, color: 'var(--accent)', display: 'flex', alignItems: 'center', gap: 6 }}>
                  {s}
                  <button onClick={() => removeSkill(s)} style={{ background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer', padding: 0, fontSize: 14, lineHeight: 1 }}>×</button>
                </span>
              ))}
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <select value={skillInput} onChange={e => setSkillInput(e.target.value)} style={{ ...inputStyle, flex: 1 }}>
                <option value="">Seleccionar skill...</option>
                {allSkills.filter(s => !form.skills.includes(s.name)).map(s => <option key={s.id || s.name} value={s.name}>{s.name}</option>)}
              </select>
              <Button onClick={() => { if (skillInput) addSkill(skillInput) }}>+</Button>
            </div>
            <div style={{ marginTop: 8, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {['React', 'Python', 'AWS', 'DevOps', 'Scrum', 'SQL', 'Java', 'Angular'].filter(s => !form.skills.includes(s)).map(s => (
                <button key={s} onClick={() => addSkill(s)} style={{ background: 'var(--surface-4)', border: 'none', borderRadius: 4, padding: '2px 8px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 11, fontFamily: 'inherit' }}>+{s}</button>
              ))}
            </div>
          </div>

          <div style={{ marginBottom: 14 }}>
            <label style={labelStyle}>Rol</label>
            <select value={form.role} onChange={e => setForm(f => ({ ...f, role: e.target.value }))} style={inputStyle}>
              <option value="">Cualquier rol</option>
              <option value="employee">Empleado / Consultor</option>
              <option value="pm">Project Manager</option>
              <option value="team_lead">Team Lead</option>
            </select>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 14 }}>
            <div><label style={labelStyle}>Horas necesarias</label><input type="number" value={form.hours_needed} onChange={e => setForm(f => ({ ...f, hours_needed: +e.target.value }))} style={inputStyle} /></div>
            <div><label style={labelStyle}>Tarifa máx. (€/h)</label><input type="number" value={form.max_hourly_rate} onChange={e => setForm(f => ({ ...f, max_hourly_rate: e.target.value }))} style={inputStyle} placeholder={t(modulo.clave)} /></div>
            <div><label style={labelStyle}>Inicio</label><input type="date" value={form.start_date} onChange={e => setForm(f => ({ ...f, start_date: e.target.value }))} style={inputStyle} /></div>
            <div><label style={labelStyle}>Fin</label><input type="date" value={form.end_date} onChange={e => setForm(f => ({ ...f, end_date: e.target.value }))} style={inputStyle} /></div>
          </div>

          <Button onClick={() => search({ ...form, max_hourly_rate: form.max_hourly_rate ? +form.max_hourly_rate : undefined })} loading={isPending} disabled={isPending} style={{ width: '100%' }}>
            {isPending ? '⟳ Buscando...' : '🔍 Buscar recursos'}
          </Button>
        </div>
      </div>

      <div>
        {!results && !isPending && (
          <div style={{ ...panelStyle, padding: '48px', textAlign: 'center' }}>
            <div style={{ fontSize: 48, marginBottom: 16 }}>🎯</div>
            <div style={{ fontSize: 14, color: 'var(--text-2)' }}>Configura los criterios y pulsa &quot;Buscar recursos&quot;</div>
          </div>
        )}
        {isPending && <Spinner />}
        {results && (
          <div>
            <div style={{ fontSize: 13, color: 'var(--text-2)', marginBottom: 16 }}>{results.message}</div>
            {(results.candidates || []).map((c, i) => (
              <div key={c.user_id} style={{ ...panelStyle, padding: '18px 22px', marginBottom: 12, border: `1px solid ${scoreColor(c.scores.overall)}30` }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
                  <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
                    <div style={{ width: 40, height: 40, borderRadius: 12, background: `linear-gradient(135deg,${scoreColor(c.scores.overall)}40,${scoreColor(c.scores.overall)}20)`, border: `1px solid ${scoreColor(c.scores.overall)}40`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 16, fontWeight: 800, color: scoreColor(c.scores.overall) }}>{i + 1}</div>
                    <div>
                      <div style={{ fontSize: 15, fontWeight: 700 }}>{c.user_name}</div>
                      <div style={{ fontSize: 12, color: 'var(--text-2)' }}>{c.job_title || c.role} · {c.department || '—'}</div>
                    </div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: 22, fontWeight: 800, color: scoreColor(c.scores.overall) }}>{c.scores.overall}%</div>
                    <div style={{ fontSize: 12, color: scoreColor(c.scores.overall) }}>{c.recommendation}</div>
                  </div>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 10, marginBottom: 12 }}>
                  {[['Skills', c.scores.skills + '%', 'var(--purple)'], ['Disponibilidad', c.scores.availability + '%', 'var(--accent)'], ['Carga', c.scores.workload + '%', 'var(--success)'], ['Coste', c.scores.cost + '%', 'var(--warning)']].map(([l, v, col]) => (
                    <div key={l} style={{ background: 'var(--surface-3)', borderRadius: 8, padding: '8px 12px', textAlign: 'center' }}>
                      <div style={{ fontSize: 16, fontWeight: 800, color: col }}>{v}</div>
                      <div style={{ fontSize: 10, color: 'var(--text-3)', marginTop: 2 }}>{l}</div>
                    </div>
                  ))}
                </div>
                <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap', fontSize: 12, color: 'var(--text-2)' }}>
                  {c.hourly_rate > 0 && <span>💰 {c.hourly_rate}€/h</span>}
                  <span>⏱ {c.availability_hours}h disponibles</span>
                  <span>📋 {c.active_tasks} tareas activas</span>
                  {c.matched_skills?.length > 0 && <span>✓ {c.matched_skills.join(', ')}</span>}
                  {c.missing_skills?.length > 0 && <span style={{ color: 'var(--danger)' }}>✗ Faltan: {c.missing_skills.join(', ')}</span>}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export default function ResourcesPage() {
  const t = useAppT()
  const [resTab, setResTab] = useState('team')
  const { hasRole } = useAuth()
  const [deptFilter, setDeptFilter] = useState('')
  const [search, setSearch] = useState('')
  const [resSortBy] = useState('user.full_name')
  const [editTarget, setEditTarget] = useState(null)
  const [view, setView] = useState('grid')

  const { data: loadData = [], isLoading } = useQuery({
    queryKey: ['resources'],
    queryFn: () => usersApi.load().then(r => r.data),
  })

  const filtered = loadData.filter(r => {
    const name = r.user?.full_name || ''
    const dept = r.user?.department || ''
    return (!search || name.toLowerCase().includes(search.toLowerCase())) && (!deptFilter || dept === deptFilter)
  })
  const { sort: resSort, setSort: setResSort, sortedData: sortedResources } = useSort(filtered, resSortBy)

  const departments = [...new Set(loadData.map(r => r.user?.department).filter(Boolean))]
  const overloaded  = loadData.filter(r => r.current_load_pct > 100).length
  const available   = loadData.filter(r => r.current_load_pct < 60).length
  const avgLoad     = loadData.length ? (loadData.reduce((s, r) => s + r.current_load_pct, 0) / loadData.length).toFixed(0) : 0

  const TABS = [
    { id: 'team',       label: '👥 Equipo' },
    { id: 'heatmap',    label: '📊 Heatmap' },
    { id: 'smartmatch', label: '🧠 SmartMatch' },
    { id: 'burnout',    label: '🔥 Burnout Monitor' },
  ]

  return (
    <div style={{ padding: '28px 32px' }}>
      <PageHeader icon={<Users size={18} />} title={t('resources.title')} subtitle={t('resources.subtitle')} />

      {/* KPI bar */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 24 }}>
        {[
          { label: 'Total personas',     value: loadData.length,  color: 'var(--accent)' },
          { label: 'Disponibles (<60%)', value: available,        color: 'var(--success)' },
          { label: 'Sobrecargados',      value: overloaded,       color: overloaded > 0 ? 'var(--danger)' : 'var(--success)' },
          { label: 'Carga media equipo', value: `${avgLoad}%`,    color: Number(avgLoad) > 85 ? 'var(--warning)' : 'var(--accent)' },
        ].map(k => (
          <div key={k.label} style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, padding: '14px 18px' }}>
            <div style={{ fontSize: 24, fontWeight: 800, fontFamily: "'Space Mono', monospace", color: k.color, lineHeight: 1.1 }}>{k.value}</div>
            <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 4 }}>{k.label}</div>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 24, background: 'var(--surface-1)', borderRadius: 10, padding: 4, width: 'fit-content' }}>
        {TABS.map(({ id, label }) => (
          <button key={id} onClick={() => setResTab(id)}
            style={{ padding: '7px 18px', borderRadius: 7, border: 'none',
              background: resTab === id ? 'var(--accent-muted)' : 'transparent',
              color: resTab === id ? 'var(--accent)' : 'var(--text-2)',
              fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
              outline: resTab === id ? '1px solid rgba(79,142,247,0.3)' : 'none',
              transition: 'all .15s' }}>
            {label}
          </button>
        ))}
      </div>

      {resTab === 'heatmap' ? <ResourceHeatmap /> : resTab === 'smartmatch' ? <SmartMatchTab /> : resTab === 'burnout' ? <BurnoutMonitorTab /> : (
        <>
          <div style={{ display: 'flex', gap: 12, marginBottom: 20 }}>
            <input value={search} onChange={e => setSearch(e.target.value)} placeholder={t(modulo.clave)}
              style={{ flex: 1, background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 14px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit' }} />
            <select value={deptFilter} onChange={e => setDeptFilter(e.target.value)}
              style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 14px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', cursor: 'pointer' }}>
              <option value="">Todos los departamentos</option>
              {departments.map(d => <option key={d} value={d}>{d}</option>)}
            </select>
            <select value={resSort.key} onChange={e => setResSort({ key: e.target.value, dir: 'asc' })}
              style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 14px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', cursor: 'pointer' }}>
              <option value="user.full_name">Nombre A-Z</option>
              <option value="current_load_pct">Carga %</option>
              <option value="user.department">Departamento</option>
              <option value="user.role">Rol</option>
            </select>
            <ViewToggle view={view} onChange={setView} />
          </div>
          {isLoading ? (
            <div style={{ display: 'flex', gap: 12, alignItems: 'center', padding: '40px 0' }}><Spinner /><span style={{ color: 'var(--text-2)' }}>Cargando recursos...</span></div>
          ) : filtered.length === 0 ? (
            <EmptyState icon="👥" title={t(modulo.clave)} description={t(modulo.clave)} />
          ) : view === 'grid' ? (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 16 }}>
              {sortedResources.map(r => <ResourceCard key={r.user?.id} resource={r} onEdit={setEditTarget} showRates={hasRole('admin', 'hr')} />)}
            </div>
          ) : (
            <div style={{ background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 12, overflow: 'hidden' }}>
              <div style={{ display: 'grid', gridTemplateColumns: hasRole('admin', 'hr') ? '2fr 1fr 1fr 1fr 1fr 1fr 80px' : '2fr 1fr 1fr 1fr 1fr 80px', gap: 12, padding: '10px 20px', borderBottom: '1px solid #1e2d45', fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', alignItems: 'center' }}>
                <SortableTH col="user.full_name" sort={resSort} onSort={setResSort}>Recurso</SortableTH>
                <SortableTH col="user.department" sort={resSort} onSort={setResSort}>Departamento</SortableTH>
                <SortableTH col="user.role" sort={resSort} onSort={setResSort}>Rol</SortableTH>
                <SortableTH col="current_load_pct" sort={resSort} onSort={setResSort}>Carga %</SortableTH>
                <SortableTH col="hours_this_week" sort={resSort} onSort={setResSort}>Horas/sem</SortableTH>
                <SortableTH col="active_projects" sort={resSort} onSort={setResSort}>Proyectos</SortableTH>
                {hasRole('admin', 'hr') && <SortableTH col="user.hourly_rate" sort={resSort} onSort={setResSort}>Tarifa/h</SortableTH>}
              </div>
              {sortedResources.map(r => (
                <div key={r.user?.id} style={{ display: 'grid', gridTemplateColumns: hasRole('admin', 'hr') ? '2fr 1fr 1fr 1fr 1fr 1fr 80px' : '2fr 1fr 1fr 1fr 1fr 80px', gap: 12, padding: '11px 20px', borderBottom: '1px solid #1e2d4530', alignItems: 'center', cursor: 'pointer' }}
                  onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-3)'}
                  onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <div style={{ width: 30, height: 30, borderRadius: 8, background: 'var(--accent-muted)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, fontWeight: 700, color: 'var(--accent)', flexShrink: 0 }}>
                      {r.user?.full_name?.charAt(0) || '?'}
                    </div>
                    <div>
                      <div style={{ fontSize: 13, fontWeight: 600 }}>{r.user?.full_name}</div>
                      <div style={{ fontSize: 11, color: 'var(--text-2)' }}>{r.user?.job_title}</div>
                    </div>
                  </div>
                  <span style={{ fontSize: 12, color: 'var(--text-2)' }}>{r.user?.department || '—'}</span>
                  <span style={{ fontSize: 12, color: 'var(--text-2)' }}>{r.user?.role || '—'}</span>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <div style={{ flex: 1, height: 6, background: 'var(--surface-4)', borderRadius: 3, overflow: 'hidden' }}>
                      <div style={{ height: '100%', width: `${Math.min(r.current_load_pct, 100)}%`, background: r.current_load_pct > 100 ? 'var(--danger)' : r.current_load_pct > 80 ? 'var(--warning)' : 'var(--success)', borderRadius: 3 }} />
                    </div>
                    <span style={{ fontSize: 11, fontFamily: "'Space Mono', monospace", color: r.current_load_pct > 100 ? 'var(--danger)' : 'var(--text-1)', minWidth: 34 }}>{r.current_load_pct}%</span>
                  </div>
                  <span style={{ fontSize: 12, fontFamily: "'Space Mono', monospace" }}>{r.hours_this_week || 0}h</span>
                  <span style={{ fontSize: 12 }}>{r.active_projects || 0}</span>
                  {hasRole('admin', 'hr') && <span style={{ fontSize: 12, fontFamily: "'Space Mono', monospace" }}>{r.user?.hourly_rate ? `${r.user.hourly_rate}€` : '—'}</span>}
                </div>
              ))}
            </div>
          )}
          {editTarget && <EditUserModal user={editTarget} open={!!editTarget} onClose={() => setEditTarget(null)} />}
        </>
      )}
    </div>
  )
}
