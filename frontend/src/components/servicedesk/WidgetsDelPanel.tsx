/**
 * WidgetsDelPanel — un render propio por widget de «Mi panel» (19-11-2026).
 *
 * Antes cada widget se pintaba con `VistaDeDatos` (volcado genérico): claves
 * técnicas en inglés («Sla at risk count»), el UUID del incidente mayor en una
 * columna de 30 px y «—» en las aprobaciones. Ahora cada uno usa el lenguaje de
 * los paneles del sistema (MetricsDashboardTab, DashKit): KpiCard con tono por
 * umbral de la empresa, GaugeCard, BarRow, tablas con columnas útiles y
 * etiquetas i18n, EmptyState con mensaje y clic para abrir lo que se ve.
 *
 * Los renders son puros (reciben `datos`): MiPanel hace las peticiones. Nunca se
 * enseña un id interno: número/código, título, estado traducido, fechas
 * formateadas.
 */
import type { CSSProperties, ReactNode } from 'react'
import {
  AlertTriangle, Bot, CheckCircle2, ClipboardCheck, Flame, FolderOpen, GitPullRequestArrow, Inbox, ShieldAlert,
  Star, Ticket, Timer, Users,
} from 'lucide-react'
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useAppT } from '../../i18n/AppLangContext'
import { etiquetaCodigo } from '../../i18n/etiquetaCodigo'
import { Avatar, EmptyState, KpiCard, Pulsable, StatusBadge, TablaSimple } from '../ui'
import type { StatusBadgeKind } from '../ui'
import { BarRow, GaugeCard, typePalette } from '../dashboard/DashKit'
import { COLOR } from '../../constants/theme'
import { useTono, useUmbrales } from '../../hooks/useOrgSettings'
import { colorDeTono } from '../../utils/umbrales'
import type { Tono } from '../../utils/umbrales'
import { fmtDate, fmtDateTime, fmtRelative } from '../../utils/helpers'
import { useChartTheme } from '../../charts/useChartTheme'
import { tooltipDelTemaConBorde } from '../../constants/estilosGrafico'
import './sdMercado.css'

/* ── Tipos (los campos reales de cada endpoint) ──────────────────────────── */

/** `/sd/tickets/my-queue/prioritized` (ticket_out + puntuaciones). */
export interface TicketDeCola {
  id: string; number: string; title: string; status?: string | null; status_label?: string | null
  priority?: string | null; priority_label?: string | null; client_name?: string | null
  sla_resolution_due?: string | null; sla_resolution_status?: string | null
  priority_score?: number | null; sla_risk_score?: number | null; business_value_score?: number | null
}
/** `/sd/predictive/stats`. */
export interface EstadisticasDeRiesgo {
  open_tickets: number; severity_distribution: Record<string, number>; sla_at_risk_count: number
  sla_at_risk_pct: number; analyzed_tickets: number; truncated: boolean; failed_tickets?: number
}
/** `/sd/major-incidents` (serialize_major_incident). */
export interface IncidenteMayor {
  id: string; number: string | null; title: string; status: string; severity: string | null
  declared_at: string | null; resolved_at: string | null; commander: string | null; impact_statement: string | null
}
/** `/sd/metrics/itil`. */
export interface MetricasItil {
  volume?: { total: number; open: number; resolved: number; breached_sla: number }
  sla_compliance_pct?: number | null; mttr_minutes?: number | null; fcr_percent?: number | null
  avg_csat?: number | null; by_type?: Record<string, number>; by_priority?: Record<string, number>
  breach_by_priority?: Record<string, number>
}
/** `/sd/metrics/agent-performance` (una fila por agente). */
export interface RendimientoDeAgente {
  agent_id: string; agent_name: string; total: number; resolved: number; open: number
  mttr_minutes: number | null; avg_csat: number | null; sla_breaches: number
}
/** `/sd/autonomous/stats`. */
export interface EstadisticasDelAgente {
  total_executions: number; success: number; applied: number; suggested: number; discarded: number
  skipped: number; failed: number; success_rate_pct: number; by_playbook_type: Record<string, number>
}
/** Un cambio de `/sd/changes/cab-dashboard` (serialize_change). */
export interface CambioDelCab {
  id: string; number: string | null; title: string; change_type: string | null; status: string | null
  risk: string | null; planned_start: string | null; owner: string | null; requester: string | null
  auto_risk_score: number | null; auto_risk_label: string | null
}
export interface PanelDelCab { total: number; unscored: number; items: CambioDelCab[] }
/** `/sd/approvals/mine`. */
export interface AprobacionPendiente {
  approval_id: string; ticket_id: string; number: string; title: string
  requester_name: string | null; service_item_name: string | null; created_at: string | null
}

