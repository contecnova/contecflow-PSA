/**
 * GlobalSearch — Cmd+K search palette with keyboard navigation
 */
import { useState, useEffect, useRef, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import api from '../../services/api'
import { useAppT } from '../../i18n/AppLangContext'

const ICON_MAP = { project:'⬡', task:'▦', ticket:'🎫', user:'👤', invoice:'🧾', opportunity:'🎪' }
const TYPE_LABELS = { project:'Proyecto', task:'Tarea', ticket:'Ticket', user:'Usuario', invoice:'Factura', opportunity:'Oportunidad' }

const QUICK_ACTIONS = [
  { label: 'Nueva tarea',         icon: '✅', path: '/tasks',           hint: 'Ir a tareas' },
  { label: 'Imputar horas',       icon: '⏱',  path: '/time',            hint: 'Registro de tiempo' },
  { label: 'Nuevo ticket soporte',icon: '🎫', path: '/service-desk',    hint: 'Service desk' },
  { label: 'Ver proyectos',       icon: '⬡',  path: '/projects',        hint: 'Lista de proyectos' },
  { label: 'Cronómetro',          icon: '⏲',  path: '/time',            hint: 'Timer de trabajo' },
  { label: 'Calendario',          icon: '📅', path: '/calendar',        hint: 'Ver calendario' },
  { label: 'Gastos',              icon: '💸', path: '/expenses',        hint: 'Registrar gasto' },
  { label: 'Configuración',       icon: '⚙️',  path: '/settings',        hint: 'Ajustes del sistema' },
]

export default function GlobalSearch({ onClose }) {
  const t = useAppT()
  const navigate = useNavigate()
  const [q, setQ] = useState('')
  const [debouncedQ, setDebouncedQ] = useState('')
  const [selectedIdx, setSelectedIdx] = useState(-1)
  const inputRef = useRef(null)
  const listRef = useRef(null)

  function runAction(path) {
    navigate(path)
    onClose()
  }

  useEffect(() => { inputRef.current?.focus() }, [])

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedQ(q), 150)
    return () => clearTimeout(timer)
  }, [q])

  // Reset selection whenever query changes
  useEffect(() => { setSelectedIdx(-1) }, [debouncedQ])

  const { data, isLoading } = useQuery({
    queryKey: ['global-search', debouncedQ],
    queryFn: () => api.get('/global-search', { params: { q: debouncedQ } }).then(r => r.data),
    enabled: debouncedQ.length >= 2,
  })

  const results = data?.flat || []
  const grouped = data?.grouped || {}

  // Flat list of navigable items for keyboard nav
  const flatItems = useMemo(() => {
    if (debouncedQ.length < 2) {
      return QUICK_ACTIONS.map(a => ({ kind: 'action', path: a.path }))
    }
    return results.map(item => ({ kind: 'result', url: item.url }))
  }, [debouncedQ, results])

  // Scroll selected item into view
  useEffect(() => {
    if (selectedIdx < 0 || !listRef.current) return
    const items = listRef.current.querySelectorAll('[data-nav-item]')
    items[selectedIdx]?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [selectedIdx])

  function handleKeyDown(e) {
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
    <div role="presentation" style={{ position:'fixed', top:0, left:0, right:0, bottom:0, background:'rgba(0,0,0,0.5)', zIndex:9999, display:'flex', alignItems:'flex-start', justifyContent:'center', paddingTop:'15vh' }}
      onMouseDown={onClose}>
      <div role="presentation" style={{ width:'100%', maxWidth:620, background:'var(--surface-1)', borderRadius:16, border:'.5px solid var(--surface-4)', overflow:'hidden', boxShadow:'0 20px 60px rgba(0,0,0,0.3)' }}
        onMouseDown={e => e.stopPropagation()}>
        <div style={{ display:'flex', alignItems:'center', padding:'14px 18px', borderBottom:'.5px solid var(--surface-4)', gap:10 }}>
          <span style={{ fontSize:16, color:'var(--text-2)' }}>⌕</span>
          <input
            ref={inputRef}
            value={q}
            onChange={e => setQ(e.target.value)}
            placeholder={t('global_search.placeholder')}
            style={{ flex:1, background:'transparent', border:'none', outline:'none', fontSize:15, color:'var(--text-1)', fontFamily:'inherit' }}
            onKeyDown={handleKeyDown}
          />
          {isLoading && <span style={{ fontSize:12, color:'var(--text-3)' }}>{t('common.searching')}</span>}
          <button onClick={onClose} style={{ background:'transparent', border:'.5px solid var(--surface-4)', borderRadius:6, padding:'3px 8px', fontSize:11, color:'var(--text-2)', cursor:'pointer', fontFamily:'inherit' }}>Esc</button>
        </div>

        <div ref={listRef} style={{ maxHeight:450, overflowY:'auto' }}>
          {debouncedQ.length < 2 ? (
            <div>
              <div style={{ padding: '10px 18px 6px', fontSize: 11, fontWeight: 600, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '.06em' }}>
                Acciones rápidas
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 1, padding: '0 10px 10px' }}>
                {QUICK_ACTIONS.map((action, idx) => {
                  const isSelected = selectedIdx === idx
                  return (
                    <button key={action.path + action.label}
                      data-nav-item
                      onClick={() => runAction(action.path)}
                      type="button"
                      style={{
                        display: 'flex', alignItems: 'center', gap: 10,
                        padding: '10px 12px', cursor: 'pointer',
                        background: isSelected ? 'var(--accent-muted)' : 'transparent',
                        border: isSelected ? '1px solid var(--accent-glow)' : '1px solid transparent',
                        borderRadius: 8,
                        textAlign: 'left', fontFamily: 'inherit',
                        outline: 'none',
                      }}
                      onMouseEnter={e => { if (!isSelected) e.currentTarget.style.background = 'var(--surface-2)' }}
                      onMouseLeave={e => { if (!isSelected) e.currentTarget.style.background = 'transparent' }}
                    >
                      <span style={{ fontSize: 18, lineHeight: 1, flexShrink: 0 }}>{action.icon}</span>
                      <div>
                        <div style={{ fontSize: 13, fontWeight: 600, color: isSelected ? 'var(--accent)' : 'var(--text-1)' }}>{action.label}</div>
                        <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 1 }}>{action.hint}</div>
                      </div>
                    </button>
                  )
                })}
              </div>
            </div>
          ) : results.length === 0 && !isLoading ? (
            <div style={{ padding:'32px', textAlign:'center', color:'var(--text-3)', fontSize:13 }}>
              {t('global_search.no_results_for')} &quot;{debouncedQ}&quot;
            </div>
          ) : (
            Object.entries(grouped).filter(([, items]) => items?.length > 0).map(([type, items]) => (
              <div key={type}>
                <div style={{ padding:'8px 18px 4px', fontSize:11, fontWeight:500, color:'var(--text-3)', textTransform:'uppercase', letterSpacing:'.06em' }}>
                  {TYPE_LABELS[type] || type}s
                </div>
                {(items || []).map(item => {
                  const idx = resultCursor++
                  const isSelected = selectedIdx === idx
                  return (
                    <button key={item.id}
                      data-nav-item
                      style={{
                        display:'flex', gap:12, padding:'10px 18px', cursor:'pointer', alignItems:'center',
                        borderBottom:'.5px solid var(--surface-4)',
                        background: isSelected ? 'var(--accent-muted)' : 'transparent',
                        outline: 'none', width: '100%', textAlign: 'left', fontFamily: 'inherit',
                        border: 'none', borderBottom: '.5px solid var(--surface-4)',
                      }}
                      onMouseEnter={e => { if (!isSelected) e.currentTarget.style.background = 'var(--surface-2)' }}
                      onMouseLeave={e => { if (!isSelected) e.currentTarget.style.background = 'transparent' }}
                      onClick={() => { if (item.url) navigate(item.url); onClose() }}
                      type="button"
                    >
                      <span style={{ fontSize:16, flexShrink:0 }}>{ICON_MAP[item.type] || '•'}</span>
                      <div style={{ flex:1, minWidth:0 }}>
                        <div style={{ fontSize:13, fontWeight: isSelected ? 600 : 500, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap', color: isSelected ? 'var(--accent)' : 'var(--text-1)' }}>{item.title}</div>
                        {item.subtitle && <div style={{ fontSize:11, color:'var(--text-2)', marginTop:1 }}>{item.subtitle}</div>}
                      </div>
                      {item.status && (
                        <span style={{ fontSize:10, padding:'2px 6px', borderRadius:4, background:'var(--surface-2)', color:'var(--text-2)', whiteSpace:'nowrap' }}>{item.status}</span>
                      )}
                    </button>
                  )
                })}
              </div>
            ))
          )}
        </div>

        <div style={{ padding:'8px 18px', borderTop:'.5px solid var(--surface-4)', fontSize:11, color:'var(--text-3)', display:'flex', gap:16 }}>
          <span>{`↑↓ ${t('common.navigate')}`}</span><span>{`↵ ${t('common.open')}`}</span><span>{`Esc ${t('common.close').toLowerCase()}`}</span>
        </div>
      </div>
    </div>
  )
}
