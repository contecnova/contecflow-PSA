import { useState } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr } from '../utils/helpers'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../services/api'
import { Avatar, Button, Spinner, EmptyState, Modal } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import { useAppT } from '../i18n/AppLangContext'

const LEVELS = [
  { value: 'none',    label: 'Sin acceso',  color: 'var(--danger)', desc: 'Bloqueado explícitamente — no puede ver el proyecto' },
  { value: 'viewer',  label: 'Visor',       color: 'var(--text-2)', desc: 'Solo lectura — ve tareas y avance, sin datos financieros' },
  { value: 'member',  label: 'Miembro',     color: 'var(--accent)', desc: 'Puede imputar horas, crear y editar sus tareas' },
  { value: 'manager', label: 'Manager',     color: 'var(--warning)', desc: 'PM-level: edita el proyecto, ve finanzas' },
  { value: 'owner',   label: 'Propietario', color: 'var(--success)', desc: 'Control total incluyendo eliminar' },
]

const panelStyle = { background: 'var(--surface-2)', border: '1px solid #1e2d45', borderRadius: 12, padding: '20px 24px' }
const inputStyle = { width: '100%', background: 'var(--surface-3)', border: '1px solid #1e2d45', borderRadius: 8, padding: '8px 12px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
const labelStyle = { fontSize: 11, fontWeight: 600, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 5 }

function PermissionForm({ projectId, users, perm, onClose }) {
  const qc = useQueryClient()
  const toast = useToast()
  const isEdit = !!perm?.id
  const [form, setForm] = useState({
    user_id:            perm?.user_id            || '',
    level:              perm?.level              || 'member',
    can_see_financials: perm?.can_see_financials || false,
    can_see_rates:      perm?.can_see_rates      || false,
    can_export:         perm?.can_export         ?? true,
  })
  const set = k => v => setForm(f => ({ ...f, [k]: v }))
  const _selectedLevel = LEVELS.find(l => l.value === form.level)

  const { mutate, isPending } = useMutation({
    mutationFn: d => isEdit
      ? api.patch(`/permissions/${projectId}/${perm.id}`, d).then(r => r.data)
      : api.post(`/permissions/${projectId}`, d).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries(['permissions', projectId]); onClose() },
    onError: e => toast.error(extractErr(e, 'Error al guardar')),
  })

  return (
    <Modal open onClose={onClose} title={isEdit ? 'Editar permiso' : 'Añadir acceso al proyecto'}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {!isEdit && (
          <div>
            <label style={labelStyle}>Usuario</label>
            <select style={inputStyle} value={form.user_id} onChange={e => set('user_id')(e.target.value)}>
              <option value="">Selecciona un usuario...</option>
              {users.map(u => <option key={u.id} value={u.id}>{u.full_name} — {u.role}</option>)}
            </select>
          </div>
        )}
        {isEdit && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px', background: 'var(--surface-1)', borderRadius: 8 }}>
            <Avatar name={perm.user?.full_name} size={36} />
            <div>
              <div style={{ fontWeight: 500 }}>{perm.user?.full_name}</div>
              <div style={{ fontSize: 12, color: 'var(--text-2)' }}>{perm.user?.job_title || perm.user?.role}</div>
            </div>
          </div>
        )}

        <div>
          <label style={labelStyle}>Nivel de acceso</label>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {LEVELS.map(l => (
              <button key={l.value} onClick={() => set('level')(l.value)}
                style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px', borderRadius: 8, border: `1px solid ${form.level === l.value ? l.color + '50' : 'var(--surface-4)'}`, background: form.level === l.value ? l.color + '15' : 'transparent', cursor: 'pointer', fontFamily: 'inherit', textAlign: 'left' }}>
                <div style={{ width: 10, height: 10, borderRadius: '50%', background: l.color, flexShrink: 0 }} />
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, fontWeight: form.level === l.value ? 600 : 400, color: form.level === l.value ? l.color : 'var(--text-1)' }}>{l.label}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-2)' }}>{l.desc}</div>
                </div>
                {form.level === l.value && <span style={{ color: l.color }}>✓</span>}
              </button>
            ))}
          </div>
        </div>

        {['member','manager','owner'].includes(form.level) && (
          <div style={{ padding: '14px', background: 'var(--surface-1)', borderRadius: 8, border: '1px solid #1a2640' }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 10 }}>Permisos adicionales</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13 }}>
                <input type="checkbox" checked={form.can_see_financials} onChange={e => set('can_see_financials')(e.target.checked)} />
                <span>Ver datos financieros (costes, presupuesto, facturación)</span>
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13 }}>
                <input type="checkbox" checked={form.can_see_rates} onChange={e => set('can_see_rates')(e.target.checked)} />
                <span>Ver tarifas €/hora de los compañeros</span>
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13 }}>
                <input type="checkbox" checked={form.can_export} onChange={e => set('can_export')(e.target.checked)} />
                <span>Exportar datos del proyecto</span>
              </label>
            </div>
          </div>
        )}

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 4 }}>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={() => mutate(form)} disabled={isPending || (!isEdit && !form.user_id)} loading={isPending}>
            {isPending ? 'Guardando...' : isEdit ? 'Actualizar permiso' : 'Conceder acceso'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

export default function ProjectPermissionsPage() {
  const _t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [selectedProject, setSelectedProject] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [editingPerm, setEditingPerm] = useState(null)

  const { data: projects = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: () => api.get('/projects').then(r => Array.isArray(r.data) ? r.data : []).catch(() => []),
  })

  const { data: allUsers = [] } = useQuery({
    queryKey: ['users'],
    queryFn: () => api.get('/users').then(r => Array.isArray(r.data) ? r.data : []).catch(() => []),
  })

  const { data: perms = [], isLoading } = useQuery({
    queryKey: ['permissions', selectedProject],
    queryFn: () => api.get(`/permissions/${selectedProject}`).then(r => r.data).catch(() => []),
    enabled: !!selectedProject,
  })

  const { mutate: revoke } = useMutation({
    mutationFn: pid => api.delete(`/permissions/${selectedProject}/${pid}`),
    onSuccess: () => qc.invalidateQueries(['permissions', selectedProject]),
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const selectedProj = projects.find(p => p.id === selectedProject)
  const assignedUserIds = new Set(perms.map(p => p.user_id))
  const availableUsers = allUsers.filter(u => !assignedUserIds.has(u.id))

  const byLevel = Object.fromEntries(LEVELS.map(l => [l.value, perms.filter(p => p.level === l.value)]))

  return (
    <div style={{ padding: 32 }}>
      <PageHeader
        title={t(modulo.clave)}
        subtitle={_t('project_permissions.subtitle')}
        actions={selectedProject && (
          <Button onClick={() => { setEditingPerm(null); setShowForm(true) }}>+ Añadir acceso</Button>
        )}
      />

      {/* Selector de proyecto */}
      <div style={{ ...panelStyle, marginBottom: 24 }}>
        <label style={labelStyle}>Proyecto</label>
        <select value={selectedProject} onChange={e => setSelectedProject(e.target.value)}
          style={{ ...inputStyle, width: 360 }}>
          <option value="">Selecciona un proyecto...</option>
          {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        {selectedProject && (
          <div style={{ marginTop: 10, fontSize: 12, color: 'var(--text-3)' }}>
            Los permisos de proyecto sobrescriben el rol global del usuario. Un admin siempre tiene acceso completo independientemente de los permisos.
          </div>
        )}
      </div>

      {!selectedProject && (
        <EmptyState icon="🔐" title={t(modulo.clave)} description={t(modulo.clave)} />
      )}

      {selectedProject && isLoading && <Spinner />}

      {selectedProject && !isLoading && perms.length === 0 && (
        <div style={{ ...panelStyle, textAlign: 'center', padding: '48px 24px' }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>🔓</div>
          <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 8 }}>Sin permisos específicos</div>
          <div style={{ fontSize: 13, color: 'var(--text-2)', marginBottom: 20 }}>
            Todos los usuarios con rol PM o Admin pueden ver este proyecto.<br />
            Añade permisos específicos para restringir o ampliar el acceso individualmente.
          </div>
          <Button onClick={() => { setEditingPerm(null); setShowForm(true) }}>+ Añadir primer permiso</Button>
        </div>
      )}

      {selectedProject && perms.length > 0 && (
        <div>
          {/* Resumen */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 10, marginBottom: 20 }}>
            {LEVELS.map(l => (
              <div key={l.value} style={{ background: 'var(--surface-2)', border: `1px solid ${byLevel[l.value]?.length > 0 ? l.color + '40' : 'var(--surface-4)'}`, borderRadius: 10, padding: '12px 14px' }}>
                <div style={{ fontSize: 20, fontWeight: 700, color: l.color }}>{byLevel[l.value]?.length || 0}</div>
                <div style={{ fontSize: 11, color: 'var(--text-2)', marginTop: 2 }}>{l.label}</div>
              </div>
            ))}
          </div>

          {/* Tabla de permisos */}
          <div style={panelStyle}>
            <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 16 }}>
              {perms.length} {perms.length === 1 ? 'permiso' : 'permisos'} — {selectedProj?.name}
            </div>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #1e2d45' }}>
                  {['Usuario', 'Nivel de acceso', 'Finanzas', 'Tarifas', 'Exportar', 'Acciones'].map(h => (
                    <th key={h} style={{ textAlign: 'left', padding: '8px 12px', fontSize: 11, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {perms.map((perm, i) => {
                  const level = LEVELS.find(l => l.value === perm.level)
                  return (
                    <tr key={perm.id} style={{ borderBottom: '1px solid #1e2d45', background: i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.03)' }}>
                      <td style={{ padding: '10px 12px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                          <Avatar name={perm.user?.full_name} size={30} />
                          <div>
                            <div style={{ fontWeight: 500 }}>{perm.user?.full_name || perm.user_id}</div>
                            <div style={{ fontSize: 11, color: 'var(--text-2)' }}>{perm.user?.job_title || perm.user?.role}</div>
                          </div>
                        </div>
                      </td>
                      <td style={{ padding: '10px 12px' }}>
                        <span style={{ fontSize: 12, padding: '3px 10px', borderRadius: 6, background: (level?.color || 'var(--text-2)') + '20', color: level?.color || 'var(--text-2)', fontWeight: 500 }}>
                          {level?.label || perm.level}
                        </span>
                      </td>
                      {[perm.can_see_financials, perm.can_see_rates, perm.can_export].map((v, idx) => (
                        <td key={idx} style={{ padding: '10px 12px' }}>
                          <span style={{ color: v ? 'var(--success)' : 'var(--danger)', fontSize: 16 }}>{v ? '✓' : '✕'}</span>
                        </td>
                      ))}
                      <td style={{ padding: '10px 12px' }}>
                        <div style={{ display: 'flex', gap: 8 }}>
                          <button onClick={() => { setEditingPerm(perm); setShowForm(true) }}
                            style={{ background: 'none', border: '1px solid #1e2d45', borderRadius: 6, padding: '4px 10px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 11 }}>
                            Editar
                          </button>
                          <button onClick={() => { openConfirmGlobal({ message: `¿Revocar acceso de ${perm.user?.full_name}?`, onConfirm: () => revoke(perm.id), danger: true }) }}
                            style={{ background: 'none', border: '1px solid #ff475730', borderRadius: 6, padding: '4px 10px', color: 'var(--danger)', cursor: 'pointer', fontSize: 11 }}>
                            Revocar
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          {/* Leyenda de niveles */}
          <div style={{ ...panelStyle, marginTop: 16 }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 12 }}>Niveles de acceso</div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 10 }}>
              {LEVELS.map(l => (
                <div key={l.value}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                    <div style={{ width: 8, height: 8, borderRadius: '50%', background: l.color }} />
                    <span style={{ fontSize: 12, fontWeight: 600, color: l.color }}>{l.label}</span>
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-3)', lineHeight: 1.4 }}>{l.desc}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {showForm && (
        <PermissionForm
          projectId={selectedProject}
          users={availableUsers}
          perm={editingPerm}
          onClose={() => { setShowForm(false); setEditingPerm(null) }}
        />
      )}
    </div>
  )
}
