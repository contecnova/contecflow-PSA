// Pestañas de registro de auditoria y aprobaciones de GRC. 23-11-2026: troceado de GrcPage sin cambio de comportamiento.
import { useAppLang, useAppT } from '../i18n/AppLangContext'
import { useState } from 'react'
import type { CSSProperties } from 'react'
import { useQuery } from '@tanstack/react-query'
import { grcApi, approvalsApi } from '../services/api'
import { Link } from 'react-router-dom'
import type { EventoDeAuditoriaGrc as AuditEvent } from '../services/api/tipos-grc'
import { AlertTriangle, CheckCircle2, ClipboardList, GitPullRequestArrow, KeyRound, Pencil, RefreshCw, RotateCcw, ScrollText, ShieldAlert, Trash2, Zap } from 'lucide-react'
import { Button, Spinner, EmptyState, IconButton } from '../components/ui'
import { fmtDateTime } from '../utils/helpers'
import { alpha } from '../constants/theme'
import { SEV_COLOR } from './GrcComun'
import { type Workflow } from './GrcSod'

// ═══════════════════════════════════════════════════════════════════════════════
// 4. AUDIT LOG GRC
// ═══════════════════════════════════════════════════════════════════════════════
export function AuditLogTab() {
  const { t } = useAppLang()
  const traducir = useAppT()
  const [severity, setSeverity] = useState('')

  const { data: log = [], isLoading, refetch } = useQuery<AuditEvent[]>({
    queryKey: ['grc-audit-log', severity],
    queryFn: () => grcApi.auditLog(severity ? { severity } : {}).then(r => r.data),
  })

  const ACTION_ICONS: Record<string, JSX.Element> = {
    permission_changed: <KeyRound size={14} />, permission_matrix_reset: <RotateCcw size={14} />,
    sod_rule_created: <AlertTriangle size={14} />, sod_rule_updated: <Pencil size={14} />, sod_rule_deleted: <Trash2 size={14} />,
    sod_violation_detected: <ShieldAlert size={14} />, sod_violation_resolved: <CheckCircle2 size={14} />, approval_override: <Zap size={14} />,
  }

  return (
    <div>
      <div className="grc-card-9">
        <strong className="u-text1">{t('pagina_grc.audit_log_inmutable_grc')}</strong> {traducir('grc.todos_los_eventos_de_seguridad_cambios_de')}
      </div>

      <div className="grc-row-14">
        <span className="u-text2-sm">{t('pagina_grc.severidad')}</span>
        {[['', t('pagina_grc.todas')], ['info', t('pagina_grc.info')], ['warning', t('pagina_grc.aviso')], ['critical', t('pagina_grc.critico')]].map(([val, label]) => (
          <Button key={val} size="sm" variant={severity === val ? 'primary' : 'secondary'} onClick={() => setSeverity(val)}>
            {label}
          </Button>
        ))}
        <IconButton onClick={() => refetch()} ariaLabel={t('pagina_grc.refrescar_audit_log')}><RefreshCw size={14} /></IconButton>
      </div>

      {isLoading ? <Spinner /> : log.length === 0 ? (
        <EmptyState icon={<ScrollText size={28} />} title={traducir('grc.sin_eventos_de_auditoria')} description={t('pagina_grc.los_eventos_de_seguridad_apareceran_aqui')} />
      ) : (
        <div className="grc-stack">
          {log.map((e: AuditEvent) => {
            const sc = SEV_COLOR[e.severity || ''] || 'var(--text-2)'
            return (
              <div key={e.id} className="grc-page-e11" style={{ '--grc-page-border-left': `3px solid ${sc}` } as CSSProperties}>
                <div className="grc-row-15">
                  <div className="u-row-center-8">
                    <span className="grc-label-3" aria-hidden>{ACTION_ICONS[e.action_type || ''] || <ClipboardList size={14} />}</span>
                    <span className="u-text1-sm-600">{t(`grc.evento_${e.action_type}`)}</span>
                    {e.resource_type && <span className="grc-card-10">{e.resource_type}</span>}
                    <span className="grc-label-8 grc-page-e12" style={{ '--grc-page-color': sc, '--grc-page-background': alpha(sc, '15') } as CSSProperties}>{t(`grc.severidad_${e.severity}`)}</span>
                  </div>
                  <span className="grc-label-9">{fmtDateTime(e.timestamp)}</span>
                </div>
                <div className="u-text2-xs">
                  {e.user_name && <span>{t('pagina_grc.actor')}{' '}<strong>{e.user_name}</strong>{e.ip_address ? t('pagina_grc.ip', { ip_address: e.ip_address }) : ''}</span>}
                  {e.detail && typeof e.detail === 'object' && (
                    <span className="ds-codigo grc-label-10">
                      {JSON.stringify(e.detail).slice(0, 120)}
                    </span>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

export function ApprovalsTab() {
  const { t } = useAppLang()
  const traducir = useAppT()
  const { data: workflows = [], isLoading } = useQuery<Workflow[]>({
    queryKey: ['approval-workflows-grc'],
    queryFn: () => approvalsApi.listWorkflows(undefined).then(r => r.data),
  })

  return (
    <div>
      <div className="grc-card-11">
        {traducir('grc.los')} <strong className="u-text1">{traducir('grc.flujos_de_aprobacion')}</strong> {traducir('grc.mitigan_los_riesgos_sod_anadiendo_revision_obligatoria')}{' '}
        <Link to="/approvals" className="u-accent">{t('pagina_grc.aprobaciones')}</Link>.
      </div>

      {isLoading ? <Spinner /> : workflows.length === 0 ? (
        <EmptyState icon={<GitPullRequestArrow size={28} />} title={traducir('grc.sin_flujos_de_aprobacion')}
          description={t('pagina_grc.configura_flujos_de_aprobacion_para_mitigar')} />
      ) : (
        <div className="u-stack-10">
          {workflows.map(wf => (
            <div key={wf.id} className="grc-card-12">
              <div className="grc-row-16">
                <div>
                  <span className="grc-label-11">
                    {wf.name}
                  </span>
                  <span className="grc-card-13">{wf.entity_type?.replace(/_/g,' ')}</span>
                </div>
                <span className={`grc-label-12 ${wf.is_active ? 'grcpage-sx10' : 'grcpage-sx12'}`}>
                  {wf.is_active ? t('pagina_grc.activo') : t('pagina_grc.inactivo')}
                </span>
              </div>
              <div className="u-wrap-6">
                {(wf.steps || []).map((step, i) => (
                  <div key={step.id} className="grc-row-17">
                    {i > 0 && <span className="grc-label-13">→</span>}
                    <span className="grc-card-14">
                      {step.name || step.approver_role || step.approver_user_name || t('pagina_grc.paso') + (i+1)}
                    </span>
                  </div>
                ))}
                {(!wf.steps || wf.steps.length === 0) && (
                  <span className="u-text3-sm">{traducir('grc.sin_pasos_configurados')}</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
