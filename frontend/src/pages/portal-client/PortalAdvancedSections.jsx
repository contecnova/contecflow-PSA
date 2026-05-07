import { useId, useState, useEffect } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useToast } from '../../context/ToastContext'
import { BadgeWithTooltip } from '../../components/ui/BadgeWithTooltip'
import { IconCR } from '../../components/ui/FRCRIcons'
import { STATUS_CFG } from '../../constants/sharedStatus'
import { extractErr } from '../../utils/helpers'
import {
  CLIENT_API,
  useLang,
  useClientAuth,
  S,
  Badge,
} from './portalClientContext'
import { ClientGovernedConversationInbox } from '../../components/portal/GovernedConversations'

export function PortalUAT() {
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
    const hasFailure = Object.values(testResults).includes('failed')

    return (
      <div>
        <button onClick={() => setSelected(null)} style={{ ...S.btnSec, marginBottom: 20 }}>← Volver</button>
        <div style={{ marginBottom: 20 }}>
          <h3 style={{ fontSize: "var(--text-lg-em)", fontWeight: 700, margin: '0 0 8px' }}>{selected.title}</h3>
          {selected.description && <p style={{ color: 'var(--text-2)', margin: '0 0 8px' }}>{selected.description}</p>}
          {selected.test_environment && (
            <a href={selected.test_environment} target="_blank" rel="noopener noreferrer"
              style={{ display: 'inline-flex', alignItems: 'center', gap: 6, background: 'var(--accent-muted)', border: '1px solid var(--accent-border)', borderRadius: 8, padding: '8px 14px', color: 'var(--accent)', textDecoration: 'none', fontSize: "var(--text-base)", fontWeight: 600 }}>
              🔗 {_t('uat_run_case')}
            </a>
          )}
          {selected.test_credentials && <div style={{ marginTop: 8, fontSize: "var(--text-sm)", color: 'var(--text-2)', background: 'var(--surface-4)', borderRadius: 8, padding: '6px 12px' }}>🔑 {selected.test_credentials}</div>}
        </div>

        {selected.test_cases.length > 0 && (
          <div style={{ marginBottom: 20 }}>
            <h4 style={{ fontSize: "var(--text-md)", fontWeight: 700, margin: '0 0 12px', color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{_t('uat_cases')}</h4>
            {selected.test_cases.map(tc => (
              <div key={tc.id} style={{ ...S.card, marginBottom: 10 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: "var(--text-md)", fontWeight: 700, marginBottom: 4 }}>{tc.title}</div>
                    {tc.steps && <div style={{ fontSize: "var(--text-base)", color: 'var(--text-2)', marginBottom: 4 }}>📋 {tc.steps}</div>}
                    {tc.expected_result && <div style={{ fontSize: "var(--text-base)", color: 'var(--success)' }}>✓ {tc.expected_result}</div>}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  {[['passed', `✓ ${_t('uat_pass')}`, 'var(--success)'], ['failed', `✗ ${_t('uat_fail')}`, 'var(--danger)']].map(([val, label, color]) => (
                    <button key={val} onClick={() => setTestResults(r => ({ ...r, [tc.id]: val }))}
                      style={{ flex: 1, padding: '10px', borderRadius: 8, border: `2px solid ${testResults[tc.id] === val ? color : 'var(--surface-4)'}`, background: testResults[tc.id] === val ? color + '20' : 'transparent', color: testResults[tc.id] === val ? color : 'var(--text-2)', fontSize: "var(--text-base)", fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit', transition: 'all 0.15s' }}>
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
            <h4 style={{ fontSize: "var(--text-md)", fontWeight: 700, margin: '0 0 12px', color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{_t('uat_issue')}</h4>
            {selected.issues.map(issue => (
              <div key={issue.id} style={{ ...S.card, marginBottom: 8, border: `1px solid ${issue.status === 'open' ? 'var(--danger-border)' : 'var(--surface-4)'}` }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                  <span style={{ fontSize: "var(--text-base)", fontWeight: 600 }}>{issue.title}</span>
                  <span style={{ fontSize: "var(--text-xs)", color: issue.status === 'fixed' ? 'var(--success)' : 'var(--danger)' }}>{issue.status === 'fixed' ? `✓ ${_t('roadmap_completed')}` : `⚠ ${_t('ticket_status_new')}`}</span>
                </div>
                <p style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', margin: 0 }}>{issue.description}</p>
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
          <div role="dialog" aria-modal="true" aria-labelledby={`${issueIdPrefix}-issue-title`} style={{ ...S.card, marginTop: 20, border: '1px solid var(--danger-border)' }}>
            <h4 id={`${issueIdPrefix}-issue-title`} style={{ fontSize: "var(--text-md)", fontWeight: 700, margin: '0 0 14px', color: 'var(--danger)' }}>🐛 {_t('uat_issue')}</h4>
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
      <h3 style={{ fontSize: "var(--text-lg-em)", fontWeight: 700, margin: '0 0 20px' }}>{_t('uat_title')}</h3>
      {sessions.length === 0 ? (
        <div style={{ ...S.card, textAlign: 'center', padding: '40px 20px', color: 'var(--text-2)' }}>
          <div style={{ fontSize: "var(--text-5xl)", marginBottom: 12 }}>🧪</div>
          <div style={{ fontSize: "var(--text-lg)", fontWeight: 600 }}>{_t('uat_empty')}</div>
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
                    <div style={{ fontSize: "var(--text-md-em)", fontWeight: 700, marginBottom: 4 }}>{s.title}</div>
                    {s.deadline && <div style={{ fontSize: "var(--text-sm)", color: s.overdue ? 'var(--danger)' : 'var(--text-2)' }}>
                      {s.overdue ? '⚠ Vencido: ' : '📅 Plazo: '}{s.deadline}
                    </div>}
                  </div>
                  <Badge status={s.status} />
                </div>
                {s.stats.total > 0 && (
                  <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginBottom: 8 }}>
                    {s.stats.total} casos · {s.stats.passed} ✓ · {s.stats.failed} ✗
                  </div>
                )}
                {['pending', 'in_progress'].includes(s.status) && (
                  <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6, background: 'var(--accent-muted)', border: '1px solid var(--accent-border)', borderRadius: 8, padding: '6px 12px', fontSize: "var(--text-base)", color: 'var(--accent)', fontWeight: 600 }}>
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

export function PortalFeatureRequests() {
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
        <h3 style={{ fontSize: "var(--text-lg-em)", fontWeight: 700, margin: 0 }}>{_t('fr_title')}</h3>
        {client?.can_request_changes && <button onClick={() => setShowNew(true)} style={S.btn}>＋ {_t('fr_new')}</button>}
      </div>

      {isLoading ? null : frs.length === 0 ? (
        <div style={{ ...S.card, textAlign: 'center', padding: '40px 20px', color: 'var(--text-2)' }}>
          <div style={{ fontSize: "var(--text-5xl)", marginBottom: 12 }}>💡</div>
          <div style={{ fontSize: "var(--text-lg)", fontWeight: 600 }}>{_t('fr_empty')}</div>
          <p style={{ margin: '8px 0 0' }}>{_t('fr_subtitle')}</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {frs.map(fr => (
            <div key={fr.id} style={{ ...S.card, border: `1px solid ${fr.priority_color + '30'}` }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 4 }}>
                    <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', fontFamily: 'var(--font-mono)' }}>{fr.code}</span>
                    <span style={{ fontSize: "var(--text-md-em)", fontWeight: 700 }}>{fr.title}</span>
                  </div>
                  <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', fontSize: "var(--text-xs)", color: 'var(--text-3)', marginBottom: 8 }}>
                    {fr.project_name && <span>📁 {fr.project_name}</span>}
                    {fr.submitted_at && <span>{_t('created')}: {fr.submitted_at}</span>}
                    {fr.updated_at && <span>{_t('updated')}: {fr.updated_at}</span>}
                  </div>
                  <p style={{ fontSize: "var(--text-base)", color: 'var(--text-2)', margin: '0 0 8px' }}>{fr.description}</p>
                  {fr.pm_response && (
                    <div style={{ background: 'var(--portal-bg)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '10px 14px', fontSize: "var(--text-base)" }}>
                      <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', marginBottom: 6, textTransform: 'uppercase' }}>{_t('fr_desc')}</div>
                      <p style={{ margin: '0 0 8px' }}>{fr.pm_response}</p>
                      <div style={{ display: 'flex', gap: 16, fontSize: "var(--text-sm)" }}>
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
                  {fr.client_approved === true && <div style={{ marginTop: 8, fontSize: "var(--text-sm)", color: 'var(--success)' }}>{_t('fr_approved_by_client')} {fr.client_approved_at}</div>}
                  {fr.client_approved === false && <div style={{ marginTop: 8, fontSize: "var(--text-sm)", color: 'var(--danger)' }}>✗ {_t('fr_status_rejected')}</div>}
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
                      color={fr.cr_status_color || 'var(--text-3)'}
                      tooltip={`Estado de la Change Request vinculada.`}
                      icon={<IconCR />}
                    />
                  ) : (
                    <BadgeWithTooltip
                      label={'Sin CR'}
                      color="var(--text-3)"
                      tooltip={'No se ha generado Change Request. Se crea automáticamente al aprobar la FR por el cliente.'}
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
            <h3 id={`${formIdPrefix}-title`} style={{ fontSize: "var(--text-lg-em)", fontWeight: 700, margin: '0 0 20px' }}>{editingFr ? _t('fr_edit_modal_title') : _t('fr_new')}</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              {(client?.projects?.length > 1 || client?.project_ids?.length > 1) && (
                <div>
                  <label htmlFor={`${formIdPrefix}-project`} style={S.label}>{_t('fr_project_label')}</label>
                  <select id={`${formIdPrefix}-project`} value={form.project_id} onChange={e => setForm(f => ({ ...f, project_id: e.target.value }))} style={S.input}>
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
                  disabled={!form.title || !form.description || ((client?.projects?.length > 1 || client?.project_ids?.length > 1) && !form.project_id)}
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

export function PortalMessages() {
  const t = useLang()
  const { client } = useClientAuth()
  const projectOptions = Array.isArray(client?.projects)
    ? client.projects.map((project) => ({ id: project.id, name: project.name || project.code || project.id, code: project.code || '' }))
    : []
  const fallbackProject = client?.project_id
    ? [{ id: client.project_id, name: client.project_id, code: '' }]
    : []

  return (
    <ClientGovernedConversationInbox
      title={t('messages_team_title')}
      emptyTitle={t('messages_empty')}
      emptyDescription={t('messages_empty')}
      projectOptions={projectOptions.length ? projectOptions : fallbackProject}
      initialProjectId={client?.project_id || ''}
    />
  )
}

export function PortalInvoices() {
  const t = useLang()
  const toast = useToast()
  const qc = useQueryClient()
  const defaultCurrency = 'EUR'
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

  const fmtMoney = (amount, currency) => {
    const value = Number(amount || 0)
    if (!currency) return value.toLocaleString('es-ES')
    return value.toLocaleString('es-ES', { style: 'currency', currency })
  }

  if (isLoading) return <div style={{ color: 'var(--text-2)', textAlign: 'center', padding: 40 }}>{t('invoices_loading')}</div>

  return (
    <div>
      <div style={{ marginBottom: 20 }}>
        <h2 style={{ fontSize: "var(--text-xl-em)", fontWeight: 800, marginBottom: 4 }}>{t('invoices_title')}</h2>
        <p style={{ color: 'var(--text-2)', fontSize: "var(--text-md)", margin: 0 }}>{t('invoices_subtitle')}</p>
      </div>

      {invoices.length === 0 ? (
        <div style={{ ...S.card, textAlign: 'center', padding: '44px 20px' }}>
          <div style={{ fontSize: "var(--text-38)", marginBottom: 12 }}>🧾</div>
          <div style={{ color: 'var(--text-2)', fontSize: "var(--text-md)" }}>{t('invoices_empty')}</div>
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
                    <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', fontFamily: 'var(--font-mono)' }}>#{inv.number || inv.id}</div>
                    <div style={{ fontSize: "var(--text-lg)", fontWeight: 700 }}>{inv.client_name || t('invoices_title')}</div>
                    <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>{t('invoices_issued')}: {inv.issue_date || '—'} · {t('invoices_due')}: {inv.due_date || '—'}</div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: "var(--text-xl)", fontWeight: 800, color: 'var(--text-1)' }}>{fmtMoney(inv.total, inv.currency || defaultCurrency)}</div>
                    <span style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: statusColor, background: `${statusColor}20`, border: `1px solid ${statusColor}40`, borderRadius: 20, padding: '2px 8px', textTransform: 'uppercase' }}>
                      {inv.status}
                    </span>
                  </div>
                </div>

                <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginBottom: 10 }}>
                  Base: {fmtMoney(inv.subtotal, inv.currency || defaultCurrency)} · IVA: {fmtMoney(inv.tax_amount, inv.currency || defaultCurrency)}
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
                    style={{ ...S.btn, background: 'linear-gradient(135deg, var(--success), #60a5fa)' }}
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

export function PortalRoadmap() {
  const _t = useLang()
  const { data, isLoading, error } = useQuery({
    queryKey: ['portal-project'],
    queryFn: () => CLIENT_API.get('/portal/project').then(r => r.data).catch(e => {
      if (e?.response?.status === 404 || e?.response?.status === 403) return null
      throw e
    }),
  })

  const milestones = data?.milestones || []
  const deliverables = data?.deliverables || []

  if (isLoading) return (
    <div style={{ textAlign: 'center', padding: '60px 0', color: 'var(--text-2)' }}>
      <div style={{ fontSize: "var(--text-3xl-em)", marginBottom: 12 }}>🗺️</div>
      {_t('roadmap_loading')}
    </div>
  )

  if (!data || error) return (
    <div style={{ textAlign: 'center', padding: '60px 20px', color: 'var(--text-2)' }}>
      <div style={{ fontSize: "var(--text-5xl)", marginBottom: 12 }}>🗺️</div>
      <div style={{ fontSize: "var(--text-md-em)", fontWeight: 700, marginBottom: 6 }}>{_t('roadmap_no_project')}</div>
      <div style={{ fontSize: "var(--text-base)" }}>{_t('roadmap_no_project_hint')}</div>
    </div>
  )

  return (
    <div>
      <h3 style={{ fontSize: "var(--text-lg-em)", fontWeight: 700, margin: '0 0 20px' }}>{_t('roadmap_title')}</h3>

      {milestones.length === 0 && deliverables.length === 0 && (
        <div style={{ textAlign: 'center', padding: '40px 20px', color: 'var(--text-2)', background: 'var(--surface-2)', borderRadius: 12, border: '1px solid var(--surface-4)' }}>
          <div style={{ fontSize: "var(--text-3xl-em)", marginBottom: 8 }}>📋</div>
          <div style={{ fontSize: "var(--text-md)", fontWeight: 600, marginBottom: 4 }}>{_t('roadmap_no_items')}</div>
          <div style={{ fontSize: "var(--text-sm)" }}>{_t('roadmap_no_items_hint')}</div>
        </div>
      )}

      {(milestones.length > 0 || deliverables.length > 0) && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
          <div>
            <h4 style={{ fontSize: "var(--text-base)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', margin: '0 0 14px' }}>{_t('roadmap_milestones_title')}</h4>
            {milestones.length === 0 ? (
              <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', padding: '12px 0' }}>{_t('roadmap_no_milestones')}</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {milestones.map((m, i) => (
                  <div key={m.id} style={{ display: 'flex', gap: 14, alignItems: 'flex-start' }}>
                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                      <div style={{ width: 28, height: 28, borderRadius: '50%', background: m.is_completed ? 'var(--success)' : 'var(--surface-4)', border: `2px solid ${m.is_completed ? 'var(--success)' : 'var(--surface-4)'}`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: "var(--text-sm)", color: m.is_completed ? 'var(--portal-bg)' : 'var(--text-2)', fontWeight: 700, flexShrink: 0 }}>
                        {m.is_completed ? '✓' : i + 1}
                      </div>
                      {i < milestones.length - 1 && <div style={{ width: 2, height: 24, background: m.is_completed ? 'var(--success-border)' : 'var(--surface-4)', margin: '4px 0' }} />}
                    </div>
                    <div style={{ paddingTop: 4 }}>
                      <div style={{ fontSize: "var(--text-base)", fontWeight: 700, color: m.is_completed ? 'var(--text-2)' : 'var(--text-1)', textDecoration: m.is_completed ? 'line-through' : 'none' }}>{m.name}</div>
                      {m.due_date && <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginTop: 2 }}>📅 {m.due_date}</div>}
                      {m.billing_pct && <div style={{ fontSize: "var(--text-xs)", color: 'var(--warning)' }}>💶 {m.billing_pct}{_t('roadmap_billing_pct')}</div>}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
          <div>
            <h4 style={{ fontSize: "var(--text-base)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', margin: '0 0 14px' }}>{_t('roadmap_deliverables_title')}</h4>
            {deliverables.length === 0 ? (
              <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', padding: '12px 0' }}>{_t('roadmap_no_deliverables')}</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {deliverables.map(d => (
                  <div key={d.id} style={{ ...S.card, padding: '12px 16px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                      <div>
                        <div style={{ fontSize: "var(--text-base)", fontWeight: 700 }}>{d.name}</div>
                        {d.format && <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>{d.format}</div>}
                        {d.planned_date && <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>{_t('updated')}: {d.planned_date}</div>}
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

export function PortalDocuments() {
  const t = useLang()
  const toast = useToast()
  const qc = useQueryClient()
  const { data: docs = [] } = useQuery({ queryKey: ['portal-docs-client'], queryFn: () => CLIENT_API.get('/portal/documents').then(r => r.data) })
  const [signModal, setSignModal] = useState(null)
  const [signJobTitle, setSignJobTitle] = useState('')
  const [signedPdfB64, setSignedPdfB64] = useState(null)

  const { mutate: sign, isPending: signing } = useMutation({
    mutationFn: ({ id, job_title }) => CLIENT_API.post(`/portal/documents/${id}/sign`, { job_title }).then(r => r.data),
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

  useEffect(() => {
    if (signedPdfB64) {
      const bytes = atob(signedPdfB64.b64)
      const arr = new Uint8Array(bytes.length)
      for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i)
      const blob = new Blob([arr], { type: 'application/pdf' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `Firmado_${signedPdfB64.title.replace(/\s+/g, '_').slice(0, 40)}.pdf`
      a.click()
      URL.revokeObjectURL(url)
      setSignedPdfB64(null)
      toast.success('✓ Documento firmado. Se ha descargado el certificado PDF.')
    }
  }, [signedPdfB64, toast])

  return (
    <div>
      <h3 style={{ fontSize: "var(--text-lg-em)", fontWeight: 700, margin: '0 0 20px' }}>{t('doc_title')}</h3>
      {docs.length === 0 ? (
        <div style={{ ...S.card, textAlign: 'center', padding: '40px 20px', color: 'var(--text-2)' }}>
          <div style={{ fontSize: "var(--text-5xl)", marginBottom: 12 }}>📄</div>
          <p>{t('doc_empty')}</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {docs.map(doc => (
            <div key={doc.id} style={{ ...S.card, display: 'flex', gap: 14, alignItems: 'center' }}>
              <span style={{ fontSize: "var(--text-2xl)" }}>{CAT_ICONS[doc.category] || '📄'}</span>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: "var(--text-md)", fontWeight: 700 }}>{doc.title}</div>
                {doc.description && <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>{doc.description}</div>}
                <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginTop: 2 }}>{doc.file_name || doc.category} · {doc.created_at}</div>
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                {doc.requires_signature && !doc.signed_by_client && (
                  <button onClick={() => { setSignModal({ id: doc.id, title: doc.title }); setSignJobTitle('') }}
                    style={{ ...S.btn, padding: '7px 14px', fontSize: "var(--text-sm)", background: 'var(--success-bg)', borderColor: 'var(--success-border)', color: 'var(--success)' }}>
                    {t('doc_sign_modal_title')}
                  </button>
                )}
                {doc.signed_by_client && (
                  <span style={{ fontSize: "var(--text-xs)", padding: '3px 8px', borderRadius: 4, background: 'var(--success-bg)', color: 'var(--success)', fontWeight: 600 }}>
                    {t('doc_signed_on')} {doc.signed_at?.slice(0, 10) || ''}
                  </span>
                )}
                {doc.file_url && <a href={doc.file_url} target="_blank" rel="noopener noreferrer" style={{ ...S.btnSec, padding: '7px 12px', fontSize: "var(--text-sm)", textDecoration: 'none' }}>{t('doc_download_btn')}</a>}
              </div>
            </div>
          ))}
        </div>
      )}

      {signModal && (
        <div role="presentation" onMouseDown={() => setSignModal(null)} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 9999, padding: 20 }}>
          <div role="dialog" aria-modal="true" aria-labelledby="sign-modal-title" onMouseDown={e => e.stopPropagation()} style={{ background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 16, padding: '28px 32px', maxWidth: 460, width: '100%', boxShadow: '0 24px 64px rgba(0,0,0,0.8)' }}>
            <div id="sign-modal-title" style={{ fontSize: "var(--text-lg-em)", fontWeight: 800, marginBottom: 8 }}>{t('doc_sign_modal_title')}</div>
            <div style={{ fontSize: "var(--text-base)", color: 'var(--text-2)', marginBottom: 20, lineHeight: 1.5 }}>
              {t('doc_sign_about')}: <strong style={{ color: 'var(--text-1)' }}>{signModal.title}</strong>.
            </div>

            <div style={{ marginBottom: 16 }}>
              <label style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', display: 'block', marginBottom: 6 }}>
                {t('doc_job_title_label')}
              </label>
              <input value={signJobTitle} onChange={e => setSignJobTitle(e.target.value)} placeholder={t('doc_job_title_label')}
                style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", width: '100%', outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }}
              />
            </div>

            <div style={{ background: 'var(--success-bg)', border: '1px solid var(--success-border)', borderRadius: 8, padding: '10px 14px', marginBottom: 20, fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>
              📄 {t('doc_sign_pdf_info')}
            </div>

            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
              <button onClick={() => setSignModal(null)}
                style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 20px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-base)", fontFamily: 'inherit' }}>
                {t('cancel')}
              </button>
              <button onClick={() => sign({ id: signModal.id, job_title: signJobTitle })} disabled={signing}
                style={{ background: signing ? 'var(--surface-4)' : 'var(--success)', border: 'none', borderRadius: 8, padding: '9px 24px', color: 'var(--surface-0)', cursor: signing ? 'wait' : 'pointer', fontSize: "var(--text-base)", fontWeight: 700, fontFamily: 'inherit', opacity: signing ? 0.7 : 1 }}>
                {signing ? t('doc_signing') : t('doc_confirm_sign')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export function PortalWiki() {
  const t = useLang()
  const [selected, setSelected] = useState(null)
  const [wikiTab, setWikiTab] = useState('docs')
  const [searchKB, setSearchKB] = useState('')

  const { data: pages = [], isLoading } = useQuery({
    queryKey: ['portal-wiki-pages'],
    queryFn: () => CLIENT_API.get('/portal/wiki/pages').then(r => r.data),
  })
  const { data: pageDetail } = useQuery({
    queryKey: ['portal-wiki-page', selected],
    queryFn: () => CLIENT_API.get(`/portal/wiki/pages/${selected}`).then(r => r.data),
    enabled: !!selected,
  })
  const { data: kbArticles = [], isLoading: loadingKB } = useQuery({
    queryKey: ['portal-wiki-kb', searchKB],
    queryFn: () => CLIENT_API.get('/sd/kb', { params: { public_only: true, search: searchKB || undefined } }).then(r => r.data),
    enabled: wikiTab === 'kb',
  })

  if (isLoading) return <div style={{ color: 'var(--text-2)', padding: 40, textAlign: 'center' }}>{t('wiki_loading')}</div>

  const tabBtn = (active) => ({
    padding: '7px 16px', borderRadius: 8,
    border: `1px solid ${active ? 'var(--accent)' : 'var(--surface-4)'}`,
    background: active ? 'var(--accent-muted)' : 'transparent',
    color: active ? 'var(--accent)' : 'var(--text-2)',
    fontSize: "var(--text-sm)", fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit', whiteSpace: 'nowrap',
  })

  return (
    <div>
      <h2 style={{ fontSize: "var(--text-xl-em)", fontWeight: 800, marginBottom: 4 }}>{t('nav_wiki')}</h2>
      <p style={{ color: 'var(--text-2)', fontSize: "var(--text-md)", marginBottom: 20 }}>{t('wiki_subtitle')}</p>

      {/* Tab switcher */}
      <div role="tablist" aria-label={t('nav_wiki')} style={{ display: 'flex', gap: 8, marginBottom: 24, borderBottom: '1px solid var(--surface-4)', paddingBottom: 16 }}>
        <button role="tab" aria-selected={wikiTab === 'docs'} aria-controls="wiki-panel-docs" id="wiki-tab-docs"
          onClick={() => { setWikiTab('docs'); setSelected(null) }} style={tabBtn(wikiTab === 'docs')}>{t('wiki_tab_docs')}</button>
        <button role="tab" aria-selected={wikiTab === 'kb'} aria-controls="wiki-panel-kb" id="wiki-tab-kb"
          onClick={() => setWikiTab('kb')} style={tabBtn(wikiTab === 'kb')}>{t('wiki_tab_kb')}</button>
      </div>

      {/* Docs tab */}
      {wikiTab === 'docs' && (
        <div id="wiki-panel-docs" role="tabpanel" aria-labelledby="wiki-tab-docs">
          {selected && pageDetail ? (
            <div style={S.card}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
                <button onClick={() => setSelected(null)} style={{ ...S.btnSec, padding: '6px 14px', fontSize: "var(--text-sm)" }}>← {t('back')}</button>
                <h3 style={{ fontSize: "var(--text-lg-em)", fontWeight: 700, margin: 0 }}>{pageDetail.title}</h3>
              </div>
              <div style={{ color: 'var(--text-2)', fontSize: "var(--text-md)", lineHeight: 1.7 }}>
                {(pageDetail.content || []).map((block, i) => {
                  if (block.type === 'heading1') return <h1 key={i} style={{ fontSize: "var(--text-xl-em)", fontWeight: 800, margin: '20px 0 10px' }}>{block.content}</h1>
                  if (block.type === 'heading2') return <h2 key={i} style={{ fontSize: "var(--text-lg-em)", fontWeight: 700, margin: '18px 0 8px', color: 'var(--accent)' }}>{block.content}</h2>
                  if (block.type === 'heading3') return <h3 key={i} style={{ fontSize: "var(--text-md-em)", fontWeight: 700, margin: '14px 0 6px' }}>{block.content}</h3>
                  if (block.type === 'bullet') return <li key={i} style={{ marginLeft: 20, marginBottom: 4 }}>{block.content}</li>
                  if (block.type === 'code') return <pre key={i} style={{ background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '12px 16px', fontSize: "var(--text-sm)", overflow: 'auto', marginBottom: 12 }}>{block.content}</pre>
                  if (block.type === 'callout') return <div key={i} style={{ background: 'var(--accent-muted)', border: '1px solid var(--accent-border)', borderRadius: 8, padding: '12px 16px', marginBottom: 12 }}>{block.content}</div>
                  if (block.type === 'separator') return <hr key={i} style={{ border: 'none', borderTop: '1px solid var(--surface-4)', margin: '16px 0' }} />
                  return <p key={i} style={{ marginBottom: 10 }}>{block.content}</p>
                })}
              </div>
              <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', marginTop: 20 }}>
                {t('last_updated')}: {new Date(pageDetail.updated_at).toLocaleDateString()}
              </div>
            </div>
          ) : (
            <div>
              {pages.length === 0 ? (
                <div style={{ ...S.card, textAlign: 'center', padding: 48 }}>
                  <div style={{ fontSize: "var(--text-5xl)", marginBottom: 16 }}>📚</div>
                  <div style={{ color: 'var(--text-2)', fontSize: "var(--text-md)" }}>{t('wiki_empty')}</div>
                </div>
              ) : (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 14 }}>
                  {pages.map(p => (
                    <button key={p.id} type="button" onClick={() => setSelected(p.id)} style={{ ...S.card, cursor: 'pointer', transition: 'border-color 0.15s' }}
                      onMouseEnter={e => e.currentTarget.style.borderColor = 'var(--accent-glow)'}
                      onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--surface-4)'}>
                      <div style={{ fontSize: "var(--text-xl)", marginBottom: 10 }}>📄</div>
                      <div style={{ fontSize: "var(--text-md-em)", fontWeight: 700, marginBottom: 6 }}>{p.title}</div>
                      <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>
                        {t('last_updated')}: {new Date(p.updated_at).toLocaleDateString()}
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* KB Articles tab */}
      {wikiTab === 'kb' && (
        <div id="wiki-panel-kb" role="tabpanel" aria-labelledby="wiki-tab-kb">
          <div style={{ marginBottom: 16 }}>
            <input aria-label={t('wiki_kb_search')} value={searchKB}
              onChange={e => setSearchKB(e.target.value)}
              placeholder={t('wiki_kb_search')}
              style={{ ...S.input, fontSize: "var(--text-md)", padding: '12px 16px' }} />
          </div>
          {loadingKB ? (
            <div style={{ color: 'var(--text-2)', padding: 40, textAlign: 'center' }}>{t('wiki_loading')}</div>
          ) : kbArticles.length === 0 ? (
            <div style={{ ...S.card, textAlign: 'center', padding: 48 }}>
              <div style={{ fontSize: "var(--text-5xl)", marginBottom: 16 }}>🔍</div>
              <div style={{ color: 'var(--text-2)', fontSize: "var(--text-md)" }}>{t('wiki_kb_empty')}</div>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {kbArticles.map(a => (
                <div key={a.id} style={{ ...S.card }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                    <span style={{ fontSize: "var(--text-md-em)", fontWeight: 700 }}>{a.title}</span>
                    <span style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>👁 {a.view_count} · ✓ {a.helpful_count}</span>
                  </div>
                  {a.summary && <p style={{ fontSize: "var(--text-base)", color: 'var(--text-2)', margin: '0 0 10px' }}>{a.summary}</p>}
                  {a.tags && <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>🏷 {a.tags}</div>}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export function PortalStats() {
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
  const uatPending = uats.filter(u => ['pending', 'in_progress'].includes(u.status)).length

  const KPI = ({ icon, label, value, sub, color = 'var(--accent)' }) => (
    <div style={{ ...S.card, padding: '16px 18px' }}>
      <div style={{ fontSize: "var(--text-xl-em)", marginBottom: 8 }}>{icon}</div>
      <div style={{ fontSize: "var(--text-xl-em)", fontWeight: 800, color, marginBottom: 2, fontFamily: 'var(--font-mono)' }}>{value}</div>
      <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, marginBottom: 2 }}>{label}</div>
      {sub && <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>{sub}</div>}
    </div>
  )

  const ProgressBar = ({ value, color = 'var(--accent)' }) => (
    <div style={{ height: 8, background: 'var(--surface-4)', borderRadius: 4, overflow: 'hidden' }}>
      <div style={{ height: '100%', width: `${Math.min(100, value)}%`, background: color, borderRadius: 4, transition: 'width 0.6s' }} />
    </div>
  )

  return (
    <div>
      <h2 style={{ fontSize: "var(--text-lg-em)", fontWeight: 800, marginBottom: 4 }}>{t('nav_stats')}</h2>
      <p style={{ color: 'var(--text-2)', fontSize: "var(--text-sm)", marginBottom: 20 }}>{t('stats_subtitle')}</p>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 14, marginBottom: 24 }}>
        <KPI icon="📈" label={t('stats_progress')} value={`${progress}%`} color="#4f8ef7" sub={`${tasks_done}/${tasks_total} tareas`} />
        <KPI icon="💰" label={t('stats_budget')} value={`${budget_used}%`} color={budget_used > 90 ? 'var(--danger)' : budget_used > 75 ? 'var(--warning)' : 'var(--success)'} sub={t('stats_budget_used')} />
        <KPI icon="🧪" label={t('nav_uat')} value={uatPassed} color="var(--success)" sub={`${uatFailed} rechazadas`} />
        <KPI icon="💡" label={t('nav_requests')} value={frs.length} color="#a78bfa" sub={`${frs.filter(f => f.status === 'approved').length} aprobadas`} />
        <KPI icon="📄" label={t('nav_documents')} value={docs.length} color="var(--warning)" sub={`${docs.filter(d => d.is_signed).length} firmados`} />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 24 }}>
        <div style={{ ...S.card, padding: '20px 22px' }}>
          <h3 style={{ fontSize: "var(--text-base)", fontWeight: 700, marginBottom: 16 }}>Avance del proyecto</h3>
          <div style={{ marginBottom: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: "var(--text-sm)", marginBottom: 6 }}>
              <span>Progreso general</span><span style={{ color: 'var(--accent)', fontWeight: 700 }}>{progress}%</span>
            </div>
            <ProgressBar value={progress} />
          </div>
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: "var(--text-sm)", marginBottom: 6 }}>
              <span>Presupuesto consumido</span>
              <span style={{ color: budget_used > 90 ? 'var(--danger)' : 'var(--warning)', fontWeight: 700 }}>{budget_used}%</span>
            </div>
            <ProgressBar value={budget_used} color={budget_used > 90 ? 'var(--danger)' : 'var(--warning)'} />
          </div>
        </div>

        <div style={{ ...S.card, padding: '20px 22px' }}>
          <h3 style={{ fontSize: "var(--text-base)", fontWeight: 700, marginBottom: 16 }}>Estado UATs</h3>
          {[
            { label: 'Aprobadas', value: uatPassed, total: uats.length, color: 'var(--success)' },
            { label: 'En progreso', value: uatPending, total: uats.length, color: 'var(--accent)' },
            { label: 'Rechazadas', value: uatFailed, total: uats.length, color: 'var(--danger)' },
          ].map(row => (
            <div key={row.label} style={{ marginBottom: 10 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: "var(--text-sm)", marginBottom: 5 }}>
                <span>{row.label}</span>
                <span style={{ color: row.color, fontWeight: 700 }}>{row.value}/{uats.length}</span>
              </div>
              <ProgressBar value={uats.length ? (row.value / uats.length) * 100 : 0} color={row.color} />
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
