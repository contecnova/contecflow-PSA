
/**
 * Pagination — simple prev/next + page number controls.
 *
 * Props:
 *   page        — current page (1-based)
 *   totalPages  — total number of pages
 *   onChange    — (newPage: number) => void
 *   maxVisible  — max page number buttons to show (default 7)
 */
export default function Pagination({ page, totalPages, onChange, maxVisible = 7 }) {
  if (totalPages <= 1) return null

  const btnBase = {
    minWidth: 32,
    height: 32,
    padding: '0 6px',
    border: '1px solid var(--surface-4)',
    borderRadius: 6,
    background: 'var(--surface-2)',
    color: 'var(--text-1)',
    cursor: 'pointer',
    fontSize: "var(--text-base)",
    fontFamily: 'inherit',
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    transition: 'background 0.15s, border-color 0.15s',
  }

  const activeBtnStyle = {
    ...btnBase,
    background: 'var(--accent)',
    borderColor: 'var(--accent)',
    color: '#fff',
    fontWeight: 700,
  }

  const disabledBtnStyle = {
    ...btnBase,
    opacity: 0.35,
    cursor: 'not-allowed',
  }

  // Compute visible page range
  const half = Math.floor(maxVisible / 2)
  let start = Math.max(1, page - half)
  let end = Math.min(totalPages, start + maxVisible - 1)
  if (end - start < maxVisible - 1) {
    start = Math.max(1, end - maxVisible + 1)
  }
  const pageNums = Array.from({ length: end - start + 1 }, (_, i) => start + i)

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 4, justifyContent: 'center', padding: '12px 0' }}>
      <button
        style={page === 1 ? disabledBtnStyle : btnBase}
        disabled={page === 1}
        onClick={() => onChange(1)}
        title="Primera página"
      >
        «
      </button>
      <button
        style={page === 1 ? disabledBtnStyle : btnBase}
        disabled={page === 1}
        onClick={() => onChange(page - 1)}
        title="Anterior"
      >
        ‹
      </button>

      {start > 1 && (
        <>
          <button style={btnBase} onClick={() => onChange(1)}>1</button>
          {start > 2 && <span style={{ color: 'var(--text-3)', padding: '0 2px' }}>…</span>}
        </>
      )}

      {pageNums.map(n => (
        <button
          key={n}
          style={n === page ? activeBtnStyle : btnBase}
          onClick={() => onChange(n)}
        >
          {n}
        </button>
      ))}

      {end < totalPages && (
        <>
          {end < totalPages - 1 && <span style={{ color: 'var(--text-3)', padding: '0 2px' }}>…</span>}
          <button style={btnBase} onClick={() => onChange(totalPages)}>{totalPages}</button>
        </>
      )}

      <button
        style={page === totalPages ? disabledBtnStyle : btnBase}
        disabled={page === totalPages}
        onClick={() => onChange(page + 1)}
        title="Siguiente"
      >
        ›
      </button>
      <button
        style={page === totalPages ? disabledBtnStyle : btnBase}
        disabled={page === totalPages}
        onClick={() => onChange(totalPages)}
        title="Última página"
      >
        »
      </button>
    </div>
  )
}
