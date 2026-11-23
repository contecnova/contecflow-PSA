// Pestaña de sesiones UAT del portal de cliente (lista, alta y detalle). 23-11-2026: troceado de ClientPortalPage sin cambio de comportamiento.
import React, { useState } from 'react'
import type { CSSProperties } from 'react'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { portalApi, deliverablesApi } from '../services/api'
import type { Entregable } from '../services/api/tipos-alm'
import { Button, IconButton, Modal, Pulsable, Select, Spinner, EmptyState, useErroresDeCampo, Input, Textarea } from '../components/ui'
import { FlaskConical, Plus, Check, AlertTriangle, CheckCircle2, XCircle, Bug, X, Link2, Minus } from 'lucide-react'
import { fmtDate, extractErr } from '../utils/helpers'
import { STATUS_CFG } from '../constants/sharedStatus'
import { useAppT } from '../i18n/AppLangContext'
import { useFormValidation } from '../hooks/useFormValidation'
import DateInput from '../components/ui/DateInput'
import { isSafeUrl, sanitizeUrl } from '../utils/security'
import { type CasoNuevo, type EventoDeCampo, type FormUat, MensajeError, type SesionUat, StatusBadge, colorVar, crearEsquemaUat, propsDeError } from './ClientPortalComun'

export function UATTab({ projectId }: { projectId: string }) {
  const t = useAppT()
  const [showCreate, setShowCreate] = useState(false)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const { data: sessions = [], isLoading } = useQuery({
    queryKey: ['uat-team', projectId],
    queryFn: () => portalApi.uat({ project_id: projectId }).then(r => r.data),
    enabled: !!projectId,
  })
  const { data: deliverables = [] } = useQuery({
    queryKey: ['deliverables-uat', projectId],
    queryFn: () => deliverablesApi.listByProject(projectId).then(r => r.data.deliverables || []),
    enabled: !!projectId,
  })
  // Always read live data so UATDetailModal reflects updates without reopening
  const selectedSession = selectedId ? (sessions.find(s => s.id === selectedId) ?? null) : null

  return (
    <div>
      <div className="cpp-tab-head">
        <div className="u-text2-base">{sessions.length} {t('client_portal.uat_sessions_count')}</div>
        {projectId && <Button onClick={() => setShowCreate(true)} icon={<Plus size={14} />}>{t('client_portal.uat_new_session')}</Button>}
      </div>
      {isLoading ? <Spinner /> : sessions.length === 0 ? (
        <EmptyState svgIcon={<FlaskConical size={36} />} title={t('client_portal.uat_empty_title')} description={t('client_portal.uat_empty_desc')} />
      ) : (
        <div className="u-stack-10">
          {sessions.map(s => (
            <Pulsable key={s.id}
              className={STATUS_CFG[s.status] ? 'cpp-uat has-color' : 'cpp-uat'}
              style={STATUS_CFG[s.status] ? colorVar(STATUS_CFG[s.status].color) : undefined}
              onClick={() => setSelectedId(s.id)}>
              <div className="cpp-row-top cpp-row-top--mb">
                <div>
                  <div className="cpp-title-row">
                    <span className="u-text2-mono-xs">{s.code}</span>
                    <span className="u-md-700">{s.title}</span>
                    {s.overdue && <span className="cpp-overdue cpp-con-icono"><AlertTriangle size={12} aria-hidden="true" />{t('client_portal.uat_overdue')}</span>}
                  </div>
                  <div className="u-text2-sm cpp-con-icono">
                    {s.deadline && `${t('client_portal.uat_deadline')}: ${fmtDate(s.deadline)} · `}
                    {s.stats.total} {t('client_portal.uat_cases')} ·
                    <CheckCircle2 size={12} className="u-success" aria-label={t('clientportalpage.estado_passed')} />{s.stats.passed} ·
                    <XCircle size={12} className="u-danger" aria-label={t('clientportalpage.estado_failed')} />{s.stats.failed}
                  </div>
                </div>
                <StatusBadge status={s.status} cfg={STATUS_CFG} />
              </div>
              {s.stats.total > 0 && (
                <div className="cpp-progress" aria-hidden="true">
                  <div className="cpp-progress__bar" style={{ '--cpp-pct': `${(s.stats.passed / s.stats.total) * 100}%` } as CSSProperties} />
                </div>
              )}
              {s.issues.length > 0 && (
                <div className="cpp-uat__issues cpp-con-icono">
                  <Bug size={12} aria-hidden="true" />{`${s.issues.filter(i => i.status === 'open').length} ${t('client_portal.uat_open_issues')}`}
                </div>
              )}
            </Pulsable>
          ))}
        </div>
      )}
      {showCreate && projectId && <CreateUATModal projectId={projectId} deliverables={deliverables} onClose={() => setShowCreate(false)} />}
      {selectedSession && <UATDetailModal session={selectedSession} onClose={() => setSelectedId(null)} />}
    </div>
  )
}

