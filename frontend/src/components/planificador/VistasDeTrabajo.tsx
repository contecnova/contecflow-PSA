/**
 * VistasDeTrabajo — tabla editable en línea, línea temporal, calendario y carga
 * por persona, con vistas guardadas (rev. 173). La usan Tareas (además del
 * Kanban y la lista) y la pestaña Tareas de la ficha del proyecto.
 *
 * Una vista guardada guarda su tipo y su configuración (columnas de la tabla y
 * filtros de estado y persona) en el modelo único de vistas (`/planning/views`).
 */
import { useMemo, useState, type CSSProperties } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bookmark, CalendarDays, ChevronLeft, ChevronRight, GanttChartSquare, Save, Table2, Trash2, Users } from 'lucide-react'
import { planificacionApi, tasksApi, usersApi, type TaskListItem, type VistaGuardada } from '../../services/api'
import type { TaskUpdatePayload } from '../../services/api/tasks'
import { Button, EmptyState, Spinner } from '../ui'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { useAuth } from '../../context/AuthContext'
import { extractErr, fmtDate, localeActivo } from '../../utils/helpers'
import { SCHEDULE_TASKS_LIST_SIZE } from '../../constants/pagination'
import { STALE_DEFAULT_MS } from '../../constants/timings'
import './planificador.css'

export const VISTAS_DE_TRABAJO = ['table', 'timeline', 'calendar', 'workload'] as const
export type VistaDeTrabajo = typeof VISTAS_DE_TRABAJO[number]

const ESTADOS = ['backlog', 'todo', 'in_progress', 'blocked', 'in_review', 'done'] as const
const PRIORIDADES = ['critical', 'high', 'medium', 'low'] as const
const COLUMNAS = ['status', 'assignee', 'priority', 'estimated_hours', 'progress_pct', 'start_date', 'due_date', 'total_float_days'] as const
type Columna = typeof COLUMNAS[number]

type Config = { columns?: Columna[]; status?: string; assignee?: string }

const DIA_MS = 86400000
const aFecha = (s: string) => new Date(`${s.slice(0, 10)}T00:00:00`)

