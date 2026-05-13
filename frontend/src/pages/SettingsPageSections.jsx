import React, { useState } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { settingsApi, advancedConfigApi } from '../services/settingsApi'
import { usersApi, organizationsApi, biSmartAlertsApi, esignApi } from '../services/api'
import { Button, Modal, Spinner, EmptyState } from '../components/ui'
import { Search, Layers, Sparkles, Building2 } from 'lucide-react'
import { useAppLang } from '../i18n/AppLangContext'
import { extractErr } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { IdiomasSection, EmailInboundSection, LogLevelSection, SystemStateSection } from './settings-sections/SettingsAdvancedSections'

import { ROLE_LABELS, ROLE_COLORS } from '../constants/api'
import { useOrgSettings } from '../hooks/useOrgSettings'
const fs = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '10px 14px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
const ls = { fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 6 }

function Section({ icon, title, description, children }) {
  return (
    <div className="ds-card" style={{ marginBottom: 'var(--space-6)' }}>
      <div className="ds-stack-sm" style={{ marginBottom: 'var(--space-3)' }}>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 'var(--space-2)',
          fontSize: 'var(--text-lg)', fontWeight: 700, color: 'var(--text-1)',
        }}>
          {icon && <span style={{ display: 'inline-flex', alignItems: 'center', color: 'var(--accent)' }}>{icon}</span>}
          <span>{title}</span>
        </div>
        {description && <div className="ds-muted">{description}</div>}
      </div>
      {children}
    </div>
  )
}

// ── General settings ──────────────────────────────────────────────────────────

const LABELS = {
  company_name: 'Nombre empresa',
  company_logo_url: 'URL logotipo',
  currency: 'Moneda',
  timezone: 'Zona horaria',
  language: 'Idioma',
  work_hours_per_day: 'Horas/día',
  work_days_per_week: 'Días laborables/semana',
  budget_alert_threshold: '% alerta presupuesto',
  overload_threshold: '% carga máxima',
}

// Settings cuya key empieza por estos prefijos son estado interno de servicios BI/ITSM
// (no deben aparecer en la página de Configuración general porque son JSON serializado).
const INTERNAL_KEY_PREFIXES = [
  'bi.', 'sd.', 'olap.', 'ml_', '_', 'cache_', 'feedback_', 'lineage_', 'embed_', 'idle_timeout_',
]
const isUserFacingSetting = (key) => {
  if (!key) return false
  if (key in LABELS) return true
  const lower = String(key).toLowerCase()
  if (INTERNAL_KEY_PREFIXES.some(p => lower.startsWith(p))) return false
  // Permitir keys "limpias" (sin punto y sin parecer JSON): nombres simples como
  // company_name, currency, etc.
  return !lower.includes('.')
}

function GeneralSection() {
  const qc = useQueryClient()
  const toast = useToast()
  const { data: settings = [] } = useQuery({ queryKey: ['settings-general'], queryFn: () => settingsApi.getGeneral().then(r => r.data) })
  const { mutate: update } = useMutation({ mutationFn: ({ key, value }) => settingsApi.updateSetting(key, value), onSuccess: () => qc.invalidateQueries(['settings-general']) , onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))})

  const visible = (settings || []).filter(s => isUserFacingSetting(s.key))

  return (
    <Section icon="⚙️" title="Configuración general" description="Parámetros globales de la organización">
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 14 }}>
        {visible.map(s => <SettingField key={s.key} setting={s} label={LABELS[s.key] || s.key} onSave={(v) => update({ key: s.key, value: v })} />)}
      </div>
      {visible.length === 0 && (
        <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)', textAlign: 'center', padding: 16 }}>
          Sin parámetros generales configurados.
        </div>
      )}
    </Section>
  )
}

function SettingField({ setting, label, onSave }) {
  const [editing, setEditing] = useState(false)
  const [val, setVal] = useState(setting.value || '')
  return (
    <div style={{
      background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
      borderRadius: 10, padding: '12px 16px',
      minWidth: 0, overflow: 'hidden',
    }}>
      <label style={ls}>{label}</label>
      {editing ? (
        <div style={{ display: 'flex', gap: 8 }}>
          <input value={val} onChange={e => setVal(e.target.value)} style={{ ...fs, flex: 1, minWidth: 0 }} autoFocus onKeyDown={e => { if (e.key === 'Enter') { onSave(val); setEditing(false) } if (e.key === 'Escape') { setVal(setting.value); setEditing(false) } }} />
          <button onClick={() => { onSave(val); setEditing(false) }} style={{ background: 'var(--accent)', border: 'none', borderRadius: 6, padding: '0 12px', color: 'var(--surface-0)', cursor: 'pointer', fontWeight: 700, flexShrink: 0 }}>✓</button>
          <button onClick={() => { setVal(setting.value); setEditing(false) }} style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 6, padding: '0 12px', color: 'var(--text-2)', cursor: 'pointer', flexShrink: 0 }}>✕</button>
        </div>
      ) : (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8, minWidth: 0 }}>
          <span style={{
            fontSize: "var(--text-md)", fontWeight: 600,
            color: setting.value ? 'var(--text-1)' : 'var(--text-3)',
            wordBreak: 'break-word', overflowWrap: 'anywhere',
            flex: 1, minWidth: 0,
          }}>{setting.value || '—'}</span>
          <button onClick={() => setEditing(true)} style={{ background: 'none', border: 'none', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)", flexShrink: 0 }}>✏️</button>
        </div>
      )}
    </div>
  )
}

// ── Users section ─────────────────────────────────────────────────────────────
function UsersSection() {
  const toast = useToast()
  const qc = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)
  const [editUser, setEditUser] = useState(null)
  const [search, setSearch] = useState('')
  const [orgFilter, setOrgFilter] = useState('')
  const { data: users = [], isLoading } = useQuery({ queryKey: ['users'], queryFn: () => usersApi.list().then(r => r.data) })
  const { data: roles = [] } = useQuery({ queryKey: ['custom-roles'], queryFn: () => advancedConfigApi.getRoles().then(r => r.data) })
  const { data: departments = [] } = useQuery({ queryKey: ['departments-select'], queryFn: () => settingsApi.getDepartments().then(r => r.data) })
  const { data: organizations = [] } = useQuery({ queryKey: ['orgs-for-users'], queryFn: () => organizationsApi.list().then(r => r.data) })
  const roleMap = Object.fromEntries(roles.map(r => [r.name, r]))
  const { mutate: createUser, isPending: creating } = useMutation({ mutationFn: usersApi.create, onSuccess: () => { qc.invalidateQueries(['users']); setShowCreate(false) } , onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))})
  const { mutate: updateUser, isPending: updating } = useMutation({ mutationFn: ({ id, data }) => usersApi.update(id, data), onSuccess: () => { qc.invalidateQueries(['users']); setEditUser(null) } , onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))})
  const { mutate: deactivate } = useMutation({ mutationFn: usersApi.deactivate, onSuccess: () => qc.invalidateQueries(['users']) , onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))})
  const { mutate: deletePermanent } = useMutation({ mutationFn: usersApi.deletePermanent, onSuccess: () => { qc.invalidateQueries(['users']); qc.invalidateQueries(['users-settings']); qc.invalidateQueries(['resources']); } , onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))})
  const filtered = users.filter((u) => {
    const bySearch = !search
      || u.full_name?.toLowerCase().includes(search.toLowerCase())
      || u.username?.toLowerCase().includes(search.toLowerCase())

    if (!bySearch) return false
    if (!orgFilter) return true

    const orgs = Array.isArray(u.organizations) ? u.organizations : []
    const hasInMemberships = orgs.some((o) => String(o.id) === String(orgFilter))
    const hasPrimary = String(u.organization_id || '') === String(orgFilter)
    return hasInMemberships || hasPrimary
  })
  return (
    <Section title="Usuarios" description="Gestiona accesos y datos del equipo">
      <div className="ds-toolbar" style={{ marginBottom: 'var(--space-4)' }}>
        <div style={{ position: 'relative', flex: 1, minWidth: 200 }}>
          <Search size={14} aria-hidden style={{
            position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)',
            color: 'var(--text-3)', pointerEvents: 'none',
          }} />
          <input value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Buscar usuario por nombre o alias"
            aria-label="Buscar usuario por nombre o alias"
            className="ds-input"
            style={{ paddingLeft: 32 }} />
        </div>
        <select
          value={orgFilter}
          onChange={(e) => setOrgFilter(e.target.value)}
          className="ds-input"
          aria-label="Filtrar usuarios por organización"
          style={{ minWidth: 220, maxWidth: 320 }}
        >
          <option value="">Todas las organizaciones</option>
          {organizations.filter(o => o.is_active !== false).map((o) => (
            <option key={o.id} value={o.id}>{o.name}</option>
          ))}
        </select>
        {(search || orgFilter) && (
          <Button
            variant="secondary"
            onClick={() => {
              setSearch('')
              setOrgFilter('')
            }}
          >
            Limpiar filtros
          </Button>
        )}
        <Button onClick={() => setShowCreate(true)}>+ Nuevo usuario</Button>
      </div>
      {isLoading ? <Spinner /> : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {filtered.map(u => {
            const roleColor = roleMap[u.role]?.color || ROLE_COLORS[u.role] || 'var(--text-2)'
            const roleLabel = roleMap[u.role]?.description || ROLE_LABELS[u.role] || u.role
            const orgs = Array.isArray(u.organizations) ? u.organizations : []
            const primaryOrgId = u.organization_id || ''
            return (
            <div key={u.id} style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '10px 14px', background: 'var(--surface-2)', border: `1px solid ${u.is_active ? 'var(--surface-4)' : 'var(--danger-border)'}`, borderRadius: 10, opacity: u.is_active ? 1 : 0.6 }}>
              <div style={{ width: 34, height: 34, borderRadius: '50%', background: `linear-gradient(135deg, ${roleColor}, var(--surface-0))`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: "var(--text-base)", fontWeight: 700, flexShrink: 0 }}>
                {u.full_name?.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()}
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: "var(--text-base)", fontWeight: 600 }}>{u.full_name}</div>
                <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>{u.username} · {u.email}</div>
              </div>
              <span style={{ fontSize: "var(--text-xs)", background: `${roleColor}15`, color: roleColor, border: `1px solid ${roleColor}30`, borderRadius: 20, padding: '2px 8px', fontWeight: 700 }}>{roleLabel}</span>
              {orgs.length > 0 && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                  {orgs.slice(0, 3).map((org) => {
                    const isPrimary = String(org.id || '') === String(primaryOrgId)
                    return (
                      <span key={org.id} style={{
                        fontSize: "var(--text-xs)",
                        borderRadius: 20,
                        padding: '2px 8px',
                        border: `1px solid ${isPrimary ? 'var(--accent)' : 'var(--surface-4)'}`,
                        color: isPrimary ? 'var(--accent)' : 'var(--text-2)',
                        background: isPrimary ? 'var(--accent-muted)' : 'var(--surface-3)',
                        fontWeight: isPrimary ? 700 : 500,
                      }}>
                        {org.name || org.slug || org.id}{isPrimary ? ' (Principal)' : ''}
                      </span>
                    )
                  })}
                  {orgs.length > 3 && (
                    <span
                      title={orgs.map((org) => `${org.name || org.slug || org.id}${String(org.id || '') === String(primaryOrgId) ? ' (Principal)' : ''}`).join('\n')}
                      style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', cursor: 'help' }}
                    >
                      +{orgs.length - 3}
                    </span>
                  )}
                </div>
              )}
              {u.department && <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>{u.department}</span>}
              {!u.is_active && <span style={{ fontSize: "var(--text-xs)", color: 'var(--danger)' }}>Inactivo</span>}
              <button onClick={() => setEditUser(u)} style={{ background: 'none', border: '1px solid var(--surface-4)', borderRadius: 6, padding: '3px 8px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>✏️ Editar</button>
              {u.is_active ? <button onClick={() => openConfirmGlobal({ message: `¿Desactivar a "${u.full_name}"?`, onConfirm: () => deactivate(u.id) })} style={{ background: 'none', border: '1px solid var(--warning-border)', borderRadius: 6, padding: '3px 8px', color: 'var(--warning)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>⏸ Desactivar</button>
                : <button onClick={() => deactivate(u.id)} style={{ background: 'none', border: '1px solid var(--success-border)', borderRadius: 6, padding: '3px 8px', color: 'var(--success)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>▶ Activar</button>}
              <button onClick={() => openConfirmGlobal({ title: '⚠️ Eliminar permanentemente', message: `¿Eliminar permanentemente a "${u.full_name}"? Esta acción no se puede deshacer.`, onConfirm: () => deletePermanent(u.id), danger: true })} style={{ background: 'none', border: '1px solid var(--danger-border)', borderRadius: 6, padding: '3px 8px', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>🗑 Eliminar</button>
            </div>
          )})}
        </div>
      )}
      <UserFormModal open={showCreate} roles={roles} departments={departments} organizations={organizations} onClose={() => setShowCreate(false)} onSave={createUser} isPending={creating} />
      {editUser && <UserFormModal open roles={roles} departments={departments} organizations={organizations} user={editUser} onClose={() => setEditUser(null)} onSave={(data) => updateUser({ id: editUser.id, data })} isPending={updating} />}
    </Section>
  )
}

const COMMON_TIMEZONES = [
  'Europe/Madrid', 'Europe/London', 'Europe/Paris', 'Europe/Berlin', 'Europe/Rome',
  'Europe/Warsaw', 'Europe/Amsterdam', 'Europe/Brussels', 'Europe/Lisbon',
  'America/New_York', 'America/Chicago', 'America/Denver', 'America/Los_Angeles',
  'America/Sao_Paulo', 'America/Buenos_Aires', 'America/Mexico_City',
  'Asia/Tokyo', 'Asia/Shanghai', 'Asia/Kolkata', 'Asia/Dubai',
  'Australia/Sydney', 'Pacific/Auckland',
]

function UserFormModal({ open, onClose, user, onSave, isPending, roles = [], departments = [], organizations = [] }) {
  const isEdit = !!user
  const [form, setForm] = useState({
    username: user?.username || '',
    email: user?.email || '',
    full_name: user?.full_name || '',
    role: user?.role || 'employee',
    department: user?.department || '',
    job_title: user?.job_title || '',
    weekly_capacity_hours: user?.weekly_capacity_hours || 40,
    hourly_rate: user?.hourly_rate || '',
    timezone: user?.timezone || '',
    organization_ids: (Array.isArray(user?.organization_ids) && user.organization_ids.length > 0)
      ? user.organization_ids
      : (user?.organization_id ? [user.organization_id] : []),
    organization_id: user?.organization_id || '',
    password: '',
  })
  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.value }))
  const setOrganizations = (e) => {
    const values = Array.from(e.target.selectedOptions).map(o => o.value)
    setForm((f) => {
      const nextPrimary = values.includes(f.organization_id)
        ? f.organization_id
        : (values[0] || '')
      return { ...f, organization_ids: values, organization_id: nextPrimary }
    })
  }
  const handleSubmit = (e) => {
    e.preventDefault()
    onSave(form)
  }
  return (
    <Modal open={open} onClose={onClose} title={isEdit ? `Editar — ${user.full_name}` : 'Nuevo Usuario'} width={580}>
      <form onSubmit={handleSubmit}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
        <div style={{ gridColumn: '1/-1' }}><label style={ls}>Nombre completo *</label><input value={form.full_name} onChange={set('full_name')} style={fs} /></div>
        <div><label style={ls}>Usuario *</label><input value={form.username} onChange={set('username')} style={fs} /></div>
        <div><label style={ls}>Email *</label><input type="email" value={form.email} onChange={set('email')} style={fs} /></div>
        <div><label style={ls}>Rol</label><select value={form.role} onChange={set('role')} style={fs}>
          {roles.length > 0
            ? roles.map(r => <option key={r.name} value={r.name}>{r.description || r.name}</option>)
            : Object.entries(ROLE_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)
          }
        </select></div>
        <div><label style={ls}>Departamento</label><select value={form.department} onChange={set('department')} style={fs}>
          <option value="">— Sin departamento —</option>
          {departments.filter(d => d.is_active !== false).map(d => <option key={d.id} value={d.name}>{d.name}</option>)}
        </select></div>
        <div><label style={ls}>Cargo</label><input value={form.job_title} onChange={set('job_title')} style={fs} /></div>
        <div><label style={ls}>Horas semanales</label><input type="number" value={form.weekly_capacity_hours} onChange={set('weekly_capacity_hours')} style={fs} /></div>
        <div><label style={ls}>Tarifa €/hora</label><input type="number" value={form.hourly_rate} onChange={set('hourly_rate')} style={fs} /></div>
        <div style={{ gridColumn: '1/-1' }}>
          <label style={ls}>Organizaciones (selección múltiple)</label>
          <select multiple value={form.organization_ids} onChange={setOrganizations} style={{ ...fs, minHeight: 112 }}>
            {organizations.filter(o => o.is_active !== false).map(o => (
              <option key={o.id} value={o.id}>{o.name} ({o.slug})</option>
            ))}
          </select>
        </div>
        <div style={{ gridColumn: '1/-1' }}>
          <label style={ls}>Organización principal</label>
          <select value={form.organization_id} onChange={set('organization_id')} style={fs}>
            <option value="">— Sin organización principal —</option>
            {form.organization_ids.map((orgId) => {
              const org = organizations.find(o => o.id === orgId)
              return <option key={orgId} value={orgId}>{org?.name || orgId}</option>
            })}
          </select>
        </div>
        <div style={{ gridColumn: '1/-1' }}>
          <label style={ls}>Zona horaria</label>
          <select value={form.timezone} onChange={set('timezone')} style={fs}>
            <option value="">— Usa la zona de la organización —</option>
            {COMMON_TIMEZONES.map(tz => <option key={tz} value={tz}>{tz}</option>)}
          </select>
        </div>
        {!isEdit && <div style={{ gridColumn: '1/-1' }}><label style={ls}>Contraseña *</label><input type="password" value={form.password} onChange={set('password')} style={fs} /></div>}
        <div style={{ gridColumn: '1/-1', display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 8 }}>
          <Button variant="secondary" type="button" onClick={onClose}>Cancelar</Button>
          <Button type="submit" disabled={isPending || !form.full_name || !form.username || !form.email || (!isEdit && !form.password)}>
            {isPending ? 'Guardando...' : isEdit ? 'Guardar' : 'Crear'}
          </Button>
        </div>
        </div>
      </form>
    </Modal>
  )
}

