import { useState, useId } from 'react'
import type { CSSProperties, ChangeEvent } from 'react'
import { useToast } from '../context/ToastContext'
import ResourceHeatmap from '../components/ResourceHeatmap'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { usersApi, skillsApi, burnoutRiskApi, billingSmartMatchApi, unwrapList } from '../services/api'
import type { RiesgoDeAgotamiento } from '../services/api/tipos-analitica'
import type { ResultadoSmartMatch } from '../services/api/tipos-finanzas'
import { settingsApi } from '../services/settingsApi'
/*
 * 16-11-2026: pasada de diseño. KPIs con KpiCard (antes cifra monoespaciada
 * propia); pestañas con icono; botones del kit (Recalcular, Editar, Añadir,
 * Buscar) con iconos lucide en lugar de emojis y flechas de texto; campos
 * con .ds-input; vacío de SmartMatch con
 * EmptyState; "skills" y "burnout" en castellano.
 */
import { Buscador, Avatar, LoadBar, Button, Card, KpiCard, Modal, Input, Select, Spinner, EmptyState, useSort, SortableTH, ViewToggle, Tabs, MarcaExterno, Pulsable, useErroresDeCampo } from '../components/ui'
import AltaDeExternoModal from '../components/externos/AltaDeExternoModal'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { AlertTriangle, BatteryWarning, Check, ClipboardList, Clock, Gauge, Grid3x3, HardHat, Plus, RefreshCw, Search, ShieldCheck, Sparkles, Target, UserCheck, UserX, Users, Wallet, X } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { extractErr } from '../utils/helpers'
import { useAppT } from '../i18n/AppLangContext'
import DateInput from '../components/ui/DateInput'
import { useFormatoMoneda } from '../hooks/useFormatoMoneda'
import { useOrgSettings, useTono, useUmbrales } from '../hooks/useOrgSettings'
import { estadoDeCarga } from '../utils/umbrales'
import { STALE_5_MIN_MS } from '../constants/timings'
import './ResourcesPage.css'
import { useRolesReales } from '../hooks/useRolesReales'

type T = ReturnType<typeof useAppT>

/** Nombre del rol en el idioma activo (`resources.role_*`); si no hay clave, el código. */
const nombreDeRol = (t: T, rol?: string | null) => rol ? t(`resources.role_${rol}`, rol) : '—'

const RISK_LEVELS = ['green', 'yellow', 'orange', 'red'] as const
type RiskLevelId = typeof RISK_LEVELS[number]
const nivelDeRiesgo = (l?: string | null): RiskLevelId => (RISK_LEVELS as readonly string[]).includes(l ?? '') ? l as RiskLevelId : 'green'

/** Ancho/alto dinámico en una variable CSS. */
const varCss = (nombre: string, valor: string | number) => ({ [nombre]: valor }) as CSSProperties

type BurnoutMember = RiesgoDeAgotamiento

