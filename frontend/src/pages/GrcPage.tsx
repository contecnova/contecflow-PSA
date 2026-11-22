/**
 * GrcPage — Governance, Risk & Compliance (backbone de seguridad)
 *
 * Pestañas:
 *  1. Matriz de permisos — editable por admin, persiste en DB vía API
 *  2. Segregación SoD    — reglas CRUD (POST/PATCH/DELETE)
 *  3. Violaciones SoD    — instancias detectadas, resolución
 *  4. Flujos de mitigación — workflows de aprobación
 *  5. Audit Log          — historial inmutable de eventos GRC
 *  6. Explicar acceso, informe medido, evidencias por marco (SOC 2 / ISO 27001) y retención
 */
import { useAppLang } from '../i18n/AppLangContext'
import { useState, useId } from 'react'
import type { CSSProperties } from 'react'
import { openConfirmGlobal, pedirTexto, confirmar } from '../context/ConfirmContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useToast } from '../context/ToastContext'
import { grcApi, approvalsApi, usersApi, governanceApi } from '../services/api'
import { PREFIJO_API_SERVIDOR } from '../services/api/urls'
import type {
  PermisosGrc, MatrizDePermisos as PermMatrix, ReglaSod as SodRule, ConflictoSod as SodViolation,
  ViolacionSod as ViolationRecord, EventoDeAuditoriaGrc as AuditEvent, CapaDeAcceso, ExplicacionDeAcceso as Explicacion,
  InformeDeCumplimiento, PoliticaDeRetencion, BloqueoLegal as Bloqueo, VistaPreviaDeRetencion,
  MarcosDeCumplimiento, EstadoDeControlesDelMarco, EvidenciaDeCumplimiento,
} from '../services/api/tipos-grc'
import type { AxiosResponse } from 'axios'
import Pagination from '../components/ui/Pagination'
import { SMALL_PAGE_SIZE } from '../constants/pagination'
import { advancedConfigApi } from '../services/settingsApi'
import {
  AlertOctagon, AlertTriangle, Check, CheckCircle2, ClipboardList, FileCheck2, FileText, GitPullRequestArrow, Grid3x3,
  KeyRound, Loader2, Pause, Pencil, Play, Plus, RefreshCw, RotateCcw, ScrollText, Search, ShieldAlert, ShieldCheck,
  Timer, Trash2, UserCheck, X, Zap,
} from 'lucide-react'
import { Button, Spinner, EmptyState, Modal, Page, Tabs, KpiCard, StatusBadge, IconButton, Select, TablaSimple, useErroresDeCampo, Input } from '../components/ui'
import { extractErr, downloadBlob, fmtDate, fmtDateTime } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useAppT } from '../i18n/AppLangContext'
import { alpha } from '../constants/theme'
import { POLL_DEFAULT_MS, STALE_SHORT_MS } from '../constants/timings'
import './GrcPage.css'

// ── Catálogo de módulos, acciones y roles ────────────────────────────────────
// Revisión GRC 2026-11b: los módulos los da la API (`/grc/permissions` →
// `modules`, derivados de las rutas). Antes había 15 escritos aquí, dos de
// ellos (`service_desk`, `hr`) sin ninguna ruta detrás, y los otros ~95 que la
// matriz sí aplica no se podían ver ni tocar. Esto sólo pone nombre e icono.
const MODULE_LABELS: Record<string, { label: string }> = {
  projects:   { label: 'pagina_grc.proyectos' },
  tasks:      { label: 'pagina_grc.tareas' },
  timesheets: { label: 'pagina_grc.timesheets' },
  invoices:   { label: 'pagina_grc.facturacion' },
  expenses:   { label: 'pagina_grc.gastos' },
  resources:  { label: 'pagina_grc.recursos' },
  sd:         { label: 'pagina_grc.service_desk' },
  contracts:  { label: 'pagina_grc.contratos' },
  clients:    { label: 'pagina_grc.clientes_crm' },
  reports:    { label: 'pagina_grc.informes_bi' },
  settings:   { label: 'pagina_grc.configuracion' },
  approvals:  { label: 'pagina_grc.aprobaciones' },
  alm:        { label: 'pagina_grc.alm_activos' },
  absences:   { label: 'pagina_grc.ausencias' },
  grc:        { label: 'pagina_grc.grc_seguridad' },
}
type Traductor = ReturnType<typeof useAppT>
const moduleInfo = (t: Traductor) => (id?: string) => {
  const m = MODULE_LABELS[id || '']
  return { id: id || '', label: m ? t(m.label) : id || '' }
}

/** La matriz efectiva con sus módulos y roles, como la devuelve la API (caché compartida). */
function usePermisos() {
  return useQuery<PermisosGrc>({
    queryKey: ['grc-permissions'],
    queryFn: () => grcApi.permissions().then(r => r.data),
  })
}

/** Reserva por si la API no manda `actions` (el vocabulario es `grc_catalog.GRC_ACTIONS`). */
const ACTIONS = ['ver', 'crear', 'editar', 'eliminar', 'aprobar', 'exportar']
const ACTION_LABEL: Record<string, string> = { ver: 'pagina_grc.ver', crear: 'pagina_grc.crear', editar: 'pagina_grc.editar', eliminar: 'pagina_grc.eliminar', aprobar: 'pagina_grc.aprobar', exportar: 'pagina_grc.exportar' }

type Role = { id: string; label: string; color: string }

// ROLES se carga dinámicamente desde la API — ver useRoles() en GrcPage
const FALLBACK_ROLES = [
  { id: 'admin',     label: 'pagina_grc.admin',      color: 'var(--accent)' },
  { id: 'pm',        label: 'pagina_grc.pm',  color: 'var(--purple)' },
  { id: 'team_lead', label: 'pagina_grc.team_lead',  color: 'var(--sky-blue)' },
  { id: 'employee',  label: 'pagina_grc.employee',   color: 'var(--success)' },
  { id: 'hr',        label: 'pagina_grc.hr',  color: 'var(--warning)' },
  { id: 'subcontractor', label: 'pagina_grc.subcontratado', color: 'var(--orange)' },
]

/** FALLBACK_ROLES con el nombre ya traducido. */
const rolesDeReserva = (t: Traductor): Role[] => FALLBACK_ROLES.map(r => ({ ...r, label: t(r.label) }))

const RISK_COLOR: Record<string, string> = { critical: 'var(--danger)', high: 'var(--orange)', medium: 'var(--warning)', low: 'var(--success)' }
/** Niveles de riesgo de una regla SoD (`schemas.grc.NivelDeRiesgo`). */
const RIESGOS = ['critical', 'high', 'medium', 'low'] as const
/** Texto de una acción GRC (con reserva al código si no es del vocabulario). */
const accionDe = (t: Traductor) => (a?: string) => ACTION_LABEL[a || ''] ? t(ACTION_LABEL[a || '']) : (a || '')
const SEV_COLOR: Record<string, string>  = { critical: 'var(--danger)', warning: 'var(--warning)', info: 'var(--info)' }

// ── Shared style atoms ────────────────────────────────────────────────────────

// ═══════════════════════════════════════════════════════════════════════════════
// 1. MATRIZ DE PERMISOS (wired to API)
// ═══════════════════════════════════════════════════════════════════════════════

