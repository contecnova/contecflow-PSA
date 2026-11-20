/**
 * InformesDelCambio — informe propio de cada pestaña del análisis del cambio
 * (19-11-2026). Antes `AnalisisDelCambio` pintaba todo con `VistaDeDatos`
 * (volcado genérico). Ahora cada respuesta tiene su render con los campos
 * reales del servidor (`app/services/service_desk/change_impact_service/` y
 * `cab_workflow_service.py`):
 *
 *  - análisis de impacto → KPIs de riesgo, componentes de la puntuación,
 *    ventana sugerida, CIs afectados y software en esos CIs;
 *  - matriz de riesgo → gráfico de barras por CI y tabla;
 *  - plan de vuelta atrás → KPIs y pasos con su tiempo acumulado;
 *  - plan de pruebas → KPIs, minutos por fase y una tabla por fase;
 *  - plan de comunicaciones → KPIs, avisos por público y tabla por momento;
 *  - simulación «¿y si…?» → comparación original/simulado con gráfico;
 *  - flujo del CAB → estado, quórum, reunión y votos.
 *
 * Los renders son puros (reciben `datos`); las peticiones las hace
 * `AnalisisDelCambio`. Ningún id interno llega a la pantalla.
 */
import {
  AlertTriangle, Bot, Boxes, CalendarClock, CheckCircle2, Clock, Gauge, Hash, ListChecks, Megaphone, ShieldAlert,
  ThumbsDown, ThumbsUp, Ticket, Users, XCircle,
} from 'lucide-react'
import { Bar, BarChart, Cell, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useAppT } from '../../i18n/AppLangContext'
import { etiquetaCodigo } from '../../i18n/etiquetaCodigo'
import { KpiCard, StatusBadge, TablaSimple } from '../ui'
import type { StatusBadgeKind } from '../ui'
import { BarRow, typePalette } from '../dashboard/DashKit'
import { useTono } from '../../hooks/useOrgSettings'
import { colorDeTono } from '../../utils/umbrales'
import { fmtDateTime } from '../../utils/helpers'
import { useChartTheme } from '../../charts/useChartTheme'
import type { ChartThemeTokens } from '../../charts/useChartTheme'
import { LEYENDA_XS, tooltipDelTemaConBorde } from '../../constants/estilosGrafico'
import { Barra, fmtMinutos } from './WidgetsDelPanel'
import { Nivel, Subtitulo, codigo, useVentana } from './InformesComunes'
import './sdMercado.css'

/* ── Tipos (campos reales de cada endpoint) ──────────────────────────────── */

/** Componentes de la puntuación de riesgo (`score_change_risk`). */
export interface ComponentesDeRiesgo {
  change_type_score?: number; ci_count_score?: number; downtime_score?: number
  open_tickets_penalty?: number; incident_penalty?: number
}
interface VentanaSugerida { day_of_week?: number; hour_utc?: number; window_label?: string; avg_incidents_in_window?: number; confidence?: string }
/** `/sd/changes/{id}/impact-analysis` (`generate_impact_report` + matriz). */
export interface AnalisisDeImpacto {
  risk_score: number; risk_label: string; risk_components?: ComponentesDeRiesgo; generated_at?: string | null
  affected_cis?: {
    direct_count: number; expanded_count: number; critical_cis?: string[]
    ci_list?: { id: string; name: string; ci_type: string | null; status: string | null; criticality: string | null }[]
  }
  open_incidents_on_cis?: number; incidents_last_30d?: number; suggested_window?: VentanaSugerida
  software_on_cis?: {
    instances: { instance_id: string; product: string | null; version: string | null; environment: string | null; open_findings: number; lifecycle: string | null }[]
    open_findings: number; critical_findings: number; eol_instances: number
  }
}
/** Una fila de `/sd/changes/{id}/risk-matrix`. */
export interface FilaDeMatriz {
  ci_id: string; ci_name: string; ci_type: string | null; criticality: string | null
  dependency_count: number; recent_incidents: number; risk_score: number; impact_level: string
}
/** `/sd/changes/{id}/rollback-plan`. */
export interface PlanDeVueltaAtras {
  overall_risk: string; affected_ci_count: number; total_estimated_minutes: number; generated_at?: string | null
  rollback_steps: { step: number; action: string; responsible: string; estimated_minutes: number }[]
}
interface PasoDePrueba {
  step: number; phase: string; test_type: string; description: string; expected_result: string
  estimated_minutes: number; responsible: string; automated: boolean; command?: string
}
/** `/sd/changes/{id}/testing-plan`. */
export interface PlanDePruebas {
  risk_label: string; total_steps: number; estimated_total_minutes: number; steps: PasoDePrueba[]; generated_at?: string | null
}
interface Aviso {
  id: number; timing: string; hours_before_change: number | null; audience: string; channel: string
  subject: string; message_template: string; responsible: string
}
/** `/sd/changes/{id}/comms-plan`. */
export interface PlanDeComunicaciones {
  risk_label: string; suggested_window: string | null; total_notifications: number; notifications: Aviso[]; generated_at?: string | null
}
interface LadoDeSimulacion {
  score: number; risk_label: string; components: ComponentesDeRiesgo; ci_count_expanded: number; window: VentanaSugerida
}
/** `/sd/changes/{id}/whatif` (`simulate_change_whatif`). */
export interface Simulacion {
  original: LadoDeSimulacion; simulated: LadoDeSimulacion
  delta: { score_diff: number; risk_change: string; ci_count_diff: number; window_changed: boolean }
  proposed_window_evaluation?: VentanaSugerida & { vs_optimal_diff: number; is_optimal: boolean }
}
/** `/sd/changes/{id}/cab/workflow` (`get_workflow`). */
export interface FlujoDelCab {
  status: string; quorum: number | null
  meeting: { scheduled_at: string; agenda: string | null } | null
  votes: { user_id: string; name: string | null; approved: boolean; decision: string | null; note: string | null; voted_at: string | null }[]
}

