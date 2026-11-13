import React, { useState } from 'react'
import type { CSSProperties, SetStateAction, ChangeEvent, FormEvent } from 'react'
import { z } from 'zod'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { settingsApi, advancedConfigApi, type SettingOut, type DepartmentOut, type CustomRole, type ModuleOption } from '../services/settingsApi'
import { useAuth } from '../context/AuthContext'
import { presupuestosApi } from '../services/api'
import { usersApi, organizationsApi, biSmartAlertsApi, esignApi, apiUrl, type UserListItem, type UserCreatePayload, type UserUpdatePayload } from '../services/api'
import { Button, Modal, Spinner, EmptyState } from '../components/ui'
import { Search, Layers, Sparkles, Building2 } from 'lucide-react'
import { useAppLang } from '../i18n/AppLangContext'
import { extractErr } from '../utils/helpers'
import { useFormValidation } from '../hooks/useFormValidation'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import SeccionDeAjustes from './settings-sections/SeccionDeAjustes'
import { IdiomasSection, EmailInboundSection, LogLevelSection, SystemStateSection, RuntimeFlagsSection, IntegrationCredentialsSection } from './settings-sections/SettingsAdvancedSections'

import { ROLE_LABELS, ROLE_COLORS } from '../constants/api'
import { useOrgSettings } from '../hooks/useOrgSettings'
import { timezoneOptions } from '../constants/timezones'
import { COLOR_DATO_POR_DEFECTO, alpha } from '../constants/theme'
import { useFormatoMoneda } from '../hooks/useFormatoMoneda'
const fs: CSSProperties = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '10px 14px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
const ls: CSSProperties = { fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.07em', display: 'block', marginBottom: 6 }

// Shared, repeated inline-style fragments. Use spreads to add per-instance tweaks.
const styles: Record<string, CSSProperties> = {
  colGap8: { display: 'flex', flexDirection: 'column', gap: 8 },
  colGap10: { display: 'flex', flexDirection: 'column', gap: 10 },
  colGap14: { display: 'flex', flexDirection: 'column', gap: 14 },
  colGap16: { display: 'flex', flexDirection: 'column', gap: 16 },
  rowEndsCenter: { display: 'flex', justifyContent: 'space-between', alignItems: 'center' },
  rowFlexEnd: { display: 'flex', justifyContent: 'flex-end', gap: 10 },
  btnDelete: { background: 'none', border: '1px solid var(--danger-border)', borderRadius: 'var(--radius-sm)', padding: '3px 8px', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-xs)" },
  btnEdit: { background: 'none', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-sm)', padding: '3px 8px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-xs)" },
  addPanel10: { display: 'flex', gap: 10, padding: '10px 14px', background: 'var(--accent-muted)', border: '1px dashed var(--accent-border)', borderRadius: 'var(--radius-md)', flexWrap: 'wrap', alignItems: 'flex-end' },
  addPanelBasic: { padding: '14px 16px', background: 'var(--accent-muted)', border: '1px dashed var(--accent-border)', borderRadius: 'var(--radius-md)' },
  saveBtn: { background: 'var(--accent)', border: 'none', borderRadius: 'var(--radius-sm)', padding: '6px 14px', color: 'var(--on-accent)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' },
  cancelBtnSm: { background: 'none', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-sm)', padding: '6px 10px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)" },
  cardListItem: { display: 'flex', alignItems: 'center', gap: 14, padding: '10px 14px', background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-md)' },
  mutedCenter: { fontSize: "var(--text-sm)", color: 'var(--text-3)', textAlign: 'center' },
  pill: { fontSize: "var(--text-2xs)", background: 'var(--accent-muted)', color: 'var(--accent)', borderRadius: 20, padding: '1px 8px', marginLeft: 8 },
  sectionTitleUpper: { fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '.07em' },
}

// ── Tipos ─────────────────────────────────────────────────────────────────────
// Formas de lo que devuelve la API para cada sección (app/schemas/** y los
// serializadores de app/services/advanced_config_service.py) y del estado local
// de los formularios. Se declaran con `type` (no `interface`) para que sigan
// siendo asignables a `Record<string, unknown>`, que es lo que piden los
// métodos de escritura de settingsApi/advancedConfigApi.

type Organizacion = { id: string; name: string; slug?: string | null; is_active?: boolean }

/** Usuario del listado (`UserPublic`). `GET /users` no manda `hourly_rate` (es
 *  confidencial): la ficha de edición la completa con `GET /users/{id}` (`UserWithRate`). */
type UserRow = UserListItem & {
  hourly_rate?: number | null
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

type AlertRule = { id: string; name: string; metric_key: string; condition: string; threshold?: number | null; severity: string; enabled: boolean }
type MetricOption = { key: string; label: string; is_custom?: boolean }
type SupportedMetrics = { metrics?: MetricOption[]; conditions?: unknown[] }
type RuleForm = { name: string; metric_key: string; condition: string; threshold: string | number; severity: string; cooldown_minutes: string | number }

type RateEntry = { id: string; label: string; cost_rate: number | null; billing_rate: number | null }
type RateTable = { id: string; name: string; applies_to: string; is_default: boolean; entries?: RateEntry[] }
type EntryForm = { label: string; cost_rate: string | number; billing_rate: string | number }
type NewRateTable = { name: string; applies_to: string; is_default: boolean }

type VacationPolicy = { id: string; name: string; days_per_year: number; carries_over: boolean; max_carryover_days: number | null; is_default: boolean }
type NewVacationPolicy = { name: string; days_per_year: number; carries_over: boolean; max_carryover_days: number; is_default: boolean }
type VacationBalance = { user_id: string; user_name: string; department?: string | null; days_entitled: number; days_taken: number; days_pending: number; days_remaining: number }

type NumberingSeq = { entity: string; prefix: string; separator: string; padding: number; include_year: boolean; current_value: number; next_preview: string }

type CustomField = { id: string; entity: string; name: string; field_key: string; field_type: string; is_required: boolean; placeholder?: string | null }
type CustomFieldEdit = { name: string; is_required: boolean; placeholder: string }
type CustomFieldForm = { entity: string; name: string; field_key: string; field_type: string; is_required: boolean; placeholder: string }

type TemplateTask = { id?: string; title: string; estimated_hours?: number | null }
type TemplatePhase = { id?: string; name: string; tasks?: TemplateTask[] }
type ProjectTemplate = {
  id: string
  name: string
  description?: string | null
  phase_count: number
  task_count: number
  risk_count: number
  deliverable_count: number
  estimated_weeks?: number | null
  phases?: TemplatePhase[]
}
type DraftTask = { title: string; estimated_hours: number | null; skill_required: string | null }
type DraftPhase = { name: string; description: string | null; estimated_weeks: number | null; estimated_hours: number | null; tasks: DraftTask[] }
type DraftRisk = { title: string; category: string | null; probability: string; impact: string; mitigation_plan: string | null }
type DraftDeliverable = { name: string; format: string | null; week_offset: number | null; billing_pct: number | null; acceptance_criteria: string | null }
type TemplateForm = {
  name: string
  description: string
  project_type: string
  estimated_weeks: string
  estimated_hours: string
  phases: DraftPhase[]
  risks: DraftRisk[]
  deliverables: DraftDeliverable[]
}
type TemplatePayload = Omit<TemplateForm, 'estimated_weeks' | 'estimated_hours'> & { estimated_weeks: number | null; estimated_hours: number | null }
type PhaseInput = { name: string; description: string; estimated_weeks: string; estimated_hours: string; tasks: DraftTask[] }
type TaskInput = { title: string; estimated_hours: string; skill_required: string }
type RiskInput = { title: string; category: string; probability: string; impact: string; mitigation_plan: string }
type DeliverableInput = { name: string; format: string; week_offset: string; billing_pct: string; acceptance_criteria: string }

type Office = { id: string; name: string; country?: string | null; city?: string | null; timezone?: string | null }
type OfficeForm = { name: string; country: string; city: string; timezone: string }

type TaskType = { id: string; name: string; value: string; icon: string; color: string; is_billable_default: boolean }
type TaskTypeForm = { name: string; value: string; icon: string; color: string; is_billable_default: boolean }
type TaskTypeEdit = Omit<TaskTypeForm, 'value'>

type DepartmentForm = { name: string; description: string; area_id: string }

type MetricFormula = { operand_a?: string; operator?: string; operand_b_type?: string; operand_b?: string | number; scale?: string | number }
type CustomMetric = { key: string; label: string; description?: string | null; formula?: MetricFormula | null }
type MetricForm = { label: string; description: string; operand_a: string; operator: string; operand_b_type: string; operand_b: string; scale: string | number }

type InputChange = ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>

// ── General settings ──────────────────────────────────────────────────────────

const LABELS: Record<string, string> = {
  company_name: 'Nombre empresa',
  currency: 'Moneda',
  timezone: 'Zona horaria',
  language: 'Idioma',
  work_hours_per_day: 'Horas/día',
}

// Settings cuya key empieza por estos prefijos son estado interno de servicios BI/ITSM
// (no deben aparecer en la página de Configuración general porque son JSON serializado).
const INTERNAL_KEY_PREFIXES = [
  'bi.', 'sd.', 'olap.', 'ml_', '_', 'cache_', 'feedback_', 'lineage_', 'embed_', 'idle_timeout_',
]
const isUserFacingSetting = (key: string) => {
  if (!key) return false
  if (key in LABELS) return true
  const lower = String(key).toLowerCase()
  if (INTERNAL_KEY_PREFIXES.some(p => lower.startsWith(p))) return false
  // Permitir keys "limpias" (sin punto y sin parecer JSON): nombres simples como
  // company_name, currency, etc.
  return !lower.includes('.')
}

function GeneralSection() {
  const { t } = useAppLang()
  const qc = useQueryClient()
  const toast = useToast()
  const { data: settings = [] } = useQuery({ queryKey: ['settings-general'], queryFn: () => settingsApi.getGeneral().then(r => r.data) })
  const { mutate: update } = useMutation({ mutationFn: ({ key, value }: { key: string; value: string }) => settingsApi.updateSetting(key, value), onSuccess: () => qc.invalidateQueries({ queryKey: ['settings-general'] }) , onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))})

  const visible = (settings || []).filter(s => isUserFacingSetting(s.key))

  return (
    <SeccionDeAjustes icon="⚙️" title={t('settings.configuracion_general')} description="Parámetros globales de la organización">
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 14 }}>
        {visible.map(s => <SettingField key={s.key} setting={s} label={LABELS[s.key] || s.key} onSave={(v) => update({ key: s.key, value: v })} />)}
      </div>
      {visible.length === 0 && (
        <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)', textAlign: 'center', padding: 16 }}>
          {t('settings.sin_parametros_generales_configurados')}
        </div>
      )}
    </SeccionDeAjustes>
  )
}

