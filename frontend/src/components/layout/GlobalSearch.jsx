/**
 * GlobalSearch — Cmd+K search palette
 */
import { useState, useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import api from '../../services/api'

const ICON_MAP = { project:'⬡', task:'▦', ticket:'🎫', user:'👤', invoice:'🧾', opportunity:'🎪' }
const TYPE_LABELS = { project:'Proyecto', task:'Tarea', ticket:'Ticket', user:'Usuario', invoice:'Factura', opportunity:'Oportunidad' }

export default function GlobalSearch({ onClose }) {
  const [q, setQ] = useState('')
  const [debouncedQ, setDebouncedQ] = useState('')
  const inputRef = useRef(null)

  useEffect(() => { inputRef.current?.focus() }, [])
  useEffect(() => {
    const t = setTimeout(() => setDebouncedQ(q), 250)
    return () => clearTimeout(t)
  }, [q])

  const { data, isLoading } = useQuery({
    queryKey: ['global-search', debouncedQ],
    queryFn: () => api.get('/global-search', { params: { q: debouncedQ } }).then(r => r.data),
    enabled: debouncedQ.length >= 2,
  })

  const results = data?.flat || []
  const grouped = data?.grouped || {}

  return (
    <div style={{ position:'fixed', top:0, left:0, right:0, bottom:0, background:'rgba(0,0,0,0.5)', zIndex:9999, display:'flex', alignItems:'flex-start', justifyContent:'center', paddingTop:'15vh' }}
      onClick={onClose}>
      <div style={{ width:'100%', maxWidth:620, background:'var(--color-background-primary)', borderRadius:16, border:'.5px solid var(--color-border-secondary)', overflow:'hidden', boxShadow:'0 20px 60px rgba(0,0,0,0.3)' }}
        onClick={e => e.stopPropagation()}>
        <div style={{ display:'flex', alignItems:'center', padding:'14px 18px', borderBottom:'.5px solid var(--color-border-tertiary)', gap:10 }}>
          <span style={{ fontSize:16, color:'var(--color-text-secondary)' }}>⌕</span>
          <input
            ref={inputRef}
            value={q}
            onChange={e => setQ(e.target.value)}
            placeholder="Buscar proyectos, tareas, tickets, usuarios..."
            style={{ flex:1, background:'transparent', border:'none', outline:'none', fontSize:15, color:'var(--color-text-primary)', fontFamily:'inherit' }}
            onKeyDown={e => { if(e.key === 'Escape') onClose() }}
          />
          {isLoading && <span style={{ fontSize:12, color:'var(--color-text-tertiary)' }}>Buscando...</span>}
          <button onClick={onClose} style={{ background:'transparent', border:'.5px solid var(--color-border-tertiary)', borderRadius:6, padding:'3px 8px', fontSize:11, color:'var(--color-text-secondary)', cursor:'pointer', fontFamily:'inherit' }}>Esc</button>
        </div>

        <div style={{ maxHeight:450, overflowY:'auto' }}>
          {debouncedQ.length < 2 ? (
            <div style={{ padding:'32px', textAlign:'center', color:'var(--color-text-tertiary)', fontSize:13 }}>
              Escribe al menos 2 caracteres para buscar
            </div>
          ) : results.length === 0 && !isLoading ? (
            <div style={{ padding:'32px', textAlign:'center', color:'var(--color-text-tertiary)', fontSize:13 }}>
              Sin resultados para &quot;{debouncedQ}&quot;
            </div>
          ) : (
            Object.entries(grouped).filter(([, items]) => items?.length > 0).map(([type, items]) => (
              <div key={type}>
                <div style={{ padding:'8px 18px 4px', fontSize:11, fontWeight:500, color:'var(--color-text-tertiary)', textTransform:'uppercase', letterSpacing:'.06em' }}>
                  {TYPE_LABELS[type] || type}s
                </div>
                {(items || []).map(item => (
                  <div key={item.id}
                    style={{ display:'flex', gap:12, padding:'10px 18px', cursor:'pointer', alignItems:'center', borderBottom:'.5px solid var(--color-border-tertiary)' }}
                    onMouseEnter={e => e.currentTarget.style.background = 'var(--color-background-secondary)'}
                    onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                    onClick={() => { window.location.hash = item.url || '#'; onClose() }}
                  >
                    <span style={{ fontSize:16, flexShrink:0 }}>{ICON_MAP[item.type] || '•'}</span>
                    <div style={{ flex:1, minWidth:0 }}>
                      <div style={{ fontSize:13, fontWeight:500, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{item.title}</div>
                      {item.subtitle && <div style={{ fontSize:11, color:'var(--color-text-secondary)', marginTop:1 }}>{item.subtitle}</div>}
                    </div>
                    {item.status && (
                      <span style={{ fontSize:10, padding:'2px 6px', borderRadius:4, background:'var(--color-background-secondary)', color:'var(--color-text-secondary)', whiteSpace:'nowrap' }}>{item.status}</span>
                    )}
                  </div>
                ))}
              </div>
            ))
          )}
        </div>

        <div style={{ padding:'8px 18px', borderTop:'.5px solid var(--color-border-tertiary)', fontSize:11, color:'var(--color-text-tertiary)', display:'flex', gap:16 }}>
          <span>↑↓ navegar</span><span>↵ abrir</span><span>Esc cerrar</span>
        </div>
      </div>
    </div>
  )
}
