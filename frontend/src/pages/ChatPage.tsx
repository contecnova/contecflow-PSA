/**
 * ChatPage — Teams-like internal chat for Contecflow PSA.
 * Three-pane layout (sidebar / conversation / context panel) per
 * docs/chat_interno_teams_solucion_final.txt §6.1.
 *
 * Wired to /api/v1/collaboration endpoints + WebSocket realtime.
 */
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { MessageSquare, Search, Plus } from 'lucide-react'
import PageHeader from '../components/layout/PageHeader'
import { useToast } from '../context/ToastContext'
import { useAuth } from '../context/AuthContext'
import { collabApi } from '../services/collaborationApi'
import { apiUrl } from '../services/api'
import { registerCollabPush } from '../utils/collabPush'
import { useAppLang } from '../i18n/AppLangContext'
import useMediaQuery from '../hooks/useMediaQuery'
import { Button } from '../components/ui'
import { POLL_DEFAULT_MS, POLL_FREQUENT_MS, PRESENCE_POLL_MS, STALE_5_MIN_MS, STALE_DEFAULT_MS } from '../constants/timings'
import { type Channel, type ChatBot, type CollabNotification, type Conv, type Presence, type Team } from './chat/compartido'
import { ConversationsList, NavRail } from './chat/ListaDeConversaciones'
import { ConversationPane } from './chat/PanelDeConversacion'
import { ContextPanel } from './chat/PanelDeContexto'
import { SearchModal } from './chat/BusquedaYEnlaces'
import { NewConversationModal } from './chat/ModalesDeConversacion'
import './ChatPage.css'

