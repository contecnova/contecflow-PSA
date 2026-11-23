/**
 * Tipos, constantes y utilidades compartidas de la página de informes.
 * Troceado de ReportsPage.tsx sin cambio de comportamiento (23-11-2026).
 */
import {
  type LucideIcon,
  Grid3X3,
  Table as TableIcon,
  Clock,
  Wallet,
  Coins,
  CalendarDays,
  Hexagon,
  Briefcase,
  Users,
  Ticket,
  KeyRound,
  Brain,
  Target,
  HeartPulse,
  Star,
  GraduationCap,
  GitBranch,
  TrendingUp,
  Receipt,
  ListChecks,
  FolderKanban,
  Bell,
  Cog,
  Server,
  Activity,
  Layers,
  LineChart as LineChartIcon,
  AreaChart as AreaChartIcon,
  PieChart as PieChartIcon,
  Donut,
  ScatterChart as ScatterChartIcon,
  Columns3,
  BarChart3,
} from 'lucide-react'
import type { CatalogoDeMetricas, ConsultaDeMetrica, FilaDeMetrica, OpcionesDeFiltroAnalitico } from '../../services/api/tipos-analitica'
import { CHART_COLORS_EXTENDED } from '../../constants/theme'
import { etiquetaCategoriaMetrica } from '../../i18n/catalogoMetricas'

/** El eje es de importes si su etiqueta (la pone el servidor) lleva el simbolo o
 *  el codigo de la moneda de la empresa, o el '€' con el que la escribe hoy. */
export function esEjeDeMoneda(etiqueta: string | null | undefined, m: { moneda: string; simbolo: string }): boolean {
  if (!etiqueta) return false
  return etiqueta.includes('€') || etiqueta.includes(m.simbolo) || etiqueta.includes(m.moneda)
}

// ── Colours ───────────────────────────────────────────────────────────────────
export const PALETTE = CHART_COLORS_EXTENDED

// Shared style constants used across sub-components
export const STATUS_COLORS: Record<string, string> = {
  ok: 'var(--success)', warning: 'var(--warning)', critical: 'var(--danger)',
  Crítico: 'var(--danger)', Alto: 'var(--warning)', Medio: 'var(--accent)', Bajo: 'var(--success)',
}

/** Nombre visible de una categoría (las desconocidas, que vienen del catálogo, se muestran tal cual). */
export const etiquetaCategoria = (cat: string | undefined, t: Parameters<typeof etiquetaCategoriaMetrica>[0]) => etiquetaCategoriaMetrica(t, cat)

/** Icono lucide de cada categoría del catálogo (antes, un emoji por categoría). */
const CAT_ICONS: Record<string, LucideIcon> = { Horas: Clock, Costes: Wallet, Rentabilidad: Coins, Capacidad: CalendarDays, Proyectos: Hexagon, Negocio: Briefcase, RRHH: Users, 'Service Desk': Ticket, Agilidad: Activity, ALM: KeyRound, IA: Brain, Estrategia: Target, Bienestar: HeartPulse, OKR: Target, NPS: Star, Formación: GraduationCap, Git: GitBranch, Ingresos: TrendingUp, Gastos: Receipt, Sprints: Activity, Tareas: ListChecks, Portfolio: FolderKanban, Facturación: Receipt, Alertas: Bell, Automatizaciones: Cog, CMDB: Server }

export function IconoCategoria({ cat, size = 14 }: { cat?: string; size?: number }) {
  const Icono = (cat && CAT_ICONS[cat]) || BarChart3
  return <Icono size={size} aria-hidden />
}

/** Celda de una fila de métrica: `label`, `value`, `status` o una serie por columna. */
export type MetricCell = string | number | null | undefined

export type MetricRow = FilaDeMetrica

export type MetricResult = ConsultaDeMetrica

export type Catalogue = CatalogoDeMetricas

export type FilterOptions = Partial<OpcionesDeFiltroAnalitico>

/** Configuración de un informe del explorador (lo que se guarda). */
export interface ReportConfig {
  name?: string
  metric?: string
  chartType?: string
  color?: string
  dateFrom?: string
  dateTo?: string
  projectId?: string
  userId?: string
  department?: string
  topN?: number
}

/** Informe guardado en `extra.informes_guardados` de las preferencias. */
export interface SavedReport extends ReportConfig {
  id: string
  savedAt?: string
}

export interface UserPreferences {
  extra?: { informes_guardados?: SavedReport[]; [clave: string]: unknown }
  [clave: string]: unknown
}

export interface ScheduledReportCreate {
  name: string
  metric: string
  frequency: string
  include_pdf: boolean
  recipients: string[]
}

export interface TooltipEntry {
  name?: string
  value?: number | string
  color?: string
}

export const CHART_TYPES: Array<{ id: string; label: string; Icon: LucideIcon }> = [
  { id: 'bar',         label: 'reportes_ui.graf_bar', Icon: BarChart3 },
  { id: 'bar_grouped', label: 'reportes_ui.graf_bar_grouped', Icon: Columns3 },
  { id: 'bar_stacked', label: 'reportes_ui.graf_bar_stacked', Icon: Layers },
  { id: 'line',        label: 'reportes_ui.graf_line', Icon: LineChartIcon },
  { id: 'area',        label: 'reportes_ui.graf_area', Icon: AreaChartIcon },
  { id: 'pie',         label: 'reportes_ui.graf_pie', Icon: PieChartIcon },
  { id: 'donut',       label: 'reportes_ui.graf_donut', Icon: Donut },
  { id: 'scatter',     label: 'reportes_ui.graf_scatter', Icon: ScatterChartIcon },
  { id: 'heatmap',     label: 'reportes_ui.graf_heatmap', Icon: Grid3X3 },
  { id: 'table',       label: 'reportes_ui.graf_table', Icon: TableIcon },
]

export const ICONO_GRAFICO: Record<string, LucideIcon> = Object.fromEntries(CHART_TYPES.map(c => [c.id, c.Icon]))
