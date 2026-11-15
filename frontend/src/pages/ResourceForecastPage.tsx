import type { CSSProperties } from 'react'
import { useState } from 'react'
import { useToast } from '../context/ToastContext'
import { useQuery } from '@tanstack/react-query'
import { forecastApi } from '../services/api'
import type { MapaDeCarga, ProyeccionDePersona, ResumenDeCapacidad, SemanaDeCarga } from '../services/api/tipos-personas'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { EmptyState } from '../components/ui'
import { BarChart } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import { alpha } from '../constants/theme'
import useMediaQuery from '../hooks/useMediaQuery'
import { STALE_DEFAULT_MS } from '../constants/timings'
import './ResourceForecastPage.css'

const STATUS_COLOR: Record<string, string> = {
  overloaded: 'var(--danger)',
  high:       'var(--warning)',
  medium:     'var(--accent)',
  low:        'var(--success)',
  available:  'var(--surface-4)',
}
const STATUS_LABEL: Record<string, string> = {
  overloaded: 'prevision_recursos_ui.estado_overloaded',
  high:       'prevision_recursos_ui.estado_high',
  medium:     'prevision_recursos_ui.estado_medium',
  low:        'prevision_recursos_ui.estado_low',
  available:  'prevision_recursos_ui.estado_available',
}


// ─────────────────────────────────────────────────────────────────────────────
// Las formas que esta pagina consume
//
// Los tipos de la respuesta estan en services/api/tipos-personas.ts.
// ─────────────────────────────────────────────────────────────────────────────

type FilaDeCarga = MapaDeCarga['users'][number]

/** El estado de carga que corresponde a un porcentaje.
 *
 *  Auditoria 2026-09: esta cadena de umbrales —100 / 85 / 50 / 10— estaba
 *  escrita **tres veces** en este mismo fichero, palabra por palabra. Tres
 *  copias de una regla de negocio es una regla que se puede cambiar en dos
 *  sitios y quedarse mal en el tercero sin que nada avise.
 *
 *  Sin dato el estado es `available`, que es lo que el codigo ya hacia: en
 *  JavaScript `undefined > 100` es falso y la cadena caia hasta el ultimo
 *  escalon. Aqui va escrito en vez de deducirse.
 */
function estadoDeCarga(pct?: number): string {
  const carga = pct ?? 0
  if (carga > 100) return 'overloaded'
  if (carga > 85) return 'high'
  if (carga > 50) return 'medium'
  if (carga > 10) return 'low'
  return 'available'
}

// ── Celda del heatmap ─────────────────────────────────────────────────────────
function HeatCell({ week }: { week: SemanaDeCarga }) {
  const t = useAppT()
  const [hover, setHover] = useState(false)
  const color = (week.status && STATUS_COLOR[week.status]) || 'var(--surface-4)'
  const pct   = Math.min(week.load_pct ?? 0, 100)

  return (
    <div className="rfc-card"
      onPointerEnter={() => setHover(true)}
      onPointerLeave={() => setHover(false)}
      style={{ '--rfc-card-border': `1px solid ${alpha(color, '30')}` } as CSSProperties}
    >
      {/* Barra de relleno proporcional */}
      <div className="rfc-box" style={{ '--rfc-box-height': `${pct}%`, '--rfc-box-background': alpha(color, '40') } as CSSProperties} />
      <div className="rfc-row-mono" style={{ '--rfc-row-mono-color': color } as CSSProperties}>
        {(week.load_pct ?? 0) > 0 ? `${Math.round(week.load_pct ?? 0)}%` : '—'}
      </div>

      {/* Tooltip */}
      {hover && (
        <div className="rfc-card-2">
          <div className="rfc-text-strong" style={{ '--rfc-text-strong-color': color } as CSSProperties}>{STATUS_LABEL[week.status ?? ''] ? t(STATUS_LABEL[week.status ?? '']) : week.status}</div>
          <div>{t('prevision_recursos_ui.comprometido')} <strong>{week.committed_hours}h</strong></div>
          <div>{t('prevision_recursos_ui.disponible')} <strong>{week.available_hours}h</strong></div>
          <div className="rfc-text-muted-2xs">{week.week}</div>
        </div>
      )}
    </div>
  )
}

// ── Fila de usuario ───────────────────────────────────────────────────────────
interface UserRowProps {
  user: FilaDeCarga
  /** El usuario resaltado, o `null` si no hay ninguno. */
  selectedUser: string | number | null
  /** Recibe `null` al deseleccionar: pulsar la fila activa la quita. */
  onSelect: (userId: string | number | null) => void
  /** Ancho de la columna del nombre (más estrecha en móvil). */
  nameWidth?: number
}

