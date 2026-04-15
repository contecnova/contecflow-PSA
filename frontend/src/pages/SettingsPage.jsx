import React, { useEffect, useState } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { settingsApi, advancedConfigApi } from '../services/settingsApi'
import api, { usersApi } from '../services/api'
import { Card, Button, Modal, Spinner, EmptyState } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import { Settings } from 'lucide-react'
import { useAppLang } from '../i18n/AppLangContext'
import { APP_TRANSLATIONS, APP_LANGUAGES, getAllKeys } from '../i18n/appTranslations'
import { PORTAL_TRANSLATIONS, PORTAL_LANGUAGES, getPortalKeys } from '../i18n/portalTranslations'
import { extractErr } from '../utils/helpers'
import { useAuth } from '../context/AuthContext'

const ROLE_LABELS = { admin: 'Dirección', pm: 'Project Manager', team_lead: 'Team Lead', hr: 'RRHH', employee: 'Empleado' }
const ROLE_COLORS = { admin: 'var(--danger)', pm: 'var(--accent)', team_lead: 'var(--purple)', hr: 'var(--success)', employee: 'var(--text-2)' }
const fs = { width: '100%', background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 8, padding: '10px 14px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
const ls = { fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 6 }

function Section({ icon, title, description, children }) {
  return (
    <Card style={{ marginBottom: 24 }}>
      <div style={{ marginBottom: 20 }}>
        <div style={{ fontSize: 16, fontWeight: 700 }}>{icon} {title}</div>
        {description && <div style={{ fontSize: 13, color: 'var(--text-2)', marginTop: 4 }}>{description}</div>}
      </div>
      {children}
    </Card>
  )
}

// ── General settings ──────────────────────────────────────────────────────────
function GeneralSection() {
  const qc = useQueryClient()
  const toast = useToast()
  const { data: settings = [] } = useQuery({ queryKey: ['settings-general'], queryFn: () => settingsApi.getGeneral().then(r => r.data) })
  const { mutate: update } = useMutation({ mutationFn: ({ key, value }) => settingsApi.updateSetting(key, value), onSuccess: () => qc.invalidateQueries(['settings-general']) , onError: e => toast.error(extractErr(e, 'Error'))})
  const LABELS = { company_name: 'Nombre empresa', company_logo_url: 'URL logotipo', currency: 'Moneda', timezone: 'Zona horaria', language: 'Idioma', work_hours_per_day: 'Horas/día', work_days_per_week: 'Días laborables/semana', budget_alert_threshold: '% alerta presupuesto', overload_threshold: '% carga máxima' }
  return (
    <Section icon="⚙️" title="General" description="Parámetros globales de la aplicación">
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
        {settings.map(s => <SettingField key={s.key} setting={s} label={LABELS[s.key] || s.key} onSave={(v) => update({ key: s.key, value: v })} />)}
      </div>
    </Section>
  )
}

function SettingField({ setting, label, onSave }) {
  const [editing, setEditing] = useState(false)
  const [val, setVal] = useState(setting.value || '')
  return (
    <div style={{ background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 10, padding: '12px 16px' }}>
      <label style={ls}>{label}</label>
      {editing ? (
        <div style={{ display: 'flex', gap: 8 }}>
          <input value={val} onChange={e => setVal(e.target.value)} style={{ ...fs, flex: 1 }} autoFocus onKeyDown={e => { if (e.key === 'Enter') { onSave(val); setEditing(false) } if (e.key === 'Escape') { setVal(setting.value); setEditing(false) } }} />
          <button onClick={() => { onSave(val); setEditing(false) }} style={{ background: 'var(--accent)', border: 'none', borderRadius: 6, padding: '0 12px', color: 'var(--surface-0)', cursor: 'pointer', fontWeight: 700 }}>✓</button>
          <button onClick={() => { setVal(setting.value); setEditing(false) }} style={{ background: 'transparent', border: '1px solid #1e2d45', borderRadius: 6, padding: '0 12px', color: 'var(--text-2)', cursor: 'pointer' }}>✕</button>
        </div>
      ) : (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: 14, fontWeight: 600, color: setting.value ? 'var(--text-1)' : 'var(--text-3)' }}>{setting.value || '—'}</span>
          <button onClick={() => setEditing(true)} style={{ background: 'none', border: 'none', color: 'var(--text-2)', cursor: 'pointer', fontSize: 12 }}>✏️</button>
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
  const { data: users = [], isLoading } = useQuery({ queryKey: ['users'], queryFn: () => usersApi.list().then(r => r.data) })
  const { mutate: createUser, isPending: creating } = useMutation({ mutationFn: usersApi.create, onSuccess: () => { qc.invalidateQueries(['users']); setShowCreate(false) } , onError: e => toast.error(extractErr(e, 'Error'))})
  const { mutate: updateUser, isPending: updating } = useMutation({ mutationFn: ({ id, data }) => usersApi.update(id, data), onSuccess: () => { qc.invalidateQueries(['users']); setEditUser(null) } , onError: e => toast.error(extractErr(e, 'Error'))})
  const { mutate: deactivate } = useMutation({ mutationFn: usersApi.deactivate, onSuccess: () => qc.invalidateQueries(['users']) , onError: e => toast.error(extractErr(e, 'Error'))})
  const { mutate: deletePermanent } = useMutation({ mutationFn: usersApi.deletePermanent, onSuccess: () => { qc.invalidateQueries(['users']); qc.invalidateQueries(['users-settings']); qc.invalidateQueries(['resources']); } , onError: e => toast.error(extractErr(e, 'Error'))})
  const filtered = users.filter(u => !search || u.full_name?.toLowerCase().includes(search.toLowerCase()) || u.username?.toLowerCase().includes(search.toLowerCase()))
  return (
    <Section icon="👤" title="Usuarios" description="Gestión de accesos, roles y capacidad">
      <div style={{ display: 'flex', gap: 12, marginBottom: 16 }}>
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="🔍 Buscar..." style={{ ...fs, flex: 1 }} />
        <Button onClick={() => setShowCreate(true)} icon="＋">Nuevo usuario</Button>
      </div>
      {isLoading ? <Spinner /> : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {filtered.map(u => (
            <div key={u.id} style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '10px 14px', background: 'var(--surface-2)', border: `1px solid ${u.is_active ? 'var(--surface-4)' : 'var(--danger-border)'}`, borderRadius: 10, opacity: u.is_active ? 1 : 0.6 }}>
              <div style={{ width: 34, height: 34, borderRadius: '50%', background: `linear-gradient(135deg, ${ROLE_COLORS[u.role] || 'var(--text-2)'}, #0a0e1a)`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, fontWeight: 700, flexShrink: 0 }}>
                {u.full_name?.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()}
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 13, fontWeight: 600 }}>{u.full_name}</div>
                <div style={{ fontSize: 11, color: 'var(--text-2)' }}>{u.username} · {u.email}</div>
              </div>
              <span style={{ fontSize: 11, background: `${ROLE_COLORS[u.role]}15`, color: ROLE_COLORS[u.role], border: `1px solid ${ROLE_COLORS[u.role]}30`, borderRadius: 20, padding: '2px 8px', fontWeight: 700 }}>{ROLE_LABELS[u.role] || u.role}</span>
              {u.department && <span style={{ fontSize: 11, color: 'var(--text-2)' }}>{u.department}</span>}
              {!u.is_active && <span style={{ fontSize: 11, color: 'var(--danger)' }}>Inactivo</span>}
              <button onClick={() => setEditUser(u)} style={{ background: 'none', border: '1px solid #1e2d45', borderRadius: 6, padding: '3px 8px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 11 }}>✏️ Editar</button>
              {u.is_active ? <button onClick={() => openConfirmGlobal({ message: `¿Desactivar a "${u.full_name}"?`, onConfirm: () => deactivate(u.id) })} style={{ background: 'none', border: '1px solid #ffb80030', borderRadius: 6, padding: '3px 8px', color: 'var(--warning)', cursor: 'pointer', fontSize: 11 }}>⏸ Desactivar</button>
                : <button onClick={() => deactivate(u.id)} style={{ background: 'none', border: '1px solid #00e5a030', borderRadius: 6, padding: '3px 8px', color: 'var(--success)', cursor: 'pointer', fontSize: 11 }}>▶ Activar</button>}
              <button onClick={() => openConfirmGlobal({ title: '⚠️ Eliminar permanentemente', message: `¿Eliminar permanentemente a "${u.full_name}"? Esta acción no se puede deshacer.`, onConfirm: () => deletePermanent(u.id), danger: true })} style={{ background: 'none', border: '1px solid #ff475730', borderRadius: 6, padding: '3px 8px', color: 'var(--danger)', cursor: 'pointer', fontSize: 11 }}>🗑 Eliminar</button>
            </div>
          ))}
        </div>
      )}
      <UserFormModal open={showCreate} onClose={() => setShowCreate(false)} onSave={createUser} isPending={creating} />
      {editUser && <UserFormModal open user={editUser} onClose={() => setEditUser(null)} onSave={(data) => updateUser({ id: editUser.id, data })} isPending={updating} />}
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

function UserFormModal({ open, onClose, user, onSave, isPending }) {
  const isEdit = !!user
  const [form, setForm] = useState({ username: user?.username || '', email: user?.email || '', full_name: user?.full_name || '', role: user?.role || 'employee', department: user?.department || '', job_title: user?.job_title || '', weekly_capacity_hours: user?.weekly_capacity_hours || 40, hourly_rate: user?.hourly_rate || '', timezone: user?.timezone || '', password: '' })
  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.value }))
  return (
    <Modal open={open} onClose={onClose} title={isEdit ? `Editar — ${user.full_name}` : 'Nuevo Usuario'} width={580}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
        <div style={{ gridColumn: '1/-1' }}><label style={ls}>Nombre completo *</label><input value={form.full_name} onChange={set('full_name')} style={fs} /></div>
        <div><label style={ls}>Usuario *</label><input value={form.username} onChange={set('username')} style={fs} /></div>
        <div><label style={ls}>Email *</label><input type="email" value={form.email} onChange={set('email')} style={fs} /></div>
        <div><label style={ls}>Rol</label><select value={form.role} onChange={set('role')} style={fs}>{Object.entries(ROLE_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></div>
        <div><label style={ls}>Departamento</label><input value={form.department} onChange={set('department')} style={fs} /></div>
        <div><label style={ls}>Cargo</label><input value={form.job_title} onChange={set('job_title')} style={fs} /></div>
        <div><label style={ls}>Horas semanales</label><input type="number" value={form.weekly_capacity_hours} onChange={set('weekly_capacity_hours')} style={fs} /></div>
        <div><label style={ls}>Tarifa €/hora</label><input type="number" value={form.hourly_rate} onChange={set('hourly_rate')} style={fs} /></div>
        <div style={{ gridColumn: '1/-1' }}>
          <label style={ls}>Zona horaria</label>
          <select value={form.timezone} onChange={set('timezone')} style={fs}>
            <option value="">— Usa la zona de la organización —</option>
            {COMMON_TIMEZONES.map(tz => <option key={tz} value={tz}>{tz}</option>)}
          </select>
        </div>
        {!isEdit && <div style={{ gridColumn: '1/-1' }}><label style={ls}>Contraseña *</label><input type="password" value={form.password} onChange={set('password')} style={fs} /></div>}
        <div style={{ gridColumn: '1/-1', display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 8 }}>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={() => onSave(form)} disabled={isPending || !form.full_name || !form.username || !form.email || (!isEdit && !form.password)}>
            {isPending ? 'Guardando...' : isEdit ? 'Guardar' : 'Crear'}
          </Button>
        </div>
      </div>
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
  const { mutate: deleteRole } = useMutation({ mutationFn: advancedConfigApi.deleteRole, onSuccess: () => qc.invalidateQueries(['custom-roles']) , onError: e => toast.error(extractErr(e, 'Error'))})

  return (
    <Section icon="🔐" title="Roles y Permisos" description="Gestión de roles con control de acceso por módulo">
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {isLoading ? <Spinner /> : roles.map(r => (
          <div key={r.id} style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '12px 16px', background: 'var(--surface-2)', border: `1px solid ${r.color}30`, borderRadius: 10 }}>
            <div style={{ width: 10, height: 10, borderRadius: '50%', background: r.color, flexShrink: 0 }} />
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 13, fontWeight: 700 }}>{r.name}</div>
              {r.description && <div style={{ fontSize: 12, color: 'var(--text-2)' }}>{r.description}</div>}
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 6 }}>
                {Object.entries(r.module_access || {}).filter(([, v]) => v).slice(0, 8).map(([m]) => (
                  <span key={m} style={{ fontSize: 9, background: 'var(--surface-3)', color: 'var(--text-2)', borderRadius: 4, padding: '1px 6px' }}>{m}</span>
                ))}
                {Object.values(r.module_access || {}).filter(Boolean).length > 8 && <span style={{ fontSize: 9, color: 'var(--text-2)' }}>+{Object.values(r.module_access || {}).filter(Boolean).length - 8}</span>}
              </div>
            </div>
            {r.is_system && <span style={{ fontSize: 10, color: 'var(--text-2)', background: 'var(--surface-3)', borderRadius: 20, padding: '2px 8px' }}>Sistema</span>}
            <button onClick={() => setEditRole(r)} style={{ background: 'none', border: '1px solid #1e2d45', borderRadius: 6, padding: '3px 8px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 11 }}>✏️ Editar</button>
            {!r.is_system && <button onClick={() => deleteRole(r.id)} style={{ background: 'none', border: '1px solid #ff475730', borderRadius: 6, padding: '3px 8px', color: 'var(--danger)', cursor: 'pointer', fontSize: 11 }}>🗑</button>}
          </div>
        ))}
        <button onClick={() => setShowCreate(true)} style={{ padding: '10px', border: '1px dashed #1e2d45', borderRadius: 10, background: 'transparent', color: 'var(--text-2)', fontSize: 13, cursor: 'pointer', fontFamily: 'inherit', textAlign: 'center' }}>＋ Crear rol personalizado</button>
      </div>
      {(showCreate || editRole) && (
        <RoleFormModal role={editRole} modules={modules} onClose={() => { setShowCreate(false); setEditRole(null) }}
          onSave={(data) => { const fn = editRole ? () => advancedConfigApi.updateRole(editRole.id, data) : () => advancedConfigApi.createRole(data); fn().then(() => { qc.invalidateQueries(['custom-roles']); setShowCreate(false); setEditRole(null) }) }} />
      )}
    </Section>
  )
}

