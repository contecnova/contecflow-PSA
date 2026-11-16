import { useTextoUi } from './useTextoUi'
import './Pagination.css'

/**
 * Pagination — controles de primera/anterior/números/siguiente/última.
 *
 * Accesible: `<nav aria-label>`, `aria-current="page"` en la página activa y
 * un `aria-label` por botón (los símbolos « ‹ › » no se leen bien).
 * Opcionalmente muestra "1–25 de 312" si se le pasan `total` y `pageSize`.
 */
export interface PaginationProps {
  page: number
  totalPages: number
  onChange: (newPage: number) => void
  maxVisible?: number
  /** Total de elementos (X-Total-Count / meta.total): pinta el resumen "desde–hasta de total". */
  total?: number
  /** Tamaño de página, necesario junto a `total` para el resumen. */
  pageSize?: number
}

export default function Pagination({ page, totalPages, onChange, maxVisible = 7, total, pageSize }: PaginationProps) {
  const t = useTextoUi()
  if (totalPages <= 1) return null

  // Compute visible page range
  const half = Math.floor(maxVisible / 2)
  let start = Math.max(1, page - half)
  const end = Math.min(totalPages, start + maxVisible - 1)
  if (end - start < maxVisible - 1) {
    start = Math.max(1, end - maxVisible + 1)
  }
  const pageNums = Array.from({ length: end - start + 1 }, (_, i) => start + i)

  const numero = (n: number) => (
    <button
      key={n}
      type="button"
      className={n === page ? 'pag-btn pag-btn--active' : 'pag-btn'}
      aria-current={n === page ? 'page' : undefined}
      aria-label={t('pagination.pagina_n', { n })}
      onClick={() => onChange(n)}
    >
      {n}
    </button>
  )

  const resumen = total != null && pageSize
    ? t('pagination.resumen', {
        desde: Math.min(total, (page - 1) * pageSize + 1),
        hasta: Math.min(total, page * pageSize),
        total,
      })
    : null

  return (
    <nav className="pag" aria-label={t('pagination.navegacion')}>
      {resumen && <span className="pag-resumen" aria-live="polite">{resumen}</span>}
      <button
        type="button"
        className="pag-btn"
        disabled={page === 1}
        onClick={() => onChange(1)}
        title={t('pagination.primera_pagina')}
        aria-label={t('pagination.primera_pagina')}
      >
        «
      </button>
      <button
        type="button"
        className="pag-btn"
        disabled={page === 1}
        onClick={() => onChange(page - 1)}
        title={t('pagination.anterior')}
        aria-label={t('pagination.anterior')}
      >
        ‹
      </button>

      {start > 1 && (
        <>
          {numero(1)}
          {start > 2 && <span className="pag-ellipsis" aria-hidden="true">…</span>}
        </>
      )}

      {pageNums.map(numero)}

      {end < totalPages && (
        <>
          {end < totalPages - 1 && <span className="pag-ellipsis" aria-hidden="true">…</span>}
          {numero(totalPages)}
        </>
      )}

      <button
        type="button"
        className="pag-btn"
        disabled={page === totalPages}
        onClick={() => onChange(page + 1)}
        title={t('pagination.siguiente')}
        aria-label={t('pagination.siguiente')}
      >
        ›
      </button>
      <button
        type="button"
        className="pag-btn"
        disabled={page === totalPages}
        onClick={() => onChange(totalPages)}
        title={t('pagination.ultima_pagina')}
        aria-label={t('pagination.ultima_pagina')}
      >
        »
      </button>
    </nav>
  )
}
