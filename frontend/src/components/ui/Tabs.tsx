import { useRef } from 'react'
import type { CSSProperties, KeyboardEvent, ReactNode } from 'react'

/**
 * Tabs — pills planos compactos, idénticos al patrón usado en /expenses y /grc.
 *
 *   <Tabs items={[{id, label, count?, icon?}]} active={tab} onChange={setTab} />
 *
 * a11y: patrón ARIA de pestañas. role="tablist"/"tab", aria-selected en la
 * activa y sólo ella en el orden de tabulación; las flechas, Inicio y Fin
 * mueven el foco y la seleccionan. El anillo de foco sale sólo con teclado
 * (:focus-visible en index.css), así que ya no aparece al cargar.
 */
export interface TabItem {
  id: string
  label: ReactNode
  count?: number
  icon?: ReactNode
  disabled?: boolean
}

export type TabsVariant = 'pill' | 'underline'

export type TabsSize = 'sm' | 'md' | 'lg'

export interface TabsProps {
  items?: TabItem[]
  active?: string
  onChange?: (id: string) => void
  variant?: TabsVariant
  ariaLabel?: string
  size?: TabsSize
  className?: string
  style?: CSSProperties
}

/**
 * useTabListKeys — teclado del patrón ARIA de pestañas, compartido por Tabs y
 * PortalTabs. Sólo una pestaña entra en el orden de Tab (la activa, o la
 * primera habilitada); flechas, Inicio y Fin mueven el foco y la seleccionan.
 * Cada botón lleva role="tab" y data-tab-id.
 */
export function useTabListKeys(ids: string[], active: string | undefined, onChange?: (id: string) => void) {
  const listRef = useRef<HTMLDivElement>(null)
  const focusId = active !== undefined && ids.includes(active) ? active : ids[0]

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (!ids.length) return
    const cur = ids.indexOf(focusId as string)
    let next: number
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') next = (cur + 1) % ids.length
    else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') next = (cur - 1 + ids.length) % ids.length
    else if (e.key === 'Home') next = 0
    else if (e.key === 'End') next = ids.length - 1
    else return
    e.preventDefault()
    const id = ids[next]
    onChange?.(id)
    Array.from(listRef.current?.querySelectorAll<HTMLElement>('[role="tab"]') ?? [])
      .find(b => b.dataset.tabId === id)?.focus()
  }

  return { listRef, onKeyDown, focusId }
}

export default function Tabs({
  items = [],
  active,
  onChange,
  variant = 'pill',
  ariaLabel,
  size = 'md',
  className,
  style,
}: TabsProps) {
  const isPill = variant === 'pill'
  const { listRef, onKeyDown, focusId } = useTabListKeys(
    items.filter(it => !it.disabled).map(it => it.id), active, onChange)
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
      ref={listRef}
      role="tablist"
      aria-label={ariaLabel}
      onKeyDown={onKeyDown}
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
            role="tab"
            data-tab-id={it.id}
            aria-selected={isActive}
            tabIndex={it.id === focusId ? 0 : -1}
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
              boxShadow: 'none',
            }}
          >
            {it.icon && <span aria-hidden="true" style={{ display: 'inline-flex' }}>{it.icon}</span>}
            <span>{it.label}</span>
            {typeof it.count === 'number' && (
              <span style={{
                fontSize: 'var(--text-2xs)', fontWeight: 700,
                background: isActive ? 'var(--accent)' : 'var(--surface-4)',
                color: isActive ? 'var(--on-accent)' : 'var(--text-2)',
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

export interface TabPanelProps {
  id: string
  active?: string
  children?: ReactNode
  style?: CSSProperties
  padded?: boolean
}

/**
 * TabPanel — wrapper opcional con aria-labelledby/role.
 */
export function TabPanel({ id, active, children, style, padded = true }: TabPanelProps) {
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
