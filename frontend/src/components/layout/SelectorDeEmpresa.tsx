/**
 * Selector de empresa en la cabecera (revisión multitenant 2026-11).
 *
 * Solo aparece si el usuario pertenece a más de una empresa activa y el
 * despliegue entra con «correo + selector»: en los modos subdominio y código de
 * empresa, la empresa la fija el acceso. Cambiar emite una sesión nueva y
 * recarga la página, para que nada de la empresa anterior quede en caché.
 */
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { authApi } from '../../services/api'
import { useAppT } from '../../i18n/AppLangContext'

export default function SelectorDeEmpresa() {
  const t = useAppT()
  const [cambiando, setCambiando] = useState(false)
  const { data: entrada } = useQuery({
    queryKey: ['entry-config'],
    queryFn: () => authApi.entryConfig().then(r => r.data),
    staleTime: Infinity,
  })
  const { data } = useQuery({
    queryKey: ['my-organizations'],
    queryFn: () => authApi.myOrganizations().then(r => r.data),
    enabled: entrada?.mode === 'email_selector',
  })
  if (entrada?.mode !== 'email_selector' || !data || data.items.length < 2) return null

  async function cambiar(id: string) {
    if (!id || id === data?.current) return
    setCambiando(true)
    try {
      await authApi.switchOrganization(id)
      window.location.reload()
    } catch {
      setCambiando(false)
    }
  }

  return (
    <select
      aria-label={t('login.switch_org')}
      title={t('login.switch_org')}
      value={data.current ?? ''}
      disabled={cambiando}
      onChange={e => { void cambiar(e.target.value) }}
      style={{
        maxWidth: 180, height: 30, padding: '0 8px', borderRadius: 8,
        background: 'var(--surface-3)', border: '1px solid var(--surface-4)',
        color: 'var(--text-1)', fontSize: 'var(--text-sm)', fontWeight: 600, fontFamily: 'inherit',
      }}
    >
      {data.items.map(o => <option key={o.id} value={o.id}>{o.name}</option>)}
    </select>
  )
}
