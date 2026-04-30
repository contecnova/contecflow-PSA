import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useToast } from '../../context/ToastContext'
import { extractErr } from '../../utils/helpers'
import { CHART } from '../../constants/theme'
import { CLIENT_API, useLang, useClientAuth, S } from './portalClientContext'

export function PortalSupportDesk() {
  const t = useLang()
  const { _client } = useClientAuth()
  const toast = useToast()
  const qc = useQueryClient()
  const [_view, _setView] = useState('list')
  const [selectedId, setSelectedId] = useState(null)
  const [showCreate, setShowCreate] = useState(false)
  const [searchKB, setSearchKB] = useState('')
  const [tab, setTab] = useState('tickets')

  const { data: tickets = [], isLoading: _isLoading } = useQuery({
    queryKey: ['portal-sd-tickets'],
    queryFn: () => CLIENT_API.get('/sd/tickets/client/my').then(r => r.data),
  })
  const { data: catalog = [] } = useQuery({
    queryKey: ['portal-sd-catalog'],
    queryFn: () => CLIENT_API.get('/sd/catalog?public_only=true').then(r => r.data),
  })
  const { data: kbArticles = [] } = useQuery({
    queryKey: ['portal-kb', searchKB],
    queryFn: () => CLIENT_API.get('/sd/kb', { params: { public_only: true, search: searchKB || undefined } }).then(r => r.data),
  })
  const { data: announcements = [] } = useQuery({
    queryKey: ['portal-sd-anns'],
    queryFn: () => CLIENT_API.get('/sd/announcements').then(r => r.data),
  })
  const { data: ticketDetail } = useQuery({
    queryKey: ['portal-sd-ticket', selectedId],
    queryFn: () => CLIENT_API.get(`/sd/tickets/client/${selectedId}`).then(r => r.data),
    enabled: !!selectedId,
  })

  const { mutate: createTicket } = useMutation({
    mutationFn: d => CLIENT_API.post('/sd/tickets/client', d),
    onSuccess: () => { qc.invalidateQueries(['portal-sd-tickets']); setShowCreate(false) },
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: addComment } = useMutation({
    mutationFn: d => CLIENT_API.post(`/sd/tickets/${selectedId}/comments/client`, d),
    onSuccess: () => qc.invalidateQueries(['portal-sd-ticket', selectedId]),
    onError: e => toast.error(extractErr(e, 'Error')),
  })
  const { mutate: submitCSAT } = useMutation({
    mutationFn: d => CLIENT_API.post(`/sd/tickets/${selectedId}/csat`, d),
    onSuccess: () => qc.invalidateQueries(['portal-sd-ticket', selectedId]),
    onError: e => toast.error(extractErr(e, 'Error')),
  })

  const [newComment, setNewComment] = useState('')
  const [createForm, setCreateForm] = useState({ title: '', description: '', ticket_type: 'incident', urgency: 'medium', impact: 'user', service_item_id: '' })

  const PRIORITY_COLORS = { p1_critical: 'var(--danger)', p2_high: CHART.orange, p3_medium: 'var(--warning)', p4_low: 'var(--success)' }
  const STATUS_LABELS = { new: t('ticket_status_new'), assigned: t('ticket_status_assigned'), in_progress: t('ticket_status_in_progress'), pending_client: t('ticket_status_pending_client'), pending_third: t('no_data'), resolved: t('ticket_status_resolved'), closed: t('ticket_status_closed'), cancelled: t('cancel') }
  const STATUS_COLORS = { new: 'var(--text-2)', assigned: 'var(--accent)', in_progress: 'var(--purple)', pending_client: 'var(--warning)', resolved: 'var(--success)', closed: 'var(--text-3)' }
  const TYPE_ICONS = { incident: '🔥', service_request: '📋', change: '🔀', question: '❓' }

  const pendingClientTickets = tickets.filter(tk => tk.status === 'pending_client').length

  return (
    <div>
      {/* Active announcements */}
      {announcements.filter(a => a.show_to_clients).map(a => (
        <div key={a.id} style={{ background: a.type === 'outage' ? 'var(--danger-bg)' : 'var(--accent-muted)', border: `1px solid ${a.type === 'outage' ? 'var(--danger-border)' : 'var(--accent-glow)'}`, borderRadius: 10, padding: '10px 16px', marginBottom: 16, display: 'flex', gap: 10, alignItems: 'center', fontSize: "var(--text-base)" }}>
          <span style={{ fontSize: "var(--text-lg-em)" }}>{a.type === 'outage' ? '🚨' : a.type === 'maintenance' ? '🔧' : 'ℹ️'}</span>
          <div>
            <div style={{ fontWeight: 700 }}>{a.title}</div>
            <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>{a.body}</div>
          </div>
        </div>
      ))}

      {pendingClientTickets > 0 && (
        <div role="button" tabIndex={0} aria-label={t('support_pending_hint')} style={{ background: 'var(--warning-bg)', border: '2px solid var(--warning-border)', borderRadius: 10, padding: '12px 16px', marginBottom: 20, display: 'flex', gap: 12, alignItems: 'center', cursor: 'pointer' }} onClick={() => setTab('tickets')} onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setTab('tickets') } }}>
          <span style={{ fontSize: "var(--text-xl)" }}>⏳</span>
          <div>
            <div style={{ fontSize: "var(--text-base)", fontWeight: 700, color: 'var(--warning)' }}>{pendingClientTickets} {t('support_pending_count')}</div>
            <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>{t('support_pending_hint')}</div>
          </div>
        </div>
      )}

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <div role="tablist" aria-label={t('nav_support')} style={{ display: 'flex', gap: 8 }}>
          {[[`tickets`, `${t('support_tab_tickets')} (${tickets.length})`], ['kb', t('support_tab_kb')], ['announcements', `${t('support_tab_ann')} (${announcements.length})`]].map(([tabId, l]) => (
            <button key={tabId} role="tab" aria-selected={tab === tabId} aria-controls={`portal-support-panel-${tabId}`} id={`portal-support-tab-${tabId}`} onClick={() => setTab(tabId)}
              style={{ padding: '7px 14px', borderRadius: 8, border: `1px solid ${tab === tabId ? 'var(--accent)' : 'var(--surface-4)'}`, background: tab === tabId ? 'var(--accent-muted)' : 'transparent', color: tab === tabId ? 'var(--accent)' : 'var(--text-2)', fontSize: "var(--text-sm)", fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>
              {l}
            </button>
          ))}
        </div>
        {tab === 'tickets' && !selectedId && (
          <button onClick={() => setShowCreate(true)} style={{ background: 'linear-gradient(135deg, var(--accent), var(--purple))', border: 'none', borderRadius: 8, padding: '10px 18px', color: '#fff', fontSize: "var(--text-base)", fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit' }}>
            {t('support_open_ticket_btn')}
          </button>
        )}
      </div>

      {/* Tickets tab */}
      {tab === 'tickets' && !selectedId && (
        <div id="portal-support-panel-tickets" role="tabpanel" aria-labelledby="portal-support-tab-tickets">
          {tickets.length === 0 ? (
            <div style={{ ...S.card, textAlign: 'center', padding: '40px 20px', color: 'var(--text-2)' }}>
              <div style={{ fontSize: "var(--text-5xl)", marginBottom: 12 }}>🎫</div>
              <div style={{ fontSize: "var(--text-lg)", fontWeight: 600 }}>{t('support_empty')}</div>
              <p style={{ margin: '8px 0 16px' }}>¿Tienes algún problema o necesitas ayuda? Abre un ticket y el equipo te atenderá.</p>
              <button onClick={() => setShowCreate(true)} style={{ background: 'linear-gradient(135deg, var(--accent), var(--purple))', border: 'none', borderRadius: 8, padding: '10px 20px', color: '#fff', fontSize: "var(--text-base)", fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit' }}>{t('ticket_submit')}</button>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {tickets.map(tk => {
                const stColor = STATUS_COLORS[tk.status] || 'var(--text-2)'
                const prColor = PRIORITY_COLORS[tk.priority] || 'var(--text-2)'
                return (
                  <div key={tk.id} role="button" tabIndex={0} onClick={() => setSelectedId(tk.id)} onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSelectedId(tk.id) } }} aria-label={`Abrir ticket ${tk.number} ${tk.title}`}
                    style={{ ...S.card, cursor: 'pointer', border: `1px solid ${tk.status === 'pending_client' ? 'rgba(245,158,11,0.31)' : 'var(--surface-4)'}`, transition: 'all 0.15s' }}
                    onMouseEnter={e => e.currentTarget.style.borderColor = 'var(--accent-glow)'}
                    onMouseLeave={e => e.currentTarget.style.borderColor = tk.status === 'pending_client' ? 'rgba(245,158,11,0.31)' : 'var(--surface-4)'}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                      <div style={{ flex: 1 }}>
                        <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 4 }}>
                          <span style={{ fontSize: "var(--text-xs)", fontFamily: 'var(--font-mono)', color: 'var(--text-2)' }}>{tk.number}</span>
                          <span style={{ fontSize: "var(--text-sm)" }}>{TYPE_ICONS[tk.ticket_type]}</span>
                          <span style={{ fontSize: "var(--text-md)", fontWeight: 700 }}>{tk.title}</span>
                        </div>
                        <div style={{ display: 'flex', gap: 14, fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>
                          <span>{t('created')}: {tk.created_at}</span>
                          {tk.assigned_to_name && <span>{t('assigned_to')}: {tk.assigned_to_name}</span>}
                        </div>
                      </div>
                      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                        <span style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: prColor, background: prColor + '15', border: `1px solid ${prColor}30`, borderRadius: 20, padding: '2px 8px' }}>{tk.priority_label}</span>
                        <span style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: stColor, background: stColor + '15', border: `1px solid ${stColor}30`, borderRadius: 20, padding: '2px 8px' }}>{STATUS_LABELS[tk.status] || tk.status_label || tk.status}</span>
                      </div>
                    </div>
                    {tk.status === 'pending_client' && (
                      <div style={{ marginTop: 8, padding: '6px 10px', background: 'var(--warning-bg)', borderRadius: 6, fontSize: "var(--text-sm)", color: 'var(--warning)', fontWeight: 600 }}>
                        ⏳ {t('ticket_status_pending_client')} — haz clic para responder
                      </div>
                    )}
                    {tk.csat_requested_at && !tk.csat_score && (
                      <div style={{ marginTop: 8, padding: '6px 10px', background: 'var(--success-bg)', borderRadius: 6, fontSize: "var(--text-sm)", color: 'var(--success)', fontWeight: 600 }}>
                        ⭐ {t('ticket_rate_prompt')}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* Ticket detail */}
      {tab === 'tickets' && selectedId && (
        !ticketDetail ? (
          <div style={{ textAlign: 'center', padding: 60, color: 'var(--text-2)' }}>
            <div style={{ fontSize: "var(--text-3xl-em)", marginBottom: 12, animation: 'spin 1s linear infinite' }}>⟳</div>
            <div>{t('loading')}</div>
          </div>
        ) : (
          <div>
            <button onClick={() => setSelectedId(null)} style={{ ...S.btnSec, marginBottom: 20 }}>← Volver a mis tickets</button>
          <div style={{ marginBottom: 20 }}>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8, flexWrap: 'wrap' }}>
              <span style={{ fontSize: "var(--text-xs)", fontFamily: 'var(--font-mono)', color: 'var(--text-2)' }}>{ticketDetail.number}</span>
              <span style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: STATUS_COLORS[ticketDetail.status] || 'var(--text-2)', background: (STATUS_COLORS[ticketDetail.status] || 'var(--text-2)') + '15', border: `1px solid ${(STATUS_COLORS[ticketDetail.status] || 'var(--text-2)')}30`, borderRadius: 20, padding: '2px 8px' }}>
                {STATUS_LABELS[ticketDetail.status] || ticketDetail.status}
              </span>
              <span style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: PRIORITY_COLORS[ticketDetail.priority] || 'var(--text-2)' }}>{ticketDetail.priority_label}</span>
            </div>
            <h3 style={{ fontSize: "var(--text-lg-em)", fontWeight: 800, margin: '0 0 6px' }}>{ticketDetail.title}</h3>
            {ticketDetail.assigned_to_name && <div style={{ fontSize: "var(--text-base)", color: 'var(--text-2)' }}>Agente asignado: <span style={{ color: 'var(--text-1)' }}>{ticketDetail.assigned_to_name}</span></div>}
            {ticketDetail.sla_resolution_due && (
              <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginTop: 4 }}>Resolución estimada antes de: {ticketDetail.sla_resolution_due}</div>
            )}
          </div>

          <div style={{ ...S.card, marginBottom: 16 }}>
            <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--text-2)', marginBottom: 8, textTransform: 'uppercase' }}>Descripción original</div>
            <p style={{ fontSize: "var(--text-md)", lineHeight: 1.7, margin: 0, whiteSpace: 'pre-wrap' }}>{ticketDetail.description}</p>
          </div>

          {ticketDetail.resolution && (
            <div style={{ background: 'var(--success-bg)', border: '1px solid var(--success-border)', borderRadius: 12, padding: 16, marginBottom: 16 }}>
              <div style={{ fontSize: "var(--text-xs)", fontWeight: 700, color: 'var(--success)', marginBottom: 8, textTransform: 'uppercase' }}>✓ Resolución del equipo</div>
              <p style={{ fontSize: "var(--text-md)", lineHeight: 1.7, margin: 0 }}>{ticketDetail.resolution}</p>
            </div>
          )}

          {ticketDetail.csat_requested_at && !ticketDetail.csat_score && (
            <div style={{ ...S.card, border: '1px solid var(--success-border)', marginBottom: 16 }}>
              <div style={{ fontSize: "var(--text-md)", fontWeight: 700, marginBottom: 12 }}>⭐ ¿Cómo valorarías la atención recibida?</div>
              <div style={{ display: 'flex', gap: 10 }}>
                {[1,2,3,4,5].map(n => (
                  <button key={n} onClick={() => submitCSAT({ score: n })}
                    style={{ flex: 1, padding: '12px', borderRadius: 10, border: '1px solid var(--surface-4)', background: 'var(--surface-1)', color: 'var(--text-1)', cursor: 'pointer', fontSize: "var(--text-xl-em)", fontFamily: 'inherit', transition: 'all 0.15s' }}
                    onMouseEnter={e => { e.currentTarget.style.background = 'var(--success-bg)'; e.currentTarget.style.borderColor = 'var(--success-border)' }}
                    onMouseLeave={e => { e.currentTarget.style.background = 'var(--surface-1)'; e.currentTarget.style.borderColor = 'var(--surface-4)' }}>
                    {'⭐'.repeat(n)}
                  </button>
                ))}
              </div>
            </div>
          )}
          {ticketDetail.csat_score && (
            <div style={{ background: 'var(--success-bg)', border: '1px solid var(--success-border)', borderRadius: 10, padding: '10px 16px', marginBottom: 16, fontSize: "var(--text-base)", color: 'var(--success)' }}>
              ✓ Valoraste este ticket con {'⭐'.repeat(ticketDetail.csat_score)} — ¡gracias por tu feedback!
            </div>
          )}

          <div style={{ marginBottom: 16 }}>
            <div style={{ fontSize: "var(--text-base)", fontWeight: 700, color: 'var(--text-2)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 14 }}>Conversación</div>
            {ticketDetail.comments?.filter(c => c.is_public).map(c => (
              <div key={c.id} style={{ display: 'flex', gap: 12, marginBottom: 16 }}>
                <div style={{ width: 34, height: 34, borderRadius: '50%', background: c.author_type === 'agent' ? 'linear-gradient(135deg, var(--accent), var(--purple))' : 'linear-gradient(135deg, var(--success), var(--purple))', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: "var(--text-sm)", fontWeight: 700, flexShrink: 0 }}>
                  {c.author_name?.split(' ').map(w => w[0]).join('').slice(0,2)}
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', gap: 10, marginBottom: 4 }}>
                    <span style={{ fontSize: "var(--text-base)", fontWeight: 700 }}>{c.author_name}</span>
                    <span style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>{c.created_at}</span>
                  </div>
                  <div style={{ background: c.author_type === 'agent' ? 'var(--portal-bg)' : 'var(--portal-surface)', borderRadius: 10, padding: '12px 16px', fontSize: "var(--text-base)", lineHeight: 1.6 }}>{c.body}</div>
                </div>
              </div>
            ))}
          </div>

          {!['closed', 'cancelled'].includes(ticketDetail.status) && (
            <div style={{ ...S.card }}>
              <div style={{ fontSize: "var(--text-sm)", fontWeight: 700, color: 'var(--text-2)', marginBottom: 8, textTransform: 'uppercase' }}>Tu respuesta</div>
              <textarea value={newComment} onChange={e => setNewComment(e.target.value)} rows={4}
                placeholder="Escribe tu respuesta"
                style={{ ...S.input, resize: 'vertical', marginBottom: 12 }} />
              <button onClick={() => { addComment({ body: newComment, is_public: true }); setNewComment('') }}
                disabled={!newComment}
                style={{ ...S.btn, opacity: newComment ? 1 : 0.5 }}>
                Enviar respuesta
              </button>
            </div>
          )}
          </div>
        )
      )}

      {/* KB tab */}
      {tab === 'kb' && (
        <div id="portal-support-panel-kb" role="tabpanel" aria-labelledby="portal-support-tab-kb">
          <div style={{ marginBottom: 20 }}>
            <input aria-label="Buscar en la base de conocimiento" value={searchKB} onChange={e => setSearchKB(e.target.value)} placeholder="Buscar en la base de conocimiento"
              style={{ ...S.input, fontSize: "var(--text-md-em)", padding: '13px 16px' }} />
          </div>
          {kbArticles.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '40px 0', color: 'var(--text-2)' }}>
              <div style={{ fontSize: "var(--text-4xl)", marginBottom: 12 }}>📚</div>
              <p>{searchKB ? `Sin resultados para "${searchKB}"` : 'La base de conocimiento está vacía de momento'}</p>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {kbArticles.map(a => (
                <div key={a.id} style={{ ...S.card }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                    <span style={{ fontSize: "var(--text-md-em)", fontWeight: 700 }}>{a.title}</span>
                    <span style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)' }}>👁 {a.view_count} · ✓ {a.helpful_count}</span>
                  </div>
                  {a.summary && <p style={{ fontSize: "var(--text-base)", color: 'var(--text-2)', margin: '0 0 10px' }}>{a.summary}</p>}
                  {a.tags && <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)' }}>🏷 {a.tags}</div>}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Announcements tab */}
      {tab === 'announcements' && (
        <div id="portal-support-panel-announcements" role="tabpanel" aria-labelledby="portal-support-tab-announcements">
          {announcements.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '40px 0', color: 'var(--text-2)' }}>
              <div style={{ fontSize: "var(--text-4xl)", marginBottom: 12 }}>📢</div>
              <p>No hay comunicados activos</p>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {announcements.map(a => (
                <div key={a.id} style={{ ...S.card, border: `1px solid ${a.type === 'outage' ? 'rgba(248,113,113,0.25)' : 'var(--surface-4)'}` }}>
                  <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
                    <span style={{ fontSize: "var(--text-2xl)" }}>{a.type === 'outage' ? '🚨' : a.type === 'maintenance' ? '🔧' : a.type === 'resolved' ? '✅' : 'ℹ️'}</span>
                    <div>
                      <div style={{ fontSize: "var(--text-md)", fontWeight: 700, marginBottom: 4 }}>{a.title}</div>
                      <p style={{ fontSize: "var(--text-base)", color: 'var(--text-2)', margin: 0 }}>{a.body}</p>
                      {a.starts_at && <div style={{ fontSize: "var(--text-xs)", color: 'var(--text-2)', marginTop: 6 }}>{a.starts_at} {a.ends_at && `→ ${a.ends_at}`}</div>}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Create ticket modal */}
      {showCreate && (
        <div style={{ position: 'fixed', inset: 0, background: 'var(--overlay)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
          <div role="dialog" aria-modal="true" aria-labelledby="portal-support-create-title" style={{ ...S.card, width: 580, maxHeight: '90vh', overflowY: 'auto' }}>
            <h3 id="portal-support-create-title" style={{ fontSize: "var(--text-lg-em)", fontWeight: 800, margin: '0 0 20px' }}>{t('support_modal_title')}</h3>

            <div style={{ background: 'var(--portal-bg)', borderRadius: 10, padding: 14, marginBottom: 20 }}>
              <div style={{ fontSize: "var(--text-sm)", color: 'var(--text-2)', marginBottom: 8 }}>{t('support_kb_hint')}</div>
              <div style={{ display: 'flex', gap: 8 }}>
                <input placeholder="Buscar artículo relacionado" aria-label="Buscar artículo relacionado" style={{ ...S.input, flex: 1, fontSize: "var(--text-sm)", padding: '8px 12px' }}
                  onChange={e => setSearchKB(e.target.value)} />
                <button onClick={() => { setShowCreate(false); setTab('kb') }}
                  style={{ ...S.btnSec, padding: '7px 12px', fontSize: "var(--text-sm)", whiteSpace: 'nowrap' }}>Ver KB</button>
              </div>
            </div>

            {catalog.length > 0 && (
              <div style={{ marginBottom: 16 }}>
                <label style={S.label}>Tipo de solicitud (catálogo de servicios)</label>
                <select value={createForm.service_item_id} onChange={e => setCreateForm(f => ({ ...f, service_item_id: e.target.value }))} style={S.input}>
                  <option value="">Seleccionar del catálogo...</option>
                  {catalog.map(cat => (
                    <optgroup key={cat.id} label={`${cat.icon} ${cat.name}`}>
                      {cat.services.map(s => <option key={s.id} value={s.id}>{s.name} — SLA {s.sla_resolution_hours}h</option>)}
                    </optgroup>
                  ))}
                </select>
              </div>
            )}

            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <div>
                <label style={S.label}>Tipo de ticket</label>
                <div style={{ display: 'flex', gap: 8 }}>
                  {[['incident','🔥 Incidencia'],['service_request','📋 Solicitud'],['question','❓ Consulta']].map(([v,l]) => (
                    <button key={v} onClick={() => setCreateForm(f => ({ ...f, ticket_type: v }))}
                      style={{ flex: 1, padding: '8px', borderRadius: 8, border: `1px solid ${createForm.ticket_type === v ? 'var(--accent)' : 'var(--surface-4)'}`, background: createForm.ticket_type === v ? 'var(--accent-muted)' : 'transparent', color: createForm.ticket_type === v ? 'var(--accent)' : 'var(--text-2)', cursor: 'pointer', fontSize: "var(--text-sm)", fontFamily: 'inherit', fontWeight: 600 }}>
                      {l}
                    </button>
                  ))}
                </div>
              </div>
              <div><label style={S.label}>Título *</label><input value={createForm.title} onChange={e => setCreateForm(f => ({ ...f, title: e.target.value }))} style={S.input} placeholder="Título del ticket" aria-label="Título del ticket" /></div>
              <div><label style={S.label}>Descripción *</label><textarea value={createForm.description} onChange={e => setCreateForm(f => ({ ...f, description: e.target.value }))} rows={4} style={{ ...S.input, resize: 'vertical' }} placeholder="Describe el problema o solicitud" aria-label="Descripción del ticket" /></div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <div>
                  <label style={S.label}>Urgencia</label>
                  <select value={createForm.urgency} onChange={e => setCreateForm(f => ({ ...f, urgency: e.target.value }))} style={S.input}>
                    <option value="critical">Crítica — el negocio está parado</option>
                    <option value="high">Alta — funcionalidad importante no funciona</option>
                    <option value="medium">Media — hay un workaround posible</option>
                    <option value="low">Baja — es un problema menor</option>
                  </select>
                </div>
                <div>
                  <label style={S.label}>Impacto</label>
                  <select value={createForm.impact} onChange={e => setCreateForm(f => ({ ...f, impact: e.target.value }))} style={S.input}>
                    <option value="enterprise">Afecta a toda la empresa</option>
                    <option value="department">Afecta a mi departamento</option>
                    <option value="user">Me afecta solo a mí</option>
                    <option value="minimal">Impacto mínimo</option>
                  </select>
                </div>
              </div>
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 8 }}>
                <button onClick={() => setShowCreate(false)} style={S.btnSec}>Cancelar</button>
                <button onClick={() => createTicket(createForm)} disabled={!createForm.title || !createForm.description}
                  style={{ ...S.btn, opacity: createForm.title && createForm.description ? 1 : 0.5 }}>
                  Abrir ticket
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
