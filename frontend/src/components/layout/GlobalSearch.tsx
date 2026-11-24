/**
 * GlobalSearch — Cmd+K search palette with keyboard navigation
 */
import { useState, useEffect, useRef, useMemo } from 'react'
import type { MouseEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { searchApi } from '../../services/api'
import type { ResultadoDeBusqueda } from '../../services/api/tipos-analitica'
import { INPUT_DEBOUNCE_MS } from '../../constants/timings'
import { useAppT } from '../../i18n/AppLangContext'
import { etiquetaCodigo } from '../../i18n/etiquetaCodigo'
import { Input, Pulsable } from '../ui'
import { useAuth } from '../../context/AuthContext'
import { puedeAbrir } from '../../permisos/navegacion'
import { Calendar, CheckSquare, Clock, FileText, FolderOpen, Megaphone, NotebookPen, Receipt, Search, Settings, Ticket, Timer, User } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import './GlobalSearch.css'

// 23-11-2026: `note` = páginas de «Mi cuaderno» (solo las propias o compartidas con quien busca).
const ICON_MAP: Record<string, LucideIcon> = { project: FolderOpen, task: CheckSquare, ticket: Ticket, user: User, invoice: FileText, opportunity: Megaphone, note: NotebookPen }

interface QuickAction {
  /** Texto: `globalsearch.accion_<clave>` y `globalsearch.pista_<clave>`. */
  clave: string
  Icono: LucideIcon
  path: string
}

// Auditoría 22-11-2026 (A2 del 04): antes, textos en castellano fijos y emojis, y sin
// mirar permisos. Ahora claves i18n, iconos lucide y filtro por la capacidad de la ruta.
const QUICK_ACTIONS: QuickAction[] = [
  { clave: 'nueva_tarea',   Icono: CheckSquare, path: '/tasks' },
  { clave: 'imputar_horas', Icono: Clock,       path: '/time' },
  { clave: 'nuevo_ticket',  Icono: Ticket,      path: '/service-desk' },
  { clave: 'proyectos',     Icono: FolderOpen,  path: '/projects' },
  { clave: 'cronometro',    Icono: Timer,       path: '/timer' },
  { clave: 'calendario',    Icono: Calendar,    path: '/calendar' },
  { clave: 'gastos',        Icono: Receipt,     path: '/expenses' },
  { clave: 'configuracion', Icono: Settings,    path: '/settings' },
]

type SearchResult = ResultadoDeBusqueda

type FlatItem =
  | { kind: 'action'; path: string }
  | { kind: 'result'; url?: string }

interface Props {
  onClose: () => void
}

// Resalte al pasar el ratón sobre una fila no seleccionada (delegado en el contenedor de la lista).
function filaDeNavegacion(e: MouseEvent<HTMLElement>): HTMLElement | null {
  const fila = (e.target as HTMLElement).closest<HTMLElement>('[data-nav-item]')
  return fila && !fila.dataset.sel ? fila : null
}
function resaltarFila(e: MouseEvent<HTMLElement>) {
  const fila = filaDeNavegacion(e)
  if (fila) fila.style.background = 'var(--surface-2)'
}
function apagarFila(e: MouseEvent<HTMLElement>) {
  const fila = filaDeNavegacion(e)
  if (fila) fila.style.background = 'transparent'
}

export default function GlobalSearch({ onClose }: Props) {
  const t = useAppT()
  const navigate = useNavigate()
  const { puede, canOpen } = useAuth()
  const acciones = useMemo(() => QUICK_ACTIONS.filter(a => puedeAbrir(a.path, puede, true) && canOpen(a.path)), [puede, canOpen])
  const [q, setQ] = useState<string>('')
  const [debouncedQ, setDebouncedQ] = useState<string>('')
  const [selectedIdx, setSelectedIdx] = useState<number>(-1)
  const inputRef = useRef<HTMLInputElement | null>(null)
  const listRef = useRef<HTMLDivElement | null>(null)

  // Auditoría 04 (código muerto, /search), 23-11-2026: «Ver todos los resultados» abre la
  // búsqueda completa (/search?q=…, filtros por tipo) desde la paleta; también Intro sin fila elegida.
  const puedeVerTodo = puedeAbrir('/search', puede, true) && canOpen('/search')
  function verTodos() {
    navigate(`/search?q=${encodeURIComponent(q.trim())}`)
    onClose()
  }

  function runAction(path: string) {
    navigate(path)
    onClose()
  }

  useEffect(() => { inputRef.current?.focus() }, [])

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedQ(q), INPUT_DEBOUNCE_MS)
    return () => clearTimeout(timer)
  }, [q])

  // Reset selection whenever query changes
  useEffect(() => { setSelectedIdx(-1) }, [debouncedQ])

  const { data, isLoading } = useQuery({
    queryKey: ['global-search', debouncedQ],
    queryFn: () => searchApi.search({ q: debouncedQ }).then(r => r.data),
    enabled: debouncedQ.length >= 2,
  })

  const results = useMemo<SearchResult[]>(() => data?.flat ?? [], [data])
  const grouped = useMemo<Record<string, SearchResult[]>>(() => data?.grouped ?? {}, [data])

  // Flat list of navigable items for keyboard nav
  const flatItems = useMemo<FlatItem[]>(() => {
    if (debouncedQ.length < 2) {
      return acciones.map(a => ({ kind: 'action', path: a.path }))
    }
    return results.map(item => ({ kind: 'result', url: item.url }))
  }, [debouncedQ, results, acciones])

  // Scroll selected item into view
  useEffect(() => {
    if (selectedIdx < 0 || !listRef.current) return
    const items = listRef.current.querySelectorAll<HTMLElement>('[data-nav-item]')
    items[selectedIdx]?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [selectedIdx])

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Escape') { onClose(); return }
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setSelectedIdx(i => Math.min(i + 1, flatItems.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setSelectedIdx(i => Math.max(i - 1, -1))
    } else if (e.key === 'Enter' && selectedIdx >= 0) {
      e.preventDefault()
      const item = flatItems[selectedIdx]
      if (item.kind === 'action') runAction(item.path)
      else if (item.url) { navigate(item.url); onClose() }
    } else if (e.key === 'Enter' && q.trim().length >= 2 && puedeVerTodo) {
      e.preventDefault()
      verTodos()
    }
  }

  // Compute running index across result groups for highlight
  let resultCursor = 0

  return (
    <div role="presentation" className="globalse-sx1"
      onMouseDown={onClose}>
      <div role="dialog" aria-modal="true" aria-label={t('globalsearch.busqueda_global')} className="globalse-sx2"
        onMouseDown={e => e.stopPropagation()}>
        <div className="globsear-row-1">
          <span className="globsear-txt-1"><Search size={16} aria-hidden /></span>
          <Input aria-label={t('global_search.placeholder')}
            ref={inputRef}
            value={q}
            onChange={e => setQ(e.target.value)}
            placeholder={t('global_search.placeholder')}
            className="u-flex1-min0"
            inputClassName="globsear-box-1"
            onKeyDown={handleKeyDown}
          />
          {isLoading && <span className="u-text3-sm">{t('common.searching')}</span>}
          <Pulsable onClick={onClose} className="globsear-box-2">Esc</Pulsable>
        </div>

        <div ref={listRef} className="globsear-box-3" role="presentation" onMouseOver={resaltarFila} onMouseOut={apagarFila}>
          {debouncedQ.length < 2 ? (
            <div>
              <div className="globsear-box-4">
                {t('globalsearch.acciones_rapidas')}
              </div>
              <div className="globsear-grid-1">
                {acciones.map((action, idx) => {
                  const isSelected = selectedIdx === idx
                  return (
                    <Pulsable className={`globsear-row-3 globalse-sx3 ${isSelected ? 'global-search-m1' : 'global-search-m2'}`} key={action.clave}
                      data-nav-item="1"
                      data-sel={isSelected ? '1' : undefined}
                      onClick={() => runAction(action.path)}
                    >
                      <span className="globsear-box-5"><action.Icono size={16} aria-hidden /></span>
                      <div>
                        <div className={`globsear-txt-2 ${isSelected ? 'global-search-m3' : 'global-search-m4'}`}>{t(`globalsearch.accion_${action.clave}`)}</div>
                        <div className="globsear-box-6">{t(`globalsearch.pista_${action.clave}`)}</div>
                      </div>
                    </Pulsable>
                  )
                })}
              </div>
            </div>
          ) : results.length === 0 && !isLoading ? (
            <div className="globsear-box-7">
              {t('global_search.no_results_for')} &quot;{debouncedQ}&quot;
            </div>
          ) : (
            Object.entries(grouped).filter(([, items]) => items?.length > 0).map(([type, items]) => (
              <div key={type}>
                <div className="globsear-box-8">
                  {etiquetaCodigo(t, 'busqueda_tipo', type)}
                </div>
                {(items || []).map(item => {
                  const idx = resultCursor++
                  const isSelected = selectedIdx === idx
                  return (
                    <Pulsable className={`globsear-row-4 ${isSelected ? 'global-search-m5' : 'global-search-m6'}`} key={item.id}
                      data-nav-item="1"
                      data-sel={isSelected ? '1' : undefined}
                      onClick={() => { if (item.url) navigate(item.url); onClose() }}
                    >
                      <span className="globsear-box-9">{(() => { const Icono = item.type ? ICON_MAP[item.type] : undefined; return Icono ? <Icono size={14} aria-hidden /> : '•' })()}</span>
                      <div className="u-flex1-min0">
                        <div className={`globsear-box-12 ${isSelected ? 'global-search-m7' : 'global-search-m8'}`}>{item.title}</div>
                        {item.subtitle && <div className="globsear-box-10">{item.subtitle}</div>}
                      </div>
                      {item.status && (
                        <span className="globsear-box-11">{item.status}</span>
                      )}
                    </Pulsable>
                  )
                })}
              </div>
            ))
          )}
        </div>

        {debouncedQ.length >= 2 && puedeVerTodo && (
          <Pulsable className="globsear-row-4 global-search-m6" onClick={verTodos}>
            <span className="globsear-box-9"><Search size={14} aria-hidden /></span>
            <div className="u-flex1-min0">
              <div className="globsear-box-12 global-search-m8">{t('globalsearch.ver_todos', { q: debouncedQ })}</div>
            </div>
          </Pulsable>
        )}

        <div className="globsear-row-2">
          <span>{`↑↓ ${t('common.navigate')}`}</span><span>{`↵ ${t('common.open')}`}</span><span>{`Esc ${t('common.close').toLowerCase()}`}</span>
        </div>
      </div>
    </div>
  )
}