function MatrixTab({ roles }: { roles: Role[] }) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [selRole, setSelRole] = useState('all')
  const [saving, setSaving] = useState<string | null>(null)
  const [filtro, setFiltro] = useState('')

  const { data, isLoading, refetch } = usePermisos()
  const matrix: PermMatrix = data?.matrix || {}
  const acciones = data?.actions || ACTIONS
  const modulos = (data?.modules || Object.keys(Object.values(matrix)[0] || {}))
    .map(moduleInfo(t))
    .filter(m => !filtro || `${m.id} ${m.label}`.toLowerCase().includes(filtro.toLowerCase()))
  // Las columnas son los roles que la matriz gobierna (los de la API); el
  // nombre y el color salen de los roles configurados si existen.
  const rolesDeLaMatriz: Role[] = (data?.roles || roles.map(r => r.id)).map(id =>
    roles.find(r => r.id === id) || rolesDeReserva(t).find(r => r.id === id) || { id, label: id, color: 'var(--text-2)' })

  const { mutate: resetMatrix, isPending: resetting } = useMutation({
    mutationFn: () => grcApi.seedPermissions(),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['grc-permissions'] }); toast.success(t('grc.matrix_reset_success')) },
    onError: e => toast.error(extractErr(e, t('grc.error'))),
  })

  const togglePerm = async (role: string, module: string, action: string, current: boolean) => {
    const key = `${role}/${module}/${action}`
    setSaving(key)
    try {
      await grcApi.updatePermission(role, module, action, { allowed: !current })
      qc.invalidateQueries({ queryKey: ['grc-permissions'] })
    } catch (e) {
      toast.error(extractErr(e, t('grc.error_save_permission')))
    } finally {
      setSaving(null)
    }
  }

  const displayRoles = selRole === 'all' ? rolesDeLaMatriz : rolesDeLaMatriz.filter((r: Role) => r.id === selRole)

  if (isLoading) return <Spinner />

  return (
    <div>
      <div className="grc-row">
        <div className="grc-row-2">
          <span className="grc-label">{t('grc.role')}:</span>
          <Button size="sm" variant={selRole === 'all' ? 'primary' : 'secondary'} onClick={() => setSelRole('all')}>
            {t('grc.all')}
          </Button>
          {rolesDeLaMatriz.map(r => (
            <Button key={r.id} size="sm" variant={selRole === r.id ? 'primary' : 'secondary'} onClick={() => setSelRole(r.id)}>
              {r.label}
            </Button>
          ))}
        </div>
        <div className="u-row-8">
          <input value={filtro} onChange={e => setFiltro(e.target.value)} placeholder={t('pagina_grc.filtrar_modulos')}
            aria-label={t('pagina_grc.filtrar_modulos_2')} className="grc-page-e3" />
          <Button size="sm" variant="secondary" icon={<RefreshCw size={14} />} onClick={() => refetch()}>{t('grc.refresh')}</Button>
          <Button size="sm" variant="secondary" icon={<RotateCcw size={14} />} loading={resetting}
            onClick={() => { openConfirmGlobal({ message: t('grc.reset_confirm'), onConfirm: () => resetMatrix(), danger: true }) }}>
            {resetting ? t('grc.resetting') : t('grc.reset_to_default')}
          </Button>
        </div>
      </div>

      <div className="u-scroll-x">
        <TablaSimple claseTabla="grc-table">
          <thead>
            <tr className="grc-row-3">
              <th className="grc-th">{t('grc.module')}</th>
              {displayRoles.map(r => (
                <th key={r.id} colSpan={acciones.length}
                  className="grc-th-2 grc-page-e4" style={{ '--grc-page-color': r.color } as CSSProperties}>
                  {r.label}
                </th>
              ))}
            </tr>
            <tr className="u-border-b">
              <th aria-hidden="true" className="grc-th-3" />
              {displayRoles.map(r => acciones.map(a => (
                <th key={r.id + a} className="grc-th-4">
                  {t(`grc.action_${a}`)}
                </th>
              )))}
            </tr>
          </thead>
          <tbody>
            {modulos.map((mod, mIdx) => (
              <tr key={mod.id} className={`u-border-b ${mIdx % 2 === 0 ? 'grcpage-sx4' : 'grcpage-sx5'}`}>
                <td className={`grc-td ${mIdx % 2 === 0 ? 'grcpage-sx4' : 'grcpage-sx5'}`}>
                  {mod.label}
                </td>
                {displayRoles.map(role =>
                  acciones.map(action => {
                    const celda = matrix[role.id]?.[mod.id]?.[action];
                    const key = `${role.id}/${mod.id}/${action}`;
                    const isSaving = saving === key;
                    // Sin casilla: el módulo no tiene esa operación (nada que gobernar).
                    if (celda === undefined) return <td key={key} className="grc-td-2">—</td>;
                    const allowed = celda;
                    return (
                      <td
                        key={key}
                        className="grc-td-3"
                        onClick={() => togglePerm(role.id, mod.id, action, allowed)}
                        title={`${role.label} · ${mod.label} · ${t(`grc.action_${action}`)}: ${allowed ? t('grc.allowed') : t('grc.denied')} — ${t('grc.click_to_change')}`}
                      >
                        <span className={`grc-label-2 ${isSaving ? 'grcpage-sx6' : 'grcpage-sx7'}`}>
                          {isSaving ? <Loader2 size={14} className="grc-girando" aria-hidden />
                            : allowed ? <Check size={15} className="grc-permitido" aria-label={t('grc.allowed')} />
                            : <X size={15} className="grc-denegado" aria-label={t('grc.denied')} />}
                        </span>
                      </td>
                    );
                  })
                )}
              </tr>
            ))}
          </tbody>
        </TablaSimple>
      </div>

      <div className="grc-row-4">
        <div className="grc-row-5"><Check size={14} className="grc-permitido" aria-hidden /><span>{t('grc.allowed')}</span></div>
        <div className="grc-row-5"><X size={14} className="grc-denegado" aria-hidden /><span>{t('grc.denied')}</span></div>
        <span className="grc-label-4">{t('grc.changes_auto_saved')}</span>
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// 2. SEGREGACIÓN SoD (wired to API + CRUD)
// ═══════════════════════════════════════════════════════════════════════════════
type Workflow = {
  [k: string]: unknown
  id: string
  name?: string
  entity_type?: string
  is_active?: boolean
  steps?: { id: string; name?: string; approver_role?: string; approver_user_name?: string }[]
}

function SodRuleModal({ rule, workflows, onClose, roles }: { rule: SodRule | null; workflows: Workflow[]; onClose: () => void; roles: Role[] }) {
  const idCampo = useId()
  const traducir = useAppT()
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const isEdit = !!rule
  const { data: permisos } = usePermisos()
  const MODULES = (permisos?.modules || Object.keys(MODULE_LABELS)).map(moduleInfo(t))
  const acciones = permisos?.actions || ACTIONS
  // Revisión GRC 16-11-2026: sólo los roles que gobierna la matriz (la API rechaza otros con 422).
  const rolesDeLaMatriz: Role[] = (permisos?.roles || roles.map(r => r.id)).map(id =>
    roles.find(r => r.id === id) || rolesDeReserva(t).find(r => r.id === id) || { id, label: id, color: 'var(--text-2)' })
  const [form, setForm] = useState<{
    module_a: string; action_a: string; module_b: string; action_b: string;
    risk: string; description: string; roles_conflict: string[]; mitigated_by_workflow_id: string | null;
  }>({
    module_a: rule?.module_a || 'invoices',
    action_a: rule?.action_a || 'crear',
    module_b: rule?.module_b || 'invoices',
    action_b: rule?.action_b || 'aprobar',
    risk: rule?.risk || 'high',
    description: rule?.description || '',
    roles_conflict: rule?.roles_conflict || [],
    mitigated_by_workflow_id: rule?.mitigated_by_workflow_id || '',
  })

  const camposB = useErroresDeCampo()
  const msgB = (k: string) => camposB.de(k) ? <div className="u-field-error">{camposB.de(k)}</div> : null
  const { mutate, isPending } = useMutation({
    onMutate: () => camposB.limpiar(),
    mutationFn: (d: typeof form) => isEdit ? grcApi.updateSodRule(rule!.id, d) : grcApi.createSodRule(d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['grc-sod-rules'] }); qc.invalidateQueries({ queryKey: ['grc-sod-check'] }); onClose() },
    onError: (e: unknown) => { if (!camposB.recoger(e)) toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) },
  })

  const toggleRole = (r: string) => setForm(f => ({
    ...f,
    roles_conflict: f.roles_conflict.includes(r) ? f.roles_conflict.filter((x: string) => x !== r) : [...f.roles_conflict, r],
  }))

  return (
    <Modal open title={isEdit ? t('grc.edit_sod_rule') : t('grc.new_sod_rule')} onClose={onClose} width={580}>
      <div className="u-stack-14">
        <div className="grc-card">
          {t('grc.sod_rule_desc1')} <strong className="u-text1">{t('grc.sod_rule_desc2')}</strong>. {t('grc.sod_rule_desc3')}
        </div>

        <div className="grc-grid">
          <div>
            <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="grc-page-e18">{t('grc.module_a')}</label>
            <Select suelto placeholder={false} id={`${idCampo}-1`} value={form.module_a} onChange={e => { camposB.limpiar('module_a'); setForm(f => ({ ...f, module_a: e.target.value })) }} className="grc-page-e19">
              {MODULES.map(m => <option key={m.id} value={m.id}>{m.label}</option>)}
            </Select>{msgB('module_a')}
          </div>
          <div>
            <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="grc-page-e18">{t('grc.action_a')}</label>
            <Select suelto placeholder={false} id={`${idCampo}-2`} value={form.action_a} onChange={e => { camposB.limpiar('action_a'); setForm(f => ({ ...f, action_a: e.target.value })) }} className="grc-page-e19">
              {acciones.map(a => <option key={a} value={a}>{accionDe(t)(a)}</option>)}
            </Select>{msgB('action_a')}
          </div>
        </div>
        <div className="grc-box">{traducir('grc.en_conflicto_con')}</div>
        <div className="grc-grid-2">
          <div>
            <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="grc-page-e18">{t('grc.module_b')}</label>
            <Select suelto placeholder={false} id={`${idCampo}-3`} value={form.module_b} onChange={e => { camposB.limpiar('module_b'); setForm(f => ({ ...f, module_b: e.target.value })) }} className="grc-page-e19">
              {MODULES.map(m => <option key={m.id} value={m.id}>{m.label}</option>)}
            </Select>{msgB('module_b')}
          </div>
          <div>
            <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="grc-page-e18">{t('grc.action_b')}</label>
            <Select suelto placeholder={false} id={`${idCampo}-4`} value={form.action_b} onChange={e => { camposB.limpiar('action_b'); setForm(f => ({ ...f, action_b: e.target.value })) }} className="grc-page-e19">
              {acciones.map(a => <option key={a} value={a}>{accionDe(t)(a)}</option>)}
            </Select>{msgB('action_b')}
          </div>
        </div>

        <div className="u-grid2-10">
          <div>
            <label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} className="grc-page-e18">{t('grc.risk_level')}</label>
            <Select suelto placeholder={false} id={`${idCampo}-5`} value={form.risk} onChange={e => { camposB.limpiar('risk'); setForm(f => ({ ...f, risk: e.target.value })) }} className="grc-page-e19">
              {RIESGOS.map(r => <option key={r} value={r}>{t(`grc.riesgo_${r}`)}</option>)}
            </Select>{msgB('risk')}
          </div>
          <div>
            <label id={`${idCampo}-et6`} htmlFor={`${idCampo}-6`} className="grc-page-e18">{t('grc.mitigation_flow')}</label>
            <Select suelto placeholder={false} id={`${idCampo}-6`} value={form.mitigated_by_workflow_id || ''} onChange={e => { camposB.limpiar('mitigated_by_workflow_id'); setForm(f => ({ ...f, mitigated_by_workflow_id: e.target.value })) }} className="grc-page-e19">
              <option value="">{t('grc.no_mitigation')}</option>
              {(workflows || []).map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
            </Select>{msgB('mitigated_by_workflow_id')}
          </div>
        </div>

        <div>
          <label className="grc-page-e18">{t('grc.risk_description')}</label>
          <Input value={form.description} onChange={e => { camposB.limpiar('description'); setForm(f => ({ ...f, description: e.target.value })) }} placeholder={traducir('grc.descripcion_de_la_regla_sod')} aria-label={traducir('grc.descripcion_de_la_regla_sod')} inputClassName="grc-page-e19" />{msgB('description')}
        </div>

        <div>
          <label className="grc-page-e18">{t('grc.conflicting_roles')}</label>
          <div className="grc-row-6">
            {rolesDeLaMatriz.map(r => (
              <Button key={r.id} size="sm" variant={form.roles_conflict.includes(r.id) ? 'primary' : 'secondary'}
                icon={form.roles_conflict.includes(r.id) ? <Check size={13} /> : undefined} onClick={() => toggleRole(r.id)}>
                {r.label}
              </Button>
            ))}
          </div>
        </div>

        <div className="u-actions-10">
          <Button variant="secondary" onClick={onClose}>{t('grc.cancel')}</Button>
          <Button onClick={() => mutate({ ...form, mitigated_by_workflow_id: form.mitigated_by_workflow_id || null })} loading={isPending} disabled={isPending || !form.description}>
            {isPending ? t('grc.saving') : isEdit ? t('grc.save_changes') : t('grc.create_rule')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

function SodTab({ roles }: { roles: Role[] }) {
  const traducir = useAppT()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [showModal, setShowModal] = useState(false)
  const [editingRule, setEditingRule] = useState<SodRule | null>(null)

  const { data: rules = [], isLoading } = useQuery<SodRule[]>({
    queryKey: ['grc-sod-rules'],
    queryFn: () => grcApi.sodRules().then(r => r.data),
  })
  const { data: checkData } = useQuery<{ violations: SodViolation[]; not_evaluable_rule_ids?: string[] }>({
    queryKey: ['grc-sod-check'],
    queryFn: () => grcApi.sodCheck().then(r => r.data),
    staleTime: STALE_SHORT_MS,
  })
  const { data: workflows = [] } = useQuery<Workflow[]>({
    queryKey: ['approval-workflows-grc'],
    queryFn: () => approvalsApi.listWorkflows(undefined).then(r => r.data),
  })

  const { mutate: del } = useMutation({
    mutationFn: (id: string) => grcApi.deleteSodRule(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['grc-sod-rules'] }); qc.invalidateQueries({ queryKey: ['grc-sod-check'] }) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const { mutate: toggle } = useMutation({
    mutationFn: ({ id, active }: { id: string; active: boolean }) => grcApi.updateSodRule(id, { is_active: active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['grc-sod-rules'] }),
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  const violations = checkData?.violations || []
  const criticalCount = violations.filter((v: SodViolation) => v.risk === 'critical').length

  return (
    <div>
      <div className="ds-grid-stats grc-mb">
        <KpiCard icon={<ShieldCheck size={14} />} label={t('grc.active_sod_rules')} value={rules.filter((r: SodRule) => r.is_active).length} />
        <KpiCard icon={<Search size={14} />} label={t('grc.detected_conflicts')} value={violations.length} warning={violations.length > 0} />
        <KpiCard icon={<ShieldAlert size={14} />} label={t('grc.critical_conflicts')} value={criticalCount} danger={criticalCount > 0} />
      </div>

      {violations.length > 0 && (
        <div className="grc-card-2">
          <div className="grc-box-5"><AlertOctagon size={15} aria-hidden /> {t('grc.sod_conflicts_detected')}</div>
          <div className="u-stack-6">
            {violations.map((v: SodViolation, i: number) => (
              <div key={i} className="grc-row-7">
                <span className="grc-label-5 grc-page-e6" style={{ '--grc-page-background': alpha(RISK_COLOR[v.risk || ''], '20'), '--grc-page-color': RISK_COLOR[v.risk || ''] } as CSSProperties}>{t(`grc.riesgo_${v.risk}`)}</span>
                <span className="u-text1"><strong>{roles.find(r => r.id === v.conflicting_role)?.label || v.conflicting_role}</strong> {t('grc.can')} {accionDe(t)(v.action_a)} <em>{moduleInfo(t)(v.module_a).label}</em> {t('grc.and')} {accionDe(t)(v.action_b)} <em>{moduleInfo(t)(v.module_b).label}</em></span>
                {v.mitigated && <StatusBadge kind="success" caps={false}>{t('grc.mitigated')}</StatusBadge>}
              </div>
            ))}
          </div>
        </div>
      )}

      {(checkData?.not_evaluable_rule_ids?.length ?? 0) > 0 && (
        <div className="u-text3-sm">{t('grc.sod_no_evaluables', { n: checkData?.not_evaluable_rule_ids?.length ?? 0 })}</div>
      )}

      <div className="grc-row-8">
        <Button icon={<Plus size={14} />} onClick={() => setShowModal(true)}>{t('grc.new_sod_rule')}</Button>
      </div>

      {isLoading ? <Spinner /> : rules.length === 0 ? (
        <EmptyState icon={<ShieldCheck size={28} />} title={traducir('grc.sin_reglas_sod')} description={t('pagina_grc.crea_reglas_para_detectar_conflictos_de')}
          action={<Button icon={<Plus size={14} />} onClick={() => setShowModal(true)}>{t('grc.new_sod_rule')}</Button>} />
      ) : (
        <div className="u-stack-10">
          {rules.map((rule: SodRule) => {
            const rc = RISK_COLOR[rule.risk || ''] || 'var(--text-3)'
            const modA = moduleInfo(t)(rule.module_a)
            const modB = moduleInfo(t)(rule.module_b)
            return (
              <div key={rule.id} className={`grc-page-e7 ${rule.is_active ? 'grc-page-m8' : 'grc-page-m9'}`} style={{ '--grc-page-border-left': `4px solid ${rc}` } as CSSProperties}>
                <div className="grc-row-9">
                  <div className="u-wrap-center-8">
                    <span className="grc-label-6 grc-page-e6" style={{ '--grc-page-background': alpha(rc, '20'), '--grc-page-color': rc } as CSSProperties}>{t(`grc.riesgo_${rule.risk}`)}</span>
                    <span className="u-text1-base-600">{modA?.label} · {accionDe(t)(rule.action_a)}</span>
                    <span className="u-text3-sm">{traducir('grc.conflicto_con')}</span>
                    <span className="u-text1-base-600">{modB?.label} · {accionDe(t)(rule.action_b)}</span>
                    {rule.mitigated_by_workflow_id && <span className="grc-card-4">{t('pagina_grc.mitigado')}</span>}
                    {!rule.is_active && <span className="grc-card-5">{t('pagina_grc.inactiva')}</span>}
                    {checkData?.not_evaluable_rule_ids?.includes(rule.id) && <span className="grc-card-5">{t('grc.sod_no_evaluable')}</span>}
                  </div>
                  <div className="u-row-6">
                    <IconButton onClick={() => toggle({ id: rule.id, active: !rule.is_active })}
                      ariaLabel={rule.is_active ? t('pagina_grc.desactivar_regla_sod') : t('pagina_grc.activar_regla_sod')}>
                      {rule.is_active ? <Pause size={14} /> : <Play size={14} />}
                    </IconButton>
                    <IconButton onClick={() => setEditingRule(rule)} ariaLabel={t('pagina_grc.editar_regla_sod')}>
                      <Pencil size={14} />
                    </IconButton>
                    <IconButton onClick={() => { openConfirmGlobal({ message: t('pagina_grc.eliminar_esta_regla_sod'), onConfirm: () => del(rule.id), danger: true }) }}
                      ariaLabel={t('pagina_grc.eliminar_regla_sod')} className="grc-borrar">
                      <Trash2 size={14} />
                    </IconButton>
                  </div>
                </div>
                <div className={`u-text2-sm ${(rule.roles_conflict?.length ?? 0) > 0 ? 'grcpage-sx8' : 'grcpage-sx9'}`}>{rule.description}</div>
                {(rule.roles_conflict?.length ?? 0) > 0 && (
                  <div className="grc-row-10">
                    <span className="u-text3-xs">{traducir('grc.roles_con_conflicto')}</span>
                    {rule.roles_conflict?.map((r: string) => {
                      const role = roles.find((x: Role) => x.id === r)
                      return role ? <span key={r} className="grc-label-7 grc-page-e6" style={{ '--grc-page-background': alpha(role.color, '20'), '--grc-page-color': role.color } as CSSProperties}>{role.label}</span> : <span key={r} className="grc-card-6">{r}</span>
                    })}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {(showModal || editingRule) && (
        <SodRuleModal rule={editingRule} workflows={workflows} roles={roles} onClose={() => { setShowModal(false); setEditingRule(null) }} />
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// 3. VIOLACIONES SoD
// ═══════════════════════════════════════════════════════════════════════════════
function ViolationsTab({ roles }: { roles: Role[] }) {
  const { t } = useAppLang()
  const traducir = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [filter, setFilter] = useState<boolean | null>(false)

  const { data: violations = [], isLoading, refetch } = useQuery<ViolationRecord[]>({
    queryKey: ['grc-violations', filter],
    queryFn: () => grcApi.violations(filter === null ? {} : { resolved: filter }).then(r => r.data),
    refetchInterval: POLL_DEFAULT_MS,
  })

  const { mutate: resolve } = useMutation({
    mutationFn: ({ id, note }: { id: string; note: string }) => grcApi.resolveViolation(id, { resolution_note: note }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['grc-violations'] }); toast.success(t('pagina_grc.violacion_marcada_como_resuelta')) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  return (
    <div>
      <div className="grc-card-7">
        <strong className="u-danger">{t('pagina_grc.violaciones_sod_en_tiempo_real')}</strong> {traducir('grc.registradas_cuando_el_mismo_usuario_intenta_realizar')}
      </div>

      <div className="grc-row-11">
        {([[false, t('pagina_grc.pendientes')], [null, t('pagina_grc.todas')], [true, t('pagina_grc.resueltas')]] as [boolean | null, string][]).map(([val, label]) => (
          <Button key={String(val)} size="sm" variant={filter === val ? 'primary' : 'secondary'} onClick={() => setFilter(val)}>
            {label}
          </Button>
        ))}
        <IconButton onClick={() => refetch()} ariaLabel={t('pagina_grc.refrescar_violaciones_sod')}><RefreshCw size={14} /></IconButton>
      </div>

      {isLoading ? <Spinner /> : violations.length === 0 ? (
        <EmptyState icon={filter === false ? <CheckCircle2 size={28} /> : <Search size={28} />} title={filter === false ? t('pagina_grc.sin_violaciones_pendientes') : t('pagina_grc.sin_violaciones_registradas')} description={filter === false ? t('pagina_grc.no_hay_violaciones_sod_pendientes_de') : t('pagina_grc.no_hay_violaciones_registradas')} />
      ) : (
        <div className="u-stack-10">
          {violations.map(v => (
            <div key={v.id} className="grc-page-e10" style={{ '--grc-page-border-left': `3px solid ${v.resolved ? 'var(--success)' : 'var(--danger)'}` } as CSSProperties}>
              <div className="grc-row-12">
                <div>
                  <div className="grc-row-13">
                    <span className={`u-sm-700 ${v.resolved ? 'grcpage-sx10' : 'grcpage-sx11'}`}>{v.resolved ? t('pagina_grc.resuelta') : t('pagina_grc.pendiente')}</span>
                    {v.role && <span className="grc-card-8">{roles.find(r => r.id === v.role)?.label || v.role}</span>}
                  </div>
                  <div className="grc-box-6">
                    {t('pagina_grc.usuario')}{' '}<strong>{v.user_name || v.user_id || '—'}</strong>{' '}{t('pagina_grc.contexto')}{' '}{v.context_type === 'approval_request' ? t('pagina_grc.aprobaciones') : moduleInfo(traducir)(v.context_type || '').label} ({v.context_id})
                  </div>
                  <div className="u-text3-xs-mt2">{t('pagina_grc.detectada')}{' '}{fmtDateTime(v.detected_at)}</div>
                  {v.resolution_note && <div className="grc-box-7">{traducir('grc.resolucion')} {v.resolution_note}</div>}
                </div>
                {!v.resolved && (
                  <Button size="sm" variant="secondary" icon={<Check size={14} />} onClick={async () => {
                    const note = await pedirTexto({ title: t('pagina_grc.resolver_violacion'), message: t('pagina_grc.puedes_anadir_una_nota_de_resolucion'), label: t('pagina_grc.nota_de_resolucion_opcional'), multiline: true, confirmLabel: t('pagina_grc.resolver') })
                    if (note === null) return
                    resolve({ id: v.id, note })
                  }}>
                    {t('pagina_grc.resolver_2')}
                  </Button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════════
// 4. AUDIT LOG GRC
// ═══════════════════════════════════════════════════════════════════════════════
function AuditLogTab() {
  const { t } = useAppLang()
  const traducir = useAppT()
  const [severity, setSeverity] = useState('')

  const { data: log = [], isLoading, refetch } = useQuery<AuditEvent[]>({
    queryKey: ['grc-audit-log', severity],
    queryFn: () => grcApi.auditLog(severity ? { severity } : {}).then(r => r.data),
  })

  const ACTION_ICONS: Record<string, JSX.Element> = {
    permission_changed: <KeyRound size={14} />, permission_matrix_reset: <RotateCcw size={14} />,
    sod_rule_created: <AlertTriangle size={14} />, sod_rule_updated: <Pencil size={14} />, sod_rule_deleted: <Trash2 size={14} />,
    sod_violation_detected: <ShieldAlert size={14} />, sod_violation_resolved: <CheckCircle2 size={14} />, approval_override: <Zap size={14} />,
  }

  return (
    <div>
      <div className="grc-card-9">
        <strong className="u-text1">{t('pagina_grc.audit_log_inmutable_grc')}</strong> {traducir('grc.todos_los_eventos_de_seguridad_cambios_de')}
      </div>

      <div className="grc-row-14">
        <span className="u-text2-sm">{t('pagina_grc.severidad')}</span>
        {[['', t('pagina_grc.todas')], ['info', t('pagina_grc.info')], ['warning', t('pagina_grc.aviso')], ['critical', t('pagina_grc.critico')]].map(([val, label]) => (
          <Button key={val} size="sm" variant={severity === val ? 'primary' : 'secondary'} onClick={() => setSeverity(val)}>
            {label}
          </Button>
        ))}
        <IconButton onClick={() => refetch()} ariaLabel={t('pagina_grc.refrescar_audit_log')}><RefreshCw size={14} /></IconButton>
      </div>

      {isLoading ? <Spinner /> : log.length === 0 ? (
        <EmptyState icon={<ScrollText size={28} />} title={traducir('grc.sin_eventos_de_auditoria')} description={t('pagina_grc.los_eventos_de_seguridad_apareceran_aqui')} />
      ) : (
        <div className="grc-stack">
          {log.map((e: AuditEvent) => {
            const sc = SEV_COLOR[e.severity || ''] || 'var(--text-2)'
            return (
              <div key={e.id} className="grc-page-e11" style={{ '--grc-page-border-left': `3px solid ${sc}` } as CSSProperties}>
                <div className="grc-row-15">
                  <div className="u-row-center-8">
                    <span className="grc-label-3" aria-hidden>{ACTION_ICONS[e.action_type || ''] || <ClipboardList size={14} />}</span>
                    <span className="u-text1-sm-600">{t(`grc.evento_${e.action_type}`)}</span>
                    {e.resource_type && <span className="grc-card-10">{e.resource_type}</span>}
                    <span className="grc-label-8 grc-page-e12" style={{ '--grc-page-color': sc, '--grc-page-background': alpha(sc, '15') } as CSSProperties}>{t(`grc.severidad_${e.severity}`)}</span>
                  </div>
                  <span className="grc-label-9">{fmtDateTime(e.timestamp)}</span>
                </div>
                <div className="u-text2-xs">
                  {e.user_name && <span>{t('pagina_grc.actor')}{' '}<strong>{e.user_name}</strong>{e.ip_address ? t('pagina_grc.ip', { ip_address: e.ip_address }) : ''}</span>}
                  {e.detail && typeof e.detail === 'object' && (
                    <span className="ds-codigo grc-label-10">
                      {JSON.stringify(e.detail).slice(0, 120)}
                    </span>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

function ApprovalsTab() {
  const { t } = useAppLang()
  const traducir = useAppT()
  const { data: workflows = [], isLoading } = useQuery<Workflow[]>({
    queryKey: ['approval-workflows-grc'],
    queryFn: () => approvalsApi.listWorkflows(undefined).then(r => r.data),
  })

  return (
    <div>
      <div className="grc-card-11">
        {traducir('grc.los')} <strong className="u-text1">{traducir('grc.flujos_de_aprobacion')}</strong> {traducir('grc.mitigan_los_riesgos_sod_anadiendo_revision_obligatoria')}{' '}
        <a href="/approvals" className="u-accent">{t('pagina_grc.aprobaciones')}</a>.
      </div>

      {isLoading ? <Spinner /> : workflows.length === 0 ? (
        <EmptyState icon={<GitPullRequestArrow size={28} />} title={traducir('grc.sin_flujos_de_aprobacion')}
          description={t('pagina_grc.configura_flujos_de_aprobacion_para_mitigar')} />
      ) : (
        <div className="u-stack-10">
          {workflows.map(wf => (
            <div key={wf.id} className="grc-card-12">
              <div className="grc-row-16">
                <div>
                  <span className="grc-label-11">
                    {wf.name}
                  </span>
                  <span className="grc-card-13">{wf.entity_type?.replace(/_/g,' ')}</span>
                </div>
                <span className={`grc-label-12 ${wf.is_active ? 'grcpage-sx10' : 'grcpage-sx12'}`}>
                  {wf.is_active ? t('pagina_grc.activo') : t('pagina_grc.inactivo')}
                </span>
              </div>
              <div className="u-wrap-6">
                {(wf.steps || []).map((step, i) => (
                  <div key={step.id} className="grc-row-17">
                    {i > 0 && <span className="grc-label-13">→</span>}
                    <span className="grc-card-14">
                      {step.name || step.approver_role || step.approver_user_name || t('pagina_grc.paso') + (i+1)}
                    </span>
                  </div>
                ))}
                {(!wf.steps || wf.steps.length === 0) && (
                  <span className="u-text3-sm">{traducir('grc.sin_pasos_configurados')}</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

const COLOR_VEREDICTO: Record<string, string> = { allow: 'var(--success)', deny: 'var(--danger)', unknown: 'var(--warning)', not_applicable: 'var(--text-3)' }

const COLOR_CONTROL: Record<string, string> = { pass: 'var(--success)', attention: 'var(--danger)', info: 'var(--accent)', not_measurable: 'var(--text-3)' }

/** Retención por tipo de registro y bloqueo legal (revisión 2026-11). */
function RetencionTab() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { data } = useQuery<{ policies: PoliticaDeRetencion[]; min_days: number }>({
    // Revisión GRC 16-11-2026: ['retention'] y ['legal-holds'] eran también las claves del
    // chat (ChatAdminPage, otra forma de datos): la caché de una pantalla rompía la otra.
    queryKey: ['grc-retention'], queryFn: () => governanceApi.retentionPolicies().then(r => r.data),
  })
  const { data: bloqueos = [] } = useQuery<Bloqueo[]>({ queryKey: ['grc-legal-holds'], queryFn: () => governanceApi.legalHolds().then(r => r.data) })
  const [dias, setDias] = useState<Record<string, string>>({})
  const [previas, setPrevias] = useState<Record<string, VistaPreviaDeRetencion>>({})
  const [nuevo, setNuevo] = useState({ case_reference: '', reason: '', entity: '*', field: 'client_id', value: '' })
  const error = (e: unknown) => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK))
  const refrescar = () => { qc.invalidateQueries({ queryKey: ['grc-retention'] }); qc.invalidateQueries({ queryKey: ['grc-legal-holds'] }) }
  const diasDe = (p: PoliticaDeRetencion) => Number(dias[p.entity] ?? p.keep_days ?? 365)
  const previa = async (p: PoliticaDeRetencion) => {
    try { const r = await governanceApi.retentionPreview(p.entity, diasDe(p)); setPrevias(v => ({ ...v, [p.entity]: r.data })) } catch (e) { error(e) }
  }
  const guardar = async (p: PoliticaDeRetencion, activa: boolean) => {
    try { await governanceApi.saveRetention(p.entity, { keep_days: diasDe(p), is_active: activa }); toast.success(t('grc.retencion_guardada')); refrescar() } catch (e) { error(e) }
  }
  const aplicar = async () => {
    if (!await confirmar({ message: t('grc.retencion_confirmar_aplicar'), danger: true })) return
    try {
      const r = await governanceApi.retentionRun()
      const total = Object.values(r.data).reduce((a, x) => a + x.deleted, 0)
      toast.success(t('grc.retencion_aplicada', { n: total })); refrescar()
    } catch (e) { error(e) }
  }
  const crear = async () => {
    try { await governanceApi.createLegalHold(nuevo); setNuevo({ ...nuevo, case_reference: '', reason: '', value: '' }); refrescar() } catch (e) { error(e) }
  }
  const camposDe = (entidad: string) => Array.from(new Set((data?.policies || []).filter(p => entidad === '*' || p.entity === entidad).flatMap(p => p.hold_fields)))
  const campos = camposDe(nuevo.entity)
  // Revisión GRC 16-11-2026: al cambiar de tipo, el campo elegido podía no existir en él
  // (el desplegable mostraba otro y la API devolvía 422).
  const cambiarTipo = (entidad: string) => {
    const validos = camposDe(entidad)
    setNuevo(n => ({ ...n, entity: entidad, field: validos.includes(n.field) ? n.field : (validos[0] || '') }))
  }
  const levantar = (id: string) => openConfirmGlobal({ message: t('grc.bloqueo_confirmar_levantar'), danger: true,
    onConfirm: async () => { try { await governanceApi.releaseLegalHold(id); refrescar() } catch (e) { error(e) } } })

    if (!data) return <Spinner />
  return (
    <div className="grc-grid-4">
      <section>
        <div className="grc-row-18">
          <h3 className="grc-title">{t('grc.retencion_titulo')}</h3>
          <Button size="sm" variant="secondary" onClick={aplicar}>{t('grc.retencion_aplicar_ya')}</Button>
        </div>
        <p className="grc-text">{t('grc.retencion_intro', { min: data.min_days })}</p>
        <TablaSimple claseTabla="u-table-sm">
          <thead><tr><th className="grc-page-e20">{t('grc.retencion_tipo')}</th><th className="grc-page-e20">{t('grc.retencion_dias')}</th><th className="grc-page-e20">{t('grc.retencion_previa')}</th><th className="grc-page-e20">{t('grc.retencion_estado')}</th><th className="grc-page-e20"><span className="u-sr-only">{t('pagina_grc.acciones')}</span></th></tr></thead>
          <tbody>
            {data.policies.map(p => {
              const v = previas[p.entity]
              return (
                <tr key={p.entity} className="grc-row-19">
                  <td className="grc-td-4">{t(`grc.retencion_tipo_${p.entity}`)}</td>
                  <td className="grc-td-5">
                    <Input type="number" min={data.min_days} aria-label={t('grc.retencion_dias')} value={dias[p.entity] ?? p.keep_days ?? ''} placeholder="365" onChange={e => setDias(d => ({ ...d, [p.entity]: e.target.value }))} inputClassName="grc-page-e14" />
                  </td>
                  <td className="grc-td-6">
                    {v ? t('grc.retencion_previa_resultado', { borraria: v.would_delete, retenidos: v.held, vencidos: v.expired })
                      : <Button size="sm" variant="ghost" onClick={() => previa(p)}>{t('grc.retencion_ver_previa')}</Button>}
                  </td>
                  <td className={`grc-td-5 ${p.is_active ? 'grcpage-sx10' : 'grcpage-sx13'}`}>
                    {p.is_active ? t('grc.retencion_activa') : t('grc.retencion_apagada')}
                    {p.last_run_at && <div className="u-text3-xs">{t('grc.retencion_ultima', { n: p.last_deleted ?? 0, fecha: fmtDateTime(p.last_run_at) })}</div>}
                  </td>
                  <td className="grc-td-7">
                    <Button size="sm" variant={p.is_active ? 'secondary' : 'primary'} onClick={() => guardar(p, !p.is_active)}>
                      {p.is_active ? t('grc.retencion_apagar') : t('grc.retencion_activar')}
                    </Button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </TablaSimple>
      </section>
      <section>
        <h3 className="grc-title-2">{t('grc.bloqueo_titulo')}</h3>
        <p className="grc-text">{t('grc.bloqueo_intro')}</p>
        <div className="grc-row-20">
          <input aria-label={t('grc.bloqueo_caso')} placeholder={t('grc.bloqueo_caso')} value={nuevo.case_reference} onChange={e => setNuevo({ ...nuevo, case_reference: e.target.value })} className="grc-page-e21" />
          <Select suelto placeholder={false} aria-label={t('grc.retencion_tipo')} value={nuevo.entity} onChange={e => cambiarTipo(e.target.value)} className="grc-page-e21">
            <option value="*">{t('grc.bloqueo_todos')}</option>
            {data.policies.map(p => <option key={p.entity} value={p.entity}>{t(`grc.retencion_tipo_${p.entity}`)}</option>)}
          </Select>
          <Select suelto placeholder={false} aria-label={t('grc.bloqueo_campo')} value={nuevo.field} onChange={e => setNuevo({ ...nuevo, field: e.target.value })} className="grc-page-e21">
            {campos.map(c => <option key={c} value={c}>{t(`grc.bloqueo_campo_${c}`)}</option>)}
          </Select>
          <input aria-label={t('grc.bloqueo_valor')} placeholder={t('grc.bloqueo_valor')} value={nuevo.value} onChange={e => setNuevo({ ...nuevo, value: e.target.value })} className="ds-codigo grc-page-e15" />
          <Button size="sm" onClick={crear} disabled={!nuevo.case_reference.trim() || !nuevo.value.trim()}>{t('grc.bloqueo_crear')}</Button>
        </div>
        {bloqueos.length === 0 ? <div className="u-text3-sm">{t('grc.bloqueo_ninguno')}</div> : (
          <TablaSimple claseTabla="u-table-sm">
            <tbody>
              {bloqueos.map(b => (
                <tr key={b.id} className={`grc-row-19 ${b.is_active ? 'grcpage-sx7' : 'grcpage-sx14'}`}>
                  <td className="grc-td-4">{b.case_reference}</td>
                  <td className="grc-td-5">{b.entity === '*' ? t('grc.bloqueo_todos') : t(`grc.retencion_tipo_${b.entity}`)}</td>
                  <td className="grc-td-8">{t(`grc.bloqueo_campo_${b.field}`)} = {b.value}</td>
                  <td className={`grc-td-5 ${b.is_active ? 'grcpage-sx15' : 'grcpage-sx13'}`}>{b.is_active ? t('grc.bloqueo_activo') : t('grc.bloqueo_levantado')}</td>
                  <td className="grc-td-9">
                    {b.is_active && <Button size="sm" variant="secondary" onClick={() => levantar(b.id)}>{t('grc.bloqueo_levantar')}</Button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </TablaSimple>
        )}
      </section>
    </div>
  )
}

/** Sufijo de la clave del título de un control (`marcos_de_cumplimiento.clave_de_texto`). */
const claveDeControl = (id: string) => id.replace(/[^A-Za-z0-9]/g, '_')

/**
 * Marcos (SOC 2, ISO 27001), estado de cada control y evidencias (revisión GRC 16-11-2026).
 * La API existía (`/governance/compliance/*`) y ninguna pantalla la usaba. El estado
 * cruza la evidencia subida con lo que mide el informe: un control medido en rojo
 * pide atención aunque tenga evidencias.
 */
function EvidenciasTab() {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { data: marcos } = useQuery<MarcosDeCumplimiento>({
    queryKey: ['grc-frameworks'], queryFn: () => governanceApi.frameworks().then(r => r.data),
  })
  const nombres = Object.keys(marcos?.frameworks || {})
  const [elegido, setElegido] = useState('')
  const marco = elegido || nombres[0] || ''
  const controles = marcos?.frameworks[marco] || []
  const { data: estado, isLoading: cargandoEstado } = useQuery<EstadoDeControlesDelMarco>({
    queryKey: ['grc-controls-status', marco], enabled: !!marco,
    queryFn: () => governanceApi.controlsStatus(marco).then(r => r.data),
  })
  const [page, setPage] = useState(1)
  const { data: pagina } = useQuery<{ items: EvidenciaDeCumplimiento[]; total: number }>({
    queryKey: ['grc-evidence', marco, page], enabled: !!marco,
    queryFn: () => governanceApi.evidence({ framework: marco, page, page_size: SMALL_PAGE_SIZE })
      .then((r: AxiosResponse<EvidenciaDeCumplimiento[]> & { meta?: { total?: number } }) =>
        ({ items: r.data, total: Number(r.meta?.total ?? r.data.length) })),
  })
  const paginas = Math.max(1, Math.ceil((pagina?.total ?? 0) / SMALL_PAGE_SIZE))
  const vacia = { control_id: '', evidence_type: 'policy', title: '', artifact_uri: '', artifact_sha256: '' }
  const [nueva, setNueva] = useState(vacia)
  const control = nueva.control_id || controles[0] || ''
  const shaValido = !nueva.artifact_sha256 || /^[0-9a-fA-F]{64}$/.test(nueva.artifact_sha256)

  const { mutate: registrar, isPending } = useMutation({
    mutationFn: () => governanceApi.createEvidence({
      framework: marco, control_id: control, evidence_type: nueva.evidence_type, title: nueva.title.trim(),
      artifact_uri: nueva.artifact_uri.trim() || undefined, artifact_sha256: nueva.artifact_sha256.trim() || undefined,
    }),
    onSuccess: () => {
      setNueva(vacia)
      qc.invalidateQueries({ queryKey: ['grc-controls-status'] })
      qc.invalidateQueries({ queryKey: ['grc-evidence'] })
      toast.success(t('grc.evidencias_registrada'))
    },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })
  const cambiarMarco = (m: string) => { setElegido(m); setPage(1); setNueva(vacia) }

  if (!marcos) return <Spinner />
  return (
    <div className="grc-grid-4">
      <p className="grc-text">{t('grc.evidencias_intro')}</p>
      <div className="grc-row-11">
        {nombres.map(m => (
          <Button key={m} size="sm" variant={marco === m ? 'primary' : 'secondary'} onClick={() => cambiarMarco(m)}>
            {m}
          </Button>
        ))}
      </div>

      <section>
        {cargandoEstado || !estado ? <Spinner /> : (
          <TablaSimple claseTabla="u-table-sm">
            <thead><tr className="grc-row-23">
              <th className="grc-th-5">{t('grc.informe_col_estado')}</th><th className="grc-th-5">{t('grc.evidencias_col_control')}</th>
              <th className="grc-th-5">{t('grc.evidencias_col_evidencias')}</th><th className="grc-th-5">{t('grc.evidencias_col_medido')}</th>
            </tr></thead>
            <tbody>
              {estado.controls.map(c => (
                <tr key={c.control_id} className="grc-row-24">
                  <td className="grc-td-10 grc-page-e4" style={{ '--grc-page-color': COLOR_CONTROL[c.status] } as CSSProperties}>{t(`grc.informe_estado_${c.status}`)}</td>
                  <td className="grc-td-5">
                    <div className="u-600">{t(`grc.marco_control_${claveDeControl(c.control_id)}`)}</div>
                    <div className="u-text3-xs">{c.control_id}</div>
                  </td>
                  <td className="grc-td-5">{c.evidence_count}</td>
                  <td className="grc-td-11">
                    {c.measured.length === 0 ? '—' : c.measured.map(m => (
                      <div key={m.id} className="grc-page-e4" style={{ '--grc-page-color': COLOR_CONTROL[m.status] } as CSSProperties}>
                        {t(`grc.informe_control_${m.id}`)}: {t(`grc.informe_estado_${m.status}`)}
                      </div>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </TablaSimple>
        )}
      </section>

      <section>
        <h3 className="grc-title-2">{t('grc.evidencias_registrar')}</h3>
        <div className="grc-row-20">
          <Select suelto placeholder={false} aria-label={t('grc.evidencias_control')} value={control} onChange={e => setNueva({ ...nueva, control_id: e.target.value })} className="grc-page-e21">
            {controles.map(c => <option key={c} value={c}>{c} — {t(`grc.marco_control_${claveDeControl(c)}`)}</option>)}
          </Select>
          <Select suelto placeholder={false} aria-label={t('grc.evidencias_tipo')} value={nueva.evidence_type} onChange={e => setNueva({ ...nueva, evidence_type: e.target.value })} className="grc-page-e21">
            {marcos.evidence_types.map(x => <option key={x} value={x}>{t(`grc.evidencia_tipo_${x}`)}</option>)}
          </Select>
          <input aria-label={t('grc.evidencias_titulo')} placeholder={t('grc.evidencias_titulo')} maxLength={255} value={nueva.title} onChange={e => setNueva({ ...nueva, title: e.target.value })} className="grc-page-e21" />
          <input aria-label={t('grc.evidencias_uri')} placeholder={t('grc.evidencias_uri')} maxLength={1000} value={nueva.artifact_uri} onChange={e => setNueva({ ...nueva, artifact_uri: e.target.value })} className="grc-page-e21" />
          <input aria-label={t('grc.evidencias_sha256')} placeholder={t('grc.evidencias_sha256')} maxLength={64} value={nueva.artifact_sha256} onChange={e => setNueva({ ...nueva, artifact_sha256: e.target.value })} className="ds-codigo grc-page-e15" aria-invalid={!shaValido} />
          <Button size="sm" onClick={() => registrar()} loading={isPending} disabled={isPending || !control || !nueva.title.trim() || !shaValido}>{t('grc.evidencias_registrar')}</Button>
        </div>
        {(pagina?.items.length ?? 0) === 0 ? <div className="u-text3-sm">{t('grc.evidencias_ninguna')}</div> : (
          <TablaSimple claseTabla="u-table-sm">
            <tbody>
              {pagina?.items.map(ev => (
                <tr key={ev.id} className="grc-row-19">
                  <td className="grc-td-5">{fmtDate(ev.created_at)}</td>
                  <td className="grc-td-5">{ev.control_id}</td>
                  <td className="grc-td-5">{t(`grc.evidencia_tipo_${ev.evidence_type}`)}</td>
                  <td className="grc-td-4">{ev.title}</td>
                  <td className="grc-td-8"><code className="ds-codigo">{ev.artifact_uri || '—'}{ev.artifact_hash ? ` · sha256 ${ev.artifact_hash.slice(0, 12)}…` : ''}</code></td>
                </tr>
              ))}
            </tbody>
          </TablaSimple>
        )}
        {paginas > 1 && <Pagination page={page} totalPages={paginas} onChange={setPage} />}
      </section>
    </div>
  )
}

/** Informe de evidencias medido sobre el sistema vivo (revisión 2026-11). */
function InformeDeCumplimientoTab() {
  const t = useAppT()
  const toast = useToast()
  const [bajando, setBajando] = useState(false)
  const { data, isFetching, refetch } = useQuery<InformeDeCumplimiento>({
    queryKey: ['grc-compliance-report'], queryFn: () => grcApi.complianceReport().then(r => r.data),
  })
  const descargar = async () => {
    setBajando(true)
    try { downloadBlob((await grcApi.complianceReportSigned()).data, `compliance-report-${new Date().toISOString().slice(0, 10)}.json`) }
    catch (e) { toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) } finally { setBajando(false) }
  }
  const valor = (v: unknown): string => v === null || v === undefined ? '—' : typeof v === 'object' ? JSON.stringify(v) : String(v)
  return (
    <div>
      <div className="grc-row-21">
        <p className="grc-text-2">{t('grc.informe_intro')}</p>
        <Button size="sm" variant="secondary" icon={<RefreshCw size={14} />} onClick={() => refetch()} loading={isFetching}>{t('grc.informe_regenerar')}</Button>
        <Button size="sm" onClick={descargar} loading={bajando}>{t('grc.informe_descargar')}</Button>
        <Button size="sm" variant="ghost" onClick={() => window.print()}>{t('grc.informe_imprimir')}</Button>
      </div>
      {!data ? <div className="grc-box-8"><Spinner /></div> : (
        <>
          <div className="ds-grid-stats grc-mb">
            <KpiCard label={t('grc.informe_estado_pass')} value={data.summary.pass ?? 0} />
            <KpiCard label={t('grc.informe_estado_attention')} value={data.summary.attention ?? 0} danger={(data.summary.attention ?? 0) > 0} />
            <KpiCard label={t('grc.informe_estado_info')} value={data.summary.info ?? 0} />
            <KpiCard label={t('grc.informe_estado_not_measurable')} value={data.summary.not_measurable ?? 0} />
          </div>
          <div className="grc-box-12">
            {t('grc.informe_generado', { fecha: fmtDateTime(data.generated_at) })}
          </div>
          <TablaSimple claseTabla="u-table-sm">
            <thead><tr className="grc-row-23">
              <th className="grc-th-5">{t('grc.informe_col_estado')}</th><th className="grc-th-5">{t('grc.informe_col_control')}</th>
              <th className="grc-th-5">{t('grc.informe_col_medido')}</th><th className="grc-th-5">{t('grc.informe_col_marcos')}</th>
            </tr></thead>
            <tbody>
              {data.controls.map(c => (
                <tr key={c.id} className="grc-row-24">
                  <td className="grc-td-10 grc-page-e4" style={{ '--grc-page-color': COLOR_CONTROL[c.status] } as CSSProperties}>{t(`grc.informe_estado_${c.status}`)}</td>
                  <td className="grc-td-5">
                    <div className="u-600">{t(`grc.informe_control_${c.id}`)}</div>
                    <div className="u-text3-xs">{c.source}</div>
                  </td>
                  <td className="grc-td-11">
                    {Object.entries(c.measured).map(([k, v]) => <div key={k}>{k}: {valor(v)}</div>)}
                  </td>
                  <td className="grc-td-12">{c.frameworks.join(' · ') || '—'}</td>
                </tr>
              ))}
            </tbody>
          </TablaSimple>
        </>
      )}
    </div>
  )
}

/** ¿Puede este usuario hacer esto y qué capa lo decide? (revisión 2026-11) */
function ExplicarAccesoTab() {
  const t = useAppT()
  const toast = useToast()
  const [usuario, setUsuario] = useState('')
  const [metodo, setMetodo] = useState('GET')
  // No es una URL que pida el cliente: es la ruta del servidor que se quiere explicar (las de `rutas` llevan el mismo prefijo).
  const [camino, setCamino] = useState(`${PREFIJO_API_SERVIDOR}/projects`)
  const [res, setRes] = useState<Explicacion | null>(null)
  const [cargando, setCargando] = useState(false)
  const { data: usuarios = [] } = useQuery<{ id: string; full_name?: string; email?: string; role?: string }[]>({
    queryKey: ['users'], queryFn: () => usersApi.list().then(r => r.data ?? []),
  })
  const { data: rutas = [] } = useQuery<{ method: string; path: string }[]>({
    queryKey: ['grc-explainer-routes'], queryFn: () => grcApi.explainerRoutes().then(r => r.data),
  })
  const explicar = async () => {
    if (!usuario || !camino.trim()) return
    setCargando(true)
    try { setRes((await grcApi.explainAccess({ user_id: usuario, method: metodo, path: camino.trim() })).data) }
    catch (e) { toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)) } finally { setCargando(false) }
  }
  
  const detalle = (c: CapaDeAcceso) => {
    const extra = ['module', 'action', 'role', 'required', 'level', 'project_id', 'guards', 'resource_type', 'allowed_methods']
      .filter(k => c[k] !== undefined && c[k] !== null && c[k] !== '')
      .map(k => `${k}: ${Array.isArray(c[k]) ? (c[k] as string[]).join(', ') : String(c[k])}`)
    const texto = t(`grc.acceso_detalle_${c.detail}`)
    return (texto.startsWith('grc.') ? c.detail : texto) + (extra.length ? ` — ${extra.join(' · ')}` : '')
  }
  return (
    <div>
      <p className="grc-text-3">{t('grc.acceso_intro')}</p>
      <div className="u-wrap-center-8">
        <Select suelto placeholder={false} aria-label={t('grc.acceso_usuario')} value={usuario} onChange={e => setUsuario(e.target.value)} className="grc-page-e16">
          <option value="">{t('grc.acceso_usuario')}</option>
          {usuarios.map(u => <option key={u.id} value={u.id}>{u.full_name || u.email} {u.role ? `(${u.role})` : ''}</option>)}
        </Select>
        <Select suelto placeholder={false} aria-label="HTTP" value={metodo} onChange={e => setMetodo(e.target.value)} className="grc-page-e22">
          {['GET', 'POST', 'PUT', 'PATCH', 'DELETE'].map(m => <option key={m}>{m}</option>)}
        </Select>
        <input aria-label={t('grc.acceso_ruta')} list="grc-rutas" value={camino} onChange={e => setCamino(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') explicar() }} className="ds-codigo grc-page-e17" />
        <datalist id="grc-rutas">
          {rutas.filter(r => r.method === metodo).slice(0, 3000).map(r => <option key={r.path} value={r.path} aria-label={r.path} />)}
        </datalist>
        <Button onClick={explicar} disabled={!usuario} loading={cargando}>{t('grc.acceso_explicar')}</Button>
      </div>
      <div className="grc-box-13">{t('grc.acceso_ayuda_ruta')}</div>
      {res && (
        <div className="grc-box-14">
          <div role="status" className="grc-box-15 grcpage-sx17 grc-page-e13" style={{ '--grc-page-border': `1px solid ${COLOR_VEREDICTO[res.verdict]}`, '--grc-page-background': alpha(COLOR_VEREDICTO[res.verdict], '12') } as CSSProperties}>
            <div className="grc-box-16 grc-page-e4" style={{ '--grc-page-color': COLOR_VEREDICTO[res.verdict] } as CSSProperties}>
              {t(`grc.acceso_veredicto_${res.verdict}`)}{res.decided_by ? ` — ${t(`grc.acceso_capa_${res.decided_by}`)}` : ''}
            </div>
            <div className="ds-codigo grc-box-17">
              {res.method} {res.template || res.path}
            </div>
          </div>
          <ol className="grc-box-18">
            {res.layers.map(c => (
              <li key={c.layer} className={`grc-row-25 ${c.verdict === 'not_applicable' ? 'grcpage-sx18' : 'grcpage-sx7'}`}>
                <span className="grc-label-14 grc-page-e4" style={{ '--grc-page-color': COLOR_VEREDICTO[c.verdict] } as CSSProperties}>
                  {t(`grc.acceso_estado_${c.verdict}`)}
                </span>
                <span className="grc-label-15">{t(`grc.acceso_capa_${c.layer}`)}</span>
                <span className="u-text2-sm">{detalle(c)}</span>
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  )
}

export default function GrcPage(): JSX.Element {
  const { t } = useAppLang()
  const _t = useAppT()
  const [tab, setTab] = useState('matrix')

  const { data: rawRoles = [] } = useQuery<{ name: string; description?: string; color: string }[]>({
    queryKey: ['custom-roles'],
    queryFn: () => advancedConfigApi.getRoles().then(r => r.data),
  })
  const roles: Role[] = rawRoles.length > 0
    ? rawRoles.map((r: { name: string; description?: string; color: string }) => ({ id: r.name, label: r.description || r.name, color: r.color }))
    : rolesDeReserva(t)

  const TABS = [
    { id: 'matrix',     label: t('pagina_grc.matriz_de_permisos'), icon: <Grid3x3 size={14} /> },
    { id: 'sod',        label: t('pagina_grc.segregacion_sod'), icon: <ShieldCheck size={14} /> },
    { id: 'violations', label: t('pagina_grc.violaciones'), icon: <ShieldAlert size={14} /> },
    { id: 'approvals',  label: t('pagina_grc.flujos_de_mitigacion'), icon: <GitPullRequestArrow size={14} /> },
    { id: 'auditlog',   label: t('pagina_grc.audit_log'), icon: <ScrollText size={14} /> },
    { id: 'access',     label: _t('grc.acceso_pestana'), icon: <UserCheck size={14} /> },
    { id: 'compliance', label: _t('grc.informe_pestana'), icon: <FileCheck2 size={14} /> },
    { id: 'evidence',   label: _t('grc.evidencias_pestana'), icon: <FileText size={14} /> },
    { id: 'retention',  label: _t('grc.retencion_pestana'), icon: <Timer size={14} /> },
  ]

  return (
    <Page
      icon={<ShieldCheck size={18} />}
      title={_t('nav.grc')}
      subtitle={_t('grc.subtitle')}
    >
      <Tabs items={TABS} active={tab} onChange={setTab} ariaLabel={_t('nav.grc')} />

      <div className="grc-card-15">
        {tab === 'matrix'     && <MatrixTab roles={roles} />}
        {tab === 'sod'        && <SodTab roles={roles} />}
        {tab === 'violations' && <ViolationsTab roles={roles} />}
        {tab === 'approvals'  && <ApprovalsTab />}
        {tab === 'auditlog'   && <AuditLogTab />}
        {tab === 'access'     && <ExplicarAccesoTab />}
        {tab === 'compliance' && <InformeDeCumplimientoTab />}
        {tab === 'evidence'   && <EvidenciasTab />}
        {tab === 'retention'  && <RetencionTab />}
      </div>
    </Page>
  )
}
