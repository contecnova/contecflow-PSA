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
 *   - Subtítulos: pipeline opcional vía /api/v1/collaboration/calls/{id}/transcribe-chunk
 *     (envía chunks audio a Whisper si está habilitado).
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams, useSearchParams, useNavigate } from 'react-router-dom'
import {
  Mic, MicOff, Video, VideoOff, Monitor, Phone, MessageSquare,
  Captions, Disc, Users, X, Send, Hand,
} from 'lucide-react'
import { collabApi } from '../services/collaborationApi'

export default function CallPage() {
  const { callId } = useParams()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  // Leer credenciales desde sessionStorage (nunca desde URL) y limpiar inmediatamente
  const _stored = (() => {
    try {
      const raw = sessionStorage.getItem(`call_creds_${callId}`)
      if (raw) { sessionStorage.removeItem(`call_creds_${callId}`); return JSON.parse(raw) }
    } catch { /* noop */ }
    return {}
  })()
  const livekitRoom = _stored.room || params.get('room')
  const livekitUrl = _stored.url || params.get('url')
  const livekitToken = _stored.token || params.get('token')
  const kind = _stored.kind || params.get('kind') || 'video'
  const isLiveKitReal = !!livekitToken && !livekitToken.startsWith('dev:')

  const [muted, setMuted] = useState(false)
  const [cameraOff, setCameraOff] = useState(kind !== 'video')
  const [sharing, setSharing] = useState(false)
  const [recording, setRecording] = useState(false)
  const [captions, setCaptions] = useState(false)
  const [showChat, setShowChat] = useState(true)
  const [showParticipants, setShowParticipants] = useState(false)
  const [chatMsg, setChatMsg] = useState('')
  const [chatItems, setChatItems] = useState([])
  const [duration, setDuration] = useState(0)
  const [participants, setParticipants] = useState([])  // {id, name, audioOnly, raised, quality}
  const [networkQuality, setNetworkQuality] = useState('excellent')
  const [autoFallback, setAutoFallback] = useState(false)
  const [captionLines, setCaptionLines] = useState([])

  const localVideoRef = useRef(null)
  const localStreamRef = useRef(null)
  const remoteRefs = useRef({})  // identity -> HTMLVideoElement
  const roomRef = useRef(null)
  const recorderRef = useRef(null)

  // ── Timer ──────────────────────────────────────────────────────────────────
  useEffect(() => {
    const startedAt = Date.now()
    const t = setInterval(() => setDuration(Math.floor((Date.now() - startedAt) / 1000)), 1000)
    return () => clearInterval(t)
  }, [])

  // ── LiveKit connection (real) ──────────────────────────────────────────────
  useEffect(() => {
    if (!isLiveKitReal) return
    let mounted = true
    let room

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
        room.on(RoomEvent.ConnectionQualityChanged, (quality, p) => {
          if (p?.identity === room.localParticipant.identity) {
            setNetworkQuality(quality)
            // Auto-fallback a audio si la red baja
            if (quality === ConnectionQuality.Poor && !autoFallback) {
              setAutoFallback(true)
              try { room.localParticipant.setCameraEnabled(false) } catch { /* noop */ }
            } else if (quality === ConnectionQuality.Excellent && autoFallback) {
              setAutoFallback(false)
            }
          }
          refreshParticipants()
        })
        room.on(RoomEvent.TrackSubscribed, (track, _pub, p) => {
          if (track.kind === Track.Kind.Video) {
            const el = remoteRefs.current[p.identity]
            if (el) track.attach(el)
          } else if (track.kind === Track.Kind.Audio) {
            track.attach()
          }
        })
        room.on(RoomEvent.DataReceived, (payload, p) => {
          try {
            const decoded = new TextDecoder().decode(payload)
            const msg = JSON.parse(decoded)
            handleDataMessage(msg, p)
          } catch { /* noop */ }
        })

        await room.connect(livekitUrl, livekitToken)
        if (!mounted) return
        if (kind === 'video') await room.localParticipant.setCameraEnabled(true)
        await room.localParticipant.setMicrophoneEnabled(true)

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
      const list = []
      list.push({
        id: roomRef.current.localParticipant.identity,
        name: 'Tú',
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

    function handleDataMessage(msg, sender) {
      if (msg.type === 'chat') {
        setChatItems(prev => [...prev, {
          time: new Date().toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' }),
          name: sender?.name || sender?.identity || 'Otro',
          body: msg.body, me: false,
        }])
      } else if (msg.type === 'reaction') {
        setChatItems(prev => [...prev, {
          time: new Date().toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' }),
          name: sender?.name || 'Otro',
          body: `reaccionó ${msg.emoji}`,
          me: false, reaction: true,
        }])
      } else if (msg.type === 'caption') {
        setCaptionLines(prev => [...prev.slice(-5), { name: sender?.name || 'Otro', text: msg.text, ts: Date.now() }])
      }
    }

    return () => {
      mounted = false
      try { room?.disconnect() } catch { /* noop */ }
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

  // ── Subtitles via Whisper ──────────────────────────────────────────────────
  const startCaptions = useCallback(async () => {
    if (!localStreamRef.current && !roomRef.current) return
    try {
      const stream = roomRef.current
        ? new MediaStream([
            ...Array.from(roomRef.current.localParticipant.audioTrackPublications.values())
              .map(p => p.track?.mediaStreamTrack).filter(Boolean),
          ])
        : new MediaStream(localStreamRef.current.getAudioTracks())
      const recorder = new MediaRecorder(stream, { mimeType: 'audio/webm' })
      recorderRef.current = recorder
      const chunks = []
      recorder.ondataavailable = async (e) => {
        if (e.data.size === 0) return
        chunks.push(e.data)
        if (chunks.length >= 1) {
          const blob = new Blob(chunks.splice(0), { type: 'audio/webm' })
          const fd = new FormData()
          fd.append('audio', blob, 'chunk.webm')
          try {
            // #45: kept as fetch() — side-effects/realtime/optimistic
            const r = await fetch(`/api/v1/collaboration/calls/${callId}/transcribe-chunk`, {
              method: 'POST', body: fd, credentials: 'include',
            })
            const data = await r.json()
            if (data?.text) {
              setCaptionLines(prev => [...prev.slice(-5), { name: 'Tú', text: data.text, ts: Date.now() }])
              if (roomRef.current) {
                const enc = new TextEncoder().encode(JSON.stringify({ type: 'caption', text: data.text }))
                roomRef.current.localParticipant.publishData(enc, { reliable: true })
              }
            }
          } catch { /* noop */ }
        }
      }
      recorder.start(5000)  // chunk de 5s
    } catch (e) { console.warn('captions:', e) }
  }, [callId])

  useEffect(() => {
    if (captions) startCaptions()
    else { try { recorderRef.current?.stop() } catch { /* noop */ } }
  }, [captions, startCaptions])

  const fmtDuration = (s) => {
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
    } catch { /* noop */ }
  }

  const raiseHand = () => {
    if (!roomRef.current) return
    const enc = new TextEncoder().encode(JSON.stringify({ type: 'reaction', emoji: '✋' }))
    roomRef.current.localParticipant.publishData(enc, { reliable: true })
    setChatItems(prev => [...prev, { time: now(), name: 'Tú', body: '✋ levantaste la mano', me: true, reaction: true }])
  }

  const sendChat = () => {
    if (!chatMsg.trim()) return
    const body = chatMsg
    setChatItems(prev => [...prev, { time: now(), me: true, name: 'Tú', body }])
    setChatMsg('')
    if (roomRef.current) {
      const enc = new TextEncoder().encode(JSON.stringify({ type: 'chat', body }))
      roomRef.current.localParticipant.publishData(enc, { reliable: true })
    }
  }

  const leave = async () => {
    try { await collabApi.leaveCall(callId) } catch { /* noop */ }
    try { roomRef.current?.disconnect() } catch { /* noop */ }
    navigate(-1)
  }

  const endCall = async () => {
    try { await collabApi.endCall(callId) } catch { /* noop */ }
    try { roomRef.current?.disconnect() } catch { /* noop */ }
    navigate(-1)
  }

  const tilesToShow = isLiveKitReal && participants.length > 0
    ? participants
    : [{ id: 'me', name: 'Tú', local: true, audioOnly: cameraOff }, { id: 'wait1', name: 'Esperando…' }]

  return (
    <div style={{
      minHeight: '100vh', display: 'flex', flexDirection: 'column',
      background: '#0a0d14', color: '#fff', fontFamily: "'Inter', system-ui, sans-serif",
    }}>
      <div style={{
        height: 56, padding: '0 22px', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        borderBottom: '1px solid rgba(255,255,255,0.08)',
      }}>
        <div>
          <div style={{ fontSize: 14, fontWeight: 700 }}>Reunión Contecflow</div>
          <div style={{ fontSize: 11, color: '#94a3b8' }}>Sala {livekitRoom?.slice(-12)}{isLiveKitReal ? ' · LiveKit' : ' · dev'}</div>
        </div>
        <div style={{ display: 'flex', gap: 14, alignItems: 'center', fontFamily: 'var(--font-mono)', fontSize: 14, color: '#e0e7ff' }}>
          <QualityBadge q={networkQuality} fallback={autoFallback} />
          <span>{fmtDuration(duration)}</span>
        </div>
      </div>

      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
        <div style={{ flex: 1, padding: 18, display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: 12, alignContent: 'start' }}>
          {tilesToShow.map(p => (
            <Tile key={p.id}
              name={p.name}
              hasVideo={p.local ? (kind === 'video' && !cameraOff) : !p.audioOnly}
              videoRef={p.local ? localVideoRef : (el) => { if (el) remoteRefs.current[p.id] = el }}
              raised={p.raised}
              quality={p.quality}
            />
          ))}
        </div>

        {captions && captionLines.length > 0 && (
          <div style={{
            position: 'absolute', bottom: 100, left: '50%', transform: 'translateX(-50%)',
            background: 'rgba(0,0,0,0.7)', color: '#fff', padding: '8px 14px', borderRadius: 10,
            maxWidth: '70%', fontSize: 14, lineHeight: 1.4,
          }}>
            {captionLines.slice(-2).map((c, i) => <div key={i}><b>{c.name}:</b> {c.text}</div>)}
          </div>
        )}

        {showChat && (
          <ChatLateral
            items={chatItems}
            value={chatMsg} onChange={setChatMsg} onSend={sendChat}
            onClose={() => setShowChat(false)}
          />
        )}
        {showParticipants && (
          <ParticipantsPanel onClose={() => setShowParticipants(false)} participants={participants} />
        )}
      </div>

      <div style={{
        height: 76, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 14,
        background: '#0e1322', borderTop: '1px solid rgba(255,255,255,0.08)',
      }}>
        <CtrlBtn icon={muted ? MicOff : Mic} active={!muted} dangerWhenOff={muted} onClick={() => setMuted(m => !m)} label={muted ? 'Activar mic' : 'Silenciar'} />
        <CtrlBtn icon={cameraOff ? VideoOff : Video} active={!cameraOff} dangerWhenOff={cameraOff} onClick={() => setCameraOff(c => !c)} label={cameraOff ? 'Encender cámara' : 'Apagar cámara'} />
        <CtrlBtn icon={Monitor} active={sharing} onClick={startScreenShare} label="Compartir pantalla" />
        <CtrlBtn icon={Hand} onClick={raiseHand} label="Levantar mano" />
        <CtrlBtn icon={Captions} active={captions} onClick={() => setCaptions(c => !c)} label="Subtítulos" />
        <CtrlBtn icon={Disc} active={recording} onClick={toggleRecording} label="Grabar" />
        <CtrlBtn icon={Users} active={showParticipants} onClick={() => setShowParticipants(p => !p)} label="Participantes" />
        <CtrlBtn icon={MessageSquare} active={showChat} onClick={() => setShowChat(s => !s)} label="Chat" />
        <button onClick={leave} style={{
          display: 'inline-flex', alignItems: 'center', gap: 6,
          height: 44, padding: '0 18px', borderRadius: 22,
          background: '#dc2626', color: '#fff', border: 'none',
          cursor: 'pointer', fontFamily: 'inherit', fontSize: 13, fontWeight: 700,
        }}>
          <Phone size={14} style={{ transform: 'rotate(135deg)' }} /> Salir
        </button>
        <button onClick={endCall} title="Cerrar para todos" style={{
          height: 44, padding: '0 14px', borderRadius: 22,
          background: 'transparent', color: '#fca5a5', border: '1px solid #b91c1c',
          cursor: 'pointer', fontFamily: 'inherit', fontSize: 12, fontWeight: 700,
        }}>
          Finalizar para todos
        </button>
      </div>

      {!isLiveKitReal && (
        <div style={{ position: 'absolute', top: 70, right: 16, padding: '8px 12px', background: 'rgba(245,158,11,0.15)', border: '1px solid rgba(245,158,11,0.4)', borderRadius: 8, fontSize: 11, maxWidth: 320, color: '#fcd34d' }}>
          Modo dev: cámara y micrófono locales. Para llamadas multi-usuario configura LIVEKIT_API_KEY/SECRET/URL en backend.
        </div>
      )}
    </div>
  )
}

function now() { return new Date().toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' }) }

function QualityBadge({ q, fallback }) {
  const map = {
    excellent: { color: '#10b981', label: 'Excelente' },
    good: { color: '#34d399', label: 'Buena' },
    poor: { color: '#f59e0b', label: 'Mala' },
    lost: { color: '#dc2626', label: 'Perdida' },
  }
  const m = map[q] || map.excellent
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 6,
      padding: '3px 10px', borderRadius: 999,
      background: `${m.color}25`, color: m.color, fontSize: 11, fontWeight: 700,
    }}>
      ●  {m.label}{fallback ? ' · audio-only' : ''}
    </span>
  )
}

function Tile({ name, hasVideo, videoRef, raised, quality }) {
  return (
    <div style={{
      aspectRatio: '16 / 9', borderRadius: 14, overflow: 'hidden',
      position: 'relative', background: '#1f2738',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      {hasVideo ? (
        <video ref={videoRef} autoPlay muted playsInline
          style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
      ) : (
        <div style={{
          width: 96, height: 96, borderRadius: '50%',
          background: 'linear-gradient(135deg, #4f8ef7, #7c3aed)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 32, fontWeight: 800,
        }}>{name?.charAt(0)?.toUpperCase() || '?'}</div>
      )}
      {raised && (
        <div style={{ position: 'absolute', top: 10, right: 10, fontSize: 22 }}>✋</div>
      )}
      {quality && quality !== 'excellent' && (
        <div style={{ position: 'absolute', top: 10, left: 10, padding: '2px 8px', background: 'rgba(245,158,11,0.85)', color: '#000', fontSize: 10, fontWeight: 800, borderRadius: 999 }}>
          {quality}
        </div>
      )}
      <div style={{ position: 'absolute', bottom: 10, left: 12, padding: '3px 10px', borderRadius: 999, background: 'rgba(0,0,0,0.55)', fontSize: 12, fontWeight: 600 }}>
        {name}
      </div>
    </div>
  )
}

function CtrlBtn({ icon: Icon, active, onClick, label, dangerWhenOff }) {
  const bg = dangerWhenOff ? '#dc2626' : (active ? '#4f8ef7' : '#1f2738')
  return (
    <button onClick={onClick} title={label} style={{
      width: 44, height: 44, borderRadius: 22,
      display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
      background: bg, color: '#fff', border: 'none', cursor: 'pointer',
    }}>
      <Icon size={16} />
    </button>
  )
}

function ChatLateral({ items, value, onChange, onSend, onClose }) {
  return (
    <div style={{ width: 320, borderLeft: '1px solid rgba(255,255,255,0.08)', display: 'flex', flexDirection: 'column' }}>
      <div style={{ height: 44, display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 14px', borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
        <span style={{ fontWeight: 700, fontSize: 13 }}>Chat de la reunión</span>
        <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#cbd5e1' }}><X size={14} /></button>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: '12px 14px' }}>
        {items.length === 0 && <div style={{ fontSize: 12, color: '#94a3b8' }}>Sin mensajes aún</div>}
        {items.map((m, i) => (
          <div key={i} style={{ marginBottom: 10 }}>
            <div style={{ fontSize: 11, color: '#94a3b8' }}>{m.time} {m.name}</div>
            <div style={{ fontSize: 13 }}>{m.body}</div>
          </div>
        ))}
      </div>
      <div style={{ padding: 10, borderTop: '1px solid rgba(255,255,255,0.08)', display: 'flex', gap: 6 }}>
        <input value={value} onChange={e => onChange(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && onSend()}
          placeholder="Escribe…"
          style={{
            flex: 1, padding: '8px 10px',
            background: '#1f2738', border: '1px solid #2c3a55', borderRadius: 8,
            color: '#fff', fontSize: 12, outline: 'none', fontFamily: 'inherit',
          }} />
        <button onClick={onSend} style={{
          width: 32, height: 32, borderRadius: 8, border: 'none',
          background: '#4f8ef7', color: '#fff', cursor: 'pointer',
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        }}><Send size={13} /></button>
      </div>
    </div>
  )
}

function ParticipantsPanel({ onClose, participants }) {
  return (
    <div style={{ width: 280, borderLeft: '1px solid rgba(255,255,255,0.08)', display: 'flex', flexDirection: 'column' }}>
      <div style={{ height: 44, display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 14px', borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
        <span style={{ fontWeight: 700, fontSize: 13 }}>Participantes ({participants.length})</span>
        <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#cbd5e1' }}><X size={14} /></button>
      </div>
      <div style={{ padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 8 }}>
        {participants.length === 0 && <div style={{ fontSize: 12, color: '#94a3b8' }}>Esperando participantes…</div>}
        {participants.map(p => (
          <div key={p.id} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
            <span style={{ width: 22, height: 22, borderRadius: '50%', background: 'linear-gradient(135deg,#4f8ef7,#7c3aed)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 10, fontWeight: 800 }}>{(p.name||'?').charAt(0).toUpperCase()}</span>
            <span style={{ flex: 1 }}>{p.name}{p.local ? ' (tú)' : ''}</span>
            {p.raised && <span>✋</span>}
            {p.audioOnly && <Mic size={11} style={{ color: '#94a3b8' }} />}
          </div>
        ))}
      </div>
    </div>
  )
}
