import { useState, useMemo } from 'react'
import type { CSSProperties } from 'react'
import { openConfirmGlobal } from '../context/ConfirmContext'
import { extractErr } from '../utils/helpers'
import { useToast } from '../context/ToastContext'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ticketsApi } from '../services/api'
import { Button, Spinner, EmptyState } from '../components/ui'
import PageHeader from '../components/layout/PageHeader'
import PageShell from '../components/layout/PageShell'
import { MessageSquare } from 'lucide-react'
import { useAppT } from '../i18n/AppLangContext'

interface InternalComment {
  id: string | number
  content: string
  created_at?: string
}

interface TicketItem {
  id: string | number
  number?: string
  title?: string
  requester_name?: string
  status?: string
}

const _ps: CSSProperties = { background:'var(--surface-2)', border:'1px solid var(--surface-4)', borderRadius:12, padding:'20px 24px' }
const is: CSSProperties = { width:'100%', background:'var(--surface-3)', border:'1px solid var(--surface-4)', borderRadius:8, padding: '9px 13px', color:'var(--text-1)', fontSize: "var(--text-base)", outline:'none', fontFamily:'inherit', boxSizing:'border-box' }
const ls: CSSProperties = { fontSize: "var(--text-xs)", fontWeight:600, color:'var(--text-2)', textTransform:'uppercase', letterSpacing:'0.07em', display:'block', marginBottom:5 }