// ── Roles section ─────────────────────────────────────────────────────────────
function RolesSection() {
  const toast = useToast()
  const qc = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)
  const [editRole, setEditRole] = useState(null)
  const { data: roles = [], isLoading } = useQuery({ queryKey: ['custom-roles'], queryFn: () => advancedConfigApi.getRoles().then(r => r.data) })
  const { data: modules = [] } = useQuery({ queryKey: ['modules-list'], queryFn: () => advancedConfigApi.getModules().then(r => r.data) })
  const { mutate: deleteRole } = useMutation({ mutationFn: advancedConfigApi.deleteRole, onSuccess: () => qc.invalidateQueries(['custom-roles']) , onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))})

  return (
    <Section icon="🔐" title="Roles y permisos" description="Define accesos avanzados por modulo">
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {isLoading ? <Spinner /> : roles.map(r => (
          <div key={r.id} style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '12px 16px', background: 'var(--surface-2)', border: `1px solid ${r.color}30`, borderRadius: 10 }}>
            <div style={{ width: 10, height: 10, borderRadius: '50%', background: r.color, flexShrink: 0 }} />
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: "var(--text-base)", fontWeight: 700 }}>{r.name}</div>
              {r.description && <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>{r.description}</div>}
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 6 }}>
                {Object.entries(r.module_access || {}).filter(([, v]) => v).slice(0, 8).map(([m]) => (
                  <span key={m} style={{ fontSize: "var(--text-3xs)", background: 'var(--surface-3)', color: 'var(--text-2)', borderRadius: 4, padding: '1px 6px' }}>{m}</span>
                ))}
                {Object.values(r.module_access || {}).filter(Boolean).length > 8 && <span style={{ fontSize: "var(--text-3xs)", color: 'var(--text-2)' }}>+{Object.values(r.module_access || {}).filter(Boolean).length - 8}</span>}
              </div>
            </div>
            {r.is_system && <span style={{ fontSize: "var(--text-2xs)", color: 'var(--text-2)', background: 'var(--surface-3)', borderRadius: 20, padding: '2px 8px' }}>Sistema</span>}
            <button onClick={() => setEditRole(r)} style={{ background: 'none', border: '1px solid var(--surface-4)', borderRadius: 6, padding: '3px 8px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>✏️ Editar</button>
            {!r.is_system && <button onClick={() => deleteRole(r.id)} style={{ background: 'none', border: '1px solid var(--danger-border)', borderRadius: 6, padding: '3px 8px', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>🗑</button>}
          </div>
        ))}
        <button onClick={() => setShowCreate(true)} style={{ padding: '10px', border: '1px dashed var(--surface-4)', borderRadius: 10, background: 'transparent', color: 'var(--text-2)', fontSize: "var(--text-base)", cursor: 'pointer', fontFamily: 'inherit', textAlign: 'center' }}>＋ Crear rol personalizado</button>
      </div>
      {(showCreate || editRole) && (
        <RoleFormModal role={editRole} modules={modules} onClose={() => { setShowCreate(false); setEditRole(null) }}
          onSave={(data) => { const fn = editRole ? () => advancedConfigApi.updateRole(editRole.id, data) : () => advancedConfigApi.createRole(data); fn().then(() => { qc.invalidateQueries(['custom-roles']); setShowCreate(false); setEditRole(null) }) }} />
      )}
    </Section>
  )
}

function RoleFormModal({ role, modules, onClose, onSave }) {
  const [form, setForm] = useState({ name: role?.name || '', description: role?.description || '', color: /^#[0-9a-fA-F]{6}$/.test(role?.color) ? role.color : '#7a8aaa', module_access: role?.module_access || {} })
  const toggleModule = (m) => setForm(f => ({ ...f, module_access: { ...f.module_access, [m]: !f.module_access[m] } }))
  const allOn = modules.every(m => form.module_access[m.id])
  return (
    <Modal open title={role ? `Editar rol — ${role.name}` : 'Nuevo rol'} onClose={onClose} width={560}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 12 }}>
          <div><label style={ls}>Nombre *</label><input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} style={fs} disabled={role?.is_system} /></div>
          <div><label style={ls}>Color</label><div style={{ display: 'flex', gap: 8 }}><input type="color" value={/^#[0-9a-fA-F]{6}$/.test(form.color) ? form.color : '#7a8aaa'} onChange={e => setForm(f => ({ ...f, color: e.target.value }))} style={{ width: 40, height: 38, border: 'none', background: 'transparent', cursor: 'pointer' }} /><input value={form.color} onChange={e => setForm(f => ({ ...f, color: e.target.value }))} style={{ ...fs, flex: 1 }} /></div></div>
        </div>
        <div><label style={ls}>Descripción</label><input value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} style={fs} /></div>
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
            <label style={ls}>Módulos accesibles</label>
            <button onClick={() => setForm(f => ({ ...f, module_access: modules.reduce((a, m) => ({ ...a, [m.id]: !allOn }), {}) }))} style={{ background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>
              {allOn ? 'Desactivar todos' : 'Activar todos'}
            </button>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6 }}>
            {modules.map(m => (
              <label key={m.id} style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', padding: '6px 10px', background: form.module_access[m.id] ? 'var(--accent-muted)' : 'var(--surface-3)', borderRadius: 6, border: `1px solid ${form.module_access[m.id] ? 'var(--accent)' : 'var(--surface-4)'}`, fontSize: "var(--text-sm)" }}>
                <input type="checkbox" checked={!!form.module_access[m.id]} onChange={() => toggleModule(m.id)} />
                {m.label}
              </label>
            ))}
          </div>
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={() => onSave(form)} disabled={!form.name}>Guardar</Button>
        </div>
      </div>
    </Modal>
  )
}

// ── Alert configs section ─────────────────────────────────────────────────────
const CONDITION_LABELS = {
  threshold_above: 'Supera umbral',
  threshold_below: 'Por debajo del umbral',
  trend_up: 'Tendencia al alza',
  trend_down: 'Tendencia a la baja',
  anomaly: 'Anomalía detectada',
}
const THRESHOLD_CONDITIONS = ['threshold_above', 'threshold_below']

