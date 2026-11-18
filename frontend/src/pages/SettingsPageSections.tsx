import React, { useState } from 'react'
import type { CSSProperties, SetStateAction, ChangeEvent, FormEvent } from 'react'
import { z } from 'zod'
import { Link } from 'react-router-dom'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { settingsApi, advancedConfigApi, type DepartmentOut, type CustomRole, type ModuleOption } from '../services/settingsApi'
import { useAuth } from '../context/AuthContext'
import { presupuestosApi } from '../services/api'
import { usersApi, organizationsApi, biSmartAlertsApi, esignApi, apiUrl, esFichaCompleta, type UserPublic, type UserCreatePayload, type UserUpdatePayload } from '../services/api'
import type { ClaveDeFirma, ConfigDeFirma } from '../services/api/tipos-finanzas'
import type { Organizacion } from '../services/api/tipos-plataforma'
import type { MetricasDeAlertaBi } from '../services/api/tipos-bi'
import { Button, Checkbox, GrupoDeOpciones, IconButton, Input, Modal, Pulsable, Select, Spinner, EmptyState, MarcaExterno, Switch, useErroresDeCampo } from '../components/ui'
import type { ErroresDeCampo } from '../components/ui'
import { Search, Layers, Building2, Pencil, Trash2, Check, X, Plus, Pause, Play, Settings, KeyRound, Bell, Palmtree, Hash, Puzzle, Compass, BarChart3, PenLine, Lock, Type, Calendar, List, CheckSquare, Link2, FileSignature, CheckCircle2 } from 'lucide-react'
/*
 * 16-11-2026: pasada de diseño de /settings. Iconos lucide en lugar de emojis
 * (cabeceras de sección, botones de editar, borrar, guardar, cancelar, añadir,
 * activar y desactivar, tipos de campo, sedes y proveedores de firma).
 */
import { useAppLang } from '../i18n/AppLangContext'
import { extractErr } from '../utils/helpers'
import { useFormValidation } from '../hooks/useFormValidation'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import SeccionDeAjustes from './settings-sections/SeccionDeAjustes'
import ConfirmarBajaModal from '../components/alm/ConfirmarBajaModal'
import { IdiomasSection, LogLevelSection, SystemStateSection, RuntimeFlagsSection, IntegrationCredentialsSection } from './settings-sections/SettingsAdvancedSections'

import { ROLE_LABELS, ROLE_COLORS } from '../constants/api'
import { etiquetaCodigo } from '../i18n/etiquetaCodigo'
import { useOrgSettings } from '../hooks/useOrgSettings'
import { timezoneOptions } from '../constants/timezones'
import { COLOR_DATO_POR_DEFECTO } from '../constants/theme'
import { useFormatoMoneda } from '../hooks/useFormatoMoneda'
import './SettingsPageSections.css'

// ── Tipos ─────────────────────────────────────────────────────────────────────
// Formas de lo que devuelve la API para cada sección (app/schemas/** y los
// serializadores de app/services/advanced_config_service.py) y del estado local
// de los formularios. Se declaran con `type` (no `interface`) para que sigan
// siendo asignables a `Record<string, unknown>`, que es lo que piden los
// métodos de escritura de settingsApi/advancedConfigApi.


/** Usuario del listado (`UserPublic`). `GET /users` no manda `hourly_rate` (es
 *  confidencial): la ficha de edición la completa con `GET /users/{id}` (`UserWithRate`). */
type UserRow = UserPublic & {
  hourly_rate?: number | null
  /** Rev. 166 (#27): grado o categoría profesional (ámbito y condiciones de las políticas). */
  grade?: string | null
}

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

type UserFormValues = {
  username: string
  email: string
  full_name: string
  role: string
  department: string
  job_title: string
  grade: string
  // Los <input type="number"> dejan aquí el texto tal cual.
  weekly_capacity_hours: number | string
  hourly_rate: number | string
  timezone: string
  organization_ids: string[]
  organization_id: string
  custom_role_id: string
  password: string
}
/** Sin superadmin el formulario no envía las empresas. */
type UserFormPayload = UserFormValues | Omit<UserFormValues, 'organization_ids' | 'organization_id'>

type RoleForm = { name: string; description: string; color: string; module_access: Record<string, unknown> }

type NotifyKey = 'notify_admin' | 'notify_pm' | 'notify_hr' | 'notify_employee' | 'notify_email'
type AlertConfig = {
  alert_type: string
  label: string
  description?: string | null
  severity: string
  is_enabled: boolean
  threshold_value: number | null
  threshold_unit?: string | null
} & Partial<Record<NotifyKey, boolean>>

type RuleForm = { name: string; metric_key: string; condition: string; threshold: string | number; severity: string; cooldown_minutes: string | number }


type VacationBalance = { user_id: string; user_name: string; department?: string | null; days_entitled: number; days_taken: number; days_pending: number; days_remaining: number }

type NumberingSeq = { entity: string; prefix: string; separator: string; padding: number; include_year: boolean; current_value: number; next_preview: string }

type CustomField = { id: string; entity: string; name: string; field_key: string; field_type: string; is_required: boolean; placeholder?: string | null }
type CustomFieldEdit = { name: string; is_required: boolean; placeholder: string }
type CustomFieldForm = { entity: string; name: string; field_key: string; field_type: string; is_required: boolean; placeholder: string }


type Office = { id: string; name: string; country?: string | null; city?: string | null; timezone?: string | null }
type OfficeForm = { name: string; country: string; city: string; timezone: string }


type DepartmentForm = { name: string; description: string; area_id: string }

type MetricForm = { label: string; description: string; operand_a: string; operator: string; operand_b_type: string; operand_b: string; scale: string | number }

type InputChange = ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>

// ── General: moneda, zona horaria, idioma y jornada de la empresa ───────────────
/**
 * 18-11-2026 (reorganización de Configuración): una sola fuente. Estos cuatro
 * valores son las claves de ejecución `DEFAULT_CURRENCY`, `DEFAULT_TIMEZONE`,
 * `DEFAULT_LANGUAGE` y `DEFAULT_WORKING_HOURS_PER_DAY` (las que lee
 * `/settings/org-defaults`); `PATCH /settings/general/{alias}` las escribe
 * (ALIAS_DE_EJECUCION en app/services/settings_service/generales.py). Antes se
 * guardaban en filas propias que no leía nadie, y Config. dinámica → Locale
 * editaba las de verdad: ahora Config. dinámica las oculta.
 * El nombre visible de la empresa y del producto se edita en Marca.
 * Guardado como el resto de secciones: borrador + «Guardar»; el refresco tras
 * escritura (services/api/refrescoTrasEscritura.ts) actualiza las pantallas.
 */
const CAMPOS_GENERALES = ['currency', 'timezone', 'language', 'work_hours_per_day'] as const
type CampoGeneral = typeof CAMPOS_GENERALES[number]
const IDIOMAS_OPERADOR = ['es', 'en', 'zh'] as const

