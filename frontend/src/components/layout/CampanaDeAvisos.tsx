/**
 * CampanaDeAvisos — campana de la barra superior de operadores.
 *
 * 16-11-2026. El número es el mismo «Sin leer» de la bandeja (/inbox): avisos
 * sin leer de la persona + alertas sin leer (admin/pm/hr, igual que la
 * bandeja). Comparte con la bandeja y con la pestaña Notificaciones las mismas
 * claves de consulta (`useContadorDeAvisos`), así que no pueden discrepar.
 * Al abrirla enseña los últimos avisos y alertas.
 *
 * Tiempo real: se suma al WebSocket de avisos compartido (`useAvisosEnVivo`,
 * el mismo que la bandeja) y, con cada mensaje de avisos, vuelve a pedir el
 * contador y la lista. Sólo si el socket no está abierto sondea, cada
 * `NOTIFICATIONS_POLL_MS`.
 */
import { useCallback, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { avisosApi, CLAVE_ALERTAS, type AvisoDelServidor } from '../../services/api/avisos'
import type { Alerta } from '../../services/api/tipos-documentos'
import { useAppLang } from '../../i18n/AppLangContext'
import { useAuth } from '../../context/AuthContext'
import { queryKeys } from '../../constants/queryKeys'
import { NOTIFICATIONS_POLL_MS, POLL_DEFAULT_MS, STALE_LIVE_MS, STALE_SHORT_MS } from '../../constants/timings'
import useAvisosEnVivo, { type MensajeDeAvisos } from '../../hooks/useAvisosEnVivo'
import BandejaDesplegable, { type AvisoDeLaBandeja } from '../avisos/BandejaDesplegable'

/** Cuántos avisos enseña el panel. */
export const AVISOS_EN_LA_CAMPANA = 8

/** Mensajes del WebSocket que cambian los avisos. */
const MENSAJES_DE_AVISOS = new Set(['notifications', 'notification_push'])

/** Prefijo de los ids de alerta en la lista (los avisos y las alertas se mezclan). */
const ALERTA = 'alert_'

/** Las claves de consulta que dependen de los avisos (campana, pestaña, bandeja). */
export function refrescarAvisos(qc: ReturnType<typeof useQueryClient>) {
  qc.invalidateQueries({ queryKey: queryKeys.notifications.all() })
  qc.invalidateQueries({ queryKey: ['notifications-page'] })
  qc.invalidateQueries({ queryKey: [...CLAVE_ALERTAS] })
}

/**
 * El «Sin leer» de la bandeja: avisos sin leer + alertas sin leer. Mismas
 * claves que `useNotificationBadges` (pestaña de /inbox) y la bandeja.
 */
export function useContadorDeAvisos(activo: boolean, sondear: boolean) {
  const { puede } = useAuth()
  const veAlertas = puede('alertas.ver')
  const avisos = useQuery<number>({
    queryKey: queryKeys.notifications.badges(),
    queryFn: () => avisosApi.contador().catch(() => 0),
    enabled: activo,
    staleTime: STALE_LIVE_MS,
    refetchInterval: sondear ? NOTIFICATIONS_POLL_MS : false,
  })
  const alertas = useQuery<Alerta[]>({
    queryKey: [...CLAVE_ALERTAS],
    queryFn: () => avisosApi.alertas().catch((): Alerta[] => []),
    enabled: activo && veAlertas,
    staleTime: STALE_SHORT_MS,
    refetchInterval: POLL_DEFAULT_MS,
  })
  const listaDeAlertas = veAlertas ? (alertas.data ?? []) : []
  const alertasSinLeer = listaDeAlertas.filter(a => !a.is_read).length
  const avisosSinLeer = Number(avisos.data || 0)
  return { total: avisosSinLeer + alertasSinLeer, avisosSinLeer, alertasSinLeer, alertas: listaDeAlertas }
}

export default function CampanaDeAvisos({ activo = true }: { activo?: boolean }) {
  const { t } = useAppLang()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [verLista, setVerLista] = useState(false)

  const alRecibir = useCallback((m: MensajeDeAvisos) => {
    if (m.type && MENSAJES_DE_AVISOS.has(m.type)) refrescarAvisos(qc)
  }, [qc])
  const enVivo = useAvisosEnVivo(activo, alRecibir)

  const { total, alertas } = useContadorDeAvisos(activo, !enVivo)

  const { data: avisos = [], isLoading } = useQuery<AvisoDelServidor[]>({
    queryKey: [...queryKeys.notifications.all(), 'campana'],
    queryFn: () => avisosApi.ultimos(AVISOS_EN_LA_CAMPANA),
    enabled: activo && verLista,
    staleTime: STALE_LIVE_MS,
  })

  const marcarUna = useMutation({
    mutationFn: (id: string) => id.startsWith(ALERTA)
      ? avisosApi.marcarAlertaLeida(id.slice(ALERTA.length))
      : avisosApi.marcarLeido(id),
    onSettled: () => refrescarAvisos(qc),
  })
  const marcarTodas = useMutation({
    mutationFn: () => avisosApi.marcarTodoLeido(alertas),
    onSettled: () => refrescarAvisos(qc),
  })

  const porId = new Map(avisos.map(a => [String(a.id), a]))
  const lista: AvisoDeLaBandeja[] = [
    ...avisos.map(a => ({
      id: String(a.id),
      titulo: a.title || t('pagina_notif.notificacion'),
      extracto: a.body,
      fecha: a.created_at_iso || null,
      leido: !!a.is_read,
      tipo: a.type,
    })),
    // Las alertas sin leer también cuentan en el número: se ven en el panel.
    ...alertas.filter(a => !a.is_read).map(a => ({
      id: ALERTA + a.id,
      titulo: a.title || t('pagina_notif.alerta'),
      extracto: a.description,
      fecha: a.created_at || null,
      leido: false,
      tipo: a.alert_type,
      esAlerta: true,
      etiqueta: t('pagina_notif.alerta'),
    })),
  ]
    .sort((a, b) => (b.fecha || '').localeCompare(a.fecha || ''))
    .slice(0, AVISOS_EN_LA_CAMPANA)

  const elegir = (a: AvisoDeLaBandeja) => {
    if (!a.leido) marcarUna.mutate(a.id)
    if (a.id.startsWith(ALERTA)) { navigate('/inbox?tab=notifications'); return }
    const destino = porId.get(a.id)?.action_url
    // Sólo rutas de la propia aplicación: un enlace externo no se sigue a ciegas.
    if (destino && destino.startsWith('/') && !destino.startsWith('//')) navigate(destino)
  }

  return (
    <BandejaDesplegable
      contador={total}
      avisos={lista}
      cargando={isLoading && verLista}
      textos={{
        titulo: t('campana.titulo'),
        sinLeer: n => t(n === 1 ? 'campana.sin_leer_uno' : 'campana.sin_leer_otros', { n }),
        marcarTodas: t('campana.marcar_todas'),
        verTodas: t('campana.ver_todas'),
        vacio: t('campana.vacio'),
        noLeido: t('campana.no_leido'),
        cargando: t('campana.cargando'),
      }}
      onAbrir={() => { setVerLista(true); if (verLista) refrescarAvisos(qc) }}
      onElegir={elegir}
      onMarcarTodas={() => marcarTodas.mutate()}
      marcandoTodas={marcarTodas.isPending}
      onVerTodas={() => navigate('/inbox?tab=notifications')}
    />
  )
}
