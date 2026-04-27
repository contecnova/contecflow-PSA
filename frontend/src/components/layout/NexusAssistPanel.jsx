import { useState, useRef, useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import api from '../../services/api'

const LAST_CONV_KEY = 'nexusassist_last_conversation_id'

const SUGGESTIONS = [
  '¿Cuáles son los proyectos con más riesgo esta semana?',
  '¿Qué tickets llevan más de 24h sin respuesta?',
  'Resume el estado del equipo esta semana',
  '¿Cuántas horas se han imputado en los últimos 7 días?',
]

export default function ContecflowAssistPanel({ open, onClose, context }) {
  // Derive human-readable page label from path
  const PAGE_LABELS = {
    '/': 'Dashboard', '/projects': 'Proyectos', '/tasks': 'Tareas',
    '/timesheets': 'Imputaciones', '/resources': 'Recursos', '/clients': 'Clientes',
    '/pipeline': 'Pipeline', '/expenses': 'Gastos', '/documents': 'Documentos',
    '/service-desk': 'Service Desk', '/risks': 'Riesgos', '/okrs': 'OKRs',
    '/analytics': 'Analytics', '/reports': 'Informes', '/capacity': 'Capacidad',
    '/settings': 'Ajustes',
  }
  const pageLabel = context?.page
    ? (Object.entries(PAGE_LABELS).find(([k]) => context.page === k || context.page.startsWith(k + '/'))?.[1] || context.page)
    : null
  const qc = useQueryClient()
  const [convId, setConvId]   = useState(null)
  const [input, setInput]     = useState('')
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)
  const [restoredOnce, setRestoredOnce] = useState(false)
  const bottomRef = useRef(null)

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  const { data: conversations = [] } = useQuery({
    queryKey: ['ai-conversations'],
    queryFn: () => api.get('/ai/conversations').then(r => r.data),
    enabled: open,
  })

  useEffect(() => {
    if (convId) {
      localStorage.setItem(LAST_CONV_KEY, convId)
    }
  }, [convId])

  useEffect(() => {
    if (!open) {
      setRestoredOnce(false)
      return
    }
    if (restoredOnce || convId || messages.length > 0) return

    const storedId = localStorage.getItem(LAST_CONV_KEY)
    if (!storedId) {
      setRestoredOnce(true)
      return
    }

    const exists = conversations.some(c => c.id === storedId)
    if (!exists && conversations.length > 0) {
      localStorage.removeItem(LAST_CONV_KEY)
      setRestoredOnce(true)
      return
    }

    if (!exists && conversations.length === 0) return

    const restore = async () => {
      try {
        const { data } = await api.get(`/ai/conversations/${storedId}`)
        setConvId(storedId)
        setMessages(data.messages || [])
      } catch {
        localStorage.removeItem(LAST_CONV_KEY)
      } finally {
        setRestoredOnce(true)
      }
    }

    restore()
  }, [open, restoredOnce, convId, messages.length, conversations])

  const sendMessage = async (text) => {
    if (!text.trim() || loading) return
    const userText = text.trim(); setInput(''); setLoading(true)
    setMessages(prev => [...prev, { role: 'user', content: userText }])
    try {
      const { data } = await api.post('/ai/chat', { message: userText, conversation_id: convId, context: context || undefined })
      setConvId(data.conversation_id)
      setMessages(prev => [...prev, { role: 'assistant', content: data.message }])
      qc.invalidateQueries(['ai-conversations'])
    } catch {
      setMessages(prev => [...prev, { role: 'assistant', content: '⚠ Error de conexión con NexusAssist.' }])
    }
    setLoading(false)
  }

  const loadConv = async (id) => {
    const { data } = await api.get(`/ai/conversations/${id}`)
    setConvId(id); setMessages(data.messages || [])
  }

  if (!open) return null
  return (
    <div style={{ position:'fixed', top:0, right:0, bottom:0, width:420, zIndex:1000,
      background:'var(--surface-1)', borderLeft:'.5px solid var(--surface-4)',
      display:'flex', flexDirection:'column', boxShadow:'-4px 0 24px rgba(0,0,0,0.18)' }}>
      <div style={{ padding:'16px 20px', borderBottom:'.5px solid var(--surface-4)',
        background:'var(--surface-2)', display:'flex', justifyContent:'space-between', alignItems:'center' }}>
        <div style={{ display:'flex', gap:10, alignItems:'center' }}>
          <span style={{ fontSize:22 }}>🤖</span>
          <div>
            <div style={{ fontSize:14, fontWeight:600 }}>NexusAssist</div>
            <div style={{ fontSize:11, color:'var(--text-2)' }}>Asistente IA</div>
          </div>
        </div>
        {pageLabel && (
          <div style={{ fontSize:10, padding:'2px 8px', borderRadius:10,
            background:'rgba(79,142,247,0.12)', color:'var(--accent)',
            border:'.5px solid rgba(79,142,247,0.25)', whiteSpace:'nowrap', flexShrink:0 }}>
            📍 {pageLabel}
          </div>
        )}
        <div style={{ display:'flex', gap:8 }}>
          <button onClick={() => { localStorage.removeItem(LAST_CONV_KEY); setConvId(null); setMessages([]) }}
            style={{ background:'transparent', border:'.5px solid var(--surface-4)', borderRadius:6,
              padding:'4px 10px', color:'var(--text-2)', cursor:'pointer', fontSize:12, fontFamily:'inherit' }}>
            + Nueva
          </button>
          <button onClick={onClose} style={{ background:'transparent', border:'none', fontSize:18, cursor:'pointer', color:'var(--text-2)', padding:'2px 6px' }}>✕</button>
        </div>
      </div>
      {!convId && messages.length === 0 && conversations.length > 0 && (
        <div style={{ padding:'12px 16px', borderBottom:'.5px solid var(--surface-4)', maxHeight:180, overflowY:'auto' }}>
          <div style={{ fontSize:11, fontWeight:500, color:'var(--text-2)', marginBottom:8 }}>Recientes</div>
          {conversations.slice(0,5).map(c => (
            <button key={c.id} onClick={() => loadConv(c.id)}
              type="button"
              style={{ padding:'7px 10px', borderRadius:7, cursor:'pointer', marginBottom:4,
                background:'var(--surface-2)', fontSize:12,
                border:'.5px solid var(--surface-4)', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap',
                width:'100%', textAlign:'left', color:'var(--text-2)', fontFamily:'inherit' }}>
              {c.title}
            </button>
          ))}
        </div>
      )}
      <div style={{ flex:1, overflowY:'auto', padding:'16px 18px', display:'flex', flexDirection:'column', gap:12 }}>
        {messages.length === 0 && (
          <div>
            <div style={{ fontSize:13, color:'var(--text-2)', marginBottom:16, textAlign:'center', paddingTop:20 }}>¿En qué puedo ayudarte hoy?</div>
            {SUGGESTIONS.map((s, i) => (
              <button key={i} onClick={() => sendMessage(s)}
                type="button"
                style={{ padding:'10px 14px', borderRadius:10, border:'.5px solid var(--surface-4)',
                  cursor:'pointer', marginBottom:8, fontSize:12, color:'var(--text-2)',
                  background:'var(--surface-2)', width:'100%', textAlign:'left', fontFamily:'inherit' }}>
                {s}
              </button>
            ))}
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} style={{ display:'flex', justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start' }}>
            <div style={{ maxWidth:'85%', padding:'10px 14px',
              borderRadius: m.role === 'user' ? '16px 16px 4px 16px' : '4px 16px 16px 16px',
              background: m.role === 'user' ? 'var(--accent-muted)' : 'var(--surface-2)',
              border: `.5px solid ${m.role === 'user' ? 'rgba(0,212,255,0.25)' : 'var(--surface-4)'}`,
              fontSize:13, lineHeight:1.55, whiteSpace:'pre-wrap' }}>
              {m.content}
            </div>
          </div>
        ))}
        {loading && (
          <div style={{ display:'flex', gap:6, padding:'12px 14px',
            background:'var(--surface-2)', borderRadius:'4px 16px 16px 16px',
            width:'fit-content', border:'.5px solid var(--surface-4)' }}>
            {[0,1,2].map(i => (
              <div key={i} style={{ width:8, height:8, borderRadius:'50%', background:'var(--text-3)',
                animation:`bounce ${1.4}s ease-in-out ${i*0.2}s infinite` }} />
            ))}
          </div>
        )}
        <div ref={bottomRef} />
      </div>
      <div style={{ padding:'14px 18px', borderTop:'.5px solid var(--surface-4)', background:'var(--surface-2)' }}>
        <div style={{ display:'flex', gap:10, alignItems:'flex-end' }}>
          <textarea value={input} onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(input) } }}
            placeholder="Escribe aquí..." rows={2}
            style={{ flex:1, background:'var(--surface-1)', border:'.5px solid var(--surface-4)',
              borderRadius:10, padding:'10px 14px', fontSize:13, outline:'none', fontFamily:'inherit', resize:'none', lineHeight:1.4 }} />
          <button onClick={() => sendMessage(input)} disabled={!input.trim() || loading}
            style={{ padding:'10px 16px', borderRadius:10, background:'var(--accent)',
              border:'none', color:'white', cursor:'pointer', fontSize:18,
              opacity: !input.trim() || loading ? 0.5 : 1 }}>↑</button>
        </div>
        <div style={{ fontSize:10, color:'var(--text-3)', marginTop:5, textAlign:'center' }}>Enter enviar · Shift+Enter nueva línea</div>
      </div>
      <style>{`@keyframes bounce{0%,80%,100%{transform:scale(0)}40%{transform:scale(1)}}`}</style>
    </div>
  )
}
