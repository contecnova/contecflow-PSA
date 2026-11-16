/**
 * SprintChartsPage — Burnup chart + Velocity trend per project
 *
 * Routes: /sprint-charts
 *
 * 16-11-2026: título igual que el menú ("Burnup y velocidad") y subtítulo
 * traducido (antes en inglés); sin ancho máximo centrado; selectores dentro de
 * una Card con ds-input (antes fondo gris suelto); gráficas en Card + Section;
 * KPIs con KpiCard; vacíos con icono lucide (antes emoji); estado del sprint
 * traducido y fechas del eje con el formato del idioma.
 */

import { useState, useId } from 'react'
import { useQuery } from '@tanstack/react-query'
import { projectsApi, projectSprintsApi } from '../services/api'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { Activity, BarChart2, CheckCircle2, FolderKanban, Gauge, Target, TrendingUp } from 'lucide-react'
import { Card, KpiCard, Section, Spinner, EmptyState } from '../components/ui'
import { useAppT } from '../i18n/AppLangContext'
import { localeActivo } from '../utils/helpers'
import {
  ComposedChart, Area, Line, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, ReferenceLine,
} from 'recharts'

// Recharts pinta el tooltip con estilos inline propios: solo se sobrescriben con estas props.
const TOOLTIP_CONTENT = { background: 'var(--surface-2)', border: '1px solid var(--surface-5)', borderRadius: 8, fontSize: 'var(--text-sm)' }
const TOOLTIP_LABEL = { color: 'var(--text-1)', fontWeight: 600 }
const TOOLTIP_ITEM = { color: 'var(--text-2)' }
import './SprintChartsPage.css'
import { LEYENDA_SM } from '../constants/estilosGrafico'