function GeneralSection() {
  const { t } = useAppLang()
  const toast = useToast()
  const { currencies } = useOrgSettings()
  const { data: settings = [], isLoading } = useQuery({ queryKey: ['settings-general'], queryFn: () => settingsApi.getGeneral().then(r => r.data) })
  const guardados = Object.fromEntries(CAMPOS_GENERALES.map(k => [k, settings.find(s => s.key === k)?.value ?? ''])) as Record<CampoGeneral, string>
  const [borrador, setBorrador] = useState<Partial<Record<CampoGeneral, string>>>({})
  const valor = (k: CampoGeneral) => borrador[k] ?? guardados[k]
  const cambiados = CAMPOS_GENERALES.filter(k => borrador[k] !== undefined && borrador[k] !== guardados[k])
  const { mutate: guardar, isPending } = useMutation({
    mutationFn: async () => { for (const k of cambiados) await settingsApi.updateSetting(k, String(borrador[k])) },
    onSuccess: () => { setBorrador({}); toast.success(t('i18n.saved')) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const poner = (k: CampoGeneral) => (e: ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setBorrador(b => ({ ...b, [k]: e.target.value }))
  const monedas = Array.from(new Set([...(currencies || []), guardados.currency].filter(Boolean)))

  if (isLoading) return <Spinner />
  return (
    <SeccionDeAjustes icon={<Settings size={18} />} title={t('settings.configuracion_general')} description={t('ajustes.general_desc')}>
      <div className="set-grid-fields">
        <Select label={t('settings.currency')} value={valor('currency')} onChange={poner('currency')}
          options={monedas.map(m => ({ value: m, label: m }))} />
        <Select label={t('settings.timezone')} value={valor('timezone')} onChange={poner('timezone')}
          options={timezoneOptions(valor('timezone')).map(tz => ({ value: tz, label: tz }))} />
        <Select label={t('settings_sections.idioma')} value={valor('language')} onChange={poner('language')}
          options={IDIOMAS_OPERADOR.map(l => ({ value: l, label: t(`ajustes.idioma_${l}`) }))} />
        <Input label={t('settings.work_hours')} type="number" min={1} max={24} step={0.5}
          value={valor('work_hours_per_day')} onChange={poner('work_hours_per_day')} />
      </div>
      <div className="set-acciones">
        <span className="u-text2-sm">{t('ajustes.general_nombre_en_marca')} <Link to="/settings/branding" className="set-enlace">{t('settings_page.tab_branding')}</Link></span>
        <Button icon={<Check size={14} />} disabled={cambiados.length === 0} loading={isPending} onClick={() => guardar()}>{t('common.save')}</Button>
      </div>
    </SeccionDeAjustes>
  )
}

// ── Users section ─────────────────────────────────────────────────────────────
function UsersSection() {
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
  const { user: yo, hasRole } = useAuth()
  const esSuperadmin = !!yo?.is_superadmin
  // 18-11-2026: alta, baja y borrado son `require_admin` (app/api/v1/endpoints/users.py);
  // RRHH veía los botones y recibía 403. RRHH sigue editando fichas.
  const esAdmin = hasRole('admin')
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
  const { mutate: deactivate } = useMutation({ mutationFn: (id: string) => usersApi.deactivate(id), onSuccess: () => qc.invalidateQueries({ queryKey: ['users'] }) , onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))})
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
        <div className="set-search">
          <Search size={14} aria-hidden className="set-search-icon" />
          <input value={search} onChange={e => setSearch(e.target.value)}
            placeholder={t('settings.buscar_usuario_por_nombre_o_alias')}
            aria-label={t('settings.buscar_usuario_por_nombre_o_alias')}
            className="ds-input set-search-input" />
        </div>
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
            const roleColor = roleMap[u.role]?.color || ROLE_COLORS[u.role] || 'var(--text-2)'
            const roleLabel = roleMap[u.role]?.description || etiquetaCodigo(t, 'rol_usuario', u.role, ROLE_LABELS[u.role])
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
                : <Pulsable onClick={() => deactivate(u.id)} className="set-btn-ok"><Play size={13} aria-hidden /> {t('settings_sections.activar')}</Pulsable>)}
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
        <div className="u-col-full"><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="set-label">{t('settings_sections.nombre_completo')} *</label><input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.full_name} onChange={set('full_name')} className="set-input" aria-invalid={!!validation.errors.full_name} />{errField('full_name')}</div>
        <div><label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="set-label">{t('settings_sections.usuario')} *</label><input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.username} onChange={set('username')} className="set-input" aria-invalid={!!validation.errors.username} />{errField('username')}</div>
        <div><label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="set-label">{t('settings_sections.email')} *</label><input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} type="email" value={form.email} onChange={set('email')} className="set-input" aria-invalid={!!validation.errors.email} />{errField('email')}</div>
        <div><label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="set-label">{t('settings_sections.rol')}</label><Select suelto placeholder={false} id={`${idCampo}-4`} value={form.role} onChange={set('role')} className="set-input" error={!!validation.errors.role}>
          {/* Un externo se da de alta desde su proveedor (Recursos o Subcontratistas): aquí solo se muestra si ya lo es. */}
          {Object.entries(ROLE_LABELS).filter(([v]) => v !== 'subcontractor' || form.role === 'subcontractor').map(([v, l]) => <option key={v} value={v}>{etiquetaCodigo(t, 'rol_usuario', v, l)}</option>)}
        </Select>{errField('role')}</div>
        <div><label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} className="set-label">{t('settings_sections.rol_personalizado')}</label><Select suelto placeholder={t('settings_sections.ninguno_rol_base')} id={`${idCampo}-5`} value={form.custom_role_id} onChange={set('custom_role_id')} className="set-input">
          {roles.filter(r => !r.is_system).map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
        </Select>{errField('custom_role_id')}</div>
        <div><label id={`${idCampo}-et6`} htmlFor={`${idCampo}-6`} className="set-label">{t('settings_sections.departamento')}</label><Select suelto placeholder={t('settings.sin_departamento')} id={`${idCampo}-6`} value={form.department} onChange={set('department')} className="set-input">
          {departments.filter(d => d.is_active !== false).map(d => <option key={d.id} value={d.name}>{d.name}</option>)}
        </Select>{errField('department')}</div>
        <div><label id={`${idCampo}-et7`} htmlFor={`${idCampo}-7`} className="set-label">{t('settings_sections.cargo')}</label><input id={`${idCampo}-7`} aria-labelledby={`${idCampo}-et7`} value={form.job_title} onChange={set('job_title')} className="set-input" />{errField('job_title')}</div>
        <div><label htmlFor={`${idCampo}-grado`} className="set-label">{t('settings_sections.grado')}</label><input id={`${idCampo}-grado`} aria-label={t('settings_sections.grado')} value={form.grade} onChange={set('grade')} maxLength={60} className="set-input" aria-describedby={`${idCampo}-grado-ayuda`} />{errField('grade')}<span id={`${idCampo}-grado-ayuda`} className="u-text3-xs">{t('settings_sections.grado_ayuda')}</span></div>
        <div><label id={`${idCampo}-et8`} htmlFor={`${idCampo}-8`} className="set-label">{t('settings_sections.horas_semanales')}</label><input id={`${idCampo}-8`} aria-labelledby={`${idCampo}-et8`} type="number" value={form.weekly_capacity_hours} onChange={set('weekly_capacity_hours')} className="set-input" aria-invalid={!!validation.errors.weekly_capacity_hours} />{errField('weekly_capacity_hours')}</div>
        <div><label id={`${idCampo}-et9`} htmlFor={`${idCampo}-9`} className="set-label">{t('settings_sections.tarifa_hora', { simbolo: fmtMoneda.simbolo })}</label><input id={`${idCampo}-9`} aria-labelledby={`${idCampo}-et9`} type="number" value={form.hourly_rate} onChange={set('hourly_rate')} className="set-input" aria-invalid={!!validation.errors.hourly_rate} />{errField('hourly_rate')}</div>
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
        {!isEdit && <div className="u-col-full"><label id={`${idCampo}-et13`} htmlFor={`${idCampo}-13`} className="set-label">{t('settings.contrasena')}</label><input id={`${idCampo}-13`} aria-labelledby={`${idCampo}-et13`} type="password" value={form.password} onChange={set('password')} className="set-input" aria-invalid={!!validation.errors.password} />{errField('password')}</div>}
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
function RolesSection() {
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
            {!r.is_system && <Pulsable onClick={() => deleteRole(r.id)} className="set-btn-delete" aria-label={t('settings_sections.eliminar_x', { nombre: r.name })} title={t('common.delete')}><Trash2 size={14} aria-hidden /></Pulsable>}
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
          <div><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="set-label">{t('common.name')} *</label><input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} className="set-input" disabled={role?.is_system} /></div>
          <div><label id={`${idCampo}-etc613`} htmlFor={`${idCampo}-c613`} className="set-label">{t('settings_sections.color')}</label><div className="u-row-8"><input id={`${idCampo}-c613`} aria-labelledby={`${idCampo}-etc613`} type="color" value={/^#[0-9a-fA-F]{6}$/.test(form.color) ? form.color : COLOR_DATO_POR_DEFECTO} onChange={e => setForm(f => ({ ...f, color: e.target.value }))} className="set-color-input" /><input aria-labelledby={`${idCampo}-etc613`} value={form.color} onChange={e => setForm(f => ({ ...f, color: e.target.value }))} className="set-input set-input--flex" /></div></div>
        </div>
        <div><label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="set-label">{t('settings.descripcion')}</label><input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} className="set-input" /></div>
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

// ── Alert configs section ─────────────────────────────────────────────────────
// Códigos de condición; la etiqueta sale de `condicion_alerta.<código>` (etiquetaCodigo).
const CONDITION_CODES = ['threshold_above', 'threshold_below', 'trend_up', 'trend_down', 'anomaly'] as const
const THRESHOLD_CONDITIONS = ['threshold_above', 'threshold_below']
const NOTIFY_FIELDS: ReadonlyArray<readonly [NotifyKey, string]> = [['notify_admin', 'settings_sections.notif_admin'], ['notify_pm', 'settings_sections.notif_pm'], ['notify_hr', 'settings_sections.notif_rrhh'], ['notify_employee', 'settings_sections.notif_empleado'], ['notify_email', 'settings_sections.notif_email']]

function AlertConfigSection() {
  const idCampo = React.useId()
  const { t } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const SEV_CFG: Record<string, string> = { info: 'var(--accent)', warning: 'var(--warning)', critical: 'var(--danger)' }

  // — system alert configs (fixed 8 types) —
  const { data: configs = [], isLoading } = useQuery<AlertConfig[]>({ queryKey: ['alert-configs'], queryFn: () => advancedConfigApi.getAlertConfigs().then(r => r.data) })
  const { mutate: update } = useMutation({ mutationFn: ({ type, data }: { type: string; data: Partial<AlertConfig> }) => advancedConfigApi.updateAlertConfig(type, data), onSuccess: () => qc.invalidateQueries({ queryKey: ['alert-configs'] }), onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) })

  // — BI custom alert rules —
  const { data: rulesData } = useQuery({ queryKey: ['bi-alert-rules'], queryFn: () => biSmartAlertsApi.listRules().then(r => r.data) })
  const { data: metricsData } = useQuery<MetricasDeAlertaBi>({ queryKey: ['bi-alert-metrics'], queryFn: () => biSmartAlertsApi.supportedMetrics().then(r => r.data) })
  const rules = rulesData?.items ?? []
  const metrics = metricsData?.metrics ?? []

  const { mutate: createRule, isPending: isCreating } = useMutation({
    mutationFn: biSmartAlertsApi.createRule,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['bi-alert-rules'] }); setShowCreate(false); setRuleForm(EMPTY_RULE) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: toggleRule } = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) => biSmartAlertsApi.updateRule(id, { enabled }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['bi-alert-rules'] }),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: deleteRule } = useMutation({
    mutationFn: biSmartAlertsApi.deleteRule,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['bi-alert-rules'] }),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const EMPTY_RULE: RuleForm = { name: '', metric_key: '', condition: 'threshold_above', threshold: '', severity: 'warning', cooldown_minutes: 60 }
  const [ui, setUi] = useState<{ showCreate: boolean; ruleForm: RuleForm }>({ showCreate: false, ruleForm: EMPTY_RULE })
  const { showCreate, ruleForm } = ui
  const setShowCreate = (v: SetStateAction<boolean>) => setUi(s => ({ ...s, showCreate: typeof v === 'function' ? v(s.showCreate) : v }))
  const setRuleForm = (v: SetStateAction<RuleForm>) => setUi(s => ({ ...s, ruleForm: typeof v === 'function' ? v(s.ruleForm) : v }))
  const setR = (k: keyof RuleForm) => (e: InputChange) => setRuleForm(f => ({ ...f, [k]: e.target.value }))
  const condLabel = (c: string) => etiquetaCodigo(t, 'condicion_alerta', c)

  const submitRule = () => {
    if (!ruleForm.name.trim() || !ruleForm.metric_key) { toast.error(t('settings_sections.err_nombre_metrica')); return }
    const payload = { ...ruleForm, cooldown_minutes: +ruleForm.cooldown_minutes }
    if (THRESHOLD_CONDITIONS.includes(ruleForm.condition)) payload.threshold = +ruleForm.threshold
    else delete payload.threshold
    createRule(payload)
  }

  return (
    <SeccionDeAjustes icon={<Bell size={18} />} title={t('settings_sections.alertas_titulo')} description={t('settings_sections.alertas_desc')}>
      {isLoading ? <Spinner /> : (
        <div className="u-stack-10">
          {configs.map(cfg => (
            <div key={cfg.alert_type} className={`set-alert-card ${cfg.is_enabled ? 'set-alert-card--on' : 'set-alert-card--off'}`} style={{ '--set-color': SEV_CFG[cfg.severity] } as CSSProperties}>
              <div className="set-alert-head">
                <div>
                  <div className="set-alert-title">
                    <span className="u-base-700">{cfg.label}</span>
                    <span className="set-sev">{cfg.severity}</span>
                  </div>
                  {cfg.description && <div className="u-text2-sm">{cfg.description}</div>}
                </div>
                <Checkbox className="set-toggle" aria-label={cfg.label} label={<span className="u-text2-sm">{cfg.is_enabled ? t('settings_sections.activa') : t('settings_sections.inactiva')}</span>} checked={cfg.is_enabled} onChange={m => update({ type: cfg.alert_type, data: { is_enabled: m } })} />
              </div>
              {cfg.is_enabled && (
                <div className="set-alert-body">
                  {cfg.threshold_value !== null && (
                    <div className="u-row-center-8">
                      <label id={`${idCampo}-${cfg.alert_type}-etc723`} htmlFor={`${idCampo}-${cfg.alert_type}-c723`} className="u-text2-xs">{t('settings_sections.umbral')}:</label>
                      <input id={`${idCampo}-${cfg.alert_type}-c723`} aria-labelledby={`${idCampo}-${cfg.alert_type}-etc723`} type="number" defaultValue={cfg.threshold_value} onBlur={e => update({ type: cfg.alert_type, data: { threshold_value: +e.target.value } })}
                        className="set-threshold" />
                      <span className="u-text2-xs">{cfg.threshold_unit}</span>
                    </div>
                  )}
                  <div className="u-wrap-10" role="group" aria-label={t('settings_sections.notificar_a')}>
                    {NOTIFY_FIELDS.map(([key, labelKey]) => (
                      <Checkbox key={key} className={`set-notify${cfg[key] ? ' set-notify--on' : ''}`} label={t(labelKey)} checked={!!cfg[key]} onChange={m => update({ type: cfg.alert_type, data: { [key]: m } })} />
                    ))}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* ── Custom BI alert rules ─────────────────── */}
      <div className="set-block-top">
        <div className="u-row-between u-mb-12">
          <div>
            <div className="u-base-700">{t('settings_sections.reglas_personalizadas')}</div>
            <div className="u-text2-sm">{t('settings.alertas_basadas_en_metricas_del_sistema')}</div>
          </div>
          <Button icon={<Plus size={14} />} onClick={() => setShowCreate(true)}>{t('settings.nueva_alerta')}</Button>
        </div>
        {rules.length === 0 ? (
          <div className="set-empty-row">{t('settings.no_hay_reglas_personalizadas_crea_la_primera')}</div>
        ) : (
          <div className="u-stack-8">
            {rules.map(rule => (
              <div key={rule.id} className={`set-rule ${rule.enabled ? 'set-rule--on' : 'set-rule--off'}`} style={{ '--set-color': SEV_CFG[rule.severity] } as CSSProperties}>
                <div className="u-flex1-min0">
                  <div className="set-rule-title">
                    <span className="u-base-600">{rule.name}</span>
                    <span className="set-sev">{rule.severity}</span>
                  </div>
                  <div className="u-text2-xs">
                    {metrics.find(m => m.key === rule.metric_key)?.label ?? rule.metric_key} · {condLabel(rule.condition)}{rule.threshold != null ? ` · ${t('settings_sections.umbral_valor', { valor: rule.threshold })}` : ''}
                  </div>
                </div>
                <div className="set-rule-actions">
                  <Checkbox className="set-notify" aria-label={rule.name} label={rule.enabled ? t('settings_sections.activa') : t('settings_sections.inactiva')} checked={!!rule.enabled} onChange={m => toggleRule({ id: rule.id, enabled: m })} />
                  <Button variant="danger" size="xs" onClick={() => openConfirmGlobal({ title: t('settings_sections.eliminar_regla'), message: t('settings_sections.confirmar_eliminar_x', { nombre: rule.name }), onConfirm: () => deleteRule(rule.id) })}>{t('common.delete')}</Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {showCreate && (
        <Modal open title={t('settings.nueva_regla_de_alerta')} onClose={() => { setShowCreate(false); setRuleForm(EMPTY_RULE) }} width={480}>
          <div className="u-stack-14">
            <div>
              <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="set-label">{t('common.name')}</label>
              <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={ruleForm.name} onChange={setR('name')} className="set-input" placeholder={t('settings.ej_ingresos_por_debajo_del_objetivo')} />
            </div>
            <div>
              <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="set-label">{t('settings.metrica')}</label>
              <Select suelto placeholder={t('settings.selecciona_una_metrica')} id={`${idCampo}-2`} value={ruleForm.metric_key} onChange={setR('metric_key')} className="set-input">
                {metrics.map(m => <option key={m.key} value={m.key}>{m.label}</option>)}
              </Select>
            </div>
            <div className="u-grid2-12">
              <div>
                <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="set-label">{t('settings.condicion')}</label>
                <Select suelto placeholder={false} id={`${idCampo}-3`} value={ruleForm.condition} onChange={setR('condition')} className="set-input">
                  {CONDITION_CODES.map(k => <option key={k} value={k}>{condLabel(k)}</option>)}
                </Select>
              </div>
              {THRESHOLD_CONDITIONS.includes(ruleForm.condition) && (
                <div>
                  <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="set-label">{t('settings_sections.umbral')}</label>
                  <input id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} type="number" value={ruleForm.threshold} onChange={setR('threshold')} className="set-input" placeholder="0" />
                </div>
              )}
            </div>
            <div className="u-grid2-12">
              <div>
                <label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} className="set-label">{t('settings_sections.severidad')}</label>
                <Select suelto placeholder={false} id={`${idCampo}-5`} value={ruleForm.severity} onChange={setR('severity')} className="set-input">
                  <option value="info">{t('settings_sections.sev_info')}</option>
                  <option value="warning">{t('settings_sections.sev_warning')}</option>
                  <option value="critical">{t('settings_sections.sev_critical')}</option>
                </Select>
              </div>
              <div>
                <label id={`${idCampo}-et6`} htmlFor={`${idCampo}-6`} className="set-label">{t('settings_sections.cooldown_minutos')}</label>
                <input id={`${idCampo}-6`} aria-labelledby={`${idCampo}-et6`} type="number" value={ruleForm.cooldown_minutes} onChange={setR('cooldown_minutes')} className="set-input" min={5} />
              </div>
            </div>
            <div className="u-actions-10 set-mt4">
              <Button variant="secondary" onClick={() => { setShowCreate(false); setRuleForm(EMPTY_RULE) }}>{t('common.cancel')}</Button>
              <Button onClick={submitRule} disabled={isCreating}>{isCreating ? t('settings_sections.creando') : t('settings_sections.crear_alerta')}</Button>
            </div>
          </div>
        </Modal>
      )}
    </SeccionDeAjustes>
  )
}

// ── Vacaciones: derecho anual por persona ──────────────────────────────────────
/**
 * 18-11-2026 (reorganización de Configuración): solo el derecho anual
 * (`user_vacation_balances.days_entitled`, PATCH /advanced-config/vacation-balances),
 * que es lo que el motor de Ausencias lee como ficha. Se quitan:
 * - las «políticas de vacaciones» (`vacation_policies`): ningún servicio las lee;
 * - las columnas tomados/pendientes/disponibles: el saldo se calculaba aquí con
 *   otra fórmula que en Ausencias (sin arrastre, ajustes ni prorrateo). El saldo
 *   bueno está en Configuración → Ausencias → Personas y saldos.
 */
function VacationSection() {
  const { t } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const currentYear = new Date().getFullYear()
  const [year, setYear] = useState(currentYear)
  const { data: balances = [] } = useQuery<VacationBalance[]>({ queryKey: ['vacation-balances', year], queryFn: () => advancedConfigApi.getVacationBalances(year).then(r => r.data) })
  const { mutate: updateBalance } = useMutation({ mutationFn: ({ userId, days }: { userId: string; days: number }) => advancedConfigApi.updateVacationBalance(userId, year, days), onSuccess: () => { qc.invalidateQueries({ queryKey: ['vacation-balances', year] }); qc.invalidateQueries({ queryKey: ['vacation-balance-my'] }); } , onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))})

  return (
    <SeccionDeAjustes icon={<Palmtree size={18} />} title={t('settings_sections.vacaciones_titulo')} description={t('ajustes.vacaciones_desc')}>
      <div className="u-row-between u-mb-12">
        <Link to="/settings/ausencias?sub=personas" className="set-enlace">{t('ajustes.ver_saldos')}</Link>
        <Select suelto placeholder={false} value={year} onChange={e => setYear(+e.target.value)} className="set-select-sm" aria-label={t('settings_sections.anio')}>
          {[currentYear - 1, currentYear, currentYear + 1].map(y => <option key={y} value={y}>{y}</option>)}
        </Select>
      </div>
      <div className="ds-card ds-card--plano">
        <div className="set-bal-row set-bal-row--2 set-bal-head">
          <span>{t('settings_sections.persona')}</span><span>{t('settings_sections.asignados')}</span>
        </div>
        {balances.map(b => (
          <div key={b.user_id} className="set-bal-row set-bal-row--2">
            <div>
              <div className="u-base-600">{b.user_name}</div>
              {b.department && <div className="u-text2-xs">{b.department}</div>}
            </div>
            <input type="number" aria-label={t('settings_sections.dias_asignados_de', { nombre: b.user_name })} defaultValue={b.days_entitled} min="0" max="60" onBlur={e => updateBalance({ userId: b.user_id, days: +e.target.value })}
              className="set-threshold set-threshold--full" />
          </div>
        ))}
      </div>
    </SeccionDeAjustes>
  )
}

// ── Numbering section ─────────────────────────────────────────────────────────
function NumberingSection() {
  const idCampo = React.useId()
  const { t } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const { data: seqs = [], isLoading } = useQuery<NumberingSeq[]>({ queryKey: ['numbering-seqs'], queryFn: () => advancedConfigApi.getNumbering().then(r => r.data) })
  const { mutate: update } = useMutation({ mutationFn: ({ entity, data }: { entity: string; data: NumberingSeq }) => advancedConfigApi.updateNumbering(entity, data), onSuccess: () => qc.invalidateQueries({ queryKey: ['numbering-seqs'] }) , onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))})
  const { mutate: reset } = useMutation({ mutationFn: advancedConfigApi.resetNumbering, onSuccess: () => qc.invalidateQueries({ queryKey: ['numbering-seqs'] }) , onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))})
  const entityLabel = (e: string) => (ENTITY_KEYS[e] ? t(ENTITY_KEYS[e]) : e)

  return (
    <SeccionDeAjustes icon={<Hash size={18} />} title={t('settings_sections.numeracion_titulo')} description={t('settings_sections.numeracion_desc')}>
      {isLoading ? <Spinner /> : (
        <div className="u-stack-10">
          {seqs.map(s => (
            <div key={s.entity} className="set-item set-seq">
              <div className="set-seq-name">
                <div className="set-seq-title">{entityLabel(s.entity)}</div>
                <div className="set-seq-preview">{s.next_preview}</div>
              </div>
              <div className="set-seq-fields">
                <div><label htmlFor={`${idCampo}-${s.entity}-c1038`} className="set-label set-label--xs">{t('settings_sections.prefijo')}</label><input aria-label={t('settings_sections.prefijo')} id={`${idCampo}-${s.entity}-c1038`} defaultValue={s.prefix} onBlur={e => update({ entity: s.entity, data: { ...s, prefix: e.target.value } })} className="set-input set-input--w70" placeholder={t('settings_sections.prefijo')} /></div>
                <div><label id={`${idCampo}-${s.entity}-etc1039`} htmlFor={`${idCampo}-${s.entity}-c1039`} className="set-label set-label--xs" title={t('settings_sections.separador')}>{t('settings_sections.sep')}</label><input id={`${idCampo}-${s.entity}-c1039`} aria-labelledby={`${idCampo}-${s.entity}-etc1039`} defaultValue={s.separator} onBlur={e => update({ entity: s.entity, data: { ...s, separator: e.target.value } })} className="set-input set-input--w40" /></div>
                <div><label id={`${idCampo}-${s.entity}-etc1040`} htmlFor={`${idCampo}-${s.entity}-c1040`} className="set-label set-label--xs">{t('settings.digitos')}</label><input id={`${idCampo}-${s.entity}-c1040`} aria-labelledby={`${idCampo}-${s.entity}-etc1040`} type="number" min="1" max="8" defaultValue={s.padding} onBlur={e => update({ entity: s.entity, data: { ...s, padding: +e.target.value } })} className="set-input set-input--w60" /></div>
                <Checkbox className="set-check-muted" label={t('settings.incluir_ano')} checked={!!s.include_year} onChange={m => update({ entity: s.entity, data: { ...s, include_year: m } })} />
              </div>
              <div className="set-shrink0">
                <div className="u-text2-xs-mb4">{t('settings_sections.contador', { valor: s.current_value })}</div>
                <Pulsable onClick={() => { openConfirmGlobal({ message: t('settings_sections.confirmar_resetear', { entidad: entityLabel(s.entity) }), onConfirm: () => reset(s.entity), danger: true }) }} className="set-btn-delete set-btn-delete--md">{t('settings_sections.resetear')}</Pulsable>
              </div>
            </div>
          ))}
        </div>
      )}
    </SeccionDeAjustes>
  )
}

const ENTITY_KEYS: Record<string, string> = {
  project: 'settings_sections.ent_proyecto',
  task: 'settings_sections.ent_tarea',
  user: 'settings_sections.ent_usuario',
  client: 'settings_sections.ent_cliente',
  contract: 'settings_sections.ent_contrato',
  invoice: 'settings_sections.ent_factura',
  absence: 'settings_sections.ent_ausencia',
  document: 'settings_sections.ent_documento',
  risk: 'settings_sections.ent_riesgo',
  deliverable: 'settings_sections.ent_entregable',
  imputation: 'settings_sections.ent_imputacion',
  expense: 'settings_sections.ent_gasto',
  opportunity: 'settings_sections.ent_oportunidad',
  ticket: 'settings_sections.ent_ticket',
  change_request: 'settings_sections.ent_control_cambios',
}
const CUSTOM_FIELD_ENTITIES = ['project', 'task', 'user', 'client', 'contract', 'invoice', 'absence', 'document', 'risk', 'deliverable', 'imputation', 'expense', 'opportunity', 'ticket']
const FIELD_TYPE_KEYS: Record<string, string> = {
  text: 'settings_sections.tipo_texto',
  number: 'settings_sections.tipo_numero',
  date: 'settings_sections.tipo_fecha',
  select: 'settings_sections.tipo_selector',
  boolean: 'settings_sections.tipo_si_no',
  url: 'settings_sections.tipo_url',
}

// ── Custom fields section ─────────────────────────────────────────────────────
function CustomFieldsSection() {
  const idCampo = React.useId()
  const { t } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const { data: fields = [], isLoading } = useQuery<CustomField[]>({ queryKey: ['custom-fields'], queryFn: () => advancedConfigApi.getCustomFields(undefined).then(r => r.data) })
  const { mutate: createField } = useMutation({ mutationFn: advancedConfigApi.createCustomField, onSuccess: () => qc.invalidateQueries({ queryKey: ['custom-fields'] }), onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) })
  const { mutate: updateField } = useMutation({ mutationFn: ({ id, data }: { id: string; data: CustomFieldEdit }) => advancedConfigApi.updateCustomField(id, data), onSuccess: () => { qc.invalidateQueries({ queryKey: ['custom-fields'] }); setEditingFieldId(null) }, onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) })
  const { mutate: deleteField } = useMutation({ mutationFn: advancedConfigApi.deleteCustomField, onSuccess: () => qc.invalidateQueries({ queryKey: ['custom-fields'] }), onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) })
  const [ui, setUi] = useState<{ editingFieldId: string | null; editFieldForm: CustomFieldEdit; form: CustomFieldForm }>({
    editingFieldId: null,
    editFieldForm: { name: '', is_required: false, placeholder: '' },
    form: { entity: 'project', name: '', field_key: '', field_type: 'text', is_required: false, placeholder: '' },
  })
  const { editingFieldId, editFieldForm, form } = ui
  const setEditingFieldId = (v: SetStateAction<string | null>) => setUi(s => ({ ...s, editingFieldId: typeof v === 'function' ? v(s.editingFieldId) : v }))
  const setEditFieldForm = (v: SetStateAction<CustomFieldEdit>) => setUi(s => ({ ...s, editFieldForm: typeof v === 'function' ? v(s.editFieldForm) : v }))
  const setForm = (v: SetStateAction<CustomFieldForm>) => setUi(s => ({ ...s, form: typeof v === 'function' ? v(s.form) : v }))
  const entityLabel = (e: string) => (ENTITY_KEYS[e] ? t(ENTITY_KEYS[e]) : e)
  const typeLabel = (ty: string) => (FIELD_TYPE_KEYS[ty] ? t(FIELD_TYPE_KEYS[ty]) : ty)
  const TYPE_ICONS: Record<string, React.ReactNode> = { text: <Type size={18} />, number: <Hash size={18} />, date: <Calendar size={18} />, select: <List size={18} />, boolean: <CheckSquare size={18} />, url: <Link2 size={18} /> }
  const byEntity = fields.reduce<Record<string, CustomField[]>>((a, f) => { if (!a[f.entity]) a[f.entity] = []; a[f.entity].push(f); return a }, {})

  return (
    <SeccionDeAjustes icon={<Puzzle size={18} />} title={t('settings.custom_fields')} description={t('settings_sections.campos_desc')}>
      {isLoading ? <Spinner /> : (
        <div className="u-mb-20">
          {Object.entries(byEntity).map(([entity, entityFields]) => (
            <div key={entity} className="u-mb-16">
              <div className="set-group-title">
                {entityLabel(entity)}
              </div>
              <div className="u-stack-6">
                {entityFields.map(f => (
                  <React.Fragment key={f.id}>
                    <div className="set-item set-field-row">
                      <span className="set-icon-lg" aria-hidden="true">{TYPE_ICONS[f.field_type] || <Type size={18} />}</span>
                      <div className="u-flex1">
                        <span className="u-base-600">{f.name}</span>
                        <span className="ds-codigo set-key">{f.field_key}</span>
                        {f.is_required && <span className="set-required">*{t('settings_sections.obligatorio_min')}</span>}
                      </div>
                      <span className="u-text2-xs">{typeLabel(f.field_type)}</span>
                      <Pulsable onClick={() => { setEditingFieldId(f.id); setEditFieldForm({ name: f.name, is_required: f.is_required, placeholder: f.placeholder||'' }) }} className="set-btn-edit" aria-label={t('settings_sections.editar_x', { nombre: f.name })} title={t('common.edit')}><Pencil size={14} aria-hidden /></Pulsable>
                      <Pulsable onClick={() => deleteField(f.id)} className="set-btn-delete" aria-label={t('settings_sections.eliminar_x', { nombre: f.name })} title={t('common.delete')}><Trash2 size={14} aria-hidden /></Pulsable>
                    </div>
                    {editingFieldId === f.id && (
                      <div className="set-edit-strip">
                        <input value={editFieldForm.name} onChange={e=>setEditFieldForm(f=>({...f,name:e.target.value}))}
                          className="set-input set-input--f2" placeholder={t('settings.nombre_del_campo')} aria-label={t('settings.nombre_del_campo')} autoFocus />
                        <input value={editFieldForm.placeholder} onChange={e=>setEditFieldForm(f=>({...f,placeholder:e.target.value}))}
                          className="set-input set-input--f2" placeholder={t('settings.placeholder_del_campo')} aria-label={t('settings.placeholder_del_campo')} />
                        <Checkbox className="set-check-nowrap" label={t('settings_sections.obligatorio')} checked={editFieldForm.is_required}
                          onChange={m=>setEditFieldForm(f=>({...f,is_required:m}))} />
                        <Pulsable onClick={() => updateField({ id: f.id, data: editFieldForm })} disabled={!editFieldForm.name} className="set-btn-save set-btn-save--sm"><Check size={13} aria-hidden /> {t('common.save')}</Pulsable>
                        <Pulsable onClick={() => setEditingFieldId(null)} className="set-btn-cancel set-btn-cancel--sm" aria-label={t('common.cancel')} title={t('common.cancel')}><X size={14} aria-hidden /></Pulsable>
                      </div>
                    )}
                  </React.Fragment>
                ))}
              </div>
            </div>
          ))}
          {fields.length === 0 && <EmptyState svgIcon={<Layers size={36} />} title={t('settings.empty_custom_fields_title')} description={t('settings.empty_custom_fields_desc')} />}
        </div>
      )}
      <div className="set-add-panel-basic">
        <div className="set-add-title">{t('settings.anadir_campo_personalizado')}</div>
        <div className="set-grid-add-field">
          <div><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="set-label">{t('settings_sections.entidad')}</label><Select suelto placeholder={false} id={`${idCampo}-1`} value={form.entity} onChange={e => setForm(f => ({ ...f, entity: e.target.value }))} className="set-input">{CUSTOM_FIELD_ENTITIES.map(e => <option key={e} value={e}>{entityLabel(e)}</option>)}</Select></div>
          <div><label htmlFor={`${idCampo}-c1150`} className="set-label">{t('common.name')}</label><input aria-label={t('common.name')} id={`${idCampo}-c1150`} value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value, field_key: e.target.value.toLowerCase().replace(/\s+/g, '_').replace(/[^a-z0-9_]/g, '') }))} className="set-input" placeholder={t('settings.nombre_del_campo')} /></div>
          <div><label htmlFor={`${idCampo}-c1151`} className="set-label">{t('settings_sections.clave')}</label><input aria-label={t('settings_sections.clave')} id={`${idCampo}-c1151`} value={form.field_key} onChange={e => setForm(f => ({ ...f, field_key: e.target.value }))} className="set-input" placeholder={t('settings_sections.clave_interna')} /></div>
          <div><label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="set-label">{t('settings_sections.tipo')}</label><Select suelto placeholder={false} id={`${idCampo}-2`} value={form.field_type} onChange={e => setForm(f => ({ ...f, field_type: e.target.value }))} className="set-input">{Object.keys(FIELD_TYPE_KEYS).map(ty => <option key={ty} value={ty}>{typeLabel(ty)}</option>)}</Select></div>
          <Button onClick={() => { createField(form); setForm({ entity: form.entity, name: '', field_key: '', field_type: 'text', is_required: false, placeholder: '' }) }} disabled={!form.name || !form.field_key}>{t('settings.anadir')}</Button>
        </div>
      </div>
    </SeccionDeAjustes>
  )
}

