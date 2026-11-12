import { useState } from 'react'
import { useToast } from '../context/ToastContext'
import { useQuery } from '@tanstack/react-query'
import { forecastApi } from '../services/api'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { EmptyState } from '../components/ui'
import { BarChart } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'
import { alpha } from '../constants/theme'
import useMediaQuery from '../hooks/useMediaQuery'

const STATUS_COLOR: Record<string, string> = {
  overloaded: 'var(--danger)',
  high:       'var(--warning)',
  medium:     'var(--accent)',
  low:        'var(--success)',
  available:  'var(--surface-4)',
}
const STATUS_LABEL: Record<string, string> = {
  overloaded: 'Sobrecargado',
  high:       'Alto',
  medium:     'Medio',
  low:        'Bajo',
  available:  'Libre',
}


// ─────────────────────────────────────────────────────────────────────────────
// Las formas que esta pagina consume
//
// Auditoria 2026-09 (modo estricto): el cliente de API devuelve `any` y ningun
// componente de este fichero declaraba sus props. Se declara lo que la pagina
// lee; los campos opcionales lo son porque este fichero no puede prometer lo
// que manda el backend.
// ─────────────────────────────────────────────────────────────────────────────

/** El reparto de horas de una semana entre proyectos. */
interface RepartoDeSemana {
  project_name?: string
  hours?: number
}

/** Una semana de carga de una persona. */
interface SemanaDeCarga {
  week: string
  status?: string
  load_pct?: number
  committed_hours?: number
  available_hours?: number
  split?: unknown
  breakdown?: RepartoDeSemana[]
}

/** Una fila del heatmap: una persona y sus semanas. */
interface FilaDeCarga {
  user_id: string | number
  user_name?: string
  avg_load_pct?: number
  overloaded_weeks?: number
  weeks?: SemanaDeCarga[]
}

/** La respuesta del heatmap. */
interface RespuestaDeHeatmap {
  week_labels?: string[]
  users?: FilaDeCarga[]
}

/** El detalle de carga de una persona. */
interface DetalleDeCarga {
  user_name?: string
  weeks?: SemanaDeCarga[]
}

