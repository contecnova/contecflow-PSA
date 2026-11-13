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
import { useState, useId } from 'react'
import type { CSSProperties } from 'react'
import { openConfirmGlobal, pedirTexto } from '../context/ConfirmContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useToast } from '../context/ToastContext'
import { grcApi, approvalsApi, usersApi, governanceApi } from '../services/api'
import { advancedConfigApi } from '../services/settingsApi'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { ShieldCheck } from 'lucide-react'
import { Button, Spinner, EmptyState, Modal } from '../components/ui'
import { extractErr, downloadBlob } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useAppT } from '../i18n/AppLangContext'
import { alpha } from '../constants/theme'
import { POLL_DEFAULT_MS, STALE_SHORT_MS } from '../constants/timings'

// ── Catálogo de módulos, acciones y roles ────────────────────────────────────
// Revisión GRC 2026-11b: los módulos los da la API (`/grc/permissions` →
// `modules`, derivados de las rutas). Antes había 15 escritos aquí, dos de
// ellos (`service_desk`, `hr`) sin ninguna ruta detrás, y los otros ~95 que la
// matriz sí aplica no se podían ver ni tocar. Esto sólo pone nombre e icono.
const MODULE_LABELS: Record<string, { label: string; icon: string }> = {
  projects:   { label: 'Proyectos',       icon: '⬡' },
  tasks:      { label: 'Tareas',           icon: '▦' },
  timesheets: { label: 'Timesheets',       icon: '⏱' },
  invoices:   { label: 'Facturación',      icon: '🧾' },
  expenses:   { label: 'Gastos',           icon: '💸' },
  resources:  { label: 'Recursos',         icon: '👥' },
  sd:         { label: 'Service Desk',     icon: '🎫' },
  contracts:  { label: 'Contratos',        icon: '📄' },
  clients:    { label: 'Clientes/CRM',     icon: '🏢' },
  reports:    { label: 'Informes/BI',      icon: '📊' },
  settings:   { label: 'Configuración',    icon: '⚙️' },
  approvals:  { label: 'Aprobaciones',     icon: '✅' },
  alm:        { label: 'ALM/Activos',      icon: '🔑' },
  absences:   { label: 'Ausencias',        icon: '🏖' },
  grc:        { label: 'GRC/Seguridad',    icon: '🛡' },
}
const moduleInfo = (id?: string) => ({ id: id || '', ...(MODULE_LABELS[id || ''] || { label: id || '', icon: '·' }) })

type PermResponse = { matrix: PermMatrix; modules?: string[]; roles?: string[] }

/** La matriz efectiva con sus módulos y roles, como la devuelve la API (caché compartida). */
function usePermisos() {
  return useQuery<PermResponse>({
    queryKey: ['grc-permissions'],
    queryFn: () => grcApi.permissions().then(r => r.data as PermResponse),
  })
}

type PermMatrix = Record<string, Record<string, Record<string, boolean>>>

const ACTIONS = ['ver', 'crear', 'editar', 'eliminar', 'aprobar', 'exportar']
const ACTION_LABEL: Record<string, string> = { ver: 'Ver', crear: 'Crear', editar: 'Editar', eliminar: 'Eliminar', aprobar: 'Aprobar', exportar: 'Exportar' }

type Role = { id: string; label: string; color: string }

// ROLES se carga dinámicamente desde la API — ver useRoles() en GrcPage
const FALLBACK_ROLES = [
  { id: 'admin',     label: 'Admin',      color: 'var(--accent)' },
  { id: 'pm',        label: 'PM',         color: 'var(--purple)' },
  { id: 'team_lead', label: 'Team Lead',  color: 'var(--sky-blue)' },
  { id: 'employee',  label: 'Employee',   color: 'var(--success)' },
  { id: 'hr',        label: 'HR',         color: 'var(--warning)' },
  { id: 'subcontractor', label: 'Subcontratado', color: 'var(--orange)' },
]

const RISK_COLOR: Record<string, string> = { critical: 'var(--danger)', high: 'var(--orange)', medium: 'var(--warning)', low: 'var(--success)' }
const SEV_COLOR: Record<string, string>  = { critical: 'var(--danger)', warning: 'var(--warning)', info: 'var(--info)' }

// ── Shared style atoms ────────────────────────────────────────────────────────
const card: CSSProperties = { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12 }
const fs: CSSProperties = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
const ls: CSSProperties = { fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }

// ═══════════════════════════════════════════════════════════════════════════════
// 1. MATRIZ DE PERMISOS (wired to API)
// ═══════════════════════════════════════════════════════════════════════════════

