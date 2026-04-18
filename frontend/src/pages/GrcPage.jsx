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
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useToast } from '../context/ToastContext'
import api from '../services/api'
import PageHeader from '../components/layout/PageHeader'
import { Button, Spinner, EmptyState, Modal } from '../components/ui'
import { extractErr } from '../utils/helpers'
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
const ACTION_LABEL = { ver: 'Ver', crear: 'Crear', editar: 'Editar', eliminar: 'Eliminar', aprobar: 'Aprobar', exportar: 'Exportar' }

const ROLES = [
  { id: 'admin',     label: 'Admin',      color: 'var(--accent)' },
  { id: 'pm',        label: 'PM',         color: '#7c3aed' },
  { id: 'team_lead', label: 'Team Lead',  color: '#0891b2' },
  { id: 'employee',  label: 'Employee',   color: '#059669' },
  { id: 'hr',        label: 'HR',         color: '#d97706' },
  { id: 'client',    label: 'Cliente',    color: '#6b7280' },
]

const RISK_COLOR = { critical: '#ff4757', high: '#fb923c', medium: '#ffb800', low: '#00e5a0' }
const SEV_COLOR  = { critical: '#ff4757', warning: '#ffb800', info: '#00d4ff' }

// ── Shared style atoms ────────────────────────────────────────────────────────
const card = { background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 12 }
const fs = { width: '100%', background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 8, padding: '8px 12px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
const ls = { fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }

// ═══════════════════════════════════════════════════════════════════════════════
// 1. MATRIZ DE PERMISOS (wired to API)
// ═══════════════════════════════════════════════════════════════════════════════
function MatrixTab() {
  const toast = useToast()
  const qc = useQueryClient()
  const [selRole, setSelRole] = useState('all')
  const [saving, setSaving] = useState(null)

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['grc-permissions'],
    queryFn: () => api.get('/grc/permissions').then(r => r.data.matrix),
  })
  const matrix = data || {}

  const { mutate: resetMatrix, isPending: resetting } = useMutation({
    mutationFn: () => api.post('/grc/permissions/seed'),
    onSuccess: () => { qc.invalidateQueries(['grc-permissions']); toast.success('Matriz restaurada a valores por defecto') },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const togglePerm = async (role, module, action, current) => {
    const key = `${role}/${module}/${action}`
    setSaving(key)
    try {
      await api.patch(`/grc/permissions/${role}/${module}/${action}`, { allowed: !current })
      qc.invalidateQueries(['grc-permissions'])
    } catch (e) {
      toast.error(extractErr(e, 'Error al guardar permiso'))
    } finally {
      setSaving(null)
    }
  }

  const displayRoles = selRole === 'all' ? ROLES : ROLES.filter(r => r.id === selRole)

  if (isLoading) return <Spinner />

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20, flexWrap: 'wrap', gap: 10 }}>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
          <span style={{ fontSize: 12, color: 'var(--text-2)', marginRight: 4 }}>Rol:</span>
          <button onClick={() => setSelRole('all')}
            style={{ padding: '5px 14px', borderRadius: 6, border: `1px solid ${selRole === 'all' ? 'var(--accent)' : 'var(--surface-4)'}`, background: selRole === 'all' ? 'var(--accent-muted)' : 'transparent', color: selRole === 'all' ? 'var(--accent)' : 'var(--text-2)', fontSize: 11, cursor: 'pointer', fontFamily: 'inherit' }}>
            Todos
          </button>
          {ROLES.map(r => (
            <button key={r.id} onClick={() => setSelRole(r.id)}
              style={{ padding: '5px 14px', borderRadius: 6, border: `1px solid ${selRole === r.id ? r.color : 'var(--surface-4)'}`, background: selRole === r.id ? `${r.color}15` : 'transparent', color: selRole === r.id ? r.color : 'var(--text-2)', fontSize: 11, cursor: 'pointer', fontFamily: 'inherit' }}>
              {r.label}
            </button>
          ))}
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button onClick={() => refetch()} style={{ background: 'transparent', border: '1px solid #1e2d45', borderRadius: 6, padding: '6px 14px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}>↻ Actualizar</button>
          <button onClick={() => { openConfirmGlobal({ message: '¿Resetear toda la matriz a valores por defecto?', onConfirm: () => resetMatrix(), danger: true }) }}
            style={{ background: 'transparent', border: '1px solid #ff475730', borderRadius: 6, padding: '6px 14px', color: 'var(--danger)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}
            disabled={resetting}>
            {resetting ? 'Reseteando...' : '⟳ Resetear a defecto'}
          </button>
        </div>
      </div>

      <div style={{ overflowX: 'auto' }}>
        <table style={{ borderCollapse: 'collapse', minWidth: 600, width: '100%' }}>
          <thead>
            <tr style={{ borderBottom: '2px solid var(--surface-4)' }}>
              <th style={{ padding: '8px 12px', fontSize: 11, fontWeight: 600, color: 'var(--text-3)', textAlign: 'left', minWidth: 140, position: 'sticky', left: 0, background: 'var(--surface-2)', textTransform: 'uppercase' }}>Módulo</th>
              {displayRoles.map(r => (
                <th key={r.id} colSpan={ACTIONS.length}
                  style={{ padding: '8px 6px', fontSize: 11, fontWeight: 700, color: r.color, textAlign: 'center', borderLeft: '2px solid var(--surface-4)' }}>
                  {r.label}
                </th>
              ))}
            </tr>
            <tr style={{ borderBottom: '1px solid var(--surface-4)' }}>
              <th style={{ position: 'sticky', left: 0, background: 'var(--surface-2)' }} />
              {displayRoles.map(r => ACTIONS.map(a => (
                <th key={r.id + a} style={{ padding: '5px 3px', fontSize: 9, color: 'var(--text-3)', textAlign: 'center', fontWeight: 600, letterSpacing: '0.04em', textTransform: 'uppercase', minWidth: 42 }}>
                  {ACTION_LABEL[a]}
                </th>
              )))}
            </tr>
          </thead>
          <tbody>
            {MODULES.map((mod, mIdx) => (
              <tr key={mod.id} style={{ borderBottom: '1px solid var(--surface-4)', background: mIdx % 2 === 0 ? 'var(--surface-2)' : 'var(--surface-1)' }}>
                <td style={{ padding: '9px 12px', fontSize: 12, fontWeight: 600, color: 'var(--text-1)', position: 'sticky', left: 0, background: mIdx % 2 === 0 ? 'var(--surface-2)' : 'var(--surface-1)', whiteSpace: 'nowrap' }}>
                  {mod.icon} {mod.label}
                </td>
                {displayRoles.map(role => ACTIONS.map(action => {
                  const allowed = matrix[role.id]?.[mod.id]?.[action] ?? false
                  const key = `${role.id}/${mod.id}/${action}`
                  const isSaving = saving === key
                  return (
                    <td key={key} style={{ padding: '6px 3px', textAlign: 'center', cursor: 'pointer' }}
                      onClick={() => togglePerm(role.id, mod.id, action, allowed)}
                      title={`${role.label} · ${mod.label} · ${ACTION_LABEL[action]}: ${allowed ? 'Permitido' : 'Denegado'} — click para cambiar`}>
                      <span style={{ fontSize: 15, opacity: isSaving ? 0.4 : 1, transition: 'opacity .15s' }}>
                        {isSaving ? '⟳' : allowed ? '✅' : '❌'}
                      </span>
                    </td>
                  )
                }))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div style={{ display: 'flex', gap: 20, marginTop: 16, flexWrap: 'wrap' }}>
        {[['✅', 'Permitido', '#00e5a0'], ['❌', 'Denegado', '#ff4757']].map(([sym, label, color]) => (
          <div key={sym} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
            <span style={{ fontSize: 15 }}>{sym}</span><span style={{ color }}>{label}</span>
          </div>
        ))}
        <span style={{ fontSize: 11, color: 'var(--text-3)', marginLeft: 8 }}>Los cambios se guardan automáticamente y quedan en el Audit Log.</span>
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// 2. SEGREGACIÓN SoD (wired to API + CRUD)
// ═══════════════════════════════════════════════════════════════════════════════
function SodRuleModal({ rule, workflows, onClose }) {
  const qc = useQueryClient()
  const toast = useToast()
  const isEdit = !!rule
  const [form, setForm] = useState({
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
    mutationFn: d => isEdit ? api.patch(`/grc/sod-rules/${rule.id}`, d) : api.post('/grc/sod-rules', d),
    onSuccess: () => { qc.invalidateQueries(['grc-sod-rules']); qc.invalidateQueries(['grc-sod-check']); onClose() },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const toggleRole = r => setForm(f => ({
    ...f,
    roles_conflict: f.roles_conflict.includes(r) ? f.roles_conflict.filter(x => x !== r) : [...f.roles_conflict, r],
  }))

  return (
    <Modal open title={isEdit ? 'Editar regla SoD' : 'Nueva regla SoD'} onClose={onClose} width={580}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div style={{ background: 'var(--surface-3)', borderRadius: 8, padding: '12px 14px', fontSize: 12, color: 'var(--text-2)', lineHeight: 1.6 }}>
          Define un par de acciones que <strong style={{ color: 'var(--text-1)' }}>no deben recaer en la misma persona</strong>.
          La plataforma bloqueará el auto-aprobado cuando el solicitante coincida con el aprobador.
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 80px', gap: 10, background: 'var(--purple-bg)', border: '1px solid #7c3aed30', borderRadius: 8, padding: '12px 14px' }}>
          <div>
            <label style={ls}>Módulo A</label>
            <select value={form.module_a} onChange={e => setForm(f => ({ ...f, module_a: e.target.value }))} style={fs}>
              {MODULES.map(m => <option key={m.id} value={m.id}>{m.icon} {m.label}</option>)}
            </select>
          </div>
          <div>
            <label style={ls}>Acción A</label>
            <select value={form.action_a} onChange={e => setForm(f => ({ ...f, action_a: e.target.value }))} style={fs}>
              {ACTIONS.map(a => <option key={a} value={a}>{ACTION_LABEL[a]}</option>)}
            </select>
          </div>
        </div>
        <div style={{ textAlign: 'center', color: 'var(--text-3)', fontSize: 13 }}>↕ en conflicto con ↕</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 80px', gap: 10, background: 'var(--accent-muted)', border: '1px solid #00d4ff30', borderRadius: 8, padding: '12px 14px' }}>
          <div>
            <label style={ls}>Módulo B</label>
            <select value={form.module_b} onChange={e => setForm(f => ({ ...f, module_b: e.target.value }))} style={fs}>
              {MODULES.map(m => <option key={m.id} value={m.id}>{m.icon} {m.label}</option>)}
            </select>
          </div>
          <div>
            <label style={ls}>Acción B</label>
            <select value={form.action_b} onChange={e => setForm(f => ({ ...f, action_b: e.target.value }))} style={fs}>
              {ACTIONS.map(a => <option key={a} value={a}>{ACTION_LABEL[a]}</option>)}
            </select>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          <div>
            <label style={ls}>Nivel de riesgo</label>
            <select value={form.risk} onChange={e => setForm(f => ({ ...f, risk: e.target.value }))} style={fs}>
              {['critical', 'high', 'medium', 'low'].map(r => <option key={r} value={r}>{r}</option>)}
            </select>
          </div>
          <div>
            <label style={ls}>Flujo de mitigación (opcional)</label>
            <select value={form.mitigated_by_workflow_id} onChange={e => setForm(f => ({ ...f, mitigated_by_workflow_id: e.target.value }))} style={fs}>
              <option value="">Sin mitigación configurada</option>
              {(workflows || []).map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
            </select>
          </div>
        </div>

        <div>
          <label style={ls}>Descripción del riesgo</label>
          <input value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} style={fs} placeholder="Ej: Quien crea facturas no debe aprobarlas (riesgo de fraude)" />
        </div>

        <div>
          <label style={ls}>Roles con conflicto potencial</label>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 4 }}>
            {ROLES.map(r => (
              <button key={r.id} onClick={() => toggleRole(r.id)}
                style={{ padding: '4px 12px', borderRadius: 6, border: `1px solid ${form.roles_conflict.includes(r.id) ? r.color : 'var(--surface-4)'}`, background: form.roles_conflict.includes(r.id) ? `${r.color}20` : 'transparent', color: form.roles_conflict.includes(r.id) ? r.color : 'var(--text-2)', fontSize: 12, cursor: 'pointer', fontFamily: 'inherit' }}>
                {r.label}
              </button>
            ))}
          </div>
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={() => mutate({ ...form, mitigated_by_workflow_id: form.mitigated_by_workflow_id || null })} loading={isPending} disabled={isPending || !form.description}>
            {isPending ? 'Guardando...' : isEdit ? 'Guardar cambios' : 'Crear regla'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

function SodTab() {
  const toast = useToast()
  const qc = useQueryClient()
  const [showModal, setShowModal] = useState(false)
  const [editingRule, setEditingRule] = useState(null)

  const { data: rules = [], isLoading } = useQuery({
    queryKey: ['grc-sod-rules'],
    queryFn: () => api.get('/grc/sod-rules').then(r => r.data),
  })
  const { data: checkData } = useQuery({
    queryKey: ['grc-sod-check'],
    queryFn: () => api.get('/grc/sod-check').then(r => r.data),
    staleTime: 30000,
  })
  const { data: workflows = [] } = useQuery({
    queryKey: ['approval-workflows-grc'],
    queryFn: () => api.get('/approvals/workflows').then(r => r.data),
  })

  const { mutate: del } = useMutation({
    mutationFn: id => api.delete(`/grc/sod-rules/${id}`),
    onSuccess: () => { qc.invalidateQueries(['grc-sod-rules']); qc.invalidateQueries(['grc-sod-check']) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: toggle } = useMutation({
    mutationFn: ({ id, active }) => api.patch(`/grc/sod-rules/${id}`, { is_active: active }),
    onSuccess: () => qc.invalidateQueries(['grc-sod-rules']),
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const violations = checkData?.violations || []
  const criticalCount = violations.filter(v => v.risk === 'critical').length

  return (
    <div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 12, marginBottom: 20 }}>
        {[
          { label: 'Reglas SoD activas', value: rules.filter(r => r.is_active).length, color: 'var(--accent)', icon: '⚠️' },
          { label: 'Conflictos detectados', value: violations.length, color: violations.length > 0 ? 'var(--warning)' : 'var(--success)', icon: '🔍' },
          { label: 'Conflictos críticos', value: criticalCount, color: criticalCount > 0 ? 'var(--danger)' : 'var(--success)', icon: '🚨' },
        ].map(({ label, value, color, icon }) => (
          <div key={label} style={{ ...card, padding: '14px 18px' }}>
            <div style={{ fontSize: 20, marginBottom: 6 }}>{icon}</div>
            <div style={{ fontSize: 26, fontWeight: 800, color }}>{value}</div>
            <div style={{ fontSize: 12, color: 'var(--text-2)', marginTop: 4 }}>{label}</div>
          </div>
        ))}
      </div>

      {violations.length > 0 && (
        <div style={{ background: 'rgba(255,71,87,0.08)', border: '1px solid #ff475730', borderRadius: 10, padding: '12px 16px', marginBottom: 20 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--danger)', marginBottom: 8 }}>🚨 Conflictos SoD detectados en la matriz actual:</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {violations.map((v, i) => (
              <div key={i} style={{ display: 'flex', gap: 10, alignItems: 'center', fontSize: 12 }}>
                <span style={{ fontSize: 10, fontWeight: 700, padding: '2px 6px', borderRadius: 4, background: `${RISK_COLOR[v.risk]}20`, color: RISK_COLOR[v.risk], textTransform: 'uppercase', minWidth: 48, textAlign: 'center' }}>{v.risk}</span>
                <span style={{ color: 'var(--text-1)' }}><strong>{v.conflicting_role}</strong> puede {v.action_a} <em>{v.module_a}</em> y {v.action_b} <em>{v.module_b}</em></span>
                {v.mitigated && <span style={{ fontSize: 10, color: 'var(--success)', background: 'rgba(0,229,160,0.1)', padding: '1px 6px', borderRadius: 4 }}>✓ Mitigado</span>}
              </div>
            ))}
          </div>
        </div>
      )}

      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 16 }}>
        <Button onClick={() => setShowModal(true)}>+ Nueva regla SoD</Button>
      </div>

      {isLoading ? <Spinner /> : rules.length === 0 ? (
        <EmptyState icon="⚠️" title="Sin reglas SoD" description="Define pares de acciones que no deben recaer en la misma persona" />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {rules.map(rule => {
            const rc = RISK_COLOR[rule.risk] || '#6b7280'
            const modA = MODULES.find(m => m.id === rule.module_a)
            const modB = MODULES.find(m => m.id === rule.module_b)
            return (
              <div key={rule.id} style={{ ...card, borderLeft: `4px solid ${rc}`, padding: '14px 18px', opacity: rule.is_active ? 1 : 0.55 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                    <span style={{ fontSize: 11, fontWeight: 700, background: `${rc}20`, color: rc, padding: '2px 8px', borderRadius: 4, textTransform: 'uppercase' }}>{rule.risk}</span>
                    <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-1)' }}>{modA?.icon} {modA?.label} · {ACTION_LABEL[rule.action_a] || rule.action_a}</span>
                    <span style={{ fontSize: 12, color: 'var(--text-3)' }}>↔ conflicto con</span>
                    <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-1)' }}>{modB?.icon} {modB?.label} · {ACTION_LABEL[rule.action_b] || rule.action_b}</span>
                    {rule.mitigated_by_workflow_id && <span style={{ fontSize: 10, padding: '2px 6px', borderRadius: 4, background: 'rgba(0,229,160,0.12)', color: 'var(--success)' }}>✓ Mitigado</span>}
                    {!rule.is_active && <span style={{ fontSize: 10, padding: '2px 6px', borderRadius: 4, background: 'var(--surface-4)', color: 'var(--text-3)' }}>Inactiva</span>}
                  </div>
                  <div style={{ display: 'flex', gap: 6 }}>
                    <button onClick={() => toggle({ id: rule.id, active: !rule.is_active })}
                      style={{ background: 'none', border: '1px solid #1e2d45', borderRadius: 6, padding: '3px 9px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 11 }}>
                      {rule.is_active ? '⏸' : '▶'}
                    </button>
                    <button onClick={() => setEditingRule(rule)}
                      style={{ background: 'none', border: '1px solid #1e2d45', borderRadius: 6, padding: '3px 9px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 11 }}>✏</button>
                    <button onClick={() => { openConfirmGlobal({ message: '¿Eliminar esta regla SoD?', onConfirm: () => del(rule.id), danger: true }) }}
                      style={{ background: 'none', border: '1px solid #ff475730', borderRadius: 6, padding: '3px 9px', color: 'var(--danger)', cursor: 'pointer', fontSize: 11 }}>🗑</button>
                  </div>
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-2)', marginBottom: rule.roles_conflict?.length > 0 ? 8 : 0 }}>{rule.description}</div>
                {rule.roles_conflict?.length > 0 && (
                  <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
                    <span style={{ fontSize: 11, color: 'var(--text-3)' }}>Roles con conflicto:</span>
                    {rule.roles_conflict.map(r => {
                      const role = ROLES.find(x => x.id === r)
                      return role ? <span key={r} style={{ fontSize: 11, background: `${role.color}20`, color: role.color, padding: '2px 8px', borderRadius: 4, fontWeight: 600 }}>{role.label}</span> : null
                    })}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {(showModal || editingRule) && (
        <SodRuleModal rule={editingRule} workflows={workflows} onClose={() => { setShowModal(false); setEditingRule(null) }} />
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// 3. VIOLACIONES SoD
// ═══════════════════════════════════════════════════════════════════════════════
function ViolationsTab() {
  const toast = useToast()
  const qc = useQueryClient()
  const [filter, setFilter] = useState(false)

  const { data: violations = [], isLoading, refetch } = useQuery({
    queryKey: ['grc-violations', filter],
    queryFn: () => api.get('/grc/violations', { params: filter === null ? {} : { resolved: filter } }).then(r => r.data),
    refetchInterval: 60000,
  })

  const { mutate: resolve } = useMutation({
    mutationFn: ({ id, note }) => api.patch(`/grc/violations/${id}/resolve`, { resolution_note: note }),
    onSuccess: () => { qc.invalidateQueries(['grc-violations']); toast.success('Violación marcada como resuelta') },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  return (
    <div>
      <div style={{ background: 'rgba(255,71,87,0.06)', border: '1px solid #ff475720', borderRadius: 8, padding: '12px 16px', marginBottom: 18, fontSize: 12, color: 'var(--text-2)', lineHeight: 1.7 }}>
        <strong style={{ color: 'var(--danger)' }}>Violaciones SoD en tiempo real</strong> — Registradas cuando el mismo usuario intenta realizar las dos acciones de un par conflictivo (ej: crear y aprobar su propia solicitud). Cada violación debe revisarse y resolverse explícitamente.
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        {[[false, 'Pendientes'], [null, 'Todas'], [true, 'Resueltas']].map(([val, label]) => (
          <button key={String(val)} onClick={() => setFilter(val)}
            style={{ padding: '6px 14px', borderRadius: 6, border: `1px solid ${filter === val ? 'var(--accent-glow)' : 'var(--surface-4)'}`, background: filter === val ? 'var(--accent-muted)' : 'transparent', color: filter === val ? 'var(--accent)' : 'var(--text-2)', fontSize: 12, cursor: 'pointer', fontFamily: 'inherit' }}>
            {label}
          </button>
        ))}
        <button onClick={() => refetch()} style={{ marginLeft: 'auto', background: 'transparent', border: '1px solid #1e2d45', borderRadius: 6, padding: '6px 12px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}>↻</button>
      </div>

      {isLoading ? <Spinner /> : violations.length === 0 ? (
        <EmptyState icon={filter === false ? '✅' : '🔍'} title="Sin violaciones" description={filter === false ? 'No hay violaciones SoD pendientes de resolver' : 'No hay violaciones registradas'} />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {violations.map(v => (
            <div key={v.id} style={{ ...card, padding: '14px 18px', borderLeft: `3px solid ${v.resolved ? 'var(--success)' : 'var(--danger)'}` }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
                <div>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 4 }}>
                    <span style={{ fontSize: 12, fontWeight: 700, color: v.resolved ? 'var(--success)' : 'var(--danger)' }}>{v.resolved ? '✓ Resuelta' : '✗ Pendiente'}</span>
                    {v.role && <span style={{ fontSize: 11, padding: '2px 8px', background: 'var(--surface-4)', color: 'var(--text-2)', borderRadius: 4 }}>{v.role}</span>}
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text-1)' }}>
                    Usuario: <strong>{v.user_name || v.user_id || '—'}</strong> · Contexto: {v.context_type} ({v.context_id})
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 2 }}>Detectada: {v.detected_at}</div>
                  {v.resolution_note && <div style={{ fontSize: 11, color: 'var(--success)', marginTop: 2 }}>Resolución: {v.resolution_note}</div>}
                </div>
                {!v.resolved && (
                  <button onClick={() => {
                    const note = window.prompt('Nota de resolución (opcional):') ?? ''
                    resolve({ id: v.id, note })
                  }}
                    style={{ background: 'var(--success-bg)', border: '1px solid rgba(0,229,160,0.3)', borderRadius: 6, padding: '5px 12px', color: 'var(--success)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit', fontWeight: 600, whiteSpace: 'nowrap' }}>
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
function AuditLogTab() {
  const [severity, setSeverity] = useState('')

  const { data: log = [], isLoading, refetch } = useQuery({
    queryKey: ['grc-audit-log', severity],
    queryFn: () => api.get('/grc/audit-log', { params: severity ? { severity } : {} }).then(r => r.data),
  })

  const ACTION_ICONS = {
    permission_changed: '🔑', permission_matrix_reset: '♻️',
    sod_rule_created: '⚠️', sod_rule_updated: '✏️', sod_rule_deleted: '🗑',
    sod_violation_detected: '🚨', sod_violation_resolved: '✅', approval_override: '⚡',
  }

  return (
    <div>
      <div style={{ background: 'var(--surface-3)', borderRadius: 8, padding: '12px 16px', marginBottom: 18, fontSize: 12, color: 'var(--text-2)', lineHeight: 1.7 }}>
        <strong style={{ color: 'var(--text-1)' }}>Audit Log inmutable GRC</strong> — Todos los eventos de seguridad: cambios de permisos, violaciones SoD, resets y aprobaciones críticas. Útil para auditorías SOC-2, ISO 27001 y cumplimiento regulatorio.
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 16, alignItems: 'center' }}>
        <span style={{ fontSize: 12, color: 'var(--text-2)' }}>Severidad:</span>
        {[['', 'Todas'], ['info', 'Info'], ['warning', 'Aviso'], ['critical', 'Crítico']].map(([val, label]) => (
          <button key={val} onClick={() => setSeverity(val)}
            style={{ padding: '5px 14px', borderRadius: 6, border: `1px solid ${severity === val ? 'var(--accent-glow)' : 'var(--surface-4)'}`, background: severity === val ? 'var(--accent-muted)' : 'transparent', color: severity === val ? 'var(--accent)' : 'var(--text-2)', fontSize: 11, cursor: 'pointer', fontFamily: 'inherit' }}>
            {label}
          </button>
        ))}
        <button onClick={() => refetch()} style={{ marginLeft: 'auto', background: 'transparent', border: '1px solid #1e2d45', borderRadius: 6, padding: '6px 12px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}>↻</button>
      </div>

      {isLoading ? <Spinner /> : log.length === 0 ? (
        <EmptyState icon="📋" title="Sin registros" description="Los eventos GRC aparecerán aquí al realizarse cambios de permisos, reglas SoD o violaciones" />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 600, overflowY: 'auto', paddingRight: 4 }}>
          {log.map(e => {
            const sc = SEV_COLOR[e.severity] || 'var(--text-2)'
            return (
              <div key={e.id} style={{ ...card, padding: '10px 14px', borderLeft: `3px solid ${sc}` }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 4 }}>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <span style={{ fontSize: 15 }}>{ACTION_ICONS[e.action_type] || '📋'}</span>
                    <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-1)' }}>{(e.action_type || '').replace(/_/g, ' ')}</span>
                    {e.resource_type && <span style={{ fontSize: 10, padding: '1px 6px', background: 'var(--surface-4)', color: 'var(--text-3)', borderRadius: 4 }}>{e.resource_type}</span>}
                    <span style={{ fontSize: 10, fontWeight: 700, color: sc, background: `${sc}15`, padding: '1px 6px', borderRadius: 4, textTransform: 'uppercase' }}>{e.severity}</span>
                  </div>
                  <span style={{ fontSize: 11, color: 'var(--text-3)', whiteSpace: 'nowrap', marginLeft: 12 }}>{e.timestamp}</span>
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-2)' }}>
                  {e.user_name && <span>Actor: <strong>{e.user_name}</strong>{e.ip_address ? ` · IP: ${e.ip_address}` : ''}</span>}
                  {e.detail && typeof e.detail === 'object' && (
                    <span style={{ marginLeft: 8, fontFamily: 'monospace', fontSize: 10, color: 'var(--text-3)' }}>
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
  const { data: workflows = [], isLoading } = useQuery({
    queryKey: ['approval-workflows-grc'],
    queryFn: () => api.get('/approvals/workflows').then(r => r.data),
  })

  return (
    <div>
      <div style={{ marginBottom: 16, padding: '12px 16px', background: 'var(--surface-2)',
        borderRadius: 8, fontSize: 12, color: 'var(--text-2)', lineHeight: 1.7 }}>
        Los <strong style={{ color: 'var(--text-1)' }}>flujos de aprobación</strong> mitigan los riesgos
        SoD añadiendo revisión obligatoria de un segundo nivel. Configúralos en la sección{' '}
        <a href="/approvals" style={{ color: 'var(--accent)' }}>Aprobaciones</a>.
      </div>

      {isLoading ? <Spinner /> : workflows.length === 0 ? (
        <EmptyState icon="✅" title="Sin flujos configurados"
          description="Ve a Aprobaciones → Flujos para crear flujos de aprobación por entidad" />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {workflows.map(wf => (
            <div key={wf.id} style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
              borderRadius: 10, padding: '14px 18px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                <div>
                  <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-1)', marginRight: 10 }}>
                    {wf.name}
                  </span>
                  <span style={{ fontSize: 11, color: 'var(--text-3)', background: 'var(--surface-4)',
                    padding: '2px 8px', borderRadius: 4 }}>{wf.entity_type?.replace(/_/g,' ')}</span>
                </div>
                <span style={{ fontSize: 11, fontWeight: 600,
                  color: wf.is_active ? '#00e5a0' : 'var(--text-4)' }}>
                  {wf.is_active ? '● Activo' : '○ Inactivo'}
                </span>
              </div>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {(wf.steps || []).map((step, i) => (
                  <div key={step.id} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                    {i > 0 && <span style={{ color: 'var(--text-4)', fontSize: 14 }}>→</span>}
                    <span style={{ fontSize: 11, background: 'var(--surface-1)',
                      border: '1px solid var(--surface-4)', borderRadius: 6, padding: '3px 10px',
                      color: 'var(--text-2)' }}>
                      {step.name || step.approver_role || step.approver_user_name || 'Paso ' + (i+1)}
                    </span>
                  </div>
                ))}
                {(!wf.steps || wf.steps.length === 0) && (
                  <span style={{ fontSize: 12, color: 'var(--text-3)' }}>Sin pasos configurados</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function GrcPage() {
  const _t = useAppT()
  const [tab, setTab] = useState('matrix')

  const TABS = [
    { id: 'matrix',     label: '📋 Matriz de permisos' },
    { id: 'sod',        label: '⚠️ Segregación SoD' },
    { id: 'violations', label: '🚨 Violaciones' },
    { id: 'approvals',  label: '✅ Flujos de mitigación' },
    { id: 'auditlog',   label: '📋 Audit Log' },
  ]

  return (
    <div style={{ padding: '20px 28px' }}>
      <PageHeader
        title={_t('grc.title')}
        subtitle={_t('grc.subtitle')}
      />

      <div style={{ display: 'flex', gap: 6, marginBottom: 24, borderBottom: '1px solid var(--surface-4)',
        paddingBottom: 16, flexWrap: 'wrap' }}>
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)} style={{
            padding: '8px 18px', borderRadius: 8,
            border: `1px solid ${tab === t.id ? 'var(--accent-glow)' : 'var(--surface-4)'}`,
            background: tab === t.id ? 'var(--accent-muted)' : 'transparent',
            color: tab === t.id ? 'var(--accent)' : 'var(--text-2)',
            fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
          }}>{t.label}</button>
        ))}
      </div>

      <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
        borderRadius: 12, padding: '20px 22px' }}>
        {tab === 'matrix'     && <MatrixTab />}
        {tab === 'sod'        && <SodTab />}
        {tab === 'violations' && <ViolationsTab />}
        {tab === 'approvals'  && <ApprovalsTab />}
        {tab === 'auditlog'   && <AuditLogTab />}
      </div>
    </div>
  )
}