/* ── Utilidades ───────────────────────────────────────────────────────────── */

/** Cada componente con su máximo (los de `score_change_risk`). */
const COMPONENTES: { clave: keyof ComponentesDeRiesgo; maximo: number }[] = [
  { clave: 'change_type_score', maximo: 80 }, { clave: 'ci_count_score', maximo: 30 }, { clave: 'downtime_score', maximo: 20 },
  { clave: 'open_tickets_penalty', maximo: 15 }, { clave: 'incident_penalty', maximo: 15 },
]
const FASES_DE_PRUEBA = ['pre_change', 'execution', 'post_change', 'rollback_validation']
/** Momento de un aviso → tramo (antes, durante, después). */
const tramoDeAviso = (timing: string) => timing.startsWith('T-') ? 'pre_change'
  : (timing === 'change_start' || timing === 'change_midpoint') ? 'during_change' : 'post_change'
const TRAMOS = ['pre_change', 'during_change', 'post_change']
const KIND_DECISION: Record<string, StatusBadgeKind> = { approved: 'success', rejected: 'danger', pending: 'neutral' }

/** Color resuelto de un nivel para Recharts (que no entiende variables CSS en todos los navegadores). */
function colorDeNivelResuelto(nivel: string, tk: ChartThemeTokens): string {
  return nivel === 'critical' ? tk.danger : nivel === 'high' ? tk.warning : nivel === 'medium' ? tk.accent : tk.success
}

/** Barras de los componentes de la puntuación (valor sobre su máximo). */
function ComponentesDeLaPuntuacion({ componentes }: { componentes?: ComponentesDeRiesgo }) {
  const t = useAppT()
  if (!componentes) return null
  return (
    <div>
      <Subtitulo>{t('sd_informes.componentes')}</Subtitulo>
      {COMPONENTES.map((c, i) => {
        const v = componentes[c.clave] ?? 0
        return <BarRow key={c.clave} label={t(`sd_informes.componente.${c.clave}`)} count={v} total={c.maximo}
          color={typePalette[i % typePalette.length]} displayValue={`${v}/${c.maximo}`} />
      })}
    </div>
  )
}

function Generado({ cuando }: { cuando?: string | null }) {
  const t = useAppT()
  return cuando ? <p className="u-hint">{t('sd_informes.generado', { f: fmtDateTime(cuando) })}</p> : null
}

/* ── 1. Análisis de impacto ──────────────────────────────────────────────── */

