/**
 * OrganizationsPage — Gestión multi-tenant de organizaciones
 */
import { CSSProperties, useState } from 'react'
import { extractErr } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { organizationsApi, usersApi } from '../services/api'
import { Button, Modal, Spinner, EmptyState, Confirm } from '../components/ui'
import { UserSelect } from '../components/ui/EntitySelect'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Building2 } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import { useOrgSettings } from '../hooks/useOrgSettings'
import { z } from 'zod'
import { useFormValidation } from '../hooks/useFormValidation'

const fs: CSSProperties = { width:'100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius:8, padding: '9px 13px', color:'var(--text-1)', fontSize: "var(--text-base)", outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
const ls: CSSProperties = { fontSize: "var(--text-xs)", fontWeight:500, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'.07em', display:'block', marginBottom:5 }
const card: CSSProperties = { background:'var(--surface-1)', border:'.5px solid var(--surface-4)', borderRadius:12 }

const PLAN_COLORS: Record<string, string> = { starter:'var(--text-2)', pro:'var(--accent)', enterprise:'var(--success)' }

const PLAN_VALUES = ['starter', 'pro', 'enterprise'] as const

const organizationCreateSchema = z.object({
  name: z.string().trim().min(1, 'El nombre es obligatorio').max(120, 'Máximo 120 caracteres'),
  slug: z.string().trim().min(2, 'Mínimo 2 caracteres').max(60, 'Máximo 60 caracteres').regex(/^[a-z0-9-]+$/, 'Solo minúsculas, números y guiones'),
  plan: z.enum(PLAN_VALUES),
  max_users: z.coerce.number().int().positive('Debe ser mayor que 0').max(100000, 'Valor demasiado alto'),
  max_projects: z.coerce.number().int().positive('Debe ser mayor que 0').max(100000, 'Valor demasiado alto'),
  admin_email: z.string().trim().email('Email inválido').or(z.literal('')).optional(),
  admin_name: z.string().trim().max(120).optional(),
  domain: z.string().trim().toLowerCase().regex(/^([a-z0-9-]+\.)+[a-z]{2,}$/, 'Dominio inválido').or(z.literal('')).optional(),
  timezone: z.string().optional(),
})

const organizationUpdateSchema = z.object({
  name: z.string().trim().min(1, 'El nombre es obligatorio').max(120, 'Máximo 120 caracteres'),
  plan: z.enum(PLAN_VALUES),
  max_users: z.coerce.number().int().positive('Debe ser mayor que 0').max(100000, 'Valor demasiado alto'),
  max_projects: z.coerce.number().int().positive('Debe ser mayor que 0').max(100000, 'Valor demasiado alto'),
  admin_email: z.string().trim().email('Email inválido').or(z.literal('')).optional(),
  timezone: z.string().optional(),
  locale: z.string().optional(),
  primary_color: z.string().optional(),
  domain: z.string().trim().toLowerCase().regex(/^([a-z0-9-]+\.)+[a-z]{2,}$/, 'Dominio inválido').or(z.literal('')).optional(),
})


// ─────────────────────────────────────────────────────────────────────────────
// Las formas que esta pagina consume
//
// Auditoria 2026-09 (modo estricto): el cliente de API devuelve `any` y los
// estados arrancaban en `null` sin argumento de tipo, con lo que TypeScript los
// fijaba a `null` **para siempre** y todo lo que se pintaba a partir de ellos
// era `never`. Se declara lo que esta pagina lee, con los campos opcionales
// porque este fichero no puede prometer lo que manda el backend.
// ─────────────────────────────────────────────────────────────────────────────

/** Una organizacion, tal como la lista el maestro. */
interface OrganizacionEnLista {
  id: string | number
  name?: string
  slug?: string
  plan?: string
  admin_email?: string
  is_active?: boolean
  created_at?: string
  user_count?: number
  project_count?: number
  max_users?: number
  max_projects?: number
  domain?: string | null
  suspension_reason?: string | null
  deletion_purge_after?: string | null
}

/** Un usuario asignado a una organizacion. */
interface UsuarioDeOrganizacion {
  id: string | number
  full_name?: string
  role?: string
  is_active?: boolean
}

/** El detalle de una organizacion, con sus usuarios. */
interface DetalleDeOrganizacion extends OrganizacionEnLista {
  timezone?: string
  locale?: string
  primary_color?: string
  max_users?: number
  max_projects?: number
  users?: UsuarioDeOrganizacion[]
}

/** El formulario de edicion. Arranca en `null` —no hay formulario hasta que se
 *  abre el modal— y por eso cada campo se lee con `?.`. */
interface FormularioDeEdicion {
  name: string
  plan: string
  max_users: number
  max_projects: number
  admin_email: string
  timezone: string
  locale: string
  primary_color: string
  domain: string
}

type OrgCreateForm = z.infer<typeof organizationCreateSchema>
type OrgUpdateForm = z.infer<typeof organizationUpdateSchema>

export default function OrganizationsPage() {
  // ...existing code...
  const [removingUserId, setRemovingUserId] = useState<string | number | null>(null)
    // Mutación para eliminar usuario de la organización
    const { mutate: removeUser, isPending: isRemoving } = useMutation({
      mutationFn: ({ orgId, userId }: { orgId: string | number; userId: string | number }) => organizationsApi.removeUser(orgId, userId),
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ['org-detail', selected] });
        setRemovingUserId(null)
        toast.success('Usuario eliminado')
      },
      onError: e => {
        const msg = extractErr(e, 'Error al eliminar usuario')
        const normalized = String(msg).toLowerCase()
        if (normalized.includes('ultima organizacion') || normalized.includes('última organización')) {
          toast.error('No se puede quitar al usuario de su ultima organizacion')
          return
        }
        if (normalized.includes('ultimo usuario') || normalized.includes('último usuario')) {
          toast.error('No se puede quitar el ultimo usuario de la organizacion')
          return
        }
        toast.error(msg)
      },
    })
  // Estado para asignar usuario
  const [showAssignUser, setShowAssignUser] = useState(false)
  const [assignUserId, setAssignUserId] = useState('')
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const { timezone: defaultTimezone } = useOrgSettings()
  const [showCreate, setShowCreate] = useState(false)
  const [showEdit, setShowEdit] = useState(false)
  const [selected, setSelected] = useState<string | number | null>(null)
  const [form, setForm] = useState({ name:'', slug:'', plan:'starter', max_users:25, max_projects:100, admin_email:'', admin_name:'', domain:'', timezone: defaultTimezone })
  // Revisión multitenant 2026-11: la contraseña inicial del primer admin se enseña una vez.
  const [altaHecha, setAltaHecha] = useState<{ email: string; password: string } | null>(null)
  const [suspendiendo, setSuspendiendo] = useState<OrganizacionEnLista | null>(null)
  const [motivo, setMotivo] = useState('')
  // Baja definitiva y «entrar como»: un mismo diálogo de motivo para las dos.
  const [pidiendoMotivo, setPidiendoMotivo] = useState<{ tipo: 'baja' | 'entrar'; userId?: string; nombre?: string } | null>(null)
  const [editForm, setEditForm] = useState<FormularioDeEdicion | null>(null)
  const createValidation = useFormValidation(organizationCreateSchema)
  const editValidation = useFormValidation(organizationUpdateSchema)

  const { data: orgs = [], isLoading } = useQuery<OrganizacionEnLista[]>({ queryKey:['orgs'], queryFn:() => organizationsApi.list().then(r=>r.data) })
  // `selected!` respaldado por el `enabled`: react-query no ejecuta `queryFn`
  // mientras `enabled` sea falso, asi que aqui nunca es null.
  const { data: detail } = useQuery<DetalleDeOrganizacion>({ queryKey:['org-detail', selected], queryFn:() => organizationsApi.get(selected!).then(r=>r.data), enabled:!!selected })
  const removingUser = detail?.users?.find(u => u.id === removingUserId) || null
  // Todos los usuarios activos
  const { data: allUsers = [] } = useQuery<UsuarioDeOrganizacion[]>({ queryKey:['users'], queryFn:() => usersApi.list({}).then(r=>r.data) })
  // Mutación para asignar usuario
  const { mutate: assignUser, isPending: isAssigning } = useMutation({
    mutationFn: ({ orgId, userId }: { orgId: string | number; userId: string | number }) => organizationsApi.assignUser(orgId, { user_id: userId }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['org-detail', selected] });
      setShowAssignUser(false)
      setAssignUserId('')
      toast.success('Usuario asignado')
    },
    onError: e => toast.error(extractErr(e, 'Error al asignar usuario')),
  })

  const { mutate: create, isPending } = useMutation({
    mutationFn: (d: OrgCreateForm) => organizationsApi.create(d),
    onSuccess: (r: { data?: { admin_email?: string | null; initial_password?: string | null } }) => {
      qc.invalidateQueries({ queryKey: ['orgs'] }); setShowCreate(false); createValidation.setErrors({})
      if (r?.data?.initial_password && r.data.admin_email) setAltaHecha({ email: r.data.admin_email, password: r.data.initial_password })
    },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const submitCreate = () => {
    const result = createValidation.validateForm(form)
    if (!result.success || !result.data) return
    create(result.data as OrgCreateForm)
  }

  const submitEdit = () => {
    if (selected == null || !editForm) return
    const result = editValidation.validateForm(editForm)
    if (!result.success || !result.data) return
    update({ id: selected, data: result.data as OrgUpdateForm })
  }
  const { mutate: toggle } = useMutation({
    mutationFn: ({ id, is_active, suspension_reason }: { id: string | number; is_active: boolean; suspension_reason?: string }) =>
      organizationsApi.update(id, { is_active, ...(suspension_reason ? { suspension_reason } : {}) }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['orgs'] }); setSuspendiendo(null); setMotivo('') },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const refrescar = () => { qc.invalidateQueries({ queryKey: ['orgs'] }); qc.invalidateQueries({ queryKey: ['org-detail', selected] }) }
  const { mutate: darDeBaja, isPending: dandoDeBaja } = useMutation({
    mutationFn: (reason: string) => organizationsApi.requestDeletion(selected!, reason),
    onSuccess: () => { refrescar(); setPidiendoMotivo(null); setMotivo(''); toast.success('Baja pedida: la empresa queda suspendida durante la cuarentena') },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: deshacerBaja } = useMutation({
    mutationFn: () => organizationsApi.cancelDeletion(selected!),
    onSuccess: () => { refrescar(); toast.success('Baja deshecha (la empresa sigue suspendida hasta reactivarla)') },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: entrarComo, isPending: entrando } = useMutation({
    mutationFn: ({ userId, reason }: { userId: string; reason: string }) => organizationsApi.impersonate(selected!, userId, reason),
    onSuccess: () => { window.location.href = '/' },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  async function exportar() {
    try {
      const { data } = await organizationsApi.exportData(selected!)
      const url = URL.createObjectURL(data as Blob)
      const a = document.createElement('a')
      a.href = url; a.download = `${detail?.slug ?? 'empresa'}-export.zip`; a.click()
      URL.revokeObjectURL(url)
    } catch (e) { toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) }
  }

  const { mutate: update, isPending: isUpdating } = useMutation({
    mutationFn: ({ id, data }: { id: string | number; data: OrgUpdateForm }) => organizationsApi.update(id, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['orgs'] }); qc.invalidateQueries({ queryKey: ['org-detail', selected] }); setShowEdit(false); editValidation.setErrors({}) },
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
        timezone: detail.timezone || defaultTimezone,
        locale: detail.locale || '',
        primary_color: detail.primary_color || '',
        domain: detail.domain || '',
      })
      setShowEdit(true)
    }
  }

  return (
    <PageShell>
      <PageHeader
        icon={<Building2 size={18} />}
        title={t('organizations.title')}
        subtitle={t('organizations.subtitle')}
        showListExport={orgs.length > 0}
        exportTargetSelector='[data-export-table="organizations-list"]'
        exportFilePrefix='organizations'
      />
      <div style={{ background:'var(--accent-muted)', border:'.5px solid rgba(0,212,255,0.25)', borderRadius:10, padding:'12px 16px', marginBottom:24, fontSize: "var(--text-base)", color:'var(--accent)' }}>
        {t('organizations.cada_organizacion_tiene_sus_propios_usuarios_proyectos')}
      </div>
      <div style={{ display:'flex', justifyContent:'flex-end', marginBottom:16 }}>
        <Button onClick={() => setShowCreate(true)}>{t('organizations.nueva_organizacion')}</Button>
      </div>

      <div style={{ display:'grid', gridTemplateColumns: selected ? '1fr 360px' : '1fr', gap:20 }}>
        <div>
          {isLoading ? <Spinner /> : orgs.length === 0 ? (
            <EmptyState icon="🏢" title={t('organizations.no_orgs')} description="Crea la primera organizacion para gestionar entornos aislados" />
          ) : (
            <div data-export-table="organizations-list" style={{ display:'flex', flexDirection:'column', gap:10 }}>
              {orgs.map(o => (
                <div key={o.id} onClick={() => setSelected(selected===o.id?null:o.id)}
                  role="button" tabIndex={0}
                  onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSelected(selected===o.id?null:o.id) } }}
                  style={{ ...card, padding:'16px 20px', cursor:'pointer', opacity: o.is_active ? 1 : 0.6, border:selected===o.id?'.5px solid rgba(0,212,255,0.25)':'var(--surface-4) .5px solid' }}>
                  <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center' }}>
                    <div>
                      <div style={{ display:'flex', gap:10, alignItems:'center', marginBottom:4 }}>
                        <span style={{ fontSize: "var(--text-md)", fontWeight:500 }}>{o.name}</span>
                        <span style={{ fontSize: "var(--text-xs)", padding:'1px 6px', borderRadius:4, background:'var(--surface-2)', color: (o.plan && PLAN_COLORS[o.plan]) || 'var(--text-2)', fontWeight:500 }}>{o.plan}</span>
                        {!o.is_active && <span style={{ fontSize: "var(--text-xs)", padding:'1px 6px', borderRadius:4, background:'var(--danger-bg)', color:'var(--danger)' }}>{o.deletion_purge_after ? `Baja · se borra el ${o.deletion_purge_after.slice(0, 10)}` : 'Suspendida'}</span>}
                      </div>
                      <div style={{ fontSize: "var(--text-sm)", color:'var(--text-2)' }}>
                        {o.slug}{o.domain ? ` · ${o.domain}` : ''} · {o.admin_email || '—'}
                      </div>
                      {/* Uso frente al límite del plan: el alta de usuarios y proyectos se para al llegar. */}
                      <div style={{ fontSize: "var(--text-sm)", marginTop:2 }}>
                        {([['usuarios', o.user_count, o.max_users], ['proyectos', o.project_count, o.max_projects]] as const).map(([k, usados, limite]) => (
                          <span key={k} style={{ marginRight:12, color: limite != null && (usados ?? 0) >= limite ? 'var(--danger)' : 'var(--text-2)' }}>
                            {usados ?? 0}/{limite ?? '∞'} {k}
                          </span>
                        ))}
                      </div>
                      {!o.is_active && o.suspension_reason && (
                        <div style={{ fontSize: "var(--text-sm)", color:'var(--danger)', marginTop:2 }}>Motivo: {o.suspension_reason}</div>
                      )}
                    </div>
                    <div style={{ display:'flex', gap:8 }}>
                      <span style={{ fontSize: "var(--text-sm)", color:'var(--text-2)' }}>{o.created_at}</span>
                      <button onClick={e => { e.stopPropagation(); if (o.is_active) { setSuspendiendo(o); setMotivo('') } else toggle({ id:o.id, is_active:true }) }}
                        style={{ background:'transparent', border:'.5px solid var(--surface-4)', borderRadius:6, padding:'3px 10px', color:'var(--text-2)', cursor:'pointer', fontSize: "var(--text-xs)", fontFamily:'inherit' }}>
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
              <div style={{ fontSize: "var(--text-md)", fontWeight:500 }}>{detail.name}</div>
              <Button size="sm" onClick={openEdit}>Editar</Button>
            </div>
            <div style={{ display:'flex', flexWrap:'wrap', gap:8, marginBottom:14 }}>
              <Button size="sm" variant="secondary" onClick={() => { void exportar() }}>Exportar datos</Button>
              {detail.deletion_purge_after
                ? <Button size="sm" variant="secondary" onClick={() => deshacerBaja()}>Deshacer baja</Button>
                : <Button size="sm" variant="danger" onClick={() => { setMotivo(''); setPidiendoMotivo({ tipo: 'baja' }) }}>Dar de baja</Button>}
            </div>
            {detail.deletion_purge_after && (
              <div style={{ fontSize: "var(--text-sm)", color:'var(--danger)', marginBottom:12 }}>
                Baja pedida: sus datos se borrarán a partir del {detail.deletion_purge_after.slice(0, 10)}. Hasta entonces se puede deshacer y exportar.
              </div>
            )}
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:10, marginBottom:16 }}>
              {[['Plan', detail.plan], ['Usuarios', `${detail.users?.length}/${detail.max_users}`], ['Zona horaria', detail.timezone], ['Idioma', detail.locale]].map(([k,v]) => (
                <div key={k} style={{ background:'var(--surface-2)', borderRadius:8, padding:'10px 12px' }}>
                  <div style={{ fontSize: "var(--text-2xs)", color:'var(--text-3)', marginBottom:2 }}>{k}</div>
                  <div style={{ fontSize: "var(--text-sm)", fontWeight:500 }}>{v}</div>
                </div>
              ))}
            </div>
            <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:10 }}>
              <span style={{ fontSize: "var(--text-base)", fontWeight:500 }}>Usuarios ({detail.users?.length})</span>
              <Button size="sm" onClick={() => setShowAssignUser(true)}>Asignar usuario</Button>
            </div>
            {(detail.users || []).length === 0 && <div style={{ color:'var(--text-3)', fontSize: "var(--text-sm)", marginBottom:8 }}>{t('organizations.no_hay_usuarios_asignados')}</div>}
            {(detail.users || []).map((u, idx, arr) => {
              const isLast = arr.length === 1
              return (
                <div key={u.id} style={{ display:'flex', justifyContent:'space-between', alignItems:'center', gap:4, padding:'6px 0', borderBottom:'.5px solid var(--surface-4)', fontSize: "var(--text-sm)" }}>
                  <span>{u.full_name}</span>
                  <span style={{ color:'var(--text-2)' }}>{u.role}</span>
                  <Button size="xs" variant="secondary" style={{ marginLeft:8 }}
                    title="Entrar como este usuario (soporte; queda auditado)"
                    onClick={() => { setMotivo(''); setPidiendoMotivo({ tipo: 'entrar', userId: String(u.id), nombre: u.full_name }) }}>Entrar como</Button>
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
                          title={t('organizations.quitar_usuario_de_la_organizacion')}
                          description={`Vas a quitar ${removingUser?.full_name || 'este usuario'} de ${detail.name}. El usuario seguira existiendo en el sistema si pertenece a otras organizaciones.`}
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
                      <div style={{ color:'var(--danger)', fontSize: "var(--text-sm)", minHeight:18 }}>
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
                          disabled={Boolean(!assignUserId || isAssigning || (assignUserId && allUsers.find(u => u.id === assignUserId)?.is_active === false) || (assignUserId && (detail?.users || []).some(u => u.id === assignUserId)))}
                        >{isAssigning ? 'Asignando...' : 'Asignar'}</Button>
                      </div>
                    </div>
                  </Modal>
                )}
          </div>
        )}
      </div>

      {showCreate && (
        <Modal open title={t('organizations.nueva_organizacion_2')} onClose={() => { setShowCreate(false); createValidation.setErrors({}) }} width={520}>
          <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:12 }}>
              <div>
                <label style={ls}>Nombre</label>
                <input value={form.name} onChange={e=>{ setForm(f=>({...f,name:e.target.value})); createValidation.clearFieldError('name') }} style={createValidation.inputStyle(fs, 'name')} />
                {createValidation.errors.name && <div style={{ color:'var(--danger)', fontSize: "var(--text-xs)", marginTop:4 }}>{createValidation.errors.name}</div>}
              </div>
              <div>
                <label style={ls}>{t('organizations.slug_identificador_unico')}</label>
                <input value={form.slug} onChange={e=>{ setForm(f=>({...f,slug:e.target.value.toLowerCase().replace(/\s+/g,'-')})); createValidation.clearFieldError('slug') }} style={createValidation.inputStyle(fs, 'slug')} />
                {createValidation.errors.slug && <div style={{ color:'var(--danger)', fontSize: "var(--text-xs)", marginTop:4 }}>{createValidation.errors.slug}</div>}
              </div>
            </div>
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr 1fr', gap:12 }}>
              <div><label style={ls}>Plan</label>
                <select value={form.plan} onChange={e=>setForm(f=>({...f,plan:e.target.value}))} style={fs}>
                  {['starter','pro','enterprise'].map(p => <option key={p} value={p}>{p}</option>)}
                </select>
              </div>
              <div>
                <label style={ls}>{t('organizations.max_usuarios')}</label>
                <input type="number" value={form.max_users} onChange={e=>{ setForm(f=>({...f,max_users:+e.target.value})); createValidation.clearFieldError('max_users') }} style={createValidation.inputStyle(fs, 'max_users')} />
                {createValidation.errors.max_users && <div style={{ color:'var(--danger)', fontSize: "var(--text-xs)", marginTop:4 }}>{createValidation.errors.max_users}</div>}
              </div>
              <div>
                <label style={ls}>{t('organizations.max_proyectos')}</label>
                <input type="number" value={form.max_projects} onChange={e=>{ setForm(f=>({...f,max_projects:+e.target.value})); createValidation.clearFieldError('max_projects') }} style={createValidation.inputStyle(fs, 'max_projects')} />
                {createValidation.errors.max_projects && <div style={{ color:'var(--danger)', fontSize: "var(--text-xs)", marginTop:4 }}>{createValidation.errors.max_projects}</div>}
              </div>
            </div>
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:12 }}>
              <div>
                <label style={ls}>{t('organizations.email_del_admin')}</label>
                <input value={form.admin_email} onChange={e=>{ setForm(f=>({...f,admin_email:e.target.value})); createValidation.clearFieldError('admin_email') }} style={createValidation.inputStyle(fs, 'admin_email')} />
                {createValidation.errors.admin_email && <div style={{ color:'var(--danger)', fontSize: "var(--text-xs)", marginTop:4 }}>{createValidation.errors.admin_email}</div>}
              </div>
              <div>
                <label style={ls}>Nombre del admin</label>
                <input value={form.admin_name} onChange={e=>setForm(f=>({...f,admin_name:e.target.value}))} style={fs} />
              </div>
            </div>
            <div style={{ fontSize: "var(--text-xs)", color:'var(--text-3)', marginTop:-6 }}>
              Con el correo se crea el primer administrador de la empresa; su contraseña inicial se enseña una sola vez.
            </div>
            <div>
              <label style={ls}>Dominio propio (opcional)</label>
              <input value={form.domain} placeholder="app.cliente.com" onChange={e=>{ setForm(f=>({...f,domain:e.target.value})); createValidation.clearFieldError('domain') }} style={createValidation.inputStyle(fs, 'domain')} />
              {createValidation.errors.domain && <div style={{ color:'var(--danger)', fontSize: "var(--text-xs)", marginTop:4 }}>{createValidation.errors.domain}</div>}
            </div>
            <div style={{ display:'flex', justifyContent:'flex-end', gap:10 }}>
              <Button variant="secondary" onClick={()=>{ setShowCreate(false); createValidation.setErrors({}) }}>Cancelar</Button>
              <Button onClick={submitCreate} disabled={isPending}>{isPending?'Creando...':'Crear'}</Button>
            </div>
          </div>
        </Modal>
      )}

      {showEdit && editForm && (
        <Modal open title="Editar organizacion" onClose={() => { setShowEdit(false); editValidation.setErrors({}) }} width={520}>
          <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:12 }}>
              <div>
                <label style={ls}>Nombre</label>
                <input value={editForm?.name ?? ''} onChange={e=>{ setEditForm(f => f && ({...f,name:e.target.value})); editValidation.clearFieldError('name') }} style={editValidation.inputStyle(fs, 'name')} />
                {editValidation.errors.name && <div style={{ color:'var(--danger)', fontSize: "var(--text-xs)", marginTop:4 }}>{editValidation.errors.name}</div>}
              </div>
              {/* El slug no se puede editar */}
              <div><label style={ls}>Slug</label><input value={detail?.slug ?? ''} disabled style={{...fs, background:'#f5f5f5'}} /></div>
            </div>
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr 1fr', gap:12 }}>
              <div><label style={ls}>Plan</label>
                <select value={editForm?.plan ?? ''} onChange={e=>setEditForm(f => f && ({...f,plan:e.target.value}))} style={fs}>
                  {['starter','pro','enterprise'].map(p => <option key={p} value={p}>{p}</option>)}
                </select>
              </div>
              <div>
                <label style={ls}>{t('organizations.max_usuarios')}</label>
                <input type="number" value={editForm?.max_users ?? ''} onChange={e=>{ setEditForm(f => f && ({...f,max_users:+e.target.value})); editValidation.clearFieldError('max_users') }} style={editValidation.inputStyle(fs, 'max_users')} />
                {editValidation.errors.max_users && <div style={{ color:'var(--danger)', fontSize: "var(--text-xs)", marginTop:4 }}>{editValidation.errors.max_users}</div>}
              </div>
              <div>
                <label style={ls}>{t('organizations.max_proyectos')}</label>
                <input type="number" value={editForm?.max_projects ?? ''} onChange={e=>{ setEditForm(f => f && ({...f,max_projects:+e.target.value})); editValidation.clearFieldError('max_projects') }} style={editValidation.inputStyle(fs, 'max_projects')} />
                {editValidation.errors.max_projects && <div style={{ color:'var(--danger)', fontSize: "var(--text-xs)", marginTop:4 }}>{editValidation.errors.max_projects}</div>}
              </div>
            </div>
            <div>
              <label style={ls}>Dominio propio (opcional)</label>
              <input value={editForm?.domain ?? ''} placeholder="app.cliente.com" onChange={e=>{ setEditForm(f => f && ({...f,domain:e.target.value})); editValidation.clearFieldError('domain') }} style={editValidation.inputStyle(fs, 'domain')} />
              {editValidation.errors.domain && <div style={{ color:'var(--danger)', fontSize: "var(--text-xs)", marginTop:4 }}>{editValidation.errors.domain}</div>}
            </div>
            <div>
              <label style={ls}>{t('organizations.email_del_admin')}</label>
              <input value={editForm?.admin_email ?? ''} onChange={e=>{ setEditForm(f => f && ({...f,admin_email:e.target.value})); editValidation.clearFieldError('admin_email') }} style={editValidation.inputStyle(fs, 'admin_email')} />
              {editValidation.errors.admin_email && <div style={{ color:'var(--danger)', fontSize: "var(--text-xs)", marginTop:4 }}>{editValidation.errors.admin_email}</div>}
            </div>
            <div style={{ display:'flex', justifyContent:'flex-end', gap:10 }}>
              <Button variant="secondary" onClick={()=>{ setShowEdit(false); editValidation.setErrors({}) }}>Cancelar</Button>
              <Button onClick={submitEdit} disabled={isUpdating}>{isUpdating?'Guardando...':'Guardar'}</Button>
            </div>
          </div>
        </Modal>
      )}
      {suspendiendo && (
        <Modal open title={`Suspender ${suspendiendo.name ?? ''}`} onClose={() => setSuspendiendo(null)} width={460}>
          <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
            <div style={{ fontSize: "var(--text-sm)", color:'var(--text-2)' }}>
              Nadie de la empresa podrá entrar, y las sesiones abiertas se cortan en su siguiente petición. Se puede reactivar.
            </div>
            <div>
              <label style={ls} htmlFor="motivo_suspension">Motivo</label>
              <textarea id="motivo_suspension" value={motivo} onChange={e => setMotivo(e.target.value)} rows={3} style={{ ...fs, resize:'vertical' }} />
            </div>
            <div style={{ display:'flex', justifyContent:'flex-end', gap:10 }}>
              <Button variant="secondary" onClick={() => setSuspendiendo(null)}>Cancelar</Button>
              <Button variant="danger" disabled={!motivo.trim()}
                onClick={() => toggle({ id: suspendiendo.id, is_active: false, suspension_reason: motivo.trim() })}>Suspender</Button>
            </div>
          </div>
        </Modal>
      )}

      {pidiendoMotivo && (
        <Modal open title={pidiendoMotivo.tipo === 'baja' ? `Dar de baja ${detail?.name ?? ''}` : `Entrar como ${pidiendoMotivo.nombre ?? ''}`}
          onClose={() => setPidiendoMotivo(null)} width={460}>
          <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
            <div style={{ fontSize: "var(--text-sm)", color:'var(--text-2)' }}>
              {pidiendoMotivo.tipo === 'baja'
                ? 'La empresa se suspende ahora. Al acabar la cuarentena se borran todos sus datos; antes se puede deshacer y exportar.'
                : 'Entrarás con su sesión durante un tiempo limitado, sin poder tocar credenciales. Queda en la auditoría de su empresa. Para volver, «Salir» en el aviso superior.'}
            </div>
            <div>
              <label style={ls} htmlFor="motivo_org">Motivo</label>
              <textarea id="motivo_org" value={motivo} onChange={e => setMotivo(e.target.value)} rows={3} style={{ ...fs, resize:'vertical' }} />
            </div>
            <div style={{ display:'flex', justifyContent:'flex-end', gap:10 }}>
              <Button variant="secondary" onClick={() => setPidiendoMotivo(null)}>Cancelar</Button>
              <Button variant={pidiendoMotivo.tipo === 'baja' ? 'danger' : 'primary'} disabled={!motivo.trim() || dandoDeBaja || entrando}
                onClick={() => pidiendoMotivo.tipo === 'baja'
                  ? darDeBaja(motivo.trim())
                  : entrarComo({ userId: pidiendoMotivo.userId!, reason: motivo.trim() })}>
                {pidiendoMotivo.tipo === 'baja' ? 'Dar de baja' : 'Entrar'}
              </Button>
            </div>
          </div>
        </Modal>
      )}

      {altaHecha && (
        <Modal open title="Empresa creada" onClose={() => setAltaHecha(null)} width={460}>
          <div style={{ display:'flex', flexDirection:'column', gap:12, fontSize: "var(--text-sm)" }}>
            <div>Primer administrador: <strong>{altaHecha.email}</strong></div>
            <div>Contraseña inicial (solo se enseña ahora; pídele que la cambie al entrar):</div>
            <code style={{ ...fs, userSelect:'all', fontFamily:'monospace' }}>{altaHecha.password}</code>
            <div style={{ display:'flex', justifyContent:'flex-end' }}>
              <Button onClick={() => setAltaHecha(null)}>Hecho</Button>
            </div>
          </div>
        </Modal>
      )}
    </PageShell>
  )
}
