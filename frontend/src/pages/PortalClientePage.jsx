/**
 * PortalClientePage – The external-facing client portal.
 * Accessed at /portal — uses separate client auth (ClientUser, not User).
 * This is what the CLIENT sees, not the internal team.
 *
 * Shared context, auth, API client, and styles live in portal-client/portalClientContext.js
 */
import { CHART } from '../constants/theme'
import { extractErr } from '../utils/helpers'
import React from 'react'
import { useState, useEffect } from 'react'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAppT } from '../i18n/AppLangContext'
import { BadgeWithTooltip } from '../components/ui/BadgeWithTooltip'
import { IconCR } from '../components/ui/FRCRIcons'
import {
  CLIENT_API, LangContext, useLang, useClientAuth,
  ClientAuthProvider, S, Badge, LoginScreen,
} from './portal-client/portalClientContext'
import { PortalSupportDesk } from './portal-client/PortalSupportDesk'

// ── Dashboard ─────────────────────────────────────────────────────────────────
function PortalDashboard() {
  const [selectedProjectId, setSelectedProjectId] = useState(
    () => localStorage.getItem('portal_selected_project') || null
  )
  const t = useLang()
  const { client } = useClientAuth()
  const params = selectedProjectId ? { project_id: selectedProjectId } : {}
  const { data, isLoading } = useQuery({
    queryKey: ['portal-dashboard', selectedProjectId],
    queryFn: () => CLIENT_API.get('/portal/dashboard', { params }).then(r => r.data),
  })

  if (isLoading) return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 300, color: 'var(--text-2)' }}>
      <div style={{ textAlign: 'center' }}>
        <div style={{ fontSize: 32, marginBottom: 12 }}>◈</div>
            {t('dashboard_loading')}
      </div>
    </div>
  )
  if (!data) return null

  // Multi-project: show project selector
  if (data.needs_project_selection) {
    return (
      <div>
        <div style={{ marginBottom: 28 }}>
          <div style={{ fontSize: 22, fontWeight: 800, marginBottom: 4 }}>
            {t('dashboard_welcome').replace('{{name}}', client?.full_name?.split(' ')[0] || '')}
          </div>
          <div style={{ fontSize: 14, color: 'var(--text-2)' }}>
              {t('dashboard_choose_project_cta').replace('{{count}}', String(data.projects?.length || 0))}
          </div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 16 }}>
          {(data.projects || []).map(p => (
            <div key={p.id} role="button" tabIndex={0} onClick={() => {
                setSelectedProjectId(p.id)
                localStorage.setItem('portal_selected_project', p.id)
              }}
              onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSelectedProjectId(p.id); localStorage.setItem('portal_selected_project', p.id) } }}
              aria-label={`Abrir proyecto ${p.name}`}
              style={{ background: 'var(--surface-1)', border: '1px solid #1a2640', borderRadius: 14,
                padding: '20px 22px', cursor: 'pointer', transition: 'border-color .15s',
                ':hover': { borderColor: 'var(--accent)' } }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--accent)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '.06em' }}>{p.code}</div>
              <div style={{ fontSize: 17, fontWeight: 700, marginBottom: 8 }}>{p.name}</div>
              <span style={{ fontSize: 11, fontWeight: 700, padding: '2px 9px', borderRadius: 20,
                background: p.status === 'active' ? '#22c55e20' : '#94a3b820',
                color: p.status === 'active' ? '#22c55e' : '#94a3b8',
                border: `1px solid ${p.status === 'active' ? '#22c55e40' : '#94a3b840'}`,
                textTransform: 'uppercase' }}>{p.status}</span>
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (!data.project) return (
    <div style={{ display:'flex', flexDirection:'column', alignItems:'center', justifyContent:'center',
      height:300, textAlign:'center', gap:12 }}>
      <div style={{ fontSize:40 }}>🏗</div>
        <div style={{ fontSize:17, fontWeight:700, color:'var(--text-1)' }}>{t('dashboard_not_configured')}</div>
      <div style={{ fontSize:13, color:'var(--text-2)', maxWidth:380, lineHeight:1.6 }}>
          {data.message || t('dashboard_not_configured_hint')}
      </div>
    </div>
  )

  const { project, kpis, next_milestone, recent_activity } = data
  const budgetPct = kpis?.budget_total > 0 ? Math.round((kpis.budget_spent / kpis.budget_total) * 100) : 0

  return (
    <div>
      {/* Saludo */}
      <div style={{ marginBottom: 28, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <div style={{ fontSize: 22, fontWeight: 800, marginBottom: 4 }}>
            {t('dashboard_welcome').replace('{{name}}', client?.full_name?.split(' ')[0] || '')}
          </div>
          <div style={{ fontSize: 14, color: 'var(--text-2)' }}>
            {project?.name || t('portal')} · {new Date().toLocaleDateString('es-ES', { weekday: 'long', day: 'numeric', month: 'long' })}
          </div>
        </div>
        {(client?.projects?.length > 1 || client?.project_ids?.length > 1) && (
          <button onClick={() => { setSelectedProjectId(null); localStorage.removeItem('portal_selected_project') }}
            style={{ background: 'transparent', border: '1px solid #1a2640', borderRadius: 8,
              padding: '7px 14px', color: 'var(--text-2)', fontSize: 12, cursor: 'pointer',
              fontFamily: 'inherit', fontWeight: 600 }}>
            ⇆ {t('dashboard_change_project')}
          </button>
        )}
      </div>

      {/* KPIs del proyecto */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 14, marginBottom: 28 }}>
        {[
          { icon: '📦', label: t('kpi_deliverables'), value: `${kpis?.deliverables_approved || 0}/${kpis?.deliverables_total || 0}`, sub: t('kpi_approved'), color: 'var(--success)' },
          { icon: '🧪', label: t('kpi_uat'), value: `${kpis?.uat_passed || 0}/${kpis?.uat_total || 0}`, sub: t('kpi_passed'), color: 'var(--accent)' },
          { icon: '💡', label: t('kpi_requests'), value: kpis?.feature_requests_open || 0, sub: t('kpi_pending'), color: 'var(--warning)' },
          { icon: '🎫', label: t('kpi_tickets'), value: kpis?.tickets_open || 0, sub: t('kpi_open'), color: 'var(--purple)' },
          { icon: '💬', label: t('kpi_messages'), value: kpis?.unread_messages || 0, sub: t('kpi_unread'), color: 'var(--warning)' },
        ].map(k => (
          <div key={k.label} style={{
            background: 'var(--surface-1)', border: `1px solid ${k.color}20`,
            borderRadius: 12, padding: '16px 18px',
          }}>
            <div style={{ fontSize: 22, marginBottom: 8 }}>{k.icon}</div>
            <div style={{ fontSize: 22, fontWeight: 800, color: k.color, marginBottom: 2, fontFamily: "'Space Mono', monospace" }}>{k.value}</div>
            <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-1)' }}>{k.label}</div>
            <div style={{ fontSize: 11, color: 'var(--text-2)' }}>{k.sub}</div>
          </div>
        ))}
      </div>

      {/* Estado del proyecto + Próximo hito */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 24 }}>
        {/* Presupuesto */}
        <div style={{ background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 12, padding: '20px 22px' }}>
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 16 }}>{t('dashboard_budget_section')}</div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
            <span style={{ fontSize: 12, color: 'var(--text-2)' }}>{t('stats_budget_consumed')}</span>
            <span style={{ fontSize: 13, fontWeight: 700, color: budgetPct > 90 ? 'var(--danger)' : budgetPct > 70 ? 'var(--warning)' : 'var(--success)' }}>
              {budgetPct}%
            </span>
          </div>
          <div style={{ height: 8, background: 'var(--surface-4)', borderRadius: 4, overflow: 'hidden', marginBottom: 12 }}>
            <div style={{
              width: `${Math.min(budgetPct, 100)}%`, height: '100%', borderRadius: 4,
              background: budgetPct > 90 ? 'var(--danger)' : budgetPct > 70 ? 'var(--warning)' : 'var(--success)',
              transition: 'width 0.5s ease',
            }} />
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--text-2)' }}>
            <span>{t('dashboard_budget_spent')}: <strong style={{ color: 'var(--text-1)' }}>{kpis?.budget_spent?.toLocaleString('es-ES', { style: 'currency', currency: 'EUR' }) || '—'}</strong></span>
            <span>{t('dashboard_budget_total')}: <strong style={{ color: 'var(--text-1)' }}>{kpis?.budget_total?.toLocaleString('es-ES', { style: 'currency', currency: 'EUR' }) || '—'}</strong></span>
          </div>
        </div>

        {/* Próximo hito */}
        <div style={{ background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 12, padding: '20px 22px' }}>
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 16 }}>{t('dashboard_next_milestone')}</div>
          {next_milestone ? (
            <>
              <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 6 }}>{next_milestone.title}</div>
              <div style={{ fontSize: 12, color: 'var(--text-2)', marginBottom: 12 }}>{next_milestone.due_date}</div>
              <div style={{ fontSize: 11, padding: '4px 10px', borderRadius: 20, display: 'inline-flex',
                background: 'var(--accent-muted)', color: 'var(--accent)', fontWeight: 700 }}>
                {next_milestone.days_remaining > 0 ? t('dashboard_days_remaining').replace('{{n}}', next_milestone.days_remaining) : t('dashboard_today')}
              </div>
            </>
          ) : (
            <div style={{ fontSize: 12, color: 'var(--text-2)', padding: '20px 0', textAlign: 'center' }}>
              {t('dashboard_no_milestone')}
            </div>
          )}
        </div>
      </div>

      {/* Actividad reciente */}
      {recent_activity?.length > 0 && (
        <div style={{ background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 12, padding: '20px 22px' }}>
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 16 }}>{t('dashboard_activity')}</div>
          {recent_activity.slice(0, 5).map((item, i) => (
            <div key={i} style={{ display: 'flex', gap: 12, padding: '8px 0',
              borderBottom: i < 4 ? '1px solid var(--surface-4)' : 'none', alignItems: 'flex-start' }}>
              <span style={{ fontSize: 16, flexShrink: 0 }}>
                {item.type === 'deliverable' ? '📦' : item.type === 'message' ? '💬' : item.type === 'uat' ? '🧪' : '●'}
              </span>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 12, color: 'var(--text-1)' }}>{item.description}</div>
                <div style={{ fontSize: 10, color: 'var(--text-3)', marginTop: 2 }}>{item.date?.slice(0, 16)?.replace('T', ' ')}</div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}


