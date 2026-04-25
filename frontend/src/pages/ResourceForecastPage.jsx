import { useState } from 'react'
import { useToast } from '../context/ToastContext'
import { useQuery } from '@tanstack/react-query'
import { forecastApi } from '../services/api'
import PageHeader from '../components/layout/PageHeader'
import { EmptyState } from '../components/ui'
import { BarChart } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'

const STATUS_COLOR = {
  overloaded: 'var(--danger)',
  high:       'var(--warning)',
  medium:     'var(--accent)',
  low:        'var(--success)',
  available:  'var(--surface-4)',
}
const STATUS_LABEL = {
  overloaded: 'Sobrecargado',
  high:       'Alto',
  medium:     'Medio',
  low:        'Bajo',
  available:  'Libre',
}

// ── Celda del heatmap ─────────────────────────────────────────────────────────
function HeatCell({ week }) {
  const [hover, setHover] = useState(false)
  const color = STATUS_COLOR[week.status] || 'var(--surface-4)'
  const pct   = Math.min(week.load_pct, 100)

  return (
    <div
      onPointerEnter={() => setHover(true)}
      onPointerLeave={() => setHover(false)}
      style={{
        position: 'relative', width: 36, height: 36, borderRadius: 6,
        background: 'var(--surface-1)', border: `1px solid ${color}30`,
        cursor: 'default', overflow: 'visible', flexShrink: 0,
      }}
    >
      {/* Barra de relleno proporcional */}
      <div style={{
        position: 'absolute', bottom: 0, left: 0, right: 0,
        height: `${pct}%`, background: color + '40',
        borderRadius: '0 0 5px 5px', transition: 'height 0.2s',
      }} />
      <div style={{
        position: 'absolute', inset: 0, display: 'flex',
        alignItems: 'center', justifyContent: 'center',
        fontSize: 9, fontWeight: 700, color,
        fontFamily: "'Space Mono', monospace",
      }}>
        {week.load_pct > 0 ? `${Math.round(week.load_pct)}%` : '—'}
      </div>

      {/* Tooltip */}
      {hover && (
        <div style={{
          position: 'absolute', bottom: '110%', left: '50%',
          transform: 'translateX(-50%)',
          background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
          borderRadius: 8, padding: '8px 12px', zIndex: 100,
          whiteSpace: 'nowrap', fontSize: 11, color: 'var(--text-1)',
          boxShadow: '0 8px 24px rgba(0,0,0,0.6)',
          minWidth: 140,
        }}>
          <div style={{ fontWeight: 700, marginBottom: 4, color }}>{STATUS_LABEL[week.status]}</div>
          <div>Comprometido: <strong>{week.committed_hours}h</strong></div>
          <div>Disponible: <strong>{week.available_hours}h</strong></div>
          <div style={{ marginTop: 4, fontSize: 10, color: 'var(--text-2)' }}>{week.week}</div>
        </div>
      )}
    </div>
  )
}

// ── Fila de usuario ───────────────────────────────────────────────────────────
function UserRow({ user, selectedUser, onSelect }) {
  const isSelected = selectedUser === user.user_id
  const avgColor = STATUS_COLOR[
    user.avg_load_pct > 100 ? 'overloaded' :
    user.avg_load_pct > 85  ? 'high' :
    user.avg_load_pct > 50  ? 'medium' :
    user.avg_load_pct > 10  ? 'low' : 'available'
  ]

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
      {/* Nombre usuario */}
      <button
        type="button"
        onClick={() => onSelect(isSelected ? null : user.user_id)}
        style={{
          width: 160, flexShrink: 0, fontSize: 12, fontWeight: 600,
          color: isSelected ? 'var(--accent)' : 'var(--text-1)',
          cursor: 'pointer', padding: '4px 6px', borderRadius: 6,
          background: isSelected ? 'var(--accent-muted)' : 'transparent',
          border: isSelected ? '1px solid rgba(79,142,247,0.3)' : '1px solid transparent',
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', textAlign:'left', fontFamily:'inherit'
        }}
        title={user.user_name}
      >
        {user.user_name.split(' ')[0]} {user.user_name.split(' ')[1]?.[0] || ''}.
      </button>

      {/* Carga media */}
      <div style={{
        width: 44, flexShrink: 0, fontSize: 10, fontWeight: 700,
        color: avgColor, textAlign: 'right', fontFamily: "'Space Mono', monospace",
      }}>
        {user.avg_load_pct}%
      </div>

      {/* Celdas del heatmap */}
      <div style={{ display: 'flex', gap: 3, flex: 1, overflowX: 'hidden' }}>
        {user.weeks.map(w => <HeatCell key={w.week} week={w} />)}
      </div>

      {/* Indicador semanas saturadas */}
      {user.overloaded_weeks > 0 && (
        <div style={{
          fontSize: 10, padding: '1px 6px', borderRadius: 4,
          background: 'var(--danger-bg)', color: 'var(--danger)', flexShrink: 0,
        }}>
          ⚠ {user.overloaded_weeks}s
        </div>
      )}
    </div>
  )
}

