/**
 * VistasDeTrabajo — tabla editable en línea, línea temporal, calendario y carga
 * por persona, con vistas guardadas (rev. 173). La usan Tareas (además del
 * Kanban y la lista) y la pestaña Tareas de la ficha del proyecto.
 *
 * Una vista guardada guarda su tipo y su configuración (columnas de la tabla y
 * filtros de estado y persona) en el modelo único de vistas (`/planning/views`).
 *
 * 16-11-2026 (diseño único): una sola barra `ds-toolbar` con filtros, columnas
 * y vistas guardadas; la tabla es la del kit (`contecflow-table`) y cada celda
 * MUESTRA su valor (StatusBadge, Avatar, números alineados) y se edita en el
 * sitio al pulsarla (clic, Enter o F2) con los campos del kit; el calendario
 * usa `NavegadorDeMes` y la carga por persona la rejilla única
 * `RejillaPersonaDia`.
 */
import { useCallback, useEffect, useId, useMemo, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CalendarDays, Columns3, GanttChartSquare, Save, Table2, Trash2, Users } from 'lucide-react'
import { planificacionApi, tasksApi, usersApi, type TaskListItem, type VistaGuardada } from '../../services/api'
import type { TaskUpdatePayload } from '../../services/api/tasks'
import { Avatar, Button, EmptyState, NavegadorDeMes, RejillaPersonaDia, Spinner, StatusBadge, columnasDeSemanas, isoLocal } from '../ui'
import type { StatusBadgeKind } from '../ui/StatusBadge'
import { CampoFecha } from '../ui/SelectorDeFecha'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { useConfirm } from '../../context/ConfirmContext'
import { useAuth } from '../../context/AuthContext'
import { extractErr, fmtDate, fmtNumber, formateadorDeFecha } from '../../utils/helpers'
import { SCHEDULE_TASKS_LIST_SIZE } from '../../constants/pagination'
import { STALE_DEFAULT_MS } from '../../constants/timings'
import './planificador.css'

export const VISTAS_DE_TRABAJO = ['table', 'timeline', 'calendar', 'workload'] as const
export type VistaDeTrabajo = typeof VISTAS_DE_TRABAJO[number]

const ESTADOS = ['backlog', 'todo', 'in_progress', 'blocked', 'in_review', 'done'] as const
const PRIORIDADES = ['critical', 'high', 'medium', 'low'] as const
const COLUMNAS = ['status', 'assignee', 'priority', 'estimated_hours', 'progress_pct', 'start_date', 'due_date', 'total_float_days'] as const
type Columna = typeof COLUMNAS[number]

const TONO_DE_ESTADO: Record<string, StatusBadgeKind> = {
  backlog: 'neutral', todo: 'neutral', in_progress: 'accent', blocked: 'danger', in_review: 'purple', done: 'success',
}
const TONO_DE_PRIORIDAD: Record<string, StatusBadgeKind> = { critical: 'danger', high: 'orange', medium: 'info', low: 'neutral' }

type Config = { columns?: Columna[]; status?: string; assignee?: string }
type Persona = { id: string; full_name: string; avatar_url?: string | null }

const DIA_MS = 86400000
const aFecha = (s: string) => new Date(`${s.slice(0, 10)}T00:00:00`)
/** Fecha 'YYYY-MM-DD' en hora local (sin desplazarse un día por la zona horaria). */
const fmtDia = (s?: string | null) => (s ? fmtDate(aFecha(s)) : '—')