function RoleFormModal({ role, modules, onClose, onSave }) {
  const [form, setForm] = useState({ name: role?.name || '', description: role?.description || '', color: role?.color || 'var(--text-2)', module_access: role?.module_access || {} })
  const toggleModule = (m) => setForm(f => ({ ...f, module_access: { ...f.module_access, [m]: !f.module_access[m] } }))
  const allOn = modules.every(m => form.module_access[m.id])
  return (
    <Modal open title={role ? `Editar rol — ${role.name}` : 'Nuevo rol'} onClose={onClose} width={560}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 12 }}>
          <div><label style={ls}>Nombre *</label><input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} style={fs} disabled={role?.is_system} /></div>
          <div><label style={ls}>Color</label><div style={{ display: 'flex', gap: 8 }}><input type="color" value={form.color} onChange={e => setForm(f => ({ ...f, color: e.target.value }))} style={{ width: 40, height: 38, border: 'none', background: 'transparent', cursor: 'pointer' }} /><input value={form.color} onChange={e => setForm(f => ({ ...f, color: e.target.value }))} style={{ ...fs, flex: 1 }} /></div></div>
        </div>
        <div><label style={ls}>Descripción</label><input value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} style={fs} /></div>
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
            <label style={ls}>Módulos accesibles</label>
            <button onClick={() => setForm(f => ({ ...f, module_access: modules.reduce((a, m) => ({ ...a, [m.id]: !allOn }), {}) }))} style={{ background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}>
              {allOn ? 'Desactivar todos' : 'Activar todos'}
            </button>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6 }}>
            {modules.map(m => (
              <label key={m.id} style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', padding: '6px 10px', background: form.module_access[m.id] ? 'var(--accent-muted)' : 'var(--surface-3)', borderRadius: 6, border: `1px solid ${form.module_access[m.id] ? 'var(--accent-glow)' : 'var(--surface-4)'}`, fontSize: 12 }}>
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
function AlertConfigSection() {
  const toast = useToast()
  const qc = useQueryClient()
  const { data: configs = [], isLoading } = useQuery({ queryKey: ['alert-configs'], queryFn: () => advancedConfigApi.getAlertConfigs().then(r => r.data) })
  const { mutate: update } = useMutation({ mutationFn: ({ type, data }) => advancedConfigApi.updateAlertConfig(type, data), onSuccess: () => qc.invalidateQueries(['alert-configs']) , onError: e => toast.error(extractErr(e, 'Error'))})
  const SEV_CFG = { info: 'var(--accent)', warning: 'var(--warning)', critical: 'var(--danger)' }
  return (
    <Section icon="🔔" title="Configuración de Alertas" description="Umbrales y destinatarios de cada tipo de alerta">
      {isLoading ? <Spinner /> : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {configs.map(cfg => (
            <div key={cfg.alert_type} style={{ padding: '14px 16px', background: 'var(--surface-2)', border: `1px solid ${cfg.is_enabled ? SEV_CFG[cfg.severity] + '30' : 'var(--surface-4)'}`, borderRadius: 10, opacity: cfg.is_enabled ? 1 : 0.6 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 }}>
                <div>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 3 }}>
                    <span style={{ fontSize: 13, fontWeight: 700 }}>{cfg.label}</span>
                    <span style={{ fontSize: 10, fontWeight: 700, color: SEV_CFG[cfg.severity], background: SEV_CFG[cfg.severity] + '20', borderRadius: 20, padding: '1px 7px', textTransform: 'uppercase' }}>{cfg.severity}</span>
                  </div>
                  {cfg.description && <div style={{ fontSize: 12, color: 'var(--text-2)' }}>{cfg.description}</div>}
                </div>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                  <input type="checkbox" checked={cfg.is_enabled} onChange={e => update({ type: cfg.alert_type, data: { is_enabled: e.target.checked } })} />
                  <span style={{ fontSize: 12, color: 'var(--text-2)' }}>{cfg.is_enabled ? 'Activa' : 'Inactiva'}</span>
                </label>
              </div>
              {cfg.is_enabled && (
                <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', alignItems: 'center' }}>
                  {cfg.threshold_value !== null && (
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                      <label style={{ fontSize: 11, color: 'var(--text-2)' }}>Umbral:</label>
                      <input type="number" defaultValue={cfg.threshold_value} onBlur={e => update({ type: cfg.alert_type, data: { threshold_value: +e.target.value } })}
                        style={{ width: 70, background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 6, padding: '4px 8px', color: 'var(--text-1)', fontSize: 12, outline: 'none', fontFamily: 'inherit', textAlign: 'center' }} />
                      <span style={{ fontSize: 11, color: 'var(--text-2)' }}>{cfg.threshold_unit}</span>
                    </div>
                  )}
                  <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                    {[['notify_admin', 'Admin'], ['notify_pm', 'PM'], ['notify_hr', 'RRHH'], ['notify_employee', 'Empleado'], ['notify_email', '📧 Email']].map(([key, label]) => (
                      <label key={key} style={{ display: 'flex', alignItems: 'center', gap: 5, cursor: 'pointer', fontSize: 11, color: cfg[key] ? 'var(--text-1)' : 'var(--text-2)' }}>
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
    </Section>
  )
}

// ── Rate tables section ───────────────────────────────────────────────────────
function RateTablesSection() {
  const toast = useToast()
  const qc = useQueryClient()
  const { data: tables = [], isLoading } = useQuery({ queryKey: ['rate-tables'], queryFn: () => advancedConfigApi.getRateTables().then(r => r.data) })
  const { mutate: createTable } = useMutation({ mutationFn: advancedConfigApi.createRateTable, onSuccess: () => qc.invalidateQueries(['rate-tables']) , onError: e => toast.error(extractErr(e, 'Error'))})
  const { mutate: deleteTable } = useMutation({ mutationFn: advancedConfigApi.deleteRateTable, onSuccess: () => qc.invalidateQueries(['rate-tables']) , onError: e => toast.error(extractErr(e, 'Error'))})
  const { mutate: addEntry } = useMutation({ mutationFn: ({ tableId, data }) => advancedConfigApi.addRateEntry(tableId, data), onSuccess: () => qc.invalidateQueries(['rate-tables']) , onError: e => toast.error(extractErr(e, 'Error'))})
  const { mutate: deleteEntry } = useMutation({ mutationFn: ({ tableId, entryId }) => advancedConfigApi.deleteRateEntry(tableId, entryId), onSuccess: () => qc.invalidateQueries(['rate-tables']), onError: e => toast.error(extractErr(e, 'Error')) })
  const { mutate: updateEntry } = useMutation({ mutationFn: ({ tableId, entryId, data }) => advancedConfigApi.updateRateEntry(tableId, entryId, data), onSuccess: () => { qc.invalidateQueries(['rate-tables']); setEditingEntryId(null) }, onError: e => toast.error(extractErr(e, 'Error')) })
  const [editingEntryId, setEditingEntryId] = useState(null)
  const [editEntryForm, setEditEntryForm] = useState({ label: '', cost_rate: '', billing_rate: '' })
  const [newTable, setNewTable] = useState({ name: '', applies_to: 'role', is_default: false })
  const [addingEntry, setAddingEntry] = useState(null)
  const [entryForm, setEntryForm] = useState({ label: '', cost_rate: '', billing_rate: '' })

  return (
    <Section icon="💶" title="Tablas de Tarifas" description="Tarifas de coste y facturación por rol, departamento o cliente">
      {isLoading ? <Spinner /> : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {tables.map(t => (
            <div key={t.id} style={{ background: 'var(--surface-2)', border: `1px solid ${t.is_default ? 'var(--accent-glow)' : 'var(--surface-4)'}`, borderRadius: 12, padding: 16 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                <div>
                  <span style={{ fontSize: 14, fontWeight: 700 }}>{t.name}</span>
                  {t.is_default && <span style={{ fontSize: 10, background: 'var(--accent-muted)', color: 'var(--accent)', borderRadius: 20, padding: '1px 8px', marginLeft: 8 }}>Por defecto</span>}
                  <span style={{ fontSize: 11, color: 'var(--text-2)', marginLeft: 8 }}>{t.applies_to === 'role' ? 'Por rol' : t.applies_to === 'department' ? 'Por departamento' : 'Por cliente'}</span>
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <button onClick={() => setAddingEntry(t.id)} style={{ background: 'var(--accent-muted)', border: '1px solid #00d4ff30', borderRadius: 6, padding: '4px 10px', color: 'var(--accent)', cursor: 'pointer', fontSize: 11, fontFamily: 'inherit' }}>＋ Tarifa</button>
                  <button onClick={() => deleteTable(t.id)} style={{ background: 'none', border: '1px solid #ff475730', borderRadius: 6, padding: '4px 10px', color: 'var(--danger)', cursor: 'pointer', fontSize: 11 }}>🗑</button>
                </div>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 30px', gap: 8 }}>
                <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', padding: '0 8px' }}>Etiqueta</div>
                <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', textAlign: 'center' }}>Coste €/h</div>
                <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', textAlign: 'center' }}>Factura €/h</div>
                <div></div>
                {(t.entries || []).map(e => (
                  editingEntryId === e.id ? (
                    <React.Fragment key={e.id}>
                      <input value={editEntryForm.label} onChange={ev => setEditEntryForm(f=>({...f,label:ev.target.value}))} style={{...fs,padding:'5px 8px'}} autoFocus />
                      <input type="number" value={editEntryForm.cost_rate} onChange={ev => setEditEntryForm(f=>({...f,cost_rate:ev.target.value}))} style={{...fs,padding:'5px 8px'}} placeholder="€/h" />
                      <input type="number" value={editEntryForm.billing_rate} onChange={ev => setEditEntryForm(f=>({...f,billing_rate:ev.target.value}))} style={{...fs,padding:'5px 8px'}} placeholder="€/h" />
                      <div style={{display:'flex',gap:4}}>
                        <button onClick={() => updateEntry({ tableId: t.id, entryId: e.id, data: editEntryForm })} disabled={!editEntryForm.label} style={{background:'var(--accent)',border:'none',borderRadius:5,padding:'4px 8px',color:'#fff',cursor:'pointer',fontSize:12}}>✓</button>
                        <button onClick={() => setEditingEntryId(null)} style={{background:'none',border:'1px solid var(--surface-4)',borderRadius:5,padding:'4px 7px',color:'var(--text-2)',cursor:'pointer',fontSize:12}}>✕</button>
                      </div>
                    </React.Fragment>
                  ) : (
                    <React.Fragment key={e.id}>
                      <div style={{ padding: '6px 8px', background: 'var(--surface-3)', borderRadius: 6, fontSize: 13 }}>{e.label}</div>
                      <div style={{ padding: '6px 8px', background: 'var(--surface-3)', borderRadius: 6, fontSize: 13, textAlign: 'center', fontFamily: "'Space Mono', monospace", color: 'var(--warning)' }}>{e.cost_rate ? `${e.cost_rate}€` : '—'}</div>
                      <div style={{ padding: '6px 8px', background: 'var(--surface-3)', borderRadius: 6, fontSize: 13, textAlign: 'center', fontFamily: "'Space Mono', monospace", color: 'var(--success)' }}>{e.billing_rate ? `${e.billing_rate}€` : '—'}</div>
                      <div style={{display:'flex',gap:3}}>
                        <button onClick={() => { setEditingEntryId(e.id); setEditEntryForm({ label: e.label, cost_rate: e.cost_rate||'', billing_rate: e.billing_rate||'' }) }} style={{ background: 'none', border: 'none', color: 'var(--text-3)', cursor: 'pointer', fontSize: 12 }}>✏</button>
                        <button onClick={() => deleteEntry({ tableId: t.id, entryId: e.id })} style={{ background: 'none', border: 'none', color: 'var(--danger)', cursor: 'pointer', fontSize: 14 }}>×</button>
                      </div>
                    </React.Fragment>
                  )
                ))}
              </div>
              {addingEntry === t.id && (
                <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr auto', gap: 8, marginTop: 8, padding: '10px', background: 'var(--accent-muted)', border: '1px dashed #00d4ff30', borderRadius: 8 }}>
                  <input value={entryForm.label} onChange={e => setEntryForm(f => ({ ...f, label: e.target.value }))} style={{ ...fs }} placeholder="Ej: Senior Developer" />
                  <input type="number" value={entryForm.cost_rate} onChange={e => setEntryForm(f => ({ ...f, cost_rate: e.target.value }))} style={fs} placeholder="€/h coste" />
                  <input type="number" value={entryForm.billing_rate} onChange={e => setEntryForm(f => ({ ...f, billing_rate: e.target.value }))} style={fs} placeholder="€/h factura" />
                  <div style={{ display: 'flex', gap: 6 }}>
                    <Button size="sm" onClick={() => { addEntry({ tableId: t.id, data: entryForm }); setEntryForm({ label: '', cost_rate: '', billing_rate: '' }); setAddingEntry(null) }} disabled={!entryForm.label}>Añadir</Button>
                    <Button size="sm" variant="secondary" onClick={() => setAddingEntry(null)}>×</Button>
                  </div>
                </div>
              )}
            </div>
          ))}
          <div style={{ display: 'flex', gap: 10, padding: '12px 16px', background: 'var(--accent-muted)', border: '1px dashed #00d4ff30', borderRadius: 10, alignItems: 'flex-end' }}>
            <div style={{ flex: 2 }}><label style={ls}>Nombre tabla</label><input value={newTable.name} onChange={e => setNewTable(f => ({ ...f, name: e.target.value }))} style={fs} placeholder="Tarifas 2026" /></div>
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
  const { mutate: createPolicy } = useMutation({ mutationFn: advancedConfigApi.createVacationPolicy, onSuccess: () => qc.invalidateQueries(['vacation-policies']) , onError: e => toast.error(extractErr(e, 'Error'))})
  const { mutate: deletePolicy } = useMutation({ mutationFn: advancedConfigApi.deleteVacationPolicy, onSuccess: () => qc.invalidateQueries(['vacation-policies']) , onError: e => toast.error(extractErr(e, 'Error'))})
  const { mutate: updateBalance } = useMutation({ mutationFn: ({ userId, days }) => advancedConfigApi.updateVacationBalance(userId, year, days), onSuccess: () => { qc.invalidateQueries(['vacation-balances', year]); qc.invalidateQueries(['vacation-balance-my']); } , onError: e => toast.error(extractErr(e, 'Error'))})
  const [newPolicy, setNewPolicy] = useState({ name: '', days_per_year: 23, carries_over: true, max_carryover_days: 5, is_default: false })

  return (
    <Section icon="🏖️" title="Política de Vacaciones" description="Días anuales, acumulación y saldos del equipo">
      <div style={{ marginBottom: 20 }}>
        <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 12 }}>Políticas configuradas</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {policies.map(p => (
            <div key={p.id} style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '10px 14px', background: 'var(--surface-2)', border: `1px solid ${p.is_default ? 'var(--accent-glow)' : 'var(--surface-4)'}`, borderRadius: 10 }}>
              <div style={{ flex: 1 }}>
                <span style={{ fontSize: 13, fontWeight: 700 }}>{p.name}</span>
                {p.is_default && <span style={{ fontSize: 10, background: 'var(--accent-muted)', color: 'var(--accent)', borderRadius: 20, padding: '1px 8px', marginLeft: 8 }}>Por defecto</span>}
                <div style={{ fontSize: 12, color: 'var(--text-2)', marginTop: 2 }}>
                  {p.days_per_year} días/año {p.carries_over ? `· Acumula hasta ${p.max_carryover_days || '∞'} días` : '· No acumula'}
                </div>
              </div>
              <button onClick={() => deletePolicy(p.id)} style={{ background: 'none', border: '1px solid #ff475730', borderRadius: 6, padding: '3px 8px', color: 'var(--danger)', cursor: 'pointer', fontSize: 11 }}>🗑</button>
            </div>
          ))}
        </div>
        <div style={{ display: 'flex', gap: 10, marginTop: 12, padding: '10px 14px', background: 'var(--accent-muted)', border: '1px dashed #00d4ff30', borderRadius: 10, flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <div style={{ flex: 2 }}><label style={ls}>Nombre</label><input value={newPolicy.name} onChange={e => setNewPolicy(f => ({ ...f, name: e.target.value }))} style={fs} placeholder="Política general" /></div>
          <div style={{ flex: 1 }}><label style={ls}>Días/año</label><input type="number" value={newPolicy.days_per_year} onChange={e => setNewPolicy(f => ({ ...f, days_per_year: +e.target.value }))} style={fs} /></div>
          <div style={{ flex: 1 }}><label style={ls}>Máx. acumulación</label><input type="number" value={newPolicy.max_carryover_days} onChange={e => setNewPolicy(f => ({ ...f, max_carryover_days: +e.target.value }))} style={fs} /></div>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 12 }}><input type="checkbox" checked={newPolicy.is_default} onChange={e => setNewPolicy(f => ({ ...f, is_default: e.target.checked }))} />Por defecto</label>
          <Button onClick={() => { createPolicy(newPolicy); setNewPolicy({ name: '', days_per_year: 23, carries_over: true, max_carryover_days: 5, is_default: false }) }} disabled={!newPolicy.name}>Crear</Button>
        </div>
      </div>

      {/* Balances */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <div style={{ fontSize: 13, fontWeight: 700 }}>Saldos del equipo</div>
          <select value={year} onChange={e => setYear(+e.target.value)} style={{ background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 8, padding: '6px 12px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit' }}>
            {[currentYear - 1, currentYear, currentYear + 1].map(y => <option key={y} value={y}>{y}</option>)}
          </select>
        </div>
        <div style={{ background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 12, overflow: 'hidden' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr 1fr 80px', gap: 12, padding: '8px 16px', borderBottom: '1px solid #1e2d45', fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            <span>Persona</span><span>Asignados</span><span>Tomados</span><span>Pendientes</span><span>Disponibles</span><span>Editar</span>
          </div>
          {balances.map(b => (
            <div key={b.user_id} style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr 1fr 80px', gap: 12, padding: '10px 16px', borderBottom: '1px solid #1e2d4530', alignItems: 'center' }}>
              <div>
                <div style={{ fontSize: 13, fontWeight: 600 }}>{b.user_name}</div>
                {b.department && <div style={{ fontSize: 11, color: 'var(--text-2)' }}>{b.department}</div>}
              </div>
              <span style={{ fontSize: 13, fontFamily: "'Space Mono', monospace" }}>{b.days_entitled}d</span>
              <span style={{ fontSize: 13, fontFamily: "'Space Mono', monospace", color: 'var(--accent)' }}>{b.days_taken}d</span>
              <span style={{ fontSize: 13, fontFamily: "'Space Mono', monospace", color: 'var(--warning)' }}>{b.days_pending}d</span>
              <span style={{ fontSize: 13, fontFamily: "'Space Mono', monospace", color: b.days_remaining <= 0 ? 'var(--danger)' : 'var(--success)', fontWeight: 700 }}>{b.days_remaining}d</span>
              <input type="number" defaultValue={b.days_entitled} min="0" max="60" onBlur={e => updateBalance({ userId: b.user_id, days: +e.target.value })}
                style={{ background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 6, padding: '4px 8px', color: 'var(--text-1)', fontSize: 12, outline: 'none', fontFamily: 'inherit', width: '100%', textAlign: 'center' }} />
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
  const { mutate: update } = useMutation({ mutationFn: ({ entity, data }) => advancedConfigApi.updateNumbering(entity, data), onSuccess: () => qc.invalidateQueries(['numbering-seqs']) , onError: e => toast.error(extractErr(e, 'Error'))})
  const { mutate: reset } = useMutation({ mutationFn: advancedConfigApi.resetNumbering, onSuccess: () => qc.invalidateQueries(['numbering-seqs']) , onError: e => toast.error(extractErr(e, 'Error'))})
  const ENTITY_LABELS = { project: 'Proyecto', task: 'Tarea', contract: 'Contrato', opportunity: 'Oportunidad', change_request: 'Control de cambios', deliverable: 'Entregable', risk: 'Riesgo' }

  return (
    <Section icon="🔢" title="Numeración Automática" description="Formato de los códigos generados automáticamente">
      {isLoading ? <Spinner /> : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {seqs.map(s => (
            <div key={s.entity} style={{ display: 'flex', gap: 14, alignItems: 'flex-end', padding: '12px 16px', background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 10 }}>
              <div style={{ width: 120, flexShrink: 0 }}>
                <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-1)' }}>{ENTITY_LABELS[s.entity] || s.entity}</div>
                <div style={{ fontSize: 11, color: 'var(--accent)', fontFamily: "'Space Mono', monospace", marginTop: 4 }}>{s.next_preview}</div>
              </div>
              <div style={{ display: 'flex', gap: 8, flex: 1, flexWrap: 'wrap', alignItems: 'flex-end' }}>
                <div><label style={{ ...ls, fontSize: 10 }}>Prefijo</label><input defaultValue={s.prefix} onBlur={e => update({ entity: s.entity, data: { ...s, prefix: e.target.value } })} style={{ ...fs, width: 70 }} placeholder="PRJ" /></div>
                <div><label style={{ ...ls, fontSize: 10 }}>Sep.</label><input defaultValue={s.separator} onBlur={e => update({ entity: s.entity, data: { ...s, separator: e.target.value } })} style={{ ...fs, width: 40 }} /></div>
                <div><label style={{ ...ls, fontSize: 10 }}>Dígitos</label><input type="number" min="1" max="8" defaultValue={s.padding} onBlur={e => update({ entity: s.entity, data: { ...s, padding: +e.target.value } })} style={{ ...fs, width: 60 }} /></div>
                <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', fontSize: 12, color: 'var(--text-2)', paddingBottom: 4 }}>
                  <input type="checkbox" defaultChecked={s.include_year} onChange={e => update({ entity: s.entity, data: { ...s, include_year: e.target.checked } })} />
                  Incluir año
                </label>
              </div>
              <div style={{ flexShrink: 0 }}>
                <div style={{ fontSize: 11, color: 'var(--text-2)', marginBottom: 4 }}>Contador: {s.current_value}</div>
                <button onClick={() => { openConfirmGlobal({ message: `¿Resetear contador de ${ENTITY_LABELS[s.entity] || s.entity} a 0?`, onConfirm: () => reset(s.entity), danger: true }) }} style={{ background: 'none', border: '1px solid #ff475730', borderRadius: 6, padding: '4px 10px', color: 'var(--danger)', cursor: 'pointer', fontSize: 11, fontFamily: 'inherit' }}>Resetear</button>
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
  const toast = useToast()
  const qc = useQueryClient()
  const { data: fields = [], isLoading } = useQuery({ queryKey: ['custom-fields'], queryFn: () => advancedConfigApi.getCustomFields().then(r => r.data) })
  const { mutate: createField } = useMutation({ mutationFn: advancedConfigApi.createCustomField, onSuccess: () => qc.invalidateQueries(['custom-fields']), onError: e => toast.error(extractErr(e, 'Error')) })
  const { mutate: updateField } = useMutation({ mutationFn: ({ id, data }) => advancedConfigApi.updateCustomField(id, data), onSuccess: () => { qc.invalidateQueries(['custom-fields']); setEditingFieldId(null) }, onError: e => toast.error(extractErr(e, 'Error')) })
  const { mutate: deleteField } = useMutation({ mutationFn: advancedConfigApi.deleteCustomField, onSuccess: () => qc.invalidateQueries(['custom-fields']), onError: e => toast.error(extractErr(e, 'Error')) })
  const [editingFieldId, setEditingFieldId] = useState(null)
  const [editFieldForm, setEditFieldForm] = useState({ name: '', is_required: false, placeholder: '' })
  const [form, setForm] = useState({ entity: 'project', name: '', field_key: '', field_type: 'text', is_required: false, placeholder: '' })
  const ENTITIES = [{ value: 'project', label: 'Proyecto' }, { value: 'task', label: 'Tarea' }, { value: 'user', label: 'Usuario' }]
  const TYPES = [{ value: 'text', label: 'Texto' }, { value: 'number', label: 'Número' }, { value: 'date', label: 'Fecha' }, { value: 'select', label: 'Selector' }, { value: 'boolean', label: 'Sí/No' }, { value: 'url', label: 'URL' }]
  const TYPE_ICONS = { text: '📝', number: '🔢', date: '📅', select: '📋', boolean: '☑️', url: '🔗' }
  const byEntity = fields.reduce((a, f) => { if (!a[f.entity]) a[f.entity] = []; a[f.entity].push(f); return a }, {})

  return (
    <Section icon="🧩" title="Campos Personalizados" description="Añade campos adicionales a proyectos, tareas y usuarios">
      {isLoading ? <Spinner /> : (
        <div style={{ marginBottom: 20 }}>
          {Object.entries(byEntity).map(([entity, entityFields]) => (
            <div key={entity} style={{ marginBottom: 16 }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>
                {ENTITIES.find(e => e.value === entity)?.label || entity}
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {entityFields.map(f => (
                  <React.Fragment key={f.id}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '8px 12px', background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 8 }}>
                      <span style={{ fontSize: 16 }}>{TYPE_ICONS[f.field_type] || '📝'}</span>
                      <div style={{ flex: 1 }}>
                        <span style={{ fontSize: 13, fontWeight: 600 }}>{f.name}</span>
                        <span style={{ fontSize: 11, color: 'var(--text-2)', marginLeft: 8, fontFamily: "'Space Mono', monospace" }}>{f.field_key}</span>
                        {f.is_required && <span style={{ fontSize: 10, color: 'var(--danger)', marginLeft: 8 }}>*obligatorio</span>}
                      </div>
                      <span style={{ fontSize: 11, color: 'var(--text-2)' }}>{TYPES.find(t => t.value === f.field_type)?.label}</span>
                      <button onClick={() => { setEditingFieldId(f.id); setEditFieldForm({ name: f.name, is_required: f.is_required, placeholder: f.placeholder||'' }) }}
                        style={{ background: 'none', border: '1px solid #1e2d45', borderRadius: 6, padding: '3px 8px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 11 }}>✏</button>
                      <button onClick={() => deleteField(f.id)} style={{ background: 'none', border: '1px solid #ff475730', borderRadius: 6, padding: '3px 8px', color: 'var(--danger)', cursor: 'pointer', fontSize: 11 }}>🗑</button>
                    </div>
                    {editingFieldId === f.id && (
                      <div style={{ display:'flex', gap:8, padding:'10px', background:'var(--accent-muted)',
                        border:'1px solid var(--accent-glow)', borderRadius:8, marginTop:-4, alignItems:'center' }}>
                        <input value={editFieldForm.name} onChange={e=>setEditFieldForm(f=>({...f,name:e.target.value}))}
                          style={{...fs,flex:2}} placeholder="Nombre del campo" autoFocus />
                        <input value={editFieldForm.placeholder} onChange={e=>setEditFieldForm(f=>({...f,placeholder:e.target.value}))}
                          style={{...fs,flex:2}} placeholder="Placeholder" />
                        <label style={{display:'flex',alignItems:'center',gap:5,cursor:'pointer',fontSize:12,whiteSpace:'nowrap'}}>
                          <input type="checkbox" checked={editFieldForm.is_required}
                            onChange={e=>setEditFieldForm(f=>({...f,is_required:e.target.checked}))} />Obligatorio
                        </label>
                        <button onClick={() => updateField({ id: f.id, data: editFieldForm })} disabled={!editFieldForm.name}
                          style={{background:'var(--accent)',border:'none',borderRadius:6,padding:'5px 12px',color:'#fff',cursor:'pointer',fontSize:12,fontFamily:'inherit'}}>✓ Guardar</button>
                        <button onClick={() => setEditingFieldId(null)}
                          style={{background:'none',border:'1px solid var(--surface-4)',borderRadius:6,padding:'5px 9px',color:'var(--text-2)',cursor:'pointer',fontSize:12}}>✕</button>
                      </div>
                    )}
                  </React.Fragment>
                ))}
              </div>
            </div>
          ))}
          {fields.length === 0 && <EmptyState icon="🧩" title="Sin campos personalizados" description="Añade campos específicos de tu empresa" />}
        </div>
      )}
      <div style={{ padding: '14px 16px', background: 'var(--accent-muted)', border: '1px dashed #00d4ff30', borderRadius: 10 }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--accent)', marginBottom: 12 }}>Añadir campo personalizado</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr auto', gap: 10, alignItems: 'flex-end' }}>
          <div><label style={ls}>Entidad</label><select value={form.entity} onChange={e => setForm(f => ({ ...f, entity: e.target.value }))} style={fs}>{ENTITIES.map(e => <option key={e.value} value={e.value}>{e.label}</option>)}</select></div>
          <div><label style={ls}>Nombre</label><input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value, field_key: e.target.value.toLowerCase().replace(/\s+/g, '_').replace(/[^a-z0-9_]/g, '') }))} style={fs} placeholder="Código SAP" /></div>
          <div><label style={ls}>Clave</label><input value={form.field_key} onChange={e => setForm(f => ({ ...f, field_key: e.target.value }))} style={fs} placeholder="codigo_sap" /></div>
          <div><label style={ls}>Tipo</label><select value={form.field_type} onChange={e => setForm(f => ({ ...f, field_type: e.target.value }))} style={fs}>{TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}</select></div>
          <Button onClick={() => { createField(form); setForm({ entity: form.entity, name: '', field_key: '', field_type: 'text', is_required: false, placeholder: '' }) }} disabled={!form.name || !form.field_key}>Añadir</Button>
        </div>
      </div>
    </Section>
  )
}

// ── Templates section ─────────────────────────────────────────────────────────
function TemplatesSection() {
  const toast = useToast()
  const qc = useQueryClient()
  const { data: templates = [], isLoading } = useQuery({ queryKey: ['project-templates'], queryFn: () => advancedConfigApi.getTemplates().then(r => r.data) })
  const { mutate: deleteTemplate } = useMutation({ mutationFn: advancedConfigApi.deleteTemplate, onSuccess: () => qc.invalidateQueries(['project-templates']) , onError: e => toast.error(extractErr(e, 'Error'))})
  const [showCreate, setShowCreate] = useState(false)
  const [selected, setSelected] = useState(null)

  return (
    <Section icon="📐" title="Plantillas de Proyecto" description="Reutiliza configuraciones de proyectos similares con fases, tareas, riesgos y entregables predefinidos">
      {isLoading ? <Spinner /> : templates.length === 0 ? (
        <EmptyState icon="📐" title="Sin plantillas" description="Crea plantillas para agilizar la configuración de nuevos proyectos" />
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 14, marginBottom: 16 }}>
          {templates.map(t => (
            <div key={t.id} style={{ background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 12, padding: 18, cursor: 'pointer' }}
              onMouseEnter={e => e.currentTarget.style.borderColor = 'var(--accent-glow)'}
              onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--surface-4)'}
              onClick={() => setSelected(t)}>
              <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 6 }}>{t.name}</div>
              {t.description && <div style={{ fontSize: 12, color: 'var(--text-2)', marginBottom: 10 }}>{t.description}</div>}
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 12 }}>
                {[`${t.phase_count} fases`, `${t.task_count} tareas`, `${t.risk_count} riesgos`, `${t.deliverable_count} entregables`].map(l => (
                  <span key={l} style={{ fontSize: 11, background: 'var(--surface-3)', color: 'var(--text-2)', borderRadius: 20, padding: '2px 8px' }}>{l}</span>
                ))}
                {t.estimated_weeks && <span style={{ fontSize: 11, color: 'var(--accent)' }}>~{t.estimated_weeks}sem</span>}
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <Button size="sm" onClick={e => { e.stopPropagation(); setSelected(t) }}>Ver detalle</Button>
                <button onClick={e => { e.stopPropagation(); deleteTemplate(t.id) }} style={{ background: 'none', border: '1px solid #ff475730', borderRadius: 6, padding: '4px 10px', color: 'var(--danger)', cursor: 'pointer', fontSize: 11 }}>🗑</button>
              </div>
            </div>
          ))}
        </div>
      )}
      <button onClick={() => setShowCreate(true)} style={{ width: '100%', padding: '10px', border: '1px dashed #1e2d45', borderRadius: 10, background: 'transparent', color: 'var(--text-2)', fontSize: 13, cursor: 'pointer', fontFamily: 'inherit', textAlign: 'center' }}>＋ Crear plantilla</button>
      {showCreate && <CreateTemplateModal onClose={() => setShowCreate(false)} onSave={(data) => advancedConfigApi.createTemplate(data).then(() => { qc.invalidateQueries(['project-templates']); setShowCreate(false) })} />}
      {selected && <TemplateDetailModal template={selected} onClose={() => setSelected(null)} />}
    </Section>
  )
}

function CreateTemplateModal({ onClose, onSave }) {
  const [form, setForm] = useState({ name: '', description: '', project_type: '', estimated_weeks: '', estimated_hours: '', phases: [], risks: [], deliverables: [] })
  const [phase, setPhase] = useState({ name: '', estimated_weeks: '', tasks: [] })
  const [_task, _setTask] = useState({ title: '', estimated_hours: '' })
  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.value }))

  return (
    <Modal open title="Crear plantilla de proyecto" onClose={onClose} width={660}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr', gap: 12 }}>
          <div><label style={ls}>Nombre *</label><input value={form.name} onChange={set('name')} style={fs} placeholder="Proyecto de desarrollo web" /></div>
          <div><label style={ls}>Semanas estimadas</label><input type="number" value={form.estimated_weeks} onChange={set('estimated_weeks')} style={fs} /></div>
          <div><label style={ls}>Horas estimadas</label><input type="number" value={form.estimated_hours} onChange={set('estimated_hours')} style={fs} /></div>
        </div>
        <div><label style={ls}>Descripción</label><textarea value={form.description} onChange={set('description')} rows={2} style={{ ...fs, resize: 'vertical' }} /></div>

        {/* Phases */}
        <div>
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 10 }}>Fases ({form.phases.length})</div>
          {form.phases.map((p, i) => (
            <div key={i} style={{ padding: '8px 12px', background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 8, marginBottom: 6 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: 13, fontWeight: 600 }}>{p.name}</span>
                <div style={{ display: 'flex', gap: 8 }}>
                  <span style={{ fontSize: 11, color: 'var(--text-2)' }}>{p.tasks.length} tareas</span>
                  <button onClick={() => setForm(f => ({ ...f, phases: f.phases.filter((_, j) => j !== i) }))} style={{ background: 'none', border: 'none', color: 'var(--danger)', cursor: 'pointer' }}>×</button>
                </div>
              </div>
            </div>
          ))}
          <div style={{ display: 'flex', gap: 8, padding: '8px', background: 'var(--surface-3)', borderRadius: 8 }}>
            <input value={phase.name} onChange={e => setPhase(f => ({ ...f, name: e.target.value }))} style={{ ...fs, flex: 2 }} placeholder="Nombre fase" />
            <input type="number" value={phase.estimated_weeks} onChange={e => setPhase(f => ({ ...f, estimated_weeks: e.target.value }))} style={{ ...fs, flex: 1 }} placeholder="Semanas" />
            <Button size="sm" onClick={() => { if (phase.name) { setForm(f => ({ ...f, phases: [...f.phases, { ...phase, tasks: [] }] })); setPhase({ name: '', estimated_weeks: '', tasks: [] }) } }}>+ Fase</Button>
          </div>
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={() => onSave(form)} disabled={!form.name}>Crear plantilla</Button>
        </div>
      </div>
    </Modal>
  )
}

function TemplateDetailModal({ template, onClose }) {
  return (
    <Modal open title={template.name} onClose={onClose} width={600}>
      {template.description && <p style={{ color: 'var(--text-2)', fontSize: 13, marginBottom: 16 }}>{template.description}</p>}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {template.phases?.map(p => (
          <div key={p.id} style={{ background: 'var(--surface-3)', borderRadius: 10, padding: '12px 16px' }}>
            <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 8 }}>📋 {p.name}</div>
            {p.tasks?.map(t => (
              <div key={t.id} style={{ fontSize: 12, color: 'var(--text-2)', padding: '3px 8px', borderLeft: '2px solid #1e2d45', marginBottom: 3 }}>
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
  const { data: offices = [] } = useQuery({ queryKey: ['offices'], queryFn: () => advancedConfigApi.getOffices().then(r => r.data) })
  const { mutate: create } = useMutation({ mutationFn: advancedConfigApi.createOffice, onSuccess: () => qc.invalidateQueries(['offices']), onError: e => toast.error(extractErr(e, 'Error')) })
  const { mutate: update } = useMutation({ mutationFn: ({ id, data }) => advancedConfigApi.updateOffice(id, data), onSuccess: () => { qc.invalidateQueries(['offices']); setEditingId(null) }, onError: e => toast.error(extractErr(e, 'Error')) })
  const { mutate: del } = useMutation({ mutationFn: advancedConfigApi.deleteOffice, onSuccess: () => qc.invalidateQueries(['offices']), onError: e => toast.error(extractErr(e, 'Error')) })
  const [form, setForm] = useState({ name: '', country: '', city: '', timezone: 'Europe/Madrid' })
  const [editingId, setEditingId] = useState(null)
  const [editForm, setEditForm] = useState({ name: '', country: '', city: '', timezone: 'Europe/Madrid' })
  const TIMEZONES = ['Europe/Madrid', 'Europe/London', 'Europe/Paris', 'Europe/Berlin', 'America/New_York', 'America/Los_Angeles', 'Asia/Tokyo', 'Asia/Shanghai']

  return (
    <Section icon="🏢" title="Sedes y Oficinas" description="Gestión de ubicaciones con calendarios laborales propios">
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
                      color:'#fff',cursor:'pointer',fontSize:12,fontFamily:'inherit' }}>✓ Guardar</button>
                  <button onClick={() => setEditingId(null)}
                    style={{ background:'none',border:'1px solid var(--surface-4)',borderRadius:6,
                      padding:'6px 10px',color:'var(--text-2)',cursor:'pointer',fontSize:12 }}>Cancelar</button>
                </div>
              </div>
            ) : (
              <div style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '10px 14px', background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 10 }}>
                <span style={{ fontSize: 20 }}>🏢</span>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, fontWeight: 700 }}>{o.name}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-2)' }}>{o.city}{o.country ? `, ${o.country}` : ''} · {o.timezone}</div>
                </div>
                <button onClick={() => { setEditingId(o.id); setEditForm({ name:o.name, country:o.country||'', city:o.city||'', timezone:o.timezone||'Europe/Madrid' }) }}
                  style={{ background:'none',border:'1px solid #1e2d45',borderRadius:6,padding:'3px 8px',color:'var(--text-2)',cursor:'pointer',fontSize:11 }}>✏</button>
                <button onClick={() => del(o.id)} style={{ background: 'none', border: '1px solid #ff475730', borderRadius: 6, padding: '3px 8px', color: 'var(--danger)', cursor: 'pointer', fontSize: 11 }}>🗑</button>
              </div>
            )}
          </div>
        ))}
        {offices.length === 0 && <EmptyState icon="🏢" title="Sin sedes configuradas" />}
      </div>
      <div style={{ display: 'flex', gap: 10, padding: '10px 14px', background: 'var(--accent-muted)', border: '1px dashed #00d4ff30', borderRadius: 10, flexWrap: 'wrap', alignItems: 'flex-end' }}>
        <div style={{ flex: 2 }}><label style={ls}>Nombre *</label><input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} style={fs} placeholder="Madrid" /></div>
        <div style={{ flex: 1 }}><label style={ls}>País</label><input value={form.country} onChange={e => setForm(f => ({ ...f, country: e.target.value }))} style={fs} placeholder="España" /></div>
        <div style={{ flex: 1 }}><label style={ls}>Ciudad</label><input value={form.city} onChange={e => setForm(f => ({ ...f, city: e.target.value }))} style={fs} /></div>
        <div style={{ flex: 1 }}><label style={ls}>Zona horaria</label><select value={form.timezone} onChange={e => setForm(f => ({ ...f, timezone: e.target.value }))} style={fs}>{TIMEZONES.map(t => <option key={t} value={t}>{t}</option>)}</select></div>
        <Button onClick={() => { create(form); setForm({ name: '', country: '', city: '', timezone: 'Europe/Madrid' }) }} disabled={!form.name}>Añadir</Button>
      </div>
    </Section>
  )
}

