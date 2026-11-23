/**
 * CapacityPage — Planificador visual de recursos con drag-and-drop
 *
 * Matriz: usuarios (filas) × semanas (columnas)
 * Permite arrastrar bloques de horas de un usuario/semana a otro.
 */
import { useState, useId, useMemo } from 'react'
import { extractErr, fmtNumber, fmtHours, formateadorDeFecha } from '../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../constants/errors'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { usersApi, capacityApi, esFichaCompleta } from '../services/api'
import { useListaDeProyectos } from '../hooks/useListas'
import type { PlanDeCapacidad } from '../services/api/tipos-personas'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { TrendingUp, Plus, X, Users, Building2, ClipboardList, CalendarRange, Info } from 'lucide-react'
import { Button, Modal, EmptyState, KpiCard, RejillaPersonaDia, columnasDeSemanas, Pulsable, Select, useErroresDeCampo, Input } from '../components/ui'
import type { TonoDeRejilla } from '../components/ui'
import { useAppT } from '../i18n/AppLangContext'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { z } from 'zod'
import { useFormValidation } from '../hooks/useFormValidation'
import { useOrgSettings, useUmbrales } from '../hooks/useOrgSettings'
import { estadoDeCarga } from '../utils/umbrales'
import DateInput from '../components/ui/DateInput'
import { STALE_SHORT_MS } from '../constants/timings'
import './CapacityPage.css'

type UserItem = {
  id: string | number
  full_name: string
  department?: string | null
  weekly_capacity_hours?: number | null
  is_active?: boolean
}

type CapacityPlan = PlanDeCapacidad

type AssignPrefill = {
  user_id?: string | number
  project_id?: string | number
  week_start?: string
  hours?: number
}

type AssignForm = {
  user_id: string
  project_id: string
  week_start: string
  planned_hours: number
  notes: string
}

type Traducir = (key: string, vars?: Record<string, string | number>) => string

/** El esquema lleva los mensajes en el idioma activo. */
const crearEsquema = (t: Traducir) => z.object({
  user_id: z.string().trim().min(1, t('capacity.val_persona')),
  project_id: z.string().optional(),
  week_start: z.string().min(1, t('capacity.val_semana')),
  planned_hours: z.coerce.number().min(1, t('capacity.val_horas_min')).max(80, t('capacity.val_horas_max')),
  notes: z.string().optional(),
})
type EsquemaAsignacion = ReturnType<typeof crearEsquema>

/** Estado de carga de una semana (clave de la leyenda de la rejilla común). */
// 19-11-2026: `estadoDeCarga` (utils/umbrales) con los umbrales de la empresa; antes 100/85/60 aquí.
const LEYENDA: Array<{ clave: string; tono: TonoDeRejilla }> = [
  { clave: 'disponible',   tono: 'success' },
  { clave: 'ocupado',      tono: 'accent' },
  { clave: 'alto',         tono: 'warning' },
  { clave: 'sobrecargado', tono: 'danger' },
]

function monday(d: Date | string) {
  const dt = new Date(d)
  const day = dt.getDay()
  dt.setDate(dt.getDate() - (day === 0 ? 6 : day - 1))
  return dt.toISOString().slice(0, 10)
}

function addWeeks(dateStr: string, n: number) {
  const d = new Date(dateStr)
  d.setDate(d.getDate() + n * 7)
  return d.toISOString().slice(0, 10)
}

/** Día y mes del lunes de la semana, en el formato del idioma activo. */
function weekLabel(dateStr: string) {
  return formateadorDeFecha({ day: 'numeric', month: 'numeric' }).format(new Date(dateStr))
}

