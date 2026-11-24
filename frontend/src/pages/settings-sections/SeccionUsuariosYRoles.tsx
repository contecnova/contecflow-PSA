/**
 * Secciones de usuarios y roles con sus modales y esquemas.
 * Troceado de SettingsPageSections.tsx sin cambio de comportamiento (23-11-2026).
 */
import React, { useState, type CSSProperties, type SetStateAction, type FormEvent } from 'react'
import { z } from 'zod'
import { openConfirmGlobal } from '../../context/ConfirmContext'
import { useToast } from '../../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { settingsApi, advancedConfigApi, type DepartmentOut, type CustomRole, type ModuleOption } from '../../services/settingsApi'
import { useAuth } from '../../context/AuthContext'
import { usersApi, organizationsApi, esFichaCompleta, type UserCreatePayload, type UserUpdatePayload } from '../../services/api'
import type { Organizacion } from '../../services/api/tipos-plataforma'
import {
  Buscador,
  Button,
  Checkbox,
  GrupoDeOpciones,
  Input,
  Modal,
  Pulsable,
  Select,
  Spinner,
  MarcaExterno,
  useErroresDeCampo,
  type ErroresDeCampo, IconButton,
} from '../../components/ui'
import { Pencil, Trash2, Plus, Pause, Play, KeyRound } from 'lucide-react'
import { useAppLang } from '../../i18n/AppLangContext'
import { extractErr } from '../../utils/helpers'
import { useFormValidation } from '../../hooks/useFormValidation'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import SeccionDeAjustes from './SeccionDeAjustes'
import ConfirmarBajaModal from '../../components/alm/ConfirmarBajaModal'
import { etiquetaCodigo } from '../../i18n/etiquetaCodigo'
import { timezoneOptions } from '../../constants/timezones'
import { COLOR_DATO_POR_DEFECTO } from '../../constants/theme'
import { useFormatoMoneda } from '../../hooks/useFormatoMoneda'
import { useRolesReales } from '../../hooks/useRolesReales'
import { type InputChange, type RoleForm, type UserFormPayload, type UserFormValues, type UserRow } from './tiposDeAjustes'

/** Campos opcionales del formulario de usuario en los que '' significa «sin valor». */
const CAMPOS_USUARIO_VACIABLES = ['hourly_rate', 'timezone', 'custom_role_id'] as const

function limpiarUsuario(data: UserFormPayload, modo: 'omitir' | 'anular'): Record<string, unknown> {
  const limpio: Record<string, unknown> = { ...data }
  for (const campo of CAMPOS_USUARIO_VACIABLES) {
    if (limpio[campo] !== '') continue
    if (modo === 'omitir') delete limpio[campo]
    else limpio[campo] = null
  }
  return limpio
}

