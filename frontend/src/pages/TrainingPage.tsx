/**
 * TrainingPage — Formación y Certificaciones
 * Catálogo de cursos, inscripciones por usuario, certificaciones con alertas de caducidad
 */
import { useState } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { trainingApi, usersApi } from '../services/api'
import { Button, Modal, Spinner, EmptyState } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { BookOpen } from 'lucide-react'
import { useToast } from '../context/ToastContext'
import { extractErr } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useAuth } from '../context/AuthContext'
import { useAppT } from '../i18n/AppLangContext'
import { sanitizeUrl } from '../utils/security'

const STATUS_CFG = {
  planned:     { color:'var(--accent)',   label:'Planificado',   icon:'📅' },
  in_progress: { color:'var(--warning)',  label:'En curso',      icon:'⏳' },
  completed:   { color:'var(--success)',  label:'Completado',    icon:'✅' },
  cancelled:   { color:'var(--danger)',   label:'Cancelado',     icon:'✗' },
}

const IS = { width:'100%', background:'var(--surface-3)', border:'1px solid var(--surface-4)',
  borderRadius:8, padding:'8px 12px', color:'var(--text-1)', fontSize: "var(--text-base)",
  outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
const LS = { fontSize: "var(--text-xs)", fontWeight:700, color:'var(--text-2)', textTransform:'uppercase',
  letterSpacing:'0.07em', display:'block', marginBottom:4 }

function CourseModal({ course, onClose }) {
  const t = useAppT()
  const toast = useToast(); const qc = useQueryClient()
  const isEdit = !!course?.id
  const [form, setForm] = useState({
    title:course?.title||'', description:course?.description||'',
    provider:course?.provider||'', category:course?.category||'',
    duration_h:course?.duration_h||'', url:course?.url||'', cost:course?.cost||''
  })
  const { mutate, isPending } = useMutation({
    mutationFn: d => isEdit ? trainingApi.updateCourse(course.id, d) : trainingApi.createCourse(d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['training-courses'] }); onClose() },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  return (
    <Modal open onClose={onClose} title={isEdit ? 'Editar curso' : 'Nuevo curso'} width={520}>
      <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
        <div><label style={LS}>Título *</label>
          <input value={form.title} onChange={e=>setForm(f=>({...f,title:e.target.value}))} style={IS} autoFocus /></div>
        <div><label style={LS}>Proveedor</label>
          <input value={form.provider} onChange={e=>setForm(f=>({...f,provider:e.target.value}))} style={IS} placeholder="Nombre del proveedor" aria-label="Nombre del proveedor" /></div>
        <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr 1fr', gap:10 }}>
          <div><label style={LS}>Categoría</label>
            <input value={form.category} onChange={e=>setForm(f=>({...f,category:e.target.value}))} style={IS} placeholder="Categoria" aria-label="Categoria" /></div>
          <div><label style={LS}>Horas</label>
            <input type="number" value={form.duration_h} onChange={e=>setForm(f=>({...f,duration_h:e.target.value}))} style={IS} placeholder="Horas del curso" aria-label="Horas del curso" /></div>
          <div><label style={LS}>Coste €</label>
            <input type="number" value={form.cost} onChange={e=>setForm(f=>({...f,cost:e.target.value}))} style={IS} placeholder="Coste del curso" aria-label="Coste del curso" /></div>
        </div>
        <div><label style={LS}>URL</label>
          <input value={form.url} onChange={e=>setForm(f=>({...f,url:e.target.value}))} style={IS} placeholder="https://proveedor.com/curso" aria-label="URL del curso" /></div>
        <div style={{ display:'flex', justifyContent:'flex-end', gap:10 }}>
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={()=>mutate(form)} disabled={isPending||!form.title} loading={isPending}>
            {isEdit ? t('common.save') : 'Crear curso'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

function CertModal({ cert, userId, onClose }) {
  const t = useAppT()
  const toast = useToast(); const qc = useQueryClient()
  const isEdit = !!cert?.id
  const [form, setForm] = useState({
    user_id: userId || cert?.user_id || '',
    name:cert?.name||'', issuer:cert?.issuer||'', cert_id:cert?.cert_id||'',
    obtained_at:cert?.obtained_at||'', expires_at:cert?.expires_at||'',
    url:cert?.url||'', notes:cert?.notes||''
  })
  const { data: users = [] } = useQuery({
    queryKey:['users'], queryFn:()=>usersApi.list().then(r=>Array.isArray(r.data)?r.data:(r.data?.users||[]))
  })
  const { mutate, isPending } = useMutation({
    mutationFn: d => isEdit ? trainingApi.updateCert(cert.id, d) : trainingApi.createCert(d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['training-certs'] }); onClose() },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  return (
    <Modal open onClose={onClose} title={isEdit ? 'Editar certificación' : 'Nueva certificación'} width={500}>
      <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
        {!userId && <div><label style={LS}>Usuario *</label>
          <select value={form.user_id} onChange={e=>setForm(f=>({...f,user_id:e.target.value}))} style={IS}>
            <option value="">Seleccionar…</option>
            {users.map(u=><option key={u.id} value={u.id}>{u.full_name}</option>)}
          </select></div>}
        <div><label style={LS}>Nombre certificación *</label>
          <input value={form.name} onChange={e=>setForm(f=>({...f,name:e.target.value}))} style={IS} autoFocus /></div>
        <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:10 }}>
          <div><label style={LS}>Organismo emisor</label>
            <input value={form.issuer} onChange={e=>setForm(f=>({...f,issuer:e.target.value}))} style={IS} placeholder="Entidad emisora" aria-label="Entidad emisora" /></div>
          <div><label style={LS}>ID certificado</label>
            <input value={form.cert_id} onChange={e=>setForm(f=>({...f,cert_id:e.target.value}))} style={IS} /></div>
          <div><label style={LS}>Obtenida</label>
            <input type="date" value={form.obtained_at} onChange={e=>setForm(f=>({...f,obtained_at:e.target.value}))} style={IS} /></div>
          <div><label style={LS}>Caduca</label>
            <input type="date" value={form.expires_at} onChange={e=>setForm(f=>({...f,expires_at:e.target.value}))} style={IS} /></div>
        </div>
        <div><label style={LS}>URL verificación</label>
          <input value={form.url} onChange={e=>setForm(f=>({...f,url:e.target.value}))} style={IS} placeholder="https://verificacion.com/certificado" aria-label="URL de verificacion" /></div>
        <div style={{ display:'flex', justifyContent:'flex-end', gap:10 }}>
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={()=>mutate(form)} disabled={isPending||!form.name||!form.user_id} loading={isPending}>
            {isEdit ? t('common.save') : 'Añadir'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

export default function TrainingPage() {
  const t = useAppT()
  const _toast = useToast(); const qc = useQueryClient()
  const { user, hasRole } = useAuth()
  const isAdmin = hasRole('admin','hr')
  const [tab, setTab] = useState('courses')
  const [showCourseModal, setShowCourseModal] = useState(false)
  const [editingCourse, setEditingCourse] = useState(null)
  const [showCertModal, setShowCertModal] = useState(false)
  const [editingCert, setEditingCert] = useState(null)

  const { data: courses = [], isLoading: loadC } = useQuery({
    queryKey:['training-courses'],
    queryFn:()=>trainingApi.courses().then(r=>r.data?.items ?? r.data ?? []).catch(()=>[]),
  })
  const { data: certs = [], isLoading: loadCert } = useQuery({
    queryKey:['training-certs'],
    queryFn:()=>trainingApi.certs().then(r=>r.data?.items ?? r.data ?? []).catch(()=>[]),
    enabled: tab === 'certs',
  })
  const { data: enrollments = [] } = useQuery({
    queryKey:['training-enrollments'],
    queryFn:()=>trainingApi.enrollments().then(r=>r.data?.items ?? r.data ?? []).catch(()=>[]),
    enabled: tab === 'enrollments',
  })

  const { mutate: delCourse } = useMutation({
    mutationFn: id => trainingApi.deleteCourse(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['training-courses'] }),
  })
  const { mutate: delCert } = useMutation({
    mutationFn: id => trainingApi.deleteCert(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['training-certs'] }),
  })

  const expiringSoon = certs.filter(c => c.expiring_soon && !c.is_expired)
  const expired = certs.filter(c => c.is_expired)

  const TABS = [
    { id:'courses', label:'Catálogo' },
    { id:'enrollments', label:'Inscripciones' },
    { id:'certs', label:'Certificaciones' },
  ]

  return (
    <PageShell>
      <PageHeader
        icon={<BookOpen size={18} />}
        title={t('training.title')}
        subtitle={t('training.subtitle')}
        actions={
          <div style={{ display:'flex', gap:8 }}>
            {tab === 'courses' && isAdmin && (
              <Button onClick={() => { setEditingCourse(null); setShowCourseModal(true) }}>+ Curso</Button>
            )}
            {tab === 'certs' && (
              <Button onClick={() => { setEditingCert(null); setShowCertModal(true) }}>+ Certificación</Button>
            )}
          </div>
        }
      />

      {/* Alertas caducidad */}
      {tab === 'certs' && (expired.length > 0 || expiringSoon.length > 0) && (
        <div style={{ marginBottom:20 }}>
          {expired.map(c => (
            <div key={c.id} style={{ display:'flex', gap:10, padding:'10px 14px', marginBottom:6,
              background:'var(--danger-bg)', border:'1px solid var(--danger-border)',
              borderRadius:10, alignItems:'center' }}>
              <span>🔴</span>
              <div style={{ flex:1 }}>
                <span style={{ fontSize: "var(--text-base)", fontWeight:700 }}>{c.name}</span>
                <span style={{ fontSize: "var(--text-sm)", color:'var(--text-2)', marginLeft:8 }}>{c.user_name}</span>
              </div>
              <span style={{ fontSize: "var(--text-sm)", color:'var(--danger)', fontWeight:700 }}>Caducada</span>
            </div>
          ))}
          {expiringSoon.map(c => (
            <div key={c.id} style={{ display:'flex', gap:10, padding:'10px 14px', marginBottom:6,
              background:'var(--orange-bg)', border:'1px solid var(--orange-border)',
              borderRadius:10, alignItems:'center' }}>
              <span>🟡</span>
              <div style={{ flex:1 }}>
                <span style={{ fontSize: "var(--text-base)", fontWeight:700 }}>{c.name}</span>
                <span style={{ fontSize: "var(--text-sm)", color:'var(--text-2)', marginLeft:8 }}>{c.user_name}</span>
              </div>
              <span style={{ fontSize: "var(--text-sm)", color:'var(--warning)', fontWeight:700 }}>
                Caduca en {c.days_until_expiry}d
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Tabs */}
      <div style={{ display:'flex', gap:6, marginBottom: 20 , borderBottom: '1px solid var(--surface-4)', paddingBottom: 12 }}>
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            style={{ padding:'8px 16px', borderRadius:8, fontSize: "var(--text-sm)", fontWeight:600,
              border:`1px solid ${tab===t.id?'var(--accent-glow)':'var(--surface-4)'}`,
              background:tab===t.id?'var(--accent-muted)':'transparent',
              color:tab===t.id?'var(--accent)':'var(--text-2)',
              cursor:'pointer', fontFamily:'inherit' }}>
            {t.label}
          </button>
        ))}
      </div>

      {/* Catálogo de cursos */}
      {tab === 'courses' && (
        loadC ? <Spinner /> : courses.length === 0 ? (
          <EmptyState icon="📚" title="Sin cursos" description="Crea el primer curso para arrancar el catalogo de formacion" />
        ) : (
          <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill, minmax(300px,1fr))', gap:12 }}>
            {courses.map(c => (
              <div key={c.id} style={{ background:'var(--surface-2)', border:'1px solid var(--surface-4)',
                borderRadius:12, padding:'16px 18px' }}>
                <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom:8 }}>
                  <div style={{ flex:1, minWidth:0 }}>
                    <div style={{ fontSize: "var(--text-md)", fontWeight:700 }}>{c.title}</div>
                    {c.provider && <div style={{ fontSize: "var(--text-xs)", color:'var(--accent)', marginTop:2 }}>{c.provider}</div>}
                  </div>
                  {isAdmin && (
                    <div style={{ display:'flex', gap:4, marginLeft:8 }}>
                      <button onClick={()=>{setEditingCourse(c);setShowCourseModal(true)}}
                        style={{background:'none',border:'1px solid var(--surface-4)',borderRadius:5,padding:'3px 7px',color:'var(--text-2)',cursor:'pointer',fontSize: "var(--text-xs)"}}>✏</button>
                      <button onClick={()=>{ openConfirmGlobal({ message: '¿Eliminar curso?', onConfirm: () => delCourse(c.id), danger: true }) }}
                        style={{background:'none',border:'1px solid var(--danger-border)',borderRadius:5,padding:'3px 7px',color:'var(--danger)',cursor:'pointer',fontSize: "var(--text-xs)"}}>🗑</button>
                    </div>
                  )}
                </div>
                {c.description && <div style={{ fontSize: "var(--text-sm)", color:'var(--text-2)', marginBottom:8, lineHeight:1.4 }}>{c.description.slice(0,100)}{c.description.length>100?'…':''}</div>}
                <div style={{ display:'flex', gap:8, flexWrap:'wrap' }}>
                  {c.category && <span style={{ fontSize: "var(--text-2xs)", fontWeight:700, padding:'2px 7px', borderRadius:20, background:'var(--accent-muted)', color:'var(--accent)' }}>{c.category}</span>}
                  {c.duration_h && <span style={{ fontSize: "var(--text-xs)", color:'var(--text-2)' }}>⏱ {c.duration_h}h</span>}
                  {c.cost > 0 && <span style={{ fontSize: "var(--text-xs)", color:'var(--success)' }}>💶 {c.cost}€</span>}
                  {c.url && <a href={sanitizeUrl(c.url)} target="_blank" rel="noopener noreferrer" style={{ fontSize: "var(--text-xs)", color:'var(--accent)' }}>🔗 Ver</a>}
                  <span style={{ fontSize: "var(--text-2xs)", color:'var(--text-3)', marginLeft:'auto' }}>{c.enrolled} inscritos</span>
                </div>
              </div>
            ))}
          </div>
        )
      )}

      {/* Inscripciones */}
      {tab === 'enrollments' && (
        enrollments.length === 0 ? (
          <EmptyState icon="👤" title="Sin inscripciones" description="Todavia no hay empleados inscritos en cursos" />
        ) : (
          <div style={{ background:'var(--surface-2)', border:'1px solid var(--surface-4)', borderRadius:12, overflow:'hidden' }}>
            <table style={{ width:'100%', borderCollapse:'collapse' }}>
              <thead>
                <tr style={{ borderBottom:'1px solid var(--surface-4)' }}>
                  {['Empleado','Curso','Estado','Inicio','Fin','Nota'].map(h => (
                    <th key={h} style={{ padding:'10px 14px', textAlign:'left', fontSize: "var(--text-xs)", fontWeight:700, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'0.06em' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {enrollments.map(e => {
                  const sc = STATUS_CFG[e.status] || STATUS_CFG.planned
                  return (
                    <tr key={e.id} style={{ borderBottom:'1px solid var(--surface-4)20' }}
                      onMouseEnter={el=>el.currentTarget.style.background='var(--surface-3)'}
                      onMouseLeave={el=>el.currentTarget.style.background='transparent'}>
                      <td style={{ padding:'10px 14px', fontSize: "var(--text-base)", fontWeight:600 }}>{e.user_name}</td>
                      <td style={{ padding:'10px 14px', fontSize: "var(--text-base)" }}>{e.course_title}</td>
                      <td style={{ padding:'10px 14px' }}>
                        <span style={{ fontSize: "var(--text-xs)", fontWeight:700, padding:'2px 8px', borderRadius:20,
                          background:`${sc.color}20`, color:sc.color }}>
                          {sc.icon} {sc.label}
                        </span>
                      </td>
                      <td style={{ padding:'10px 14px', fontSize: "var(--text-sm)", color:'var(--text-2)' }}>{e.start_date || '—'}</td>
                      <td style={{ padding:'10px 14px', fontSize: "var(--text-sm)", color:'var(--text-2)' }}>{e.end_date || '—'}</td>
                      <td style={{ padding:'10px 14px', fontSize: "var(--text-sm)", color: e.score >= 7 ? 'var(--success)' : e.score ? 'var(--warning)' : 'var(--text-3)' }}>
                        {e.score ? `${e.score}/10` : '—'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )
      )}

      {/* Certificaciones */}
      {tab === 'certs' && (
        loadCert ? <Spinner /> : certs.length === 0 ? (
          <EmptyState icon="🏅" title="Sin certificaciones" description="Anade la primera certificacion para hacer seguimiento de vigencias" />
        ) : (
          <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
            {certs.map(c => (
              <div key={c.id} style={{ display:'flex', alignItems:'center', gap:12,
                padding:'12px 16px', background:'var(--surface-2)', borderRadius:10,
                border:`1px solid ${c.is_expired ? 'var(--danger-border)' : c.expiring_soon ? 'var(--orange-border)' : 'var(--surface-4)'}` }}>
                <div style={{ fontSize: "var(--text-2xl)" }}>🏅</div>
                <div style={{ flex:1, minWidth:0 }}>
                  <div style={{ fontSize: "var(--text-base)", fontWeight:700 }}>{c.name}
                    {c.issuer && <span style={{ fontSize: "var(--text-xs)", color:'var(--text-2)', marginLeft:8 }}>{c.issuer}</span>}
                  </div>
                  <div style={{ fontSize: "var(--text-sm)", color:'var(--text-2)', marginTop:2 }}>
                    {c.user_name}
                    {c.cert_id && <span style={{ marginLeft:8, fontFamily:'var(--font-mono)', fontSize: "var(--text-xs)" }}>#{c.cert_id}</span>}
                    {c.obtained_at && <span style={{ marginLeft:8 }}>· Obtenida: {c.obtained_at}</span>}
                  </div>
                </div>
                <div style={{ textAlign:'right', flexShrink:0 }}>
                  {c.expires_at ? (
                    <div style={{ fontSize: "var(--text-sm)", fontWeight:700,
                      color: c.is_expired ? 'var(--danger)' : c.expiring_soon ? 'var(--warning)' : 'var(--success)' }}>
                      {c.is_expired ? '⚠ Caducada' : `Caduca ${c.expires_at}`}
                    </div>
                  ) : (
                    <div style={{ fontSize: "var(--text-xs)", color:'var(--text-3)' }}>Sin caducidad</div>
                  )}
                </div>
                {c.url && <a href={sanitizeUrl(c.url)} target="_blank" rel="noopener noreferrer"
                  style={{ fontSize: "var(--text-xs)", color:'var(--accent)', whiteSpace:'nowrap' }}>🔗 Verificar</a>}
                <button onClick={()=>{setEditingCert(c);setShowCertModal(true)}}
                  style={{background:'none',border:'1px solid var(--surface-4)',borderRadius:6,padding:'4px 8px',color:'var(--text-2)',cursor:'pointer',fontSize: "var(--text-xs)"}}>✏</button>
                <button onClick={()=>{ openConfirmGlobal({ message: '¿Eliminar?', onConfirm: () => delCert(c.id), danger: true }) }}
                  style={{background:'none',border:'1px solid var(--danger-border)',borderRadius:6,padding:'4px 8px',color:'var(--danger)',cursor:'pointer',fontSize: "var(--text-xs)"}}>🗑</button>
              </div>
            ))}
          </div>
        )
      )}

      {showCourseModal && <CourseModal course={editingCourse} onClose={()=>{setShowCourseModal(false);setEditingCourse(null)}} />}
      {showCertModal && <CertModal cert={editingCert} userId={!isAdmin?user?.id:null} onClose={()=>{setShowCertModal(false);setEditingCert(null)}} />}
    </PageShell>
  )
}
