/**
 * CallPage — vista de videollamada (Mockup §6.2).
 *
 * Layout:
 *   header (room name + duration)
 *   video-grid (tiles)
 *   chat-lateral
 *   bottom-bar (mic/cam/share/grabar/subtítulos/participantes/salir)
 *
 * Conexión:
 *   - Si el backend devuelve un token LiveKit real (HS256) usamos `livekit-client`
 *     para conectar a la sala y publicar/suscribir tracks de los participantes.
 *   - En modo dev (token "dev:") cae a getUserMedia local para mostrar la
 *     cámara/mic propios sin LiveKit.
 *   - Telemetría QoS: lee `connectionQuality` de los participantes y degrada a
 *     audio-only automáticamente si la red baja a "poor".
 *   - Subtítulos: pipeline opcional vía collabApi.transcribeChunk (POST /collaboration/calls/{id}/transcribe-chunk)
 *     (envía chunks audio a Whisper si está habilitado).
 *   - Asistente de reuniones (19-11-2026): botón «Asistente» → aviso obligatorio →
 *     `/meeting-assistant/calls/{id}/activate`. Con él activo, cada navegador sube
 *     SU audio por el mismo `transcribe-chunk` (aunque los subtítulos estén
 *     apagados), salvo que la persona no consienta. Al colgar se analiza y el acta
 *     llega a la conversación.
 *   - Arreglo 19-11-2026: antes `recorder.start(5000)`; solo el primer trozo llevaba
 *     la cabecera WebM y el resto no se transcribía. Ahora se cierra y se abre el
 *     grabador cada 12 s (`useGrabacionPorTrozos`): cada trozo es un fichero completo.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import type { Ref } from 'react'
import type { Room, RemoteTrack } from 'livekit-client'
import { useParams, useSearchParams, useNavigate } from 'react-router-dom'
import {
  Mic, MicOff, Video, VideoOff, Monitor, Phone, MessageSquare,
  Captions, Disc, Users, X, Send, Hand, AudioLines,
  type LucideIcon,
} from 'lucide-react'
import { collabApi } from '../services/collaborationApi'
import { useAppT } from '../i18n/AppLangContext'
import { extractErr, localeActivo } from '../utils/helpers'
import StatusBadge from '../components/ui/StatusBadge'
import { CLOCK_TICK_MS } from '../constants/timings'
import './CallPage.css'
import { Input, Pulsable } from '../components/ui'
import { useGrabacionPorTrozos } from '../components/reuniones/grabacionPorTrozos'
import { BannerDelAsistente, ModalActivarAsistente, useAsistenteEnLlamada } from '../components/reuniones/AsistenteEnLlamada'

type TFn = (moduleOrFullKey: string, keyOrParams?: string | Record<string, unknown>) => string

interface ChatItem {
  time: string
  name: string
  body: string
  me: boolean
  reaction?: boolean
}
interface CaptionLine {
  name: string
  text: string
  ts: number
}
interface ParticipantInfo {
  id: string
  name: string
  audioOnly?: boolean
  raised?: boolean
  quality?: string
  local?: boolean
}

export default function CallPage(): JSX.Element {
  const t = useAppT()
  const { callId } = useParams<{ callId: string }>()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  // Auditoría 22-11-2026 (A4 del 04): las credenciales LiveKit NUNCA salen de la URL
  // (`?token=&url=&room=` dejaba el token en historial y Referer, y un enlace podía
  // llevar el cliente a un servidor LiveKit ajeno). Vienen de sessionStorage (las deja
  // ChatPage al abrir la ventana; se leen una vez, en el estado) o, si no están (recarga,
  // enlace), del servidor por la sala: POST /collaboration/calls/{id}/join.
  const [creds, setCreds] = useState<{ room?: string; url?: string; token?: string; kind?: string }>(() => {
    try {
      const raw = sessionStorage.getItem(`call_creds_${callId}`)
      if (raw) { sessionStorage.removeItem(`call_creds_${callId}`); return JSON.parse(raw) }
    } catch { /* accesorio: sessionStorage bloqueado; se piden al servidor */ }
    return {}
  })
  const [errorDeCredenciales, setErrorDeCredenciales] = useState<string | null>(null)
  useEffect(() => {
    if (creds.token || !callId) return
    let vivo = true
    collabApi.joinCall(callId)
      .then((c: { livekit_room?: string; livekit_url?: string; livekit_token?: string; kind?: string }) => {
        if (vivo) setCreds({ room: c.livekit_room, url: c.livekit_url, token: c.livekit_token, kind: c.kind })
      })
      .catch((e: unknown) => { if (vivo) setErrorDeCredenciales(extractErr(e, t('call.error_unirse'))) })
    return () => { vivo = false }
  }, [callId, creds.token, t])
  const livekitRoom = creds.room ?? null
  const livekitUrl = creds.url ?? null
  const livekitToken = creds.token ?? null
  // El tipo (vídeo/voz) sí puede venir en la URL: no es una credencial.
  const kind = creds.kind || params.get('kind') || 'video'
  const isLiveKitReal = !!livekitToken && !livekitToken.startsWith('dev:')

  const [muted, setMuted] = useState(false)
  const [cameraOff, setCameraOff] = useState(kind !== 'video')
  const [sharing, setSharing] = useState(false)
  const [recording, setRecording] = useState(false)
  const [captions, setCaptions] = useState(false)
  const [showChat, setShowChat] = useState(true)
  const [showParticipants, setShowParticipants] = useState(false)
  const [chatMsg, setChatMsg] = useState('')
  const [chatItems, setChatItems] = useState<ChatItem[]>([])
  const [duration, setDuration] = useState(0)
  const [participants, setParticipants] = useState<ParticipantInfo[]>([])  // {id, name, audioOnly, raised, quality}
  const [networkQuality, setNetworkQuality] = useState('excellent')
  const [autoFallback, setAutoFallback] = useState(false)
  const [captionLines, setCaptionLines] = useState<CaptionLine[]>([])
  // La pista local ya existe (sala conectada o getUserMedia hecho): arranca la grabación por trozos.
  const [audioListo, setAudioListo] = useState(0)
  const [modalAsistente, setModalAsistente] = useState(false)
  const asistente = useAsistenteEnLlamada(callId)

  const localVideoRef = useRef<HTMLVideoElement | null>(null)
  const localStreamRef = useRef<MediaStream | null>(null)
  const remoteRefs = useRef<Record<string, HTMLVideoElement>>({})  // identity -> HTMLVideoElement
   
  const roomRef = useRef<Room | null>(null)

  // ── Timer ──────────────────────────────────────────────────────────────────
  useEffect(() => {
    const startedAt = Date.now()
    const t = setInterval(() => setDuration(Math.floor((Date.now() - startedAt) / 1000)), CLOCK_TICK_MS)
    return () => clearInterval(t)
  }, [])

  // ── LiveKit connection (real) ──────────────────────────────────────────────
  useEffect(() => {
    if (!isLiveKitReal) return
    let mounted = true
     
    let room: Room | undefined

    ;(async () => {
      try {
        const lk = await import('livekit-client')
        const { Room, RoomEvent, Track, ConnectionQuality } = lk
        room = new Room({
          adaptiveStream: true,
          dynacast: true,
        })
        roomRef.current = room

        room.on(RoomEvent.ParticipantConnected, refreshParticipants)
        room.on(RoomEvent.ParticipantDisconnected, refreshParticipants)
        room.on(RoomEvent.ConnectionQualityChanged, (quality: string, p: { identity?: string }) => {
          if (p?.identity === room.localParticipant.identity) {
            setNetworkQuality(quality)
            // Auto-fallback a audio si la red baja
            if (quality === ConnectionQuality.Poor && !autoFallback) {
              setAutoFallback(true)
              try { room.localParticipant.setCameraEnabled(false) } catch { /* accesorio: limpieza o señal de la llamada; un fallo no cambia lo que ve el usuario */ }
            } else if (quality === ConnectionQuality.Excellent && autoFallback) {
              setAutoFallback(false)
            }
          }
          refreshParticipants()
        })
         
        room.on(RoomEvent.TrackSubscribed, (track: RemoteTrack, _pub: unknown, p: { identity: string }) => {
          if (track.kind === Track.Kind.Video) {
            const el = remoteRefs.current[p.identity]
            if (el) track.attach(el)
          } else if (track.kind === Track.Kind.Audio) {
            track.attach()
          }
        })
        room.on(RoomEvent.DataReceived, (payload: Uint8Array, p: { name?: string; identity?: string } | undefined) => {
          try {
            const decoded = new TextDecoder().decode(payload)
            const msg = JSON.parse(decoded)
            handleDataMessage(msg, p)
          } catch { /* accesorio: limpieza o señal de la llamada; un fallo no cambia lo que ve el usuario */ }
        })

        await room.connect(livekitUrl, livekitToken)
        if (!mounted) return
        if (kind === 'video') await room.localParticipant.setCameraEnabled(true)
        await room.localParticipant.setMicrophoneEnabled(true)
        setAudioListo(n => n + 1)

        // Attach local video
        const localTrack = Array.from(room.localParticipant.videoTrackPublications.values())
           
          .map(p => p.track).find(Boolean)
        if (localTrack && localVideoRef.current) localTrack.attach(localVideoRef.current)

        refreshParticipants()
      } catch (exc) {
        console.warn('LiveKit connect failed:', exc)
      }
    })()

    function refreshParticipants() {
      if (!roomRef.current) return
      const list: ParticipantInfo[] = []
      list.push({
        id: roomRef.current.localParticipant.identity,
        name: t('call.you'),
        audioOnly: !roomRef.current.localParticipant.isCameraEnabled,
        raised: false,
        quality: networkQuality,
        local: true,
      })
      for (const p of roomRef.current.remoteParticipants.values()) {
        list.push({
          id: p.identity,
          name: p.name || p.identity,
           
          audioOnly: !Array.from(p.videoTrackPublications.values()).some(pub => pub.track),
          raised: p.metadata?.includes('raised') || false,
          quality: p.connectionQuality,
        })
      }
      setParticipants(list)
    }

    function handleDataMessage(msg: { type?: string; body?: string; emoji?: string; text?: string }, sender: { name?: string; identity?: string } | undefined) {
      if (msg.type === 'chat') {
        setChatItems(prev => [...prev, {
          time: new Date().toLocaleTimeString(localeActivo(), { hour: '2-digit', minute: '2-digit' }),
          name: sender?.name || sender?.identity || t('call.other'),
          body: msg.body || '', me: false,
        }])
      } else if (msg.type === 'reaction') {
        setChatItems(prev => [...prev, {
          time: new Date().toLocaleTimeString(localeActivo(), { hour: '2-digit', minute: '2-digit' }),
          name: sender?.name || t('call.other'),
          body: `${t('call.reacted')} ${msg.emoji}`,
          me: false, reaction: true,
        }])
      } else if (msg.type === 'caption') {
        setCaptionLines(prev => [...prev.slice(-5), { name: sender?.name || t('call.other'), text: msg.text || '', ts: Date.now() }])
      }
    }

    return () => {
      mounted = false
      try { room?.disconnect() } catch { /* accesorio: limpieza o señal de la llamada; un fallo no cambia lo que ve el usuario */ }
      roomRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLiveKitReal, livekitUrl, livekitToken])

  // ── Local fallback (sin LiveKit) ───────────────────────────────────────────
  useEffect(() => {
    if (isLiveKitReal) return
    let mounted = true
    ;(async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: true,
          video: kind === 'video' ? { width: 640, height: 360 } : false,
        })
        if (!mounted) return
        localStreamRef.current = stream
        if (localVideoRef.current) localVideoRef.current.srcObject = stream
        setAudioListo(n => n + 1)
      } catch (e) { console.warn('getUserMedia:', e) }
    })()
    return () => {
      mounted = false
      if (localStreamRef.current) localStreamRef.current.getTracks().forEach(t => t.stop())
    }
  }, [kind, isLiveKitReal])

  // ── Toggle mic / cam ───────────────────────────────────────────────────────
  useEffect(() => {
    if (roomRef.current) { roomRef.current.localParticipant.setMicrophoneEnabled(!muted); return }
    if (localStreamRef.current) localStreamRef.current.getAudioTracks().forEach(t => (t.enabled = !muted))
  }, [muted])

  useEffect(() => {
    if (roomRef.current) { roomRef.current.localParticipant.setCameraEnabled(!cameraOff); return }
    if (localStreamRef.current) localStreamRef.current.getVideoTracks().forEach(t => (t.enabled = !cameraOff))
  }, [cameraOff])

  // ── Subtítulos y asistente de reuniones: audio propio por trozos completos ──
  const estadoAsistente = asistente.estado
  const subeParaAsistente = !!estadoAsistente?.active && estadoAsistente.my_consent !== false
  const captionsRef = useRef(captions)
  captionsRef.current = captions

  const obtenerAudioPropio = useCallback((): MediaStream | null => {
    if (roomRef.current) {
      const pistas = Array.from(roomRef.current.localParticipant.audioTrackPublications.values())
        .map(p => p.track?.mediaStreamTrack).filter((x): x is MediaStreamTrack => !!x)
      return pistas.length ? new MediaStream(pistas) : null
    }
    return localStreamRef.current ? new MediaStream(localStreamRef.current.getAudioTracks()) : null
  }, [])

  const subirTrozo = useCallback(async (trozo: Blob) => {
    if (!callId) return
    const fd = new FormData()
    fd.append('audio', trozo, 'chunk.webm')
    try {
      const data = await collabApi.transcribeChunk(callId, fd)
      // Los subtítulos solo se pintan (y se mandan a la sala) si están activados.
      if (data?.text && captionsRef.current) {
        setCaptionLines(prev => [...prev.slice(-5), { name: t('call.you'), text: data.text, ts: Date.now() }])
        if (roomRef.current) {
          const enc = new TextEncoder().encode(JSON.stringify({ type: 'caption', text: data.text }))
          roomRef.current.localParticipant.publishData(enc, { reliable: true })
        }
      }
    } catch { /* accesorio: limpieza o señal de la llamada; un fallo no cambia lo que ve el usuario */ }
    // `t` (traducciones) faltaba: al cambiar de idioma el callback seguía usando el anterior.
  }, [callId, t])

  useGrabacionPorTrozos({
    activo: captions || subeParaAsistente,
    obtenerStream: obtenerAudioPropio,
    onTrozo: trozo => { void subirTrozo(trozo) },
    duracionMs: 12_000,
    clave: audioListo,
  })

  const fmtDuration = (s: number) => {
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60
    return [h, m, sec].map(x => String(x).padStart(2, '0')).join(':')
  }

  const startScreenShare = async () => {
    try {
      if (roomRef.current) {
        await roomRef.current.localParticipant.setScreenShareEnabled(!sharing)
        setSharing(s => !s)
        return
      }
      const stream = await navigator.mediaDevices.getDisplayMedia({ video: true })
      if (localVideoRef.current) localVideoRef.current.srcObject = stream
      setSharing(true)
      stream.getVideoTracks()[0].onended = () => {
        setSharing(false)
        if (localStreamRef.current && localVideoRef.current) localVideoRef.current.srcObject = localStreamRef.current
      }
    } catch { /* user cancelled */ }
  }

  const toggleRecording = async () => {
    try {
      if (!recording) {
        await collabApi.startRecording(callId)
        setRecording(true)
      }
    } catch { /* accesorio: limpieza o señal de la llamada; un fallo no cambia lo que ve el usuario */ }
  }

  const raiseHand = () => {
    if (!roomRef.current) return
    const enc = new TextEncoder().encode(JSON.stringify({ type: 'reaction', emoji: '✋' }))
    roomRef.current.localParticipant.publishData(enc, { reliable: true })
    setChatItems(prev => [...prev, { time: now(), name: t('call.you'), body: `✋ ${t('call.raised_hand')}`, me: true, reaction: true }])
  }

  const sendChat = () => {
    if (!chatMsg.trim()) return
    const body = chatMsg
    setChatItems(prev => [...prev, { time: now(), me: true, name: t('call.you'), body }])
    setChatMsg('')
    if (roomRef.current) {
      const enc = new TextEncoder().encode(JSON.stringify({ type: 'chat', body }))
      roomRef.current.localParticipant.publishData(enc, { reliable: true })
    }
  }

  const leave = async () => {
    try { await collabApi.leaveCall(callId) } catch { /* accesorio: limpieza o señal de la llamada; un fallo no cambia lo que ve el usuario */ }
    try { roomRef.current?.disconnect() } catch { /* accesorio: limpieza o señal de la llamada; un fallo no cambia lo que ve el usuario */ }
    navigate(-1)
  }

  const endCall = async () => {
    try { await collabApi.endCall(callId) } catch { /* accesorio: limpieza o señal de la llamada; un fallo no cambia lo que ve el usuario */ }
    try { roomRef.current?.disconnect() } catch { /* accesorio: limpieza o señal de la llamada; un fallo no cambia lo que ve el usuario */ }
    navigate(-1)
  }

  const tilesToShow: ParticipantInfo[] = isLiveKitReal && participants.length > 0
    ? participants
    : [{ id: 'me', name: t('call.you'), local: true, audioOnly: cameraOff }, { id: 'wait1', name: t('call.waiting') }]

  return (
    <div className="call">
      <header className="call-header">
        <div>
          <h1 className="call-title">{t('call.meeting_title')}</h1>
          <div className="call-room">{t('call.room_label')} {livekitRoom?.slice(-12)}{isLiveKitReal ? ' · LiveKit' : ' · dev'}</div>
        </div>
        <div className="call-status">
          <QualityBadge q={networkQuality} fallback={autoFallback} t={t} />
          <span aria-label={t('call.duracion')}>{fmtDuration(duration)}</span>
        </div>
      </header>
      {errorDeCredenciales && <div role="alert" className="call-error">{errorDeCredenciales}</div>}

      {estadoAsistente?.active && (
        <BannerDelAsistente
          estado={estadoAsistente}
          onConsentir={si => asistente.consentir.mutate(si)}
          onParar={() => asistente.parar.mutate()}
          consintiendo={asistente.consentir.isPending}
          parando={asistente.parar.isPending}
        />
      )}

      <div className="call-main">
        <div className="call-grid">
          {tilesToShow.map(p => (
            <Tile key={p.id}
              name={p.name}
              hasVideo={p.local ? (kind === 'video' && !cameraOff) : !p.audioOnly}
              videoRef={p.local ? localVideoRef : (el) => { if (el) remoteRefs.current[p.id] = el }}
              raised={p.raised}
              quality={p.quality}
              t={t}
            />
          ))}
        </div>

        {captions && captionLines.length > 0 && (
          <div className="call-captions" aria-live="polite">
            {captionLines.slice(-2).map((c, i) => <div key={i}><b>{c.name}:</b> {c.text}</div>)}
          </div>
        )}

        {showChat && (
          <ChatLateral
            items={chatItems}
            value={chatMsg} onChange={setChatMsg} onSend={sendChat}
            onClose={() => setShowChat(false)}
            t={t}
          />
        )}
        {showParticipants && (
          <ParticipantsPanel onClose={() => setShowParticipants(false)} participants={participants} t={t} />
        )}
      </div>

      <div className="call-bar" role="toolbar" aria-label={t('call.controles')}>
        <CtrlBtn icon={muted ? MicOff : Mic} active={!muted} dangerWhenOff={muted} onClick={() => setMuted(m => !m)} label={muted ? t('call.activate_mic') : t('call.mute')} />
        <CtrlBtn icon={cameraOff ? VideoOff : Video} active={!cameraOff} dangerWhenOff={cameraOff} onClick={() => setCameraOff(c => !c)} label={cameraOff ? t('call.turn_on_camera') : t('call.turn_off_camera')} />
        <CtrlBtn icon={Monitor} active={sharing} onClick={startScreenShare} label={t('call.share_screen')} />
        <CtrlBtn icon={Hand} onClick={raiseHand} label={t('call.raise_hand')} />
        <CtrlBtn icon={Captions} active={captions} onClick={() => setCaptions(c => !c)} label={t('call.captions')} />
        <CtrlBtn icon={Disc} active={recording} onClick={toggleRecording} label={t('call.record')} />
        <CtrlBtn icon={AudioLines} active={!!estadoAsistente?.active}
          onClick={() => { if (!estadoAsistente?.active) setModalAsistente(true) }}
          label={estadoAsistente?.active ? t('reuniones.llamada.boton_activo') : t('reuniones.llamada.boton')} />
        <CtrlBtn icon={Users} active={showParticipants} onClick={() => setShowParticipants(p => !p)} label={t('call.participants')} />
        <CtrlBtn icon={MessageSquare} active={showChat} onClick={() => setShowChat(s => !s)} label={t('call.chat')} />
        <Pulsable type="button" onClick={leave} className="call-leave">
          <Phone size={14} className="call-leave__icon" aria-hidden="true" /> {t('call.leave')}
        </Pulsable>
        <Pulsable type="button" onClick={endCall} title={t('call.end_for_all_tooltip')} className="call-end">
          {t('call.end_for_all')}
        </Pulsable>
      </div>

      {modalAsistente && (
        <ModalActivarAsistente
          textoAviso={estadoAsistente?.notice_text}
          cargando={asistente.activar.isPending}
          onClose={() => setModalAsistente(false)}
          onActivar={() => asistente.activar.mutate(undefined, { onSuccess: () => setModalAsistente(false) })}
        />
      )}

      {!isLiveKitReal && (
        <div className="call-dev-warning" role="status">
          {t('call.dev_mode_warning')}
        </div>
      )}
    </div>
  )
}

