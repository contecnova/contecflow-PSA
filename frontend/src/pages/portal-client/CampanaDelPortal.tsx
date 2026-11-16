/**
 * CampanaDelPortal — campana de avisos de la cabecera del portal de clientes.
 *
 * 16-11-2026. Antes la campana sumaba contadores (tickets pendientes y
 * mensajes) y llevaba a Soporte. Ahora es la bandeja del cliente: sus avisos
 * (`/portal/collaboration/notifications`, sólo los suyos), que son las
 * respuestas y cambios de sus tickets, los mensajes del equipo y los de sus
 * conversaciones (ver `app/services/avisos_del_portal.py`).
 *
 * Tiempo real: el WebSocket del portal (`/ws/portal-notifications`, abierto en
 * PortalClientePage) incluye el número de avisos sin leer y, al cambiar,
 * invalida `portal-avisos`. Sin socket abierto, el contador se sondea cada
 * `NOTIFICATIONS_POLL_MS`.
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CLIENT_API, useLang, type TraductorDelPortal } from './portalClientContext'
import BandejaDesplegable, { type AvisoDeLaBandeja } from '../../components/avisos/BandejaDesplegable'
import { NOTIFICATIONS_POLL_MS, STALE_LIVE_MS } from '../../constants/timings'

/** Evento con el que la campana pide a Soporte que abra un ticket. */
export const EVENTO_ABRIR_TICKET = 'portal:abrir-ticket'

/** Prefijo de las consultas de avisos del portal (lo invalida el WebSocket). */
export const CLAVE_AVISOS_DEL_PORTAL = 'portal-avisos'

/** Cuántos avisos enseña el panel. */
const EN_LA_CAMPANA = 8

export interface AvisoDelPortal {
  id: string
  kind?: string
  title?: string
  body?: string | null
  is_read?: boolean
  created_at?: string | null
  conversation_id?: string | null
  payload?: { tipo?: string; seccion?: string; ticket_id?: string }
}

/** Etiqueta (clave del portal) de cada tipo de aviso. */
const ETIQUETA_DE_TIPO: Record<string, string> = {
  ticket_created: 'portal_avisos.tipo_ticket',
  ticket_replied: 'portal_avisos.tipo_respuesta',
  ticket_updated: 'portal_avisos.tipo_actualizacion',
  ticket_resolved: 'portal_avisos.tipo_actualizacion',
  approval_requested: 'portal_avisos.tipo_actualizacion',
  mensaje_del_equipo: 'portal_avisos.tipo_mensaje',
}

/** Icono: el tipo del aviso o, en una conversación, el de mensaje. */
function tipoVisual(a: AvisoDelPortal): string {
  if (a.payload?.tipo) return a.payload.tipo
  return a.conversation_id ? 'mensaje_del_equipo' : 'system'
}

export function avisoParaLaBandeja(a: AvisoDelPortal, t: TraductorDelPortal): AvisoDeLaBandeja {
  const tipo = tipoVisual(a)
  const clave = ETIQUETA_DE_TIPO[tipo] ?? (a.conversation_id ? 'portal_avisos.tipo_conversacion' : null)
  return {
    id: String(a.id),
    titulo: a.title || t('portal_avisos.titulo'),
    extracto: a.body,
    fecha: a.created_at || null,
    leido: !!a.is_read,
    tipo,
    etiqueta: clave ? t(clave) : null,
  }
}

export const portalAvisosApi = {
  contador: (): Promise<number> =>
    CLIENT_API.get('/portal/collaboration/notifications/unread-count')
      .then(r => Number((r.data as { unread_count?: number })?.unread_count || 0)),
  lista: (limit?: number, soloSinLeer = false): Promise<AvisoDelPortal[]> =>
    CLIENT_API.get('/portal/collaboration/notifications', {
      params: { ...(limit ? { limit } : {}), ...(soloSinLeer ? { unread_only: true } : {}) },
    }).then(r => (r.data as AvisoDelPortal[]) || []),
  marcarLeido: (id: string) => CLIENT_API.post(`/portal/collaboration/notifications/${id}/read`),
  marcarTodos: () => CLIENT_API.post('/portal/collaboration/notifications/mark-all-read'),
}