/** El burnup trae la fecha como MM-DD: se pinta como día y mes del idioma activo. */
function fmtMesDia(md: string): string {
  const [m, d] = md.split('-').map(Number)
  if (!m || !d) return md
  return new Intl.DateTimeFormat(localeActivo(), { day: 'numeric', month: 'short' }).format(new Date(2000, m - 1, d))
}

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
    <PageShell>
      <PageHeader
        icon={<Activity size={18} />}
        title={t('nav.sprint_charts')}
        subtitle={t('sprint_charts.subtitle')}
        showListExport={false}
      />

      <div className="u-stack-16">
      {/* Project + Sprint selectors */}
      <Card className="spc-filtros">
      <div className="spc-selectors">
        <div className="spc-field">
          <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="spc-label">
            {t('sprint_charts_page.proyecto')}
          </label>
          <select id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={projectId} onChange={e => { setProjectId(e.target.value); setSprintId('') }} className="ds-input">
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
            <select id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={sprintId} onChange={e => setSprintId(e.target.value)} className="ds-input">
              <option value="">{t('sprintcharts.selecciona_un_sprint')}</option>
              {sprints.map(s => (
                <option key={s.id} value={s.id}>{s.name} ({t(`sprints.status_${s.status}`, s.status || '')})</option>
              ))}
            </select>
          </div>
        )}
      </div>
      </Card>

      {!projectId && (
        <EmptyState icon={<FolderKanban size={28} />} title={t('sprintcharts.selecciona_un_proyecto_2')} description={t('sprint_charts_page.vacio_proyecto')} />
      )}

      {/* Velocity chart */}
      {projectId && (
        <Card>
          <Section
            title={<span className="spc-titulo"><BarChart2 size={16} aria-hidden />{t('sprintcharts.velocity_ultimos_sprints')}</span>}
            actions={avgVel > 0 ? (
              <span className="u-text2-base">
                {t('sprint_charts_page.velocidad_media')}: <strong className="spc-dato">{t('sprint_charts_page.n_pts', { n: fmtNum(avgVel) })}</strong>
              </span>
            ) : undefined}
          >
          {loadVel ? <Spinner /> : velocity.length === 0 ? (
            <EmptyState icon={<BarChart2 size={28} />} title={t('sprintcharts.sin_datos_de_velocidad')} description={t('sprint_charts_page.vacio_velocidad')} />
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <ComposedChart data={velocity} margin={{ top: 10, right: 20, bottom: 0, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-4)" />
                <XAxis dataKey="sprint" tick={{ fill: 'var(--text-2)', fontSize: "var(--text-xs)" }} />
                <YAxis tick={{ fill: 'var(--text-2)', fontSize: "var(--text-xs)" }} />
                <Tooltip
                  contentStyle={TOOLTIP_CONTENT}
                  labelStyle={TOOLTIP_LABEL}
                  itemStyle={TOOLTIP_ITEM}
                />
                <Legend wrapperStyle={LEYENDA_SM} />
                <Bar dataKey="planned"   name={t('sprint_charts_page.planificados')} fill="var(--surface-5)" radius={[4,4,0,0]} />
                <Bar dataKey="completed" name={t('sprint_charts_page.completados')} fill="var(--purple)" radius={[4,4,0,0]} />
                <Line dataKey="velocity" name={t('sprint_charts_page.velocidad')} stroke="var(--success)" strokeWidth={2} dot={{ r: 4, fill: 'var(--success)' }} type="monotone" />
                {avgVel > 0 && (
                  <ReferenceLine y={avgVel} stroke="var(--accent)" strokeDasharray="4 4"
                    label={{ value: t('sprint_charts_page.media_n', { n: fmtNum(avgVel) }), fill: 'var(--accent)', fontSize: "var(--text-xs)", position: 'right' }} />
                )}
              </ComposedChart>
            </ResponsiveContainer>
          )}
          </Section>
        </Card>
      )}

      {/* Burnup chart */}
      {projectId && sprintId && (
        <Card>
          <Section
            title={<span className="spc-titulo"><TrendingUp size={16} aria-hidden />{t('sprint_charts_page.burnup_titulo', { nombre: burnupData?.sprint?.name || t('sprint_charts_page.sprint') })}</span>}
            actions={(burnupData?.target ?? 0) > 0 ? (
              <span className="u-text2-base">
                {t('sprint_charts_page.objetivo')}: <strong className="spc-dato">{t('sprint_charts_page.n_pts', { n: fmtNum(burnupData?.target ?? 0) })}</strong>
              </span>
            ) : undefined}
          >
          {loadBU ? <Spinner /> : burnup.length === 0 ? (
            <EmptyState icon={<TrendingUp size={28} />} title={t('sprintcharts.sin_datos_de_burnup')} description={t('sprint_charts_page.vacio_burnup')} />
          ) : (
            <>
              <p className="spc-note">
                {t('sprintcharts.el_burnup_muestra_el_progreso_acumulado_completado')}
              </p>
              <ResponsiveContainer width="100%" height={280}>
                <ComposedChart data={burnup} margin={{ top: 10, right: 20, bottom: 0, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-4)" />
                  <XAxis dataKey="date" tickFormatter={(d: string) => fmtMesDia(d)} tick={{ fill: 'var(--text-2)', fontSize: "var(--text-xs)" }} />
                  <YAxis tick={{ fill: 'var(--text-2)', fontSize: "var(--text-xs)" }} />
                  <Tooltip
                    contentStyle={TOOLTIP_CONTENT}
                    labelStyle={TOOLTIP_LABEL}
                    itemStyle={TOOLTIP_ITEM}
                    labelFormatter={(d) => fmtMesDia(String(d))}
                  />
                  <Legend wrapperStyle={LEYENDA_SM} />
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
                  <div className="ds-grid-stats spc-kpis">
                    <KpiCard icon={<CheckCircle2 size={16} />} label={t('sprint_charts_page.completado')} value={t('sprint_charts_page.n_pts', { n: fmtNum(last.completed) })} />
                    <KpiCard icon={<Target size={16} />} label={t('sprint_charts_page.scope_total')} value={t('sprint_charts_page.n_pts', { n: fmtNum(last.scope) })} />
                    <KpiCard icon={<Gauge size={16} />} label={t('sprint_charts_page.progreso')} value={`${fmtNum(pct)}%`}
                      danger={pct < 50} warning={pct >= 50 && pct < 80} />
                  </div>
                )
              })()}
            </>
          )}
          </Section>
        </Card>
      )}
      </div>
    </PageShell>
  )
}
