/**
 * BiGovernancePanel.jsx — BI Governance management.
 *
 * Endpoints:
 *   GET  /bi/governance/rules                    -> dict { policy_name: {policy_type, enabled, ...} }
 *   PATCH /bi/governance/rules                   merge update
 *   GET  /bi/governance/audit/access?days=N      -> { items: [{action, resource|dataset_id, user_id, accessed_at, ...}], count }
 *   GET  /bi/governance/overview                 -> overview snapshot
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../../services/api'
import { useAppT } from '../../i18n/AppLangContext'
import { Shield, Plus, RefreshCw, ToggleLeft, ToggleRight, Trash2, Database, MessageCircle, Calendar, Zap, Clock } from 'lucide-react'
import { Card, Button, Tabs, Spinner, EmptyState } from '../ui'
import { useToast } from '../../context/ToastContext'

const POLICY_TYPES = [
  { id: 'data_retention',    label: 'Retención de datos' },
  { id: 'access_control',    label: 'Control de acceso' },
  { id: 'classification',    label: 'Clasificación' },
  { id: 'export_restriction', label: 'Restricción de export' },
  { id: 'masking',           label: 'Enmascaramiento' },
]

const POLICY_TYPE_LABEL = Object.fromEntries(POLICY_TYPES.map(p => [p.id, p.label]))

const fieldLabel = {
  fontSize: 'var(--text-2xs)',
  fontWeight: 700,
  color: 'var(--text-3)',
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
  marginBottom: 6,
}
const inputBase = {
  width: '100%',
  background: 'var(--surface-3)',
  border: '1px solid var(--surface-4)',
  borderRadius: 8,
  padding: '8px 12px',
  color: 'var(--text-1)',
  fontSize: 'var(--text-sm)',
  fontFamily: 'inherit',
  outline: 'none',
  boxSizing: 'border-box',
}
const chip = (color) => ({
  fontSize: 'var(--text-2xs)',
  fontWeight: 700,
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
  color,
  background: `color-mix(in srgb, ${color} 15%, transparent)`,
  border: `1px solid color-mix(in srgb, ${color} 30%, transparent)`,
  borderRadius: 'var(--radius-full, 999px)',
  padding: '2px 9px',
  whiteSpace: 'nowrap',
})

// ── Overview structured renderer ──────────────────────────────────────────────

function OverviewSection({ icon: Icon, iconColor, title, children, badge }) {
  return (
    <div style={{
      background: 'var(--surface-3)',
      border: '1px solid var(--surface-4)',
      borderRadius: 10,
      padding: '14px 16px',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12, gap: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Icon size={14} style={{ color: iconColor }} />
          <span style={{
            fontSize: 'var(--text-2xs)', fontWeight: 700, color: 'var(--text-3)',
            textTransform: 'uppercase', letterSpacing: '0.06em',
          }}>{title}</span>
        </div>
        {badge != null && badge}
      </div>
      {children}
    </div>
  )
}

function MetricRow({ label, value, mono }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      gap: 12, padding: '6px 0', borderTop: '1px solid var(--surface-4)',
      fontSize: 'var(--text-sm)',
    }}>
      <span style={{ color: 'var(--text-3)' }}>{label}</span>
      <span style={{
        color: 'var(--text-1)', fontWeight: 600,
        fontFamily: mono ? 'var(--font-mono)' : 'inherit',
        textAlign: 'right',
        wordBreak: mono ? 'break-all' : 'normal',
        maxWidth: '60%',
      }}>{value}</span>
    </div>
  )
}

function OverviewView({ data }) {
  const ts = data.timestamp ? new Date(data.timestamp) : null
  const olap = data.olap || {}
  const sched = data.scheduled_reports || {}
  const collab = data.collaboration || {}
  const cache = data.cache_policy || {}

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
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* Snapshot timestamp */}
      {ts && (
        <div style={{
          fontSize: 'var(--text-xs)', color: 'var(--text-3)',
          display: 'flex', alignItems: 'center', gap: 6,
        }}>
          <Clock size={12} />
          Snapshot generado: <span style={{ color: 'var(--text-2)' }}>{ts.toLocaleString()}</span>
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 10 }}>
        {/* OLAP */}
        <OverviewSection
          icon={Database}
          iconColor={olapColor}
          title="OLAP store"
          badge={<span style={chip(olapColor)}>{olapAvailable ? 'Disponible' : 'No disponible'}</span>}
        >
          <MetricRow
            label="Antigüedad"
            value={olapStaleness == null
              ? '—'
              : <span style={{ color: stalenessColor, fontWeight: 700 }}>
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
          title="Reports programados"
          badge={<span style={chip(schedColor)}>{schedActive} activos</span>}
        >
          <MetricRow label="Activos" value={schedActive} />
          <MetricRow
            label="Con error"
            value={<span style={{ color: schedError > 0 ? 'var(--danger)' : 'var(--success)', fontWeight: 700 }}>{schedError}</span>}
          />
        </OverviewSection>

        {/* Collaboration */}
        <OverviewSection
          icon={MessageCircle}
          iconColor={collabColor}
          title="Colaboración"
          badge={<span style={chip(collabColor)}>{unresolved} sin resolver</span>}
        >
          <MetricRow
            label="Comentarios sin resolver"
            value={<span style={{ color: collabColor, fontWeight: 700 }}>{unresolved}</span>}
          />
        </OverviewSection>

        {/* Cache policy */}
        <OverviewSection
          icon={Zap}
          iconColor="var(--purple)"
          title="Política de cache (TTL)"
          badge={<span style={chip('var(--purple)')}>{cache.metric_count ?? 0} métricas</span>}
        >
          <MetricRow label="TTL por defecto" value={`${cache.default_ttl_seconds ?? '—'}s`} />
          <MetricRow label="TTL mínimo" value={`${cache.min_ttl_seconds ?? '—'}s`} />
          <MetricRow label="TTL máximo" value={`${cache.max_ttl_seconds ?? '—'}s`} />
        </OverviewSection>
      </div>
    </div>
  )
}

