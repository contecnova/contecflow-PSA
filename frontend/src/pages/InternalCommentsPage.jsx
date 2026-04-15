import { useState, useMemo } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr } from '../utils/helpers'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../services/api'
import { Button, Spinner, EmptyState } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import { useAppT } from '../i18n/AppLangContext'

const _ps = { background:'var(--surface-2)', border:'1px solid #1e2d45', borderRadius:12, padding:'20px 24px' }
const is = { width:'100%', background:'var(--surface-3)', border:'1px solid #1e2d45', borderRadius:8, padding:'8px 12px', color:'var(--text-1)', fontSize:13, outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
const ls = { fontSize:11, fontWeight:600, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'0.07em', display:'block', marginBottom:5 }

function InternalCommentThread({ ticketId }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [content, setContent] = useState('')
  const [editing, setEditing] = useState(null)
  const [editContent, setEditContent] = useState('')

  const { data: comments = [], isLoading } = useQuery({
    queryKey: ['internal-comments', ticketId],
    queryFn: () => api.get(`/sd/tickets/${ticketId}/internal-comments`).then(r => r.data).catch(() => []),
    enabled: !!ticketId,
  })

  const { mutate: addComment, isPending: adding } = useMutation({
    mutationFn: () => api.post(`/sd/tickets/${ticketId}/internal-comments`, { content }).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries(['internal-comments', ticketId]); setContent('') },
    onError: e => toast.error(extractErr(e, 'Error al añadir comentario')),
  })

  const { mutate: updateComment, isPending: updating } = useMutation({
    mutationFn: ({ id, content: c }) => api.patch(`/sd/tickets/${ticketId}/internal-comments/${id}`, { content: c }).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries(['internal-comments', ticketId]); setEditing(null) },
    onError: e => toast.error(extractErr(e, 'Error al actualizar')),
  })

  const { mutate: deleteComment } = useMutation({
    mutationFn: id => api.delete(`/sd/tickets/${ticketId}/internal-comments/${id}`),
    onSuccess: () => qc.invalidateQueries(['internal-comments', ticketId]),
    onError: e => toast.error(extractErr(e, 'Error al eliminar')),
  })

  if (!ticketId) return (
    <div style={{textAlign:'center', padding:'40px 24px', color:'var(--text-3)', fontSize:13}}>
      Introduce el ID de un ticket para ver sus comentarios internos
    </div>
  )

  return (
    <div>
      {/* Banner "Solo visible para agentes" */}
      <div style={{padding:'10px 14px', background:'var(--warning-bg)', border:'1px solid #ffb80030',
        borderRadius:8, marginBottom:16, fontSize:12, color:'var(--warning)', display:'flex', gap:8, alignItems:'center'}}>
        <span>🔒</span>
        <span><strong>Comentarios internos</strong> — Solo visibles para el equipo de soporte. El cliente no puede verlos.</span>
      </div>

      {isLoading ? <Spinner /> : (
        <div>
          {comments.length === 0 ? (
            <div style={{textAlign:'center', padding:'24px', color:'var(--text-3)', fontSize:13}}>
              Sin comentarios internos en este ticket.
            </div>
          ) : (
            <div style={{display:'flex', flexDirection:'column', gap:8, marginBottom:16}}>
              {comments.map((c, _i) => (
                <div key={c.id} style={{padding:'12px 16px', background:'var(--surface-1)',
                  borderRadius:8, border:'1px solid #ffb80020',
                  borderLeft:'3px solid #ffb800'}}>
                  <div style={{display:'flex', justifyContent:'space-between', marginBottom:6}}>
                    <div style={{display:'flex', gap:8, alignItems:'center'}}>
                      <span style={{fontSize:11, padding:'2px 8px', borderRadius:20,
                        background:'var(--warning-bg)', color:'var(--warning)', fontWeight:600}}>🔒 INTERNO</span>
                      <span style={{fontSize:11, color:'var(--text-3)'}}>
                        {c.created_at ? new Date(c.created_at).toLocaleString('es-ES') : ''}
                      </span>
                    </div>
                    <div style={{display:'flex', gap:6}}>
                      <button onClick={() => { setEditing(c.id); setEditContent(c.content) }}
                        style={{background:'none',border:'none',color:'var(--text-2)',cursor:'pointer',fontSize:12}}>✏ Editar</button>
                      <button onClick={() => { openConfirmGlobal({ message: '¿Eliminar este comentario interno?', onConfirm: () => deleteComment(c.id), danger: true }) }}
                        style={{background:'none',border:'none',color:'var(--danger)',cursor:'pointer',fontSize:12}}>✕</button>
                    </div>
                  </div>
                  {editing === c.id ? (
                    <div>
                      <textarea value={editContent} onChange={e => setEditContent(e.target.value)}
                        rows={2} style={{...is, marginBottom:8, resize:'vertical'}} />
                      <div style={{display:'flex', gap:8}}>
                        <Button onClick={() => updateComment({id: c.id, content: editContent})} disabled={updating || !editContent.trim()}>
                          {updating ? '...' : 'Guardar'}
                        </Button>
                        <Button variant="secondary" onClick={() => setEditing(null)}>Cancelar</Button>
                      </div>
                    </div>
                  ) : (
                    <div style={{fontSize:13, color:'var(--text-1)', lineHeight:1.6}}>{c.content}</div>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Nuevo comentario */}
          <div>
            <label style={ls}>Añadir nota interna</label>
            <textarea value={content} onChange={e => setContent(e.target.value)}
              placeholder="Nota visible solo para el equipo de soporte..."
              rows={3} style={{...is, marginBottom:8, resize:'vertical'}} />
            <Button onClick={() => addComment()} disabled={adding || !content.trim()}>
              {adding ? 'Enviando...' : '🔒 Añadir nota interna'}
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

export default function InternalCommentsPage() {
  const t = useAppT()
  const [ticketId, setTicketId] = useState('')
  const [search, setSearch] = useState('')

  // Cargar tickets del SD para búsqueda
  const { data: ticketsData } = useQuery({
    queryKey: ['sd-tickets', { page_size: 200 }],
    queryFn: () => api.get('/sd/tickets', { params: { page_size: 200 } }).then(r => {
      const d = r.data
      return Array.isArray(d) ? d : (d?.tickets || d?.items || [])
    }),
    staleTime: 60000,
  })
  const tickets = useMemo(() => ticketsData || [], [ticketsData])

  const filtered = useMemo(() => {
    if (!search.trim()) return tickets.slice(0, 20)
    const q = search.toLowerCase()
    return tickets.filter(t =>
      t.number?.toLowerCase().includes(q) ||
      t.title?.toLowerCase().includes(q) ||
      t.requester_name?.toLowerCase().includes(q)
    ).slice(0, 15)
  }, [tickets, search])

  const selectedTicket = tickets.find(t => t.id === ticketId)

  const is = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: 13, outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
  const ps = { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, padding: '20px 22px' }
  const ls = { fontSize: 11, fontWeight: 600, color: 'var(--text-2)', display: 'block', marginBottom: 5, textTransform: 'uppercase', letterSpacing: '0.06em' }

  return (
    <div style={{padding:32}}>
      <PageHeader title={t('internal_comments.title')} subtitle={t('internal_comments.subtitle')} />

      <div style={{...ps, marginBottom:20}}>
        <div style={{display:'grid', gridTemplateColumns:'1fr', gap:12}}>
          <div>
            <label style={ls}>Buscar ticket</label>
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Buscar por número, título o solicitante..."
              style={is}
              autoFocus
            />
          </div>
          {search.length > 0 && filtered.length > 0 && !selectedTicket && (
            <div style={{ background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 8, overflow: 'hidden', maxHeight: 280, overflowY: 'auto' }}>
              {filtered.map(t => (
                <div key={t.id}
                  onClick={() => { setTicketId(t.id); setSearch(`${t.number} — ${t.title}`) }}
                  style={{ padding: '10px 14px', cursor: 'pointer', borderBottom: '1px solid var(--surface-4)',
                    display: 'flex', alignItems: 'center', gap: 10 }}
                  onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-3)'}
                  onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
                  <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--accent)', minWidth: 80 }}>{t.number}</span>
                  <span style={{ fontSize: 13, color: 'var(--text-1)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{t.title}</span>
                  <span style={{ fontSize: 11, color: 'var(--text-3)', whiteSpace: 'nowrap' }}>{t.requester_name}</span>
                  <span style={{ fontSize: 10, background: 'var(--surface-4)', color: 'var(--text-2)', padding: '1px 6px', borderRadius: 4 }}>{t.status?.replace(/_/g,' ')}</span>
                </div>
              ))}
            </div>
          )}
          {search.length > 0 && filtered.length === 0 && (
            <div style={{ fontSize: 12, color: 'var(--text-3)', padding: '8px 0' }}>No se encontraron tickets con &quot;{search}&quot;</div>
          )}
          {selectedTicket && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px',
              background: 'var(--accent-muted)', border: '1px solid var(--accent-glow)', borderRadius: 8 }}>
              <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--accent)' }}>{selectedTicket.number}</span>
              <span style={{ fontSize: 13, color: 'var(--text-1)', flex: 1 }}>{selectedTicket.title}</span>
              <button onClick={() => { setTicketId(''); setSearch('') }}
                style={{ background: 'none', border: 'none', color: 'var(--text-2)', cursor: 'pointer', fontSize: 16, lineHeight: 1 }}>×</button>
            </div>
          )}
        </div>
        <div style={{marginTop:12, fontSize:12, color:'var(--text-3)', lineHeight:1.7}}>
          Los comentarios internos son visibles <strong style={{color:'var(--warning)'}}>solo para el equipo de soporte</strong>.
          El cliente no los puede ver en el portal. Usa estas notas para coordinar internamente,
          escalar o registrar contexto técnico sensible.
        </div>
      </div>

      {/* Diferencia visual con comentarios normales */}
      <div style={{display:'grid', gridTemplateColumns:'1fr 1fr', gap:16, marginBottom:24}}>
        <div style={{...ps, padding:'14px 18px', border:'1px solid #1a2640'}}>
          <div style={{fontSize:12, fontWeight:600, color:'var(--text-2)', marginBottom:8}}>💬 Comentario normal</div>
          <div style={{fontSize:12, color:'var(--text-3)', lineHeight:1.7}}>
            Visible para el agente <strong style={{color:'var(--text-1)'}}>Y para el cliente</strong> en el portal.
            Se usa para actualizar al cliente del estado.
          </div>
        </div>
        <div style={{...ps, padding:'14px 18px', border:'1px solid #ffb80030', background:'var(--warning-bg)'}}>
          <div style={{fontSize:12, fontWeight:600, color:'var(--warning)', marginBottom:8}}>🔒 Comentario interno</div>
          <div style={{fontSize:12, color:'var(--text-2)', lineHeight:1.7}}>
            Visible <strong style={{color:'var(--warning)'}}>solo para el equipo</strong>.
            El cliente nunca lo ve. Ideal para escalar, notas técnicas o coordinación interna.
          </div>
        </div>
      </div>

      {ticketId && (
        <div style={ps}>
          <div style={{fontSize:13, fontWeight:600, marginBottom:16}}>
            Comentarios internos — ticket <code style={{color:'var(--accent)', fontSize:12}}>{ticketId.slice(0,8)}…</code>
          </div>
          <InternalCommentThread ticketId={ticketId} />
        </div>
      )}

      {!ticketId && (
        <EmptyState icon="🔒" title="Introduce un ID de ticket" description="Los comentarios internos se muestran por ticket" />
      )}
    </div>
  )
}