// ── Page entry ───────────────────────────────────────────────────────────────
export default function ChatPage(): JSX.Element {
  const _toast = useToast()
  const { user } = useAuth()
  const { t: traducir } = useAppLang()
  const [newConvOpen, setNewConvOpen] = useState(false)

  const [activeTab, setActiveTab] = useState('chats') // chats | teams | activity | calls
  const [searchParams, setSearchParams] = useSearchParams()
  const urlConvId = searchParams.get('conv')
  const [showSlashMenu, setShowSlashMenu] = useState(false)
  const [draft, setDraft] = useState('')
  const [searchModalOpen, setSearchModalOpen] = useState(false)
  // En pantalla estrecha se ve una sola columna: la lista o la conversación.
  const narrow = useMediaQuery('(max-width: 900px)')
  const [mobileShowConv, setMobileShowConv] = useState(false)

  // ── Data ───────────────────────────────────────────────────────────────────
  useQuery({
    queryKey: ['collab-workspace'],
    queryFn:  () => collabApi.getWorkspace(),
    staleTime: STALE_DEFAULT_MS,
  })

  const { data: conversations = [], isLoading: loadingConvs } = useQuery({
    queryKey: ['collab-conversations'],
    queryFn:  () => collabApi.listConversations() as Promise<Conv[]>,
    refetchInterval: POLL_FREQUENT_MS,
  })

  const { data: teams = [] } = useQuery({
    queryKey: ['collab-teams'],
    queryFn:  () => collabApi.listTeams() as Promise<Team[]>,
    staleTime: STALE_DEFAULT_MS,
  })

  const { data: channels = [] } = useQuery({
    queryKey: ['collab-channels'],
    queryFn:  () => collabApi.listChannels(undefined) as Promise<Channel[]>,
    staleTime: STALE_DEFAULT_MS,
  })

  const { data: presence = [] } = useQuery({
    queryKey: ['collab-presence'],
    queryFn:  () => collabApi.listPresence() as Promise<Presence[]>,
    refetchInterval: POLL_DEFAULT_MS,
  })

  const { data: notifications = [] } = useQuery({
    queryKey: ['collab-notifications'],
    queryFn:  () => collabApi.listNotifications(false) as Promise<CollabNotification[]>,
    refetchInterval: POLL_FREQUENT_MS,
  })

  const { data: bots = [] } = useQuery({
    queryKey: ['collab-bots'],
    queryFn:  () => collabApi.listBots() as Promise<ChatBot[]>,
    staleTime: STALE_5_MIN_MS,
  })

  // Conversación activa = ?conv= de la URL si es válida; si no, primer canal disponible
  const activeConv = (() => {
    if (urlConvId) {
      const found = conversations.find(c => c.id === urlConvId)
      if (found) return found
    }
    if (conversations.length === 0) return null
    return conversations.find(c => c.kind === 'channel') || conversations[0]
  })()

  // Si la URL no trae conv pero ya hay conversaciones cargadas, fija la URL
  // por defecto (sin generar entrada nueva en el historial → replace).
  useEffect(() => {
    if (!urlConvId && activeConv?.id) {
      setSearchParams({ conv: activeConv.id }, { replace: true })
    }
  }, [urlConvId, activeConv?.id, setSearchParams])

  const setActiveConv = (c: Conv | null) => {
    if (!c?.id) return
    setSearchParams({ conv: c.id }, { replace: false })
    setMobileShowConv(true)
  }

  // Register Web Push subscription (best-effort, only if VAPID configured)
  useEffect(() => {
    registerCollabPush().catch(() => { /* accesorio: el aviso push es opcional (sin VAPID o sin permiso del navegador el chat funciona igual) */ })
  }, [])

  // Auto-presencia: online al cargar, away en blur, offline al cerrar
  // Sólo activa cuando hay sesión válida (user no nulo) para evitar 401
  // del cleanup tras logout.
  useEffect(() => {
    if (!user?.id) return
    let stopped = false
    const setStatus = (status: string) => {
      if (stopped) return
      collabApi.setPresence({ status }).catch(() => { /* accesorio: la presencia se reenvía en el siguiente cambio de visibilidad */ })
    }
    setStatus('online')
    const onVis = () => setStatus(document.visibilityState === 'visible' ? 'online' : 'away')
    const onBeforeUnload = () => {
      try {
        // sendBeacon y no el cliente: es lo único que sobrevive al cierre de la pestaña.
        navigator.sendBeacon(apiUrl('/collaboration/presence/me'), new Blob([JSON.stringify({ status: 'offline' })], { type: 'application/json' }))
      } catch { /* accesorio: la baja de presencia al cerrar es de mejor esfuerzo; el servidor la caduca solo */ }
    }
    // Listener para "logout" — cuando se dispara este evento dejamos de
    // mandar updates de presencia (evita 401 inútiles al servidor).
    const onLogout = () => { stopped = true }
    document.addEventListener('visibilitychange', onVis)
    window.addEventListener('beforeunload', onBeforeUnload)
    window.addEventListener('auth:session-expired', onLogout)
    window.addEventListener('auth:logout-start', onLogout)
    // Heartbeat
    const hb = setInterval(() => {
      if (!stopped && document.visibilityState === 'visible') setStatus('online')
    }, PRESENCE_POLL_MS)
    return () => {
      stopped = true
      document.removeEventListener('visibilitychange', onVis)
      window.removeEventListener('beforeunload', onBeforeUnload)
      window.removeEventListener('auth:session-expired', onLogout)
      window.removeEventListener('auth:logout-start', onLogout)
      clearInterval(hb)
      // No emitimos "away" en el cleanup: si el cleanup viene de un logout,
      // ya no hay sesión y la llamada daría 401.
    }
  }, [user?.id])

  // Global keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const isMac = navigator.platform.toUpperCase().includes('MAC')
      const cmd = isMac ? e.metaKey : e.ctrlKey
      if (!cmd) return
      if (e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setSearchModalOpen(true)
      } else if (e.key === '/') {
        e.preventDefault()
        const ta = document.querySelector('[data-chat-composer]') as HTMLTextAreaElement | null
        if (ta) { ta.focus(); ta.value = '/'; ta.dispatchEvent(new Event('input', { bubbles: true })) }
      } else if (e.shiftKey && e.key.toLowerCase() === 'a') {
        e.preventDefault()
        setActiveTab('activity')
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  // El WebSocket vive ahora en ChatRealtimeProvider (always-on, app-wide).
  // Aquí ya no se abre una conexión adicional para evitar duplicados; el
  // provider invalida React Query y reemite `collab:typing`/`collab:resync`.

  // ── Render ─────────────────────────────────────────────────────────────────
  const botonNueva = (
    <Button icon={<Plus size={14} />} onClick={() => setNewConvOpen(true)}>{traducir('chat.nueva_conversacion')}</Button>
  )

  return (
    <div className="chat-page">
    <div className="chat-page__head">
      <PageHeader
        icon={<MessageSquare size={18} />}
        title={traducir('nav.chat')}
        subtitle={traducir('chat.page_subtitle')}
        showListExport={false}
        actions={<>
          <Button variant="secondary" icon={<Search size={14} />} onClick={() => setSearchModalOpen(true)}>{traducir('chat.search_messages')}</Button>
          {botonNueva}
        </>}
      />
    </div>
    <div className="chat-root">
      {(!narrow || !mobileShowConv) && (<>
      <NavRail activeTab={activeTab} onTab={setActiveTab} unreadNotifs={notifications.filter(n => !n.is_read).length} />

      <ConversationsList
        narrow={narrow}
        activeTab={activeTab}
        conversations={conversations}
        teams={teams}
        channels={channels}
        presence={presence}
        loading={loadingConvs}
        activeConv={activeConv}
        onSelect={setActiveConv}
        newConvAction={botonNueva}
      />
      </>)}

      {(!narrow || mobileShowConv) && (
      <ConversationPane
        onBack={narrow ? () => setMobileShowConv(false) : undefined}
        newConvAction={botonNueva}
        conv={activeConv}
        currentUser={user}
        _bots={bots}
        draft={draft}
        setDraft={setDraft}
        showSlashMenu={showSlashMenu}
        setShowSlashMenu={setShowSlashMenu}
      />
      )}

      {activeConv && !narrow ? <ContextPanel conv={activeConv} /> : null}

      {searchModalOpen && (
        <SearchModal
          onClose={() => setSearchModalOpen(false)}
          onJump={(conversationId: string) => {
            const c = conversations.find(c => c.id === conversationId)
            if (c) setActiveConv(c)
            setSearchModalOpen(false)
          }}
        />
      )}

      {newConvOpen && (
        <NewConversationModal
          onClose={() => setNewConvOpen(false)}
          onCreated={(c) => { setNewConvOpen(false); setActiveConv(c) }}
        />
      )}
    </div>
    </div>
  )
}
