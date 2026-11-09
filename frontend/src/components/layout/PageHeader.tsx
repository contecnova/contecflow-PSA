import type { ReactNode } from 'react'
// TODO type: ToastContext still JS — useToast() returns an untyped shape with `.error(msg: string)`.
import { useToast } from '../../context/ToastContext'

interface ExtractedTable {
  headers: string[]
  rows: string[][]
}

function isVisible(el: Element | null): boolean {
  if (!el) return false
  const style = window.getComputedStyle(el as Element)
  return style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0'
}

function toCellText(node: Element | null): string {
  if (!node) return ''
  const clone = node.cloneNode(true) as Element
  clone.querySelectorAll('button,input,select,textarea,svg,img,[aria-hidden="true"],[role="button"]').forEach(el => el.remove())
  return (clone?.textContent || '')
    .replace(/\s+/g, ' ')
    // Los caracteres de esta clase son ESPACIOS IRREGULARES a proposito: es el
    // saneador que normaliza NBSP y caracteres de ancho cero a un espacio normal.
    // eslint-disable-next-line no-irregular-whitespace
    .replace(/[   ]/g, ' ')
    .trim()
}

function escapeHtml(value: unknown): string {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function buildXlsFromMatrix(headers: string[], rows: string[][], sheetName: string): string {
  const headerRow = headers.map(h => `<th>${escapeHtml(h)}</th>`).join('')
  const bodyRows = rows.map(r => `<tr>${r.map(c => `<td>${escapeHtml(c)}</td>`).join('')}</tr>`).join('')
  return `<!doctype html><html><head><meta charset="utf-8"></head><body><table data-sheet="${escapeHtml(sheetName)}"><thead><tr>${headerRow}</tr></thead><tbody>${bodyRows}</tbody></table></body></html>`
}

function downloadXlsFile(filename: string, content: string): void {
  const blob = new Blob([content], { type: 'application/vnd.ms-excel;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

function extractFromHtmlTable(root: Element): ExtractedTable | null {
  const tables: HTMLTableElement[] = root.tagName === 'TABLE'
    ? [root as HTMLTableElement]
    : [...root.querySelectorAll('table')] as HTMLTableElement[]
  let best: { table: HTMLTableElement; rows: HTMLTableRowElement[]; score: number } | null = null
  for (const table of tables) {
    if (!isVisible(table)) continue
    const rows = [...table.querySelectorAll('tbody tr')] as HTMLTableRowElement[]
    const headerCount = table.querySelectorAll('thead th').length
    const score = rows.length > 0 ? rows.length : (headerCount > 0 ? 1 : 0)
    if (score === 0) continue
    if (!best || score > best.score) {
      best = { table, rows, score }
    }
  }
  if (!best) return null
  const headers = [...best.table.querySelectorAll('thead th')].map(toCellText).filter(Boolean)
  const dataRows: string[][] = best.rows
    .map(tr => [...tr.querySelectorAll('td,th')].map(toCellText))
    .filter(r => r.some(Boolean))
  if (headers.length === 0 && dataRows.length > 0) {
    const fallbackHeaders = dataRows[0].map((_, i) => `Columna ${i + 1}`)
    return { headers: fallbackHeaders, rows: dataRows }
  }
  if (headers.length > 0) return { headers, rows: dataRows }
  return null
}

function extractFromGridList(root: Element): ExtractedTable | null {
  const containers: Element[] = root.tagName === 'DIV'
    ? [root, ...root.querySelectorAll('div')]
    : [...root.querySelectorAll('div')]
  let best: ExtractedTable | null = null
  for (const container of containers) {
    if (!isVisible(container)) continue
    const children = [...container.children]
    const gridRows = children.filter(ch => ch.tagName === 'DIV' && (ch.getAttribute('style') || '').includes('grid-template-columns'))
    if (gridRows.length < 2) continue
    const header = [...gridRows[0].children].map(toCellText).filter(Boolean)
    const rows = gridRows.slice(1)
      .map(r => [...r.children].map(toCellText))
      .filter(r => r.some(Boolean))
      .map(r => {
        // Trim trailing empty action columns to keep exported files usable.
        let end = r.length
        while (end > 0 && !r[end - 1]) end -= 1
        return r.slice(0, Math.max(end, header.length))
      })
    if (header.length < 2 || rows.length === 0) continue
    if (!best || rows.length > best.rows.length) best = { headers: header, rows }
  }
  return best
}

function extractFromCardList(root: Element): ExtractedTable | null {
  const containers: Element[] = root.tagName === 'DIV'
    ? [root, ...root.querySelectorAll('div')]
    : [...root.querySelectorAll('div')]
  let best: ExtractedTable | null = null
  for (const container of containers) {
    if (!isVisible(container)) continue
    const children = [...container.children].filter(ch => ch.tagName === 'DIV' && isVisible(ch))
    if (children.length < 2) continue

    const rows: string[][] = children
      .map(ch => toCellText(ch))
      .filter(Boolean)
      .map(text => [text])

    if (rows.length < 2) continue
    if (!best || rows.length > best.rows.length) {
      best = { headers: ['Detalle'], rows }
    }
  }
  return best
}

function resolveExportRoot(root: Element, targetSelector?: string): Element {
  if (targetSelector) {
    const explicit = root.querySelector(targetSelector)
    if (explicit && isVisible(explicit)) return explicit
  }
  const marked = [...root.querySelectorAll('[data-export-table]')].find(isVisible)
  if (marked) return marked
  return root
}

interface ExportOptions {
  targetSelector?: string
  filePrefix?: string
}

function exportVisibleListToExcel({ targetSelector, filePrefix }: ExportOptions = {}): boolean {
  const root = (document.querySelector('.page-content') as Element | null) || document.body
  const exportRoot = resolveExportRoot(root, targetSelector)
  const data = extractFromHtmlTable(exportRoot) || extractFromGridList(exportRoot) || extractFromCardList(exportRoot)
  if (!data || !data.headers?.length) return false

  const sheetName = document.title || 'Listado'
  const content = buildXlsFromMatrix(data.headers, data.rows, sheetName)
  const dateSuffix = new Date().toISOString().slice(0, 10)
  const baseTitle = filePrefix || sheetName || 'listado'
  const safeTitle = baseTitle.toLowerCase().replace(/[^a-z0-9_-]+/g, '_').replace(/^_+|_+$/g, '') || 'listado'
  downloadXlsFile(`${safeTitle}_${dateSuffix}.xls`, content)
  return true
}

interface AutoListExportButtonProps {
  exportTargetSelector?: string
  exportFilePrefix?: string
}

function AutoListExportButton({ exportTargetSelector, exportFilePrefix }: AutoListExportButtonProps) {
  // TODO type: ToastContext still JS — `.error` signature inferred.
  const toast = useToast() as { error: (msg: string) => void }
  return (
    <button
      type="button"
      onClick={() => {
        const ok = exportVisibleListToExcel({ targetSelector: exportTargetSelector, filePrefix: exportFilePrefix })
        if (!ok) toast.error('No hay una lista exportable en la vista actual.')
      }}
      style={{
        display: 'flex', alignItems: 'center', gap: 6,
        background: 'var(--surface-2)', border: '1px solid var(--surface-4)',
        borderRadius: 8, padding: '8px 14px', color: 'var(--text-1)',
        cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit', fontWeight: 600,
      }}
      aria-label="Exportar lista a Excel"
    >
      📊 Exportar Excel
    </button>
  )
}

export interface BreadcrumbCrumb {
  label: string
  onClick?: () => void
}

export interface MetaItem {
  icon?: ReactNode
  value?: ReactNode
  label?: ReactNode
  color?: string
}

interface PageHeaderProps {
  title?: ReactNode
  subtitle?: ReactNode
  actions?: ReactNode
  breadcrumb?: BreadcrumbCrumb[]
  meta?: MetaItem[]
  icon?: ReactNode
  sticky?: boolean
  showListExport?: boolean
  exportTargetSelector?: string
  exportFilePrefix?: string
}

/**
 * PageHeader — Cabecera de página consistente con icono, título, breadcrumb, acciones y métricas.
 * Props: title, subtitle, icon, actions, meta, breadcrumb, sticky (fija al scroll).
 */
export default function PageHeader({
  title,
  subtitle,
  actions,
  breadcrumb,
  meta,
  icon,
  sticky = false,
  showListExport = true,
  exportTargetSelector,
  exportFilePrefix,
}: PageHeaderProps) {
  return (
    <div className={sticky ? 'sticky-top sticky-top--shadow' : undefined} style={{
      marginBottom: 28,
      paddingTop: sticky ? 16 : 0,
      paddingBottom: 20,
      borderBottom: '1px solid var(--surface-4)',
    }}>
      {/* Breadcrumb */}
      {breadcrumb && (
        <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginBottom: 10 }}>
          {breadcrumb.map((crumb, i) => (
            <span key={i} style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
              {i > 0 && <span style={{ color: 'var(--text-4)', fontSize: "var(--text-xs)" }}>›</span>}
              {crumb.onClick ? (
                <button type="button" style={{
                  fontSize: "var(--text-xs)", fontWeight: 500, color: i === breadcrumb.length - 1 ? 'var(--text-2)' : 'var(--accent)',
                  cursor: 'pointer', textTransform: 'uppercase', letterSpacing: '0.06em',
                  background: 'none', border: 'none', padding: 0, fontFamily: 'inherit',
                }} onClick={crumb.onClick}>{crumb.label}</button>
              ) : (
                <span style={{
                  fontSize: "var(--text-xs)", fontWeight: 500, color: i === breadcrumb.length - 1 ? 'var(--text-2)' : 'var(--accent)',
                  textTransform: 'uppercase', letterSpacing: '0.06em',
                }}>{crumb.label}</span>
              )}
            </span>
          ))}
        </div>
      )}

      {/* Título + acciones */}
      {/* Revisión 2026-11: en pantallas estrechas las acciones bajan de línea
          en vez de salirse (medido en /cmdb a 390 px: +346 px de desborde). */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
        <div style={{ flex: '1 1 240px', minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            {icon && (
              <div style={{
                width: 36, height: 36, borderRadius: 10,
                background: 'var(--accent-muted)', border: '1px solid var(--accent-muted)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                color: 'var(--accent)', flexShrink: 0,
              }}>
                {icon}
              </div>
            )}
            <h1 style={{
              fontSize: "var(--text-xl-em)", fontWeight: 700, color: 'var(--text-1)',
              letterSpacing: '-0.01em', lineHeight: 1.2, margin: 0,
            }}>
              {title}
            </h1>
          </div>
          {subtitle && (
            <p style={{ fontSize: "var(--text-base)", color: 'var(--text-2)', margin: '8px 0 0', fontWeight: 400, paddingLeft: icon ? 46 : 0 }}>
              {subtitle}
            </p>
          )}
          {/* Meta tags */}
          {meta && meta.length > 0 && (
            <div style={{ display: 'flex', gap: 12, marginTop: 10, flexWrap: 'wrap', paddingLeft: icon ? 46 : 0 }}>
              {meta.map((m, i) => (
                <div key={i} style={{ display: 'flex', gap: 5, alignItems: 'center', fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>
                  {m.icon && <span style={{ opacity: 0.7 }}>{m.icon}</span>}
                  <span style={{ color: m.color || 'var(--text-2)' }}>{m.value}</span>
                  {m.label && <span style={{ color: 'var(--text-3)' }}>{m.label}</span>}
                </div>
              ))}
            </div>
          )}
        </div>
        {/* Actions slot */}
        {(actions || showListExport) && (
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', maxWidth: '100%' }}>
            {actions}
            {showListExport && <AutoListExportButton exportTargetSelector={exportTargetSelector} exportFilePrefix={exportFilePrefix} />}
          </div>
        )}
      </div>
    </div>
  )
}