function CreateUATModal({ projectId, deliverables, onClose }: { projectId: string; deliverables: Entregable[]; onClose: () => void }) {
  const idCampo = React.useId()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [form, setForm] = useState<Required<FormUat>>({ title: '', description: '', deliverable_id: '', test_environment: '', test_credentials: '', test_guide_url: '', available_from: '', deadline: '' })
  const [testCases, setTestCases] = useState<CasoNuevo[]>([{ title: '', steps: '', expected_result: '' }])
  const esquema = React.useMemo(() => crearEsquemaUat(t), [t])
  const validation = useFormValidation(esquema)
  const errs = validation.errors as Record<string, string | undefined>
  const err = (k: string) => propsDeError(errs, k, idCampo)
  const msg = (k: string) => (campos.de(k) ? <div className="u-field-error">{campos.de(k)}</div> : <MensajeError errors={errs} campo={k} idBase={idCampo} />)
  const set = (k: keyof FormUat) => (e: EventoDeCampo) => {
    setForm(f => ({ ...f, [k]: e.target.value }))
    validation.clearFieldError(k)
  }

  const campos = useErroresDeCampo()
  const { mutate, isPending } = useMutation({
    onMutate: () => campos.limpiar(),
    mutationFn: async (data: { form: FormUat; testCases: CasoNuevo[] }) => {
      const res = await portalApi.createUat(projectId, data.form)
      for (const tc of data.testCases.filter(t => t.title)) {
        await portalApi.addTestCase(res.data.id, { title: tc.title, steps: tc.steps, expected_result: tc.expected_result, order: data.testCases.indexOf(tc) })
      }
      return res
    },
    onSuccess: () => { validation.setErrors({}); qc.invalidateQueries({ queryKey: ['uat-team', projectId] }); onClose() },
    onError: (e: unknown) => { if (!campos.recoger(e)) toast.error(extractErr(e, t('ai.generic_error'))) },
  })

  const submit = () => {
    const result = validation.validateForm(form)
    if (!result.success) return
    mutate({ form: result.data, testCases })
  }

  return (
    <Modal open title={t('client_portal.uat_modal_new_title')} onClose={onClose} width={680}>
      <div className="u-stack-14">
        <div className="cpp-grid-2-1">
          <div>
            <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="cpp-label">{t('client_portal.uat_label_title')} *</label>
            <Input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.title} onChange={set('title')} inputClassName="cpp-input" placeholder={t('client_portal.uat_placeholder_title')} {...err('title')} />{msg('title')}
            {msg('title')}
          </div>
          <div><label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="cpp-label">{t('client_portal.uat_label_deliverable')}</label>
            <Select suelto id={`${idCampo}-2`} placeholder={t('client_portal.uat_unlinked')} value={form.deliverable_id} onChange={set('deliverable_id')} className="cpp-input">
              {deliverables.map(d => <option key={d.id} value={d.id}>{d.code} — {d.name}</option>)}
            </Select>{msg('deliverable_id')}
          </div>
        </div>
        <div><label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="cpp-label">{t('client_portal.uat_label_description')}</label><Textarea id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={form.description} onChange={set('description')} rows={2} inputClassName="cpp-input" />{msg('description')}</div>
        <div className="u-grid2-12">
          <div><label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="cpp-label">{t('client_portal.uat_label_test_env_url')}</label><Input id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={form.test_environment} onChange={set('test_environment')} placeholder={t('client_portal.uat_placeholder_test_env_url')} inputClassName="cpp-input" />{msg('test_environment')}</div>
          <div><label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} className="cpp-label">{t('client_portal.uat_label_test_credentials')}</label><Input id={`${idCampo}-5`} aria-labelledby={`${idCampo}-et5`} value={form.test_credentials} onChange={set('test_credentials')} placeholder={t('client_portal.uat_placeholder_test_credentials')} inputClassName="cpp-input" />{msg('test_credentials')}</div>
          <div><label id={`${idCampo}-et6`} htmlFor={`${idCampo}-6`} className="cpp-label">{t('client_portal.uat_label_available_from')}</label><DateInput id={`${idCampo}-6`} value={form.available_from} onChange={set('available_from')} className="cpp-input" {...err('available_from')} />{msg('available_from')}</div>
          <div>
            <label id={`${idCampo}-et7`} htmlFor={`${idCampo}-7`} className="cpp-label">{t('client_portal.uat_label_deadline')}</label>
            <DateInput id={`${idCampo}-7`} value={form.deadline} onChange={set('deadline')} className="cpp-input" {...err('deadline')} />{msg('deadline')}
            {msg('deadline')}
          </div>
        </div>

        <div>
          <div className="cpp-subtitle-accent">{t('client_portal.uat_test_cases')}</div>
          {testCases.map((tc, i) => (
            <div key={i} className="cpp-case">
              <Input aria-label={t('client_portal.uat_test_case_title_placeholder', { index: i + 1 })} value={tc.title} onChange={e => setTestCases(tcs => tcs.map((c, j) => j === i ? { ...c, title: e.target.value } : c))} placeholder={t('client_portal.uat_test_case_title_placeholder', { index: i + 1 })} inputClassName="cpp-input" />{msg('title')}
              <Input aria-label={t('client_portal.uat_test_case_steps_placeholder')} value={tc.steps} onChange={e => setTestCases(tcs => tcs.map((c, j) => j === i ? { ...c, steps: e.target.value } : c))} placeholder={t('client_portal.uat_test_case_steps_placeholder')} inputClassName="cpp-input" />{msg('steps')}
              <Input aria-label={t('client_portal.uat_test_case_expected_placeholder')} value={tc.expected_result} onChange={e => setTestCases(tcs => tcs.map((c, j) => j === i ? { ...c, expected_result: e.target.value } : c))} placeholder={t('client_portal.uat_test_case_expected_placeholder')} inputClassName="cpp-input" />{msg('expected_result')}
              <IconButton onClick={() => setTestCases(tcs => tcs.filter((_, j) => j !== i))} className="cpp-case__remove"
                ariaLabel={t('clientportalpage.quitar_caso', { index: i + 1 })}><X size={14} aria-hidden="true" /></IconButton>
            </div>
          ))}
          <Button variant="secondary" size="sm" icon={<Plus size={14} />} onClick={() => setTestCases(tcs => [...tcs, { title: '', steps: '', expected_result: '' }])}>
            {t('client_portal.uat_add_test_case')}
          </Button>
        </div>

        <div className="cpp-actions">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={submit} disabled={isPending} loading={isPending}>
            {isPending ? t('client_portal.uat_creating_session') : t('client_portal.uat_create_session')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

function UATDetailModal({ session: initialSession, onClose }: { session: SesionUat; onClose: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { mutate: updateIssue } = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) => portalApi.updateUatStatus(id, { status }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['uat-team'], exact: false }),
    onError: e => toast.error(extractErr(e, t('ai.generic_error'))),
  })

  const SEV_COLORS: Record<string, string> = { low: 'var(--success)', medium: 'var(--accent)', high: 'var(--warning)', blocker: 'var(--danger)' }
  const ISSUE_STATUS = ['open', 'fixed', 'deferred', 'wontfix']

  return (
    <Modal open title={`${initialSession.code} — ${initialSession.title}`} onClose={onClose} width={700}>
      <div className="cpp-detail-head">
        <StatusBadge status={initialSession.status} cfg={STATUS_CFG} />
        {initialSession.test_environment && isSafeUrl(initialSession.test_environment) && <a href={sanitizeUrl(initialSession.test_environment)} target="_blank" rel="noopener noreferrer" className="cpp-link cpp-con-icono"><Link2 size={13} aria-hidden="true" />{t('client_portal.uat_detail_test_env')}</a>}
        {initialSession.deadline && <span className="u-text2-sm">{`${t('client_portal.uat_deadline')}: ${fmtDate(initialSession.deadline)}`}</span>}
      </div>

      {initialSession.client_notes && (
        <div className="cpp-notes">
          <div className="cpp-notes__title">{t('client_portal.uat_detail_client_notes')}</div>
          <p className="cpp-notes__text">{initialSession.client_notes}</p>
        </div>
      )}

      {/* Test cases */}
      {initialSession.test_cases.length > 0 && (
        <div className="u-mb-16">
          <div className="cpp-section-title">
            {t('client_portal.uat_detail_cases_summary', { passed: initialSession.stats.passed, total: initialSession.stats.total })}
          </div>
          <div className="u-stack-8">
            {initialSession.test_cases.map(tc => {
              const color = tc.status === 'passed' ? 'var(--success)' : tc.status === 'failed' ? 'var(--danger)' : 'var(--text-2)'
              return (
                <div key={tc.id} className="cpp-item cpp-item--case" style={colorVar(color)}>
                  <div className="cpp-row-top">
                    <div className="u-flex1">
                      <div className="cpp-item__title">{tc.title}</div>
                      {tc.expected_result && <div className="u-text2-sm">{`${t('client_portal.uat_expected')}: ${tc.expected_result}`}</div>}
                      {tc.actual_result && <div className="cpp-item__result">{`${t('client_portal.uat_result')}: ${tc.actual_result}`}</div>}
                    </div>
                    <span className="cpp-chip cpp-con-icono">
                      {tc.status === 'passed' ? <><CheckCircle2 size={12} aria-hidden="true" />{t('clientportalpage.estado_passed')}</>
                        : tc.status === 'failed' ? <><XCircle size={12} aria-hidden="true" />{t('clientportalpage.estado_failed')}</>
                        : <><Minus size={12} aria-hidden="true" />{t('client_portal.uat_pending')}</>}
                    </span>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Issues */}
      {initialSession.issues.length > 0 && (
        <div>
          <div className="cpp-section-title">
            {t('client_portal.uat_issues_summary', { n: initialSession.issues.filter(i => i.status === 'open').length })}
          </div>
          <div className="u-stack-8">
            {initialSession.issues.map(issue => {
              const sevColor = SEV_COLORS[issue.severity] || 'var(--text-2)'
              return (
                <div key={issue.id} className={issue.status === 'open' ? 'cpp-item cpp-item--issue-open' : 'cpp-item'} style={colorVar(sevColor)}>
                  <div className="cpp-row-top cpp-row-top--gap">
                    <div className="u-flex1">
                      <div className="cpp-title-row cpp-title-row--sm">
                        <span className="cpp-sev">{SEV_COLORS[issue.severity] ? t(`clientportalpage.sev_${issue.severity}`) : issue.severity}</span>
                        <span className="u-base-600">{issue.title}</span>
                      </div>
                      <p className="cpp-issue__desc">{issue.description}</p>
                    </div>
                    {issue.status === 'open' && (
                      <Select suelto tamano="sm" placeholder={false} value={issue.status} onChange={e => updateIssue({ id: issue.id, status: e.target.value })}
                        aria-label={t('clientportalpage.estado_incidencia', { title: issue.title })}
                        className="cpp-select-sm">
                        <option value="open">{t('client_portal.uat_issue_open')}</option>
                        <option value="fixed">{t('client_portal.uat_issue_fixed')}</option>
                        <option value="deferred">{t('client_portal.uat_issue_deferred')}</option>
                        <option value="wontfix">{t('client_portal.uat_issue_wontfix')}</option>
                      </Select>
                    )}
                    {issue.status !== 'open' && <span className="cpp-resolved cpp-con-icono"><Check size={12} aria-hidden="true" />{ISSUE_STATUS.includes(issue.status) ? t(`client_portal.uat_issue_${issue.status}`) : issue.status}</span>}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      <div className="cpp-footer">
        <Button variant="secondary" onClick={onClose}>{t('client_portal.close')}</Button>
      </div>
    </Modal>
  )
}