// ── Users section ─────────────────────────────────────────────────────────────
export function UsersSection() {
  const { t } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  type UsersUi = { showCreate: boolean; editUser: UserRow | null; search: string; orgFilter: string }
  const [ui, setUi] = React.useReducer(
    (s: UsersUi, p: Partial<UsersUi> | ((s: UsersUi) => Partial<UsersUi>)): UsersUi => {
      const next = typeof p === 'function' ? p(s) : p
      return { ...s, ...next }
    },
    { showCreate: false, editUser: null, search: '', orgFilter: '' },
  )
  const { showCreate, editUser, search, orgFilter } = ui
  const setShowCreate = (v: SetStateAction<boolean>) => setUi(typeof v === 'function' ? (s: UsersUi) => ({ showCreate: v(s.showCreate) }) : { showCreate: v })
  // Fase 4 de licencias y hardware: desactivar enseña antes qué se libera y qué equipo debe volver.
  const [bajaDe, setBajaDe] = useState<{ id: string; nombre: string } | null>(null)
  const setEditUser = (v: SetStateAction<UserRow | null>) => setUi(typeof v === 'function' ? (s: UsersUi) => ({ editUser: v(s.editUser) }) : { editUser: v })
  const setSearch = (v: SetStateAction<string>) => setUi(typeof v === 'function' ? (s: UsersUi) => ({ search: v(s.search) }) : { search: v })
  const setOrgFilter = (v: SetStateAction<string>) => setUi(typeof v === 'function' ? (s: UsersUi) => ({ orgFilter: v(s.orgFilter) }) : { orgFilter: v })
  const { data: users = [], isLoading } = useQuery<UserRow[]>({ queryKey: ['users', 'fichas'], queryFn: () => usersApi.list().then(r => r.data.filter(esFichaCompleta)) })
  const { data: roles = [] } = useQuery({ queryKey: ['custom-roles'], queryFn: () => advancedConfigApi.getRoles().then(r => r.data) })
  const { data: departments = [] } = useQuery({ queryKey: ['departments-select'], queryFn: () => settingsApi.getDepartments().then(r => r.data) })
  // La lista de empresas y asignar a otras es del superadmin (la API la sirve
  // sólo a él); un admin de empresa da de alta en la suya (revisión 2026-11).
  const { puede } = useAuth()
  const esSuperadmin = puede('plataforma.empresas')
  // 18-11-2026: alta, baja y borrado son `require_admin` (app/api/v1/endpoints/users.py);
  // RRHH veía los botones y recibía 403. RRHH sigue editando fichas.
  const esAdmin = puede('org.administrar')
  const { data: organizations = [] } = useQuery<Organizacion[]>({ queryKey: ['orgs-for-users'], queryFn: () => organizationsApi.list().then(r => r.data), enabled: esSuperadmin })
  const roleMap = Object.fromEntries(roles.map(r => [r.name, r]))
  // El formulario envía los campos tal como los tiene (la tarifa y las horas como
  // texto; pydantic los convierte). Un '' en la tarifa o la zona horaria es «sin valor»:
  // en el alta se omite y al editar viaja como null (un '' en la tarifa daba 422).
  // Auditoría 2026-11 (#25).
  const camposAlta = useErroresDeCampo()
  const camposEdicion = useErroresDeCampo()
  const { mutate: createUser, isPending: creating } = useMutation({ onMutate: () => camposAlta.limpiar(), mutationFn: (data: UserFormPayload) => usersApi.create(limpiarUsuario(data, 'omitir') as unknown as UserCreatePayload), onSuccess: () => { qc.invalidateQueries({ queryKey: ['users'] }); setShowCreate(false) } , onError: e => { if (!camposAlta.recoger(e)) toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) }})
  const { mutate: updateUser, isPending: updating } = useMutation({ onMutate: () => camposEdicion.limpiar(), mutationFn: ({ id, data }: { id: string; data: UserFormPayload }) => usersApi.update(id, limpiarUsuario(data, 'anular') as UserUpdatePayload), onSuccess: () => { qc.invalidateQueries({ queryKey: ['users'] }); qc.invalidateQueries({ queryKey: ['user-detail'] }); setEditUser(null) } , onError: e => { if (!camposEdicion.recoger(e)) toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) }})
  // `GET /users` (`UserPublic`) no lleva la tarifa, que es confidencial: la ficha la
  // pide a `GET /users/{id}` (`UserWithRate`) al abrirse.
  const { data: editUserDetail, isFetched: editUserFetched } = useQuery({
    queryKey: ['user-detail', editUser?.id],
    queryFn: () => usersApi.get(editUser?.id ?? '').then(r => r.data),
    enabled: !!editUser,
  })
  // Auditoría 22-11-2026 (A1 del 04b): «Activar» llamaba a desactivar (DELETE) y relanzaba la baja de ALM.
  const { mutate: reactivate } = useMutation({ mutationFn: (id: string) => usersApi.reactivate(id), onSuccess: () => qc.invalidateQueries({ queryKey: ['users'] }) , onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))})
  const { mutate: deletePermanent } = useMutation({ mutationFn: usersApi.deletePermanent, onSuccess: () => { qc.invalidateQueries({ queryKey: ['users'] }); qc.invalidateQueries({ queryKey: ['users-settings'] }); qc.invalidateQueries({ queryKey: ['resources'] }); } , onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))})
  const filtered = users.filter(u => {
    const bySearch = !search
      || u.full_name?.toLowerCase().includes(search.toLowerCase())
      || u.username?.toLowerCase().includes(search.toLowerCase())

    if (!bySearch) return false
    if (!orgFilter) return true

    const orgs = Array.isArray(u.organizations) ? u.organizations : []
    const hasInMemberships = orgs.some(o => String(o.id) === String(orgFilter))
    const hasPrimary = String(u.organization_id || '') === String(orgFilter)
    return hasInMemberships || hasPrimary
  })
  return (
    <SeccionDeAjustes title={t('settings.users')} description={t('settings_sections.users_desc')}>
      <div className="ds-toolbar set-toolbar">
        <Buscador className="set-search" value={search} onChange={setSearch} placeholder={t('settings.buscar_usuario_por_nombre_o_alias')} aria-label={t('settings.buscar_usuario_por_nombre_o_alias')} />
        <Select suelto placeholder={t('settings.todas_las_organizaciones')} value={orgFilter} onChange={(e) => setOrgFilter(e.target.value)} className="set-org-filter" aria-label={t('settings.filtrar_usuarios_por_organizacion')}>
          {organizations.filter(o => o.is_active !== false).map(o => (
            <option key={o.id} value={o.id}>{o.name}</option>
          ))}
        </Select>
        {(search || orgFilter) && (
          <Button
            variant="secondary"
            onClick={() => {
              setSearch('')
              setOrgFilter('')
            }}
          >
            {t('settings_sections.limpiar_filtros')}
          </Button>
        )}
        {esAdmin && <Button icon={<Plus size={14} />} onClick={() => setShowCreate(true)}>{t('settings.nuevo_usuario')}</Button>}
      </div>
      {isLoading ? <Spinner /> : (
        <div className="u-stack-8">
          {filtered.map(u => {
            const roleColor = roleMap[u.role]?.color || 'var(--text-2)'
            const roleLabel = roleMap[u.role]?.description || etiquetaCodigo(t, 'rol_usuario', u.role)
            const orgs = Array.isArray(u.organizations) ? u.organizations : []
            const primaryOrgId = u.organization_id || ''
            const principal = ` (${t('settings_sections.principal')})`
            return (
            <div key={u.id} className={`set-item${u.is_active ? '' : ' set-item--inactive'}`} style={{ '--set-color': roleColor } as CSSProperties}>
              <div className="set-avatar" aria-hidden="true">
                {u.full_name?.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()}
              </div>
              <div className="u-flex1">
                <div className="u-base-600">{u.full_name} <MarcaExterno persona={u} /></div>
                <div className="u-text2-xs">{u.username} · {u.email}</div>
              </div>
              <span className="set-role-badge">{roleLabel}</span>
              {orgs.length > 0 && (
                <div className="u-wrap-center-8">
                  {orgs.slice(0, 3).map(org => {
                    const isPrimary = String(org.id || '') === String(primaryOrgId)
                    return (
                      <span key={org.id} className={`set-org-chip${isPrimary ? ' set-org-chip--primary' : ''}`}>
                        {org.name || org.slug || org.id}{isPrimary ? principal : ''}
                      </span>
                    )
                  })}
                  {orgs.length > 3 && (
                    <span
                      title={orgs.map(org => `${org.name || org.slug || org.id}${String(org.id || '') === String(primaryOrgId) ? principal : ''}`).join('\n')}
                      className="set-more"
                    >
                      +{orgs.length - 3}
                    </span>
                  )}
                </div>
              )}
              {u.department && <span className="u-text2-xs">{u.department}</span>}
              {!u.is_active && <span className="set-inactive">{t('settings_sections.inactivo')}</span>}
              <Pulsable onClick={() => setEditUser(u)} className="set-btn-edit"><Pencil size={13} aria-hidden /> {t('common.edit')}</Pulsable>
              {esAdmin && (u.is_active ? <Pulsable onClick={() => setBajaDe({ id: u.id, nombre: u.full_name })} className="set-btn-warn"><Pause size={13} aria-hidden /> {t('settings_sections.desactivar')}</Pulsable>
                : <Pulsable onClick={() => openConfirmGlobal({ title: t('settings_sections.activar'), message: t('settings_sections.confirmar_reactivar_usuario', { nombre: u.full_name ?? '' }), confirmLabel: t('settings_sections.activar'), onConfirm: () => reactivate(u.id) })} className="set-btn-ok"><Play size={13} aria-hidden /> {t('settings_sections.activar')}</Pulsable>)}
              {esAdmin && <Pulsable onClick={() => openConfirmGlobal({ title: t('settings_sections.eliminar_permanentemente'), message: t('settings_sections.confirmar_eliminar_usuario', { nombre: u.full_name }), onConfirm: () => deletePermanent(u.id), danger: true })} className="set-btn-delete"><Trash2 size={13} aria-hidden /> {t('common.delete')}</Pulsable>}
            </div>
          )})}
        </div>
      )}
      <UserFormModal open={showCreate} roles={roles} departments={departments} organizations={organizations} esSuperadmin={esSuperadmin} campos={camposAlta} onClose={() => setShowCreate(false)} onSave={createUser} isPending={creating} />
      {bajaDe && <ConfirmarBajaModal userId={bajaDe.id} nombre={bajaDe.nombre} onClose={() => setBajaDe(null)} />}
      {editUser && editUserFetched && <UserFormModal open roles={roles} departments={departments} organizations={organizations} esSuperadmin={esSuperadmin} campos={camposEdicion} user={editUserDetail ? { ...editUser, ...editUserDetail } : editUser} onClose={() => setEditUser(null)} onSave={data => updateUser({ id: editUser.id, data })} isPending={updating} />}
    </SeccionDeAjustes>
  )
}

