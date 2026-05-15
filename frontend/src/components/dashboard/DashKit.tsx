/**
 * DashKit — componentes visuales compartidos para todos los dashboards de sección.
 * Mismo sistema de diseño que MetricsDashboardTab y BIPage.
 */
import React from 'react'
import { Link } from 'react-router-dom'
import { COLOR } from '../../constants/theme'
import PageShell from '../layout/PageShell'
import PageHeader from '../layout/PageHeader'

export { COLOR }

interface KpiIconProps {
  icon: React.ComponentType<{ size?: number; strokeWidth?: number }>
  size?: number
}

/* ── KpiIcon — wrapper para usar iconos Lucide en KpiCard ───────────────────
 * Sustituye el patrón de pasar emojis (icon="✅") por un icono de la librería.
 * Mantiene la altura y centrado consistentes con el resto de la card.
 */
export function KpiIcon({ icon: Icon, size = 14 }: KpiIconProps) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 16, height: 16 }}>
      <Icon size={size} strokeWidth={2.2} />
    </span>
  )
}

/* ── Design tokens ─────────────────────────────────────────────────────────── */
export const S: Record<string, React.CSSProperties> = {
  card: {
    background: 'var(--surface-2)',
    border: '1px solid var(--surface-4)',
    borderRadius: 14,
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
    <button onClick={onClick} style={{
      padding: '7px 18px', borderRadius: 8,
      border: `1px solid ${active ? COLOR.accent : 'var(--surface-4)'}`,
      background: active ? COLOR.accentMuted : 'transparent',
      color: active ? COLOR.accent : 'var(--text-2)',
      fontSize: "var(--text-sm)", fontWeight: 600, cursor: 'pointer',
      fontFamily: 'inherit', transition: 'all 0.15s',
    }}>{label}</button>
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
    <div style={{ ...S.card, display: 'flex', flexDirection: 'column' }}>
      <div style={{ height: 3, background: bar, borderRadius: '14px 14px 0 0' }} />
      <div style={{ ...S.cardPad, flex: 1, display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {icon && (
            <span style={{
              fontSize: "var(--text-lg-em)", background: `${bar}18`,
              borderRadius: 8, padding: '5px 7px', lineHeight: 1,
            }}>{icon}</span>
          )}
          <span style={{
            fontSize: "var(--text-2xs)", fontWeight: 700, color: 'var(--text-3)',
            textTransform: 'uppercase', letterSpacing: '0.09em',
          }}>{label}</span>
        </div>
        <div style={{
          fontSize: "var(--text-34)", fontWeight: 700,
          color: color || 'var(--text-1)',
          lineHeight: 1.1, letterSpacing: '-0.5px',
        }}>{value ?? '—'}</div>
        {sub && (
          <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', lineHeight: 1.4 }}>{sub}</div>
        )}
        {action?.to && (
          <Link to={action.to} style={{
            marginTop: 4, fontSize: "var(--text-xs)", fontWeight: 600,
            color: COLOR.accent, textDecoration: 'none',
            display: 'inline-flex', alignItems: 'center', gap: 3,
            opacity: 0.85,
          }}
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
    <svg width={size} height={size} style={{ transform: 'rotate(-90deg)', flexShrink: 0 }}>
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
      <div style={{ position: 'relative', flexShrink: 0 }}>
        <RingGauge value={typeof value === 'number' ? value : 0} color={color} />
        <div style={{
          position: 'absolute', inset: 0,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: "var(--text-sm)", fontWeight: 700, color,
        }}>
          {value != null ? `${value}` : '—'}
        </div>
      </div>
      <div>
        <div style={{
          fontSize: "var(--text-2xs)", fontWeight: 700, color: 'var(--text-3)',
          textTransform: 'uppercase', letterSpacing: '0.09em', marginBottom: 4,
        }}>{label}</div>
        <div style={{
          fontSize: "var(--text-2xl-em)", fontWeight: 700, color,
          lineHeight: 1, letterSpacing: '-0.5px',
        }}>{value != null ? `${value}${suffix}` : '—'}</div>
        {sub && (
          <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', marginTop: 4 }}>{sub}</div>
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
    <div style={{ marginBottom: 14 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
        <span style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', textTransform: 'capitalize' }}>
          {String(label).replace(/_/g, ' ')}
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{
            fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-1)',
            background: 'var(--surface-4)', borderRadius: 6, padding: '2px 7px',
          }}>{displayValue ?? count}</span>
          <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', minWidth: 32, textAlign: 'right' }}>
            {pct}%
          </span>
        </div>
      </div>
      <div style={{ height: 7, background: 'var(--surface-4)', borderRadius: 4, overflow: 'hidden' }}>
        <div style={{
          width: `${pct}%`, height: '100%',
          background: color, borderRadius: 4,
          transition: 'width 0.6s cubic-bezier(0.4,0,0.2,1)',
        }} />
      </div>
    </div>
  )
}

/* ── Section card wrapper ──────────────────────────────────────────────────── */
export function SectionCard({ title, children, badge }: { title: string; children?: React.ReactNode; badge?: React.ReactNode }) {
  return (
    <div style={S.card}>
      <div style={{ ...S.cardPad, borderBottom: '1px solid var(--surface-4)', display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={S.sectionTitle}>{title}</span>
        {badge != null && (
          <span style={{
            fontSize: "var(--text-2xs)", fontWeight: 700, color: 'var(--text-3)',
            background: 'var(--surface-4)', borderRadius: 12,
            padding: '2px 8px', marginLeft: 4,
          }}>{badge}</span>
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
          <div style={{ display: 'flex', gap: 6 }}>
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
    <div style={{ ...S.card, display: 'flex', flexDirection: 'column' }}>
      <div style={{ height: 3, background: 'var(--surface-4)', borderRadius: '14px 14px 0 0' }} />
      <div style={{ ...S.cardPad, flex: 1, display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
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
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
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
    <div style={{ textAlign: 'center', padding: '80px 24px', color: 'var(--text-3)' }}>
      <div style={{ fontSize: "var(--text-6xl)", marginBottom: 16, opacity: 0.4 }}>{icon}</div>
      <div style={{ fontSize: "var(--text-md-em)", fontWeight: 600, marginBottom: 8, color: 'var(--text-2)' }}>{title}</div>
      {description && (
        <div style={{ fontSize: "var(--text-base)", maxWidth: 280, margin: '0 auto', lineHeight: 1.6 }}>{description}</div>
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
  if (!currency) return new Intl.NumberFormat(lang === 'en' ? 'en-US' : 'es-ES', { maximumFractionDigits: 0 }).format(v)
  return new Intl.NumberFormat(lang === 'en' ? 'en-US' : 'es-ES', {
    style: 'currency', currency, maximumFractionDigits: 0,
  }).format(v)
}

export const typePalette = [COLOR.accent, COLOR.success, COLOR.warning, COLOR.purple, '#2dd4bf', 'var(--orange)']