export interface PropsDeWidget<T> {
  datos: T
  /** Abre un ticket (detalle del service desk). */
  onAbrir: (ticketId: string) => void
  /** Va a otra pestaña del service desk (`mi`, `changes`, `queue`, `approvals`). */
  onIrA?: (pestana: string) => void
}

/* ── Utilidades ───────────────────────────────────────────────────────────── */

export function fmtMinutos(m: number | null | undefined): string {
  if (m == null || m === 0) return '—'
  if (m < 60) return `${Math.round(m)}m`
  const h = Math.floor(m / 60)
  const min = Math.round(m % 60)
  return min > 0 ? `${h}h ${min}m` : `${h}h`
}

/** Variación en % (redondeada); sin base, `null`. */
export function variacion(actual: number | null | undefined, previo: number | null | undefined): number | null {
  if (actual == null || previo == null || previo === 0) return null
  return Math.round(((actual - previo) / previo) * 100)
}

const COLOR_PRIORIDAD: Record<string, string> = {
  p1_critical: COLOR.danger, p2_high: 'var(--orange)', p3_medium: COLOR.warning, p4_low: COLOR.text3,
}
const COLOR_SEVERIDAD: Record<string, string> = {
  critical: COLOR.danger, high: 'var(--orange)', medium: COLOR.warning, low: COLOR.text3,
}
const TONO_SLA: Record<string, StatusBadgeKind> = { ok: 'success', at_risk: 'warning', breached: 'danger', paused: 'neutral' }
const TONO_ESTADO_MI: Record<string, StatusBadgeKind> = { active: 'danger', resolved: 'success', closed: 'neutral' }
const SEVERIDADES = ['critical', 'high', 'medium', 'low']

const kindDeTono = (tono: Tono | undefined): StatusBadgeKind => tono ?? 'neutral'

function Prioridad({ codigo, respaldo }: { codigo?: string | null; respaldo?: string | null }) {
  const t = useAppT()
  if (!codigo) return <span className="u-text3-sm">—</span>
  return <StatusBadge caps={false} color={COLOR_PRIORIDAD[codigo] ?? COLOR.text3}>{etiquetaCodigo(t, 'estado', codigo, respaldo)}</StatusBadge>
}

/** Número + título que abre lo que representa (sin ids a la vista). */
function Enlace({ numero, titulo, sub, onClick }: { numero?: string | null; titulo: string; sub?: ReactNode; onClick?: () => void }) {
  const cuerpo = (
    <span className="sdp-enlace__cuerpo">
      <span className="sdp-enlace__titulo">
        {numero && <span className="u-mono sdp-enlace__numero">{numero}</span>}
        <span className="sdp-wrap">{titulo}</span>
      </span>
      {sub && <span className="sdp-enlace__sub">{sub}</span>}
    </span>
  )
  return onClick ? <Pulsable className="sdp-enlace" onClick={onClick}>{cuerpo}</Pulsable> : cuerpo
}

/** Barra fina de 0-100 coloreada (la usan también los informes de CMDB y del cambio). */
export function Barra({ pct, color, etiqueta }: { pct: number; color: string; etiqueta: string }) {
  const v = Math.max(0, Math.min(100, Math.round(pct)))
  return (
    <span className="sdp-barra" role="img" aria-label={etiqueta}>
      <span className="sdp-barra__pista"><span className="sdp-barra__relleno" style={{ '--sdp-w': `${v}%`, '--sdp-c': color } as CSSProperties} /></span>
      <span className="sdp-barra__valor">{v}</span>
    </span>
  )
}

