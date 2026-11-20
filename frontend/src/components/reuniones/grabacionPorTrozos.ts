/**
 * Grabación de audio por trozos completos (19-11-2026).
 *
 * `MediaRecorder.start(timeslice)` solo pone la cabecera WebM en el primer
 * trozo: los siguientes no se pueden transcribir sueltos. Aquí cada N ms se
 * cierra el grabador y se abre otro sobre la misma pista, así que cada trozo
 * es un fichero completo. Lo usan la llamada del chat (subtítulos y asistente
 * de reuniones) y, con la misma idea, `GrabadorDeReunion`.
 */
import { useEffect, useRef } from 'react'

const TIPO_PREFERIDO = 'audio/webm;codecs=opus'

export function tipoDeGrabacion(): string | undefined {
  try {
    return typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported?.(TIPO_PREFERIDO) ? TIPO_PREFERIDO : undefined
  } catch { return undefined }
}

interface Opciones {
  /** Grabar o no. Al pasar a `false` se cierra el trozo en curso (y se entrega). */
  activo: boolean
  /** La pista de audio; se pide al activar (y cada vez que cambia `clave`). */
  obtenerStream: () => MediaStream | null
  /** Recibe cada trozo completo. */
  onTrozo: (trozo: Blob) => void
  /** Duración de cada trozo. */
  duracionMs?: number
  /** Cambia cuando la pista ya está lista (p. ej. al conectar la sala). */
  clave?: unknown
}

export function useGrabacionPorTrozos({ activo, obtenerStream, onTrozo, duracionMs = 12_000, clave }: Opciones): void {
  const onTrozoRef = useRef(onTrozo)
  const obtenerRef = useRef(obtenerStream)
  onTrozoRef.current = onTrozo
  obtenerRef.current = obtenerStream

  useEffect(() => {
    if (!activo || typeof MediaRecorder === 'undefined') return undefined
    const stream = obtenerRef.current()
    if (!stream || stream.getAudioTracks().length === 0) return undefined
    let rec: MediaRecorder | null = null

    const abrir = () => {
      const tipo = tipoDeGrabacion()
      const r = tipo ? new MediaRecorder(stream, { mimeType: tipo }) : new MediaRecorder(stream)
      const partes: Blob[] = []
      r.ondataavailable = e => { if (e.data && e.data.size > 0) partes.push(e.data) }
      r.onstop = () => {
        const trozo = new Blob(partes, { type: r.mimeType || 'audio/webm' })
        if (trozo.size > 0) onTrozoRef.current(trozo)
      }
      r.start()
      rec = r
    }
    const cerrar = () => { try { if (rec && rec.state !== 'inactive') rec.stop() } catch { /* ya parado */ } }

    try { abrir() } catch (e) { console.warn('grabación por trozos:', e); return undefined }
    const reloj = setInterval(() => {
      cerrar()
      try { abrir() } catch { /* la pista se cerró */ }
    }, duracionMs)
    return () => { clearInterval(reloj); cerrar() }
  }, [activo, duracionMs, clave])
}
