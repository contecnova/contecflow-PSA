// Seccion de pruebas de aceptacion (UAT) del portal de cliente. 23-11-2026: troceado de PortalAdvancedSections sin cambio de comportamiento.
import { useId, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { FlaskConical, ArrowLeft, Bug, CheckCircle2, XCircle, Clock, ExternalLink, Key, ClipboardList } from 'lucide-react'
import { useToast } from '../../context/ToastContext'
import { fmtDate } from '../../utils/helpers'
import { CLIENT_API, useErrorDelPortal, useLang } from './portalClientContext'
import { PortalPageHeader, PortalCard, PortalSection, PortalEmpty, PortalBadge, PortalButton, PortalModal, PortalField, PortalInput, PortalSelect, PortalTextarea } from './PortalUI'
import { isSafeUrl, sanitizeUrl } from '../../utils/security'
import { StatusBadge, type UatSession } from './PortalAdvancedComun'

// ════════════════════════════════════════════════════════════════════════════
// PortalUAT
// ════════════════════════════════════════════════════════════════════════════
export function PortalUAT() {
  const traducir = useLang()
  const errorDe = useErrorDelPortal()
  const t = useLang()
  const qc = useQueryClient()
  const toast = useToast()
  const issueIdPrefix = useId()
  const [selected, setSelected] = useState<UatSession | null>(null)
  const [testResults, setTestResults] = useState<Record<string, string>>({})
  const [globalNotes, setGlobalNotes] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [reportingIssue, setReportingIssue] = useState(false)
  const [issueForm, setIssueForm] = useState({ title: '', description: '', severity: 'medium', steps_to_reproduce: '' })

  const { data: sessions = [], isLoading } = useQuery<UatSession[]>({
    queryKey: ['portal-uat'],
    queryFn: () => CLIENT_API.get('/portal/uat').then(r => r.data),
  })

  const submitResult = async (sessionId: string, result: string) => {
    setSubmitting(true)
    try {
      const testCases = selected?.test_cases?.map(tc => ({
        id: tc.id, status: testResults[tc.id] || 'pending', actual_result: '', notes: '',
      })) || []
      await CLIENT_API.post(`/portal/uat/${sessionId}/submit-result`, { result, notes: globalNotes, test_cases: testCases })
      qc.invalidateQueries({ queryKey: ['portal-uat'] })
      toast.success(traducir('portaladvanced.resultado_enviado'))
      setSelected(null)
    } catch (e) {
      toast.error(errorDe(e, t('pas_err_generic')))
    } finally { setSubmitting(false) }
  }

  const submitIssue = async () => {
    try {
      await CLIENT_API.post(`/portal/uat/${selected?.id}/issues`, issueForm)
      qc.invalidateQueries({ queryKey: ['portal-uat'] })
      toast.success(traducir('portaladvanced.incidencia_reportada'))
      setReportingIssue(false)
      setIssueForm({ title: '', description: '', severity: 'medium', steps_to_reproduce: '' })
    } catch (e) {
      toast.error(errorDe(e, t('pas_err_generic')))
    }
  }

  // ── Detail view ────────────────────────────────────────────────────────────
  if (selected) {
    const hasFailure = Object.values(testResults).includes('failed')
    return (
      <div>
        <PortalPageHeader
          title={selected.title}
          subtitle={selected.description}
          icon={FlaskConical}
          breadcrumb={[
            { label: t('nav_uat') || 'UAT', onClick: () => setSelected(null) },
            { label: selected.title },
          ]}
          actions={
            <PortalButton variant="secondary" size="sm" icon={<ArrowLeft size={13} />}
              onClick={() => setSelected(null)}>{traducir('chat.back')}</PortalButton>
          }
        />

        {(selected.test_environment || selected.test_credentials) && (
          <PortalCard className="portalad-sx1">
            <PortalSection title={traducir('portaladvanced.entorno_de_pruebas')}>
              <div className="poadse-row-1">
                {/* 23-11-2026 (A3 del 04b): enlace solo si es http(s); si no, texto. */}
                {selected.test_environment && !/^https?:/i.test(selected.test_environment.trim()) && <span className="poadse-row-2">{selected.test_environment}</span>}
                {selected.test_environment && /^https?:/i.test(selected.test_environment.trim()) && isSafeUrl(selected.test_environment) && (
                  <a href={sanitizeUrl(selected.test_environment)} target="_blank" rel="noopener noreferrer" className="poadse-row-2">
                    <ExternalLink size={13} /> {traducir('portaladvanced.abrir_entorno')}
                  </a>
                )}
                {selected.test_credentials && (
                  <div className="poadse-row-3">
                    <Key size={13} /> {selected.test_credentials}
                  </div>
                )}
              </div>
            </PortalSection>
          </PortalCard>
        )}

        {selected.test_cases?.length > 0 && (
          <div className="u-mb-16">
            <div className="poadse-box-1">{traducir('portaladvanced.casos_de_prueba')}</div>
            <div className="u-stack-10">
              {selected.test_cases.map(tc => (
                <PortalCard key={tc.id}>
                  <div className="u-mb-10">
                    <div className="poadse-box-2">{tc.title}</div>
                    {tc.steps && <div className="poadse-box-3 poadse-con-icono"><ClipboardList size={13} aria-hidden="true" /><span>{tc.steps}</span></div>}
                    {tc.expected_result && <div className="poadse-txt-1 poadse-con-icono"><CheckCircle2 size={13} aria-hidden="true" /><span>{tc.expected_result}</span></div>}
                  </div>
                  <div className="u-row-8">
                    {[
                      { val: 'passed', label: t('pas_tc_passed'), activo: 'primary', icon: <CheckCircle2 size={14} /> },
                      { val: 'failed', label: t('pas_tc_failed'), activo: 'danger',  icon: <XCircle size={14} /> },
                    ].map(opt => (
                      <PortalButton key={opt.val} size="sm" icon={opt.icon}
                        variant={testResults[tc.id] === opt.val ? opt.activo : 'secondary'}
                        onClick={() => setTestResults(r => ({ ...r, [tc.id]: opt.val }))}>{opt.label}</PortalButton>
                    ))}
                  </div>
                </PortalCard>
              ))}
            </div>
          </div>
        )}

        {selected.issues?.length > 0 && (
          <div className="u-mb-16">
            <div className="poadse-box-1">{traducir('client_portal.uat_issues_title')}</div>
            <div className="u-stack-8">
              {selected.issues.map(issue => (
                <PortalCard key={issue.id} padding={14}>
                  <div className="poadse-row-4">
                    <div>
                      <div className="u-sm-700">{issue.title}</div>
                      <p className="poadse-box-4">{issue.description}</p>
                    </div>
                    <PortalBadge tone={issue.status === 'fixed' ? 'success' : 'danger'}>{issue.status === 'fixed' ? t('st_fixed') : t('st_open')}</PortalBadge>
                  </div>
                </PortalCard>
              ))}
            </div>
          </div>
        )}

        <PortalCard className="portalad-sx1">
          <PortalField label={traducir('portaladvanced.notas_para_el_equipo')}>
            <PortalTextarea rows={3} value={globalNotes} onChange={e => setGlobalNotes(e.target.value)} placeholder={traducir('portaladvanced.comentarios_generales_de_la_sesion')} />
          </PortalField>
        </PortalCard>

        <div className="u-wrap-10">
          <PortalButton variant="secondary" icon={<Bug size={14} />} onClick={() => setReportingIssue(true)}>
            {traducir('portaladvanced.reportar_incidencia')}
          </PortalButton>
          {selected.status !== 'passed' && selected.status !== 'failed' && (
            <>
              <PortalButton variant="danger" icon={<XCircle size={14} />}
                onClick={() => submitResult(selected.id, 'failed')} loading={submitting}>
                {traducir('aus.rechazar')}
              </PortalButton>
              <PortalButton variant="primary" icon={<CheckCircle2 size={14} />}
                onClick={() => submitResult(selected.id, hasFailure ? 'conditional' : 'passed')}
                loading={submitting}>
                {hasFailure ? t('pas_approve_with_notes') : t('pas_approve')}
              </PortalButton>
            </>
          )}
        </div>

        <PortalModal
          open={reportingIssue}
          onClose={() => setReportingIssue(false)}
          title={traducir('portaladvanced.reportar_incidencia')}
          subtitle={traducir('portaladvanced.describe_el_problema_encontrado_durante_la_prueba')}
          footer={
            <>
              <PortalButton variant="secondary" onClick={() => setReportingIssue(false)}>{traducir('common.cancel')}</PortalButton>
              <PortalButton onClick={submitIssue} disabled={!issueForm.title || !issueForm.description}>{traducir('chat.send')}</PortalButton>
            </>
          }
        >
          <div className="u-stack-14">
            <PortalField label={traducir('portaladvanced.titulo')} required>
              <PortalInput id={`${issueIdPrefix}-title`} value={issueForm.title} onChange={e => setIssueForm(f => ({ ...f, title: e.target.value }))} />
            </PortalField>
            <PortalField label={traducir('portaladvanced.descripcion')} required>
              <PortalTextarea rows={3} value={issueForm.description} onChange={e => setIssueForm(f => ({ ...f, description: e.target.value }))} />
            </PortalField>
            <PortalField label={traducir('lec.severidad')}>
              <PortalSelect value={issueForm.severity} onChange={e => setIssueForm(f => ({ ...f, severity: e.target.value }))}>
                <option value="low">{traducir('lec.sev_baja')}</option>
                <option value="medium">{traducir('lec.sev_media')}</option>
                <option value="high">{traducir('lec.sev_alta')}</option>
                <option value="blocker">{traducir('clientportalpage.sev_blocker')}</option>
              </PortalSelect>
            </PortalField>
            <PortalField label={traducir('portaladvanced.pasos_para_reproducir')}>
              <PortalTextarea rows={2} value={issueForm.steps_to_reproduce} onChange={e => setIssueForm(f => ({ ...f, steps_to_reproduce: e.target.value }))} />
            </PortalField>
          </div>
        </PortalModal>
      </div>
    )
  }

  // ── List view ──────────────────────────────────────────────────────────────
  return (
    <div>
      <PortalPageHeader
        title={t('nav_uat')}
        subtitle={traducir('portaladvanced.sesiones_de_aceptacion_de_usuario_donde_validas')}
        icon={FlaskConical}
        meta={[
          { value: sessions.length, label: t('pas_meta_sessions') },
          { value: sessions.filter(s => ['pending', 'in_progress'].includes(s.status)).length, label: t('pas_meta_pending'), color: 'var(--warning)' },
          { value: sessions.filter(s => ['passed', 'conditional'].includes(s.status)).length, label: t('pas_meta_approved'), color: 'var(--success)' },
        ]}
      />

      {isLoading ? (
        <div className="poadse-box-5">{traducir('common.loading')}</div>
      ) : sessions.length === 0 ? (
        <PortalEmpty icon={FlaskConical}
          title={traducir('portaladvanced.no_hay_sesiones_uat')}
          description={traducir('portaladvanced.cuando_el_equipo_prepare_una_entrega_para')}
        />
      ) : (
        <div className="u-stack-12">
          {sessions.map(s => (
            <PortalCard key={s.id} onClick={() => { setSelected(s); setTestResults({}); setGlobalNotes('') }}>
              <div className="poadse-row-5">
                <div className="u-flex1-min0">
                  <div className="poadse-row-6">
                    <FlaskConical size={16} className="portalad-sx3" />
                    <div className="poadse-txt-2">{s.title}</div>
                  </div>
                  <div className="poadse-box-6">
                    {s.deadline && (
                      <span className={`poadse-row-30 ${s.overdue ? 'portal-advanced-sections-m2' : 'portal-advanced-sections-m3'}`}>
                        <Clock size={12} /> {s.overdue ? t('pas_overdue_label') : t('pas_deadline_label')} {fmtDate(s.deadline)}
                      </span>
                    )}
                  </div>
                  {s.stats?.total > 0 && (
                    <div className="poadse-row-7">
                      <span>{s.stats.total} {traducir('client_portal.uat_cases')}</span>
                      <span className="u-success poadse-con-icono"><CheckCircle2 size={12} aria-label={t('pas_tc_passed')} />{s.stats.passed}</span>
                      <span className="u-danger poadse-con-icono"><XCircle size={12} aria-label={t('pas_tc_failed')} />{s.stats.failed}</span>
                    </div>
                  )}
                </div>
                <StatusBadge status={s.status} />
              </div>
            </PortalCard>
          ))}
        </div>
      )}
    </div>
  )
}