export default function VistasDeTrabajo({ projectId, vista: vistaExterna, onVista }: {
  projectId?: string; vista?: VistaDeTrabajo; onVista?: (v: VistaDeTrabajo) => void
}) {
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const { hasRole } = useAuth()
  const [vistaLocal, setVistaLocal] = useState<VistaDeTrabajo>('table')
  const vista = vistaExterna ?? vistaLocal
  const cambiarVista = (v: VistaDeTrabajo) => (onVista ? onVista(v) : setVistaLocal(v))
  const [config, setConfig] = useState<Config>({ columns: [...COLUMNAS] })
  const [vistaGuardada, setVistaGuardada] = useState<string>('')

  const { data: tareas = [], isLoading } = useQuery({
    queryKey: ['tasks', 'vistas', projectId ?? 'todas'],
    queryFn: () => tasksApi.list({ ...(projectId ? { project_id: projectId } : {}), page_size: SCHEDULE_TASKS_LIST_SIZE }).then(r => r.data),
  })
  const { data: personas = [] } = useQuery({
    queryKey: ['users', 'directory'],
    queryFn: () => usersApi.directory().then(r => r.data),
    staleTime: STALE_DEFAULT_MS,
  })
  const { data: guardadas = [] } = useQuery({
    queryKey: ['vistas', projectId ?? ''],
    queryFn: () => planificacionApi.vistas({ entity_type: 'task', ...(projectId ? { project_id: projectId } : {}) }),
  })

  const filtradas = useMemo(() => tareas.filter(x =>
    (!config.status || x.status === config.status) && (!config.assignee || x.assignee_id === config.assignee)), [tareas, config])

  const onError = (e: unknown) => toast.error(extractErr(e, t('planificador.error_generico')))
  const editar = useMutation({
    mutationFn: ({ id, cambios }: { id: string; cambios: TaskUpdatePayload }) => tasksApi.update(id, cambios),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['tasks'] }); qc.invalidateQueries({ queryKey: ['plan'] }) },
    onError,
  })
  const guardar = useMutation({
    mutationFn: (nombre: string) => planificacionApi.crearVista({ name: nombre, entity_type: 'task', view_type: vista, project_id: projectId ?? null, config: config as Record<string, unknown> }),
    onSuccess: v => { toast.success(t('planificador.vista_guardada')); setVistaGuardada(v.id); qc.invalidateQueries({ queryKey: ['vistas'] }) },
    onError,
  })
  const borrar = useMutation({
    mutationFn: (id: string) => planificacionApi.borrarVista(id),
    onSuccess: () => { setVistaGuardada(''); qc.invalidateQueries({ queryKey: ['vistas'] }) },
    onError,
  })

  const aplicarGuardada = (id: string) => {
    setVistaGuardada(id)
    const v = guardadas.find((x: VistaGuardada) => x.id === id)
    if (!v) return
    if (v.view_type && (VISTAS_DE_TRABAJO as readonly string[]).includes(v.view_type)) cambiarVista(v.view_type as VistaDeTrabajo)
    setConfig({ columns: [...COLUMNAS], ...(v.config as Config) })
  }

  const puedeEditar = hasRole('admin', 'pm', 'team_lead', 'employee')
  const iconos: Record<VistaDeTrabajo, JSX.Element> = {
    table: <Table2 size={12} />, timeline: <GanttChartSquare size={12} />, calendar: <CalendarDays size={12} />, workload: <Users size={12} />,
  }

  return (
    <div className="plan-stack">
      <div className="plan-row plan-row--between">
        {/* 16-11-2026: si la página controla la vista (onVista), ya pinta su
            propia barra de pestañas; aquí no se repite el selector. */}
        {!onVista ? (
          <div className="ds-segmented" role="group" aria-label={t('planificador.vistas')}>
            {VISTAS_DE_TRABAJO.map(v => (
              <button key={v} type="button" aria-pressed={vista === v} onClick={() => cambiarVista(v)}>
                {iconos[v]} {t(`planificador.vista_${v}`)}
              </button>
            ))}
          </div>
        ) : <span />}
        <div className="plan-row">
          <Bookmark size={13} aria-hidden />
          <select className="plan-select" aria-label={t('planificador.vistas_guardadas')} value={vistaGuardada} onChange={e => aplicarGuardada(e.target.value)}>
            <option value="">{t('planificador.vistas_guardadas')}</option>
            {guardadas.map((v: VistaGuardada) => <option key={v.id} value={v.id}>{v.name}{v.is_shared ? ` · ${t('planificador.compartida')}` : ''}</option>)}
          </select>
          <Button size="xs" variant="subtle" icon={<Save size={12} />}
            onClick={() => { const n = window.prompt(t('planificador.nombre_de_vista')); if (n?.trim()) guardar.mutate(n.trim()) }}>
            {t('planificador.guardar_vista')}
          </Button>
          {vistaGuardada && (
            <Button size="xs" variant="ghost" icon={<Trash2 size={12} />} onClick={() => borrar.mutate(vistaGuardada)}>
              {t('planificador.borrar')}
            </Button>
          )}
        </div>
      </div>

      <div className="plan-row">
        <select className="plan-select" aria-label={t('planificador.filtro_estado')} value={config.status ?? ''}
          onChange={e => setConfig(c => ({ ...c, status: e.target.value || undefined }))}>
          <option value="">{t('planificador.todos_los_estados')}</option>
          {ESTADOS.map(s => <option key={s} value={s}>{t(`planificador.estado_${s}`)}</option>)}
        </select>
        <select className="plan-select" aria-label={t('planificador.filtro_persona')} value={config.assignee ?? ''}
          onChange={e => setConfig(c => ({ ...c, assignee: e.target.value || undefined }))}>
          <option value="">{t('planificador.todas_las_personas')}</option>
          {personas.map(p => <option key={p.id} value={p.id}>{p.full_name}</option>)}
        </select>
        {vista === 'table' && (
          <details className="plan-chip">
            <summary>{t('planificador.columnas')}</summary>
            {COLUMNAS.map(c => (
              <label key={c} className="plan-row">
                <input type="checkbox" checked={(config.columns ?? []).includes(c)}
                  onChange={e => setConfig(x => ({ ...x, columns: e.target.checked ? [...(x.columns ?? []), c] : (x.columns ?? []).filter(y => y !== c) }))} />
                {t(`planificador.columna_${c}`)}
              </label>
            ))}
          </details>
        )}
      </div>

      {isLoading ? <Spinner /> : vista === 'workload' ? <CargaPorPersona projectId={projectId} /> : filtradas.length === 0 ? (
        <EmptyState title={t('planificador.sin_tareas')} description={t('planificador.sin_tareas_filtro')} />
      ) : vista === 'table' ? (
        <TablaEditable tareas={filtradas} columnas={config.columns ?? [...COLUMNAS]} personas={personas}
          editable={puedeEditar} onCambio={(id, cambios) => editar.mutate({ id, cambios })} />
      ) : vista === 'timeline' ? <LineaTemporal tareas={filtradas} /> : <Calendario tareas={filtradas} />}
    </div>
  )
}