function AlertConfigSection() {
  const toast = useToast()
  const qc = useQueryClient()
  const SEV_CFG = { info: 'var(--accent)', warning: 'var(--warning)', critical: 'var(--danger)' }

  // — system alert configs (fixed 8 types) —
  const { data: configs = [], isLoading } = useQuery({ queryKey: ['alert-configs'], queryFn: () => advancedConfigApi.getAlertConfigs().then(r => r.data) })
  const { mutate: update } = useMutation({ mutationFn: ({ type, data }) => advancedConfigApi.updateAlertConfig(type, data), onSuccess: () => qc.invalidateQueries(['alert-configs']), onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) })

  // — BI custom alert rules —
  const { data: rulesData = { items: [] } } = useQuery({ queryKey: ['bi-alert-rules'], queryFn: () => biSmartAlertsApi.listRules().then(r => r.data) })
  const { data: metricsData = { metrics: [], conditions: [] } } = useQuery({ queryKey: ['bi-alert-metrics'], queryFn: () => biSmartAlertsApi.supportedMetrics().then(r => r.data) })
  const rules = rulesData.items ?? []
  const metrics = metricsData.metrics ?? []

  const { mutate: createRule, isPending: isCreating } = useMutation({
    mutationFn: biSmartAlertsApi.createRule,
    onSuccess: () => { qc.invalidateQueries(['bi-alert-rules']); setShowCreate(false); setRuleForm(EMPTY_RULE) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: toggleRule } = useMutation({
    mutationFn: ({ id, enabled }) => biSmartAlertsApi.updateRule(id, { enabled }),
    onSuccess: () => qc.invalidateQueries(['bi-alert-rules']),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: deleteRule } = useMutation({
    mutationFn: biSmartAlertsApi.deleteRule,
    onSuccess: () => qc.invalidateQueries(['bi-alert-rules']),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const EMPTY_RULE = { name: '', metric_key: '', condition: 'threshold_above', threshold: '', severity: 'warning', cooldown_minutes: 60 }
  const [showCreate, setShowCreate] = useState(false)
  const [ruleForm, setRuleForm] = useState(EMPTY_RULE)
  const setR = k => e => setRuleForm(f => ({ ...f, [k]: e.target.value }))

  const submitRule = () => {
    if (!ruleForm.name.trim() || !ruleForm.metric_key) return toast.error('Nombre y métrica son obligatorios')
    const payload = { ...ruleForm, cooldown_minutes: +ruleForm.cooldown_minutes }
    if (THRESHOLD_CONDITIONS.includes(ruleForm.condition)) payload.threshold = +ruleForm.threshold
    else delete payload.threshold
    createRule(payload)
  }

  return (
    <Section icon="🔔" title="Alertas" description="Configura notificaciones, umbrales y reglas personalizadas">
      {isLoading ? <Spinner /> : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {configs.map(cfg => (
            <div key={cfg.alert_type} style={{ padding: '14px 16px', background: 'var(--surface-2)', border: `1px solid ${cfg.is_enabled ? SEV_CFG[cfg.severity] + '30' : 'var(--surface-4)'}`, borderRadius: 10, opacity: cfg.is_enabled ? 1 : 0.6 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 }}>
                <div>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 3 }}>
                    <span style={{ fontSize: "var(--text-base)", fontWeight: 700 }}>{cfg.label}</span>
                    <span style={{ fontSize: "var(--text-2xs)", fontWeight: 700, color: SEV_CFG[cfg.severity], background: SEV_CFG[cfg.severity] + '20', borderRadius: 20, padding: '1px 7px', textTransform: 'uppercase' }}>{cfg.severity}</span>
                  </div>
                  {cfg.description && <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>{cfg.description}</div>}
                </div>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                  <input type="checkbox" checked={cfg.is_enabled} onChange={e => update({ type: cfg.alert_type, data: { is_enabled: e.target.checked } })} />
                  <span style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>{cfg.is_enabled ? 'Activa' : 'Inactiva'}</span>
                </label>
              </div>
              {cfg.is_enabled && (
                <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', alignItems: 'center' }}>
                  {cfg.threshold_value !== null && (
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                      <label style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>Umbral:</label>
                      <input type="number" defaultValue={cfg.threshold_value} onBlur={e => update({ type: cfg.alert_type, data: { threshold_value: +e.target.value } })}
                        style={{ width: 70, background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 6, padding: '4px 8px', color: 'var(--text-1)', fontSize: "var(--text-sm)", outline: 'none', fontFamily: 'inherit', textAlign: 'center' }} />
                      <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>{cfg.threshold_unit}</span>
                    </div>
                  )}
                  <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                    {[['notify_admin', 'Admin'], ['notify_pm', 'PM'], ['notify_hr', 'RRHH'], ['notify_employee', 'Empleado'], ['notify_email', '📧 Email']].map(([key, label]) => (
                      <label key={key} style={{ display: 'flex', alignItems: 'center', gap: 5, cursor: 'pointer', fontSize: "var(--text-xs)", color: cfg[key] ? 'var(--text-1)' : 'var(--text-2)' }}>
                        <input type="checkbox" checked={!!cfg[key]} onChange={e => update({ type: cfg.alert_type, data: { [key]: e.target.checked } })} />
                        {label}
                      </label>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* ── Custom BI alert rules ─────────────────── */}
      <div style={{ marginTop: 28 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <div>
            <div style={{ fontSize: "var(--text-base)", fontWeight: 700 }}>Reglas personalizadas</div>
            <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>Alertas basadas en métricas del sistema</div>
          </div>
          <Button onClick={() => setShowCreate(true)}>+ Nueva alerta</Button>
        </div>
        {rules.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '20px 0', color: 'var(--text-3)', fontSize: "var(--text-sm)" }}>No hay reglas personalizadas. Crea la primera.</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {rules.map(rule => (
              <div key={rule.id} style={{ padding: '12px 14px', background: 'var(--surface-2)', border: `1px solid ${rule.enabled ? SEV_CFG[rule.severity] + '30' : 'var(--surface-4)'}`, borderRadius: 10, display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, opacity: rule.enabled ? 1 : 0.6 }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 2 }}>
                    <span style={{ fontWeight: 600, fontSize: "var(--text-base)" }}>{rule.name}</span>
                    <span style={{ fontSize: "var(--text-2xs)", fontWeight: 700, color: SEV_CFG[rule.severity], background: SEV_CFG[rule.severity] + '20', borderRadius: 20, padding: '1px 7px', textTransform: 'uppercase' }}>{rule.severity}</span>
                  </div>
                  <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>
                    {metrics.find(m => m.key === rule.metric_key)?.label ?? rule.metric_key} · {CONDITION_LABELS[rule.condition] ?? rule.condition}{rule.threshold != null ? ` · umbral: ${rule.threshold}` : ''}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexShrink: 0 }}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>
                    <input type="checkbox" checked={!!rule.enabled} onChange={e => toggleRule({ id: rule.id, enabled: e.target.checked })} />
                    {rule.enabled ? 'Activa' : 'Inactiva'}
                  </label>
                  <Button variant="danger" style={{ padding: '4px 10px', fontSize: "var(--text-xs)" }} onClick={() => openConfirmGlobal({ title: 'Eliminar regla', message: `¿Eliminar "${rule.name}"?`, onConfirm: () => deleteRule(rule.id) })}>Eliminar</Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {showCreate && (
        <Modal open title="Nueva regla de alerta" onClose={() => { setShowCreate(false); setRuleForm(EMPTY_RULE) }} width={480}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div>
              <label style={ls}>Nombre</label>
              <input value={ruleForm.name} onChange={setR('name')} style={fs} placeholder="Ej: Ingresos por debajo del objetivo" />
            </div>
            <div>
              <label style={ls}>Métrica</label>
              <select value={ruleForm.metric_key} onChange={setR('metric_key')} style={fs}>
                <option value="">— Selecciona una métrica —</option>
                {metrics.map(m => <option key={m.key} value={m.key}>{m.label}</option>)}
              </select>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <div>
                <label style={ls}>Condición</label>
                <select value={ruleForm.condition} onChange={setR('condition')} style={fs}>
                  {Object.entries(CONDITION_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </div>
              {THRESHOLD_CONDITIONS.includes(ruleForm.condition) && (
                <div>
                  <label style={ls}>Umbral</label>
                  <input type="number" value={ruleForm.threshold} onChange={setR('threshold')} style={fs} placeholder="0" />
                </div>
              )}
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <div>
                <label style={ls}>Severidad</label>
                <select value={ruleForm.severity} onChange={setR('severity')} style={fs}>
                  <option value="info">Info</option>
                  <option value="warning">Warning</option>
                  <option value="critical">Critical</option>
                </select>
              </div>
              <div>
                <label style={ls}>Cooldown (minutos)</label>
                <input type="number" value={ruleForm.cooldown_minutes} onChange={setR('cooldown_minutes')} style={fs} min={5} />
              </div>
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 4 }}>
              <Button variant="secondary" onClick={() => { setShowCreate(false); setRuleForm(EMPTY_RULE) }}>Cancelar</Button>
              <Button onClick={submitRule} disabled={isCreating}>{isCreating ? 'Creando…' : 'Crear alerta'}</Button>
            </div>
          </div>
        </Modal>
      )}
    </Section>
  )
}

// ── Rate tables section ───────────────────────────────────────────────────────
function RateTablesSection() {
  const toast = useToast()
  const qc = useQueryClient()
  const { data: tables = [], isLoading } = useQuery({ queryKey: ['rate-tables'], queryFn: () => advancedConfigApi.getRateTables().then(r => r.data) })
  const { mutate: createTable } = useMutation({ mutationFn: advancedConfigApi.createRateTable, onSuccess: () => qc.invalidateQueries(['rate-tables']) , onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))})
  const { mutate: deleteTable } = useMutation({ mutationFn: advancedConfigApi.deleteRateTable, onSuccess: () => qc.invalidateQueries(['rate-tables']) , onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))})
  const { mutate: addEntry } = useMutation({ mutationFn: ({ tableId, data }) => advancedConfigApi.addRateEntry(tableId, data), onSuccess: () => qc.invalidateQueries(['rate-tables']) , onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))})
  const { mutate: deleteEntry } = useMutation({ mutationFn: ({ tableId, entryId }) => advancedConfigApi.deleteRateEntry(tableId, entryId), onSuccess: () => qc.invalidateQueries(['rate-tables']), onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) })
  const { mutate: updateEntry } = useMutation({ mutationFn: ({ tableId, entryId, data }) => advancedConfigApi.updateRateEntry(tableId, entryId, data), onSuccess: () => { qc.invalidateQueries(['rate-tables']); setEditingEntryId(null) }, onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) })
  const [editingEntryId, setEditingEntryId] = useState(null)
  const [editEntryForm, setEditEntryForm] = useState({ label: '', cost_rate: '', billing_rate: '' })
  const [newTable, setNewTable] = useState({ name: '', applies_to: 'role', is_default: false })
  const [addingEntry, setAddingEntry] = useState(null)
  const [entryForm, setEntryForm] = useState({ label: '', cost_rate: '', billing_rate: '' })

  return (
    <Section icon="💶" title="Tarifas internas" description="Mantiene tablas de coste y facturacion">
      {isLoading ? <Spinner /> : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {tables.map(t => (
            <div key={t.id} style={{ background: 'var(--surface-2)', border: `1px solid ${t.is_default ? 'var(--accent)' : 'var(--surface-4)'}`, borderRadius: 12, padding: 16 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                <div>
                  <span style={{ fontSize: "var(--text-md)", fontWeight: 600 }}>{t.name}</span>
                  {t.is_default && <span style={{ fontSize: "var(--text-2xs)", background: 'var(--accent-muted)', color: 'var(--accent)', borderRadius: 20, padding: '1px 8px', marginLeft: 8 }}>Por defecto</span>}
                  <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginLeft: 8 }}>{t.applies_to === 'role' ? 'Por rol' : t.applies_to === 'department' ? 'Por departamento' : 'Por cliente'}</span>
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <button onClick={() => setAddingEntry(t.id)} style={{ background: 'var(--accent-muted)', border: '1px solid var(--accent-border)', borderRadius: 6, padding: '4px 10px', color: 'var(--accent)', cursor: 'pointer', fontSize: "var(--text-xs)", fontFamily: 'inherit' }}>＋ Tarifa</button>
                  <button onClick={() => deleteTable(t.id)} style={{ background: 'none', border: '1px solid var(--danger-border)', borderRadius: 6, padding: '4px 10px', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>🗑</button>
                </div>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 30px', gap: 8 }}>
                <div style={{ fontSize: "var(--text-2xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', padding: '0 8px' }}>Etiqueta</div>
                <div style={{ fontSize: "var(--text-2xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', textAlign: 'center' }}>Coste €/h</div>
                <div style={{ fontSize: "var(--text-2xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', textAlign: 'center' }}>Factura €/h</div>
                <div></div>
                {(t.entries || []).map(e => (
                  editingEntryId === e.id ? (
                    <React.Fragment key={e.id}>
                      <input value={editEntryForm.label} onChange={ev => setEditEntryForm(f=>({...f,label:ev.target.value}))} style={{...fs,padding:'5px 8px'}} autoFocus />
                      <input type="number" value={editEntryForm.cost_rate} onChange={ev => setEditEntryForm(f=>({...f,cost_rate:ev.target.value}))} style={{...fs,padding:'5px 8px'}} placeholder="Coste por hora" aria-label="Coste por hora" />
                      <input type="number" value={editEntryForm.billing_rate} onChange={ev => setEditEntryForm(f=>({...f,billing_rate:ev.target.value}))} style={{...fs,padding:'5px 8px'}} placeholder="Tarifa de facturacion" aria-label="Tarifa de facturacion" />
                      <div style={{display:'flex',gap:4}}>
                        <button onClick={() => updateEntry({ tableId: t.id, entryId: e.id, data: editEntryForm })} disabled={!editEntryForm.label} style={{background:'var(--accent)',border:'none',borderRadius:5,padding:'4px 8px',color:'#fff',cursor:'pointer',fontSize: "var(--text-sm)"}}>✓</button>
                        <button onClick={() => setEditingEntryId(null)} style={{background:'none',border:'1px solid var(--surface-4)',borderRadius:5,padding:'4px 7px',color:'var(--text-2)',cursor:'pointer',fontSize: "var(--text-sm)"}}>✕</button>
                      </div>
                    </React.Fragment>
                  ) : (
                    <React.Fragment key={e.id}>
                      <div style={{ padding: '6px 8px', background: 'var(--surface-3)', borderRadius: 6, fontSize: "var(--text-base)" }}>{e.label}</div>
                      <div style={{ padding: '6px 8px', background: 'var(--surface-3)', borderRadius: 6, fontSize: "var(--text-base)", textAlign: 'center', fontFamily: 'var(--font-mono)', color: 'var(--warning)' }}>{e.cost_rate ? `${e.cost_rate}€` : '—'}</div>
                      <div style={{ padding: '6px 8px', background: 'var(--surface-3)', borderRadius: 6, fontSize: "var(--text-base)", textAlign: 'center', fontFamily: 'var(--font-mono)', color: 'var(--success)' }}>{e.billing_rate ? `${e.billing_rate}€` : '—'}</div>
                      <div style={{display:'flex',gap:3}}>
                        <button onClick={() => { setEditingEntryId(e.id); setEditEntryForm({ label: e.label, cost_rate: e.cost_rate||'', billing_rate: e.billing_rate||'' }) }} style={{ background: 'none', border: 'none', color: 'var(--text-3)', cursor: 'pointer', fontSize: "var(--text-sm)" }}>✏</button>
                        <button onClick={() => deleteEntry({ tableId: t.id, entryId: e.id })} style={{ background: 'none', border: 'none', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-md)" }}>×</button>
                      </div>
                    </React.Fragment>
                  )
                ))}
              </div>
              {addingEntry === t.id && (
                <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr auto', gap: 8, marginTop: 8, padding: '10px', background: 'var(--accent-muted)', border: '1px dashed var(--accent-border)', borderRadius: 8 }}>
                  <input value={entryForm.label} onChange={e => setEntryForm(f => ({ ...f, label: e.target.value }))} style={{ ...fs }} placeholder="Etiqueta de la tarifa" aria-label="Etiqueta de la tarifa" />
                  <input type="number" value={entryForm.cost_rate} onChange={e => setEntryForm(f => ({ ...f, cost_rate: e.target.value }))} style={fs} placeholder="Coste por hora" aria-label="Coste por hora" />
                  <input type="number" value={entryForm.billing_rate} onChange={e => setEntryForm(f => ({ ...f, billing_rate: e.target.value }))} style={fs} placeholder="Tarifa de facturacion" aria-label="Tarifa de facturacion" />
                  <div style={{ display: 'flex', gap: 6 }}>
                    <Button size="sm" onClick={() => { addEntry({ tableId: t.id, data: entryForm }); setEntryForm({ label: '', cost_rate: '', billing_rate: '' }); setAddingEntry(null) }} disabled={!entryForm.label}>Añadir</Button>
                    <Button size="sm" variant="secondary" onClick={() => setAddingEntry(null)}>×</Button>
                  </div>
                </div>
              )}
            </div>
          ))}
          <div style={{ display: 'flex', gap: 10, padding: '12px 16px', background: 'var(--accent-muted)', border: '1px dashed var(--accent-border)', borderRadius: 10, alignItems: 'flex-end' }}>
            <div style={{ flex: 2 }}><label style={ls}>Nombre tabla</label><input value={newTable.name} onChange={e => setNewTable(f => ({ ...f, name: e.target.value }))} style={fs} placeholder="Nombre de la tabla" aria-label="Nombre de la tabla" /></div>
            <div style={{ flex: 1 }}><label style={ls}>Aplica a</label><select value={newTable.applies_to} onChange={e => setNewTable(f => ({ ...f, applies_to: e.target.value }))} style={fs}><option value="role">Por rol</option><option value="department">Por depto</option><option value="client">Por cliente</option></select></div>
            <Button onClick={() => { createTable(newTable); setNewTable({ name: '', applies_to: 'role', is_default: false }) }} disabled={!newTable.name}>Crear tabla</Button>
          </div>
        </div>
      )}
    </Section>
  )
}

// ── Vacation policies section ─────────────────────────────────────────────────
function VacationSection() {
  const toast = useToast()
  const qc = useQueryClient()
  const currentYear = new Date().getFullYear()
  const [year, setYear] = useState(currentYear)
  const { data: policies = [] } = useQuery({ queryKey: ['vacation-policies'], queryFn: () => advancedConfigApi.getVacationPolicies().then(r => r.data) })
  const { data: balances = [] } = useQuery({ queryKey: ['vacation-balances', year], queryFn: () => advancedConfigApi.getVacationBalances(year).then(r => r.data) })
  const { mutate: createPolicy } = useMutation({ mutationFn: advancedConfigApi.createVacationPolicy, onSuccess: () => qc.invalidateQueries(['vacation-policies']) , onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))})
  const { mutate: deletePolicy } = useMutation({ mutationFn: advancedConfigApi.deleteVacationPolicy, onSuccess: () => qc.invalidateQueries(['vacation-policies']) , onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))})
  const { mutate: updateBalance } = useMutation({ mutationFn: ({ userId, days }) => advancedConfigApi.updateVacationBalance(userId, year, days), onSuccess: () => { qc.invalidateQueries(['vacation-balances', year]); qc.invalidateQueries(['vacation-balance-my']); } , onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))})
  const [newPolicy, setNewPolicy] = useState({ name: '', days_per_year: 23, carries_over: true, max_carryover_days: 5, is_default: false })

  return (
    <Section icon="🏖️" title="Vacaciones y permisos" description="Configura politicas y saldos del equipo">
      <div style={{ marginBottom: 20 }}>
        <div style={{ fontSize: "var(--text-base)", fontWeight: 700, marginBottom: 12 }}>Políticas configuradas</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {policies.map(p => (
            <div key={p.id} style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '10px 14px', background: 'var(--surface-2)', border: `1px solid ${p.is_default ? 'var(--accent)' : 'var(--surface-4)'}`, borderRadius: 8 }}>
              <div style={{ flex: 1 }}>
                <span style={{ fontSize: "var(--text-sm)", fontWeight: 600 }}>{p.name}</span>
                {p.is_default && <span style={{ fontSize: "var(--text-2xs)", background: 'var(--accent-muted)', color: 'var(--accent)', borderRadius: 20, padding: '1px 8px', marginLeft: 8 }}>Por defecto</span>}
                <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginTop: 2 }}>
                  {p.days_per_year} días/año {p.carries_over ? `· Acumula hasta ${p.max_carryover_days || '∞'} días` : '· No acumula'}
                </div>
              </div>
              <button onClick={() => deletePolicy(p.id)} style={{ background: 'none', border: '1px solid var(--danger-border)', borderRadius: 6, padding: '3px 8px', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>🗑</button>
            </div>
          ))}
        </div>
        <div style={{ display: 'flex', gap: 10, marginTop: 12, padding: '10px 14px', background: 'var(--accent-muted)', border: '1px dashed var(--accent-border)', borderRadius: 10, flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <div style={{ flex: 2 }}><label style={ls}>Nombre</label><input value={newPolicy.name} onChange={e => setNewPolicy(f => ({ ...f, name: e.target.value }))} style={fs} placeholder="Nombre de la politica" aria-label="Nombre de la politica" /></div>
          <div style={{ flex: 1 }}><label style={ls}>Días/año</label><input type="number" value={newPolicy.days_per_year} onChange={e => setNewPolicy(f => ({ ...f, days_per_year: +e.target.value }))} style={fs} /></div>
          <div style={{ flex: 1 }}><label style={ls}>Máx. acumulación</label><input type="number" value={newPolicy.max_carryover_days} onChange={e => setNewPolicy(f => ({ ...f, max_carryover_days: +e.target.value }))} style={fs} /></div>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: "var(--text-sm)" }}><input type="checkbox" checked={newPolicy.is_default} onChange={e => setNewPolicy(f => ({ ...f, is_default: e.target.checked }))} />Por defecto</label>
          <Button onClick={() => { createPolicy(newPolicy); setNewPolicy({ name: '', days_per_year: 23, carries_over: true, max_carryover_days: 5, is_default: false }) }} disabled={!newPolicy.name}>Crear</Button>
        </div>
      </div>

      {/* Balances */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <div style={{ fontSize: "var(--text-base)", fontWeight: 700 }}>Saldos del equipo</div>
          <select value={year} onChange={e => setYear(+e.target.value)} style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '6px 12px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit' }}>
            {[currentYear - 1, currentYear, currentYear + 1].map(y => <option key={y} value={y}>{y}</option>)}
          </select>
        </div>
        <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, overflow: 'hidden' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr 1fr 80px', gap: 12, padding: '8px 16px', borderBottom: '1px solid var(--surface-4)', fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            <span>Persona</span><span>Asignados</span><span>Tomados</span><span>Pendientes</span><span>Disponibles</span><span>Editar</span>
          </div>
          {balances.map(b => (
            <div key={b.user_id} style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr 1fr 80px', gap: 12, padding: '10px 16px', borderBottom: '1px solid var(--surface-4)30', alignItems: 'center' }}>
              <div>
                <div style={{ fontSize: "var(--text-base)", fontWeight: 600 }}>{b.user_name}</div>
                {b.department && <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>{b.department}</div>}
              </div>
              <span style={{ fontSize: "var(--text-base)", fontFamily: 'var(--font-mono)' }}>{b.days_entitled}d</span>
              <span style={{ fontSize: "var(--text-base)", fontFamily: 'var(--font-mono)', color: 'var(--accent)' }}>{b.days_taken}d</span>
              <span style={{ fontSize: "var(--text-base)", fontFamily: 'var(--font-mono)', color: 'var(--warning)' }}>{b.days_pending}d</span>
              <span style={{ fontSize: "var(--text-base)", fontFamily: 'var(--font-mono)', color: b.days_remaining <= 0 ? 'var(--danger)' : 'var(--success)', fontWeight: 700 }}>{b.days_remaining}d</span>
              <input type="number" defaultValue={b.days_entitled} min="0" max="60" onBlur={e => updateBalance({ userId: b.user_id, days: +e.target.value })}
                style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 6, padding: '4px 8px', color: 'var(--text-1)', fontSize: "var(--text-sm)", outline: 'none', fontFamily: 'inherit', width: '100%', textAlign: 'center' }} />
            </div>
          ))}
        </div>
      </div>
    </Section>
  )
}