function SettingField({ setting, label, onSave }: { setting: SettingOut; label: string; onSave: (v: string) => void }) {
  const [state, setState] = useState<{ editing: boolean; val: string }>({ editing: false, val: setting.value || '' })
  const { editing, val } = state
  const setEditing = (v: SetStateAction<boolean>) => setState(s => ({ ...s, editing: typeof v === 'function' ? v(s.editing) : v }))
  const setVal = (v: SetStateAction<string>) => setState(s => ({ ...s, val: typeof v === 'function' ? v(s.val) : v }))
  return (
    <div style={{
      background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
      borderRadius: 'var(--radius-md)', padding: '12px 16px',
      minWidth: 0, overflow: 'hidden',
    }}>
      <label style={ls}>{label}</label>
      {editing ? (
        <div className="u-row-8">
          <input value={val} onChange={e => setVal(e.target.value)} style={{ ...fs, flex: 1, minWidth: 0 }} autoFocus onKeyDown={e => { if (e.key === 'Enter') { onSave(val); setEditing(false) } if (e.key === 'Escape') { setVal(setting.value); setEditing(false) } }} />
          <button onClick={() => { onSave(val); setEditing(false) }} style={{ background: 'var(--accent)', border: 'none', borderRadius: 'var(--radius-sm)', padding: '0 12px', color: 'var(--surface-0)', cursor: 'pointer', fontWeight: 700, flexShrink: 0 }}>✓</button>
          <button onClick={() => { setVal(setting.value); setEditing(false) }} style={{ background: 'transparent', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-sm)', padding: '0 12px', color: 'var(--text-2)', cursor: 'pointer', flexShrink: 0 }}>✕</button>
        </div>
      ) : (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8, minWidth: 0 }}>
          <span style={{
            fontSize: "var(--text-md)", fontWeight: 600,
            color: setting.value ? 'var(--text-1)' : 'var(--text-3)',
            wordBreak: 'break-word', overflowWrap: 'anywhere',
            flex: 1, minWidth: 0,
          }}>{setting.value || '—'}</span>
          <button onClick={() => setEditing(true)} style={{ background: 'none', border: 'none', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)", flexShrink: 0 }}>✏️</button>
        </div>
      )}
    </div>
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
  const setEditUser = (v: SetStateAction<UserRow | null>) => setUi(typeof v === 'function' ? (s: UsersUi) => ({ editUser: v(s.editUser) }) : { editUser: v })
  const setSearch = (v: SetStateAction<string>) => setUi(typeof v === 'function' ? (s: UsersUi) => ({ search: v(s.search) }) : { search: v })
  const setOrgFilter = (v: SetStateAction<string>) => setUi(typeof v === 'function' ? (s: UsersUi) => ({ orgFilter: v(s.orgFilter) }) : { orgFilter: v })
  const { data: users = [], isLoading } = useQuery<UserRow[]>({ queryKey: ['users'], queryFn: () => usersApi.list().then(r => r.data) })
  const { data: roles = [] } = useQuery({ queryKey: ['custom-roles'], queryFn: () => advancedConfigApi.getRoles().then(r => r.data) })
  const { data: departments = [] } = useQuery({ queryKey: ['departments-select'], queryFn: () => settingsApi.getDepartments().then(r => r.data) })
  // La lista de empresas y asignar a otras es del superadmin (la API la sirve
  // sólo a él); un admin de empresa da de alta en la suya (revisión 2026-11).
  const esSuperadmin = !!useAuth().user?.is_superadmin
  const { data: organizations = [] } = useQuery<Organizacion[]>({ queryKey: ['orgs-for-users'], queryFn: () => organizationsApi.list().then(r => r.data), enabled: esSuperadmin })
  const roleMap = Object.fromEntries(roles.map(r => [r.name, r]))
  // El formulario envía los campos tal como los tiene (la tarifa y las horas como
  // texto; pydantic los convierte). Un '' en la tarifa o la zona horaria es «sin valor»:
  // en el alta se omite y al editar viaja como null (un '' en la tarifa daba 422).
  // Auditoría 2026-11 (#25).
  const { mutate: createUser, isPending: creating } = useMutation({ mutationFn: (data: UserFormPayload) => usersApi.create(limpiarUsuario(data, 'omitir') as unknown as UserCreatePayload), onSuccess: () => { qc.invalidateQueries({ queryKey: ['users'] }); setShowCreate(false) } , onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))})
  const { mutate: updateUser, isPending: updating } = useMutation({ mutationFn: ({ id, data }: { id: string; data: UserFormPayload }) => usersApi.update(id, limpiarUsuario(data, 'anular') as UserUpdatePayload), onSuccess: () => { qc.invalidateQueries({ queryKey: ['users'] }); qc.invalidateQueries({ queryKey: ['user-detail'] }); setEditUser(null) } , onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))})
  // `GET /users` (`UserPublic`) no lleva la tarifa, que es confidencial: la ficha la
  // pide a `GET /users/{id}` (`UserWithRate`) al abrirse.
  const { data: editUserDetail, isFetched: editUserFetched } = useQuery({
    queryKey: ['user-detail', editUser?.id],
    queryFn: () => usersApi.get(editUser?.id ?? '').then(r => r.data),
    enabled: !!editUser,
  })
  const { mutate: deactivate } = useMutation({ mutationFn: usersApi.deactivate, onSuccess: () => qc.invalidateQueries({ queryKey: ['users'] }) , onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))})
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
    <SeccionDeAjustes title="Usuarios" description="Gestiona accesos y datos del equipo">
      <div className="ds-toolbar" style={{ marginBottom: 'var(--space-4)' }}>
        <div style={{ position: 'relative', flex: 1, minWidth: 200 }}>
          <Search size={14} aria-hidden style={{
            position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)',
            color: 'var(--text-3)', pointerEvents: 'none',
          }} />
          <input value={search} onChange={e => setSearch(e.target.value)}
            placeholder={t('settings.buscar_usuario_por_nombre_o_alias')}
            aria-label={t('settings.buscar_usuario_por_nombre_o_alias')}
            className="ds-input"
            style={{ paddingLeft: 32 }} />
        </div>
        <select
          value={orgFilter}
          onChange={(e) => setOrgFilter(e.target.value)}
          className="ds-input"
          aria-label={t('settings.filtrar_usuarios_por_organizacion')}
          style={{ minWidth: 220, maxWidth: 320 }}
        >
          <option value="">{t('settings.todas_las_organizaciones')}</option>
          {organizations.filter(o => o.is_active !== false).map(o => (
            <option key={o.id} value={o.id}>{o.name}</option>
          ))}
        </select>
        {(search || orgFilter) && (
          <Button
            variant="secondary"
            onClick={() => {
              setSearch('')
              setOrgFilter('')
            }}
          >
            Limpiar filtros
          </Button>
        )}
        <Button onClick={() => setShowCreate(true)}>{t('settings.nuevo_usuario')}</Button>
      </div>
      {isLoading ? <Spinner /> : (
        <div style={styles.colGap8}>
          {filtered.map(u => {
            const roleColor = roleMap[u.role]?.color || ROLE_COLORS[u.role] || 'var(--text-2)'
            const roleLabel = roleMap[u.role]?.description || ROLE_LABELS[u.role] || u.role
            const orgs = Array.isArray(u.organizations) ? u.organizations : []
            const primaryOrgId = u.organization_id || ''
            return (
            <div key={u.id} style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '10px 14px', background: 'var(--surface-2)', border: `1px solid ${u.is_active ? 'var(--surface-4)' : 'var(--danger-border)'}`, borderRadius: 'var(--radius-md)', opacity: u.is_active ? 1 : 0.6 }}>
              <div style={{ width: 34, height: 34, borderRadius: '50%', background: `linear-gradient(135deg, ${roleColor}, var(--surface-0))`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: "var(--text-base)", fontWeight: 700, flexShrink: 0 }}>
                {u.full_name?.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()}
              </div>
              <div className="u-flex1">
                <div className="u-base-600">{u.full_name}</div>
                <div className="u-text2-xs">{u.username} · {u.email}</div>
              </div>
              <span style={{ fontSize: "var(--text-xs)", background: alpha(roleColor, '15'), color: roleColor, border: `1px solid ${alpha(roleColor, '30')}`, borderRadius: 20, padding: '2px 8px', fontWeight: 700 }}>{roleLabel}</span>
              {orgs.length > 0 && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                  {orgs.slice(0, 3).map(org => {
                    const isPrimary = String(org.id || '') === String(primaryOrgId)
                    return (
                      <span key={org.id} style={{
                        fontSize: "var(--text-xs)",
                        borderRadius: 20,
                        padding: '2px 8px',
                        border: `1px solid ${isPrimary ? 'var(--accent)' : 'var(--surface-4)'}`,
                        color: isPrimary ? 'var(--accent)' : 'var(--text-2)',
                        background: isPrimary ? 'var(--accent-muted)' : 'var(--surface-3)',
                        fontWeight: isPrimary ? 700 : 500,
                      }}>
                        {org.name || org.slug || org.id}{isPrimary ? ' (Principal)' : ''}
                      </span>
                    )
                  })}
                  {orgs.length > 3 && (
                    <span
                      title={orgs.map(org => `${org.name || org.slug || org.id}${String(org.id || '') === String(primaryOrgId) ? ' (Principal)' : ''}`).join('\n')}
                      style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', cursor: 'help' }}
                    >
                      +{orgs.length - 3}
                    </span>
                  )}
                </div>
              )}
              {u.department && <span className="u-text2-xs">{u.department}</span>}
              {!u.is_active && <span style={{ fontSize: "var(--text-xs)", color: 'var(--danger)' }}>Inactivo</span>}
              <button onClick={() => setEditUser(u)} style={styles.btnEdit}>✏️ Editar</button>
              {u.is_active ? <button onClick={() => openConfirmGlobal({ message: `¿Desactivar a "${u.full_name}"?`, onConfirm: () => deactivate(u.id) })} style={{ background: 'none', border: '1px solid var(--warning-border)', borderRadius: 'var(--radius-sm)', padding: '3px 8px', color: 'var(--warning)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>⏸ Desactivar</button>
                : <button onClick={() => deactivate(u.id)} style={{ background: 'none', border: '1px solid var(--success-border)', borderRadius: 'var(--radius-sm)', padding: '3px 8px', color: 'var(--success)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>▶ Activar</button>}
              <button onClick={() => openConfirmGlobal({ title: '⚠️ Eliminar permanentemente', message: `¿Eliminar permanentemente a "${u.full_name}"? Esta acción no se puede deshacer.`, onConfirm: () => deletePermanent(u.id), danger: true })} style={styles.btnDelete}>🗑 Eliminar</button>
            </div>
          )})}
        </div>
      )}
      <UserFormModal open={showCreate} roles={roles} departments={departments} organizations={organizations} esSuperadmin={esSuperadmin} onClose={() => setShowCreate(false)} onSave={createUser} isPending={creating} />
      {editUser && editUserFetched && <UserFormModal open roles={roles} departments={departments} organizations={organizations} esSuperadmin={esSuperadmin} user={editUserDetail ? { ...editUser, ...editUserDetail } : editUser} onClose={() => setEditUser(null)} onSave={data => updateUser({ id: editUser.id, data })} isPending={updating} />}
    </SeccionDeAjustes>
  )
}

// Zod schema mirroring backend UserBase/UserCreate (app/schemas/users.py)
const userFormSchemaBase = z.object({
  username: z.string().trim().min(1, 'El usuario es obligatorio').max(150, 'Máximo 150 caracteres'),
  email: z.string().trim().min(1, 'El email es obligatorio').email('Email inválido').max(200, 'Máximo 200 caracteres'),
  full_name: z.string().trim().min(1, 'El nombre completo es obligatorio').max(255, 'Máximo 255 caracteres'),
  role: z.string().min(1, 'Selecciona un rol'),
  department: z.union([z.literal(''), z.string().max(100)]).optional(),
  job_title: z.union([z.literal(''), z.string().max(150)]).optional(),
  weekly_capacity_hours: z.coerce.number({ invalid_type_error: 'Debe ser un número' })
    .min(0, 'No puede ser negativo')
    .max(168, 'Máximo 168h/semana'),
  hourly_rate: z.union([
    z.literal(''),
    z.coerce.number({ invalid_type_error: 'Debe ser un número' }).nonnegative('No puede ser negativo'),
  ]).optional(),
  timezone: z.union([z.literal(''), z.string()]).optional(),
  organization_ids: z.array(z.string()).optional(),
  organization_id: z.union([z.literal(''), z.string()]).optional(),
  custom_role_id: z.union([z.literal(''), z.string()]).optional(),
})
const userCreateSchema = userFormSchemaBase.extend({
  password: z.string().min(6, 'Mínimo 6 caracteres').max(128, 'Máximo 128 caracteres'),
})
const userEditSchema = userFormSchemaBase.extend({
  password: z.union([z.literal(''), z.string().min(6, 'Mínimo 6 caracteres')]).optional(),
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
}

function UserFormModal({ open, onClose, user, onSave, isPending, roles = [], departments = [], organizations = [], esSuperadmin = false }: UserFormModalProps) {
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
  }
  const setOrganizations = (e: ChangeEvent<HTMLSelectElement>) => {
    const values = Array.from(e.target.selectedOptions).map(o => o.value)
    setForm((f) => {
      const nextPrimary = values.includes(f.organization_id)
        ? f.organization_id
        : (values[0] || '')
      return { ...f, organization_ids: values, organization_id: nextPrimary }
    })
    validation.clearFieldError('organization_ids')
  }
  const errField = (key: string) => validation.errors[key] && (
    <div className="u-field-error">{validation.errors[key]}</div>
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
    <Modal open={open} onClose={onClose} title={isEdit ? `Editar — ${user.full_name}` : 'Nuevo Usuario'} width={580}>
      <form onSubmit={handleSubmit}>
        <div className="u-grid2-14">
        <div className="u-col-full"><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={ls}>Nombre completo *</label><input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.full_name} onChange={set('full_name')} style={validation.inputStyle(fs, 'full_name')} />{errField('full_name')}</div>
        <div><label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} style={ls}>Usuario *</label><input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.username} onChange={set('username')} style={validation.inputStyle(fs, 'username')} />{errField('username')}</div>
        <div><label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} style={ls}>Email *</label><input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} type="email" value={form.email} onChange={set('email')} style={validation.inputStyle(fs, 'email')} />{errField('email')}</div>
        <div><label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} style={ls}>Rol</label><select id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={form.role} onChange={set('role')} style={validation.inputStyle(fs, 'role')}>
          {Object.entries(ROLE_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>{errField('role')}</div>
        <div><label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} style={ls}>Rol personalizado (cierra módulos)</label><select id={`${idCampo}-5`} aria-labelledby={`${idCampo}-et5`} value={form.custom_role_id} onChange={set('custom_role_id')} style={fs}>
          <option value="">Ninguno — el de su rol base</option>
          {roles.filter(r => !r.is_system).map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
        </select></div>
        <div><label id={`${idCampo}-et6`} htmlFor={`${idCampo}-6`} style={ls}>Departamento</label><select id={`${idCampo}-6`} aria-labelledby={`${idCampo}-et6`} value={form.department} onChange={set('department')} style={fs}>
          <option value="">{t('settings.sin_departamento')}</option>
          {departments.filter(d => d.is_active !== false).map(d => <option key={d.id} value={d.name}>{d.name}</option>)}
        </select></div>
        <div><label id={`${idCampo}-et7`} htmlFor={`${idCampo}-7`} style={ls}>Cargo</label><input id={`${idCampo}-7`} aria-labelledby={`${idCampo}-et7`} value={form.job_title} onChange={set('job_title')} style={fs} /></div>
        <div><label id={`${idCampo}-et8`} htmlFor={`${idCampo}-8`} style={ls}>Horas semanales</label><input id={`${idCampo}-8`} aria-labelledby={`${idCampo}-et8`} type="number" value={form.weekly_capacity_hours} onChange={set('weekly_capacity_hours')} style={validation.inputStyle(fs, 'weekly_capacity_hours')} />{errField('weekly_capacity_hours')}</div>
        <div><label id={`${idCampo}-et9`} htmlFor={`${idCampo}-9`} style={ls}>Tarifa {fmtMoneda.simbolo}/hora</label><input id={`${idCampo}-9`} aria-labelledby={`${idCampo}-et9`} type="number" value={form.hourly_rate} onChange={set('hourly_rate')} style={validation.inputStyle(fs, 'hourly_rate')} />{errField('hourly_rate')}</div>
        {esSuperadmin && <>
        <div className="u-col-full">
          <label id={`${idCampo}-et10`} htmlFor={`${idCampo}-10`} style={ls}>{t('settings.organizaciones_seleccion_multiple')}</label>
          <select id={`${idCampo}-10`} aria-labelledby={`${idCampo}-et10`} multiple value={form.organization_ids} onChange={setOrganizations} style={{ ...fs, minHeight: 112 }}>
            {organizations.filter(o => o.is_active !== false).map(o => (
              <option key={o.id} value={o.id}>{o.name} ({o.slug})</option>
            ))}
          </select>
        </div>
        <div className="u-col-full">
          <label id={`${idCampo}-et11`} htmlFor={`${idCampo}-11`} style={ls}>{t('settings.organizacion_principal')}</label>
          <select id={`${idCampo}-11`} aria-labelledby={`${idCampo}-et11`} value={form.organization_id} onChange={set('organization_id')} style={fs}>
            <option value="">{t('settings.sin_organizacion_principal')}</option>
            {form.organization_ids.map(orgId => {
              const org = organizations.find(o => o.id === orgId)
              return <option key={orgId} value={orgId}>{org?.name || orgId}</option>
            })}
          </select>
        </div>
        </>}
        <div className="u-col-full">
          <label id={`${idCampo}-et12`} htmlFor={`${idCampo}-12`} style={ls}>Zona horaria</label>
          <select id={`${idCampo}-12`} aria-labelledby={`${idCampo}-et12`} value={form.timezone} onChange={set('timezone')} style={fs}>
            <option value="">{t('settings.usa_la_zona_de_la_organizacion')}</option>
            {timezoneOptions(form.timezone).map(tz => <option key={tz} value={tz}>{tz}</option>)}
          </select>
        </div>
        {!isEdit && <div className="u-col-full"><label id={`${idCampo}-et13`} htmlFor={`${idCampo}-13`} style={ls}>{t('settings.contrasena')}</label><input id={`${idCampo}-13`} aria-labelledby={`${idCampo}-et13`} type="password" value={form.password} onChange={set('password')} style={validation.inputStyle(fs, 'password')} />{errField('password')}</div>}
        <div style={{ gridColumn: '1/-1', display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 8 }}>
          <Button variant="secondary" type="button" onClick={onClose}>Cancelar</Button>
          <Button type="submit" disabled={isPending}>
            {isPending ? 'Guardando...' : isEdit ? 'Guardar' : 'Crear'}
          </Button>
        </div>
        </div>
      </form>
    </Modal>
  )
}