function InternalCommentThread({ ticketId }: { ticketId: string | number }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [content, setContent] = useState('')
  const [editing, setEditing] = useState<string | number | null>(null)
  const [editContent, setEditContent] = useState('')
  const t = useAppT()

  const { data: comments = [], isLoading } = useQuery<InternalComment[]>({
    queryKey: ['internal-comments', ticketId],
    queryFn: () => ticketsApi.internalComments(ticketId).then(r => r.data).catch(() => []),
    enabled: !!ticketId,
  })

  const { mutate: addComment, isPending: adding } = useMutation({
    mutationFn: () => ticketsApi.createInternalComment(ticketId, { content }).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['internal-comments', ticketId] }); setContent('') },
    onError: (e: unknown) => toast.error(extractErr(e, t('internal_comments.error_add'))),
  })

  const { mutate: updateComment, isPending: updating } = useMutation({
    mutationFn: ({ id, content: c }: { id: string | number; content: string }) => ticketsApi.updateInternalComment(ticketId, id, { content: c }).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['internal-comments', ticketId] }); setEditing(null) },
    onError: (e: unknown) => toast.error(extractErr(e, t('internal_comments.error_update'))),
  })

  const { mutate: deleteComment } = useMutation({
    mutationFn: (id: string | number) => ticketsApi.deleteInternalComment(ticketId, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['internal-comments', ticketId] }),
    onError: (e: unknown) => toast.error(extractErr(e, t('internal_comments.error_delete'))),
  })
  if (!ticketId) return (
    <div style={{textAlign:'center', padding:'40px 24px', color:'var(--text-3)', fontSize: "var(--text-base)"}}>
      {t('internal_comments.no_ticket_selected')}
    </div>
  )

  return (
    <div>
      {/* Banner "Solo visible para agentes" */}
      <div style={{padding:'10px 14px', background:'var(--warning-bg)', border:'1px solid var(--warning-border)',
        borderRadius:8, marginBottom:16, fontSize: "var(--text-sm)", color:'var(--warning)', display:'flex', gap:8, alignItems:'center'}}>
        <span>🔒</span>
        <span><strong>{t('internal_comments.banner_title')}</strong> — {t('internal_comments.banner_desc')}</span>
      </div>

      {isLoading ? <Spinner /> : (
        <div>
          {comments.length === 0 ? (
            <div style={{textAlign:'center', padding:'24px', color:'var(--text-3)', fontSize: "var(--text-base)"}}>
              {t('internal_comments.empty')}
            </div>
          ) : (
            <div style={{display:'flex', flexDirection:'column', gap:8, marginBottom:16}}>
              {comments.map((c, _i) => (
                <div key={c.id} style={{padding:'12px 16px', background:'var(--surface-1)',
                  borderRadius:8, border:'1px solid var(--warning-border)',
                  borderLeft:'3px solid var(--warning)'}}>
                  <div style={{display:'flex', justifyContent:'space-between', marginBottom:6}}>
                    <div style={{display:'flex', gap:8, alignItems:'center'}}>
                      <span style={{fontSize: "var(--text-xs)", padding:'2px 8px', borderRadius:20,
                        background:'var(--warning-bg)', color:'var(--warning)', fontWeight:600}}>🔒 INTERNO</span>
                      <span style={{fontSize: "var(--text-xs)", color:'var(--text-3)'}}>
                        {c.created_at ? new Date(c.created_at).toLocaleString('es-ES') : ''}
                      </span>
                    </div>
                    <div style={{display:'flex', gap:6}}>
                      <button onClick={() => { setEditing(c.id); setEditContent(c.content) }}
                        style={{background:'none',border:'none',color:'var(--text-2)',cursor:'pointer',fontSize: "var(--text-sm)"}}>✏ {t('internal_comments.edit')}</button>
                      <button onClick={() => { openConfirmGlobal({ message: t('internal_comments.confirm_delete'), onConfirm: () => deleteComment(c.id), danger: true }) }}
                        style={{background:'none',border:'none',color:'var(--danger)',cursor:'pointer',fontSize: "var(--text-sm)"}}>✕</button>
                    </div>
                  </div>
                  {editing === c.id ? (
                    <div>
                      <textarea value={editContent} onChange={e => setEditContent(e.target.value)}
                        rows={2} style={{...is, marginBottom:8, resize:'vertical'}} />
                      <div style={{display:'flex', gap:8}}>
                        <Button onClick={() => updateComment({id: c.id, content: editContent})} disabled={updating || !editContent.trim()}>
                          {updating ? t('internal_comments.saving') : t('internal_comments.save')}
                        </Button>
                        <Button variant="secondary" onClick={() => setEditing(null)}>{t('internal_comments.cancel')}</Button>
                      </div>
                    </div>
                  ) : (
                    <div style={{fontSize: "var(--text-base)", color:'var(--text-1)', lineHeight:1.6}}>{c.content}</div>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Nuevo comentario */}
          <div>
            <label style={ls}>{t('internal_comments.add_label')}</label>
            <textarea value={content} onChange={e => setContent(e.target.value)}
              placeholder="Escribe un comentario privado..."
              rows={3} style={{...is, marginBottom:8, resize:'vertical'}} />
            <Button onClick={() => addComment()} disabled={adding || !content.trim()}>
              {adding ? t('internal_comments.sending') : '🔒 ' + t('internal_comments.add_btn')}
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

export default function InternalCommentsPage(): JSX.Element {
  const t = useAppT()
  const [ticketId, setTicketId] = useState<string | number | ''>('')
  const [search, setSearch] = useState('')

  // Cargar tickets del SD para búsqueda
  const { data: ticketsData } = useQuery<TicketItem[]>({
    queryKey: ['sd-tickets', { page_size: 200 }],
    queryFn: () => ticketsApi.list({ page_size: 200 }).then(r => {
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

  const selectedTicket = tickets.find((t) => t.id === ticketId)

  const is: CSSProperties = { width: '100%', background: 'var(--surface-3)', border: '1px solid var(--surface-4)', borderRadius: 8, padding: '9px 13px', color: 'var(--text-1)', fontSize: "var(--text-base)", outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box' }
  const ps: CSSProperties = { background: 'var(--surface-2)', border: '1px solid var(--surface-4)', borderRadius: 12, padding: '20px 22px' }
  const ls: CSSProperties = { fontSize: "var(--text-xs)", fontWeight: 600, color: 'var(--text-2)', display: 'block', marginBottom: 5, textTransform: 'uppercase', letterSpacing: '0.06em' }

  return (
    <PageShell>
      <PageHeader icon={<MessageSquare size={18} />} title={t('internal_comments.title')} subtitle={t('internal_comments.subtitle')} showListExport={false} />

      <div style={{...ps, marginBottom:20}}>
        <div style={{display:'grid', gridTemplateColumns:'1fr', gap:12}}>
          <div>
            <label style={ls}>{t('internal_comments.search_label')}</label>
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder={t('internal_comments.search_placeholder')}
              style={is}
              autoFocus
            />
          </div>
          {search.length > 0 && filtered.length > 0 && !selectedTicket && (
            <div style={{ background: 'var(--surface-1)', border: '1px solid var(--surface-4)', borderRadius: 8, overflow: 'hidden', maxHeight: 280, overflowY: 'auto' }}>
              {filtered.map((t) => (
                <button key={t.id}
                  onClick={() => { setTicketId(t.id); setSearch(`${t.number} — ${t.title}`) }}
                  style={{ padding: '10px 14px', cursor: 'pointer', borderBottom: '1px solid var(--surface-4)',
                    display: 'flex', alignItems: 'center', gap: 10, width:'100%', textAlign:'left',
                    background:'transparent', borderLeft:'none', borderRight:'none', borderTop:'none', fontFamily:'inherit' }}
                  type="button"
                  onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-3)'}
                  onMouseLeave={e => e.currentTarget.style.background = 'transparent'}>
                  <span style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--accent)', minWidth: 80 }}>{t.number}</span>
                  <span style={{ fontSize: "var(--text-base)", color: 'var(--text-1)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{t.title}</span>
                  <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-3)', whiteSpace: 'nowrap' }}>{t.requester_name}</span>
                  <span style={{ fontSize: "var(--text-2xs)", background: 'var(--surface-4)', color: 'var(--text-2)', padding: '1px 6px', borderRadius: 4 }}>{t.status?.replace(/_/g,' ')}</span>
                </button>
              ))}
            </div>
          )}
          {search.length > 0 && filtered.length === 0 && (
            <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-3)', padding: '8px 0' }}>{t('internal_comments.no_tickets_found', { search })}</div>
          )}
          {selectedTicket && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px',
              background: 'var(--accent-muted)', border: '1px solid var(--accent-glow)', borderRadius: 8 }}>
              <span style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--accent)' }}>{selectedTicket.number}</span>
              <span style={{ fontSize: "var(--text-base)", color: 'var(--text-1)', flex: 1 }}>{selectedTicket.title}</span>
              <button onClick={() => { setTicketId(''); setSearch('') }}
                style={{ background: 'none', border: 'none', color: 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-lg)", lineHeight: 1 }}>×</button>
            </div>
          )}
        </div>
        <div style={{marginTop:12, fontSize: "var(--text-sm)", color:'var(--text-3)', lineHeight:1.7}}>
          Los comentarios internos son visibles <strong style={{color:'var(--warning)'}}>solo para el equipo de soporte</strong>.
          El cliente no los puede ver en el portal. Usa estas notas para coordinar internamente,
          escalar o registrar contexto técnico sensible.
        </div>
      </div>

      {/* Diferencia visual con comentarios normales */}
      <div style={{display:'grid', gridTemplateColumns:'1fr 1fr', gap:16, marginBottom:24}}>
        <div style={{...ps, padding:'14px 18px', border:'1px solid var(--surface-4)'}}>
          <div style={{fontSize: "var(--text-sm)", fontWeight:600, color:'var(--text-2)', marginBottom:8}}>💬 {t('internal_comments.normal_label')}</div>
          <div style={{fontSize: "var(--text-sm)", color:'var(--text-3)', lineHeight:1.7}}>
            {t('internal_comments.normal_desc')}
          </div>
        </div>
        <div style={{...ps, padding:'14px 18px', border:'1px solid var(--warning-border)', background:'var(--warning-bg)'}}>
          <div style={{fontSize: "var(--text-sm)", fontWeight:600, color:'var(--warning)', marginBottom:8}}>🔒 {t('internal_comments.internal_label')}</div>
          <div style={{fontSize: "var(--text-sm)", color:'var(--text-2)', lineHeight:1.7}}>
            {t('internal_comments.internal_desc')}
          </div>
        </div>
      </div>

      {ticketId && (
        <div style={ps}>
          <div style={{fontSize: "var(--text-base)", fontWeight:600, marginBottom:16}}>
            {t('internal_comments.thread_title')} — ticket <code style={{color:'var(--accent)', fontSize: "var(--text-sm)"}}>{String(ticketId).slice(0,8)}…</code>
          </div>
          <InternalCommentThread ticketId={ticketId} />
        </div>
      )}

      {!ticketId && (
        <EmptyState icon="🔒" title={t('internal_comments.empty_title')} description={t('internal_comments.empty_desc')} />
      )}
    </PageShell>
  )
}
