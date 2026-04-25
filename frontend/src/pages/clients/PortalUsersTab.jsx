import { useState } from 'react'
import { useToast } from '../../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../../services/api'
import { Button, EmptyState, Modal } from '../../components/ui'
import { extractErr } from '../../utils/helpers'

const panel = { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12 }
const inp = { background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '8px 12px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', width: '100%', boxSizing: 'border-box' }
const lbl = { fontSize: 11, fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', display: 'block', marginBottom: 5 }

export function PortalUsersTab({ cid, clientName }) {
  const toast = useToast()
  const qc = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const [showReset, setShowReset] = useState(null)
  const [newPassword, setNewPassword] = useState('')
  const [createdCreds, setCreatedCreds] = useState(null)
  const [editUser, setEditUser] = useState(null)
  const [editForm, setEditForm] = useState({})
  const [form, setForm] = useState({
    full_name: '', email: '', job_title: '', phone: '',
    project_ids: [], password: '', confirm_password: '',
    can_approve_deliverables: true, can_request_changes: true,
    can_view_budget: false, can_view_team: false,
  })

  const { data: users = [] } = useQuery({
    queryKey: ['portal-clients-org', cid],
    queryFn: () => api.get('/portal/clients', { params: { client_org_id: cid } }).then(r => r.data),
  })
  const { data: clientDetail } = useQuery({
    queryKey: ['client-detail-projects', cid],
    queryFn: () => api.get(`/clients/${cid}`).then(r => r.data),
  })
  const projects = clientDetail?.projects || []
  const projectLabelById = new Map(projects.map(p => [p.id, `${p.code} — ${p.name}`]))

  const { mutate: add, isPending } = useMutation({
    mutationFn: d => api.post('/portal/clients', d).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries(['portal-clients-org', cid])
      setShowAdd(false)
      setCreatedCreds({ email: form.email, password: form.password })
      setForm({ full_name: '', email: '', job_title: '', phone: '', project_ids: [], password: '', confirm_password: '', can_approve_deliverables: true, can_request_changes: true, can_view_budget: false, can_view_team: false })
    },
    onError: e => toast.error(extractErr(e, 'Error al crear usuario')),
  })

  const { mutate: toggle } = useMutation({
    mutationFn: ({ id, active }) => api.patch(`/portal/clients/${id}`, { is_active: active }),
    onSuccess: () => qc.invalidateQueries(['portal-clients-org', cid]),
    onError: e => toast.error(extractErr(e, 'Error'))
  })

  const { mutate: resetPwd, isPending: resetting } = useMutation({
    mutationFn: ({ id, password }) => api.patch(`/portal/clients/${id}`, { password }),
    onSuccess: () => { qc.invalidateQueries(['portal-clients-org', cid]); setShowReset(null); setNewPassword('') },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const { mutate: updateUser, isPending: updating } = useMutation({
    mutationFn: ({ id, data }) => api.patch(`/portal/clients/${id}`, data).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries(['portal-clients-org', cid])
      setEditUser(null)
      toast.success('Usuario actualizado correctamente')
    },
    onError: e => toast.error(extractErr(e, 'Error al actualizar usuario')),
  })

  const openEdit = (u) => {
    setEditUser(u)
    setEditForm({
      full_name: u.full_name || '',
      email: u.email || '',
      job_title: u.job_title || '',
      phone: u.phone || '',
      project_ids: Array.isArray(u.project_ids) ? u.project_ids : (u.project_id ? [u.project_id] : []),
      can_approve_deliverables: u.can_approve_deliverables ?? true,
      can_request_changes: u.can_request_changes ?? true,
      can_view_budget: u.can_view_budget ?? false,
      can_view_team: u.can_view_team ?? false,
    })
  }

  const portalUrl = `${window.location.origin}/portal`

  return (
    <div>
      <div style={{ background: 'var(--accent-muted)', border: '1px solid #00d4ff20', borderRadius: 10, padding: '14px 18px', marginBottom: 20 }}>
        <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 6, color: 'var(--accent)' }}>🌐 Cómo accede el cliente al portal</div>
        <div style={{ fontSize: 12, color: 'var(--text-2)', lineHeight: 1.7 }}>
          1. Crea un usuario con email y contraseña en este formulario.<br/>
          2. Comparte las credenciales con el cliente (email + contraseña).<br/>
          3. El cliente accede en: <strong style={{ color: 'var(--text-1)' }}>{portalUrl}</strong><br/>
          4. Desde el portal puede ver proyectos, abrir tickets de Service Desk, aprobar entregables y más.
        </div>
        <button onClick={() => navigator.clipboard.writeText(portalUrl)}
          style={{ marginTop: 10, background: 'transparent', border: '1px solid #00d4ff30', borderRadius: 6, padding: '4px 12px', color: 'var(--accent)', cursor: 'pointer', fontSize: 11, fontFamily: 'inherit' }}>
          📋 Copiar URL del portal
        </button>
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <div style={{ fontSize: 13, color: 'var(--text-2)' }}>{users.length} usuario(s) de portal activos</div>
        <Button onClick={() => setShowAdd(true)} size="sm">+ Crear usuario de portal</Button>
      </div>

      {users.length === 0
        ? <EmptyState icon="🔐" title="Sin usuarios de portal" description="Crea el primer acceso del cliente al portal" />
        : users.map(u => {
          const assignedProjects = (u.project_ids || []).map(pid => projectLabelById.get(pid)).filter(Boolean)
          return (
          <div key={u.id} style={{ ...panel, padding: '14px 18px', marginBottom: 10, opacity: u.is_active ? 1 : 0.5 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
                <div style={{ width: 38, height: 38, borderRadius: 10, background: u.is_active ? 'var(--accent-muted)' : 'var(--surface-4)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 17, fontWeight: 800, color: u.is_active ? 'var(--accent)' : 'var(--text-2)' }}>
                  {u.full_name?.charAt(0)?.toUpperCase() || '?'}
                </div>
                <div>
                  <div style={{ fontSize: 14, fontWeight: 700 }}>{u.full_name}
                    {!u.is_active && <span style={{ marginLeft: 6, fontSize: 10, color: 'var(--danger)', background: 'var(--danger-bg)', padding: '1px 6px', borderRadius: 4 }}>Inactivo</span>}
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text-2)' }}>
                    📧 {u.email}{u.job_title && ` · ${u.job_title}`}
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 2 }}>
                    {assignedProjects.length > 0 ? `📁 Proyectos: ${assignedProjects.join(' · ')}` : '🔓 Sin proyecto — acceso general al Service Desk'}
                    {u.last_login && <span style={{ marginLeft: 10 }}>· Último acceso: <strong style={{ color: 'var(--text-2)' }}>{u.last_login.slice(0, 10)}</strong></span>}
                    {!u.last_login && <span style={{ marginLeft: 10, color: 'rgba(248,113,113,0.50)' }}>· Nunca ha accedido</span>}
                  </div>
                </div>
              </div>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                {u.can_approve_deliverables && <span style={{ fontSize: 10, padding: '2px 6px', borderRadius: 4, background: 'var(--success-bg)', color: 'var(--success)' }}>✓ Aprueba</span>}
                {u.can_view_budget && <span style={{ fontSize: 10, padding: '2px 6px', borderRadius: 4, background: 'var(--warning-bg)', color: 'var(--warning)' }}>💰 Budget</span>}
                {u.can_view_team && <span style={{ fontSize: 10, padding: '2px 6px', borderRadius: 4, background: 'var(--purple-bg)', color: 'var(--purple)' }}>👥 Equipo</span>}
              </div>
            </div>
            <div style={{ display: 'flex', gap: 8, marginTop: 10, paddingTop: 10, borderTop: '1px solid var(--surface-4)' }}>
              <button onClick={() => openEdit(u)}
                style={{ fontSize: 11, padding: '4px 12px', borderRadius: 6, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--success)', cursor: 'pointer', fontFamily: 'inherit' }}>
                ✏️ Editar
              </button>
              <button onClick={() => setShowReset({ id: u.id, email: u.email })}
                style={{ fontSize: 11, padding: '4px 12px', borderRadius: 6, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--accent)', cursor: 'pointer', fontFamily: 'inherit' }}>
                🔑 Cambiar contraseña
              </button>
              <button onClick={() => toggle({ id: u.id, active: !u.is_active })}
                style={{ fontSize: 11, padding: '4px 12px', borderRadius: 6, border: '1px solid var(--surface-4)', background: 'transparent', color: u.is_active ? 'var(--danger)' : 'var(--success)', cursor: 'pointer', fontFamily: 'inherit' }}>
                {u.is_active ? '⏸ Suspender acceso' : '▶ Reactivar acceso'}
              </button>
              <button onClick={() => {
                const text = `Acceso al portal de ${clientName || 'Clarive'}\n\nURL: ${portalUrl}\nEmail: ${u.email}\n\nContacta con tu gestor para obtener tu contraseña.`
                navigator.clipboard.writeText(text)
                toast.info('📋 Info de acceso copiada al portapapeles')
              }} style={{ fontSize: 11, padding: '4px 12px', borderRadius: 6, border: '1px solid var(--surface-4)', background: 'transparent', color: 'var(--text-2)', cursor: 'pointer', fontFamily: 'inherit' }}>
                📋 Copiar datos de acceso
              </button>
            </div>
          </div>
          )
        })
      }

      {createdCreds && (
        <Modal open title="Credenciales creadas" onClose={() => setCreatedCreds(null)} width={480}>
          <div style={{ background: 'var(--success-bg)', border: '1px solid #00e5a030', borderRadius: 10, padding: '18px 20px', marginBottom: 16 }}>
            <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 12, color: 'var(--success)' }}>Credenciales de acceso al portal</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: 12, color: 'var(--text-2)' }}>URL del portal:</span>
                <strong style={{ fontSize: 13, color: 'var(--accent)' }}>{portalUrl}</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: 12, color: 'var(--text-2)' }}>Email:</span>
                <strong style={{ fontSize: 13 }}>{createdCreds.email}</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: 12, color: 'var(--text-2)' }}>Contraseña:</span>
                <strong style={{ fontSize: 13, fontFamily: 'monospace', background: 'var(--surface-4)', padding: '3px 10px', borderRadius: 6 }}>{createdCreds.password}</strong>
              </div>
            </div>
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-2)', marginBottom: 16 }}>⚠️ Guarda estas credenciales — la contraseña no se puede recuperar, solo restablecer.</div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button onClick={() => {
              navigator.clipboard.writeText(`Portal: ${portalUrl}\nEmail: ${createdCreds.email}\nContraseña: ${createdCreds.password}`)
              toast.success('Copiado al portapapeles')
            }} style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '7px 16px', color: 'var(--accent)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}>📋 Copiar todo</button>
            <Button onClick={() => setCreatedCreds(null)}>Entendido</Button>
          </div>
        </Modal>
      )}

      {showReset && (
        <Modal open title="Cambiar contrasena" onClose={() => { setShowReset(null); setNewPassword('') }} width={420}>
          <div style={{ marginBottom: 6, fontSize: 13, color: 'var(--text-2)' }}>Usuario: <strong style={{ color: 'var(--text-1)' }}>{showReset.email}</strong></div>
          <div style={{ marginBottom: 16 }}>
            <label style={lbl}>Nueva contraseña</label>
            <input type="password" value={newPassword} onChange={e => setNewPassword(e.target.value)}
              style={inp} placeholder="Nueva contrasena" aria-label="Nueva contrasena" />
          </div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button onClick={() => { setShowReset(null); setNewPassword('') }} style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '7px 16px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}>Cancelar</button>
            <Button onClick={() => resetPwd({ id: showReset.id, password: newPassword })} disabled={newPassword.length < 6 || resetting}>
              {resetting ? '⟳ Guardando...' : '✓ Cambiar contraseña'}
            </Button>
          </div>
        </Modal>
      )}

      {editUser && (
        <Modal open title={`✏️ Editar: ${editUser.full_name}`} onClose={() => setEditUser(null)} width={560}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 14 }}>
            <div>
              <label style={lbl}>Nombre completo *</label>
              <input value={editForm.full_name} onChange={e => setEditForm(f => ({ ...f, full_name: e.target.value }))} style={inp} />
            </div>
            <div>
              <label style={lbl}>Email *</label>
              <input type="email" value={editForm.email} onChange={e => setEditForm(f => ({ ...f, email: e.target.value }))} style={inp} />
            </div>
            <div>
              <label style={lbl}>Cargo</label>
              <input value={editForm.job_title} onChange={e => setEditForm(f => ({ ...f, job_title: e.target.value }))} style={inp} placeholder="Cargo" aria-label="Cargo" />
            </div>
            <div>
              <label style={lbl}>Teléfono</label>
              <input value={editForm.phone} onChange={e => setEditForm(f => ({ ...f, phone: e.target.value }))} style={inp} placeholder="Telefono" aria-label="Telefono" />
            </div>
            <div style={{ gridColumn: '1 / -1' }}>
              <label style={lbl}>Proyectos asociados</label>
              <select multiple value={editForm.project_ids || []}
                onChange={e => setEditForm(f => ({ ...f, project_ids: Array.from(e.target.selectedOptions).map(opt => opt.value).filter(Boolean) }))}
                style={{ ...inp, height: 38 + Math.min(projects.length, 4) * 28 }}>
                {projects.map(p => (
                  <option key={p.id} value={p.id}>{p.code} — {p.name}</option>
                ))}
              </select>
              <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 4 }}>Puedes asignar acceso a varios proyectos al mismo usuario.</div>
            </div>
          </div>

          <div style={{ ...panel, padding: '12px 16px', marginBottom: 14 }}>
            <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 10, color: 'var(--text-2)',
              textTransform: 'uppercase', letterSpacing: '0.05em' }}>Permisos en el portal</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
              {[
                { key: 'can_approve_deliverables', label: 'Puede aprobar entregables', desc: 'Validar o rechazar entregables del proyecto' },
                { key: 'can_request_changes',      label: '↩ Puede solicitar cambios',   desc: 'Enviar solicitudes de cambio' },
                { key: 'can_view_budget',           label: 'Puede ver presupuesto',    desc: 'Ver consumo vs presupuesto' },
                { key: 'can_view_team',             label: 'Puede ver equipo',          desc: 'Ver miembros del equipo asignado' },
              ].map(p => (
                <label key={p.key} style={{
                  display: 'flex', gap: 8, alignItems: 'flex-start', cursor: 'pointer',
                  background: editForm[p.key] ? 'var(--accent-muted)' : 'transparent',
                  border: `1px solid ${editForm[p.key] ? 'var(--accent-glow)' : 'var(--surface-4)'}`,
                  borderRadius: 8, padding: '8px 10px',
                }}>
                  <input type="checkbox" checked={!!editForm[p.key]}
                    onChange={e => setEditForm(f => ({ ...f, [p.key]: e.target.checked }))}
                    style={{ accentColor: 'var(--accent)', marginTop: 2, flexShrink: 0 }} />
                  <div>
                    <div style={{ fontSize: 12, fontWeight: 600,
                      color: editForm[p.key] ? 'var(--text-1)' : 'var(--text-2)' }}>{p.label}</div>
                    <div style={{ fontSize: 10, color: 'var(--text-3)' }}>{p.desc}</div>
                  </div>
                </label>
              ))}
            </div>
          </div>

          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button onClick={() => setEditUser(null)}
              style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 8,
                padding: '7px 16px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}>
              Cancelar
            </button>
            <Button
              loading={updating}
              disabled={!editForm.full_name || !editForm.email || updating}
              onClick={() => updateUser({ id: editUser.id, data: {
                full_name:                editForm.full_name,
                email:                    editForm.email,
                job_title:                editForm.job_title || null,
                phone:                    editForm.phone || null,
                project_ids:              editForm.project_ids || [],
                can_approve_deliverables: editForm.can_approve_deliverables,
                can_request_changes:      editForm.can_request_changes,
                can_view_budget:          editForm.can_view_budget,
                can_view_team:            editForm.can_view_team,
              }})}>
              {updating ? '⟳ Guardando...' : '💾 Guardar cambios'}
            </Button>
          </div>
        </Modal>
      )}

      {showAdd && (
        <Modal open title="Nuevo usuario de portal" onClose={() => setShowAdd(false)} width={560}>
          <div style={{ background: 'var(--purple-bg)', border: '1px solid #7c3aed30', borderRadius: 8, padding: '10px 14px', marginBottom: 16, fontSize: 12, color: 'var(--text-2)' }}>
            🔐 Crea las credenciales que el cliente usará para entrar en <strong style={{ color: 'var(--text-1)' }}>{portalUrl}</strong>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 14 }}>
            <div><label style={lbl}>Nombre completo *</label><input value={form.full_name} onChange={e => setForm(f => ({ ...f, full_name: e.target.value }))} style={inp} /></div>
            <div><label style={lbl}>Email * (será el usuario de login)</label><input type="email" value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} style={inp} placeholder="Email de acceso" aria-label="Email de acceso" /></div>
            <div><label style={lbl}>Contraseña *</label><input type="password" value={form.password} onChange={e => setForm(f => ({ ...f, password: e.target.value }))} style={inp} placeholder="Contrasena temporal" aria-label="Contrasena temporal" /></div>
            <div><label style={lbl}>Confirmar contraseña</label><input type="password" value={form.confirm_password} onChange={e => setForm(f => ({ ...f, confirm_password: e.target.value }))} style={inp} /></div>
            <div><label style={lbl}>Cargo</label><input value={form.job_title} onChange={e => setForm(f => ({ ...f, job_title: e.target.value }))} style={inp} placeholder="Cargo" aria-label="Cargo" /></div>
            <div>
              <label style={lbl}>Asociar a proyectos (opcional)</label>
              <select multiple value={form.project_ids} onChange={e => {
                const options = Array.from(e.target.selectedOptions).map(opt => opt.value).filter(Boolean)
                setForm(f => ({ ...f, project_ids: options }))
              }} style={{ ...inp, height: 38 + Math.min(projects.length, 4) * 28 }}>
                {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
              </select>
            </div>
          </div>
          <div style={{ ...panel, padding: '12px 16px', marginBottom: 14 }}>
            <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 10, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Permisos en el portal</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
              {[
                { key: 'can_approve_deliverables', label: 'Puede aprobar entregables', desc: 'Validar o rechazar entregables del proyecto' },
                { key: 'can_request_changes', label: '↩ Puede solicitar cambios', desc: 'Enviar solicitudes de cambio' },
                { key: 'can_view_budget', label: 'Puede ver presupuesto', desc: 'Ver consumo vs presupuesto' },
                { key: 'can_view_team', label: 'Puede ver equipo', desc: 'Ver miembros del equipo asignado' },
              ].map(p => (
                <label key={p.key} style={{ display: 'flex', gap: 8, alignItems: 'flex-start', cursor: 'pointer',
                  background: form[p.key] ? 'var(--accent-muted)' : 'transparent', border: `1px solid ${form[p.key] ? 'var(--accent-glow)' : 'var(--surface-4)'}`,
                  borderRadius: 8, padding: '8px 10px' }}>
                  <input type="checkbox" checked={form[p.key]} onChange={e => setForm(f => ({ ...f, [p.key]: e.target.checked }))}
                    style={{ accentColor: 'var(--accent)', marginTop: 2, flexShrink: 0 }} />
                  <div>
                    <div style={{ fontSize: 12, fontWeight: 600, color: form[p.key] ? 'var(--text-1)' : 'var(--text-2)' }}>{p.label}</div>
                    <div style={{ fontSize: 10, color: 'var(--text-3)' }}>{p.desc}</div>
                  </div>
                </label>
              ))}
            </div>
          </div>
          {form.password && form.confirm_password && form.password !== form.confirm_password && (
            <div style={{ background: 'var(--danger-bg)', border: '1px solid #ff475730', borderRadius: 8, padding: '8px 12px', marginBottom: 12, fontSize: 12, color: 'var(--danger)' }}>
              ✗ Las contraseñas no coinciden
            </div>
          )}
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button onClick={() => setShowAdd(false)} style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '7px 16px', color: 'var(--text-2)', cursor: 'pointer', fontSize: 12, fontFamily: 'inherit' }}>Cancelar</button>
            <Button onClick={() => add({ ...form, client_org_id: cid, project_ids: form.project_ids && form.project_ids.length > 0 ? form.project_ids : undefined })}
              disabled={!form.full_name || !form.email || !form.password || form.password !== form.confirm_password || isPending}>
              {isPending ? '⟳ Creando...' : '🔐 Crear acceso al portal'}
            </Button>
          </div>
        </Modal>
      )}
    </div>
  )
}