// Zod schema mirroring backend UserBase/UserCreate (app/schemas/users.py).
// Los mensajes son claves de i18n: `errField` los traduce al pintarlos.
const userFormSchemaBase = z.object({
  username: z.string().trim().min(1, 'settings_sections.err_usuario_obligatorio').max(150, 'settings_sections.err_max_150'),
  email: z.string().trim().min(1, 'settings_sections.err_email_obligatorio').pipe(z.email('settings_sections.err_email_invalido').max(200, 'settings_sections.err_max_200')),
  full_name: z.string().trim().min(1, 'settings_sections.err_nombre_obligatorio').max(255, 'settings_sections.err_max_255'),
  role: z.string().min(1, 'settings_sections.err_selecciona_rol'),
  department: z.union([z.literal(''), z.string().max(100)]).optional(),
  job_title: z.union([z.literal(''), z.string().max(150)]).optional(),
  grade: z.union([z.literal(''), z.string().max(60)]).optional(),
  weekly_capacity_hours: z.coerce.number({ error: 'settings_sections.err_numero' })
    .min(0, 'settings_sections.err_no_negativo')
    .max(168, 'settings_sections.err_max_168h'),
  hourly_rate: z.union([
    z.literal(''),
    z.coerce.number({ error: 'settings_sections.err_numero' }).nonnegative('settings_sections.err_no_negativo'),
  ]).optional(),
  timezone: z.union([z.literal(''), z.string()]).optional(),
  organization_ids: z.array(z.string()).optional(),
  organization_id: z.union([z.literal(''), z.string()]).optional(),
  custom_role_id: z.union([z.literal(''), z.string()]).optional(),
})