// ── Roles section ─────────────────────────────────────────────────────────────
function RolesSection() {
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
    <SeccionDeAjustes icon="🔐" title="Roles y permisos" description="Cierra módulos por rol. Los roles de sistema se aplican a todos los de ese rol base; un rol personalizado se asigna a una persona en Usuarios y manda sobre el de su rol base. Solo restringe: nunca da más de lo que permite el rol base. Al rol admin no se le cierra nada.">
      <div style={styles.colGap8}>
        {isLoading ? <Spinner /> : roles.map(r => (
          <div key={r.id} style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '12px 16px', background: 'var(--surface-2)', border: `1px solid ${alpha(r.color, '30')}`, borderRadius: 'var(--radius-md)' }}>
            <div style={{ width: 10, height: 10, borderRadius: '50%', background: r.color, flexShrink: 0 }} />
            <div className="u-flex1">
              <div className="u-base-700">{r.name}</div>
              {r.description && <div className="u-text2-sm">{r.description}</div>}
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 6 }}>
                {Object.entries(r.module_access || {}).filter(([, v]) => v).slice(0, 8).map(([m]) => (
                  <span key={m} style={{ fontSize: "var(--text-3xs)", background: 'var(--surface-3)', color: 'var(--text-2)', borderRadius: 4, padding: '1px 6px' }}>{m}</span>
                ))}
                {Object.values(r.module_access || {}).filter(Boolean).length > 8 && <span style={{ fontSize: "var(--text-3xs)", color: 'var(--text-2)' }}>+{Object.values(r.module_access || {}).filter(Boolean).length - 8}</span>}
              </div>
            </div>
            {r.is_system && <span style={{ fontSize: "var(--text-2xs)", color: 'var(--text-2)', background: 'var(--surface-3)', borderRadius: 20, padding: '2px 8px' }}>Sistema</span>}
            <button onClick={() => setEditRole(r)} style={styles.btnEdit}>✏️ Editar</button>
            {!r.is_system && <button onClick={() => deleteRole(r.id)} style={styles.btnDelete}>🗑</button>}
          </div>
        ))}
        <button onClick={() => setShowCreate(true)} style={{ padding: '10px', border: '1px dashed var(--surface-4)', borderRadius: 'var(--radius-md)', background: 'transparent', color: 'var(--text-2)', fontSize: "var(--text-base)", cursor: 'pointer', fontFamily: 'inherit', textAlign: 'center' }}>＋ Crear rol personalizado</button>
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
    <Modal open title={role ? `Editar rol — ${role.name}` : 'Nuevo rol'} onClose={onClose} width={560}>
      <div style={styles.colGap14}>
        <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 12 }}>
          <div><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={ls}>Nombre *</label><input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} style={fs} disabled={role?.is_system} /></div>
          <div><label style={ls}>Color</label><div className="u-row-8"><input type="color" value={/^#[0-9a-fA-F]{6}$/.test(form.color) ? form.color : COLOR_DATO_POR_DEFECTO} onChange={e => setForm(f => ({ ...f, color: e.target.value }))} style={{ width: 40, height: 38, border: 'none', background: 'transparent', cursor: 'pointer' }} /><input value={form.color} onChange={e => setForm(f => ({ ...f, color: e.target.value }))} style={{ ...fs, flex: 1 }} /></div></div>
        </div>
        <div><label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} style={ls}>{t('settings.descripcion')}</label><input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} style={fs} /></div>
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
            <label style={ls}>{t('settings.modulos_accesibles')}</label>
            <button onClick={() => setForm(f => ({ ...f, module_access: modules.reduce<Record<string, unknown>>((a, m) => ({ ...a, [m.id]: !allOn }), {}) }))} style={{ background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>
              {allOn ? 'Desactivar todos' : 'Activar todos'}
            </button>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6 }}>
            {modules.map(m => (
              <label key={m.id} style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', padding: '6px 10px', background: form.module_access[m.id] ? 'var(--accent-muted)' : 'var(--surface-3)', borderRadius: 'var(--radius-sm)', border: `1px solid ${form.module_access[m.id] ? 'var(--accent)' : 'var(--surface-4)'}`, fontSize: "var(--text-sm)" }}>
                <input type="checkbox" checked={!!form.module_access[m.id]} onChange={() => toggleModule(m.id)} />
                {m.label}
              </label>
            ))}
          </div>
        </div>
        <div style={styles.rowFlexEnd}>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={() => onSave(form)} disabled={!form.name}>Guardar</Button>
        </div>
      </div>
    </Modal>
  )
}

