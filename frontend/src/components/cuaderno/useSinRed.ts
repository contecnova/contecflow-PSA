/**
 * Fija el ámbito de la cola sin conexión (persona y empresa de la sesión) y
 * sincroniza lo pendiente al montar y cada vez que vuelve la red.
 */
import { useEffect, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useAuth } from '../../context/AuthContext'
import { useAppT } from '../../i18n/AppLangContext'
import { useToast } from '../../context/ToastContext'
import { CLAVES_CUADERNO } from '../../services/api/cuaderno'
import { establecerAmbitoCuaderno, pendientes, sincronizar } from './colaOffline'

export function useSinRed(): { enLinea: boolean; pendientes: number } {
  const { user } = useAuth()
  const t = useAppT()
  const toast = useToast()
  const qc = useQueryClient()
  const [enLinea, setEnLinea] = useState(() => (typeof navigator === 'undefined' ? true : navigator.onLine))
  const [n, setN] = useState(0)
  const userId = user?.id
  const orgId = (user as { organization_id?: string | null } | null)?.organization_id

  useEffect(() => {
    establecerAmbitoCuaderno(userId, orgId)
    let vivo = true
    const contar = async () => { const p = await pendientes(); if (vivo) setN(p.length) }
    const subir = async () => {
      if (!navigator.onLine) return
      const r = await sincronizar(t('cuaderno.sufijo_sin_red'))
      if (r.enviados || r.copias) {
        void qc.invalidateQueries({ queryKey: CLAVES_CUADERNO.arbol })
        toast.success(t('cuaderno.sincronizado', { n: r.enviados + r.copias }))
        if (r.copias) toast.info(t('cuaderno.sincronizado_con_copias', { n: r.copias }))
      }
      await contar()
    }
    const alVolver = () => { setEnLinea(true); void subir() }
    const alIrse = () => { setEnLinea(false); void contar() }
    window.addEventListener('online', alVolver)
    window.addEventListener('offline', alIrse)
    void subir()
    return () => { vivo = false; window.removeEventListener('online', alVolver); window.removeEventListener('offline', alIrse) }
  }, [userId, orgId, t, toast, qc])

  return { enLinea, pendientes: n }
}