/* ── 1. Mi cola por riesgo ───────────────────────────────────────────────── */

export function WidgetMiCola({ datos, onAbrir, onIrA }: PropsDeWidget<TicketDeCola[]>) {
  const t = useAppT()
  const tono = useTono()
  if (datos.length === 0) {
    return <EmptyState icon={<Inbox size={28} />} title={t('sd_mercado.panel.cola_vacia')} description={t('sd_mercado.panel.cola_vacia_desc')} />
  }
  return (
    <div className="u-stack-10">
      <TablaSimple densidad="compacta" etiqueta={t('sd_mercado.widget.my_queue_prioritized')} claseTabla="sdp-tabla">
        <thead>
          <tr>
            <th>{t('sd_mercado.panel.col_ticket')}</th>
            <th>{t('sd_mercado.panel.col_estado')}</th>
            <th>{t('sd_mercado.panel.col_prioridad')}</th>
            <th>{t('sd_mercado.panel.col_vence_sla')}</th>
            <th className="sdp-num">{t('sd_mercado.panel.col_puntuacion')}</th>
          </tr>
        </thead>
        <tbody>
          {datos.map(tk => {
            const puntos = Math.round((tk.priority_score ?? 0) * 100)
            const tonoPuntos = tono('riesgo', puntos)
            return (
              <tr key={tk.id}>
                <td><Enlace numero={tk.number} titulo={tk.title} sub={tk.client_name ?? undefined} onClick={() => onAbrir(tk.id)} /></td>
                <td><StatusBadge caps={false} kind="neutral">{etiquetaCodigo(t, 'estado', tk.status, tk.status_label)}</StatusBadge></td>
                <td><Prioridad codigo={tk.priority} respaldo={tk.priority_label} /></td>
                <td>
                  {tk.sla_resolution_due ? (
                    <StatusBadge caps={false} kind={TONO_SLA[tk.sla_resolution_status ?? ''] ?? 'neutral'} title={fmtDateTime(tk.sla_resolution_due)}>
                      {fmtRelative(tk.sla_resolution_due)}
                    </StatusBadge>
                  ) : <span className="u-text3-sm">{t('sd_mercado.panel.sin_sla')}</span>}
                </td>
                <td className="sdp-num">
                  <Barra pct={puntos} color={colorDeTono(tonoPuntos)} etiqueta={t('sd_mercado.panel.puntuacion_aria', { n: puntos })} />
                </td>
              </tr>
            )
          })}
        </tbody>
      </TablaSimple>
      <p className="u-hint">{t('sd_mercado.panel.puntuacion_ayuda')}</p>
      {onIrA && <div className="u-row-end"><Pulsable className="sdp-mas" onClick={() => onIrA('queue')}>{t('sd_mercado.panel.ver_cola')}</Pulsable></div>}
    </div>
  )
}

/* ── 2. Riesgo de SLA ────────────────────────────────────────────────────── */

export function WidgetRiesgoSla({ datos }: PropsDeWidget<EstadisticasDeRiesgo>) {
  const t = useAppT()
  const tono = useTono()
  if (!datos.open_tickets) {
    return <EmptyState icon={<CheckCircle2 size={28} />} title={t('sd_mercado.panel.sin_abiertos')} description={t('sd_mercado.panel.sin_abiertos_desc')} />
  }
  const tonoRiesgo = tono('riesgo', datos.sla_at_risk_pct)
  const dist = datos.severity_distribution ?? {}
  const analizados = datos.analyzed_tickets || 1
  return (
    <div className="u-stack-12">
      <div className="sdp-kpis">
        <KpiCard icon={<ShieldAlert size={16} />} label={t('sd_mercado.panel.en_riesgo')} value={datos.sla_at_risk_count}
          danger={tonoRiesgo === 'danger'} warning={tonoRiesgo === 'warning'}
          sub={t('sd_mercado.panel.pct_de_analizados', { pct: datos.sla_at_risk_pct })} />
        <KpiCard icon={<FolderOpen size={16} />} label={t('sd_mercado.panel.abiertos')} value={datos.open_tickets} />
      </div>
      <div>
        <div className="ds-eyebrow sdp-subtitulo">{t('sd_mercado.panel.severidad_prevista')}</div>
        {SEVERIDADES.map(s => (
          <BarRow key={s} label={etiquetaCodigo(t, 'estado', s)} count={dist[s] ?? 0} total={analizados} color={COLOR_SEVERIDAD[s]} />
        ))}
      </div>
      {datos.truncated && <p className="u-hint">{t('sd_mercado.panel.recortado', { n: datos.analyzed_tickets, total: datos.open_tickets })}</p>}
      {!!datos.failed_tickets && <p className="u-hint">{t('sd_mercado.panel.fallidos', { n: datos.failed_tickets })}</p>}
    </div>
  )
}