function PortalUAT() {
  const _t = useLang()
  const qc = useQueryClient()
  const _toast = useToast()
  const issueIdPrefix = useId()
  const [selected, setSelected] = useState(null)
  const [testResults, setTestResults] = useState({})
  const [globalNotes, setGlobalNotes] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [reportingIssue, setReportingIssue] = useState(null)
  const [issueForm, setIssueForm] = useState({ title: '', description: '', severity: 'medium', steps_to_reproduce: '' })

  const { data: sessions = [], isLoading } = useQuery({ queryKey: ['portal-uat'], queryFn: () => CLIENT_API.get('/portal/uat').then(r => r.data) })

  const submitResult = async (sessionId, result) => {
    setSubmitting(true)
    try {
      const testCases = selected?.test_cases?.map(tc => ({ id: tc.id, status: testResults[tc.id] || 'pending', actual_result: '', notes: '' })) || []
      await CLIENT_API.post(`/portal/uat/${sessionId}/submit-result`, { result, notes: globalNotes, test_cases: testCases })
      qc.invalidateQueries(['portal-uat'])
      setSelected(null)
    } finally { setSubmitting(false) }
  }

  const submitIssue = async () => {
    await CLIENT_API.post(`/portal/uat/${selected.id}/issues`, issueForm)
    qc.invalidateQueries(['portal-uat'])
    setReportingIssue(false)
    setIssueForm({ title: '', description: '', severity: 'medium', steps_to_reproduce: '' })
  }

  if (isLoading) return <div style={{ color: 'var(--text-2)', textAlign: 'center', padding: 40 }}>{_t('loading')}</div>

  if (selected) {
    const _allCasesMarked = selected.test_cases.length === 0 || selected.test_cases.every(tc => testResults[tc.id])
    const hasFailure = Object.values(testResults).includes('failed')

    return (
      <div>
        <button onClick={() => setSelected(null)} style={{ ...S.btnSec, marginBottom: 20 }}>← Volver</button>
        <div style={{ marginBottom: 20 }}>
          <h3 style={{ fontSize: 18, fontWeight: 700, margin: '0 0 8px' }}>{selected.title}</h3>
          {selected.description && <p style={{ color: 'var(--text-2)', margin: '0 0 8px' }}>{selected.description}</p>}
          {selected.test_environment && (
            <a href={selected.test_environment} target="_blank" rel="noopener noreferrer"
              style={{ display: 'inline-flex', alignItems: 'center', gap: 6, background: 'var(--accent-muted)', border: '1px solid #00d4ff30', borderRadius: 8, padding: '8px 14px', color: 'var(--accent)', textDecoration: 'none', fontSize: 13, fontWeight: 600 }}>
              🔗 {_t('uat_run_case')}
            </a>
          )}
          {selected.test_credentials && <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-2)', background: 'var(--surface-4)', borderRadius: 8, padding: '6px 12px' }}>🔑 {selected.test_credentials}</div>}
        </div>

        {selected.test_cases.length > 0 && (
          <div style={{ marginBottom: 20 }}>
            <h4 style={{ fontSize: 14, fontWeight: 700, margin: '0 0 12px', color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{_t('uat_cases')}</h4>
            {selected.test_cases.map(tc => (
              <div key={tc.id} style={{ ...S.card, marginBottom: 10 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 4 }}>{tc.title}</div>
                    {tc.steps && <div style={{ fontSize: 13, color: 'var(--text-2)', marginBottom: 4 }}>📋 {tc.steps}</div>}
                    {tc.expected_result && <div style={{ fontSize: 13, color: 'var(--success)' }}>✓ {tc.expected_result}</div>}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  {[['passed', `✓ ${_t('uat_pass')}`, 'var(--success)'], ['failed', `✗ ${_t('uat_fail')}`, 'var(--danger)']].map(([val, label, color]) => (
                    <button key={val} onClick={() => setTestResults(r => ({ ...r, [tc.id]: val }))}
                      style={{ flex: 1, padding: '10px', borderRadius: 8, border: `2px solid ${testResults[tc.id] === val ? color : 'var(--surface-4)'}`, background: testResults[tc.id] === val ? color + '20' : 'transparent', color: testResults[tc.id] === val ? color : 'var(--text-2)', fontSize: 13, fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit', transition: 'all 0.15s' }}>
                      {label}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}

        {selected.issues.length > 0 && (
          <div style={{ marginBottom: 20 }}>
            <h4 style={{ fontSize: 14, fontWeight: 700, margin: '0 0 12px', color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{_t('uat_issue')}</h4>
            {selected.issues.map(issue => (
              <div key={issue.id} style={{ ...S.card, marginBottom: 8, border: `1px solid ${issue.status === 'open' ? 'var(--danger-border)' : 'var(--surface-4)'}` }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                  <span style={{ fontSize: 13, fontWeight: 600 }}>{issue.title}</span>
                  <span style={{ fontSize: 11, color: issue.status === 'fixed' ? 'var(--success)' : 'var(--danger)' }}>{issue.status === 'fixed' ? `✓ ${_t('roadmap_completed')}` : `⚠ ${_t('ticket_status_new')}`}</span>
                </div>
                <p style={{ fontSize: 12, color: 'var(--text-2)', margin: 0 }}>{issue.description}</p>
              </div>
            ))}
          </div>
        )}

        <div style={{ ...S.card, marginBottom: 20 }}>
          <label htmlFor={`${issueIdPrefix}-global-notes`} style={S.label}>{_t('uat_notes')}</label>
          <textarea id={`${issueIdPrefix}-global-notes`} value={globalNotes} onChange={e => setGlobalNotes(e.target.value)} rows={3} placeholder={_t('uat_notes')}
            style={{ ...S.input, resize: 'vertical' }} />
        </div>

        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <button onClick={() => setReportingIssue(true)} style={{ ...S.btnSec }}>🐛 {_t('uat_issue')}</button>
          {selected.status !== 'passed' && selected.status !== 'failed' && (
            <>
              <button onClick={() => submitResult(selected.id, 'failed')} disabled={submitting}
                style={{ ...S.btnSec, borderColor: 'var(--danger-border)', color: 'var(--danger)' }}>✗ {_t('uat_fail')}</button>
              <button onClick={() => submitResult(selected.id, hasFailure ? 'conditional' : 'passed')} disabled={submitting}
                style={{ ...S.btn }}>
                {hasFailure ? `✓ ${_t('uat_pass')}` : `✓ ${_t('uat_pass')}`}
              </button>
            </>
          )}
        </div>

        {reportingIssue && (
          <div role="dialog" aria-modal="true" aria-labelledby={`${issueIdPrefix}-issue-title`} style={{ ...S.card, marginTop: 20, border: '1px solid #ff475740' }}>
            <h4 id={`${issueIdPrefix}-issue-title`} style={{ fontSize: 14, fontWeight: 700, margin: '0 0 14px', color: 'var(--danger)' }}>🐛 {_t('uat_issue')}</h4>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div><label htmlFor={`${issueIdPrefix}-issue-name`} style={S.label}>{_t('uat_issue_title')}</label><input id={`${issueIdPrefix}-issue-name`} value={issueForm.title} onChange={e => setIssueForm(f => ({ ...f, title: e.target.value }))} style={S.input} /></div>
              <div><label htmlFor={`${issueIdPrefix}-issue-desc`} style={S.label}>{_t('uat_issue_desc')}</label><textarea id={`${issueIdPrefix}-issue-desc`} value={issueForm.description} onChange={e => setIssueForm(f => ({ ...f, description: e.target.value }))} rows={3} style={{ ...S.input, resize: 'vertical' }} /></div>
              <div><label htmlFor={`${issueIdPrefix}-issue-severity`} style={S.label}>{_t('uat_issue_severity')}</label>
                <select id={`${issueIdPrefix}-issue-severity`} value={issueForm.severity} onChange={e => setIssueForm(f => ({ ...f, severity: e.target.value }))} style={S.input}>
                  <option value="low">{_t('sev_low')}</option>
                  <option value="medium">{_t('sev_medium')}</option>
                  <option value="high">{_t('sev_high')}</option>
                  <option value="blocker">{_t('sev_critical')}</option>
                </select>
              </div>
              <div><label htmlFor={`${issueIdPrefix}-issue-steps`} style={S.label}>Pasos para reproducir</label><textarea id={`${issueIdPrefix}-issue-steps`} value={issueForm.steps_to_reproduce} onChange={e => setIssueForm(f => ({ ...f, steps_to_reproduce: e.target.value }))} rows={2} style={{ ...S.input, resize: 'vertical' }} /></div>
              <div style={{ display: 'flex', gap: 10 }}>
                <button onClick={() => setReportingIssue(false)} style={S.btnSec}>{_t('uat_cancel')}</button>
                <button onClick={submitIssue} disabled={!issueForm.title || !issueForm.description} style={S.btn}>{_t('uat_submit')}</button>
              </div>
            </div>
          </div>
        )}
      </div>
    )
  }

  return (
    <div>
      <h3 style={{ fontSize: 18, fontWeight: 700, margin: '0 0 20px' }}>{_t('uat_title')}</h3>
      {sessions.length === 0 ? (
        <div style={{ ...S.card, textAlign: 'center', padding: '40px 20px', color: 'var(--text-2)' }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>🧪</div>
          <div style={{ fontSize: 16, fontWeight: 600 }}>{_t('uat_empty')}</div>
          <p style={{ margin: '8px 0 0' }}>{_t('uat_subtitle')}</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {sessions.map(s => {
            const cfg = STATUS_CFG[s.status] || { color: 'var(--text-2)' }
            return (
              <div key={s.id} role="button" tabIndex={0} onClick={() => { setSelected(s); setTestResults({}); setGlobalNotes('') }}
                onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSelected(s); setTestResults({}); setGlobalNotes('') } }}
                aria-label={`Abrir sesión UAT ${s.title}`}
                style={{ ...S.card, cursor: 'pointer', border: `1px solid ${cfg.color}30`, transition: 'all 0.15s' }}
                onMouseEnter={e => e.currentTarget.style.borderColor = cfg.color + '70'}
                onMouseLeave={e => e.currentTarget.style.borderColor = cfg.color + '30'}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 }}>
                  <div>
                    <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 4 }}>{s.title}</div>
                    {s.deadline && <div style={{ fontSize: 12, color: s.overdue ? 'var(--danger)' : 'var(--text-2)' }}>
                      {s.overdue ? '⚠ Vencido: ' : '📅 Plazo: '}{s.deadline}
                    </div>}
                  </div>
                  <Badge status={s.status} />
                </div>
                {s.stats.total > 0 && (
                  <div style={{ fontSize: 12, color: 'var(--text-2)', marginBottom: 8 }}>
                    {s.stats.total} casos · {s.stats.passed} ✓ · {s.stats.failed} ✗
                  </div>
                )}
                {['pending', 'in_progress'].includes(s.status) && (
                  <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6, background: 'var(--accent-muted)', border: '1px solid #00d4ff30', borderRadius: 8, padding: '6px 12px', fontSize: 13, color: 'var(--accent)', fontWeight: 600 }}>
                    → {_t('uat_run_case')}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ── Feature Requests ──────────────────────────────────────────────────────────
function PortalFeatureRequests() {
  const _t = useLang()
  const toast = useToast()
  const qc = useQueryClient()
  const formIdPrefix = useId()
  const { client } = useClientAuth()
  const [showNew, setShowNew] = useState(false)
  const [editingFr, setEditingFr] = useState(null)
  const [form, setForm] = useState({ title: '', description: '', business_justification: '', affected_area: '', priority: 'medium', project_id: '' })
  const [_crDetail] = useState(null)
  const [_deciding, setDeciding] = useState(null)

  const { data: frs = [], isLoading } = useQuery({ queryKey: ['portal-frs-client'], queryFn: () => CLIENT_API.get('/portal/feature-requests').then(r => r.data) })

  const { mutate: createFR } = useMutation({
    mutationFn: (data) => CLIENT_API.post('/portal/feature-requests', data),
    onSuccess: () => { qc.invalidateQueries(['portal-frs-client']); setShowNew(false); setForm({ title: '', description: '', business_justification: '', affected_area: '', priority: 'medium', project_id: '' }) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: updateFR, isPending: updatingFr } = useMutation({
    mutationFn: ({ id, data }) => CLIENT_API.patch(`/portal/feature-requests/${id}`, data),
    onSuccess: () => {
      qc.invalidateQueries(['portal-frs-client'])
      setEditingFr(null)
      setShowNew(false)
      setForm({ title: '', description: '', business_justification: '', affected_area: '', priority: 'medium', project_id: '' })
    },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: withdrawFR, isPending: withdrawingFr } = useMutation({
    mutationFn: ({ id }) => CLIENT_API.post(`/portal/feature-requests/${id}/withdraw`, {}),
    onSuccess: () => qc.invalidateQueries(['portal-frs-client']),
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: decide } = useMutation({
    mutationFn: ({ id, approved, reason }) => CLIENT_API.post(`/portal/feature-requests/${id}/decide`, { approved, reason }),
    onSuccess: () => { qc.invalidateQueries(['portal-frs-client']); setDeciding(null) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const openEdit = (fr) => {
    setEditingFr(fr)
    setShowNew(true)
    setForm({
      title: fr.title || '',
      description: fr.description || '',
      business_justification: fr.business_justification || '',
      affected_area: fr.affected_area || '',
      priority: fr.priority || 'medium',
      project_id: fr.project_id || '',
    })
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <h3 style={{ fontSize: 18, fontWeight: 700, margin: 0 }}>{_t('fr_title')}</h3>
        {client?.can_request_changes && <button onClick={() => setShowNew(true)} style={S.btn}>＋ {_t('fr_new')}</button>}
      </div>

      {isLoading ? null : frs.length === 0 ? (
        <div style={{ ...S.card, textAlign: 'center', padding: '40px 20px', color: 'var(--text-2)' }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>💡</div>
          <div style={{ fontSize: 16, fontWeight: 600 }}>{_t('fr_empty')}</div>
          <p style={{ margin: '8px 0 0' }}>{_t('fr_subtitle')}</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {frs.map(fr => (
            <div key={fr.id} style={{ ...S.card, border: `1px solid ${fr.priority_color + '30'}` }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 4 }}>
                    <span style={{ fontSize: 11, color: 'var(--text-2)', fontFamily: "'Space Mono', monospace" }}>{fr.code}</span>
                    <span style={{ fontSize: 15, fontWeight: 700 }}>{fr.title}</span>
                  </div>
                  <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', fontSize: 11, color: 'var(--text-3)', marginBottom: 8 }}>
                    {fr.project_name && <span>📁 {fr.project_name}</span>}
                    {fr.submitted_at && <span>{_t('created')}: {fr.submitted_at}</span>}
                    {fr.updated_at && <span>{_t('updated')}: {fr.updated_at}</span>}
                  </div>
                  <p style={{ fontSize: 13, color: 'var(--text-2)', margin: '0 0 8px' }}>{fr.description}</p>
                  {fr.pm_response && (
                    <div style={{ background: 'var(--portal-bg)', border: '1px solid #1a2640', borderRadius: 8, padding: '10px 14px', fontSize: 13 }}>
                      <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-2)', marginBottom: 6, textTransform: 'uppercase' }}>{_t('fr_desc')}</div>
                      <p style={{ margin: '0 0 8px' }}>{fr.pm_response}</p>
                      <div style={{ display: 'flex', gap: 16, fontSize: 12 }}>
                        {fr.estimated_cost && <span style={{ color: 'var(--warning)', fontWeight: 700 }}>💶 {fr.estimated_cost.toLocaleString('es-ES')}€</span>}
                        {fr.estimated_hours && <span style={{ color: 'var(--accent)' }}>⏱ {fr.estimated_hours}h</span>}
                        {fr.estimated_delivery_weeks && <span style={{ color: 'var(--text-2)' }}>📅 ~{fr.estimated_delivery_weeks} sem</span>}
                      </div>
                    </div>
                  )}
                  {fr.status === 'estimated' && fr.client_approved === null && (
                    <div style={{ marginTop: 12, display: 'flex', gap: 10 }}>
                      <button onClick={() => decide({ id: fr.id, approved: false })} style={{ ...S.btnSec, borderColor: 'var(--danger-border)', color: 'var(--danger)' }}>✗ {_t('fr_status_rejected')}</button>
                      <button onClick={() => decide({ id: fr.id, approved: true })} style={S.btn}>✓ {_t('fr_approve_budget')}</button>
                    </div>
                  )}
                  {fr.client_approved === true && <div style={{ marginTop: 8, fontSize: 12, color: 'var(--success)' }}>{_t('fr_approved_by_client')} {fr.client_approved_at}</div>}
                  {fr.client_approved === false && <div style={{ marginTop: 8, fontSize: 12, color: 'var(--danger)' }}>✗ {_t('fr_status_rejected')}</div>}
                  {fr.can_edit_by_client && (
                    <div style={{ marginTop: 12, display: 'flex', gap: 10 }}>
                      <button onClick={() => openEdit(fr)} style={S.btnSec}>{_t('fr_edit_btn')}</button>
                      <button onClick={() => withdrawFR({ id: fr.id })} disabled={withdrawingFr} style={{ ...S.btnSec, borderColor: 'var(--danger-border)', color: 'var(--danger)' }}>{_t('fr_withdraw_btn')}</button>
                    </div>
                  )}
                </div>
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4 }}>
                    <Badge status={fr.status} />
                    {fr.cr_status ? (
                      <BadgeWithTooltip
                        label={`CR: ${fr.cr_status_label || fr.cr_status}`}
                        color={fr.cr_status_color || '#7a8aaa'}
                        tooltip={`Estado de la Change Request vinculada.`}
                        icon={<IconCR />}
                      />
                    ) : (
                      <BadgeWithTooltip
                        label={"Sin CR"}
                        color="#7a8aaa"
                        tooltip={"No se ha generado Change Request. Se crea automáticamente al aprobar la FR por el cliente."}
                        icon={<IconCR />}
                      />
                    )}
                  </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {showNew && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.44)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
          <div role="dialog" aria-modal="true" aria-labelledby={`${formIdPrefix}-title`} style={{ ...S.card, width: 560, maxHeight: '90vh', overflowY: 'auto' }}>
            <h3 id={`${formIdPrefix}-title`} style={{ fontSize: 18, fontWeight: 700, margin: '0 0 20px' }}>{editingFr ? _t('fr_edit_modal_title') : _t('fr_new')}</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              {(client?.projects?.length > 1 || client?.project_ids?.length > 1) && (
                <div>
                  <label htmlFor={`${formIdPrefix}-project`} style={S.label}>{_t('fr_project_label')}</label>
                  <select
                    id={`${formIdPrefix}-project`}
                    value={form.project_id}
                    onChange={e => setForm(f => ({ ...f, project_id: e.target.value }))}
                    style={S.input}
                  >
                    <option value="">{_t('fr_select_project')}</option>
                    {(client.projects || []).map(p => (
                      <option key={p.id} value={p.id}>{p.name}</option>
                    ))}
                  </select>
                </div>
              )}
              <div><label htmlFor={`${formIdPrefix}-fr-title`} style={S.label}>{_t('fr_title_label')}</label><input id={`${formIdPrefix}-fr-title`} value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))} style={S.input} placeholder={_t('fr_title_label')} /></div>
              <div><label htmlFor={`${formIdPrefix}-fr-description`} style={S.label}>{_t('fr_desc_label')}</label><textarea id={`${formIdPrefix}-fr-description`} value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} rows={3} style={{ ...S.input, resize: 'vertical' }} placeholder={_t('fr_desc_label')} /></div>
              <div><label htmlFor={`${formIdPrefix}-fr-justification`} style={S.label}>{_t('fr_justify_label')}</label><textarea id={`${formIdPrefix}-fr-justification`} value={form.business_justification} onChange={e => setForm(f => ({ ...f, business_justification: e.target.value }))} rows={2} style={{ ...S.input, resize: 'vertical' }} placeholder={_t('fr_justify_label')} /></div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <div><label htmlFor={`${formIdPrefix}-fr-area`} style={S.label}>{_t('fr_area_label')}</label><input id={`${formIdPrefix}-fr-area`} value={form.affected_area} onChange={e => setForm(f => ({ ...f, affected_area: e.target.value }))} style={S.input} placeholder={_t('fr_area_label')} /></div>
                <div><label htmlFor={`${formIdPrefix}-fr-priority`} style={S.label}>{_t('fr_priority')}</label>
                  <select id={`${formIdPrefix}-fr-priority`} value={form.priority} onChange={e => setForm(f => ({ ...f, priority: e.target.value }))} style={S.input}>
                    <option value="low">{_t('fr_priority_low')}</option>
                    <option value="medium">{_t('fr_priority_medium')}</option>
                    <option value="high">{_t('fr_priority_high')}</option>
                    <option value="critical">{_t('fr_priority_critical')}</option>
                  </select>
                </div>
              </div>
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 8 }}>
                <button onClick={() => { setShowNew(false); setEditingFr(null); setForm({ title: '', description: '', business_justification: '', affected_area: '', priority: 'medium', project_id: '' }) }} style={S.btnSec}>{_t('cancel')}</button>
                <button
                  onClick={() => editingFr ? updateFR({ id: editingFr.id, data: form }) : createFR(form)}
                  disabled={
                    !form.title || !form.description ||
                    ((client?.projects?.length > 1 || client?.project_ids?.length > 1) && !form.project_id)
                  }
                  style={S.btn}
                >{editingFr ? (updatingFr ? _t('profile_saving') : _t('fr_update_submit')) : _t('fr_submit')}</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Messages ──────────────────────────────────────────────────────────────────
function PortalMessages() {
  const t = useLang()
  const toast = useToast()
  const qc = useQueryClient()
  const messageIdPrefix = useId()
  const [reply, setReply] = useState(null)
  const [newMsg, setNewMsg] = useState('')
  const [newSubject, setNewSubject] = useState('')
  const [showNew, setShowNew] = useState(false)

  const { data: messages = [] } = useQuery({
    queryKey: ['portal-messages-client'],
    queryFn: () => CLIENT_API.get('/portal/messages').then(r => r.data),
    refetchInterval: 30000,
  })

  const { mutate: send } = useMutation({
    mutationFn: (data) => CLIENT_API.post('/portal/messages', data),
    onSuccess: () => { qc.invalidateQueries(['portal-messages-client']); setNewMsg(''); setNewSubject(''); setReply(null); setShowNew(false) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <h3 style={{ fontSize: 18, fontWeight: 700, margin: 0 }}>{t('messages_team_title')}</h3>
        <button onClick={() => setShowNew(true)} style={S.btn}>{t('messages_new_btn')}</button>
      </div>
      {messages.length === 0 ? (
        <div style={{ ...S.card, textAlign: 'center', padding: '40px 20px', color: 'var(--text-2)' }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>💬</div>
          <p>{t('messages_empty')}</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {messages.map(thread => (
            <div key={thread.id} style={{ ...S.card, border: `1px solid ${!thread.is_read_by_client && thread.sender_type === 'team' ? 'var(--accent-glow)' : 'var(--surface-4)'}` }}>
              {thread.subject && <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 8 }}>{thread.subject}</div>}
              <div style={{ fontSize: 13, marginBottom: 8 }}>{thread.body}</div>
              <div style={{ fontSize: 11, color: 'var(--text-2)', marginBottom: thread.replies?.length ? 12 : 0 }}>
                {thread.sender_type === 'team' ? '💼' : '👤'} {thread.sender_name} · {thread.created_at}
              </div>
              {thread.replies?.map(r => (
                <div key={r.id} style={{ padding: '10px 14px', background: r.sender_type === 'team' ? 'var(--portal-bg)' : 'var(--portal-surface)', borderRadius: 8, marginBottom: 6 }}>
                  <div style={{ fontSize: 13, marginBottom: 4 }}>{r.body}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-2)' }}>{r.sender_type === 'team' ? '💼' : '👤'} {r.sender_name} · {r.created_at}</div>
                </div>
              ))}
              <button onClick={() => setReply(thread)} style={{ ...S.btnSec, marginTop: 10 }}>{t('messages_reply_btn')}</button>
            </div>
          ))}
        </div>
      )}

      {(showNew || reply) && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.44)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
          <div role="dialog" aria-modal="true" aria-labelledby={`${messageIdPrefix}-dialog-title`} style={{ ...S.card, width: 480 }}>
            <h4 id={`${messageIdPrefix}-dialog-title`} style={{ margin: '0 0 16px', fontSize: 16, fontWeight: 700 }}>{reply ? t('messages_reply_modal_title') : t('messages_new_modal_title')}</h4>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {!reply && <div><label htmlFor={`${messageIdPrefix}-subject`} style={S.label}>{t('messages_subject_label')}</label><input id={`${messageIdPrefix}-subject`} value={newSubject} onChange={e => setNewSubject(e.target.value)} style={S.input} /></div>}
              <label htmlFor={`${messageIdPrefix}-body`} style={S.label}>{reply ? t('messages_reply_btn') : t('msg_send')}</label>
              <textarea id={`${messageIdPrefix}-body`} value={newMsg} onChange={e => setNewMsg(e.target.value)} rows={5} placeholder={t('msg_placeholder')} style={{ ...S.input, resize: 'vertical' }} />
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
                <button onClick={() => { setShowNew(false); setReply(null) }} style={S.btnSec}>{t('cancel')}</button>
                <button onClick={() => send({ body: newMsg, subject: newSubject || undefined, parent_id: reply?.id, thread_id: reply?.thread_id })} disabled={!newMsg} style={S.btn}>{t('msg_send')}</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function PortalInvoices() {
  const t = useLang()
  const toast = useToast()
  const qc = useQueryClient()
  const [reasonByInvoice, setReasonByInvoice] = useState({})

  const { data: invoices = [], isLoading } = useQuery({
    queryKey: ['portal-invoices'],
    queryFn: () => CLIENT_API.get('/portal/invoices').then(r => r.data),
  })

  const { mutate: approveInvoice, isPending } = useMutation({
    mutationFn: ({ invoiceId, approved, reason }) => CLIENT_API.post(`/portal/invoices/${invoiceId}/approve`, { approved, reason }),
    onSuccess: () => {
      qc.invalidateQueries(['portal-invoices'])
      qc.invalidateQueries(['portal-dashboard'])
      toast.success(t('invoices_updated'))
    },
    onError: e => toast.error(extractErr(e, t('invoices_error'))),
  })

  const fmtMoney = (amount, currency = 'EUR') => {
    const value = Number(amount || 0)
    return value.toLocaleString('es-ES', { style: 'currency', currency })
  }

  if (isLoading) return <div style={{ color: 'var(--text-2)', textAlign: 'center', padding: 40 }}>{t('invoices_loading')}</div>

  return (
    <div>
      <div style={{ marginBottom: 20 }}>
        <h2 style={{ fontSize: 22, fontWeight: 800, marginBottom: 4 }}>{t('invoices_title')}</h2>
        <p style={{ color: 'var(--text-2)', fontSize: 14, margin: 0 }}>{t('invoices_subtitle')}</p>
      </div>

      {invoices.length === 0 ? (
        <div style={{ ...S.card, textAlign: 'center', padding: '44px 20px' }}>
          <div style={{ fontSize: 38, marginBottom: 12 }}>🧾</div>
          <div style={{ color: 'var(--text-2)', fontSize: 14 }}>{t('invoices_empty')}</div>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {invoices.map(inv => {
            const statusColor = inv.status === 'paid' ? 'var(--success)' : inv.status === 'overdue' ? 'var(--danger)' : inv.status === 'sent' ? 'var(--warning)' : 'var(--text-2)'
            const reason = reasonByInvoice[inv.id] || ''
            return (
              <div key={inv.id} style={{ ...S.card, border: `1px solid ${statusColor}33` }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', marginBottom: 10 }}>
                  <div>
                    <div style={{ fontSize: 11, color: 'var(--text-2)', fontFamily: "'Space Mono', monospace" }}>#{inv.number || inv.id}</div>
                    <div style={{ fontSize: 16, fontWeight: 700 }}>{inv.client_name || t('invoices_title')}</div>
                    <div style={{ fontSize: 12, color: 'var(--text-2)' }}>{t('invoices_issued')}: {inv.issue_date || '—'} · {t('invoices_due')}: {inv.due_date || '—'}</div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: 20, fontWeight: 800, color: 'var(--text-1)' }}>{fmtMoney(inv.total, inv.currency || 'EUR')}</div>
                    <span style={{ fontSize: 11, fontWeight: 700, color: statusColor, background: `${statusColor}20`, border: `1px solid ${statusColor}40`, borderRadius: 20, padding: '2px 8px', textTransform: 'uppercase' }}>
                      {inv.status}
                    </span>
                  </div>
                </div>

                <div style={{ fontSize: 12, color: 'var(--text-2)', marginBottom: 10 }}>
                  Base: {fmtMoney(inv.subtotal, inv.currency || 'EUR')} · IVA: {fmtMoney(inv.tax_amount, inv.currency || 'EUR')}
                </div>

                <textarea
                  rows={2}
                  value={reason}
                  onChange={(e) => setReasonByInvoice(prev => ({ ...prev, [inv.id]: e.target.value }))}
                  placeholder={t('invoices_comment_placeholder')}
                  style={{ ...S.input, resize: 'vertical', marginBottom: 10 }}
                />

                <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
                  <button
                    onClick={() => approveInvoice({ invoiceId: inv.id, approved: false, reason })}
                    disabled={isPending}
                    style={{ ...S.btnSec, borderColor: 'var(--danger-border)', color: 'var(--danger)' }}
                  >
                    {t('invoices_reject')}
                  </button>
                  <button
                    onClick={() => approveInvoice({ invoiceId: inv.id, approved: true, reason })}
                    disabled={isPending}
                    style={{ ...S.btn, background: 'linear-gradient(135deg, #00c389, #0ea5e9)' }}
                  >
                    {t('invoices_approve')}
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ── Roadmap ───────────────────────────────────────────────────────────────────
function PortalRoadmap() {
  const _t = useLang()
  const { data, isLoading, error } = useQuery({
    queryKey: ['portal-project'],
    queryFn: () => CLIENT_API.get('/portal/project').then(r => r.data).catch(e => {
      if (e?.response?.status === 404) return null
      throw e
    }),
  })

  const milestones   = data?.milestones   || []
  const deliverables = data?.deliverables || []

  if (isLoading) return (
    <div style={{ textAlign: 'center', padding: '60px 0', color: 'var(--text-2)' }}>
      <div style={{ fontSize: 32, marginBottom: 12 }}>🗺️</div>
      {_t('roadmap_loading')}
    </div>
  )

  if (!data || error) return (
    <div style={{ textAlign: 'center', padding: '60px 20px', color: 'var(--text-2)' }}>
      <div style={{ fontSize: 40, marginBottom: 12 }}>🗺️</div>
      <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 6 }}>{_t('roadmap_no_project')}</div>
      <div style={{ fontSize: 13 }}>{_t('roadmap_no_project_hint')}</div>
    </div>
  )

  return (
    <div>
      <h3 style={{ fontSize: 18, fontWeight: 700, margin: '0 0 20px' }}>{_t('roadmap_title')}</h3>

      {milestones.length === 0 && deliverables.length === 0 && (
        <div style={{ textAlign: 'center', padding: '40px 20px', color: 'var(--text-2)', background: 'var(--surface-2)', borderRadius: 12, border: '1px solid var(--surface-4)' }}>
          <div style={{ fontSize: 32, marginBottom: 8 }}>📋</div>
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>{_t('roadmap_no_items')}</div>
          <div style={{ fontSize: 12 }}>{_t('roadmap_no_items_hint')}</div>
        </div>
      )}

      {(milestones.length > 0 || deliverables.length > 0) && (
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
        <div>
          <h4 style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', margin: '0 0 14px' }}>{_t('roadmap_milestones_title')}</h4>
          {milestones.length === 0 ? (
            <div style={{ fontSize: 12, color: 'var(--text-2)', padding: '12px 0' }}>{_t('roadmap_no_milestones')}</div>
          ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {milestones.map((m, i) => (
              <div key={m.id} style={{ display: 'flex', gap: 14, alignItems: 'flex-start' }}>
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                  <div style={{ width: 28, height: 28, borderRadius: '50%', background: m.is_completed ? 'var(--success)' : 'var(--surface-4)', border: `2px solid ${m.is_completed ? 'var(--success)' : 'var(--surface-4)'}`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 12, color: m.is_completed ? 'var(--portal-bg)' : 'var(--text-2)', fontWeight: 700, flexShrink: 0 }}>
                    {m.is_completed ? '✓' : i + 1}
                  </div>
                  {i < milestones.length - 1 && <div style={{ width: 2, height: 24, background: m.is_completed ? 'var(--success-border)' : 'var(--surface-4)', margin: '4px 0' }} />}
                </div>
                <div style={{ paddingTop: 4 }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: m.is_completed ? 'var(--text-2)' : 'var(--text-1)', textDecoration: m.is_completed ? 'line-through' : 'none' }}>{m.name}</div>
                  {m.due_date && <div style={{ fontSize: 11, color: 'var(--text-2)', marginTop: 2 }}>📅 {m.due_date}</div>}
                  {m.billing_pct && <div style={{ fontSize: 11, color: 'var(--warning)' }}>💶 {m.billing_pct}{_t('roadmap_billing_pct')}</div>}
                </div>
              </div>
            ))}
          </div>
          )}
        </div>
        <div>
          <h4 style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', margin: '0 0 14px' }}>{_t('roadmap_deliverables_title')}</h4>
          {deliverables.length === 0 ? (
            <div style={{ fontSize: 12, color: 'var(--text-2)', padding: '12px 0' }}>{_t('roadmap_no_deliverables')}</div>
          ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {deliverables.map(d => (
              <div key={d.id} style={{ ...S.card, padding: '12px 16px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 700 }}>{d.name}</div>
                    {d.format && <div style={{ fontSize: 11, color: 'var(--text-2)' }}>{d.format}</div>}
                    {d.planned_date && <div style={{ fontSize: 11, color: 'var(--text-2)' }}>{_t('updated')}: {d.planned_date}</div>}
                  </div>
                  <Badge status={d.status} />
                </div>
              </div>
            ))}
          </div>
          )}
        </div>
      </div>
      )}
    </div>
  )
}

// ── Documents section ─────────────────────────────────────────────────────────
function PortalDocuments() {
  const t = useLang()
  const toast = useToast()
  const qc = useQueryClient()
  const { data: docs = [] } = useQuery({ queryKey: ['portal-docs-client'], queryFn: () => CLIENT_API.get('/portal/documents').then(r => r.data) })
  const [signModal, setSignModal] = useState(null)   // { id, title }
  const [signJobTitle, setSignJobTitle] = useState('')
  const [signedPdfB64, setSignedPdfB64] = useState(null)

  const { mutate: sign, isPending: signing } = useMutation({
    mutationFn: ({ id, job_title }) => CLIENT_API.post(`/portal/documents/${id}/sign`,
      { job_title }).then(r => r.data),
    onSuccess: (data) => {
      qc.invalidateQueries(['portal-docs-client'])
      setSignModal(null)
      setSignJobTitle('')
      if (data.pdf_b64) {
        setSignedPdfB64({ b64: data.pdf_b64, title: signModal?.title || 'documento' })
      } else {
        toast.success('Documento firmado correctamente')
      }
    },
    onError: e => toast.error(extractErr(e, 'Error al firmar')),
  })
  const CAT_ICONS = { contract: '📋', deliverable: '📦', meeting_notes: '📝', report: '📊', other: '📄' }

  // Descargar PDF firmado automáticamente cuando está listo
  React.useEffect(() => {
    if (signedPdfB64) {
      const bytes = atob(signedPdfB64.b64)
      const arr = new Uint8Array(bytes.length)
      for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i)
      const blob = new Blob([arr], { type: 'application/pdf' })
      const url  = URL.createObjectURL(blob)
      const a    = document.createElement('a')
      a.href     = url
      a.download = `Firmado_${signedPdfB64.title.replace(/\s+/g,'_').slice(0,40)}.pdf`
      a.click()
      URL.revokeObjectURL(url)
      setSignedPdfB64(null)
      toast.success('✓ Documento firmado. Se ha descargado el certificado PDF.')
    }
  }, [signedPdfB64, toast])

  return (
    <div>
      <h3 style={{ fontSize: 18, fontWeight: 700, margin: '0 0 20px' }}>{t('doc_title')}</h3>
      {docs.length === 0 ? (
        <div style={{ ...S.card, textAlign: 'center', padding: '40px 20px', color: 'var(--text-2)' }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>📄</div>
          <p>{t('doc_empty')}</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {docs.map(doc => (
            <div key={doc.id} style={{ ...S.card, display: 'flex', gap: 14, alignItems: 'center' }}>
              <span style={{ fontSize: 24 }}>{CAT_ICONS[doc.category] || '📄'}</span>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 14, fontWeight: 700 }}>{doc.title}</div>
                {doc.description && <div style={{ fontSize: 12, color: 'var(--text-2)' }}>{doc.description}</div>}
                <div style={{ fontSize: 11, color: 'var(--text-2)', marginTop: 2 }}>{doc.file_name || doc.category} · {doc.created_at}</div>
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                {doc.requires_signature && !doc.signed_by_client && (
                  <button onClick={() => { setSignModal({ id: doc.id, title: doc.title }); setSignJobTitle('') }}
                    style={{ ...S.btn, padding: '7px 14px', fontSize: 12, background: 'var(--success-bg)',
                      borderColor: 'var(--success-border)', color: 'var(--success)' }}>
                    {t('doc_sign_modal_title')}
                  </button>
                )}
                {doc.signed_by_client && (
                  <span style={{ fontSize: 11, padding: '3px 8px', borderRadius: 4,
                    background: 'var(--success-bg)', color: 'var(--success)', fontWeight: 600 }}>
                    {t('doc_signed_on')} {doc.signed_at?.slice(0,10) || ''}
                  </span>
                )}
                {doc.file_url && <a href={doc.file_url} target="_blank" rel="noopener noreferrer"
                  style={{ ...S.btnSec, padding: '7px 12px', fontSize: 12, textDecoration: 'none' }}>
                  {t('doc_download_btn')}
                </a>}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Modal de confirmación de firma */}
      {signModal && (
        <div role="presentation" onMouseDown={() => setSignModal(null)} style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          zIndex: 9999, padding: 20,
        }}>
          <div role="presentation" onMouseDown={e => e.stopPropagation()} style={{
            background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 16,
            padding: '28px 32px', maxWidth: 460, width: '100%',
            boxShadow: '0 24px 64px rgba(0,0,0,0.8)',
          }}>
            <div style={{ fontSize: 18, fontWeight: 800, marginBottom: 8 }}>
              {t('doc_sign_modal_title')}
            </div>
            <div style={{ fontSize: 13, color: 'var(--text-2)', marginBottom: 20, lineHeight: 1.5 }}>
              {t('doc_sign_about')}: <strong style={{ color: 'var(--text-1)' }}>{signModal.title}</strong>.
            </div>

            <div style={{ marginBottom: 16 }}>
              <label style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-2)',
                textTransform: 'uppercase', letterSpacing: '0.06em', display: 'block', marginBottom: 6 }}>
                {t('doc_job_title_label')}
              </label>
              <input value={signJobTitle}
                onChange={e => setSignJobTitle(e.target.value)}
                placeholder={t('doc_job_title_label')}
                style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8,
                  padding: '9px 14px', color: 'var(--text-1)', fontSize: 13, width: '100%',
                  outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }}
              />
            </div>

            <div style={{ background: 'var(--success-bg)', border: '1px solid #00e5a020',
              borderRadius: 8, padding: '10px 14px', marginBottom: 20, fontSize: 11, color: 'var(--text-2)' }}>
              📄 {t('doc_sign_pdf_info')}
            </div>

            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
              <button onClick={() => setSignModal(null)}
                style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 8,
                  padding: '9px 20px', color: 'var(--text-2)', cursor: 'pointer',
                  fontSize: 13, fontFamily: 'inherit' }}>
                {t('cancel')}
              </button>
              <button
                onClick={() => sign({ id: signModal.id, job_title: signJobTitle })}
                disabled={signing}
                style={{ background: signing ? 'var(--surface-4)' : 'var(--success)', border: 'none',
                  borderRadius: 8, padding: '9px 24px', color: 'var(--surface-0)',
                  cursor: signing ? 'wait' : 'pointer', fontSize: 13, fontWeight: 700,
                  fontFamily: 'inherit', opacity: signing ? 0.7 : 1 }}>
                {signing ? t('doc_signing') : t('doc_confirm_sign')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Portal Wiki ───────────────────────────────────────────────────────────────
function PortalWiki() {
  const t = useLang()
  const [selected, setSelected] = useState(null)

  const { data: pages = [], isLoading } = useQuery({
    queryKey: ['portal-wiki-pages'],
    queryFn: () => CLIENT_API.get('/portal/wiki/pages').then(r => r.data),
  })
  const { data: pageDetail } = useQuery({
    queryKey: ['portal-wiki-page', selected],
    queryFn: () => CLIENT_API.get(`/portal/wiki/pages/${selected}`).then(r => r.data),
    enabled: !!selected,
  })

  if (isLoading) return <div style={{ color: 'var(--text-2)', padding: 40, textAlign: 'center' }}>Cargando...</div>

  return (
    <div>
      <h2 style={{ fontSize: 22, fontWeight: 800, marginBottom: 4 }}>{t('nav_wiki')}</h2>
      <p style={{ color: 'var(--text-2)', fontSize: 14, marginBottom: 24 }}>{t('wiki_subtitle')}</p>

      {selected && pageDetail ? (
        <div style={S.card}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
            <button onClick={() => setSelected(null)} style={{ ...S.btnSec, padding: '6px 14px', fontSize: 12 }}>← {t('back')}</button>
            <h3 style={{ fontSize: 18, fontWeight: 700, margin: 0 }}>{pageDetail.title}</h3>
          </div>
          <div style={{ color: 'var(--text-2)', fontSize: 14, lineHeight: 1.7 }}>
            {(pageDetail.content || []).map((block, i) => {
              if (block.type === 'heading1') return <h1 key={i} style={{ fontSize: 22, fontWeight: 800, margin: '20px 0 10px' }}>{block.content}</h1>
              if (block.type === 'heading2') return <h2 key={i} style={{ fontSize: 18, fontWeight: 700, margin: '18px 0 8px', color: 'var(--accent)' }}>{block.content}</h2>
              if (block.type === 'heading3') return <h3 key={i} style={{ fontSize: 15, fontWeight: 700, margin: '14px 0 6px' }}>{block.content}</h3>
              if (block.type === 'bullet') return <li key={i} style={{ marginLeft: 20, marginBottom: 4 }}>{block.content}</li>
              if (block.type === 'code') return <pre key={i} style={{ background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '12px 16px', fontSize: 12, overflow: 'auto', marginBottom: 12 }}>{block.content}</pre>
              if (block.type === 'callout') return <div key={i} style={{ background: 'var(--accent-muted)', border: '1px solid #00d4ff30', borderRadius: 8, padding: '12px 16px', marginBottom: 12 }}>{block.content}</div>
              if (block.type === 'separator') return <hr key={i} style={{ border: 'none', borderTop: '1px solid var(--surface-4)', margin: '16px 0' }} />
              return <p key={i} style={{ marginBottom: 10 }}>{block.content}</p>
            })}
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 20 }}>
            {t('last_updated')}: {new Date(pageDetail.updated_at).toLocaleDateString()}
          </div>
        </div>
      ) : (
        <div>
          {pages.length === 0 ? (
            <div style={{ ...S.card, textAlign: 'center', padding: 48 }}>
              <div style={{ fontSize: 40, marginBottom: 16 }}>📚</div>
              <div style={{ color: 'var(--text-2)', fontSize: 14 }}>{t('wiki_empty')}</div>
            </div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 14 }}>
              {pages.map(p => (
                <button key={p.id} type="button" onClick={() => setSelected(p.id)}
                  style={{ ...S.card, cursor: 'pointer', transition: 'border-color 0.15s' }}
                  onMouseEnter={e => e.currentTarget.style.borderColor = 'var(--accent-glow)'}
                  onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--surface-4)'}>
                  <div style={{ fontSize: 20, marginBottom: 10 }}>📄</div>
                  <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 6 }}>{p.title}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-2)' }}>
                    {t('last_updated')}: {new Date(p.updated_at).toLocaleDateString()}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Portal Statistics ─────────────────────────────────────────────────────────
function PortalStats() {
  const t = useLang()
  const { data: dash } = useQuery({ queryKey: ['portal-dash'], queryFn: () => CLIENT_API.get('/portal/dashboard').then(r => r.data) })
  const { data: uats = [] } = useQuery({ queryKey: ['portal-uat-stats'], queryFn: () => CLIENT_API.get('/portal/uat').then(r => r.data) })
  const { data: docs = [] } = useQuery({ queryKey: ['portal-docs-stats'], queryFn: () => CLIENT_API.get('/portal/documents').then(r => r.data) })
  const { data: frs = [] } = useQuery({ queryKey: ['portal-fr-stats'], queryFn: () => CLIENT_API.get('/portal/feature-requests').then(r => r.data) })

  const project = dash?.projects?.[0] || dash?.project || {}
  const progress = project.progress_pct ?? 0
  const budget_used = project.budget_used_pct ?? 0
  const tasks_done = project.tasks_done ?? 0
  const tasks_total = project.tasks_total ?? 0

  const uatPassed = uats.filter(u => u.status === 'passed').length
  const uatFailed = uats.filter(u => u.status === 'failed').length
  const uatPending = uats.filter(u => ['pending','in_progress'].includes(u.status)).length

  const KPI = ({ icon, label, value, sub, color = 'var(--accent)' }) => (
    <div style={{ ...S.card, textAlign: 'center', padding: '24px 20px' }}>
      <div style={{ fontSize: 28, marginBottom: 8 }}>{icon}</div>
      <div style={{ fontSize: 28, fontWeight: 800, color, marginBottom: 4 }}>{value}</div>
      <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 4 }}>{label}</div>
      {sub && <div style={{ fontSize: 11, color: 'var(--text-2)' }}>{sub}</div>}
    </div>
  )

  const ProgressBar = ({ value, color = 'var(--accent)' }) => (
    <div style={{ height: 8, background: 'var(--surface-4)', borderRadius: 4, overflow: 'hidden' }}>
      <div style={{ height: '100%', width: `${Math.min(100, value)}%`, background: color, borderRadius: 4, transition: 'width 0.6s' }} />
    </div>
  )

  return (
    <div>
      <h2 style={{ fontSize: 22, fontWeight: 800, marginBottom: 4 }}>{t('nav_stats')}</h2>
      <p style={{ color: 'var(--text-2)', fontSize: 14, marginBottom: 28 }}>{t('stats_subtitle')}</p>

      {/* KPIs principales */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 16, marginBottom: 32 }}>
        <KPI icon="📈" label={t('stats_progress')} value={`${progress}%`} color="#00d4ff" sub={`${tasks_done}/${tasks_total} tareas`} />
        <KPI icon="💰" label={t('stats_budget')} value={`${budget_used}%`}
          color={budget_used > 90 ? 'var(--danger)' : budget_used > 75 ? 'var(--warning)' : 'var(--success)'}
          sub={t('stats_budget_used')} />
        <KPI icon="🧪" label={t('nav_uat')} value={uatPassed} color="#00e5a0" sub={`${uatFailed} rechazadas`} />
        <KPI icon="💡" label={t('nav_requests')} value={frs.length} color="#7c3aed"
          sub={`${frs.filter(f=>f.status==='approved').length} aprobadas`} />
        <KPI icon="📄" label={t('nav_documents')} value={docs.length} color="#ffb800"
          sub={`${docs.filter(d=>d.is_signed).length} firmados`} />
      </div>

      {/* Barras de progreso */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 32 }}>
        <div style={S.card}>
          <h3 style={{ fontSize: 15, fontWeight: 700, marginBottom: 16 }}>Avance del proyecto</h3>
          <div style={{ marginBottom: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 6 }}>
              <span>Progreso general</span><span style={{ color: 'var(--accent)', fontWeight: 700 }}>{progress}%</span>
            </div>
            <ProgressBar value={progress} />
          </div>
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 6 }}>
              <span>Presupuesto consumido</span>
              <span style={{ color: budget_used > 90 ? 'var(--danger)' : 'var(--warning)', fontWeight: 700 }}>{budget_used}%</span>
            </div>
            <ProgressBar value={budget_used} color={budget_used > 90 ? 'var(--danger)' : 'var(--warning)'} />
          </div>
        </div>

        <div style={S.card}>
          <h3 style={{ fontSize: 15, fontWeight: 700, marginBottom: 16 }}>Estado UATs</h3>
          {[
            { label: 'Aprobadas', value: uatPassed, total: uats.length, color: 'var(--success)' },
            { label: 'En progreso', value: uatPending, total: uats.length, color: 'var(--accent)' },
            { label: 'Rechazadas', value: uatFailed, total: uats.length, color: 'var(--danger)' },
          ].map(row => (
            <div key={row.label} style={{ marginBottom: 10 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 5 }}>
                <span>{row.label}</span>
                <span style={{ color: row.color, fontWeight: 700 }}>{row.value}/{uats.length}</span>
              </div>
              <ProgressBar value={uats.length ? (row.value/uats.length)*100 : 0} color={row.color} />
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function PortalApp({ changeLang, _currentLang }) {
  const { client, logout } = useClientAuth()
  const toast = useToast()
  const qc = useQueryClient()
  const t = useLang()
  const [section, setSection] = useState('dashboard')

  const { data: branding } = useQuery({
    queryKey: ['portal-branding'],
    queryFn: () => CLIENT_API.get('/portal/branding').then(r => r.data),
    enabled: !!client,
  })

  const { data: surveys = [] } = useQuery({
    queryKey: ['portal-surveys'],
    queryFn: () => CLIENT_API.get('/portal/surveys').then(r => r.data),
    enabled: !!client,
  })
  const pendingSurveys = surveys.filter(s => s.status === 'pending').length

  useEffect(() => {
    if (!client) return
    let socket = null
    let pingInterval = null
    let cancelled = false

    const connect = async () => {
      try {
        const ticketRes = await CLIENT_API.get('/ws/portal-ticket')
        const ticket = ticketRes?.data?.ticket
        if (!ticket || cancelled) return

        const wsProto = window.location.protocol === 'https:' ? 'wss' : 'ws'
        const wsUrl = `${wsProto}://${window.location.host}/api/v1/ws/portal-notifications?ticket=${encodeURIComponent(ticket)}`
        socket = new window.WebSocket(wsUrl)

        socket.onmessage = (event) => {
          try {
            const msg = JSON.parse(event.data)
            if (msg?.type === 'portal_notifications') {
              qc.invalidateQueries(['portal-dashboard'])
              qc.invalidateQueries(['portal-messages-client'])
              qc.invalidateQueries(['portal-sd-tickets'])
              qc.invalidateQueries(['portal-invoices'])
            }
          } catch {
            // Ignore malformed payloads from network middleboxes.
          }
        }

        socket.onerror = () => {
          toast.error('No se pudo conectar al canal realtime del portal')
        }

        pingInterval = window.setInterval(() => {
          if (socket && socket.readyState === window.WebSocket.OPEN) {
            socket.send(JSON.stringify({ type: 'ping' }))
          }
        }, 25000)
      } catch {
        // WS is optional; portal works with polling queries.
      }
    }

    connect()
    return () => {
      cancelled = true
      if (pingInterval) window.clearInterval(pingInterval)
      if (socket && socket.readyState === window.WebSocket.OPEN) socket.close()
    }
  }, [client, qc, toast])

  const SECTIONS = [
    { id: 'dashboard', icon: '◈',  label: t('nav_dashboard') },
    { id: 'stats',     icon: '📊', label: t('nav_stats') },
    { id: 'uat',       icon: '🧪', label: t('nav_uat') },
    { id: 'requests',  icon: '💡', label: t('nav_requests') },
    { id: 'roadmap',   icon: '🗺️', label: t('nav_roadmap') },
    { id: 'wiki',      icon: '📚', label: t('nav_wiki') },
    { id: 'documents', icon: '📄', label: t('nav_documents') },
    { id: 'invoices',  icon: '🧾', label: 'Facturas' },
    { id: 'support',   icon: '🎫', label: t('nav_support') },
    { id: 'messages',  icon: '💬', label: t('nav_messages') },
    { id: 'profile',   icon: '⚙️', label: 'Mi perfil' },
  ]

  return (
    <div style={{ display: 'flex', minHeight: '100vh', background: 'var(--surface-0)' }}>
      {/* Sidebar */}
      <aside style={{ width: 220, background: 'var(--portal-deep)', borderRight: '1px solid #1a2640', display: 'flex', flexDirection: 'column', flexShrink: 0 }}>
        <div style={{ padding: '20px 20px', borderBottom: '1px solid #1a2640' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
            {branding?.logo_url ? (
              <img src={branding.logo_url} alt={branding.brand_name || 'Portal'} style={{ width: 28, height: 28, borderRadius: 7, objectFit: 'cover', border: '1px solid #1a2640' }} />
            ) : (
              <div style={{ width: 28, height: 28, background: `linear-gradient(135deg, ${branding?.primary_color || '#00d4ff'}, #0f172a)`, borderRadius: 7, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, fontWeight: 800 }}>◈</div>
            )}
            <span style={{ fontWeight: 800, fontSize: 14 }}>{branding?.brand_name || t('portal')}</span>
          </div>
        </div>

        <nav style={{ flex: 1, padding: '12px 10px' }}>
          {SECTIONS.map(s => (
            <button key={s.id} onClick={() => setSection(s.id)}
              style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 10, padding: '9px 12px', borderRadius: 8, border: `1px solid ${section === s.id ? 'var(--accent-glow)' : 'transparent'}`, background: section === s.id ? 'var(--accent-muted)' : 'transparent', color: section === s.id ? 'var(--accent)' : 'var(--text-2)', fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit', marginBottom: 2, textAlign: 'left' }}>
              <span style={{ fontSize: 15 }}>{s.icon}</span>
              {s.label}
            </button>
          ))}
        </nav>

        <div style={{ padding: '12px 10px', borderTop: '1px solid #1a2640' }}>
          <div style={{ padding: '8px 12px', marginBottom: 4, display: 'flex', gap: 10, alignItems: 'center' }}>
            <div style={{ width: 30, height: 30, borderRadius: 8, background: 'var(--accent-muted)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14, fontWeight: 800, color: 'var(--accent)', flexShrink: 0 }}>
              {client?.full_name?.charAt(0)?.toUpperCase() || '?'}
            </div>
            <div style={{ overflow: 'hidden' }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-1)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{client?.full_name}</div>
              <button onClick={() => setSection('profile')} style={{ background: 'none', border: 'none', padding: 0, fontSize: 10, color: 'var(--text-2)', cursor: 'pointer', fontFamily: 'inherit' }}>⚙️ Mi perfil</button>
            </div>
          </div>
          <button onClick={logout} style={{ ...S.btnSec, width: '100%', padding: '7px 12px', fontSize: 12 }}>⏻ {t('logout')}</button>
        </div>
      </aside>

      {/* Content */}
      <main style={{ flex: 1, overflowY: 'auto', padding: 32, color: 'var(--text-1)' }}>
        {pendingSurveys > 0 && (
          <button type="button" style={{ background: 'var(--success-bg)', border: '1px solid #00e5a040', borderRadius: 10, padding: '12px 20px', marginBottom: 24, display: 'flex', alignItems: 'center', gap: 12, cursor: 'pointer', width: '100%', textAlign: 'left', fontFamily: 'inherit' }} onClick={() => setSection('surveys')}>
            <span style={{ fontSize: 20 }}>⭐</span>
            <div>
              <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--success)' }}>Tienes {pendingSurveys} encuesta(s) pendiente(s)</div>
              <div style={{ fontSize: 12, color: 'var(--text-2)' }}>Tu opinión nos ayuda a mejorar. Solo toma 1 minuto.</div>
            </div>
          </button>
        )}

        {section === 'dashboard'  && <PortalDashboard />}
        {section === 'stats'      && <PortalStats />}
        {section === 'uat'        && <PortalUAT />}
        {section === 'requests'   && <PortalFeatureRequests />}
        {section === 'roadmap'    && <PortalRoadmap />}
        {section === 'wiki'       && <PortalWiki />}
        {section === 'documents'  && <PortalDocuments />}
        {section === 'invoices'   && <PortalInvoices />}
        {section === 'support'    && <PortalSupportDesk />}
        {section === 'messages'   && <PortalMessages />}
        {section === 'profile'    && <PortalMyProfile changeLang={changeLang} />}
      </main>
    </div>
  )
}

// ── Mi Perfil (cliente) ───────────────────────────────────────────────────────
function PortalMyProfile({ changeLang }) {
  const { client, _login } = useClientAuth()
  const toast = useToast()
  const qc = useQueryClient()
  const _t = useLang()

  const [tab, setTab] = useState('info')
  const [form, setForm] = useState({
    full_name: client?.full_name || '',
    phone: client?.phone || '',
    job_title: client?.job_title || '',
    language: client?.language || 'es',
  })
  const [pwdForm, setPwdForm]   = useState({ current: '', new_pwd: '', confirm: '' })
  const [saved, setSaved]       = useState(false)
  const [pwdError, setPwdError] = useState('')

  // Obtener config del portal para saber qué puede editar
  const { data: me } = useQuery({
    queryKey: ['portal-me'],
    queryFn: () => CLIENT_API.get('/portal/auth/me').then(r => r.data),
  })

  const LANGUAGES = [
    { code: 'es', label: 'Español' }, { code: 'en', label: 'English' },
    { code: 'fr', label: 'Français' }, { code: 'de', label: 'Deutsch' },
    { code: 'pt', label: 'Português' }, { code: 'it', label: 'Italiano' },
    { code: 'pl', label: 'Polski' }, { code: 'zh', label: '中文' },
  ]

  const { mutate: saveProfile, isPending: saving } = useMutation({
    mutationFn: d => CLIENT_API.patch('/portal/auth/me', d).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries(['portal-me'])
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
      // Actualizar el idioma si cambió
      if (form.language !== client?.language) {
        localStorage.setItem('portal_lang', form.language)
        if (changeLang) changeLang(form.language)
        // Actualizar el client guardado en localStorage
        try {
          const saved = JSON.parse(localStorage.getItem('client_user') || '{}')
          saved.language = form.language
          localStorage.setItem('client_user', JSON.stringify(saved))
        } catch { /* noop */ }
        // Recargar para aplicar nuevas traducciones
        window.location.reload()
      }
    },
    onError: e => toast.error(extractErr(e, 'Error al guardar')),
  })

  const { mutate: savePwd, isPending: changingPwd } = useMutation({
    mutationFn: d => CLIENT_API.patch('/portal/auth/me', { password: d.new_pwd }).then(r => r.data),
    onSuccess: () => { setPwdForm({ current: '', new_pwd: '', confirm: '' }); toast.success('✅ Contraseña actualizada correctamente') },
    onError: e => { const raw = e?.response?.data?.detail; setPwdError(Array.isArray(raw) ? raw.map(d => d.msg).join(', ') : (raw || 'Error al cambiar contraseña')) },
  })

  const handlePwdChange = () => {
    setPwdError('')
    if (pwdForm.new_pwd !== pwdForm.confirm) { setPwdError('Las contraseñas no coinciden'); return }
    if (pwdForm.new_pwd.length < 6) { setPwdError('La contraseña debe tener al menos 6 caracteres'); return }
    savePwd(pwdForm)
  }

  const TABS = [
    { id: 'info',     label: 'Mis datos' },
    { id: 'security', label: 'Seguridad' },
    { id: 'access',   label: 'Mi acceso' },
  ]

  return (
    <div style={{ maxWidth: 640 }}>
      <div style={{ marginBottom: 24 }}>
        <div style={{ fontSize: 22, fontWeight: 800, marginBottom: 4 }}>Mi perfil</div>
        <div style={{ fontSize: 13, color: 'var(--text-2)' }}>Gestiona tus datos personales y preferencias</div>
      </div>

      {/* Avatar + info rápida */}
      <div style={{ ...S.card, display: 'flex', gap: 16, alignItems: 'center', marginBottom: 20 }}>
        <div style={{ width: 56, height: 56, borderRadius: 14, background: 'linear-gradient(135deg, #00d4ff30, #7c3aed30)', border: '1px solid #00d4ff30', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 24, fontWeight: 800, color: 'var(--accent)', flexShrink: 0 }}>
          {client?.full_name?.charAt(0)?.toUpperCase() || '?'}
        </div>
        <div>
          <div style={{ fontSize: 17, fontWeight: 800 }}>{client?.full_name}</div>
          <div style={{ fontSize: 13, color: 'var(--text-2)' }}>{client?.email}</div>
          <div style={{ fontSize: 12, color: 'var(--text-3)' }}>
            {client?.job_title && `${client.job_title} · `}{client?.company}
          </div>
        </div>
      </div>

      {/* Sub-tabs */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 20, borderBottom: '1px solid #1a2640', paddingBottom: 10 }}>
        {TABS.map(tb => (
          <button key={tb.id} onClick={() => setTab(tb.id)}
            style={{ padding: '6px 16px', borderRadius: 8, border: `1px solid ${tab === tb.id ? 'var(--accent-glow)' : 'transparent'}`,
              background: tab === tb.id ? 'var(--accent-muted)' : 'transparent', color: tab === tb.id ? 'var(--accent)' : 'var(--text-2)',
              fontSize: 12, fontWeight: tab === tb.id ? 700 : 400, cursor: 'pointer', fontFamily: 'inherit' }}>
            {tb.label}
          </button>
        ))}
      </div>

      {/* Tab: Mis datos */}
      {tab === 'info' && (
        <div style={S.card}>
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 16 }}>Información personal</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginBottom: 16 }}>
            <div>
              <label style={S.label}>Nombre visible</label>
              <input value={form.full_name} onChange={e => setForm(f => ({ ...f, full_name: e.target.value }))} style={S.input} />
            </div>
            <div>
              <label style={S.label}>Cargo / Rol</label>
              <input value={form.job_title} onChange={e => setForm(f => ({ ...f, job_title: e.target.value }))} style={S.input} />
            </div>
            <div>
              <label style={S.label}>Teléfono</label>
              <input value={form.phone} onChange={e => setForm(f => ({ ...f, phone: e.target.value }))} style={S.input} placeholder="Teléfono" />
            </div>
            <div>
              <label style={S.label}>Idioma del portal</label>
              <select value={form.language} onChange={e => setForm(f => ({ ...f, language: e.target.value }))} style={S.input}>
                {LANGUAGES.map(l => <option key={l.code} value={l.code}>{l.label}</option>)}
              </select>
            </div>
          </div>
          <div style={{ marginBottom: 16, padding: '10px 14px', background: 'var(--surface-4)', borderRadius: 8, fontSize: 12, color: 'var(--text-2)' }}>
            🔒 El email (<strong style={{ color: 'var(--text-1)' }}>{client?.email}</strong>) es tu identificador de acceso y no puede modificarse. Contacta con el equipo si necesitas cambiarlo.
          </div>
          {saved && (
            <div style={{ marginBottom: 12, padding: '8px 14px', background: 'var(--success-bg)', border: '1px solid #00e5a030', borderRadius: 8, fontSize: 12, color: 'var(--success)' }}>
              ✅ Perfil actualizado correctamente
              {form.language !== client?.language && ' · La página se recargará para aplicar el nuevo idioma'}
            </div>
          )}
          <button onClick={() => saveProfile(form)} disabled={saving}
            style={{ ...S.btn, opacity: saving ? 0.6 : 1 }}>
            {saving ? 'Guardando...' : '💾 Guardar cambios'}
          </button>
        </div>
      )}

      {/* Tab: Seguridad */}
      {tab === 'security' && (
        <div style={S.card}>
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 16 }}>Cambiar contraseña</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 16 }}>
            <div>
              <label style={S.label}>Nueva contraseña</label>
              <input type="password" value={pwdForm.new_pwd} onChange={e => setPwdForm(f => ({ ...f, new_pwd: e.target.value }))} style={S.input} placeholder="Nueva contraseña" />
            </div>
            <div>
              <label style={S.label}>Confirmar nueva contraseña</label>
              <input type="password" value={pwdForm.confirm} onChange={e => setPwdForm(f => ({ ...f, confirm: e.target.value }))} style={S.input} />
            </div>
          </div>
          {pwdError && (
            <div style={{ marginBottom: 12, padding: '8px 14px', background: 'var(--danger-bg)', border: '1px solid #ff475730', borderRadius: 8, fontSize: 12, color: 'var(--danger)' }}>
              ✗ {pwdError}
            </div>
          )}
          <button onClick={handlePwdChange} disabled={changingPwd || !pwdForm.new_pwd || !pwdForm.confirm}
            style={{ ...S.btn, opacity: (changingPwd || !pwdForm.new_pwd) ? 0.6 : 1 }}>
            {changingPwd ? 'Actualizando...' : '🔑 Cambiar contraseña'}
          </button>
          <div style={{ marginTop: 16, fontSize: 11, color: 'var(--text-3)', lineHeight: 1.6 }}>
            Elige una contraseña segura que no uses en otros servicios. Si olvidas tu contraseña, contacta con el equipo para que te la restablezcan.
          </div>
        </div>
      )}

      {/* Tab: Mi acceso */}
      {tab === 'access' && (
        <div style={S.card}>
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 16 }}>Mis permisos en el portal</div>
          <div style={{ fontSize: 12, color: 'var(--text-2)', marginBottom: 16 }}>Estos permisos son asignados por tu gestor y no pueden modificarse desde aquí.</div>
          {[
            { key: 'can_approve_deliverables', label: 'Aprobar entregables', desc: 'Puedes validar o rechazar entregables del proyecto' },
            { key: 'can_request_changes', label: '↩ Solicitar cambios', desc: 'Puedes enviar solicitudes de cambio al equipo' },
            { key: 'can_view_budget', label: 'Ver presupuesto', desc: 'Puedes ver el consumo vs presupuesto del proyecto' },
            { key: 'can_view_team', label: 'Ver equipo', desc: 'Puedes ver los miembros del equipo asignado' },
          ].map(p => (
            <div key={p.key} style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 12, padding: '10px 12px',
              background: me?.[p.key] ? 'var(--success-bg)' : 'var(--surface-4)', border: `1px solid ${me?.[p.key] ? 'var(--success-bg)' : 'var(--surface-4)'}`, borderRadius: 8 }}>
              <span style={{ fontSize: 16 }}>{me?.[p.key] ? '✅' : '⛔'}</span>
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: me?.[p.key] ? 'var(--text-1)' : 'var(--text-2)' }}>{p.label}</div>
                <div style={{ fontSize: 11, color: 'var(--text-3)' }}>{p.desc}</div>
              </div>
            </div>
          ))}
          <div style={{ marginTop: 16, padding: '10px 14px', background: 'var(--surface-4)', borderRadius: 8, fontSize: 12, color: 'var(--text-2)' }}>
            📧 Email de acceso: <strong style={{ color: 'var(--text-1)' }}>{client?.email}</strong>
            {me?.language && <span style={{ marginLeft: 12 }}>🌍 Idioma: <strong style={{ color: 'var(--text-1)' }}>{me.language.toUpperCase()}</strong></span>}
          </div>
        </div>
      )}
    </div>
  )
}


// ── Root export ───────────────────────────────────────────────────────────────
export default function PortalClientePage() {
  const _t = useAppT()
  const [lang, setLang] = useState(() => {
    // Prioridad: idioma del perfil del cliente > localStorage > 'es'
    try {
      const savedClient = JSON.parse(localStorage.getItem('client_user') || 'null')
      if (savedClient?.language) return savedClient.language
    } catch { /* noop */ }
    return localStorage.getItem('portal_lang') || 'es'
  })
  const changeLang = (l) => { setLang(l); localStorage.setItem('portal_lang', l) }
  return (
    <LangContext.Provider value={lang}>
      <ClientAuthProvider>
        <PortalClienteInner changeLang={changeLang} currentLang={lang} />
      </ClientAuthProvider>
    </LangContext.Provider>
  )
}

function PortalClienteInner({ changeLang, currentLang }) {
  const _toast = useToast()
  const { client } = useClientAuth()
  return client ? <PortalApp changeLang={changeLang} currentLang={currentLang} /> : <LoginScreen changeLang={changeLang} currentLang={currentLang} />
}

// ── Portal Service Desk (client-facing) ───────────────────────────────────────
// This is appended to PortalClientePage.jsx
// The PortalApp SECTIONS array needs 'servicedesk' added and PortalServiceDesk rendered

// Export helper so PortalApp can import it
export function PortalServiceDesk() {
  const qc = useQueryClient()
  const toast = useToast()
  const { _client } = useClientAuth()
  const [showNew, setShowNew] = useState(false)
  const [selected, setSelected] = useState(null)
  const [newForm, setNewForm] = useState({ title: '', description: '', ticket_type: 'incident', priority: 'p3_medium', urgency: 'medium', impact: 'individual', service_item_id: '' })
  const [newComment, setNewComment] = useState('')

  const { data: catalog = [] } = useQuery({ queryKey: ['sd-catalog-client'], queryFn: () => CLIENT_API.get('/sd/catalog').then(r => r.data) })
  const { data: myTickets = [], isLoading } = useQuery({ queryKey: ['sd-my-tickets'], queryFn: () => CLIENT_API.get('/sd/tickets/client/my').then(r => r.data) })
  const { data: ticket = null } = useQuery({ queryKey: ['sd-ticket-client', selected], queryFn: () => CLIENT_API.get(`/sd/tickets/client/${selected}`).then(r => r.data), enabled: !!selected })
  const { data: kb = [] } = useQuery({ queryKey: ['sd-kb-client'], queryFn: () => CLIENT_API.get('/sd/kb', { params: { limit: 6 } }).then(r => r.data) })
  const { data: announcements = [] } = useQuery({ queryKey: ['sd-ann-client'], queryFn: () => CLIENT_API.get('/sd/announcements').then(r => r.data) })

  const { mutate: createTicket } = useMutation({
    mutationFn: (data) => CLIENT_API.post('/sd/tickets/client', data),
    onSuccess: () => { qc.invalidateQueries(['sd-my-tickets']); setShowNew(false); setNewForm({ title: '', description: '', ticket_type: 'incident', priority: 'p3_medium', urgency: 'medium', impact: 'individual', service_item_id: '' }) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: addComment } = useMutation({
    mutationFn: ({ ticketId, body }) => CLIENT_API.post(`/sd/tickets/${ticketId}/comments/client`, { body }),
    onSuccess: () => { qc.invalidateQueries(['sd-ticket-client', selected]); setNewComment('') },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: rateCsat } = useMutation({
    mutationFn: ({ ticketId, score, comment }) => CLIENT_API.post(`/sd/tickets/${ticketId}/csat`, { score, comment }),
    onSuccess: () => qc.invalidateQueries(['sd-my-tickets']),
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const PRIORITY_COLORS = { p1_critical: 'var(--danger)', p2_high: CHART.orange, p3_medium: 'var(--warning)', p4_low: 'var(--success)' }
  const STATUS_LABELS = { new: 'Nuevo', assigned: 'Asignado', in_progress: 'En progreso', pending_client: 'Pendiente tuya', resolved: 'Resuelto', closed: 'Cerrado' }
  const STATUS_COLORS = { new: 'var(--purple)', assigned: 'var(--accent)', in_progress: 'var(--warning)', pending_client: 'var(--warning)', resolved: 'var(--success)', closed: 'var(--text-2)' }
  const TYPE_LABELS = { incident: '🔴 Incidencia', service_request: '📋 Solicitud', question: '❓ Consulta', change: '🔀 Cambio' }

  if (selected && ticket) {
    return (
      <div>
        <button onClick={() => setSelected(null)} style={{ ...S.btnSec, marginBottom: 20 }}>← Volver</button>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 }}>
          <div>
            <div style={{ fontSize: 12, color: 'var(--text-2)', marginBottom: 4 }}>Ticket #{ticket.number}</div>
            <h3 style={{ fontSize: 18, fontWeight: 700, margin: 0 }}>{ticket.title}</h3>
          </div>
          <span style={{ fontSize: 12, fontWeight: 700, padding: '4px 12px', borderRadius: 20, background: (STATUS_COLORS[ticket.status] || 'var(--text-2)') + '20', color: STATUS_COLORS[ticket.status] || 'var(--text-2)', border: `1px solid ${(STATUS_COLORS[ticket.status] || 'var(--text-2)')}40` }}>
            {STATUS_LABELS[ticket.status] || ticket.status}
          </span>
        </div>

        <div style={{ ...S.card, marginBottom: 16 }}>
          <p style={{ fontSize: 14, color: 'var(--text-1)', lineHeight: 1.7, margin: 0, whiteSpace: 'pre-wrap' }}>{ticket.description}</p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginTop: 16 }}>
            {[
              { label: 'Prioridad', value: ticket.priority_label, color: PRIORITY_COLORS[ticket.priority] },
              { label: 'Asignado a', value: ticket.assigned_to_name || 'Pendiente asignación' },
              { label: 'SLA resolución', value: ticket.sla_resolution_due || '—', color: ticket.sla_resolution_status === 'breached' ? 'var(--danger)' : 'var(--text-2)' },
            ].map(({ label, value, color }) => (
              <div key={label} style={{ background: 'var(--portal-bg)', borderRadius: 8, padding: '10px 12px' }}>
                <div style={{ fontSize: 11, color: 'var(--text-2)', marginBottom: 3 }}>{label}</div>
                <div style={{ fontSize: 13, fontWeight: 600, color: color || 'var(--text-1)' }}>{value}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Comments */}
        <div style={{ ...S.card, marginBottom: 16 }}>
          <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 14 }}>Conversación</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 14 }}>
            {(ticket.comments || []).filter(c => !c.is_internal).map(c => (
              <div key={c.id} style={{ padding: '10px 14px', background: c.author_type === 'client' ? 'var(--accent-muted)' : 'var(--portal-bg)', borderRadius: 8, border: `1px solid ${c.author_type === 'client' ? 'var(--accent-glow)' : 'var(--surface-4)'}` }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                  <span style={{ fontSize: 12, fontWeight: 600 }}>{c.author_type === 'client' ? 'Tú' : `Soporte — ${c.author_name}`}</span>
                  <span style={{ fontSize: 11, color: 'var(--text-2)' }}>{c.created_at}</span>
                </div>
                <p style={{ fontSize: 13, margin: 0, whiteSpace: 'pre-wrap' }}>{c.body}</p>
              </div>
            ))}
            {!(ticket.comments || []).filter(c => !c.is_internal).length && (
              <div style={{ fontSize: 13, color: 'var(--text-2)', textAlign: 'center', padding: '12px 0' }}>Sin mensajes aún</div>
            )}
          </div>
          {ticket.status !== 'closed' && ticket.status !== 'cancelled' && (
            <div style={{ display: 'flex', gap: 10 }}>
              <textarea value={newComment} onChange={e => setNewComment(e.target.value)} rows={2} placeholder="Escribe un comentario"
                style={{ ...S.input, flex: 1, resize: 'vertical' }} />
              <button onClick={() => addComment({ ticketId: selected, body: newComment })} disabled={!newComment} style={{ ...S.btn, alignSelf: 'flex-end', padding: '10px 16px', whiteSpace: 'nowrap' }}>Enviar</button>
            </div>
          )}
        </div>

        {/* CSAT */}
        {ticket.status === 'resolved' && !ticket.csat_score && (
          <div style={{ ...S.card, border: '1px solid #00e5a040' }}>
            <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 12 }}>⭐ ¿Cómo valorarías la atención recibida?</div>
            <div style={{ display: 'flex', gap: 8 }}>
              {[1,2,3,4,5].map(score => (
                <button key={score} onClick={() => rateCsat({ ticketId: selected, score, comment: '' })}
                  style={{ flex: 1, padding: '12px 0', fontSize: 24, background: 'var(--portal-bg)', border: '1px solid #1a2640', borderRadius: 10, cursor: 'pointer', transition: 'all 0.15s' }}
                  onMouseEnter={e => { e.currentTarget.style.background = 'var(--success-bg)'; e.currentTarget.style.borderColor = 'rgba(52,211,153,0.25)' }}
                  onMouseLeave={e => { e.currentTarget.style.background = 'var(--portal-bg)'; e.currentTarget.style.borderColor = 'var(--surface-4)' }}>
                  {'⭐'.repeat(score)}
                </button>
              ))}
            </div>
          </div>
        )}
        {ticket.csat_score && <div style={{ ...S.card, color: 'var(--success)', textAlign: 'center' }}>✓ Gracias por tu valoración: {'⭐'.repeat(ticket.csat_score)}</div>}
      </div>
    )
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <h3 style={{ fontSize: 18, fontWeight: 700, margin: 0 }}>Soporte</h3>
        <button onClick={() => setShowNew(true)} style={S.btn}>＋ Nuevo ticket</button>
      </div>

      {/* Announcements */}
      {announcements.length > 0 && (
        <div style={{ marginBottom: 20 }}>
          {announcements.map(a => (
            <div key={a.id} style={{ display: 'flex', gap: 12, padding: '12px 16px', borderRadius: 10, marginBottom: 8, background: a.type === 'critical' ? 'var(--danger-bg)' : a.type === 'warning' ? 'var(--warning-bg)' : 'var(--accent-muted)', border: `1px solid ${a.type === 'critical' ? 'var(--danger-border)' : a.type === 'warning' ? 'var(--warning-border)' : 'var(--accent-glow)'}` }}>
              <span style={{ fontSize: 20 }}>{a.type === 'critical' ? '🚨' : a.type === 'warning' ? '⚠️' : 'ℹ️'}</span>
              <div>
                <div style={{ fontSize: 13, fontWeight: 700 }}>{a.title}</div>
                <div style={{ fontSize: 12, color: 'var(--text-2)' }}>{a.body}</div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* KB quick links */}
      {kb.length > 0 && (
        <div style={{ ...S.card, marginBottom: 20 }}>
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 12 }}>📚 Artículos que pueden ayudarte</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {kb.slice(0, 4).map(a => (
              <div key={a.id} style={{ fontSize: 13, color: 'var(--accent)', cursor: 'pointer', padding: '6px 0', borderBottom: '1px solid #1a2640' }}>{a.title}</div>
            ))}
          </div>
        </div>
      )}

      {/* My tickets */}
      <h4 style={{ fontSize: 14, fontWeight: 700, margin: '0 0 14px', color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Mis tickets</h4>
      {isLoading ? null : myTickets.length === 0 ? (
        <div style={{ ...S.card, textAlign: 'center', padding: '40px 20px', color: 'var(--text-2)' }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>🎫</div>
          <p>No tienes tickets abiertos. ¿Necesitas ayuda?</p>
          <button onClick={() => setShowNew(true)} style={{ ...S.btn, marginTop: 12 }}>Abrir un ticket</button>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {myTickets.map(t => (
            <button key={t.id} type="button" onClick={() => setSelected(t.id)} style={{ ...S.card, cursor: 'pointer', border: `1px solid ${(STATUS_COLORS[t.status] || 'var(--surface-4)')}30`, transition: 'border-color 0.15s', width: '100%', textAlign: 'left', fontFamily: 'inherit' }}
              onMouseEnter={e => e.currentTarget.style.borderColor = (STATUS_COLORS[t.status] || 'var(--accent)') + '60'}
              onMouseLeave={e => e.currentTarget.style.borderColor = (STATUS_COLORS[t.status] || 'var(--surface-4)') + '30'}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 12, color: 'var(--text-2)', marginBottom: 3 }}>#{t.number} · {TYPE_LABELS[t.ticket_type] || t.ticket_type}</div>
                  <div style={{ fontSize: 14, fontWeight: 700 }}>{t.title}</div>
                </div>
                <span style={{ fontSize: 11, fontWeight: 700, padding: '2px 9px', borderRadius: 20, background: (STATUS_COLORS[t.status] || 'var(--text-2)') + '20', color: STATUS_COLORS[t.status] || 'var(--text-2)', border: `1px solid ${(STATUS_COLORS[t.status] || 'var(--text-2)')}40`, flexShrink: 0 }}>
                  {STATUS_LABELS[t.status] || t.status}
                </span>
              </div>
              <div style={{ display: 'flex', gap: 14, fontSize: 12, color: 'var(--text-2)' }}>
                {t.assigned_to_name && <span>👤 {t.assigned_to_name}</span>}
                {t.sla_resolution_status === 'breached' && <span style={{ color: 'var(--danger)', fontWeight: 700 }}>⚠ SLA roto</span>}
                {t.sla_resolution_status === 'warning' && <span style={{ color: 'var(--warning)' }}>⚠ SLA en riesgo</span>}
                <span>Hace {t.age_hours < 24 ? `${t.age_hours}h` : `${Math.floor(t.age_hours/24)}d`}</span>
              </div>
            </button>
          ))}
        </div>
      )}

      {/* New ticket modal */}
      {showNew && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.44)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: 20 }}>
          <div style={{ ...S.card, width: '100%', maxWidth: 560, maxHeight: '90vh', overflowY: 'auto' }}>
            <h3 style={{ fontSize: 18, fontWeight: 700, margin: '0 0 20px' }}>Nuevo ticket de soporte</h3>

            {/* Service catalog */}
            {catalog?.categories?.length > 0 && (
              <div style={{ marginBottom: 16 }}>
                <label style={S.label}>Selecciona el tipo de solicitud</label>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                  {catalog.categories.flatMap(cat => cat.services || []).map(svc => (
                    <button key={svc.id} onClick={() => setNewForm(f => ({ ...f, service_item_id: svc.id, ticket_type: svc.ticket_type, priority: svc.default_priority }))}
                      style={{ padding: '8px 14px', borderRadius: 8, border: `1px solid ${newForm.service_item_id === svc.id ? 'var(--accent-glow)' : 'var(--surface-4)'}`, background: newForm.service_item_id === svc.id ? 'var(--accent-muted)' : 'var(--portal-bg)', color: newForm.service_item_id === svc.id ? 'var(--accent)' : 'var(--text-2)', fontSize: 12, cursor: 'pointer', fontFamily: 'inherit' }}>
                      {svc.name}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <div><label style={S.label}>Título *</label><input value={newForm.title} onChange={e => setNewForm(f => ({ ...f, title: e.target.value }))} style={S.input} placeholder="Título del ticket" aria-label="Título del ticket" /></div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <div><label style={S.label}>Tipo</label>
                  <select value={newForm.ticket_type} onChange={e => setNewForm(f => ({ ...f, ticket_type: e.target.value }))} style={S.input}>
                    <option value="incident">🔴 Incidencia — algo no funciona</option>
                    <option value="service_request">📋 Solicitud de servicio</option>
                    <option value="question">❓ Consulta o duda</option>
                    <option value="change">🔀 Solicitud de cambio</option>
                  </select>
                </div>
                <div><label style={S.label}>Urgencia</label>
                  <select value={newForm.urgency} onChange={e => setNewForm(f => ({ ...f, urgency: e.target.value }))} style={S.input}>
                    <option value="critical">🚨 Crítica — no puedo trabajar</option>
                    <option value="high">🔴 Alta — impacto significativo</option>
                    <option value="medium">🟡 Media — trabajo reducido</option>
                    <option value="low">🟢 Baja — cuando podáis</option>
                  </select>
                </div>
              </div>
              <div><label style={S.label}>Descripción detallada *</label>
                <textarea value={newForm.description} onChange={e => setNewForm(f => ({ ...f, description: e.target.value }))} rows={5} style={{ ...S.input, resize: 'vertical' }} placeholder="Describe el problema o solicitud" aria-label="Descripción del ticket" />
              </div>
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
                <button onClick={() => setShowNew(false)} style={S.btnSec}>Cancelar</button>
                <button onClick={() => createTicket(newForm)} disabled={!newForm.title || !newForm.description} style={S.btn}>Enviar ticket</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
