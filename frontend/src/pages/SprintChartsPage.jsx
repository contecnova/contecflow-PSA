/**
 * SprintChartsPage — Burnup chart + Velocity trend per project
 *
 * Routes: /sprint-charts
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import api from '../services/api'
import PageHeader from '../components/layout/PageHeader'
import { Spinner, EmptyState } from '../components/ui'
import { useAppT } from '../i18n/AppLangContext'
import {
  ComposedChart, Area, Line, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, ReferenceLine,
} from 'recharts'

const sf = { background: '#1a202c', border: '1px solid #2d3748', borderRadius: 10, padding: 20 }

export default function SprintChartsPage() {
  const _t = useAppT()
  const [projectId, setProjectId] = useState('')
  const [sprintId,  setSprintId]  = useState('')

  const { data: projects = [] } = useQuery({
    queryKey: ['projects-list'],
    queryFn: () => api.get('/projects').then(r => Array.isArray(r.data) ? r.data : r.data?.items || []),
  })

  const { data: sprintsData } = useQuery({
    queryKey: ['sprints', projectId],
    queryFn: () => api.get(`/sprints/${projectId}/sprints`).then(r => r.data),
    enabled: !!projectId,
  })

  const sprints = Array.isArray(sprintsData) ? sprintsData : sprintsData?.sprints || []

  const { data: burnupData, isLoading: loadBU } = useQuery({
    queryKey: ['burnup', projectId, sprintId],
    queryFn: () => api.get(`/sprints/${projectId}/sprints/${sprintId}/burnup`).then(r => r.data),
    enabled: !!projectId && !!sprintId,
  })

  const { data: velocityData, isLoading: loadVel } = useQuery({
    queryKey: ['velocity', projectId],
    queryFn: () => api.get(`/sprints/${projectId}/velocity`).then(r => r.data),
    enabled: !!projectId,
  })

  const burnup   = burnupData?.burnup   || []
  const velocity = velocityData?.sprints || []
  const avgVel   = velocityData?.avg_velocity || 0

  const sel = {
    background: '#2d3748', border: '1px solid #4a5568', borderRadius: 8,
    padding: '9px 14px', color: '#e2e8f0', fontSize: 13,
    outline: 'none', fontFamily: 'inherit', cursor: 'pointer',
  }

  return (
    <div style={{ padding: 32, maxWidth: 1050, margin: '0 auto' }}>
      <PageHeader
        title="Graficas de sprint"
        subtitle={_t('sprint_charts.subtitle')}
      />

      {/* Project + Sprint selectors */}
      <div style={{ display: 'flex', gap: 14, marginBottom: 28, flexWrap: 'wrap' }}>
        <div style={{ flex: 1, minWidth: 200 }}>
          <label style={{ fontSize: 11, fontWeight: 700, color: '#718096', display: 'block', marginBottom: 6 }}>
            PROYECTO
          </label>
          <select value={projectId} onChange={e => { setProjectId(e.target.value); setSprintId('') }} style={{ ...sel, width: '100%' }}>
            <option value="">Selecciona un proyecto...</option>
            {projects.map(p => (
              <option key={p.id} value={p.id}>{p.code} — {p.name}</option>
            ))}
          </select>
        </div>
        {projectId && (
          <div style={{ flex: 1, minWidth: 180 }}>
            <label style={{ fontSize: 11, fontWeight: 700, color: '#718096', display: 'block', marginBottom: 6 }}>
              SPRINT (para burnup)
            </label>
            <select value={sprintId} onChange={e => setSprintId(e.target.value)} style={{ ...sel, width: '100%' }}>
              <option value="">Selecciona un sprint...</option>
              {sprints.map(s => (
                <option key={s.id} value={s.id}>{s.name} ({s.status})</option>
              ))}
            </select>
          </div>
        )}
      </div>

      {!projectId && (
        <EmptyState icon="📈" title="Selecciona un proyecto" description="Elige un proyecto para ver las graficas de sprint" />
      )}

      {/* Velocity chart */}
      {projectId && (
        <div style={{ ...sf, marginBottom: 24 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <h3 style={{ margin: 0, fontSize: 16, color: '#e2e8f0' }}>📊 Velocity — Últimos sprints</h3>
            {avgVel > 0 && (
              <span style={{ fontSize: 13, color: '#718096' }}>
                Velocidad media: <strong style={{ color: '#90cdf4' }}>{avgVel} pts</strong>
              </span>
            )}
          </div>
          {loadVel ? <Spinner /> : velocity.length === 0 ? (
            <EmptyState icon="📊" title="Sin datos de velocidad" description="Completa sprints para ver la grafica de velocidad" />
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <ComposedChart data={velocity} margin={{ top: 10, right: 20, bottom: 0, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#2d3748" />
                <XAxis dataKey="sprint" tick={{ fill: '#718096', fontSize: 11 }} />
                <YAxis tick={{ fill: '#718096', fontSize: 11 }} />
                <Tooltip
                  contentStyle={{ background: '#1a202c', border: '1px solid #4a5568', borderRadius: 8, fontSize: 12 }}
                  labelStyle={{ color: '#e2e8f0', fontWeight: 600 }}
                  itemStyle={{ color: '#a0aec0' }}
                />
                <Legend wrapperStyle={{ fontSize: 12, color: '#718096' }} />
                <Bar dataKey="planned"   name="Planificados" fill="#4a5568" radius={[4,4,0,0]} />
                <Bar dataKey="completed" name="Completados"  fill="#9f7aea" radius={[4,4,0,0]} />
                <Line dataKey="velocity" name="Velocidad"    stroke="#68d391" strokeWidth={2} dot={{ r: 4, fill: '#68d391' }} type="monotone" />
                {avgVel > 0 && (
                  <ReferenceLine y={avgVel} stroke="#63b3ed" strokeDasharray="4 4"
                    label={{ value: `Avg ${avgVel}`, fill: '#63b3ed', fontSize: 11, position: 'right' }} />
                )}
              </ComposedChart>
            </ResponsiveContainer>
          )}
        </div>
      )}

      {/* Burnup chart */}
      {projectId && sprintId && (
        <div style={sf}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <h3 style={{ margin: 0, fontSize: 16, color: '#e2e8f0' }}>📈 Burnup — {burnupData?.sprint?.name || 'Sprint'}</h3>
            {burnupData?.target > 0 && (
              <span style={{ fontSize: 13, color: '#718096' }}>
                Objetivo: <strong style={{ color: '#f6e05e' }}>{burnupData.target} pts</strong>
              </span>
            )}
          </div>
          {loadBU ? <Spinner /> : burnup.length === 0 ? (
            <EmptyState icon="📈" title="Sin datos de burnup" description="Inicia un sprint para ver el progreso del burnup" />
          ) : (
            <>
              <p style={{ fontSize: 12, color: '#718096', marginBottom: 16, marginTop: 0 }}>
                El burnup muestra el progreso acumulado (completado) frente al alcance total. Si la línea azul sube, el scope ha aumentado (scope creep).
              </p>
              <ResponsiveContainer width="100%" height={280}>
                <ComposedChart data={burnup} margin={{ top: 10, right: 20, bottom: 0, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#2d3748" />
                  <XAxis dataKey="date" tick={{ fill: '#718096', fontSize: 11 }} />
                  <YAxis tick={{ fill: '#718096', fontSize: 11 }} />
                  <Tooltip
                    contentStyle={{ background: '#1a202c', border: '1px solid #4a5568', borderRadius: 8, fontSize: 12 }}
                    labelStyle={{ color: '#e2e8f0', fontWeight: 600 }}
                    itemStyle={{ color: '#a0aec0' }}
                  />
                  <Legend wrapperStyle={{ fontSize: 12, color: '#718096' }} />
                  <Area
                    type="monotone"
                    dataKey="scope"
                    name="Scope (total)"
                    fill="#2d3748"
                    stroke="#63b3ed"
                    strokeWidth={2}
                    fillOpacity={0.3}
                  />
                  <Line
                    type="monotone"
                    dataKey="completed"
                    name="Completado"
                    stroke="#68d391"
                    strokeWidth={2.5}
                    dot={{ r: 3, fill: '#68d391' }}
                  />
                  {burnupData?.target > 0 && (
                    <ReferenceLine
                      y={burnupData.target}
                      stroke="#f6e05e"
                      strokeDasharray="5 5"
                      label={{ value: 'Objetivo', fill: '#f6e05e', fontSize: 11, position: 'right' }}
                    />
                  )}
                </ComposedChart>
              </ResponsiveContainer>

              {/* Burnup KPIs */}
              {burnup.length > 0 && (() => {
                const last = burnup[burnup.length - 1]
                const pct  = last.scope > 0 ? Math.round(last.completed / last.scope * 100) : 0
                return (
                  <div style={{ display: 'flex', gap: 14, marginTop: 18 }}>
                    {[
                      { label: 'Completado', value: `${last.completed} pts`, color: '#68d391' },
                      { label: 'Scope total', value: `${last.scope} pts`, color: '#63b3ed' },
                      { label: 'Progreso', value: `${pct}%`, color: pct >= 80 ? '#68d391' : pct >= 50 ? '#f6e05e' : '#fc8181' },
                    ].map(k => (
                      <div key={k.label} style={{
                        flex: 1, background: '#0d1117', border: '1px solid #2d3748',
                        borderRadius: 8, padding: '12px 16px',
                      }}>
                        <div style={{ fontSize: 20, fontWeight: 800, color: k.color }}>{k.value}</div>
                        <div style={{ fontSize: 11, color: '#718096', marginTop: 2 }}>{k.label}</div>
                      </div>
                    ))}
                  </div>
                )
              })()}
            </>
          )}
        </div>
      )}
    </div>
  )
}