const userCreateSchema = userFormSchemaBase.extend({
  password: z.string().min(6, 'settings_sections.err_min_6').max(128, 'settings_sections.err_max_128'),
})

const userEditSchema = userFormSchemaBase.extend({
  password: z.union([z.literal(''), z.string().min(6, 'settings_sections.err_min_6')]).optional(),
})

interface UserFormModalProps {
  open: boolean
  onClose: () => void
  user?: UserRow | null
  onSave: (data: UserFormPayload) => void
  isPending?: boolean
  roles?: CustomRole[]
  departments?: DepartmentOut[]
  organizations?: Organizacion[]
  esSuperadmin?: boolean
  campos: ErroresDeCampo
}

function UserFormModal({ open, onClose, user, onSave, isPending, roles = [], departments = [], organizations = [], esSuperadmin = false, campos }: UserFormModalProps) {
  const fmtMoneda = useFormatoMoneda()
  const idCampo = React.useId()
  const { t } = useAppLang()
  const isEdit = !!user
  const [form, setForm] = useState<UserFormValues>({
    username: user?.username || '',
    email: user?.email || '',
    full_name: user?.full_name || '',
    role: user?.role || 'employee',
    department: user?.department || '',
    job_title: user?.job_title || '',
    grade: user?.grade || '',
    weekly_capacity_hours: user?.weekly_capacity_hours || 40,
    hourly_rate: user?.hourly_rate || '',
    timezone: user?.timezone || '',
    organization_ids: (Array.isArray(user?.organization_ids) && user.organization_ids.length > 0)
      ? user.organization_ids
      : (user?.organization_id ? [user.organization_id] : []),
    organization_id: user?.organization_id || '',
    custom_role_id: user?.custom_role_id || '',
    password: '',
  })
  const validation = useFormValidation(isEdit ? userEditSchema : userCreateSchema)
  // 19-11-2026: roles reales del backend (`GET /auth/roles`), no una lista escrita aquí.
  const rolesReales = useRolesReales()
  const set = (k: keyof UserFormValues) => (e: InputChange) => {
    setForm(f => ({ ...f, [k]: e.target.value }))
    validation.clearFieldError(k)
    campos.limpiar(k)
  }
  const setOrganizations = (values: string[]) => {
    setForm((f) => {
      const nextPrimary = values.includes(f.organization_id)
        ? f.organization_id
        : (values[0] || '')
      return { ...f, organization_ids: values, organization_id: nextPrimary }
    })
    validation.clearFieldError('organization_ids')
    campos.limpiar('organization_ids')
  }
  const textoError = (key: string) => (validation.errors[key] ? t(validation.errors[key]) : campos.de(key))
  const errField = (key: string) => textoError(key) && (
    <div className="u-field-error" role="alert">{textoError(key)}</div>
  )
  const handleSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const result = validation.validateForm(form)
    if (!result.success) return
    if (esSuperadmin) { onSave(form); return }
    // Sin superadmin, las empresas no se tocan: el servidor da de alta en la propia.
    const { organization_ids: _ids, organization_id: _principal, ...resto } = form
    onSave(resto)
  }
  return (
    <Modal open={open} onClose={onClose} title={isEdit ? t('settings_sections.editar_usuario', { nombre: user.full_name }) : t('settings_sections.nuevo_usuario_titulo')} width={580}>
      <form onSubmit={handleSubmit}>
        <div className="u-grid2-14">
        <div className="u-col-full"><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="set-label">{t('settings_sections.nombre_completo')} *</label><Input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.full_name} onChange={set('full_name')} aria-invalid={!!validation.errors.full_name} inputClassName="set-input" />{errField('full_name')}</div>
        <div><label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="set-label">{t('settings_sections.usuario')} *</label><Input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.username} onChange={set('username')} aria-invalid={!!validation.errors.username} inputClassName="set-input" />{errField('username')}</div>
        <div><label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="set-label">{t('settings_sections.email')} *</label><Input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} type="email" value={form.email} onChange={set('email')} aria-invalid={!!validation.errors.email} inputClassName="set-input" />{errField('email')}</div>
        <div><label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="set-label">{t('settings_sections.rol')}</label><Select suelto placeholder={false} id={`${idCampo}-4`} value={form.role} onChange={set('role')} className="set-input" error={!!validation.errors.role}>
          {/* Un externo se da de alta desde su proveedor (Recursos o Subcontratistas): aquí solo se muestra si ya lo es. */}
          {rolesReales.filter(r => r.interno || form.role === r.id).map(r => <option key={r.id} value={r.id}>{r.etiqueta}</option>)}
        </Select>{errField('role')}</div>
        <div><label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} className="set-label">{t('settings_sections.rol_personalizado')}</label><Select suelto placeholder={t('settings_sections.ninguno_rol_base')} id={`${idCampo}-5`} value={form.custom_role_id} onChange={set('custom_role_id')} className="set-input">
          {roles.filter(r => !r.is_system).map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
        </Select>{errField('custom_role_id')}</div>
        <div><label id={`${idCampo}-et6`} htmlFor={`${idCampo}-6`} className="set-label">{t('settings_sections.departamento')}</label><Select suelto placeholder={t('settings.sin_departamento')} id={`${idCampo}-6`} value={form.department} onChange={set('department')} className="set-input">
          {departments.filter(d => d.is_active !== false).map(d => <option key={d.id} value={d.name}>{d.name}</option>)}
        </Select>{errField('department')}</div>
        <div><label id={`${idCampo}-et7`} htmlFor={`${idCampo}-7`} className="set-label">{t('settings_sections.cargo')}</label><Input id={`${idCampo}-7`} aria-labelledby={`${idCampo}-et7`} value={form.job_title} onChange={set('job_title')} inputClassName="set-input" />{errField('job_title')}</div>
        <div><label htmlFor={`${idCampo}-grado`} className="set-label">{t('settings_sections.grado')}</label><Input id={`${idCampo}-grado`} aria-label={t('settings_sections.grado')} value={form.grade} onChange={set('grade')} maxLength={60} aria-describedby={`${idCampo}-grado-ayuda`} inputClassName="set-input" />{errField('grade')}<span id={`${idCampo}-grado-ayuda`} className="u-text3-xs">{t('settings_sections.grado_ayuda')}</span></div>
        <div><label id={`${idCampo}-et8`} htmlFor={`${idCampo}-8`} className="set-label">{t('settings_sections.horas_semanales')}</label><Input id={`${idCampo}-8`} aria-labelledby={`${idCampo}-et8`} type="number" value={form.weekly_capacity_hours} onChange={set('weekly_capacity_hours')} aria-invalid={!!validation.errors.weekly_capacity_hours} inputClassName="set-input" />{errField('weekly_capacity_hours')}</div>
        <div><label id={`${idCampo}-et9`} htmlFor={`${idCampo}-9`} className="set-label">{t('settings_sections.tarifa_hora', { simbolo: fmtMoneda.simbolo })}</label><Input id={`${idCampo}-9`} aria-labelledby={`${idCampo}-et9`} type="number" value={form.hourly_rate} onChange={set('hourly_rate')} aria-invalid={!!validation.errors.hourly_rate} inputClassName="set-input" />{errField('hourly_rate')}</div>
        {esSuperadmin && <>
        <GrupoDeOpciones tipo="checkbox" forma="lista" className="u-col-full set-input--multi"
          leyenda={t('settings.organizaciones_seleccion_multiple')}
          valor={form.organization_ids} onChange={setOrganizations}
          opciones={organizations.filter(o => o.is_active !== false).map(o => ({ valor: String(o.id), titulo: `${o.name} (${o.slug})` }))} />
        <div className="u-col-full">
          <label id={`${idCampo}-et11`} htmlFor={`${idCampo}-11`} className="set-label">{t('settings.organizacion_principal')}</label>
          <Select suelto placeholder={t('settings.sin_organizacion_principal')} id={`${idCampo}-11`} value={form.organization_id} onChange={set('organization_id')} className="set-input">
            {form.organization_ids.map(orgId => {
              const org = organizations.find(o => o.id === orgId)
              return <option key={orgId} value={orgId}>{org?.name || orgId}</option>
            })}
          </Select>{errField('organization_id')}
        </div>
        </>}
        <div className="u-col-full">
          <label id={`${idCampo}-et12`} htmlFor={`${idCampo}-12`} className="set-label">{t('settings.timezone')}</label>
          <Select suelto placeholder={t('settings.usa_la_zona_de_la_organizacion')} id={`${idCampo}-12`} value={form.timezone} onChange={set('timezone')} className="set-input">
            {timezoneOptions(form.timezone).map(tz => <option key={tz} value={tz}>{tz}</option>)}
          </Select>{errField('timezone')}
        </div>
        {!isEdit && <div className="u-col-full"><label id={`${idCampo}-et13`} htmlFor={`${idCampo}-13`} className="set-label">{t('settings.contrasena')}</label><Input id={`${idCampo}-13`} aria-labelledby={`${idCampo}-et13`} type="password" value={form.password} onChange={set('password')} aria-invalid={!!validation.errors.password} inputClassName="set-input" />{errField('password')}</div>}
        <div className="set-form-actions">
          <Button variant="secondary" type="button" onClick={onClose}>{t('common.cancel')}</Button>
          <Button type="submit" disabled={isPending}>
            {isPending ? t('common.saving') : isEdit ? t('common.save') : t('settings_sections.crear')}
          </Button>
        </div>
        </div>
      </form>
    </Modal>
  )
}