// ── Alert configs section ─────────────────────────────────────────────────────
const CONDITION_LABELS: Record<string, string> = {
  threshold_above: 'Supera umbral',
  threshold_below: 'Por debajo del umbral',
  trend_up: 'Tendencia al alza',
  trend_down: 'Tendencia a la baja',
  anomaly: 'Anomalía detectada',
}
const THRESHOLD_CONDITIONS = ['threshold_above', 'threshold_below']
const NOTIFY_FIELDS: ReadonlyArray<readonly [NotifyKey, string]> = [['notify_admin', 'Admin'], ['notify_pm', 'PM'], ['notify_hr', 'RRHH'], ['notify_employee', 'Empleado'], ['notify_email', '📧 Email']]

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
  const { data: rulesData = { items: [] } } = useQuery<{ items?: AlertRule[] }>({ queryKey: ['bi-alert-rules'], queryFn: () => biSmartAlertsApi.listRules().then(r => r.data) })
  const { data: metricsData = { metrics: [], conditions: [] } } = useQuery<SupportedMetrics>({ queryKey: ['bi-alert-metrics'], queryFn: () => biSmartAlertsApi.supportedMetrics().then(r => r.data) })
  const rules = rulesData.items ?? []
  const metrics = metricsData.metrics ?? []

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

  const submitRule = () => {
    if (!ruleForm.name.trim() || !ruleForm.metric_key) { toast.error('Nombre y métrica son obligatorios'); return }
    const payload = { ...ruleForm, cooldown_minutes: +ruleForm.cooldown_minutes }
    if (THRESHOLD_CONDITIONS.includes(ruleForm.condition)) payload.threshold = +ruleForm.threshold
    else delete payload.threshold
    createRule(payload)
  }

  return (
    <SeccionDeAjustes icon="🔔" title="Alertas" description="Configura notificaciones, umbrales y reglas personalizadas">
      {isLoading ? <Spinner /> : (
        <div style={styles.colGap10}>
          {configs.map(cfg => (
            <div key={cfg.alert_type} style={{ padding: '14px 16px', background: 'var(--surface-2)', border: `1px solid ${cfg.is_enabled ? alpha(SEV_CFG[cfg.severity], '30') : 'var(--surface-4)'}`, borderRadius: 'var(--radius-md)', opacity: cfg.is_enabled ? 1 : 0.6 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 }}>
                <div>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 3 }}>
                    <span className="u-base-700">{cfg.label}</span>
                    <span style={{ fontSize: "var(--text-2xs)", fontWeight: 700, color: SEV_CFG[cfg.severity], background: alpha(SEV_CFG[cfg.severity], '20'), borderRadius: 20, padding: '1px 7px', textTransform: 'uppercase' }}>{cfg.severity}</span>
                  </div>
                  {cfg.description && <div className="u-text2-sm">{cfg.description}</div>}
                </div>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                  <input type="checkbox" checked={cfg.is_enabled} onChange={e => update({ type: cfg.alert_type, data: { is_enabled: e.target.checked } })} />
                  <span className="u-text2-sm">{cfg.is_enabled ? 'Activa' : 'Inactiva'}</span>
                </label>
              </div>
              {cfg.is_enabled && (
                <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', alignItems: 'center' }}>
                  {cfg.threshold_value !== null && (
                    <div className="u-row-center-8">
                      <label className="u-text2-xs">Umbral:</label>
                      <input type="number" defaultValue={cfg.threshold_value} onBlur={e => update({ type: cfg.alert_type, data: { threshold_value: +e.target.value } })}
                        style={{ width: 70, background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-sm)', padding: '4px 8px', color: 'var(--text-1)', fontSize: "var(--text-sm)", outline: 'none', fontFamily: 'inherit', textAlign: 'center' }} />
                      <span className="u-text2-xs">{cfg.threshold_unit}</span>
                    </div>
                  )}
                  <div className="u-wrap-10">
                    {NOTIFY_FIELDS.map(([key, label]) => (
                      <label key={key} style={{ display: 'flex', alignItems: 'center', gap: 5, cursor: 'pointer', fontSize: "var(--text-xs)", color: cfg[key] ? 'var(--text-1)' : 'var(--text-2)' }}>
                        <input type="checkbox" checked={!!cfg[key]} onChange={e => update({ type: cfg.alert_type, data: { [key]: e.target.checked } })} />
                        {label}
                      </label>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* ── Custom BI alert rules ─────────────────── */}
      <div style={{ marginTop: 28 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <div>
            <div className="u-base-700">Reglas personalizadas</div>
            <div className="u-text2-sm">{t('settings.alertas_basadas_en_metricas_del_sistema')}</div>
          </div>
          <Button onClick={() => setShowCreate(true)}>{t('settings.nueva_alerta')}</Button>
        </div>
        {rules.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '20px 0', color: 'var(--text-3)', fontSize: "var(--text-sm)" }}>{t('settings.no_hay_reglas_personalizadas_crea_la_primera')}</div>
        ) : (
          <div style={styles.colGap8}>
            {rules.map(rule => (
              <div key={rule.id} style={{ padding: '12px 14px', background: 'var(--surface-2)', border: `1px solid ${rule.enabled ? alpha(SEV_CFG[rule.severity], '30') : 'var(--surface-4)'}`, borderRadius: 'var(--radius-md)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, opacity: rule.enabled ? 1 : 0.6 }}>
                <div className="u-flex1-min0">
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 2 }}>
                    <span className="u-base-600">{rule.name}</span>
                    <span style={{ fontSize: "var(--text-2xs)", fontWeight: 700, color: SEV_CFG[rule.severity], background: alpha(SEV_CFG[rule.severity], '20'), borderRadius: 20, padding: '1px 7px', textTransform: 'uppercase' }}>{rule.severity}</span>
                  </div>
                  <div className="u-text2-xs">
                    {metrics.find(m => m.key === rule.metric_key)?.label ?? rule.metric_key} · {CONDITION_LABELS[rule.condition] ?? rule.condition}{rule.threshold != null ? ` · umbral: ${rule.threshold}` : ''}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexShrink: 0 }}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>
                    <input type="checkbox" checked={!!rule.enabled} onChange={e => toggleRule({ id: rule.id, enabled: e.target.checked })} />
                    {rule.enabled ? 'Activa' : 'Inactiva'}
                  </label>
                  <Button variant="danger" style={{ padding: '4px 10px', fontSize: "var(--text-xs)" }} onClick={() => openConfirmGlobal({ title: 'Eliminar regla', message: `¿Eliminar "${rule.name}"?`, onConfirm: () => deleteRule(rule.id) })}>Eliminar</Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {showCreate && (
        <Modal open title={t('settings.nueva_regla_de_alerta')} onClose={() => { setShowCreate(false); setRuleForm(EMPTY_RULE) }} width={480}>
          <div style={styles.colGap14}>
            <div>
              <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={ls}>Nombre</label>
              <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={ruleForm.name} onChange={setR('name')} style={fs} placeholder={t('settings.ej_ingresos_por_debajo_del_objetivo')} />
            </div>
            <div>
              <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} style={ls}>{t('settings.metrica')}</label>
              <select id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={ruleForm.metric_key} onChange={setR('metric_key')} style={fs}>
                <option value="">{t('settings.selecciona_una_metrica')}</option>
                {metrics.map(m => <option key={m.key} value={m.key}>{m.label}</option>)}
              </select>
            </div>
            <div className="u-grid2-12">
              <div>
                <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} style={ls}>{t('settings.condicion')}</label>
                <select id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={ruleForm.condition} onChange={setR('condition')} style={fs}>
                  {Object.entries(CONDITION_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </div>
              {THRESHOLD_CONDITIONS.includes(ruleForm.condition) && (
                <div>
                  <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} style={ls}>Umbral</label>
                  <input id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} type="number" value={ruleForm.threshold} onChange={setR('threshold')} style={fs} placeholder="0" />
                </div>
              )}
            </div>
            <div className="u-grid2-12">
              <div>
                <label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} style={ls}>Severidad</label>
                <select id={`${idCampo}-5`} aria-labelledby={`${idCampo}-et5`} value={ruleForm.severity} onChange={setR('severity')} style={fs}>
                  <option value="info">Info</option>
                  <option value="warning">Warning</option>
                  <option value="critical">Critical</option>
                </select>
              </div>
              <div>
                <label id={`${idCampo}-et6`} htmlFor={`${idCampo}-6`} style={ls}>Cooldown (minutos)</label>
                <input id={`${idCampo}-6`} aria-labelledby={`${idCampo}-et6`} type="number" value={ruleForm.cooldown_minutes} onChange={setR('cooldown_minutes')} style={fs} min={5} />
              </div>
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 4 }}>
              <Button variant="secondary" onClick={() => { setShowCreate(false); setRuleForm(EMPTY_RULE) }}>Cancelar</Button>
              <Button onClick={submitRule} disabled={isCreating}>{isCreating ? 'Creando…' : 'Crear alerta'}</Button>
            </div>
          </div>
        </Modal>
      )}
    </SeccionDeAjustes>
  )
}

// ── Rate tables section ───────────────────────────────────────────────────────
function RateTablesSection() {
  const fmtMoneda = useFormatoMoneda()
  const idCampo = React.useId()
  const { t } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const { data: tables = [], isLoading } = useQuery<RateTable[]>({ queryKey: ['rate-tables'], queryFn: () => advancedConfigApi.getRateTables().then(r => r.data) })
  const { mutate: createTable } = useMutation({ mutationFn: advancedConfigApi.createRateTable, onSuccess: () => qc.invalidateQueries({ queryKey: ['rate-tables'] }) , onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))})
  const { mutate: deleteTable } = useMutation({ mutationFn: advancedConfigApi.deleteRateTable, onSuccess: () => qc.invalidateQueries({ queryKey: ['rate-tables'] }) , onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))})
  const { mutate: addEntry } = useMutation({ mutationFn: ({ tableId, data }: { tableId: string; data: EntryForm }) => advancedConfigApi.addRateEntry(tableId, data), onSuccess: () => qc.invalidateQueries({ queryKey: ['rate-tables'] }) , onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))})
  const { mutate: deleteEntry } = useMutation({ mutationFn: ({ tableId, entryId }: { tableId: string; entryId: string }) => advancedConfigApi.deleteRateEntry(tableId, entryId), onSuccess: () => qc.invalidateQueries({ queryKey: ['rate-tables'] }), onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) })
  const { mutate: updateEntry } = useMutation({ mutationFn: ({ tableId, entryId, data }: { tableId: string; entryId: string; data: EntryForm }) => advancedConfigApi.updateRateEntry(tableId, entryId, data), onSuccess: () => { qc.invalidateQueries({ queryKey: ['rate-tables'] }); setEditingEntryId(null) }, onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) })
  type RatesUi = { editingEntryId: string | null; editEntryForm: EntryForm; newTable: NewRateTable; addingEntry: string | null; entryForm: EntryForm }
  const [ui, setUi] = React.useReducer(
    (s: RatesUi, p: Partial<RatesUi> | ((s: RatesUi) => Partial<RatesUi>)): RatesUi => {
      const next = typeof p === 'function' ? p(s) : p
      return { ...s, ...next }
    },
    {
      editingEntryId: null,
      editEntryForm: { label: '', cost_rate: '', billing_rate: '' },
      newTable: { name: '', applies_to: 'role', is_default: false },
      addingEntry: null,
      entryForm: { label: '', cost_rate: '', billing_rate: '' },
    },
  )
  const { editingEntryId, editEntryForm, newTable, addingEntry, entryForm } = ui
  const setEditingEntryId = (v: SetStateAction<string | null>) => setUi(typeof v === 'function' ? (s: RatesUi) => ({ editingEntryId: v(s.editingEntryId) }) : { editingEntryId: v })
  const setEditEntryForm = (v: SetStateAction<EntryForm>) => setUi(typeof v === 'function' ? (s: RatesUi) => ({ editEntryForm: v(s.editEntryForm) }) : { editEntryForm: v })
  const setNewTable = (v: SetStateAction<NewRateTable>) => setUi(typeof v === 'function' ? (s: RatesUi) => ({ newTable: v(s.newTable) }) : { newTable: v })
  const setAddingEntry = (v: SetStateAction<string | null>) => setUi(typeof v === 'function' ? (s: RatesUi) => ({ addingEntry: v(s.addingEntry) }) : { addingEntry: v })
  const setEntryForm = (v: SetStateAction<EntryForm>) => setUi(typeof v === 'function' ? (s: RatesUi) => ({ entryForm: v(s.entryForm) }) : { entryForm: v })

  return (
    <SeccionDeAjustes icon="💶" title="Tarifas internas" description="Mantiene tablas de coste y facturacion">
      {isLoading ? <Spinner /> : (
        <div style={styles.colGap16}>
          {tables.map(tabla => (
            <div key={tabla.id} style={{ background: 'var(--surface-2)', border: `1px solid ${tabla.is_default ? 'var(--accent)' : 'var(--surface-4)'}`, borderRadius: 12, padding: 16 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                <div>
                  <span className="u-md-600">{tabla.name}</span>
                  {tabla.is_default && <span style={styles.pill}>{t('settings.por_defecto')}</span>}
                  <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginLeft: 8 }}>{tabla.applies_to === 'role' ? 'Por rol' : tabla.applies_to === 'department' ? 'Por departamento' : 'Por cliente'}</span>
                </div>
                <div className="u-row-8">
                  <button onClick={() => setAddingEntry(tabla.id)} style={{ background: 'var(--accent-muted)', border: '1px solid var(--accent-border)', borderRadius: 'var(--radius-sm)', padding: '4px 10px', color: 'var(--accent)', cursor: 'pointer', fontSize: "var(--text-xs)", fontFamily: 'inherit' }}>＋ Tarifa</button>
                  <button onClick={() => deleteTable(tabla.id)} style={{ background: 'none', border: '1px solid var(--danger-border)', borderRadius: 'var(--radius-sm)', padding: '4px 10px', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>🗑</button>
                </div>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 30px', gap: 8 }}>
                <div style={{ fontSize: "var(--text-2xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', padding: '0 8px' }}>Etiqueta</div>
                <div style={{ fontSize: "var(--text-2xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', textAlign: 'center' }}>Coste {fmtMoneda.simbolo}/h</div>
                <div style={{ fontSize: "var(--text-2xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', textAlign: 'center' }}>Factura {fmtMoneda.simbolo}/h</div>
                <div></div>
                {(tabla.entries || []).map(e => (
                  editingEntryId === e.id ? (
                    <React.Fragment key={e.id}>
                      <input value={editEntryForm.label} onChange={ev => setEditEntryForm(f=>({...f,label:ev.target.value}))} style={{...fs,padding:'5px 8px'}} autoFocus />
                      <input type="number" value={editEntryForm.cost_rate} onChange={ev => setEditEntryForm(f=>({...f,cost_rate:ev.target.value}))} style={{...fs,padding:'5px 8px'}} placeholder={t('settings.coste_por_hora')} aria-label={t('settings.coste_por_hora')} />
                      <input type="number" value={editEntryForm.billing_rate} onChange={ev => setEditEntryForm(f=>({...f,billing_rate:ev.target.value}))} style={{...fs,padding:'5px 8px'}} placeholder={t('settings.tarifa_de_facturacion')} aria-label={t('settings.tarifa_de_facturacion')} />
                      <div style={{display:'flex',gap:4}}>
                        <button onClick={() => updateEntry({ tableId: tabla.id, entryId: e.id, data: editEntryForm })} disabled={!editEntryForm.label} style={{background:'var(--accent)',border:'none',borderRadius:5,padding:'4px 8px',color: 'var(--on-accent)',cursor:'pointer',fontSize: "var(--text-sm)"}}>✓</button>
                        <button onClick={() => setEditingEntryId(null)} style={{background:'none',border:'1px solid var(--surface-4)',borderRadius:5,padding:'4px 7px',color:'var(--text-2)',cursor:'pointer',fontSize: "var(--text-sm)"}}>✕</button>
                      </div>
                    </React.Fragment>
                  ) : (
                    <React.Fragment key={e.id}>
                      <div style={{ padding: '6px 8px', background: 'var(--surface-3)', borderRadius: 'var(--radius-sm)', fontSize: "var(--text-base)" }}>{e.label}</div>
                      <div style={{ padding: '6px 8px', background: 'var(--surface-3)', borderRadius: 'var(--radius-sm)', fontSize: "var(--text-base)", textAlign: 'center', fontFamily: 'var(--font-mono)', color: 'var(--warning)' }}>{e.cost_rate ? fmtMoneda(e.cost_rate) : '—'}</div>
                      <div style={{ padding: '6px 8px', background: 'var(--surface-3)', borderRadius: 'var(--radius-sm)', fontSize: "var(--text-base)", textAlign: 'center', fontFamily: 'var(--font-mono)', color: 'var(--success)' }}>{e.billing_rate ? fmtMoneda(e.billing_rate) : '—'}</div>
                      <div style={{display:'flex',gap:3}}>
                        <button onClick={() => { setEditingEntryId(e.id); setEditEntryForm({ label: e.label, cost_rate: e.cost_rate||'', billing_rate: e.billing_rate||'' }) }} style={{ background: 'none', border: 'none', color: 'var(--text-3)', cursor: 'pointer', fontSize: "var(--text-sm)" }}>✏</button>
                        <button onClick={() => deleteEntry({ tableId: tabla.id, entryId: e.id })} style={{ background: 'none', border: 'none', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-md)" }}>×</button>
                      </div>
                    </React.Fragment>
                  )
                ))}
              </div>
              {addingEntry === tabla.id && (
                <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr auto', gap: 8, marginTop: 8, padding: '10px', background: 'var(--accent-muted)', border: '1px dashed var(--accent-border)', borderRadius: 8 }}>
                  <input value={entryForm.label} onChange={e => setEntryForm(f => ({ ...f, label: e.target.value }))} style={{ ...fs }} placeholder={t('settings.etiqueta_de_la_tarifa')} aria-label={t('settings.etiqueta_de_la_tarifa')} />
                  <input type="number" value={entryForm.cost_rate} onChange={e => setEntryForm(f => ({ ...f, cost_rate: e.target.value }))} style={fs} placeholder={t('settings.coste_por_hora')} aria-label={t('settings.coste_por_hora')} />
                  <input type="number" value={entryForm.billing_rate} onChange={e => setEntryForm(f => ({ ...f, billing_rate: e.target.value }))} style={fs} placeholder={t('settings.tarifa_de_facturacion')} aria-label={t('settings.tarifa_de_facturacion')} />
                  <div className="u-row-6">
                    <Button size="sm" onClick={() => { addEntry({ tableId: tabla.id, data: entryForm }); setEntryForm({ label: '', cost_rate: '', billing_rate: '' }); setAddingEntry(null) }} disabled={!entryForm.label}>{t('settings.anadir')}</Button>
                    <Button size="sm" variant="secondary" onClick={() => setAddingEntry(null)}>×</Button>
                  </div>
                </div>
              )}
            </div>
          ))}
          <div style={{ display: 'flex', gap: 10, padding: '12px 16px', background: 'var(--accent-muted)', border: '1px dashed var(--accent-border)', borderRadius: 'var(--radius-md)', alignItems: 'flex-end' }}>
            <div style={{ flex: 2 }}><label style={ls}>Nombre tabla</label><input value={newTable.name} onChange={e => setNewTable(f => ({ ...f, name: e.target.value }))} style={fs} placeholder={t('settings.nombre_de_la_tabla')} aria-label={t('settings.nombre_de_la_tabla')} /></div>
            <div className="u-flex1"><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={ls}>Aplica a</label><select id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={newTable.applies_to} onChange={e => setNewTable(f => ({ ...f, applies_to: e.target.value }))} style={fs}><option value="role">{t('settings.por_rol')}</option><option value="department">{t('settings.por_depto')}</option><option value="client">{t('settings.por_cliente')}</option></select></div>
            <Button onClick={() => { createTable(newTable); setNewTable({ name: '', applies_to: 'role', is_default: false }) }} disabled={!newTable.name}>Crear tabla</Button>
          </div>
        </div>
      )}
    </SeccionDeAjustes>
  )
}

// ── Vacation policies section ─────────────────────────────────────────────────
function VacationSection() {
  const idCampo = React.useId()
  const { t } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const currentYear = new Date().getFullYear()
  const [ui, setUi] = useState({
    year: currentYear,
    newPolicy: { name: '', days_per_year: 23, carries_over: true, max_carryover_days: 5, is_default: false },
  })
  const { year, newPolicy } = ui
  const setYear = (v: SetStateAction<number>) => setUi(s => ({ ...s, year: typeof v === 'function' ? v(s.year) : v }))
  const setNewPolicy = (v: SetStateAction<NewVacationPolicy>) => setUi(s => ({ ...s, newPolicy: typeof v === 'function' ? v(s.newPolicy) : v }))
  const { data: policies = [] } = useQuery<VacationPolicy[]>({ queryKey: ['vacation-policies'], queryFn: () => advancedConfigApi.getVacationPolicies().then(r => r.data) })
  const { data: balances = [] } = useQuery<VacationBalance[]>({ queryKey: ['vacation-balances', year], queryFn: () => advancedConfigApi.getVacationBalances(year).then(r => r.data) })
  const { mutate: createPolicy } = useMutation({ mutationFn: advancedConfigApi.createVacationPolicy, onSuccess: () => qc.invalidateQueries({ queryKey: ['vacation-policies'] }) , onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))})
  const { mutate: deletePolicy } = useMutation({ mutationFn: advancedConfigApi.deleteVacationPolicy, onSuccess: () => qc.invalidateQueries({ queryKey: ['vacation-policies'] }) , onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))})
  const { mutate: updateBalance } = useMutation({ mutationFn: ({ userId, days }: { userId: string; days: number }) => advancedConfigApi.updateVacationBalance(userId, year, days), onSuccess: () => { qc.invalidateQueries({ queryKey: ['vacation-balances', year] }); qc.invalidateQueries({ queryKey: ['vacation-balance-my'] }); } , onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))})

  return (
    <SeccionDeAjustes icon="🏖️" title="Vacaciones y permisos" description="Configura politicas y saldos del equipo">
      <div className="u-mb-20">
        <div style={{ fontSize: "var(--text-base)", fontWeight: 700, marginBottom: 12 }}>{t('settings.politicas_configuradas')}</div>
        <div style={styles.colGap8}>
          {policies.map(p => (
            <div key={p.id} style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '10px 14px', background: 'var(--surface-2)', border: `1px solid ${p.is_default ? 'var(--accent)' : 'var(--surface-4)'}`, borderRadius: 8 }}>
              <div className="u-flex1">
                <span style={{ fontSize: "var(--text-sm)", fontWeight: 600 }}>{p.name}</span>
                {p.is_default && <span style={styles.pill}>{t('settings.por_defecto')}</span>}
                <div className="u-text2-sm-mt2">
                  {p.days_per_year} {t('settings.dias_ano')} {p.carries_over ? `· Acumula hasta ${p.max_carryover_days || '∞'} días` : '· No acumula'}
                </div>
              </div>
              <button onClick={() => deletePolicy(p.id)} style={styles.btnDelete}>🗑</button>
            </div>
          ))}
        </div>
        <div style={{ display: 'flex', gap: 10, marginTop: 12, padding: '10px 14px', background: 'var(--accent-muted)', border: '1px dashed var(--accent-border)', borderRadius: 'var(--radius-md)', flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <div style={{ flex: 2 }}><label style={ls}>Nombre</label><input value={newPolicy.name} onChange={e => setNewPolicy(f => ({ ...f, name: e.target.value }))} style={fs} placeholder={t('settings.nombre_de_la_politica')} aria-label={t('settings.nombre_de_la_politica')} /></div>
          <div className="u-flex1"><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={ls}>{t('settings.dias_ano_2')}</label><input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} type="number" value={newPolicy.days_per_year} onChange={e => setNewPolicy(f => ({ ...f, days_per_year: +e.target.value }))} style={fs} /></div>
          <div className="u-flex1"><label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} style={ls}>{t('settings.max_acumulacion')}</label><input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} type="number" value={newPolicy.max_carryover_days} onChange={e => setNewPolicy(f => ({ ...f, max_carryover_days: +e.target.value }))} style={fs} /></div>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: "var(--text-sm)" }}><input type="checkbox" checked={newPolicy.is_default} onChange={e => setNewPolicy(f => ({ ...f, is_default: e.target.checked }))} />{t('settings.por_defecto')}</label>
          <Button onClick={() => { createPolicy(newPolicy); setNewPolicy({ name: '', days_per_year: 23, carries_over: true, max_carryover_days: 5, is_default: false }) }} disabled={!newPolicy.name}>Crear</Button>
        </div>
      </div>

      {/* Balances */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <div className="u-base-700">{t('settings.saldos_del_equipo')}</div>
          <select value={year} onChange={e => setYear(+e.target.value)} style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '6px 12px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit' }}>
            {[currentYear - 1, currentYear, currentYear + 1].map(y => <option key={y} value={y}>{y}</option>)}
          </select>
        </div>
        <div className="ds-card ds-card--plano">
          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr 1fr 80px', gap: 12, padding: '8px 16px', borderBottom: '1px solid var(--surface-4)', fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            <span>Persona</span><span>Asignados</span><span>Tomados</span><span>Pendientes</span><span>Disponibles</span><span>Editar</span>
          </div>
          {balances.map(b => (
            <div key={b.user_id} style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr 1fr 80px', gap: 12, padding: '10px 16px', borderBottom: '1px solid color-mix(in srgb, var(--surface-4) 19%, transparent)', alignItems: 'center' }}>
              <div>
                <div className="u-base-600">{b.user_name}</div>
                {b.department && <div className="u-text2-xs">{b.department}</div>}
              </div>
              <span style={{ fontSize: "var(--text-base)", fontFamily: 'var(--font-mono)' }}>{b.days_entitled}d</span>
              <span style={{ fontSize: "var(--text-base)", fontFamily: 'var(--font-mono)', color: 'var(--accent)' }}>{b.days_taken}d</span>
              <span style={{ fontSize: "var(--text-base)", fontFamily: 'var(--font-mono)', color: 'var(--warning)' }}>{b.days_pending}d</span>
              <span style={{ fontSize: "var(--text-base)", fontFamily: 'var(--font-mono)', color: b.days_remaining <= 0 ? 'var(--danger)' : 'var(--success)', fontWeight: 700 }}>{b.days_remaining}d</span>
              <input type="number" defaultValue={b.days_entitled} min="0" max="60" onBlur={e => updateBalance({ userId: b.user_id, days: +e.target.value })}
                style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-sm)', padding: '4px 8px', color: 'var(--text-1)', fontSize: "var(--text-sm)", outline: 'none', fontFamily: 'inherit', width: '100%', textAlign: 'center' }} />
            </div>
          ))}
        </div>
      </div>
    </SeccionDeAjustes>
  )
}