// ── Task types section ────────────────────────────────────────────────────────
function TaskTypesSection() {
  const toast = useToast()
  const qc = useQueryClient()
  const { data: types = [], isLoading } = useQuery({ queryKey: ['task-types-config'], queryFn: () => advancedConfigApi.getTaskTypes().then(r => r.data) })
  const { mutate: create } = useMutation({ mutationFn: advancedConfigApi.createTaskType, onSuccess: () => qc.invalidateQueries(['task-types-config']), onError: e => toast.error(extractErr(e, 'Error')) })
  const { mutate: update } = useMutation({ mutationFn: ({ id, data }) => advancedConfigApi.updateTaskType(id, data), onSuccess: () => { qc.invalidateQueries(['task-types-config']); setEditingId(null) }, onError: e => toast.error(extractErr(e, 'Error')) })
  const { mutate: del } = useMutation({ mutationFn: advancedConfigApi.deleteTaskType, onSuccess: () => qc.invalidateQueries(['task-types-config']), onError: e => toast.error(extractErr(e, 'Error')) })
  const [form, setForm] = useState({ name: '', value: '', icon: '📋', color: 'var(--text-2)', is_billable_default: true })
  const [editingId, setEditingId] = useState(null)
  const [editForm, setEditForm] = useState({ name: '', icon: '📋', color: '#6b7280', is_billable_default: true })

  return (
    <Section icon="🏷️" title="Tipos de Tarea" description="Categorías de tareas con iconos y colores personalizados">
      {isLoading ? <Spinner /> : (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 16 }}>
          {types.map(t => (
            <div key={t.id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px', background: 'var(--surface-2)', border: `1px solid ${t.color}40`, borderRadius: 10 }}>
              <span style={{ fontSize: 18 }}>{t.icon}</span>
              <div>
                <div style={{ fontSize: 13, fontWeight: 700, color: t.color }}>{t.name}</div>
                <div style={{ fontSize: 10, color: 'var(--text-2)' }}>{t.is_billable_default ? 'Facturable' : 'No facturable'}</div>
              </div>
              <button onClick={() => { setEditingId(t.id); setEditForm({ name: t.name, icon: t.icon, color: t.color, is_billable_default: t.is_billable_default }) }}
                style={{ background: 'none', border: 'none', color: 'var(--text-3)', cursor: 'pointer', fontSize: 12, marginLeft: 2 }}>✏</button>
              <button onClick={() => del(t.id)} style={{ background: 'none', border: 'none', color: 'var(--danger)', cursor: 'pointer', fontSize: 14, marginLeft: 2 }}>×</button>
            </div>
          ))}
        </div>
      )}
      {editingId && (
        <div style={{ display:'flex', gap:8, padding:'10px 14px', background:'var(--accent-muted)',
          border:'1px solid var(--accent-glow)', borderRadius:10, marginBottom:8, flexWrap:'wrap', alignItems:'flex-end' }}>
          <div><label style={ls}>Nombre *</label><input value={editForm.name} onChange={e => setEditForm(f=>({...f,name:e.target.value}))} style={{...fs,width:130}} autoFocus /></div>
          <div><label style={ls}>Icono</label><input value={editForm.icon} onChange={e => setEditForm(f=>({...f,icon:e.target.value}))} style={{...fs,width:55}} /></div>
          <div><label style={ls}>Color</label><input type="color" value={editForm.color.startsWith('#')?editForm.color:'#6b7280'} onChange={e=>setEditForm(f=>({...f,color:e.target.value}))} style={{width:38,height:35,border:'none',background:'transparent',cursor:'pointer'}} /></div>
          <label style={{display:'flex',alignItems:'center',gap:5,cursor:'pointer',fontSize:12,paddingBottom:4}}><input type="checkbox" checked={editForm.is_billable_default} onChange={e=>setEditForm(f=>({...f,is_billable_default:e.target.checked}))} />Facturable</label>
          <button onClick={() => update({ id: editingId, data: editForm })} disabled={!editForm.name} style={{background:'var(--accent)',border:'none',borderRadius:6,padding:'6px 14px',color:'#fff',cursor:'pointer',fontSize:12,fontFamily:'inherit'}}>✓ Guardar</button>
          <button onClick={() => setEditingId(null)} style={{background:'none',border:'1px solid var(--surface-4)',borderRadius:6,padding:'6px 10px',color:'var(--text-2)',cursor:'pointer',fontSize:12}}>Cancelar</button>
        </div>
      )}
      <div style={{ display: 'flex', gap: 10, padding: '10px 14px', background: 'var(--accent-muted)', border: '1px dashed #00d4ff30', borderRadius: 10, flexWrap: 'wrap', alignItems: 'flex-end' }}>
        <div><label style={ls}>Nombre *</label><input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value, value: e.target.value.toLowerCase().replace(/\s+/g, '_') }))} style={{ ...fs, width: 140 }} placeholder="Bug" /></div>
        <div><label style={ls}>Clave</label><input value={form.value} onChange={e => setForm(f => ({ ...f, value: e.target.value }))} style={{ ...fs, width: 110 }} placeholder="bug" /></div>
        <div><label style={ls}>Icono</label><input value={form.icon} onChange={e => setForm(f => ({ ...f, icon: e.target.value }))} style={{ ...fs, width: 60 }} placeholder="🐛" /></div>
        <div><label style={ls}>Color</label><div style={{ display: 'flex', gap: 6 }}><input type="color" value={form.color} onChange={e => setForm(f => ({ ...f, color: e.target.value }))} style={{ width: 38, height: 38, border: 'none', background: 'transparent', cursor: 'pointer' }} /><input value={form.color} onChange={e => setForm(f => ({ ...f, color: e.target.value }))} style={{ ...fs, width: 90 }} /></div></div>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', fontSize: 12, paddingBottom: 4 }}><input type="checkbox" checked={form.is_billable_default} onChange={e => setForm(f => ({ ...f, is_billable_default: e.target.checked }))} />Facturable</label>
        <Button onClick={() => { create(form); setForm({ name: '', value: '', icon: '📋', color: 'var(--text-2)', is_billable_default: true }) }} disabled={!form.name || !form.value}>Añadir</Button>
      </div>
    </Section>
  )
}

