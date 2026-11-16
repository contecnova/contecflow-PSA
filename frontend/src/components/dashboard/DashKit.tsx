/**
 * DashKit — componentes visuales compartidos para todos los dashboards de sección.
 * Mismo sistema de diseño que MetricsDashboardTab y BIPage.
 *
 * 16-11-2026 (pasada de diseño): KpiCard y DashEmpty delegan en el kit
 * (components/ui); el periodo de DashPageShell va bajo la cabecera (SelectorDePeriodo)
 * y "últimos N días" se traduce (es/en/zh, módulo `dashkit`).
 */
import { ArrowRight, BarChart3 } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import React, { type CSSProperties } from 'react'
import { Link } from 'react-router-dom'
import { COLOR } from '../../constants/theme'
import PageShell from '../layout/PageShell'
import PageHeader from '../layout/PageHeader'
import { EmptyState, KpiCard as UiKpiCard, SelectorDePeriodo } from '../ui'
import type { ResultadoPeriodo } from '../../hooks/usePeriodo'
import { useAppT } from '../../i18n/AppLangContext'
import { localeActivo } from '../../utils/helpers'
import './DashKit.css'
import { medidasDeEsqueleto } from '../../utils/estilos'

export { COLOR }

interface KpiIconProps {
  /** Un icono de lucide-react. Auditoria 2026-11 (#39): con
   *  ComponentType<{size?: number}> los iconos de lucide (size: string | number)
   *  no encajaban y cada pantalla los forzaba con `as unknown as`. */
  icon: LucideIcon
  size?: number
}

/* ── KpiIcon — wrapper para usar iconos Lucide en KpiCard ───────────────────
 * Sustituye el patrón de pasar emojis (icon="✅") por un icono de la librería.
 * Mantiene la altura y centrado consistentes con el resto de la card.
 */
export function KpiIcon({ icon: Icon, size = 14 }: KpiIconProps) {
  return (
    <span className="dashkit-row-1">
      <Icon size={size} strokeWidth={2.2} />
    </span>
  )
}

/* ── KPI card ──────────────────────────────────────────────────────────────
 * 16-11-2026: delega en el KpiCard del kit (components/ui): misma tarjeta que
 * /projects, sin barra superior de color ni icono en recuadro tintado. Se
 * mantiene la API (color, accentBar, action) para no tocar a quien la usa:
 * `color` solo colorea la cifra si es uno de los semánticos del kit (peligro,
 * aviso, acento); `accentBar` se ignora; `action` sale como enlace bajo la cifra.
 */
interface KpiCardProps {
  label: string
  value?: number | string | null
  sub?: React.ReactNode
  color?: string
  icon?: React.ReactNode
  /** @deprecated Se ignora (16-11-2026): las KPI ya no llevan barra de color. */
  accentBar?: string
  action?: { to: string; label?: string }
}

export function KpiCard({ label, value, sub, color, icon, action }: KpiCardProps) {
  const t = useAppT()
  const detalle = action?.to ? (
    <>
      {sub && <span className="dashkit-kpi-sub">{sub}</span>}
      <Link to={action.to} className="dashkit-kpi-enlace">
        {action.label ?? t('dashkit.ver')}
        <ArrowRight size={12} aria-hidden />
      </Link>
    </>
  ) : sub
  return (
    <UiKpiCard
      icon={icon}
      label={label}
      value={value ?? '—'}
      sub={detalle}
      danger={color === COLOR.danger}
      warning={color === COLOR.warning}
      accent={color === COLOR.accent}
    />
  )
}

/* ── Gauge (ring SVG + number) ─────────────────────────────────────────────── */
function RingGauge({ value, color, size = 68 }: { value?: number | null; color: string; size?: number }) {
  const r = (size - 8) / 2
  const circ = 2 * Math.PI * r
  const progress = Math.min(Math.max(value ?? 0, 0), 100) / 100
  return (
    <svg width={size} height={size} className="dashkit-box-1">
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--surface-4)" strokeWidth={7} />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={7}
        strokeDasharray={circ} strokeDashoffset={circ * (1 - progress)} strokeLinecap="round" />
    </svg>
  )
}

interface GaugeCardProps {
  label: string
  value?: number | null
  color: string
  suffix?: string
  sub?: React.ReactNode
}

export function GaugeCard({ label, value, color, suffix = '%', sub }: GaugeCardProps) {
  return (
    <div className="dash-kit-e4">
      <div className="dashkit-box-2">
        <RingGauge value={typeof value === 'number' ? value : 0} color={color} />
        <div className="dashkit-row-3 dash-kit-e3" style={{ '--dash-kit-color': color } as CSSProperties}>
          {value != null ? `${value}` : '—'}
        </div>
      </div>
      <div>
        <div className="dashkit-box-3">{label}</div>
        <div className="dashkit-txt-5 dash-kit-e3" style={{ '--dash-kit-color': color } as CSSProperties}>{value != null ? `${value}${suffix}` : '—'}</div>
        {sub && (
          <div className="u-hint">{sub}</div>
        )}
      </div>
    </div>
  )
}

/* ── Bar row ───────────────────────────────────────────────────────────────── */
interface BarRowProps {
  label: string
  count: number
  total: number
  color: string
  displayValue?: React.ReactNode
}