// ── Panel de detalle de usuario ───────────────────────────────────────────────
function UserDetailPanel({ userId, weeks }) {
  const _toast = useToast()
  const { data, isLoading } = useQuery({
    queryKey: ['forecast-user', userId, weeks],
    queryFn: () => forecastApi.userDetail(userId, { weeks }).then(r => r.data),
    enabled: !!userId,
  })

  if (isLoading) return (
    <div style={{ padding: 20, color: 'var(--text-2)', fontSize: 12, textAlign: 'center' }}>
      Cargando detalle...
    </div>
  )
  if (!data) return null

  return (
    <div style={{
      background: 'var(--surface-1)', border: '1px solid rgba(79,142,247,0.2)',
      borderRadius: 12, padding: '18px 20px', marginTop: 16,
    }}>
      <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 14, color: 'var(--accent)' }}>
        📊 {data.user_name} — Detalle {weeks} semanas
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 11 }}>
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
            {data.weeks.map(w => {
              const color = STATUS_COLOR[
                w.load_pct > 100 ? 'overloaded' :
                w.load_pct > 85  ? 'high' :
                w.load_pct > 50  ? 'medium' :
                w.load_pct > 10  ? 'low' : 'available'
              ]
              return (
                <tr key={w.week} style={{ borderBottom: '1px solid #0d1626' }}>
                  <td style={{ padding: '5px 8px', color: 'var(--text-2)' }}>{w.week}</td>
                  <td style={{ padding: '5px 8px', textAlign: 'right', color, fontWeight: 700 }}>{w.load_pct}%</td>
                  <td style={{ padding: '5px 8px', textAlign: 'right', color: 'var(--text-1)' }}>{w.committed_hours}h</td>
                  <td style={{ padding: '5px 8px', textAlign: 'right', color: 'var(--success)' }}>{w.available_hours}h</td>
                  <td style={{ padding: '5px 8px', color: 'var(--text-2)', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {w.breakdown.map(b => `${b.project_name} (${b.hours}h)`).join(', ') || '—'}
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
  const _t = useAppT()
  const _toast = useToast()
  const [weeks, setWeeks]             = useState(13)
  const [department, setDepartment]   = useState('')
  const [selectedUser, setSelectedUser] = useState(null)
  const [view, setView]               = useState('heatmap')   // heatmap | summary | availability

  const { data: heatmapData, isLoading: loadingHeatmap } = useQuery({
    queryKey: ['forecast-heatmap', weeks, department],
    queryFn: () => forecastApi.heatmap({ weeks, department: department || undefined }).then(r => r.data),
    staleTime: 60000,
  })

  const { data: summaryData } = useQuery({
    queryKey: ['forecast-summary', weeks, department],
    queryFn: () => forecastApi.summary({ weeks, department: department || undefined }).then(r => r.data),
    staleTime: 60000,
  })

  const weekLabels = heatmapData?.week_labels || []
  const users      = heatmapData?.users || []

  // Calcular slice de semanas visibles (máximo ~16 para no sobrecargar)
  const VISIBLE_WEEKS = Math.min(weeks, 16)
  const visibleUsers  = users

  const panel = { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 14, padding: '16px 20px' }

  return (
    <div style={{ padding: 32 }}>
      <PageHeader
        title={_t('resource_forecast.title')}
        subtitle={_t('resource_forecast.subtitle', { weeks })}
        icon={<BarChart size={18} />}
      />

      {/* KPIs de resumen */}
      {summaryData && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 12, marginBottom: 24 }}>
          {[
            { label: 'Carga media equipo',  value: `${summaryData.avg_team_load_pct}%`, color: summaryData.avg_team_load_pct > 85 ? 'var(--danger)' : 'var(--accent)' },
            { label: 'Horas disponibles',   value: `${summaryData.total_available_hrs}h`, color: 'var(--success)' },
            { label: 'Horas comprometidas', value: `${summaryData.total_committed_hrs}h`, color: 'var(--purple)' },
            { label: 'Semanas de riesgo',   value: summaryData.risk_weeks_count, color: summaryData.risk_weeks_count > 0 ? 'var(--warning)' : 'var(--success)' },
            { label: 'Personas saturadas',  value: summaryData.overloaded_users_count, color: summaryData.overloaded_users_count > 0 ? 'var(--danger)' : 'var(--success)' },
          ].map(k => (
            <div key={k.label} style={{ background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, padding: '14px 18px', textAlign: 'center' }}>
              <div style={{ fontSize: 22, fontWeight: 800, color: k.color, fontFamily: "'Space Mono', monospace", lineHeight: 1.1 }}>
                {k.value}
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 4 }}>{k.label}</div>
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
              cursor: 'pointer', fontSize: 12, fontFamily: 'inherit', fontWeight: 600,
              outline: view === v.id ? '1px solid rgba(79,142,247,0.3)' : 'none',
            }}>{v.label}</button>
          ))}
        </div>

        <select value={weeks} onChange={e => setWeeks(+e.target.value)} style={{
          background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 8,
          padding: '6px 12px', color: 'var(--text-1)', fontSize: 12, fontFamily: 'inherit', outline: 'none',
        }}>
          {[4,8,13,26,52].map(n => (
            <option key={n} value={n}>{n} semanas</option>
          ))}
        </select>

        <input
          placeholder="Departamento..."
          value={department}
          onChange={e => setDepartment(e.target.value)}
          style={{
            background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 8,
            padding: '6px 12px', color: 'var(--text-1)', fontSize: 12, outline: 'none', fontFamily: 'inherit',
          }}
        />
      </div>

      {/* Vista heatmap */}
      {view === 'heatmap' && (
        <div style={panel}>
          {/* Cabecera de semanas */}
          <div style={{ display: 'flex', gap: 8, marginBottom: 8, alignItems: 'center' }}>
            <div style={{ width: 160, flexShrink: 0 }} />
            <div style={{ width: 44, flexShrink: 0 }} />
            <div style={{ display: 'flex', gap: 3, flex: 1, overflowX: 'hidden' }}>
              {weekLabels.slice(0, VISIBLE_WEEKS).map(w => (
                <div key={w} style={{
                  width: 36, flexShrink: 0, fontSize: 8, color: 'var(--text-3)',
                  textAlign: 'center', fontFamily: "'Space Mono', monospace",
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
              Calculando proyección...
            </div>
          ) : users.length === 0 ? (
            <EmptyState icon="📈" title="Sin datos de prevision"
              description="Selecciona un horizonte y aplica filtros para ver la prevision" />
          ) : (
            <div>
              {visibleUsers.map(u => (
                <UserRow
                  key={u.user_id}
                  user={{ ...u, weeks: u.weeks.slice(0, VISIBLE_WEEKS) }}
                  selectedUser={selectedUser}
                  onSelect={setSelectedUser}
                />
              ))}
            </div>
          )}

          {/* Leyenda */}
          <div style={{ display: 'flex', gap: 14, marginTop: 16, paddingTop: 12, borderTop: '1px solid var(--surface-4)', flexWrap: 'wrap' }}>
            {Object.entries(STATUS_COLOR).map(([k, c]) => k !== 'available' && (
              <div key={k} style={{ display: 'flex', gap: 5, alignItems: 'center', fontSize: 10, color: 'var(--text-2)' }}>
                <div style={{ width: 10, height: 10, borderRadius: 2, background: c }} />
                {STATUS_LABEL[k]}
              </div>
            ))}
            <div style={{ fontSize: 10, color: 'var(--text-2)', marginLeft: 'auto' }}>
              Haz clic en un nombre para ver el detalle por proyecto
            </div>
          </div>
        </div>
      )}

      {/* Vista resumen semanal */}
      {view === 'summary' && (
        <div style={panel}>
          <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 16 }}>
            Tendencia de carga del equipo — {weeks} semanas
          </div>
          {(!summaryData || !summaryData.week_trend || summaryData.week_trend.length === 0) ? (
            <div style={{ textAlign: 'center', padding: '40px 0', color: 'var(--text-2)', fontSize: 13 }}>
              Sin datos de carga disponibles. Configura usuarios con capacidad semanal y asigna reservas de recursos.
            </div>
          ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {(summaryData.week_trend || []).map(w => {
              const pct = w.load_pct
              const color = pct > 100 ? 'var(--danger)' : pct > 85 ? 'var(--warning)' : pct > 50 ? 'var(--accent)' : 'var(--success)'
              return (
                <div key={w.week} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <div style={{ fontSize: 10, color: 'var(--text-2)', width: 70, fontFamily: "'Space Mono', monospace", flexShrink: 0 }}>
                    {w.week}
                  </div>
                  <div style={{ flex: 1, height: 20, background: 'var(--surface-1)', borderRadius: 4, overflow: 'hidden' }}>
                    <div style={{
                      width: `${Math.min(pct, 100)}%`, height: '100%',
                      background: color + '60', borderRadius: 4,
                      transition: 'width 0.3s',
                    }} />
                  </div>
                  <div style={{ fontSize: 11, fontWeight: 700, color, width: 44, textAlign: 'right', fontFamily: "'Space Mono', monospace" }}>
                    {pct}%
                  </div>
                  {(summaryData.risk_weeks || []).includes(w.week) && (
                    <span style={{ fontSize: 10, color: 'var(--danger)' }}>⚠</span>
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
    </div>
  )
}
