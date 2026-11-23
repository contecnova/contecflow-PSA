/**
 * Barra de navegación y lista de conversaciones.
 * Troceado de ChatPage.tsx sin cambio de comportamiento (23-11-2026).
 */
import { type ReactNode, useState } from 'react'
import { Hash, MessageSquare, Users, Phone, ChevronDown, ChevronRight, Bell } from 'lucide-react'
import { useAppLang } from '../../i18n/AppLangContext'
import { Buscador, EmptyState, Pulsable } from '../../components/ui'
import { type Channel, type Conv, type Presence, type Team, tituloConv } from './compartido'
import { ActivityList, Loader } from './PanelDeContexto'

// ── Left rail ────────────────────────────────────────────────────────────────
export function NavRail({ activeTab, onTab, unreadNotifs }: { activeTab: string; onTab: (id: string) => void; unreadNotifs: number }) {
  const { t: traducir } = useAppLang()
  const items = [
    { id: 'activity', label: traducir('chat.nav_activity'), icon: Bell, badge: unreadNotifs },
    { id: 'chats',    label: traducir('chat.nav_chat'),     icon: MessageSquare },
    { id: 'teams',    label: traducir('chat.nav_teams'),    icon: Users },
    { id: 'calls',    label: traducir('chat.nav_calls'),    icon: Phone },
  ]
  return (
    <nav className="chat-rail" aria-label={traducir('chat.nav_label')}>
      {items.map(it => {
        const Icon = it.icon
        const active = activeTab === it.id
        return (
          <Pulsable type="button" key={it.id} onClick={() => onTab(it.id)} title={it.label}
            className="chat-rail__btn" aria-current={active ? 'page' : undefined}>
            <Icon size={20} aria-hidden="true" />
            <span className="u-xs">{it.label}</span>
            {(it.badge ?? 0) > 0 && (
              <span className="chat-rail__badge" aria-label={traducir('chat.unread_count', { count: it.badge ?? 0 })}>{(it.badge ?? 0) > 99 ? '99+' : it.badge}</span>
            )}
          </Pulsable>
        )
      })}
    </nav>
  )
}

