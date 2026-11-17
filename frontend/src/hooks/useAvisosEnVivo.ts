/**
 * useAvisosEnVivo — el WebSocket de avisos del operador (`/ws/notifications`),
 * compartido.
 *
 * 16-11-2026 (campana de notificaciones). La bandeja abría su propio socket y
 * la campana de la barra superior necesita el mismo: dos conexiones por persona
 * son dos sondeos en el servidor. Aquí hay **una** conexión por pestaña, que
 * se abre con el primer componente que la pide y se cierra con el último. Cada
 * suscriptor recibe todos los mensajes; el estado «conectado» se lee con
 * `useSyncExternalStore`.
 *
 * La conexión usa el ticket de un solo uso (`GET /ws/ticket`) y, si se cae,
 * reintenta con espera creciente (tope de intentos): mientras no hay socket,
 * quien la usa tira de su sondeo de respaldo.
 */
import { useEffect, useRef, useSyncExternalStore } from 'react'
import api, { apiWsUrl } from '../services/api'
import { WS_PING_INTERVAL_MS } from '../constants/timings'

/** Un mensaje del WebSocket de avisos (`type`: notifications, notification_push…). */
export interface MensajeDeAvisos {
  type?: string
  count?: number
  items?: Array<{ id?: string | number }>
  [clave: string]: unknown
}

type Oyente = (m: MensajeDeAvisos) => void

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
    // CONNECTING: se cierra al abrir (evita el aviso del navegador).
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
    ticket = (await api.get('/ws/ticket')).data?.ticket
  } catch {
    programarReintento(gen)
    return
  }
  if (gen !== generacion || usuarios === 0 || !ticket) return
  let s: WebSocket
  try {
    s = new WebSocket(apiWsUrl(`/ws/notifications?ticket=${encodeURIComponent(ticket)}`))
  } catch {
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
    let m: MensajeDeAvisos
    try { m = JSON.parse(ev.data) } catch { return }
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
  }, WS_PING_INTERVAL_MS)
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

/**
 * Se suma a la conexión compartida mientras `activo` (normalmente: hay sesión)
 * y llama a `alRecibir` con cada mensaje. Devuelve si el socket está abierto.
 */
export default function useAvisosEnVivo(activo: boolean, alRecibir?: Oyente): boolean {
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

/**
 * Manda un mensaje por la conexión compartida (17-11-2026: la bandeja de
 * conversaciones avisa de que está abierta, de que se escribe y de lo leído).
 * Devuelve `false` si el socket no está abierto (quien llama sigue con su sondeo).
 */
export function enviarPorAvisosEnVivo(mensaje: Record<string, unknown>): boolean {
  if (!socket || socket.readyState !== WebSocket.OPEN) return false
  try { socket.send(JSON.stringify(mensaje)); return true } catch { return false }
}

/** Sólo para pruebas: deja el módulo como recién cargado. */
export function _reiniciarAvisosEnVivo() {
  generacion += 1
  limpiar()
  oyentes.clear()
  usuarios = 0
  intentos = 0
}
