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
import { Pulsable } from '../ui'
import './GlobalSearch.css'

const ICON_MAP: Record<string, string> = { project:'⬡', task:'▦', ticket:'🎫', user:'👤', invoice:'🧾', opportunity:'🎪' }

interface QuickAction {
  label: string
  icon: string
  path: string
  hint: string
}

const QUICK_ACTIONS: QuickAction[] = [
  { label: 'Nueva tarea',         icon: '✅', path: '/tasks',           hint: 'Ir a tareas' },
  { label: 'Imputar horas',       icon: '⏱',  path: '/time',            hint: 'Registro de tiempo' },
  { label: 'Nuevo ticket soporte',icon: '🎫', path: '/service-desk',    hint: 'Service desk' },
  { label: 'Ver proyectos',       icon: '⬡',  path: '/projects',        hint: 'Lista de proyectos' },
  { label: 'Cronómetro',          icon: '⏲',  path: '/time',            hint: 'Timer de trabajo' },
  { label: 'Calendario',          icon: '📅', path: '/calendar',        hint: 'Ver calendario' },
  { label: 'Gastos',              icon: '💸', path: '/expenses',        hint: 'Registrar gasto' },
  { label: 'Configuración',       icon: '⚙️',  path: '/settings',        hint: 'Ajustes del sistema' },
]

// TODO type: search result payload — needs shared type from searchApi
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
  const [q, setQ] = useState<string>('')
  const [debouncedQ, setDebouncedQ] = useState<string>('')
  const [selectedIdx, setSelectedIdx] = useState<number>(-1)
  const inputRef = useRef<HTMLInputElement | null>(null)
  const listRef = useRef<HTMLDivElement | null>(null)

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
      return QUICK_ACTIONS.map(a => ({ kind: 'action', path: a.path }))
    }
    return results.map(item => ({ kind: 'result', url: item.url }))
  }, [debouncedQ, results])

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
          <span className="globsear-txt-1">⌕</span>
          <input aria-label={t('global_search.placeholder')}
            ref={inputRef}
            value={q}
            onChange={e => setQ(e.target.value)}
            placeholder={t('global_search.placeholder')}
            className="globsear-box-1"
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
                {QUICK_ACTIONS.map((action, idx) => {
                  const isSelected = selectedIdx === idx
                  return (
                    <Pulsable className={`globsear-row-3 globalse-sx3 ${isSelected ? 'global-search-m1' : 'global-search-m2'}`} key={action.path + action.label}
                      data-nav-item="1"
                      data-sel={isSelected ? '1' : undefined}
                      onClick={() => runAction(action.path)}
                    >
                      <span className="globsear-box-5">{action.icon}</span>
                      <div>
                        <div className={`globsear-txt-2 ${isSelected ? 'global-search-m3' : 'global-search-m4'}`}>{action.label}</div>
                        <div className="globsear-box-6">{action.hint}</div>
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
                      <span className="globsear-box-9">{(item.type && ICON_MAP[item.type]) || '•'}</span>
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

        <div className="globsear-row-2">
          <span>{`↑↓ ${t('common.navigate')}`}</span><span>{`↵ ${t('common.open')}`}</span><span>{`Esc ${t('common.close').toLowerCase()}`}</span>
        </div>
      </div>
    </div>
  )
}
