/**
 * DashKit — componentes visuales compartidos para todos los dashboards de sección.
 * Mismo sistema de diseño que MetricsDashboardTab y BIPage.
 */
import type { LucideIcon } from 'lucide-react'
import React from 'react'
import { Link } from 'react-router-dom'
import { COLOR, alpha } from '../../constants/theme'
import PageShell from '../layout/PageShell'
import PageHeader from '../layout/PageHeader'
import { localeActivo } from '../../utils/helpers'
import './DashKit.css'

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

/* ── Design tokens ─────────────────────────────────────────────────────────── */
export const S: Record<string, React.CSSProperties> = {
  card: {
    background: 'var(--surface-2)',
    border: '1px solid var(--surface-4)',
    borderRadius: 'var(--radius-lg)',
    overflow: 'hidden',
  },
  cardPad: { padding: '20px 24px' },
  sectionTitle: {
    fontSize: "var(--text-xs)",
    fontWeight: 700,
    color: 'var(--text-3)',
    textTransform: 'uppercase',
    letterSpacing: '0.09em',
    margin: 0,
  },
}

/* ── Period selector ───────────────────────────────────────────────────────── */
export function PeriodButton({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) {
  return (
    <button className="dashkit-box-13 dashkit-sx1" onClick={onClick} style={{ border: `1px solid ${active ? COLOR.accent : 'var(--surface-4)'}`, background: active ? COLOR.accentMuted : 'transparent', color: active ? COLOR.accent : 'var(--text-2)' }}>{label}</button>
  )
}

/* ── KPI card ──────────────────────────────────────────────────────────────── */
interface KpiCardProps {
  label: string
  value?: number | string | null
  sub?: React.ReactNode
  color?: string
  icon?: React.ReactNode
  accentBar?: string
  action?: { to: string; label?: string }
}

export function KpiCard({ label, value, sub, color, icon, accentBar, action }: KpiCardProps) {
  const bar = accentBar ?? color ?? COLOR.accent
  return (
    <div className="dashkit-card">
      <div className="dashkit-box-14" style={{ background: bar }} />
      <div className="dashkit-cardpad">
        <div className="u-row-center-8">
          {icon && (
            <span className="dashkit-box-15" style={{ background: alpha(bar, '18') }}>{icon}</span>
          )}
          <span className="dashkit-txt-1">{label}</span>
        </div>
        <div className="dashkit-txt-4" style={{ color: color || 'var(--text-1)' }}>{value ?? '—'}</div>
        {sub && (
          <div className="dashkit-txt-2">{sub}</div>
        )}
        {action?.to && (
          <Link to={action.to} className="dashkit-sx2" style={{ color: COLOR.accent }}
            onMouseEnter={e => { e.currentTarget.style.opacity = '1' }}
            onMouseLeave={e => { e.currentTarget.style.opacity = '0.85' }}
          >
            {action.label ?? 'Ver'} →
          </Link>
        )}
      </div>
    </div>
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
    <div style={{ ...S.card, ...S.cardPad, display: 'flex', alignItems: 'center', gap: 16 }}>
      <div className="dashkit-box-2">
        <RingGauge value={typeof value === 'number' ? value : 0} color={color} />
        <div className="dashkit-row-3" style={{ color }}>
          {value != null ? `${value}` : '—'}
        </div>
      </div>
      <div>
        <div className="dashkit-box-3">{label}</div>
        <div className="dashkit-txt-5" style={{ color }}>{value != null ? `${value}${suffix}` : '—'}</div>
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
        <div className="dashkit-box-16" style={{ width: `${pct}%`, background: color }} />
      </div>
    </div>
  )
}

/* ── Section card wrapper ──────────────────────────────────────────────────── */
export function SectionCard({ title, children, badge }: { title: string; children?: React.ReactNode; badge?: React.ReactNode }) {
  return (
    <div style={S.card}>
      <div className="dashkit-cardpad2">
        <span style={S.sectionTitle}>{title}</span>
        {badge != null && (
          <span className="dashkit-box-7">{badge}</span>
        )}
      </div>
      <div style={S.cardPad}>{children}</div>
    </div>
  )
}

/* ── Page shell (header + period selector) ───────────────────────────────────
   Wrapper sobre <PageShell> + <PageHeader>. Mantiene API legacy con icon/title/
   subtitle/days/setDays/periods para los Dashboards. */
interface DashPageShellProps {
  icon?: React.ReactNode
  title: string
  subtitle?: string
  days?: number
  setDays?: (d: number) => void
  periods?: number[]
  showPeriodSuffix?: boolean
  children?: React.ReactNode
}

export function DashPageShell({
  icon,
  title,
  subtitle,
  days,
  setDays,
  periods = [7, 30, 90],
  showPeriodSuffix = true,
  children,
}: DashPageShellProps) {
  const hasPeriodSelector = Array.isArray(periods) && periods.length > 0 && typeof days === 'number' && typeof setDays === 'function'
  const headerSubtitle = showPeriodSuffix && typeof days === 'number'
    ? `${subtitle} · últimos ${days} días`
    : subtitle

  return (
    <PageShell>
      <PageHeader
        icon={icon}
        title={title}
        subtitle={headerSubtitle}
        actions={hasPeriodSelector ? (
          <div className="u-row-6">
            {periods.map(d => (
              <PeriodButton key={d} active={days === d}
                label={d >= 365 ? '1a' : d >= 90 ? '90d' : `${d}d`}
                onClick={() => setDays(d)} />
            ))}
          </div>
        ) : undefined}
        showListExport={false}
      />
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
const skBox = (w: number | string, h: number | string, r: number | string = 6, extra: React.CSSProperties = {}): React.CSSProperties => ({
  width: w, height: h, borderRadius: r,
  background: 'var(--surface-4)',
  animation: 'skeletonPulse 1.4s ease-in-out infinite',
  ...extra,
})

export function KpiCardSkeleton() {
  return (
    <div className="dashkit-card">
      <div className="dashkit-box-8" />
      <div className="dashkit-cardpad3">
        <div className="u-row-center-8">
          <div style={skBox(32, 32, 8)} />
          <div style={skBox(80, 10, 4)} />
        </div>
        <div style={skBox(60, 34, 6)} />
        <div style={skBox(100, 9, 4)} />
      </div>
    </div>
  )
}

export function GaugeCardSkeleton() {
  return (
    <div style={{ ...S.card, ...S.cardPad, display: 'flex', alignItems: 'center', gap: 16 }}>
      <div style={skBox(68, 68, '50%', { flexShrink: 0 })} />
      <div className="u-stack-8">
        <div style={skBox(80, 10, 4)} />
        <div style={skBox(50, 26, 6)} />
        <div style={skBox(100, 9, 4)} />
      </div>
    </div>
  )
}

/* ── Empty state ───────────────────────────────────────────────────────────── */
export function DashEmpty({ icon = '📊', title = 'Sin datos', description }: { icon?: React.ReactNode; title?: string; description?: React.ReactNode }) {
  return (
    <div className="dashkit-box-9">
      <div className="dashkit-box-10">{icon}</div>
      <div className="dashkit-box-11">{title}</div>
      {description && (
        <div className="dashkit-box-12">{description}</div>
      )}
    </div>
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