// ── Numbering section ─────────────────────────────────────────────────────────
function NumberingSection() {
  const toast = useToast()
  const qc = useQueryClient()
  const { data: seqs = [], isLoading } = useQuery({ queryKey: ['numbering-seqs'], queryFn: () => advancedConfigApi.getNumbering().then(r => r.data) })
  const { mutate: update } = useMutation({ mutationFn: ({ entity, data }) => advancedConfigApi.updateNumbering(entity, data), onSuccess: () => qc.invalidateQueries(['numbering-seqs']) , onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))})
  const { mutate: reset } = useMutation({ mutationFn: advancedConfigApi.resetNumbering, onSuccess: () => qc.invalidateQueries(['numbering-seqs']) , onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))})
  const ENTITY_LABELS = { project: 'Proyecto', task: 'Tarea', contract: 'Contrato', opportunity: 'Oportunidad', change_request: 'Control de cambios', deliverable: 'Entregable', risk: 'Riesgo' }

  return (
    <Section icon="🔢" title="Numeracion" description="Prefijos y contadores automaticos">
      {isLoading ? <Spinner /> : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {seqs.map(s => (
            <div key={s.entity} style={{ display: 'flex', gap: 14, alignItems: 'flex-end', padding: '12px 16px', background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 10 }}>
              <div style={{ width: 120, flexShrink: 0 }}>
                <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--text-1)' }}>{ENTITY_LABELS[s.entity] || s.entity}</div>
                <div style={{ fontSize: "var(--text-xs)", color: 'var(--accent)', fontFamily: 'var(--font-mono)', marginTop: 4 }}>{s.next_preview}</div>
              </div>
              <div style={{ display: 'flex', gap: 8, flex: 1, flexWrap: 'wrap', alignItems: 'flex-end' }}>
                <div><label style={{ ...ls, fontSize: "var(--text-2xs)" }}>Prefijo</label><input defaultValue={s.prefix} onBlur={e => update({ entity: s.entity, data: { ...s, prefix: e.target.value } })} style={{ ...fs, width: 70 }} placeholder="Prefijo" aria-label="Prefijo" /></div>
                <div><label style={{ ...ls, fontSize: "var(--text-2xs)" }}>Sep.</label><input defaultValue={s.separator} onBlur={e => update({ entity: s.entity, data: { ...s, separator: e.target.value } })} style={{ ...fs, width: 40 }} /></div>
                <div><label style={{ ...ls, fontSize: "var(--text-2xs)" }}>Dígitos</label><input type="number" min="1" max="8" defaultValue={s.padding} onBlur={e => update({ entity: s.entity, data: { ...s, padding: +e.target.value } })} style={{ ...fs, width: 60 }} /></div>
                <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', fontSize: "var(--text-sm)", color: 'var(--text-2)', paddingBottom: 4 }}>
                  <input type="checkbox" defaultChecked={s.include_year} onChange={e => update({ entity: s.entity, data: { ...s, include_year: e.target.checked } })} />
                  Incluir año
                </label>
              </div>
              <div style={{ flexShrink: 0 }}>
                <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginBottom: 4 }}>Contador: {s.current_value}</div>
                <button onClick={() => { openConfirmGlobal({ message: `¿Resetear contador de ${ENTITY_LABELS[s.entity] || s.entity} a 0?`, onConfirm: () => reset(s.entity), danger: true }) }} style={{ background: 'none', border: '1px solid var(--danger-border)', borderRadius: 6, padding: '4px 10px', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-xs)", fontFamily: 'inherit' }}>Resetear</button>
              </div>
            </div>
          ))}
        </div>
      )}
    </Section>
  )
}