// ── Roles section ─────────────────────────────────────────────────────────────
export function RolesSection() {
  const { t } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const [ui, setUi] = useState<{ showCreate: boolean; editRole: CustomRole | null }>({ showCreate: false, editRole: null })
  const { showCreate, editRole } = ui
  const setShowCreate = (v: SetStateAction<boolean>) => setUi(s => ({ ...s, showCreate: typeof v === 'function' ? v(s.showCreate) : v }))
  const setEditRole = (v: SetStateAction<CustomRole | null>) => setUi(s => ({ ...s, editRole: typeof v === 'function' ? v(s.editRole) : v }))
  const { data: roles = [], isLoading } = useQuery({ queryKey: ['custom-roles'], queryFn: () => advancedConfigApi.getRoles().then(r => r.data) })
  const { data: modules = [] } = useQuery({ queryKey: ['modules-list'], queryFn: () => advancedConfigApi.getModules().then(r => r.data) })
  const { mutate: deleteRole } = useMutation({ mutationFn: advancedConfigApi.deleteRole, onSuccess: () => qc.invalidateQueries({ queryKey: ['custom-roles'] }) , onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))})

  return (
    <SeccionDeAjustes icon={<KeyRound size={18} />} title={t('settings_sections.roles_titulo')} description={t('settings_sections.roles_desc')}>
      <div className="u-stack-8">
        {isLoading ? <Spinner /> : roles.map(r => {
          const activos = Object.values(r.module_access || {}).filter(Boolean).length
          return (
          <div key={r.id} className="set-item set-item--lg set-item--tinted" style={{ '--set-color': r.color } as CSSProperties}>
            <div className="set-dot" aria-hidden="true" />
            <div className="u-flex1">
              <div className="u-base-700">{r.name}</div>
              {r.description && <div className="u-text2-sm">{r.description}</div>}
              <div className="set-modules">
                {Object.entries(r.module_access || {}).filter(([, v]) => v).slice(0, 8).map(([m]) => (
                  <span key={m} className="set-module-tag">{m}</span>
                ))}
                {activos > 8 && <span className="set-module-more">+{activos - 8}</span>}
              </div>
            </div>
            {r.is_system && <span className="set-chip">{t('settings_sections.sistema')}</span>}
            <Pulsable onClick={() => setEditRole(r)} className="set-btn-edit"><Pencil size={13} aria-hidden /> {t('common.edit')}</Pulsable>
            {!r.is_system && <IconButton variante="caja" tono="peligro" onClick={() => openConfirmGlobal({ title: t('settings_sections.eliminar_x', { nombre: r.name }), message: t('settings_sections.confirmar_eliminar_x', { nombre: r.name }), danger: true, onConfirm: () => deleteRole(r.id) })} ariaLabel={t('settings_sections.eliminar_x', { nombre: r.name })} title={t('common.delete')}><Trash2 size={14} aria-hidden /></IconButton>}
          </div>
        )})}
        <Pulsable onClick={() => setShowCreate(true)} className="set-btn-dashed"><Plus size={13} aria-hidden /> {t('settings_sections.crear_rol')}</Pulsable>
      </div>
      {(showCreate || editRole) && (
        <RoleFormModal role={editRole} modules={modules} onClose={() => { setShowCreate(false); setEditRole(null) }}
          onSave={data => { const fn = editRole ? () => advancedConfigApi.updateRole(editRole.id, data) : () => advancedConfigApi.createRole(data); fn().then(() => { qc.invalidateQueries({ queryKey: ['custom-roles'] }); setShowCreate(false); setEditRole(null) }) }} />
      )}
    </SeccionDeAjustes>
  )
}