// ── Modal de nueva asignación ─────────────────────────────────────────────────
function AssignModal({ prefill, onClose }: { prefill: AssignPrefill | null; onClose: () => void }) {
  const idCampo = useId()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { working_hours_per_day: jornada, weekly_capacity_hours: capacidadSemanal } = useOrgSettings()
  const [form, setForm] = useState<AssignForm>({
    user_id:       prefill?.user_id ? String(prefill.user_id) : '',
    project_id:    prefill?.project_id ? String(prefill.project_id) : '',
    week_start:    prefill?.week_start || monday(new Date()),
    planned_hours: prefill?.hours || jornada, // 18-11-2026: jornada de la empresa
    notes:         '',
  })
  const assignPlanSchema = useMemo(() => crearEsquema(t as Traducir), [t])
  const validation = useFormValidation(assignPlanSchema)

  const { data: users = [] } = useQuery<UserItem[]>({
    // Capacidad semanal: solo la ficha completa la trae (`PersonaInterna` no); clave propia porque filtra.
    queryKey: ['users', 'capacidad'],
    queryFn: () => usersApi.list({}).then(r => r.data.filter(esFichaCompleta).filter((u) => u.is_active)),
  })
  // 23-11-2026 (04 A8): solo proyectos activos, pasado como parámetro (entra en la clave de la lista
  // compartida; antes este filtro cliente guardaba bajo `['projects']` una lista distinta de la de las demás pantallas).
  const { data: projects = [] } = useListaDeProyectos({ status: 'active' })

  const campos = useErroresDeCampo()
  const msg = (k: string) => campos.de(k) ? <div className="u-field-error">{campos.de(k)}</div> : null
  const { mutate, isPending } = useMutation({
    onMutate: () => campos.limpiar(),
    mutationFn: (d: z.infer<EsquemaAsignacion>) => capacityApi.createPlan(d),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['capacity-board'] })
      qc.invalidateQueries({ queryKey: ['forecast-heatmap'] })
      qc.invalidateQueries({ queryKey: ['forecast-summary'] })
      toast.success(t('capacity.toast_creada'))
      validation.setErrors({})
      onClose()
    },
    onError: (e: unknown) => { if (!campos.recoger(e)) toast.error(extractErr(e, t('capacity.error_guardar'))) },
  })

  const setField = (key: keyof AssignForm) => (e: { target: { value: string } }) => {
    const value = key === 'planned_hours' ? +e.target.value : e.target.value
    setForm(current => ({ ...current, [key]: value as never }))
    validation.clearFieldError(key)
  }

  const submit = () => {
    const result = validation.validateForm(form)
    if (!result.success) {
      return
    }
    mutate(result.data)
  }

  return (
    <Modal open title={t('capacity.nueva_asignacion')} onClose={onClose} width={460}>
      <div className="cap-form">
        <div>
          <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="cap-label">{t('capacity.persona_obligatoria')}</label>
          <Select suelto placeholder={false} id={`${idCampo}-1`} value={form.user_id} onChange={setField('user_id')} className="cap-input" aria-invalid={!!validation.errors.user_id}>
            <option value="">{t('capacity.seleccionar')}</option>
            {users.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
          </Select>{msg('user_id')}
          {validation.errors.user_id && <div className="u-field-error" role="alert">{validation.errors.user_id}</div>}
        </div>
        <div>
          <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="cap-label">{t('capacity.proyecto')}</label>
          <Select suelto placeholder={false} id={`${idCampo}-2`} value={form.project_id} onChange={setField('project_id')} className="cap-input">
            <option value="">{t('capacity.sin_proyecto_disponible')}</option>
            {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
          </Select>{msg('project_id')}
        </div>
        <div className="u-grid2-12">
          <div>
            <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="cap-label">{t('capacity.semana')}</label>
            <DateInput id={`${idCampo}-3`} value={form.week_start}
              onChange={e => {
                setForm(current => ({ ...current, week_start: monday(e.target.value) }))
                validation.clearFieldError('week_start')
              }} className="cap-input" aria-invalid={!!validation.errors.week_start} />{msg('week_start')}
            {validation.errors.week_start && <div className="u-field-error" role="alert">{validation.errors.week_start}</div>}
          </div>
          <div>
            <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="cap-label">{t('capacity.horas_planificadas')}</label>
            <Input id={`${idCampo}-4`} aria-labelledby={`${idCampo}-et4`} type="number" value={form.planned_hours} min="1" max={2 * capacidadSemanal} step="0.5" onChange={setField('planned_hours')} aria-invalid={!!validation.errors.planned_hours} inputClassName="cap-input" />{msg('planned_hours')}
            {validation.errors.planned_hours && <div className="u-field-error" role="alert">{validation.errors.planned_hours}</div>}
          </div>
        </div>
        <div>
          <label id={`${idCampo}-eta183`} htmlFor={`${idCampo}-a183`} className="cap-label">{t('capacity.notas')}</label>
          <Input id={`${idCampo}-a183`} aria-labelledby={`${idCampo}-eta183`} value={form.notes} onChange={setField('notes')} placeholder={t('capacity.notas_de_la_asignacion')} inputClassName="cap-input" />{msg('notes')}
        </div>
      </div>
      <div className="u-actions-8">
        <Button variant="secondary" onClick={onClose}>{t('capacity.cancelar')}</Button>
        <Button onClick={submit} loading={isPending} disabled={isPending}>
          {t('capacity.asignar')}
        </Button>
      </div>
    </Modal>
  )
}

// ── Celda de capacidad con drag & drop ────────────────────────────────────────
function CapCell({ userId, weekStart, plans, capacity, onDrop, onAdd }: {
  userId: string | number
  weekStart: string
  plans: CapacityPlan[]
  capacity: number
  onDrop: (planId: string | number, userId: string | number, weekStart: string) => void
  onAdd: (prefill: AssignPrefill) => void
}) {
  const t = useAppT()
  const toast = useToast()
  const [dragOver, setDragOver] = useState(false)
  const qc = useQueryClient()

  const committed = plans.reduce((s, p) => s + (p.planned_hours || 0), 0)
  const loadPct   = capacity > 0 ? Math.round((committed / capacity) * 100) : 0

  const { mutate: deletePlan } = useMutation({
    mutationFn: (id: string | number) => capacityApi.deletePlan(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['capacity-board'] }); qc.invalidateQueries({ queryKey: ['forecast-heatmap'] }); qc.invalidateQueries({ queryKey: ['forecast-summary'] }); toast.success(t('capacity.toast_eliminada')) },
    onError: e => toast.error(extractErr(e, GENERIC_ERROR_FALLBACK)),
  })

  return (
    <div
      onDragOver={e => { e.preventDefault(); setDragOver(true) }}
      onDragLeave={() => setDragOver(false)}
      onDrop={e => {
        e.preventDefault()
        setDragOver(false)
        const data = JSON.parse(e.dataTransfer.getData('application/json') || '{}')
        if (data.planId) onDrop(data.planId, userId, weekStart)
      }}
      onClick={() => plans.length === 0 && onAdd({ user_id: userId, week_start: weekStart })}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if ((e.key === 'Enter' || e.key === ' ') && plans.length === 0) {
          e.preventDefault()
          onAdd({ user_id: userId, week_start: weekStart })
        }
      }}
      aria-label={committed > 0
        ? t('capacity.celda_carga', { semana: weekLabel(weekStart), pct: fmtNumber(loadPct, 0) })
        : t('capacity.celda_vacia', { semana: weekLabel(weekStart) })}
      className={['cap-cell', committed > 0 && 'cap-cell--loaded', dragOver && 'cap-cell--over'].filter(Boolean).join(' ')}
    >

      {/* Contenido */}
      <div className="cap-cell__content">
        {committed > 0 && (
          <div className="cap-cell__pct">
            {fmtNumber(loadPct, 0)}%
          </div>
        )}
        {plans.map(plan => (
          <div
            key={plan.id}
            draggable
            role="button"
            tabIndex={0}
            className="cap-plan"
            onDragStart={e => {
              e.stopPropagation()
              e.dataTransfer.setData('application/json', JSON.stringify({ planId: plan.id }))
            }}
            title={t('capacity.plan_title', { proyecto: plan.project_name || t('capacity.sin_proyecto'), horas: fmtHours(plan.planned_hours) })}
          >
            <span className="cap-plan__name">
              {(plan.project_name || t('capacity.libre')).slice(0, 7)}
            </span>
            <span className="cap-plan__hours">
              {fmtHours(plan.planned_hours)}
            </span>
            <Pulsable
              type="button"
              className="cap-plan__remove"
              aria-label={t('capacity.eliminar_plan', { proyecto: plan.project_name || t('capacity.libre'), horas: fmtHours(plan.planned_hours) })}
              onClick={e => { e.stopPropagation(); openConfirmGlobal({ message: t('capacity.confirmar_eliminar', { horas: fmtHours(plan.planned_hours), proyecto: plan.project_name || t('capacity.libre') }), onConfirm: () => deletePlan(plan.id), danger: true }) }}
              onKeyDown={e => e.stopPropagation()}>
              <X size={10} aria-hidden="true" />
            </Pulsable>
          </div>
        ))}
        {committed === 0 && (
          <div className="cap-cell__plus" aria-hidden="true"><Plus size={14} /></div>
        )}
      </div>
    </div>
  )
}