function BurnoutRiskCard({ member }: { member: BurnoutMember }) {
  const t = useAppT()
  const tonoDe = useTono()
  const nivel = nivelDeRiesgo(member.risk_level)
  return (
    <div className={`res-bo-card res-risk--${nivel}`}>
      <Avatar name={member.full_name} size={38} url={undefined} />
      <div className="u-flex1-min0">
        <div className="res-bo-card__head">
          <div>
            <div className="res-bo-card__name">{member.full_name}</div>
            <div className="u-text3-xs">{member.job_title || member.department}</div>
          </div>
          <span className="res-bo-badge">{t(`resources_page.riesgo_${nivel}`)}</span>
        </div>
        <div className="res-bo-stats">
          {[
            { label: t('resources_page.carga_actual'), value: `${member.current_load_pct?.toFixed(0)}%`, tone: tonoDe('carga', member.current_load_pct ?? 0) === 'danger' ? 'danger' : 'text' },
            { label: t('resources_page.media_4sem'),   value: `${member.avg_load_4w?.toFixed(0)}%`,      tone: (member.avg_load_4w ?? 0) > 90 ? 'warning' : 'text' },
            { label: t('resources_page.racha_semanas'), value: member.overload_weeks_streak,             tone: (member.overload_weeks_streak ?? 0) >= 3 ? 'danger' : 'text' },
          ].map(s => (
            <div key={s.label} className={`res-bo-stat res-tone--${s.tone}`}>
              <div className="res-bo-stat__value">{s.value}</div>
              <div className="res-bo-stat__label">{s.label}</div>
            </div>
          ))}
        </div>
        {/* Sparkline mini-bar */}
        {(member.weekly_history?.length ?? 0) > 0 && (
          <div className="res-spark" aria-hidden="true">
            {member.weekly_history!.slice(0, 8).map((w: { load_pct?: number }, i: number) => {
              const carga = w.load_pct ?? 0
              const h = Math.min(100, carga)
              // El color sale de la carga real: con el valor ya topado a 100 nunca salía rojo.
              const tone = tonoDe('carga', carga)
              return (
                <div key={i} title={t('resources_page.semana_menos', { n: i, pct: w.load_pct?.toFixed(0) ?? 0 })}
                  className={`res-spark__bar res-tone--${tone}`}
                  style={{ ...varCss('--h', `${Math.max(8, h * 0.28)}px`), ...varCss('--op', 0.7 + i * 0.04) }} />
              )
            }).reverse()}
          </div>
        )}
        {(member.factors?.length ?? 0) > 0 && (
          <div className="res-factors">
            {member.factors!.map((f: string, i: number) => (
              <span key={i} className="res-factor">{f}</span>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function BurnoutMonitorTab() {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const [filter, setFilter] = useState('all')
  const { data, isLoading } = useQuery({
    queryKey: ['burnout-risk', filter],
    queryFn: () => burnoutRiskApi.get(
      filter !== 'all' ? { min_risk_level: filter } : undefined
    ).then(r => r.data),
    staleTime: STALE_5_MIN_MS,
  })
  const { mutate: recompute, isPending } = useMutation({
    mutationFn: () => burnoutRiskApi.compute(),
    // Antes no refrescaba: el recálculo no se veía hasta pasados 5 minutos.
    onSuccess: () => qc.invalidateQueries({ queryKey: ['burnout-risk'] }),
    onError: (e: unknown) => toast.error(extractErr(e, t('resources_page.error_generico'))),
  })

  const members = data?.members || []
  const summary: Record<string, number> = data?.summary || {}

  return (
    <div>
      <div className="res-bo-bar">
        <div className="u-wrap-6" role="group" aria-label={t('resources_page.filtrar_riesgo')}>
          {(['all', 'yellow', 'orange', 'red'] as const).map(id => (
            <Pulsable key={id} type="button" onClick={() => setFilter(id)} aria-pressed={filter === id} className="res-chip">
              {id === 'all' ? t('resources_page.todos') : t(`resources_page.riesgo_${id}`)}
            </Pulsable>
          ))}
        </div>
        <Button variant="secondary" size="sm" icon={<RefreshCw size={14} />} onClick={() => recompute()} loading={isPending}>
          {isPending ? t('resources_page.calculando') : t('resources_page.recalcular')}
        </Button>
      </div>

      {/* Summary pills */}
      <div className="res-bo-summary">
        {RISK_LEVELS.map(k => (
          <div key={k} className={`res-bo-pill res-risk--${k}`}>
            <span className="res-bo-pill__n">{summary[k] ?? 0}</span>
            <span className="u-text3-xs">{t(`resources_page.riesgo_${k}`)}</span>
          </div>
        ))}
      </div>

      {isLoading ? (
        <div className="res-loading res-loading--sm" role="status">
          <Spinner /><span className="u-text2">{t('resources.analyzing_load_patterns')}</span>
        </div>
      ) : members.length === 0 ? (
        <EmptyState icon={<ShieldCheck size={28} />} title={t('resources.empty_title')} description={t('resources.empty_desc')} />
      ) : (
        <div className="res-bo-grid">
          {members.map(m => <BurnoutRiskCard key={m.user_id} member={m} />)}
        </div>
      )}
    </div>
  )
}

interface ResourceUser {
  id?: string
  full_name?: string
  job_title?: string
  department?: string
  role?: string
  email?: string
  hourly_rate?: number | string | null
  weekly_capacity_hours?: number | string
  /** Proveedor si es un recurso externo (rol `subcontractor`). */
  external_company?: string | null
}
type Resource = {
  [key: string]: unknown
  user?: ResourceUser
  full_name?: string
  job_title?: string
  department?: string
  current_load_pct?: number
  hours_this_week?: number
  active_projects?: number
  hourly_rate?: number | string | null
}

/** 19-11-2026: bandas de carga de la empresa (`estadoDeCarga`, utils/umbrales); antes 100/85/60 aquí. */
const TONO_DE_ESTADO = { sobrecargado: 'danger', alto: 'warning', ocupado: 'accent', disponible: 'success' } as const

function ResourceCard({ resource, onEdit, showRates, canEdit }: { resource: Resource; onEdit: (r: Resource) => void; showRates: boolean; canEdit: boolean }) {
  const fmtMoneda = useFormatoMoneda()
  const t = useAppT()
  const umbrales = useUmbrales()
  const load = resource.current_load_pct ?? 0
  const tono = TONO_DE_ESTADO[estadoDeCarga(load, umbrales)]
  const nombre = resource.user?.full_name || resource.full_name
  return (
    <div className={`res-card${tono === 'danger' ? ' res-card--over' : ''}`}>
      <div className="res-card__head">
        <div className="res-card__who">
          <Avatar name={nombre} size={40} url={undefined} />
          <div>
            <div className="res-card__name">{nombre}</div>
            <MarcaExterno persona={resource.user} />
            <div className="res-card__sub">
              {resource.user?.job_title || resource.job_title}
              {(resource.user?.department || resource.department) && (
                <> · <span className="res-card__dept">{resource.user?.department || resource.department}</span></>
              )}
            </div>
          </div>
        </div>
        <div className="res-card__actions">
          {tono === 'danger' && <span title={t('resources_page.sobrecarga')} role="img" aria-label={t('resources_page.sobrecarga')} className="res-card__warn"><AlertTriangle size={16} aria-hidden /></span>}
          {/* Sólo para administradores: el editor cambia capacidad semanal,
              departamento y tarifa, y `PATCH /users/{id}` reserva esos campos a
              un administrador. Antes el botón se mostraba a todo el mundo y
              devolvía 403 al guardar. */}
          {canEdit && <Button variant="secondary" size="sm" onClick={() => onEdit(resource)}
            title={t('resources_page.editar_recurso', { nombre: nombre ?? '' })}>
            {t('resources_page.editar')}
          </Button>}
        </div>
      </div>
      <div className="res-metrics">
        {[
          { label: t('resources_page.carga'),      value: `${load.toFixed(0)}%`,                           tone: tono },
          { label: t('resources_page.horas_sem'),  value: `${resource.hours_this_week?.toFixed(1) ?? 0}h`, tone: 'text' },
          { label: t('resources_page.proyectos'),  value: resource.active_projects ?? 0,                  tone: 'text' },
        ].map(m => (
          <div key={m.label} className={`res-metric res-tone--${m.tone}`}>
            <div className="res-metric__value">{m.value}</div>
            <div className="res-metric__label">{m.label}</div>
          </div>
        ))}
      </div>
      <div>
        <div className="res-util__head">
          <span>{t('resources.utilization')}</span>
          <span className={`res-util__value res-tone--${tono}`}>{load.toFixed(0)}%</span>
        </div>
        <LoadBar value={load} label={undefined} />
      </div>
      {showRates && resource.user?.hourly_rate && (
        <div className="res-rate">
          <span className="u-text3">{t('resources_page.tarifa')}</span>
          <span className="res-rate__value">{t('resources_page.por_hora', { importe: fmtMoneda(resource.user.hourly_rate) })}</span>
        </div>
      )}
    </div>
  )
}

function EditUserModal({ user, open, onClose }: { user: Resource; open: boolean; onClose: () => void }) {
  const t = useAppT()
  const qc = useQueryClient()
  const toast = useToast()
  const { weekly_capacity_hours: capacidadEmpresa } = useOrgSettings() // 18-11-2026: capacidad por defecto de la empresa
  const [form, setForm] = useState<Record<string, string>>({
    email:                 String(user?.user?.email                 || user?.email                 || ''),
    full_name:             String(user?.user?.full_name             || user?.full_name             || ''),
    job_title:             String(user?.user?.job_title             || user?.job_title             || ''),
    department:            String(user?.user?.department            || user?.department            || ''),
    role:                  String(user?.user?.role                  || (user?.role as string)     || 'employee'),
    weekly_capacity_hours: String(user?.user?.weekly_capacity_hours || capacidadEmpresa),
    hourly_rate:           String(user?.hourly_rate                 ?? user?.user?.hourly_rate     ?? ''),
  })
  const { puede } = useAuth()
  const rolesReales = useRolesReales()
  const userId = (user?.user?.id || user?.id) as string
  const { data: departments = [] } = useQuery<Array<{ name: string; is_active?: boolean }>>({
    queryKey: ['departments-select'],
    queryFn: () => settingsApi.getDepartments().then(r => r.data),
  })
  const campos = useErroresDeCampo()
  const { mutate, isPending } = useMutation({
    mutationFn: (data: Record<string, unknown>) => usersApi.update(userId, data),
    onMutate: () => campos.limpiar(),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['resources'] }); qc.invalidateQueries({ queryKey: ['users'] }); qc.invalidateQueries({ queryKey: ['capacity-board'] }); qc.invalidateQueries({ queryKey: ['forecast-heatmap'] }); qc.invalidateQueries({ queryKey: ['forecast-summary'] }); onClose() },
    onError: (e: unknown) => { if (!campos.recoger(e)) toast.error(extractErr(e, t('resources_page.error_generico'))) },
  })
  const set = (k: string) => (e: ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => { campos.limpiar(k); setForm(f => ({ ...f, [k]: e.target.value })) }
  const handleSave = () => {
    const payload = {
      ...form,
      weekly_capacity_hours: form.weekly_capacity_hours !== '' ? parseFloat(form.weekly_capacity_hours) : capacidadEmpresa,
      hourly_rate: form.hourly_rate !== '' ? parseFloat(form.hourly_rate) : null,
    }
    mutate(payload)
  }
  // «Externo» no se da desde aquí: el externo nace de un proveedor («Nuevo externo»).
  // 19-11-2026: roles reales del backend (`GET /auth/roles`).
  const roles = rolesReales
    .filter(r => r.interno || form.role === r.id)
    .map(r => ({ value: r.id, label: nombreDeRol(t, r.id) }))
  return (
    <Modal open={open} onClose={onClose} title={t('resources_page.editar_titulo')}>
      <div className="u-stack-14">
        <Input error={campos.de('email')} label={t('resources_page.email')} type="email" value={form.email} onChange={set('email')} placeholder={undefined} required={undefined} hint={undefined} />
        <Input error={campos.de('full_name')} label={t('resources_page.nombre_completo')} value={form.full_name} onChange={set('full_name')} placeholder={undefined} required={undefined} hint={undefined} />
        <Input error={campos.de('job_title')} label={t('resources.job_title')} value={form.job_title} onChange={set('job_title')} placeholder={undefined} required={undefined} hint={undefined} />
        <Select error={campos.de('department')} label={t('resources.department')} value={form.department} onChange={set('department')}
          options={[{ value: '', label: t('resources_page.sin_departamento') }, ...departments.filter((d) => d.is_active !== false).map((d) => ({ value: d.name, label: d.name }))]} />
        <Select error={campos.de('role')} label={t('resources_page.rol')} value={form.role} onChange={set('role')} options={roles} />
        <Input error={campos.de('weekly_capacity_hours')} label={t('resources.weekly_capacity')} type="number" value={form.weekly_capacity_hours} onChange={set('weekly_capacity_hours')} placeholder={undefined} required={undefined} hint={undefined} />
        {puede('org.administrar') && <Input error={campos.de('hourly_rate')} label={t('resources.tarifa_por_hora')} type="number" value={form.hourly_rate} onChange={set('hourly_rate')} placeholder={undefined} required={undefined} hint={undefined} />}
        <div className="res-form-actions">
          <Button variant="secondary" onClick={onClose}>{t('resources_page.cancelar')}</Button>
          <Button onClick={handleSave} disabled={isPending} loading={isPending}>{isPending ? t('resources_page.guardando') : t('resources_page.guardar_cambios')}</Button>
        </div>
      </div>
    </Modal>
  )
}

interface SmartMatchForm {
  skills: string[]
  role: string
  hours_needed: number
  start_date: string
  end_date: string
  max_hourly_rate: string
}
type SmartMatchResult = ResultadoSmartMatch
interface SkillItem { id?: string; name: string }

const SKILLS_SUGERIDOS = ['React', 'Python', 'AWS', 'DevOps', 'Scrum', 'SQL', 'Java', 'Angular']
const tonoDePuntuacion = (n: number) => n >= 75 ? 'success' : n >= 25 ? 'warning' : 'danger'

function SmartMatchTab() {
  const fmtMoneda = useFormatoMoneda()
  const idCampo = useId()
  const t = useAppT()
  const toast = useToast()
  const [form, setForm] = useState<SmartMatchForm>({ skills: [], role: '', hours_needed: 40, start_date: '', end_date: '', max_hourly_rate: '' })
  const [skillInput, setSkillInput] = useState('')
  const [results, setResults] = useState<SmartMatchResult | null>(null)

  const { data: allSkills = [] } = useQuery<SkillItem[]>({
    queryKey: ['skills-sm'],
    queryFn: () => skillsApi.catalog().then(r => r.data),
  })

  const { mutate: search, isPending } = useMutation({
    mutationFn: (d: Record<string, unknown>) => billingSmartMatchApi.match(d).then(r => r.data),
    onSuccess: (data) => setResults(data),
    onError: (e: unknown) => toast.error(extractErr(e, t('resources_page.error_generico'))),
  })

  const addSkill = (skill: string | SkillItem) => {
    const name = typeof skill === 'string' ? skill : skill.name
    if (name && !form.skills.includes(name)) setForm(f => ({ ...f, skills: [...f.skills, name] }))
    setSkillInput('')
  }
  const removeSkill = (s: string) => setForm(f => ({ ...f, skills: f.skills.filter(x => x !== s) }))

  return (
    <div className="res-sm">
      <div>
        <div className="res-panel">
          <div className="res-sm__title"><Sparkles size={16} aria-hidden /> {t('resources_page.tab_smartmatch')}</div>
          <div className="res-sm__intro">{t('resources.encuentra_los_mejores_recursos_para_tu_proyecto')}</div>

          <div className="u-mb-14">
            <label id={`${idCampo}-etskill`} htmlFor={`${idCampo}-skill`} className="res-label">{t('resources_page.skills_requeridos')}</label>
            <div className="res-skills">
              {form.skills.map(s => (
                <span key={s} className="res-skill">
                  {s}
                  <Pulsable type="button" onClick={() => removeSkill(s)} className="res-skill__remove"
                    aria-label={t('resources_page.quitar_skill', { skill: s })}><span aria-hidden="true">×</span></Pulsable>
                </span>
              ))}
            </div>
            <div className="u-row-8">
              <Select suelto placeholder={false} id={`${idCampo}-skill`} value={skillInput} onChange={e => setSkillInput(e.target.value)} className="res-input--grow">
                <option value="">{t('resources_page.seleccionar_skill')}</option>
                {allSkills.filter(s => !form.skills.includes(s.name)).map(s => <option key={s.id || s.name} value={s.name}>{s.name}</option>)}
              </Select>
              <Button variant="secondary" icon={<Plus size={14} />} onClick={() => { if (skillInput) addSkill(skillInput) }} disabled={!skillInput}>{t('resources_page.anadir')}</Button>
            </div>
            <div className="res-quicks">
              {SKILLS_SUGERIDOS.filter(s => !form.skills.includes(s)).map(s => (
                <Pulsable key={s} type="button" onClick={() => addSkill(s)} className="res-quick"
                  aria-label={t('resources_page.anadir_skill_nombre', { skill: s })}>+{s}</Pulsable>
              ))}
            </div>
          </div>

          <div className="u-mb-14">
            <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="res-label">{t('resources_page.rol')}</label>
            <Select suelto placeholder={false} id={`${idCampo}-1`} value={form.role} onChange={e => setForm(f => ({ ...f, role: e.target.value }))}>
              <option value="">{t('resources_page.cualquier_rol')}</option>
              <option value="employee">{t('resources_page.rol_employee')}</option>
              <option value="pm">{t('resources_page.rol_pm')}</option>
              <option value="team_lead">{t('resources_page.rol_team_lead')}</option>
            </Select>
          </div>

          <div className="res-sm__grid">
            <div><label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="res-label">{t('resources_page.horas_necesarias')}</label><Input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} type="number" value={form.hours_needed} onChange={e => setForm(f => ({ ...f, hours_needed: +e.target.value }))} /></div>
            <div><label id={`${idCampo}-et5`} htmlFor={`${idCampo}-5`} className="res-label">{t('resources_page.tarifa_max')}</label><Input id={`${idCampo}-5`} aria-labelledby={`${idCampo}-et5`} type="number" value={form.max_hourly_rate} onChange={e => setForm(f => ({ ...f, max_hourly_rate: e.target.value }))} placeholder={t('resources_page.tarifa_maxima')} /></div>
            <div><label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="res-label">{t('resources_page.inicio')}</label><DateInput id={`${idCampo}-3`} aria-labelledby={`${idCampo}-et3`} value={form.start_date} onChange={e => setForm(f => ({ ...f, start_date: e.target.value }))} className="ds-input" /></div>
            <div><label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="res-label">{t('resources_page.fin')}</label><DateInput id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} value={form.end_date} onChange={e => setForm(f => ({ ...f, end_date: e.target.value }))} className="ds-input" /></div>
          </div>

          <div className="res-full">
            <Button icon={<Search size={14} />} onClick={() => search({ ...form, max_hourly_rate: form.max_hourly_rate ? +form.max_hourly_rate : undefined })} loading={isPending} disabled={isPending}>
              {isPending ? t('resources_page.buscando') : t('resources_page.buscar_recursos')}
            </Button>
          </div>
        </div>
      </div>

      <div aria-live="polite">
        {!results && !isPending && (
          <Card>
            <EmptyState icon={<Target size={28} />} title={t('resources_page.smartmatch_vacio_titulo')}
              description={t('resources.configura_los_criterios_y_pulsa_buscar_recursos')} />
          </Card>
        )}
        {isPending && <Spinner />}
        {results && (
          <div>
            <div className="res-sm__message">{results.message}</div>
            {(results.candidates || []).map((c, i) => (
              <div key={c.user_id} className={`res-cand res-tone--${tonoDePuntuacion(c.scores.overall)}`}>
                <div className="res-cand__head">
                  <div className="u-row-center-12">
                    <div className="res-rank" aria-label={t('resources_page.puesto', { n: i + 1 })}>{i + 1}</div>
                    <div>
                      <div className="res-cand__name">{c.user_name}</div>
                      <div className="u-text2-sm">{c.job_title || nombreDeRol(t, c.role)} · {c.department || '—'}</div>
                    </div>
                  </div>
                  <div className="res-cand__score">
                    <div className="res-cand__overall">{c.scores.overall}%</div>
                    <div className="res-cand__reco">{c.recommendation}</div>
                  </div>
                </div>
                <div className="res-cand__scores">
                  {([
                    [t('resources_page.score_skills'), c.scores.skills, 'purple'],
                    [t('resources_page.score_disponibilidad'), c.scores.availability, 'accent'],
                    [t('resources_page.score_carga'), c.scores.workload, 'success'],
                    [t('resources_page.score_coste'), c.scores.cost, 'warning'],
                  ] as const).map(([l, v, tone]) => (
                    <div key={l} className={`res-cand__cell res-tone--${tone}`}>
                      <div className="res-cand__cell-value">{v}%</div>
                      <div className="res-cand__cell-label">{l}</div>
                    </div>
                  ))}
                </div>
                <div className="res-cand__facts">
                  {(c.hourly_rate ?? 0) > 0 && <span className="res-fact"><Wallet size={13} aria-hidden /> {t('resources_page.por_hora', { importe: fmtMoneda(c.hourly_rate) })}</span>}
                  <span className="res-fact"><Clock size={13} aria-hidden /> {t('resources_page.horas_disponibles', { n: c.availability_hours })}</span>
                  <span className="res-fact"><ClipboardList size={13} aria-hidden /> {t('resources_page.tareas_activas', { n: c.active_tasks })}</span>
                  {(c.matched_skills?.length ?? 0) > 0 && <span className="res-fact res-fact--ok"><Check size={13} aria-hidden /> {c.matched_skills!.join(', ')}</span>}
                  {(c.missing_skills?.length ?? 0) > 0 && <span className="res-fact u-danger"><X size={13} aria-hidden /> {t('resources_page.faltan', { skills: c.missing_skills!.join(', ') })}</span>}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export default function ResourcesPage() {
  const fmtMoneda = useFormatoMoneda()
  const t = useAppT()
  const umbrales = useUmbrales()
  const tonoDe = useTono()
  const [resTab, setResTab] = useState('team')
  const { puede } = useAuth()
  const [deptFilter, setDeptFilter] = useState('')
  const [search, setSearch] = useState('')
  const [resSortBy] = useState('user.full_name')
  const [editTarget, setEditTarget] = useState<Resource | null>(null)
  const [view, setView] = useState('grid')
  const [altaExterno, setAltaExterno] = useState(false)
  // Alta de externos: quien gestiona proveedores (Subcontratistas: admin y pm).
  const puedeAltaExterno = puede('externos.alta')

  const { data: loadData = [], isLoading } = useQuery<Resource[]>({
    queryKey: ['resources'],
    queryFn: () => usersApi.load().then(unwrapList) as Promise<Resource[]>,
  })

  // El buscador anuncia nombre, cargo o departamento: antes solo miraba el nombre.
  const q = search.trim().toLowerCase()
  const filtered = loadData.filter(r => {
    const dept = r.user?.department || ''
    const texto = [r.user?.full_name, r.user?.job_title, r.user?.department, r.user?.external_company].filter(Boolean).join(' ').toLowerCase()
    return (!q || texto.includes(q)) && (!deptFilter || dept === deptFilter)
  })
  const { sort: resSort, setSort: setResSort, sortedData: sortedResources } = useSort<Resource>(filtered, resSortBy)

  const departments = [...new Set<string>(loadData.map(r => r.user?.department).filter((v): v is string => Boolean(v)))]
  const overloaded  = loadData.filter(r => tonoDe('carga', r.current_load_pct ?? 0) === 'danger').length
  const available   = loadData.filter(r => estadoDeCarga(r.current_load_pct ?? 0, umbrales) === 'disponible').length
  const avgLoad     = loadData.length ? (loadData.reduce((s, r) => s + (r.current_load_pct ?? 0), 0) / loadData.length).toFixed(0) : 0
  const conTarifas  = puede('costes.ver')

  const TABS = [
    { id: 'team',       label: t('resources_page.tab_equipo'),     icon: <Users size={14} /> },
    { id: 'heatmap',    label: t('resources_page.tab_heatmap'),    icon: <Grid3x3 size={14} /> },
    { id: 'smartmatch', label: t('resources_page.tab_smartmatch'), icon: <Sparkles size={14} /> },
    { id: 'burnout',    label: t('resources_page.tab_burnout'),    icon: <BatteryWarning size={14} /> },
  ]

  return (
    <PageShell>
      <PageHeader icon={<Users size={18} />} title={t('resources.title')} subtitle={t('resources.subtitle')}
        actions={puedeAltaExterno ? <Button variant="secondary" icon={<HardHat size={14} />} onClick={() => setAltaExterno(true)}>{t('externos.nuevo_externo')}</Button> : undefined} />
      {altaExterno && <AltaDeExternoModal onClose={() => setAltaExterno(false)} />}

      {/* KPI bar */}
      <div className="ds-grid-stats res-kpis">
        <KpiCard icon={<Users size={16} />} label={t('resources_page.kpi_total')} value={loadData.length} />
        <KpiCard icon={<UserCheck size={16} />} label={t('resources_page.kpi_disponibles')} value={available} />
        <KpiCard icon={<UserX size={16} />} label={t('resources_page.kpi_sobrecargados')} value={overloaded} danger={overloaded > 0} />
        <KpiCard icon={<Gauge size={16} />} label={t('resources_page.kpi_carga_media')} value={`${avgLoad}%`} warning={tonoDe('carga', Number(avgLoad)) !== 'success'} />
      </div>

      <Tabs items={TABS} active={resTab} onChange={setResTab} ariaLabel={t('resources.title')} />

      {resTab === 'heatmap' ? <ResourceHeatmap /> : resTab === 'smartmatch' ? <SmartMatchTab /> : resTab === 'burnout' ? <BurnoutMonitorTab /> : (
        <>
          <div className="res-filters">
            <Buscador aria-label={t('resources.buscar_por_nombre_cargo_o_departamento')} value={search} onChange={setSearch} placeholder={t('resources.buscar_por_nombre_cargo_o_departamento')}
              inputClassName="res-input--search" />
            <Select suelto placeholder={false} value={deptFilter} onChange={e => setDeptFilter(e.target.value)} aria-label={t('resources.department')} className="res-input--auto">
              <option value="">{t('resources.todos_los_departamentos')}</option>
              {departments.map(d => <option key={d} value={d}>{d}</option>)}
            </Select>
            <Select suelto placeholder={false} value={resSort.key} onChange={e => setResSort(e.target.value)} aria-label={t('resources_page.ordenar')} className="res-input--auto">
              <option value="user.full_name">{t('resources_page.orden_nombre')}</option>
              <option value="current_load_pct">{t('resources_page.orden_carga')}</option>
              <option value="user.department">{t('resources.department')}</option>
              <option value="user.role">{t('resources_page.rol')}</option>
            </Select>
            <ViewToggle view={view} onChange={setView} />
          </div>
          {isLoading ? (
            <div className="res-loading" role="status"><Spinner /><span className="u-text2">{t('resources_page.cargando')}</span></div>
          ) : filtered.length === 0 ? (
            <EmptyState icon={<Users size={28} />} title={t('resources.sin_recursos')} description={t('resources_page.sin_coincidencias')} />
          ) : view === 'grid' ? (
            <div className="res-grid">
              {sortedResources.map(r => <ResourceCard key={r.user?.id} resource={r} onEdit={setEditTarget} showRates={conTarifas} canEdit={puede('org.administrar')} />)}
            </div>
          ) : (
            <div className={`res-table${conTarifas ? ' res-table--rates' : ''}`}>
              <div className="res-table__inner">
              <div className="res-table__row res-table__head">
                <SortableTH col="user.full_name" sort={resSort} onSort={setResSort}>{t('resources_page.col_recurso')}</SortableTH>
                <SortableTH col="user.department" sort={resSort} onSort={setResSort}>{t('resources.department')}</SortableTH>
                <SortableTH col="user.role" sort={resSort} onSort={setResSort}>{t('resources_page.rol')}</SortableTH>
                <SortableTH col="current_load_pct" sort={resSort} onSort={setResSort}>{t('resources_page.orden_carga')}</SortableTH>
                <SortableTH col="hours_this_week" sort={resSort} onSort={setResSort}>{t('resources_page.horas_sem')}</SortableTH>
                <SortableTH col="active_projects" sort={resSort} onSort={setResSort}>{t('resources_page.proyectos')}</SortableTH>
                {conTarifas && <SortableTH col="user.hourly_rate" sort={resSort} onSort={setResSort}>{t('resources.hourly_rate')}</SortableTH>}
              </div>
              {sortedResources.map(r => {
                const carga = r.current_load_pct ?? 0
                return (
                  <div key={r.user?.id} className="res-table__row">
                    <div className="u-row-center-10">
                      <div className="res-initial" aria-hidden="true">
                        {r.user?.full_name?.charAt(0) || '?'}
                      </div>
                      <div>
                        <div className="u-base-600">{r.user?.full_name} <MarcaExterno persona={r.user} /></div>
                        <div className="u-text2-xs">{r.user?.job_title}</div>
                      </div>
                    </div>
                    <span className="u-text2-sm">{r.user?.department || '—'}</span>
                    <span className="u-text2-sm">{nombreDeRol(t, r.user?.role)}</span>
                    <div className="u-row-center-6">
                      <div className={`res-track res-tone--${tonoDe('carga', carga)}`} aria-hidden="true">
                        <div className="res-fill" style={varCss('--pct', `${Math.min(carga, 100)}%`)} />
                      </div>
                      <span className={`res-pct${tonoDe('carga', carga) === 'danger' ? ' res-pct--over' : ''}`}>{r.current_load_pct}%</span>
                    </div>
                    <span className="res-mono">{r.hours_this_week || 0}h</span>
                    <span className="u-sm">{r.active_projects || 0}</span>
                    {conTarifas && <span className="res-mono">{r.user?.hourly_rate ? fmtMoneda(r.user.hourly_rate) : '—'}</span>}
                  </div>
                )
              })}
              </div>
            </div>
          )}
          {editTarget && <EditUserModal user={editTarget} open={!!editTarget} onClose={() => setEditTarget(null)} />}
        </>
      )}
    </PageShell>
  )
}
