import React from 'react'

/**
 * Tabs — pills planos compactos, idénticos al patrón usado en /expenses y /grc.
 *
 *   <Tabs items={[{id, label, count?, icon?}]} active={tab} onChange={setTab} />
 *
 * Markup deliberadamente simple: <button onClick> sin role="tab"/aria-selected
 * para evitar el focus indicator del navegador que aparece en la primera carga.
 * a11y: aria-pressed marca el activo. ARIA tabs pattern descartado a propósito —
 * causaba "línea blanca" debajo del tab activo en algunos navegadores.
 */
export default function Tabs({
  items = [],
  active,
  onChange,
  variant = 'pill', // "pill" (default) | "underline"
  ariaLabel,
  size = 'md',
  className,
  style,
}) {
  const isPill = variant === 'pill'
  const padding =
    size === 'sm' ? '4px 12px'
    : size === 'lg' ? '7px 16px'
    : '5px 14px'
  const fontSize =
    size === 'sm' ? 'var(--text-2xs)'
    : size === 'lg' ? 'var(--text-sm)'
    : 'var(--text-xs)'

  return (
    <div
      role="group"
      aria-label={ariaLabel}
      className={className}
      style={{
        display: 'flex',
        gap: isPill ? 6 : 0,
        flexWrap: 'wrap',
        borderBottom: isPill ? 'none' : '1px solid var(--surface-4)',
        marginBottom: 18,
        ...(style || {}),
      }}
    >
      {items.map((it) => {
        const isActive = it.id === active
        return (
          <button
            key={it.id}
            type="button"
            aria-pressed={isActive}
            disabled={it.disabled}
            onClick={() => !it.disabled && onChange?.(it.id)}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 6,
              padding,
              fontSize,
              fontFamily: 'inherit',
              cursor: it.disabled ? 'not-allowed' : 'pointer',
              opacity: it.disabled ? 0.5 : 1,
              borderTop: isPill
                ? `1px solid ${isActive ? 'var(--accent)' : 'var(--surface-4)'}`
                : 'none',
              borderRight: isPill
                ? `1px solid ${isActive ? 'var(--accent)' : 'var(--surface-4)'}`
                : 'none',
              borderLeft: isPill
                ? `1px solid ${isActive ? 'var(--accent)' : 'var(--surface-4)'}`
                : 'none',
              borderBottom: isPill
                ? `1px solid ${isActive ? 'var(--accent)' : 'var(--surface-4)'}`
                : (isActive ? '2px solid var(--accent)' : '2px solid transparent'),
              background: isPill
                ? (isActive ? 'var(--accent-muted)' : 'transparent')
                : 'transparent',
              color: isActive ? 'var(--accent)' : 'var(--text-2)',
              borderRadius: isPill ? 6 : 0,
              marginBottom: isPill ? 0 : -1,
              transition: 'color 0.12s, background 0.12s, border-color 0.12s',
              whiteSpace: 'nowrap',
              outline: 'none',
              boxShadow: 'none',
            }}
          >
            {it.icon && <span aria-hidden="true" style={{ display: 'inline-flex' }}>{it.icon}</span>}
            <span>{it.label}</span>
            {typeof it.count === 'number' && (
              <span style={{
                fontSize: "var(--text-2xs)", fontWeight: 700,
                background: isActive ? 'var(--accent)' : 'var(--surface-4)',
                color: isActive ? '#fff' : 'var(--text-2)',
                borderRadius: 'var(--radius-full)',
                padding: '1px 7px',
                minWidth: 16, textAlign: 'center',
              }}>{it.count}</span>
            )}
          </button>
        )
      })}
    </div>
  )
}

/**
 * TabPanel — wrapper opcional con aria-labelledby/role.
 */
export function TabPanel({ id, active, children, style, padded = true }) {
  if (id !== active) return null
  return (
    <div
      id={`tabpanel-${id}`}
      style={{ paddingTop: padded ? 12 : 0, ...(style || {}) }}
    >
      {children}
    </div>
  )
}