// ── Conversations sidebar (middle column) ────────────────────────────────────
export function ConversationsList({ narrow = false, activeTab, conversations, teams, channels, presence, loading, activeConv, onSelect, newConvAction }: {
  narrow?: boolean; activeTab: string; conversations: Conv[]; teams: Team[]; channels: Channel[];
  presence: Presence[]; loading: boolean; activeConv: Conv | null; onSelect: (c: Conv) => void
  newConvAction?: ReactNode
}) {
  const { t: traducir } = useAppLang()
  const [filter, setFilter] = useState('')
  const [openTeams, setOpenTeams] = useState(true)

  // Hooks must run unconditionally — compute always.
  const presenceMap = (() => {
    const m: Record<string, string> = {}
    for (const p of presence) if (p.user_id) m[p.user_id] = p.status
    return m
  })()
  const channelsByTeam = (() => {
    const map: Record<string, Channel[]> = {}
    for (const ch of channels) {
      map[ch.team_id] = map[ch.team_id] || []
      map[ch.team_id].push(ch)
    }
    return map
  })()

  if (activeTab === 'activity') return <ActivityList narrow={narrow} />

  const directs = conversations.filter(c => c.kind === 'direct')
  const groups = conversations.filter(c => c.kind === 'group')

  const matches = (text: string | undefined | null) => !filter || (text || '').toLowerCase().includes(filter.toLowerCase())

  return (
    <div className={`chat-list${narrow ? ' chat-list--narrow' : ''}`}>
      <div className="chat-list__search">
        <Buscador className="chat-search-box" aria-label={traducir('chat.search_placeholder')} value={filter} onChange={setFilter} placeholder={traducir('chat.search_placeholder')} />
      </div>

      <div className="chat-list__scroll">
        {loading && <Loader />}

        {!loading && conversations.length === 0 && teams.length === 0 && (
          <EmptyState icon={<MessageSquare size={28} />}
            title={traducir('chat.vacio_titulo')}
            description={traducir('chat.vacio_desc')}
            action={newConvAction} />
        )}

        {activeTab !== 'teams' && directs.length > 0 && (
          <SectionGroup title={traducir('chat.direct_chats')} count={directs.length}>
            {directs.filter(c => matches(c.title)).map(c => (
              <ConvRow key={c.id} c={c} active={activeConv?.id === c.id} onClick={() => onSelect(c)}
                presence={c.peer_user_id ? presenceMap[c.peer_user_id] : null} />
            ))}
          </SectionGroup>
        )}

        {activeTab !== 'teams' && groups.length > 0 && (
          <SectionGroup title={traducir('chat.groups')} count={groups.length}>
            {groups.filter(c => matches(c.title)).map(c => (
              <ConvRow key={c.id} c={c} active={activeConv?.id === c.id} onClick={() => onSelect(c)} />
            ))}
          </SectionGroup>
        )}

        {teams.length > 0 && <SectionGroup
          title={traducir('chat.nav_teams')}
          count={teams.length}
          collapsed={!openTeams}
          onToggle={() => setOpenTeams(o => !o)}
        >
          {openTeams && teams.filter(t => matches(t.name)).map(team => (
            <div key={team.id} className="chat-team">
              <div className="chat-team__name">
                <Users size={13} aria-hidden="true" /> {team.name}
              </div>
              {(channelsByTeam[team.id] || []).filter(ch => matches(ch.name)).map(ch => {
                const conv = conversations.find(c => c.id === ch.conversation_id)
                if (!conv) return null
                return (
                  <ConvRow key={ch.id} c={conv} active={activeConv?.id === conv.id}
                    onClick={() => onSelect(conv)} indent />
                )
              })}
            </div>
          ))}
        </SectionGroup>}
      </div>
    </div>
  )
}

function SectionGroup({ title, count, children, collapsed, onToggle }: {
  title: string; count?: number; children?: ReactNode; collapsed?: boolean; onToggle?: () => void
}) {
  return (
    <div className="u-mb-12">
      {onToggle ? (
        <Pulsable type="button" onClick={onToggle} aria-expanded={!collapsed} className="chat-section-btn chat-section-btn--toggle">
          {collapsed ? <ChevronRight size={11} aria-hidden="true" /> : <ChevronDown size={11} aria-hidden="true" />}
          {title} {count != null && <span className="chat-section-btn__count">({count})</span>}
        </Pulsable>
      ) : (
        <h3 className="chat-section-btn">
          {title} {count != null && <span className="chat-section-btn__count">({count})</span>}
        </h3>
      )}
      {!collapsed && children}
    </div>
  )
}

function ConvRow({ c, active, onClick, presence, indent }: {
  c: Conv; active: boolean; onClick: () => void; presence?: string | null; indent?: boolean
}) {
  const { t: traducir } = useAppLang()
  return (
    <Pulsable type="button" onClick={onClick} aria-current={active ? 'true' : undefined}
      className={`chat-conv-row${indent ? ' chat-conv-row--indent' : ''}`}>
      {c.kind === 'channel' && <Hash size={13} aria-hidden="true" />}
      {c.kind === 'direct'  && (
        <span className="chat-presence-wrap">
          <span className="chat-avatar" aria-hidden="true">{(c.title || '?').charAt(0).toUpperCase()}</span>
          {presence && presence !== 'offline' && (
            <span className={`chat-presence-dot chat-presence-dot--${presence}`} role="img" aria-label={traducir(`chat.presence_${presence}`, presence)} />
          )}
        </span>
      )}
      {c.kind === 'group' && <Users size={13} aria-hidden="true" />}
      <span className="chat-ellipsis">{tituloConv(c)}</span>
    </Pulsable>
  )
}