function now() { return new Date().toLocaleTimeString(localeActivo(), { hour: '2-digit', minute: '2-digit' }) }

function etiquetaCalidad(q: string, t: TFn): string {
  const claves: Record<string, string> = {
    excellent: 'call.quality_excellent',
    good: 'call.quality_good',
    poor: 'call.quality_poor',
    lost: 'call.quality_lost',
  }
  return claves[q] ? t(claves[q]) : q
}

function QualityBadge({ q, fallback, t }: { q: string; fallback: boolean; t: TFn }) {
  const colores: Record<string, string> = {
    excellent: 'var(--success)',
    good: 'var(--success)',
    poor: 'var(--warning)',
    lost: 'var(--call-danger)',
  }
  const clave = colores[q] ? q : 'excellent'
  return (
    <StatusBadge color={colores[clave]} dot caps={false}>
      {etiquetaCalidad(clave, t)}{fallback ? ` · ${t('call.audio_only_suffix')}` : ''}
    </StatusBadge>
  )
}

function Tile({ name, hasVideo, videoRef, raised, quality, t }: {
  name?: string
  hasVideo?: boolean
  videoRef: Ref<HTMLVideoElement> | ((el: HTMLVideoElement | null) => void)
  raised?: boolean
  quality?: string
  t: TFn
}) {
  return (
    <div className="call-tile">
      {hasVideo ? (
        <video ref={videoRef} aria-label={name} autoPlay muted playsInline className="call-tile__video" />
      ) : (
        <div className="call-avatar call-avatar--lg" aria-hidden="true">{name?.charAt(0)?.toUpperCase() || '?'}</div>
      )}
      {raised && (
        <div className="call-tile__hand" role="img" aria-label={t('call.raised_hand')}>✋</div>
      )}
      {quality && quality !== 'excellent' && (
        <div className="call-tile__quality">
          {etiquetaCalidad(quality, t)}
        </div>
      )}
      <div className="call-tile__name">
        {name}
      </div>
    </div>
  )
}