export default function CapacityPage(): JSX.Element {
  const t = useAppT()
  const umbrales = useUmbrales()
  const toast = useToast()
  const qc = useQueryClient()
  const { weekly_capacity_hours: capacidadSemanal } = useOrgSettings() // 18-11-2026: capacidad por defecto de la empresa
  const [weeksAhead, setWeeksAhead] = useState(8)
  const [showAssign, setShowAssign] = useState(false)
  const [assignPrefill, setAssignPrefill] = useState<AssignPrefill | null>(null)
  const [deptFilter, setDeptFilter]       = useState('')

  const weekStarts = Array.from({ length: weeksAhead }, (_, i) =>
    addWeeks(monday(new Date()), i)
  )

  const { data: users = [] } = useQuery<UserItem[]>({
    // Capacidad semanal: solo la ficha completa la trae (`PersonaInterna` no); clave propia porque filtra.
    queryKey: ['users', 'capacidad'],
    queryFn: () => usersApi.list({}).then(r => r.data.filter(esFichaCompleta).filter((u) => u.is_active)),
  })

  const { data: board = [], isLoading } = useQuery<CapacityPlan[]>({
    queryKey: ['capacity-board', weeksAhead],
    queryFn: () => capacityApi.board({
      week_from: weekStarts[0],
      week_to:   weekStarts[weekStarts.length - 1],
    }).then(r => r.data),
    staleTime: STALE_SHORT_MS,
  })

  const { mutate: movePlan } = useMutation({
    mutationFn: ({ id, user_id, week_start }: { id: string | number; user_id: string | number; week_start: string }) =>
      capacityApi.updatePlan(id, { user_id, week_start }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['capacity-board'] })
      qc.invalidateQueries({ queryKey: ['forecast-heatmap'] })
      qc.invalidateQueries({ queryKey: ['forecast-summary'] })
      toast.success(t('capacity.toast_movida'))
    },
    onError: e => toast.error(extractErr(e, t('capacity.error_mover'))),
  })

  // Construir mapa de planes: { userId_weekStart: [plans] }
  const planMap: Record<string, CapacityPlan[]> = {}
  for (const plan of board) {
    const key = `${plan.user_id}_${plan.week_start}`
    if (!planMap[key]) planMap[key] = []
    planMap[key].push(plan)
  }

  const displayUsers = deptFilter
    ? users.filter(u => (u.department || '').toLowerCase().includes(deptFilter.toLowerCase()))
    : users

  const departments: string[] = [...new Set<string>(users.map((u) => u.department).filter((v): v is string => Boolean(v)))]

  // Calcular KPIs de capacidad
  const totalAssignments = board.length
  const uniqueWeeksWithLoad = new Set(board.map(p => p.week_start)).size

  return (
    <PageShell>
      <PageHeader
        icon={<TrendingUp size={18} />}
        title={t('nav.capacity')}
        subtitle={t('capacity.subtitle')}
        actions={<Button icon={<Plus size={14} />} onClick={() => { setAssignPrefill(null); setShowAssign(true) }}>{t('capacity.nueva_asignacion')}</Button>}
      />

      {/* KPI bar */}
      <div className="ds-grid-stats cap-kpis">
        <KpiCard icon={<Users size={16} />} label={t('capacity.kpi_personas')} value={fmtNumber(users.length, 0)} />
        <KpiCard icon={<Building2 size={16} />} label={t('capacity.kpi_departamentos')} value={fmtNumber(departments.length, 0)} />
        <KpiCard icon={<ClipboardList size={16} />} label={t('capacity.kpi_asignaciones')} value={fmtNumber(totalAssignments, 0)} />
        <KpiCard icon={<CalendarRange size={16} />} label={t('capacity.kpi_semanas')} value={fmtNumber(uniqueWeeksWithLoad, 0)} />
      </div>

      {/* Controles */}
      <div className="ds-toolbar cap-controls">
        <Select suelto placeholder={false} value={weeksAhead} onChange={e => setWeeksAhead(+e.target.value)} className="ds-input cap-select" aria-label={t('capacity.horizonte')}>
          {[4, 8, 13, 26].map(n => <option key={n} value={n}>{t('capacity.n_semanas', { count: n })}</option>)}
        </Select>
        <Select suelto placeholder={false} value={deptFilter} onChange={e => setDeptFilter(e.target.value)} className="ds-input cap-select cap-select--dept" aria-label={t('capacity.departamento')}>
          <option value="">{t('capacity.todos_los_departamentos')}</option>
          {departments.map(d => <option key={d} value={d}>{d}</option>)}
        </Select>
        <div className="cap-controls__hint">
          <Info size={13} aria-hidden="true" /> {t('capacity.arrastra_para_mover_clic_en_para_anadir')}
        </div>
      </div>

      {/* Tabla drag-and-drop */}
      {isLoading ? (
        <div className="cap-loading" role="status">{t('capacity.cargando')}</div>
      ) : displayUsers.length === 0 ? (
        <div className="ds-card">
          <EmptyState icon={<Users size={28} />} title={t('capacity.sin_personas_disponibles')} description={t('capacity.sin_personas_desc')} />
        </div>
      ) : (
        <RejillaPersonaDia
          titulo={t('nav.capacity')}
          cabeceraFilas={t('capacity.col_persona')}
          unidad="semana"
          filas={displayUsers.map(u => ({
            id: String(u.id), nombre: u.full_name, usuario: u,
            sub: [u.department, `${t('capacity.col_capacidad')} ${fmtHours(u.weekly_capacity_hours || capacidadSemanal)}`].filter(Boolean).join(' · '),
          }))}
          columnas={columnasDeSemanas(weekStarts)}
          celda={(fila, col) => {
            const u = fila.usuario
            const plans = planMap[`${u.id}_${col.clave}`] || []
            const capacidad = u.weekly_capacity_hours || capacidadSemanal
            const horas = plans.reduce((s, p) => s + (p.planned_hours || 0), 0)
            return {
              estado: horas > 0 ? estadoDeCarga(capacidad > 0 ? (horas / capacidad) * 100 : 0, umbrales) : undefined,
              contenido: (
                <CapCell
                  userId={u.id}
                  weekStart={col.clave}
                  plans={plans}
                  capacity={capacidad}
                  onDrop={(planId, newUserId, newWeek) => movePlan({ id: planId, user_id: newUserId, week_start: newWeek })}
                  onAdd={(prefill) => { setAssignPrefill(prefill); setShowAssign(true) }}
                />
              ),
            }
          }}
          leyenda={LEYENDA.map(l => ({ clave: l.clave, tono: l.tono, etiqueta: t(`capacity.leyenda_${l.clave}`) }))}
        />
      )}

      {showAssign && (
        <AssignModal prefill={assignPrefill} onClose={() => setShowAssign(false)} />
      )}
    </PageShell>
  )
}