// ── Custom fields section ─────────────────────────────────────────────────────
function CustomFieldsSection() {
  const { t } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const { data: fields = [], isLoading } = useQuery({ queryKey: ['custom-fields'], queryFn: () => advancedConfigApi.getCustomFields().then(r => r.data) })
  const { mutate: createField } = useMutation({ mutationFn: advancedConfigApi.createCustomField, onSuccess: () => qc.invalidateQueries(['custom-fields']), onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) })
  const { mutate: updateField } = useMutation({ mutationFn: ({ id, data }) => advancedConfigApi.updateCustomField(id, data), onSuccess: () => { qc.invalidateQueries(['custom-fields']); setEditingFieldId(null) }, onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) })
  const { mutate: deleteField } = useMutation({ mutationFn: advancedConfigApi.deleteCustomField, onSuccess: () => qc.invalidateQueries(['custom-fields']), onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) })
  const [editingFieldId, setEditingFieldId] = useState(null)
  const [editFieldForm, setEditFieldForm] = useState({ name: '', is_required: false, placeholder: '' })
  const [form, setForm] = useState({ entity: 'project', name: '', field_key: '', field_type: 'text', is_required: false, placeholder: '' })
  const ENTITIES = [
    { value: 'project',     label: 'Proyecto' },
    { value: 'task',        label: 'Tarea' },
    { value: 'user',        label: 'Usuario' },
    { value: 'client',      label: 'Cliente' },
    { value: 'contract',    label: 'Contrato' },
    { value: 'invoice',     label: 'Factura' },
    { value: 'absence',     label: 'Ausencia' },
    { value: 'document',    label: 'Documento' },
    { value: 'risk',        label: 'Riesgo' },
    { value: 'deliverable', label: 'Entregable' },
    { value: 'imputation',  label: 'Imputación' },
    { value: 'expense',     label: 'Gasto' },
    { value: 'opportunity', label: 'Oportunidad' },
    { value: 'ticket',      label: 'Ticket' },
  ]
  const TYPES = [{ value: 'text', label: 'Texto' }, { value: 'number', label: 'Número' }, { value: 'date', label: 'Fecha' }, { value: 'select', label: 'Selector' }, { value: 'boolean', label: 'Sí/No' }, { value: 'url', label: 'URL' }]
  const TYPE_ICONS = { text: '📝', number: '🔢', date: '📅', select: '📋', boolean: '☑️', url: '🔗' }
  const byEntity = fields.reduce((a, f) => { if (!a[f.entity]) a[f.entity] = []; a[f.entity].push(f); return a }, {})

  return (
    <Section icon="🧩" title="Campos personalizados" description="Define campos extra para entidades">
      {isLoading ? <Spinner /> : (
        <div style={{ marginBottom: 20 }}>
          {Object.entries(byEntity).map(([entity, entityFields]) => (
            <div key={entity} style={{ marginBottom: 16 }}>
              <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>
                {ENTITIES.find(e => e.value === entity)?.label || entity}
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {entityFields.map(f => (
                  <React.Fragment key={f.id}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '8px 12px', background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 8 }}>
                      <span style={{ fontSize: "var(--text-lg)" }}>{TYPE_ICONS[f.field_type] || '📝'}</span>
                      <div style={{ flex: 1 }}>
                        <span style={{ fontSize: "var(--text-base)", fontWeight: 600 }}>{f.name}</span>
                        <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginLeft: 8, fontFamily: 'var(--font-mono)' }}>{f.field_key}</span>
                        {f.is_required && <span style={{ fontSize: "var(--text-2xs)", color: 'var(--danger)', marginLeft: 8 }}>*obligatorio</span>}
                      </div>
                      <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>{TYPES.find(t => t.value === f.field_type)?.label}</span>
                      <button onClick={() => { setEditingFieldId(f.id); setEditFieldForm({ name: f.name, is_required: f.is_required, placeholder: f.placeholder||'' }) }}
                        style={{ background: 'none', border: '1px solid var(--surface-4)', borderRadius: 6, padding: '3px 8px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>✏</button>
                      <button onClick={() => deleteField(f.id)} style={{ background: 'none', border: '1px solid var(--danger-border)', borderRadius: 6, padding: '3px 8px', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>🗑</button>
                    </div>
                    {editingFieldId === f.id && (
                      <div style={{ display:'flex', gap:8, padding:'10px', background:'var(--accent-muted)',
                        border:'1px solid var(--accent-glow)', borderRadius:8, marginTop:-4, alignItems:'center' }}>
                        <input value={editFieldForm.name} onChange={e=>setEditFieldForm(f=>({...f,name:e.target.value}))}
                          style={{...fs,flex:2}} placeholder="Nombre del campo" aria-label="Nombre del campo" autoFocus />
                        <input value={editFieldForm.placeholder} onChange={e=>setEditFieldForm(f=>({...f,placeholder:e.target.value}))}
                          style={{...fs,flex:2}} placeholder="Placeholder del campo" aria-label="Placeholder del campo" />
                        <label style={{display:'flex',alignItems:'center',gap:5,cursor:'pointer',fontSize: "var(--text-sm)",whiteSpace:'nowrap'}}>
                          <input type="checkbox" checked={editFieldForm.is_required}
                            onChange={e=>setEditFieldForm(f=>({...f,is_required:e.target.checked}))} />Obligatorio
                        </label>
                        <button onClick={() => updateField({ id: f.id, data: editFieldForm })} disabled={!editFieldForm.name}
                          style={{background:'var(--accent)',border:'none',borderRadius:6,padding:'5px 12px',color:'#fff',cursor:'pointer',fontSize: "var(--text-sm)",fontFamily:'inherit'}}>✓ Guardar</button>
                        <button onClick={() => setEditingFieldId(null)}
                          style={{background:'none',border:'1px solid var(--surface-4)',borderRadius:6,padding:'5px 9px',color:'var(--text-2)',cursor:'pointer',fontSize: "var(--text-sm)"}}>✕</button>
                      </div>
                    )}
                  </React.Fragment>
                ))}
              </div>
            </div>
          ))}
          {fields.length === 0 && <EmptyState svgIcon={<Layers size={36} />} title={t('settings.empty_custom_fields_title')} description={t('settings.empty_custom_fields_desc')} />}
        </div>
      )}
      <div style={{ padding: '14px 16px', background: 'var(--accent-muted)', border: '1px dashed var(--accent-border)', borderRadius: 10 }}>
        <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--accent)', marginBottom: 12 }}>Añadir campo personalizado</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr auto', gap: 10, alignItems: 'flex-end' }}>
          <div><label style={ls}>Entidad</label><select value={form.entity} onChange={e => setForm(f => ({ ...f, entity: e.target.value }))} style={fs}>{ENTITIES.map(e => <option key={e.value} value={e.value}>{e.label}</option>)}</select></div>
          <div><label style={ls}>Nombre</label><input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value, field_key: e.target.value.toLowerCase().replace(/\s+/g, '_').replace(/[^a-z0-9_]/g, '') }))} style={fs} placeholder="Nombre del campo" aria-label="Nombre del campo" /></div>
          <div><label style={ls}>Clave</label><input value={form.field_key} onChange={e => setForm(f => ({ ...f, field_key: e.target.value }))} style={fs} placeholder="Clave interna" aria-label="Clave interna" /></div>
          <div><label style={ls}>Tipo</label><select value={form.field_type} onChange={e => setForm(f => ({ ...f, field_type: e.target.value }))} style={fs}>{TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}</select></div>
          <Button onClick={() => { createField(form); setForm({ entity: form.entity, name: '', field_key: '', field_type: 'text', is_required: false, placeholder: '' }) }} disabled={!form.name || !form.field_key}>Añadir</Button>
        </div>
      </div>
    </Section>
  )
}

// ── Templates section ─────────────────────────────────────────────────────────
function TemplatesSection() {
  const { t } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const { data: templates = [], isLoading } = useQuery({ queryKey: ['project-templates'], queryFn: () => advancedConfigApi.getTemplates().then(r => r.data) })
  const { mutate: deleteTemplate } = useMutation({ mutationFn: advancedConfigApi.deleteTemplate, onSuccess: () => qc.invalidateQueries(['project-templates']) , onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))})
  const { mutate: createTemplate, isPending: creatingTemplate } = useMutation({
    mutationFn: advancedConfigApi.createTemplate,
    onSuccess: () => {
      qc.invalidateQueries(['project-templates'])
      setShowCreate(false)
      toast.success('Plantilla creada')
    },
    onError: e => toast.error(extractErr(e, 'No se pudo crear la plantilla')),
  })
  const [showCreate, setShowCreate] = useState(false)
  const [selected, setSelected] = useState(null)

  return (
    <Section icon="📐" title="Plantillas" description="Define plantillas de proyecto y fases">
      {isLoading ? <Spinner /> : templates.length === 0 ? (
        <EmptyState svgIcon={<Sparkles size={36} />} title={t('settings.empty_templates_title')} description={t('settings.empty_templates_desc')} />
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 14, marginBottom: 16 }}>
          {templates.map(t => (
              <div key={t.id} role="button" tabIndex={0} style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, padding: 18, cursor: 'pointer', width:'100%', textAlign:'left', fontFamily:'inherit' }}
              onMouseEnter={e => e.currentTarget.style.borderColor = 'var(--accent-glow)'}
              onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--surface-4)'}
                onClick={() => setSelected(t)}
                onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSelected(t) } }}>
              <div style={{ fontSize: "var(--text-md-em)", fontWeight: 700, marginBottom: 6 }}>{t.name}</div>
              {t.description && <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginBottom: 10 }}>{t.description}</div>}
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 12 }}>
                {[`${t.phase_count} fases`, `${t.task_count} tareas`, `${t.risk_count} riesgos`, `${t.deliverable_count} entregables`].map(l => (
                  <span key={l} style={{ fontSize: "var(--text-xs)", background: 'var(--surface-3)', color: 'var(--text-2)', borderRadius: 20, padding: '2px 8px' }}>{l}</span>
                ))}
                {t.estimated_weeks && <span style={{ fontSize: "var(--text-xs)", color: 'var(--accent)' }}>~{t.estimated_weeks}sem</span>}
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <Button size="sm" onClick={e => { e.stopPropagation(); setSelected(t) }}>Ver detalle</Button>
                <button onClick={e => { e.stopPropagation(); deleteTemplate(t.id) }} style={{ background: 'none', border: '1px solid var(--danger-border)', borderRadius: 6, padding: '4px 10px', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>🗑</button>
              </div>
            </div>
          ))}
        </div>
      )}
      <button onClick={() => setShowCreate(true)} style={{ width: '100%', padding: '10px', border: '1px dashed var(--surface-4)', borderRadius: 10, background: 'transparent', color: 'var(--text-2)', fontSize: "var(--text-base)", cursor: 'pointer', fontFamily: 'inherit', textAlign: 'center' }}>＋ Crear plantilla</button>
      {showCreate && <CreateTemplateModal isSaving={creatingTemplate} onClose={() => setShowCreate(false)} onSave={createTemplate} />}
      {selected && <TemplateDetailModal template={selected} onClose={() => setSelected(null)} />}
    </Section>
  )
}