function CtrlBtn({ icon: Icon, active, onClick, label, dangerWhenOff }: {
  icon: LucideIcon
  active?: boolean
  onClick: () => void
  label: string
  dangerWhenOff?: boolean
}) {
  const estado = dangerWhenOff ? 'call-ctrl call-ctrl--danger' : (active ? 'call-ctrl call-ctrl--active' : 'call-ctrl')
  return (
    <Pulsable type="button" aria-label={label} onClick={onClick} title={label} className={estado}>
      <Icon size={16} aria-hidden="true" />
    </Pulsable>
  )
}

function ChatLateral({ items, value, onChange, onSend, onClose, t }: {
  items: ChatItem[]
  value: string
  onChange: (v: string) => void
  onSend: () => void
  onClose: () => void
  t: TFn
}) {
  return (
    <aside className="call-side" aria-label={t('call.meeting_chat')}>
      <div className="call-side__head">
        <h2 className="call-side__title">{t('call.meeting_chat')}</h2>
        <Pulsable type="button" onClick={onClose} className="call-side__close" aria-label={t('call.cerrar_chat')} title={t('call.cerrar_chat')}><X size={14} aria-hidden="true" /></Pulsable>
      </div>
      <div className="call-side__body" aria-live="polite">
        {items.length === 0 && <div className="call-side__empty">{t('call.no_messages_yet')}</div>}
        {items.map((m, i) => (
          <div key={i} className="u-mb-10">
            <div className="call-msg__meta">{m.time} {m.name}</div>
            <div className="call-msg__body">{m.body}</div>
          </div>
        ))}
      </div>
      <div className="call-side__form">
        <Input aria-label={t('call.write_placeholder')} value={value} onChange={e => onChange(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') onSend() }}
          placeholder={t('call.write_placeholder')}
          className="u-flex1-min0" inputClassName="call-side__input" />
        <Pulsable type="button" onClick={onSend} className="call-side__send" aria-label={t('call.enviar')} title={t('call.enviar')}><Send size={13} aria-hidden="true" /></Pulsable>
      </div>
    </aside>
  )
}

function ParticipantsPanel({ onClose, participants, t }: {
  onClose: () => void
  participants: ParticipantInfo[]
  t: TFn
}) {
  return (
    <aside className="call-side call-side--narrow" aria-label={t('call.participants')}>
      <div className="call-side__head">
        <h2 className="call-side__title">{t('call.participants')} ({participants.length})</h2>
        <Pulsable type="button" onClick={onClose} className="call-side__close" aria-label={t('call.cerrar_participantes')} title={t('call.cerrar_participantes')}><X size={14} aria-hidden="true" /></Pulsable>
      </div>
      {participants.length === 0 && <div className="call-side__body call-side__empty">{t('call.waiting_participants')}</div>}
      {participants.length > 0 && (
        <ul className="call-people">
          {participants.map(p => (
            <li key={p.id} className="call-person">
              <span className="call-avatar call-avatar--sm" aria-hidden="true">{(p.name||'?').charAt(0).toUpperCase()}</span>
              <span className="u-flex1">{p.name}{p.local ? ` (${t('call.you_lower')})` : ''}</span>
              {p.raised && <span role="img" aria-label={t('call.raised_hand')}>✋</span>}
              {p.audioOnly && <Mic size={11} className="call-person__audio" aria-label={t('call.solo_audio')} />}
            </li>
          ))}
        </ul>
      )}
    </aside>
  )
}