/** Contador y acciones de los avisos del cliente (campana y página). */
export function useAvisosDelPortal(enVivo: boolean) {
  const qc = useQueryClient()
  const refrescar = () => qc.invalidateQueries({ queryKey: [CLAVE_AVISOS_DEL_PORTAL] })
  const contador = useQuery<number>({
    queryKey: [CLAVE_AVISOS_DEL_PORTAL, 'contador'],
    queryFn: portalAvisosApi.contador,
    staleTime: STALE_LIVE_MS,
    refetchInterval: enVivo ? false : NOTIFICATIONS_POLL_MS,
  })
  const marcarUno = useMutation({ mutationFn: portalAvisosApi.marcarLeido, onSettled: refrescar })
  const marcarTodos = useMutation({ mutationFn: portalAvisosApi.marcarTodos, onSettled: refrescar })
  return { contador: contador.data ?? 0, marcarUno, marcarTodos, refrescar }
}

/** Lleva a la sección del aviso y, si es de un ticket, lo abre. */
export function irAlAviso(a: AvisoDelPortal | undefined, onSection: (s: string) => void) {
  const seccion = a?.payload?.seccion || (a?.conversation_id ? 'messages' : null)
  const ticket = a?.payload?.ticket_id
  if (ticket) {
    // Soporte lee `?ticket=` al montarse; si ya está montado, escucha el evento.
    const url = new URL(window.location.href)
    url.searchParams.set('ticket', ticket)
    window.history.replaceState(window.history.state, '', url)
    onSection('support')
    window.dispatchEvent(new CustomEvent(EVENTO_ABRIR_TICKET, { detail: ticket }))
    return
  }
  if (seccion) onSection(seccion)
}

interface Props {
  onSection: (section: string) => void
  /** El WebSocket del portal está abierto: no hace falta sondear. */
  enVivo?: boolean
}

export default function CampanaDelPortal({ onSection, enVivo = false }: Props) {
  const t = useLang()
  const { contador, marcarUno, marcarTodos, refrescar } = useAvisosDelPortal(enVivo)
  // La lista se pide la primera vez que se abre el panel.
  const [verLista, setVerLista] = useState(false)
  const lista = useQuery<AvisoDelPortal[]>({
    queryKey: [CLAVE_AVISOS_DEL_PORTAL, 'campana'],
    queryFn: () => portalAvisosApi.lista(EN_LA_CAMPANA),
    staleTime: STALE_LIVE_MS,
    enabled: verLista,
  })
  const avisos = lista.data ?? []
  const porId = new Map(avisos.map(a => [String(a.id), a]))

  const elegir = (v: AvisoDeLaBandeja) => {
    if (!v.leido) marcarUno.mutate(v.id)
    irAlAviso(porId.get(v.id), onSection)
  }

  return (
    <BandejaDesplegable
      contador={contador}
      avisos={avisos.map(a => avisoParaLaBandeja(a, t))}
      cargando={verLista && lista.isLoading}
      textos={{
        titulo: t('portal_avisos.titulo'),
        sinLeer: n => t(n === 1 ? 'portal_avisos.sin_leer_uno' : 'portal_avisos.sin_leer_otros', { n }),
        marcarTodas: t('portal_avisos.marcar_todas'),
        verTodas: t('portal_avisos.ver_todas'),
        vacio: t('portal_avisos.vacio'),
        noLeido: t('portal_avisos.no_leido'),
        cargando: t('portal_avisos.cargando'),
      }}
      onAbrir={() => { if (verLista) void refrescar(); else setVerLista(true) }}
      onElegir={elegir}
      onMarcarTodas={() => marcarTodos.mutate()}
      marcandoTodas={marcarTodos.isPending}
      onVerTodas={() => onSection('notifications')}
      claseBoton="campana-del-portal"
    />
  )
}
