import { useState, useRef, useEffect } from 'react'

/**
 * ColVisibility — gear button + dropdown to show/hide table columns.
 *
 * Usage:
 *   const { visibleCols, ColToggle } = useColVisibility(COLS, storageKey)
 *   ...
 *   <ColToggle />  ← renders the ⚙ button + panel
 *   const colTemplate = visibleCols.map(c => c.width).join(' ')
 */

export interface ColumnDef {
  id: string
  label: string
  width: string
}

export interface UseColVisibilityResult {
  visibleCols: ColumnDef[]
  colTemplate: string
  ColToggle: () => JSX.Element
  visible: string[]
}

export function useColVisibility(allCols: ColumnDef[], storageKey: string): UseColVisibilityResult {
  const [visible, setVisible] = useState<string[]>(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(`cols-${storageKey}`) || 'null')
      if (Array.isArray(saved)) return saved
    } catch { /* noop */ }
    return allCols.map((c) => c.id)
  })

  const save = (ids: string[]): void => {
    setVisible(ids)
    localStorage.setItem(`cols-${storageKey}`, JSON.stringify(ids))
  }

  const toggle = (id: string): void => {
    // Never hide the first column (identity/name column)
    if (id === allCols[0].id) return
    save(
      visible.includes(id)
        ? visible.filter((x) => x !== id)
        : [...visible, id]
    )
  }

  const reset = (): void => save(allCols.map((c) => c.id))

  const visibleCols = allCols.filter((c) => visible.includes(c.id))
  const colTemplate = visibleCols.map((c) => c.width).join(' ')

  function ColToggle() {
    const [open, setOpen] = useState(false)
    const ref = useRef<HTMLDivElement | null>(null)

    useEffect(() => {
      if (!open) return
      const close = (e: MouseEvent): void => {
        if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
      }
      document.addEventListener('mousedown', close)
      return () => document.removeEventListener('mousedown', close)
    }, [open])

    return (
      <div ref={ref} style={{ position: 'relative', display: 'inline-block' }}>
        <button
          onClick={() => setOpen((o) => !o)}
          title="Mostrar / ocultar columnas"
          style={{
            background: open ? 'var(--surface-4)' : 'transparent',
            border: `1px solid ${open ? 'var(--surface-5)' : 'transparent'}`,
            borderRadius: 'var(--radius-sm)', padding: '4px 7px', cursor: 'pointer',
            color: open ? 'var(--text-1)' : 'var(--text-3)',
            fontSize: 'var(--text-sm)', transition: 'all 0.1s', display: 'flex', alignItems: 'center', gap: 4,
          }}
          onMouseEnter={(e) => { if (!open) { e.currentTarget.style.background = 'var(--surface-3)'; e.currentTarget.style.color = 'var(--text-2)' } }}
          onMouseLeave={(e) => { if (!open) { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--text-3)' } }}
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 20h9M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
          </svg>
          Columnas
        </button>

        {open && (
          <div className="col-toggle-panel"
            style={{ position: 'absolute', right: 0, top: 'calc(100% + 6px)', zIndex: 'var(--z-dropdown)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              marginBottom: 8, paddingBottom: 8, borderBottom: '1px solid var(--surface-4)' }}>
              <span style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--text-2)',
                textTransform: 'uppercase', letterSpacing: '0.07em' }}>Columnas</span>
              <button onClick={reset} style={{ fontSize: 'var(--text-2xs)', color: 'var(--text-3)', background: 'none',
                border: 'none', cursor: 'pointer', fontFamily: 'inherit', padding: 0, transition: 'color 0.1s' }}
                onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--text-1)' }}
                onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--text-3)' }}
              >
                Restablecer
              </button>
            </div>
            {allCols.map((col) => {
              const isChecked = visible.includes(col.id)
              const isFirst = col.id === allCols[0].id
              return (
                <label key={col.id} className="col-toggle-item"
                  style={{ opacity: isFirst ? 0.45 : 1, cursor: isFirst ? 'not-allowed' : 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={isChecked}
                    disabled={isFirst}
                    onChange={() => toggle(col.id)}
                    style={{ accentColor: 'var(--accent)', cursor: isFirst ? 'not-allowed' : 'pointer' }}
                  />
                  <span className="u-text2-sm">{col.label}</span>
                  {isFirst && <span style={{ fontSize: 'var(--text-2xs)', color: 'var(--text-3)', marginLeft: 'auto' }}>fijo</span>}
                </label>
              )
            })}
          </div>
        )}
      </div>
    )
  }

  return { visibleCols, colTemplate, ColToggle, visible }
}
