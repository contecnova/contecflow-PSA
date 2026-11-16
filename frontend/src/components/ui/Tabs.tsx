import { useRef } from 'react'
import type { CSSProperties, KeyboardEvent, ReactNode } from 'react'
import './Tabs.css'

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
/** Quita emojis de una etiqueta de texto (red de seguridad: los textos de las
 *  pestañas no deben llevarlos; el icono va en `icon`, y es lucide). */
const RE_PICTOGRAMAS = /[\p{Extended_Pictographic}\u{FE0F}\u{200D}]/gu
function sinPictogramas(label: ReactNode): ReactNode {
  return typeof label === 'string' ? label.replace(RE_PICTOGRAMAS, '').replace(/\s{2,}/g, ' ').trim() : label
}

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
  /** @deprecated Se ignora: todas las pestañas son `pill` (16-11-2026). */
  variant?: TabsVariant
  ariaLabel?: string
  /** @deprecated Se ignora: todas las pestañas son `md` (16-11-2026). */
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
  ariaLabel,
  className,
  style,
}: TabsProps) {
  // 16-11-2026 (pasada de diseño): todas las pestañas del producto son
  // pastilla y tamaño md. `variant` y `size` se siguen aceptando para no romper
  // a quien los pasa, pero se ignoran: cada pantalla tenía su tamaño y su estilo
  // (subrayado, grande, pequeño) y era lo primero que se notaba al navegar.
  const variant: TabsVariant = 'pill'
  const size: TabsSize = 'md'
  const { listRef, onKeyDown, focusId } = useTabListKeys(
    items.filter(it => !it.disabled).map(it => it.id), active, onChange)

  return (
    <div
      ref={listRef}
      role="tablist"
      aria-label={ariaLabel}
      onKeyDown={onKeyDown}
      className={['uitabs', `uitabs--${variant}`, className].filter(Boolean).join(' ')}
      style={style}
    >
      {items.map((it) => {
        const isActive = it.id === active
        return (
          <button
            className={`uitabs-row-2 uitabs-row-2--${size} uitabs-row-2--${variant}${isActive ? ' is-active' : ''}`}
            key={it.id}
            type="button"
            role="tab"
            data-tab-id={it.id}
            aria-selected={isActive}
            tabIndex={it.id === focusId ? 0 : -1}
            disabled={it.disabled}
            onClick={() => !it.disabled && onChange?.(it.id)}
          >
            {it.icon && typeof it.icon !== 'string' && <span aria-hidden="true" className="uitabs-row-1">{it.icon}</span>}
            <span>{sinPictogramas(it.label)}</span>
            {typeof it.count === 'number' && (
              <span className="uitabs-box-1">{it.count}</span>
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
  className?: string
  style?: CSSProperties
  padded?: boolean
}

/**
 * TabPanel — wrapper opcional con aria-labelledby/role.
 */
export function TabPanel({ id, active, children, className, style, padded = true }: TabPanelProps) {
  if (id !== active) return null
  return (
    <div
      id={`tabpanel-${id}`}
      className={['uitabs-panel', padded ? '' : 'uitabs-panel--plano', className].filter(Boolean).join(' ')}
      style={style}
    >
      {children}
    </div>
  )
}
