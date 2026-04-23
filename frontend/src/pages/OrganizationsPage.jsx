/**
 * OrganizationsPage — Gestión multi-tenant de organizaciones
 */
import { useState } from 'react'
import { extractErr } from '../utils/helpers'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../services/api'
import { Button, Modal, Spinner, EmptyState, Confirm } from '../components/ui'
import { UserSelect } from '../components/ui/EntitySelect'
import PageHeader from '../components/layout/PageHeader'
import { Building2 } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'

const fs = { width:'100%', background:'var(--surface-2)', border:'.5px solid var(--surface-4)', borderRadius:8, padding:'9px 12px', color:'var(--text-1)', fontSize:13, outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
const ls = { fontSize:11, fontWeight:500, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'.07em', display:'block', marginBottom:5 }
const card = { background:'var(--surface-1)', border:'.5px solid var(--surface-4)', borderRadius:12 }

const PLAN_COLORS = { starter:'var(--text-2)', pro:'var(--accent)', enterprise:'var(--success)' }

export default function OrganizationsPage() {
  // ...existing code...
  const [removingUserId, setRemovingUserId] = useState(null)
    // Mutación para eliminar usuario de la organización
    const { mutate: removeUser, isPending: isRemoving } = useMutation({
      mutationFn: ({ orgId, userId }) => api.delete(`/organizations/${orgId}/remove-user/${userId}`),
      onSuccess: () => {
        qc.invalidateQueries(['org-detail', selected]);
        setRemovingUserId(null)
        toast.success('Usuario eliminado')
      },
      onError: e => toast.error(extractErr(e, 'Error al eliminar usuario')),
    })
  // Estado para asignar usuario
  const [showAssignUser, setShowAssignUser] = useState(false)
  const [assignUserId, setAssignUserId] = useState('')
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [showCreate, setShowCreate] = useState(false)
  const [showEdit, setShowEdit] = useState(false)
  const [selected, setSelected] = useState(null)
  const [form, setForm] = useState({ name:'', slug:'', plan:'starter', max_users:25, max_projects:100, admin_email:'', timezone:'Europe/Madrid' })
  const [editForm, setEditForm] = useState(null)

  const { data: orgs = [], isLoading } = useQuery({ queryKey:['orgs'], queryFn:() => api.get('/organizations').then(r=>r.data) })
  const { data: detail } = useQuery({ queryKey:['org-detail', selected], queryFn:() => api.get(`/organizations/${selected}`).then(r=>r.data), enabled:!!selected })
  // Todos los usuarios activos
  const { data: allUsers = [] } = useQuery({ queryKey:['users'], queryFn:() => api.get('/users').then(r=>r.data) })
  // Mutación para asignar usuario
  const { mutate: assignUser, isPending: isAssigning } = useMutation({
    mutationFn: ({ orgId, userId }) => api.post(`/organizations/${orgId}/assign-user`, { user_id: userId }),
    onSuccess: () => {
      qc.invalidateQueries(['org-detail', selected]);
      setShowAssignUser(false)
      setAssignUserId('')
      toast.success('Usuario asignado')
    },
    onError: e => toast.error(extractErr(e, 'Error al asignar usuario')),
  })

  const { mutate: create, isPending } = useMutation({
    mutationFn: d => api.post('/organizations', d),
    onSuccess: () => { qc.invalidateQueries(['orgs']); setShowCreate(false) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: toggle } = useMutation({
    mutationFn: ({ id, is_active }) => api.patch(`/organizations/${id}`, { is_active }),
    onSuccess: () => qc.invalidateQueries(['orgs']),
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: update, isPending: isUpdating } = useMutation({
    mutationFn: ({ id, data }) => api.patch(`/organizations/${id}`, data),
    onSuccess: () => { qc.invalidateQueries(['orgs']); qc.invalidateQueries(['org-detail', selected]); setShowEdit(false) },
    onError: e => toast.error(extractErr(e, 'Error al actualizar')),
  })

  // Rellena editForm con los datos actuales al abrir modal de edición
  const openEdit = () => {
    if (detail) {
      setEditForm({
        name: detail.name || '',
        plan: detail.plan || 'starter',
        max_users: detail.max_users || 25,
        max_projects: detail.max_projects || 100,
        admin_email: detail.admin_email || '',
        timezone: detail.timezone || 'Europe/Madrid',
        locale: detail.locale || '',
        primary_color: detail.primary_color || '',
      })
      setShowEdit(true)
    }
  }

  return (
    <div style={{ padding:32 }}>
      <PageHeader icon={<Building2 size={18} />} title={t('organizations.title')} subtitle={t('organizations.subtitle')} />
      <div style={{ background:'var(--accent-muted)', border:'.5px solid rgba(0,212,255,0.25)', borderRadius:10, padding:'12px 16px', marginBottom:24, fontSize:13, color:'var(--accent)' }}>
        Cada organización tiene sus propios usuarios, proyectos y datos aislados. Esta arquitectura permite ofrecer Clarive como SaaS multi-empresa.
      </div>
      <div style={{ display:'flex', justifyContent:'flex-end', marginBottom:16 }}>
        <Button onClick={() => setShowCreate(true)}>+ Nueva organización</Button>
      </div>

      <div style={{ display:'grid', gridTemplateColumns: selected ? '1fr 360px' : '1fr', gap:20 }}>
        <div>
          {isLoading ? <Spinner /> : orgs.length === 0 ? (
            <EmptyState icon="🏢" title="Sin organizaciones" description="Crea la primera organizacion para gestionar entornos aislados" />
          ) : (
            <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
              {orgs.map(o => (
                <div key={o.id} onClick={() => setSelected(selected===o.id?null:o.id)}
                  role="button" tabIndex={0}
                  onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSelected(selected===o.id?null:o.id) } }}
                  style={{ ...card, padding:'16px 20px', cursor:'pointer', opacity: o.is_active ? 1 : 0.6, border:selected===o.id?'.5px solid rgba(0,212,255,0.25)':'var(--surface-4) .5px solid' }}>
                  <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center' }}>
                    <div>
                      <div style={{ display:'flex', gap:10, alignItems:'center', marginBottom:4 }}>
                        <span style={{ fontSize:14, fontWeight:500 }}>{o.name}</span>
                        <span style={{ fontSize:11, padding:'1px 6px', borderRadius:4, background:'var(--surface-2)', color: PLAN_COLORS[o.plan] || 'var(--text-2)', fontWeight:500 }}>{o.plan}</span>
                        {!o.is_active && <span style={{ fontSize:11, padding:'1px 6px', borderRadius:4, background:'var(--danger-bg)', color:'var(--danger)' }}>Inactiva</span>}
                      </div>
                      <div style={{ fontSize:12, color:'var(--text-2)' }}>
                        {o.slug} · {o.user_count} usuarios · {o.project_count} proyectos · {o.admin_email || '—'}
                      </div>
                    </div>
                    <div style={{ display:'flex', gap:8 }}>
                      <span style={{ fontSize:12, color:'var(--text-2)' }}>{o.created_at}</span>
                      <button onClick={e => { e.stopPropagation(); toggle({ id:o.id, is_active:!o.is_active }) }}
                        style={{ background:'transparent', border:'.5px solid var(--surface-4)', borderRadius:6, padding:'3px 10px', color:'var(--text-2)', cursor:'pointer', fontSize:11, fontFamily:'inherit' }}>
                        {o.is_active ? 'Suspender' : 'Activar'}
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {selected && detail && (
          <div style={{ ...card, padding:'20px 22px', position:'sticky', top:80, alignSelf:'start' }}>
            <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:14 }}>
              <div style={{ fontSize:14, fontWeight:500 }}>{detail.name}</div>
              <Button size="sm" onClick={openEdit}>Editar</Button>
            </div>
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:10, marginBottom:16 }}>
              {[['Plan', detail.plan], ['Usuarios', `${detail.users?.length}/${detail.max_users}`], ['Zona horaria', detail.timezone], ['Idioma', detail.locale]].map(([k,v]) => (
                <div key={k} style={{ background:'var(--surface-2)', borderRadius:8, padding:'10px 12px' }}>
                  <div style={{ fontSize:10, color:'var(--text-3)', marginBottom:2 }}>{k}</div>
                  <div style={{ fontSize:12, fontWeight:500 }}>{v}</div>
                </div>
              ))}
            </div>
            <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:10 }}>
              <span style={{ fontSize:13, fontWeight:500 }}>Usuarios ({detail.users?.length})</span>
              <Button size="sm" onClick={() => setShowAssignUser(true)}>Asignar usuario</Button>
            </div>
            {(detail.users || []).length === 0 && <div style={{ color:'var(--text-3)', fontSize:12, marginBottom:8 }}>No hay usuarios asignados.</div>}
            {(detail.users || []).map((u, idx, arr) => {
              const isLast = arr.length === 1
              return (
                <div key={u.id} style={{ display:'flex', justifyContent:'space-between', alignItems:'center', padding:'6px 0', borderBottom:'.5px solid var(--surface-4)', fontSize:12 }}>
                  <span>{u.full_name}</span>
                  <span style={{ color:'var(--text-2)' }}>{u.role}</span>
                  <Button
                    size="xs"
                    variant="danger"
                    style={{marginLeft:8, opacity: isLast ? 0.5 : 1, pointerEvents: isLast ? 'none' : 'auto'}}
                    disabled={isLast}
                    title={isLast ? 'No puedes quitar el último usuario de la organización' : 'Quitar usuario'}
                    onClick={()=>setRemovingUserId(u.id)}
                  >Quitar</Button>
                </div>
              )
            })}
                      {removingUserId && detail && (
                        <Confirm
                          open
                          title="No puedes quitar el ultimo usuario"
                          description="Asigna otra persona antes de eliminar el ultimo usuario de la organizacion"
                          onCancel={()=>setRemovingUserId(null)}
                          onConfirm={()=>removeUser({ orgId: detail.id, userId: removingUserId })}
                          loading={isRemoving}
                        />
                      )}
                {showAssignUser && detail && (
                  <Modal open title="Asignar usuario" onClose={() => setShowAssignUser(false)} width={420}>
                    <div style={{ display:'flex', flexDirection:'column', gap:18 }}>
                      <div>
                        <label style={ls}>Usuario</label>
                        <UserSelect
                          value={assignUserId}
                          onChange={id => setAssignUserId(id)}
                          placeholder="Buscar usuario activo"
                          style={fs}
                          filterFn={u => u.is_active !== false && !(detail.users || []).some(du => du.id === u.id)}
                        />
                      </div>
                      <div style={{ color:'var(--danger)', fontSize:12, minHeight:18 }}>
                        {assignUserId === '' ? '' : (() => {
                          const user = allUsers.find(u => u.id === assignUserId)
                          if (user && user.is_active === false) return 'No puedes asignar usuarios inactivos.'
                          if ((detail.users || []).some(u => u.id === assignUserId)) return 'Este usuario ya está asignado.'
                          return ''
                        })()}
                      </div>
                      <div style={{ display:'flex', justifyContent:'flex-end', gap:10 }}>
                        <Button variant="secondary" onClick={()=>setShowAssignUser(false)}>Cancelar</Button>
                        <Button
                          onClick={()=>assignUser({ orgId: detail.id, userId: assignUserId })}
                          disabled={!assignUserId || isAssigning || (assignUserId && allUsers.find(u => u.id === assignUserId)?.is_active === false) || (assignUserId && (detail.users || []).some(u => u.id === assignUserId))}
                        >{isAssigning ? 'Asignando...' : 'Asignar'}</Button>
                      </div>
                    </div>
                  </Modal>
                )}
          </div>
        )}
      </div>

      {showCreate && (
        <Modal open title="Nueva organizacion" onClose={() => setShowCreate(false)} width={520}>
          <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:12 }}>
              <div><label style={ls}>Nombre</label><input value={form.name} onChange={e=>setForm(f=>({...f,name:e.target.value}))} style={fs} /></div>
              <div><label style={ls}>Slug (identificador único)</label><input value={form.slug} onChange={e=>setForm(f=>({...f,slug:e.target.value.toLowerCase().replace(/\s+/g,'-')}))} style={fs} /></div>
            </div>
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr 1fr', gap:12 }}>
              <div><label style={ls}>Plan</label>
                <select value={form.plan} onChange={e=>setForm(f=>({...f,plan:e.target.value}))} style={fs}>
                  {['starter','pro','enterprise'].map(p => <option key={p} value={p}>{p}</option>)}
                </select>
              </div>
              <div><label style={ls}>Máx. usuarios</label><input type="number" value={form.max_users} onChange={e=>setForm(f=>({...f,max_users:+e.target.value}))} style={fs} /></div>
              <div><label style={ls}>Máx. proyectos</label><input type="number" value={form.max_projects} onChange={e=>setForm(f=>({...f,max_projects:+e.target.value}))} style={fs} /></div>
            </div>
            <div><label style={ls}>Email del admin</label><input value={form.admin_email} onChange={e=>setForm(f=>({...f,admin_email:e.target.value}))} style={fs} /></div>
            <div style={{ display:'flex', justifyContent:'flex-end', gap:10 }}>
              <Button variant="secondary" onClick={()=>setShowCreate(false)}>Cancelar</Button>
              <Button onClick={()=>create(form)} disabled={isPending||!form.name||!form.slug}>{isPending?'Creando...':'Crear'}</Button>
            </div>
          </div>
        </Modal>
      )}

      {showEdit && editForm && (
        <Modal open title="Editar organizacion" onClose={() => setShowEdit(false)} width={520}>
          <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:12 }}>
              <div><label style={ls}>Nombre</label><input value={editForm.name} onChange={e=>setEditForm(f=>({...f,name:e.target.value}))} style={fs} /></div>
              {/* El slug no se puede editar */}
              <div><label style={ls}>Slug</label><input value={detail.slug} disabled style={{...fs, background:'#f5f5f5'}} /></div>
            </div>
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr 1fr', gap:12 }}>
              <div><label style={ls}>Plan</label>
                <select value={editForm.plan} onChange={e=>setEditForm(f=>({...f,plan:e.target.value}))} style={fs}>
                  {['starter','pro','enterprise'].map(p => <option key={p} value={p}>{p}</option>)}
                </select>
              </div>
              <div><label style={ls}>Máx. usuarios</label><input type="number" value={editForm.max_users} onChange={e=>setEditForm(f=>({...f,max_users:+e.target.value}))} style={fs} /></div>
              <div><label style={ls}>Máx. proyectos</label><input type="number" value={editForm.max_projects} onChange={e=>setEditForm(f=>({...f,max_projects:+e.target.value}))} style={fs} /></div>
            </div>
            <div><label style={ls}>Email del admin</label><input value={editForm.admin_email} onChange={e=>setEditForm(f=>({...f,admin_email:e.target.value}))} style={fs} /></div>
            <div style={{ display:'flex', justifyContent:'flex-end', gap:10 }}>
              <Button variant="secondary" onClick={()=>setShowEdit(false)}>Cancelar</Button>
              <Button onClick={()=>update({ id: selected, data: editForm })} disabled={isUpdating||!editForm.name}>{isUpdating?'Guardando...':'Guardar'}</Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}