function UserRow({ user, selectedUser, onSelect, nameWidth = 160 }: UserRowProps) {
  const t = useAppT()
  const isSelected = selectedUser === user.user_id
  const avgColor = STATUS_COLOR[estadoDeCarga(user.avg_load_pct)]

  return (
    <div className="rfc-row">
      {/* Nombre usuario */}
      <button className="rfc-btn-sm"
        type="button"
        onClick={() => onSelect(isSelected ? null : user.user_id)}
        style={{ '--rfc-btn-sm-color': isSelected ? 'var(--accent)' : 'var(--text-1)', '--rfc-btn-sm-background': isSelected ? 'var(--accent-muted)' : 'transparent', '--rfc-btn-sm-border': isSelected ? '1px solid var(--accent-border)' : '1px solid transparent', '--rfc-nombre-ancho': `${nameWidth}px` } as CSSProperties}
        title={user.user_name ?? ''}
      >
        {(user.user_name ?? '').split(' ')[0]} {(user.user_name ?? '').split(' ')[1]?.[0] || ''}.
      </button>

      {/* Carga media */}
      <div className="rfc-box-mono rfc-text" style={{ '--rfc-text-color': avgColor } as CSSProperties}>
        {user.avg_load_pct}%
      </div>

      {/* Celdas del heatmap */}
      <div className="rfc-row-2">
        {(user.weeks ?? []).map(w => <HeatCell key={w.week} week={w} />)}
      </div>

      {/* Indicador semanas saturadas */}
      {(user.overloaded_weeks ?? 0) > 0 && (
        <div className="rfc-card-danger">
          <span title={t('prevision_recursos_ui.semanas_saturadas_titulo', { n: user.overloaded_weeks ?? 0 })}>{t('prevision_recursos_ui.semanas_saturadas', { n: user.overloaded_weeks ?? 0 })}</span>
        </div>
      )}
    </div>
  )
}

