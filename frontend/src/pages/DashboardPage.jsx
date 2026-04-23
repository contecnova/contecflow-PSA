import React, { useLayoutEffect, useState, useRef } from 'react'
/**
 * DashboardPage v24 — Drag & Resize widgets + extended metrics catalog
 */

import { useQuery } from '@tanstack/react-query'
import GridLayout from 'react-grid-layout'
import 'react-grid-layout/css/styles.css'
import 'react-resizable/css/styles.css'
import api, { dashboardApi, alertsApi } from '../services/api'
import { Spinner } from '../components/ui'
import _PageHeader from '../components/layout/PageHeader'
import { SkeletonDashboard } from '../components/ui/Skeletons'
import { fmtCurrency, fmtHours } from '../utils/helpers'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
         PieChart, Pie, Cell, CartesianGrid, AreaChart, Area } from 'recharts'
import { useNavigate } from 'react-router-dom'
import useCountUp from '../hooks/useCountUp'
import { useAppT, useAppLang } from '../i18n/AppLangContext'

const COLORS = ['var(--accent)','var(--success)','var(--warning)','var(--purple)','var(--danger)','var(--warning)']
// panel: no border/radius — the grid-item wrapper supplies those
const panel = { background: 'var(--surface-2)', height: '100%', boxSizing: 'border-box' }
const LANG_LOCALE = { es: 'es-ES', en: 'en-GB', fr: 'fr-FR', de: 'de-DE', pt: 'pt-PT', it: 'it-IT', pl: 'pl-PL', zh: 'zh-CN' }

// ── Animated KPI number ───────────────────────────────────────────────────────
function AnimatedKpi({ value, color }) {
  const animated = useCountUp(value, 700, value !== 0 && value !== '0%' && value !== '0h')
  return (
    <div className="kpi-number" style={{
      fontSize: 22, fontWeight: 800, color,
      fontFamily: 'var(--font-mono)', marginBottom: 2,
    }}>
      {animated}
    </div>
  )
}