// ── Tabla editable ───────────────────────────────────────────────────────────

function TablaEditable({ tareas, columnas, personas, editable, onCambio }: {
  tareas: TaskListItem[]; columnas: Columna[]; personas: { id: string; full_name: string }[]
  editable: boolean; onCambio: (id: string, cambios: TaskUpdatePayload) => void
}) {
  const t = useAppT()
  const ver = (c: Columna) => columnas.includes(c)
  const num = (v: string) => (v === '' ? null : Number(v))
  return (
    <div className="plan-card plan-tabla-scroll">
      <table className="plan-tabla">
        <thead>
          <tr>
            <th>{t('planificador.col_tarea')}</th>
            {COLUMNAS.filter(ver).map(c => <th key={c}>{t(`planificador.columna_${c}`)}</th>)}
          </tr>
        </thead>
        <tbody>
          {tareas.map(x => (
            <tr key={x.id}>
              <td>
                {editable ? (
                  <input className="plan-input" aria-label={t('planificador.col_tarea')} defaultValue={x.title}
                    onBlur={e => e.target.value.trim() && e.target.value !== x.title && onCambio(x.id, { title: e.target.value.trim() })} />
                ) : x.title}
                <div className="plan-muted">{x.code}{x.is_critical ? ` · ${t('planificador.critica')}` : ''}</div>
              </td>
              {ver('status') && <td>
                <select className="plan-select" disabled={!editable} aria-label={t('planificador.columna_status')} value={x.status}
                  onChange={e => onCambio(x.id, { status: e.target.value as TaskListItem['status'] })}>
                  {ESTADOS.map(s => <option key={s} value={s}>{t(`planificador.estado_${s}`)}</option>)}
                </select>
              </td>}
              {ver('assignee') && <td>
                <select className="plan-select" disabled={!editable} aria-label={t('planificador.columna_assignee')} value={x.assignee_id ?? ''}
                  onChange={e => onCambio(x.id, { assignee_id: e.target.value || null })}>
                  <option value="">{t('planificador.sin_asignar')}</option>
                  {personas.map(p => <option key={p.id} value={p.id}>{p.full_name}</option>)}
                </select>
              </td>}
              {ver('priority') && <td>
                <select className="plan-select" disabled={!editable} aria-label={t('planificador.columna_priority')} value={x.priority}
                  onChange={e => onCambio(x.id, { priority: e.target.value as TaskListItem['priority'] })}>
                  {PRIORIDADES.map(p => <option key={p} value={p}>{t(`planificador.prioridad_${p}`)}</option>)}
                </select>
              </td>}
              {ver('estimated_hours') && <td>
                <input type="number" min={0} className="plan-input plan-input--num" disabled={!editable} aria-label={t('planificador.columna_estimated_hours')}
                  defaultValue={x.estimated_hours ?? ''} onBlur={e => num(e.target.value) !== x.estimated_hours && Number(e.target.value) > 0 && onCambio(x.id, { estimated_hours: num(e.target.value) })} />
              </td>}
              {ver('progress_pct') && <td>
                <input type="number" min={0} max={100} className="plan-input plan-input--num" disabled={!editable} aria-label={t('planificador.columna_progress_pct')}
                  defaultValue={x.progress_pct ?? ''} onBlur={e => num(e.target.value) !== (x.progress_pct ?? null) && onCambio(x.id, { progress_pct: num(e.target.value) })} />
              </td>}
              {ver('start_date') && <td>
                <input type="date" className="plan-input plan-input--fecha" disabled={!editable} aria-label={t('planificador.columna_start_date')}
                  defaultValue={x.start_date ?? ''} onBlur={e => (e.target.value || null) !== x.start_date && onCambio(x.id, { start_date: e.target.value || null })} />
              </td>}
              {ver('due_date') && <td>
                <input type="date" className="plan-input plan-input--fecha" disabled={!editable} aria-label={t('planificador.columna_due_date')}
                  defaultValue={x.due_date ?? ''} onBlur={e => (e.target.value || null) !== x.due_date && onCambio(x.id, { due_date: e.target.value || null })} />
              </td>}
              {ver('total_float_days') && <td className={`plan-num ${x.is_critical ? 'plan-critica' : ''}`}>{x.total_float_days ?? '—'}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Línea temporal ───────────────────────────────────────────────────────────

function LineaTemporal({ tareas }: { tareas: TaskListItem[] }) {
  const t = useAppT()
  const con = tareas.filter(x => x.start_date && x.due_date)
  if (con.length === 0) return <EmptyState title={t('planificador.sin_fechas')} />
  const fechas = con.flatMap(x => [x.start_date!, x.due_date!, x.baseline_start, x.baseline_end].filter(Boolean) as string[]).map(aFecha)
  const min = Math.min(...fechas.map(d => d.getTime()))
  const max = Math.max(...fechas.map(d => d.getTime())) + DIA_MS
  const pct = (s: string) => ((aFecha(s).getTime() - min) / (max - min)) * 100
  const ancho = (a: string, b: string) => Math.max(((aFecha(b).getTime() + DIA_MS - aFecha(a).getTime()) / (max - min)) * 100, 0.5)
  return (
    <div className="plan-card plan-stack">
      <div className="plan-row plan-row--between plan-muted"><span>{fmtDate(new Date(min).toISOString())}</span><span>{fmtDate(new Date(max - DIA_MS).toISOString())}</span></div>
      {con.map(x => (
        <div key={x.id} className="plan-stack">
          <span className="plan-row plan-row--between">
            <span className={x.is_critical ? 'plan-critica' : ''}>{x.code} {x.title}</span>
            <span className="plan-muted">{fmtDate(x.start_date)} – {fmtDate(x.due_date)}</span>
          </span>
          <div className="plan-linea" role="img" aria-label={`${x.title}: ${fmtDate(x.start_date)} – ${fmtDate(x.due_date)}`}>
            <div className={`plan-linea__barra${x.is_critical ? ' plan-linea__barra--critica' : ''}`}
              style={{ '--plan-izq': `${pct(x.start_date!)}%`, '--plan-ancho': `${ancho(x.start_date!, x.due_date!)}%` } as CSSProperties} />
            {x.baseline_start && x.baseline_end && (
              <div className="plan-linea__base" title={t('planificador.linea_base')}
                style={{ '--plan-izq': `${pct(x.baseline_start)}%`, '--plan-ancho': `${ancho(x.baseline_start, x.baseline_end)}%` } as CSSProperties} />
            )}
          </div>
        </div>
      ))}
    </div>
  )
}

// ── Calendario ───────────────────────────────────────────────────────────────

function Calendario({ tareas }: { tareas: TaskListItem[] }) {
  const t = useAppT()
  const hoy = new Date()
  const [mes, setMes] = useState(new Date(hoy.getFullYear(), hoy.getMonth(), 1))
  const primerDia = (mes.getDay() + 6) % 7
  const dias = new Date(mes.getFullYear(), mes.getMonth() + 1, 0).getDate()
  const celdas = Array.from({ length: Math.ceil((primerDia + dias) / 7) * 7 }, (_, i) => i - primerDia + 1)
  const clave = (d: number) => `${mes.getFullYear()}-${String(mes.getMonth() + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`
  const enDia = (d: number) => {
    const k = clave(d)
    return tareas.filter(x => {
      const ini = x.start_date ?? x.due_date
      return ini && x.due_date && ini <= k && k <= x.due_date
    })
  }
  const semana = Array.from({ length: 7 }, (_, i) => new Date(2024, 0, 1 + i).toLocaleDateString(localeActivo(), { weekday: 'short' }))
  return (
    <div className="plan-card plan-stack">
      <div className="plan-row plan-row--between">
        <Button size="xs" variant="subtle" icon={<ChevronLeft size={12} />} onClick={() => setMes(new Date(mes.getFullYear(), mes.getMonth() - 1, 1))}>{t('planificador.mes_anterior')}</Button>
        <strong>{mes.toLocaleDateString(localeActivo(), { month: 'long', year: 'numeric' })}</strong>
        <Button size="xs" variant="subtle" icon={<ChevronRight size={12} />} onClick={() => setMes(new Date(mes.getFullYear(), mes.getMonth() + 1, 1))}>{t('planificador.mes_siguiente')}</Button>
      </div>
      <div className="plan-cal">
        {semana.map(d => <div key={d} className="plan-cal__cab">{d}</div>)}
        {celdas.map((d, i) => d < 1 || d > dias ? <div key={i} className="plan-cal__dia plan-cal__dia--fuera plan-cal__dia--vacio" /> : (
          <div key={i} className="plan-cal__dia">
            <span className="plan-cal__num">{d}</span>
            {enDia(d).map(x => <span key={x.id} className={`plan-cal__tarea${x.is_critical ? ' plan-cal__tarea--critica' : ''}`}>{x.code} {x.title}</span>)}
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Carga por persona ────────────────────────────────────────────────────────

function CargaPorPersona({ projectId }: { projectId?: string }) {
  const t = useAppT()
  const { data, isLoading } = useQuery({
    queryKey: ['carga', projectId ?? ''],
    queryFn: () => planificacionApi.carga({ ...(projectId ? { project_id: projectId } : {}) }),
  })
  if (isLoading) return <Spinner />
  if (!data || data.people.length === 0) return <EmptyState title={t('planificador.sin_carga')} />
  const colores: Record<string, CSSProperties> = {
    over: { '--plan-carga-fondo': 'var(--danger-bg)', '--plan-carga-color': 'var(--danger)' } as CSSProperties,
    under: { '--plan-carga-fondo': 'var(--warning-bg)', '--plan-carga-color': 'var(--warning)' } as CSSProperties,
    ok: { '--plan-carga-fondo': 'var(--success-bg)', '--plan-carga-color': 'var(--success)' } as CSSProperties,
  }
  return (
    <div className="plan-card plan-tabla-scroll">
      <table className="plan-tabla">
        <thead>
          <tr>
            <th>{t('planificador.col_persona')}</th>
            {data.people[0].weeks.map(w => <th key={w.week} className="plan-num">{fmtDate(w.week)}</th>)}
          </tr>
        </thead>
        <tbody>
          {data.people.map(p => (
            <tr key={p.user_id}>
              <td>{p.name ?? p.user_id}</td>
              {p.weeks.map(w => (
                <td key={w.week} className="plan-num">
                  <span className="plan-carga" style={colores[w.state]}
                    title={t('planificador.carga_detalle', { h: w.hours, c: w.capacity, p: w.project_hours ?? w.hours })}>
                    {w.pct == null ? '—' : `${Math.round(w.pct)} %`}
                  </span>
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="plan-muted">{t('planificador.carga_leyenda')}</p>
    </div>
  )
}