// ── Offices section ───────────────────────────────────────────────────────────
function OfficesSection() {
  const idCampo = React.useId()
  const { t } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const { timezone: defaultTimezone } = useOrgSettings()
  const { data: offices = [] } = useQuery<Office[]>({ queryKey: ['offices'], queryFn: () => advancedConfigApi.getOffices().then(r => r.data) })
  const { mutate: create } = useMutation({ mutationFn: advancedConfigApi.createOffice, onSuccess: () => qc.invalidateQueries({ queryKey: ['offices'] }), onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) })
  const { mutate: update } = useMutation({ mutationFn: ({ id, data }: { id: string; data: OfficeForm }) => advancedConfigApi.updateOffice(id, data), onSuccess: () => { qc.invalidateQueries({ queryKey: ['offices'] }); setEditingId(null) }, onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) })
  const { mutate: del } = useMutation({ mutationFn: advancedConfigApi.deleteOffice, onSuccess: () => qc.invalidateQueries({ queryKey: ['offices'] }), onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) })
  const [ui, setUi] = useState<{ form: OfficeForm; editingId: string | null; editForm: OfficeForm }>({
    form: { name: '', country: '', city: '', timezone: defaultTimezone },
    editingId: null,
    editForm: { name: '', country: '', city: '', timezone: defaultTimezone },
  })
  const { form, editingId, editForm } = ui
  const setForm = (v: SetStateAction<OfficeForm>) => setUi(s => ({ ...s, form: typeof v === 'function' ? v(s.form) : v }))
  const setEditingId = (v: SetStateAction<string | null>) => setUi(s => ({ ...s, editingId: typeof v === 'function' ? v(s.editingId) : v }))
  const setEditForm = (v: SetStateAction<OfficeForm>) => setUi(s => ({ ...s, editForm: typeof v === 'function' ? v(s.editForm) : v }))

  return (
    <SeccionDeAjustes icon={<Building2 size={18} />} title={t('settings_sections.sedes_titulo')} description={t('settings_sections.sedes_desc')}>
      <div className="set-stack-mb16">
        {offices.map(o => (
          <div key={o.id}>
            {editingId === o.id ? (
              <div className="set-edit-panel">
                <div className="set-fld-name"><label id={`${idCampo}-${o.id}-etc1457`} htmlFor={`${idCampo}-${o.id}-c1457`} className="set-label">{t('common.name')} *</label>
                  <input id={`${idCampo}-${o.id}-c1457`} aria-labelledby={`${idCampo}-${o.id}-etc1457`} value={editForm.name} onChange={e => setEditForm(f=>({...f,name:e.target.value}))} className="set-input" autoFocus /></div>
                <div className="set-fld-sm"><label id={`${idCampo}-${o.id}-etc1459`} htmlFor={`${idCampo}-${o.id}-c1459`} className="set-label">{t('settings.pais')}</label>
                  <input id={`${idCampo}-${o.id}-c1459`} aria-labelledby={`${idCampo}-${o.id}-etc1459`} value={editForm.country} onChange={e => setEditForm(f=>({...f,country:e.target.value}))} className="set-input" /></div>
                <div className="set-fld-sm"><label id={`${idCampo}-${o.id}-etc1461`} htmlFor={`${idCampo}-${o.id}-c1461`} className="set-label">{t('settings_sections.ciudad')}</label>
                  <input id={`${idCampo}-${o.id}-c1461`} aria-labelledby={`${idCampo}-${o.id}-etc1461`} value={editForm.city} onChange={e => setEditForm(f=>({...f,city:e.target.value}))} className="set-input" /></div>
                <div className="set-fld-tz"><label id={`${idCampo}-${o.id}-etc1463`} htmlFor={`${idCampo}-${o.id}-c1463`} className="set-label">{t('settings.timezone')}</label>
                  <Select suelto placeholder={false} id={`${idCampo}-${o.id}-c1463`} value={editForm.timezone} onChange={e => setEditForm(f=>({...f,timezone:e.target.value}))} className="set-input">
                    {timezoneOptions(editForm.timezone).map(tz => <option key={tz} value={tz}>{tz}</option>)}
                  </Select></div>
                <div className="set-actions-inline">
                  <Pulsable onClick={() => update({ id: o.id, data: editForm })} disabled={!editForm.name} className="set-btn-save"><Check size={13} aria-hidden /> {t('common.save')}</Pulsable>
                  <Pulsable onClick={() => setEditingId(null)} className="set-btn-cancel">{t('common.cancel')}</Pulsable>
                </div>
              </div>
            ) : (
              <div className="set-item">
                <span className="set-icon-xl" aria-hidden="true"><Building2 size={22} /></span>
                <div className="u-flex1">
                  <div className="u-base-700">{o.name}</div>
                  <div className="u-text2-xs">{o.city}{o.country ? `, ${o.country}` : ''} · {o.timezone}</div>
                </div>
                <Pulsable onClick={() => { setEditingId(o.id); setEditForm({ name:o.name, country:o.country||'', city:o.city||'', timezone:o.timezone||defaultTimezone }) }} className="set-btn-edit" aria-label={t('settings_sections.editar_x', { nombre: o.name })} title={t('common.edit')}><Pencil size={14} aria-hidden /></Pulsable>
                <Pulsable onClick={() => del(o.id)} className="set-btn-delete" aria-label={t('settings_sections.eliminar_x', { nombre: o.name })} title={t('common.delete')}><Trash2 size={14} aria-hidden /></Pulsable>
              </div>
            )}
          </div>
        ))}
        {offices.length === 0 && <EmptyState svgIcon={<Building2 size={36} />} title={t('settings.sin_sedes_registradas')} description={t('settings_sections.sedes_vacio_desc')} />}
      </div>
      <div className="set-add-panel">
        <div className="set-flex2"><label htmlFor={`${idCampo}-c1491`} className="set-label">{t('common.name')} *</label><input aria-label={t('common.name')} id={`${idCampo}-c1491`} value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} className="set-input" placeholder={t('settings.nombre_de_la_sede')} /></div>
        <div className="u-flex1"><label htmlFor={`${idCampo}-pais`} className="set-label">{t('settings.pais')}</label><input aria-label={t('settings.pais')} id={`${idCampo}-pais`} value={form.country} onChange={e => setForm(f => ({ ...f, country: e.target.value }))} className="set-input" placeholder={t('settings.pais')} /></div>
        <div className="u-flex1"><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="set-label">{t('settings_sections.ciudad')}</label><input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.city} onChange={e => setForm(f => ({ ...f, city: e.target.value }))} className="set-input" /></div>
        <div className="u-flex1"><label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="set-label">{t('settings.timezone')}</label><Select suelto placeholder={false} id={`${idCampo}-2`} value={form.timezone} onChange={e => setForm(f => ({ ...f, timezone: e.target.value }))} className="set-input">{timezoneOptions(form.timezone).map(tz => <option key={tz} value={tz}>{tz}</option>)}</Select></div>
        <Button onClick={() => { create(form); setForm({ name: '', country: '', city: '', timezone: defaultTimezone }) }} disabled={!form.name}>{t('settings.anadir')}</Button>
      </div>
    </SeccionDeAjustes>
  )
}

