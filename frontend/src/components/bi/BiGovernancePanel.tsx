/**
 * BiGovernancePanel.jsx — BI Governance management.
 *
 * Endpoints:
 *   GET  /bi/governance/rules                    -> dict { policy_name: {policy_type, enabled, ...} }
 *   PATCH /bi/governance/rules                   merge update
 *   GET  /bi/governance/audit/access?days=N      -> { items: [{action, resource|dataset_id, user_id, accessed_at, ...}], count }
 *   GET  /bi/governance/overview                 -> overview snapshot
 */
import React, { type CSSProperties, useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { biCollaborationApi, biGovernanceAuditApi } from '../../services/api'
import type { AccesoBi as AuditEvent, ReglasDeGobiernoBi, ResumenDeGobiernoBi as OverviewData } from '../../services/api/tipos-grc'
import { useAppT } from '../../i18n/AppLangContext'
import { Shield, RefreshCw, Database, MessageCircle, Calendar, Zap, Clock } from 'lucide-react'
import { Card, Button, Tabs, Spinner, EmptyState } from '../ui'
import { useToast } from '../../context/ToastContext'
import { localeActivo } from '../../utils/helpers'
import './BiGovernancePanel.css'
import { chipColor } from '../../utils/estilos'


// ── Overview structured renderer ──────────────────────────────────────────────

interface OverviewSectionProps {
  icon: React.ComponentType<{ size?: number | string; className?: string; style?: React.CSSProperties }>
  iconColor: string
  title: string
  children?: React.ReactNode
  badge?: React.ReactNode
}

function OverviewSection({ icon: Icon, iconColor, title, children, badge }: OverviewSectionProps) {
  return (
    <div className="bigopa-box-1">
      <div className="bigopa-row-1">
        <div className="u-row-center-8">
          <Icon size={14} className="u-dato-color" style={{ '--dato-color': iconColor } as CSSProperties} />
          <span className="bigopa-txt-1">{title}</span>
        </div>
        {badge != null && badge}
      </div>
      {children}
    </div>
  )
}

interface MetricRowProps {
  label: string
  value: React.ReactNode
  mono?: boolean
}

function MetricRow({ label, value, mono }: MetricRowProps) {
  return (
    <div className="bigopa-row-2">
      <span className="u-text3">{label}</span>
      <span className={`bigopa-box-10 ${mono ? 'bi-governance-panel-m1' : 'bi-governance-panel-m2'}`}>{value}</span>
    </div>
  )
}

function OverviewView({ data }: { data?: OverviewData | null }) {
  const t = useAppT()
  const d: Partial<OverviewData> = data ?? {}
  const ts = d.timestamp ? new Date(d.timestamp) : null
  const olap: Partial<OverviewData['olap']> = d.olap || {}
  const sched: Partial<OverviewData['scheduled_reports']> = d.scheduled_reports || {}
  const collab: Partial<OverviewData['collaboration']> = d.collaboration || {}
  const cache: Partial<OverviewData['cache_policy']> = d.cache_policy || {}

  const olapAvailable = !!olap.available
  const olapColor = olapAvailable ? 'var(--success)' : 'var(--danger)'
  const olapStaleness = olap.staleness_hours
  const stalenessColor = olapStaleness == null
    ? 'var(--text-3)'
    : olapStaleness < 6 ? 'var(--success)'
    : olapStaleness < 24 ? 'var(--warning)' : 'var(--danger)'

  const schedActive = sched.active || 0
  const schedError = sched.error || 0
  const schedColor = schedError > 0 ? 'var(--danger)' : schedActive > 0 ? 'var(--success)' : 'var(--text-3)'

  const unresolved = collab.unresolved_comments || 0
  const collabColor = unresolved > 10 ? 'var(--warning)' : unresolved > 0 ? 'var(--accent)' : 'var(--success)'

  return (
    <div className="u-stack-12">
      {/* Snapshot timestamp */}
      {ts && (
        <div className="bigopa-row-3">
          <Clock size={12} />
          {t('bigovernance.snapshot_generado')} <span className="u-text2">{ts.toLocaleString(localeActivo())}</span>
        </div>
      )}

      <div className="bigopa-grid-1">
        {/* OLAP */}
        <OverviewSection
          icon={Database}
          iconColor={olapColor}
          title="OLAP store"
          badge={<span className="chip-dato" style={chipColor(olapColor)}>{olapAvailable ? 'Disponible' : 'No disponible'}</span>}
        >
          <MetricRow
            label={t('bigovernance.antiguedad')}
            value={olapStaleness == null
              ? '—'
              : <span className="bigopa-txt-2 bi-governance-panel-e3" style={{ '--bi-governance-panel-color': stalenessColor } as CSSProperties}>
                  {olapStaleness < 1 ? `${Math.round(olapStaleness * 60)}min` : `${olapStaleness}h`}
                </span>}
          />
          {olap.path && (
            <MetricRow label="Path" value={olap.path} mono />
          )}
        </OverviewSection>

        {/* Scheduled reports */}
        <OverviewSection
          icon={Calendar}
          iconColor={schedColor}
          title={t('bigovernance.reports_programados')}
          badge={<span className="chip-dato" style={chipColor(schedColor)}>{schedActive} {t('bigovernance.activos')}</span>}
        >
          <MetricRow label={t('alm.assets')} value={schedActive} />
          <MetricRow
            label={t('bigovernance.con_error')}
            value={<span className={`bigopa-txt-2 ${schedError > 0 ? 'bi-governance-panel-m4' : 'bi-governance-panel-m5'}`}>{schedError}</span>}
          />
        </OverviewSection>

        {/* Collaboration */}
        <OverviewSection
          icon={MessageCircle}
          iconColor={collabColor}
          title={t('bigovernance.colaboracion')}
          badge={<span className="chip-dato" style={chipColor(collabColor)}>{unresolved} {t('bigovernance.sin_resolver')}</span>}
        >
          <MetricRow
            label={t('bigovernance.comentarios_sin_resolver')}
            value={<span className="bigopa-txt-2 bi-governance-panel-e3" style={{ '--bi-governance-panel-color': collabColor } as CSSProperties}>{unresolved}</span>}
          />
        </OverviewSection>

        {/* Cache policy */}
        <OverviewSection
          icon={Zap}
          iconColor="var(--purple)"
          title={t('bigovernance.politica_de_cache_ttl')}
          badge={<span className="chip-dato" style={chipColor('var(--purple)')}>{cache.metric_count ?? 0} {t('bigovernance.metricas')}</span>}
        >
          <MetricRow label={t('bigovernance.ttl_por_defecto')} value={`${cache.default_ttl_seconds ?? '—'}s`} />
          <MetricRow label={t('bigovernance.ttl_minimo')} value={`${cache.min_ttl_seconds ?? '—'}s`} />
          <MetricRow label={t('bigovernance.ttl_maximo')} value={`${cache.max_ttl_seconds ?? '—'}s`} />
        </OverviewSection>
      </div>
    </div>
  )
}

/** Lo que se edita de las reglas: el PATCH acepta cualquier subconjunto. */
type Reglas = Partial<ReglasDeGobiernoBi>

interface ApiError {
  response?: { data?: { detail?: string } }
}

export default function BiGovernancePanel() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [tab, setTab] = useState<string>('policies')
  const [auditDays, setAuditDays] = useState<number>(30)
  const [auditUserFilter, setAuditUserFilter] = useState<string>('')

  const { data: policiesData, isLoading: policiesLoading } = useQuery({
    queryKey: ['bi-gov-policies'],
    queryFn: () => biCollaborationApi.governanceRules().then(r => r.data),
  })

  const { data: auditData, isLoading: auditLoading, refetch: refetchAudit } = useQuery({
    queryKey: ['bi-gov-audit', auditDays, auditUserFilter],
    queryFn: () => biGovernanceAuditApi.getAccessHistory({ days: auditDays, ...(auditUserFilter ? { user_id: auditUserFilter } : {}) }).then(r => r.data).catch(() => ({ items: [], count: 0 })),
    enabled: tab === 'audit',
  })

  const { data: overviewData, isLoading: overviewLoading } = useQuery({
    queryKey: ['bi-gov-overview'],
    queryFn: () => biCollaborationApi.governanceOverview().then(r => r.data).catch(() => null),
    enabled: tab === 'overview',
  })

  const [reglas, setReglas] = useState<Reglas>({})
  useEffect(() => { if (policiesData) setReglas(policiesData) }, [policiesData])
  const guardarReglas = useMutation({
    mutationFn: (r: Reglas) => biCollaborationApi.updateGovernanceRules(r).then(x => x.data),
    onSuccess: () => { toast.success(t('bigovernance.reglas_guardadas')); qc.invalidateQueries({ queryKey: ['bi-gov-policies'] }) },
    onError: (e: unknown) => toast.error((e as ApiError)?.response?.data?.detail || 'Error al guardar'),
  })

  const auditItems = auditData?.items ?? []

  return (
    <Card className="bigovern-sx1">
      <div className="bigopa-row-4">
        <div className="u-row-center-8">
          <Shield size={18} className="bigovern-sx2" />
          <h2 className="bigopa-box-2">
            {t('bi.governance.title', 'Gobernanza BI')}
          </h2>
        </div>
      </div>

      <Tabs
        items={[
          { id: 'policies',  label: t('bigovernance.reglas') },
          { id: 'audit',     label: 'Auditoría' },
          { id: 'overview',  label: 'Overview' },
        ]}
        active={tab}
        onChange={setTab}
        ariaLabel="Gobernanza BI"
      />

      {tab === 'policies' && (
        // Revisión 2026-11: antes había un «editor de políticas» que escribía
        // nombres libres en este mismo JSON; el servidor sólo guarda estas tres
        // reglas (las que usan las comprobaciones) y lo demás se perdía.
        <div>
          <div className="bigopa-fieldlabel2">{t('bigovernance.reglas_de_las_comprobaciones')}</div>
          {policiesLoading ? (
            <div className="bigopa-row-5"><Spinner /></div>
          ) : (
            <div className="bigopa-grid-2">
              <label className="bigopa-stack-1">
                {t('bigovernance.horas_max_olap')}
                <input type="number" aria-label={t('bigovernance.horas_max_olap')} min={1} max={240} value={reglas.olap_max_staleness_hours ?? ''}
                  onChange={e => setReglas(r => ({ ...r, olap_max_staleness_hours: e.target.value === '' ? undefined : Number(e.target.value) }))}
                  className="bigopa-inputbase" />
              </label>
              <label className="bigopa-stack-1">
                {t('bigovernance.informes_en_error_max')}
                <input type="number" aria-label={t('bigovernance.informes_en_error_max')} min={0} max={100} value={reglas.max_error_reports ?? ''}
                  onChange={e => setReglas(r => ({ ...r, max_error_reports: e.target.value === '' ? undefined : Number(e.target.value) }))}
                  className="bigopa-inputbase" />
              </label>
              <label className="bigopa-row-6">
                <input type="checkbox" aria-label={t('bigovernance.exigir_informes_activos')} checked={!!reglas.require_active_schedules}
                  onChange={e => setReglas(r => ({ ...r, require_active_schedules: e.target.checked }))} />
                {t('bigovernance.exigir_informes_activos')}
              </label>
            </div>
          )}
          <div className="bigopa-row-7">
            <Button onClick={() => guardarReglas.mutate(reglas)} loading={guardarReglas.isPending}>{t('common.save')}</Button>
          </div>
          <p className="bigopa-box-3">
            {t('bigovernance.otras_politicas')}
          </p>
        </div>
      )}

      {tab === 'audit' && (
        <div>
          <div className="bigopa-row-8">
            <div className="bigopa-box-4">
              <div className="bigopa-fieldlabel">{t('approvals.ventana')}</div>
              <select value={auditDays} onChange={e => setAuditDays(Number(e.target.value))} className="bigopa-inputbase">
                <option value={7}>{t('bigovernance.7_dias')}</option>
                <option value={30}>{t('bigovernance.30_dias')}</option>
                <option value={60}>{t('bigovernance.60_dias')}</option>
                <option value={90}>{t('bigovernance.90_dias')}</option>
              </select>
            </div>
            <div className="bigopa-box-5">
              <div className="bigopa-fieldlabel">{t('bigovernance.filtrar_por_user_id')}</div>
              <input aria-label={t('bigovernance.user_id_opcional')}
                type="text"
                placeholder={t('bigovernance.user_id_opcional')}
                value={auditUserFilter}
                onChange={e => setAuditUserFilter(e.target.value)}
                className="bigopa-inputbase"
              />
            </div>
            <Button size="sm" variant="secondary" icon={<RefreshCw size={13} />} onClick={() => refetchAudit()}>
              {t('common.update')}
            </Button>
          </div>

          {auditLoading ? (
            <div className="bigopa-row-5"><Spinner /></div>
          ) : auditItems.length === 0 ? (
            <EmptyState icon="📋" title={t('bigovernance.sin_eventos_de_auditoria')} description={`Ningún evento registrado en los últimos ${auditDays} días.`} />
          ) : (
            <div className="bigopa-stack-2">
              <div className="bigopa-box-6">
                {auditItems.length} {t('bigovernance.evento_s')} {auditUserFilter && `· user ${auditUserFilter}`}
              </div>
              {auditItems.map((ev: AuditEvent, i: number) => {
                const action = ev.action || 'view'
                const actionColor = action === 'delete' ? 'var(--danger)'
                  : action === 'create' || action === 'update' ? 'var(--warning)'
                  : 'var(--accent)'
                return (
                  <div key={i} className="bigopa-row-9">
                    <span className="chip-dato" style={chipColor(actionColor)}>{action}</span>
                    <span className="bigopa-box-7">
                      {ev.entity_id || ev.entity_type || '—'}
                    </span>
                    <span className="bigopa-box-8">
                      {ev.user_name || ev.user_id || '—'}
                    </span>
                    <span className="bigopa-box-9">
                      {ev.timestamp ? new Date(ev.timestamp).toLocaleString(localeActivo()) : ''}
                    </span>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {tab === 'overview' && (
        overviewLoading ? (
          <div className="bigopa-row-5"><Spinner /></div>
        ) : !overviewData ? (
          <EmptyState icon="📊" title={t('bigovernance.sin_overview')} />
        ) : (
          <OverviewView data={overviewData} />
        )
      )}
    </Card>
  )
}