export default function BiGovernancePanel() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [tab, setTab] = useState('policies')
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState({ name: '', policy_type: 'data_retention' })
  const [auditDays, setAuditDays] = useState(30)
  const [auditUserFilter, setAuditUserFilter] = useState('')

  const { data: policiesData, isLoading: policiesLoading } = useQuery({
    queryKey: ['bi-gov-policies'],
    queryFn: () => api.get('/bi/governance/rules').then(r => r.data).catch(() => ({})),
  })

  const { data: auditData, isLoading: auditLoading, refetch: refetchAudit } = useQuery({
    queryKey: ['bi-gov-audit', auditDays, auditUserFilter],
    queryFn: () => api.get('/bi/governance/audit/access', {
      params: { days: auditDays, ...(auditUserFilter ? { user_id: auditUserFilter } : {}) },
    }).then(r => r.data).catch(() => ({ items: [] })),
    enabled: tab === 'audit',
  })

  const { data: overviewData, isLoading: overviewLoading } = useQuery({
    queryKey: ['bi-gov-overview'],
    queryFn: () => api.get('/bi/governance/overview').then(r => r.data).catch(() => null),
    enabled: tab === 'overview',
  })

  // Normalizamos las reglas: backend devuelve un dict { name: {...} } o array
  const rawPolicies = policiesData?.policies ?? policiesData?.items ?? policiesData?.rules ?? policiesData
  const rulesObject = rawPolicies && typeof rawPolicies === 'object' && !Array.isArray(rawPolicies)
    ? rawPolicies
    : {}
  const policies = Array.isArray(rawPolicies)
    ? rawPolicies
    : Object.entries(rulesObject).map(([key, value]) => {
        const r = value && typeof value === 'object' ? value : {}
        return {
          id: r.id ?? key,
          name: r.name ?? key,
          policy_type: r.policy_type ?? 'data_retention',
          enabled: r.enabled ?? r.active ?? true,
          extra: r,
        }
      })

  const createPolicyMutation = useMutation({
    mutationFn: (data) => {
      const next = {
        ...rulesObject,
        [data.name]: {
          ...(rulesObject[data.name] || {}),
          policy_type: data.policy_type,
          enabled: true,
        },
      }
      return api.patch('/bi/governance/rules', next).then(r => r.data)
    },
    onSuccess: () => {
      toast.success('Política creada')
      setShowCreate(false)
      setForm({ name: '', policy_type: 'data_retention' })
      qc.invalidateQueries({ queryKey: ['bi-gov-policies'] })
    },
    onError: (e) => toast.error(e?.response?.data?.detail || 'Error al crear política'),
  })

  const togglePolicyMutation = useMutation({
    mutationFn: ({ name, enabled }) => {
      const next = {
        ...rulesObject,
        [name]: { ...(rulesObject[name] || {}), enabled },
      }
      return api.patch('/bi/governance/rules', next).then(r => r.data)
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['bi-gov-policies'] }),
    onError: (e) => toast.error(e?.response?.data?.detail || 'Error al cambiar estado'),
  })

  const deletePolicyMutation = useMutation({
    mutationFn: (name) => {
      const { [name]: _removed, ...rest } = rulesObject
      return api.patch('/bi/governance/rules', rest).then(r => r.data)
    },
    onSuccess: () => {
      toast.success('Política eliminada')
      qc.invalidateQueries({ queryKey: ['bi-gov-policies'] })
    },
    onError: (e) => toast.error(e?.response?.data?.detail || 'Error al eliminar'),
  })

  const auditItems = auditData?.items ?? auditData?.events ?? auditData?.entries ?? []

  return (
    <Card style={{ padding: '20px 22px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14, gap: 12, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Shield size={18} style={{ color: 'var(--warning)' }} />
          <h2 style={{ fontSize: 'var(--text-md)', fontWeight: 700, color: 'var(--text-1)', margin: 0 }}>
            {t('bi.governance.title', 'Gobernanza BI')}
          </h2>
        </div>
        <span style={chip('var(--accent)')}>{policies.length} políticas</span>
      </div>

      <Tabs
        items={[
          { id: 'policies',  label: 'Políticas' },
          { id: 'audit',     label: 'Auditoría' },
          { id: 'overview',  label: 'Overview' },
        ]}
        active={tab}
        onChange={setTab}
        ariaLabel="Gobernanza BI"
      />

      {tab === 'policies' && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, gap: 8, flexWrap: 'wrap' }}>
            <div style={fieldLabel}>Políticas configuradas</div>
            <Button size="sm" icon={<Plus size={13} />} onClick={() => setShowCreate(v => !v)}>
              {showCreate ? 'Cerrar' : 'Nueva política'}
            </Button>
          </div>

          {showCreate && (
            <div style={{
              background: 'var(--surface-3)',
              border: '1px solid color-mix(in srgb, var(--warning) 30%, var(--surface-4))',
              borderRadius: 12,
              padding: '14px 16px',
              marginBottom: 14,
            }}>
              <div style={fieldLabel}>Nueva política</div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 10 }}>
                <input
                  type="text"
                  placeholder="Nombre (único)"
                  value={form.name}
                  onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                  style={{ ...inputBase, gridColumn: '1 / -1' }}
                />
                <select
                  value={form.policy_type}
                  onChange={e => setForm(f => ({ ...f, policy_type: e.target.value }))}
                  style={{ ...inputBase, gridColumn: '1 / -1' }}
                >
                  {POLICY_TYPES.map(p => <option key={p.id} value={p.id}>{p.label}</option>)}
                </select>
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <Button
                  onClick={() => createPolicyMutation.mutate(form)}
                  disabled={!form.name.trim() || createPolicyMutation.isPending}
                  loading={createPolicyMutation.isPending}
                >Crear</Button>
                <Button variant="secondary" onClick={() => setShowCreate(false)}>Cancelar</Button>
              </div>
            </div>
          )}

          {policiesLoading ? (
            <div style={{ display: 'flex', justifyContent: 'center', padding: 24 }}><Spinner /></div>
          ) : policies.length === 0 ? (
            <EmptyState icon="🛡" title="Sin políticas" description="Crea la primera política para empezar a gobernar tus datos BI." />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {policies.map(p => {
                const typeLabel = POLICY_TYPE_LABEL[p.policy_type] || p.policy_type
                const stateColor = p.enabled ? 'var(--success)' : 'var(--text-3)'
                return (
                  <div key={p.id} style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    padding: '10px 14px',
                    background: 'var(--surface-3)',
                    border: '1px solid var(--surface-4)',
                    borderRadius: 8,
                    gap: 10, flexWrap: 'wrap',
                  }}>
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--text-1)' }}>
                        {p.name}
                      </div>
                      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', marginTop: 2 }}>
                        {typeLabel}
                      </div>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span style={chip(stateColor)}>{p.enabled ? 'Activa' : 'Inactiva'}</span>
                      <button
                        type="button"
                        onClick={() => togglePolicyMutation.mutate({ name: p.name, enabled: !p.enabled })}
                        title={p.enabled ? 'Desactivar' : 'Activar'}
                        style={{
                          background: 'transparent', border: 'none', cursor: 'pointer',
                          color: p.enabled ? 'var(--success)' : 'var(--text-3)',
                          padding: 4, display: 'inline-flex',
                        }}
                      >
                        {p.enabled ? <ToggleRight size={20} /> : <ToggleLeft size={20} />}
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          if (window.confirm(`¿Eliminar política "${p.name}"?`)) {
                            deletePolicyMutation.mutate(p.name)
                          }
                        }}
                        title="Eliminar política"
                        style={{
                          background: 'transparent', border: 'none', cursor: 'pointer',
                          color: 'var(--text-3)', padding: 4, display: 'inline-flex',
                        }}
                        onMouseEnter={e => { e.currentTarget.style.color = 'var(--danger)' }}
                        onMouseLeave={e => { e.currentTarget.style.color = 'var(--text-3)' }}
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {tab === 'audit' && (
        <div>
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: 10, flexWrap: 'wrap', marginBottom: 12 }}>
            <div style={{ minWidth: 100 }}>
              <div style={fieldLabel}>Ventana</div>
              <select value={auditDays} onChange={e => setAuditDays(Number(e.target.value))} style={inputBase}>
                <option value={7}>7 días</option>
                <option value={30}>30 días</option>
                <option value={60}>60 días</option>
                <option value={90}>90 días</option>
              </select>
            </div>
            <div style={{ flex: '1 1 200px' }}>
              <div style={fieldLabel}>Filtrar por user_id</div>
              <input
                type="text"
                placeholder="user_id (opcional)"
                value={auditUserFilter}
                onChange={e => setAuditUserFilter(e.target.value)}
                style={inputBase}
              />
            </div>
            <Button size="sm" variant="secondary" icon={<RefreshCw size={13} />} onClick={() => refetchAudit()}>
              Actualizar
            </Button>
          </div>

          {auditLoading ? (
            <div style={{ display: 'flex', justifyContent: 'center', padding: 24 }}><Spinner /></div>
          ) : auditItems.length === 0 ? (
            <EmptyState icon="📋" title="Sin eventos de auditoría" description={`Ningún evento registrado en los últimos ${auditDays} días.`} />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4, maxHeight: 480, overflowY: 'auto' }}>
              <div style={{
                fontSize: 'var(--text-xs)', color: 'var(--text-3)', marginBottom: 4,
              }}>
                {auditItems.length} evento(s) {auditUserFilter && `· user ${auditUserFilter}`}
              </div>
              {auditItems.map((ev, i) => {
                const action = ev.action || 'view'
                const actionColor = action === 'delete' ? 'var(--danger)'
                  : action === 'create' || action === 'update' ? 'var(--warning)'
                  : 'var(--accent)'
                return (
                  <div key={i} style={{
                    display: 'flex', alignItems: 'center', gap: 10,
                    padding: '8px 12px',
                    background: 'var(--surface-3)',
                    border: '1px solid var(--surface-4)',
                    borderRadius: 8,
                    fontSize: 'var(--text-xs)', color: 'var(--text-2)',
                  }}>
                    <span style={chip(actionColor)}>{action}</span>
                    <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {ev.resource || ev.dataset_id || ev.entity_type || '—'}
                    </span>
                    <span style={{ color: 'var(--text-3)', fontFamily: 'var(--font-mono)', flexShrink: 0 }}>
                      {ev.user_id || '—'}
                    </span>
                    <span style={{ color: 'var(--text-3)', flexShrink: 0 }}>
                      {ev.accessed_at ? new Date(ev.accessed_at).toLocaleString() : ''}
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
          <div style={{ display: 'flex', justifyContent: 'center', padding: 24 }}><Spinner /></div>
        ) : !overviewData ? (
          <EmptyState icon="📊" title="Sin overview" />
        ) : (
          <OverviewView data={overviewData} />
        )
      )}
    </Card>
  )
}