function CreateTemplateModal({ onClose, onSave, isSaving = false }) {
  const [form, setForm] = useState({ name: '', description: '', project_type: 'consulting', estimated_weeks: '', estimated_hours: '', phases: [], risks: [], deliverables: [] })
  const [phase, setPhase] = useState({ name: '', description: '', estimated_weeks: '', estimated_hours: '', tasks: [] })
  const [task, setTask] = useState({ title: '', estimated_hours: '', skill_required: '' })
  const [risk, setRisk] = useState({ title: '', category: '', probability: 'medium', impact: 'moderate', mitigation_plan: '' })
  const [deliverable, setDeliverable] = useState({ name: '', format: '', week_offset: '', billing_pct: '', acceptance_criteria: '' })
  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.value }))

  const addTaskToPhase = () => {
    if (!task.title?.trim()) return
    setPhase(p => ({
      ...p,
      tasks: [
        ...p.tasks,
        {
          title: task.title.trim(),
          estimated_hours: task.estimated_hours ? Number(task.estimated_hours) : null,
          skill_required: task.skill_required || null,
        },
      ],
    }))
    setTask({ title: '', estimated_hours: '', skill_required: '' })
  }

  const addPhase = () => {
    if (!phase.name?.trim()) return
    setForm(f => ({
      ...f,
      phases: [
        ...f.phases,
        {
          name: phase.name.trim(),
          description: phase.description || null,
          estimated_weeks: phase.estimated_weeks ? Number(phase.estimated_weeks) : null,
          estimated_hours: phase.estimated_hours ? Number(phase.estimated_hours) : null,
          tasks: phase.tasks,
        },
      ],
    }))
    setPhase({ name: '', description: '', estimated_weeks: '', estimated_hours: '', tasks: [] })
    setTask({ title: '', estimated_hours: '', skill_required: '' })
  }

  const addRisk = () => {
    if (!risk.title?.trim()) return
    setForm(f => ({
      ...f,
      risks: [
        ...f.risks,
        {
          title: risk.title.trim(),
          category: risk.category || null,
          probability: risk.probability,
          impact: risk.impact,
          mitigation_plan: risk.mitigation_plan || null,
        },
      ],
    }))
    setRisk({ title: '', category: '', probability: 'medium', impact: 'moderate', mitigation_plan: '' })
  }

  const addDeliverable = () => {
    if (!deliverable.name?.trim()) return
    setForm(f => ({
      ...f,
      deliverables: [
        ...f.deliverables,
        {
          name: deliverable.name.trim(),
          format: deliverable.format || null,
          week_offset: deliverable.week_offset ? Number(deliverable.week_offset) : null,
          billing_pct: deliverable.billing_pct ? Number(deliverable.billing_pct) : null,
          acceptance_criteria: deliverable.acceptance_criteria || null,
        },
      ],
    }))
    setDeliverable({ name: '', format: '', week_offset: '', billing_pct: '', acceptance_criteria: '' })
  }

  const submit = () => {
    onSave({
      ...form,
      estimated_weeks: form.estimated_weeks ? Number(form.estimated_weeks) : null,
      estimated_hours: form.estimated_hours ? Number(form.estimated_hours) : null,
    })
  }

  return (
    <Modal open title="Nueva plantilla" onClose={onClose} width={760}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr', gap: 12 }}>
          <div><label style={ls}>Nombre *</label><input value={form.name} onChange={set('name')} style={fs} placeholder="Nombre de la plantilla" aria-label="Nombre de la plantilla" /></div>
          <div><label style={ls}>Tipo proyecto</label><select value={form.project_type} onChange={set('project_type')} style={fs}><option value="consulting">consulting</option><option value="development">development</option><option value="maintenance">maintenance</option><option value="internal">internal</option><option value="rd">rd</option></select></div>
          <div><label style={ls}>Semanas estimadas</label><input type="number" value={form.estimated_weeks} onChange={set('estimated_weeks')} style={fs} /></div>
          <div><label style={ls}>Horas estimadas</label><input type="number" value={form.estimated_hours} onChange={set('estimated_hours')} style={fs} /></div>
        </div>
        <div><label style={ls}>Descripción</label><textarea value={form.description} onChange={set('description')} rows={2} style={{ ...fs, resize: 'vertical' }} /></div>

        {/* Phases */}
        <div>
          <div style={{ fontSize: "var(--text-base)", fontWeight: 700, marginBottom: 10 }}>Fases ({form.phases.length})</div>
          {form.phases.map((p, i) => (
            <div key={i} style={{ padding: '8px 12px', background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 8, marginBottom: 6 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: "var(--text-base)", fontWeight: 600 }}>{p.name}</span>
                <div style={{ display: 'flex', gap: 8 }}>
                  <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>{p.tasks.length} tareas</span>
                  <button onClick={() => setForm(f => ({ ...f, phases: f.phases.filter((_, j) => j !== i) }))} style={{ background: 'none', border: 'none', color: 'var(--danger)', cursor: 'pointer' }}>×</button>
                </div>
              </div>
            </div>
          ))}
          <div style={{ display: 'grid', gridTemplateColumns: '2fr 2fr 1fr 1fr', gap: 8, padding: 8, background: 'var(--surface-3)', borderRadius: 8, marginBottom: 8 }}>
            <input value={phase.name} onChange={e => setPhase(f => ({ ...f, name: e.target.value }))} style={fs} placeholder="Nombre de la fase" aria-label="Nombre de la fase" />
            <input value={phase.description} onChange={e => setPhase(f => ({ ...f, description: e.target.value }))} style={fs} placeholder="Descripción de fase" aria-label="Descripción de fase" />
            <input type="number" value={phase.estimated_weeks} onChange={e => setPhase(f => ({ ...f, estimated_weeks: e.target.value }))} style={fs} placeholder="Semanas" aria-label="Semanas estimadas" />
            <input type="number" value={phase.estimated_hours} onChange={e => setPhase(f => ({ ...f, estimated_hours: e.target.value }))} style={fs} placeholder="Horas" aria-label="Horas estimadas" />
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr auto', gap: 8, padding: 8, background: 'var(--surface-3)', borderRadius: 8 }}>
            <input value={task.title} onChange={e => setTask(f => ({ ...f, title: e.target.value }))} style={fs} placeholder="Título tarea" aria-label="Título tarea" />
            <input type="number" value={task.estimated_hours} onChange={e => setTask(f => ({ ...f, estimated_hours: e.target.value }))} style={fs} placeholder="Horas" aria-label="Horas tarea" />
            <input value={task.skill_required} onChange={e => setTask(f => ({ ...f, skill_required: e.target.value }))} style={fs} placeholder="Skill requerida" aria-label="Skill requerida" />
            <Button size="sm" onClick={addTaskToPhase} disabled={!task.title}>+ Tarea</Button>
          </div>
          {phase.tasks.length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 8 }}>
              {phase.tasks.map((tk, i) => (
                <span key={`${tk.title}-${i}`} style={{ fontSize: "var(--text-xs)", background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 16, padding: '2px 8px' }}>{tk.title}{tk.estimated_hours ? ` (${tk.estimated_hours}h)` : ''}</span>
              ))}
            </div>
          )}
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 8 }}>
            <Button size="sm" onClick={addPhase} disabled={!phase.name}>+ Fase</Button>
          </div>
        </div>

        {/* Risks */}
        <div>
          <div style={{ fontSize: "var(--text-base)", fontWeight: 700, marginBottom: 10 }}>Riesgos ({form.risks.length})</div>
          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr auto', gap: 8, padding: 8, background: 'var(--surface-3)', borderRadius: 8 }}>
            <input value={risk.title} onChange={e => setRisk(f => ({ ...f, title: e.target.value }))} style={fs} placeholder="Título riesgo" aria-label="Título riesgo" />
            <input value={risk.category} onChange={e => setRisk(f => ({ ...f, category: e.target.value }))} style={fs} placeholder="Categoría" aria-label="Categoría riesgo" />
            <select value={risk.probability} onChange={e => setRisk(f => ({ ...f, probability: e.target.value }))} style={fs}><option value="low">low</option><option value="medium">medium</option><option value="high">high</option></select>
            <select value={risk.impact} onChange={e => setRisk(f => ({ ...f, impact: e.target.value }))} style={fs}><option value="minor">minor</option><option value="moderate">moderate</option><option value="major">major</option><option value="critical">critical</option></select>
            <Button size="sm" onClick={addRisk} disabled={!risk.title}>+ Riesgo</Button>
          </div>
          <textarea value={risk.mitigation_plan} onChange={e => setRisk(f => ({ ...f, mitigation_plan: e.target.value }))} rows={2} style={{ ...fs, resize: 'vertical', marginTop: 8 }} placeholder="Plan de mitigación (opcional)" />
        </div>

        {/* Deliverables */}
        <div>
          <div style={{ fontSize: "var(--text-base)", fontWeight: 700, marginBottom: 10 }}>Entregables ({form.deliverables.length})</div>
          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr auto', gap: 8, padding: 8, background: 'var(--surface-3)', borderRadius: 8 }}>
            <input value={deliverable.name} onChange={e => setDeliverable(f => ({ ...f, name: e.target.value }))} style={fs} placeholder="Nombre entregable" aria-label="Nombre entregable" />
            <input value={deliverable.format} onChange={e => setDeliverable(f => ({ ...f, format: e.target.value }))} style={fs} placeholder="Formato" aria-label="Formato entregable" />
            <input type="number" value={deliverable.week_offset} onChange={e => setDeliverable(f => ({ ...f, week_offset: e.target.value }))} style={fs} placeholder="Semana" aria-label="Semana entregable" />
            <input type="number" value={deliverable.billing_pct} onChange={e => setDeliverable(f => ({ ...f, billing_pct: e.target.value }))} style={fs} placeholder="% facturación" aria-label="Porcentaje facturación" />
            <Button size="sm" onClick={addDeliverable} disabled={!deliverable.name}>+ Entregable</Button>
          </div>
          <textarea value={deliverable.acceptance_criteria} onChange={e => setDeliverable(f => ({ ...f, acceptance_criteria: e.target.value }))} rows={2} style={{ ...fs, resize: 'vertical', marginTop: 8 }} placeholder="Criterio de aceptación (opcional)" />
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={submit} disabled={!form.name || isSaving}>{isSaving ? 'Creando...' : 'Crear plantilla'}</Button>
        </div>
      </div>
    </Modal>
  )
}

function TemplateDetailModal({ template, onClose }) {
  return (
    <Modal open title={template.name} onClose={onClose} width={600}>
      {template.description && <p style={{ color: 'var(--text-2)', fontSize: "var(--text-base)", marginBottom: 16 }}>{template.description}</p>}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {template.phases?.map(p => (
          <div key={p.id} style={{ background: 'var(--surface-3)', borderRadius: 10, padding: '12px 16px' }}>
            <div style={{ fontSize: "var(--text-base)", fontWeight: 700, marginBottom: 8 }}>📋 {p.name}</div>
            {p.tasks?.map(t => (
              <div key={t.id} style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', padding: '3px 8px', borderLeft: '2px solid var(--surface-4)', marginBottom: 3 }}>
                {t.title} {t.estimated_hours ? `(${t.estimated_hours}h)` : ''}
              </div>
            ))}
          </div>
        ))}
      </div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 16 }}>
        <Button variant="secondary" onClick={onClose}>Cerrar</Button>
      </div>
    </Modal>
  )
}

// ── Offices section ───────────────────────────────────────────────────────────
function OfficesSection() {
  const toast = useToast()
  const qc = useQueryClient()
  const { timezone: defaultTimezone } = useOrgSettings()
  const { data: offices = [] } = useQuery({ queryKey: ['offices'], queryFn: () => advancedConfigApi.getOffices().then(r => r.data) })
  const { mutate: create } = useMutation({ mutationFn: advancedConfigApi.createOffice, onSuccess: () => qc.invalidateQueries(['offices']), onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) })
  const { mutate: update } = useMutation({ mutationFn: ({ id, data }) => advancedConfigApi.updateOffice(id, data), onSuccess: () => { qc.invalidateQueries(['offices']); setEditingId(null) }, onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) })
  const { mutate: del } = useMutation({ mutationFn: advancedConfigApi.deleteOffice, onSuccess: () => qc.invalidateQueries(['offices']), onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) })
  const [form, setForm] = useState({ name: '', country: '', city: '', timezone: defaultTimezone })
  const [editingId, setEditingId] = useState(null)
  const [editForm, setEditForm] = useState({ name: '', country: '', city: '', timezone: defaultTimezone })
  const TIMEZONES = ['Europe/Madrid', 'Europe/London', 'Europe/Paris', 'Europe/Berlin', 'America/New_York', 'America/Los_Angeles', 'Asia/Tokyo', 'Asia/Shanghai']

  return (
    <Section icon="🏢" title="Sedes" description="Gestiona oficinas y zonas horarias">
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 16 }}>
        {offices.map(o => (
          <div key={o.id}>
            {editingId === o.id ? (
              <div style={{ display: 'flex', gap: 8, padding: '10px 12px', background: 'var(--accent-muted)',
                border: '1px solid var(--accent-glow)', borderRadius: 10, flexWrap: 'wrap', alignItems: 'flex-end' }}>
                <div style={{ flex: 2, minWidth: 120 }}><label style={ls}>Nombre *</label>
                  <input value={editForm.name} onChange={e => setEditForm(f=>({...f,name:e.target.value}))} style={fs} autoFocus /></div>
                <div style={{ flex: 1, minWidth: 90 }}><label style={ls}>País</label>
                  <input value={editForm.country} onChange={e => setEditForm(f=>({...f,country:e.target.value}))} style={fs} /></div>
                <div style={{ flex: 1, minWidth: 90 }}><label style={ls}>Ciudad</label>
                  <input value={editForm.city} onChange={e => setEditForm(f=>({...f,city:e.target.value}))} style={fs} /></div>
                <div style={{ flex: 1, minWidth: 160 }}><label style={ls}>Zona horaria</label>
                  <select value={editForm.timezone} onChange={e => setEditForm(f=>({...f,timezone:e.target.value}))} style={fs}>
                    {TIMEZONES.map(t => <option key={t} value={t}>{t}</option>)}
                  </select></div>
                <div style={{ display: 'flex', gap: 6, paddingBottom: 1 }}>
                  <button onClick={() => update({ id: o.id, data: editForm })} disabled={!editForm.name}
                    style={{ background:'var(--accent)',border:'none',borderRadius:6,padding:'6px 14px',
                      color:'#fff',cursor:'pointer',fontSize: "var(--text-sm)",fontFamily:'inherit' }}>✓ Guardar</button>
                  <button onClick={() => setEditingId(null)}
                    style={{ background:'none',border:'1px solid var(--surface-4)',borderRadius:6,
                      padding:'6px 10px',color:'var(--text-2)',cursor:'pointer',fontSize: "var(--text-sm)" }}>Cancelar</button>
                </div>
              </div>
            ) : (
              <div style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '10px 14px', background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 10 }}>
                <span style={{ fontSize: "var(--text-xl)" }}>🏢</span>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: "var(--text-base)", fontWeight: 700 }}>{o.name}</div>
                  <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>{o.city}{o.country ? `, ${o.country}` : ''} · {o.timezone}</div>
                </div>
                <button onClick={() => { setEditingId(o.id); setEditForm({ name:o.name, country:o.country||'', city:o.city||'', timezone:o.timezone||defaultTimezone }) }}
                  style={{ background:'none',border:'1px solid var(--surface-4)',borderRadius:6,padding:'3px 8px',color:'var(--text-2)',cursor:'pointer',fontSize: "var(--text-xs)" }}>✏</button>
                <button onClick={() => del(o.id)} style={{ background: 'none', border: '1px solid var(--danger-border)', borderRadius: 6, padding: '3px 8px', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>🗑</button>
              </div>
            )}
          </div>
        ))}
        {offices.length === 0 && <EmptyState svgIcon={<Building2 size={36} />} title="Sin sedes registradas" description="Añade la primera sede para tu organización" />}
      </div>
      <div style={{ display: 'flex', gap: 10, padding: '10px 14px', background: 'var(--accent-muted)', border: '1px dashed var(--accent-border)', borderRadius: 10, flexWrap: 'wrap', alignItems: 'flex-end' }}>
        <div style={{ flex: 2 }}><label style={ls}>Nombre *</label><input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} style={fs} placeholder="Nombre de la sede" aria-label="Nombre de la sede" /></div>
        <div style={{ flex: 1 }}><label style={ls}>País</label><input value={form.country} onChange={e => setForm(f => ({ ...f, country: e.target.value }))} style={fs} placeholder="Pais" aria-label="Pais" /></div>
        <div style={{ flex: 1 }}><label style={ls}>Ciudad</label><input value={form.city} onChange={e => setForm(f => ({ ...f, city: e.target.value }))} style={fs} /></div>
        <div style={{ flex: 1 }}><label style={ls}>Zona horaria</label><select value={form.timezone} onChange={e => setForm(f => ({ ...f, timezone: e.target.value }))} style={fs}>{TIMEZONES.map(t => <option key={t} value={t}>{t}</option>)}</select></div>
        <Button onClick={() => { create(form); setForm({ name: '', country: '', city: '', timezone: defaultTimezone }) }} disabled={!form.name}>Añadir</Button>
      </div>
    </Section>
  )
}