// ── Departments & Holidays (existing) ─────────────────────────────────────────
function DepartmentsSection() {
  const { t } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const { data = [], isLoading } = useQuery({ queryKey: ['departments'], queryFn: () => settingsApi.getDepartments().then(r => r.data) })
  // Revisión 2026-11: un departamento pertenece a un área (base del presupuesto del área).
  const { data: areas = [] } = useQuery({ queryKey: ['areas'], queryFn: () => presupuestosApi.areas() })
  const nombreDeArea = (id?: string | null) => areas.find(a => a.id === id)?.name
  const refrescar = () => { qc.invalidateQueries({ queryKey: ['departments'] }); qc.invalidateQueries({ queryKey: ['areas'] }) }
  const { mutate: create } = useMutation({ mutationFn: settingsApi.createDepartment, onSuccess: refrescar, onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) })
  const { mutate: update } = useMutation({ mutationFn: ({ id, data }: { id: string; data: Record<string, unknown> }) => settingsApi.updateDepartment(id, data), onSuccess: () => { refrescar(); setEditingId(null) }, onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) })
  const { mutate: del } = useMutation({ mutationFn: settingsApi.deleteDepartment, onSuccess: refrescar, onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) })
  const [ui, setUi] = useState<{ form: DepartmentForm; editingId: string | null; editForm: DepartmentForm }>({
    form: { name: '', description: '', area_id: '' },
    editingId: null,
    editForm: { name: '', description: '', area_id: '' },
  })
  const { form, editingId, editForm } = ui
  const setForm = (v: SetStateAction<DepartmentForm>) => setUi(s => ({ ...s, form: typeof v === 'function' ? v(s.form) : v }))
  const setEditingId = (v: SetStateAction<string | null>) => setUi(s => ({ ...s, editingId: typeof v === 'function' ? v(s.editingId) : v }))
  const setEditForm = (v: SetStateAction<DepartmentForm>) => setUi(s => ({ ...s, editForm: typeof v === 'function' ? v(s.editForm) : v }))
  const selectorDeArea = (valor: string, onChange: (v: string) => void) => (
    <Select suelto placeholder={t('settings.sin_area')} value={valor} onChange={e => onChange(e.target.value)} aria-label={t('settings.area_del_departamento')} className="set-input set-input--f2 set-input--compact">
      {areas.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
    </Select>
  )
  return (
    <>
    <AreasSection />
    <SeccionDeAjustes icon={<Building2 size={18} />} title={t('settings.departments')} description={t('settings_sections.departamentos_desc')}>
      {isLoading ? <Spinner /> : (
        <div className="set-stack-mb12">
          {data.map(d => (
            <div key={d.id}>
              {editingId === d.id ? (
                <div className="set-edit-panel set-edit-panel--center">
                  <input value={editForm.name} onChange={e => setEditForm(f => ({ ...f, name: e.target.value }))}
                    className="set-input set-input--f2 set-input--compact" placeholder={t('settings.nombre_del_departamento')} aria-label={t('settings.nombre_del_departamento')} autoFocus />
                  <input value={editForm.description} onChange={e => setEditForm(f => ({ ...f, description: e.target.value }))}
                    className="set-input set-input--f3 set-input--compact" placeholder={t('common.description')} aria-label={t('settings.descripcion_del_departamento')} />
                  {selectorDeArea(editForm.area_id, v => setEditForm(f => ({ ...f, area_id: v })))}
                  <Pulsable onClick={() => update({ id: d.id, data: { ...editForm, area_id: editForm.area_id || null } })} disabled={!editForm.name} className="set-btn-save set-btn-confirm-light" aria-label={t('common.save')} title={t('common.save')}><Check size={14} aria-hidden /></Pulsable>
                  <Pulsable onClick={() => setEditingId(null)} className="set-btn-cancel set-btn-cancel--sm" aria-label={t('common.cancel')} title={t('common.cancel')}><X size={14} aria-hidden /></Pulsable>
                </div>
              ) : (
                <div className="set-item set-item--wrap">
                  <span className="set-dept-name">{d.name}</span>
                  {nombreDeArea(d.area_id) && <span className="set-area-tag">{nombreDeArea(d.area_id)}</span>}
                  {d.description && <span className="u-text2-sm">{d.description}</span>}
                  <Pulsable onClick={() => { setEditingId(d.id); setEditForm({ name: d.name, description: d.description || '', area_id: d.area_id || '' }) }} className="set-btn-edit" aria-label={t('settings_sections.editar_x', { nombre: d.name })} title={t('common.edit')}><Pencil size={14} aria-hidden /></Pulsable>
                  <Pulsable onClick={() => del(d.id)} className="set-btn-delete" aria-label={t('settings_sections.eliminar_x', { nombre: d.name })} title={t('common.delete')}><Trash2 size={14} aria-hidden /></Pulsable>
                </div>
              )}
            </div>
          ))}
          {data.length === 0 && <div className="set-empty-base">{t('settings.sin_departamentos')}</div>}
        </div>
      )}
      <div className="set-add-inline">
        <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} className="set-input set-input--f2" placeholder={t('settings.nombre_del_departamento')} aria-label={t('settings.nombre_del_departamento')} />
        <input value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} className="set-input set-input--f2" placeholder={t('common.description')} aria-label={t('settings.descripcion_del_departamento')} />
        {selectorDeArea(form.area_id, v => setForm(f => ({ ...f, area_id: v })))}
        <Button onClick={() => { create({ ...form, area_id: form.area_id || null }); setForm({ name: '', description: '', area_id: '' }) }} disabled={!form.name}>{t('settings.anadir')}</Button>
      </div>
    </SeccionDeAjustes>
    </>
  )
}

