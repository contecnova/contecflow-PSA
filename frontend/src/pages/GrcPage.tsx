/**
 * GrcPage — Governance, Risk & Compliance (backbone de seguridad)
 *
 * Pestañas:
 *  1. Matriz de permisos — editable por admin, persiste en DB vía API
 *  2. Segregación SoD    — reglas CRUD (POST/PATCH/DELETE)
 *  3. Violaciones SoD    — instancias detectadas, resolución
 *  4. Flujos de mitigación — workflows de aprobación
 *  5. Audit Log          — historial inmutable de eventos GRC
 */
import { useState } from 'react'
import type { CSSProperties } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useToast } from '../context/ToastContext'
import { grcApi, approvalsApi } from '../services/api'
import { advancedConfigApi } from '../services/settingsApi'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { ShieldCheck } from 'lucide-react'
import { Button, Spinner, EmptyState, Modal } from '../components/ui'
import { extractErr } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useAppT } from '../i18n/AppLangContext'

// ── Catálogo de módulos, acciones y roles ────────────────────────────────────
const MODULES = [
  { id: 'projects',     label: 'Proyectos',       icon: '⬡' },
  { id: 'tasks',        label: 'Tareas',           icon: '▦' },
  { id: 'timesheets',   label: 'Timesheets',       icon: '⏱' },
  { id: 'invoices',     label: 'Facturación',      icon: '🧾' },
  { id: 'expenses',     label: 'Gastos',           icon: '💸' },
  { id: 'resources',    label: 'Recursos',         icon: '👥' },
  { id: 'service_desk', label: 'Service Desk',     icon: '🎫' },
  { id: 'contracts',    label: 'Contratos',        icon: '📄' },
  { id: 'clients',      label: 'Clientes/CRM',     icon: '🏢' },
  { id: 'reports',      label: 'Informes/BI',      icon: '📊' },
  { id: 'settings',     label: 'Configuración',    icon: '⚙️' },
  { id: 'approvals',    label: 'Aprobaciones',     icon: '✅' },
  { id: 'alm',          label: 'ALM/Activos',      icon: '🔑' },
  { id: 'hr',           label: 'RRHH/Ausencias',   icon: '🏖' },
  { id: 'grc',          label: 'GRC/Seguridad',    icon: '🛡' },
]

const ACTIONS = ['ver', 'crear', 'editar', 'eliminar', 'aprobar', 'exportar']
const ACTION_LABEL: Record<string, string> = { ver: 'Ver', crear: 'Crear', editar: 'Editar', eliminar: 'Eliminar', aprobar: 'Aprobar', exportar: 'Exportar' }

type Role = { id: string; label: string; color: string }

// ROLES se carga dinámicamente desde la API — ver useRoles() en GrcPage
const FALLBACK_ROLES = [
  { id: 'admin',     label: 'Admin',      color: 'var(--accent)' },
  { id: 'pm',        label: 'PM',         color: '#a78bfa' },
  { id: 'team_lead', label: 'Team Lead',  color: '#0891b2' },
  { id: 'employee',  label: 'Employee',   color: '#34d399' },
  { id: 'hr',        label: 'HR',         color: '#f59e0b' },
  { id: 'subcontractor', label: 'Subcontratado', color: '#f97316' },
]

const RISK_COLOR: Record<string, string> = { critical: '#f87171', high: '#fb923c', medium: '#f59e0b', low: '#34d399' }
const SEV_COLOR: Record<string, string>  = { critical: '#f87171', warning: '#f59e0b', info: '#60a5fa' }

// ── Shared style atoms ────────────────────────────────────────────────────────
const card: CSSProperties = { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12 }
const fs: CSSProperties = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
const ls: CSSProperties = { fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }

// ═══════════════════════════════════════════════════════════════════════════════
// 1. MATRIZ DE PERMISOS (wired to API)
// ═══════════════════════════════════════════════════════════════════════════════
type PermMatrix = Record<string, Record<string, Record<string, boolean>>>