// ── Task types section ────────────────────────────────────────────────────────
function TaskTypesSection() {
  const toast = useToast()
  const qc = useQueryClient()
  const { data: types = [], isLoading } = useQuery({ queryKey: ['task-types-config'], queryFn: () => advancedConfigApi.getTaskTypes().then(r => r.data) })
  const { mutate: create } = useMutation({ mutationFn: advancedConfigApi.createTaskType, onSuccess: () => qc.invalidateQueries(['task-types-config']), onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) })
  const { mutate: update } = useMutation({ mutationFn: ({ id, data }) => advancedConfigApi.updateTaskType(id, data), onSuccess: () => { qc.invalidateQueries(['task-types-config']); setEditingId(null) }, onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) })
  const { mutate: del } = useMutation({ mutationFn: advancedConfigApi.deleteTaskType, onSuccess: () => qc.invalidateQueries(['task-types-config']), onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) })
  const [form, setForm] = useState({ name: '', value: '', icon: '📋', color: '#7a8aaa', is_billable_default: true })
  const [editingId, setEditingId] = useState(null)
  const [editForm, setEditForm] = useState({ name: '', icon: '📋', color: '#7a8aaa', is_billable_default: true })

  return (
    <Section icon="🏷️" title="Tipos de tarea" description="Gestiona etiquetas y tipos facturables">
      {isLoading ? <Spinner /> : (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 16 }}>
          {types.map(t => (
            <div key={t.id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px', background: 'var(--surface-2)', border: `1px solid ${t.color}40`, borderRadius: 10 }}>
              <span style={{ fontSize: "var(--text-lg-em)" }}>{t.icon}</span>
              <div>
                <div style={{ fontSize: "var(--text-base)", fontWeight: 700, color: t.color }}>{t.name}</div>
                <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-2)' }}>{t.is_billable_default ? 'Facturable' : 'No facturable'}</div>
              </div>
              <button onClick={() => { setEditingId(t.id); setEditForm({ name: t.name, icon: t.icon, color: t.color, is_billable_default: t.is_billable_default }) }}
                style={{ background: 'none', border: 'none', color: 'var(--text-3)', cursor: 'pointer', fontSize: "var(--text-sm)", marginLeft: 2 }}>✏</button>
              <button onClick={() => del(t.id)} style={{ background: 'none', border: 'none', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-md)", marginLeft: 2 }}>×</button>
            </div>
          ))}
        </div>
      )}
      {editingId && (
        <div style={{ display:'flex', gap:8, padding:'10px 14px', background:'var(--accent-muted)',
          border:'1px solid var(--accent-glow)', borderRadius:10, marginBottom:8, flexWrap:'wrap', alignItems:'flex-end' }}>
          <div><label style={ls}>Nombre *</label><input value={editForm.name} onChange={e => setEditForm(f=>({...f,name:e.target.value}))} style={{...fs,width:130}} autoFocus /></div>
          <div><label style={ls}>Icono</label><input value={editForm.icon} onChange={e => setEditForm(f=>({...f,icon:e.target.value}))} style={{...fs,width:55}} /></div>
          <div><label style={ls}>Color</label><input type="color" value={/^#[0-9a-fA-F]{6}$/.test(editForm.color)?editForm.color:'#7a8aaa'} onChange={e=>setEditForm(f=>({...f,color:e.target.value}))} style={{width:38,height:35,border:'none',background:'transparent',cursor:'pointer'}} /></div>
          <label style={{display:'flex',alignItems:'center',gap:5,cursor:'pointer',fontSize: "var(--text-sm)",paddingBottom:4}}><input type="checkbox" checked={editForm.is_billable_default} onChange={e=>setEditForm(f=>({...f,is_billable_default:e.target.checked}))} />Facturable</label>
          <button onClick={() => update({ id: editingId, data: editForm })} disabled={!editForm.name} style={{background:'var(--accent)',border:'none',borderRadius:6,padding:'6px 14px',color:'#fff',cursor:'pointer',fontSize: "var(--text-sm)",fontFamily:'inherit'}}>✓ Guardar</button>
          <button onClick={() => setEditingId(null)} style={{background:'none',border:'1px solid var(--surface-4)',borderRadius:6,padding:'6px 10px',color:'var(--text-2)',cursor:'pointer',fontSize: "var(--text-sm)"}}>Cancelar</button>
        </div>
      )}
      <div style={{ display: 'flex', gap: 10, padding: '10px 14px', background: 'var(--accent-muted)', border: '1px dashed var(--accent-border)', borderRadius: 10, flexWrap: 'wrap', alignItems: 'flex-end' }}>
        <div><label style={ls}>Nombre *</label><input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value, value: e.target.value.toLowerCase().replace(/\s+/g, '_') }))} style={{ ...fs, width: 140 }} placeholder="Nombre" aria-label="Nombre" /></div>
        <div><label style={ls}>Clave</label><input value={form.value} onChange={e => setForm(f => ({ ...f, value: e.target.value }))} style={{ ...fs, width: 110 }} placeholder="Clave" aria-label="Clave" /></div>
        <div><label style={ls}>Icono</label><input value={form.icon} onChange={e => setForm(f => ({ ...f, icon: e.target.value }))} style={{ ...fs, width: 60 }} placeholder="Icono" aria-label="Icono" /></div>
        <div><label style={ls}>Color</label><div style={{ display: 'flex', gap: 6 }}><input type="color" value={/^#[0-9a-fA-F]{6}$/.test(form.color) ? form.color : '#7a8aaa'} onChange={e => setForm(f => ({ ...f, color: e.target.value }))} style={{ width: 38, height: 38, border: 'none', background: 'transparent', cursor: 'pointer' }} /><input value={form.color} onChange={e => setForm(f => ({ ...f, color: e.target.value }))} style={{ ...fs, width: 90 }} /></div></div>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', fontSize: "var(--text-sm)", paddingBottom: 4 }}><input type="checkbox" checked={form.is_billable_default} onChange={e => setForm(f => ({ ...f, is_billable_default: e.target.checked }))} />Facturable</label>
        <Button onClick={() => { create(form); setForm({ name: '', value: '', icon: '📋', color: '#7a8aaa', is_billable_default: true }) }} disabled={!form.name || !form.value}>Añadir</Button>
      </div>
    </Section>
  )
}

// ── Departments & Holidays (existing) ─────────────────────────────────────────
function DepartmentsSection() {
  const toast = useToast()
  const qc = useQueryClient()
  const { data = [], isLoading } = useQuery({ queryKey: ['departments'], queryFn: () => settingsApi.getDepartments().then(r => r.data) })
  const { mutate: create } = useMutation({ mutationFn: settingsApi.createDepartment, onSuccess: () => qc.invalidateQueries(['departments']), onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) })
  const { mutate: update } = useMutation({ mutationFn: ({ id, data }) => settingsApi.updateDepartment(id, data), onSuccess: () => { qc.invalidateQueries(['departments']); setEditingId(null) }, onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) })
  const { mutate: del } = useMutation({ mutationFn: settingsApi.deleteDepartment, onSuccess: () => qc.invalidateQueries(['departments']), onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) })
  const [form, setForm] = useState({ name: '', description: '' })
  const [editingId, setEditingId] = useState(null)
  const [editForm, setEditForm] = useState({ name: '', description: '' })
  return (
    <Section icon="🏢" title="Departamentos" description="Estructura interna de la organizacion">
      {isLoading ? <Spinner /> : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 12 }}>
          {data.map(d => (
            <div key={d.id}>
              {editingId === d.id ? (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px',
                  background: 'var(--accent-muted)', border: '1px solid var(--accent-glow)', borderRadius: 10 }}>
                  <input value={editForm.name} onChange={e => setEditForm(f => ({ ...f, name: e.target.value }))}
                    style={{ ...fs, flex: 2, padding: '5px 9px' }} placeholder="Nombre del departamento" aria-label="Nombre del departamento" autoFocus />
                  <input value={editForm.description} onChange={e => setEditForm(f => ({ ...f, description: e.target.value }))}
                    style={{ ...fs, flex: 3, padding: '5px 9px' }} placeholder="Descripcion" aria-label="Descripcion del departamento" />
                  <button onClick={() => update({ id: d.id, data: editForm })} disabled={!editForm.name}
                    style={{ background: 'var(--accent)', border: 'none', borderRadius: 6, padding: '5px 12px',
                      color: '#fff', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>✓</button>
                  <button onClick={() => setEditingId(null)}
                    style={{ background: 'none', border: '1px solid var(--surface-4)', borderRadius: 6,
                      padding: '5px 9px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)" }}>✕</button>
                </div>
              ) : (
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px',
                  background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 10 }}>
                  <span style={{ flex: 1, fontSize: "var(--text-base)", fontWeight: 600 }}>{d.name}</span>
                  {d.description && <span style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>{d.description}</span>}
                  <button onClick={() => { setEditingId(d.id); setEditForm({ name: d.name, description: d.description || '' }) }}
                    style={{ background: 'none', border: '1px solid var(--surface-4)', borderRadius: 6,
                      padding: '3px 8px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>✏</button>
                  <button onClick={() => del(d.id)}
                    style={{ background: 'none', border: '1px solid var(--danger-border)', borderRadius: 6,
                      padding: '3px 8px', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>🗑</button>
                </div>
              )}
            </div>
          ))}
          {data.length === 0 && <div style={{ fontSize: "var(--text-base)", color: 'var(--text-3)', textAlign: 'center', padding: 16 }}>Sin departamentos</div>}
        </div>
      )}
      <div style={{ display: 'flex', gap: 10, padding: '10px', background: 'var(--accent-muted)', border: '1px dashed var(--accent-border)', borderRadius: 10 }}>
        <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} style={{ ...fs, flex: 2 }} placeholder="Nombre del departamento" aria-label="Nombre del departamento" />
        <input value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} style={{ ...fs, flex: 2 }} placeholder="Descripcion" aria-label="Descripcion del departamento" />
        <Button onClick={() => { create(form); setForm({ name: '', description: '' }) }} disabled={!form.name}>Añadir</Button>
      </div>
    </Section>
  )
}



// ── Metrics section ───────────────────────────────────────────────────────────
const OPERATOR_LABELS = { '+': 'Suma', '-': 'Resta', '*': 'Multiplica', '/': 'Divide' }
const EMPTY_METRIC = { label: '', description: '', operand_a: '', operator: '/', operand_b_type: 'metric', operand_b: '', scale: 1 }