function AreasSection() {
  const { t } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const { data: areas = [], isLoading } = useQuery({ queryKey: ['areas'], queryFn: () => presupuestosApi.areas() })
  const [nombre, setNombre] = useState('')
  const [editando, setEditando] = useState<{ id: string; name: string } | null>(null)
  const ejecutar = async (f: () => Promise<unknown>) => {
    try { await f(); qc.invalidateQueries({ queryKey: ['areas'] }); qc.invalidateQueries({ queryKey: ['departments'] }) }
    catch (e) { toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) }
  }
  return (
    <SeccionDeAjustes icon={<Compass size={18} />} title={t('settings.areas')} description={t('settings.areas_ayuda')}>
      {isLoading ? <Spinner /> : (
        <div className="set-stack-mb12">
          {areas.map(a => (
            <div key={a.id} className="set-item set-item--wrap">
              {editando?.id === a.id ? (
                <>
                  <input value={editando.name} onChange={e => setEditando({ id: a.id, name: e.target.value })} aria-label={t('settings.nombre_del_area')} className="set-input set-input--f2 set-input--compact" autoFocus />
                  <Pulsable onClick={() => ejecutar(() => presupuestosApi.guardarArea({ name: editando.name }, a.id)).then(() => setEditando(null))} disabled={!editando.name.trim()} className="set-btn-save set-btn-confirm-light" aria-label={t('common.save')} title={t('common.save')}><Check size={14} aria-hidden /></Pulsable>
                  <Pulsable onClick={() => setEditando(null)} className="set-btn-cancel set-btn-cancel--sm" aria-label={t('common.cancel')} title={t('common.cancel')}><X size={14} aria-hidden /></Pulsable>
                </>
              ) : (
                <>
                  <span className="u-base-600">{a.name}</span>
                  <span className="set-area-depts">{a.departamentos.length ? a.departamentos.join(', ') : t('settings.area_sin_departamentos')}</span>
                  <Pulsable onClick={() => setEditando({ id: a.id, name: a.name })} className="set-btn-edit" aria-label={t('settings_sections.editar_x', { nombre: a.name })} title={t('common.edit')}><Pencil size={14} aria-hidden /></Pulsable>
                  <Pulsable onClick={() => ejecutar(() => presupuestosApi.borrarArea(a.id))} className="set-btn-delete" aria-label={t('settings_sections.eliminar_x', { nombre: a.name })} title={t('common.delete')}><Trash2 size={14} aria-hidden /></Pulsable>
                </>
              )}
            </div>
          ))}
          {areas.length === 0 && <div className="set-empty-base">{t('settings.sin_areas')}</div>}
        </div>
      )}
      <div className="set-add-inline">
        <input value={nombre} onChange={e => setNombre(e.target.value)} className="set-input set-input--f2" placeholder={t('settings.nombre_del_area')} aria-label={t('settings.nombre_del_area')} />
        <Button onClick={() => ejecutar(() => presupuestosApi.guardarArea({ name: nombre })).then(() => setNombre(''))} disabled={!nombre.trim()}>{t('settings.anadir')}</Button>
      </div>
    </SeccionDeAjustes>
  )
}