export function InformeImpacto({ datos }: { datos: AnalisisDeImpacto }) {
  const t = useAppT()
  const tono = useTono()
  const ventana = useVentana()
  const tonoRiesgo = tono('riesgo', datos.risk_score)
  const cis = datos.affected_cis
  const lista = [...(cis?.ci_list ?? [])].sort((a, b) =>
    ['critical', 'high', 'medium', 'low'].indexOf(codigo(a.criticality)) - ['critical', 'high', 'medium', 'low'].indexOf(codigo(b.criticality)))
  const v = datos.suggested_window
  const sw = datos.software_on_cis
  return (
    <div className="u-stack-14">
      <div className="sdp-kpis sdp-kpis--anchos">
        <KpiCard icon={<Gauge size={16} />} label={t('sd_informes.riesgo')} value={`${datos.risk_score}/100`}
          danger={tonoRiesgo === 'danger'} warning={tonoRiesgo === 'warning'} sub={etiquetaCodigo(t, 'sd_informes.nivel', datos.risk_label)} />
        <KpiCard icon={<Boxes size={16} />} label={t('sd_informes.cis_afectados')} value={cis?.expanded_count ?? 0}
          sub={t('sd_informes.n_directos', { n: cis?.direct_count ?? 0 })} />
        <KpiCard icon={<Ticket size={16} />} label={t('sd_informes.tickets_abiertos_cis')} value={datos.open_incidents_on_cis ?? 0}
          warning={(datos.open_incidents_on_cis ?? 0) > 0} />
        <KpiCard icon={<AlertTriangle size={16} />} label={t('sd_informes.incidentes_30d')} value={datos.incidents_last_30d ?? 0} />
      </div>
      <div className="sdp-columnas">
        <ComponentesDeLaPuntuacion componentes={datos.risk_components} />
        {v && (
          <div className="u-stack-8">
            <Subtitulo>{t('sd_informes.ventana_sugerida')}</Subtitulo>
            <div className="u-row-center-8"><CalendarClock size={16} aria-hidden="true" /><span className="u-text1-sm-600">{ventana(v.day_of_week, v.hour_utc, v.window_label)}</span></div>
            <div className="u-text3-xs">
              {t('sd_informes.incidentes_en_ventana', { n: v.avg_incidents_in_window ?? 0 })}
              {v.confidence ? ` · ${t('sd_informes.confianza_n', { n: etiquetaCodigo(t, 'sd_informes.confianza', v.confidence) })}` : ''}
            </div>
          </div>
        )}
      </div>
      {lista.length > 0 && (
        <div>
          <Subtitulo>{t('sd_informes.cis_afectados')}</Subtitulo>
          <TablaSimple densidad="compacta" etiqueta={t('sd_informes.cis_afectados')} claseTabla="sdp-tabla">
            <thead>
              <tr>
                <th>{t('sd_informes.col_ci')}</th>
                <th>{t('sd_informes.col_clase')}</th>
                <th>{t('sd_informes.col_estado')}</th>
                <th>{t('sd_informes.col_criticidad')}</th>
              </tr>
            </thead>
            <tbody>
              {lista.map(c => (
                <tr key={c.id}>
                  <td className="sdp-wrap">{c.name}</td>
                  <td>{c.ci_type ? etiquetaCodigo(t, 'sd_mercado.clase_base', codigo(c.ci_type)) : '—'}</td>
                  <td>{c.status ? etiquetaCodigo(t, 'sd_informes.estado_ci', codigo(c.status)) : '—'}</td>
                  <td><Nivel nivel={c.criticality} /></td>
                </tr>
              ))}
            </tbody>
          </TablaSimple>
        </div>
      )}
      {sw && (sw.instances?.length ?? 0) > 0 && (
        <div className="u-stack-10">
          <Subtitulo>{t('sd_informes.software_en_cis')}</Subtitulo>
          <div className="sdp-kpis">
            <KpiCard icon={<ShieldAlert size={16} />} label={t('sd_informes.vulnerabilidades_abiertas')} value={sw.open_findings}
              sub={t('sd_informes.n_criticas_altas', { n: sw.critical_findings })} danger={sw.critical_findings > 0} warning={sw.open_findings > 0} />
            <KpiCard icon={<Clock size={16} />} label={t('sd_informes.sin_soporte')} value={sw.eol_instances} warning={sw.eol_instances > 0} />
          </div>
          <TablaSimple densidad="compacta" etiqueta={t('sd_informes.software_en_cis')} claseTabla="sdp-tabla">
            <thead>
              <tr>
                <th>{t('sd_informes.col_producto')}</th>
                <th>{t('sd_informes.col_version')}</th>
                <th>{t('sd_informes.col_entorno')}</th>
                <th>{t('sd_informes.col_ciclo')}</th>
                <th className="sdp-num">{t('sd_informes.col_vulnerabilidades')}</th>
              </tr>
            </thead>
            <tbody>
              {sw.instances.slice(0, 15).map(s => (
                <tr key={s.instance_id}>
                  <td className="sdp-wrap">{s.product ?? '—'}</td>
                  <td className="u-mono">{s.version ?? '—'}</td>
                  <td>{s.environment ? etiquetaCodigo(t, 'sd_informes.entorno', s.environment) : '—'}</td>
                  <td>{s.lifecycle
                    ? <StatusBadge caps={false} kind={s.lifecycle === 'eol' ? 'danger' : s.lifecycle === 'unsupported' ? 'orange' : s.lifecycle === 'soon' ? 'warning' : 'neutral'}>
                      {etiquetaCodigo(t, 'sd_informes.ciclo', s.lifecycle)}</StatusBadge>
                    : '—'}</td>
                  <td className="sdp-num"><StatusBadge caps={false} kind={s.open_findings > 0 ? 'danger' : 'success'}>{s.open_findings}</StatusBadge></td>
                </tr>
              ))}
            </tbody>
          </TablaSimple>
          {sw.instances.length > 15 && <p className="u-hint">{t('sd_informes.y_mas', { n: sw.instances.length - 15 })}</p>}
        </div>
      )}
      <Generado cuando={datos.generated_at} />
    </div>
  )
}

