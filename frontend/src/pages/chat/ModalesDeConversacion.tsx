/**
 * Modales de nueva conversación, alta de miembros y menú de cabecera.
 * Troceado de ChatPage.tsx sin cambio de comportamiento (23-11-2026).
 */
import { type ReactNode, useEffect, useReducer, useRef, useState, useId } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Hash, MessageSquare, Users, X, BellOff, Link as LinkIcon, UserPlus, LogOut, Check } from 'lucide-react'
import { useToast } from '../../context/ToastContext'
import { confirmar } from '../../context/ConfirmContext'
import { collabApi } from '../../services/collaborationApi'
import { useAppLang } from '../../i18n/AppLangContext'
import { extractErr } from '../../utils/helpers'
import { Buscador, useDialogoEditable, Button, Tabs, Pulsable, Select, Input } from '../../components/ui'
import { MENTION_SUGGESTIONS_LIMIT, MENTION_SUGGESTIONS_MEMBERS_LIMIT } from '../../constants/pagination'
import { type Conv, type Member, type MentionSuggestions, type NotificationRule, type Team, type UserLike } from './compartido'

export function NewConversationModal({ onClose, onCreated }: { onClose: () => void; onCreated?: (c: Conv) => void }) {
  const idCampo = useId()
  const { t: traducir } = useAppLang()
  const qc = useQueryClient()
  const toast = useToast()
  // Estado del formulario agrupado: todos los campos cambian juntos al
  // navegar entre pestañas (direct | group | channel) y se resetean a la
  // vez al cerrar. Un único objeto reduce el ruido de useStates sin
  // alterar la lógica.
  const [tab, setTab] = useState('direct')  // direct | group | channel
  type ModalForm = {
    search: string; selectedUsers: UserLike[]; groupTitle: string;
    channelName: string; channelType: string; selectedTeamId: string
  }
  const [form, updateForm] = useReducer(
    (s: ModalForm, patch: Partial<ModalForm>) => ({ ...s, ...patch }),
    {
      search: '',
      selectedUsers: [] as UserLike[],
      groupTitle: '',
      channelName: '',
      channelType: 'public',
      selectedTeamId: '',
    },
  )
  const { search, selectedUsers, groupTitle, channelName, channelType, selectedTeamId } = form

  const { data: suggestions = { users: [], groups: [] } } = useQuery({
    queryKey: ['mention-suggestions-modal', search],
    queryFn: () => collabApi.mentionSuggestions({ q: search, limit: MENTION_SUGGESTIONS_LIMIT }) as Promise<MentionSuggestions>,
  })
  const { data: teams = [] } = useQuery({
    queryKey: ['collab-teams'],
    queryFn: () => collabApi.listTeams() as Promise<Team[]>,
  })

  useEffect(() => {
    if (!selectedTeamId && teams.length > 0) updateForm({ selectedTeamId: teams[0].id })
  }, [teams, selectedTeamId])

  const toggleUser = (u: UserLike) => {
    updateForm({
      selectedUsers: selectedUsers.find(x => x.id === u.id)
        ? selectedUsers.filter(x => x.id !== u.id)
        : [...selectedUsers, u],
    })
  }

  const submit = useMutation({
    mutationFn: async () => {
      if (tab === 'direct') {
        if (!selectedUsers.length) throw new Error(traducir('chat.selecciona_un_usuario'))
        return await collabApi.openDirect({ user_id: selectedUsers[0].id })
      } else if (tab === 'group') {
        if (!selectedUsers.length) throw new Error(traducir('chat.err_min_one_member'))
        return await collabApi.createGroup({
          title: groupTitle.trim() || null,
          user_ids: selectedUsers.map(u => u.id),
        })
      } else {
        if (!channelName.trim()) throw new Error(traducir('chat.err_channel_name'))
        if (!selectedTeamId) throw new Error(traducir('chat.err_select_team'))
        const ch = await collabApi.createChannel({
          team_id: selectedTeamId,
          name: channelName.trim(),
          channel_type: channelType,
          initial_member_ids: selectedUsers.map(u => u.id),
        })
        return { conversation_id: ch.conversation_id }
      }
    },
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['collab-conversations'] })
      qc.invalidateQueries({ queryKey: ['collab-channels'] })
      // Notifica al WS para que re-suscriba a la nueva conversación sin recargar página
      window.dispatchEvent(new CustomEvent('collab:resync'))
      onCreated?.({ id: data.conversation_id || data.id, kind: tab === 'channel' ? 'channel' : tab })
      toast.success(traducir(tab === 'direct' ? 'chat.chat_opened' : tab === 'group' ? 'chat.group_created' : 'chat.channel_created'))
    },
    onError: (e: unknown) => toast.error(extractErr(e, traducir('chat.error_generic'))),
  })

  // Fondo, Esc y X preguntan si hay cambios sin guardar (kit, 23-11-2026).
  const { ref: dialogRef, pedirCierre } = useDialogoEditable<HTMLDivElement>(true, onClose, {
    cambiosSinGuardar: form.selectedUsers.length > 0 || Boolean(form.groupTitle.trim() || form.channelName.trim()),
  })
  const tituloId = `${idCampo}-titulo`
  return (
    <div role="presentation" onMouseDown={e => { if (e.target === e.currentTarget) pedirCierre() }} className="chat-modal-overlay">
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby={tituloId} tabIndex={-1}
        className="chat-modal">
        <div className="chat-modal__head">
          <h2 id={tituloId} className="u-md-700 chat-reset-h">{traducir('chat.nueva_conversacion')}</h2>
          <Pulsable type="button" onClick={pedirCierre} className="chat-icon-close" aria-label={traducir('chat.close')}><X size={14} aria-hidden="true" /></Pulsable>
        </div>
        <div className="chat-modal-tabs">
          <Tabs
            ariaLabel={traducir('chat.nueva_conversacion')}
            active={tab}
            onChange={setTab}
            items={[
              { id: 'direct', label: traducir('chat.tab_direct'), icon: <MessageSquare size={14} /> },
              { id: 'group', label: traducir('chat.tab_group'), icon: <Users size={14} /> },
              { id: 'channel', label: traducir('chat.tab_channel'), icon: <Hash size={14} /> },
            ]}
          />
        </div>
        <div className="chat-modal__body">
          {tab === 'group' && (
            <div className="u-mb-12">
              <label id={`${idCampo}-et1`} htmlFor={`${idCampo}-1`} className="chat-form-label">{traducir('chat.titulo_opcional')}</label>
              <Input id={`${idCampo}-1`} aria-labelledby={`${idCampo}-et1`} value={form.groupTitle} onChange={(e) => updateForm({ groupTitle: e.target.value })} placeholder={traducir('chat.group_title_placeholder')}
                inputClassName="chat-input" />
            </div>
          )}
          {tab === 'channel' && (
            <>
              <div className="u-mb-12">
                <label id={`${idCampo}-et2`} htmlFor={`${idCampo}-2`} className="chat-form-label">{traducir('chat.name')}</label>
                <Input id={`${idCampo}-2`} aria-labelledby={`${idCampo}-et2`} value={form.channelName} onChange={(e) => updateForm({ channelName: e.target.value })} placeholder={traducir('chat.channel_name_placeholder')} inputClassName="chat-input" />
              </div>
              <div className="chat-form-grid2">
                <div>
                  <label id={`${idCampo}-et3`} htmlFor={`${idCampo}-3`} className="chat-form-label">{traducir('chat.team')}</label>
                  <Select suelto placeholder={false} id={`${idCampo}-3`} value={form.selectedTeamId} onChange={(e) => updateForm({ selectedTeamId: e.target.value })} className="chat-input">
                    {teams.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
                  </Select>
                </div>
                <div>
                  <label id={`${idCampo}-et4`} htmlFor={`${idCampo}-4`} className="chat-form-label">{traducir('chat.type')}</label>
                  <Select suelto placeholder={false} id={`${idCampo}-4`} value={form.channelType} onChange={(e) => updateForm({ channelType: e.target.value })} className="chat-input">
                    <option value="public">{traducir('chat.publico')}</option>
                    <option value="private">{traducir('chat.private')}</option>
                    <option value="announcement">{traducir('chat.announcements')}</option>
                  </Select>
                </div>
              </div>
            </>
          )}
          {tab === 'direct' ? (
            <div className="chat-hint-xs">{traducir('chat.selecciona_un_usuario')}</div>
          ) : (
            <div className="chat-hint-xs">
              {traducir(tab === 'group' ? 'chat.anade_miembros_minimo' : 'chat.anade_miembros_opcional')}
            </div>
          )}
          <Buscador aria-label={traducir('chat.search_users')} value={search} onChange={v => updateForm({ search: v })} placeholder={traducir('chat.search_users')}
            inputClassName="chat-input" autoFocus />
          {selectedUsers.length > 0 && (
            <div className="chat-chips">
              {selectedUsers.map(u => (
                <span key={u.id} className="chat-chip">
                  {u.full_name || u.username} <Pulsable type="button" onClick={() => toggleUser(u)} className="chat-chip__remove" aria-label={traducir('chat.remove_name', { name: u.full_name || u.username || '' })}><X size={11} aria-hidden="true" /></Pulsable>
                </span>
              ))}
            </div>
          )}
          <div className="chat-user-list">
            {((suggestions.users || []) as UserLike[]).map((u: UserLike) => {
              const sel = !!selectedUsers.find(x => x.id === u.id)
              return (
                <Pulsable type="button" key={u.id} aria-pressed={sel} onClick={() => {
                  if (tab === 'direct') {
                    updateForm({ selectedUsers: [u] })
                  } else {
                    toggleUser(u)
                  }
                }} className="chat-user-option">
                  <span className="chat-avatar chat-avatar--28" aria-hidden="true">{(u.full_name || u.username || '?').charAt(0).toUpperCase()}</span>
                  <div className="u-flex1-min0">
                    <div className="u-text1-sm-600">{u.full_name}</div>
                    <div className="u-text3-xs">{u.email}</div>
                  </div>
                  {sel && <Check size={14} className="chat-check" aria-hidden="true" />}
                </Pulsable>
              )
            })}
          </div>
        </div>
        <div className="chat-modal__foot">
          <Button variant="secondary" onClick={onClose}>{traducir('chat.cancel')}</Button>
          <Button onClick={() => submit.mutate()} loading={submit.isPending}>{submit.isPending ? traducir('chat.creating') : traducir('chat.create')}</Button>
        </div>
      </div>
    </div>
  )
}