// ── Metrics section ───────────────────────────────────────────────────────────
const OPERATOR_KEYS: Record<string, string> = { '+': 'settings_sections.op_suma', '-': 'settings_sections.op_resta', '*': 'settings_sections.op_multiplica', '/': 'settings_sections.op_divide' }
const EMPTY_METRIC: MetricForm = { label: '', description: '', operand_a: '', operator: '/', operand_b_type: 'metric', operand_b: '', scale: 1 }

function MetricsSection() {
  const idCampo = React.useId()
  const { t } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()

  const { data: metricsData } = useQuery<MetricasDeAlertaBi>({ queryKey: ['bi-alert-metrics'], queryFn: () => biSmartAlertsApi.supportedMetrics().then(r => r.data) })
  const { data: customData } = useQuery({ queryKey: ['bi-custom-metrics'], queryFn: () => biSmartAlertsApi.listCustomMetrics().then(r => r.data) })
  const builtinMetrics = (metricsData?.metrics ?? []).filter(m => !m.is_custom)
  const customMetrics = customData?.items ?? []

  const { mutate: createMetric, isPending: isCreating } = useMutation({
    mutationFn: biSmartAlertsApi.createCustomMetric,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['bi-custom-metrics'] }); qc.invalidateQueries({ queryKey: ['bi-alert-metrics'] }); setShowCreate(false); setForm(EMPTY_METRIC) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: deleteMetric } = useMutation({
    mutationFn: biSmartAlertsApi.deleteCustomMetric,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['bi-custom-metrics'] }); qc.invalidateQueries({ queryKey: ['bi-alert-metrics'] }) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const [ui, setUi] = useState<{ showCreate: boolean; form: MetricForm }>({ showCreate: false, form: EMPTY_METRIC })
  const { showCreate, form } = ui
  const setShowCreate = (v: SetStateAction<boolean>) => setUi(s => ({ ...s, showCreate: typeof v === 'function' ? v(s.showCreate) : v }))
  const setForm = (v: SetStateAction<MetricForm>) => setUi(s => ({ ...s, form: typeof v === 'function' ? v(s.form) : v }))
  const setF = (k: keyof MetricForm) => (e: InputChange) => setForm(f => ({ ...f, [k]: e.target.value }))

  const preview = (() => {
    const la = builtinMetrics.find(m => m.key === form.operand_a)?.label ?? form.operand_a
    const lb = form.operand_b_type === 'metric'
      ? (builtinMetrics.find(m => m.key === form.operand_b)?.label ?? form.operand_b)
      : form.operand_b
    if (!form.operand_a) return ''
    const scaled = parseFloat(String(form.scale)) !== 1 ? ` × ${form.scale}` : ''
    return `(${la} ${form.operator} ${lb})${scaled}`
  })()

  const submit = () => {
    if (!form.label.trim() || !form.operand_a) { toast.error(t('settings_sections.err_nombre_operando')); return }
    if (form.operand_b_type === 'metric' && !form.operand_b) { toast.error(t('settings_sections.err_selecciona_metrica_b')); return }
    createMetric({ ...form, scale: parseFloat(String(form.scale)) || 1 })
  }

  return (
    <SeccionDeAjustes icon={<BarChart3 size={18} />} title={t('settings.metricas')} description={t('settings_sections.metricas_desc')}>
      {/* Built-in metrics */}
      <div className="set-mb24">
        <div className="set-section-title set-section-title--mb">{t('settings.metricas_del_sistema')}{builtinMetrics.length})</div>
        <div className="set-metrics-grid">
          {builtinMetrics.map(m => (
            <div key={m.key} className="set-metric-tile">
              <div className="u-text1-sm-600">{m.label}</div>
              <div className="ds-codigo set-metric-key">{m.key}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Custom metrics */}
      <div>
        <div className="u-row-between u-mb-10">
          <div className="set-section-title">{t('settings.metricas_personalizadas')}{customMetrics.length})</div>
          <Button icon={<Plus size={14} />} onClick={() => setShowCreate(true)}>{t('settings.nueva_metrica')}</Button>
        </div>
        {customMetrics.length === 0 ? (
          <div className="set-empty-row set-empty-row--sm">{t('settings.no_hay_metricas_personalizadas_crea_la_primera')}</div>
        ) : (
          <div className="u-stack-8">
            {customMetrics.map(cm => {
              const f = cm.formula
              const la = builtinMetrics.find(m => m.key === f.operand_a)?.label ?? f.operand_a
              const lb = f.operand_b_type === 'metric'
                ? (builtinMetrics.find(m => m.key === f.operand_b)?.label ?? f.operand_b)
                : f.operand_b
              const scale = f.scale !== 1 ? ` × ${f.scale}` : ''
              return (
                <div key={cm.key} className="set-rule">
                  <div className="u-flex1-min0">
                    <div className="set-metric-name">{cm.label}</div>
                    <div className="ds-codigo set-metric-formula">({la} {f.operator} {lb}){scale}</div>
                    {cm.description && <div className="u-text3-xs-mt2">{cm.description}</div>}
                  </div>
                  <div className="set-rule-actions set-rule-actions--8">
                    <span className="ds-codigo set-metric-id">{cm.key}</span>
                    <Button variant="danger" size="xs" onClick={() => openConfirmGlobal({ title: t('settings_sections.eliminar_metrica'), message: t('settings_sections.confirmar_eliminar_metrica', { nombre: cm.label }), onConfirm: () => deleteMetric(cm.key) })}>{t('common.delete')}</Button>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {showCreate && (
        <Modal open title={t('settings.nueva_metrica_personalizada')} onClose={() => { setShowCreate(false); setForm(EMPTY_METRIC) }} width={500}>
          <div className="u-stack-14">
            <div>
              <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="set-label">{t('common.name')}</label>
              <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.label} onChange={setF('label')} className="set-input" placeholder={t('settings_sections.ej_ratio')} />
            </div>
            <div>
              <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="set-label">{t('settings.descripcion_opcional')}</label>
              <input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.description} onChange={setF('description')} className="set-input" placeholder={t('settings.para_que_sirve_esta_metrica')} />
            </div>
            <div className="set-formula-box">
              <div className="set-formula-title">{t('settings.formula_a_operador_b_escala')}</div>
              <div className="set-formula-grid">
                <div>
                  <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="set-label">{t('settings.metrica_a')}</label>
                  <Select suelto placeholder={t('settings_sections.selecciona')} id={`${idCampo}-3`} value={form.operand_a} onChange={setF('operand_a')} className="set-input">
                    {builtinMetrics.map(m => <option key={m.key} value={m.key}>{m.label}</option>)}
                  </Select>
                </div>
                <div>
                  <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="set-label" title={t('settings_sections.operador')}>{t('settings_sections.op')}</label>
                  <Select suelto placeholder={false} id={`${idCampo}-4`} value={form.operator} onChange={setF('operator')} className="set-input set-input--w70">
                    {Object.entries(OPERATOR_KEYS).map(([k, v]) => <option key={k} value={k}>{k} ({t(v)})</option>)}
                  </Select>
                </div>
                <div>
                  <label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} className="set-label">{t('settings_sections.tipo_b')}</label>
                  <Select suelto placeholder={false} id={`${idCampo}-5`} value={form.operand_b_type} onChange={setF('operand_b_type')} className="set-input">
                    <option value="metric">{t('settings.otra_metrica')}</option>
                    <option value="constant">{t('settings_sections.constante')}</option>
                  </Select>
                </div>
              </div>
              <div className="u-grid2-10">
                <div>
                  <label id={`${idCampo}-etopb`} htmlFor={`${idCampo}-opb`} className="set-label">{form.operand_b_type === 'metric' ? t('settings_sections.metrica_b') : t('settings_sections.valor_constante')}</label>
                  {form.operand_b_type === 'metric' ? (
                    <Select suelto placeholder={t('settings_sections.selecciona')} id={`${idCampo}-opb`} value={form.operand_b} onChange={setF('operand_b')} className="set-input">
                      {builtinMetrics.filter(m => m.key !== form.operand_a).map(m => <option key={m.key} value={m.key}>{m.label}</option>)}
                    </Select>
                  ) : (
                    <input id={`${idCampo}-opb`} aria-labelledby={`${idCampo}-etopb`} type="number" value={form.operand_b} onChange={setF('operand_b')} className="set-input" placeholder="0" />
                  )}
                </div>
                <div>
                  <label id={`${idCampo}-et6`} htmlFor={`${idCampo}-6`} className="set-label">{t('settings_sections.escala')}</label>
                  <input id={`${idCampo}-6`} aria-labelledby={`${idCampo}-et6`} type="number" value={form.scale} onChange={setF('scale')} className="set-input" placeholder="1" step="any" />
                </div>
              </div>
              {preview && (
                <div className="set-preview">
                  {t('settings_sections.vista_previa', { formula: preview })}
                </div>
              )}
            </div>
            <div className="u-actions-10">
              <Button variant="secondary" onClick={() => { setShowCreate(false); setForm(EMPTY_METRIC) }}>{t('common.cancel')}</Button>
              <Button onClick={submit} disabled={isCreating}>{isCreating ? t('settings_sections.creando') : t('settings_sections.crear_metrica')}</Button>
            </div>
          </div>
        </Modal>
      )}
    </SeccionDeAjustes>
  )
}


// ── E-firma (Electronic Signature) settings ───────────────────────────────────
type ESignFieldKey = ClaveDeFirma
/** GET /esign/config, o el formulario a medio rellenar. */
type ESignConfig = Partial<ConfigDeFirma>
type ESignProvider = {
  id: string
  label: string
  icon: React.ReactNode
  configKey: 'docusign_configured' | 'adobe_configured'
  fields: Array<{ key: ESignFieldKey; label: string; placeholder: string; secret: boolean }>
}

const ESIGN_PROVIDERS: ESignProvider[] = [
  {
    id: 'docusign',
    label: 'DocuSign',
    icon: <FileSignature size={18} />,
    configKey: 'docusign_configured',
    fields: [
      { key: 'docusign_integration_key', label: 'Integration Key (Client ID)', placeholder: 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx', secret: false },
      { key: 'docusign_account_id',      label: 'Account ID',                  placeholder: 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx', secret: false },
      { key: 'docusign_secret_key',      label: 'Secret Key',                  placeholder: '••••••••••••••••',                     secret: true  },
      { key: 'docusign_base_url',        label: 'Base URL',                    placeholder: 'https://demo.docusign.net/restapi',   secret: false },
    ],
  },
  {
    id: 'adobe',
    label: 'Adobe Sign',
    icon: <PenLine size={18} />,
    configKey: 'adobe_configured',
    fields: [
      { key: 'adobe_sign_client_id',     label: 'Client ID',     placeholder: 'CBJCH…',                                         secret: false },
      { key: 'adobe_sign_client_secret', label: 'Client Secret', placeholder: '••••••••••••••••',                               secret: true  },
      { key: 'adobe_sign_base_url',      label: 'Base URL',      placeholder: 'https://api.na1.adobesign.com/api/rest/v6',     secret: false },
    ],
  },
]

interface ProviderCardProps {
  provider: ESignProvider
  config: ESignConfig | undefined
  form: ESignConfig
  onChange: (key: ESignFieldKey, value: string) => void
  onSave: (provider: ESignProvider) => void
  isSaving: boolean
}

function ProviderCard({ provider, config, form, onChange, onSave, isSaving }: ProviderCardProps) {
  const idCampo = React.useId()
  const { t } = useAppLang()
  const isConfigured = config?.[provider.configKey]
  const handleSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    onSave(provider)
  }
  return (
    <div className={`set-provider${isConfigured ? ' set-provider--ok' : ''}`}>
      <div className="u-row-between u-mb-14">
        <div className="u-row-center-8">
          <span className="set-provider-icon" aria-hidden="true">{provider.icon}</span>
          <span className="u-md-700">{provider.label}</span>
        </div>
        <span className={`set-status${isConfigured ? ' set-status--ok' : ''}`}>
          {isConfigured ? <><CheckCircle2 size={13} aria-hidden /> {t('settings_sections.configurado')}</> : t('settings_sections.no_configurado')}
        </span>
      </div>

      <form onSubmit={handleSubmit}>
        <div className="set-grid2-mb14">
        {provider.fields.map(f => (
          <div key={f.key}>
            <label id={`${idCampo}-${f.key}-etc1934`} htmlFor={`${idCampo}-${f.key}-c1934`} className="set-label">{f.label}</label>
            <input id={`${idCampo}-${f.key}-c1934`} aria-labelledby={`${idCampo}-${f.key}-etc1934`}
              type={f.secret ? 'password' : 'text'}
              value={form[f.key] ?? ''}
              onChange={e => onChange(f.key, e.target.value)}
              placeholder={f.secret && form[f.key] === '***' ? t('settings_sections.guardado_cambiar') : f.placeholder}
              className="set-input"
              autoComplete="off"
            />
          </div>
        ))}
        </div>

        <div className="u-row-end">
          <Button size="sm" type="submit" loading={isSaving}>{t('settings_sections.guardar_x', { nombre: provider.label })}</Button>
        </div>
      </form>
    </div>
  )
}
function ESignSettingsSection() {
  const { t } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()

  const { data: config, isLoading } = useQuery<ESignConfig>({
    queryKey: ['esign-config'],
    queryFn: () => esignApi.getConfig().then(r => r.data),
  })

  const [form, setForm] = useState<ESignConfig>({})
  React.useEffect(() => {
    if (config) setForm({ ...config })
  }, [config])

  const { mutate: save, isPending: isSaving } = useMutation({
    mutationFn: (data: Partial<Record<ESignFieldKey, string>>) => esignApi.saveConfig(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['esign-config'] })
      qc.invalidateQueries({ queryKey: ['esign-stats'] })
      toast.success(t('settings.settings_saved'))
    },
    onError: e => toast.error(extractErr(e, t('settings_sections.err_guardar_config'))),
  })

  const handleChange = (key: ESignFieldKey, value: string) => setForm(f => ({ ...f, [key]: value }))

  const handleSave = (provider: ESignProvider) => {
    const payload: Partial<Record<ESignFieldKey, string>> = {}
    provider.fields.forEach(f => {
      const val = form[f.key]
      if (val !== undefined) payload[f.key] = val
    })
    save(payload)
  }

  return (
    <SeccionDeAjustes icon={<PenLine size={18} />} title={t('settings.firma_electronica')} description={t('settings_sections.firma_desc')}>
      {isLoading ? (
        <Spinner />
      ) : (
        <>
          <div className="set-note">
            <div className="set-note-title">{t('settings_sections.modo_manual')}</div>
            <div className="u-text2-sm">
              {t('settings.sin_credenciales_las_solicitudes_se_gestionan_en')}
            </div>
          </div>

          <div className="u-mb-20">
            <div className="set-eyebrow">{t('settings.webhooks_de_sincronizacion_de_estado')}</div>
            <div className="set-code-box">
              <div className="u-text2-xs-mb4">{t('settings.configura_en_el_panel_de_tu_proveedor')}</div>
              <div className="set-code-line">DocuSign Connect: <span className="ds-codigo u-text1">{apiUrl('/esign/webhooks/docusign')}</span></div>
              <div className="set-code-line">Adobe Sign: <span className="ds-codigo u-text1">{apiUrl('/esign/webhooks/adobe')}</span></div>
            </div>
          </div>

          {ESIGN_PROVIDERS.map(provider => (
            <ProviderCard
              key={provider.id}
              provider={provider}
              config={config}
              form={form}
              onChange={handleChange}
              onSave={handleSave}
              isSaving={isSaving}
            />
          ))}
        </>
      )}
    </SeccionDeAjustes>
  )
}

// ── Session security ──────────────────────────────────────────────────────────
const IDLE_TIMEOUT_OPTIONS = [5, 10, 15, 30, 60, 120, 240]

function SessionSecuritySection() {
  const { t } = useAppLang()
  const qc = useQueryClient()
  const toast = useToast()

  const { data: settings = [] } = useQuery({
    queryKey: ['settings-general'],
    queryFn: () => settingsApi.getGeneral().then(r => r.data),
  })
  const { mutate: update } = useMutation({
    mutationFn: ({ key, value }: { key: string; value: string }) => settingsApi.updateSetting(key, value),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['settings-general'] }),
    onError: e => toast.error(extractErr(e, t('settings_sections.err_guardar'))),
  })

  const find = (k: string) => settings.find(s => s.key === k)?.value
  const idleEnabled = find('idle_timeout_enabled') === 'true'
  const idleMinutes = parseInt(find('idle_timeout_minutes') || '30', 10)

  return (
    <SeccionDeAjustes icon={<Lock size={18} />} title={t('settings.seguridad_de_sesion')} description={t('settings_sections.sesion_desc')}>
      <div className="set-session">

        {/* Toggle idle timeout */}
        <div className="set-panel set-panel--row">
          <div>
            <div className="set-panel-title">
              {t('settings.cierre_de_sesion_por_inactividad')}
            </div>
            <div className="u-text3-xs-mt2">
              {t('settings.cierra_la_sesion_automaticamente_si_el_usuario')}
            </div>
          </div>
          <Switch aria-label={t('settings.cierre_de_sesion_por_inactividad')} checked={idleEnabled}
            onChange={m => update({ key: 'idle_timeout_enabled', value: m ? 'true' : 'false' })} />
        </div>

        {/* Timeout duration selector */}
        <div className={`set-panel${idleEnabled ? '' : ' set-panel--off'}`} role="group" aria-labelledby="set-idle-minutes" aria-disabled={!idleEnabled || undefined}>
          <span id="set-idle-minutes" className="set-label">{t('settings.minutos_de_inactividad_antes_de_cerrar_sesion')}</span>
          <div className="set-options">
            {IDLE_TIMEOUT_OPTIONS.map(m => (
              <IconButton
                key={m}
                ariaLabel={m < 60 ? t('settings_sections.n_min', { n: m }) : t('settings_sections.n_h', { n: m / 60 })}
                aria-pressed={m === idleMinutes}
                tabIndex={idleEnabled ? undefined : -1}
                onClick={() => update({ key: 'idle_timeout_minutes', value: String(m) })}
                className={`set-option${m === idleMinutes ? ' set-option--on' : ''}`}
              >
                {m < 60 ? t('settings_sections.n_min', { n: m }) : t('settings_sections.n_h', { n: m / 60 })}
              </IconButton>
            ))}
          </div>
          <div className="set-hint-mt10">
            {t('settings.se_mostrara_un_aviso_60_segundos_antes')}
          </div>
        </div>

      </div>
    </SeccionDeAjustes>
  )
}
export {
  GeneralSection,
  SessionSecuritySection,
  UsersSection,
  RolesSection,
  AlertConfigSection,
  MetricsSection,
  VacationSection,
  DepartmentsSection,
  OfficesSection,
  NumberingSection,
  CustomFieldsSection,
  IdiomasSection,
  LogLevelSection,
  SystemStateSection,
  ESignSettingsSection,
  RuntimeFlagsSection,
  IntegrationCredentialsSection,
}