/* ── 3. Incidentes mayores ───────────────────────────────────────────────── */

export function WidgetIncidentesMayores({ datos, onIrA }: PropsDeWidget<IncidenteMayor[]>) {
  const t = useAppT()
  if (datos.length === 0) {
    return <EmptyState icon={<Flame size={28} />} title={t('sd_mercado.panel.sin_incidentes')} description={t('sd_mercado.panel.sin_incidentes_desc')} />
  }
  // Activos primero; dentro, lo más reciente.
  const filas = [...datos].sort((a, b) => Number(b.status === 'active') - Number(a.status === 'active')).slice(0, 6)
  const abrir = onIrA ? () => onIrA('mi') : undefined
  return (
    <div className="u-stack-10">
      <TablaSimple densidad="compacta" etiqueta={t('sd_mercado.widget.major_incidents')} claseTabla="sdp-tabla">
        <thead>
          <tr>
            <th>{t('sd_mercado.panel.col_incidente')}</th>
            <th>{t('sd_mercado.panel.col_severidad')}</th>
            <th>{t('sd_mercado.panel.col_estado')}</th>
            <th>{t('sd_mercado.panel.col_declarado')}</th>
            <th>{t('sd_mercado.panel.col_responsable')}</th>
          </tr>
        </thead>
        <tbody>
          {filas.map(mi => (
            <tr key={mi.id}>
              <td><Enlace numero={mi.number} titulo={mi.title} sub={mi.impact_statement ?? undefined} onClick={abrir} /></td>
              <td>{mi.severity ? <StatusBadge caps={false} kind={mi.severity === 'P1' ? 'danger' : 'orange'}>{mi.severity}</StatusBadge> : '—'}</td>
              <td><StatusBadge caps={false} dot kind={TONO_ESTADO_MI[mi.status] ?? 'neutral'}>{etiquetaCodigo(t, 'estado', mi.status)}</StatusBadge></td>
              <td title={fmtDateTime(mi.declared_at)}>{fmtDate(mi.declared_at)}</td>
              <td>{mi.commander ?? <span className="u-text3-sm">{t('sd_mercado.panel.sin_asignar')}</span>}</td>
            </tr>
          ))}
        </tbody>
      </TablaSimple>
      {datos.length > filas.length && <p className="u-hint">{t('sd_mercado.panel.y_mas', { n: datos.length - filas.length })}</p>}
    </div>
  )
}

/* ── 4. Métricas ITIL (con tendencia frente al periodo anterior) ─────────── */

