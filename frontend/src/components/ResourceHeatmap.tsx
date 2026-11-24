/**
 * ResourceHeatmap — Visual weekly load heatmap per team member
 * Shows hard/soft bookings, utilization %, and overload warnings
 *
 * 16-11-2026: pasada de diseño (pestaña "Mapa de calor" de /resources).
 * KPIs con KpiCard e iconos lucide (antes emojis de colores); horizonte y
 * filtro en selects .ds-input (antes botones "4w/8w"); botones del kit con
 * icono (antes con emojis, flechas y «+» de texto);
 * colores de estado con tokens (antes rgba fijos que no seguían el tema);
 * textos que estaban en castellano a fuego (estados, KPIs, validación,
 * tooltip, "Guardando...") pasan por t(); tipo de reserva y rol traducidos
 * (antes "hard"/"soft"/"employee"); fechas con el formateador de la app.
 *
 * Periodo libre (16-11-2026): el horizonte es el selector de periodo común
 * hacia delante (`sentido: 'futuro'`, por semanas, máximo 52) en vez de
 * 4/8/12/16 semanas. La API sigue aceptando `weeks`.
 */
import { useMemo, useState, type CSSProperties, useId } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { reservasApi } from '../services/api'
import { Button, Card, KpiCard, Modal, Select, Spinner, EmptyState, SelectorDePeriodo, RejillaPersonaDia, columnasDeSemanas, useErroresDeCampo, Input, IconButton } from './ui'
import type { TonoDeRejilla } from './ui'
import { usePeriodo } from '../hooks/usePeriodo'
import { AlertTriangle, ArrowLeft, BatteryLow, CalendarDays, Flame, List, Plus, Trash2, Users } from 'lucide-react'
import { z } from 'zod'
import { useFormValidation } from '../hooks/useFormValidation'
import { useAppT } from '../i18n/AppLangContext'
import { alpha } from '../constants/theme'
import { fmtDate, fmtNumber } from '../utils/helpers'
import DateInput from './ui/DateInput'
import { POLL_DEFAULT_MS } from '../constants/timings'
import './ResourceHeatmap.css'
import { useListaDeProyectos, useListaDeUsuarios } from '../hooks/useListas'

interface ProjectItem {
  id: string | number
  code?: string
  name?: string
}

interface UserItem {
  id: string | number
  full_name?: string
  role?: string
}

interface BookingPrefill {
  user_id?: string | number
  week?: string
}

interface BookingItem {
  id: string | number
  user_name?: string
  booking_type?: 'hard' | 'soft'
  project_name?: string
  start_date?: string
  end_date?: string
  hours_per_day?: number
  total_hours?: number
}

interface HeatmapWeek {
  status: 'overloaded' | 'high' | 'ok' | 'free'
  hard_hours: number
  soft_hours: number
  capacity: number
  available: number
  utilization_pct: number
  week_label: string
  week: string
}

interface HeatmapUser {
  user_id: string | number
  user_name: string
  role?: string
  avg_utilization: number
  weeks: HeatmapWeek[]
}

interface HeatmapData {
  users?: HeatmapUser[]
  week_labels?: string[]
}

type T = ReturnType<typeof useAppT>

/** Colores de cada estado de carga, solo con tokens del tema. */
const STATUS_COLORS: Record<string, { tono: TonoDeRejilla; label: string }> = {
  overloaded: { tono: 'danger',  label: 'resourceheatmap.estado_overloaded' },
  high:       { tono: 'warning', label: 'resourceheatmap.estado_high' },
  ok:         { tono: 'accent',  label: 'resourceheatmap.estado_ok' },
  free:       { tono: 'vacio',   label: 'resourceheatmap.estado_free' },
}

const BOOKING_COLORS = {
  hard: 'var(--accent)',
  soft: 'var(--purple)',
}

/** Nombre del rol en el idioma activo; si no hay clave, el código. */
const nombreDeRol = (t: T, rol?: string) => rol ? t(`resources.role_${rol}`, rol) : ''

/** Tipo de reserva traducido (antes salía "hard"/"soft"). */
const nombreDeTipo = (t: T, tipo?: string) =>
  tipo === 'soft' ? t('resourceheatmap.soft_tentativo') : tipo === 'hard' ? t('resourceheatmap.hard_confirmado') : (tipo ?? '')