// ── Departments & Holidays (existing) ─────────────────────────────────────────
function DepartmentsSection() {
  const toast = useToast()
  const qc = useQueryClient()
  const { data = [], isLoading } = useQuery({ queryKey: ['departments'], queryFn: () => settingsApi.getDepartments().then(r => r.data) })
  const { mutate: create } = useMutation({ mutationFn: settingsApi.createDepartment, onSuccess: () => qc.invalidateQueries(['departments']), onError: e => toast.error(extractErr(e, 'Error')) })
  const { mutate: update } = useMutation({ mutationFn: ({ id, data }) => settingsApi.updateDepartment(id, data), onSuccess: () => { qc.invalidateQueries(['departments']); setEditingId(null) }, onError: e => toast.error(extractErr(e, 'Error')) })
  const { mutate: del } = useMutation({ mutationFn: settingsApi.deleteDepartment, onSuccess: () => qc.invalidateQueries(['departments']), onError: e => toast.error(extractErr(e, 'Error')) })
  const [form, setForm] = useState({ name: '', description: '' })
  const [editingId, setEditingId] = useState(null)
  const [editForm, setEditForm] = useState({ name: '', description: '' })
  return (
    <Section icon="🏢" title="Departamentos" description="Estructura organizativa de la empresa">
      {isLoading ? <Spinner /> : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 12 }}>
          {data.map(d => (
            <div key={d.id}>
              {editingId === d.id ? (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px',
                  background: 'var(--accent-muted)', border: '1px solid var(--accent-glow)', borderRadius: 10 }}>
                  <input value={editForm.name} onChange={e => setEditForm(f => ({ ...f, name: e.target.value }))}
                    style={{ ...fs, flex: 2, padding: '5px 9px' }} placeholder="Nombre *" autoFocus />
                  <input value={editForm.description} onChange={e => setEditForm(f => ({ ...f, description: e.target.value }))}
                    style={{ ...fs, flex: 3, padding: '5px 9px' }} placeholder="Descripción" />
                  <button onClick={() => update({ id: d.id, data: editForm })} disabled={!editForm.name}
                    style={{ background: 'var(--accent)', border: 'none', borderRadius: 6, padding: '5px 12px',
                      color: '#fff', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}>✓</button>
                  <button onClick={() => setEditingId(null)}
                    style={{ background: 'none', border: '1px solid var(--surface-4)', borderRadius: 6,
                      padding: '5px 9px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 12 }}>✕</button>
                </div>
              ) : (
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px',
                  background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 10 }}>
                  <span style={{ flex: 1, fontSize: 13, fontWeight: 600 }}>{d.name}</span>
                  {d.description && <span style={{ fontSize: 12, color: 'var(--text-2)' }}>{d.description}</span>}
                  <button onClick={() => { setEditingId(d.id); setEditForm({ name: d.name, description: d.description || '' }) }}
                    style={{ background: 'none', border: '1px solid #1e2d45', borderRadius: 6,
                      padding: '3px 8px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 11 }}>✏</button>
                  <button onClick={() => del(d.id)}
                    style={{ background: 'none', border: '1px solid #ff475730', borderRadius: 6,
                      padding: '3px 8px', color: 'var(--danger)', cursor: 'pointer', fontSize: 11 }}>🗑</button>
                </div>
              )}
            </div>
          ))}
          {data.length === 0 && <div style={{ fontSize: 13, color: 'var(--text-3)', textAlign: 'center', padding: 16 }}>Sin departamentos</div>}
        </div>
      )}
      <div style={{ display: 'flex', gap: 10, padding: '10px', background: 'var(--accent-muted)', border: '1px dashed #00d4ff30', borderRadius: 10 }}>
        <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} style={{ ...fs, flex: 2 }} placeholder="Nombre departamento *" />
        <input value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} style={{ ...fs, flex: 2 }} placeholder="Descripción" />
        <Button onClick={() => { create(form); setForm({ name: '', description: '' }) }} disabled={!form.name}>Añadir</Button>
      </div>
    </Section>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────
