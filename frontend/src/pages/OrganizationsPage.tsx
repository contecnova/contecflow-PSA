/**
 * OrganizationsPage — Gestión multi-tenant de organizaciones
 *
 * 16-11-2026: "Nueva organización" en la cabecera con icono (antes en el
 * cuerpo y con "+" de texto); título = el del menú; tarjetas con Card del kit
 * (seleccionada en --accent); plan y estado con StatusBadge; fechas con fmtDate
 * según idioma (antes ISO 2026-11-16); "usuarios"/"proyectos" y el rol de cada
 * usuario traducidos; vacíos con EmptyState e icono lucide (antes emoji y
 * texto gris); botones propios → Button; campos con ds-input.
 */
import { useState, useId } from 'react'
import { extractErr, fmtDate } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { confirmar } from '../context/ConfirmContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { organizationsApi } from '../services/api'
import type { DetalleDeOrganizacion, Organizacion } from '../services/api/tipos-plataforma'
import { Button, Card, Checkbox, Modal, Select, Spinner, EmptyState, Input, Textarea } from '../components/ui'
import StatusBadge from '../components/ui/StatusBadge'
import { UserSelect } from '../components/ui/EntitySelect'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Building2, Download, Info, LogIn, Pause, Pencil, Play, Plus, Trash2, Undo2, UserMinus, UserPlus, Users } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import { useOrgSettings } from '../hooks/useOrgSettings'
import { useListaDeUsuarios } from '../hooks/useListas'
import { z } from 'zod'
import { useFormValidation } from '../hooks/useFormValidation'
import './OrganizationsPage.css'