export default function VistasDeTrabajo({ projectId, vista: vistaExterna, onVista }: {
  projectId?: string; vista?: VistaDeTrabajo; onVista?: (v: VistaDeTrabajo) => void
}) {
  const t = useAppT()
  const toast = useToast()
  const { pedirTexto } = useConfirm()
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
    table: <Table2 size={14} />, timeline: <GanttChartSquare size={14} />, calendar: <CalendarDays size={14} />, workload: <Users size={14} />,
  }

  return (
    <div className="plan-stack">
      {/* Una sola barra: vista (si la página no la controla), filtros, columnas
          y, a la derecha, las vistas guardadas. Todo a 38 px (md del kit). */}
      <div className="ds-toolbar plan-vbarra">
        {!onVista && (
          <div className="ds-segmented" role="group" aria-label={t('planificador.vistas')}>
            {VISTAS_DE_TRABAJO.map(v => (
              <button key={v} type="button" aria-pressed={vista === v} onClick={() => cambiarVista(v)}>
                {iconos[v]} {t(`planificador.vista_${v}`)}
              </button>
            ))}
          </div>
        )}
        {vista !== 'workload' && (
          <>
            <select className="ds-input plan-vbarra__select" aria-label={t('planificador.filtro_estado')} value={config.status ?? ''}
              onChange={e => setConfig(c => ({ ...c, status: e.target.value || undefined }))}>
              <option value="">{t('planificador.todos_los_estados')}</option>
              {ESTADOS.map(s => <option key={s} value={s}>{t(`planificador.estado_${s}`)}</option>)}
            </select>
            <select className="ds-input plan-vbarra__select" aria-label={t('planificador.filtro_persona')} value={config.assignee ?? ''}
              onChange={e => setConfig(c => ({ ...c, assignee: e.target.value || undefined }))}>
              <option value="">{t('planificador.todas_las_personas')}</option>
              {personas.map(p => <option key={p.id} value={p.id}>{p.full_name}</option>)}
            </select>
          </>
        )}
        {vista === 'table' && (
          <SelectorDeColumnas visibles={config.columns ?? [...COLUMNAS]}
            onCambiar={cols => setConfig(x => ({ ...x, columns: cols }))} />
        )}
        <div className="ds-toolbar__spacer" />
        <select className="ds-input plan-vbarra__select" aria-label={t('planificador.vistas_guardadas')} value={vistaGuardada} onChange={e => aplicarGuardada(e.target.value)}>
          <option value="">{t('planificador.vistas_guardadas')}</option>
          {guardadas.map((v: VistaGuardada) => <option key={v.id} value={v.id}>{v.name}{v.is_shared ? ` · ${t('planificador.compartida')}` : ''}</option>)}
        </select>
        <Button size="md" variant="secondary" icon={<Save size={14} />} loading={guardar.isPending}
          onClick={async () => { const n = await pedirTexto({ message: t('planificador.nombre_de_vista'), required: true }); if (n?.trim()) guardar.mutate(n.trim()) }}>
          {t('planificador.guardar_vista')}
        </Button>
        {vistaGuardada && (
          <Button size="md" variant="ghost" icon={<Trash2 size={14} />} onClick={() => borrar.mutate(vistaGuardada)}>
            {t('planificador.borrar')}
          </Button>
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

// ── Selector de columnas ─────────────────────────────────────────────────────
// No usa `useColVisibility` del kit: aquí las columnas forman parte de la vista
// guardada (no de localStorage) y la columna fija (la tarea) no está en la lista.

function SelectorDeColumnas({ visibles, onCambiar }: { visibles: Columna[]; onCambiar: (cols: Columna[]) => void }) {
  const t = useAppT()
  const [abierto, setAbierto] = useState(false)
  const raiz = useRef<HTMLDivElement>(null)
  const idPanel = useId()

  useEffect(() => {
    if (!abierto) return
    const fuera = (e: MouseEvent) => { if (raiz.current && !raiz.current.contains(e.target as Node)) setAbierto(false) }
    const escape = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      e.preventDefault(); setAbierto(false)
      raiz.current?.querySelector<HTMLButtonElement>('button')?.focus()
    }
    document.addEventListener('mousedown', fuera)
    document.addEventListener('keydown', escape)
    return () => { document.removeEventListener('mousedown', fuera); document.removeEventListener('keydown', escape) }
  }, [abierto])

  return (
    <div ref={raiz} className="plan-columnas">
      <Button size="md" variant="secondary" icon={<Columns3 size={14} />} aria-expanded={abierto} aria-controls={idPanel}
        onClick={() => setAbierto(a => !a)}>
        {t('planificador.columnas')}
      </Button>
      {abierto && (
        <div id={idPanel} className="plan-columnas__panel" role="group" aria-label={t('planificador.columnas')}>
          {COLUMNAS.map(c => (
            <label key={c} className="plan-columnas__opcion">
              <input type="checkbox" checked={visibles.includes(c)}
                onChange={e => onCambiar(e.target.checked ? COLUMNAS.filter(x => x === c || visibles.includes(x)) : visibles.filter(y => y !== c))} />
              {t(`planificador.columna_${c}`)}
            </label>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Celda editable ───────────────────────────────────────────────────────────

/** Cierra el editor; devuelve `false` si ya estaba cerrado (para no guardar dos veces). */
type Cerrar = (devolverFoco: boolean) => boolean

/**
 * Celda que muestra su valor y, si es editable, se edita en el sitio: clic,
 * Enter o F2 abren el editor (con la misma altura de fila); Escape cancela,
 * Enter o salir del campo guardan, y el foco vuelve a la celda.
 */
function CeldaEditable({ columna, valorTexto, editable, className, extra, children, editor }: {
  columna: string; valorTexto: string; editable: boolean; className?: string
  /** Contenido fijo bajo el valor (código y «crítica» en la columna de tarea). */
  extra?: ReactNode
  children: ReactNode
  editor: (cerrar: Cerrar) => ReactNode
}) {
  const t = useAppT()
  const [editando, setEditando] = useState(false)
  const abierto = useRef(false)
  const volverFoco = useRef(false)
  const boton = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!editando && volverFoco.current) { volverFoco.current = false; boton.current?.focus() }
  }, [editando])

  const abrir = () => { abierto.current = true; setEditando(true) }
  const cerrar = useCallback<Cerrar>(foco => {
    if (!abierto.current) return false
    abierto.current = false
    volverFoco.current = foco
    setEditando(false)
    return true
  }, [])

  if (!editable) return <td className={className}>{children}{extra}</td>
  return (
    <td className={`plan-celda${className ? ` ${className}` : ''}`}>
      {editando ? <div className="plan-celda__editor">{editor(cerrar)}</div> : (
        <button ref={boton} type="button" className="plan-celda__ver"
          aria-label={t('planificador.editar_celda', { columna, valor: valorTexto })}
          onClick={abrir}
          onKeyDown={e => { if (e.key === 'F2') { e.preventDefault(); abrir() } }}>
          {children}
        </button>
      )}
      {extra}
    </td>
  )
}

function EditorTexto({ etiqueta, valor, numero, min, max, cerrar, onGuardar }: {
  etiqueta: string; valor: string; numero?: boolean; min?: number; max?: number
  cerrar: Cerrar; onGuardar: (v: string) => void
}) {
  const terminar = (v: string, foco: boolean) => { if (cerrar(foco)) onGuardar(v) }
  return (
    <input className={`ds-input plan-celda__campo${numero ? ' plan-celda__campo--num' : ''}`} autoFocus aria-label={etiqueta}
      type={numero ? 'number' : 'text'} min={min} max={max} defaultValue={valor}
      onFocus={e => e.currentTarget.select()}
      onKeyDown={e => {
        if (e.key === 'Enter') { e.preventDefault(); terminar(e.currentTarget.value, true) }
        else if (e.key === 'Escape') { e.preventDefault(); cerrar(true) }
      }}
      onBlur={e => terminar(e.currentTarget.value, false)} />
  )
}

function EditorLista({ etiqueta, valor, opciones, cerrar, onGuardar }: {
  etiqueta: string; valor: string; opciones: { valor: string; etiqueta: string }[]
  cerrar: Cerrar; onGuardar: (v: string) => void
}) {
  return (
    <select className="ds-input plan-celda__campo" autoFocus aria-label={etiqueta} value={valor}
      onChange={e => { const v = e.target.value; if (cerrar(true) && v !== valor) onGuardar(v) }}
      onKeyDown={e => { if (e.key === 'Escape') { e.preventDefault(); cerrar(true) } }}
      onBlur={() => cerrar(false)}>
      {opciones.map(o => <option key={o.valor} value={o.valor}>{o.etiqueta}</option>)}
    </select>
  )
}

function EditorFecha({ etiqueta, valor, cerrar, onGuardar }: {
  etiqueta: string; valor: string; cerrar: Cerrar; onGuardar: (v: string) => void
}) {
  const raiz = useRef<HTMLDivElement>(null)
  const pendiente = useRef(valor)
  const id = useId()
  const terminar = useCallback((foco: boolean) => { if (cerrar(foco)) onGuardar(pendiente.current) }, [cerrar, onGuardar])
  // ¿El foco o el clic siguen en el campo o en su calendario (que sale en un portal)?
  const dentro = useCallback((n: Node | null) =>
    !!n && (!!raiz.current?.contains(n) || !!document.getElementById(`${id}-panel`)?.contains(n)), [id])

  // Escuchas en `document` (después de las del campo): si el campo ya usó la
  // tecla (Escape con el calendario abierto) llega con defaultPrevented.
  useEffect(() => {
    const fuera = (e: Event) => { if (!dentro(e.target as Node)) terminar(false) }
    const teclas = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement
      if (e.defaultPrevented || !raiz.current?.contains(el)) return
      if (e.key === 'Escape') { e.preventDefault(); cerrar(true) }
      else if (e.key === 'Enter' && el.tagName === 'INPUT') { e.preventDefault(); terminar(true) }
    }
    document.addEventListener('mousedown', fuera)
    document.addEventListener('focusin', fuera)
    document.addEventListener('keydown', teclas)
    return () => {
      document.removeEventListener('mousedown', fuera)
      document.removeEventListener('focusin', fuera)
      document.removeEventListener('keydown', teclas)
    }
  }, [dentro, terminar, cerrar])

  return (
    <div ref={raiz} className="plan-celda__fecha">
      <CampoFecha id={id} className="ds-input plan-celda__campo" autoFocus aria-label={etiqueta} value={valor}
        onChange={v => { pendiente.current = v; if (v) terminar(true) }} />
    </div>
  )
}

// ── Tabla editable ───────────────────────────────────────────────────────────

function TablaEditable({ tareas, columnas, personas, editable, onCambio }: {
  tareas: TaskListItem[]; columnas: Columna[]; personas: Persona[]
  editable: boolean; onCambio: (id: string, cambios: TaskUpdatePayload) => void
}) {
  const t = useAppT()
  const ver = (c: Columna) => columnas.includes(c)
  const etq = (c: Columna) => t(`planificador.columna_${c}`)
  const num = (v: string) => (v.trim() === '' ? null : Number(v))
  const porId = useMemo(() => new Map(personas.map(p => [p.id, p])), [personas])
  const opcionesEstado = ESTADOS.map(s => ({ valor: s, etiqueta: t(`planificador.estado_${s}`) }))
  const opcionesPrioridad = PRIORIDADES.map(p => ({ valor: p, etiqueta: t(`planificador.prioridad_${p}`) }))
  const opcionesPersona = [{ valor: '', etiqueta: t('planificador.sin_asignar') }, ...personas.map(p => ({ valor: p.id, etiqueta: p.full_name }))]

  return (
    <div className="plan-card plan-vtabla-marco">
      <table className="contecflow-table plan-vtabla">
        <thead>
          <tr>
            <th scope="col" className="plan-vtabla__tarea">{t('planificador.col_tarea')}</th>
            {COLUMNAS.filter(ver).map(c => (
              <th key={c} scope="col" className={['estimated_hours', 'progress_pct', 'total_float_days'].includes(c) ? 'plan-num' : undefined}>{etq(c)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {tareas.map(x => {
            const persona = x.assignee_id ? porId.get(x.assignee_id) : undefined
            const nombrePersona = x.assignee?.full_name ?? persona?.full_name ?? null
            const estado = t(`planificador.estado_${x.status}`)
            const prioridad = t(`planificador.prioridad_${x.priority}`)
            const horas = x.estimated_hours == null ? '—' : fmtNumber(x.estimated_hours)
            const avance = x.progress_pct == null ? '—' : `${fmtNumber(x.progress_pct, 0)} %`
            return (
              <tr key={x.id}>
                <CeldaEditable columna={t('planificador.col_tarea')} valorTexto={x.title} editable={editable} className="plan-vtabla__tarea"
                  extra={<span className="plan-muted plan-vtabla__sub">{x.code}{x.is_critical ? ` · ${t('planificador.critica')}` : ''}</span>}
                  editor={cerrar => <EditorTexto etiqueta={t('planificador.col_tarea')} valor={x.title} cerrar={cerrar}
                    onGuardar={v => { const n = v.trim(); if (n && n !== x.title) onCambio(x.id, { title: n }) }} />}>
                  <span className="plan-vtabla__titulo">{x.title}</span>
                </CeldaEditable>
                {ver('status') && (
                  <CeldaEditable columna={etq('status')} valorTexto={estado} editable={editable}
                    editor={cerrar => <EditorLista etiqueta={etq('status')} valor={x.status} opciones={opcionesEstado} cerrar={cerrar}
                      onGuardar={v => onCambio(x.id, { status: v as TaskListItem['status'] })} />}>
                    <StatusBadge kind={TONO_DE_ESTADO[x.status] ?? 'neutral'} caps={false}>{estado}</StatusBadge>
                  </CeldaEditable>
                )}
                {ver('assignee') && (
                  <CeldaEditable columna={etq('assignee')} valorTexto={nombrePersona ?? t('planificador.sin_asignar')} editable={editable}
                    editor={cerrar => <EditorLista etiqueta={etq('assignee')} valor={x.assignee_id ?? ''} opciones={opcionesPersona} cerrar={cerrar}
                      onGuardar={v => onCambio(x.id, { assignee_id: v || null })} />}>
                    {nombrePersona ? (
                      <span className="plan-vtabla__persona">
                        <Avatar name={nombrePersona} size={22} url={x.assignee?.avatar_url ?? persona?.avatar_url ?? undefined} />
                        {nombrePersona}
                      </span>
                    ) : <span className="plan-muted">{t('planificador.sin_asignar')}</span>}
                  </CeldaEditable>
                )}
                {ver('priority') && (
                  <CeldaEditable columna={etq('priority')} valorTexto={prioridad} editable={editable}
                    editor={cerrar => <EditorLista etiqueta={etq('priority')} valor={x.priority} opciones={opcionesPrioridad} cerrar={cerrar}
                      onGuardar={v => onCambio(x.id, { priority: v as TaskListItem['priority'] })} />}>
                    <StatusBadge kind={TONO_DE_PRIORIDAD[x.priority] ?? 'neutral'} caps={false}>{prioridad}</StatusBadge>
                  </CeldaEditable>
                )}
                {ver('estimated_hours') && (
                  <CeldaEditable columna={etq('estimated_hours')} valorTexto={horas} editable={editable} className="plan-num"
                    editor={cerrar => <EditorTexto etiqueta={etq('estimated_hours')} numero min={0} valor={x.estimated_hours == null ? '' : String(x.estimated_hours)} cerrar={cerrar}
                      onGuardar={v => { const n = num(v); if (n != null && n > 0 && n !== x.estimated_hours) onCambio(x.id, { estimated_hours: n }) }} />}>
                    {horas}
                  </CeldaEditable>
                )}
                {ver('progress_pct') && (
                  <CeldaEditable columna={etq('progress_pct')} valorTexto={avance} editable={editable} className="plan-num"
                    editor={cerrar => <EditorTexto etiqueta={etq('progress_pct')} numero min={0} max={100} valor={x.progress_pct == null ? '' : String(x.progress_pct)} cerrar={cerrar}
                      onGuardar={v => {
                        const n = num(v)
                        if (n != null && (Number.isNaN(n) || n < 0 || n > 100)) return
                        if (n !== (x.progress_pct ?? null)) onCambio(x.id, { progress_pct: n })
                      }} />}>
                    {avance}
                  </CeldaEditable>
                )}
                {(['start_date', 'due_date'] as const).filter(ver).map(c => (
                  <CeldaEditable key={c} columna={etq(c)} valorTexto={fmtDia(x[c])} editable={editable}
                    editor={cerrar => <EditorFecha etiqueta={etq(c)} valor={x[c] ?? ''} cerrar={cerrar}
                      onGuardar={v => {
                        if ((v || null) === (x[c] ?? null)) return
                        onCambio(x.id, c === 'start_date' ? { start_date: v || null } : { due_date: v || null })
                      }} />}>
                    {fmtDia(x[c])}
                  </CeldaEditable>
                ))}
                {ver('total_float_days') && (
                  <td className={`plan-num${x.is_critical ? ' plan-critica' : ''}`}>{x.total_float_days == null ? '—' : fmtNumber(x.total_float_days)}</td>
                )}
              </tr>
            )
          })}
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
      <div className="plan-row plan-row--between plan-muted"><span>{fmtDate(new Date(min))}</span><span>{fmtDate(new Date(max - DIA_MS))}</span></div>
      {con.map(x => (
        <div key={x.id} className="plan-stack plan-lt__fila">
          <span className="plan-row plan-row--between">
            <span className={`plan-lt__titulo${x.is_critical ? ' plan-critica' : ''}`}>
              <span className="plan-muted">{x.code}</span> {x.title}
            </span>
            <span className="plan-muted plan-num">{fmtDia(x.start_date)} – {fmtDia(x.due_date)}</span>
          </span>
          <div className="plan-linea" role="img" aria-label={`${x.title}: ${fmtDia(x.start_date)} – ${fmtDia(x.due_date)}`}>
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
  const ahora = new Date()
  const [mes, setMes] = useState(new Date(ahora.getFullYear(), ahora.getMonth(), 1))
  const hoy = isoLocal(ahora)
  const primerDia = (mes.getDay() + 6) % 7
  const dias = new Date(mes.getFullYear(), mes.getMonth() + 1, 0).getDate()
  const celdas = Array.from({ length: Math.ceil((primerDia + dias) / 7) * 7 }, (_, i) => i - primerDia + 1)
  const clave = (d: number) => isoLocal(new Date(mes.getFullYear(), mes.getMonth(), d))
  const enDia = (d: number) => {
    const k = clave(d)
    return tareas.filter(x => {
      const ini = x.start_date ?? x.due_date
      return ini && x.due_date && ini.slice(0, 10) <= k && k <= x.due_date.slice(0, 10)
    })
  }
  const corto = formateadorDeFecha({ weekday: 'short' })
  const semana = Array.from({ length: 7 }, (_, i) => corto.format(new Date(2024, 0, 1 + i)))
  return (
    <div className="plan-card plan-stack">
      <NavegadorDeMes mes={mes} onCambiar={setMes} />
      <div className="plan-cal">
        {semana.map(d => <div key={d} className="plan-cal__cab">{d}</div>)}
        {celdas.map((d, i) => d < 1 || d > dias ? <div key={i} className="plan-cal__dia plan-cal__dia--fuera plan-cal__dia--vacio" /> : (
          <div key={i} className={`plan-cal__dia${clave(d) === hoy ? ' plan-cal__dia--hoy' : ''}`} aria-current={clave(d) === hoy ? 'date' : undefined}>
            <span className="plan-cal__num">{d}</span>
            {enDia(d).map(x => (
              <span key={x.id} title={`${x.code} ${x.title}`} className={`plan-cal__tarea${x.is_critical ? ' plan-cal__tarea--critica' : ''}`}>{x.code} {x.title}</span>
            ))}
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
  const semanas = useMemo(() => new Map((data?.people ?? []).map(p => [p.user_id, new Map(p.weeks.map(w => [w.week, w]))])), [data])
  if (isLoading) return <Spinner />
  if (!data || data.people.length === 0) return <EmptyState title={t('planificador.sin_carga')} />
  return (
    <RejillaPersonaDia
      titulo={t('planificador.vista_workload')}
      cabeceraFilas={t('planificador.col_persona')}
      unidad="semana"
      filas={data.people.map(p => ({ id: p.user_id, nombre: p.name ?? p.user_id }))}
      columnas={columnasDeSemanas(data.people[0].weeks.map(w => w.week))}
      celda={(fila, col) => {
        const w = semanas.get(fila.id)?.get(col.clave)
        if (!w) return null
        return {
          estado: w.state,
          contenido: w.pct == null ? '—' : `${fmtNumber(w.pct, 0)} %`,
          detalle: t('planificador.carga_detalle', { h: fmtNumber(w.hours), c: fmtNumber(w.capacity), p: fmtNumber(w.project_hours ?? w.hours) }),
        }
      }}
      leyenda={[
        { clave: 'ok', etiqueta: t('planificador.carga_ok'), tono: 'success' },
        { clave: 'under', etiqueta: t('planificador.carga_under'), tono: 'warning' },
        { clave: 'over', etiqueta: t('planificador.carga_over'), tono: 'danger' },
      ]}
      notaLeyenda={t('planificador.carga_leyenda')}
    />
  )
}