// ── Numbering section ─────────────────────────────────────────────────────────
function NumberingSection() {
  const { t } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const { data: seqs = [], isLoading } = useQuery<NumberingSeq[]>({ queryKey: ['numbering-seqs'], queryFn: () => advancedConfigApi.getNumbering().then(r => r.data) })
  const { mutate: update } = useMutation({ mutationFn: ({ entity, data }: { entity: string; data: NumberingSeq }) => advancedConfigApi.updateNumbering(entity, data), onSuccess: () => qc.invalidateQueries({ queryKey: ['numbering-seqs'] }) , onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))})
  const { mutate: reset } = useMutation({ mutationFn: advancedConfigApi.resetNumbering, onSuccess: () => qc.invalidateQueries({ queryKey: ['numbering-seqs'] }) , onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))})
  const ENTITY_LABELS: Record<string, string> = { project: 'Proyecto', task: 'Tarea', contract: 'Contrato', opportunity: 'Oportunidad', change_request: 'Control de cambios', deliverable: 'Entregable', risk: 'Riesgo' }

  return (
    <SeccionDeAjustes icon="🔢" title="Numeracion" description="Prefijos y contadores automaticos">
      {isLoading ? <Spinner /> : (
        <div style={styles.colGap10}>
          {seqs.map(s => (
            <div key={s.entity} style={{ display: 'flex', gap: 14, alignItems: 'flex-end', padding: '12px 16px', background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-md)' }}>
              <div style={{ width: 120, flexShrink: 0 }}>
                <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--text-1)' }}>{ENTITY_LABELS[s.entity] || s.entity}</div>
                <div style={{ fontSize: "var(--text-xs)", color: 'var(--accent)', fontFamily: 'var(--font-mono)', marginTop: 4 }}>{s.next_preview}</div>
              </div>
              <div style={{ display: 'flex', gap: 8, flex: 1, flexWrap: 'wrap', alignItems: 'flex-end' }}>
                <div><label style={{ ...ls, fontSize: "var(--text-2xs)" }}>Prefijo</label><input defaultValue={s.prefix} onBlur={e => update({ entity: s.entity, data: { ...s, prefix: e.target.value } })} style={{ ...fs, width: 70 }} placeholder="Prefijo" aria-label="Prefijo" /></div>
                <div><label style={{ ...ls, fontSize: "var(--text-2xs)" }}>Sep.</label><input defaultValue={s.separator} onBlur={e => update({ entity: s.entity, data: { ...s, separator: e.target.value } })} style={{ ...fs, width: 40 }} /></div>
                <div><label style={{ ...ls, fontSize: "var(--text-2xs)" }}>{t('settings.digitos')}</label><input type="number" min="1" max="8" defaultValue={s.padding} onBlur={e => update({ entity: s.entity, data: { ...s, padding: +e.target.value } })} style={{ ...fs, width: 60 }} /></div>
                <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', fontSize: "var(--text-sm)", color: 'var(--text-2)', paddingBottom: 4 }}>
                  <input type="checkbox" defaultChecked={s.include_year} onChange={e => update({ entity: s.entity, data: { ...s, include_year: e.target.checked } })} />
                  {t('settings.incluir_ano')}
                </label>
              </div>
              <div style={{ flexShrink: 0 }}>
                <div className="u-text2-xs-mb4">Contador: {s.current_value}</div>
                <button onClick={() => { openConfirmGlobal({ message: `¿Resetear contador de ${ENTITY_LABELS[s.entity] || s.entity} a 0?`, onConfirm: () => reset(s.entity), danger: true }) }} style={{ background: 'none', border: '1px solid var(--danger-border)', borderRadius: 'var(--radius-sm)', padding: '4px 10px', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-xs)", fontFamily: 'inherit' }}>Resetear</button>
              </div>
            </div>
          ))}
        </div>
      )}
    </SeccionDeAjustes>
  )
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
  const ENTITIES = [
    { value: 'project',     label: 'Proyecto' },
    { value: 'task',        label: 'Tarea' },
    { value: 'user',        label: 'Usuario' },
    { value: 'client',      label: 'Cliente' },
    { value: 'contract',    label: 'Contrato' },
    { value: 'invoice',     label: 'Factura' },
    { value: 'absence',     label: 'Ausencia' },
    { value: 'document',    label: 'Documento' },
    { value: 'risk',        label: 'Riesgo' },
    { value: 'deliverable', label: 'Entregable' },
    { value: 'imputation',  label: 'Imputación' },
    { value: 'expense',     label: 'Gasto' },
    { value: 'opportunity', label: 'Oportunidad' },
    { value: 'ticket',      label: 'Ticket' },
  ]
  const TYPES = [{ value: 'text', label: 'Texto' }, { value: 'number', label: 'Número' }, { value: 'date', label: 'Fecha' }, { value: 'select', label: 'Selector' }, { value: 'boolean', label: 'Sí/No' }, { value: 'url', label: 'URL' }]
  const TYPE_ICONS: Record<string, string> = { text: '📝', number: '🔢', date: '📅', select: '📋', boolean: '☑️', url: '🔗' }
  const byEntity = fields.reduce<Record<string, CustomField[]>>((a, f) => { if (!a[f.entity]) a[f.entity] = []; a[f.entity].push(f); return a }, {})

  return (
    <SeccionDeAjustes icon="🧩" title="Campos personalizados" description="Define campos extra para entidades">
      {isLoading ? <Spinner /> : (
        <div className="u-mb-20">
          {Object.entries(byEntity).map(([entity, entityFields]) => (
            <div key={entity} className="u-mb-16">
              <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>
                {ENTITIES.find(e => e.value === entity)?.label || entity}
              </div>
              <div className="u-stack-6">
                {entityFields.map(f => (
                  <React.Fragment key={f.id}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '8px 12px', background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 8 }}>
                      <span style={{ fontSize: "var(--text-lg)" }}>{TYPE_ICONS[f.field_type] || '📝'}</span>
                      <div className="u-flex1">
                        <span className="u-base-600">{f.name}</span>
                        <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginLeft: 8, fontFamily: 'var(--font-mono)' }}>{f.field_key}</span>
                        {f.is_required && <span style={{ fontSize: "var(--text-2xs)", color: 'var(--danger)', marginLeft: 8 }}>*obligatorio</span>}
                      </div>
                      <span className="u-text2-xs">{TYPES.find(t => t.value === f.field_type)?.label}</span>
                      <button onClick={() => { setEditingFieldId(f.id); setEditFieldForm({ name: f.name, is_required: f.is_required, placeholder: f.placeholder||'' }) }}
                        style={styles.btnEdit}>✏</button>
                      <button onClick={() => deleteField(f.id)} style={styles.btnDelete}>🗑</button>
                    </div>
                    {editingFieldId === f.id && (
                      <div style={{ display:'flex', gap:8, padding:'10px', background:'var(--accent-muted)',
                        border:'1px solid var(--accent-glow)', borderRadius:8, marginTop:-4, alignItems:'center' }}>
                        <input value={editFieldForm.name} onChange={e=>setEditFieldForm(f=>({...f,name:e.target.value}))}
                          style={{...fs,flex:2}} placeholder={t('settings.nombre_del_campo')} aria-label={t('settings.nombre_del_campo')} autoFocus />
                        <input value={editFieldForm.placeholder} onChange={e=>setEditFieldForm(f=>({...f,placeholder:e.target.value}))}
                          style={{...fs,flex:2}} placeholder={t('settings.placeholder_del_campo')} aria-label={t('settings.placeholder_del_campo')} />
                        <label style={{display:'flex',alignItems:'center',gap:5,cursor:'pointer',fontSize: "var(--text-sm)",whiteSpace:'nowrap'}}>
                          <input type="checkbox" checked={editFieldForm.is_required}
                            onChange={e=>setEditFieldForm(f=>({...f,is_required:e.target.checked}))} />Obligatorio
                        </label>
                        <button onClick={() => updateField({ id: f.id, data: editFieldForm })} disabled={!editFieldForm.name}
                          style={{background:'var(--accent)',border:'none',borderRadius:'var(--radius-sm)',padding:'5px 12px',color: 'var(--on-accent)',cursor:'pointer',fontSize: "var(--text-sm)",fontFamily:'inherit'}}>✓ Guardar</button>
                        <button onClick={() => setEditingFieldId(null)}
                          style={{background:'none',border:'1px solid var(--surface-4)',borderRadius:'var(--radius-sm)',padding:'5px 9px',color:'var(--text-2)',cursor:'pointer',fontSize: "var(--text-sm)"}}>✕</button>
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
      <div style={{ padding: '14px 16px', background: 'var(--accent-muted)', border: '1px dashed var(--accent-border)', borderRadius: 'var(--radius-md)' }}>
        <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--accent)', marginBottom: 12 }}>{t('settings.anadir_campo_personalizado')}</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr auto', gap: 10, alignItems: 'flex-end' }}>
          <div><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={ls}>Entidad</label><select id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.entity} onChange={e => setForm(f => ({ ...f, entity: e.target.value }))} style={fs}>{ENTITIES.map(e => <option key={e.value} value={e.value}>{e.label}</option>)}</select></div>
          <div><label style={ls}>Nombre</label><input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value, field_key: e.target.value.toLowerCase().replace(/\s+/g, '_').replace(/[^a-z0-9_]/g, '') }))} style={fs} placeholder={t('settings.nombre_del_campo')} aria-label={t('settings.nombre_del_campo')} /></div>
          <div><label style={ls}>Clave</label><input value={form.field_key} onChange={e => setForm(f => ({ ...f, field_key: e.target.value }))} style={fs} placeholder="Clave interna" aria-label="Clave interna" /></div>
          <div><label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} style={ls}>Tipo</label><select id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.field_type} onChange={e => setForm(f => ({ ...f, field_type: e.target.value }))} style={fs}>{TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}</select></div>
          <Button onClick={() => { createField(form); setForm({ entity: form.entity, name: '', field_key: '', field_type: 'text', is_required: false, placeholder: '' }) }} disabled={!form.name || !form.field_key}>{t('settings.anadir')}</Button>
        </div>
      </div>
    </SeccionDeAjustes>
  )
}

// ── Templates section ─────────────────────────────────────────────────────────
function TemplatesSection() {
  const { t } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const { data: templates = [], isLoading } = useQuery<ProjectTemplate[]>({ queryKey: ['project-templates'], queryFn: () => advancedConfigApi.getTemplates().then(r => r.data) })
  const { mutate: deleteTemplate } = useMutation({ mutationFn: advancedConfigApi.deleteTemplate, onSuccess: () => qc.invalidateQueries({ queryKey: ['project-templates'] }) , onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))})
  const { mutate: createTemplate, isPending: creatingTemplate } = useMutation({
    mutationFn: advancedConfigApi.createTemplate,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['project-templates'] })
      setShowCreate(false)
      toast.success('Plantilla creada')
    },
    onError: e => toast.error(extractErr(e, 'No se pudo crear la plantilla')),
  })
  const [ui, setUi] = useState<{ showCreate: boolean; selected: ProjectTemplate | null }>({ showCreate: false, selected: null })
  const { showCreate, selected } = ui
  const setShowCreate = (v: SetStateAction<boolean>) => setUi(s => ({ ...s, showCreate: typeof v === 'function' ? v(s.showCreate) : v }))
  const setSelected = (v: SetStateAction<ProjectTemplate | null>) => setUi(s => ({ ...s, selected: typeof v === 'function' ? v(s.selected) : v }))

  return (
    <SeccionDeAjustes icon="📐" title="Plantillas" description="Define plantillas de proyecto y fases">
      {isLoading ? <Spinner /> : templates.length === 0 ? (
        <EmptyState svgIcon={<Sparkles size={36} />} title={t('settings.empty_templates_title')} description={t('settings.empty_templates_desc')} />
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 14, marginBottom: 16 }}>
          {templates.map(t => (
              <div key={t.id} role="button" tabIndex={0} style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, padding: 18, cursor: 'pointer', width:'100%', textAlign:'left', fontFamily:'inherit' }}
              onMouseEnter={e => e.currentTarget.style.borderColor = 'var(--accent-glow)'}
              onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--surface-4)'}
                onClick={() => setSelected(t)}
                onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSelected(t) } }}>
              <div style={{ fontSize: "var(--text-md-em)", fontWeight: 700, marginBottom: 6 }}>{t.name}</div>
              {t.description && <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginBottom: 10 }}>{t.description}</div>}
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 12 }}>
                {[`${t.phase_count} fases`, `${t.task_count} tareas`, `${t.risk_count} riesgos`, `${t.deliverable_count} entregables`].map(l => (
                  <span key={l} style={{ fontSize: "var(--text-xs)", background: 'var(--surface-3)', color: 'var(--text-2)', borderRadius: 20, padding: '2px 8px' }}>{l}</span>
                ))}
                {t.estimated_weeks && <span style={{ fontSize: "var(--text-xs)", color: 'var(--accent)' }}>~{t.estimated_weeks}sem</span>}
              </div>
              <div className="u-row-8">
                <Button size="sm" onClick={e => { e.stopPropagation(); setSelected(t) }}>Ver detalle</Button>
                <button onClick={e => { e.stopPropagation(); deleteTemplate(t.id) }} style={{ background: 'none', border: '1px solid var(--danger-border)', borderRadius: 'var(--radius-sm)', padding: '4px 10px', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>🗑</button>
              </div>
            </div>
          ))}
        </div>
      )}
      <button onClick={() => setShowCreate(true)} style={{ width: '100%', padding: '10px', border: '1px dashed var(--surface-4)', borderRadius: 'var(--radius-md)', background: 'transparent', color: 'var(--text-2)', fontSize: "var(--text-base)", cursor: 'pointer', fontFamily: 'inherit', textAlign: 'center' }}>＋ Crear plantilla</button>
      {showCreate && <CreateTemplateModal isSaving={creatingTemplate} onClose={() => setShowCreate(false)} onSave={createTemplate} />}
      {selected && <TemplateDetailModal template={selected} onClose={() => setSelected(null)} />}
    </SeccionDeAjustes>
  )
}

type CreateTemplateUi = { form: TemplateForm; phase: PhaseInput; task: TaskInput; risk: RiskInput; deliverable: DeliverableInput }

