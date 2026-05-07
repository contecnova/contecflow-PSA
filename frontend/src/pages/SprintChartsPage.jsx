/**
 * SprintChartsPage — Burnup chart + Velocity trend per project
 *
 * Routes: /sprint-charts
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { projectsApi, projectSprintsApi } from '../services/api'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { BarChart2 } from 'lucide-react'
import { Spinner, EmptyState } from '../components/ui'
import { useAppT } from '../i18n/AppLangContext'
import {
  ComposedChart, Area, Line, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, ReferenceLine,
} from 'recharts'

const sf = { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 10, padding: 20 }

export default function SprintChartsPage() {
  const _t = useAppT()
  const [projectId, setProjectId] = useState('')
  const [sprintId,  setSprintId]  = useState('')

  const { data: projects = [] } = useQuery({
    queryKey: ['projects-list'],
    queryFn: () => projectsApi.list().then(r => Array.isArray(r.data) ? r.data : r.data?.items || []),
  })

  const { data: sprintsData } = useQuery({
    queryKey: ['project-sprints-list', projectId],
    queryFn: () => projectSprintsApi.list(projectId).then(r => r.data),
    enabled: !!projectId,
  })

  const sprints = Array.isArray(sprintsData) ? sprintsData : sprintsData?.sprints || []

  const { data: burnupData, isLoading: loadBU } = useQuery({
    queryKey: ['burnup', projectId, sprintId],
    queryFn: () => projectSprintsApi.burnup(projectId, sprintId).then(r => r.data),
    enabled: !!projectId && !!sprintId,
  })

  const { data: velocityData, isLoading: loadVel } = useQuery({
    queryKey: ['velocity', projectId],
    queryFn: () => projectSprintsApi.velocity(projectId).then(r => r.data),
    enabled: !!projectId,
  })

  const burnup   = burnupData?.burnup   || []
  const velocity = velocityData?.sprints || []
  const avgVel   = velocityData?.avg_velocity || 0

  const sel = {
    background: 'var(--surface-4)', border: '1px solid var(--surface-5)', borderRadius: 8,
    padding: '9px 14px', color: 'var(--text-1)', fontSize: "var(--text-base)",
    outline: 'none', fontFamily: 'inherit', cursor: 'pointer',
  }

  return (
    <PageShell style={{ maxWidth: 1050, margin: '0 auto' }}>
      <PageHeader
        icon={<BarChart2 size={18} />}
        title="Graficas de sprint"
        subtitle={_t('sprint_charts.subtitle')}
      showListExport={false}
      />

      {/* Project + Sprint selectors */}
      <div style={{ display: 'flex', gap: 14, marginBottom: 28, flexWrap: 'wrap' }}>
        <div style={{ flex: 1, minWidth: 200 }}>
          <label style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', display: 'block', marginBottom: 6 }}>
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
            <label style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', display: 'block', marginBottom: 6 }}>
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
            <h3 style={{ margin: 0, fontSize: "var(--text-lg)", color: 'var(--text-1)' }}>📊 Velocity — Últimos sprints</h3>
            {avgVel > 0 && (
              <span style={{ fontSize: "var(--text-base)", color: 'var(--text-2)' }}>
                Velocidad media: <strong style={{ color: 'var(--info)' }}>{avgVel} pts</strong>
              </span>
            )}
          </div>
          {loadVel ? <Spinner /> : velocity.length === 0 ? (
            <EmptyState icon="📊" title="Sin datos de velocidad" description="Completa sprints para ver la grafica de velocidad" />
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <ComposedChart data={velocity} margin={{ top: 10, right: 20, bottom: 0, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-4)" />
                <XAxis dataKey="sprint" tick={{ fill: 'var(--text-2)', fontSize: "var(--text-xs)" }} />
                <YAxis tick={{ fill: 'var(--text-2)', fontSize: "var(--text-xs)" }} />
                <Tooltip
                  contentStyle={{ background: 'var(--surface-2)', border: '1px solid var(--surface-5)', borderRadius: 8, fontSize: "var(--text-sm)" }}
                  labelStyle={{ color: 'var(--text-1)', fontWeight: 600 }}
                  itemStyle={{ color: 'var(--text-2)' }}
                />
                <Legend wrapperStyle={{ fontSize: "var(--text-sm)", color: 'var(--text-2)' }} />
                <Bar dataKey="planned"   name="Planificados" fill="var(--surface-5)" radius={[4,4,0,0]} />
                <Bar dataKey="completed" name="Completados"  fill="var(--purple)" radius={[4,4,0,0]} />
                <Line dataKey="velocity" name="Velocidad"    stroke="var(--success)" strokeWidth={2} dot={{ r: 4, fill: 'var(--success)' }} type="monotone" />
                {avgVel > 0 && (
                  <ReferenceLine y={avgVel} stroke="var(--info)" strokeDasharray="4 4"
                    label={{ value: `Avg ${avgVel}`, fill: 'var(--info)', fontSize: "var(--text-xs)", position: 'right' }} />
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
            <h3 style={{ margin: 0, fontSize: "var(--text-lg)", color: 'var(--text-1)' }}>📈 Burnup — {burnupData?.sprint?.name || 'Sprint'}</h3>
            {burnupData?.target > 0 && (
              <span style={{ fontSize: "var(--text-base)", color: 'var(--text-2)' }}>
                Objetivo: <strong style={{ color: 'var(--warning)' }}>{burnupData.target} pts</strong>
              </span>
            )}
          </div>
          {loadBU ? <Spinner /> : burnup.length === 0 ? (
            <EmptyState icon="📈" title="Sin datos de burnup" description="Inicia un sprint para ver el progreso del burnup" />
          ) : (
            <>
              <p style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginBottom: 16, marginTop: 0 }}>
                El burnup muestra el progreso acumulado (completado) frente al alcance total. Si la línea azul sube, el scope ha aumentado (scope creep).
              </p>
              <ResponsiveContainer width="100%" height={280}>
                <ComposedChart data={burnup} margin={{ top: 10, right: 20, bottom: 0, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-4)" />
                  <XAxis dataKey="date" tick={{ fill: 'var(--text-2)', fontSize: "var(--text-xs)" }} />
                  <YAxis tick={{ fill: 'var(--text-2)', fontSize: "var(--text-xs)" }} />
                  <Tooltip
                    contentStyle={{ background: 'var(--surface-2)', border: '1px solid var(--surface-5)', borderRadius: 8, fontSize: "var(--text-sm)" }}
                    labelStyle={{ color: 'var(--text-1)', fontWeight: 600 }}
                    itemStyle={{ color: 'var(--text-2)' }}
                  />
                  <Legend wrapperStyle={{ fontSize: "var(--text-sm)", color: 'var(--text-2)' }} />
                  <Area
                    type="monotone"
                    dataKey="scope"
                    name="Scope (total)"
                    fill="var(--surface-4)"
                    stroke="var(--info)"
                    strokeWidth={2}
                    fillOpacity={0.3}
                  />
                  <Line
                    type="monotone"
                    dataKey="completed"
                    name="Completado"
                    stroke="var(--success)"
                    strokeWidth={2.5}
                    dot={{ r: 3, fill: 'var(--success)' }}
                  />
                  {burnupData?.target > 0 && (
                    <ReferenceLine
                      y={burnupData.target}
                      stroke="var(--warning)"
                      strokeDasharray="5 5"
                      label={{ value: 'Objetivo', fill: 'var(--warning)', fontSize: "var(--text-xs)", position: 'right' }}
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
                      { label: 'Completado', value: `${last.completed} pts`, color: 'var(--success)' },
                      { label: 'Scope total', value: `${last.scope} pts`, color: 'var(--info)' },
                      { label: 'Progreso', value: `${pct}%`, color: pct >= 80 ? 'var(--success)' : pct >= 50 ? 'var(--warning)' : 'var(--danger)' },
                    ].map(k => (
                      <div key={k.label} style={{
                        flex: 1, background: 'var(--surface-1)', border: '1px solid var(--surface-4)',
                        borderRadius: 8, padding: '12px 16px',
                      }}>
                        <div style={{ fontSize: "var(--text-xl)", fontWeight: 800, color: k.color }}>{k.value}</div>
                        <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginTop: 2 }}>{k.label}</div>
                      </div>
                    ))}
                  </div>
                )
              })()}
            </>
          )}
        </div>
      )}
    </PageShell>
  )
}