// ── Modal: añadir miembros a un grupo existente ─────────────────────────────
export function AddGroupMembersModal({ conv, existingUserIds, onClose, onAdded }: {
  conv: Conv; existingUserIds?: string[]; onClose: () => void; onAdded?: () => void
}) {
  const { t: traducir } = useAppLang()
  const toast = useToast()
  const [search, setSearch] = useState('')
  const [picked, setPicked] = useState<UserLike[]>([])

  const { data: suggestions = { users: [] } } = useQuery({
    queryKey: ['mention-suggestions-add-members', search],
    queryFn: () => collabApi.mentionSuggestions({ q: search, limit: MENTION_SUGGESTIONS_MEMBERS_LIMIT }) as Promise<MentionSuggestions>,
  })
  // Si no nos pasan existingUserIds, los obtenemos del servidor para evitar
  // que el listado proponga gente ya dentro del grupo.
  const { data: serverMembers = [] } = useQuery({
    queryKey: ['collab-members-for-add', conv?.id],
    queryFn: () => collabApi.listConversationMembers(conv.id) as Promise<Member[]>,
    enabled: !existingUserIds && !!conv?.id,
  })
  const dedupeIds: string[] = existingUserIds && existingUserIds.length
    ? existingUserIds
    : serverMembers.map(m => m.user_id).filter(Boolean)
  const candidates = ((suggestions.users || []) as UserLike[]).filter(u => !dedupeIds.includes(u.id))

  const submit = useMutation({
    mutationFn: () => collabApi.addConversationMembers(conv.id, { user_ids: picked.map(u => u.id) }),
    onSuccess: () => onAdded?.(),
    onError: (e: unknown) => toast.error(extractErr(e, traducir('chat.err_add_members'))),
  })

  const togglePick = (u: UserLike) => {
    setPicked(prev => prev.find(x => x.id === u.id) ? prev.filter(x => x.id !== u.id) : [...prev, u])
  }

  // Fondo, Esc y X preguntan si hay cambios sin guardar (kit, 23-11-2026).
  const { ref: dialogRef, pedirCierre } = useDialogoEditable<HTMLDivElement>(true, onClose, { cambiosSinGuardar: picked.length > 0 })
  const tituloId = useId()
  return (
    <div role="presentation" onMouseDown={e => { if (e.target === e.currentTarget) pedirCierre() }} className="chat-modal-overlay">
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby={tituloId} tabIndex={-1}
        className="chat-addm"
      >
        <div className="u-row-between">
          <h2 id={tituloId} className="u-md-700 chat-reset-h">{traducir('chat.anadir_miembros_a')} {conv.title || traducir('chat.group_fallback')}</h2>
          <Pulsable type="button" onClick={pedirCierre} className="chat-icon-close" aria-label={traducir('chat.close')}>
            <X size={16} aria-hidden="true" />
          </Pulsable>
        </div>
        <Buscador
          autoFocus
          aria-label={traducir('chat.busca_por_nombre_o_email')}
          value={search}
          onChange={setSearch}
          placeholder={traducir('chat.busca_por_nombre_o_email')}
          inputClassName="chat-input"
        />
        {picked.length > 0 && (
          <div className="u-wrap-6">
            {picked.map(u => (
              <span key={u.id} className="chat-addm__chip">
                {u.full_name || u.username}
                <Pulsable type="button" onClick={() => togglePick(u)} className="chat-addm__chip-x" aria-label={traducir('chat.remove_name', { name: u.full_name || u.username || '' })}>
                  <X size={11} aria-hidden="true" />
                </Pulsable>
              </span>
            ))}
          </div>
        )}
        <div className="chat-addm__list">
          {candidates.length === 0 ? (
            <div className="chat-addm__empty">
              {search ? traducir('chat.sin_resultados') : traducir('chat.start_typing_name')}
            </div>
          ) : candidates.map(u => {
            const isPicked = !!picked.find(x => x.id === u.id)
            return (
              <Pulsable type="button" key={u.id} onClick={() => togglePick(u)} aria-pressed={isPicked}
                className="chat-addm__option">
                <div className="chat-avatar chat-avatar--24" aria-hidden="true">
                  {(u.full_name || u.username || '?').charAt(0).toUpperCase()}
                </div>
                <span className="u-flex1">{u.full_name || u.username}</span>
                {isPicked && <Check size={14} className="chat-check" aria-hidden="true" />}
              </Pulsable>
            )
          })}
        </div>
        <div className="u-actions-8">
          <Button variant="secondary" size="sm" onClick={onClose}>{traducir('chat.cancel')}</Button>
          <Button
            size="sm"
            icon={<UserPlus size={14} />}
            disabled={!picked.length}
            loading={submit.isPending}
            onClick={() => submit.mutate()}>
            {submit.isPending ? traducir('chat.adding') : picked.length ? traducir('chat.add_n', { count: picked.length }) : traducir('chat.anadir')}
          </Button>
        </div>
      </div>
    </div>
  )
}

