import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { openConfirmGlobal } from '../../context/ConfirmContext'
import { extractErr } from '../../utils/helpers'
import { useToast } from '../../context/ToastContext'
import { useAppT } from '../../i18n/AppLangContext'
import { Button, Spinner, EmptyState, Modal } from '../../components/ui'
import { COLOR } from '../../constants/theme'
import { sdCatalogApi, sdSlaPoliciesApi, sdGroupsApi, sdTemplatesApi, sdCannedApi, sdAnnouncementsApi, usersApi } from '../../services/api'
import { PRIORITY_LABEL, PBadge } from './sdUtils'
import { RoutingRules } from './QueueAndRoutingSections'

// ── Catalog Config ────────────────────────────────────────────────────────────
function CatalogConfig() {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [showNewCat, setShowNewCat] = useState(false)
  const [showNewSvc, setShowNewSvc] = useState(false)

  const { data: catalog = [], isLoading } = useQuery({
    queryKey: ['sd-catalog'],
    queryFn: () => sdCatalogApi.get().then(r => r.data),
  })

  const [editingCat, setEditingCat] = useState(null)
  const [editingSvc, setEditingSvc] = useState(null)

  const { mutate: createCat, isPending: creatingCat } = useMutation({
    mutationFn: d => sdCatalogApi.createCategory(d),
    onSuccess: () => { qc.invalidateQueries({queryKey:['sd-catalog']}); setShowNewCat(false); toast.success(t('service_desk.cat_new_title')) },
    onError: e => toast.error(extractErr(e, 'Error'))
  })
  const { mutate: updateCat } = useMutation({
    mutationFn: ({id, ...d}) => sdCatalogApi.updateCategory(id, d),
    onSuccess: () => { qc.invalidateQueries({queryKey:['sd-catalog']}); setEditingCat(null); toast.success(t('service_desk.cat_edit_title')) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: deleteCat } = useMutation({
    mutationFn: id => sdCatalogApi.deleteCategory(id),
    onSuccess: () => { qc.invalidateQueries({queryKey:['sd-catalog']}); toast.success(t('common.delete')) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: createSvc, isPending: creatingSvc } = useMutation({
    mutationFn: d => sdCatalogApi.createService(d),
    onSuccess: () => { qc.invalidateQueries({queryKey:['sd-catalog']}); setShowNewSvc(false); toast.success(t('service_desk.svc_new_title')) },
    onError: e => toast.error(extractErr(e, 'Error'))
  })
  const { mutate: updateSvc } = useMutation({
    mutationFn: ({id, ...d}) => sdCatalogApi.updateService(id, d),
    onSuccess: () => { qc.invalidateQueries({queryKey:['sd-catalog']}); setEditingSvc(null); toast.success(t('service_desk.svc_edit_title')) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: deleteSvc } = useMutation({
    mutationFn: id => sdCatalogApi.deleteService(id),
    onSuccess: () => { qc.invalidateQueries({queryKey:['sd-catalog']}); toast.success(t('common.delete')) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const IS = { width:'100%', background:'var(--surface-3)', border:'1px solid var(--surface-4)',
    borderRadius:8, padding:'9px 13px', color:'var(--text-1)', fontSize: "var(--text-base)",
    outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
  const LS = { fontSize: "var(--text-xs)", fontWeight:600, color:'var(--text-2)', display:'block',
    marginBottom:5, textTransform:'uppercase', letterSpacing:'0.06em' }

  return (
    <div>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:20 }}>
        <div style={{ fontSize: "var(--text-sm)", color:'var(--text-3)' }}>{t('service_desk.catalog_empty_desc')}</div>
        <div style={{ display:'flex', gap:8 }}>
          <Button variant="secondary" onClick={() => setShowNewSvc(true)} disabled={catalog.length===0}>+ {t('service_desk.svc_new_title')}</Button>
          <Button onClick={() => setShowNewCat(true)}>+ {t('service_desk.cat_new_title')}</Button>
        </div>
      </div>

      {isLoading ? <Spinner /> :
       catalog.length === 0 ? <EmptyState icon="📋" title={t('service_desk.catalog_empty')} description={t('service_desk.catalog_empty_desc')} /> :
      <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
        {catalog.map(cat => (
          <div key={cat.id} style={{ background:'var(--surface-2)', border:'1px solid var(--surface-4)', borderRadius:12, overflow:'hidden' }}>
            <div style={{ padding:'14px 18px', background:'var(--surface-1)', borderBottom:'1px solid var(--surface-4)',
              display:'flex', alignItems:'center', gap:10 }}>
              <span style={{ fontSize: "var(--text-lg-em)" }}>{cat.icon || '📁'}</span>
              <span style={{ fontSize: "var(--text-md)", fontWeight:600, color:'var(--text-1)' }}>{cat.name}</span>
              {cat.description && <span style={{ fontSize: "var(--text-sm)", color:'var(--text-3)' }}>— {cat.description}</span>}
              <span style={{ marginLeft:'auto', fontSize: "var(--text-xs)", color:'var(--text-3)' }}>{cat.services?.length || 0} servicios</span>
              <div style={{ display:'flex', gap:6, marginLeft:8 }}>
                <button onClick={() => setEditingCat(cat)}
                  style={{ padding:'3px 8px', borderRadius:5, border:'1px solid var(--surface-4)', background:'transparent', color:'var(--accent)', fontSize: "var(--text-xs)", cursor:'pointer', fontFamily:'inherit' }}>✏ Editar</button>
                <button onClick={() => { openConfirmGlobal({ message: '¿Eliminar categoría y todos sus servicios?', onConfirm: () => deleteCat(cat.id), danger: true }) }}
                  style={{ padding:'3px 8px', borderRadius:5, border:`1px solid ${COLOR.danger}30`, background:'transparent', color:COLOR.danger, fontSize: "var(--text-xs)", cursor:'pointer', fontFamily:'inherit' }}>🗑 Eliminar</button>
              </div>
            </div>
            {cat.services?.length > 0 && (
              <table style={{ width:'100%', borderCollapse:'collapse' }}>
                <tbody>
                  {cat.services.map(svc => (
                    <tr key={svc.id} style={{ borderBottom:'1px solid var(--surface-4)' }}>
                      <td style={{ padding:'10px 18px', fontSize: "var(--text-base)", color:'var(--text-1)', fontWeight:500 }}>{svc.name}</td>
                      <td style={{ padding:'10px 8px', fontSize: "var(--text-xs)", color:'var(--text-2)' }}>{svc.ticket_type?.replace(/_/g,' ')}</td>
                      <td style={{ padding:'10px 8px' }}><PBadge v={svc.default_priority} /></td>
                      <td style={{ padding:'10px 8px', fontSize: "var(--text-xs)", color:'var(--text-2)' }}>R:{svc.sla_response_hours}h / Res:{svc.sla_resolution_hours}h</td>
                      <td style={{ padding:'10px 8px', fontSize: "var(--text-xs)", color:'var(--text-3)' }}>{svc.requires_approval ? '🔐' : ''}</td>
                      <td style={{ padding:'6px 12px' }}>
                        <div style={{ display:'flex', gap:6 }}>
                          <button onClick={() => setEditingSvc({...svc, category_id: cat.id})}
                            style={{ padding:'3px 8px', borderRadius:5, border:'1px solid var(--surface-4)', background:'transparent', color:'var(--accent)', fontSize: "var(--text-xs)", cursor:'pointer', fontFamily:'inherit' }}>✏</button>
                          <button onClick={() => { openConfirmGlobal({ message: '¿Eliminar servicio?', onConfirm: () => deleteSvc(svc.id), danger: true }) }}
                            style={{ padding:'3px 8px', borderRadius:5, border:`1px solid ${COLOR.danger}30`, background:'transparent', color:COLOR.danger, fontSize: "var(--text-xs)", cursor:'pointer', fontFamily:'inherit' }}>🗑</button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        ))}
      </div>}

      {showNewCat && (
        <NewCategoryModal onClose={() => setShowNewCat(false)}
          onSave={d => createCat(d)} isPending={creatingCat} IS={IS} LS={LS} />
      )}
      {editingCat && (
        <NewCategoryModal
          initial={editingCat}
          onClose={() => setEditingCat(null)}
          onSave={d => updateCat({id: editingCat.id, ...d})}
          isPending={false} IS={IS} LS={LS} />
      )}
      {showNewSvc && (
        <NewServiceModal catalog={catalog} onClose={() => setShowNewSvc(false)}
          onSave={d => createSvc(d)} isPending={creatingSvc} IS={IS} LS={LS} />
      )}
      {editingSvc && (
        <NewServiceModal
          catalog={catalog} initial={editingSvc}
          onClose={() => setEditingSvc(null)}
          onSave={d => updateSvc({id: editingSvc.id, ...d})}
          isPending={false} IS={IS} LS={LS} />
      )}
    </div>
  )
}

function NewCategoryModal({ onClose, onSave, isPending, IS, LS, initial }) {
  const t = useAppT()
  const [form, setForm] = useState({
    name: initial?.name || '', description: initial?.description || '',
    icon: initial?.icon || '📁', color: initial?.color || '#4f8ef7'
  })
  const set = k => e => setForm(f => ({...f, [k]: e.target.value}))
  return (
    <Modal open title={initial ? t('service_desk.cat_edit_title') : t('service_desk.cat_new_title')} onClose={onClose}>
      <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
        <div style={{ display:'grid', gridTemplateColumns:'1fr auto auto', gap:10 }}>
          <div><label style={LS}>{t('common.name')} *</label><input value={form.name} onChange={set('name')} style={IS} /></div>
        </div>
          <div><label style={LS}>Icon</label><input value={form.icon} onChange={set('icon')} style={{...IS, width:60, textAlign:'center'}} /></div>
          <div><label style={LS}>Color</label><input type="color" value={/^#[0-9a-fA-F]{6}$/.test(form.color) ? form.color : '#4f8ef7'} onChange={set('color')} style={{...IS, width:60, padding:'4px'}} /></div>
        <div style={{ display:'flex', justifyContent:'flex-end', gap:10 }}>
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={() => onSave(form)} disabled={isPending || !form.name} loading={isPending}>{initial ? t('common.save') : t('common.new')}</Button>
        </div>
      </div>
    </Modal>
  )
}

function NewServiceModal({ catalog, onClose, onSave, isPending, IS, LS, initial }) {
  const t = useAppT()
  const [form, setForm] = useState({
    name: initial?.name || '',
    category_id: initial?.category_id || catalog[0]?.id || '',
    ticket_type: initial?.ticket_type || 'service_request',
    default_priority: initial?.default_priority || 'p3_medium',
    sla_response_hours: initial?.sla_response_hours || 4,
    sla_resolution_hours: initial?.sla_resolution_hours || 24,
    requires_approval: initial?.requires_approval || false,
    is_visible_to_clients: initial?.is_visible_to_clients ?? true,
  })
  const set = k => e => setForm(f => ({...f, [k]: e.target.type==='checkbox' ? e.target.checked : e.target.value}))
  return (
    <Modal open title={initial ? t('service_desk.svc_edit_title') : t('service_desk.svc_new_title')} onClose={onClose}>
      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:14 }}>
        <div style={{ gridColumn:'1/-1' }}><label style={LS}>{t('common.name')} *</label><input value={form.name} onChange={set('name')} style={IS} /></div>
        <div>
          <label style={LS}>{t('service_desk.svc_ticket_type')}</label>
          <select value={form.category_id} onChange={set('category_id')} style={IS}>
            {catalog.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
        <div>
          <label style={LS}>{t('service_desk.svc_ticket_type')}</label>
          <select value={form.ticket_type} onChange={set('ticket_type')} style={IS}>
            {['incident','service_request','change','question'].map(tk => <option key={tk} value={tk}>{tk.replace(/_/g,' ')}</option>)}
          </select>
        </div>
        <div>
          <label style={LS}>{t('service_desk.svc_default_priority')}</label>
          <select value={form.default_priority} onChange={set('default_priority')} style={IS}>
            {['p1_critical','p2_high','p3_medium','p4_low'].map(p => <option key={p} value={p}>{PRIORITY_LABEL[p]}</option>)}
          </select>
        </div>
        <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:8 }}>
          <div><label style={LS}>{t('service_desk.sla_response_h')}</label><input type="number" value={form.sla_response_hours} onChange={set('sla_response_hours')} style={IS} /></div>
          <div><label style={LS}>{t('service_desk.sla_resolution_h')}</label><input type="number" value={form.sla_resolution_hours} onChange={set('sla_resolution_hours')} style={IS} /></div>
        </div>
        <div style={{ display:'flex', alignItems:'center', gap:10 }}>
          <input type="checkbox" id="req_appr" checked={form.requires_approval} onChange={set('requires_approval')} />
          <label htmlFor="req_appr" style={{ fontSize: "var(--text-base)", color:'var(--text-1)', cursor:'pointer' }}>{t('service_desk.svc_requires_approval')}</label>
        </div>
        <div style={{ gridColumn:'1/-1', display:'flex', justifyContent:'flex-end', gap:10 }}>
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={() => onSave(form)} disabled={isPending || !form.name} loading={isPending}>{initial ? t('common.save') : t('service_desk.svc_new_title')}</Button>
        </div>
      </div>
    </Modal>
  )
}

// ── SLA Config ────────────────────────────────────────────────────────────────
function SLAConfig() {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [showNew, setShowNew] = useState(false)

  const { data: policies = [], isLoading } = useQuery({
    queryKey: ['sd-sla-policies'],
    queryFn: () => sdSlaPoliciesApi.list().then(r => r.data),
  })
  const [editing, setEditing] = useState(null)
  const { mutate: create, isPending } = useMutation({
    mutationFn: d => sdSlaPoliciesApi.create(d),
    onSuccess: () => { qc.invalidateQueries({queryKey:['sd-sla-policies']}); setShowNew(false); toast.success(t('service_desk.sla_created')) },
    onError: e => toast.error(extractErr(e, 'Error'))
  })
  const { mutate: update } = useMutation({
    mutationFn: ({id, ...d}) => sdSlaPoliciesApi.update(id, d),
    onSuccess: () => { qc.invalidateQueries({queryKey:['sd-sla-policies']}); setEditing(null); toast.success(t('service_desk.sla_updated')) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: remove } = useMutation({
    mutationFn: id => sdSlaPoliciesApi.delete(id),
    onSuccess: () => { qc.invalidateQueries({queryKey:['sd-sla-policies']}); toast.success(t('service_desk.sla_deleted')) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const IS = { width:'100%', background:'var(--surface-3)', border:'1px solid var(--surface-4)',
    borderRadius:8, padding:'9px 13px', color:'var(--text-1)', fontSize: "var(--text-base)",
    outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
  const LS = { fontSize: "var(--text-xs)", fontWeight:600, color:'var(--text-2)', display:'block', marginBottom:5, textTransform:'uppercase', letterSpacing:'0.06em' }

  return (
    <div>
      <div style={{ display:'flex', justifyContent:'space-between', marginBottom:20 }}>
        <div style={{ fontSize: "var(--text-sm)", color:'var(--text-3)' }}>{t('service_desk.sla_empty_desc')}</div>
        <Button onClick={() => setShowNew(true)}>+ {t('service_desk.sla_new_title')}</Button>
      </div>

      {isLoading ? <Spinner /> :
       policies.length === 0 ? <EmptyState icon="⏱" title={t('service_desk.sla_empty')} description={t('service_desk.sla_empty_desc')} /> :
      <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
        {policies.map(p => (
          <div key={p.id} style={{ background:'var(--surface-2)', border:`1px solid ${p.is_default ? 'var(--accent)' : 'var(--surface-4)'}`, borderRadius:12, padding:20 }}>
            <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:16 }}>
              <span style={{ fontSize: "var(--text-md)", fontWeight:600, color:'var(--text-1)' }}>{p.name}</span>
              {p.is_default && <span style={{ fontSize: "var(--text-2xs)", background:'var(--accent-muted)', color:'var(--accent)', padding:'2px 8px', borderRadius:4, fontWeight: 600 }}>{t('service_desk.sla_default_policy').toUpperCase()}</span>}
              {p.business_hours_only && <span style={{ fontSize: "var(--text-2xs)", background:'var(--surface-4)', color:'var(--text-2)', padding:'2px 8px', borderRadius:4 }}>{t('service_desk.sla_business_hours')}</span>}
              <div style={{ marginLeft:'auto', display:'flex', gap:8 }}>
                <button onClick={() => setEditing(p)}
                  style={{ padding:'3px 10px', borderRadius:6, border:'1px solid var(--surface-4)', background:'transparent', color:'var(--accent)', fontSize: "var(--text-xs)", cursor:'pointer', fontFamily:'inherit' }}>✏ Editar</button>
                <button onClick={() => { openConfirmGlobal({ message: '¿Eliminar esta política SLA?', onConfirm: () => remove(p.id), danger: true }) }}
                  style={{ padding:'3px 10px', borderRadius:6, border:`1px solid ${COLOR.danger}30`, background:'transparent', color:COLOR.danger, fontSize: "var(--text-xs)", cursor:'pointer', fontFamily:'inherit' }}>🗑 Eliminar</button>
              </div>
            </div>
            <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:10 }}>
              {[['P1 Crítico', 'p1', COLOR.danger], ['P2 Alto', 'p2', 'var(--orange)'], ['P3 Medio', 'p3', COLOR.warning], ['P4 Bajo', 'p4', COLOR.text2]].map(([label, key, color]) => (
                <div key={key} style={{ background:'var(--surface-1)', borderRadius:8, padding:12, borderTop:`3px solid ${color}` }}>
                  <div style={{ fontSize: "var(--text-xs)", fontWeight:700, color, marginBottom:8 }}>{label}</div>
                  <div style={{ fontSize: "var(--text-sm)", color:'var(--text-2)' }}>
                    <div>Resp: <strong style={{ color:'var(--text-1)' }}>{p[`${key}_response_hours`]}h</strong></div>
                    <div>Res: <strong style={{ color:'var(--text-1)' }}>{p[`${key}_resolution_hours`]}h</strong></div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>}

      {showNew && (
        <Modal open title={t('service_desk.sla_new_title')} onClose={() => setShowNew(false)} size="lg">
          <NewSLAForm IS={IS} LS={LS} onSave={d => create(d)} isPending={isPending} onClose={() => setShowNew(false)} />
        </Modal>
      )}
      {editing && (
        <Modal open title={t('service_desk.sla_edit_title')} onClose={() => setEditing(null)} size="lg">
          <NewSLAForm IS={IS} LS={LS} initial={editing}
            onSave={d => update({id: editing.id, ...d})}
            isPending={false} onClose={() => setEditing(null)} />
        </Modal>
      )}
    </div>
  )
}

function NewSLAForm({ IS, LS, onSave, isPending, onClose, initial }) {
  const t = useAppT()
  const [form, setForm] = useState({
    name: initial?.name || '', description: initial?.description || '',
    is_default: initial?.is_default || false, business_hours_only: initial?.business_hours_only || false,
    p1_response_hours: initial?.p1_response_hours ?? 1, p1_resolution_hours: initial?.p1_resolution_hours ?? 4,
    p2_response_hours: initial?.p2_response_hours ?? 4, p2_resolution_hours: initial?.p2_resolution_hours ?? 8,
    p3_response_hours: initial?.p3_response_hours ?? 8, p3_resolution_hours: initial?.p3_resolution_hours ?? 24,
    p4_response_hours: initial?.p4_response_hours ?? 24, p4_resolution_hours: initial?.p4_resolution_hours ?? 72,
  })
  const set = k => e => setForm(f => ({...f, [k]: e.target.type==='checkbox' ? e.target.checked : e.target.value}))
  return (
    <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:14 }}>
      <div style={{ gridColumn:'1/-1' }}><label style={LS}>{t('common.name')} *</label><input value={form.name} onChange={set('name')} style={IS} /></div>
      {[['P1 Crítico', 'p1'], ['P2 Alto', 'p2'], ['P3 Medio', 'p3'], ['P4 Bajo', 'p4']].map(([label, key]) => (
        <div key={key} style={{ background:'var(--surface-1)', borderRadius:10, padding:14 }}>
          <div style={{ fontSize: "var(--text-sm)", fontWeight:700, color:'var(--text-2)', marginBottom:10 }}>{label}</div>
          <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:8 }}>
            <div><label style={LS}>{t('service_desk.sla_response_h')}</label><input type="number" value={form[`${key}_response_hours`]} onChange={set(`${key}_response_hours`)} style={IS} /></div>
            <div><label style={LS}>{t('service_desk.sla_resolution_h')}</label><input type="number" value={form[`${key}_resolution_hours`]} onChange={set(`${key}_resolution_hours`)} style={IS} /></div>
          </div>
        </div>
      ))}
      <div style={{ gridColumn:'1/-1', display:'flex', gap:20, alignItems:'center' }}>
        <label style={{ display:'flex', gap:8, alignItems:'center', fontSize: "var(--text-base)", color:'var(--text-1)', cursor:'pointer' }}>
          <input type="checkbox" checked={form.is_default} onChange={set('is_default')} />
          {t('service_desk.sla_default_policy')}
        </label>
        <label style={{ display:'flex', gap:8, alignItems:'center', fontSize: "var(--text-base)", color:'var(--text-1)', cursor:'pointer' }}>
          <input type="checkbox" checked={form.business_hours_only} onChange={set('business_hours_only')} />
          {t('service_desk.sla_business_only')}
        </label>
      </div>
      <div style={{ gridColumn:'1/-1', display:'flex', justifyContent:'flex-end', gap:10 }}>
        <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
        <Button onClick={() => onSave(form)} disabled={isPending || !form.name} loading={isPending}>{initial ? t('common.save') : t('service_desk.sla_new_title')}</Button>
      </div>
    </div>
  )
}

// ── Groups Config ─────────────────────────────────────────────────────────────
function GroupsConfig() {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [showNew, setShowNew] = useState(false)

  const { data: groups = [], isLoading } = useQuery({
    queryKey: ['sd-groups'],
    queryFn: () => sdGroupsApi.list().then(r => r.data),
  })
  const { data: users = [] } = useQuery({
    queryKey: ['users'],
    queryFn: () => usersApi.list().then(r => r.data),
  })
  const [editing, setEditing] = useState(null)
  const { mutate: createGroup, isPending } = useMutation({
    mutationFn: d => sdGroupsApi.create(d),
    onSuccess: () => { qc.invalidateQueries({queryKey:['sd-groups']}); setShowNew(false); toast.success(t('service_desk.groups_created')) },
    onError: e => toast.error(extractErr(e, 'Error'))
  })
  const { mutate: updateGroup } = useMutation({
    mutationFn: ({id, ...d}) => sdGroupsApi.update(id, d),
    onSuccess: () => { qc.invalidateQueries({queryKey:['sd-groups']}); setEditing(null); toast.success(t('service_desk.groups_updated')) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: deleteGroup } = useMutation({
    mutationFn: id => sdGroupsApi.delete(id),
    onSuccess: () => { qc.invalidateQueries({queryKey:['sd-groups']}); toast.success(t('service_desk.groups_deleted')) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: addMember } = useMutation({
    mutationFn: ({gid, uid}) => sdGroupsApi.addMember(gid, uid),
    onSuccess: () => qc.invalidateQueries({queryKey:['sd-groups']}),
    onError: e => toast.error(extractErr(e, 'Error'))
  })
  const { mutate: removeMember } = useMutation({
    mutationFn: ({gid, uid}) => sdGroupsApi.removeMember(gid, uid),
    onSuccess: () => qc.invalidateQueries({queryKey:['sd-groups']}),
    onError: e => toast.error(extractErr(e, 'Error'))
  })

  const IS = { width:'100%', background:'var(--surface-3)', border:'1px solid var(--surface-4)',
    borderRadius:8, padding:'9px 13px', color:'var(--text-1)', fontSize: "var(--text-base)",
    outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
  const LS = { fontSize: "var(--text-xs)", fontWeight:600, color:'var(--text-2)', display:'block', marginBottom:5, textTransform:'uppercase', letterSpacing:'0.06em' }

  return (
    <div>
      <div style={{ display:'flex', justifyContent:'space-between', marginBottom:20 }}>
        <div style={{ fontSize: "var(--text-sm)", color:'var(--text-3)' }}>{t('service_desk.groups_empty_desc')}</div>
        <Button onClick={() => setShowNew(true)}>+ {t('service_desk.groups_new_title')}</Button>
      </div>

      {isLoading ? <Spinner /> :
       groups.length === 0 ? <EmptyState icon="👥" title={t('service_desk.groups_empty')} description={t('service_desk.groups_empty_desc')} /> :
      <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
        {groups.map(g => {
          const memberIds = new Set((g.members || []).map(m => m.id))
          const available = (users || []).filter(u => !memberIds.has(u.id))
          return (
            <div key={g.id} style={{ background:'var(--surface-2)', border:'1px solid var(--surface-4)', borderRadius:12, padding:20 }}>
              <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:14 }}>
                <div style={{ display:'flex', alignItems:'center', gap:8 }}>
                  <span style={{ fontSize: "var(--text-md)", fontWeight:600, color:'var(--text-1)' }}>{g.name}</span>
                  <span style={{ fontSize: "var(--text-xs)", background:'var(--surface-4)', color:'var(--text-2)', padding:'2px 8px', borderRadius:4 }}>{g.support_level?.toUpperCase() || 'L1'}</span>
                </div>
                <div style={{ display:'flex', gap:8, alignItems:'center' }}>
                  {available.length > 0 && (
                    <select defaultValue="" onChange={e => { if(e.target.value) addMember({gid:g.id, uid:e.target.value}); e.target.value='' }}
                      style={{ ...IS, width:'auto', fontSize: "var(--text-sm)" }}>
                      <option value="" disabled>+ Añadir miembro</option>
                      {available.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
                    </select>
                  )}
                  <button onClick={() => setEditing(g)}
                    style={{ padding:'4px 10px', borderRadius:6, border:'1px solid var(--surface-4)', background:'transparent', color:'var(--accent)', fontSize: "var(--text-xs)", cursor:'pointer', fontFamily:'inherit', whiteSpace:'nowrap' }}>✏ Editar</button>
                  <button onClick={() => { openConfirmGlobal({ message: `¿Eliminar el grupo "${g.name}"?`, onConfirm: () => deleteGroup(g.id), danger: true }) }}
                    style={{ padding:'4px 10px', borderRadius:6, border:`1px solid ${COLOR.danger}30`, background:'transparent', color:COLOR.danger, fontSize: "var(--text-xs)", cursor:'pointer', fontFamily:'inherit', whiteSpace:'nowrap' }}>🗑 Eliminar</button>
                </div>
              </div>
              {g.description && <div style={{ fontSize: "var(--text-sm)", color:'var(--text-3)', marginBottom:12 }}>{g.description}</div>}
              <div style={{ display:'flex', gap:8, flexWrap:'wrap' }}>
                {(g.members || []).map(m => (
                  <div key={m.id} style={{ display:'flex', alignItems:'center', gap:6, background:'var(--surface-1)',
                    border:'1px solid var(--surface-4)', borderRadius:20, padding:'4px 12px' }}>
                    <span style={{ fontSize: "var(--text-sm)", color:'var(--text-1)' }}>{m.full_name}</span>
                    {m.is_lead && <span style={{ fontSize: "var(--text-2xs)", color:COLOR.accent }}>★</span>}
                    <button onClick={() => removeMember({gid:g.id, uid:m.id})}
                      style={{ background:'none', border:'none', color:'var(--text-4)', cursor:'pointer',
                        fontSize: "var(--text-md)", padding:'0 0 0 4px', lineHeight:1 }}>×</button>
                  </div>
                ))}
                {(!g.members || g.members.length === 0) &&
                  <span style={{ fontSize: "var(--text-sm)", color:'var(--text-4)' }}>{t('service_desk.groups_no_members')}</span>}
              </div>
            </div>
          )
        })}
      </div>}

      {showNew && (
        <Modal open title={t('service_desk.groups_new_title')} onClose={() => setShowNew(false)}>
          <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
            <NewGroupForm IS={IS} LS={LS} onSave={createGroup} isPending={isPending} onClose={() => setShowNew(false)} />
          </div>
        </Modal>
      )}
      {editing && (
        <Modal open title={t('service_desk.groups_edit_title')} onClose={() => setEditing(null)}>
          <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
            <NewGroupForm IS={IS} LS={LS} initial={editing}
              onSave={d => updateGroup({id: editing.id, ...d})}
              isPending={false} onClose={() => setEditing(null)} />
          </div>
        </Modal>
      )}
    </div>
  )
}

function NewGroupForm({ IS, LS, onSave, isPending, onClose, initial }) {
  const t = useAppT()
  const [form, setForm] = useState({
    name: initial?.name || '', description: initial?.description || '',
    support_level: initial?.support_level || 'l1'
  })
  const set = k => e => setForm(f => ({...f, [k]: e.target.value}))
  return (
    <>
      <div><label style={LS}>{t('common.name')} *</label><input value={form.name} onChange={set('name')} style={IS} /></div>
      <div><label style={LS}>{t('service_desk.groups_support_level')}</label>
        <select value={form.support_level} onChange={set('support_level')} style={IS}>
          {[['l1','L1 — Soporte básico'],['l2','L2 — Soporte técnico'],['l3','L3 — Experto / Desarrollo']].map(([v,l]) =>
            <option key={v} value={v}>{l}</option>)}
        </select>
      </div>
      <div><label style={LS}>{t('common.description')}</label><input value={form.description} onChange={set('description')} style={IS} /></div>
      <div style={{ display:'flex', justifyContent:'flex-end', gap:10 }}>
        <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
        <Button onClick={() => onSave(form)} disabled={isPending || !form.name} loading={isPending}>{initial ? t('common.save') : t('service_desk.groups_new_title')}</Button>
      </div>
    </>
  )
}

// ── Templates Config ──────────────────────────────────────────────────────────
function TemplatesConfig() {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [showNew, setShowNew] = useState(false)

  const { data: templates = [], isLoading } = useQuery({
    queryKey: ['sd-templates'],
    queryFn: () => sdTemplatesApi.list().then(r => r.data),
  })
  const [editing, setEditing] = useState(null)
  const { mutate: create, isPending } = useMutation({
    mutationFn: d => sdTemplatesApi.create(d),
    onSuccess: () => { qc.invalidateQueries({queryKey:['sd-templates']}); setShowNew(false); toast.success(t('service_desk.templates_created')) },
    onError: e => toast.error(extractErr(e, 'Error'))
  })
  const { mutate: update } = useMutation({
    mutationFn: ({id, ...d}) => sdTemplatesApi.update(id, d),
    onSuccess: () => { qc.invalidateQueries({queryKey:['sd-templates']}); setEditing(null); toast.success(t('service_desk.templates_updated')) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: toggle } = useMutation({
    mutationFn: ({id, is_active}) => sdTemplatesApi.update(id, {is_active}),
    onSuccess: () => qc.invalidateQueries({queryKey:['sd-templates']}),
    onError: e => toast.error(extractErr(e, 'Error'))
  })
  const { mutate: remove } = useMutation({
    mutationFn: id => sdTemplatesApi.delete(id),
    onSuccess: () => { qc.invalidateQueries({queryKey:['sd-templates']}); toast.success(t('service_desk.templates_deleted')) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const IS = { width:'100%', background:'var(--surface-3)', border:'1px solid var(--surface-4)',
    borderRadius:8, padding:'9px 13px', color:'var(--text-1)', fontSize: "var(--text-base)",
    outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
  const LS = { fontSize: "var(--text-xs)", fontWeight:600, color:'var(--text-2)', display:'block', marginBottom:5, textTransform:'uppercase', letterSpacing:'0.06em' }

  return (
    <div>
      <div style={{ display:'flex', justifyContent:'space-between', marginBottom:20 }}>
        <div style={{ fontSize: "var(--text-sm)", color:'var(--text-3)' }}>{t('service_desk.templates_hint')}</div>
        <Button onClick={() => setShowNew(true)}>+ {t('service_desk.templates_new_title')}</Button>
      </div>

      {isLoading ? <Spinner /> :
       templates.length === 0 ? <EmptyState icon="📝" title={t('service_desk.templates_empty')} description={t('service_desk.templates_empty_desc')} /> :
      <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill, minmax(280px,1fr))', gap:12 }}>
        {templates.map(tmpl => (
          <div key={tmpl.id} style={{ background:'var(--surface-2)', border:'1px solid var(--surface-4)',
            borderRadius:12, padding:16, opacity: tmpl.is_active ? 1 : 0.55 }}>
            <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom:10 }}>
              <div>
                <div style={{ fontSize: "var(--text-base)", fontWeight:600, color:'var(--text-1)', marginBottom:4 }}>{tmpl.name}</div>
                <span style={{ fontSize: "var(--text-xs)", background:'var(--surface-4)', color:'var(--text-2)', padding:'2px 8px', borderRadius:4 }}>
                  {tmpl.ticket_type?.replace(/_/g,' ')}
                </span>
              </div>
              <div style={{ display:'flex', gap:6 }}>
                <button onClick={() => toggle({id:tmpl.id, is_active:!tmpl.is_active})}
                  style={{ background:'none', border:'1px solid var(--surface-4)', borderRadius:6, padding:'3px 8px',
                    fontSize: "var(--text-xs)", color: tmpl.is_active ? COLOR.success : 'var(--text-3)', cursor:'pointer', fontFamily:'inherit' }}>
                  {tmpl.is_active ? t('service_desk.templates_active') : t('service_desk.templates_inactive')}
                </button>
                <button onClick={() => setEditing(tmpl)}
                  style={{ background:'none', border:'1px solid var(--surface-4)', borderRadius:6, padding:'3px 8px',
                    fontSize: "var(--text-xs)", color:'var(--accent)', cursor:'pointer', fontFamily:'inherit' }}>✏</button>
                <button onClick={() => { openConfirmGlobal({ message: '¿Eliminar esta plantilla?', onConfirm: () => remove(tmpl.id), danger: true }) }}
                  style={{ background:'none', border:`1px solid ${COLOR.danger}30`, borderRadius:6, padding:'3px 8px',
                    fontSize: "var(--text-xs)", color:COLOR.danger, cursor:'pointer', fontFamily:'inherit' }}>🗑</button>
              </div>
            </div>
            {tmpl.default_priority && <div style={{ fontSize: "var(--text-sm)", color:'var(--text-2)', marginBottom:6 }}>
              {t('service_desk.templates_priority')}: <PBadge v={tmpl.default_priority} />
            </div>}
            {tmpl.description_template && (
              <div style={{ fontSize: "var(--text-sm)", color:'var(--text-3)', borderTop:'1px solid var(--surface-4)', paddingTop:8, marginTop:8 }}>
                {tmpl.description_template.slice(0, 80)}{tmpl.description_template.length > 80 ? '…' : ''}
              </div>
            )}
          </div>
        ))}
      </div>}

      {showNew && (
        <Modal open title={t('service_desk.templates_new_title')} onClose={() => setShowNew(false)}>
          <NewTemplateForm IS={IS} LS={LS} onSave={create} isPending={isPending} onClose={() => setShowNew(false)} />
        </Modal>
      )}
      {editing && (
        <Modal open title={t('service_desk.templates_edit_title')} onClose={() => setEditing(null)}>
          <NewTemplateForm IS={IS} LS={LS} initial={editing}
            onSave={d => update({id: editing.id, ...d})}
            isPending={false} onClose={() => setEditing(null)} />
        </Modal>
      )}
    </div>
  )
}

function NewTemplateForm({ IS, LS, onSave, isPending, onClose, initial }) {
  const t = useAppT()
  const [form, setForm] = useState({
    name: initial?.name || '', ticket_type: initial?.ticket_type || 'service_request',
    default_priority: initial?.default_priority || 'p3_medium',
    description_template: initial?.description_template || '',
  })
  const set = k => e => setForm(f => ({...f, [k]: e.target.value}))
  return (
    <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
      <div><label style={LS}>{t('common.name')} *</label><input value={form.name} onChange={set('name')} style={IS} /></div>
      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:10 }}>
        <div>
          <label style={LS}>{t('service_desk.svc_ticket_type')}</label>
          <select value={form.ticket_type} onChange={set('ticket_type')} style={IS}>
            {['incident','service_request','change','question','problem'].map(tk =>
              <option key={tk} value={tk}>{tk.replace(/_/g,' ')}</option>)}
          </select>
        </div>
        <div>
          <label style={LS}>{t('service_desk.templates_priority')}</label>
          <select value={form.default_priority} onChange={set('default_priority')} style={IS}>
            {['p1_critical','p2_high','p3_medium','p4_low'].map(p =>
              <option key={p} value={p}>{PRIORITY_LABEL[p]}</option>)}
          </select>
        </div>
      </div>
      <div>
        <label style={LS}>{t('service_desk.templates_hint')}</label>
        <textarea value={form.description_template} onChange={set('description_template')} rows={4}
          style={{...IS, resize:'vertical'}} placeholder="Texto de la plantilla de descripcion..." />
      </div>
      <div style={{ display:'flex', justifyContent:'flex-end', gap:10 }}>
        <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
        <Button onClick={() => onSave(form)} disabled={isPending || !form.name} loading={isPending}>{initial ? t('common.save') : t('service_desk.templates_new_title')}</Button>
      </div>
    </div>
  )
}

// ── Canned Responses Manager ──────────────────────────────────────────────────
function CannedResponsesManager() {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [form, setForm] = useState({ title: '', body: '', category: '', shortcut: '' })
  const [editing, setEditing] = useState(null)
  const [editForm, setEditForm] = useState({})

  const { data: responses = [], isLoading } = useQuery({
    queryKey: ['canned-responses-all'],
    queryFn: () => sdCannedApi.list().then(r => r.data).catch(() => []),
  })
  const IS = { width:'100%', background:'var(--surface-3)', border:'1px solid var(--surface-4)', borderRadius:8,
    padding:'8px 12px', color:'var(--text-1)', fontSize: "var(--text-base)", outline:'none', fontFamily:'inherit',
    boxSizing:'border-box' }
  const LS = { fontSize: "var(--text-xs)", fontWeight:700, color:'var(--text-2)', textTransform:'uppercase',
    letterSpacing:'0.06em', display:'block', marginBottom:4 }

  const { mutate: create } = useMutation({
    mutationFn: d => sdCannedApi.create(d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['canned-responses-all'] }); setForm({ title:'', body:'', category:'', shortcut:'' }) },
    onError: e => toast.error(e?.response?.data?.detail || 'Error'),
  })
  const { mutate: update } = useMutation({
    mutationFn: ({ id, data }) => sdCannedApi.update(id, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['canned-responses-all'] }); setEditing(null) },
    onError: e => toast.error(e?.response?.data?.detail || 'Error'),
  })
  const { mutate: del } = useMutation({
    mutationFn: id => sdCannedApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['canned-responses-all'] }),
    onError: e => toast.error(e?.response?.data?.detail || 'Error'),
  })

  return (
    <div>
      <div style={{ fontSize: "var(--text-base)", color:'var(--text-2)', marginBottom:16 }}>
        Respuestas predefinidas reutilizables por los agentes al responder tickets.
      </div>

      {isLoading ? <div style={{textAlign:'center',padding:20}}><Spinner /></div> : (
        <div style={{ display:'flex', flexDirection:'column', gap:6, marginBottom:20 }}>
          {responses.map(r => editing === r.id ? (
            <div key={r.id} style={{ padding:'12px 14px', background:'var(--accent-muted)',
              border:'1px solid var(--accent-glow)', borderRadius:10 }}>
              <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:8, marginBottom:8 }}>
          <div><label style={LS}>{t('common.name')} *</label>
            <input value={editForm.title||''} onChange={e=>setEditForm(f=>({...f,title:e.target.value}))} style={IS} /></div>
          <div><label style={LS}>{t('service_desk.routing_name_lbl')}</label>
            <input value={editForm.category||''} onChange={e=>setEditForm(f=>({...f,category:e.target.value}))} style={IS} /></div>
        </div>
        <div style={{marginBottom:8}}><label style={LS}>{t('service_desk.canned_shortcut')}</label>
          <input value={editForm.shortcut||''} onChange={e=>setEditForm(f=>({...f,shortcut:e.target.value}))} style={{...IS}} /></div>
        <div style={{marginBottom:10}}><label style={LS}>{t('service_desk.canned_body_lbl')} *</label>
                <textarea value={editForm.body||''} onChange={e=>setEditForm(f=>({...f,body:e.target.value}))} rows={4}
                  style={{...IS, resize:'vertical'}} /></div>
              <div style={{display:'flex',gap:8}}>
                <button onClick={() => update({ id:r.id, data:editForm })} disabled={!editForm.title||!editForm.body}
                  style={{background:'var(--accent)',border:'none',borderRadius:7,padding:'7px 16px',color:'#fff',cursor:'pointer',fontSize: "var(--text-sm)",fontFamily:'inherit'}}>
                  ✓ Guardar</button>
                <button onClick={() => setEditing(null)}
                  style={{background:'none',border:'1px solid var(--surface-4)',borderRadius:7,padding:'7px 12px',color:'var(--text-2)',cursor:'pointer',fontSize: "var(--text-sm)"}}>
                  Cancelar</button>
              </div>
            </div>
          ) : (
            <div key={r.id} style={{ display:'flex', alignItems:'center', gap:12, padding:'10px 14px',
              background:'var(--surface-2)', border:'1px solid var(--surface-4)', borderRadius:10 }}>
              <div style={{ flex:1, minWidth:0 }}>
                <div style={{ fontSize: "var(--text-base)", fontWeight:700 }}>{r.title}
                  {r.shortcut && <span style={{ fontSize: "var(--text-2xs)", color:'var(--accent)', marginLeft:8,
                    fontFamily:'var(--font-mono)', background:'var(--accent-muted)', padding:'1px 6px', borderRadius:4 }}>{r.shortcut}</span>}
                  {r.category && <span style={{ fontSize: "var(--text-2xs)", color:'var(--text-3)', marginLeft:6 }}>{r.category}</span>}
                </div>
                <div style={{ fontSize: "var(--text-xs)", color:'var(--text-2)', marginTop:2, overflow:'hidden',
                  textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{r.body?.slice(0,100)}</div>
              </div>
              <button onClick={() => { setEditing(r.id); setEditForm({title:r.title,body:r.body,category:r.category||'',shortcut:r.shortcut||''}) }}
                style={{background:'none',border:'1px solid var(--surface-4)',borderRadius:6,padding:'4px 10px',color:'var(--text-2)',cursor:'pointer',fontSize: "var(--text-sm)"}}>✏</button>
              <button onClick={() => { openConfirmGlobal({ message: `¿Eliminar "${r.title}"?`, onConfirm: () => del(r.id), danger: true }) }}
                style={{background:'none',border:'1px solid var(--danger-border)',borderRadius:6,padding:'4px 10px',color:'var(--danger)',cursor:'pointer',fontSize: "var(--text-sm)"}}>🗑</button>
            </div>
          ))}
          {responses.length === 0 && !isLoading && (
            <div style={{fontSize: "var(--text-base)",color:'var(--text-3)',textAlign:'center',padding:'20px 0'}}>{t('service_desk.canned_empty')}</div>
          )}
        </div>
      )}

      <div style={{ padding:'14px', background:'var(--accent-muted)', border:'1px dashed var(--accent-border)', borderRadius:10 }}>
        <div style={{ fontSize: "var(--text-sm)", fontWeight:700, color:'var(--accent)', marginBottom:12 }}>{t('service_desk.canned_new_header')}</div>
        <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:8, marginBottom:8 }}>
          <div><label style={LS}>{t('common.name')} *</label>
            <input value={form.title} onChange={e=>setForm(f=>({...f,title:e.target.value}))} style={IS} /></div>
          <div><label style={LS}>{t('service_desk.routing_name_lbl')}</label>
            <input value={form.category} onChange={e=>setForm(f=>({...f,category:e.target.value}))} style={IS} /></div>
        </div>
        <div style={{marginBottom:8}}><label style={LS}>{t('service_desk.canned_shortcut')}</label>
          <input value={form.shortcut} onChange={e=>setForm(f=>({...f,shortcut:e.target.value}))} style={IS} placeholder={t('service_desk.canned_shortcut')} /></div>
        <div style={{marginBottom:12}}><label style={LS}>{t('service_desk.canned_body_lbl')} *</label>
          <textarea value={form.body} onChange={e=>setForm(f=>({...f,body:e.target.value}))} rows={4}
            style={{...IS, resize:'vertical'}} placeholder="Texto de la respuesta enlatada..." /></div>
        <button onClick={() => create(form)} disabled={!form.title || !form.body}
          style={{background:'var(--accent)',border:'none',borderRadius:8,padding:'8px 18px',color:'#fff',cursor:'pointer',fontSize: "var(--text-base)",fontFamily:'inherit',fontWeight:600}}>
          + {t('service_desk.canned_add_btn')}
        </button>
      </div>
    </div>
  )
}

// ── Announcements Config ──────────────────────────────────────────────────────
export function AnnouncementsConfig() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState({ title:'', body:'', type:'info', show_to_clients:true, starts_at:'', ends_at:'' })

  const IS = { background:'var(--surface-3)', border:'1px solid var(--surface-4)', borderRadius:7, padding:'7px 11px', color:'var(--text-1)', fontSize: "var(--text-sm)", outline:'none', fontFamily:'inherit', width:'100%', boxSizing:'border-box' }
  const LS = { fontSize: "var(--text-xs)", fontWeight:700, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'0.06em', display:'block', marginBottom:4 }
  const TYPE_COLOR = { info:'var(--accent)', warning:'var(--warning)', outage:'var(--danger)', maintenance:'var(--purple)' }

  const { data: anns = [], isLoading } = useQuery({
    queryKey: ['sd-announcements'],
    queryFn: () => sdAnnouncementsApi.list().then(r => r.data),
  })
  const { mutate: create, isPending: creating } = useMutation({
    mutationFn: d => sdAnnouncementsApi.create(d),
    onSuccess: () => { qc.invalidateQueries(['sd-announcements']); setShowCreate(false); setForm({ title:'', body:'', type:'info', show_to_clients:true, starts_at:'', ends_at:'' }); toast.success(t('service_desk.ann_published')) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: del } = useMutation({
    mutationFn: id => sdAnnouncementsApi.delete(id),
    onSuccess: () => { qc.invalidateQueries(['sd-announcements']); toast.success(t('service_desk.ann_deactivated')) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  return (
    <div>
      <div style={{ display:'flex', justifyContent:'flex-end', marginBottom:14 }}>
        <Button size="sm" onClick={() => setShowCreate(true)}>{t('service_desk.ann_new_btn')}</Button>
      </div>
      {isLoading ? <div style={{ textAlign:'center', padding:30 }}><Spinner /></div>
        : anns.length === 0
          ? <EmptyState icon="📢" title={t('service_desk.ann_empty')} description={t('service_desk.ann_empty_desc')} />
          : (
            <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
              {anns.map(a => (
                <div key={a.id} style={{ display:'flex', gap:14, padding:'12px 16px', background:'var(--surface-2)', border:`1px solid ${(TYPE_COLOR[a.type]||'var(--accent)')}30`, borderRadius:10, alignItems:'flex-start' }}>
                  <div style={{ width:4, alignSelf:'stretch', borderRadius:4, background:TYPE_COLOR[a.type]||'var(--accent)', flexShrink:0 }} />
                  <div style={{ flex:1 }}>
                    <div style={{ fontSize: "var(--text-base)", fontWeight:700, marginBottom:4 }}>{a.title}
                      <span style={{ fontSize: "var(--text-2xs)", padding:'2px 7px', marginLeft:8, borderRadius:20, background:(TYPE_COLOR[a.type]||'var(--accent)')+'20', color:TYPE_COLOR[a.type]||'var(--accent)', fontWeight:700, textTransform:'uppercase' }}>{a.type}</span>
                      {a.show_to_clients && <span style={{ fontSize: "var(--text-2xs)", marginLeft:6, color:'var(--text-3)' }}>👁 {t('service_desk.ann_visible_clients')}</span>}
                    </div>
                    <div style={{ fontSize: "var(--text-sm)", color:'var(--text-2)', lineHeight:1.5 }}>{a.body}</div>
                    {(a.starts_at||a.ends_at) && (
                      <div style={{ fontSize: "var(--text-xs)", color:'var(--text-3)', marginTop:6 }}>
                        {a.starts_at && `${t('service_desk.ann_starts')}: ${new Date(a.starts_at).toLocaleString()}`}
                        {a.ends_at && ` · ${t('service_desk.ann_ends')}: ${new Date(a.ends_at).toLocaleString()}`}
                      </div>
                    )}
                  </div>
                  <button onClick={() => { openConfirmGlobal({ message: '¿Desactivar este anuncio?', onConfirm: () => del(a.id) }) }}
                    style={{ background:'none', border:'1px solid var(--danger-border)', borderRadius:6, padding:'4px 10px', color:'var(--danger)', cursor:'pointer', fontSize: "var(--text-xs)" }}>🗑</button>
                </div>
              ))}
            </div>
          )
      }
      {showCreate && (
        <Modal open title="Nuevo comunicado" onClose={() => setShowCreate(false)} width={500}>
          <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:12, marginBottom:14 }}>
            <div style={{ gridColumn:'1/-1' }}><label style={LS}>{t('service_desk.ticket_title')} *</label><input value={form.title} onChange={e=>setForm(f=>({...f,title:e.target.value}))} style={IS} /></div>
            <div><label style={LS}>{t('common.status')}</label>
              <select value={form.type} onChange={e=>setForm(f=>({...f,type:e.target.value}))} style={IS}>
                {['info','warning','outage','maintenance'].map(tp=><option key={tp} value={tp}>{tp}</option>)}
              </select>
            </div>
            <div style={{ display:'flex', alignItems:'center', gap:8, paddingTop:18 }}>
              <input type="checkbox" id="showCl" checked={form.show_to_clients} onChange={e=>setForm(f=>({...f,show_to_clients:e.target.checked}))} />
              <label htmlFor="showCl" style={{ fontSize: "var(--text-sm)", color:'var(--text-1)', cursor:'pointer' }}>{t('service_desk.ann_visible_clients')}</label>
            </div>
            <div><label style={LS}>{t('service_desk.ann_starts')}</label><input type="datetime-local" value={form.starts_at} onChange={e=>setForm(f=>({...f,starts_at:e.target.value}))} style={IS} /></div>
            <div><label style={LS}>{t('service_desk.ann_ends')}</label><input type="datetime-local" value={form.ends_at} onChange={e=>setForm(f=>({...f,ends_at:e.target.value}))} style={IS} /></div>
            <div style={{ gridColumn:'1/-1' }}><label style={LS}>{t('service_desk.ann_message')} *</label><textarea value={form.body} onChange={e=>setForm(f=>({...f,body:e.target.value}))} rows={4} style={{ ...IS, resize:'vertical' }} /></div>
          </div>
          <div style={{ display:'flex', gap:8, justifyContent:'flex-end' }}>
            <button onClick={()=>setShowCreate(false)} style={{ background:'transparent', border:'1px solid var(--surface-4)', borderRadius:8, padding:'7px 16px', color:'var(--text-2)', cursor:'pointer', fontSize: "var(--text-sm)" }}>{t('common.cancel')}</button>
            <Button onClick={()=>create(form)} loading={creating} disabled={!form.title||!form.body||creating}>{t('service_desk.ann_published')}</Button>
          </div>
        </Modal>
      )}
    </div>
  )
}

// ── Config wrapper (tab nav) ──────────────────────────────────────────────────
export default function Config() {
  const t = useAppT()
  const [sub, setSub] = useState('catalog')
  const tabs = [
    {id:'catalog',  label:`${t('service_desk.tab_catalog')}`},
    {id:'sla',      label:`⏱ ${t('service_desk.tab_sla')}`},
    {id:'groups',   label:`${t('service_desk.tab_groups')}`},
    {id:'routing',  label:`${t('service_desk.tab_routing')}`},
    {id:'templates',label:`${t('service_desk.tab_templates')}`},
    {id:'canned',   label:`${t('service_desk.tab_canned')}`},
  ]
  return (
    <div>
      <div style={{ display:'flex', gap:8, marginBottom:24, borderBottom:'1px solid var(--surface-4)', paddingBottom:16, flexWrap:'wrap', paddingLeft:12 }}>
        {tabs.map(tab => (
          <button key={tab.id} onClick={() => setSub(tab.id)} style={{
            padding:'7px 16px', borderRadius:8,
            border:`1px solid ${sub===tab.id ? 'var(--accent)' : 'var(--surface-4)'}`,
            background: sub===tab.id ? 'var(--accent-muted)' : 'transparent',
            color: sub===tab.id ? 'var(--accent)' : 'var(--text-2)',
            fontSize: "var(--text-sm)", fontWeight:600, cursor:'pointer', fontFamily:'inherit',
          }}>{tab.label}</button>
        ))}
      </div>
      {sub === 'catalog'       && <CatalogConfig />}
      {sub === 'sla'           && <SLAConfig />}
      {sub === 'groups'        && <GroupsConfig />}
      {sub === 'routing'       && <RoutingRules />}
      {sub === 'templates'     && <TemplatesConfig />}
      {sub === 'canned'        && <CannedResponsesManager />}
    </div>
  )
}
