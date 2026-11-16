/**
 * services/api/avisos.ts — avisos de la persona (`/enterprise/notifications`)
 * y alertas del sistema (`/alerts`): lo que cuenta «Sin leer» en la bandeja.
 *
 * 16-11-2026 (campana de notificaciones). La campana de la barra superior, la
 * pestaña Notificaciones de /inbox y la bandeja cuentan **lo mismo**: avisos
 * sin leer + alertas sin leer (éstas sólo para admin/pm/hr, como la bandeja).
 * Las tres comparten las mismas claves de consulta de react-query.
 *
 * El contador de avisos usa `/unread-count` (un COUNT) y, si el servidor aún no
 * lo tiene (404/405: un backend sin reiniciar), cae al `unread_count` de la
 * lista, que es el cálculo de siempre.
 */
import api, { alertsApi } from './_core'
import type { Alerta } from './tipos-documentos'

export interface AvisoDelServidor {
  id: string | number
  type?: string
  title?: string
  body?: string | null
  is_read?: boolean
  created_at?: string
  /** Instante con zona (para «hace 5 min»). */
  created_at_iso?: string | null
  action_url?: string | null
}

/** Clave de las alertas sin resolver (la misma que usan bandeja y pestaña). */
export const CLAVE_ALERTAS = ['alerts-count'] as const

function estado(e: unknown): number | undefined {
  return (e as { response?: { status?: number } })?.response?.status
}

async function contadorDeLaLista(): Promise<number> {
  const r = await api.get('/enterprise/notifications', { params: { page_size: 1 } })
  return Number((r.data as { unread_count?: number })?.unread_count || 0)
}

export const avisosApi = {
  /** Avisos sin leer de quien llama. */
  contador: async (): Promise<number> => {
    try {
      const r = await api.get('/enterprise/notifications/unread-count')
      return Number((r.data as { unread_count?: number })?.unread_count || 0)
    } catch (e) {
      const s = estado(e)
      if (s === 404 || s === 405) return contadorDeLaLista()
      throw e
    }
  },
  /** Los últimos `cuantos` avisos. */
  ultimos: (cuantos: number): Promise<AvisoDelServidor[]> =>
    api.get('/enterprise/notifications', { params: { page_size: cuantos } })
      .then((r: { data?: { notifications?: AvisoDelServidor[] } }) => r.data?.notifications || []),
  marcarLeido: (id: string | number) => api.post(`/enterprise/notifications/${id}/read`),
  marcarTodos: () => api.post('/enterprise/notifications/read-all'),
  /** Alertas sin resolver (la bandeja las cuenta como sin leer si `!is_read`). */
  alertas: (): Promise<Alerta[]> =>
    alertsApi.list({ resolved: false }).then(r => r.data || []),
  marcarAlertaLeida: (id: string | number) => alertsApi.read(id),
  /** «Marcar todas»: avisos y alertas sin leer, para que el contador quede a 0. */
  marcarTodoLeido: async (alertas: Alerta[] = []) => {
    await Promise.all([
      api.post('/enterprise/notifications/read-all'),
      ...alertas.filter(a => !a.is_read).map(a => alertsApi.read(a.id)),
    ])
  },
}
