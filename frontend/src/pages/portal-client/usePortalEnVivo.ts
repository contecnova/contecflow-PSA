/**
 * usePortalEnVivo — el WebSocket del portal (`/ws/portal-notifications`),
 * compartido (17-11-2026).
 *
 * Antes lo abría `PortalClientePage` para sí sola y el chat en vivo sondeaba
 * cada 5 s. Ahora hay **una** conexión por pestaña, que se abre con el primer
 * componente que la pide y se cierra con el último; cada suscriptor recibe
 * todos los mensajes (`portal_notifications`, `livechat`…) y puede mandar los
 * suyos (`enviarPorElPortal`: escribiendo, leído). Ticket de un solo uso
 * (`GET /ws/portal-ticket`) y reintento con espera creciente (tope de
 * intentos): mientras no hay socket, quien lo usa tira de su sondeo.
 */
import { useEffect, useRef, useSyncExternalStore } from 'react'
import { apiWsUrl } from '../../services/api/urls'
import { WS_HEARTBEAT_MS } from '../../constants/timings'
import { CLIENT_API } from './portalClientContext'

/** Un mensaje del WebSocket del portal. */
export interface MensajeDelPortal {
  type?: string
  event?: string
  conversation_id?: string
  [clave: string]: unknown
}

type Oyente = (m: MensajeDelPortal) => void

const MAX_INTENTOS = 5
const ESPERA_MAX_MS = 30_000

const oyentes = new Set<Oyente>()
const avisosDeEstado = new Set<() => void>()
let usuarios = 0
let conectado = false
let socket: WebSocket | null = null
let ping: ReturnType<typeof setInterval> | null = null
let reintento: ReturnType<typeof setTimeout> | null = null
let intentos = 0
let generacion = 0

function fijarConectado(v: boolean) {
  if (conectado === v) return
  conectado = v
  avisosDeEstado.forEach(f => f())
}

function limpiar() {
  if (ping) { clearInterval(ping); ping = null }
  if (reintento) { clearTimeout(reintento); reintento = null }
  const s = socket
  socket = null
  if (s) {
    s.onmessage = null
    s.onerror = null
    s.onclose = null
    if (s.readyState === WebSocket.OPEN) s.close()
    else if (s.readyState === WebSocket.CONNECTING) s.onopen = () => s.close()
  }
  fijarConectado(false)
}

function programarReintento(gen: number) {
  if (gen !== generacion || usuarios === 0 || intentos >= MAX_INTENTOS) return
  const espera = Math.min(1000 * 2 ** intentos, ESPERA_MAX_MS)
  reintento = setTimeout(() => { reintento = null; void conectar(gen) }, espera)
}

async function conectar(gen: number) {
  if (gen !== generacion || usuarios === 0) return
  intentos += 1
  let ticket: string | undefined
  try {
    ticket = (await CLIENT_API.get('/ws/portal-ticket')).data?.ticket
  } catch {
    /* accesorio: avisos en vivo; si no hay ticket se reintenta con espera creciente y el portal sigue funcionando por sondeo */
    programarReintento(gen)
    return
  }
  if (gen !== generacion || usuarios === 0 || !ticket) return
  let s: WebSocket
  try {
    s = new WebSocket(apiWsUrl(`/ws/portal-notifications?ticket=${encodeURIComponent(ticket)}`))
  } catch {
    /* accesorio: no se pudo abrir el socket; se reintenta como arriba */
    programarReintento(gen)
    return
  }
  socket = s
  s.onopen = () => {
    if (gen !== generacion) { s.close(); return }
    intentos = 0
    fijarConectado(true)
  }
  s.onmessage = (ev: MessageEvent<string>) => {
    let m: MensajeDelPortal
    try { m = JSON.parse(ev.data) } catch { /* accesorio: mensaje del socket que no es JSON; se ignora */ return }
    oyentes.forEach(f => { try { f(m) } catch { /* un oyente no tumba a los demás */ } })
  }
  s.onerror = () => { /* llega onclose */ }
  s.onclose = (ev) => {
    if (socket === s) socket = null
    if (ping) { clearInterval(ping); ping = null }
    fijarConectado(false)
    if (ev.code !== 1000 && ev.code !== 1001) programarReintento(gen)
  }
  ping = setInterval(() => {
    if (s.readyState === WebSocket.OPEN) s.send(JSON.stringify({ type: 'ping' }))
  }, WS_HEARTBEAT_MS)
}

function alta() {
  usuarios += 1
  if (usuarios === 1) {
    generacion += 1
    intentos = 0
    void conectar(generacion)
  }
}

function baja() {
  usuarios = Math.max(0, usuarios - 1)
  if (usuarios === 0) {
    generacion += 1
    limpiar()
  }
}

function suscribirEstado(f: () => void) {
  avisosDeEstado.add(f)
  return () => { avisosDeEstado.delete(f) }
}

/** Manda un mensaje por el socket del portal; `false` si no está abierto. */
export function enviarPorElPortal(mensaje: Record<string, unknown>): boolean {
  if (!socket || socket.readyState !== WebSocket.OPEN) return false
  try { socket.send(JSON.stringify(mensaje)); return true } catch { /* accesorio: presencia/escritura en vivo; el llamador ya recibe false */ return false }
}

/**
 * Se suma a la conexión compartida mientras `activo` (hay sesión de cliente)
 * y llama a `alRecibir` con cada mensaje. Devuelve si el socket está abierto.
 */
export default function usePortalEnVivo(activo: boolean, alRecibir?: Oyente): boolean {
  const ref = useRef(alRecibir)
  useEffect(() => { ref.current = alRecibir }, [alRecibir])

  useEffect(() => {
    if (!activo) return undefined
    const oyente: Oyente = m => ref.current?.(m)
    oyentes.add(oyente)
    alta()
    return () => {
      oyentes.delete(oyente)
      baja()
    }
  }, [activo])

  return useSyncExternalStore(suscribirEstado, () => conectado, () => false)
}

/** Sólo para pruebas: deja el módulo como recién cargado. */
export function _reiniciarPortalEnVivo() {
  generacion += 1
  limpiar()
  oyentes.clear()
  usuarios = 0
  intentos = 0
}