export function BarRow({ label, count, total, color, displayValue }: BarRowProps) {
  const pct = total > 0 ? Math.round((count / total) * 100) : 0
  return (
    <div className="u-mb-14">
      <div className="dashkit-row-2">
        <span className="dashkit-txt-3">
          {String(label).replace(/_/g, ' ')}
        </span>
        <div className="u-row-center-8">
          <span className="dashkit-box-4">{displayValue ?? count}</span>
          <span className="dashkit-box-5">
            {pct}%
          </span>
        </div>
      </div>
      <div className="dashkit-box-6">
        <div className="dashkit-box-16 dash-kit-e5" style={{ '--dash-kit-width': `${pct}%`, '--dash-kit-background': color } as CSSProperties} />
      </div>
    </div>
  )
}

/* ── Section card wrapper ──────────────────────────────────────────────────── */
export function SectionCard({ title, children, badge }: { title: string; children?: React.ReactNode; badge?: React.ReactNode }) {
  return (
    <div className="dash-kit-e6">
      <div className="dashkit-cardpad2">
        <span className="dash-kit-e7">{title}</span>
        {badge != null && (
          <span className="dashkit-box-7">{badge}</span>
        )}
      </div>
      <div className="dash-kit-e8">{children}</div>
    </div>
  )
}

/* ── Page shell (header + period selector) ───────────────────────────────────
   Wrapper sobre <PageShell> + <PageHeader> para los Dashboards.
   Periodo libre (16-11-2026): el selector propio 7/30/90 días (`days`,
   `setDays`, `periods`) se sustituye por el común: se pasa `periodo.selector`
   de `usePeriodo(...)` y va bajo la cabecera, como filtro. */
interface DashPageShellProps {
  icon?: React.ReactNode
  title: string
  subtitle?: string
  /** `usePeriodo(...).selector`; sin él no hay selector de periodo. */
  periodo?: ResultadoPeriodo['selector']
  /** Informe sin serie temporal: oculta la agrupación del selector. */
  sinGranularidad?: boolean
  children?: React.ReactNode
}

export function DashPageShell({
  icon,
  title,
  subtitle,
  periodo,
  sinGranularidad = false,
  children,
}: DashPageShellProps) {
  return (
    <PageShell>
      <PageHeader
        icon={icon}
        title={title}
        subtitle={subtitle}
        showListExport={false}
      />
      {periodo && (
        <div className="dashkit-periodo">
          <SelectorDePeriodo {...periodo} sinGranularidad={sinGranularidad} />
        </div>
      )}
      {children}
    </PageShell>
  )
}

/* ── Skeleton loaders ──────────────────────────────────────────────────────── */
const skeletonPulse = `
  @keyframes skeletonPulse {
    0%,100% { opacity: 0.45; }
    50%      { opacity: 0.9; }
  }
`
if (typeof document !== 'undefined' && !document.getElementById('skeleton-pulse-style')) {
  const style = document.createElement('style')
  style.id = 'skeleton-pulse-style'
  style.textContent = skeletonPulse
  document.head.appendChild(style)
}
export function KpiCardSkeleton() {
  // Misma caja que el KpiCard del kit (sin la antigua barra superior).
  return (
    <div className="ds-card ui-kpi" aria-hidden>
      <div className="dashkit-sk" style={medidasDeEsqueleto(60, 28, 6)} />
      <div className="dashkit-sk" style={medidasDeEsqueleto(90, 10, 4)} />
      <div className="dashkit-sk" style={medidasDeEsqueleto(120, 9, 4)} />
    </div>
  )
}

export function GaugeCardSkeleton() {
  return (
    <div className="dash-kit-e4">
      <div className="dashkit-sk u-shrink0" style={medidasDeEsqueleto(68, 68, '50%')} />
      <div className="u-stack-8">
        <div className="dashkit-sk" style={medidasDeEsqueleto(80, 10, 4)} />
        <div className="dashkit-sk" style={medidasDeEsqueleto(50, 26, 6)} />
        <div className="dashkit-sk" style={medidasDeEsqueleto(100, 9, 4)} />
      </div>
    </div>
  )
}

/* ── Empty state ───────────────────────────────────────────────────────────
 * 16-11-2026: delega en el EmptyState del kit, con icono lucide y textos
 * traducidos (antes 📊 y "Sin datos" fijo en castellano). */
export function DashEmpty({ icon, title, description }: { icon?: React.ReactNode; title?: string; description?: React.ReactNode }) {
  const t = useAppT()
  return (
    <EmptyState
      icon={icon && typeof icon !== 'string' ? icon : <BarChart3 size={28} />}
      title={title ?? t('dashkit.sin_datos')}
      description={description}
    />
  )
}

/* ── helpers ───────────────────────────────────────────────────────────────── */
export function dateRange(days: number): { date_from: string; date_to: string } {
  const d_to = new Date().toISOString().slice(0, 10)
  const d_from = new Date(Date.now() - days * 86_400_000).toISOString().slice(0, 10)
  return { date_from: d_from, date_to: d_to }
}

export function fmtCur(v: number | null | undefined, lang: string = 'es', currency?: string): string {
  if (v == null) return '—'
  if (!currency) return new Intl.NumberFormat(localeActivo(lang), { maximumFractionDigits: 0 }).format(v)
  return new Intl.NumberFormat(localeActivo(lang), {
    style: 'currency', currency, maximumFractionDigits: 0,
  }).format(v)
}

export const typePalette = [COLOR.accent, COLOR.success, COLOR.warning, COLOR.purple, 'var(--chart-teal)', 'var(--orange)']
