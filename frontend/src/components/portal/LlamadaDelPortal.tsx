/**
 * Llamada o videollamada del chat del portal (24-11-2026, docs/portal/CHAT_DEL_PORTAL.md).
 *
 * La misma conexión que la videollamada del chat interno (`pages/CallPage.tsx`):
 * `livekit-client` con el token que da el servidor; sin LiveKit configurado
 * (token `dev:`, solo en desarrollo) se ve la cámara propia y un aviso. Aquí
 * solo lo que necesita una llamada operador-cliente: vídeo propio y remoto,
 * micrófono, cámara y colgar. Sin grabación, subtítulos ni asistente: el aviso
 * «esta llamada no se graba» se enseña siempre.
 *
 * Quién la abre: el equipo al llamar o al entrar en una en curso; el cliente al
 * ACEPTAR (no puede iniciarla: lo impone el servidor).
 */
import { useEffect, useRef, useState } from 'react'
import type { RemoteTrack, Room } from 'livekit-client'
import { Mic, MicOff, PhoneOff, ShieldCheck, Video, VideoOff } from 'lucide-react'
import { Button, IconButton, Modal } from '../ui'
import type { PortalLlamada } from '../../services/api/tipos-alm'

type T = (clave: string, vars?: Record<string, string | number>) => string

interface Props {
  llamada: PortalLlamada
  /** Lo que ve en la cabecera (título de la conversación). */
  titulo: string
  esperando?: boolean
  onColgar: () => void
  t: T
}

interface Remoto { identidad: string; nombre: string }