/* ── 2. Matriz de riesgo ─────────────────────────────────────────────────── */

export function InformeMatrizDeRiesgo({ datos }: { datos: FilaDeMatriz[] }) {
  const t = useAppT()
  const { tokens } = useChartTheme()
  const altos = datos.filter(f => f.impact_level === 'critical' || f.impact_level === 'high').length
  const incidentes = datos.reduce((s, f) => s + (f.recent_incidents ?? 0), 0)
  const grafico = datos.slice(0, 10).map(f => ({ nombre: f.ci_name, puntuacion: f.risk_score, nivel: f.impact_level }))
  return (
    <div className="u-stack-14">
      <div className="sdp-kpis">
        <KpiCard icon={<Boxes size={16} />} label={t('sd_informes.cis_evaluados')} value={datos.length} />
        <KpiCard icon={<ShieldAlert size={16} />} label={t('sd_informes.cis_riesgo_alto')} value={altos} danger={altos > 0} />
        <KpiCard icon={<AlertTriangle size={16} />} label={t('sd_informes.incidentes_30d')} value={incidentes} />
      </div>
      <div className="sdp-grafico" role="img" aria-label={t('sd_informes.matriz_grafico')}>
        <ResponsiveContainer width="100%" height={Math.max(120, grafico.length * 28 + 30)}>
          <BarChart data={grafico} layout="vertical" margin={{ top: 4, right: 12, bottom: 4, left: 4 }}>
            <XAxis type="number" tick={{ fill: tokens.text3, fontSize: 11 }} />
            <YAxis type="category" dataKey="nombre" width={130} tick={{ fill: tokens.text2, fontSize: 11 }} />
            <Tooltip contentStyle={tooltipDelTemaConBorde(tokens)} />
            <Bar dataKey="puntuacion" name={t('sd_informes.col_puntuacion')} radius={[0, 4, 4, 0]}>
              {grafico.map((g, i) => <Cell key={i} fill={colorDeNivelResuelto(g.nivel, tokens)} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <TablaSimple densidad="compacta" etiqueta={t('sd_mercado.chg_riesgo')} claseTabla="sdp-tabla">
        <thead>
          <tr>
            <th>{t('sd_informes.col_ci')}</th>
            <th>{t('sd_informes.col_clase')}</th>
            <th>{t('sd_informes.col_criticidad')}</th>
            <th className="sdp-num">{t('sd_informes.col_dependientes')}</th>
            <th className="sdp-num">{t('sd_informes.col_incidentes_30d')}</th>
            <th className="sdp-num">{t('sd_informes.col_puntuacion')}</th>
            <th>{t('sd_informes.col_impacto')}</th>
          </tr>
        </thead>
        <tbody>
          {datos.map(f => (
            <tr key={f.ci_id}>
              <td className="sdp-wrap">{f.ci_name}</td>
              <td>{f.ci_type ? etiquetaCodigo(t, 'sd_mercado.clase_base', codigo(f.ci_type)) : '—'}</td>
              <td><Nivel nivel={f.criticality} /></td>
              <td className="sdp-num">{f.dependency_count}</td>
              <td className="sdp-num">{f.recent_incidents}</td>
              <td className="sdp-num">{f.risk_score}</td>
              <td><Nivel nivel={f.impact_level} /></td>
            </tr>
          ))}
        </tbody>
      </TablaSimple>
      <p className="u-hint">{t('sd_informes.matriz_ayuda')}</p>
    </div>
  )
}

/* ── 3. Plan de vuelta atrás ─────────────────────────────────────────────── */

export function InformeVueltaAtras({ datos }: { datos: PlanDeVueltaAtras }) {
  const t = useAppT()
  const pasos = datos.rollback_steps ?? []
  let acumulado = 0
  return (
    <div className="u-stack-14">
      <div className="sdp-kpis">
        <KpiCard icon={<Clock size={16} />} label={t('sd_informes.duracion_total')} value={fmtMinutos(datos.total_estimated_minutes)} />
        <KpiCard icon={<ListChecks size={16} />} label={t('sd_informes.pasos')} value={pasos.length} />
        <KpiCard icon={<Gauge size={16} />} label={t('sd_informes.riesgo')} value={<Nivel nivel={datos.overall_risk} />} />
        <KpiCard icon={<Boxes size={16} />} label={t('sd_informes.cis_afectados')} value={datos.affected_ci_count ?? 0} />
      </div>
      <TablaSimple densidad="compacta" etiqueta={t('sd_mercado.chg_vuelta')} claseTabla="sdp-tabla">
        <thead>
          <tr>
            <th className="sdp-num">{t('sd_informes.col_paso')}</th>
            <th>{t('sd_informes.col_accion')}</th>
            <th>{t('sd_informes.col_responsable')}</th>
            <th className="sdp-num">{t('sd_informes.col_minutos')}</th>
            <th className="sdp-num">{t('sd_informes.col_empieza')}</th>
          </tr>
        </thead>
        <tbody>
          {pasos.map(p => {
            const empieza = acumulado
            acumulado += p.estimated_minutes ?? 0
            return (
              <tr key={p.step}>
                <td className="sdp-num">{p.step}</td>
                <td className="sdp-wrap">{p.action}</td>
                <td>{p.responsible}</td>
                <td className="sdp-num">{fmtMinutos(p.estimated_minutes)}</td>
                <td className="sdp-num">{t('sd_informes.t_mas', { m: empieza })}</td>
              </tr>
            )
          })}
        </tbody>
      </TablaSimple>
      <p className="u-hint">{t('sd_informes.empieza_ayuda')}</p>
      <Generado cuando={datos.generated_at} />
    </div>
  )
}

/* ── 4. Plan de pruebas ──────────────────────────────────────────────────── */

export function InformePruebas({ datos }: { datos: PlanDePruebas }) {
  const t = useAppT()
  const pasos = datos.steps ?? []
  const automaticos = pasos.filter(p => p.automated).length
  const minutosPorFase = FASES_DE_PRUEBA.map(f => ({ fase: f, min: pasos.filter(p => p.phase === f).reduce((s, p) => s + (p.estimated_minutes ?? 0), 0) }))
  const total = datos.estimated_total_minutes || 1
  return (
    <div className="u-stack-14">
      <div className="sdp-columnas">
        <div className="sdp-kpis">
          <KpiCard icon={<ListChecks size={16} />} label={t('sd_informes.pasos')} value={datos.total_steps ?? pasos.length} />
          <KpiCard icon={<Clock size={16} />} label={t('sd_informes.duracion_total')} value={fmtMinutos(datos.estimated_total_minutes)} />
          <KpiCard icon={<Bot size={16} />} label={t('sd_informes.automaticas')} value={automaticos}
            sub={t('sd_informes.de_n', { n: pasos.length })} />
          <KpiCard icon={<Gauge size={16} />} label={t('sd_informes.riesgo')} value={<Nivel nivel={datos.risk_label} />} />
        </div>
        <div>
          <Subtitulo>{t('sd_informes.minutos_por_fase')}</Subtitulo>
          {minutosPorFase.map((f, i) => (
            <BarRow key={f.fase} label={etiquetaCodigo(t, 'sd_informes.fase', f.fase)} count={f.min} total={total}
              color={typePalette[i % typePalette.length]} displayValue={fmtMinutos(f.min)} />
          ))}
        </div>
      </div>
      {FASES_DE_PRUEBA.map(fase => {
        const filas = pasos.filter(p => p.phase === fase)
        if (filas.length === 0) return null
        return (
          <div key={fase}>
            <Subtitulo>{etiquetaCodigo(t, 'sd_informes.fase', fase)}</Subtitulo>
            <TablaSimple densidad="compacta" etiqueta={etiquetaCodigo(t, 'sd_informes.fase', fase)} claseTabla="sdp-tabla">
              <thead>
                <tr>
                  <th className="sdp-num">{t('sd_informes.col_paso')}</th>
                  <th>{t('sd_informes.col_prueba')}</th>
                  <th>{t('sd_informes.col_resultado_esperado')}</th>
                  <th>{t('sd_informes.col_responsable')}</th>
                  <th className="sdp-num">{t('sd_informes.col_minutos')}</th>
                </tr>
              </thead>
              <tbody>
                {filas.map(p => (
                  <tr key={p.step}>
                    <td className="sdp-num">{p.step}</td>
                    <td>
                      <div className="u-wrap-6">
                        <StatusBadge caps={false} kind="info">{etiquetaCodigo(t, 'sd_informes.tipo_prueba', p.test_type)}</StatusBadge>
                        {p.automated && <StatusBadge caps={false} kind="accent">{t('sd_informes.automatica')}</StatusBadge>}
                      </div>
                      <div className="sdp-wrap">{p.description}</div>
                      {p.command && <div className="u-mono u-text3-xs sdp-wrap">{p.command}</div>}
                    </td>
                    <td className="sdp-wrap">{p.expected_result}</td>
                    <td>{p.responsible}</td>
                    <td className="sdp-num">{fmtMinutos(p.estimated_minutes)}</td>
                  </tr>
                ))}
              </tbody>
            </TablaSimple>
          </div>
        )
      })}
      <Generado cuando={datos.generated_at} />
    </div>
  )
}

/* ── 5. Plan de comunicaciones ───────────────────────────────────────────── */

export function InformeComunicaciones({ datos }: { datos: PlanDeComunicaciones }) {
  const t = useAppT()
  const ventana = useVentana()
  const avisos = datos.notifications ?? []
  const publico = (p: string) => etiquetaCodigo(t, 'sd_informes.publico', p)
  const porPublico = new Map<string, number>()
  for (const a of avisos) porPublico.set(a.audience, (porPublico.get(a.audience) ?? 0) + 1)
  return (
    <div className="u-stack-14">
      <div className="sdp-columnas">
        <div className="sdp-kpis">
          <KpiCard icon={<Megaphone size={16} />} label={t('sd_informes.avisos')} value={datos.total_notifications ?? avisos.length} />
          <KpiCard icon={<Users size={16} />} label={t('sd_informes.publicos')} value={porPublico.size} />
          <KpiCard icon={<Gauge size={16} />} label={t('sd_informes.riesgo')} value={<Nivel nivel={datos.risk_label} />} />
          <KpiCard icon={<CalendarClock size={16} />} label={t('sd_informes.ventana_sugerida')} value={ventana(null, null, datos.suggested_window)} />
        </div>
        <div>
          <Subtitulo>{t('sd_informes.avisos_por_publico')}</Subtitulo>
          {[...porPublico.entries()].sort((a, b) => b[1] - a[1]).map(([p, n], i) => (
            <BarRow key={p} label={publico(p)} count={n} total={avisos.length || 1} color={typePalette[i % typePalette.length]} />
          ))}
        </div>
      </div>
      {TRAMOS.map(tramo => {
        const filas = avisos.filter(a => tramoDeAviso(a.timing) === tramo)
        if (filas.length === 0) return null
        return (
          <div key={tramo}>
            <Subtitulo>{etiquetaCodigo(t, 'sd_informes.fase', tramo)}</Subtitulo>
            <TablaSimple densidad="compacta" etiqueta={etiquetaCodigo(t, 'sd_informes.fase', tramo)} claseTabla="sdp-tabla">
              <thead>
                <tr>
                  <th>{t('sd_informes.col_cuando')}</th>
                  <th>{t('sd_informes.col_publico')}</th>
                  <th>{t('sd_informes.col_mensaje')}</th>
                  <th>{t('sd_informes.col_canal')}</th>
                  <th>{t('sd_informes.col_responsable')}</th>
                </tr>
              </thead>
              <tbody>
                {filas.map(a => (
                  <tr key={a.id}>
                    <td>{etiquetaCodigo(t, 'sd_informes.momento', a.timing)}</td>
                    <td>{publico(a.audience)}</td>
                    <td>
                      <details>
                        <summary className="sdp-wrap">{a.subject}</summary>
                        <div className="sdm-pre u-text2-xs">{a.message_template}</div>
                      </details>
                    </td>
                    <td className="sdp-wrap">{a.channel}</td>
                    <td>{a.responsible}</td>
                  </tr>
                ))}
              </tbody>
            </TablaSimple>
          </div>
        )
      })}
      <p className="u-hint">{t('sd_informes.comunicaciones_ayuda')}</p>
      <Generado cuando={datos.generated_at} />
    </div>
  )
}

/* ── 6. Simulación «¿y si…?» ─────────────────────────────────────────────── */

export function InformeSimulacion({ datos }: { datos: Simulacion }) {
  const t = useAppT()
  const tono = useTono()
  const ventana = useVentana()
  const { tokens } = useChartTheme()
  const { original: o, simulated: s, delta: d } = datos
  const conSigno = (n: number) => `${n > 0 ? '+' : ''}${n}`
  const kindCambio: StatusBadgeKind = d.risk_change === 'escalated' ? 'danger' : d.risk_change === 'reduced' ? 'success' : 'neutral'
  const grafico = COMPONENTES.map(c => ({
    nombre: t(`sd_informes.componente.${c.clave}`), original: o.components?.[c.clave] ?? 0, simulado: s.components?.[c.clave] ?? 0,
  }))
  const tonoSim = tono('riesgo', s.score)
  const p = datos.proposed_window_evaluation
  return (
    <div className="u-stack-14">
      <div className="sdp-kpis">
        <KpiCard icon={<Gauge size={16} />} label={t('sd_informes.riesgo_simulado')} value={`${s.score}/100`}
          danger={tonoSim === 'danger'} warning={tonoSim === 'warning'}
          sub={t('sd_informes.vs_original', { v: conSigno(d.score_diff), n: o.score })} />
        <KpiCard icon={<ShieldAlert size={16} />} label={t('sd_informes.nivel_de_riesgo')}
          value={<StatusBadge caps={false} kind={kindCambio}>{etiquetaCodigo(t, 'sd_informes.cambio_riesgo', d.risk_change)}</StatusBadge>}
          sub={`${etiquetaCodigo(t, 'sd_informes.nivel', o.risk_label)} → ${etiquetaCodigo(t, 'sd_informes.nivel', s.risk_label)}`} />
        <KpiCard icon={<Boxes size={16} />} label={t('sd_informes.cis_afectados')} value={s.ci_count_expanded}
          sub={t('sd_informes.vs_original', { v: conSigno(d.ci_count_diff), n: o.ci_count_expanded })} />
      </div>
      <TablaSimple densidad="compacta" etiqueta={t('sd_mercado.chg_simulacion')} claseTabla="sdp-tabla">
        <thead>
          <tr>
            <th>{t('sd_informes.concepto')}</th>
            <th>{t('sd_informes.original')}</th>
            <th>{t('sd_informes.simulado')}</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <th scope="row">{t('sd_informes.col_puntuacion')}</th>
            <td className="sdp-num"><Barra pct={o.score} color={colorDeTono(tono('riesgo', o.score))} etiqueta={t('sd_informes.puntuacion_aria', { n: o.score })} /></td>
            <td className="sdp-num"><Barra pct={s.score} color={colorDeTono(tonoSim)} etiqueta={t('sd_informes.puntuacion_aria', { n: s.score })} /></td>
          </tr>
          <tr>
            <th scope="row">{t('sd_informes.nivel_de_riesgo')}</th>
            <td><Nivel nivel={o.risk_label} /></td>
            <td><Nivel nivel={s.risk_label} /></td>
          </tr>
          <tr>
            <th scope="row">{t('sd_informes.cis_afectados')}</th>
            <td className="sdp-num">{o.ci_count_expanded}</td>
            <td className="sdp-num">{s.ci_count_expanded}</td>
          </tr>
          <tr>
            <th scope="row">{t('sd_informes.ventana_sugerida')}</th>
            <td>{ventana(o.window?.day_of_week, o.window?.hour_utc, o.window?.window_label)}</td>
            <td>{ventana(s.window?.day_of_week, s.window?.hour_utc, s.window?.window_label)}</td>
          </tr>
        </tbody>
      </TablaSimple>
      <div className="sdp-grafico" role="img" aria-label={t('sd_informes.simulacion_grafico')}>
        <Subtitulo>{t('sd_informes.componentes')}</Subtitulo>
        <ResponsiveContainer width="100%" height={COMPONENTES.length * 36 + 40}>
          <BarChart data={grafico} layout="vertical" margin={{ top: 4, right: 12, bottom: 4, left: 4 }}>
            <XAxis type="number" allowDecimals={false} tick={{ fill: tokens.text3, fontSize: 11 }} />
            <YAxis type="category" dataKey="nombre" width={150} tick={{ fill: tokens.text2, fontSize: 11 }} />
            <Tooltip contentStyle={tooltipDelTemaConBorde(tokens)} />
            <Legend wrapperStyle={LEYENDA_XS} />
            <Bar dataKey="original" name={t('sd_informes.original')} fill={tokens.text3} radius={[0, 4, 4, 0]} />
            <Bar dataKey="simulado" name={t('sd_informes.simulado')} fill={tokens.accent} radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      {p && (
        <div className="ds-card sdm-card">
          <div className="sdm-card__head">
            {p.is_optimal ? <CheckCircle2 size={14} aria-hidden="true" /> : <AlertTriangle size={14} aria-hidden="true" />}
            {t('sd_informes.ventana_propuesta')}: {ventana(p.day_of_week, p.hour_utc, p.window_label)}
            <StatusBadge caps={false} kind={p.is_optimal ? 'success' : 'warning'}>{t(p.is_optimal ? 'sd_informes.ventana_optima' : 'sd_informes.ventana_peor')}</StatusBadge>
          </div>
          <div className="u-text2-xs">
            {t('sd_informes.incidentes_en_ventana', { n: p.avg_incidents_in_window ?? 0 })}
            {' · '}{t('sd_informes.vs_optima', { v: conSigno(p.vs_optimal_diff) })}
          </div>
        </div>
      )}
      <p className="u-hint">{t('sd_informes.simulacion_ayuda')}</p>
    </div>
  )
}

/* ── 7. Flujo del CAB ────────────────────────────────────────────────────── */

export function InformeFlujoCab({ datos }: { datos: FlujoDelCab }) {
  const t = useAppT()
  const votos = datos.votes ?? []
  const aFavor = votos.filter(v => v.decision === 'approved').length
  const enContra = votos.filter(v => v.decision === 'rejected').length
  const pendientes = votos.length - aFavor - enContra
  const quorum = datos.quorum ?? 0
  const estado = etiquetaCodigo(t, 'sd_informes.flujo_estado', datos.status, etiquetaCodigo(t, 'sd_mercado.panel.estado_cambio', datos.status))
  return (
    <div className="u-stack-12">
      <div className="u-wrap-8">
        <span className="u-text2-xs">{t('sd_informes.fase_actual')}</span>
        <StatusBadge caps={false} kind={datos.status === 'rejected' ? 'danger' : 'info'} dot>{estado}</StatusBadge>
      </div>
      <div className="sdp-kpis">
        <KpiCard icon={<ThumbsUp size={16} />} label={t('sd_informes.a_favor')} value={aFavor}
          sub={quorum ? t('sd_informes.quorum_n', { n: quorum }) : undefined} accent={quorum > 0 && aFavor >= quorum} />
        <KpiCard icon={<ThumbsDown size={16} />} label={t('sd_informes.en_contra')} value={enContra} danger={enContra > 0} />
        <KpiCard icon={<Hash size={16} />} label={t('sd_informes.pendientes')} value={pendientes} warning={pendientes > 0} />
      </div>
      {quorum > 0 && (
        <Barra pct={Math.min(100, (aFavor / quorum) * 100)} color={aFavor >= quorum ? 'var(--success)' : 'var(--accent)'}
          etiqueta={t('sd_informes.quorum_aria', { n: aFavor, q: quorum })} />
      )}
      {datos.meeting && (
        <div className="u-stack-6">
          <Subtitulo>{t('sd_mercado.reunion_cab')}</Subtitulo>
          <div className="u-row-center-8"><CalendarClock size={14} aria-hidden="true" /><span>{fmtDateTime(datos.meeting.scheduled_at)}</span></div>
          {datos.meeting.agenda && <div className="sdm-pre u-text2-xs">{datos.meeting.agenda}</div>}
        </div>
      )}
      {votos.length > 0 && (
        <TablaSimple densidad="compacta" etiqueta={t('sd_mercado.flujo_cab')} claseTabla="sdp-tabla">
          <thead>
            <tr>
              <th>{t('sd_informes.col_miembro')}</th>
              <th>{t('sd_informes.col_decision')}</th>
              <th>{t('sd_informes.col_nota')}</th>
              <th>{t('sd_informes.col_fecha')}</th>
            </tr>
          </thead>
          <tbody>
            {votos.map((v, i) => (
              <tr key={i}>
                <td>{v.name ?? <span className="u-text3-sm">{t('sd_informes.sin_nombre')}</span>}</td>
                <td>
                  <StatusBadge caps={false} kind={KIND_DECISION[v.decision ?? 'pending'] ?? 'neutral'}>
                    {v.decision === 'approved' ? <CheckCircle2 size={12} aria-hidden="true" /> : v.decision === 'rejected' ? <XCircle size={12} aria-hidden="true" /> : null}
                    {etiquetaCodigo(t, 'sd_informes.decision', v.decision ?? 'pending')}
                  </StatusBadge>
                </td>
                <td className="sdp-wrap">{v.note || '—'}</td>
                <td>{v.voted_at ? fmtDateTime(v.voted_at) : '—'}</td>
              </tr>
            ))}
          </tbody>
        </TablaSimple>
      )}
    </div>
  )
}

/** Exportado para pruebas: tramo de un aviso del plan de comunicaciones. */
export { tramoDeAviso }