function MatrixTab({ roles }: { roles: Role[] }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [selRole, setSelRole] = useState('all')
  const [saving, setSaving] = useState<string | null>(null)
  const [filtro, setFiltro] = useState('')

  const { data, isLoading, refetch } = usePermisos()
  const matrix: PermMatrix = data?.matrix || {}
  const modulos = (data?.modules || Object.keys(Object.values(matrix)[0] || {}))
    .map(moduleInfo)
    .filter(m => !filtro || `${m.id} ${m.label}`.toLowerCase().includes(filtro.toLowerCase()))
  // Las columnas son los roles que la matriz gobierna (los de la API); el
  // nombre y el color salen de los roles configurados si existen.
  const rolesDeLaMatriz: Role[] = (data?.roles || roles.map(r => r.id)).map(id =>
    roles.find(r => r.id === id) || FALLBACK_ROLES.find(r => r.id === id) || { id, label: id, color: 'var(--text-2)' })

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

  const displayRoles = selRole === 'all' ? rolesDeLaMatriz : rolesDeLaMatriz.filter((r: Role) => r.id === selRole)

  if (isLoading) return <Spinner />

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20, flexWrap: 'wrap', gap: 10 }}>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
          <span style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginRight: 4 }}>{t('grc.role')}:</span>
          <button onClick={() => setSelRole('all')}
            style={{ padding: '5px 14px', borderRadius: 'var(--radius-sm)', border: `1px solid ${selRole === 'all' ? 'var(--accent)' : 'var(--surface-4)'}`, background: selRole === 'all' ? 'var(--accent-muted)' : 'transparent', color: selRole === 'all' ? 'var(--accent)' : 'var(--text-2)', fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}>
            {t('grc.all')}
          </button>
          {rolesDeLaMatriz.map(r => (
            <button key={r.id} onClick={() => setSelRole(r.id)}
              style={{ padding: '5px 14px', borderRadius: 'var(--radius-sm)', border: `1px solid ${selRole === r.id ? r.color : 'var(--surface-4)'}`, background: selRole === r.id ? alpha(r.color, '15') : 'transparent', color: selRole === r.id ? r.color : 'var(--text-2)', fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}>
              {r.label}
            </button>
          ))}
        </div>
        <div className="u-row-8">
          <input value={filtro} onChange={e => setFiltro(e.target.value)} placeholder="Filtrar módulos…"
            aria-label="Filtrar módulos" style={{ ...fs, width: 180, padding: '6px 10px' }} />
          <button onClick={() => refetch()} style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-sm)', padding: '6px 14px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>↻ {t('grc.refresh')}</button>
          <button onClick={() => { openConfirmGlobal({ message: t('grc.reset_confirm'), onConfirm: () => resetMatrix(), danger: true }) }}
            style={{ background: 'transparent', border: '1px solid var(--danger-border)', borderRadius: 'var(--radius-sm)', padding: '6px 14px', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}
            disabled={resetting}>
            {resetting ? t('grc.resetting') : '⟳ ' + t('grc.reset_to_default')}
          </button>
        </div>
      </div>

      <div className="u-scroll-x">
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
            <tr className="u-border-b">
              <th style={{ position: 'sticky', left: 0, background: 'var(--surface-2)' }} />
              {displayRoles.map(r => ACTIONS.map(a => (
                <th key={r.id + a} style={{ padding: '5px 3px', fontSize: "var(--text-3xs)", color: 'var(--text-3)', textAlign: 'center', fontWeight: 600, letterSpacing: '0.04em', textTransform: 'uppercase', minWidth: 42 }}>
                  {t(`grc.action_${a}`)}
                </th>
              )))}
            </tr>
          </thead>
          <tbody>
            {modulos.map((mod, mIdx) => (
              <tr key={mod.id} style={{ borderBottom: '1px solid var(--surface-4)', background: mIdx % 2 === 0 ? 'var(--surface-2)' : 'var(--surface-1)' }}>
                <td style={{ padding: '9px 12px', fontSize: "var(--text-sm)", fontWeight: 600, color: 'var(--text-1)', position: 'sticky', left: 0, background: mIdx % 2 === 0 ? 'var(--surface-2)' : 'var(--surface-1)', whiteSpace: 'nowrap' }}>
                  {mod.icon} {mod.label}
                </td>
                {displayRoles.map(role =>
                  ACTIONS.map(action => {
                    const celda = matrix[role.id]?.[mod.id]?.[action];
                    const key = `${role.id}/${mod.id}/${action}`;
                    const isSaving = saving === key;
                    // Sin casilla: el módulo no tiene esa operación (nada que gobernar).
                    if (celda === undefined) return <td key={key} style={{ padding: '6px 3px', textAlign: 'center', color: 'var(--text-3)' }}>—</td>;
                    const allowed = celda;
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
        {[['✅', t('grc.allowed'), 'var(--success)'], ['❌', t('grc.denied'), 'var(--danger)']].map(([sym, label, color]) => (
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
  const idCampo = useId()
  const traducir = useAppT()
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const isEdit = !!rule
  const { data: permisos } = usePermisos()
  const MODULES = (permisos?.modules || Object.keys(MODULE_LABELS)).map(moduleInfo)
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
      <div className="u-stack-14">
        <div style={{ background: 'var(--surface-3)', borderRadius: 8, padding: '12px 14px', fontSize: "var(--text-sm)", color: 'var(--text-2)', lineHeight: 1.6 }}>
          {t('grc.sod_rule_desc1')} <strong className="u-text1">{t('grc.sod_rule_desc2')}</strong>. {t('grc.sod_rule_desc3')}
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 80px', gap: 10, background: 'var(--purple-bg)', border: '1px solid var(--purple-border)', borderRadius: 8, padding: '12px 14px' }}>
          <div>
            <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={ls}>{t('grc.module_a')}</label>
            <select id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.module_a} onChange={e => setForm(f => ({ ...f, module_a: e.target.value }))} style={fs}>
              {MODULES.map(m => <option key={m.id} value={m.id}>{m.icon} {m.label}</option>)}
            </select>
          </div>
          <div>
            <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} style={ls}>{t('grc.action_a')}</label>
            <select id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.action_a} onChange={e => setForm(f => ({ ...f, action_a: e.target.value }))} style={fs}>
              {ACTIONS.map(a => <option key={a} value={a}>{ACTION_LABEL[a]}</option>)}
            </select>
          </div>
        </div>
        <div style={{ textAlign: 'center', color: 'var(--text-3)', fontSize: "var(--text-base)" }}>{traducir('grc.en_conflicto_con')}</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 80px', gap: 10, background: 'var(--accent-muted)', border: '1px solid var(--accent-border)', borderRadius: 8, padding: '12px 14px' }}>
          <div>
            <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} style={ls}>{t('grc.module_b')}</label>
            <select id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={form.module_b} onChange={e => setForm(f => ({ ...f, module_b: e.target.value }))} style={fs}>
              {MODULES.map(m => <option key={m.id} value={m.id}>{m.icon} {m.label}</option>)}
            </select>
          </div>
          <div>
            <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} style={ls}>{t('grc.action_b')}</label>
            <select id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={form.action_b} onChange={e => setForm(f => ({ ...f, action_b: e.target.value }))} style={fs}>
              {ACTIONS.map(a => <option key={a} value={a}>{ACTION_LABEL[a]}</option>)}
            </select>
          </div>
        </div>

        <div className="u-grid2-10">
          <div>
            <label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} style={ls}>{t('grc.risk_level')}</label>
            <select id={`${idCampo}-5`} aria-labelledby={`${idCampo}-et5`} value={form.risk} onChange={e => setForm(f => ({ ...f, risk: e.target.value }))} style={fs}>
              {['critical', 'high', 'medium', 'low'].map(r => <option key={r} value={r}>{r}</option>)}
            </select>
          </div>
          <div>
            <label id={`${idCampo}-et6`} htmlFor={`${idCampo}-6`} style={ls}>{t('grc.mitigation_flow')}</label>
            <select id={`${idCampo}-6`} aria-labelledby={`${idCampo}-et6`} value={form.mitigated_by_workflow_id || ''} onChange={e => setForm(f => ({ ...f, mitigated_by_workflow_id: e.target.value }))} style={fs}>
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
                style={{ padding: '4px 12px', borderRadius: 'var(--radius-sm)', border: `1px solid ${form.roles_conflict.includes(r.id) ? r.color : 'var(--surface-4)'}`, background: form.roles_conflict.includes(r.id) ? alpha(r.color, '20') : 'transparent', color: form.roles_conflict.includes(r.id) ? r.color : 'var(--text-2)', fontSize: "var(--text-sm)", cursor: 'pointer', fontFamily: 'inherit' }}>
                {r.label}
              </button>
            ))}
          </div>
        </div>

        <div className="u-actions-10">
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
    staleTime: STALE_SHORT_MS,
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
        <div style={{ background: 'rgba(255,71,87,0.08)', border: '1px solid var(--danger-border)', borderRadius: 'var(--radius-md)', padding: '12px 16px', marginBottom: 20 }}>
          <div style={{ fontSize: "var(--text-base)", fontWeight: 700, color: 'var(--danger)', marginBottom: 8 }}>🚨 {t('grc.sod_conflicts_detected')}</div>
          <div className="u-stack-6">
            {violations.map((v: SodViolation, i: number) => (
              <div key={i} style={{ display: 'flex', gap: 10, alignItems: 'center', fontSize: "var(--text-sm)" }}>
                <span style={{ fontSize: "var(--text-2xs)", fontWeight: 700, padding: '2px 6px', borderRadius: 4, background: alpha(RISK_COLOR[v.risk || ''], '20'), color: RISK_COLOR[v.risk || ''], textTransform: 'uppercase', minWidth: 48, textAlign: 'center' }}>{v.risk}</span>
                <span className="u-text1"><strong>{v.conflicting_role}</strong> {t('grc.can')} {v.action_a} <em>{v.module_a}</em> {t('grc.and')} {v.action_b} <em>{v.module_b}</em></span>
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
        <div className="u-stack-10">
          {rules.map((rule: SodRule) => {
            const rc = RISK_COLOR[rule.risk || ''] || '#7a8aaa'
            const modA = moduleInfo(rule.module_a)
            const modB = moduleInfo(rule.module_b)
            return (
              <div key={rule.id} style={{ ...card, borderLeft: `4px solid ${rc}`, padding: '14px 18px', opacity: rule.is_active ? 1 : 0.55 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                  <div className="u-wrap-center-8">
                    <span style={{ fontSize: "var(--text-xs)", fontWeight: 700, background: alpha(rc, '20'), color: rc, padding: '2px 8px', borderRadius: 4, textTransform: 'uppercase' }}>{rule.risk}</span>
                    <span className="u-text1-base-600">{modA?.icon} {modA?.label} · {ACTION_LABEL[rule.action_a || ''] || rule.action_a}</span>
                    <span className="u-text3-sm">{traducir('grc.conflicto_con')}</span>
                    <span className="u-text1-base-600">{modB?.icon} {modB?.label} · {ACTION_LABEL[rule.action_b || ''] || rule.action_b}</span>
                    {rule.mitigated_by_workflow_id && <span style={{ fontSize: "var(--text-2xs)", padding: '2px 6px', borderRadius: 4, background: 'rgba(0,229,160,0.12)', color: 'var(--success)' }}>✓ Mitigado</span>}
                    {!rule.is_active && <span style={{ fontSize: "var(--text-2xs)", padding: '2px 6px', borderRadius: 4, background: 'var(--surface-4)', color: 'var(--text-3)' }}>Inactiva</span>}
                  </div>
                  <div className="u-row-6">
                    <button onClick={() => toggle({ id: rule.id, active: !rule.is_active })}
                      aria-label={rule.is_active ? 'Desactivar regla SoD' : 'Activar regla SoD'}
                      style={{ background: 'none', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-sm)', padding: '3px 9px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>
                      {rule.is_active ? '⏸' : '▶'}
                    </button>
                    <button onClick={() => setEditingRule(rule)}
                      aria-label="Editar regla SoD"
                      style={{ background: 'none', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-sm)', padding: '3px 9px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>✏</button>
                    <button onClick={() => { openConfirmGlobal({ message: '¿Eliminar esta regla SoD?', onConfirm: () => del(rule.id), danger: true }) }}
                      aria-label="Eliminar regla SoD"
                      style={{ background: 'none', border: '1px solid var(--danger-border)', borderRadius: 'var(--radius-sm)', padding: '3px 9px', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>🗑</button>
                  </div>
                </div>
                <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginBottom: (rule.roles_conflict?.length ?? 0) > 0 ? 8 : 0 }}>{rule.description}</div>
                {(rule.roles_conflict?.length ?? 0) > 0 && (
                  <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
                    <span className="u-text3-xs">{traducir('grc.roles_con_conflicto')}</span>
                    {rule.roles_conflict?.map((r: string) => {
                      const role = roles.find((x: Role) => x.id === r)
                      return role ? <span key={r} style={{ fontSize: "var(--text-xs)", background: alpha(role.color, '20'), color: role.color, padding: '2px 8px', borderRadius: 4, fontWeight: 600 }}>{role.label}</span> : <span key={r} style={{ fontSize: "var(--text-xs)", background: 'var(--surface-3)', color: 'var(--text-2)', padding: '2px 8px', borderRadius: 4 }}>{r}</span>
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
    refetchInterval: POLL_DEFAULT_MS,
  })

  const { mutate: resolve } = useMutation({
    mutationFn: ({ id, note }: { id: string; note: string }) => grcApi.resolveViolation(id, { resolution_note: note }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['grc-violations'] }); toast.success('Violación marcada como resuelta') },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  return (
    <div>
      <div style={{ background: 'rgba(255,71,87,0.06)', border: '1px solid var(--danger-border)', borderRadius: 8, padding: '12px 16px', marginBottom: 18, fontSize: "var(--text-sm)", color: 'var(--text-2)', lineHeight: 1.7 }}>
        <strong className="u-danger">Violaciones SoD en tiempo real</strong> {traducir('grc.registradas_cuando_el_mismo_usuario_intenta_realizar')}
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 20 , borderBottom: '1px solid var(--surface-4)', paddingBottom: 12 }}>
        {([[false, 'Pendientes'], [null, 'Todas'], [true, 'Resueltas']] as [boolean | null, string][]).map(([val, label]) => (
          <button key={String(val)} onClick={() => setFilter(val)}
            style={{ padding: '7px 16px', borderRadius: 'var(--radius-sm)', border: `1px solid ${filter === val ? 'var(--accent)' : 'var(--surface-4)'}`, background: filter === val ? 'var(--accent-muted)' : 'transparent', color: filter === val ? 'var(--accent)' : 'var(--text-2)', fontSize: "var(--text-sm)", cursor: 'pointer', fontFamily: 'inherit' }}>
            {label}
          </button>
        ))}
        <button onClick={() => refetch()} aria-label="Refrescar violaciones SoD" style={{ marginLeft: 'auto', background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-sm)', padding: '6px 12px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>↻</button>
      </div>

      {isLoading ? <Spinner /> : violations.length === 0 ? (
        <EmptyState icon={filter === false ? '✅' : '🔍'} title={filter === false ? 'Sin violaciones pendientes' : 'Sin violaciones registradas'} description={filter === false ? 'No hay violaciones SoD pendientes de resolver' : 'No hay violaciones registradas'} />
      ) : (
        <div className="u-stack-10">
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
                  <div className="u-text3-xs-mt2">Detectada: {v.detected_at}</div>
                  {v.resolution_note && <div style={{ fontSize: "var(--text-xs)", color: 'var(--success)', marginTop: 2 }}>{traducir('grc.resolucion')} {v.resolution_note}</div>}
                </div>
                {!v.resolved && (
                  <button onClick={async () => {
                    const note = await pedirTexto({ title: 'Resolver violación', message: 'Puedes añadir una nota de resolución.', label: 'Nota de resolución (opcional)', multiline: true, confirmLabel: 'Resolver' })
                    if (note === null) return
                    resolve({ id: v.id, note })
                  }}
                    style={{ background: 'var(--success-bg)', border: '1px solid rgba(0,229,160,0.3)', borderRadius: 'var(--radius-sm)', padding: '5px 12px', color: 'var(--success)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit', fontWeight: 600, whiteSpace: 'nowrap' }}>
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
        <strong className="u-text1">Audit Log inmutable GRC</strong> {traducir('grc.todos_los_eventos_de_seguridad_cambios_de')}
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 20, alignItems: 'center' , borderBottom: '1px solid var(--surface-4)', paddingBottom: 12 }}>
        <span className="u-text2-sm">Severidad:</span>
        {[['', 'Todas'], ['info', 'Info'], ['warning', 'Aviso'], ['critical', 'Crítico']].map(([val, label]) => (
          <button key={val} onClick={() => setSeverity(val)}
            style={{ padding: '7px 16px', borderRadius: 'var(--radius-sm)', border: `1px solid ${severity === val ? 'var(--accent)' : 'var(--surface-4)'}`, background: severity === val ? 'var(--accent-muted)' : 'transparent', color: severity === val ? 'var(--accent)' : 'var(--text-2)', fontSize: "var(--text-xs)", cursor: 'pointer', fontFamily: 'inherit' }}>
            {label}
          </button>
        ))}
        <button onClick={() => refetch()} aria-label="Refrescar audit log" style={{ marginLeft: 'auto', background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-sm)', padding: '6px 12px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>↻</button>
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
                  <div className="u-row-center-8">
                    <span style={{ fontSize: "var(--text-md-em)" }}>{ACTION_ICONS[e.action_type || ''] || '📋'}</span>
                    <span className="u-text1-sm-600">{(e.action_type || '').replace(/_/g, ' ')}</span>
                    {e.resource_type && <span style={{ fontSize: "var(--text-2xs)", padding: '1px 6px', background: 'var(--surface-4)', color: 'var(--text-3)', borderRadius: 4 }}>{e.resource_type}</span>}
                    <span style={{ fontSize: "var(--text-2xs)", fontWeight: 700, color: sc, background: alpha(sc, '15'), padding: '1px 6px', borderRadius: 4, textTransform: 'uppercase' }}>{e.severity}</span>
                  </div>
                  <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', whiteSpace: 'nowrap', marginLeft: 12 }}>{e.timestamp}</span>
                </div>
                <div className="u-text2-xs">
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
        {traducir('grc.los')} <strong className="u-text1">{traducir('grc.flujos_de_aprobacion')}</strong> {traducir('grc.mitigan_los_riesgos_sod_anadiendo_revision_obligatoria')}{' '}
        <a href="/approvals" className="u-accent">Aprobaciones</a>.
      </div>

      {isLoading ? <Spinner /> : workflows.length === 0 ? (
        <EmptyState icon="✅" title={traducir('grc.sin_flujos_de_aprobacion')}
          description="Configura flujos de aprobacion para mitigar riesgos SoD" />
      ) : (
        <div className="u-stack-10">
          {workflows.map(wf => (
            <div key={wf.id} style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
              borderRadius: 'var(--radius-md)', padding: '14px 18px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                <div>
                  <span style={{ fontSize: "var(--text-base)", fontWeight: 600, color: 'var(--text-1)', marginRight: 10 }}>
                    {wf.name}
                  </span>
                  <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', background: 'var(--surface-4)',
                    padding: '2px 8px', borderRadius: 4 }}>{wf.entity_type?.replace(/_/g,' ')}</span>
                </div>
                <span style={{ fontSize: "var(--text-xs)", fontWeight: 600,
                  color: wf.is_active ? 'var(--success)' : 'var(--text-4)' }}>
                  {wf.is_active ? '● Activo' : '○ Inactivo'}
                </span>
              </div>
              <div className="u-wrap-6">
                {(wf.steps || []).map((step, i) => (
                  <div key={step.id} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                    {i > 0 && <span style={{ color: 'var(--text-4)', fontSize: "var(--text-md)" }}>→</span>}
                    <span style={{ fontSize: "var(--text-xs)", background: 'var(--surface-1)',
                      border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-sm)', padding: '3px 10px',
                      color: 'var(--text-2)' }}>
                      {step.name || step.approver_role || step.approver_user_name || 'Paso ' + (i+1)}
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

type CapaDeAcceso = { layer: string; verdict: 'allow' | 'deny' | 'not_applicable' | 'unknown'; detail: string; [k: string]: unknown }
type Explicacion = { verdict: 'allow' | 'deny' | 'unknown'; decided_by: string | null; template: string | null; path: string; method: string;
  user: { name?: string; role: string }; layers: CapaDeAcceso[] }

const COLOR_VEREDICTO: Record<string, string> = { allow: 'var(--success)', deny: 'var(--danger)', unknown: 'var(--warning)', not_applicable: 'var(--text-3)' }

type ControlMedido = { id: string; status: 'pass' | 'attention' | 'info' | 'not_measurable'; measured: Record<string, unknown>; source: string; frameworks: string[] }
type InformeDeCumplimiento = { generated_at: string; organization_name?: string; summary: Record<string, number>; controls: ControlMedido[] }
const COLOR_CONTROL: Record<string, string> = { pass: 'var(--success)', attention: 'var(--danger)', info: 'var(--accent)', not_measurable: 'var(--text-3)' }

type PoliticaDeRetencion = { entity: string; hold_fields: string[]; keep_days: number | null; is_active: boolean; last_run_at: string | null; last_deleted: number | null }
type Bloqueo = { id: string; case_reference: string; reason?: string; entity: string; field: string; value: string; is_active: boolean; created_at: string; released_at?: string }

/** Retención por tipo de registro y bloqueo legal (revisión 2026-11). */
function RetencionTab() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { data } = useQuery<{ policies: PoliticaDeRetencion[]; min_days: number }>({
    queryKey: ['retention'], queryFn: () => governanceApi.retentionPolicies().then(r => r.data),
  })
  const { data: bloqueos = [] } = useQuery<Bloqueo[]>({ queryKey: ['legal-holds'], queryFn: () => governanceApi.legalHolds().then(r => r.data) })
  const [dias, setDias] = useState<Record<string, string>>({})
  const [previas, setPrevias] = useState<Record<string, { expired: number; held: number; would_delete: number }>>({})
  const [nuevo, setNuevo] = useState({ case_reference: '', reason: '', entity: '*', field: 'client_id', value: '' })
  const error = (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
  const refrescar = () => { qc.invalidateQueries({ queryKey: ['retention'] }); qc.invalidateQueries({ queryKey: ['legal-holds'] }) }
  const diasDe = (p: PoliticaDeRetencion) => Number(dias[p.entity] ?? p.keep_days ?? 365)
  const previa = async (p: PoliticaDeRetencion) => {
    try { const r = await governanceApi.retentionPreview(p.entity, diasDe(p)); setPrevias(v => ({ ...v, [p.entity]: r.data })) } catch (e) { error(e) }
  }
  const guardar = async (p: PoliticaDeRetencion, activa: boolean) => {
    try { await governanceApi.saveRetention(p.entity, { keep_days: diasDe(p), is_active: activa }); toast.success(t('grc.retencion_guardada')); refrescar() } catch (e) { error(e) }
  }
  const aplicar = async () => {
    try {
      const r = await governanceApi.retentionRun()
      const total = Object.values(r.data as Record<string, { deleted: number }>).reduce((a, x) => a + x.deleted, 0)
      toast.success(t('grc.retencion_aplicada', { n: total })); refrescar()
    } catch (e) { error(e) }
  }
  const crear = async () => {
    try { await governanceApi.createLegalHold(nuevo); setNuevo({ ...nuevo, case_reference: '', reason: '', value: '' }); refrescar() } catch (e) { error(e) }
  }
  const campos = Array.from(new Set((data?.policies || []).filter(p => nuevo.entity === '*' || p.entity === nuevo.entity).flatMap(p => p.hold_fields)))
  const campo: CSSProperties = { background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '6px 9px', color: 'var(--text-1)', fontFamily: 'inherit', fontSize: 'var(--text-sm)' }
  const th: CSSProperties = { textAlign: 'left', padding: '6px 8px', fontSize: 'var(--text-xs)', color: 'var(--text-3)', textTransform: 'uppercase' }
  if (!data) return <Spinner />
  return (
    <div style={{ display: 'grid', gap: 22 }}>
      <section>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
          <h3 style={{ margin: 0, fontSize: 'var(--text-md)', flex: 1 }}>{t('grc.retencion_titulo')}</h3>
          <Button size="sm" variant="secondary" onClick={aplicar}>{t('grc.retencion_aplicar_ya')}</Button>
        </div>
        <p style={{ margin: '0 0 10px', fontSize: 'var(--text-sm)', color: 'var(--text-2)' }}>{t('grc.retencion_intro', { min: data.min_days })}</p>
        <table className="u-table-sm">
          <thead><tr><th style={th}>{t('grc.retencion_tipo')}</th><th style={th}>{t('grc.retencion_dias')}</th><th style={th}>{t('grc.retencion_previa')}</th><th style={th}>{t('grc.retencion_estado')}</th><th style={th} /></tr></thead>
          <tbody>
            {data.policies.map(p => {
              const v = previas[p.entity]
              return (
                <tr key={p.entity} style={{ borderTop: '1px solid var(--surface-4)' }}>
                  <td style={{ padding: 8, fontWeight: 600 }}>{t(`grc.retencion_tipo_${p.entity}`)}</td>
                  <td style={{ padding: 8 }}>
                    <input type="number" min={data.min_days} aria-label={t('grc.retencion_dias')} value={dias[p.entity] ?? p.keep_days ?? ''} placeholder="365"
                      onChange={e => setDias(d => ({ ...d, [p.entity]: e.target.value }))} style={{ ...campo, width: 90 }} />
                  </td>
                  <td style={{ padding: 8, color: 'var(--text-2)' }}>
                    {v ? t('grc.retencion_previa_resultado', { borraria: v.would_delete, retenidos: v.held, vencidos: v.expired })
                      : <button type="button" onClick={() => previa(p)} style={{ background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer', fontFamily: 'inherit', fontSize: 'var(--text-sm)', padding: 0 }}>{t('grc.retencion_ver_previa')}</button>}
                  </td>
                  <td style={{ padding: 8, color: p.is_active ? 'var(--success)' : 'var(--text-3)' }}>
                    {p.is_active ? t('grc.retencion_activa') : t('grc.retencion_apagada')}
                    {p.last_run_at && <div className="u-text3-xs">{t('grc.retencion_ultima', { n: p.last_deleted ?? 0, fecha: new Date(p.last_run_at).toLocaleString() })}</div>}
                  </td>
                  <td style={{ padding: 8, whiteSpace: 'nowrap' }}>
                    <Button size="sm" variant={p.is_active ? 'secondary' : 'primary'} onClick={() => guardar(p, !p.is_active)}>
                      {p.is_active ? t('grc.retencion_apagar') : t('grc.retencion_activar')}
                    </Button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </section>
      <section>
        <h3 style={{ margin: '0 0 6px', fontSize: 'var(--text-md)' }}>{t('grc.bloqueo_titulo')}</h3>
        <p style={{ margin: '0 0 10px', fontSize: 'var(--text-sm)', color: 'var(--text-2)' }}>{t('grc.bloqueo_intro')}</p>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
          <input aria-label={t('grc.bloqueo_caso')} placeholder={t('grc.bloqueo_caso')} value={nuevo.case_reference} onChange={e => setNuevo({ ...nuevo, case_reference: e.target.value })} style={campo} />
          <select aria-label={t('grc.retencion_tipo')} value={nuevo.entity} onChange={e => setNuevo({ ...nuevo, entity: e.target.value })} style={campo}>
            <option value="*">{t('grc.bloqueo_todos')}</option>
            {data.policies.map(p => <option key={p.entity} value={p.entity}>{t(`grc.retencion_tipo_${p.entity}`)}</option>)}
          </select>
          <select aria-label={t('grc.bloqueo_campo')} value={nuevo.field} onChange={e => setNuevo({ ...nuevo, field: e.target.value })} style={campo}>
            {campos.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
          <input aria-label={t('grc.bloqueo_valor')} placeholder={t('grc.bloqueo_valor')} value={nuevo.value} onChange={e => setNuevo({ ...nuevo, value: e.target.value })} style={{ ...campo, minWidth: 260, fontFamily: 'var(--font-mono)' }} />
          <Button size="sm" onClick={crear} disabled={!nuevo.case_reference.trim() || !nuevo.value.trim()}>{t('grc.bloqueo_crear')}</Button>
        </div>
        {bloqueos.length === 0 ? <div className="u-text3-sm">{t('grc.bloqueo_ninguno')}</div> : (
          <table className="u-table-sm">
            <tbody>
              {bloqueos.map(b => (
                <tr key={b.id} style={{ borderTop: '1px solid var(--surface-4)', opacity: b.is_active ? 1 : 0.6 }}>
                  <td style={{ padding: 8, fontWeight: 600 }}>{b.case_reference}</td>
                  <td style={{ padding: 8 }}>{b.entity === '*' ? t('grc.bloqueo_todos') : t(`grc.retencion_tipo_${b.entity}`)}</td>
                  <td style={{ padding: 8, fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)' }}>{b.field} = {b.value}</td>
                  <td style={{ padding: 8, color: b.is_active ? 'var(--warning)' : 'var(--text-3)' }}>{b.is_active ? t('grc.bloqueo_activo') : t('grc.bloqueo_levantado')}</td>
                  <td style={{ padding: 8, textAlign: 'right' }}>
                    {b.is_active && <Button size="sm" variant="secondary" onClick={async () => { try { await governanceApi.releaseLegalHold(b.id); refrescar() } catch (e) { error(e) } }}>{t('grc.bloqueo_levantar')}</Button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  )
}

/** Informe de evidencias medido sobre el sistema vivo (revisión 2026-11). */
function InformeDeCumplimientoTab() {
  const t = useAppT()
  const toast = useToast()
  const [bajando, setBajando] = useState(false)
  const { data, isFetching, refetch } = useQuery<InformeDeCumplimiento>({
    queryKey: ['grc-compliance-report'], queryFn: () => grcApi.complianceReport().then(r => r.data as InformeDeCumplimiento),
  })
  const descargar = async () => {
    setBajando(true)
    try { downloadBlob((await grcApi.complianceReportSigned()).data as Blob, `compliance-report-${new Date().toISOString().slice(0, 10)}.json`) }
    catch (e) { toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) } finally { setBajando(false) }
  }
  const valor = (v: unknown): string => v === null || v === undefined ? '—' : typeof v === 'object' ? JSON.stringify(v) : String(v)
  return (
    <div>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
        <p style={{ flex: 1, minWidth: 260, fontSize: 'var(--text-sm)', color: 'var(--text-2)', margin: 0 }}>{t('grc.informe_intro')}</p>
        <Button size="sm" variant="secondary" onClick={() => refetch()} disabled={isFetching}>{isFetching ? '…' : t('grc.informe_regenerar')}</Button>
        <Button size="sm" onClick={descargar} disabled={bajando}>{bajando ? '…' : t('grc.informe_descargar')}</Button>
        <Button size="sm" variant="ghost" onClick={() => window.print()}>{t('grc.informe_imprimir')}</Button>
      </div>
      {!data ? <div style={{ padding: 24 }}><Spinner /></div> : (
        <>
          <div style={{ display: 'flex', gap: 10, margin: '14px 0', flexWrap: 'wrap' }}>
            {(['pass', 'attention', 'info', 'not_measurable'] as const).map(e => (
              <div key={e} style={{ border: `1px solid ${COLOR_CONTROL[e]}`, borderRadius: 8, padding: '8px 14px', minWidth: 120 }}>
                <div style={{ fontSize: 'var(--text-xs)', color: COLOR_CONTROL[e], fontWeight: 700, textTransform: 'uppercase' }}>{t(`grc.informe_estado_${e}`)}</div>
                <div style={{ fontSize: 'var(--text-xl)', fontWeight: 700 }}>{data.summary[e] ?? 0}</div>
              </div>
            ))}
            <div style={{ alignSelf: 'center', fontSize: 'var(--text-xs)', color: 'var(--text-3)' }}>
              {t('grc.informe_generado', { fecha: new Date(data.generated_at).toLocaleString() })}
            </div>
          </div>
          <table className="u-table-sm">
            <thead><tr style={{ textAlign: 'left', color: 'var(--text-3)', fontSize: 'var(--text-xs)', textTransform: 'uppercase' }}>
              <th style={{ padding: '6px 8px' }}>{t('grc.informe_col_estado')}</th><th style={{ padding: '6px 8px' }}>{t('grc.informe_col_control')}</th>
              <th style={{ padding: '6px 8px' }}>{t('grc.informe_col_medido')}</th><th style={{ padding: '6px 8px' }}>{t('grc.informe_col_marcos')}</th>
            </tr></thead>
            <tbody>
              {data.controls.map(c => (
                <tr key={c.id} style={{ borderTop: '1px solid var(--surface-4)', verticalAlign: 'top' }}>
                  <td style={{ padding: '8px', color: COLOR_CONTROL[c.status], fontWeight: 700, whiteSpace: 'nowrap' }}>{t(`grc.informe_estado_${c.status}`)}</td>
                  <td style={{ padding: '8px' }}>
                    <div className="u-600">{t(`grc.informe_control_${c.id}`)}</div>
                    <div className="u-text3-xs">{c.source}</div>
                  </td>
                  <td style={{ padding: '8px', fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)', color: 'var(--text-2)' }}>
                    {Object.entries(c.measured).map(([k, v]) => <div key={k}>{k}: {valor(v)}</div>)}
                  </td>
                  <td style={{ padding: '8px', fontSize: 'var(--text-xs)', color: 'var(--text-2)' }}>{c.frameworks.join(' · ') || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  )
}

/** ¿Puede este usuario hacer esto y qué capa lo decide? (revisión 2026-11) */
function ExplicarAccesoTab() {
  const t = useAppT()
  const toast = useToast()
  const [usuario, setUsuario] = useState('')
  const [metodo, setMetodo] = useState('GET')
  // No es una URL que pida el cliente: es la ruta del servidor que se quiere explicar (las de `rutas` llevan el mismo prefijo).
  const [camino, setCamino] = useState('/api/v1/projects')
  const [res, setRes] = useState<Explicacion | null>(null)
  const [cargando, setCargando] = useState(false)
  const { data: usuarios = [] } = useQuery<{ id: string; full_name?: string; email?: string; role?: string }[]>({
    queryKey: ['users'], queryFn: () => usersApi.list().then(r => r.data ?? []),
  })
  const { data: rutas = [] } = useQuery<{ method: string; path: string }[]>({
    queryKey: ['grc-explainer-routes'], queryFn: () => grcApi.explainerRoutes().then(r => r.data),
  })
  const explicar = async () => {
    if (!usuario || !camino.trim()) return
    setCargando(true)
    try { setRes((await grcApi.explainAccess({ user_id: usuario, method: metodo, path: camino.trim() })).data as Explicacion) }
    catch (e) { toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) } finally { setCargando(false) }
  }
  const campo: CSSProperties = { background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 8,
    padding: '7px 10px', color: 'var(--text-1)', fontFamily: 'inherit', fontSize: 'var(--text-sm)' }
  const detalle = (c: CapaDeAcceso) => {
    const extra = ['module', 'action', 'role', 'required', 'level', 'project_id', 'guards', 'resource_type', 'allowed_methods']
      .filter(k => c[k] !== undefined && c[k] !== null && c[k] !== '')
      .map(k => `${k}: ${Array.isArray(c[k]) ? (c[k] as string[]).join(', ') : String(c[k])}`)
    const texto = t(`grc.acceso_detalle_${c.detail}`)
    return (texto.startsWith('grc.') ? c.detail : texto) + (extra.length ? ` — ${extra.join(' · ')}` : '')
  }
  return (
    <div>
      <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text-2)', marginTop: 0 }}>{t('grc.acceso_intro')}</p>
      <div className="u-wrap-center-8">
        <select aria-label={t('grc.acceso_usuario')} value={usuario} onChange={e => setUsuario(e.target.value)} style={{ ...campo, minWidth: 220 }}>
          <option value="">{t('grc.acceso_usuario')}</option>
          {usuarios.map(u => <option key={u.id} value={u.id}>{u.full_name || u.email} {u.role ? `(${u.role})` : ''}</option>)}
        </select>
        <select aria-label="HTTP" value={metodo} onChange={e => setMetodo(e.target.value)} style={campo}>
          {['GET', 'POST', 'PUT', 'PATCH', 'DELETE'].map(m => <option key={m}>{m}</option>)}
        </select>
        <input aria-label={t('grc.acceso_ruta')} list="grc-rutas" value={camino} onChange={e => setCamino(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') explicar() }} style={{ ...campo, flex: 1, minWidth: 280, fontFamily: 'var(--font-mono)' }} />
        <datalist id="grc-rutas">
          {rutas.filter(r => r.method === metodo).slice(0, 3000).map(r => <option key={r.path} value={r.path} />)}
        </datalist>
        <Button onClick={explicar} disabled={!usuario || cargando}>{cargando ? '…' : t('grc.acceso_explicar')}</Button>
      </div>
      <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', marginTop: 6 }}>{t('grc.acceso_ayuda_ruta')}</div>
      {res && (
        <div style={{ marginTop: 16 }}>
          <div role="status" style={{ padding: '12px 14px', borderRadius: 'var(--radius-md)', border: `1px solid ${COLOR_VEREDICTO[res.verdict]}`,
            background: alpha(COLOR_VEREDICTO[res.verdict], '12') }}>
            <div style={{ fontWeight: 700, color: COLOR_VEREDICTO[res.verdict] }}>
              {t(`grc.acceso_veredicto_${res.verdict}`)}{res.decided_by ? ` — ${t(`grc.acceso_capa_${res.decided_by}`)}` : ''}
            </div>
            <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-2)', marginTop: 4, fontFamily: 'var(--font-mono)' }}>
              {res.method} {res.template || res.path}
            </div>
          </div>
          <ol style={{ listStyle: 'none', padding: 0, margin: '12px 0 0' }}>
            {res.layers.map(c => (
              <li key={c.layer} style={{ display: 'flex', gap: 12, alignItems: 'baseline', padding: '8px 4px',
                borderBottom: '1px solid var(--surface-4)', opacity: c.verdict === 'not_applicable' ? 0.7 : 1 }}>
                <span style={{ minWidth: 110, fontSize: 'var(--text-xs)', fontWeight: 700, color: COLOR_VEREDICTO[c.verdict], textTransform: 'uppercase' }}>
                  {t(`grc.acceso_estado_${c.verdict}`)}
                </span>
                <span style={{ minWidth: 170, fontWeight: 600, fontSize: 'var(--text-sm)' }}>{t(`grc.acceso_capa_${c.layer}`)}</span>
                <span className="u-text2-sm">{detalle(c)}</span>
              </li>
            ))}
          </ol>
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
    { id: 'access',     label: _t('grc.acceso_pestana') },
    { id: 'compliance', label: _t('grc.informe_pestana') },
    { id: 'retention',  label: _t('grc.retencion_pestana') },
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
        {tab === 'access'     && <ExplicarAccesoTab />}
        {tab === 'compliance' && <InformeDeCumplimientoTab />}
        {tab === 'retention'  && <RetencionTab />}
      </div>
    </PageShell>
  )
}