export default function LlamadaDelPortal({ llamada, titulo, esperando, onColgar, t }: Props) {
  const video = llamada.kind === 'video'
  const token = llamada.livekit_token || ''
  const real = !!token && !token.startsWith('dev:') && !!llamada.livekit_url
  const [micro, setMicro] = useState(true)
  const [camara, setCamara] = useState(video)
  const [remotos, setRemotos] = useState<Remoto[]>([])
  const [conectada, setConectada] = useState(false)
  const propio = useRef<HTMLVideoElement | null>(null)
  const sala = useRef<Room | null>(null)
  const flujo = useRef<MediaStream | null>(null)
  const elementos = useRef<Record<string, HTMLVideoElement | null>>({})
  const pistas = useRef<Record<string, RemoteTrack>>({})

  // ── LiveKit (como CallPage) ────────────────────────────────────────────────
  useEffect(() => {
    if (!real) return undefined
    let vivo = true
    let room: Room | undefined
    ;(async () => {
      try {
        const lk = await import('livekit-client')
        room = new lk.Room({ adaptiveStream: true, dynacast: true })
        sala.current = room
        const refrescar = () => {
          if (!room) return
          setRemotos(Array.from(room.remoteParticipants.values()).map(p => ({ identidad: p.identity, nombre: p.name || p.identity })))
        }
        room.on(lk.RoomEvent.ParticipantConnected, refrescar)
        room.on(lk.RoomEvent.ParticipantDisconnected, refrescar)
        room.on(lk.RoomEvent.TrackSubscribed, (track: RemoteTrack, _pub: unknown, p: { identity: string }) => {
          if (track.kind === lk.Track.Kind.Video) {
            pistas.current[p.identity] = track
            const el = elementos.current[p.identity]
            if (el) track.attach(el)
          } else if (track.kind === lk.Track.Kind.Audio) {
            track.attach()
          }
          refrescar()
        })
        await room.connect(llamada.livekit_url as string, token)
        if (!vivo) return
        await room.localParticipant.setMicrophoneEnabled(true)
        if (video) await room.localParticipant.setCameraEnabled(true)
        const local = Array.from(room.localParticipant.videoTrackPublications.values()).map(p => p.track).find(Boolean)
        if (local && propio.current) local.attach(propio.current)
        setConectada(true)
        refrescar()
      } catch (e) {
        console.warn('LiveKit (portal):', e)
      }
    })()
    return () => {
      vivo = false
      try { room?.disconnect() } catch { /* accesorio: la sala se cierra igualmente al colgar */ }
      sala.current = null
    }
  }, [real, llamada.livekit_url, token, video])

  // ── Sin LiveKit (desarrollo): cámara y micro propios ───────────────────────
  useEffect(() => {
    if (real) return undefined
    let vivo = true
    navigator.mediaDevices?.getUserMedia({ audio: true, video: video ? { width: 640, height: 360 } : false })
      .then(stream => {
        if (!vivo) { stream.getTracks().forEach(p => p.stop()); return }
        flujo.current = stream
        if (propio.current) propio.current.srcObject = stream
      })
      .catch(e => console.warn('getUserMedia (portal):', e))
    return () => {
      vivo = false
      flujo.current?.getTracks().forEach(p => p.stop())
      flujo.current = null
    }
  }, [real, video])

  useEffect(() => {
    if (sala.current) { void sala.current.localParticipant.setMicrophoneEnabled(micro); return }
    flujo.current?.getAudioTracks().forEach(p => { p.enabled = micro })
  }, [micro])

  useEffect(() => {
    if (sala.current) { void sala.current.localParticipant.setCameraEnabled(camara); return }
    flujo.current?.getVideoTracks().forEach(p => { p.enabled = camara })
  }, [camara])

  const estado = esperando ? t('governedconversations.llamando') : (conectada || !real) ? t('governedconversations.en_llamada') : t('common.loading')

  return (
    <Modal open onClose={onColgar} title={titulo} subtitle={estado} size="lg" avisarSinGuardar={false}>
      <div className="chat-portal-llamada">
        <p className="chat-portal-llamada__aviso" role="note">
          <ShieldCheck size={14} aria-hidden="true" /> {t('governedconversations.llamada_no_se_graba')}
        </p>
        {!real && <p className="chat-portal-llamada__aviso" role="note">{t('governedconversations.modo_desarrollo_llamada')}</p>}
        <div className={`chat-portal-llamada__rejilla${video ? '' : ' chat-portal-llamada__rejilla--voz'}`}>
          <div className="chat-portal-llamada__tile">
            <video ref={propio} autoPlay muted playsInline className={video && camara ? '' : 'chat-portal-oculto'} aria-label={t('governedconversations.tu_video')} />
            {!(video && camara) && <span className="chat-portal-llamada__inicial" aria-hidden="true">{t('governedconversations.tu')}</span>}
          </div>
          {remotos.map(r => (
            <div key={r.identidad} className="chat-portal-llamada__tile">
              <video autoPlay playsInline aria-label={r.nombre}
                ref={el => {
                  elementos.current[r.identidad] = el
                  const pista = pistas.current[r.identidad]
                  if (el && pista) pista.attach(el)
                }} />
              <span className="chat-portal-llamada__nombre">{r.nombre}</span>
            </div>
          ))}
        </div>
        <div className="chat-portal-llamada__controles" role="toolbar" aria-label={t('governedconversations.controles_llamada')}>
          <IconButton variante="caja" tamano="md" onClick={() => setMicro(v => !v)}
            ariaLabel={micro ? t('governedconversations.silenciar') : t('governedconversations.activar_micro')} aria-pressed={!micro}>
            {micro ? <Mic size={16} aria-hidden="true" /> : <MicOff size={16} aria-hidden="true" />}
          </IconButton>
          {video && (
            <IconButton variante="caja" tamano="md" onClick={() => setCamara(v => !v)}
              ariaLabel={camara ? t('governedconversations.apagar_camara') : t('governedconversations.encender_camara')} aria-pressed={!camara}>
              {camara ? <Video size={16} aria-hidden="true" /> : <VideoOff size={16} aria-hidden="true" />}
            </IconButton>
          )}
          <Button variant="danger" icon={<PhoneOff size={14} />} onClick={onColgar}>{t('governedconversations.colgar')}</Button>
        </div>
      </div>
    </Modal>
  )
}