// ── KPI Cards Row ─────────────────────────────────────────────────────────────
function KpiRow({ kpis }) {
  const nav = useNavigate()
  const t = useAppT()
  const { data: sdData } = useQuery({
    queryKey: ['dash-sd-kpi'],
    queryFn: () => api.get('/sd/tickets', { params: { page_size: 1 } }).then(r => { const d = r.data; return d?.total ?? (Array.isArray(d) ? d.length : 0); }),
  })
  const { data: clients = [] } = useQuery({
    queryKey: ['dash-clients-count'],
    queryFn: () => api.get('/clients').then(r => { const d = r.data; return Array.isArray(d) ? d : (Array.isArray(d?.items) ? d.items : []); }),
  })
  const activeClients = clients.filter(c => c.status === 'active').length

  const budgetPct = kpis?.total_budget > 0 ? Math.round(kpis.total_spent / kpis.total_budget * 100) : 0

  const cards = [
    { icon: <svg viewBox="0 0 16 16" width="18" height="18" fill="none"><path d="M8 2L2 5.5v5L8 14l6-3.5v-5L8 2z" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round"/></svg>, label: t('dashboard.kpi_projects'), value: kpis?.projects_active ?? 0, sub: `${kpis?.projects_at_risk ?? 0} ${t('dashboard.kpi_at_risk')}`, color: 'var(--accent)', path: '/projects' },
    { icon: <svg viewBox="0 0 16 16" width="18" height="18" fill="none"><rect x="2" y="2" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.4"/><rect x="9" y="2" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.4"/><rect x="2" y="9" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.4"/><rect x="9" y="9" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.4"/></svg>, label: t('dashboard.kpi_tasks_open'), value: kpis?.tasks_open ?? 0, sub: `${kpis?.tasks_overdue ?? 0} ${t('dashboard.kpi_tasks_overdue')}`, color: 'var(--success)', path: '/tasks' },
    { icon: <svg viewBox="0 0 16 16" width="18" height="18" fill="none"><rect x="2" y="4" width="12" height="9" rx="1.5" stroke="currentColor" strokeWidth="1.4"/><path d="M5 4V3a1 1 0 011-1h4a1 1 0 011 1v1" stroke="currentColor" strokeWidth="1.4"/></svg>, label: t('dashboard.kpi_clients'), value: activeClients, sub: `${clients.length} ${t('dashboard.kpi_clients_total')}`, color: 'var(--warning)', path: '/clients' },
    { icon: <svg viewBox="0 0 16 16" width="18" height="18" fill="none"><rect x="2" y="2" width="12" height="12" rx="2" stroke="currentColor" strokeWidth="1.4"/><path d="M5.5 6.5h5M5.5 9.5h3" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/></svg>, label: t('dashboard.kpi_tickets'), value: sdData ?? 0, sub: 'Service Desk', color: 'var(--purple)', path: '/service-desk' },
    { icon: <svg viewBox="0 0 16 16" width="18" height="18" fill="none"><path d="M8 2v12M4.5 5.5C4.5 4.1 6.1 3 8 3s3.5 1.1 3.5 2.5c0 1.4-1.4 2-3.5 2.5-2.1.5-3.5 1.2-3.5 2.5S6.1 13 8 13s3.5-1.1 3.5-2.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/></svg>, label: t('dashboard.kpi_budget'), value: `${budgetPct}%`, sub: t('dashboard.kpi_consumed'), color: 'var(--warning)', path: '/budgets' },
    { icon: <svg viewBox="0 0 16 16" width="18" height="18" fill="none"><circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.4"/><path d="M8 5v3.5l2 2" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/></svg>, label: t('dashboard.kpi_hours'), value: fmtHours(kpis?.hours_logged_this_week), sub: t('dashboard.kpi_work'), color: 'var(--accent)', path: '/timesheets' },
  ]

  return (
    <div className="grid-kpi grid-kpi-dashboard" style={{ marginBottom: 0 }}>
      {cards.map(c => (
        <div key={c.label} onClick={() => nav(c.path)}
          className="surface-card-interactive"
          style={{ padding: '18px 16px' }}
          onMouseEnter={e => e.currentTarget.style.borderColor = c.color + '60'}
          onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--surface-4)'}>
          <div style={{ color: c.color, marginBottom: 10, opacity: 0.85 }}>{c.icon}</div>
          <AnimatedKpi value={c.value} color={c.color} />
          <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-1)', marginBottom: 2 }}>{c.label}</div>
          <div style={{ fontSize: 11, color: 'var(--text-2)' }}>{c.sub}</div>
        </div>
      ))}
    </div>
  )
}

// ── Mis tareas pendientes ─────────────────────────────────────────────────────
function MyPendingWidget() {
  const nav = useNavigate()
  const t = useAppT()
  const { data: tasks = [], isLoading } = useQuery({
    queryKey: ['dash-my-tasks'],
    queryFn: () => api.get('/tasks', { params: { status: 'in_progress,todo', limit: 8, assigned_to_me: true } }).then(r => { const d = r.data; return Array.isArray(d) ? d : (Array.isArray(d?.items) ? d.items : []); }),
  })
  const PRIO_COLOR = { critical: 'var(--danger)', high: 'var(--warning)', medium: 'var(--accent)', low: 'var(--text-2)' }

  return (
    <div style={{ ...panel, padding: '20px 22px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div style={{ fontSize: 14, fontWeight: 700 }}>▦ {t('dashboard.widget_tasks')}</div>
        <button onClick={() => nav('/tasks')} style={{ fontSize: 11, color: 'var(--accent)', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit' }}>{t('dashboard.see_all_f')}</button>
      </div>
      {isLoading ? <Spinner /> : tasks.length === 0 ? (
        <div style={{ fontSize: 12, color: 'var(--success)', padding: '8px 0' }}>✓ {t('dashboard.no_tasks')}</div>
      ) : tasks.slice(0, 6).map(task => (
        <div key={task.id} style={{ display: 'flex', gap: 10, padding: '8px 0', borderBottom: '1px solid var(--surface-4)', alignItems: 'center' }}>
          <div style={{ width: 8, height: 8, borderRadius: '50%', background: PRIO_COLOR[task.priority] || 'var(--text-2)', flexShrink: 0 }} role="img" aria-label={`Prioridad: ${task.priority || 'normal'}`} />
          <div style={{ flex: 1, fontSize: 12, color: 'var(--text-1)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{task.title}</div>
          <div style={{ fontSize: 11, color: 'var(--text-2)', whiteSpace: 'nowrap' }}>{task.due_date?.slice(5, 10) || '—'}</div>
        </div>
      ))}
    </div>
  )
}

// ── Alertas recientes ─────────────────────────────────────────────────────────
function AlertsWidget() {
  const t = useAppT()
  const { data: alerts = [] } = useQuery({
    queryKey: ['dash-alerts'],
    queryFn: () => alertsApi.list({ resolved: false }).then(r => { const d = r.data; return Array.isArray(d) ? d : (Array.isArray(d?.items) ? d.items : (d?.data || [])); }),
  })
  const SEV_COLOR = { critical: 'var(--danger)', warning: 'var(--warning)', info: 'var(--accent)' }

  return (
    <div style={{ ...panel, padding: '20px 22px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <div style={{ fontSize: 14, fontWeight: 700 }}>🔔 {t('dashboard.widget_alerts')} <span style={{ fontSize: 12, background: 'var(--danger-bg)', color: 'var(--danger)', borderRadius: 10, padding: '1px 7px', marginLeft: 6 }}>{alerts.filter(a => !a.is_read).length}</span></div>
      </div>
      {alerts.length === 0 ? <div style={{ fontSize: 12, color: 'var(--success)' }}>✓ {t('dashboard.no_alerts')}</div>
        : alerts.slice(0, 5).map(a => (
          <div key={a.id} style={{ display: 'flex', gap: 10, padding: '7px 0', borderBottom: '1px solid var(--surface-4)', alignItems: 'flex-start' }}>
            <span style={{ color: SEV_COLOR[a.severity] || 'var(--text-2)', fontSize: 14, marginTop: 1 }} role="img" aria-label={`Severidad: ${a.severity || 'info'}`}>●</span>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 12, color: a.is_read ? 'var(--text-2)' : 'var(--text-1)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{a.title}</div>
              <div style={{ fontSize: 10, color: 'var(--text-3)' }}>{a.created_at?.slice(0, 10)}</div>
            </div>
          </div>
        ))
      }
    </div>
  )
}

// ── Carga del equipo ──────────────────────────────────────────────────────────
function TeamLoadWidget() {
  const t = useAppT()
  const { data: rawLoad = [], isLoading } = useQuery({
    queryKey: ['dash-team-load'],
    queryFn: () => dashboardApi.resourceLoad()
      .then(r => {
        const d = r.data
        return Array.isArray(d) ? d : (Array.isArray(d?.items) ? d.items : [])
      })
      .catch(() => []),
  })

  const load = rawLoad
    .slice(0, 8)
    .map(u => ({ ...u, load_pct: u.load_pct || 0 }))

  const allZero = load.length > 0 && load.every(u => u.load_pct === 0)

  return (
    <div style={{ ...panel, padding: '20px 22px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div style={{ fontSize: 14, fontWeight: 700 }}>👥 {t('dashboard.widget_team')}</div>
        <div style={{ fontSize: 10, color: 'var(--text-2)' }}>{t('dashboard.this_week')}</div>
      </div>

      {isLoading ? (
        <div style={{ fontSize: 12, color: 'var(--text-2)', textAlign: 'center', padding: '20px 0' }}>{t('dashboard.loading')}</div>
      ) : load.length === 0 ? (
        <div style={{ fontSize: 12, color: 'var(--text-2)', padding: '12px 0' }}>
          {t('dashboard.no_team_config')}
        </div>
      ) : allZero ? (
        <div>
          <div style={{ fontSize: 11, color: 'var(--warning)', marginBottom: 10, padding: '6px 10px',
            background: 'var(--warning-bg)', borderRadius: 6, border: 'var(--warning-border)' }}>
            ⚠ {t('dashboard.team_zero_msg')}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {load.map((u, i) => (
              <div key={u.user_id || i} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <div style={{ fontSize: 11, color: 'var(--text-2)', width: 80, flexShrink: 0,
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {u.user_name?.split(' ')[0] || 'Usuario'}
                </div>
                <div style={{ flex: 1, height: 6, background: 'var(--surface-4)', borderRadius: 3 }}>
                  <div style={{ width: '0%', height: '100%', background: 'var(--success)', borderRadius: 3 }} />
                </div>
                <div style={{ fontSize: 10, color: 'var(--text-2)', width: 30, textAlign: 'right' }}>0%</div>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={160}>
          <BarChart data={load} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
            <XAxis dataKey="user_name" tick={{ fontSize: 10, fill: 'var(--text-2)' }}
              tickFormatter={n => (n || '').split(' ')[0]} />
            <YAxis tick={{ fontSize: 10, fill: 'var(--text-2)' }} domain={[0, 120]}
              tickFormatter={v => `${v}%`} />
            <Tooltip
              formatter={v => [`${Math.round(v)}%`, t('dashboard.load_label')]}
              contentStyle={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 8 }} />
            <Bar dataKey="load_pct" radius={[4, 4, 0, 0]} minPointSize={2}>
              {load.map((e, i) => (
                <Cell key={i}
                  fill={e.load_pct > 100 ? 'var(--danger)' : e.load_pct > 85 ? 'var(--warning)' : 'var(--success)'} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}

// ── Pipeline por etapa ────────────────────────────────────────────────────────
function PipelineWidget() {
  const _nav = useNavigate()
  const t = useAppT()
  const { data: opps = [] } = useQuery({
    queryKey: ['dash-pipeline'],
    queryFn: () => api.get('/pipeline', { params: { limit: 50 } }).then(r => {
      const d = r.data
      return Array.isArray(d) ? d : (Array.isArray(d?.items) ? d.items : [])
    }).catch(() => []),
  })
  const byStage = opps.reduce((acc, o) => { acc[o.stage] = (acc[o.stage] || 0) + 1; return acc }, {})
  const data = Object.entries(byStage).map(([name, value]) => ({ name, value }))
  const totalRevenue = opps.reduce((s, o) => s + (o.expected_revenue || 0), 0)

  return (
    <div style={{ ...panel, padding: '20px 22px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div style={{ fontSize: 14, fontWeight: 700 }}>🎪 {t('dashboard.widget_pipeline')}</div>
        <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--success)' }}>{fmtCurrency(totalRevenue)}</div>
      </div>
      {data.length === 0 ? <div style={{ fontSize: 12, color: 'var(--text-2)' }}>{t('dashboard.no_opps')}</div> : (
        <>
          <ResponsiveContainer width="100%" height={130}>
            <PieChart>
              <Pie data={data} cx="50%" cy="50%" innerRadius={35} outerRadius={55} dataKey="value">
                {data.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
              </Pie>
              <Tooltip contentStyle={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 8 }} />
            </PieChart>
          </ResponsiveContainer>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 8 }}>
            {data.map((d, i) => (
              <span key={d.name} style={{ fontSize: 10, padding: '2px 8px', borderRadius: 20, background: COLORS[i % COLORS.length] + '20', color: COLORS[i % COLORS.length] }}>
                {d.name} ({d.value})
              </span>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

// ── Proyectos por salud ───────────────────────────────────────────────────────
function ProjectsHealthWidget() {
  const nav = useNavigate()
  const t = useAppT()
  const { data: projects = [], isLoading } = useQuery({
    queryKey: ['dash-projects-health'],
    queryFn: () => api.get('/dashboard/projects-health').then(r => {
      const d = r.data
      return Array.isArray(d) ? d : (Array.isArray(d?.items) ? d.items : (Array.isArray(d?.data) ? d.data : []))
    }).catch(() => []),
    staleTime: 60000,
  })

  const safeProjects = (Array.isArray(projects) ? projects : []).map((p) => ({
    ...p,
    schedule_deviation_days: Number(p?.schedule_deviation_days) || 0,
    budget_used_pct: Number(p?.budget_used_pct) || 0,
    alerts_count: Number(p?.alerts_count) || 0,
    tasks_total: Number(p?.tasks_total) || 0,
    tasks_done: Number(p?.tasks_done) || 0,
    progress_pct: Number(p?.progress_pct) || 0,
    health_score: p?.health_score == null ? null : Number(p.health_score),
  }))

  const getColor = (p) => {
    if (p.schedule_deviation_days > 0 || p.budget_used_pct > 100) return 'var(--danger)'
    if (p.budget_used_pct > 80 || p.alerts_count > 0) return 'var(--warning)'
    return 'var(--success)'
  }
  const getIcon = (p) => {
    if (p.schedule_deviation_days > 0 || p.budget_used_pct > 100) return '🔴'
    if (p.budget_used_pct > 80 || p.alerts_count > 0) return '🟡'
    return '🟢'
  }
  const getLabel = (p) => {
    if (p.schedule_deviation_days > 0) return `${p.schedule_deviation_days}d ${t('dashboard.delayed_label')}`
    if (p.budget_used_pct > 100) return `${p.budget_used_pct.toFixed(0)}% ${t('dashboard.budget_label')}`
    if (p.budget_used_pct > 80) return `${p.budget_used_pct.toFixed(0)}% ${t('dashboard.budget_label')}`
    if (p.alerts_count > 0) return `${p.alerts_count} ${p.alerts_count > 1 ? t('dashboard.alert_plural') : t('dashboard.alert_sing')}`
    return t('dashboard.on_time')
  }

  const counts = {
    ok:   safeProjects.filter(p => getColor(p) === 'var(--success)').length,
    warn: safeProjects.filter(p => getColor(p) === 'var(--warning)').length,
    crit: safeProjects.filter(p => getColor(p) === 'var(--danger)').length,
  }

  return (
    <div style={{ ...panel, padding: '20px 22px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
        <div style={{ fontSize: 14, fontWeight: 700 }}>⬡ {t('dashboard.widget_health')}</div>
        <button onClick={() => nav('/projects')} style={{ fontSize: 11, color: 'var(--accent)', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit' }}>{t('dashboard.see_all_m')}</button>
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 14 }}>
        {[['🟢', counts.ok, 'var(--success)', t('dashboard.health_ok')], ['🟡', counts.warn, 'var(--warning)', t('dashboard.health_risk')], ['🔴', counts.crit, 'var(--danger)', t('dashboard.health_critical')]].map(([ico, n, color, lbl]) => (
          <div key={lbl} style={{ flex: 1, textAlign: 'center', padding: '8px 4px',
            background: n > 0 ? `${color}15` : 'var(--surface-3)',
            border: `1px solid ${n > 0 ? color + '40' : 'transparent'}`, borderRadius: 8 }}>
            <div style={{ fontSize: 18 }}>{ico}</div>
            <div style={{ fontSize: 18, fontWeight: 800, color: n > 0 ? color : 'var(--text-3)',
              fontFamily: 'var(--font-mono)' }}>{n}</div>
            <div style={{ fontSize: 10, color: 'var(--text-2)' }}>{lbl}</div>
          </div>
        ))}
      </div>

      {isLoading ? <div style={{ fontSize: 12, color: 'var(--text-3)', textAlign: 'center', padding: 8 }}>{t('dashboard.loading')}</div> : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 5, maxHeight: 180, overflowY: 'auto' }}>
          {safeProjects.length === 0 && (
            <div style={{ fontSize: 12, color: 'var(--text-3)', textAlign: 'center', padding: 8 }}>{t('dashboard.no_projects')}</div>
          )}
          {safeProjects.sort((a,b) => {
            const rank = p => p.schedule_deviation_days > 0 || p.budget_used_pct > 100 ? 0
              : p.budget_used_pct > 80 || p.alerts_count > 0 ? 1 : 2
            return rank(a) - rank(b)
          }).map(p => (
            <div key={p.project_id}
              onClick={() => nav('/projects')}
              style={{ display: 'flex', alignItems: 'flex-start', gap: 8, padding: '6px 8px',
                background: 'var(--surface-3)', borderRadius: 7,
                border: `1px solid ${getColor(p)}25`, cursor: 'pointer' }}>
              <span style={{ fontSize: 12, flexShrink: 0, marginTop: 1 }}>{getIcon(p)}</span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-1)',
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {p.project_code} — {p.project_name}
                </div>
                {p.tasks_total > 0 && (
                  <div style={{ marginTop: 4 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 2 }}>
                      <span style={{ fontSize: 9, color: 'var(--text-3)' }}>
                        {p.tasks_done}/{p.tasks_total} {t('dashboard.tasks_lbl')}
                      </span>
                      <span style={{ fontSize: 9, color: 'var(--text-2)', fontWeight: 600 }}>
                        {p.progress_pct.toFixed(0)}%
                      </span>
                    </div>
                    <div style={{ height: 3, background: 'var(--surface-4)', borderRadius: 2 }}>
                      <div style={{ width: `${p.progress_pct}%`, height: '100%',
                        background: p.progress_pct >= 100 ? 'var(--success)' : 'var(--accent)',
                        borderRadius: 2, transition: 'width 0.3s ease' }} />
                    </div>
                  </div>
                )}
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4, flexShrink: 0 }}>
                {p.health_score != null && (
                  <div style={{ fontSize: 11, fontWeight: 800, fontFamily: 'var(--font-mono)', lineHeight: 1,
                    color: p.health_score >= 75 ? 'var(--success)' : p.health_score >= 50 ? 'var(--warning)' : 'var(--danger)' }}>
                    {p.health_score}<span style={{ fontSize: 8, fontWeight: 400, color: 'var(--text-3)', marginLeft: 1 }}>/100</span>
                  </div>
                )}
                <div style={{ fontSize: 10, color: getColor(p), fontWeight: 600, whiteSpace: 'nowrap' }}>
                  {getLabel(p)}
                </div>
                {p.budget_used_pct > 0 && (
                  <div style={{ width: 36 }}>
                    <div style={{ fontSize: 8, color: 'var(--text-3)', textAlign: 'right', marginBottom: 1 }}>
                      {p.budget_used_pct.toFixed(0)}% {t('dashboard.budget_abbr')}
                    </div>
                    <div style={{ height: 3, background: 'var(--surface-4)', borderRadius: 2 }}>
                      <div style={{ width: `${Math.min(100, p.budget_used_pct)}%`, height: '100%',
                        background: getColor(p), borderRadius: 2 }} />
                    </div>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Clientes activos recientes ────────────────────────────────────────────────
function TopClientsWidget() {
  const nav = useNavigate()
  const t = useAppT()
  const { data: clients = [] } = useQuery({
    queryKey: ['dash-top-clients'],
    queryFn: () => api.get('/clients', { params: { status: 'active', limit: 5 } }).then(r => {
      const d = r.data
      return Array.isArray(d) ? d : (Array.isArray(d?.items) ? d.items : [])
    }).catch(() => []),
  })
  return (
    <div style={{ ...panel, padding: '20px 22px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div style={{ fontSize: 14, fontWeight: 700 }}>🏢 {t('dashboard.widget_clients')}</div>
        <button onClick={() => nav('/clients')} style={{ fontSize: 11, color: 'var(--accent)', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit' }}>{t('dashboard.see_all_m')}</button>
      </div>
      {clients.length === 0 ? <div style={{ fontSize: 12, color: 'var(--text-2)' }}>{t('dashboard.no_clients')}</div>
        : clients.map(c => (
          <div key={c.id} onClick={() => nav('/clients')}
            style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 0', borderBottom: '1px solid var(--surface-4)', cursor: 'pointer' }}>
            <div style={{ width: 28, height: 28, borderRadius: 7, background: 'var(--warning-bg)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, fontWeight: 800, color: 'var(--warning)', flexShrink: 0 }}>
              {c.name?.charAt(0)?.toUpperCase()}
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-1)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.name}</div>
              <div style={{ fontSize: 10, color: 'var(--text-2)' }}>⬡ {c.projects_count} · 🎫 {c.tickets_count}</div>
            </div>
          </div>
        ))
      }
    </div>
  )
}

// ── Horas esta semana ─────────────────────────────────────────────────────────
function HoursChartWidget() {
  const t = useAppT()
  const { data: hoursData = [] } = useQuery({
    queryKey: ['dash-hours-week'],
    queryFn: () => api.get('/analytics/hours_by_week').then(r => r.data?.data || []).catch(() => []),
  })
  return (
    <div style={{ ...panel, padding: '20px 22px' }}>
      <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 16 }}>⏱ {t('dashboard.widget_hours')}</div>
      {hoursData.length === 0 ? <div style={{ fontSize: 12, color: 'var(--text-2)' }}>{t('dashboard.no_hours')}</div> : (
        <ResponsiveContainer width="100%" height={140}>
          <AreaChart data={hoursData.slice(-8)} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-4)" />
            <XAxis dataKey="label" tick={{ fontSize: 10, fill: 'var(--text-2)' }} />
            <YAxis tick={{ fontSize: 10, fill: 'var(--text-2)' }} />
            <Tooltip contentStyle={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 8 }} />
            <Area type="monotone" dataKey="hours" stroke="var(--accent)" fill="var(--accent-muted)" strokeWidth={2} />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}

// ── Actividad reciente ────────────────────────────────────────────────────────
function RecentActivityWidget() {
  const t = useAppT()
  const { data: activity = [] } = useQuery({
    queryKey: ['dash-activity'],
    queryFn: () => api.get('/alerts', { params: { limit: 8, resolved: false } }).then(r => { const d = r.data; return Array.isArray(d) ? d : (Array.isArray(d?.items) ? d.items : []); }).catch(() => []),
  })
  const { data: tickets = [] } = useQuery({
    queryKey: ['dash-recent-tickets'],
    queryFn: () => api.get('/sd/tickets', { params: { page_size: 4 } }).then(r => { const d = r.data; return Array.isArray(d) ? d : (d?.tickets || d?.items || []); }).catch(() => []),
  })

  const items = [
    ...(Array.isArray(tickets) ? tickets : []).slice(0, 3).map(t => ({ icon: '🎫', text: t.title, time: t.created_at, color: 'var(--purple)' })),
    ...(Array.isArray(activity) ? activity : []).slice(0, 5).map(a => ({ icon: '🔔', text: a.title, time: a.created_at, color: 'var(--warning)' })),
  ].sort((a, b) => (b.time || '').localeCompare(a.time || '')).slice(0, 6)

  return (
    <div style={{ ...panel, padding: '20px 22px' }}>
      <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 16 }}>⚡ {t('dashboard.widget_activity')}</div>
      {items.length === 0 ? <div style={{ fontSize: 12, color: 'var(--text-2)' }}>{t('dashboard.no_activity')}</div>
        : items.map((item, i) => (
          <div key={i} style={{ display: 'flex', gap: 10, padding: '7px 0', borderBottom: i < items.length - 1 ? '1px solid var(--surface-4)' : 'none', alignItems: 'flex-start' }}>
            <span style={{ fontSize: 14, flexShrink: 0 }}>{item.icon}</span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 12, color: 'var(--text-1)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.text}</div>
              <div style={{ fontSize: 10, color: 'var(--text-3)' }}>{item.time?.slice(0, 16)?.replace('T', ' ')}</div>
            </div>
          </div>
        ))
      }
    </div>
  )
}

// ── Recent Documents Widget ───────────────────────────────────────────────────
function RecentDocumentsWidget() {
  const nav = useNavigate()
  const t = useAppT()
  const { data: docs = [] } = useQuery({
    queryKey: ['dash-recent-docs'],
    queryFn: () => api.get('/documents', { params: { limit: 6 } }).then(r => {
      const d = r.data
      return Array.isArray(d) ? d : (Array.isArray(d?.items) ? d.items : [])
    }).catch(() => []),
  })

  const FILE_C = { pdf:'#ef4444', image:'#3b82f6', spreadsheet:'#10b981', word:'#6366f1', presentation:'#f59e0b', other:'#6b7280' }
  function typeColor(mime, name) {
    const ext = (name||'').split('.').pop()?.toLowerCase()
    if (mime?.startsWith('image/')) return FILE_C.image
    if (mime==='application/pdf'||ext==='pdf') return FILE_C.pdf
    if (mime?.includes('spreadsheet')||['xls','xlsx','csv'].includes(ext)) return FILE_C.spreadsheet
    if (mime?.includes('word')||['doc','docx'].includes(ext)) return FILE_C.word
    if (mime?.includes('presentation')||['ppt','pptx'].includes(ext)) return FILE_C.presentation
    return FILE_C.other
  }
  function typeLabel(mime, name) {
    const ext = (name||'').split('.').pop()?.toLowerCase()
    if (mime?.startsWith('image/')) return 'IMG'
    if (mime==='application/pdf'||ext==='pdf') return 'PDF'
    if (['xls','xlsx','csv'].includes(ext)) return 'XLS'
    if (['doc','docx'].includes(ext)) return 'DOC'
    if (['ppt','pptx'].includes(ext)) return 'PPT'
    return 'FILE'
  }

  return (
    <div style={{ ...panel, padding: '20px 22px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div style={{ fontSize: 14, fontWeight: 700 }}>📎 {t('dashboard.widget_docs')}</div>
        <button onClick={() => nav('/documents')} style={{ fontSize: 11, color: 'var(--accent)', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit' }}>{t('dashboard.see_all_m')}</button>
      </div>
      {docs.length === 0 ? (
        <div style={{ fontSize: 12, color: 'var(--text-3)', padding: '8px 0' }}>{t('dashboard.no_docs')}</div>
      ) : docs.slice(0, 5).map((doc, i) => {
        const lv = doc.latest_version
        const c = typeColor(lv?.file_mime_type, lv?.file_name)
        const l = typeLabel(lv?.file_mime_type, lv?.file_name)
        const d = new Date(doc.created_at)
        const diff = Math.floor((Date.now() - d.getTime()) / 86400000)
        const when = diff === 0 ? t('dashboard.today') : diff === 1 ? t('dashboard.yesterday') : t('dashboard.days_ago').replace('{n}', diff)
        return (
          <div key={doc.id} style={{ display: 'flex', gap: 10, padding: '7px 0', borderBottom: i < 4 ? '1px solid var(--surface-4)' : 'none', alignItems: 'center' }}>
            <div style={{ width: 28, height: 28, borderRadius: 7, backgroundColor: c + '18', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, fontFamily: 'var(--font-mono)', fontSize: 9, fontWeight: 700, color: c }}>
              {l}
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 12, color: 'var(--text-1)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{doc.title}</div>
              <div style={{ fontSize: 10, color: 'var(--text-3)' }}>{doc.category} · {when}</div>
            </div>
            {doc.requires_approval && doc.approval_status === 'pending' && (
              <span style={{ fontSize: 9, padding: '1px 6px', borderRadius: 10, backgroundColor: 'var(--warning-bg)', color: 'var(--warning)', fontWeight: 700, flexShrink: 0 }}>◷</span>
            )}
          </div>
        )
      })}
    </div>
  )
}

// ── Tareas vencidas ───────────────────────────────────────────────────────────
function OverdueTasksWidget() {
  const nav = useNavigate()
  const t = useAppT()
  const { data: tasks = [], isLoading } = useQuery({
    queryKey: ['dash-overdue-tasks'],
    queryFn: () => api.get('/tasks', { params: { overdue_only: true, page_size: 8 } })
      .then(r => { const d = r.data; return Array.isArray(d) ? d : [] })
      .catch(() => []),
    staleTime: 60000,
  })

  const PRIO_COLOR = { critical: 'var(--danger)', high: 'var(--warning)', medium: 'var(--accent)', low: 'var(--text-2)' }
  const daysDue = (due) => {
    const diff = Math.floor((Date.now() - new Date(due).getTime()) / 86400000)
    return `${diff} ${diff === 1 ? t('common.day') : t('common.days')}`
  }

  return (
    <div style={{ ...panel, padding: '20px 22px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div style={{ fontSize: 14, fontWeight: 700 }}>
          ⚠ {t('dashboard.widget_overdue')}
          {tasks.length > 0 && (
            <span style={{ marginLeft: 8, fontSize: 12, background: 'var(--danger-bg)', color: 'var(--danger)', borderRadius: 10, padding: '1px 8px' }}>
              {tasks.length}
            </span>
          )}
        </div>
        <button onClick={() => nav('/tasks')} style={{ fontSize: 11, color: 'var(--accent)', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit' }}>{t('dashboard.see_all_f')}</button>
      </div>
      {isLoading ? <Spinner /> : tasks.length === 0 ? (
        <div style={{ fontSize: 12, color: 'var(--success)', padding: '8px 0' }}>✓ {t('dashboard.no_overdue')}</div>
      ) : tasks.slice(0, 6).map(task => (
        <div key={task.id} style={{ display: 'flex', gap: 10, padding: '8px 0', borderBottom: '1px solid var(--surface-4)', alignItems: 'center' }}>
          <div style={{ width: 6, height: 6, borderRadius: '50%', background: PRIO_COLOR[task.priority] || 'var(--text-2)', flexShrink: 0, marginTop: 1 }} role="img" aria-label={`Prioridad: ${task.priority || 'normal'}`} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 12, color: 'var(--text-1)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{task.title}</div>
            <div style={{ fontSize: 10, color: 'var(--text-3)' }}>{task.code} · {task.assignee?.full_name?.split(' ')[0] || t('dashboard.no_assignee')}</div>
          </div>
          <div style={{ fontSize: 11, color: 'var(--danger)', fontWeight: 700, whiteSpace: 'nowrap', flexShrink: 0 }}>
            +{daysDue(task.due_date)}
          </div>
        </div>
      ))}
    </div>
  )
}

// ── Burndown Widget ───────────────────────────────────────────────────────────
function BurndownWidget() {
  const t = useAppT()
  const { data: sprints = [] } = useQuery({
    queryKey: ['dash-sprints-active'],
    queryFn: () => api.get('/sprints', { params: { status: 'active', limit: 1 } }).then(r => {
      const d = r.data; return Array.isArray(d) ? d : (d?.items ?? [])
    }).catch(() => []),
    staleTime: 60000,
  })
  const activeSprint = sprints[0]
  const { data: sprintTasks = [] } = useQuery({
    queryKey: ['dash-burndown-tasks', activeSprint?.id],
    queryFn: () => api.get('/tasks', { params: { sprint_id: activeSprint.id, limit: 200 } }).then(r => {
      const d = r.data; return Array.isArray(d) ? d : (d?.items ?? [])
    }).catch(() => []),
    enabled: !!activeSprint?.id,
    staleTime: 60000,
  })

  const total = sprintTasks.length
  const done = sprintTasks.filter(tk => tk.status === 'done').length
  const inProg = sprintTasks.filter(tk => tk.status === 'in_progress').length
  const pct = total > 0 ? Math.round(done / total * 100) : 0

  return (
    <div style={{ ...panel, padding: '20px 22px' }}>
      <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 16 }}>📉 {t('dashboard.widget_burndown')}</div>
      {!activeSprint ? (
        <div style={{ fontSize: 12, color: 'var(--text-3)' }}>{t('dashboard.no_active_sprint')}</div>
      ) : (
        <>
          <div style={{ fontSize: 12, color: 'var(--text-2)', marginBottom: 14, fontWeight: 600 }}>{activeSprint.name}</div>
          <div style={{ display: 'flex', gap: 10, marginBottom: 16 }}>
            {[
              { label: t('dashboard.done_label'), value: done, color: 'var(--success)' },
              { label: t('dashboard.in_progress_label'), value: inProg, color: 'var(--accent)' },
              { label: t('dashboard.remaining_label'), value: Math.max(0, total - done - inProg), color: 'var(--text-3)' },
            ].map(s => (
              <div key={s.label} style={{ flex: 1, textAlign: 'center', padding: '10px 6px', background: 'var(--surface-3)', borderRadius: 8 }}>
                <div style={{ fontSize: 20, fontWeight: 800, color: s.color }}>{s.value}</div>
                <div style={{ fontSize: 10, color: 'var(--text-2)', marginTop: 2 }}>{s.label}</div>
              </div>
            ))}
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--text-3)', marginBottom: 4 }}>
            <span>{pct}% {t('dashboard.completed_label')}</span>
            <span>{total} {t('dashboard.tasks_total_label')}</span>
          </div>
          <div style={{ background: 'var(--surface-4)', borderRadius: 6, height: 10, overflow: 'hidden' }}>
            <div style={{ width: `${pct}%`, height: '100%', background: pct >= 80 ? 'var(--success)' : pct >= 50 ? 'var(--accent)' : 'var(--warning)', borderRadius: 6, transition: 'width 0.6s' }} />
          </div>
        </>
      )}
    </div>
  )
}

// ── Velocity Widget ───────────────────────────────────────────────────────────
function VelocityWidget() {
  const t = useAppT()
  const { data: sprints = [] } = useQuery({
    queryKey: ['dash-velocity'],
    queryFn: () => api.get('/sprints', { params: { status: 'completed', limit: 6 } }).then(r => {
      const d = r.data; return Array.isArray(d) ? d : (d?.items ?? [])
    }).catch(() => []),
    staleTime: 120000,
  })

  const data = sprints.map(s => ({
    name: (s.name || `S${s.id}`).slice(0, 10),
    pts: s.completed_points ?? s.velocity ?? 0,
  }))

  return (
    <div style={{ ...panel, padding: '20px 22px' }}>
      <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 12 }}>🚀 {t('dashboard.widget_velocity')}</div>
      {data.length === 0 ? (
        <div style={{ fontSize: 12, color: 'var(--text-3)' }}>{t('dashboard.no_sprint_data')}</div>
      ) : (
        <ResponsiveContainer width="100%" height={150}>
          <BarChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-4)" />
            <XAxis dataKey="name" tick={{ fontSize: 10, fill: 'var(--text-2)' }} axisLine={false} />
            <YAxis tick={{ fontSize: 10, fill: 'var(--text-2)' }} axisLine={false} />
            <Tooltip contentStyle={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 8, fontSize: 12 }} />
            <Bar dataKey="pts" fill="var(--accent)" radius={[4,4,0,0]} />
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}

// ── Expenses Widget ───────────────────────────────────────────────────────────
function ExpensesWidget() {
  const t = useAppT()
  const { data: expenses = [] } = useQuery({
    queryKey: ['dash-expenses'],
    queryFn: () => api.get('/expenses', { params: { limit: 100 } }).then(r => {
      const d = r.data; return Array.isArray(d) ? d : (d?.items ?? [])
    }).catch(() => []),
    staleTime: 120000,
  })

  const byCategory = expenses.reduce((acc, e) => {
    const cat = e.category || 'other'
    acc[cat] = (acc[cat] || 0) + (e.amount || 0)
    return acc
  }, {})
  const data = Object.entries(byCategory).sort((a,b) => b[1]-a[1]).slice(0, 5)
  const grandTotal = expenses.reduce((s, e) => s + (e.amount || 0), 0)

  return (
    <div style={{ ...panel, padding: '20px 22px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
        <div style={{ fontSize: 14, fontWeight: 700 }}>💰 {t('dashboard.widget_expenses')}</div>
        <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-2)' }}>{fmtCurrency(grandTotal)}</div>
      </div>
      {data.length === 0 ? (
        <div style={{ fontSize: 12, color: 'var(--text-3)' }}>—</div>
      ) : data.map(([cat, total]) => {
        const pct = grandTotal > 0 ? Math.round(total / grandTotal * 100) : 0
        return (
          <div key={cat} style={{ marginBottom: 10 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--text-2)', marginBottom: 3 }}>
              <span style={{ textTransform: 'capitalize' }}>{cat}</span>
              <span style={{ fontWeight: 600 }}>{pct}%</span>
            </div>
            <div style={{ background: 'var(--surface-4)', borderRadius: 4, height: 6, overflow: 'hidden' }}>
              <div style={{ width: `${pct}%`, height: '100%', background: 'var(--accent)', borderRadius: 4 }} />
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── Risks Widget ──────────────────────────────────────────────────────────────
function RisksWidget() {
  const nav = useNavigate()
  const t = useAppT()
  const { data: risks = [] } = useQuery({
    queryKey: ['dash-risks'],
    queryFn: () => api.get('/risks', { params: { limit: 200 } }).then(r => {
      const d = r.data; return Array.isArray(d) ? d : (d?.items ?? [])
    }).catch(() => []),
    staleTime: 120000,
  })

  const bySev = { critical: 0, high: 0, medium: 0, low: 0 }
  risks.forEach(r => { if (r.severity in bySev) bySev[r.severity]++ })
  const COLORS_SEV = { critical: 'var(--danger)', high: 'var(--warning)', medium: 'var(--accent)', low: 'var(--success)' }

  return (
    <div style={{ ...panel, padding: '20px 22px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div style={{ fontSize: 14, fontWeight: 700 }}>⚠️ {t('dashboard.widget_risks')}</div>
        <button onClick={() => nav('/grc')} style={{ fontSize: 11, color: 'var(--accent)', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit' }}>{t('dashboard.see_all_m')}</button>
      </div>
      {risks.length === 0 ? (
        <div style={{ fontSize: 12, color: 'var(--success)', padding: '8px 0' }}>✓ {t('dashboard.no_risks')}</div>
      ) : (
        <>
          {Object.entries(bySev).filter(([,v]) => v > 0).map(([sev, count]) => (
            <div key={sev} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '7px 0', borderBottom: '1px solid var(--surface-4)' }}>
              <div style={{ width: 8, height: 8, borderRadius: '50%', background: COLORS_SEV[sev], flexShrink: 0 }} />
              <span style={{ flex: 1, fontSize: 12, color: 'var(--text-1)', textTransform: 'capitalize' }}>{sev}</span>
              <span style={{ fontSize: 14, fontWeight: 800, color: COLORS_SEV[sev], fontFamily: 'var(--font-mono)' }}>{count}</span>
            </div>
          ))}
          <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 10 }}>{t('dashboard.total_risks')}: {risks.length}</div>
        </>
      )}
    </div>
  )
}

// ── Approvals Widget ──────────────────────────────────────────────────────────
function ApprovalsWidget() {
  const t = useAppT()
  const { data: approvals = [] } = useQuery({
    queryKey: ['dash-approvals'],
    queryFn: () => api.get('/approvals', { params: { status: 'pending', limit: 8 } }).then(r => {
      const d = r.data; return Array.isArray(d) ? d : (d?.items ?? [])
    }).catch(() => []),
    staleTime: 60000,
  })

  return (
    <div style={{ ...panel, padding: '20px 22px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div style={{ fontSize: 14, fontWeight: 700 }}>✅ {t('dashboard.widget_approvals')}</div>
        <span style={{ fontSize: 11, color: 'var(--text-3)', background: 'var(--surface-3)', padding: '2px 8px', borderRadius: 10 }}>
          {approvals.length} {t('dashboard.pending_label')}
        </span>
      </div>
      {approvals.length === 0 ? (
        <div style={{ fontSize: 12, color: 'var(--success)', padding: '8px 0' }}>✓ {t('dashboard.no_approvals')}</div>
      ) : approvals.slice(0, 6).map(a => (
        <div key={a.id} style={{ display: 'flex', gap: 10, padding: '7px 0', borderBottom: '1px solid var(--surface-4)', alignItems: 'center' }}>
          <div style={{ flex: 1, fontSize: 12, color: 'var(--text-1)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {a.title || a.name || `#${a.id}`}
          </div>
          <span style={{ fontSize: 10, color: 'var(--warning)', background: 'color-mix(in srgb, var(--warning) 12%, transparent)', padding: '2px 6px', borderRadius: 4, fontWeight: 700, flexShrink: 0 }}>
            PENDING
          </span>
        </div>
      ))}
    </div>
  )
}

// ── Contracts Widget ──────────────────────────────────────────────────────────
function ContractsWidget() {
  const nav = useNavigate()
  const t = useAppT()
  const { data: contracts = [] } = useQuery({
    queryKey: ['dash-contracts'],
    queryFn: () => api.get('/contracts', { params: { limit: 100 } }).then(r => {
      const d = r.data; return Array.isArray(d) ? d : (d?.items ?? [])
    }).catch(() => []),
    staleTime: 120000,
  })

  const active = contracts.filter(c => c.status === 'active').length
  const expiringSoon = contracts.filter(c => {
    if (!c.end_date) return false
    const daysLeft = (new Date(c.end_date) - new Date()) / 86400000
    return daysLeft > 0 && daysLeft <= 30
  }).length

  return (
    <div style={{ ...panel, padding: '20px 22px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div style={{ fontSize: 14, fontWeight: 700 }}>📝 {t('dashboard.widget_contracts')}</div>
        <button onClick={() => nav('/contracts')} style={{ fontSize: 11, color: 'var(--accent)', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit' }}>{t('dashboard.see_all_m')}</button>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <div style={{ textAlign: 'center', padding: '14px 8px', background: 'var(--surface-3)', borderRadius: 10 }}>
          <div style={{ fontSize: 28, fontWeight: 800, color: 'var(--success)', fontFamily: 'var(--font-mono)' }}>{active}</div>
          <div style={{ fontSize: 11, color: 'var(--text-2)', marginTop: 4 }}>{t('dashboard.contracts_active')}</div>
        </div>
        <div style={{ textAlign: 'center', padding: '14px 8px', background: 'var(--surface-3)', borderRadius: 10 }}>
          <div style={{ fontSize: 28, fontWeight: 800, color: expiringSoon > 0 ? 'var(--warning)' : 'var(--text-2)', fontFamily: 'var(--font-mono)' }}>{expiringSoon}</div>
          <div style={{ fontSize: 11, color: 'var(--text-2)', marginTop: 4 }}>{t('dashboard.contracts_expiring')}</div>
        </div>
      </div>
    </div>
  )
}

// ── Widget registry ───────────────────────────────────────────────────────────
const ALL_WIDGETS = [
  { id: 'kpis',      icon: '◈', defaultHidden: false },
  { id: 'tasks',     icon: '▦', defaultHidden: false },
  { id: 'alerts',    icon: '🔔', defaultHidden: false },
  { id: 'health',    icon: '⬡', defaultHidden: false },
  { id: 'overdue',   icon: '⚠', defaultHidden: false },
  { id: 'team',      icon: '👥', defaultHidden: false },
  { id: 'pipeline',  icon: '🎪', defaultHidden: false },
  { id: 'clients',   icon: '🏢', defaultHidden: false },
  { id: 'hours',     icon: '⏱', defaultHidden: false },
  { id: 'activity',  icon: '⚡', defaultHidden: false },
  { id: 'docs',      icon: '📎', defaultHidden: false },
  { id: 'burndown',  icon: '📉', defaultHidden: true },
  { id: 'velocity',  icon: '🚀', defaultHidden: true },
  { id: 'expenses',  icon: '💰', defaultHidden: true },
  { id: 'risks',     icon: '⚠️', defaultHidden: true },
  { id: 'approvals', icon: '✅', defaultHidden: true },
  { id: 'contracts', icon: '📝', defaultHidden: true },
]

// Default grid positions (12-column grid, rowHeight=60)
const DEFAULT_POSITIONS = {
  kpis:      { i: 'kpis',      x: 0, y: 0,  w: 12, h: 3,  minW: 6, minH: 2 },
  tasks:     { i: 'tasks',     x: 0, y: 3,  w: 4,  h: 7,  minW: 3, minH: 4 },
  alerts:    { i: 'alerts',    x: 4, y: 3,  w: 4,  h: 7,  minW: 3, minH: 4 },
  health:    { i: 'health',    x: 8, y: 3,  w: 4,  h: 7,  minW: 3, minH: 4 },
  overdue:   { i: 'overdue',   x: 0, y: 10, w: 4,  h: 7,  minW: 3, minH: 4 },
  team:      { i: 'team',      x: 4, y: 10, w: 8,  h: 7,  minW: 4, minH: 4 },
  pipeline:  { i: 'pipeline',  x: 0, y: 17, w: 6,  h: 7,  minW: 3, minH: 4 },
  clients:   { i: 'clients',   x: 6, y: 17, w: 6,  h: 7,  minW: 3, minH: 4 },
  hours:     { i: 'hours',     x: 0, y: 24, w: 6,  h: 6,  minW: 4, minH: 4 },
  activity:  { i: 'activity',  x: 6, y: 24, w: 6,  h: 6,  minW: 4, minH: 4 },
  docs:      { i: 'docs',      x: 0, y: 30, w: 6,  h: 6,  minW: 4, minH: 4 },
  burndown:  { i: 'burndown',  x: 6, y: 30, w: 6,  h: 6,  minW: 3, minH: 4 },
  velocity:  { i: 'velocity',  x: 0, y: 36, w: 6,  h: 6,  minW: 4, minH: 4 },
  expenses:  { i: 'expenses',  x: 6, y: 36, w: 6,  h: 6,  minW: 3, minH: 4 },
  risks:     { i: 'risks',     x: 0, y: 42, w: 4,  h: 7,  minW: 3, minH: 4 },
  approvals: { i: 'approvals', x: 4, y: 42, w: 4,  h: 7,  minW: 3, minH: 4 },
  contracts: { i: 'contracts', x: 8, y: 42, w: 4,  h: 6,  minW: 3, minH: 4 },
}

const DASHBOARD_STORAGE_KEY = 'clarive-dashboard-v2'

function buildDefaultConfig() {
  return {
    visible: ALL_WIDGETS.filter(w => !w.defaultHidden).map(w => w.id),
    layout: ALL_WIDGETS.map(w => DEFAULT_POSITIONS[w.id]),
  }
}

function normalizeConfig(cfg) {
  const defaults = buildDefaultConfig()
  if (!cfg || !Array.isArray(cfg.visible) || !Array.isArray(cfg.layout)) return defaults

  const validIds = new Set(ALL_WIDGETS.map(w => w.id))
  const visible = cfg.visible.filter(id => validIds.has(id))

  const layoutMap = Object.fromEntries(defaults.layout.map(l => [l.i, l]))
  cfg.layout.forEach((l) => {
    if (!l || !validIds.has(l.i)) return
    layoutMap[l.i] = { ...layoutMap[l.i], ...l }
  })

  return {
    visible,
    layout: Object.values(layoutMap),
  }
}

function isValidConfig(cfg) {
  if (!cfg || !Array.isArray(cfg.visible) || !Array.isArray(cfg.layout)) return false
  const validIds = new Set(ALL_WIDGETS.map(w => w.id))
  return cfg.layout.some(l => l && validIds.has(l.i))
}

function migrateOldConfig(old) {
  if (!old || !Array.isArray(old.visible)) return null
  if (Array.isArray(old.order) && !Array.isArray(old.layout)) {
    return { visible: old.visible, layout: ALL_WIDGETS.map(w => DEFAULT_POSITIONS[w.id]) }
  }
  return null
}

function useDashboardConfig() {
  const [config, setConfig] = React.useState(null)

  const saveLocal = React.useCallback((cfg) => {
    try { localStorage.setItem(DASHBOARD_STORAGE_KEY, JSON.stringify(cfg)) } catch {}
  }, [])

  const saveBackend = React.useCallback((cfg) => {
    api.patch('/users/me/preferences', { dashboard_widgets: cfg }).catch(() => {})
  }, [])

  React.useEffect(() => {
    let mounted = true
    const defaultConfig = buildDefaultConfig()

    const readLocal = () => {
      try {
        const raw = localStorage.getItem(DASHBOARD_STORAGE_KEY)
        if (!raw) return null
        const parsed = JSON.parse(raw)
        if (isValidConfig(parsed)) return parsed
        return migrateOldConfig(parsed)
      } catch { return null }
    }

    const loadConfig = async () => {
      const localConfig = readLocal()
      try {
        const prefs = await api.get('/users/me/preferences').then(r => r.data)
        const remote = prefs?.dashboard_widgets
        if (isValidConfig(remote)) {
          if (mounted) setConfig(remote)
          saveLocal(remote)
          return
        }
      } catch {}
      if (localConfig) { if (mounted) setConfig(normalizeConfig(localConfig)); return }
      if (mounted) setConfig(defaultConfig)
    }

    loadConfig()
    return () => { mounted = false }
  }, [saveLocal, saveBackend])

  const resolvedConfig = normalizeConfig(config || buildDefaultConfig())

  const toggle = React.useCallback((id) => {
    setConfig(prev => {
      const cur = prev || buildDefaultConfig()
      const visible = cur.visible.includes(id)
        ? cur.visible.filter(x => x !== id)
        : [...cur.visible, id]
      const next = { ...cur, visible }
      saveLocal(next); saveBackend(next)
      return next
    })
  }, [saveLocal, saveBackend])

  const updateLayout = React.useCallback((newLayout) => {
    setConfig(prev => {
      const cur = prev || buildDefaultConfig()
      const layoutMap = Object.fromEntries(cur.layout.map(l => [l.i, l]))
      newLayout.forEach(item => {
        layoutMap[item.i] = { ...layoutMap[item.i], ...item }
      })
      const next = { ...cur, layout: Object.values(layoutMap) }
      saveLocal(next); saveBackend(next)
      return next
    })
  }, [saveLocal, saveBackend])

  const reset = React.useCallback(() => {
    const d = buildDefaultConfig()
    setConfig(d); saveLocal(d); saveBackend(d)
  }, [saveLocal, saveBackend])

  const visibleLayout = resolvedConfig.layout
    .filter(l => resolvedConfig.visible.includes(l.i))
    .map(l => ({ ...DEFAULT_POSITIONS[l.i], ...l }))

  return { config: resolvedConfig, visibleLayout, toggle, updateLayout, reset }
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function DashboardPage() {
  const t = useAppT()
  const tt = (key, fallback) => {
    const translated = t(key)
    return translated === key.split('.').pop() ? fallback : translated
  }
  const { lang } = useAppLang()
  const { data: kpis, isLoading: kpisLoading } = useQuery({
    queryKey: ['dash-kpis'],
    queryFn: () => dashboardApi.kpis().then(r => r.data).catch(() => ({})),
    staleTime: 30000,
    refetchInterval: 60000,
  })
  const { config, visibleLayout, toggle, updateLayout, reset } = useDashboardConfig()
  const [configOpen, setConfigOpen] = useState(false)
  const containerRef = useRef(null)
  // Initialize with a positive value so the grid renders on first mount without
  // waiting for the ResizeObserver. The actual container width is measured and
  // corrected synchronously by useLayoutEffect below.
  const [gridWidth, setGridWidth] = useState(() =>
    typeof window !== 'undefined' ? Math.max(window.innerWidth - 280, 400) : 800
  )

  useLayoutEffect(() => {
    const el = containerRef.current
    if (!el) return
    const update = () => {
      const width = el.getBoundingClientRect().width
      if (width > 0) setGridWidth(width)
    }
    update()
    const raf1 = requestAnimationFrame(update)
    // Fire again after the sidebar's 200ms CSS transition so the container
    // width is stable before react-grid-layout computes column positions.
    const tid = setTimeout(update, 260)
    const ro = new ResizeObserver(update)
    ro.observe(el)
    window.addEventListener('resize', update)
    return () => {
      ro.disconnect()
      window.removeEventListener('resize', update)
      cancelAnimationFrame(raf1)
      clearTimeout(tid)
    }
  }, [])

  const effectiveGridWidth = gridWidth

  const WIDGET_MAP = {
    kpis:      <div style={{ padding: '12px 16px 8px', height: '100%', boxSizing: 'border-box' }}>{kpisLoading ? <SkeletonDashboard /> : <KpiRow kpis={kpis} />}</div>,
    tasks:     <MyPendingWidget />,
    alerts:    <AlertsWidget />,
    health:    <ProjectsHealthWidget />,
    overdue:   <OverdueTasksWidget />,
    team:      <TeamLoadWidget />,
    pipeline:  <PipelineWidget />,
    clients:   <TopClientsWidget />,
    hours:     <HoursChartWidget />,
    activity:  <RecentActivityWidget />,
    docs:      <RecentDocumentsWidget />,
    burndown:  <BurndownWidget />,
    velocity:  <VelocityWidget />,
    expenses:  <ExpensesWidget />,
    risks:     <RisksWidget />,
    approvals: <ApprovalsWidget />,
    contracts: <ContractsWidget />,
  }

  return (
    <div style={{ padding: 32 }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24, gap: 10, flexWrap: 'wrap' }}>
        <div>
          <div style={{ fontSize: 22, fontWeight: 800, marginBottom: 4 }}>Dashboard</div>
          <div style={{ fontSize: 13, color: 'var(--text-2)' }}>
            {t('dashboard.overview')} · {new Date().toLocaleDateString(LANG_LOCALE[lang] || 'es-ES', { weekday: 'long', day: 'numeric', month: 'long' })}
          </div>
        </div>
        <button
          onClick={() => setConfigOpen(o => !o)}
          data-tour="dashboard-customize"
          style={{
            background: configOpen ? 'var(--accent-muted)' : 'var(--surface-2)',
            border: `1px solid ${configOpen ? 'rgba(79,142,247,0.4)' : 'var(--surface-4)'}`,
            borderRadius: 9, color: configOpen ? 'var(--accent)' : 'var(--text-2)', padding: '8px 16px',
            cursor: 'pointer', fontSize: 12, fontFamily: 'inherit', display: 'flex', gap: 6, alignItems: 'center',
            transition: 'all 0.15s',
          }}
        >
          ⊞ {tt('dashboard.customize_dashboard', 'Personalizar dashboard')}
        </button>
      </div>

      {/* Widget catalog panel */}
      {configOpen && (
        <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, padding: '20px 24px', marginBottom: 24 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
            <div>
              <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-1)' }}>{t('dashboard.widgets_title')}</div>
              <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 2 }}>{t('dashboard.widgets_hint_drag')}</div>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                onClick={reset}
                style={{ fontSize: 11, color: 'var(--text-2)', background: 'none', border: '1px solid var(--surface-4)', borderRadius: 6, padding: '5px 10px', cursor: 'pointer', fontFamily: 'inherit' }}
              >
                {t('dashboard.reset')}
              </button>
              <button
                onClick={() => setConfigOpen(false)}
                style={{ fontSize: 18, lineHeight: 1, color: 'var(--text-3)', background: 'none', border: 'none', cursor: 'pointer', padding: '2px 6px' }}
              >
                ×
              </button>
            </div>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 8 }}>
            {ALL_WIDGETS.map(w => {
              const visible = config.visible.includes(w.id)
              return (
                <div
                  key={w.id}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px',
                    background: 'var(--surface-3)', borderRadius: 8,
                    border: `1px solid ${visible ? 'rgba(79,142,247,0.4)' : 'var(--surface-4)'}`,
                    opacity: visible ? 1 : 0.55, transition: 'all 0.15s',
                  }}
                >
                  <span style={{ fontSize: 14, flexShrink: 0 }}>{w.icon}</span>
                  <span style={{ flex: 1, fontSize: 12, color: visible ? 'var(--text-1)' : 'var(--text-3)', fontWeight: 500 }}>
                    {t('dashboard.widget_' + w.id)}
                  </span>
                  <button
                    onClick={() => toggle(w.id)}
                    title={visible ? t('dashboard.hide') : t('dashboard.show')}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', color: visible ? 'var(--accent)' : 'var(--text-3)', fontSize: 13, padding: '2px', flexShrink: 0 }}
                  >
                    {visible ? '👁' : '○'}
                  </button>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Grid */}
      <div ref={containerRef}>
        {effectiveGridWidth > 0 && config.visible.length > 0 && (
          <GridLayout
            layout={visibleLayout}
            cols={12}
            rowHeight={60}
            width={effectiveGridWidth}
            onLayoutChange={updateLayout}
            isDraggable
            isResizable
            draggableHandle=".dash-drag-handle"
            margin={[14, 14]}
            containerPadding={[0, 0]}
            resizeHandles={['se', 's', 'e']}
          >
            {config.visible.map(id => {
              const w = ALL_WIDGETS.find(x => x.id === id)
              return (
                <div
                  key={id}
                  style={{
                    display: 'flex', flexDirection: 'column',
                    background: 'var(--surface-2)',
                    border: '1px solid var(--surface-4)',
                    borderRadius: 12, overflow: 'hidden',
                  }}
                >
                  {/* Drag handle bar */}
                  <div
                    className="dash-drag-handle"
                    style={{
                      height: 28, flexShrink: 0,
                      display: 'flex', alignItems: 'center', gap: 7, padding: '0 12px',
                      background: 'var(--surface-3)', borderBottom: '1px solid var(--surface-4)',
                      cursor: 'grab', userSelect: 'none',
                    }}
                  >
                    <span style={{ color: 'var(--text-3)', fontSize: 11, letterSpacing: 1 }}>⠿⠿</span>
                    <span style={{ fontSize: 13 }}>{w?.icon}</span>
                    <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-2)' }}>{t('dashboard.widget_' + id)}</span>
                  </div>
                  {/* Widget content */}
                  <div style={{ flex: 1, minHeight: 0, overflow: 'auto' }}>
                    {WIDGET_MAP[id]}
                  </div>
                </div>
              )
            })}
          </GridLayout>
        )}
        {config.visible.length === 0 && (
          <div style={{
            textAlign: 'center',
            padding: '52px 24px',
            border: '1px dashed var(--surface-4)',
            borderRadius: 12,
            background: 'var(--surface-2)',
          }}>
            <div style={{ fontSize: 34, marginBottom: 10 }}>⊞</div>
            <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 6 }}>
              {tt('dashboard.empty_title', 'No hay widgets visibles')}
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-2)', marginBottom: 14 }}>
              {tt('dashboard.empty_desc', 'Has ocultado todos los widgets. Puedes restaurar la configuración por defecto.')}
            </div>
            <button
              onClick={reset}
              style={{
                background: 'var(--accent-muted)',
                border: '1px solid rgba(79,142,247,0.35)',
                borderRadius: 8,
                color: 'var(--accent)',
                padding: '8px 12px',
                cursor: 'pointer',
                fontSize: 12,
                fontFamily: 'inherit',
                fontWeight: 600,
              }}
            >
              {tt('dashboard.restore_default_widgets', 'Restaurar widgets por defecto')}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