function CreateTemplateModal({ onClose, onSave, isSaving = false }: { onClose: () => void; onSave: (data: TemplatePayload) => void; isSaving?: boolean }) {
  const idCampo = React.useId()
  const { t } = useAppLang()
  const [ui, setUi] = React.useReducer(
    (s: CreateTemplateUi, p: Partial<CreateTemplateUi> | ((s: CreateTemplateUi) => Partial<CreateTemplateUi>)): CreateTemplateUi => {
      const next = typeof p === 'function' ? p(s) : p
      return { ...s, ...next }
    },
    {
      form: { name: '', description: '', project_type: 'consulting', estimated_weeks: '', estimated_hours: '', phases: [], risks: [], deliverables: [] },
      phase: { name: '', description: '', estimated_weeks: '', estimated_hours: '', tasks: [] },
      task: { title: '', estimated_hours: '', skill_required: '' },
      risk: { title: '', category: '', probability: 'medium', impact: 'moderate', mitigation_plan: '' },
      deliverable: { name: '', format: '', week_offset: '', billing_pct: '', acceptance_criteria: '' },
    },
  )
  const { form, phase, task, risk, deliverable } = ui
  const setForm = (v: SetStateAction<TemplateForm>) => setUi(typeof v === 'function' ? (s: CreateTemplateUi) => ({ form: v(s.form) }) : { form: v })
  const setPhase = (v: SetStateAction<PhaseInput>) => setUi(typeof v === 'function' ? (s: CreateTemplateUi) => ({ phase: v(s.phase) }) : { phase: v })
  const setTask = (v: SetStateAction<TaskInput>) => setUi(typeof v === 'function' ? (s: CreateTemplateUi) => ({ task: v(s.task) }) : { task: v })
  const setRisk = (v: SetStateAction<RiskInput>) => setUi(typeof v === 'function' ? (s: CreateTemplateUi) => ({ risk: v(s.risk) }) : { risk: v })
  const setDeliverable = (v: SetStateAction<DeliverableInput>) => setUi(typeof v === 'function' ? (s: CreateTemplateUi) => ({ deliverable: v(s.deliverable) }) : { deliverable: v })
  const set = (k: keyof TemplateForm) => (e: InputChange) => setForm(f => ({ ...f, [k]: e.target.value }))

  const addTaskToPhase = () => {
    if (!task.title?.trim()) return
    setPhase(p => ({
      ...p,
      tasks: [
        ...p.tasks,
        {
          title: task.title.trim(),
          estimated_hours: task.estimated_hours ? Number(task.estimated_hours) : null,
          skill_required: task.skill_required || null,
        },
      ],
    }))
    setTask({ title: '', estimated_hours: '', skill_required: '' })
  }

  const addPhase = () => {
    if (!phase.name?.trim()) return
    setForm(f => ({
      ...f,
      phases: [
        ...f.phases,
        {
          name: phase.name.trim(),
          description: phase.description || null,
          estimated_weeks: phase.estimated_weeks ? Number(phase.estimated_weeks) : null,
          estimated_hours: phase.estimated_hours ? Number(phase.estimated_hours) : null,
          tasks: phase.tasks,
        },
      ],
    }))
    setPhase({ name: '', description: '', estimated_weeks: '', estimated_hours: '', tasks: [] })
    setTask({ title: '', estimated_hours: '', skill_required: '' })
  }

  const addRisk = () => {
    if (!risk.title?.trim()) return
    setForm(f => ({
      ...f,
      risks: [
        ...f.risks,
        {
          title: risk.title.trim(),
          category: risk.category || null,
          probability: risk.probability,
          impact: risk.impact,
          mitigation_plan: risk.mitigation_plan || null,
        },
      ],
    }))
    setRisk({ title: '', category: '', probability: 'medium', impact: 'moderate', mitigation_plan: '' })
  }

  const addDeliverable = () => {
    if (!deliverable.name?.trim()) return
    setForm(f => ({
      ...f,
      deliverables: [
        ...f.deliverables,
        {
          name: deliverable.name.trim(),
          format: deliverable.format || null,
          week_offset: deliverable.week_offset ? Number(deliverable.week_offset) : null,
          billing_pct: deliverable.billing_pct ? Number(deliverable.billing_pct) : null,
          acceptance_criteria: deliverable.acceptance_criteria || null,
        },
      ],
    }))
    setDeliverable({ name: '', format: '', week_offset: '', billing_pct: '', acceptance_criteria: '' })
  }

  const submit = () => {
    onSave({
      ...form,
      estimated_weeks: form.estimated_weeks ? Number(form.estimated_weeks) : null,
      estimated_hours: form.estimated_hours ? Number(form.estimated_hours) : null,
    })
  }

  return (
    <Modal open title={t('settings.nueva_plantilla')} onClose={onClose} width={760}>
      <div style={styles.colGap16}>
        <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr', gap: 12 }}>
          <div><label style={ls}>Nombre *</label><input value={form.name} onChange={set('name')} style={fs} placeholder={t('settings.nombre_de_la_plantilla')} aria-label={t('settings.nombre_de_la_plantilla')} /></div>
          <div><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={ls}>Tipo proyecto</label><select id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.project_type} onChange={set('project_type')} style={fs}><option value="consulting">consulting</option><option value="development">development</option><option value="maintenance">maintenance</option><option value="internal">internal</option><option value="rd">rd</option></select></div>
          <div><label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} style={ls}>Semanas estimadas</label><input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} type="number" value={form.estimated_weeks} onChange={set('estimated_weeks')} style={fs} /></div>
          <div><label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} style={ls}>Horas estimadas</label><input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} type="number" value={form.estimated_hours} onChange={set('estimated_hours')} style={fs} /></div>
        </div>
        <div><label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} style={ls}>{t('settings.descripcion')}</label><textarea id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={form.description} onChange={set('description')} rows={2} style={{ ...fs, resize: 'vertical' }} /></div>

        {/* Phases */}
        <div>
          <div style={{ fontSize: "var(--text-base)", fontWeight: 700, marginBottom: 10 }}>Fases ({form.phases.length})</div>
          {form.phases.map((p, i) => (
            <div key={i} style={{ padding: '8px 12px', background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 8, marginBottom: 6 }}>
              <div className="u-row-between">
                <span className="u-base-600">{p.name}</span>
                <div className="u-row-8">
                  <span className="u-text2-xs">{p.tasks.length} tareas</span>
                  <button onClick={() => setForm(f => ({ ...f, phases: f.phases.filter((_, j) => j !== i) }))} style={{ background: 'none', border: 'none', color: 'var(--danger)', cursor: 'pointer' }}>×</button>
                </div>
              </div>
            </div>
          ))}
          <div style={{ display: 'grid', gridTemplateColumns: '2fr 2fr 1fr 1fr', gap: 8, padding: 8, background: 'var(--surface-3)', borderRadius: 8, marginBottom: 8 }}>
            <input value={phase.name} onChange={e => setPhase(f => ({ ...f, name: e.target.value }))} style={fs} placeholder={t('settings.nombre_de_la_fase')} aria-label={t('settings.nombre_de_la_fase')} />
            <input value={phase.description} onChange={e => setPhase(f => ({ ...f, description: e.target.value }))} style={fs} placeholder={t('settings.descripcion_de_fase')} aria-label={t('settings.descripcion_de_fase')} />
            <input type="number" value={phase.estimated_weeks} onChange={e => setPhase(f => ({ ...f, estimated_weeks: e.target.value }))} style={fs} placeholder="Semanas" aria-label="Semanas estimadas" />
            <input type="number" value={phase.estimated_hours} onChange={e => setPhase(f => ({ ...f, estimated_hours: e.target.value }))} style={fs} placeholder="Horas" aria-label="Horas estimadas" />
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr auto', gap: 8, padding: 8, background: 'var(--surface-3)', borderRadius: 8 }}>
            <input value={task.title} onChange={e => setTask(f => ({ ...f, title: e.target.value }))} style={fs} placeholder={t('settings.titulo_tarea')} aria-label={t('settings.titulo_tarea')} />
            <input type="number" value={task.estimated_hours} onChange={e => setTask(f => ({ ...f, estimated_hours: e.target.value }))} style={fs} placeholder="Horas" aria-label="Horas tarea" />
            <input value={task.skill_required} onChange={e => setTask(f => ({ ...f, skill_required: e.target.value }))} style={fs} placeholder="Skill requerida" aria-label="Skill requerida" />
            <Button size="sm" onClick={addTaskToPhase} disabled={!task.title}>+ Tarea</Button>
          </div>
          {phase.tasks.length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 8 }}>
              {phase.tasks.map((tk, i) => (
                <span key={`${tk.title}-${i}`} style={{ fontSize: "var(--text-xs)", background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 16, padding: '2px 8px' }}>{tk.title}{tk.estimated_hours ? ` (${tk.estimated_hours}h)` : ''}</span>
              ))}
            </div>
          )}
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 8 }}>
            <Button size="sm" onClick={addPhase} disabled={!phase.name}>+ Fase</Button>
          </div>
        </div>

        {/* Risks */}
        <div>
          <div style={{ fontSize: "var(--text-base)", fontWeight: 700, marginBottom: 10 }}>Riesgos ({form.risks.length})</div>
          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr auto', gap: 8, padding: 8, background: 'var(--surface-3)', borderRadius: 8 }}>
            <input value={risk.title} onChange={e => setRisk(f => ({ ...f, title: e.target.value }))} style={fs} placeholder={t('settings.titulo_riesgo')} aria-label={t('settings.titulo_riesgo')} />
            <input value={risk.category} onChange={e => setRisk(f => ({ ...f, category: e.target.value }))} style={fs} placeholder={t('settings.categoria')} aria-label={t('settings.categoria_riesgo')} />
            <select value={risk.probability} onChange={e => setRisk(f => ({ ...f, probability: e.target.value }))} style={fs}><option value="low">low</option><option value="medium">medium</option><option value="high">high</option></select>
            <select value={risk.impact} onChange={e => setRisk(f => ({ ...f, impact: e.target.value }))} style={fs}><option value="minor">minor</option><option value="moderate">moderate</option><option value="major">major</option><option value="critical">critical</option></select>
            <Button size="sm" onClick={addRisk} disabled={!risk.title}>+ Riesgo</Button>
          </div>
          <textarea aria-label={t('settings.plan_de_mitigacion_opcional')} value={risk.mitigation_plan} onChange={e => setRisk(f => ({ ...f, mitigation_plan: e.target.value }))} rows={2} style={{ ...fs, resize: 'vertical', marginTop: 8 }} placeholder={t('settings.plan_de_mitigacion_opcional')} />
        </div>

        {/* Deliverables */}
        <div>
          <div style={{ fontSize: "var(--text-base)", fontWeight: 700, marginBottom: 10 }}>Entregables ({form.deliverables.length})</div>
          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr auto', gap: 8, padding: 8, background: 'var(--surface-3)', borderRadius: 8 }}>
            <input value={deliverable.name} onChange={e => setDeliverable(f => ({ ...f, name: e.target.value }))} style={fs} placeholder="Nombre entregable" aria-label="Nombre entregable" />
            <input value={deliverable.format} onChange={e => setDeliverable(f => ({ ...f, format: e.target.value }))} style={fs} placeholder="Formato" aria-label="Formato entregable" />
            <input type="number" value={deliverable.week_offset} onChange={e => setDeliverable(f => ({ ...f, week_offset: e.target.value }))} style={fs} placeholder="Semana" aria-label="Semana entregable" />
            <input type="number" value={deliverable.billing_pct} onChange={e => setDeliverable(f => ({ ...f, billing_pct: e.target.value }))} style={fs} placeholder={t('settings.facturacion')} aria-label={t('settings.porcentaje_facturacion')} />
            <Button size="sm" onClick={addDeliverable} disabled={!deliverable.name}>+ Entregable</Button>
          </div>
          <textarea aria-label={t('settings.criterio_de_aceptacion_opcional')} value={deliverable.acceptance_criteria} onChange={e => setDeliverable(f => ({ ...f, acceptance_criteria: e.target.value }))} rows={2} style={{ ...fs, resize: 'vertical', marginTop: 8 }} placeholder={t('settings.criterio_de_aceptacion_opcional')} />
        </div>

        <div style={styles.rowFlexEnd}>
          <Button variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button onClick={submit} disabled={!form.name || isSaving}>{isSaving ? 'Creando...' : 'Crear plantilla'}</Button>
        </div>
      </div>
    </Modal>
  )
}

function TemplateDetailModal({ template, onClose }: { template: ProjectTemplate; onClose: () => void }) {
  return (
    <Modal open title={template.name} onClose={onClose} width={600}>
      {template.description && <p style={{ color: 'var(--text-2)', fontSize: "var(--text-base)", marginBottom: 16 }}>{template.description}</p>}
      <div className="u-stack-12">
        {template.phases?.map(p => (
          <div key={p.id} style={{ background: 'var(--surface-3)', borderRadius: 'var(--radius-md)', padding: '12px 16px' }}>
            <div style={{ fontSize: "var(--text-base)", fontWeight: 700, marginBottom: 8 }}>📋 {p.name}</div>
            {p.tasks?.map(t => (
              <div key={t.id} style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', padding: '3px 8px', borderLeft: '2px solid var(--surface-4)', marginBottom: 3 }}>
                {t.title} {t.estimated_hours ? `(${t.estimated_hours}h)` : ''}
              </div>
            ))}
          </div>
        ))}
      </div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 16 }}>
        <Button variant="secondary" onClick={onClose}>Cerrar</Button>
      </div>
    </Modal>
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
    <SeccionDeAjustes icon="🏢" title="Sedes" description="Gestiona oficinas y zonas horarias">
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 16 }}>
        {offices.map(o => (
          <div key={o.id}>
            {editingId === o.id ? (
              <div style={{ display: 'flex', gap: 8, padding: '10px 12px', background: 'var(--accent-muted)',
                border: '1px solid var(--accent-glow)', borderRadius: 'var(--radius-md)', flexWrap: 'wrap', alignItems: 'flex-end' }}>
                <div style={{ flex: 2, minWidth: 120 }}><label style={ls}>Nombre *</label>
                  <input value={editForm.name} onChange={e => setEditForm(f=>({...f,name:e.target.value}))} style={fs} autoFocus /></div>
                <div style={{ flex: 1, minWidth: 90 }}><label style={ls}>{t('settings.pais')}</label>
                  <input value={editForm.country} onChange={e => setEditForm(f=>({...f,country:e.target.value}))} style={fs} /></div>
                <div style={{ flex: 1, minWidth: 90 }}><label style={ls}>Ciudad</label>
                  <input value={editForm.city} onChange={e => setEditForm(f=>({...f,city:e.target.value}))} style={fs} /></div>
                <div style={{ flex: 1, minWidth: 160 }}><label style={ls}>Zona horaria</label>
                  <select value={editForm.timezone} onChange={e => setEditForm(f=>({...f,timezone:e.target.value}))} style={fs}>
                    {timezoneOptions(editForm.timezone).map(t => <option key={t} value={t}>{t}</option>)}
                  </select></div>
                <div style={{ display: 'flex', gap: 6, paddingBottom: 1 }}>
                  <button onClick={() => update({ id: o.id, data: editForm })} disabled={!editForm.name}
                    style={styles.saveBtn}>✓ Guardar</button>
                  <button onClick={() => setEditingId(null)}
                    style={styles.cancelBtnSm}>Cancelar</button>
                </div>
              </div>
            ) : (
              <div style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '10px 14px', background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-md)' }}>
                <span style={{ fontSize: "var(--text-xl)" }}>🏢</span>
                <div className="u-flex1">
                  <div className="u-base-700">{o.name}</div>
                  <div className="u-text2-xs">{o.city}{o.country ? `, ${o.country}` : ''} · {o.timezone}</div>
                </div>
                <button onClick={() => { setEditingId(o.id); setEditForm({ name:o.name, country:o.country||'', city:o.city||'', timezone:o.timezone||defaultTimezone }) }}
                  style={{ background:'none',border:'1px solid var(--surface-4)',borderRadius:'var(--radius-sm)',padding:'3px 8px',color:'var(--text-2)',cursor:'pointer',fontSize: "var(--text-xs)" }}>✏</button>
                <button onClick={() => del(o.id)} style={styles.btnDelete}>🗑</button>
              </div>
            )}
          </div>
        ))}
        {offices.length === 0 && <EmptyState svgIcon={<Building2 size={36} />} title={t('settings.sin_sedes_registradas')} description="Añade la primera sede para tu organización" />}
      </div>
      <div style={styles.addPanel10}>
        <div style={{ flex: 2 }}><label style={ls}>Nombre *</label><input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} style={fs} placeholder={t('settings.nombre_de_la_sede')} aria-label={t('settings.nombre_de_la_sede')} /></div>
        <div className="u-flex1"><label style={ls}>{t('settings.pais')}</label><input value={form.country} onChange={e => setForm(f => ({ ...f, country: e.target.value }))} style={fs} placeholder="Pais" aria-label="Pais" /></div>
        <div className="u-flex1"><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={ls}>Ciudad</label><input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.city} onChange={e => setForm(f => ({ ...f, city: e.target.value }))} style={fs} /></div>
        <div className="u-flex1"><label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} style={ls}>Zona horaria</label><select id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.timezone} onChange={e => setForm(f => ({ ...f, timezone: e.target.value }))} style={fs}>{timezoneOptions(form.timezone).map(t => <option key={t} value={t}>{t}</option>)}</select></div>
        <Button onClick={() => { create(form); setForm({ name: '', country: '', city: '', timezone: defaultTimezone }) }} disabled={!form.name}>{t('settings.anadir')}</Button>
      </div>
    </SeccionDeAjustes>
  )
}

