/**
 * useTraducirBajoDemanda — «Traducir» un mensaje del chat interno cuando se pide
 * (traducción en tiempo real, 16-11-2026).
 *
 * Solo está disponible si la empresa traduce y el canal `internal_chat` está entre los
 * activos. Pide `POST /translation/messages` con el mensaje y el idioma de la interfaz
 * de quien mira; el resultado se pinta con `TextoTraducido` (que ya trae «Ver original»).
 */
import { useState } from 'react'
import { useAppLang } from '../../i18n/AppLangContext'
import { useConfigDeTraduccion } from '../../hooks/useTraduccion'
import { traduccionApi, type MensajeTraducido, type TipoDeMensaje } from '../../services/api/traduccion'

export const CANAL_CHAT_INTERNO = 'internal_chat'

export function useTraducirBajoDemanda(id: string, type: TipoDeMensaje = 'chat_message') {
  const { lang } = useAppLang()
  const { data: config } = useConfigDeTraduccion()
  const disponible = !!config?.enabled && (config?.channels ?? []).includes(CANAL_CHAT_INTERNO)
  const [traduccion, setTraduccion] = useState<MensajeTraducido | null>(null)
  const [cargando, setCargando] = useState(false)

  const pedir = async () => {
    if (!disponible || cargando) return
    setCargando(true)
    try {
      const r = await traduccionApi.mensajes([{ type, id }], lang)
      const item = r.items.find(i => i.id === id && i.field === 'body') ?? r.items.find(i => i.id === id) ?? null
      // Sin resultado: se marca como no disponible para que se vea el aviso.
      setTraduccion(item ?? { type, id, field: 'body', status: 'unavailable', text: null, source_language: null, target_language: lang, reason: 'provider_error' })
    } catch {
      setTraduccion({ type, id, field: 'body', status: 'unavailable', text: null, source_language: null, target_language: lang, reason: 'provider_error' })
    } finally {
      setCargando(false)
    }
  }
  const quitar = () => setTraduccion(null)

  return { disponible, traduccion, cargando, pedir, quitar }
}