export function WidgetMetricasItil({ datos, previo }: PropsDeWidget<MetricasItil> & { previo?: MetricasItil | null }) {
  const t = useAppT()
  const tono = useTono()
  const total = datos.volume?.total ?? 0
  if (total === 0) {
    return <EmptyState icon={<Ticket size={28} />} title={t('sd_mercado.panel.sin_tickets_periodo')} description={t('sd_mercado.panel.sin_tickets_periodo_desc')} />
  }
  const vs = (actual?: number | null, antes?: number | null) => {
    const v = variacion(actual, antes)
    return v == null ? undefined : t('sd_mercado.panel.vs_anterior', { v: `${v > 0 ? '+' : ''}${v} %` })
  }
  const slaPct = datos.sla_compliance_pct ?? null
  const slaTono = tono('sla', slaPct)
  const fcr = datos.fcr_percent ?? null
  const fcrTono = tono('sla', fcr)
  const csat = datos.avg_csat != null ? Number(datos.avg_csat) : null
  const incumplidos = datos.volume?.breached_sla ?? 0
  const pp = (a?: number | null, b?: number | null) => (a == null || b == null) ? null : Math.round((a - b) * 10) / 10
  const difSla = pp(slaPct, previo?.sla_compliance_pct)
  const prioridades = Object.entries(datos.by_priority ?? {}).sort((a, b) => a[0].localeCompare(b[0]))
  const tipos = Object.entries(datos.by_type ?? {}).sort((a, b) => b[1] - a[1])
  return (
    <div className="u-stack-14">
      <div className="sdp-kpis sdp-kpis--anchos">
        <KpiCard icon={<Ticket size={16} />} label={t('sd_mercado.panel.tickets')} value={total} sub={vs(total, previo?.volume?.total)} />
        <KpiCard icon={<FolderOpen size={16} />} label={t('sd_mercado.panel.abiertos')} value={datos.volume?.open ?? 0} />
        <KpiCard icon={<CheckCircle2 size={16} />} label={t('sd_mercado.panel.resueltos')} value={datos.volume?.resolved ?? 0} sub={vs(datos.volume?.resolved, previo?.volume?.resolved)} />
        <KpiCard icon={<Timer size={16} />} label={t('sd_mercado.panel.mttr')} value={fmtMinutos(datos.mttr_minutes)} sub={vs(datos.mttr_minutes, previo?.mttr_minutes)} />
        <KpiCard icon={<Star size={16} />} label={t('sd_mercado.panel.csat')} value={csat != null ? `${csat.toFixed(1)}/5` : '—'}
          danger={csat != null && csat < 3} warning={csat != null && csat >= 3 && csat < 4} />
        <KpiCard icon={<AlertTriangle size={16} />} label={t('sd_mercado.panel.incumplimientos')} value={incumplidos} danger={incumplidos > 0}
          sub={vs(incumplidos, previo?.volume?.breached_sla)} />
      </div>
      <div className="sdp-columnas">
        <div className="u-stack-10">
          <GaugeCard label={t('sd_mercado.panel.cumplimiento_sla')} value={slaPct} color={colorDeTono(slaTono, COLOR.text3)}
            sub={difSla == null ? undefined : t('sd_mercado.panel.pp_vs_anterior', { v: `${difSla > 0 ? '+' : ''}${difSla}` })} />
          <GaugeCard label={t('sd_mercado.panel.fcr')} value={fcr} color={colorDeTono(fcrTono, COLOR.text3)} sub={t('sd_mercado.panel.fcr_desc')} />
        </div>
        <div>
          <div className="ds-eyebrow sdp-subtitulo">{t('sd_mercado.panel.por_prioridad')}</div>
          {prioridades.map(([p, n]) => (
            <BarRow key={p} label={etiquetaCodigo(t, 'estado', p)} count={n} total={total} color={COLOR_PRIORIDAD[p] ?? COLOR.text3}
              displayValue={datos.breach_by_priority?.[p] ? t('sd_mercado.panel.n_con_incumplidos', { n, b: datos.breach_by_priority[p] }) : n} />
          ))}
        </div>
        <div>
          <div className="ds-eyebrow sdp-subtitulo">{t('sd_mercado.panel.por_tipo')}</div>
          {tipos.map(([tipo, n], i) => (
            <BarRow key={tipo} label={etiquetaCodigo(t, 'metricsdashboard', `tipo_${tipo}`, tipo.replace(/_/g, ' '))} count={n} total={total} color={typePalette[i % typePalette.length]} />
          ))}
        </div>
      </div>
      <p className="u-hint">{t('sd_mercado.panel.periodo_30')}</p>
    </div>
  )
}

/* ── 5. Rendimiento por agente ───────────────────────────────────────────── */

