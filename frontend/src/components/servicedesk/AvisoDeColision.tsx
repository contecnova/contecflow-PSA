/**
 * AvisoDeColision — quién más está en este ticket ahora mismo, y si está
 * escribiendo (mejoras de mercado 16-11-2026).
 *
 * Usa el WebSocket de avisos (`/ws/notifications`, con su ticket de un solo
 * uso): manda `ticket_presence` al abrir, cada latido y al irse, y recibe la
 * lista de quién hay. El latido es un tercio de la caducidad que manda el
 * servidor (`SD_PRESENCE_TTL_SECONDS`). Sin WebSocket no avisa, pero no rompe.
 */
import { useEffect, useRef, useState } from 'react'
import { Users } from 'lucide-react'
import { useAppT } from '../../i18n/AppLangContext'
import { useAuth } from '../../context/AuthContext'
import { wsApi } from '../../services/api/_core'
import { apiWsUrl } from '../../services/api/urls'
import './sdMercado.css'

interface Presente { user_id: string; name: string | null; mode: 'view' | 'edit' }
/** Hasta que el servidor diga su caducidad, latido conservador (ms). */
const LATIDO_INICIAL_MS = 15000

export default function AvisoDeColision({ ticketId, escribiendo }: { ticketId: string; escribiendo: boolean }) {
  const t = useAppT()
  const { user } = useAuth()
  const [presentes, setPresentes] = useState<Presente[]>([])
  const wsRef = useRef<WebSocket | null>(null)
  const modoRef = useRef<'view' | 'edit'>('view')
  const latidoRef = useRef(LATIDO_INICIAL_MS)

  const enviar = (mode: 'view' | 'edit' | 'leave') => {
    const ws = wsRef.current
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'ticket_presence', ticket_id: ticketId, mode }))
  }

  useEffect(() => {
    let cerrado = false
    let temporizador: ReturnType<typeof setTimeout> | null = null
    const latir = () => {
      enviar(modoRef.current)
      temporizador = setTimeout(latir, latidoRef.current)
    }
    wsApi.ticket().then(r => {
      if (cerrado) return
      const ticket = r.data?.ticket
      if (!ticket) return
      const ws = new WebSocket(apiWsUrl(`/ws/notifications?ticket=${ticket}`))
      wsRef.current = ws
      ws.onopen = () => latir()
      ws.onmessage = (ev: MessageEvent<string>) => {
        try {
          const msg = JSON.parse(ev.data)
          if (msg?.type !== 'ticket_presence' || msg.ticket_id !== ticketId) return
          if (msg.ttl) latidoRef.current = Math.max(1000, Math.floor((msg.ttl * 1000) / 3))
          setPresentes((msg.viewers as Presente[]).filter(v => v.user_id !== user?.id))
        } catch { /* mensaje de otro tipo */ }
      }
    }).catch(() => { /* sin WebSocket: sin aviso */ })
    return () => {
      cerrado = true
      if (temporizador) clearTimeout(temporizador)
      enviar('leave')
      const ws = wsRef.current
      wsRef.current = null
      if (ws) { ws.onmessage = null; ws.onopen = null; ws.close() }
      setPresentes([])
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticketId])

  useEffect(() => {
    const modo = escribiendo ? 'edit' : 'view'
    if (modo !== modoRef.current) { modoRef.current = modo; enviar(modo) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [escribiendo])

  if (presentes.length === 0) return null
  const escriben = presentes.filter(p => p.mode === 'edit')
  return (
    <div role="status" className="sdm-collision u-mb-12">
      <Users size={14} aria-hidden="true" />
      <span>
        {escriben.length > 0
          ? t('sd_mercado.colision_escribiendo', { n: escriben.map(p => p.name).join(', ') })
          : t('sd_mercado.colision_mirando', { n: presentes.map(p => p.name).join(', ') })}
      </span>
    </div>
  )
}
