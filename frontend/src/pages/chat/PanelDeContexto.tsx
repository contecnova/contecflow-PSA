/**
 * Panel lateral de contexto de la conversación.
 * Troceado de ChatPage.tsx sin cambio de comportamiento (23-11-2026).
 */
import { type ReactNode, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Pin, Bookmark, AtSign, Phone, Video, Sparkles, X, FileSignature, UserPlus, CalendarDays } from 'lucide-react'
import { useToast } from '../../context/ToastContext'
import { confirmar } from '../../context/ConfirmContext'
import { useAuth } from '../../context/AuthContext'
import { collabApi } from '../../services/collaborationApi'
import { useAppLang } from '../../i18n/AppLangContext'
import { extractErr, fmtDateTime, fmtNumber } from '../../utils/helpers'
import { sanitizeUrl } from '../../utils/security'
import { Button, IconButton } from '../../components/ui'
import { POLL_FREQUENT_MS, POLL_SLOW_MS } from '../../constants/timings'
import {
  type CalendarData,
  type CallRow,
  type Channel,
  type CollabNotification,
  type Conv,
  type Decision,
  type Member,
  type Presence,
  type PreviewRow,
} from './compartido'
import { AddGroupMembersModal } from './ModalesDeConversacion'

// ── Right context panel ─────────────────────────────────────────────────────
export function ContextPanel({ conv }: { conv: Conv }) {
  const { t: traducir } = useAppLang()
  const qc = useQueryClient()
  const toast = useToast()
  const { user: me } = useAuth()
  const [showAddMember, setShowAddMember] = useState(false)
  const { data: pins = [] } = useQuery({
    queryKey: ['collab-pins', conv.id],
    queryFn: () => collabApi.listPins(conv.id) as Promise<PreviewRow[]>,
    enabled: !!conv?.id,
  })
  const { data: members = [] } = useQuery({
    queryKey: ['collab-members', conv?.id, conv?.kind],
    queryFn: async (): Promise<Member[]> => {
      if (conv?.kind === 'channel') {
        const all = await collabApi.listChannels(undefined)
        const ch = (all as Channel[]).find(x => x.conversation_id === conv.id)
        if (ch) return collabApi.listChannelMembers(ch.id) as Promise<Member[]>
        return []
      }
      if (conv?.kind === 'group') {
        return collabApi.listConversationMembers(conv.id) as Promise<Member[]>
      }
      return []
    },
    enabled: !!conv?.id,
  })
  const removeMember = useMutation({
    mutationFn: (uid: string) => collabApi.removeConversationMember(conv.id, uid),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['collab-members', conv.id] })
      qc.invalidateQueries({ queryKey: ['collab-conversations'] })
      toast.success(traducir('chat.member_removed'))
    },
    onError: (e: unknown) => toast.error(extractErr(e, traducir('chat.err_remove'))),
  })
  const { data: calls = [] } = useQuery({
    queryKey: ['collab-calls', conv.id],
    queryFn: () => collabApi.listCalls(conv.id) as Promise<CallRow[]>,
    enabled: !!conv?.id,
  })
  const { data: calendar } = useQuery<CalendarData>({
    queryKey: ['collab-calendar'],
    queryFn: () => collabApi.calendarEvents(7) as Promise<CalendarData>,
    refetchInterval: POLL_SLOW_MS,
  })
  const { data: decisions = [] } = useQuery({
    queryKey: ['collab-decisions-context'],
    queryFn: () => collabApi.listDecisions(5) as Promise<Decision[]>,
  })
  const { data: presenceList = [] } = useQuery({
    queryKey: ['collab-presence'],
    queryFn: () => collabApi.listPresence() as Promise<Presence[]>,
    refetchInterval: POLL_FREQUENT_MS,
  })
  const onlineUsers = presenceList.filter(p => p.user_id && p.status && p.status !== 'offline')

  return (
    <aside className="chat-ctx" aria-label={traducir('chat.informacion')}>
      <Section title={traducir('chat.informacion')}>
        <div className="u-text2-sm">{traducir(conv.kind === 'channel' ? 'chat.tab_channel' : conv.kind === 'group' ? 'chat.tab_group' : 'chat.tab_direct')}</div>
      </Section>
      <Section title={traducir('chat.online_count', { count: onlineUsers.length })}>
        {onlineUsers.length === 0 ? <Empty>{traducir('chat.nobody_online')}</Empty> : onlineUsers.slice(0, 12).map(p => {
          const name = p.user_name || traducir('chat.user')
          return (
            <div key={p.user_id} className="chat-ctx__person">
              <span className="chat-presence-wrap">
                <span className="chat-avatar" aria-hidden="true">{name.charAt(0).toUpperCase()}</span>
                <span className={`chat-presence-dot chat-presence-dot--${p.status}`} role="img" aria-label={traducir(`chat.presence_${p.status}`, p.status)} />
              </span>
              <span className="chat-ctx__name">{name}</span>
              {p.is_in_call && <Phone size={10} className="u-accent" role="img" aria-label={traducir('chat.in_call')} />}
            </div>
          )
        })}
      </Section>
      {(members.length > 0 || conv.kind === 'group') && (
        <Section
          title={traducir('chat.members_count', { count: members.length })}
          right={conv.kind === 'group' ? (
            <Button variant="ghost" size="xs" icon={<UserPlus size={12} />}
              onClick={() => setShowAddMember(true)}
              title={traducir('chat.anadir_miembro')}>
              {traducir('chat.anadir')}
            </Button>
          ) : null}
        >
          {members.slice(0, 12).map(m => {
            const isMe = m.user_id === me?.id
            const canRemove = conv.kind === 'group' && (isMe || members.find(mm => mm.user_id === me?.id)?.is_admin)
            return (
              <div key={m.id} className="chat-ctx__person chat-ctx__person--sm">
                <div className="chat-avatar" aria-hidden="true">
                  {(m.user_name || '?').charAt(0).toUpperCase()}
                </div>
                <span className="chat-ctx__name">
                  {m.user_name || traducir('chat.client')}{isMe && ` ${traducir('chat.me_suffix')}`}
                </span>
                {(m.role && m.role !== 'member') && <span className="chat-ctx__role">{traducir(`chat.role_${m.role}`, m.role)}</span>}
                {m.is_admin && <span className="chat-ctx__role chat-ctx__role--admin">{traducir('chat.admin')}</span>}
                {canRemove && (
                  <IconButton variante="caja" tono="peligro" ariaLabel={isMe ? traducir('chat.leave_group') : traducir('chat.remove_from_group')}
                    onClick={async () => { if (await confirmar({ message: isMe ? traducir('chat.leave_group_q') : traducir('chat.remove_member_q', { name: m.user_name ?? '' }), danger: true, confirmLabel: isMe ? traducir('chat.leave') : traducir('chat.remove') })) removeMember.mutate(m.user_id) }}
                    title={isMe ? traducir('chat.leave_group') : traducir('chat.remove_from_group')}
                  >
                    <X size={12} aria-hidden="true" />
                  </IconButton>
                )}
              </div>
            )
          })}
        </Section>
      )}
      {showAddMember && conv.kind === 'group' && (
        <AddGroupMembersModal
          conv={conv}
          existingUserIds={members.map(m => m.user_id).filter(Boolean)}
          onClose={() => setShowAddMember(false)}
          onAdded={() => {
            qc.invalidateQueries({ queryKey: ['collab-members', conv.id] })
            qc.invalidateQueries({ queryKey: ['collab-conversations'] })
            setShowAddMember(false)
            toast.success(traducir('chat.members_added'))
          }}
        />
      )}
      <Section title={traducir('chat.pinned_count', { count: pins.length })}>
        {pins.length === 0 ? <Empty>{traducir('chat.ningun_mensaje_anclado')}</Empty> : pins.map(p => (
          <div key={p.id} className="chat-ctx-muted">
            <Pin size={10} aria-hidden="true" /> {p.preview}
          </div>
        ))}
      </Section>
      <Section title={traducir('chat.calls_count', { count: calls.length })}>
        {calls.length === 0 ? <Empty>{traducir('chat.sin_llamadas')}</Empty> : calls.slice(0, 5).map(c => (
          <div key={c.id} className="chat-ctx-muted">
            {c.kind === 'video'
              ? <Video size={11} role="img" aria-label={traducir('chat.video_call')} />
              : <Phone size={11} role="img" aria-label={traducir('chat.llamada_de_voz')} />} {traducir('chat.seconds', { count: fmtNumber(c.duration_seconds, 0) })} — {traducir(`chat.call_status_${c.status}`, c.status)}
            {c.has_summary && <Sparkles size={10} className="chat-ctx__summary" role="img" aria-label={traducir('chat.has_summary')} />}
          </div>
        ))}
      </Section>
      <Section title={traducir('chat.proximos_eventos_7d')}>
        {!calendar?.events?.length ? (
          <Empty>{calendar?.providers_connected?.length ? traducir('chat.no_upcoming_events') : traducir('chat.connect_calendar')}</Empty>
        ) : calendar.events.slice(0, 6).map(ev => (
          <a key={ev.id} href={sanitizeUrl(ev.link)} target="_blank" rel="noopener noreferrer"
            className="chat-ctx__event">
            <div className="chat-ctx__event-title">{ev.title}</div>
            <div className="chat-ctx__event-meta">
              <CalendarDays size={11} aria-hidden="true" />
              <span>{ev.start ? fmtDateTime(ev.start) : ''}</span>
              <span className="chat-ctx__event-src">{ev.source === 'google' ? 'Google' : 'Microsoft 365'}</span>
            </div>
          </a>
        ))}
      </Section>
      <Section title={traducir('chat.decisions_count', { count: decisions.length })}>
        {decisions.length === 0 ? <Empty>{traducir('chat.sin_decisiones_registradas')}</Empty> : decisions.slice(0, 5).map(d => (
          <div key={d.id} className="chat-ctx-muted">
            <FileSignature size={10} className="chat-ctx__decision-icon" aria-hidden="true" /> {(d.text || '').slice(0, 100)}
          </div>
        ))}
      </Section>
    </aside>
  )
}