export function WidgetRendimiento({ datos }: PropsDeWidget<RendimientoDeAgente[]>) {
  const t = useAppT()
  const tono = useTono()
  const { tokens } = useChartTheme()
  // El servidor devuelve a todas las personas activas: solo las que tienen tickets.
  const filas = datos.filter(a => a.total > 0).sort((a, b) => b.total - a.total)
  if (filas.length === 0) {
    return <EmptyState icon={<Users size={28} />} title={t('sd_mercado.panel.sin_agentes')} description={t('sd_mercado.panel.sin_agentes_desc')} />
  }
  const grafico = filas.slice(0, 8).map(a => ({ nombre: a.agent_name, resueltos: a.resolved, abiertos: a.open }))
  return (
    <div className="u-stack-12">
      <div className="sdp-grafico" role="img" aria-label={t('sd_mercado.panel.grafico_agentes')}>
        <ResponsiveContainer width="100%" height={Math.max(120, grafico.length * 28 + 30)}>
          <BarChart data={grafico} layout="vertical" margin={{ top: 4, right: 12, bottom: 4, left: 4 }}>
            <XAxis type="number" allowDecimals={false} tick={{ fill: tokens.text3, fontSize: 11 }} />
            <YAxis type="category" dataKey="nombre" width={120} tick={{ fill: tokens.text2, fontSize: 11 }} />
            <Tooltip contentStyle={tooltipDelTemaConBorde(tokens)} />
            <Bar dataKey="resueltos" name={t('sd_mercado.panel.resueltos')} stackId="a" fill={tokens.success} />
            <Bar dataKey="abiertos" name={t('sd_mercado.panel.abiertos')} stackId="a" fill={tokens.accent} radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <TablaSimple densidad="compacta" etiqueta={t('sd_mercado.widget.agent_performance')} claseTabla="sdp-tabla">
        <thead>
          <tr>
            <th>{t('sd_mercado.panel.col_agente')}</th>
            <th className="sdp-num">{t('sd_mercado.panel.tickets')}</th>
            <th>{t('sd_mercado.panel.col_resolucion')}</th>
            <th className="sdp-num">{t('sd_mercado.panel.mttr')}</th>
            <th className="sdp-num">{t('sd_mercado.panel.csat')}</th>
            <th className="sdp-num">{t('sd_mercado.panel.incumplimientos')}</th>
          </tr>
        </thead>
        <tbody>
          {filas.map(a => {
            const pct = a.total > 0 ? (a.resolved / a.total) * 100 : 0
            return (
              <tr key={a.agent_id}>
                <td><span className="u-row-center-8"><Avatar name={a.agent_name} size={24} /><span>{a.agent_name}</span></span></td>
                <td className="sdp-num">{a.total}</td>
                <td><Barra pct={pct} color={colorDeTono(tono('sla', pct))} etiqueta={t('sd_mercado.panel.resolucion_aria', { pct: Math.round(pct) })} /></td>
                <td className="sdp-num">{fmtMinutos(a.mttr_minutes)}</td>
                <td className="sdp-num">{a.avg_csat != null ? Number(a.avg_csat).toFixed(1) : '—'}</td>
                <td className="sdp-num"><StatusBadge caps={false} kind={a.sla_breaches > 0 ? 'danger' : 'success'}>{a.sla_breaches}</StatusBadge></td>
              </tr>
            )
          })}
        </tbody>
      </TablaSimple>
      <p className="u-hint">{t('sd_mercado.panel.periodo_30')}</p>
    </div>
  )
}

/* ── 6. Agente autónomo ──────────────────────────────────────────────────── */

const ESTADOS_AGENTE: { clave: keyof EstadisticasDelAgente; color: string }[] = [
  { clave: 'success', color: COLOR.success }, { clave: 'applied', color: 'var(--chart-teal)' },
  { clave: 'suggested', color: COLOR.accent }, { clave: 'discarded', color: COLOR.text3 },
  { clave: 'skipped', color: COLOR.text3 }, { clave: 'failed', color: COLOR.danger },
]