function crearEsquema(t: T) {
  return z.object({
    user_id: z.string().trim().min(1, t('resourceheatmap.err_persona')),
    project_id: z.string().optional(),
    booking_type: z.enum(['hard', 'soft']),
    start_date: z.string().min(1, t('resourceheatmap.err_inicio')),
    end_date: z.string().min(1, t('resourceheatmap.err_fin')),
    hours_per_day: z.coerce.number().min(1, t('resourceheatmap.err_horas_min')).max(24, t('resourceheatmap.err_horas_max')),
    note: z.string().optional(),
  }).superRefine((data, ctx) => {
    if (data.end_date < data.start_date) {
      ctx.addIssue({
        code: 'custom',
        path: ['end_date'],
        message: t('resourceheatmap.err_fin_anterior'),
      })
    }
  })
}

function BookingModal({ onClose, prefill }: { onClose: () => void; prefill?: BookingPrefill | null }) {
  const idCampo = useId()
  const t = useAppT()
  const qc = useQueryClient()
  const [form, setForm] = useState({
    user_id: prefill?.user_id || '',
    project_id: '',
    booking_type: 'hard',
    start_date: prefill?.week || new Date().toISOString().slice(0,10),
    end_date: '',
    hours_per_day: 8,
    note: '',
  })
  const esquema = useMemo(() => crearEsquema(t), [t])
  const validation = useFormValidation(esquema)

  const { data: projRaw = [] } = useListaDeProyectos()
  const { data: usersRaw = [] } = useListaDeUsuarios()
  const projects = projRaw as ProjectItem[]
  const users = usersRaw as UserItem[]

  const campos = useErroresDeCampo()
  const msg = (k: string) => campos.de(k) ? <div className="u-field-error">{campos.de(k)}</div> : null
  const { mutate: create, isPending } = useMutation({
    onMutate: () => campos.limpiar(),
    mutationFn: (d: unknown) => reservasApi.crear(d),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['heatmap'] }); qc.invalidateQueries({ queryKey: ['bookings'] }); validation.setErrors({}); onClose() },
    onError: (e: unknown) => { campos.recoger(e) },
  })

  const setField = (key: 'user_id' | 'project_id' | 'booking_type' | 'start_date' | 'end_date' | 'hours_per_day' | 'note') => (e: { target: { value: string } }) => {
    const value = key === 'hours_per_day' ? +e.target.value : e.target.value
    setForm(current => ({ ...current, [key]: value }))
    validation.clearFieldError(key)
  }

  const submit = () => {
    const result = validation.validateForm(form)
    if (!result.success) {
      return
    }
    create(result.data)
  }

  return (
    <Modal open title={t('resource_heatmap.new_booking_title')} onClose={onClose} width={480}>
      <div className="u-stack-14">
        <div>
          <Select label={t('capacity.persona_obligatoria')} id={`${idCampo}-1`} value={form.user_id} onChange={setField('user_id')} placeholder={t('invoices.select')} aria-invalid={!!validation.errors.user_id}>
            {users.map(u => <option key={u.id} value={u.id}>{u.full_name}{u.role ? ` (${nombreDeRol(t, u.role)})` : ''}</option>)}
          </Select>{msg('user_id')}
          {validation.errors.user_id && <div className="u-field-error">{validation.errors.user_id}</div>}
        </div>
        <div>
          <Select label={t('gas.proyecto')} id={`${idCampo}-2`} value={form.project_id} onChange={setField('project_id')} placeholder={t('resourceheatmap.sin_proyecto')}>
            {projects.map(p => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
          </Select>{msg('project_id')}
        </div>
        <div className="u-grid2-12">
          <div>
            <Select label={t('alm.type')} id={`${idCampo}-3`} value={form.booking_type} onChange={setField('booking_type')} placeholder={false}>
              <option value="hard">{t('resourceheatmap.hard_confirmado')}</option>
              <option value="soft">{t('resourceheatmap.soft_tentativo')}</option>
            </Select>{msg('booking_type')}
          </div>
          <div><Input label={t('resourceheatmap.h_dia')} id={`${idCampo}-4`} type="number" min={1} max={24} value={form.hours_per_day} onChange={setField('hours_per_day')} />{msg('hours_per_day')}
            {validation.errors.hours_per_day && <div className="u-field-error">{validation.errors.hours_per_day}</div>}
          </div>
          <div>
            <DateInput label={t('resourceheatmap.fecha_inicio')} id={`${idCampo}-5`} value={form.start_date} onChange={setField('start_date')} aria-invalid={!!validation.errors.start_date} />{msg('start_date')}
            {validation.errors.start_date && <div className="u-field-error">{validation.errors.start_date}</div>}
          </div>
          <div>
            <DateInput label={t('resourceheatmap.fecha_fin')} id={`${idCampo}-6`} value={form.end_date} onChange={setField('end_date')} aria-invalid={!!validation.errors.end_date} />{msg('end_date')}
            {validation.errors.end_date && <div className="u-field-error">{validation.errors.end_date}</div>}
          </div>
        </div>
        <div>
          <Input label={t('aus.nota')} id={`${idCampo}-7`} value={form.note} onChange={setField('note')} placeholder={t('resourceheatmap.motivo_de_la_reserva')} />{msg('note')}
        </div>
        <div className="u-actions-10">
          <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
          <Button onClick={submit} loading={isPending}>
            {isPending ? t('resourceheatmap.guardando') : t('resourceheatmap.crear_reserva')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

export default function ResourceHeatmap() {
  const t = useAppT()
  const qc = useQueryClient()
  // Horizonte hacia delante por semanas; la API corta en 52 (sin «próximo año»).
  const periodo = usePeriodo({ sentido: 'futuro', defecto: 'prox30d', granularidades: ['week'], prefijo: 'mapa_' })
  const presetsHorizonte = periodo.selector.presets.filter(k => k !== 'prox365d')
  const [showBooking, setShowBooking] = useState(false)
  const [bookingPrefill, setBookingPrefill] = useState<BookingPrefill | null>(null)
  const [filterStatus, setFilterStatus] = useState('')
  const [showBookingsPanel, setShowBookingsPanel] = useState(false)

  const { data: heatmapData } = useQuery<HeatmapData>({
    queryKey: ['heatmap', periodo.params],
    queryFn: () => reservasApi.mapaDeCalor<HeatmapData>({ ...periodo.params }).then(r => r.data),
    refetchInterval: POLL_DEFAULT_MS,
  })
  const isLoading = !heatmapData

  const { data: bookingsRaw = [] } = useQuery({
    queryKey: ['bookings'],
    queryFn: () => reservasApi.listar<BookingItem[] | { items?: BookingItem[] }>().then(r => (Array.isArray(r.data) ? r.data : r.data?.items) ?? []),
    enabled: showBookingsPanel,
  })
  const bookings = bookingsRaw as BookingItem[]

  const { mutate: deleteBooking } = useMutation({
    mutationFn: (id: string | number) => reservasApi.borrar(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['heatmap'] }); qc.invalidateQueries({ queryKey: ['bookings'] }) },
  })

  const users = heatmapData?.users || []
  const weekLabels = heatmapData?.week_labels || []

  const filteredUsers = filterStatus
    ? users.filter(u => u.weeks.some(w => w.status === filterStatus))
    : users

  const overloadedCount = users.filter(u => u.weeks.some(w => w.status === 'overloaded')).length
  const highCount = users.filter(u => u.weeks.some(w => w.status === 'high')).length
  const freeCount = users.filter(u => u.avg_utilization < 20).length

  return (
    <div>
      {/* Summary KPIs */}
      <div className="ds-grid-stats resoheat-grid-1">
        <KpiCard icon={<AlertTriangle size={16} />} label={t('resourceheatmap.kpi_sobrecargados')} value={overloadedCount} danger={overloadedCount > 0} />
        <KpiCard icon={<Flame size={16} />} label={t('resourceheatmap.kpi_alta_carga')} value={highCount} warning={highCount > 0} />
        <KpiCard icon={<BatteryLow size={16} />} label={t('resourceheatmap.kpi_infrautilizados')} value={freeCount} />
        <KpiCard icon={<Users size={16} />} label={t('resourceheatmap.kpi_personas')} value={users.length} />
      </div>

      {/* Controls */}
      <div className="ds-toolbar resoheat-row-1">
        <SelectorDePeriodo {...periodo.selector} presets={presetsHorizonte} sinGranularidad />

        <Select suelto value={filterStatus} onChange={e => setFilterStatus(e.target.value)}
          aria-label={t('resourceheatmap.filtro_estado')} className="ds-input resoheat-fs2" placeholder={t('resourceheatmap.todos')}>
          <option value="overloaded">{t('resourceheatmap.solo_sobrecargados')}</option>
          <option value="high">{t('resourceheatmap.alta_carga')}</option>
          <option value="free">{t('resourceheatmap.infrautilizados')}</option>
        </Select>

        <div className="ds-toolbar__spacer" />
        <Button variant="secondary" icon={showBookingsPanel ? <ArrowLeft size={14} /> : <List size={14} />}
          onClick={() => setShowBookingsPanel(p => !p)}>
          {showBookingsPanel ? t('resourceheatmap.volver_mapa') : t('resourceheatmap.ver_reservas')}
        </Button>
        <Button icon={<Plus size={14} />} onClick={() => { setBookingPrefill(null); setShowBooking(true) }}>
          {t('resourceheatmap.nueva_reserva')}
        </Button>
      </div>

      {/* Bookings panel */}
      {showBookingsPanel && (
        <Card className="resoheat-box-4">
          <div className="resoheat-box-5">{t('resource_heatmap.active_bookings')}</div>
          {bookings.length === 0 ? (
            <EmptyState icon={<CalendarDays size={28} />} title={t('resource_heatmap.empty_bookings_title')} description={t('resource_heatmap.empty_bookings_desc')} />
          ) : (
            <div className="u-stack-6">
              {bookings.map(b => {
                const color = (b.booking_type && BOOKING_COLORS[b.booking_type]) || 'var(--text-2)'
                return (
                  <div key={b.id} className="resoheat-grid-2">
                    <span className="u-600 u-min0">{b.user_name}</span>
                    <span className="resoheat-box-14 resource-heatmap-e7" style={{ '--resource-heatmap-color': color, '--resource-heatmap-background': alpha(color, '20') } as CSSProperties}>{nombreDeTipo(t, b.booking_type)}</span>
                    <span className="u-text2 u-min0">{b.project_name || t('resource_heatmap.no_project')}</span>
                    <span className="u-text2">{fmtDate(b.start_date)} – {fmtDate(b.end_date)}</span>
                    <span>{b.hours_per_day}{t('resourceheatmap.h_dia_2')}</span>
                    <span className="resoheat-txt-1">{b.total_hours}{t('resourceheatmap.h_total')}</span>
                    <IconButton variante="caja" tono="peligro" ariaLabel={t('resourceheatmap.eliminar_reserva')}
                      onClick={() => { openConfirmGlobal({ message: t('resource_heatmap.delete_booking_confirm'), onConfirm: () => deleteBooking(b.id), danger: true }) }}><Trash2 size={14} /></IconButton>
                  </div>
                )
              })}
            </div>
          )}
        </Card>
      )}

      {/* Heatmap grid */}
      {isLoading ? <Spinner /> : filteredUsers.length === 0 ? (
        <EmptyState icon={<Users size={28} />} title={t('resource_heatmap.empty_data_title')} description={t('resource_heatmap.empty_data_desc')} />
      ) : (
        <RejillaPersonaDia
          titulo={t('resource_heatmap.person')}
          cabeceraFilas={t('resource_heatmap.person')}
          unidad="semana"
          filas={filteredUsers.map(u => ({
            id: String(u.user_id), nombre: u.user_name, usuario: u,
            sub: [nombreDeRol(t, u.role), t('resourceheatmap.media', { pct: Math.round(u.avg_utilization) })].filter(Boolean).join(' · '),
          }))}
          columnas={columnasDeSemanas((filteredUsers[0]?.weeks ?? []).map(w => w.week), (_, i) => weekLabels[i] ?? filteredUsers[0]?.weeks[i]?.week_label)}
          celda={(fila, col) => {
            const week = fila.usuario.weeks.find(w => w.week === col.clave)
            if (!week) return null
            const conHoras = week.hard_hours > 0 || week.soft_hours > 0
            return {
              estado: week.status,
              detalle: t('resourceheatmap.celda_titulo', { nombre: fila.nombre, semana: week.week_label, cap: week.capacity, hard: week.hard_hours, soft: week.soft_hours, disp: week.available, pct: week.utilization_pct }),
              contenido: conHoras ? (
                <>
                  <span>{fmtNumber(week.utilization_pct, 0)}%</span>
                  <span className="resoheat-horas">
                    {week.hard_hours > 0 && <span className="resoheat-horas--hard">{fmtNumber(week.hard_hours)}h</span>}
                    {week.soft_hours > 0 && <span className="resoheat-horas--soft">{fmtNumber(week.soft_hours)}h~</span>}
                  </span>
                </>
              ) : '—',
            }
          }}
          onCelda={(fila, col) => { setBookingPrefill({ user_id: fila.usuario.user_id, week: col.clave }); setShowBooking(true) }}
          leyenda={Object.entries(STATUS_COLORS).map(([clave, cfg]) => ({ clave, etiqueta: t(cfg.label), tono: cfg.tono }))}
          notaLeyenda={<>
            <span className="resoheat-horas--hard">{t('resource_heatmap.hard_booking')}</span>
            {' · '}
            <span className="resoheat-horas--soft">{t('resource_heatmap.soft_booking')}</span>
          </>}
        />
      )}

      {showBooking && <BookingModal onClose={() => setShowBooking(false)} prefill={bookingPrefill} />}
    </div>
  )
}