function RoleFormModal({ role, modules, onClose, onSave }: { role: CustomRole | null; modules: ModuleOption[]; onClose: () => void; onSave: (data: RoleForm) => void }) {
  const idCampo = React.useId()
  const { t } = useAppLang()
  const [form, setForm] = useState<RoleForm>({ name: role?.name || '', description: role?.description || '', color: /^#[0-9a-fA-F]{6}$/.test(role?.color) ? role.color : COLOR_DATO_POR_DEFECTO, module_access: role?.module_access || {} })
  const toggleModule = (m: string) => setForm(f => ({ ...f, module_access: { ...f.module_access, [m]: !f.module_access[m] } }))
  const allOn = modules.every(m => form.module_access[m.id])
  return (
    <Modal open title={role ? t('settings_sections.editar_rol', { nombre: role.name }) : t('settings_sections.nuevo_rol')} onClose={onClose} width={560}>
      <div className="u-stack-14">
        <div className="set-grid-2-1">
          <div><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="set-label">{t('common.name')} *</label><Input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} disabled={role?.is_system} inputClassName="set-input" /></div>
          <div><label id={`${idCampo}-etc613`} htmlFor={`${idCampo}-c613`} className="set-label">{t('settings_sections.color')}</label><div className="u-row-8"><input id={`${idCampo}-c613`} aria-labelledby={`${idCampo}-etc613`} type="color" value={/^#[0-9a-fA-F]{6}$/.test(form.color) ? form.color : COLOR_DATO_POR_DEFECTO} onChange={e => setForm(f => ({ ...f, color: e.target.value }))} className="set-color-input" /><Input aria-labelledby={`${idCampo}-etc613`} value={form.color} onChange={e => setForm(f => ({ ...f, color: e.target.value }))} className="set-input--flex" /></div></div>
        </div>
        <div><label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="set-label">{t('settings.descripcion')}</label><Input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} inputClassName="set-input" /></div>
        <div role="group" aria-labelledby={`${idCampo}-mods`}>
          <div className="set-row-label">
            <span id={`${idCampo}-mods`} className="set-label">{t('settings.modulos_accesibles')}</span>
            <Pulsable onClick={() => setForm(f => ({ ...f, module_access: modules.reduce<Record<string, unknown>>((a, m) => ({ ...a, [m.id]: !allOn }), {}) }))} className="set-btn-link">
              {allOn ? t('settings_sections.desactivar_todos') : t('settings_sections.activar_todos')}
            </Pulsable>
          </div>
          <div className="set-grid-3">
            {modules.map(m => (
              <Checkbox key={m.id} className={`set-check-tile${form.module_access[m.id] ? ' set-check-tile--on' : ''}`} label={m.label} checked={!!form.module_access[m.id]} onChange={() => toggleModule(m.id)} />
            ))}
          </div>
        </div>
        <div className="u-actions-10">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={() => onSave(form)} disabled={!form.name}>{t('common.save')}</Button>
        </div>
      </div>
    </Modal>
  )
}