/** El resumen de cartera. */
interface ResumenDeCarga {
  avg_team_load_pct?: number
  total_available_hrs?: number
  total_committed_hrs?: number
  risk_weeks_count?: number
  overloaded_users_count?: number
  week_trend?: SemanaDeCarga[]
  /** Etiquetas de las semanas en riesgo, no las semanas enteras: el
   *  grafico solo pregunta «esta esta en la lista». */
  risk_weeks?: string[]
}

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
  const [hover, setHover] = useState(false)
  const color = (week.status && STATUS_COLOR[week.status]) || 'var(--surface-4)'
  const pct   = Math.min(week.load_pct ?? 0, 100)

  return (
    <div
      onPointerEnter={() => setHover(true)}
      onPointerLeave={() => setHover(false)}
      style={{
        position: 'relative', width: 36, height: 36, borderRadius: 6,
        background: 'var(--surface-1)', border: `1px solid ${alpha(color, '30')}`,
        cursor: 'default', overflow: 'visible', flexShrink: 0,
      }}
    >
      {/* Barra de relleno proporcional */}
      <div style={{
        position: 'absolute', bottom: 0, left: 0, right: 0,
        height: `${pct}%`, background: alpha(color, '40'),
        borderRadius: '0 0 5px 5px', transition: 'height 0.2s',
      }} />
      <div style={{
        position: 'absolute', inset: 0, display: 'flex',
        alignItems: 'center', justifyContent: 'center',
        fontSize: "var(--text-3xs)", fontWeight: 700, color,
        fontFamily: 'var(--font-mono)',
      }}>
        {(week.load_pct ?? 0) > 0 ? `${Math.round(week.load_pct ?? 0)}%` : '—'}
      </div>

      {/* Tooltip */}
      {hover && (
        <div style={{
          position: 'absolute', bottom: '110%', left: '50%',
          transform: 'translateX(-50%)',
          background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
          borderRadius: 8, padding: '8px 12px', zIndex: 100,
          whiteSpace: 'nowrap', fontSize: "var(--text-xs)", color: 'var(--text-1)',
          boxShadow: '0 8px 24px rgba(0,0,0,0.6)',
          minWidth: 140,
        }}>
          <div style={{ fontWeight: 700, marginBottom: 4, color }}>{STATUS_LABEL[week.status ?? '']}</div>
          <div>Comprometido: <strong>{week.committed_hours}h</strong></div>
          <div>Disponible: <strong>{week.available_hours}h</strong></div>
          <div style={{ marginTop: 4, fontSize: "var(--text-2xs)", color: 'var(--text-2)' }}>{week.week}</div>
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
  const isSelected = selectedUser === user.user_id
  const avgColor = STATUS_COLOR[estadoDeCarga(user.avg_load_pct)]

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
      {/* Nombre usuario */}
      <button
        type="button"
        onClick={() => onSelect(isSelected ? null : user.user_id)}
        style={{
          width: nameWidth, flexShrink: 0, fontSize: "var(--text-sm)", fontWeight: 600,
          color: isSelected ? 'var(--accent)' : 'var(--text-1)',
          cursor: 'pointer', padding: '4px 6px', borderRadius: 6,
          background: isSelected ? 'var(--accent-muted)' : 'transparent',
          border: isSelected ? '1px solid rgba(79,142,247,0.3)' : '1px solid transparent',
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', textAlign:'left', fontFamily:'inherit'
        }}
        title={user.user_name ?? ''}
      >
        {(user.user_name ?? '').split(' ')[0]} {(user.user_name ?? '').split(' ')[1]?.[0] || ''}.
      </button>

      {/* Carga media */}
      <div style={{
        width: 44, flexShrink: 0, fontSize: "var(--text-2xs)", fontWeight: 700,
        color: avgColor, textAlign: 'right', fontFamily: 'var(--font-mono)',
      }}>
        {user.avg_load_pct}%
      </div>

      {/* Celdas del heatmap */}
      <div style={{ display: 'flex', gap: 3, flex: 1, overflowX: 'hidden' }}>
        {(user.weeks ?? []).map(w => <HeatCell key={w.week} week={w} />)}
      </div>

      {/* Indicador semanas saturadas */}
      {(user.overloaded_weeks ?? 0) > 0 && (
        <div style={{
          fontSize: "var(--text-2xs)", padding: '1px 6px', borderRadius: 4,
          background: 'var(--danger-bg)', color: 'var(--danger)', flexShrink: 0,
        }}>
          ⚠ {user.overloaded_weeks}s
        </div>
      )}
    </div>
  )
}

// ── Panel de detalle de usuario ───────────────────────────────────────────────
function UserDetailPanel({ userId, weeks }: { userId: string | number; weeks: number }) {
  const _toast = useToast()
  const { data, isLoading } = useQuery<DetalleDeCarga>({
    queryKey: ['forecast-user', userId, weeks],
    queryFn: () => forecastApi.userDetail(userId, { weeks }).then(r => r.data),
    enabled: !!userId,
  })

  if (isLoading) return (
    <div style={{ padding: 20, color: 'var(--text-2)', fontSize: "var(--text-sm)", textAlign: 'center' }}>
      Cargando detalle...
    </div>
  )
  if (!data) return null

  return (
    <div style={{
      background: 'var(--surface-1)', border: '1px solid rgba(79,142,247,0.2)',
      borderRadius: 12, padding: '18px 20px', marginTop: 16,
    }}>
      <div style={{ fontSize: "var(--text-md)", fontWeight: 700, marginBottom: 14, color: 'var(--accent)' }}>
        📊 {data?.user_name} — Detalle {weeks} semanas
      </div>
      <div className="u-scroll-x">
        <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: "var(--text-xs)" }}>
          <thead>
            <tr>
              <th style={{ textAlign: 'left', color: 'var(--text-2)', padding: '4px 8px', borderBottom: '1px solid var(--surface-4)' }}>Semana</th>
              <th style={{ textAlign: 'right', color: 'var(--text-2)', padding: '4px 8px', borderBottom: '1px solid var(--surface-4)' }}>Carga</th>
              <th style={{ textAlign: 'right', color: 'var(--text-2)', padding: '4px 8px', borderBottom: '1px solid var(--surface-4)' }}>Comprometido</th>
              <th style={{ textAlign: 'right', color: 'var(--text-2)', padding: '4px 8px', borderBottom: '1px solid var(--surface-4)' }}>Disponible</th>
              <th style={{ textAlign: 'left', color: 'var(--text-2)', padding: '4px 8px', borderBottom: '1px solid var(--surface-4)' }}>Proyectos</th>
            </tr>
          </thead>
          <tbody>
            {(data?.weeks ?? []).map(w => {
              const color = STATUS_COLOR[estadoDeCarga(w.load_pct)]
              return (
                <tr key={w.week} style={{ borderBottom: '1px solid var(--surface-1)' }}>
                  <td style={{ padding: '5px 8px', color: 'var(--text-2)' }}>{w.week}</td>
                  <td style={{ padding: '5px 8px', textAlign: 'right', color, fontWeight: 700 }}>{w.load_pct}%</td>
                  <td style={{ padding: '5px 8px', textAlign: 'right', color: 'var(--text-1)' }}>{w.committed_hours}h</td>
                  <td style={{ padding: '5px 8px', textAlign: 'right', color: 'var(--success)' }}>{w.available_hours}h</td>
                  <td style={{ padding: '5px 8px', color: 'var(--text-2)', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
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

  const { data: heatmapData, isLoading: loadingHeatmap } = useQuery<RespuestaDeHeatmap>({
    queryKey: ['forecast-heatmap', weeks, department],
    queryFn: () => forecastApi.heatmap({ weeks, department: department || undefined }).then(r => r.data),
    staleTime: 60000,
  })

  const { data: summaryData, isLoading: loadingSummary, isError: summaryError } = useQuery<ResumenDeCarga>({
    queryKey: ['forecast-summary', weeks, department],
    queryFn: () => forecastApi.summary({ weeks, department: department || undefined }).then(r => r.data),
    staleTime: 60000,
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

  const panel = { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 14, padding: '16px 20px' }

  return (
    <PageShell>
      <PageHeader
        title={_t('resource_forecast.title')}
        subtitle={_t('resource_forecast.subtitle', { weeks })}
        icon={<BarChart size={18} />}
      />

      {/* KPIs de resumen */}
      {summaryData && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(140px, 100%), 1fr))', gap: 12, marginBottom: 24 }}>
          {[
            { label: 'Carga media equipo',  value: `${summary.avg_team_load_pct}%`, color: summary.avg_team_load_pct > 85 ? 'var(--danger)' : 'var(--accent)' },
            { label: 'Horas disponibles',   value: `${summary.total_available_hrs}h`, color: 'var(--success)' },
            { label: 'Horas comprometidas', value: `${summary.total_committed_hrs}h`, color: 'var(--purple)' },
            { label: 'Semanas de riesgo',   value: summary.risk_weeks_count, color: summary.risk_weeks_count > 0 ? 'var(--warning)' : 'var(--success)' },
            { label: 'Personas saturadas',  value: summary.overloaded_users_count, color: summary.overloaded_users_count > 0 ? 'var(--danger)' : 'var(--success)' },
          ].map(k => (
            <div key={k.label} style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, padding: '14px 18px', textAlign: 'center' }}>
              <div style={{ fontSize: "var(--text-xl-em)", fontWeight: 800, color: k.color, fontFamily: 'var(--font-mono)', lineHeight: 1.1 }}>
                {k.value}
              </div>
              <div className="u-hint">{k.label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Controles */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 20, flexWrap: 'wrap', alignItems: 'center' }}>
        <div style={{ display: 'flex', gap: 4, background: 'var(--surface-1)', borderRadius: 10, padding: 4 }}>
          {[
            { id: 'heatmap', label: 'Heatmap' },
            { id: 'summary', label: 'Resumen' },
          ].map(v => (
            <button key={v.id} onClick={() => setView(v.id)} style={{
              padding: '6px 16px', borderRadius: 7, border: 'none',
              background: view === v.id ? 'var(--accent-muted)' : 'transparent',
              color: view === v.id ? 'var(--accent)' : 'var(--text-2)',
              cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit', fontWeight: 600,
              outline: view === v.id ? '1px solid rgba(79,142,247,0.3)' : 'none',
            }}>{v.label}</button>
          ))}
        </div>

        <select value={weeks} onChange={e => setWeeks(+e.target.value)} style={{
          background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 8,
          padding: '6px 12px', color: 'var(--text-1)', fontSize: "var(--text-sm)", fontFamily: 'inherit', outline: 'none',
        }}>
          {[4,8,13,26,52].map(n => (
            <option key={n} value={n}>{n} semanas</option>
          ))}
        </select>

        <input
          aria-label="Departamento"
          placeholder="Departamento..."
          value={department}
          onChange={e => setDepartment(e.target.value)}
          style={{
            background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 8,
            padding: '6px 12px', color: 'var(--text-1)', fontSize: "var(--text-sm)", outline: 'none', fontFamily: 'inherit',
            minWidth: 0, maxWidth: '100%',
          }}
        />
      </div>

      {/* Vista heatmap */}
      {view === 'heatmap' && (
        <div style={panel}>
          <div className="u-scroll-x">
          <div style={{ minWidth: !loadingHeatmap && users.length > 0 ? 'max-content' : undefined }}>
          {/* Cabecera de semanas */}
          <div style={{ display: 'flex', gap: 8, marginBottom: 8, alignItems: 'center' }}>
            <div style={{ width: nameWidth, flexShrink: 0 }} />
            <div style={{ width: 44, flexShrink: 0 }} />
            <div style={{ display: 'flex', gap: 3, flex: 1, overflowX: 'hidden' }}>
              {weekLabels.slice(0, VISIBLE_WEEKS).map(w => (
                <div key={w} style={{
                  width: 36, flexShrink: 0, fontSize: "var(--text-8)", color: 'var(--text-3)',
                  textAlign: 'center', fontFamily: 'var(--font-mono)',
                  transform: 'rotate(-45deg)', transformOrigin: 'center',
                  marginTop: 8,
                }}>
                  {w.split('-W')[1]}
                </div>
              ))}
            </div>
          </div>

          {loadingHeatmap ? (
            <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-2)' }}>
              {t('resourceforecast.calculando_proyeccion')}
            </div>
          ) : users.length === 0 ? (
            <EmptyState icon="📈" title={t('resourceforecast.sin_datos_de_prevision')}
              description="Selecciona un horizonte y aplica filtros para ver la prevision" />
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
          <div style={{ display: 'flex', gap: 14, marginTop: 16, paddingTop: 12, borderTop: '1px solid var(--surface-4)', flexWrap: 'wrap' }}>
            {Object.entries(STATUS_COLOR).map(([k, c]) => k !== 'available' && (
              <div key={k} style={{ display: 'flex', gap: 5, alignItems: 'center', fontSize: "var(--text-2xs)", color: 'var(--text-2)' }}>
                <div style={{ width: 10, height: 10, borderRadius: 2, background: c }} />
                {STATUS_LABEL[k]}
              </div>
            ))}
            <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-2)', marginLeft: 'auto' }}>
              {t('resourceforecast.haz_clic_en_un_nombre_para_ver')}
            </div>
          </div>
        </div>
      )}

      {/* Vista resumen semanal */}
      {view === 'summary' && (
        <div style={panel}>
          <div style={{ fontSize: "var(--text-md)", fontWeight: 700, marginBottom: 16 }}>
            {t('resourceforecast.tendencia_de_carga_del_equipo')} {weeks} semanas
          </div>
          {loadingSummary ? (
            <div style={{ textAlign: 'center', padding: '40px 0', color: 'var(--text-2)', fontSize: "var(--text-base)" }}>
              Cargando resumen...
            </div>
          ) : summaryError ? (
            <div style={{ textAlign: 'center', padding: '40px 0', color: 'var(--danger)', fontSize: "var(--text-base)" }}>
              {t('resourceforecast.no_se_pudo_cargar_el_resumen_de')}
            </div>
          ) : summary.week_trend.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '40px 0', color: 'var(--text-2)', fontSize: "var(--text-base)" }}>
              {t('resourceforecast.sin_datos_de_carga_disponibles_configura_usuarios')}
            </div>
          ) : (
          <div className="u-stack-6">
            {(summary.week_trend || []).map(w => {
              const pct = w.load_pct ?? 0
              const color = STATUS_COLOR[estadoDeCarga(pct)]
              return (
                <div key={w.week} className="u-row-center-10">
                  <div style={{ fontSize: "var(--text-2xs)", color: 'var(--text-2)', width: 70, fontFamily: 'var(--font-mono)', flexShrink: 0 }}>
                    {w.week}
                  </div>
                  <div style={{ flex: 1, height: 20, background: 'var(--surface-1)', borderRadius: 4, overflow: 'hidden' }}>
                    <div style={{
                      width: `${Math.min(pct, 100)}%`, height: '100%',
                      background: color,
                      opacity: 0.35,
                      borderRadius: 4,
                      transition: 'width 0.3s',
                    }} />
                  </div>
                  <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color, width: 44, textAlign: 'right', fontFamily: 'var(--font-mono)' }}>
                    {pct}%
                  </div>
                  {(summary.risk_weeks || []).includes(w.week) && (
                    <span style={{ fontSize: "var(--text-2xs)", color: 'var(--danger)' }}>⚠</span>
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
