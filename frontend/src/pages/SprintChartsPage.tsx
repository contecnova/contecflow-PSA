/**
 * SprintChartsPage — Burnup chart + Velocity trend per project
 *
 * Routes: /sprint-charts
 */

import { useState, useId } from 'react'
import type { CSSProperties } from 'react'
import { useQuery } from '@tanstack/react-query'
import { projectsApi, projectSprintsApi } from '../services/api'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { BarChart2 } from 'lucide-react'
import { Spinner, EmptyState } from '../components/ui'
import { useAppT } from '../i18n/AppLangContext'
import { localeActivo } from '../utils/helpers'
import {
  ComposedChart, Area, Line, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, ReferenceLine,
} from 'recharts'
import './SprintChartsPage.css'

interface ProjectItem {
  id: string | number
  code?: string
  name?: string
}

export default function SprintChartsPage() {
  const idCampo = useId()
  const t = useAppT()
  const fmtNum = (n: number) => new Intl.NumberFormat(localeActivo()).format(n)
  const [projectId, setProjectId] = useState('')
  const [sprintId,  setSprintId]  = useState('')

  const { data: projects = [] } = useQuery<ProjectItem[]>({
    queryKey: ['projects-list'],
    queryFn: () => projectsApi.list({}).then(r => r.data ?? []),
  })

  const { data: sprints = [] } = useQuery({
    queryKey: ['project-sprints-list', projectId],
    queryFn: () => projectSprintsApi.list(projectId).then(r => r.data),
    enabled: !!projectId,
  })

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

  return (
    <PageShell className="spc-shell">
      <PageHeader
        icon={<BarChart2 size={18} />}
        title={t('sprintcharts.graficas_de_sprint')}
        subtitle={t('sprint_charts.subtitle')}
      showListExport={false}
      />

      {/* Project + Sprint selectors */}
      <div className="spc-selectors">
        <div className="spc-field">
          <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="spc-label">
            {t('sprint_charts_page.proyecto')}
          </label>
          <select id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={projectId} onChange={e => { setProjectId(e.target.value); setSprintId('') }} className="spc-select">
            <option value="">{t('sprintcharts.selecciona_un_proyecto')}</option>
            {projects.map(p => (
              <option key={p.id} value={p.id}>{p.code} — {p.name}</option>
            ))}
          </select>
        </div>
        {projectId && (
          <div className="spc-field spc-field--sprint">
            <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="spc-label">
              {t('sprintcharts.sprint_para_burnup')}
            </label>
            <select id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={sprintId} onChange={e => setSprintId(e.target.value)} className="spc-select">
              <option value="">{t('sprintcharts.selecciona_un_sprint')}</option>
              {sprints.map(s => (
                <option key={s.id} value={s.id}>{s.name} ({s.status})</option>
              ))}
            </select>
          </div>
        )}
      </div>

      {!projectId && (
        <EmptyState icon="📈" title={t('sprintcharts.selecciona_un_proyecto_2')} description={t('sprint_charts_page.vacio_proyecto')} />
      )}

      {/* Velocity chart */}
      {projectId && (
        <div className="spc-card spc-card--mb">
          <div className="u-row-between-mb16">
            <h3 className="spc-title">{t('sprintcharts.velocity_ultimos_sprints')}</h3>
            {avgVel > 0 && (
              <span className="u-text2-base">
                {t('sprint_charts_page.velocidad_media')}: <strong className="spc-info">{t('sprint_charts_page.n_pts', { n: fmtNum(avgVel) })}</strong>
              </span>
            )}
          </div>
          {loadVel ? <Spinner /> : velocity.length === 0 ? (
            <EmptyState icon="📊" title={t('sprintcharts.sin_datos_de_velocidad')} description={t('sprint_charts_page.vacio_velocidad')} />
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
                <Bar dataKey="planned"   name={t('sprint_charts_page.planificados')} fill="var(--surface-5)" radius={[4,4,0,0]} />
                <Bar dataKey="completed" name={t('sprint_charts_page.completados')} fill="var(--purple)" radius={[4,4,0,0]} />
                <Line dataKey="velocity" name={t('sprint_charts_page.velocidad')} stroke="var(--success)" strokeWidth={2} dot={{ r: 4, fill: 'var(--success)' }} type="monotone" />
                {avgVel > 0 && (
                  <ReferenceLine y={avgVel} stroke="var(--info)" strokeDasharray="4 4"
                    label={{ value: t('sprint_charts_page.media_n', { n: fmtNum(avgVel) }), fill: 'var(--info)', fontSize: "var(--text-xs)", position: 'right' }} />
                )}
              </ComposedChart>
            </ResponsiveContainer>
          )}
        </div>
      )}

      {/* Burnup chart */}
      {projectId && sprintId && (
        <div className="spc-card">
          <div className="u-row-between-mb16">
            <h3 className="spc-title">📈 {t('sprint_charts_page.burnup_titulo', { nombre: burnupData?.sprint?.name || t('sprint_charts_page.sprint') })}</h3>
            {(burnupData?.target ?? 0) > 0 && (
              <span className="u-text2-base">
                {t('sprint_charts_page.objetivo')}: <strong className="u-warning">{t('sprint_charts_page.n_pts', { n: fmtNum(burnupData?.target ?? 0) })}</strong>
              </span>
            )}
          </div>
          {loadBU ? <Spinner /> : burnup.length === 0 ? (
            <EmptyState icon="📈" title={t('sprintcharts.sin_datos_de_burnup')} description={t('sprint_charts_page.vacio_burnup')} />
          ) : (
            <>
              <p className="spc-note">
                {t('sprintcharts.el_burnup_muestra_el_progreso_acumulado_completado')}
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
                    name={t('sprint_charts_page.scope_total_serie')}
                    fill="var(--surface-4)"
                    stroke="var(--info)"
                    strokeWidth={2}
                    fillOpacity={0.3}
                  />
                  <Line
                    type="monotone"
                    dataKey="completed"
                    name={t('sprint_charts_page.completado')}
                    stroke="var(--success)"
                    strokeWidth={2.5}
                    dot={{ r: 3, fill: 'var(--success)' }}
                  />
                  {(burnupData?.target ?? 0) > 0 && (
                    <ReferenceLine
                      y={burnupData?.target}
                      stroke="var(--warning)"
                      strokeDasharray="5 5"
                      label={{ value: t('sprint_charts_page.objetivo'), fill: 'var(--warning)', fontSize: "var(--text-xs)", position: 'right' }}
                    />
                  )}
                </ComposedChart>
              </ResponsiveContainer>

              {/* Burnup KPIs */}
              {burnup.length > 0 && (() => {
                const last = burnup[burnup.length - 1]
                const pct  = last.scope > 0 ? Math.round(last.completed / last.scope * 100) : 0
                return (
                  <div className="spc-kpis">
                    {[
                      { label: t('sprint_charts_page.completado'), value: t('sprint_charts_page.n_pts', { n: fmtNum(last.completed) }), color: 'var(--success)' },
                      { label: t('sprint_charts_page.scope_total'), value: t('sprint_charts_page.n_pts', { n: fmtNum(last.scope) }), color: 'var(--info)' },
                      { label: t('sprint_charts_page.progreso'), value: `${fmtNum(pct)}%`, color: pct >= 80 ? 'var(--success)' : pct >= 50 ? 'var(--warning)' : 'var(--danger)' },
                    ].map(k => (
                      <div key={k.label} className="spc-kpi">
                        <div className="spc-kpi-value" style={{ '--spc-color': k.color } as CSSProperties}>{k.value}</div>
                        <div className="u-text2-xs-mt2">{k.label}</div>
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