// ── Task types section ────────────────────────────────────────────────────────
function TaskTypesSection() {
  const idCampo = React.useId()
  const { t } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()
  const { data: types = [], isLoading } = useQuery<TaskType[]>({ queryKey: ['task-types-config'], queryFn: () => advancedConfigApi.getTaskTypes().then(r => r.data) })
  const { mutate: create } = useMutation({ mutationFn: advancedConfigApi.createTaskType, onSuccess: () => qc.invalidateQueries({ queryKey: ['task-types-config'] }), onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) })
  const { mutate: update } = useMutation({ mutationFn: ({ id, data }: { id: string; data: TaskTypeEdit }) => advancedConfigApi.updateTaskType(id, data), onSuccess: () => { qc.invalidateQueries({ queryKey: ['task-types-config'] }); setEditingId(null) }, onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) })
  const { mutate: del } = useMutation({ mutationFn: advancedConfigApi.deleteTaskType, onSuccess: () => qc.invalidateQueries({ queryKey: ['task-types-config'] }), onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) })
  const [ui, setUi] = useState<{ form: TaskTypeForm; editingId: string | null; editForm: TaskTypeEdit }>({
    form: { name: '', value: '', icon: '📋', color: COLOR_DATO_POR_DEFECTO, is_billable_default: true },
    editingId: null,
    editForm: { name: '', icon: '📋', color: COLOR_DATO_POR_DEFECTO, is_billable_default: true },
  })
  const { form, editingId, editForm } = ui
  const setForm = (v: SetStateAction<TaskTypeForm>) => setUi(s => ({ ...s, form: typeof v === 'function' ? v(s.form) : v }))
  const setEditingId = (v: SetStateAction<string | null>) => setUi(s => ({ ...s, editingId: typeof v === 'function' ? v(s.editingId) : v }))
  const setEditForm = (v: SetStateAction<TaskTypeEdit>) => setUi(s => ({ ...s, editForm: typeof v === 'function' ? v(s.editForm) : v }))

  return (
    <SeccionDeAjustes icon="🏷️" title={t('settings.tipos_de_tarea')} description="Gestiona etiquetas y tipos facturables">
      {isLoading ? <Spinner /> : (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 16 }}>
          {types.map(t => (
            <div key={t.id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px', background: 'var(--surface-2)', border: `1px solid ${alpha(t.color, '40')}`, borderRadius: 'var(--radius-md)' }}>
              <span style={{ fontSize: "var(--text-lg-em)" }}>{t.icon}</span>
              <div>
                <div style={{ fontSize: "var(--text-base)", fontWeight: 700, color: t.color }}>{t.name}</div>
                <div className="u-text2-2xs">{t.is_billable_default ? 'Facturable' : 'No facturable'}</div>
              </div>
              <button onClick={() => { setEditingId(t.id); setEditForm({ name: t.name, icon: t.icon, color: t.color, is_billable_default: t.is_billable_default }) }}
                style={{ background: 'none', border: 'none', color: 'var(--text-3)', cursor: 'pointer', fontSize: "var(--text-sm)", marginLeft: 2 }}>✏</button>
              <button onClick={() => del(t.id)} style={{ background: 'none', border: 'none', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-md)", marginLeft: 2 }}>×</button>
            </div>
          ))}
        </div>
      )}
      {editingId && (
        <div style={{ display:'flex', gap:8, padding:'10px 14px', background:'var(--accent-muted)',
          border:'1px solid var(--accent-glow)', borderRadius:'var(--radius-md)', marginBottom:8, flexWrap:'wrap', alignItems:'flex-end' }}>
          <div><label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={ls}>Nombre *</label><input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={editForm.name} onChange={e => setEditForm(f=>({...f,name:e.target.value}))} style={{...fs,width:130}} autoFocus /></div>
          <div><label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} style={ls}>Icono</label><input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={editForm.icon} onChange={e => setEditForm(f=>({...f,icon:e.target.value}))} style={{...fs,width:55}} /></div>
          <div><label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} style={ls}>Color</label><input id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} type="color" value={/^#[0-9a-fA-F]{6}$/.test(editForm.color)?editForm.color:COLOR_DATO_POR_DEFECTO} onChange={e=>setEditForm(f=>({...f,color:e.target.value}))} style={{width:38,height:35,border:'none',background:'transparent',cursor:'pointer'}} /></div>
          <label style={{display:'flex',alignItems:'center',gap:5,cursor:'pointer',fontSize: "var(--text-sm)",paddingBottom:4}}><input type="checkbox" checked={editForm.is_billable_default} onChange={e=>setEditForm(f=>({...f,is_billable_default:e.target.checked}))} />Facturable</label>
          <button onClick={() => update({ id: editingId, data: editForm })} disabled={!editForm.name} style={styles.saveBtn}>✓ Guardar</button>
          <button onClick={() => setEditingId(null)} style={styles.cancelBtnSm}>Cancelar</button>
        </div>
      )}
      <div style={styles.addPanel10}>
        <div><label style={ls}>Nombre *</label><input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value, value: e.target.value.toLowerCase().replace(/\s+/g, '_') }))} style={{ ...fs, width: 140 }} placeholder="Nombre" aria-label="Nombre" /></div>
        <div><label style={ls}>Clave</label><input value={form.value} onChange={e => setForm(f => ({ ...f, value: e.target.value }))} style={{ ...fs, width: 110 }} placeholder="Clave" aria-label="Clave" /></div>
        <div><label style={ls}>Icono</label><input value={form.icon} onChange={e => setForm(f => ({ ...f, icon: e.target.value }))} style={{ ...fs, width: 60 }} placeholder="Icono" aria-label="Icono" /></div>
        <div><label style={ls}>Color</label><div className="u-row-6"><input type="color" value={/^#[0-9a-fA-F]{6}$/.test(form.color) ? form.color : COLOR_DATO_POR_DEFECTO} onChange={e => setForm(f => ({ ...f, color: e.target.value }))} style={{ width: 38, height: 38, border: 'none', background: 'transparent', cursor: 'pointer' }} /><input value={form.color} onChange={e => setForm(f => ({ ...f, color: e.target.value }))} style={{ ...fs, width: 90 }} /></div></div>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', fontSize: "var(--text-sm)", paddingBottom: 4 }}><input type="checkbox" checked={form.is_billable_default} onChange={e => setForm(f => ({ ...f, is_billable_default: e.target.checked }))} />Facturable</label>
        <Button onClick={() => { create(form); setForm({ name: '', value: '', icon: '📋', color: COLOR_DATO_POR_DEFECTO, is_billable_default: true }) }} disabled={!form.name || !form.value}>{t('settings.anadir')}</Button>
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
    <select value={valor} onChange={e => onChange(e.target.value)} aria-label={t('settings.area_del_departamento')} style={{ ...fs, flex: 2, minWidth: 0, padding: '5px 9px' }}>
      <option value="">{t('settings.sin_area')}</option>
      {areas.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
    </select>
  )
  return (
    <>
    <AreasSection />
    <SeccionDeAjustes icon="🏢" title="Departamentos" description="Estructura interna de la organizacion">
      {isLoading ? <Spinner /> : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 12 }}>
          {data.map(d => (
            <div key={d.id}>
              {editingId === d.id ? (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px', flexWrap: 'wrap',
                  background: 'var(--accent-muted)', border: '1px solid var(--accent-glow)', borderRadius: 'var(--radius-md)' }}>
                  <input value={editForm.name} onChange={e => setEditForm(f => ({ ...f, name: e.target.value }))}
                    style={{ ...fs, flex: 2, minWidth: 0, padding: '5px 9px' }} placeholder={t('settings.nombre_del_departamento')} aria-label={t('settings.nombre_del_departamento')} autoFocus />
                  <input value={editForm.description} onChange={e => setEditForm(f => ({ ...f, description: e.target.value }))}
                    style={{ ...fs, flex: 3, minWidth: 0, padding: '5px 9px' }} placeholder="Descripcion" aria-label={t('settings.descripcion_del_departamento')} />
                  {selectorDeArea(editForm.area_id, v => setEditForm(f => ({ ...f, area_id: v })))}
                  <button onClick={() => update({ id: d.id, data: { ...editForm, area_id: editForm.area_id || null } })} disabled={!editForm.name}
                    style={{ background: 'var(--accent)', border: 'none', borderRadius: 'var(--radius-sm)', padding: '5px 12px',
                      color: 'var(--on-accent-light)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>✓</button>
                  <button onClick={() => setEditingId(null)}
                    style={{ background: 'none', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-sm)',
                      padding: '5px 9px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)" }}>✕</button>
                </div>
              ) : (
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px', flexWrap: 'wrap',
                  background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-md)' }}>
                  <span style={{ flex: 1, fontSize: "var(--text-base)", fontWeight: 600 }}>{d.name}</span>
                  {nombreDeArea(d.area_id) && <span style={{ fontSize: 'var(--text-xs)', color: 'var(--accent)', border: '1px solid currentColor', borderRadius: 99, padding: '0 8px' }}>{nombreDeArea(d.area_id)}</span>}
                  {d.description && <span className="u-text2-sm">{d.description}</span>}
                  <button onClick={() => { setEditingId(d.id); setEditForm({ name: d.name, description: d.description || '', area_id: d.area_id || '' }) }}
                    style={{ background: 'none', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-sm)',
                      padding: '3px 8px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>✏</button>
                  <button onClick={() => del(d.id)}
                    style={{ background: 'none', border: '1px solid var(--danger-border)', borderRadius: 'var(--radius-sm)',
                      padding: '3px 8px', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>🗑</button>
                </div>
              )}
            </div>
          ))}
          {data.length === 0 && <div style={{ fontSize: "var(--text-base)", color: 'var(--text-3)', textAlign: 'center', padding: 16 }}>{t('settings.sin_departamentos')}</div>}
        </div>
      )}
      <div style={{ display: 'flex', gap: 10, padding: '10px', flexWrap: 'wrap', background: 'var(--accent-muted)', border: '1px dashed var(--accent-border)', borderRadius: 'var(--radius-md)' }}>
        <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} style={{ ...fs, flex: 2, minWidth: 0 }} placeholder={t('settings.nombre_del_departamento')} aria-label={t('settings.nombre_del_departamento')} />
        <input value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} style={{ ...fs, flex: 2, minWidth: 0 }} placeholder="Descripcion" aria-label={t('settings.descripcion_del_departamento')} />
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
    <SeccionDeAjustes icon="🧭" title={t('settings.areas')} description={t('settings.areas_ayuda')}>
      {isLoading ? <Spinner /> : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 12 }}>
          {areas.map(a => (
            <div key={a.id} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px', flexWrap: 'wrap', background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-md)' }}>
              {editando?.id === a.id ? (
                <>
                  <input value={editando.name} onChange={e => setEditando({ id: a.id, name: e.target.value })} aria-label={t('settings.nombre_del_area')} style={{ ...fs, flex: 2, minWidth: 0, padding: '5px 9px' }} autoFocus />
                  <button onClick={() => ejecutar(() => presupuestosApi.guardarArea({ name: editando.name }, a.id)).then(() => setEditando(null))} disabled={!editando.name.trim()}
                    style={{ background: 'var(--accent)', border: 'none', borderRadius: 'var(--radius-sm)', padding: '5px 12px', color: 'var(--on-accent-light)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit' }}>✓</button>
                  <button onClick={() => setEditando(null)} style={{ background: 'none', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-sm)', padding: '5px 9px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)" }}>✕</button>
                </>
              ) : (
                <>
                  <span className="u-base-600">{a.name}</span>
                  <span style={{ flex: 1, minWidth: 0, fontSize: 'var(--text-sm)', color: 'var(--text-2)' }}>{a.departamentos.length ? a.departamentos.join(', ') : t('settings.area_sin_departamentos')}</span>
                  <button onClick={() => setEditando({ id: a.id, name: a.name })} style={{ background: 'none', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-sm)', padding: '3px 8px', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>✏</button>
                  <button onClick={() => ejecutar(() => presupuestosApi.borrarArea(a.id))} style={{ background: 'none', border: '1px solid var(--danger-border)', borderRadius: 'var(--radius-sm)', padding: '3px 8px', color: 'var(--danger)', cursor: 'pointer', fontSize: "var(--text-xs)" }}>🗑</button>
                </>
              )}
            </div>
          ))}
          {areas.length === 0 && <div style={{ fontSize: "var(--text-base)", color: 'var(--text-3)', textAlign: 'center', padding: 16 }}>{t('settings.sin_areas')}</div>}
        </div>
      )}
      <div style={{ display: 'flex', gap: 10, padding: '10px', flexWrap: 'wrap', background: 'var(--accent-muted)', border: '1px dashed var(--accent-border)', borderRadius: 'var(--radius-md)' }}>
        <input value={nombre} onChange={e => setNombre(e.target.value)} style={{ ...fs, flex: 2, minWidth: 0 }} placeholder={t('settings.nombre_del_area')} aria-label={t('settings.nombre_del_area')} />
        <Button onClick={() => ejecutar(() => presupuestosApi.guardarArea({ name: nombre })).then(() => setNombre(''))} disabled={!nombre.trim()}>{t('settings.anadir')}</Button>
      </div>
    </SeccionDeAjustes>
  )
}



