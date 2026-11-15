/**
 * OrganizationsPage — Gestión multi-tenant de organizaciones
 */
import { CSSProperties, useState, useId } from 'react'
import { extractErr } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { organizationsApi, usersApi } from '../services/api'
import type { DetalleDeOrganizacion, Organizacion } from '../services/api/tipos-plataforma'
import { Button, Modal, Spinner, EmptyState, Confirm } from '../components/ui'
import { UserSelect } from '../components/ui/EntitySelect'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Building2 } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import { useOrgSettings } from '../hooks/useOrgSettings'
import { z } from 'zod'
import { useFormValidation } from '../hooks/useFormValidation'
import './OrganizationsPage.css'

const fs: CSSProperties = { width:'100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius:8, padding: '9px 13px', color:'var(--text-1)', fontSize: "var(--text-base)", outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
const ls: CSSProperties = { fontSize: "var(--text-xs)", fontWeight:500, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'.07em', display:'block', marginBottom:5 }
const card: CSSProperties = { background:'var(--surface-1)', border:'.5px solid var(--surface-4)', borderRadius:12 }

const PLAN_COLORS: Record<string, string> = { starter:'var(--text-2)', pro:'var(--accent)', enterprise:'var(--success)' }

const PLAN_VALUES = ['starter', 'pro', 'enterprise'] as const

const organizationCreateSchema = z.object({
  name: z.string().trim().min(1, 'pagina_orgs.el_nombre_es_obligatorio').max(120, 'pagina_orgs.maximo_120_caracteres'),
  slug: z.string().trim().min(2, 'pagina_orgs.minimo_2_caracteres').max(60, 'pagina_orgs.maximo_60_caracteres').regex(/^[a-z0-9-]+$/, 'pagina_orgs.solo_minusculas_numeros_y_guiones'),
  plan: z.enum(PLAN_VALUES),
  max_users: z.coerce.number().int().positive('pagina_orgs.debe_ser_mayor_que_0').max(100000, 'pagina_orgs.valor_demasiado_alto'),
  max_projects: z.coerce.number().int().positive('pagina_orgs.debe_ser_mayor_que_0').max(100000, 'pagina_orgs.valor_demasiado_alto'),
  admin_email: z.string().trim().pipe(z.email('pagina_orgs.email_invalido')).or(z.literal('')).optional(),
  admin_name: z.string().trim().max(120).optional(),
  domain: z.string().trim().toLowerCase().regex(/^([a-z0-9-]+\.)+[a-z]{2,}$/, 'pagina_orgs.dominio_invalido').or(z.literal('')).optional(),
  timezone: z.string().optional(),
})

const organizationUpdateSchema = z.object({
  name: z.string().trim().min(1, 'pagina_orgs.el_nombre_es_obligatorio').max(120, 'pagina_orgs.maximo_120_caracteres'),
  plan: z.enum(PLAN_VALUES),
  max_users: z.coerce.number().int().positive('pagina_orgs.debe_ser_mayor_que_0').max(100000, 'pagina_orgs.valor_demasiado_alto'),
  max_projects: z.coerce.number().int().positive('pagina_orgs.debe_ser_mayor_que_0').max(100000, 'pagina_orgs.valor_demasiado_alto'),
  admin_email: z.string().trim().pipe(z.email('pagina_orgs.email_invalido')).or(z.literal('')).optional(),
  timezone: z.string().optional(),
  locale: z.string().optional(),
  primary_color: z.string().optional(),
  domain: z.string().trim().toLowerCase().regex(/^([a-z0-9-]+\.)+[a-z]{2,}$/, 'pagina_orgs.dominio_invalido').or(z.literal('')).optional(),
  require_mfa: z.boolean().optional(),
})


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
  require_mfa: boolean
}

type OrgCreateForm = z.infer<typeof organizationCreateSchema>
type OrgUpdateForm = z.infer<typeof organizationUpdateSchema>

