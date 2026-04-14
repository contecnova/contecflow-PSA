/**
 * OrganizationsPage — Gestión multi-tenant de organizaciones
 */
import { useState } from 'react'
import { extractErr } from '../utils/helpers'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../services/api'
import { Button, Modal, Spinner, EmptyState } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import { useAppT } from '../i18n/AppLangContext'

const fs = { width:'100%', background:'var(--color-background-secondary)', border:'.5px solid var(--color-border-secondary)', borderRadius:8, padding:'9px 12px', color:'var(--color-text-primary)', fontSize:13, outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
const ls = { fontSize:11, fontWeight:500, color:'var(--color-text-secondary)', textTransform:'uppercase', letterSpacing:'.07em', display:'block', marginBottom:5 }
const card = { background:'var(--color-background-primary)', border:'.5px solid var(--color-border-tertiary)', borderRadius:12 }

const PLAN_COLORS = { starter:'var(--color-text-secondary)', pro:'var(--color-text-info)', enterprise:'var(--color-text-success)' }

export default function OrganizationsPage() {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [showCreate, setShowCreate] = useState(false)
  const [selected, setSelected] = useState(null)
  const [form, setForm] = useState({ name:'', slug:'', plan:'starter', max_users:25, max_projects:100, admin_email:'', timezone:'Europe/Madrid' })

  const { data: orgs = [], isLoading } = useQuery({ queryKey:['orgs'], queryFn:() => api.get('/organizations').then(r=>r.data) })
  const { data: detail } = useQuery({ queryKey:['org-detail', selected], queryFn:() => api.get(`/organizations/${selected}`).then(r=>r.data), enabled:!!selected })

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

  return (
    <div style={{ padding:32 }}>
      <PageHeader title={t('organizations.title')} subtitle="Multi-tenancy — cada organización es un espacio de datos aislado" />
      <div style={{ background:'var(--color-background-info)', border:'.5px solid var(--color-border-info)', borderRadius:10, padding:'12px 16px', marginBottom:24, fontSize:13, color:'var(--color-text-info)' }}>
        Cada organización tiene sus propios usuarios, proyectos y datos aislados. Esta arquitectura permite ofrecer Clarive como SaaS multi-empresa.
      </div>
      <div style={{ display:'flex', justifyContent:'flex-end', marginBottom:16 }}>
        <Button onClick={() => setShowCreate(true)}>+ Nueva organización</Button>
      </div>

      <div style={{ display:'grid', gridTemplateColumns: selected ? '1fr 360px' : '1fr', gap:20 }}>
        <div>
          {isLoading ? <Spinner /> : orgs.length === 0 ? (
            <EmptyState icon="🏢" title="Sin organizaciones" description="Crea la primera organización para empezar" />
          ) : (
            <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
              {orgs.map(o => (
                <div key={o.id} onClick={() => setSelected(selected===o.id?null:o.id)}
                  style={{ ...card, padding:'16px 20px', cursor:'pointer', opacity: o.is_active ? 1 : 0.6, border:selected===o.id?'.5px solid var(--color-border-info)':'var(--color-border-tertiary) .5px solid' }}>
                  <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center' }}>
                    <div>
                      <div style={{ display:'flex', gap:10, alignItems:'center', marginBottom:4 }}>
                        <span style={{ fontSize:14, fontWeight:500 }}>{o.name}</span>
                        <span style={{ fontSize:11, padding:'1px 6px', borderRadius:4, background:'var(--color-background-secondary)', color: PLAN_COLORS[o.plan] || 'var(--color-text-secondary)', fontWeight:500 }}>{o.plan}</span>
                        {!o.is_active && <span style={{ fontSize:11, padding:'1px 6px', borderRadius:4, background:'var(--color-background-danger)', color:'var(--color-text-danger)' }}>Inactiva</span>}
                      </div>
                      <div style={{ fontSize:12, color:'var(--color-text-secondary)' }}>
                        {o.slug} · {o.user_count} usuarios · {o.project_count} proyectos · {o.admin_email || '—'}
                      </div>
                    </div>
                    <div style={{ display:'flex', gap:8 }}>
                      <span style={{ fontSize:12, color:'var(--color-text-secondary)' }}>{o.created_at}</span>
                      <button onClick={e => { e.stopPropagation(); toggle({ id:o.id, is_active:!o.is_active }) }}
                        style={{ background:'transparent', border:'.5px solid var(--color-border-secondary)', borderRadius:6, padding:'3px 10px', color:'var(--color-text-secondary)', cursor:'pointer', fontSize:11, fontFamily:'inherit' }}>
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
            <div style={{ fontSize:14, fontWeight:500, marginBottom:14 }}>{detail.name}</div>
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:10, marginBottom:16 }}>
              {[['Plan', detail.plan], ['Usuarios', `${detail.users?.length}/${detail.max_users}`], ['Zona horaria', detail.timezone], ['Idioma', detail.locale]].map(([k,v]) => (
                <div key={k} style={{ background:'var(--color-background-secondary)', borderRadius:8, padding:'10px 12px' }}>
                  <div style={{ fontSize:10, color:'var(--color-text-tertiary)', marginBottom:2 }}>{k}</div>
                  <div style={{ fontSize:12, fontWeight:500 }}>{v}</div>
                </div>
              ))}
            </div>
            <div style={{ fontSize:13, fontWeight:500, marginBottom:10 }}>Usuarios ({detail.users?.length})</div>
            {(detail.users || []).slice(0,8).map(u => (
              <div key={u.id} style={{ display:'flex', justifyContent:'space-between', padding:'6px 0', borderBottom:'.5px solid var(--color-border-tertiary)', fontSize:12 }}>
                <span>{u.full_name}</span>
                <span style={{ color:'var(--color-text-secondary)' }}>{u.role}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {showCreate && (
        <Modal open title="Nueva organización" onClose={() => setShowCreate(false)} width={520}>
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
    </div>
  )
}