// ── Panel de detalle de usuario ───────────────────────────────────────────────
function UserDetailPanel({ userId, weeks }: { userId: string | number; weeks: number }) {
  const _toast = useToast()
  const t = useAppT()
  const { data, isLoading } = useQuery<ProyeccionDePersona>({
    queryKey: ['forecast-user', userId, weeks],
    queryFn: () => forecastApi.userDetail(userId, { weeks }).then(r => r.data),
    enabled: !!userId,
  })

  if (isLoading) return (
    <div className="rfc-state-muted">
      {t('prevision_recursos_ui.cargando_detalle')}
    </div>
  )
  if (!data) return null

  return (
    <div className="rfc-card-3">
      <div className="rfc-text-accent-md-strong">
        {t('prevision_recursos_ui.detalle_titulo', { nombre: data?.user_name ?? '', n: weeks })}
      </div>
      <div className="u-scroll-x">
        <table className="rfc-table">
          <thead>
            <tr>
              <th className="rfc-th">{t('prevision_recursos_ui.col_semana')}</th>
              <th className="rfc-th-2">{t('prevision_recursos_ui.col_carga')}</th>
              <th className="rfc-th-2">{t('prevision_recursos_ui.col_comprometido')}</th>
              <th className="rfc-th-2">{t('prevision_recursos_ui.col_disponible')}</th>
              <th className="rfc-th">{t('prevision_recursos_ui.col_proyectos')}</th>
            </tr>
          </thead>
          <tbody>
            {(data?.weeks ?? []).map(w => {
              const color = STATUS_COLOR[estadoDeCarga(w.load_pct)]
              return (
                <tr className="rfc-tr" key={w.week}>
                  <td className="rfc-td-muted">{w.week}</td>
                  <td className="rfc-td-strong" style={{ '--rfc-td-strong-color': color } as CSSProperties}>{w.load_pct}%</td>
                  <td className="rfc-td">{w.committed_hours}h</td>
                  <td className="rfc-td-success">{w.available_hours}h</td>
                  <td className="rfc-td-muted-2">
                    {(w.breakdown ?? []).map(b => `${b.project_name} (${b.hours}h)`).join(', ') || '—'}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── Página principal ──────────────────────────────────────────────────────────
export default function ResourceForecastPage() {
  const t = useAppT()
  const _t = useAppT()
  const _toast = useToast()
  const [weeks, setWeeks]             = useState(13)
  const [department, setDepartment]   = useState('')
  const [selectedUser, setSelectedUser] = useState<string | number | null>(null)
  const [view, setView]               = useState('heatmap')   // heatmap | summary | availability
  const nameWidth = useMediaQuery('(max-width: 900px)') ? 96 : 160

  const { data: heatmapData, isLoading: loadingHeatmap } = useQuery<MapaDeCarga>({
    queryKey: ['forecast-heatmap', weeks, department],
    queryFn: () => forecastApi.heatmap({ weeks, department: department || undefined }).then(r => r.data),
    staleTime: STALE_DEFAULT_MS,
  })

  const { data: summaryData, isLoading: loadingSummary, isError: summaryError } = useQuery<ResumenDeCapacidad>({
    queryKey: ['forecast-summary', weeks, department],
    queryFn: () => forecastApi.summary({ weeks, department: department || undefined }).then(r => r.data),
    staleTime: STALE_DEFAULT_MS,
  })

  const summary = {
    avg_team_load_pct: summaryData?.avg_team_load_pct ?? 0,
    total_available_hrs: summaryData?.total_available_hrs ?? 0,
    total_committed_hrs: summaryData?.total_committed_hrs ?? 0,
    risk_weeks_count: summaryData?.risk_weeks_count ?? 0,
    overloaded_users_count: summaryData?.overloaded_users_count ?? 0,
    week_trend: Array.isArray(summaryData?.week_trend) ? summaryData.week_trend : [],
    risk_weeks: Array.isArray(summaryData?.risk_weeks) ? summaryData.risk_weeks : [],
  }

  const weekLabels = heatmapData?.week_labels || []
  const users      = heatmapData?.users || []

  // Calcular slice de semanas visibles (máximo ~16 para no sobrecargar)
  const VISIBLE_WEEKS = Math.min(weeks, 16)
  const visibleUsers  = users


  return (
    <PageShell>
      <PageHeader
        title={_t('resource_forecast.title')}
        subtitle={_t('resource_forecast.subtitle', { weeks })}
        icon={<BarChart size={18} />}
      />

      {/* KPIs de resumen */}
      {summaryData && (
        <div className="rfc-grid">
          {[
            { label: t('prevision_recursos_ui.kpi_carga_media'), value: `${summary.avg_team_load_pct}%`, color: summary.avg_team_load_pct > 85 ? 'var(--danger)' : 'var(--accent)' },
            { label: t('prevision_recursos_ui.kpi_horas_disponibles'), value: `${summary.total_available_hrs}h`, color: 'var(--success)' },
            { label: t('prevision_recursos_ui.kpi_horas_comprometidas'), value: `${summary.total_committed_hrs}h`, color: 'var(--purple)' },
            { label: t('prevision_recursos_ui.kpi_semanas_riesgo'), value: summary.risk_weeks_count, color: summary.risk_weeks_count > 0 ? 'var(--warning)' : 'var(--success)' },
            { label: t('prevision_recursos_ui.kpi_personas_saturadas'), value: summary.overloaded_users_count, color: summary.overloaded_users_count > 0 ? 'var(--danger)' : 'var(--success)' },
          ].map(k => (
            <div className="rfc-card-4" key={k.label}>
              <div className="rfc-text-xl-em-strong-mono rfc-text-2" style={{ '--rfc-text-2-color': k.color } as CSSProperties}>
                {k.value}
              </div>
              <div className="u-hint">{k.label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Controles */}
      <div className="rfc-row-3">
        <div className="rfc-row-4">
          {[
            { id: 'heatmap', label: t('prevision_recursos_ui.vista_heatmap') },
            { id: 'summary', label: t('prevision_recursos_ui.vista_resumen') },
          ].map(v => (
            <button className="rfc-btn-sm-2" type="button" aria-pressed={view === v.id} key={v.id} onClick={() => setView(v.id)} style={{ '--rfc-btn-sm-2-background': view === v.id ? 'var(--accent-muted)' : 'transparent', '--rfc-btn-sm-2-color': view === v.id ? 'var(--accent)' : 'var(--text-2)', '--rfc-btn-sm-2-outline': view === v.id ? '1px solid var(--accent-border)' : 'none' } as CSSProperties}>{v.label}</button>
          ))}
        </div>

        <select className="rfc-input" aria-label={t('prevision_recursos_ui.horizonte')} value={weeks} onChange={e => setWeeks(+e.target.value)}>
          {[4,8,13,26,52].map(n => (
            <option key={n} value={n}>{t('prevision_recursos_ui.n_semanas', { n })}</option>
          ))}
        </select>

        <input className="rfc-input-2"
          aria-label={t('prevision_recursos_ui.departamento')}
          placeholder={t('prevision_recursos_ui.departamento_ph')}
          value={department}
          onChange={e => setDepartment(e.target.value)}
        />
      </div>

      {/* Vista heatmap */}
      {view === 'heatmap' && (
        <div className="rfc-panel">
          <div className="u-scroll-x">
          <div className={!loadingHeatmap && users.length > 0 ? 'rfc-ancho-contenido' : undefined}>
          {/* Cabecera de semanas */}
          <div className="rfc-row-5">
            <div className="rfc-box-2 rfc-nombre" style={{ '--rfc-nombre-ancho': `${nameWidth}px` } as CSSProperties} />
            <div className="rfc-box-3" />
            <div className="rfc-row-2">
              {weekLabels.slice(0, VISIBLE_WEEKS).map(w => (
                <div className="rfc-box-muted-mono" key={w}>
                  {w.split('-W')[1]}
                </div>
              ))}
            </div>
          </div>

          {loadingHeatmap ? (
            <div className="rfc-state-muted-2">
              {t('resourceforecast.calculando_proyeccion')}
            </div>
          ) : users.length === 0 ? (
            <EmptyState icon="📈" title={t('resourceforecast.sin_datos_de_prevision')}
              description={t('prevision_recursos_ui.sin_datos_desc')} />
          ) : (
            <div>
              {visibleUsers.map(u => (
                <UserRow
                  key={u.user_id}
                  user={{ ...u, weeks: (u.weeks ?? []).slice(0, VISIBLE_WEEKS) }}
                  selectedUser={selectedUser}
                  onSelect={setSelectedUser}
                  nameWidth={nameWidth}
                />
              ))}
            </div>
          )}
          </div>
          </div>

          {/* Leyenda */}
          <div className="rfc-row-6">
            {Object.entries(STATUS_COLOR).map(([k, c]) => k !== 'available' && (
              <div className="rfc-row-muted" key={k}>
                <div className="rfc-box-4 rfc-box-6" style={{ '--rfc-box-6-background': c } as CSSProperties} />
                {t(STATUS_LABEL[k])}
              </div>
            ))}
            <div className="rfc-text-muted-2xs-2">
              {t('resourceforecast.haz_clic_en_un_nombre_para_ver')}
            </div>
          </div>
        </div>
      )}

      {/* Vista resumen semanal */}
      {view === 'summary' && (
        <div className="rfc-panel">
          <div className="rfc-text-md-strong">
            {t('prevision_recursos_ui.tendencia_semanas', { n: weeks })}
          </div>
          {loadingSummary ? (
            <div className="rfc-state-muted-3">
              {t('prevision_recursos_ui.cargando_resumen')}
            </div>
          ) : summaryError ? (
            <div className="rfc-state-danger">
              {t('resourceforecast.no_se_pudo_cargar_el_resumen_de')}
            </div>
          ) : summary.week_trend.length === 0 ? (
            <div className="rfc-state-muted-3">
              {t('resourceforecast.sin_datos_de_carga_disponibles_configura_usuarios')}
            </div>
          ) : (
          <div className="u-stack-6">
            {(summary.week_trend || []).map(w => {
              const pct = w.load_pct ?? 0
              const color = STATUS_COLOR[estadoDeCarga(pct)]
              return (
                <div key={w.week} className="u-row-center-10">
                  <div className="rfc-box-muted-mono-2">
                    {w.week}
                  </div>
                  <div className="rfc-card-5">
                    <div className="rfc-box-5" style={{ '--rfc-box-5-width': `${Math.min(pct, 100)}%`, '--rfc-box-5-background': color } as CSSProperties} />
                  </div>
                  <div className="rfc-box-mono-2" style={{ '--rfc-box-mono-2-color': color } as CSSProperties}>
                    {pct}%
                  </div>
                  {(summary.risk_weeks || []).includes(w.week) && (
                    <span className="rfc-text-danger-2xs">⚠</span>
                  )}
                </div>
              )
            })}
          </div>
          )}
        </div>
      )}

      {/* Panel de detalle de usuario seleccionado */}
      {selectedUser && view === 'heatmap' && (
        <UserDetailPanel userId={selectedUser} weeks={weeks} />
      )}
    </PageShell>
  )
}