export default function OrganizationsPage() {
  // ...existing code...
  const idCampo = useId()
  const [removingUserId, setRemovingUserId] = useState<string | number | null>(null)
    // Mutación para eliminar usuario de la organización
    const { mutate: removeUser, isPending: isRemoving } = useMutation({
      mutationFn: ({ orgId, userId }: { orgId: string | number; userId: string | number }) => organizationsApi.removeUser(orgId, userId),
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ['org-detail', selected] });
        setRemovingUserId(null)
        toast.success(t('pagina_orgs.usuario_eliminado'))
      },
      onError: e => {
        const msg = extractErr(e, t('pagina_orgs.error_al_eliminar_usuario'))
        const normalized = String(msg).toLowerCase()
        if (normalized.includes('ultima organizacion') || normalized.includes('última organización')) {
          toast.error(t('pagina_orgs.no_se_puede_quitar_su_ultima_org'))
          return
        }
        if (normalized.includes('ultimo usuario') || normalized.includes('último usuario')) {
          toast.error(t('pagina_orgs.no_se_puede_quitar_ultimo_usuario'))
          return
        }
        toast.error(msg)
      },
    })
  // Estado para asignar usuario
  const [showAssignUser, setShowAssignUser] = useState(false)
  const [assignUserId, setAssignUserId] = useState('')
  const t = useAppT()
  // Los mensajes propios de los esquemas son claves i18n; los de zod por defecto se ven tal cual.
  const errorDeCampo = (m?: string) => (m?.startsWith('pagina_orgs.') ? t(m) : m)
  const qc = useQueryClient()
  const toast = useToast()
  const { timezone: defaultTimezone } = useOrgSettings()
  const [showCreate, setShowCreate] = useState(false)
  const [showEdit, setShowEdit] = useState(false)
  const [selected, setSelected] = useState<string | number | null>(null)
  const [form, setForm] = useState({ name:'', slug:'', plan:'starter', max_users:25, max_projects:100, admin_email:'', admin_name:'', domain:'', timezone: defaultTimezone })
  // Revisión multitenant 2026-11: la contraseña inicial del primer admin se enseña una vez.
  const [altaHecha, setAltaHecha] = useState<{ email: string; password: string } | null>(null)
  const [suspendiendo, setSuspendiendo] = useState<Organizacion | null>(null)
  const [motivo, setMotivo] = useState('')
  // Baja definitiva y «entrar como»: un mismo diálogo de motivo para las dos.
  const [pidiendoMotivo, setPidiendoMotivo] = useState<{ tipo: 'baja' | 'entrar'; userId?: string; nombre?: string } | null>(null)
  const [editForm, setEditForm] = useState<FormularioDeEdicion | null>(null)
  const createValidation = useFormValidation(organizationCreateSchema)
  const editValidation = useFormValidation(organizationUpdateSchema)

  const { data: orgs = [], isLoading } = useQuery<Organizacion[]>({ queryKey:['orgs'], queryFn:() => organizationsApi.list().then(r=>r.data) })
  // `selected!` respaldado por el `enabled`: react-query no ejecuta `queryFn`
  // mientras `enabled` sea falso, asi que aqui nunca es null.
  const { data: detail } = useQuery<DetalleDeOrganizacion>({ queryKey:['org-detail', selected], queryFn:() => organizationsApi.get(selected!).then(r=>r.data), enabled:!!selected })
  const removingUser = detail?.users?.find(u => u.id === removingUserId) || null
  // Todos los usuarios activos
  const { data: allUsers = [] } = useQuery({ queryKey:['users'], queryFn:() => usersApi.list({}).then(r=>r.data) })
  // Mutación para asignar usuario
  const { mutate: assignUser, isPending: isAssigning } = useMutation({
    mutationFn: ({ orgId, userId }: { orgId: string | number; userId: string | number }) => organizationsApi.assignUser(orgId, { user_id: userId }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['org-detail', selected] });
      setShowAssignUser(false)
      setAssignUserId('')
      toast.success(t('pagina_orgs.usuario_asignado'))
    },
    onError: e => toast.error(extractErr(e, t('pagina_orgs.error_al_asignar_usuario'))),
  })

  const { mutate: create, isPending } = useMutation({
    mutationFn: (d: OrgCreateForm) => organizationsApi.create(d),
    onSuccess: ({ data }) => {
      qc.invalidateQueries({ queryKey: ['orgs'] }); setShowCreate(false); createValidation.setErrors({})
      if (data.initial_password && data.admin_email) setAltaHecha({ email: data.admin_email, password: data.initial_password })
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
    onSuccess: () => { refrescar(); setPidiendoMotivo(null); setMotivo(''); toast.success(t('pagina_orgs.baja_pedida_la_empresa_queda_suspendida')) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: deshacerBaja } = useMutation({
    mutationFn: () => organizationsApi.cancelDeletion(selected!),
    onSuccess: () => { refrescar(); toast.success(t('pagina_orgs.baja_deshecha_la_empresa_sigue_suspendida')) },
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
      const url = URL.createObjectURL(data)
      const a = document.createElement('a')
      a.href = url; a.download = `${detail?.slug ?? 'empresa'}-export.zip`; a.click()
      URL.revokeObjectURL(url)
    } catch (e) { toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) }
  }

  const { mutate: update, isPending: isUpdating } = useMutation({
    mutationFn: ({ id, data }: { id: string | number; data: OrgUpdateForm }) => organizationsApi.update(id, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['orgs'] }); qc.invalidateQueries({ queryKey: ['org-detail', selected] }); setShowEdit(false); editValidation.setErrors({}) },
    onError: e => toast.error(extractErr(e, t('pagina_orgs.error_al_actualizar'))),
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
        require_mfa: !!detail.require_mfa,
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
      <div className="orgs-card">
        {t('organizations.cada_organizacion_tiene_sus_propios_usuarios_proyectos')}
      </div>
      <div className="orgs-row">
        <Button onClick={() => setShowCreate(true)}>{t('organizations.nueva_organizacion')}</Button>
      </div>

      <div className="orgs-grid" style={{ gridTemplateColumns: selected ? '1fr 360px' : '1fr' }}>
        <div>
          {isLoading ? <Spinner /> : orgs.length === 0 ? (
            <EmptyState icon="🏢" title={t('organizations.no_orgs')} description={t('pagina_orgs.crea_la_primera_organizacion_para_gestionar')} />
          ) : (
            <div data-export-table="organizations-list" className="u-stack-10">
              {orgs.map(o => (
                <div key={o.id} onClick={() => setSelected(selected===o.id?null:o.id)}
                  role="button" tabIndex={0} aria-labelledby={`${idCampo}-${o.id}-n`}
                  onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSelected(selected===o.id?null:o.id) } }}
                  style={{ ...card, padding:'16px 20px', cursor:'pointer', opacity: o.is_active ? 1 : 0.6, border:selected===o.id?'.5px solid rgba(0,212,255,0.25)':'var(--surface-4) .5px solid' }}>
                  <div className="u-row-between">
                    <div>
                      <div className="orgs-row-2">
                        <span id={`${idCampo}-${o.id}-n`} className="orgs-label">{o.name}</span>
                        <span className="orgs-card-2" style={{ color: (o.plan && PLAN_COLORS[o.plan]) || 'var(--text-2)' }}>{o.plan}</span>
                        {!o.is_active && <span className="orgs-card-3">{o.deletion_purge_after ? t('pagina_orgs.baja_se_borra_el', { v1: o.deletion_purge_after.slice(0, 10) }) : t('pagina_orgs.suspendida')}</span>}
                      </div>
                      <div className="u-text2-sm">
                        {o.slug}{o.domain ? ` · ${o.domain}` : ''} · {o.admin_email || '—'}
                      </div>
                      {/* Uso frente al límite del plan: el alta de usuarios y proyectos se para al llegar. */}
                      <div className="orgs-box">
                        {([['usuarios', o.user_count, o.max_users], ['proyectos', o.project_count, o.max_projects]] as const).map(([k, usados, limite]) => (
                          <span key={k} className="orgs-label-2" style={{ color: limite != null && (usados ?? 0) >= limite ? 'var(--danger)' : 'var(--text-2)' }}>
                            {usados ?? 0}/{limite ?? '∞'} {k}
                          </span>
                        ))}
                      </div>
                      {!o.is_active && o.suspension_reason && (
                        <div className="orgs-box-2">{t('pagina_orgs.motivo')}{' '}{o.suspension_reason}</div>
                      )}
                    </div>
                    <div className="u-row-8">
                      <span className="u-text2-sm">{o.created_at}</span>
                      <button onClick={e => { e.stopPropagation(); if (o.is_active) { setSuspendiendo(o); setMotivo('') } else toggle({ id:o.id, is_active:true }) }}
                        className="orgs-btn">
                        {o.is_active ? t('pagina_orgs.suspender') : t('pagina_orgs.activar')}
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
            <div className="orgs-row-3">
              <div className="orgs-label">{detail.name}</div>
              <Button size="sm" onClick={openEdit}>{t('pagina_orgs.editar')}</Button>
            </div>
            <div className="orgs-row-4">
              <Button size="sm" variant="secondary" onClick={() => { void exportar() }}>{t('pagina_orgs.exportar_datos')}</Button>
              {detail.deletion_purge_after
                ? <Button size="sm" variant="secondary" onClick={() => deshacerBaja()}>{t('pagina_orgs.deshacer_baja')}</Button>
                : <Button size="sm" variant="danger" onClick={() => { setMotivo(''); setPidiendoMotivo({ tipo: 'baja' }) }}>{t('pagina_orgs.dar_de_baja')}</Button>}
            </div>
            {detail.deletion_purge_after && (
              <div className="orgs-box-3">
                {t('pagina_orgs.baja_pedida_sus_datos_se_borraran')}{' '}{detail.deletion_purge_after.slice(0, 10)}{t('pagina_orgs.hasta_entonces_se_puede_deshacer_y')}
              </div>
            )}
            <div className="orgs-grid-2">
              {[[t('pagina_orgs.plan'), detail.plan], [t('pagina_orgs.usuarios'), `${detail.users?.length}/${detail.max_users}`], [t('pagina_orgs.zona_horaria'), detail.timezone], [t('pagina_orgs.idioma'), detail.locale]].map(([k,v]) => (
                <div key={k} className="orgs-card-4">
                  <div className="orgs-box-4">{k}</div>
                  <div className="orgs-box-5">{v}</div>
                </div>
              ))}
            </div>
            <div className="orgs-row-5">
              <span className="orgs-label-3">{t('pagina_orgs.usuarios_2')}{detail.users?.length})</span>
              <Button size="sm" onClick={() => setShowAssignUser(true)}>{t('pagina_orgs.asignar_usuario')}</Button>
            </div>
            {(detail.users || []).length === 0 && <div className="orgs-box-6">{t('organizations.no_hay_usuarios_asignados')}</div>}
            {(detail.users || []).map((u, idx, arr) => {
              const isLast = arr.length === 1
              return (
                <div key={u.id} className="orgs-row-6">
                  <span>{u.full_name}</span>
                  <span className="u-text2">{u.role}</span>
                  <Button size="xs" variant="secondary" style={{ marginLeft:8 }}
                    title={t('pagina_orgs.entrar_como_este_usuario_soporte_queda')}
                    onClick={() => { setMotivo(''); setPidiendoMotivo({ tipo: 'entrar', userId: String(u.id), nombre: u.full_name }) }}>{t('pagina_orgs.entrar_como')}</Button>
                  <Button
                    size="xs"
                    variant="danger"
                    style={{marginLeft:8, opacity: isLast ? 0.5 : 1, pointerEvents: isLast ? 'none' : 'auto'}}
                    disabled={isLast}
                    title={isLast ? t('pagina_orgs.no_puedes_quitar_el_ultimo_usuario') : t('pagina_orgs.quitar_usuario')}
                    onClick={()=>setRemovingUserId(u.id)}
                  >{t('pagina_orgs.quitar')}</Button>
                </div>
              )
            })}
                      {removingUserId && detail && (
                        <Confirm
                          open
                          title={t('organizations.quitar_usuario_de_la_organizacion')}
                          description={t('pagina_orgs.vas_a_quitar_de_el_usuario', { v1: removingUser?.full_name || t('pagina_orgs.este_usuario'), name: detail.name })}
                          onCancel={()=>setRemovingUserId(null)}
                          onConfirm={()=>removeUser({ orgId: detail.id, userId: removingUserId })}
                          loading={isRemoving}
                        />
                      )}
                {showAssignUser && detail && (
                  <Modal open title={t('pagina_orgs.asignar_usuario')} onClose={() => setShowAssignUser(false)} width={420}>
                    <div className="orgs-stack">
                      <div role="group" aria-labelledby={`${idCampo}-usuario-et`}>
                        <div id={`${idCampo}-usuario-et`} style={ls}>{t('pagina_orgs.usuario')}</div>
                        <UserSelect
                          value={assignUserId}
                          onChange={id => setAssignUserId(id)}
                          placeholder={t('pagina_orgs.buscar_usuario_activo')}
                          style={fs}
                          filterFn={u => u.is_active !== false && !(detail.users || []).some(du => du.id === u.id)}
                        />
                      </div>
                      <div className="orgs-box-7">
                        {assignUserId === '' ? '' : (() => {
                          const user = allUsers.find(u => u.id === assignUserId)
                          if (user && user.is_active === false) return t('pagina_orgs.no_puedes_asignar_usuarios_inactivos')
                          if ((detail.users || []).some(u => u.id === assignUserId)) return t('pagina_orgs.este_usuario_ya_esta_asignado')
                          return ''
                        })()}
                      </div>
                      <div className="u-actions-10">
                        <Button variant="secondary" onClick={()=>setShowAssignUser(false)}>{t('pagina_orgs.cancelar')}</Button>
                        <Button
                          onClick={()=>assignUser({ orgId: detail.id, userId: assignUserId })}
                          disabled={Boolean(!assignUserId || isAssigning || (assignUserId && allUsers.find(u => u.id === assignUserId)?.is_active === false) || (assignUserId && (detail?.users || []).some(u => u.id === assignUserId)))}
                        >{isAssigning ? t('pagina_orgs.asignando') : t('pagina_orgs.asignar')}</Button>
                      </div>
                    </div>
                  </Modal>
                )}
          </div>
        )}
      </div>

      {showCreate && (
        <Modal open title={t('organizations.nueva_organizacion_2')} onClose={() => { setShowCreate(false); createValidation.setErrors({}) }} width={520}>
          <div className="u-stack-14">
            <div className="u-grid2-12">
              <div>
                <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={ls}>{t('pagina_orgs.nombre')}</label>
                <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.name} onChange={e=>{ setForm(f=>({...f,name:e.target.value})); createValidation.clearFieldError('name') }} style={createValidation.inputStyle(fs, 'name')} />
                {createValidation.errors.name && <div className="u-field-error">{errorDeCampo(createValidation.errors.name)}</div>}
              </div>
              <div>
                <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} style={ls}>{t('organizations.slug_identificador_unico')}</label>
                <input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.slug} onChange={e=>{ setForm(f=>({...f,slug:e.target.value.toLowerCase().replace(/\s+/g,'-')})); createValidation.clearFieldError('slug') }} style={createValidation.inputStyle(fs, 'slug')} />
                {createValidation.errors.slug && <div className="u-field-error">{errorDeCampo(createValidation.errors.slug)}</div>}
              </div>
            </div>
            <div className="orgs-grid-3">
              <div><label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} style={ls}>{t('pagina_orgs.plan')}</label>
                <select id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={form.plan} onChange={e=>setForm(f=>({...f,plan:e.target.value}))} style={fs}>
                  {['starter','pro','enterprise'].map(p => <option key={p} value={p}>{p}</option>)}
                </select>
              </div>
              <div>
                <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} style={ls}>{t('organizations.max_usuarios')}</label>
                <input id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} type="number" value={form.max_users} onChange={e=>{ setForm(f=>({...f,max_users:+e.target.value})); createValidation.clearFieldError('max_users') }} style={createValidation.inputStyle(fs, 'max_users')} />
                {createValidation.errors.max_users && <div className="u-field-error">{errorDeCampo(createValidation.errors.max_users)}</div>}
              </div>
              <div>
                <label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} style={ls}>{t('organizations.max_proyectos')}</label>
                <input id={`${idCampo}-5`} aria-labelledby={`${idCampo}-et5`} type="number" value={form.max_projects} onChange={e=>{ setForm(f=>({...f,max_projects:+e.target.value})); createValidation.clearFieldError('max_projects') }} style={createValidation.inputStyle(fs, 'max_projects')} />
                {createValidation.errors.max_projects && <div className="u-field-error">{errorDeCampo(createValidation.errors.max_projects)}</div>}
              </div>
            </div>
            <div className="u-grid2-12">
              <div>
                <label id={`${idCampo}-et6`} htmlFor={`${idCampo}-6`} style={ls}>{t('organizations.email_del_admin')}</label>
                <input id={`${idCampo}-6`} aria-labelledby={`${idCampo}-et6`} value={form.admin_email} onChange={e=>{ setForm(f=>({...f,admin_email:e.target.value})); createValidation.clearFieldError('admin_email') }} style={createValidation.inputStyle(fs, 'admin_email')} />
                {createValidation.errors.admin_email && <div className="u-field-error">{errorDeCampo(createValidation.errors.admin_email)}</div>}
              </div>
              <div>
                <label id={`${idCampo}-et7`} htmlFor={`${idCampo}-7`} style={ls}>{t('pagina_orgs.nombre_del_admin')}</label>
                <input id={`${idCampo}-7`} aria-labelledby={`${idCampo}-et7`} value={form.admin_name} onChange={e=>setForm(f=>({...f,admin_name:e.target.value}))} style={fs} />
              </div>
            </div>
            <div className="orgs-box-8">
              {t('pagina_orgs.con_el_correo_se_crea_el')}
            </div>
            <div>
              <label id={`${idCampo}-et8`} htmlFor={`${idCampo}-8`} style={ls}>{t('pagina_orgs.dominio_propio_opcional')}</label>
              <input id={`${idCampo}-8`} aria-labelledby={`${idCampo}-et8`} value={form.domain} placeholder="app.cliente.com" onChange={e=>{ setForm(f=>({...f,domain:e.target.value})); createValidation.clearFieldError('domain') }} style={createValidation.inputStyle(fs, 'domain')} />
              {createValidation.errors.domain && <div className="u-field-error">{errorDeCampo(createValidation.errors.domain)}</div>}
            </div>
            <div className="u-actions-10">
              <Button variant="secondary" onClick={()=>{ setShowCreate(false); createValidation.setErrors({}) }}>{t('pagina_orgs.cancelar')}</Button>
              <Button onClick={submitCreate} disabled={isPending}>{isPending?t('pagina_orgs.creando'):t('pagina_orgs.crear')}</Button>
            </div>
          </div>
        </Modal>
      )}

      {showEdit && editForm && (
        <Modal open title={t('pagina_orgs.editar_organizacion')} onClose={() => { setShowEdit(false); editValidation.setErrors({}) }} width={520}>
          <div className="u-stack-14">
            <div className="u-grid2-12">
              <div>
                <label id={`${idCampo}-et9`} htmlFor={`${idCampo}-9`} style={ls}>{t('pagina_orgs.nombre')}</label>
                <input id={`${idCampo}-9`} aria-labelledby={`${idCampo}-et9`} value={editForm?.name ?? ''} onChange={e=>{ setEditForm(f => f && ({...f,name:e.target.value})); editValidation.clearFieldError('name') }} style={editValidation.inputStyle(fs, 'name')} />
                {editValidation.errors.name && <div className="u-field-error">{errorDeCampo(editValidation.errors.name)}</div>}
              </div>
              {/* El slug no se puede editar */}
              <div><label id={`${idCampo}-et10`} htmlFor={`${idCampo}-10`} style={ls}>{t('pagina_orgs.slug')}</label><input id={`${idCampo}-10`} aria-labelledby={`${idCampo}-et10`} value={detail?.slug ?? ''} disabled style={{...fs, background:'var(--surface-1)'}} /></div>
            </div>
            <div className="orgs-grid-3">
              <div><label id={`${idCampo}-et11`} htmlFor={`${idCampo}-11`} style={ls}>{t('pagina_orgs.plan')}</label>
                <select id={`${idCampo}-11`} aria-labelledby={`${idCampo}-et11`} value={editForm?.plan ?? ''} onChange={e=>setEditForm(f => f && ({...f,plan:e.target.value}))} style={fs}>
                  {['starter','pro','enterprise'].map(p => <option key={p} value={p}>{p}</option>)}
                </select>
              </div>
              <div>
                <label id={`${idCampo}-et12`} htmlFor={`${idCampo}-12`} style={ls}>{t('organizations.max_usuarios')}</label>
                <input id={`${idCampo}-12`} aria-labelledby={`${idCampo}-et12`} type="number" value={editForm?.max_users ?? ''} onChange={e=>{ setEditForm(f => f && ({...f,max_users:+e.target.value})); editValidation.clearFieldError('max_users') }} style={editValidation.inputStyle(fs, 'max_users')} />
                {editValidation.errors.max_users && <div className="u-field-error">{errorDeCampo(editValidation.errors.max_users)}</div>}
              </div>
              <div>
                <label id={`${idCampo}-et13`} htmlFor={`${idCampo}-13`} style={ls}>{t('organizations.max_proyectos')}</label>
                <input id={`${idCampo}-13`} aria-labelledby={`${idCampo}-et13`} type="number" value={editForm?.max_projects ?? ''} onChange={e=>{ setEditForm(f => f && ({...f,max_projects:+e.target.value})); editValidation.clearFieldError('max_projects') }} style={editValidation.inputStyle(fs, 'max_projects')} />
                {editValidation.errors.max_projects && <div className="u-field-error">{errorDeCampo(editValidation.errors.max_projects)}</div>}
              </div>
            </div>
            <div>
              <label id={`${idCampo}-et14`} htmlFor={`${idCampo}-14`} style={ls}>{t('pagina_orgs.dominio_propio_opcional')}</label>
              <input id={`${idCampo}-14`} aria-labelledby={`${idCampo}-et14`} value={editForm?.domain ?? ''} placeholder="app.cliente.com" onChange={e=>{ setEditForm(f => f && ({...f,domain:e.target.value})); editValidation.clearFieldError('domain') }} style={editValidation.inputStyle(fs, 'domain')} />
              {editValidation.errors.domain && <div className="u-field-error">{errorDeCampo(editValidation.errors.domain)}</div>}
            </div>
            {/* Revisión 2026-11: la MFA obligatoria sólo se podía activar por API. */}
            <label className="orgs-label-4">
              <input type="checkbox" aria-label={t('organizations.exigir_mfa')} checked={!!editForm?.require_mfa} onChange={e => setEditForm(f => f && ({ ...f, require_mfa: e.target.checked }))} className="orgs-input" />
              <span>
                <strong>{t('organizations.exigir_mfa')}</strong>
                <span className="orgs-label-5">{t('organizations.exigir_mfa_ayuda')}</span>
              </span>
            </label>
            <div>
              <label id={`${idCampo}-et15`} htmlFor={`${idCampo}-15`} style={ls}>{t('organizations.email_del_admin')}</label>
              <input id={`${idCampo}-15`} aria-labelledby={`${idCampo}-et15`} value={editForm?.admin_email ?? ''} onChange={e=>{ setEditForm(f => f && ({...f,admin_email:e.target.value})); editValidation.clearFieldError('admin_email') }} style={editValidation.inputStyle(fs, 'admin_email')} />
              {editValidation.errors.admin_email && <div className="u-field-error">{errorDeCampo(editValidation.errors.admin_email)}</div>}
            </div>
            <div className="u-actions-10">
              <Button variant="secondary" onClick={()=>{ setShowEdit(false); editValidation.setErrors({}) }}>{t('pagina_orgs.cancelar')}</Button>
              <Button onClick={submitEdit} disabled={isUpdating}>{isUpdating?t('pagina_orgs.guardando'):t('pagina_orgs.guardar')}</Button>
            </div>
          </div>
        </Modal>
      )}
      {suspendiendo && (
        <Modal open title={t('pagina_orgs.suspender_2', { v1: suspendiendo.name ?? '' })} onClose={() => setSuspendiendo(null)} width={460}>
          <div className="u-stack-14">
            <div className="u-text2-sm">
              {t('pagina_orgs.nadie_de_la_empresa_podra_entrar')}
            </div>
            <div>
              <label id="motivo_suspension-et" style={ls} htmlFor="motivo_suspension">{t('pagina_orgs.motivo_2')}</label>
              <textarea id="motivo_suspension" aria-labelledby="motivo_suspension-et" value={motivo} onChange={e => setMotivo(e.target.value)} rows={3} style={{ ...fs, resize:'vertical' }} />
            </div>
            <div className="u-actions-10">
              <Button variant="secondary" onClick={() => setSuspendiendo(null)}>{t('pagina_orgs.cancelar')}</Button>
              <Button variant="danger" disabled={!motivo.trim()}
                onClick={() => toggle({ id: suspendiendo.id, is_active: false, suspension_reason: motivo.trim() })}>{t('pagina_orgs.suspender')}</Button>
            </div>
          </div>
        </Modal>
      )}

      {pidiendoMotivo && (
        <Modal open title={pidiendoMotivo.tipo === 'baja' ? t('pagina_orgs.dar_de_baja_2', { v1: detail?.name ?? '' }) : t('pagina_orgs.entrar_como_2', { v1: pidiendoMotivo.nombre ?? '' })}
          onClose={() => setPidiendoMotivo(null)} width={460}>
          <div className="u-stack-14">
            <div className="u-text2-sm">
              {pidiendoMotivo.tipo === 'baja'
                ? t('pagina_orgs.la_empresa_se_suspende_ahora_al')
                : t('pagina_orgs.entraras_con_su_sesion_durante_un')}
            </div>
            <div>
              <label id="motivo_org-et" style={ls} htmlFor="motivo_org">{t('pagina_orgs.motivo_2')}</label>
              <textarea id="motivo_org" aria-labelledby="motivo_org-et" value={motivo} onChange={e => setMotivo(e.target.value)} rows={3} style={{ ...fs, resize:'vertical' }} />
            </div>
            <div className="u-actions-10">
              <Button variant="secondary" onClick={() => setPidiendoMotivo(null)}>{t('pagina_orgs.cancelar')}</Button>
              <Button variant={pidiendoMotivo.tipo === 'baja' ? 'danger' : 'primary'} disabled={!motivo.trim() || dandoDeBaja || entrando}
                onClick={() => pidiendoMotivo.tipo === 'baja'
                  ? darDeBaja(motivo.trim())
                  : entrarComo({ userId: pidiendoMotivo.userId!, reason: motivo.trim() })}>
                {pidiendoMotivo.tipo === 'baja' ? t('pagina_orgs.dar_de_baja') : t('pagina_orgs.entrar')}
              </Button>
            </div>
          </div>
        </Modal>
      )}

      {altaHecha && (
        <Modal open title={t('pagina_orgs.empresa_creada')} onClose={() => setAltaHecha(null)} width={460}>
          <div className="orgs-stack-2">
            <div>{t('pagina_orgs.primer_administrador')}{' '}<strong>{altaHecha.email}</strong></div>
            <div>{t('pagina_orgs.contrasena_inicial_solo_se_ensena_ahora')}</div>
            <code style={{ ...fs, userSelect:'all', fontFamily:'monospace' }}>{altaHecha.password}</code>
            <div className="u-row-end">
              <Button onClick={() => setAltaHecha(null)}>{t('pagina_orgs.hecho')}</Button>
            </div>
          </div>
        </Modal>
      )}
    </PageShell>
  )
}