// ── Header dropdown: "..." con acciones de la conversación ─────────────────
export function ConvHeaderMenu({ conv, currentUser, onClose, onAddMembers }: {
  conv: Conv; currentUser: UserLike; onClose: () => void; onAddMembers: () => void
}) {
  const { t: traducir } = useAppLang()
  const qc = useQueryClient()
  const toast = useToast()
  const ref = useRef<HTMLDivElement>(null)

  // Click fuera + Esc cierran
  useEffect(() => {
    const onDoc = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) onClose() }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDoc)
      document.removeEventListener('keydown', onKey)
    }
  }, [onClose])

  // Reglas existentes para esta conv → permite alternar silencio
  const { data: rules = [] } = useQuery({
    queryKey: ['collab-rules'],
    queryFn: () => collabApi.listRules() as Promise<NotificationRule[]>,
  })
  const convRule = rules.find(r => r.scope === 'conversation' && r.target_id === conv.id)
  const muted = convRule?.notify_messages === 'none'

  const upsertMute = useMutation({
    mutationFn: (toMute: boolean) => collabApi.upsertRule({
      scope: 'conversation', target_id: conv.id,
      notify_messages: toMute ? 'none' : 'all',
      desktop_push: !toMute, email_digest: 'weekly',
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['collab-rules'] }); onClose() },
  })

  const copyLink = () => {
    const url = `${window.location.origin}/chat?conv=${encodeURIComponent(conv.id)}`
    // 23-11-2026: `writeText` devuelve una promesa; el aviso de éxito solo sale si de verdad copió.
    try {
      navigator.clipboard.writeText(url).then(
        () => toast.success(traducir('chat.link_copied')),
        () => toast.error(traducir('chat.copy_failed')),
      )
    } catch {
      toast.error(traducir('chat.copy_failed'))
    }
    onClose()
  }

  const leaveGroup = useMutation({
    mutationFn: () => collabApi.removeConversationMember(conv.id, currentUser.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['collab-conversations'] })
      toast.success(traducir('chat.left_group'))
      onClose()
    },
    onError: (e: unknown) => toast.error(extractErr(e, traducir('chat.error_generic'))),
  })

  const item =(icon: ReactNode, label: string, onClick: () => void, danger = false) => (
    <Pulsable type="button" role="menuitem" onClick={onClick} className={`chat-menu__item${danger ? ' chat-menu__item--danger' : ''}`}>
      {icon}
      <span className="u-flex1">{label}</span>
    </Pulsable>
  )

  return (
    <div ref={ref} role="menu" className="chat-menu">
      {item(<LinkIcon size={14} aria-hidden="true" />, traducir('chat.copy_link'), copyLink)}
      {item(
        <BellOff size={14} aria-hidden="true" />,
        muted ? traducir('chat.unmute') : traducir('chat.mute'),
        () => upsertMute.mutate(!muted),
      )}
      {conv.kind === 'group' && (
        <>
          <div className="chat-menu__sep" role="separator" />
          {item(<UserPlus size={14} aria-hidden="true" />, traducir('chat.add_members_ellipsis'), onAddMembers)}
          {item(<LogOut size={14} aria-hidden="true" />, traducir('chat.leave_group'), async () => {
            if (await confirmar({ message: traducir('chat.leave_group_confirm'), danger: true, confirmLabel: traducir('chat.leave') })) leaveGroup.mutate()
          }, true)}
        </>
      )}
    </div>
  )
}