// ── Idiomas & Traducciones ─────────────────────────────────────────────────────
function IdiomasSection() {
  const toast = useToast()
  const qc = useQueryClient()
  const { lang: operatorLang, setLang: setOperatorLang, t, _translations, setCustomTranslations, customTrans } = useAppLang()

  // Traducciones del portal (backend)
  const { data: _portalTrans = {} } = useQuery({
    queryKey: ['portal-translations'],
    queryFn: () => api.get('/portal/translations').then(r => r.data).catch(() => ({})),
  })
  const { mutate: savePortalTrans, isPending: savingPortal } = useMutation({
    mutationFn: d => api.post('/portal/translations', d),
    onSuccess: () => { qc.invalidateQueries(['portal-translations']); toast.success(t('i18n.saved_ok')) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const _PORTAL_LANGS = [
    { code: 'es', label: 'Español 🇪🇸' }, { code: 'en', label: 'English 🇬🇧' },
    { code: 'pl', label: 'Polski 🇵🇱' },  { code: 'zh', label: '中文 🇨🇳' },
  ]

  // Estado local
  const [activeTab,     setActiveTab]     = useState('operator')  // operator | app | portal
  const [appLang,       setAppLang]       = useState('en')         // idioma que se edita en la app
  const [portalLang,    setPortalLang]    = useState('en')
  const [searchKey,     setSearchKey]     = useState('')
  const [activeModule,  setActiveModule]  = useState('all')
  const [appEdits,      setAppEdits]      = useState({})           // {lang: {module: {key: val}}}
  const [portalEdits,   setPortalEdits]   = useState({})
  const [portalSearch,  setPortalSearch]  = useState('')
  const [hasUnsaved,    setHasUnsaved]    = useState(false)

  // Todas las claves del back-office
  const allKeys = getAllKeys()
  const modules = ['all', ...new Set(allKeys.map(k => k.module))]

  const filteredKeys = allKeys.filter(k => {
    const matchMod = activeModule === 'all' || k.module === activeModule
    const matchSrc = !searchKey || k.key.includes(searchKey.toLowerCase()) ||
                     k.base_es.toLowerCase().includes(searchKey.toLowerCase()) ||
                     k.full_key.includes(searchKey.toLowerCase())
    return matchMod && matchSrc
  })

  const getAppVal = (lang, module, key) =>
    appEdits[lang]?.[module]?.[key] ??
    customTrans[lang]?.[module]?.[key] ??
    APP_TRANSLATIONS[lang]?.[module]?.[key] ?? ''

  const setAppVal = (lang, module, key, val) => {
    setAppEdits(prev => ({
      ...prev,
      [lang]: { ...(prev[lang] || {}), [module]: { ...(prev[lang]?.[module] || {}), [key]: val } }
    }))
    setHasUnsaved(true)
  }

  const saveAppTrans = () => {
    // Mergear edits con custom existentes
    const merged = {}
    for (const lang of Object.keys({ ...customTrans, ...appEdits })) {
      merged[lang] = {}
      const mods = new Set([...Object.keys(customTrans[lang] || {}), ...Object.keys(appEdits[lang] || {})])
      for (const mod of mods) {
        merged[lang][mod] = { ...(customTrans[lang]?.[mod] || {}), ...(appEdits[lang]?.[mod] || {}) }
      }
    }
    setCustomTranslations(merged)
    setAppEdits({})
    setHasUnsaved(false)
    toast.success(t('i18n.saved_ok'))
  }

  const exportJSON = () => {
    const data = JSON.stringify(APP_TRANSLATIONS, null, 2)
    const blob = new Blob([data], { type: 'application/json' })
    const url  = URL.createObjectURL(blob)
    const a    = document.createElement('a'); a.href = url
    a.download = 'clarive_translations.json'; a.click()
    URL.revokeObjectURL(url)
  }

  const fs   = { width: '100%', background: 'var(--surface-1)', border: '1px solid #1e2d45', borderRadius: 6, padding: '6px 10px', color: 'var(--text-1)', fontSize: 12, outline: 'none', fontFamily: 'inherit' }
  const card = { background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 12 }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

      {/* Tabs principales */}
      <div style={{ display: 'flex', gap: 6, borderBottom: '1px solid #1e2d45', paddingBottom: 10 }}>
        {[['operator','⚙️ Idioma del operador'],['app','🖥 Traducciones del back-office'],['portal','🌐 Portal cliente']].map(([id, label]) => (
          <button key={id} onClick={() => setActiveTab(id)}
            style={{ padding: '7px 16px', borderRadius: 8, border: `1px solid ${activeTab === id ? 'var(--accent-glow)' : 'var(--surface-4)'}`, background: activeTab === id ? 'var(--accent-muted)' : 'transparent', color: activeTab === id ? 'var(--accent)' : 'var(--text-2)', fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>
            {label}
          </button>
        ))}
      </div>

      {/* ── OPERADOR ── */}
      {activeTab === 'operator' && (
        <div style={card}>
          <div style={{ padding: '20px 24px', borderBottom: '1px solid #1e2d45' }}>
            <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 4 }}>Idioma del operador (back-office)</div>
            <div style={{ fontSize: 12, color: 'var(--text-2)' }}>
              Idioma de la interfaz interna. Cada usuario puede configurar el suyo desde aquí. Se guarda en el navegador.
            </div>
          </div>
          <div style={{ padding: '20px 24px' }}>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              {APP_LANGUAGES.map(l => (
                <button key={l.code} onClick={() => setOperatorLang(l.code)}
                  style={{ padding: '12px 22px', borderRadius: 10, border: `2px solid ${operatorLang === l.code ? 'var(--accent)' : 'var(--surface-4)'}`, background: operatorLang === l.code ? 'var(--accent-muted)' : 'var(--surface-2)', color: operatorLang === l.code ? 'var(--accent)' : 'var(--text-2)', fontSize: 15, fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit', transition: 'all 0.15s' }}>
                  {l.flag} {l.label}
                  {operatorLang === l.code && <span style={{ marginLeft: 8, fontSize: 12 }}>✓</span>}
                </button>
              ))}
            </div>
            <div style={{ marginTop: 16, padding: '10px 14px', background: 'var(--surface-1)', borderRadius: 8, fontSize: 12, color: 'var(--text-2)' }}>
              💡 Al cambiar el idioma, los menús, títulos y textos de la interfaz se mostrarán en ese idioma.
              Las páginas que aún no estén totalmente traducidas mostrarán el texto en español.
            </div>
          </div>
        </div>
      )}

      {/* ── BACK-OFFICE ── */}
      {activeTab === 'app' && (
        <div>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 16, flexWrap: 'wrap' }}>
            <div>
              <div style={{ fontSize: 11, color: 'var(--text-2)', marginBottom: 4 }}>IDIOMA A EDITAR</div>
              <div style={{ display: 'flex', gap: 6 }}>
                {APP_LANGUAGES.filter(l => l.code !== 'es').map(l => (
                  <button key={l.code} onClick={() => setAppLang(l.code)}
                    style={{ padding: '6px 14px', borderRadius: 8, border: `1px solid ${appLang === l.code ? 'var(--accent-glow)' : 'var(--surface-4)'}`, background: appLang === l.code ? 'var(--accent-muted)' : 'transparent', color: appLang === l.code ? 'var(--accent)' : 'var(--text-2)', fontSize: 12, fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit' }}>
                    {l.flag} {l.label}
                  </button>
                ))}
              </div>
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 11, color: 'var(--text-2)', marginBottom: 4 }}>BUSCAR CLAVE</div>
              <input value={searchKey} onChange={e => setSearchKey(e.target.value)}
                placeholder="Buscar por clave o texto..." style={{ ...fs, width: 280 }} />
            </div>
            <div>
              <div style={{ fontSize: 11, color: 'var(--text-2)', marginBottom: 4 }}>MÓDULO</div>
              <select value={activeModule} onChange={e => setActiveModule(e.target.value)} style={{ ...fs, width: 160 }}>
                {modules.map(m => <option key={m} value={m}>{m === 'all' ? 'Todos los módulos' : m}</option>)}
              </select>
            </div>
          </div>

          {/* Cabecera tabla */}
          <div style={{ display: 'grid', gridTemplateColumns: '140px 1fr 1fr', gap: 8, padding: '8px 14px', background: 'var(--surface-1)', borderRadius: '8px 8px 0 0', fontSize: 10, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase' }}>
            <span>Módulo.Clave</span>
            <span>🇪🇸 Español (base)</span>
            <span>{APP_LANGUAGES.find(l => l.code === appLang)?.flag} {APP_LANGUAGES.find(l => l.code === appLang)?.label}</span>
          </div>
          <div style={{ border: '1px solid #1e2d45', borderTop: 'none', borderRadius: '0 0 8px 8px', maxHeight: 500, overflowY: 'auto' }}>
            {filteredKeys.slice(0, 200).map((item, idx) => {
              const currentVal = getAppVal(appLang, item.module, item.key)
              const isModified = appEdits[appLang]?.[item.module]?.[item.key] !== undefined
              return (
                <div key={item.full_key}
                  style={{ display: 'grid', gridTemplateColumns: '140px 1fr 1fr', gap: 8, padding: '6px 14px', borderBottom: '1px solid #1e2d4520', background: idx % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.02)', alignItems: 'center' }}>
                  <div>
                    <span style={{ fontSize: 10, color: 'var(--text-3)', display: 'block' }}>{item.module}</span>
                    <span style={{ fontSize: 11, fontFamily: 'monospace', color: isModified ? 'var(--warning)' : 'var(--text-2)' }}>{item.key}</span>
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text-2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {item.base_es}
                  </div>
                  <input
                    value={currentVal}
                    onChange={e => setAppVal(appLang, item.module, item.key, e.target.value)}
                    style={{ ...fs, padding: '4px 8px', borderColor: isModified ? 'rgba(245,158,11,0.31)' : 'var(--surface-4)' }}
                    placeholder={item.base_es}
                  />
                </div>
              )
            })}
            {filteredKeys.length > 200 && (
              <div style={{ padding: '10px 14px', fontSize: 12, color: 'var(--text-2)', textAlign: 'center' }}>
                Mostrando 200 de {filteredKeys.length} claves. Usa el filtro para buscar más específico.
              </div>
            )}
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 14 }}>
            <div style={{ fontSize: 12, color: 'var(--text-2)' }}>
              {filteredKeys.length} claves · {allKeys.length} total · {hasUnsaved && <span style={{ color: 'var(--warning)' }}>⚠ Cambios sin guardar</span>}
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button onClick={exportJSON}
                style={{ padding: '7px 14px', borderRadius: 8, border: '1px solid #1e2d45', background: 'transparent', color: 'var(--text-2)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}>
                📥 Exportar JSON
              </button>
              <button onClick={saveAppTrans} disabled={!hasUnsaved}
                style={{ padding: '7px 14px', borderRadius: 8, border: 'none', background: hasUnsaved ? 'var(--accent)' : 'var(--surface-4)', color: hasUnsaved ? 'var(--surface-0)' : 'var(--text-2)', cursor: hasUnsaved ? 'pointer' : 'default', fontSize: 12, fontWeight: 700, fontFamily: 'inherit' }}>
                💾 Guardar traducción
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── PORTAL CLIENTE ── */}
      {activeTab === 'portal' && (
        <div>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 16, flexWrap: 'wrap' }}>
            <div>
              <div style={{ fontSize: 11, color: 'var(--text-2)', marginBottom: 4 }}>IDIOMA A EDITAR</div>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {PORTAL_LANGUAGES.filter(l => l.code !== 'es').map(l => (
                  <button key={l.code} onClick={() => setPortalLang(l.code)}
                    style={{ padding: '6px 14px', borderRadius: 8, border: `1px solid ${portalLang === l.code ? 'var(--accent-glow)' : 'var(--surface-4)'}`, background: portalLang === l.code ? 'var(--accent-muted)' : 'transparent', color: portalLang === l.code ? 'var(--accent)' : 'var(--text-2)', fontSize: 12, fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit' }}>
                    {l.flag} {l.label}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <div style={{ fontSize: 11, color: 'var(--text-2)', marginBottom: 4 }}>BUSCAR</div>
              <input value={portalSearch} onChange={e => setPortalSearch(e.target.value)}
                placeholder="Buscar clave o texto..." style={{ ...fs, width: 260 }} />
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '180px 1fr 1fr', gap: 8, padding: '8px 14px', background: 'var(--surface-1)', borderRadius: '8px 8px 0 0', fontSize: 10, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase' }}>
            <span>Clave</span>
            <span>🇪🇸 Español (base)</span>
            <span>{PORTAL_LANGUAGES.find(l => l.code === portalLang)?.flag} {PORTAL_LANGUAGES.find(l => l.code === portalLang)?.label}</span>
          </div>
          <div style={{ border: '1px solid #1e2d45', borderTop: 'none', borderRadius: '0 0 8px 8px', maxHeight: 500, overflowY: 'auto' }}>
            {getPortalKeys()
              .filter(({ key, base_es }) => !portalSearch ||
                key.includes(portalSearch.toLowerCase()) ||
                base_es.toLowerCase().includes(portalSearch.toLowerCase()))
              .map(({ key, base_es }, idx) => {
                const currentVal = portalEdits[key]?.[portalLang]
                  ?? PORTAL_TRANSLATIONS[portalLang]?.[key] ?? ''
                const isModified = portalEdits[key]?.[portalLang] !== undefined
                return (
                  <div key={key} style={{ display: 'grid', gridTemplateColumns: '180px 1fr 1fr', gap: 8, padding: '6px 14px', borderBottom: '1px solid #1e2d4520', background: idx % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.02)', alignItems: 'center' }}>
                    <span style={{ fontSize: 11, fontFamily: 'monospace', color: isModified ? 'var(--warning)' : 'var(--text-2)' }}>{key}</span>
                    <span style={{ fontSize: 12, color: 'var(--text-2)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{base_es}</span>
                    <input
                      value={currentVal}
                      onChange={e => {
                        setPortalEdits(prev => ({ ...prev, [key]: { ...(prev[key] || {}), [portalLang]: e.target.value } }))
                        setHasUnsaved(true)
                      }}
                      style={{ ...fs, padding: '4px 8px', borderColor: isModified ? 'rgba(245,158,11,0.31)' : 'var(--surface-4)' }}
                      placeholder={base_es}
                    />
                  </div>
                )
              })}
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 14 }}>
            <div style={{ fontSize: 12, color: 'var(--text-2)' }}>
              {getPortalKeys().length} claves · 8 idiomas
              {hasUnsaved && <span style={{ color: 'var(--warning)', marginLeft: 8 }}>⚠ Cambios sin guardar</span>}
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button onClick={() => {
                const data = JSON.stringify(PORTAL_TRANSLATIONS, null, 2)
                const blob = new Blob([data], { type: 'application/json' })
                const url = URL.createObjectURL(blob); const a = document.createElement('a')
                a.href = url; a.download = 'portal_translations.json'; a.click()
                URL.revokeObjectURL(url)
              }} style={{ padding: '7px 14px', borderRadius: 8, border: '1px solid #1e2d45', background: 'transparent', color: 'var(--text-2)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}>
                📥 Exportar JSON
              </button>
              <button onClick={() => {
                // Guardar overrides en localStorage igual que el back-office
                const stored = JSON.parse(localStorage.getItem('clarive_portal_custom') || '{}')
                for (const [key, langs] of Object.entries(portalEdits)) {
                  for (const [lang, val] of Object.entries(langs)) {
                    if (!stored[lang]) stored[lang] = {}
                    stored[lang][key] = val
                  }
                }
                localStorage.setItem('clarive_portal_custom', JSON.stringify(stored))
                // Guardar también en backend
                savePortalTrans(stored)
                setPortalEdits({})
                setHasUnsaved(false)
              }} style={{ padding: '7px 16px', borderRadius: 8, border: 'none', background: 'var(--accent)', color: 'var(--surface-0)', cursor: 'pointer', fontSize: 12, fontWeight: 700, fontFamily: 'inherit' }}>
                {savingPortal ? 'Guardando...' : '💾 Guardar traducciones'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Log Level Section ─────────────────────────────────────────────────────────
function LogLevelSection() {
  const toast = useToast()
  const [backendLevel, setBackendLevel] = useState('')
  const [frontendLevel, setFrontendLevel] = useState(
    localStorage.getItem('clarive_log_level') || (import.meta.env.DEV ? 'debug' : 'warn')
  )
  // Eliminado loading/setLoading: no se usa
  const qc = useQueryClient()

  const { data: serverLevel, isLoading } = useQuery({
    queryKey: ['log-level'],
    queryFn: () => api.get('/settings/log-level').then(r => r.data),
  })

  useEffect(() => {
    if (serverLevel?.clarive) {
      setBackendLevel(String(serverLevel.clarive).toUpperCase())
    }
  }, [serverLevel])

  const handleSetBackend = async (level = backendLevel) => {
    if (!level) return
    try {
      const lvl = String(level).toUpperCase()
      setBackendLevel(lvl)
      await api.post('/settings/log-level', { level: lvl })
      toast.success(`Nivel backend cambiado a ${lvl}`)
      qc.invalidateQueries(['log-level'])
    } catch {
      toast.error('Error al cambiar nivel de log')
    }
  }

  const handleSetFrontend = (level) => {
    setFrontendLevel(level)
    localStorage.setItem('clarive_log_level', level)
    if (window.__clariveLogger) window.__clariveLogger.setLevel(level)
    toast.success(`Nivel frontend cambiado a ${level.toUpperCase()} (activo hasta recarga)`)
  }

  const LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
  const LEVEL_COLORS = { DEBUG: 'var(--text-2)', INFO: 'var(--accent)', WARNING: 'var(--warning)', ERROR: 'var(--danger)', CRITICAL: '#c0392b' }

  return (
    <Section icon="📋" title="Nivel de Log" description="Controla la verbosidad de logs del servidor y del navegador para depuración.">
      <div style={{ display: 'flex', flexDirection: 'column', gap: 24, maxWidth: 640 }}>

        {/* Backend */}
        <div style={{ background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 10, padding: '18px 20px' }}>
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 4 }}>🖥️ Servidor (FastAPI / Uvicorn)</div>
          <div style={{ fontSize: 12, color: 'var(--text-2)', marginBottom: 16 }}>
            Cambia el nivel en tiempo real sin reiniciar. Configurable también por variable de entorno <code style={{ background: 'var(--surface-3)', padding: '1px 6px', borderRadius: 4, fontSize: 11 }}>LOG_LEVEL=INFO</code>
          </div>
          {!isLoading && serverLevel && (
            <div style={{ fontSize: 12, color: 'var(--success)', marginBottom: 12 }}>
              Nivel actual: <strong>{serverLevel.clarive}</strong>
              <span style={{ color: 'var(--text-2)', marginLeft: 8 }}>
                (root: {serverLevel.root} · uvicorn: {serverLevel.uvicorn || serverLevel.root})
              </span>
            </div>
          )}
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {LEVELS.map(l => (
              <button key={l} onClick={() => handleSetBackend(l)}
                style={{ padding: '6px 14px', borderRadius: 8, border: `1px solid ${backendLevel === l ? LEVEL_COLORS[l] : '#1e2d45'}`,
                  background: backendLevel === l ? (LEVEL_COLORS[l] + '22') : 'var(--surface-3)',
                  color: backendLevel === l ? LEVEL_COLORS[l] : 'var(--text-2)',
                  cursor: 'pointer', fontSize: 12, fontWeight: 600, fontFamily: 'inherit' }}>
                {l}
              </button>
            ))}
          </div>
        </div>

        {/* Frontend */}
        <div style={{ background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 10, padding: '18px 20px' }}>
          <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 4 }}>🌐 Navegador (React / Vite)</div>
          <div style={{ fontSize: 12, color: 'var(--text-2)', marginBottom: 16 }}>
            Controla la consola del navegador. Se guarda en localStorage. También puedes escribir en la consola: <code style={{ background: 'var(--surface-3)', padding: '1px 6px', borderRadius: 4, fontSize: 11 }}>{"__clariveLogger.setLevel('debug')"}</code>
          </div>
          <div style={{ fontSize: 12, color: 'var(--success)', marginBottom: 12 }}>
            Nivel actual: <strong>{frontendLevel.toUpperCase()}</strong>
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {['DEBUG', 'INFO', 'WARN', 'ERROR', 'SILENT'].map(l => (
              <button key={l} onClick={() => handleSetFrontend(l.toLowerCase())}
                style={{ padding: '6px 14px', borderRadius: 8,
                  border: `1px solid ${frontendLevel.toUpperCase() === l ? (LEVEL_COLORS[l] || LEVEL_COLORS['ERROR']) : '#1e2d45'}`,
                  background: frontendLevel.toUpperCase() === l ? ((LEVEL_COLORS[l] || LEVEL_COLORS['ERROR']) + '22') : 'var(--surface-3)',
                  color: frontendLevel.toUpperCase() === l ? (LEVEL_COLORS[l] || LEVEL_COLORS['ERROR']) : 'var(--text-2)',
                  cursor: 'pointer', fontSize: 12, fontWeight: 600, fontFamily: 'inherit' }}>
                {l}
              </button>
            ))}
          </div>
        </div>
      </div>
    </Section>
  )
}


const TABS = [
  { id: 'general',      label: '⚙️ General',          roles: ['admin'] },
  { id: 'users',        label: '👤 Usuarios',          roles: ['admin', 'hr'] },
  { id: 'roles',        label: '🔐 Roles',             roles: ['admin'] },
  { id: 'alert-config', label: '🔔 Alertas',           roles: ['admin'] },
  { id: 'task-types',   label: '🏷️ Tipos tarea',       roles: ['admin', 'pm'] },
  { id: 'templates',    label: '📐 Plantillas',        roles: ['admin', 'pm'] },
  { id: 'rates',        label: '💶 Tarifas',           roles: ['admin'] },
  { id: 'vacations',    label: '🏖️ Vacaciones',        roles: ['admin', 'hr'] },
  { id: 'depts',        label: '🏢 Departamentos',     roles: ['admin', 'hr'] },
  { id: 'offices',      label: '🌍 Sedes',             roles: ['admin'] },
  { id: 'numbering',    label: '🔢 Numeración',        roles: ['admin'] },
  { id: 'fields',       label: '🧩 Campos extra',      roles: ['admin'] },
  { id: 'idiomas',      label: '🌐 Idiomas',            roles: ['admin'] },
  { id: 'email-inbound',label: '📧 Email-to-ticket',  roles: ['admin'] },
  { id: 'log-level',    label: '📋 Nivel de log',      roles: ['admin'] },
]

// ── Email-to-ticket configuration section ─────────────────────────────────────
function EmailInboundSection() {
  const _backendUrl = (import.meta.env.VITE_API_URL || '/api/v1').replace(/\/api\/v1$/, '')
  const webhookUrl = `${window.location.origin}/api/v1/service-desk/inbound-email`

  return (
    <Section icon="📧" title="Email → Ticket" description="Convierte emails entrantes en tickets de Service Desk automáticamente.">
      <div style={{ display: 'flex', flexDirection: 'column', gap: 20, maxWidth: 720 }}>

        {/* How it works */}
        <div style={{ background: 'var(--surface-3)', borderRadius: 10, padding: '16px 20px', fontSize: 13 }}>
          <div style={{ fontWeight: 600, marginBottom: 10 }}>¿Cómo funciona?</div>
          <ol style={{ margin: 0, paddingLeft: 20, lineHeight: 2, color: 'var(--text-2)' }}>
            <li>Configura tu proveedor de email (Mailgun, SendGrid, Postmark o similar) para reenviar los emails entrantes a la URL de webhook.</li>
            <li>El proveedor envía el email parseado como JSON a Clarive.</li>
            <li>Clarive crea el ticket automáticamente con asunto→título y cuerpo→descripción.</li>
            <li>El ticket se asigna al primer agente disponible con política SLA activa.</li>
          </ol>
        </div>

        {/* Webhook URL */}
        <div>
          <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--text-3)', marginBottom: 6 }}>
            URL del Webhook (configura en tu proveedor de email)
          </label>
          <div style={{ display: 'flex', gap: 8 }}>
            <input readOnly value={webhookUrl}
              style={{ flex: 1, padding: '9px 12px', borderRadius: 8, border: '1px solid var(--surface-4)', background: 'var(--surface-2)', color: 'var(--text-1)', fontSize: 13, fontFamily: 'monospace' }} />
            <button onClick={() => { navigator.clipboard.writeText(webhookUrl) }}
              style={{ padding: '9px 16px', borderRadius: 8, background: 'var(--accent)', border: 'none', color: '#fff', cursor: 'pointer', fontSize: 12, fontWeight: 600 }}>
              Copiar
            </button>
          </div>
        </div>

        {/* Secret header */}
        <div>
          <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--text-3)', marginBottom: 6 }}>
            Header de autenticación (X-Clarive-Email-Secret)
          </label>
          <div style={{ background: 'var(--surface-3)', borderRadius: 8, padding: '10px 14px', fontSize: 12, color: 'var(--text-2)', fontFamily: 'monospace' }}>
            Configura la variable de entorno <strong style={{ color: 'var(--accent)' }}>INBOUND_EMAIL_SECRET</strong> en el servidor con un valor secreto aleatorio.
            El relay de email debe enviar ese mismo valor en la cabecera HTTP <strong>X-Clarive-Email-Secret</strong> con cada petición.
          </div>
        </div>

        {/* Provider guides */}
        <div>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-3)', marginBottom: 10 }}>Guías de configuración por proveedor</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 }}>
            {[
              { name: 'Mailgun', url: 'https://documentation.mailgun.com/docs/mailgun/user-manual/receive-forward-store/', note: 'Routes → Forward → URL' },
              { name: 'SendGrid', url: 'https://docs.sendgrid.com/for-developers/parsing-email/setting-up-the-inbound-parse-webhook', note: 'Inbound Parse Webhook' },
              { name: 'Postmark', url: 'https://postmarkapp.com/developer/user-guide/inbound/how-it-works', note: 'Inbound Message Webhook' },
            ].map(p => (
              <a key={p.name} href={p.url} target="_blank" rel="noopener noreferrer"
                style={{ display: 'block', padding: '12px 16px', background: 'var(--surface-3)', borderRadius: 10, textDecoration: 'none', color: 'var(--text-1)' }}>
                <div style={{ fontWeight: 600, marginBottom: 4 }}>{p.name}</div>
                <div style={{ fontSize: 11, color: 'var(--text-3)' }}>{p.note}</div>
              </a>
            ))}
          </div>
        </div>

        {/* JSON body format */}
        <div>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-3)', marginBottom: 6 }}>Formato JSON esperado (superset compatible con todos los proveedores)</div>
          <pre style={{ background: 'var(--surface-3)', borderRadius: 8, padding: '12px 16px', fontSize: 11, color: 'var(--text-2)', overflow: 'auto', margin: 0 }}>{`{
  "from": "Cliente <cliente@empresa.com>",  // o "sender"
  "subject": "Mi impresora no funciona",
  "body-plain": "Texto del email...",       // Mailgun
  "text": "Texto del email...",             // SendGrid/Postmark
  "stripped-text": "..."                    // Mailgun (sin firma)
}`}</pre>
        </div>
      </div>
    </Section>
  )
}

export default function SettingsPage() {
  const { user } = useAuth()
  const { t } = useAppLang()
  const visibleTabs = TABS.filter(tab => tab.roles.includes(user?.role))
  const [activeTab, setActiveTab] = useState(visibleTabs[0]?.id || 'general')

  return (
    <div style={{ padding: 32 }}>
      <PageHeader title={t('settings.title')} subtitle={t('settings.subtitle')} icon={<Settings size={18} />} />

      {/* Tab bar */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 28, flexWrap: 'wrap' }}>
        {visibleTabs.map(tab => (
          <button key={tab.id} onClick={() => setActiveTab(tab.id)}
            style={{ padding: '7px 14px', borderRadius: 8, border: `1px solid ${activeTab === tab.id ? 'var(--accent-glow)' : 'var(--surface-4)'}`, background: activeTab === tab.id ? 'var(--accent-muted)' : 'transparent', color: activeTab === tab.id ? 'var(--accent)' : 'var(--text-2)', fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit', whiteSpace: 'nowrap' }}>
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === 'general'      && <GeneralSection />}
      {activeTab === 'users'        && <UsersSection />}
      {activeTab === 'roles'        && <RolesSection />}
      {activeTab === 'alert-config' && <AlertConfigSection />}
      {activeTab === 'task-types'   && <TaskTypesSection />}
      {activeTab === 'templates'    && <TemplatesSection />}
      {activeTab === 'rates'        && <RateTablesSection />}
      {activeTab === 'vacations'    && <VacationSection />}
      {activeTab === 'depts'        && <DepartmentsSection />}
      {activeTab === 'offices'      && <OfficesSection />}
      {activeTab === 'numbering'    && <NumberingSection />}
      {activeTab === 'fields'       && <CustomFieldsSection />}
      {activeTab === 'idiomas'      && <IdiomasSection />}
      {activeTab === 'email-inbound'&& <EmailInboundSection />}
      {activeTab === 'log-level'    && <LogLevelSection />}
    </div>
  )
}