// ── Metrics section ───────────────────────────────────────────────────────────
const OPERATOR_LABELS: Record<string, string> = { '+': 'Suma', '-': 'Resta', '*': 'Multiplica', '/': 'Divide' }
const EMPTY_METRIC: MetricForm = { label: '', description: '', operand_a: '', operator: '/', operand_b_type: 'metric', operand_b: '', scale: 1 }

function MetricsSection() {
  const idCampo = React.useId()
  const { t } = useAppLang()
  const toast = useToast()
  const qc = useQueryClient()

  const { data: metricsData = { metrics: [] } } = useQuery<SupportedMetrics>({ queryKey: ['bi-alert-metrics'], queryFn: () => biSmartAlertsApi.supportedMetrics().then(r => r.data) })
  const { data: customData = { items: [] } } = useQuery<{ items?: CustomMetric[] }>({ queryKey: ['bi-custom-metrics'], queryFn: () => biSmartAlertsApi.listCustomMetrics().then(r => r.data) })
  const builtinMetrics = (metricsData.metrics ?? []).filter(m => !m.is_custom)
  const customMetrics = customData.items ?? []

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
    if (!form.label.trim() || !form.operand_a) { toast.error('Nombre y operando A son obligatorios'); return }
    if (form.operand_b_type === 'metric' && !form.operand_b) { toast.error('Selecciona la métrica B'); return }
    createMetric({ ...form, scale: parseFloat(String(form.scale)) || 1 })
  }

  return (
    <SeccionDeAjustes icon="📊" title={t('settings.metricas')} description="Métricas del sistema disponibles para alertas y análisis">
      {/* Built-in metrics */}
      <div style={{ marginBottom: 24 }}>
        <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '.07em', marginBottom: 10 }}>{t('settings.metricas_del_sistema')}{builtinMetrics.length})</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 8 }}>
          {builtinMetrics.map(m => (
            <div key={m.key} style={{ padding: '8px 12px', background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 8 }}>
              <div className="u-text1-sm-600">{m.label}</div>
              <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', fontFamily: 'monospace', marginTop: 2 }}>{m.key}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Custom metrics */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
          <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '.07em' }}>{t('settings.metricas_personalizadas')}{customMetrics.length})</div>
          <Button onClick={() => setShowCreate(true)}>{t('settings.nueva_metrica')}</Button>
        </div>
        {customMetrics.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '16px 0', color: 'var(--text-3)', fontSize: "var(--text-sm)" }}>{t('settings.no_hay_metricas_personalizadas_crea_la_primera')}</div>
        ) : (
          <div style={styles.colGap8}>
            {customMetrics.map(cm => {
              const f: MetricFormula = cm.formula ?? {}
              const la = builtinMetrics.find(m => m.key === f.operand_a)?.label ?? f.operand_a
              const lb = f.operand_b_type === 'metric'
                ? (builtinMetrics.find(m => m.key === f.operand_b)?.label ?? f.operand_b)
                : f.operand_b
              const scale = parseFloat(String(f.scale)) !== 1 ? ` × ${f.scale}` : ''
              return (
                <div key={cm.key} style={{ padding: '12px 14px', background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-md)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
                  <div className="u-flex1-min0">
                    <div style={{ fontWeight: 600, fontSize: "var(--text-base)", marginBottom: 2 }}>{cm.label}</div>
                    <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', fontFamily: 'monospace' }}>({la} {f.operator} {lb}){scale}</div>
                    {cm.description && <div className="u-text3-xs-mt2">{cm.description}</div>}
                  </div>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexShrink: 0 }}>
                    <span style={{ fontSize: "var(--text-2xs)", color: 'var(--text-3)', fontFamily: 'monospace' }}>{cm.key}</span>
                    <Button variant="danger" style={{ padding: '4px 10px', fontSize: "var(--text-xs)" }} onClick={() => openConfirmGlobal({ title: 'Eliminar métrica', message: `¿Eliminar "${cm.label}"? Las reglas de alerta que la usen dejarán de funcionar.`, onConfirm: () => deleteMetric(cm.key) })}>Eliminar</Button>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {showCreate && (
        <Modal open title={t('settings.nueva_metrica_personalizada')} onClose={() => { setShowCreate(false); setForm(EMPTY_METRIC) }} width={500}>
          <div style={styles.colGap14}>
            <div>
              <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} style={ls}>Nombre</label>
              <input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.label} onChange={setF('label')} style={fs} placeholder="Ej: Ratio coste-ingreso" />
            </div>
            <div>
              <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} style={ls}>{t('settings.descripcion_opcional')}</label>
              <input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.description} onChange={setF('description')} style={fs} placeholder={t('settings.para_que_sirve_esta_metrica')} />
            </div>
            <div style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-md)', padding: '14px 16px' }}>
              <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '.07em', marginBottom: 12 }}>{t('settings.formula_a_operador_b_escala')}</div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr auto 1fr', gap: 10, alignItems: 'end', marginBottom: 12 }}>
                <div>
                  <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} style={ls}>{t('settings.metrica_a')}</label>
                  <select id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={form.operand_a} onChange={setF('operand_a')} style={fs}>
                    <option value="">— Selecciona —</option>
                    {builtinMetrics.map(m => <option key={m.key} value={m.key}>{m.label}</option>)}
                  </select>
                </div>
                <div>
                  <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} style={ls}>Op.</label>
                  <select id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={form.operator} onChange={setF('operator')} style={{ ...fs, width: 70 }}>
                    {Object.entries(OPERATOR_LABELS).map(([k, v]) => <option key={k} value={k}>{k} ({v})</option>)}
                  </select>
                </div>
                <div>
                  <label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} style={ls}>Tipo B</label>
                  <select id={`${idCampo}-5`} aria-labelledby={`${idCampo}-et5`} value={form.operand_b_type} onChange={setF('operand_b_type')} style={fs}>
                    <option value="metric">{t('settings.otra_metrica')}</option>
                    <option value="constant">Constante</option>
                  </select>
                </div>
              </div>
              <div className="u-grid2-10">
                <div>
                  <label style={ls}>{form.operand_b_type === 'metric' ? 'Métrica B' : 'Valor constante'}</label>
                  {form.operand_b_type === 'metric' ? (
                    <select value={form.operand_b} onChange={setF('operand_b')} style={fs}>
                      <option value="">— Selecciona —</option>
                      {builtinMetrics.filter(m => m.key !== form.operand_a).map(m => <option key={m.key} value={m.key}>{m.label}</option>)}
                    </select>
                  ) : (
                    <input type="number" value={form.operand_b} onChange={setF('operand_b')} style={fs} placeholder="0" />
                  )}
                </div>
                <div>
                  <label id={`${idCampo}-et6`} htmlFor={`${idCampo}-6`} style={ls}>Escala (× resultado)</label>
                  <input id={`${idCampo}-6`} aria-labelledby={`${idCampo}-et6`} type="number" value={form.scale} onChange={setF('scale')} style={fs} placeholder="1" step="any" />
                </div>
              </div>
              {preview && (
                <div style={{ marginTop: 10, padding: '8px 10px', background: 'var(--surface-3)', borderRadius: 'var(--radius-sm)', fontSize: "var(--text-xs)", color: 'var(--accent)', fontFamily: 'monospace' }}>
                  Vista previa: {preview}
                </div>
              )}
            </div>
            <div style={styles.rowFlexEnd}>
              <Button variant="secondary" onClick={() => { setShowCreate(false); setForm(EMPTY_METRIC) }}>Cancelar</Button>
              <Button onClick={submit} disabled={isCreating}>{isCreating ? 'Creando…' : 'Crear métrica'}</Button>
            </div>
          </div>
        </Modal>
      )}
    </SeccionDeAjustes>
  )
}


// ── E-firma (Electronic Signature) settings ───────────────────────────────────

type ESignFieldKey =
  | 'docusign_integration_key' | 'docusign_account_id' | 'docusign_secret_key' | 'docusign_base_url'
  | 'adobe_sign_client_id' | 'adobe_sign_client_secret' | 'adobe_sign_base_url'
/** Respuesta de GET /esign/config (app/api/v1/endpoints/esign.py): claves en texto (secretos como '***') y dos indicadores. */
type ESignConfig = Partial<Record<ESignFieldKey, string>> & { docusign_configured?: boolean; adobe_configured?: boolean }
type ESignProvider = {
  id: string
  label: string
  icon: string
  configKey: 'docusign_configured' | 'adobe_configured'
  fields: Array<{ key: ESignFieldKey; label: string; placeholder: string; secret: boolean }>
}

const ESIGN_PROVIDERS: ESignProvider[] = [
  {
    id: 'docusign',
    label: 'DocuSign',
    icon: '🖊',
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
    icon: '📝',
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
  const isConfigured = config?.[provider.configKey]
  const handleSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    onSave(provider)
  }
  return (
    <div style={{ border: `1px solid ${isConfigured ? 'var(--success)' : 'var(--surface-4)'}`, borderRadius: 12, padding: '18px 20px', background: 'var(--surface-2)', marginBottom: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
        <div className="u-row-center-8">
          <span style={{ fontSize: 20 }}>{provider.icon}</span>
          <span className="u-md-700">{provider.label}</span>
        </div>
        <span style={{
          fontSize: "var(--text-xs)", fontWeight: 700, padding: '3px 10px', borderRadius: 20,
          background: isConfigured ? 'var(--success-bg)' : 'var(--surface-4)',
          color: isConfigured ? 'var(--success)' : 'var(--text-3)',
        }}>
          {isConfigured ? '✓ Configurado' : 'No configurado'}
        </span>
      </div>

      <form onSubmit={handleSubmit}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 14 }}>
        {provider.fields.map(f => (
          <div key={f.key}>
            <label style={ls}>{f.label}</label>
            <input
              type={f.secret ? 'password' : 'text'}
              value={form[f.key] ?? ''}
              onChange={e => onChange(f.key, e.target.value)}
              placeholder={f.secret && form[f.key] === '***' ? 'Guardado — introduce para cambiar' : f.placeholder}
              style={fs}
              autoComplete="off"
            />
          </div>
        ))}
        </div>

        <div className="u-row-end">
          <Button size="sm" type="submit" loading={isSaving}>Guardar {provider.label}</Button>
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
      toast.success('Configuración guardada')
    },
    onError: e => toast.error(extractErr(e, 'Error guardando configuración')),
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
    <SeccionDeAjustes icon="✍" title={t('settings.firma_electronica')} description="Configura las credenciales de los proveedores de firma electrónica. Los cambios se aplican inmediatamente.">
      {isLoading ? (
        <Spinner />
      ) : (
        <>
          <div style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 'var(--radius-md)', padding: '12px 16px', marginBottom: 20 }}>
            <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, marginBottom: 6 }}>Modo manual siempre disponible</div>
            <div className="u-text2-sm">
              {t('settings.sin_credenciales_las_solicitudes_se_gestionan_en')}
            </div>
          </div>

          <div className="u-mb-20">
            <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 12 }}>{t('settings.webhooks_de_sincronizacion_de_estado')}</div>
            <div style={{ background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '10px 14px' }}>
              <div className="u-text2-xs-mb4">{t('settings.configura_en_el_panel_de_tu_proveedor')}</div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: "var(--text-2xs)", color: 'var(--accent)', marginBottom: 2 }}>DocuSign Connect: <span className="u-text1">{apiUrl('/esign/webhooks/docusign')}</span></div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: "var(--text-2xs)", color: 'var(--accent)' }}>Adobe Sign: <span className="u-text1">{apiUrl('/esign/webhooks/adobe')}</span></div>
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
    onError: e => toast.error(extractErr(e, 'Error al guardar')),
  })

  const find = (k: string) => settings.find(s => s.key === k)?.value
  const idleEnabled = find('idle_timeout_enabled') === 'true'
  const idleMinutes = parseInt(find('idle_timeout_minutes') || '30', 10)

  return (
    <SeccionDeAjustes icon="🔒" title={t('settings.seguridad_de_sesion')} description="Controla el cierre automático por inactividad">
      <div style={{ display: 'flex', flexDirection: 'column', gap: 20, maxWidth: 520 }}>

        {/* Toggle idle timeout */}
        <div style={{
          background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
          borderRadius: 'var(--radius-md)', padding: '16px 20px',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16,
        }}>
          <div>
            <div style={{ fontWeight: 700, color: 'var(--text-1)', fontSize: 'var(--text-sm)' }}>
              {t('settings.cierre_de_sesion_por_inactividad')}
            </div>
            <div className="u-text3-xs-mt2">
              {t('settings.cierra_la_sesion_automaticamente_si_el_usuario')}
            </div>
          </div>
          <label style={{ position: 'relative', display: 'inline-block', width: 44, height: 24, flexShrink: 0, cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={idleEnabled}
              onChange={e => update({ key: 'idle_timeout_enabled', value: e.target.checked ? 'true' : 'false' })}
              style={{ opacity: 0, width: 0, height: 0 }}
            />
            <span style={{
              position: 'absolute', inset: 0, borderRadius: 24, cursor: 'pointer', transition: '.2s',
              background: idleEnabled ? 'var(--accent)' : 'var(--surface-4)',
            }}>
              <span style={{
                position: 'absolute', left: idleEnabled ? 22 : 2, top: 2,
                width: 20, height: 20, borderRadius: '50%',
                background: 'var(--surface-0)', transition: '.2s',
              }} />
            </span>
          </label>
        </div>

        {/* Timeout duration selector */}
        <div style={{
          background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
          borderRadius: 'var(--radius-md)', padding: '16px 20px',
          opacity: idleEnabled ? 1 : 0.45,
          pointerEvents: idleEnabled ? 'auto' : 'none',
        }}>
          <label style={ls}>{t('settings.minutos_de_inactividad_antes_de_cerrar_sesion')}</label>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 4 }}>
            {IDLE_TIMEOUT_OPTIONS.map(m => (
              <button
                key={m}
                onClick={() => update({ key: 'idle_timeout_minutes', value: String(m) })}
                style={{
                  padding: '6px 16px', borderRadius: 8, cursor: 'pointer',
                  fontWeight: m === idleMinutes ? 700 : 400,
                  fontSize: 'var(--text-sm)',
                  background: m === idleMinutes ? 'var(--accent)' : 'var(--surface-3)',
                  color: m === idleMinutes ? 'var(--surface-0)' : 'var(--text-2)',
                  border: m === idleMinutes ? '1px solid var(--accent)' : '1px solid var(--surface-4)',
                  transition: 'all .15s',
                }}
              >
                {m < 60 ? `${m} min` : `${m / 60}h`}
              </button>
            ))}
          </div>
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-3)', marginTop: 10 }}>
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
  TaskTypesSection,
  TemplatesSection,
  RateTablesSection,
  VacationSection,
  DepartmentsSection,
  OfficesSection,
  NumberingSection,
  CustomFieldsSection,
  IdiomasSection,
  EmailInboundSection,
  LogLevelSection,
  SystemStateSection,
  ESignSettingsSection,
  RuntimeFlagsSection,
  IntegrationCredentialsSection,
}