function Section({ title, children, right }: { title: ReactNode; children?: ReactNode; right?: ReactNode }) {
  return (
    <section className="chat-sec">
      <div className="chat-sec__head">
        <h3 className="chat-sec__title">{title}</h3>
        {right}
      </div>
      {children}
    </section>
  )
}

function Empty({ children }: { children?: ReactNode }) { return <div className="chat-empty">{children}</div> }

export function Loader() {
  const { t: traducir } = useAppLang()
  return <div className="chat-loader" role="status" aria-label={traducir('chat.loading')}>
    <div className="chat-loader__spin" />
  </div>
}

// ── Activity tab ────────────────────────────────────────────────────────────
export function ActivityList({ narrow = false }: { narrow?: boolean }) {
  const { t: traducir } = useAppLang()
  const { data: notifs = [] } = useQuery({ queryKey: ['collab-notifications'], queryFn: () => collabApi.listNotifications(false) as Promise<CollabNotification[]> })
  const { data: mentions = [] } = useQuery({ queryKey: ['collab-mentions'], queryFn: () => collabApi.listMyMentions() as Promise<PreviewRow[]> })
  const { data: saved = [] } = useQuery({ queryKey: ['collab-saved'], queryFn: () => collabApi.listSaved() as Promise<PreviewRow[]> })
  return (
    <div className={`chat-activity${narrow ? ' chat-activity--narrow' : ''}`}>
      <Section title={traducir('chat.notifications_count', { count: notifs.length })}>
        {notifs.length === 0 ? <Empty>{traducir('chat.sin_notificaciones')}</Empty> : notifs.slice(0, 30).map(n => (
          <div key={n.id} className={`chat-notif${n.is_read ? '' : ' chat-notif--unread'}`}>
            <div className="chat-notif__title">{n.title}</div>
            <div className="u-text3-xs">{(n.body || '').slice(0, 80)}</div>
          </div>
        ))}
      </Section>
      <Section title={traducir('chat.mentions_count', { count: mentions.length })}>
        {mentions.length === 0 ? <Empty>{traducir('chat.sin_menciones')}</Empty> : mentions.slice(0, 20).map(m => (
          <div key={m.id} className="chat-ctx-muted">
            <AtSign size={10} aria-hidden="true" /> {m.preview}
          </div>
        ))}
      </Section>
      <Section title={traducir('chat.saved_count', { count: saved.length })}>
        {saved.length === 0 ? <Empty>{traducir('chat.sin_guardados')}</Empty> : saved.slice(0, 20).map(s => (
          <div key={s.id} className="chat-ctx-muted">
            <Bookmark size={10} aria-hidden="true" /> {s.preview}
          </div>
        ))}
      </Section>
    </div>
  )
}