function MatrixTab({ roles }: { roles: Role[] }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [selRole, setSelRole] = useState('all')
  const [saving, setSaving] = useState<string | null>(null)

  const { data, isLoading, refetch } = useQuery<PermMatrix>({
    queryKey: ['grc-permissions'],
    queryFn: () => grcApi.permissions().then(r => r.data.matrix),
  })
  const matrix: PermMatrix = data || {}

  const { mutate: resetMatrix, isPending: resetting } = useMutation({
    mutationFn: () => grcApi.seedPermissions(),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['grc-permissions'] }); toast.success(t('grc.matrix_reset_success')) },
    onError: e => toast.error(extractErr(e, t('grc.error'))),
  })

  const togglePerm = async (role: string, module: string, action: string, current: boolean) => {
    const key = `${role}/${module}/${action}`
    setSaving(key)
    try {
      await grcApi.updatePermission(role, module, action, { allowed: !current })
      qc.invalidateQueries({ queryKey: ['grc-permissions'] })
    } catch (e) {
      toast.error(extractErr(e, t('grc.error_save_permission')))
    } finally {
      setSaving(null)
    }
  }

  const displayRoles = selRole === 'all' ? roles : roles.filter((r: Role) => r.id === selRole)

  if (isLoading) return <Spinner />

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20, flexWrap: 'wrap', gap: 10 }}>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
          <span style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginRight: 4 }}>{t('grc.role')}:</span>
          <button onClick={() => setSelRole('all')}
            style={{ padding: '5px 14px', borderRadius: 6, border: `1px solid ${selRole === 'all' ? 'var(--accent)' : 'var(--surface-4)'}`, background: selRole === 'all' ? 'var(--accent-muted)' : 'transparent', color: selRole === 'all' ? 'var(--accent)' : 'var(--text-2)', fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}>
            {t('grc.all')}
          </button>
          {roles.map(r => (
            <button key={r.id} onClick={() => setSelRole(r.id)}
              style={{ padding: '5px 14px', borderRadius: 6, border: `1px solid ${selRole === r.id ? r.color : 'var(--surface-4)'}`, background: selRole === r.id ? `${r.color}15` : 'transparent', color: selRole === r.id ? r.color : 'var(--text-2)', fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}>
              {r.label}
            </button>
          ))}
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button onClick={() => refetch()} style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 6, padding: '6px 14px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>↻ {t('grc.refresh')}</button>
          <button onClick={() => { openConfirmGlobal({ message: t('grc.reset_confirm'), onConfirm: () => resetMatrix(), danger: true }) }}
            style={{ background: 'transparent', border: '1px solid var(--danger-border)', borderRadius: 6, padding: '6px 14px', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}
            disabled={resetting}>
            {resetting ? t('grc.resetting') : '⟳ ' + t('grc.reset_to_default')}
          </button>
        </div>
      </div>

      <div style={{ overflowX: 'auto' }}>
        <table style={{ borderCollapse: 'collapse', minWidth: 600, width: '100%' }}>
          <thead>
            <tr style={{ borderBottom: '2px solid var(--surface-4)' }}>
              <th style={{ padding: '8px 12px', fontSize: "var(--text-xs)", fontWeight: 600, color: 'var(--text-3)', textAlign: 'left', minWidth: 140, position: 'sticky', left: 0, background: 'var(--surface-2)', textTransform: 'uppercase' }}>{t('grc.module')}</th>
              {displayRoles.map(r => (
                <th key={r.id} colSpan={ACTIONS.length}
                  style={{ padding: '8px 6px', fontSize: "var(--text-xs)", fontWeight: 700, color: r.color, textAlign: 'center', borderLeft: '2px solid var(--surface-4)' }}>
                  {r.label}
                </th>
              ))}
            </tr>
            <tr style={{ borderBottom: '1px solid var(--surface-4)' }}>
              <th style={{ position: 'sticky', left: 0, background: 'var(--surface-2)' }} />
              {displayRoles.map(r => ACTIONS.map(a => (
                <th key={r.id + a} style={{ padding: '5px 3px', fontSize: "var(--text-3xs)", color: 'var(--text-3)', textAlign: 'center', fontWeight: 600, letterSpacing: '0.04em', textTransform: 'uppercase', minWidth: 42 }}>
                  {t(`grc.action_${a}`)}
                </th>
              )))}
            </tr>
          </thead>
          <tbody>
            {MODULES.map((mod, mIdx) => (
              <tr key={mod.id} style={{ borderBottom: '1px solid var(--surface-4)', background: mIdx % 2 === 0 ? 'var(--surface-2)' : 'var(--surface-1)' }}>
                <td style={{ padding: '9px 12px', fontSize: "var(--text-sm)", fontWeight: 600, color: 'var(--text-1)', position: 'sticky', left: 0, background: mIdx % 2 === 0 ? 'var(--surface-2)' : 'var(--surface-1)', whiteSpace: 'nowrap' }}>
                  {mod.icon} {mod.label}
                </td>
                {displayRoles.map(role =>
                  ACTIONS.map(action => {
                    const allowed = matrix[role.id]?.[mod.id]?.[action] ?? false;
                    const key = `${role.id}/${mod.id}/${action}`;
                    const isSaving = saving === key;
                    return (
                      <td
                        key={key}
                        style={{ padding: '6px 3px', textAlign: 'center', cursor: 'pointer' }}
                        onClick={() => togglePerm(role.id, mod.id, action, allowed)}
                        title={`${role.label} · ${mod.label} · ${t(`grc.action_${action}`)}: ${allowed ? t('grc.allowed') : t('grc.denied')} — ${t('grc.click_to_change')}`}
                      >
                        <span style={{ fontSize: "var(--text-md-em)", opacity: isSaving ? 0.4 : 1, transition: 'opacity .15s' }}>
                          {isSaving ? '⟳' : allowed ? '✅' : '❌'}
                        </span>
                      </td>
                    );
                  })
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div style={{ display: 'flex', gap: 20, marginTop: 16, flexWrap: 'wrap' }}>
        {[['✅', t('grc.allowed'), '#34d399'], ['❌', t('grc.denied'), '#f87171']].map(([sym, label, color]) => (
          <div key={sym} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: "var(--text-sm)" }}>
            <span style={{ fontSize: "var(--text-md-em)" }}>{sym}</span><span style={{ color }}>{label}</span>
          </div>
        ))}
        <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', marginLeft: 8 }}>{t('grc.changes_auto_saved')}</span>
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// 2. SEGREGACIÓN SoD (wired to API + CRUD)
// ═══════════════════════════════════════════════════════════════════════════════
type SodRule = {
  [k: string]: unknown
  id: string
  module_a?: string
  action_a?: string
  module_b?: string
  action_b?: string
  risk?: string
  description?: string
  roles_conflict?: string[]
  mitigated_by_workflow_id?: string | null
  is_active?: boolean
}
type Workflow = {
  [k: string]: unknown
  id: string
  name?: string
  entity_type?: string
  is_active?: boolean
  steps?: { id: string; name?: string; approver_role?: string; approver_user_name?: string }[]
}

function SodRuleModal({ rule, workflows, onClose, roles }: { rule: SodRule | null; workflows: Workflow[]; onClose: () => void; roles: Role[] }) {
  const traducir = useAppT()
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const isEdit = !!rule
  const [form, setForm] = useState<{
    module_a: string; action_a: string; module_b: string; action_b: string;
    risk: string; description: string; roles_conflict: string[]; mitigated_by_workflow_id: string | null;
  }>({
    module_a: rule?.module_a || 'invoices',
    action_a: rule?.action_a || 'crear',
    module_b: rule?.module_b || 'invoices',
    action_b: rule?.action_b || 'aprobar',
    risk: rule?.risk || 'high',
    description: rule?.description || '',
    roles_conflict: rule?.roles_conflict || [],
    mitigated_by_workflow_id: rule?.mitigated_by_workflow_id || '',
  })

  const { mutate, isPending } = useMutation({
    mutationFn: (d: typeof form) => isEdit ? grcApi.updateSodRule(rule!.id, d) : grcApi.createSodRule(d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['grc-sod-rules'] }); qc.invalidateQueries({ queryKey: ['grc-sod-check'] }); onClose() },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const toggleRole = (r: string) => setForm(f => ({
    ...f,
    roles_conflict: f.roles_conflict.includes(r) ? f.roles_conflict.filter((x: string) => x !== r) : [...f.roles_conflict, r],
  }))

  return (
    <Modal open title={isEdit ? t('grc.edit_sod_rule') : t('grc.new_sod_rule')} onClose={onClose} width={580}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div style={{ background: 'var(--surface-3)', borderRadius: 8, padding: '12px 14px', fontSize: "var(--text-sm)", color: 'var(--text-2)', lineHeight: 1.6 }}>
          {t('grc.sod_rule_desc1')} <strong style={{ color: 'var(--text-1)' }}>{t('grc.sod_rule_desc2')}</strong>. {t('grc.sod_rule_desc3')}
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 80px', gap: 10, background: 'var(--purple-bg)', border: '1px solid var(--purple-border)', borderRadius: 8, padding: '12px 14px' }}>
          <div>
            <label style={ls}>{t('grc.module_a')}</label>
            <select value={form.module_a} onChange={e => setForm(f => ({ ...f, module_a: e.target.value }))} style={fs}>
              {MODULES.map(m => <option key={m.id} value={m.id}>{m.icon} {m.label}</option>)}
            </select>
          </div>
          <div>
            <label style={ls}>{t('grc.action_a')}</label>
            <select value={form.action_a} onChange={e => setForm(f => ({ ...f, action_a: e.target.value }))} style={fs}>
              {ACTIONS.map(a => <option key={a} value={a}>{ACTION_LABEL[a]}</option>)}
            </select>
          </div>
        </div>
        <div style={{ textAlign: 'center', color: 'var(--text-3)', fontSize: "var(--text-base)" }}>{traducir('grc.en_conflicto_con')}</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 80px', gap: 10, background: 'var(--accent-muted)', border: '1px solid var(--accent-border)', borderRadius: 8, padding: '12px 14px' }}>
          <div>
            <label style={ls}>{t('grc.module_b')}</label>
            <select value={form.module_b} onChange={e => setForm(f => ({ ...f, module_b: e.target.value }))} style={fs}>
              {MODULES.map(m => <option key={m.id} value={m.id}>{m.icon} {m.label}</option>)}
            </select>
          </div>
          <div>
            <label style={ls}>{t('grc.action_b')}</label>
            <select value={form.action_b} onChange={e => setForm(f => ({ ...f, action_b: e.target.value }))} style={fs}>
              {ACTIONS.map(a => <option key={a} value={a}>{ACTION_LABEL[a]}</option>)}
            </select>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          <div>
            <label style={ls}>{t('grc.risk_level')}</label>
            <select value={form.risk} onChange={e => setForm(f => ({ ...f, risk: e.target.value }))} style={fs}>
              {['critical', 'high', 'medium', 'low'].map(r => <option key={r} value={r}>{r}</option>)}
            </select>
          </div>
          <div>
            <label style={ls}>{t('grc.mitigation_flow')}</label>
            <select value={form.mitigated_by_workflow_id || ''} onChange={e => setForm(f => ({ ...f, mitigated_by_workflow_id: e.target.value }))} style={fs}>
              <option value="">{t('grc.no_mitigation')}</option>
              {(workflows || []).map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
            </select>
          </div>
        </div>

        <div>
          <label style={ls}>{t('grc.risk_description')}</label>
          <input value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} style={fs} placeholder={traducir('grc.descripcion_de_la_regla_sod')} aria-label={traducir('grc.descripcion_de_la_regla_sod')} />
        </div>

        <div>
          <label style={ls}>{t('grc.conflicting_roles')}</label>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 4 }}>
            {roles.map(r => (
              <button key={r.id} onClick={() => toggleRole(r.id)}
                style={{ padding: '4px 12px', borderRadius: 6, border: `1px solid ${form.roles_conflict.includes(r.id) ? r.color : 'var(--surface-4)'}`, background: form.roles_conflict.includes(r.id) ? `${r.color}20` : 'transparent', color: form.roles_conflict.includes(r.id) ? r.color : 'var(--text-2)', fontSize: "var(--text-sm)", cursor: 'pointer', fontFamily: 'inherit' }}>
                {r.label}
              </button>
            ))}
          </div>
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
          <Button variant="secondary" onClick={onClose}>{t('grc.cancel')}</Button>
          <Button onClick={() => mutate({ ...form, mitigated_by_workflow_id: form.mitigated_by_workflow_id || null })} loading={isPending} disabled={isPending || !form.description}>
            {isPending ? t('grc.saving') : isEdit ? t('grc.save_changes') : t('grc.create_rule')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

type SodViolation = {
  [k: string]: unknown
  id?: string
  risk?: string
  conflicting_role?: string
  action_a?: string
  module_a?: string
  action_b?: string
  module_b?: string
  mitigated?: boolean
}

function SodTab({ roles }: { roles: Role[] }) {
  const traducir = useAppT()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [showModal, setShowModal] = useState(false)
  const [editingRule, setEditingRule] = useState<SodRule | null>(null)

  const { data: rules = [], isLoading } = useQuery<SodRule[]>({
    queryKey: ['grc-sod-rules'],
    queryFn: () => grcApi.sodRules().then(r => r.data),
  })
  const { data: checkData } = useQuery<{ violations?: SodViolation[] }>({
    queryKey: ['grc-sod-check'],
    queryFn: () => grcApi.sodCheck().then(r => r.data),
    staleTime: 30000,
  })
  const { data: workflows = [] } = useQuery<Workflow[]>({
    queryKey: ['approval-workflows-grc'],
    queryFn: () => approvalsApi.listWorkflows(undefined).then(r => r.data),
  })

  const { mutate: del } = useMutation({
    mutationFn: (id: string) => grcApi.deleteSodRule(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['grc-sod-rules'] }); qc.invalidateQueries({ queryKey: ['grc-sod-check'] }) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: toggle } = useMutation({
    mutationFn: ({ id, active }: { id: string; active: boolean }) => grcApi.updateSodRule(id, { is_active: active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['grc-sod-rules'] }),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const violations = checkData?.violations || []
  const criticalCount = violations.filter((v: SodViolation) => v.risk === 'critical').length

  return (
    <div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 12, marginBottom: 20 }}>
        {[
          { label: t('grc.active_sod_rules'), value: rules.filter((r: SodRule) => r.is_active).length, color: 'var(--accent)', icon: '⚠️' },
          { label: t('grc.detected_conflicts'), value: violations.length, color: violations.length > 0 ? 'var(--warning)' : 'var(--success)', icon: '🔍' },
          { label: t('grc.critical_conflicts'), value: criticalCount, color: criticalCount > 0 ? 'var(--danger)' : 'var(--success)', icon: '🚨' },
        ].map(({ label, value, color, icon }) => (
          <div key={label} style={{ ...card, padding: '14px 18px' }}>
            <div style={{ fontSize: "var(--text-xl)", marginBottom: 6 }}>{icon}</div>
            <div style={{ fontSize: "var(--text-2xl-em)", fontWeight: 800, color }}>{value}</div>
            <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginTop: 4 }}>{label}</div>
          </div>
        ))}
      </div>

      {violations.length > 0 && (
        <div style={{ background: 'rgba(255,71,87,0.08)', border: '1px solid var(--danger-border)', borderRadius: 10, padding: '12px 16px', marginBottom: 20 }}>
          <div style={{ fontSize: "var(--text-base)", fontWeight: 700, color: 'var(--danger)', marginBottom: 8 }}>🚨 {t('grc.sod_conflicts_detected')}</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {violations.map((v: SodViolation, i: number) => (
              <div key={i} style={{ display: 'flex', gap: 10, alignItems: 'center', fontSize: "var(--text-sm)" }}>
                <span style={{ fontSize: "var(--text-2xs)", fontWeight: 700, padding: '2px 6px', borderRadius: 4, background: `${RISK_COLOR[v.risk || '']}20`, color: RISK_COLOR[v.risk || ''], textTransform: 'uppercase', minWidth: 48, textAlign: 'center' }}>{v.risk}</span>
                <span style={{ color: 'var(--text-1)' }}><strong>{v.conflicting_role}</strong> {t('grc.can')} {v.action_a} <em>{v.module_a}</em> {t('grc.and')} {v.action_b} <em>{v.module_b}</em></span>
                {v.mitigated && <span style={{ fontSize: "var(--text-2xs)", color: 'var(--success)', background: 'rgba(0,229,160,0.1)', padding: '1px 6px', borderRadius: 4 }}>✓ {t('grc.mitigated')}</span>}
              </div>
            ))}
          </div>
        </div>
      )}

      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 16 }}>
        <Button onClick={() => setShowModal(true)}>+ {t('grc.new_sod_rule')}</Button>
      </div>

      {isLoading ? <Spinner /> : rules.length === 0 ? (
        <EmptyState icon="⚠️" title={traducir('grc.sin_reglas_sod')} description="Crea reglas para detectar conflictos de segregacion de funciones" />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {rules.map((rule: SodRule) => {
            const rc = RISK_COLOR[rule.risk || ''] || '#7a8aaa'
            const modA = MODULES.find(m => m.id === rule.module_a)
            const modB = MODULES.find(m => m.id === rule.module_b)
            return (
              <div key={rule.id} style={{ ...card, borderLeft: `4px solid ${rc}`, padding: '14px 18px', opacity: rule.is_active ? 1 : 0.55 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                    <span style={{ fontSize: "var(--text-xs)", fontWeight: 700, background: `${rc}20`, color: rc, padding: '2px 8px', borderRadius: 4, textTransform: 'uppercase' }}>{rule.risk}</span>
                    <span style={{ fontSize: "var(--text-base)", fontWeight: 600, color: 'var(--text-1)' }}>{modA?.icon} {modA?.label} · {ACTION_LABEL[rule.action_a || ''] || rule.action_a}</span>
                    <span style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)' }}>{traducir('grc.conflicto_con')}</span>
                    <span style={{ fontSize: "var(--text-base)", fontWeight: 600, color: 'var(--text-1)' }}>{modB?.icon} {modB?.label} · {ACTION_LABEL[rule.action_b || ''] || rule.action_b}</span>
                    {rule.mitigated_by_workflow_id && <span style={{ fontSize: "var(--text-2xs)", padding: '2px 6px', borderRadius: 4, background: 'rgba(0,229,160,0.12)', color: 'var(--success)' }}>✓ Mitigado</span>}
                    {!rule.is_active && <span style={{ fontSize: "var(--text-2xs)", padding: '2px 6px', borderRadius: 4, background: 'var(--surface-4)', color: 'var(--text-3)' }}>Inactiva</span>}
                  </div>
                  <div style={{ display: 'flex', gap: 6 }}>
                    <button onClick={() => toggle({ id: rule.id, active: !rule.is_active })}
                      aria-label={rule.is_active ? 'Desactivar regla SoD' : 'Activar regla SoD'}
                      style={{ background: 'none', border: '1px solid var(--surface-4)', borderRadius: 6, padding: '3px 9px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>
                      {rule.is_active ? '⏸' : '▶'}
                    </button>
                    <button onClick={() => setEditingRule(rule)}
                      aria-label="Editar regla SoD"
                      style={{ background: 'none', border: '1px solid var(--surface-4)', borderRadius: 6, padding: '3px 9px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>✏</button>
                    <button onClick={() => { openConfirmGlobal({ message: '¿Eliminar esta regla SoD?', onConfirm: () => del(rule.id), danger: true }) }}
                      aria-label="Eliminar regla SoD"
                      style={{ background: 'none', border: '1px solid var(--danger-border)', borderRadius: 6, padding: '3px 9px', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>🗑</button>
                  </div>
                </div>
                <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginBottom: (rule.roles_conflict?.length ?? 0) > 0 ? 8 : 0 }}>{rule.description}</div>
                {(rule.roles_conflict?.length ?? 0) > 0 && (
                  <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
                    <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)' }}>{traducir('grc.roles_con_conflicto')}</span>
                    {rule.roles_conflict?.map((r: string) => {
                      const role = roles.find((x: Role) => x.id === r)
                      return role ? <span key={r} style={{ fontSize: "var(--text-xs)", background: `${role.color}20`, color: role.color, padding: '2px 8px', borderRadius: 4, fontWeight: 600 }}>{role.label}</span> : <span key={r} style={{ fontSize: "var(--text-xs)", background: 'var(--surface-3)', color: 'var(--text-2)', padding: '2px 8px', borderRadius: 4 }}>{r}</span>
                    })}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {(showModal || editingRule) && (
        <SodRuleModal rule={editingRule} workflows={workflows} roles={roles} onClose={() => { setShowModal(false); setEditingRule(null) }} />
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// 3. VIOLACIONES SoD
// ═══════════════════════════════════════════════════════════════════════════════
type ViolationRecord = {
  [k: string]: unknown
  id: string
  resolved?: boolean
  role?: string
  user_name?: string
  user_id?: string
  context_type?: string
  context_id?: string
  detected_at?: string
  resolution_note?: string
}

function ViolationsTab() {
  const traducir = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [filter, setFilter] = useState<boolean | null>(false)

  const { data: violations = [], isLoading, refetch } = useQuery<ViolationRecord[]>({
    queryKey: ['grc-violations', filter],
    queryFn: () => grcApi.violations(filter === null ? {} : { resolved: filter }).then(r => r.data),
    refetchInterval: 60000,
  })

  const { mutate: resolve } = useMutation({
    mutationFn: ({ id, note }: { id: string; note: string }) => grcApi.resolveViolation(id, { resolution_note: note }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['grc-violations'] }); toast.success('Violación marcada como resuelta') },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  return (
    <div>
      <div style={{ background: 'rgba(255,71,87,0.06)', border: '1px solid var(--danger-border)', borderRadius: 8, padding: '12px 16px', marginBottom: 18, fontSize: "var(--text-sm)", color: 'var(--text-2)', lineHeight: 1.7 }}>
        <strong style={{ color: 'var(--danger)' }}>Violaciones SoD en tiempo real</strong> {traducir('grc.registradas_cuando_el_mismo_usuario_intenta_realizar')}
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 20 , borderBottom: '1px solid var(--surface-4)', paddingBottom: 12 }}>
        {([[false, 'Pendientes'], [null, 'Todas'], [true, 'Resueltas']] as [boolean | null, string][]).map(([val, label]) => (
          <button key={String(val)} onClick={() => setFilter(val)}
            style={{ padding: '7px 16px', borderRadius: 6, border: `1px solid ${filter === val ? 'var(--accent)' : 'var(--surface-4)'}`, background: filter === val ? 'var(--accent-muted)' : 'transparent', color: filter === val ? 'var(--accent)' : 'var(--text-2)', fontSize: "var(--text-sm)", cursor: 'pointer', fontFamily: 'inherit' }}>
            {label}
          </button>
        ))}
        <button onClick={() => refetch()} aria-label="Refrescar violaciones SoD" style={{ marginLeft: 'auto', background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 6, padding: '6px 12px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>↻</button>
      </div>

      {isLoading ? <Spinner /> : violations.length === 0 ? (
        <EmptyState icon={filter === false ? '✅' : '🔍'} title={filter === false ? 'Sin violaciones pendientes' : 'Sin violaciones registradas'} description={filter === false ? 'No hay violaciones SoD pendientes de resolver' : 'No hay violaciones registradas'} />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {violations.map(v => (
            <div key={v.id} style={{ ...card, padding: '14px 18px', borderLeft: `3px solid ${v.resolved ? 'var(--success)' : 'var(--danger)'}` }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
                <div>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 4 }}>
                    <span style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: v.resolved ? 'var(--success)' : 'var(--danger)' }}>{v.resolved ? '✓ Resuelta' : '✗ Pendiente'}</span>
                    {v.role && <span style={{ fontSize: "var(--text-xs)", padding: '2px 8px', background: 'var(--surface-4)', color: 'var(--text-2)', borderRadius: 4 }}>{v.role}</span>}
                  </div>
                  <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-1)' }}>
                    Usuario: <strong>{v.user_name || v.user_id || '—'}</strong> · Contexto: {v.context_type} ({v.context_id})
                  </div>
                  <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', marginTop: 2 }}>Detectada: {v.detected_at}</div>
                  {v.resolution_note && <div style={{ fontSize: "var(--text-xs)", color: 'var(--success)', marginTop: 2 }}>{traducir('grc.resolucion')} {v.resolution_note}</div>}
                </div>
                {!v.resolved && (
                  <button onClick={() => {
                    const note = window.prompt('Nota de resolución (opcional):') ?? ''
                    resolve({ id: v.id, note })
                  }}
                    style={{ background: 'var(--success-bg)', border: '1px solid rgba(0,229,160,0.3)', borderRadius: 6, padding: '5px 12px', color: 'var(--success)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit', fontWeight: 600, whiteSpace: 'nowrap' }}>
                    ✓ Resolver
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// 4. AUDIT LOG GRC
// ═══════════════════════════════════════════════════════════════════════════════
type AuditEvent = {
  [k: string]: unknown
  id: string
  severity?: string
  action_type?: string
  resource_type?: string
  user_name?: string
  ip_address?: string
  timestamp?: string
  detail?: Record<string, unknown> | null
}

function AuditLogTab() {
  const traducir = useAppT()
  const [severity, setSeverity] = useState('')

  const { data: log = [], isLoading, refetch } = useQuery<AuditEvent[]>({
    queryKey: ['grc-audit-log', severity],
    queryFn: () => grcApi.auditLog(severity ? { severity } : {}).then(r => r.data),
  })

  const ACTION_ICONS: Record<string, string> = {
    permission_changed: '🔑', permission_matrix_reset: '♻️',
    sod_rule_created: '⚠️', sod_rule_updated: '✏️', sod_rule_deleted: '🗑',
    sod_violation_detected: '🚨', sod_violation_resolved: '✅', approval_override: '⚡',
  }

  return (
    <div>
      <div style={{ background: 'var(--surface-3)', borderRadius: 8, padding: '12px 16px', marginBottom: 18, fontSize: "var(--text-sm)", color: 'var(--text-2)', lineHeight: 1.7 }}>
        <strong style={{ color: 'var(--text-1)' }}>Audit Log inmutable GRC</strong> {traducir('grc.todos_los_eventos_de_seguridad_cambios_de')}
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 20, alignItems: 'center' , borderBottom: '1px solid var(--surface-4)', paddingBottom: 12 }}>
        <span style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>Severidad:</span>
        {[['', 'Todas'], ['info', 'Info'], ['warning', 'Aviso'], ['critical', 'Crítico']].map(([val, label]) => (
          <button key={val} onClick={() => setSeverity(val)}
            style={{ padding: '7px 16px', borderRadius: 6, border: `1px solid ${severity === val ? 'var(--accent)' : 'var(--surface-4)'}`, background: severity === val ? 'var(--accent-muted)' : 'transparent', color: severity === val ? 'var(--accent)' : 'var(--text-2)', fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}>
            {label}
          </button>
        ))}
        <button onClick={() => refetch()} aria-label="Refrescar audit log" style={{ marginLeft: 'auto', background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 6, padding: '6px 12px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>↻</button>
      </div>

      {isLoading ? <Spinner /> : log.length === 0 ? (
        <EmptyState icon="📋" title={traducir('grc.sin_eventos_de_auditoria')} description="Los eventos de seguridad apareceran aqui conforme se produzcan" />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 600, overflowY: 'auto', paddingRight: 4 }}>
          {log.map((e: AuditEvent) => {
            const sc = SEV_COLOR[e.severity || ''] || 'var(--text-2)'
            return (
              <div key={e.id} style={{ ...card, padding: '10px 14px', borderLeft: `3px solid ${sc}` }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 4 }}>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <span style={{ fontSize: "var(--text-md-em)" }}>{ACTION_ICONS[e.action_type || ''] || '📋'}</span>
                    <span style={{ fontSize: "var(--text-sm)", fontWeight: 600, color: 'var(--text-1)' }}>{(e.action_type || '').replace(/_/g, ' ')}</span>
                    {e.resource_type && <span style={{ fontSize: "var(--text-2xs)", padding: '1px 6px', background: 'var(--surface-4)', color: 'var(--text-3)', borderRadius: 4 }}>{e.resource_type}</span>}
                    <span style={{ fontSize: "var(--text-2xs)", fontWeight: 700, color: sc, background: `${sc}15`, padding: '1px 6px', borderRadius: 4, textTransform: 'uppercase' }}>{e.severity}</span>
                  </div>
                  <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', whiteSpace: 'nowrap', marginLeft: 12 }}>{e.timestamp}</span>
                </div>
                <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>
                  {e.user_name && <span>Actor: <strong>{e.user_name}</strong>{e.ip_address ? ` · IP: ${e.ip_address}` : ''}</span>}
                  {e.detail && typeof e.detail === 'object' && (
                    <span style={{ marginLeft: 8, fontFamily: 'var(--font-mono)', fontSize: "var(--text-2xs)", color: 'var(--text-3)' }}>
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

function ApprovalsTab() {
  const traducir = useAppT()
  const { data: workflows = [], isLoading } = useQuery<Workflow[]>({
    queryKey: ['approval-workflows-grc'],
    queryFn: () => approvalsApi.listWorkflows(undefined).then(r => r.data),
  })

  return (
    <div>
      <div style={{ marginBottom: 16, padding: '12px 16px', background: 'var(--surface-2)',
        borderRadius: 8, fontSize: "var(--text-sm)", color: 'var(--text-2)', lineHeight: 1.7 }}>
        {traducir('grc.los')} <strong style={{ color: 'var(--text-1)' }}>{traducir('grc.flujos_de_aprobacion')}</strong> {traducir('grc.mitigan_los_riesgos_sod_anadiendo_revision_obligatoria')}{' '}
        <a href="/approvals" style={{ color: 'var(--accent)' }}>Aprobaciones</a>.
      </div>

      {isLoading ? <Spinner /> : workflows.length === 0 ? (
        <EmptyState icon="✅" title={traducir('grc.sin_flujos_de_aprobacion')}
          description="Configura flujos de aprobacion para mitigar riesgos SoD" />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {workflows.map(wf => (
            <div key={wf.id} style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
              borderRadius: 10, padding: '14px 18px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                <div>
                  <span style={{ fontSize: "var(--text-base)", fontWeight: 600, color: 'var(--text-1)', marginRight: 10 }}>
                    {wf.name}
                  </span>
                  <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', background: 'var(--surface-4)',
                    padding: '2px 8px', borderRadius: 4 }}>{wf.entity_type?.replace(/_/g,' ')}</span>
                </div>
                <span style={{ fontSize: "var(--text-xs)", fontWeight: 600,
                  color: wf.is_active ? '#34d399' : 'var(--text-4)' }}>
                  {wf.is_active ? '● Activo' : '○ Inactivo'}
                </span>
              </div>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {(wf.steps || []).map((step, i) => (
                  <div key={step.id} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                    {i > 0 && <span style={{ color: 'var(--text-4)', fontSize: "var(--text-md)" }}>→</span>}
                    <span style={{ fontSize: "var(--text-xs)", background: 'var(--surface-1)',
                      border: '1px solid var(--surface-4)', borderRadius: 6, padding: '3px 10px',
                      color: 'var(--text-2)' }}>
                      {step.name || step.approver_role || step.approver_user_name || 'Paso ' + (i+1)}
                    </span>
                  </div>
                ))}
                {(!wf.steps || wf.steps.length === 0) && (
                  <span style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)' }}>{traducir('grc.sin_pasos_configurados')}</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function GrcPage(): JSX.Element {
  const _t = useAppT()
  const [tab, setTab] = useState('matrix')

  const { data: rawRoles = [] } = useQuery<{ name: string; description?: string; color: string }[]>({
    queryKey: ['custom-roles'],
    queryFn: () => advancedConfigApi.getRoles().then(r => r.data),
  })
  const roles: Role[] = rawRoles.length > 0
    ? rawRoles.map((r: { name: string; description?: string; color: string }) => ({ id: r.name, label: r.description || r.name, color: r.color }))
    : FALLBACK_ROLES

  const TABS = [
    { id: 'matrix',     label: 'Matriz de permisos' },
    { id: 'sod',        label: 'Segregación SoD' },
    { id: 'violations', label: 'Violaciones' },
    { id: 'approvals',  label: 'Flujos de mitigación' },
    { id: 'auditlog',   label: 'Audit Log' },
  ]

  return (
    <PageShell>
      <PageHeader
        icon={<ShieldCheck size={18} />}
        title={_t('grc.title')}
        subtitle={_t('grc.subtitle')}
      />

      <div style={{ display: 'flex', gap: 6, marginBottom: 24, borderBottom: '1px solid var(--surface-4)',
        paddingBottom: 16, flexWrap: 'wrap' }}>
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)} style={{
            padding: '7px 16px', borderRadius: 8,
            border: `1px solid ${tab === t.id ? 'var(--accent)' : 'var(--surface-4)'}`,
            background: tab === t.id ? 'var(--accent-muted)' : 'transparent',
            color: tab === t.id ? 'var(--accent)' : 'var(--text-2)',
            fontSize: "var(--text-sm)", fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
          }}>{t.label}</button>
        ))}
      </div>

      <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
        borderRadius: 12, padding: '20px 22px' }}>
        {tab === 'matrix'     && <MatrixTab roles={roles} />}
        {tab === 'sod'        && <SodTab roles={roles} />}
        {tab === 'violations' && <ViolationsTab />}
        {tab === 'approvals'  && <ApprovalsTab />}
        {tab === 'auditlog'   && <AuditLogTab />}
      </div>
    </PageShell>
  )
}
