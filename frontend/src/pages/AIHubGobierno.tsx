// Pestañas de gobierno, enrutado y gasto de IA. 23-11-2026: troceado de AIHubPage sin cambio de comportamiento.
import { extractErr, fmtDateTime, fmtNumber, localeActivo } from '../utils/helpers'
import { Fragment, useState } from 'react'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { aiProvidersApi, aiGovernanceApi } from '../services/api'
import type { ProveedorIa as AiProvider } from '../services/api/tipos-grc'
import { Button, Spinner, KpiCard, EmptyState, EstadoDeError, StatusBadge, SelectorDePeriodo, Select, Input } from '../components/ui'
import { usePeriodo } from '../hooks/usePeriodo'
import { CON_HORA, codigoDeErrorDePeriodo } from '../utils/periodo'
import { useAppT } from '../i18n/AppLangContext'
import { Shield, ClipboardList, AlertTriangle, Ban, EyeOff, ScanSearch } from 'lucide-react'
import { POLL_DEFAULT_MS, STALE_DEFAULT_MS, STALE_SHORT_MS } from '../constants/timings'
import { AUDIT_LOG_PAGE_SIZE } from '../constants/pagination'
import { type AiAuditEntry, type AiPolicy } from './AIHubComun'

// ── Governance Tab ───────────────────────────────────────────────────────────
export function GovernanceTab() {
  const traducir = useAppT()
  // Read-only viewer del audit log + stats. El CRUD de policies se gestiona
  // vía API directa hasta que se complete la UI dedicada (decisión ARCH).
  // Por el cliente API (refresco de sesión y desenvoltorio {data,meta}/{items,meta}).
  // 23-11-2026 (04 M6): si falla ya no se pinta vacío como si no hubiera datos: se muestra el error con reintento.
  const { data: policiesRaw = [], isLoading: loadingPolicies, error: errorPolicies } = useQuery<AiPolicy[] | { items?: AiPolicy[] }>({
    queryKey: ['ai-governance', 'policies'],
    queryFn: () => aiGovernanceApi.policies().then(r => r.data),
    staleTime: STALE_DEFAULT_MS,
  })
  // Periodo libre (16-11-2026): un periodo para el registro y sus estadísticas
  // (antes 7 días el registro y 30 las estadísticas, fijos). Las evaluaciones
  // son instantes: admite hora. Los errores de periodo se muestran traducidos.
  const periodo = usePeriodo({ defecto: '30d', granularidades: CON_HORA, prefijo: 'gov' })
  const { data: auditLogRaw = [], isLoading: loadingAudit, error: errorAudit } = useQuery<AiAuditEntry[] | { items?: AiAuditEntry[] }>({
    queryKey: ['ai-governance', 'audit-log', { page_size: AUDIT_LOG_PAGE_SIZE }, periodo.params],
    queryFn: () => aiGovernanceApi.auditLog({ page_size: AUDIT_LOG_PAGE_SIZE, ...periodo.params }).then(r => r.data),
    staleTime: STALE_SHORT_MS,
  })
  const { data: stats = null, isLoading: loadingStats, error: errorStats } = useQuery({
    queryKey: ['ai-governance', 'audit-log-stats', periodo.params],
    queryFn: () => aiGovernanceApi.auditLogStats(periodo.params).then(r => r.data),
    staleTime: STALE_DEFAULT_MS,
  })
  const errorDePeriodo = codigoDeErrorDePeriodo(errorStats) ?? codigoDeErrorDePeriodo(errorAudit)
  // Error que no es de periodo (esos ya se explican abajo): se pinta con reintento.
  const errorDeCarga = [errorPolicies, errorAudit, errorStats].find(e => e && !codigoDeErrorDePeriodo(e)) ?? null
  const qcGobierno = useQueryClient()

  const policies = Array.isArray(policiesRaw) ? policiesRaw : (policiesRaw.items || [])
  const auditLog = Array.isArray(auditLogRaw) ? auditLogRaw : (auditLogRaw.items || [])
  const loading = loadingPolicies || loadingAudit || loadingStats

  const selector = (
    <div className="aih-obs-head">
      <SelectorDePeriodo {...periodo.selector} sinGranularidad />
    </div>
  )

  if (loading) return <div className="u-stack-20">{selector}<div className="aih-pad24"><Spinner /></div></div>

  return (
    <div id="aihub-panel-governance" role="tabpanel" className="u-stack-20">
      {selector}
      {errorDePeriodo && (
        <EmptyState icon={<AlertTriangle size={28} />} title={traducir(`periodo_err.${errorDePeriodo.motivo}`, errorDePeriodo.params)} />
      )}
      {errorDeCarga && (
        <EstadoDeError error={errorDeCarga} onReintentar={() => { void qcGobierno.invalidateQueries({ queryKey: ['ai-governance'] }) }} />
      )}
      {/* Stats summary */}
      {stats && (
        <div className="ds-grid-stats">
          {/* Auditoría 2026-11: leía blocked/redacted/pii_total, que la API no
              devuelve; las tarjetas salían siempre a 0. */}
          <KpiCard icon={<ScanSearch size={16} />} label={traducir('aihub.kpi_evaluations')} value={fmtNumber(stats.total_evaluations || 0, 0)} />
          <KpiCard icon={<Ban size={16} />} label={traducir('aihub.kpi_blocked')} value={fmtNumber(stats.total_blocked || 0, 0)} danger={(stats.total_blocked || 0) > 0} />
          <KpiCard icon={<EyeOff size={16} />} label={traducir('aihub.kpi_redacted')} value={fmtNumber(stats.total_redacted || 0, 0)} warning={(stats.total_redacted || 0) > 0} />
          <KpiCard icon={<Shield size={16} />} label={traducir('aihub.kpi_pii')} value={fmtNumber((stats.top_pii_types || []).reduce((n: number, x: { count?: number }) => n + (x.count || 0), 0), 0)} />
        </div>
      )}

      {/* Policies list */}
      <div className="ds-card ds-card--plano">
        <div className="aih-panel-head">
          <div className="aih-panel-title"><Shield size={14} aria-hidden="true" /> {traducir('aihub.politicas_configuradas')} ({policies.length})</div>
          <div className="u-text3-xs aih-panel-head-note">
            {traducir('aihub.policies_admin_note')}
          </div>
        </div>
        {policies.length === 0 ? (
          <EmptyState
            icon={<Shield size={28} />}
            title={traducir('aihub.policies_empty_title')}
            description={traducir('aihub.sin_policies_activas_los_guardrails_deteccion_pii')}
          />
        ) : (
          <div className="aih-scroll aih-scroll--240">
            {policies.map(p => (
              <div key={p.id} className="aih-policy">
                <div className="aih-policy-head">
                  <span className="u-600">{p.name}</span>
                  <StatusBadge kind={p.is_active ? 'success' : 'neutral'} caps={false}>
                    {p.is_active ? traducir('aihub.policy_active') : traducir('aihub.policy_inactive')}
                  </StatusBadge>
                </div>
                <div className="aih-policy-meta">
                  {traducir('aihub.policy_scope')}: {traducir(`aihub.scope_${p.scope}`, p.scope || '—')}
                  {' · '}{traducir('aihub.policy_action')}: {traducir(`aihub.act_${p.action}`, p.action || '—')}
                  {' · '}{traducir('aihub.policy_roles')}: {(p.applies_to_roles || []).length === 0 || (p.applies_to_roles || []).includes('*')
                    ? traducir('aihub.roles_all')
                    : (p.applies_to_roles || []).join(', ')}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Audit log */}
      <div className="ds-card ds-card--plano">
        <div className="aih-panel-head">
          <div className="aih-panel-title"><ClipboardList size={14} aria-hidden="true" /> {traducir('aihub.audit_log_ultimas_50_evaluaciones')}</div>
        </div>
        {auditLog.length === 0 ? (
          <EmptyState icon={<ClipboardList size={28} />} title={traducir('aihub.sin_actividad_reciente')} description={traducir('aihub.audit_empty_desc')} />
        ) : (
          <div className="aih-scroll aih-scroll--360">
            {auditLog.map(l => (
              <div key={l.id} className="aih-audit">
                <span className="aih-audit-date">{l.evaluated_at ? fmtDateTime(l.evaluated_at) : ''}</span>
                <span className="aih-audit-module">{l.module || '—'}</span>
                <span className="aih-audit-scope">{l.scope ? traducir(`aihub.scope_${l.scope}`, l.scope) : ''}</span>
                <span className={`aih-audit-action${l.was_blocked ? ' aih-audit-action--blocked' : l.action_taken === 'redacted' ? ' aih-audit-action--redacted' : ''}`}>
                  {l.action_taken ? traducir(`aihub.taken_${l.action_taken}`, l.action_taken) : traducir('aihub.action_none')}
                </span>
                {(l.pii_types_found || []).length > 0 && (
                  <span className="u-warning">{traducir('aihub.pii_found')}: {l.pii_types_found.join(', ')}</span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

/** Proveedor y modelo por función (revisión 2026-11, de contecmind). Vacío = el proveedor por defecto. */
export function RoutingTab({ providers }: { providers: AiProvider[] }) {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const { data } = useQuery({ queryKey: ['ai-routing'], queryFn: () => aiProvidersApi.getRouting().then(r => r.data) })
  const [rutas, setRutas] = useState<Record<string, { provider_id?: string | null; model?: string | null }> | null>(null)
  const actuales = rutas ?? data?.routes ?? {}
  const { mutate: guardar, isPending } = useMutation({
    mutationFn: () => aiProvidersApi.saveRouting(actuales),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['ai-routing'] }); setRutas(null); toast.success(t('aihub.routing_saved')) },
    onError: e => toast.error(extractErr(e, t('aihub.routing_save_error'))),
  })
  const cambiar = (k: string, campo: 'provider_id' | 'model', v: string) =>
    setRutas({ ...actuales, [k]: { ...(actuales[k] || {}), [campo]: v || null } })
  return (
    <div id="aihub-panel-routing" role="tabpanel" className="aih-routing">
      <p className="aih-routing-help">
        {t('aihub.routing_help')}
      </p>
      <div className="aih-routing-grid">
        {(data?.modules || []).map((m: { key: string; label: string }) => {
          const ruta = actuales[m.key] || {}
          const prov = providers.find(p => p.id === ruta.provider_id)
          const lista = `modelos-${m.key}`
          // Nombre de la función en el idioma del operador (el servidor lo manda en castellano).
          const claveModulo = `aihub.modulo.${m.key}`
          const etiqueta = t(claveModulo) !== claveModulo ? t(claveModulo) : m.label
          return (
            <Fragment key={m.key}>
              <Select label={etiqueta} placeholder={false} id={`ruta-${m.key}`} value={ruta.provider_id || ''} onChange={e => cambiar(m.key, 'provider_id', e.target.value)}>
                <option value="">{t('aihub.routing_default')}</option>
                {providers.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
              </Select>
              <Input aria-label={t('aihub.routing_model_for', { label: etiqueta })} list={lista} value={ruta.model || ''} placeholder={prov?.default_model || t('aihub.routing_default_model')} onChange={e => cambiar(m.key, 'model', e.target.value)} inputClassName="aih-input" />
              <datalist id={lista}>{(prov?.available_models || []).map((x: string) => <option key={x} value={x} aria-label={x} />)}</datalist>
            </Fragment>
          )
        })}
      </div>
      <div className="aih-routing-foot">
        <Button onClick={() => guardar()} disabled={isPending || rutas === null} loading={isPending}>{t('common.save')}</Button>
      </div>
    </div>
  )
}

// Revisión 2026-11: gasto de IA de hoy frente al tope diario de la empresa
// (AI_DAILY_BUDGET_USD). Avisa desde AI_DAILY_BUDGET_WARN_PCT; al llegar, las
// llamadas se cortan hasta las 00:00 UTC.
export function GastoDeHoy() {
  const t = useAppT()
  const { data } = useQuery<{ spent_usd: number; budget_usd: number; warn_pct: number; used_pct: number | null; blocked: boolean }>({
    queryKey: ['ai-spend-today'],
    queryFn: () => aiProvidersApi.spendToday().then(r => r.data),
    refetchInterval: POLL_DEFAULT_MS,
  })
  if (!data) return null
  const avisa = data.used_pct !== null && data.used_pct >= data.warn_pct
  const usd = new Intl.NumberFormat(localeActivo(), { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return (
    <div role={data.blocked || avisa ? 'alert' : undefined} className={`aih-spend${data.blocked ? ' aih-spend--blocked' : avisa ? ' aih-spend--warn' : ''}`}>
      {data.budget_usd > 0
        ? t('ai.gasto_con_tope', { gastado: usd.format(data.spent_usd), tope: usd.format(data.budget_usd), pct: fmtNumber(data.used_pct ?? 0, 0) })
        : t('ai.gasto_sin_tope', { gastado: usd.format(data.spent_usd) })}
      {data.blocked && ` · ${t('ai.gasto_cortado')}`}
    </div>
  )
}