export function WidgetAgenteAutonomo({ datos }: PropsDeWidget<EstadisticasDelAgente>) {
  const t = useAppT()
  const tono = useTono()
  if (!datos.total_executions) {
    return <EmptyState icon={<Bot size={28} />} title={t('sd_mercado.panel.agente_sin_actividad')} description={t('sd_mercado.panel.agente_sin_actividad_desc')} />
  }
  const tonoExito = tono('sla', datos.success_rate_pct)
  const tipos = Object.entries(datos.by_playbook_type ?? {}).sort((a, b) => b[1] - a[1]).slice(0, 5)
  return (
    <div className="u-stack-12">
      <div className="sdp-kpis">
        <KpiCard icon={<CheckCircle2 size={16} />} label={t('sd_mercado.panel.tasa_exito')} value={`${datos.success_rate_pct} %`}
          danger={tonoExito === 'danger'} warning={tonoExito === 'warning'} sub={t('sd_mercado.panel.de_n_ejecuciones', { n: datos.total_executions })} />
        <KpiCard icon={<ClipboardCheck size={16} />} label={t('sd_mercado.panel.por_decidir')} value={datos.suggested} warning={datos.suggested > 0}
          sub={t('sd_mercado.panel.por_decidir_desc')} />
      </div>
      <div>
        <div className="ds-eyebrow sdp-subtitulo">{t('sd_mercado.panel.por_resultado')}</div>
        {ESTADOS_AGENTE.filter(e => Number(datos[e.clave]) > 0).map(e => (
          <BarRow key={e.clave} label={etiquetaCodigo(t, 'sd_mercado.panel.resultado', e.clave)} count={Number(datos[e.clave])} total={datos.total_executions} color={e.color} />
        ))}
      </div>
      {tipos.length > 0 && (
        <div>
          <div className="ds-eyebrow sdp-subtitulo">{t('sd_mercado.panel.por_playbook')}</div>
          <ul className="sdp-lista">
            {tipos.map(([tipo, n]) => (
              <li key={tipo}><span className="sdp-wrap">{etiquetaCodigo(t, 'sd_mercado.panel.playbook', tipo, etiquetaCodigo(t, 'sd_mercado.pb', tipo, tipo.replace(/_/g, ' ')))}</span><StatusBadge caps={false}>{n}</StatusBadge></li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

/* ── 7. Cambios en el CAB ────────────────────────────────────────────────── */

export function WidgetCab({ datos, onIrA }: PropsDeWidget<PanelDelCab>) {
  const t = useAppT()
  const tono = useTono()
  const items = datos.items ?? []
  if (items.length === 0) {
    return <EmptyState icon={<GitPullRequestArrow size={28} />} title={t('sd_mercado.panel.cab_vacio')} description={t('sd_mercado.panel.cab_vacio_desc')} />
  }
  const abrir = onIrA ? () => onIrA('changes') : undefined
  return (
    <div className="u-stack-10">
      <TablaSimple densidad="compacta" etiqueta={t('sd_mercado.widget.cab_pending')} claseTabla="sdp-tabla">
        <thead>
          <tr>
            <th>{t('sd_mercado.panel.col_cambio')}</th>
            <th>{t('sd_mercado.panel.col_tipo')}</th>
            <th>{t('sd_mercado.panel.col_riesgo')}</th>
            <th>{t('sd_mercado.panel.col_estado')}</th>
            <th>{t('sd_mercado.panel.col_inicio')}</th>
            <th>{t('sd_mercado.panel.col_responsable')}</th>
          </tr>
        </thead>
        <tbody>
          {items.map(c => (
            <tr key={c.id}>
              <td><Enlace numero={c.number} titulo={c.title} onClick={abrir} /></td>
              <td>{c.change_type ? etiquetaCodigo(t, 'sd_mercado.panel.tipo_cambio', c.change_type) : '—'}</td>
              <td>
                {c.auto_risk_score != null
                  ? <StatusBadge caps={false} kind={kindDeTono(tono('riesgo', c.auto_risk_score))}>
                    {Math.round(c.auto_risk_score)}{c.auto_risk_label ? ` · ${etiquetaCodigo(t, 'estado', c.auto_risk_label)}` : ''}
                  </StatusBadge>
                  : <span className="u-text3-sm">{t('sd_mercado.panel.sin_puntuar')}</span>}
              </td>
              <td><StatusBadge caps={false} kind="info">{etiquetaCodigo(t, 'sd_mercado.panel.estado_cambio', c.status)}</StatusBadge></td>
              <td>{fmtDateTime(c.planned_start)}</td>
              <td>{c.owner ?? c.requester ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </TablaSimple>
      <p className="u-hint">
        {t('sd_mercado.panel.cab_total', { n: datos.total })}
        {datos.unscored > 0 ? ` · ${t('sd_mercado.panel.cab_sin_puntuar', { n: datos.unscored })}` : ''}
      </p>
    </div>
  )
}

/* ── 8. Mis aprobaciones ─────────────────────────────────────────────────── */

export function WidgetMisAprobaciones({ datos, onAbrir }: PropsDeWidget<AprobacionPendiente[]>) {
  const t = useAppT()
  const umbrales = useUmbrales()
  if (datos.length === 0) {
    return <EmptyState icon={<ClipboardCheck size={28} />} title={t('sd_mercado.panel.sin_aprobaciones')} description={t('sd_mercado.panel.sin_aprobaciones_desc')} />
  }
  const limiteHoras = umbrales.sueltos.UMBRAL_APROBACION_DECISION_HORAS
  const ahora = Date.now()
  return (
    <TablaSimple densidad="compacta" etiqueta={t('sd_mercado.widget.my_approvals')} claseTabla="sdp-tabla">
      <thead>
        <tr>
          <th>{t('sd_mercado.panel.col_peticion')}</th>
          <th>{t('sd_mercado.panel.col_solicitante')}</th>
          <th>{t('sd_mercado.panel.col_esperando')}</th>
        </tr>
      </thead>
      <tbody>
        {datos.map(a => {
          const horas = a.created_at ? (ahora - new Date(a.created_at).getTime()) / 3_600_000 : 0
          return (
            <tr key={a.approval_id}>
              <td><Enlace numero={a.number} titulo={a.title} sub={a.service_item_name ?? undefined} onClick={() => onAbrir(a.ticket_id)} /></td>
              <td>{a.requester_name ?? '—'}</td>
              <td>
                <StatusBadge caps={false} kind={horas > limiteHoras ? 'danger' : horas > limiteHoras / 2 ? 'warning' : 'neutral'} title={fmtDateTime(a.created_at)}>
                  {fmtRelative(a.created_at)}
                </StatusBadge>
              </td>
            </tr>
          )
        })}
      </tbody>
    </TablaSimple>
  )
}

/* ── Catálogo: tamaño en la rejilla de 12 columnas ───────────────────────── */

/** Columnas que ocupa cada widget (KPIs compactos, tablas anchas). */
export const TAMANO_DE_WIDGET: Record<string, 4 | 6 | 8 | 12> = {
  my_queue_prioritized: 8,
  sla_risk: 4,
  major_incidents: 8,
  itil_metrics: 12,
  agent_performance: 8,
  autonomous_agent: 4,
  cab_pending: 8,
  my_approvals: 4,
}

/** Recuento que acompaña al título del widget (o nada). */
export function recuentoDeWidget(id: string, datos: unknown): { n: number; kind: StatusBadgeKind } | null {
  if (id === 'major_incidents' && Array.isArray(datos)) {
    const activos = (datos as IncidenteMayor[]).filter(m => m.status === 'active').length
    return activos > 0 ? { n: activos, kind: 'danger' } : null
  }
  if (id === 'my_approvals' && Array.isArray(datos) && datos.length > 0) return { n: datos.length, kind: 'warning' }
  if (id === 'cab_pending' && datos && typeof datos === 'object' && 'total' in datos) {
    const n = Number((datos as PanelDelCab).total)
    return n > 0 ? { n, kind: 'info' } : null
  }
  return null
}