const PLAN_KIND: Record<string, 'neutral' | 'accent' | 'success'> = { starter: 'neutral', pro: 'accent', enterprise: 'success' }
/** Roles del backend → etiqueta traducida (las mismas que el organigrama). */
const ROL_LABEL: Record<string, string> = {
  admin: 'pagina_orgc.admin', pm: 'pagina_orgc.pm', team_lead: 'pagina_orgc.team_lead',
  employee: 'pagina_orgc.empleado', hr: 'pagina_orgc.rrhh', client: 'pagina_orgc.cliente',
}

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
    // Mutación para eliminar usuario de la organización
    const { mutate: removeUser } = useMutation({
      mutationFn: ({ orgId, userId }: { orgId: string | number; userId: string | number }) => organizationsApi.removeUser(orgId, userId),
      onSuccess: () => {
        qc.invalidateQueries({ queryKey: ['org-detail', selected] });
        toast.success(t('pagina_orgs.usuario_eliminado'))
      },
      onError: e => {
        // 23-11-2026 (04 M9): el mensaje sale del código estable del error, no de buscar texto.
        const codigo = (e as { response?: { data?: { code?: unknown } } } | null | undefined)?.response?.data?.code
        if (codigo === 'usuario_ultima_empresa') {
          toast.error(t('pagina_orgs.no_se_puede_quitar_su_ultima_org'))
          return
        }
        if (codigo === 'empresa_ultimo_usuario') {
          toast.error(t('pagina_orgs.no_se_puede_quitar_ultimo_usuario'))
          return
        }
        toast.error(extractErr(e, t('pagina_orgs.error_al_eliminar_usuario')))
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
  // Todos los usuarios activos
  const { data: allUsers = [] } = useListaDeUsuarios()
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
    onSuccess: () => { window.location.assign('/') },
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
        title={t('nav.organizations')}
        subtitle={t('organizations.subtitle')}
        showListExport={orgs.length > 0}
        exportTargetSelector='[data-export-table="organizations-list"]'
        exportFilePrefix='organizations'
        actions={<Button icon={<Plus size={14} />} onClick={() => setShowCreate(true)}>{t('organizations.nueva_organizacion')}</Button>}
      />

      <div className="u-stack-16">
      <div className="orgs-nota">
        <Info size={15} aria-hidden />
        <span>{t('organizations.cada_organizacion_tiene_sus_propios_usuarios_proyectos')}</span>
      </div>

      <div className={`orgs-layout${selected ? ' orgs-layout--detalle' : ''}`}>
        <div className="u-min0">
          {isLoading ? <Spinner /> : orgs.length === 0 ? (
            <Card>
              <EmptyState icon={<Building2 size={28} />} title={t('organizations.no_orgs')} description={t('pagina_orgs.crea_la_primera_organizacion_para_gestionar')}
                action={<Button icon={<Plus size={14} />} onClick={() => setShowCreate(true)}>{t('organizations.nueva_organizacion')}</Button>} />
            </Card>
          ) : (
            <div data-export-table="organizations-list" className="u-stack-10">
              {orgs.map(o => (
                <Card key={o.id} onClick={() => setSelected(selected === o.id ? null : o.id)}
                  className={`orgs-item${o.is_active ? '' : ' orgs-item--inactiva'}${selected === o.id ? ' orgs-item--activa' : ''}`}>
                  <div className="orgs-item__fila">
                    <div className="u-flex1-min0">
                      <div className="orgs-item__cab">
                        <span id={`${idCampo}-${o.id}-n`} className="orgs-item__nombre">{o.name}</span>
                        {o.plan && <StatusBadge kind={PLAN_KIND[o.plan] ?? 'neutral'} caps={false}>{o.plan}</StatusBadge>}
                        {!o.is_active && (
                          <StatusBadge kind="danger" caps={false}>
                            {o.deletion_purge_after ? t('pagina_orgs.baja_se_borra_el', { v1: fmtDate(o.deletion_purge_after) }) : t('pagina_orgs.suspendida')}
                          </StatusBadge>
                        )}
                      </div>
                      <div className="orgs-item__meta">
                        {o.slug}{o.domain ? ` · ${o.domain}` : ''} · {o.admin_email || '—'}
                      </div>
                      {/* Uso frente al límite del plan: el alta de usuarios y proyectos se para al llegar. */}
                      <div className="orgs-item__uso">
                        {([['pagina_orgs.usuarios_min', o.user_count, o.max_users], ['pagina_orgs.proyectos_min', o.project_count, o.max_projects]] as const).map(([k, usados, limite]) => (
                          <span key={k} className={limite != null && (usados ?? 0) >= limite ? 'orgs-item__uso--lleno' : ''}>
                            {usados ?? 0}/{limite ?? '∞'} {t(k)}
                          </span>
                        ))}
                      </div>
                      {!o.is_active && o.suspension_reason && (
                        <div className="orgs-item__motivo">{t('pagina_orgs.motivo')}{' '}{o.suspension_reason}</div>
                      )}
                    </div>
                    <div className="orgs-item__acciones">
                      {o.created_at && <span className="orgs-item__fecha">{fmtDate(o.created_at)}</span>}
                      <span onClick={e => e.stopPropagation()} onKeyDown={e => e.stopPropagation()} role="presentation">
                        <Button size="sm" variant="secondary" icon={o.is_active ? <Pause size={13} /> : <Play size={13} />}
                          onClick={() => { if (o.is_active) { setSuspendiendo(o); setMotivo('') } else toggle({ id: o.id, is_active: true }) }}>
                          {o.is_active ? t('pagina_orgs.suspender') : t('pagina_orgs.activar')}
                        </Button>
                      </span>
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          )}
        </div>

        {selected && detail && (
          <Card className="orgs-detalle">
            <div className="orgs-detalle__cab">
              <div className="orgs-item__nombre">{detail.name}</div>
              <Button size="sm" variant="secondary" icon={<Pencil size={13} />} onClick={openEdit}>{t('pagina_orgs.editar')}</Button>
            </div>
            <div className="orgs-detalle__acciones">
              <Button size="sm" variant="secondary" icon={<Download size={13} />} onClick={() => { void exportar() }}>{t('pagina_orgs.exportar_datos')}</Button>
              {detail.deletion_purge_after
                ? <Button size="sm" variant="secondary" icon={<Undo2 size={13} />} onClick={() => deshacerBaja()}>{t('pagina_orgs.deshacer_baja')}</Button>
                : <Button size="sm" variant="danger" icon={<Trash2 size={13} />} onClick={() => { setMotivo(''); setPidiendoMotivo({ tipo: 'baja' }) }}>{t('pagina_orgs.dar_de_baja')}</Button>}
            </div>
            {detail.deletion_purge_after && (
              <div className="orgs-detalle__aviso">
                {t('pagina_orgs.baja_pedida_fecha', { fecha: fmtDate(detail.deletion_purge_after) })}
              </div>
            )}
            <dl className="orgs-datos">
              {[[t('pagina_orgs.plan'), detail.plan], [t('pagina_orgs.usuarios'), `${detail.users?.length ?? 0}/${detail.max_users}`], [t('pagina_orgs.zona_horaria'), detail.timezone], [t('pagina_orgs.idioma'), detail.locale]].map(([k, v]) => (
                <div key={k} className="orgs-dato">
                  <dt>{k}</dt>
                  <dd>{v || '—'}</dd>
                </div>
              ))}
            </dl>
            <div className="orgs-detalle__usuarios">
              <span className="orgs-detalle__subtitulo">{t('pagina_orgs.usuarios_2')}{detail.users?.length})</span>
              <Button size="sm" icon={<UserPlus size={13} />} onClick={() => setShowAssignUser(true)}>{t('pagina_orgs.asignar_usuario')}</Button>
            </div>
            {(detail.users || []).length === 0 && (
              <EmptyState icon={<Users size={28} />} title={t('organizations.no_hay_usuarios_asignados')} />
            )}
            <ul className="orgs-usuarios">
              {(detail.users || []).map((u, _idx, arr) => {
                const isLast = arr.length === 1
                return (
                  <li key={u.id} className="orgs-usuario">
                    <div className="u-flex1-min0">
                      <div className="orgs-usuario__nombre">{u.full_name}</div>
                      <div className="orgs-usuario__rol">{u.role && ROL_LABEL[u.role] ? t(ROL_LABEL[u.role]) : u.role}</div>
                    </div>
                    <Button size="xs" variant="ghost" icon={<LogIn size={12} />}
                      title={t('pagina_orgs.entrar_como_este_usuario_soporte_queda')}
                      onClick={() => { setMotivo(''); setPidiendoMotivo({ tipo: 'entrar', userId: String(u.id), nombre: u.full_name }) }}>{t('pagina_orgs.entrar_como')}</Button>
                    <Button
                      size="xs"
                      variant="ghost"
                      icon={<UserMinus size={12} />}
                      disabled={isLast}
                      title={isLast ? t('pagina_orgs.no_puedes_quitar_el_ultimo_usuario') : t('pagina_orgs.quitar_usuario')}
                      onClick={async () => {
                        // 23-11-2026: confirmación única (ConfirmContext); antes `ui/Confirm`.
                        if (!detail) return
                        if (await confirmar({ title: t('organizations.quitar_usuario_de_la_organizacion'), danger: true,
                          message: t('pagina_orgs.vas_a_quitar_de_el_usuario', { v1: u.full_name || t('pagina_orgs.este_usuario'), name: detail.name }) }))
                          removeUser({ orgId: detail.id, userId: u.id })
                      }}
                    >{t('pagina_orgs.quitar')}</Button>
                  </li>
                )
              })}
            </ul>
            {showAssignUser && detail && (
              <Modal open title={t('pagina_orgs.asignar_usuario')} onClose={() => setShowAssignUser(false)} size="sm">
                <div className="orgs-stack">
                  <UserSelect
                    label={t('pagina_orgs.usuario')}
                    value={assignUserId}
                    onChange={id => setAssignUserId(id)}
                    placeholder={t('pagina_orgs.buscar_usuario_activo')}
                    filterFn={u => u.is_active !== false && !(detail.users || []).some(du => du.id === u.id)}
                  />
                  <div className="orgs-error">
                    {assignUserId === '' ? '' : (() => {
                      const user = allUsers.find(u => u.id === assignUserId)
                      if (user && user.is_active === false) return t('pagina_orgs.no_puedes_asignar_usuarios_inactivos')
                      if ((detail.users || []).some(u => u.id === assignUserId)) return t('pagina_orgs.este_usuario_ya_esta_asignado')
                      return ''
                    })()}
                  </div>
                  <div className="u-actions-10">
                    <Button variant="secondary" onClick={() => setShowAssignUser(false)}>{t('pagina_orgs.cancelar')}</Button>
                    <Button
                      onClick={() => assignUser({ orgId: detail.id, userId: assignUserId })}
                      loading={isAssigning}
                      disabled={Boolean(!assignUserId || (assignUserId && allUsers.find(u => u.id === assignUserId)?.is_active === false) || (assignUserId && (detail?.users || []).some(u => u.id === assignUserId)))}
                    >{isAssigning ? t('pagina_orgs.asignando') : t('pagina_orgs.asignar')}</Button>
                  </div>
                </div>
              </Modal>
            )}
          </Card>
        )}
      </div>
      </div>

      {showCreate && (
        <Modal open title={t('organizations.nueva_organizacion_2')} onClose={() => { setShowCreate(false); createValidation.setErrors({}) }} size="md">
          <div className="u-stack-14">
            <div className="u-grid2-12">
              <div>
                <Input label={t('pagina_orgs.nombre')} id={`${idCampo}-1`} value={form.name} onChange={e=>{ setForm(f=>({...f,name:e.target.value})); createValidation.clearFieldError('name') }} />
                {createValidation.errors.name && <div className="u-field-error">{errorDeCampo(createValidation.errors.name)}</div>}
              </div>
              <div>
                <Input label={t('organizations.slug_identificador_unico')} id={`${idCampo}-2`} value={form.slug} onChange={e=>{ setForm(f=>({...f,slug:e.target.value.toLowerCase().replace(/\s+/g,'-')})); createValidation.clearFieldError('slug') }} />
                {createValidation.errors.slug && <div className="u-field-error">{errorDeCampo(createValidation.errors.slug)}</div>}
              </div>
            </div>
            <div className="orgs-grid-3">
              <Select label={t('pagina_orgs.plan')} placeholder={false} id={`${idCampo}-3`} value={form.plan} onChange={e=>setForm(f=>({...f,plan:e.target.value}))}>
                  {['starter','pro','enterprise'].map(p => <option key={p} value={p}>{p}</option>)}
                </Select>
              <div>
                <Input label={t('organizations.max_usuarios')} id={`${idCampo}-4`} type="number" value={form.max_users} onChange={e=>{ setForm(f=>({...f,max_users:+e.target.value})); createValidation.clearFieldError('max_users') }} />
                {createValidation.errors.max_users && <div className="u-field-error">{errorDeCampo(createValidation.errors.max_users)}</div>}
              </div>
              <div>
                <Input label={t('organizations.max_proyectos')} id={`${idCampo}-5`} type="number" value={form.max_projects} onChange={e=>{ setForm(f=>({...f,max_projects:+e.target.value})); createValidation.clearFieldError('max_projects') }} />
                {createValidation.errors.max_projects && <div className="u-field-error">{errorDeCampo(createValidation.errors.max_projects)}</div>}
              </div>
            </div>
            <div className="u-grid2-12">
              <div>
                <Input label={t('organizations.email_del_admin')} id={`${idCampo}-6`} value={form.admin_email} onChange={e=>{ setForm(f=>({...f,admin_email:e.target.value})); createValidation.clearFieldError('admin_email') }} />
                {createValidation.errors.admin_email && <div className="u-field-error">{errorDeCampo(createValidation.errors.admin_email)}</div>}
              </div>
              <Input label={t('pagina_orgs.nombre_del_admin')} id={`${idCampo}-7`} value={form.admin_name} onChange={e=>setForm(f=>({...f,admin_name:e.target.value}))} />
            </div>
            <div className="orgs-pista">
              {t('pagina_orgs.con_el_correo_se_crea_el')}
            </div>
            <div>
              <Input label={t('pagina_orgs.dominio_propio_opcional')} id={`${idCampo}-8`} value={form.domain} placeholder="app.cliente.com" onChange={e=>{ setForm(f=>({...f,domain:e.target.value})); createValidation.clearFieldError('domain') }} />
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
        <Modal open title={t('pagina_orgs.editar_organizacion')} onClose={() => { setShowEdit(false); editValidation.setErrors({}) }} size="md">
          <div className="u-stack-14">
            <div className="u-grid2-12">
              <div>
                <Input label={t('pagina_orgs.nombre')} id={`${idCampo}-9`} value={editForm?.name ?? ''} onChange={e=>{ setEditForm(f => f && ({...f,name:e.target.value})); editValidation.clearFieldError('name') }} />
                {editValidation.errors.name && <div className="u-field-error">{errorDeCampo(editValidation.errors.name)}</div>}
              </div>
              {/* El slug no se puede editar */}
              <Input label={t('pagina_orgs.slug')} id={`${idCampo}-10`} value={detail?.slug ?? ''} disabled />
            </div>
            <div className="orgs-grid-3">
              <Select label={t('pagina_orgs.plan')} placeholder={false} id={`${idCampo}-11`} value={editForm?.plan ?? ''} onChange={e=>setEditForm(f => f && ({...f,plan:e.target.value}))}>
                  {['starter','pro','enterprise'].map(p => <option key={p} value={p}>{p}</option>)}
                </Select>
              <div>
                <Input label={t('organizations.max_usuarios')} id={`${idCampo}-12`} type="number" value={editForm?.max_users ?? ''} onChange={e=>{ setEditForm(f => f && ({...f,max_users:+e.target.value})); editValidation.clearFieldError('max_users') }} />
                {editValidation.errors.max_users && <div className="u-field-error">{errorDeCampo(editValidation.errors.max_users)}</div>}
              </div>
              <div>
                <Input label={t('organizations.max_proyectos')} id={`${idCampo}-13`} type="number" value={editForm?.max_projects ?? ''} onChange={e=>{ setEditForm(f => f && ({...f,max_projects:+e.target.value})); editValidation.clearFieldError('max_projects') }} />
                {editValidation.errors.max_projects && <div className="u-field-error">{errorDeCampo(editValidation.errors.max_projects)}</div>}
              </div>
            </div>
            <div>
              <Input label={t('pagina_orgs.dominio_propio_opcional')} id={`${idCampo}-14`} value={editForm?.domain ?? ''} placeholder="app.cliente.com" onChange={e=>{ setEditForm(f => f && ({...f,domain:e.target.value})); editValidation.clearFieldError('domain') }} />
              {editValidation.errors.domain && <div className="u-field-error">{errorDeCampo(editValidation.errors.domain)}</div>}
            </div>
            {/* Revisión 2026-11: la MFA obligatoria sólo se podía activar por API. */}
            <Checkbox className="orgs-check" checked={!!editForm?.require_mfa} onChange={v => setEditForm(f => f && ({ ...f, require_mfa: v }))}
              label={<strong>{t('organizations.exigir_mfa')}</strong>} ayuda={t('organizations.exigir_mfa_ayuda')} />
            <div>
              <Input label={t('organizations.email_del_admin')} id={`${idCampo}-15`} value={editForm?.admin_email ?? ''} onChange={e=>{ setEditForm(f => f && ({...f,admin_email:e.target.value})); editValidation.clearFieldError('admin_email') }} />
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
        <Modal open title={t('pagina_orgs.suspender_2', { v1: suspendiendo.name ?? '' })} onClose={() => setSuspendiendo(null)} size="sm">
          <div className="u-stack-14">
            <div className="u-text2-sm">
              {t('pagina_orgs.nadie_de_la_empresa_podra_entrar')}
            </div>
            <Textarea label={t('pagina_orgs.motivo_2')} id="motivo_suspension" value={motivo} onChange={e => setMotivo(e.target.value)} rows={3} />
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
          onClose={() => setPidiendoMotivo(null)} size="sm">
          <div className="u-stack-14">
            <div className="u-text2-sm">
              {pidiendoMotivo.tipo === 'baja'
                ? t('pagina_orgs.la_empresa_se_suspende_ahora_al')
                : t('pagina_orgs.entraras_con_su_sesion_durante_un')}
            </div>
            <Textarea label={t('pagina_orgs.motivo_2')} id="motivo_org" value={motivo} onChange={e => setMotivo(e.target.value)} rows={3} />
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
        <Modal open title={t('pagina_orgs.empresa_creada')} onClose={() => setAltaHecha(null)} size="sm">
          <div className="orgs-stack-2">
            <div>{t('pagina_orgs.primer_administrador')}{' '}<strong>{altaHecha.email}</strong></div>
            <div>{t('pagina_orgs.contrasena_inicial_solo_se_ensena_ahora')}</div>
            <code className="orgs-clave">{altaHecha.password}</code>
            <div className="u-row-end">
              <Button onClick={() => setAltaHecha(null)}>{t('pagina_orgs.hecho')}</Button>
            </div>
          </div>
        </Modal>
      )}
    </PageShell>
  )
}