function MetricsSection() {
  const toast = useToast()
  const qc = useQueryClient()

  const { data: metricsData = { metrics: [] } } = useQuery({ queryKey: ['bi-alert-metrics'], queryFn: () => biSmartAlertsApi.supportedMetrics().then(r => r.data) })
  const { data: customData = { items: [] } } = useQuery({ queryKey: ['bi-custom-metrics'], queryFn: () => biSmartAlertsApi.listCustomMetrics().then(r => r.data) })
  const builtinMetrics = (metricsData.metrics ?? []).filter(m => !m.is_custom)
  const customMetrics = customData.items ?? []

  const { mutate: createMetric, isPending: isCreating } = useMutation({
    mutationFn: biSmartAlertsApi.createCustomMetric,
    onSuccess: () => { qc.invalidateQueries(['bi-custom-metrics']); qc.invalidateQueries(['bi-alert-metrics']); setShowCreate(false); setForm(EMPTY_METRIC) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: deleteMetric } = useMutation({
    mutationFn: biSmartAlertsApi.deleteCustomMetric,
    onSuccess: () => { qc.invalidateQueries(['bi-custom-metrics']); qc.invalidateQueries(['bi-alert-metrics']) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState(EMPTY_METRIC)
  const setF = k => e => setForm(f => ({ ...f, [k]: e.target.value }))

  const preview = (() => {
    const la = builtinMetrics.find(m => m.key === form.operand_a)?.label ?? form.operand_a
    const lb = form.operand_b_type === 'metric'
      ? (builtinMetrics.find(m => m.key === form.operand_b)?.label ?? form.operand_b)
      : form.operand_b
    if (!form.operand_a) return ''
    const scaled = parseFloat(form.scale) !== 1 ? ` × ${form.scale}` : ''
    return `(${la} ${form.operator} ${lb})${scaled}`
  })()

  const submit = () => {
    if (!form.label.trim() || !form.operand_a) return toast.error('Nombre y operando A son obligatorios')
    if (form.operand_b_type === 'metric' && !form.operand_b) return toast.error('Selecciona la métrica B')
    createMetric({ ...form, scale: parseFloat(form.scale) || 1 })
  }

  return (
    <Section icon="📊" title="Métricas" description="Métricas del sistema disponibles para alertas y análisis">
      {/* Built-in metrics */}
      <div style={{ marginBottom: 24 }}>
        <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '.07em', marginBottom: 10 }}>Métricas del sistema ({builtinMetrics.length})</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 8 }}>
          {builtinMetrics.map(m => (
            <div key={m.key} style={{ padding: '8px 12px', background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 8 }}>
              <div style={{ fontSize: "var(--text-sm)", fontWeight: 600, color: 'var(--text-1)' }}>{m.label}</div>
              <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', fontFamily: 'monospace', marginTop: 2 }}>{m.key}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Custom metrics */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
          <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '.07em' }}>Métricas personalizadas ({customMetrics.length})</div>
          <Button onClick={() => setShowCreate(true)}>+ Nueva métrica</Button>
        </div>
        {customMetrics.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '16px 0', color: 'var(--text-3)', fontSize: "var(--text-sm)" }}>No hay métricas personalizadas. Crea la primera combinando métricas existentes.</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {customMetrics.map(cm => {
              const f = cm.formula ?? {}
              const la = builtinMetrics.find(m => m.key === f.operand_a)?.label ?? f.operand_a
              const lb = f.operand_b_type === 'metric'
                ? (builtinMetrics.find(m => m.key === f.operand_b)?.label ?? f.operand_b)
                : f.operand_b
              const scale = parseFloat(f.scale) !== 1 ? ` × ${f.scale}` : ''
              return (
                <div key={cm.key} style={{ padding: '12px 14px', background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 10, display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 600, fontSize: "var(--text-base)", marginBottom: 2 }}>{cm.label}</div>
                    <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', fontFamily: 'monospace' }}>({la} {f.operator} {lb}){scale}</div>
                    {cm.description && <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', marginTop: 2 }}>{cm.description}</div>}
                  </div>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexShrink: 0 }}>
                    <span style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', fontFamily: 'monospace' }}>{cm.key}</span>
                    <Button variant="danger" style={{ padding: '4px 10px', fontSize: "var(--text-xs)" }} onClick={() => openConfirmGlobal({ title: 'Eliminar métrica', message: `¿Eliminar "${cm.label}"? Las reglas de alerta que la usen dejarán de funcionar.`, onConfirm: () => deleteMetric(cm.key) })}>Eliminar</Button>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {showCreate && (
        <Modal open title="Nueva métrica personalizada" onClose={() => { setShowCreate(false); setForm(EMPTY_METRIC) }} width={500}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div>
              <label style={ls}>Nombre</label>
              <input value={form.label} onChange={setF('label')} style={fs} placeholder="Ej: Ratio coste-ingreso" />
            </div>
            <div>
              <label style={ls}>Descripción (opcional)</label>
              <input value={form.description} onChange={setF('description')} style={fs} placeholder="Para qué sirve esta métrica" />
            </div>
            <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 10, padding: '14px 16px' }}>
              <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '.07em', marginBottom: 12 }}>Fórmula: (A operador B) × escala</div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr auto 1fr', gap: 10, alignItems: 'end', marginBottom: 12 }}>
                <div>
                  <label style={ls}>Métrica A</label>
                  <select value={form.operand_a} onChange={setF('operand_a')} style={fs}>
                    <option value="">— Selecciona —</option>
                    {builtinMetrics.map(m => <option key={m.key} value={m.key}>{m.label}</option>)}
                  </select>
                </div>
                <div>
                  <label style={ls}>Op.</label>
                  <select value={form.operator} onChange={setF('operator')} style={{ ...fs, width: 70 }}>
                    {Object.entries(OPERATOR_LABELS).map(([k, v]) => <option key={k} value={k}>{k} ({v})</option>)}
                  </select>
                </div>
                <div>
                  <label style={ls}>Tipo B</label>
                  <select value={form.operand_b_type} onChange={setF('operand_b_type')} style={fs}>
                    <option value="metric">Otra métrica</option>
                    <option value="constant">Constante</option>
                  </select>
                </div>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                <div>
                  <label style={ls}>{form.operand_b_type === 'metric' ? 'Métrica B' : 'Valor constante'}</label>
                  {form.operand_b_type === 'metric' ? (
                    <select value={form.operand_b} onChange={setF('operand_b')} style={fs}>
                      <option value="">— Selecciona —</option>
                      {builtinMetrics.filter(m => m.key !== form.operand_a).map(m => <option key={m.key} value={m.key}>{m.label}</option>)}
                    </select>
                  ) : (
                    <input type="number" value={form.operand_b} onChange={setF('operand_b')} style={fs} placeholder="0" />
                  )}
                </div>
                <div>
                  <label style={ls}>Escala (× resultado)</label>
                  <input type="number" value={form.scale} onChange={setF('scale')} style={fs} placeholder="1" step="any" />
                </div>
              </div>
              {preview && (
                <div style={{ marginTop: 10, padding: '8px 10px', background: 'var(--surface-3)', borderRadius: 6, fontSize: "var(--text-xs)", color: 'var(--accent)', fontFamily: 'monospace' }}>
                  Vista previa: {preview}
                </div>
              )}
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
              <Button variant="secondary" onClick={() => { setShowCreate(false); setForm(EMPTY_METRIC) }}>Cancelar</Button>
              <Button onClick={submit} disabled={isCreating}>{isCreating ? 'Creando…' : 'Crear métrica'}</Button>
            </div>
          </div>
        </Modal>
      )}
    </Section>
  )
}


// ── E-firma (Electronic Signature) settings ───────────────────────────────────

const ESIGN_PROVIDERS = [
  {
    id: 'docusign',
    label: 'DocuSign',
    icon: '🖊',
    configKey: 'docusign_configured',
    fields: [
      { key: 'docusign_integration_key', label: 'Integration Key (Client ID)', placeholder: 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx', secret: false },
      { key: 'docusign_account_id',      label: 'Account ID',                  placeholder: 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx', secret: false },
      { key: 'docusign_secret_key',      label: 'Secret Key',                  placeholder: '••••••••••••••••',                     secret: true  },
      { key: 'docusign_base_url',        label: 'Base URL',                    placeholder: 'https://demo.docusign.net/restapi',   secret: false },
    ],
  },
  {
    id: 'adobe',
    label: 'Adobe Sign',
    icon: '📝',
    configKey: 'adobe_configured',
    fields: [
      { key: 'adobe_sign_client_id',     label: 'Client ID',     placeholder: 'CBJCH…',                                         secret: false },
      { key: 'adobe_sign_client_secret', label: 'Client Secret', placeholder: '••••••••••••••••',                               secret: true  },
      { key: 'adobe_sign_base_url',      label: 'Base URL',      placeholder: 'https://api.na1.adobesign.com/api/rest/v6',     secret: false },
    ],
  },
]

function ProviderCard({ provider, config, form, onChange, onSave, isSaving }) {
  const isConfigured = config?.[provider.configKey]
  const handleSubmit = (e) => {
    e.preventDefault()
    onSave(provider)
  }
  return (
    <div style={{ border: `1px solid ${isConfigured ? 'var(--success)' : 'var(--surface-4)'}`, borderRadius: 12, padding: '18px 20px', background: 'var(--surface-2)', marginBottom: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <span style={{ fontSize: 20 }}>{provider.icon}</span>
          <span style={{ fontSize: "var(--text-md)", fontWeight: 700 }}>{provider.label}</span>
        </div>
        <span style={{
          fontSize: "var(--text-xs)", fontWeight: 700, padding: '3px 10px', borderRadius: 20,
          background: isConfigured ? 'var(--success-bg)' : 'var(--surface-4)',
          color: isConfigured ? 'var(--success)' : 'var(--text-3)',
        }}>
          {isConfigured ? '✓ Configurado' : 'No configurado'}
        </span>
      </div>

      <form onSubmit={handleSubmit}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 14 }}>
        {provider.fields.map(f => (
          <div key={f.key}>
            <label style={ls}>{f.label}</label>
            <input
              type={f.secret ? 'password' : 'text'}
              value={form[f.key] ?? ''}
              onChange={e => onChange(f.key, e.target.value)}
              placeholder={f.secret && form[f.key] === '***' ? 'Guardado — introduce para cambiar' : f.placeholder}
              style={fs}
              autoComplete="off"
            />
          </div>
        ))}
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <Button size="sm" type="submit" loading={isSaving}>Guardar {provider.label}</Button>
        </div>
      </form>
    </div>
  )
}

function ESignSettingsSection() {
  const toast = useToast()
  const qc = useQueryClient()

  const { data: config, isLoading } = useQuery({
    queryKey: ['esign-config'],
    queryFn: () => esignApi.getConfig().then(r => r.data),
  })

  const [form, setForm] = useState({})
  React.useEffect(() => {
    if (config) setForm({ ...config })
  }, [config])

  const { mutate: save, isPending: isSaving } = useMutation({
    mutationFn: (data) => esignApi.saveConfig(data),
    onSuccess: () => {
      qc.invalidateQueries(['esign-config'])
      qc.invalidateQueries(['esign-stats'])
      toast.success('Configuración guardada')
    },
    onError: e => toast.error(extractErr(e, 'Error guardando configuración')),
  })

  const handleChange = (key, value) => setForm(f => ({ ...f, [key]: value }))

  const handleSave = (provider) => {
    const payload = {}
    provider.fields.forEach(f => {
      const val = form[f.key]
      if (val !== undefined) payload[f.key] = val
    })
    save(payload)
  }

  return (
    <Section icon="✍" title="Firma Electrónica" description="Configura las credenciales de los proveedores de firma electrónica. Los cambios se aplican inmediatamente.">
      {isLoading ? (
        <Spinner />
      ) : (
        <>
          <div style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 10, padding: '12px 16px', marginBottom: 20 }}>
            <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, marginBottom: 6 }}>Modo manual siempre disponible</div>
            <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>
              Sin credenciales, las solicitudes se gestionan en modo manual: NexusPM registra el estado internamente sin enviar sobres a proveedores externos. Configura DocuSign o Adobe Sign para el flujo completo.
            </div>
          </div>

          <div style={{ marginBottom: 20 }}>
            <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 12 }}>Webhooks de sincronización de estado</div>
            <div style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '10px 14px' }}>
              <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginBottom: 4 }}>Configura en el panel de tu proveedor las siguientes URLs de webhook:</div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: "var(--text-2xs)", color: 'var(--accent)', marginBottom: 2 }}>DocuSign Connect: <span style={{ color: 'var(--text-1)' }}>/api/v1/esign/webhooks/docusign</span></div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: "var(--text-2xs)", color: 'var(--accent)' }}>Adobe Sign: <span style={{ color: 'var(--text-1)' }}>/api/v1/esign/webhooks/adobe</span></div>
            </div>
          </div>

          {ESIGN_PROVIDERS.map(provider => (
            <ProviderCard
              key={provider.id}
              provider={provider}
              config={config}
              form={form}
              onChange={handleChange}
              onSave={handleSave}
              isSaving={isSaving}
            />
          ))}
        </>
      )}
    </Section>
  )
}

// ── Session security ──────────────────────────────────────────────────────────
const IDLE_TIMEOUT_OPTIONS = [5, 10, 15, 30, 60, 120, 240]

function SessionSecuritySection() {
  const qc = useQueryClient()
  const toast = useToast()

  const { data: settings = [] } = useQuery({
    queryKey: ['settings-general'],
    queryFn: () => settingsApi.getGeneral().then(r => r.data),
  })
  const { mutate: update } = useMutation({
    mutationFn: ({ key, value }) => settingsApi.updateSetting(key, value),
    onSuccess: () => qc.invalidateQueries(['settings-general']),
    onError: e => toast.error(extractErr(e, 'Error al guardar')),
  })

  const find = (k) => settings.find(s => s.key === k)?.value
  const idleEnabled = find('idle_timeout_enabled') === 'true'
  const idleMinutes = parseInt(find('idle_timeout_minutes') || '30', 10)

  return (
    <Section icon="🔒" title="Seguridad de sesión" description="Controla el cierre automático por inactividad">
      <div style={{ display: 'flex', flexDirection: 'column', gap: 20, maxWidth: 520 }}>

        {/* Toggle idle timeout */}
        <div style={{
          background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
          borderRadius: 10, padding: '16px 20px',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16,
        }}>
          <div>
            <div style={{ fontWeight: 700, color: 'var(--text-1)', fontSize: 'var(--text-sm)' }}>
              Cierre de sesión por inactividad
            </div>
            <div style={{ color: 'var(--text-3)', fontSize: 'var(--text-xs)', marginTop: 2 }}>
              Cierra la sesión automáticamente si el usuario no tiene actividad
            </div>
          </div>
          <label style={{ position: 'relative', display: 'inline-block', width: 44, height: 24, flexShrink: 0, cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={idleEnabled}
              onChange={e => update({ key: 'idle_timeout_enabled', value: e.target.checked ? 'true' : 'false' })}
              style={{ opacity: 0, width: 0, height: 0 }}
            />
            <span style={{
              position: 'absolute', inset: 0, borderRadius: 24, cursor: 'pointer', transition: '.2s',
              background: idleEnabled ? 'var(--accent)' : 'var(--surface-4)',
            }}>
              <span style={{
                position: 'absolute', left: idleEnabled ? 22 : 2, top: 2,
                width: 20, height: 20, borderRadius: '50%',
                background: 'var(--surface-0)', transition: '.2s',
              }} />
            </span>
          </label>
        </div>

        {/* Timeout duration selector */}
        <div style={{
          background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
          borderRadius: 10, padding: '16px 20px',
          opacity: idleEnabled ? 1 : 0.45,
          pointerEvents: idleEnabled ? 'auto' : 'none',
        }}>
          <label style={ls}>Minutos de inactividad antes de cerrar sesión</label>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 4 }}>
            {IDLE_TIMEOUT_OPTIONS.map(m => (
              <button
                key={m}
                onClick={() => update({ key: 'idle_timeout_minutes', value: String(m) })}
                style={{
                  padding: '6px 16px', borderRadius: 8, cursor: 'pointer',
                  fontWeight: m === idleMinutes ? 700 : 400,
                  fontSize: 'var(--text-sm)',
                  background: m === idleMinutes ? 'var(--accent)' : 'var(--surface-3)',
                  color: m === idleMinutes ? 'var(--surface-0)' : 'var(--text-2)',
                  border: m === idleMinutes ? '1px solid var(--accent)' : '1px solid var(--surface-4)',
                  transition: 'all .15s',
                }}
              >
                {m < 60 ? `${m} min` : `${m / 60}h`}
              </button>
            ))}
          </div>
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', marginTop: 10 }}>
            Se mostrará un aviso 60 segundos antes de cerrar la sesión.
          </div>
        </div>

      </div>
    </Section>
  )
}

export {
  GeneralSection,
  SessionSecuritySection,
  UsersSection,
  RolesSection,
  AlertConfigSection,
  MetricsSection,
  TaskTypesSection,
  TemplatesSection,
  RateTablesSection,
  VacationSection,
  DepartmentsSection,
  OfficesSection,
  NumberingSection,
  CustomFieldsSection,
  IdiomasSection,
  EmailInboundSection,
  LogLevelSection,
  SystemStateSection,
  ESignSettingsSection,
}
