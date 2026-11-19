/**
 * Horas extra (18-11-2026): petición previa o declaración posterior,
 * aprobación por flujos, control frente a la imputación y ciclo completo.
 *
 * - Mis horas extra: pedir con vista previa en vivo (POST /overtime/preview) y
 *   mis peticiones (GET /overtime/mine) con cancelar / editar las pendientes.
 * - Por aprobar: GET /overtime/inbox → POST /overtime/{id}/review.
 * - Gestión (admin/RRHH/PM/responsables): GET /overtime con filtros y totales;
 *   la fila abre el ciclo completo (GET /overtime/{id}) y «Liquidar»
 *   (POST /overtime/{id}/settle); «Para nómina» (GET /overtime/payroll, CSV).
 * - Resumen (responsables): GET /overtime/summary frente a límites y
 *   presupuestos, y GET /overtime/unauthorized.
 * - Configuración (admin/RRHH): ya no es una pestaña; vive en Configuración
 *   (`/settings/horas-extra`, ConfigHorasExtra). Aquí queda el botón
 *   «Configurar» y `?tab=config` redirige allí (18-11-2026).
 * Las respuestas van envueltas en `{ok, data}`; `_core` las desenvuelve.
 */
import { useState } from 'react'
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { AlarmClockPlus, BarChart3, Inbox, ListChecks, Settings2, UserRound } from 'lucide-react'
import { Button, Page, Tabs } from '../components/ui'
import { useAuth } from '../context/AuthContext'
import { useTh } from '../components/horas-extra/comun'
import MisHorasExtra from '../components/horas-extra/MisHorasExtra'
import BandejaHorasExtra from '../components/horas-extra/BandejaHorasExtra'
import GestionHorasExtra from '../components/horas-extra/GestionHorasExtra'
import ResumenHorasExtra from '../components/horas-extra/ResumenHorasExtra'
import CicloHorasExtra from '../components/horas-extra/CicloHorasExtra'

export default function HorasExtraPage(): JSX.Element {
  const { th, t } = useTh()
  const { puede } = useAuth()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const pedida = searchParams.get('tab')
  const gestiona = puede('horas_extra.gestionar')
  const administra = puede('horas_extra.config')
  const validas = ['mias', 'aprobar', ...(gestiona ? ['gestion', 'resumen'] : [])]
  const [tab, setTab] = useState(pedida && validas.includes(pedida) ? pedida : 'mias')
  const [abierta, setAbierta] = useState<string | null>(null)
  const items = [
    { id: 'mias', label: th('tab_mias'), icon: <UserRound size={14} /> },
    { id: 'aprobar', label: th('tab_aprobar'), icon: <Inbox size={14} /> },
    ...(gestiona ? [
      { id: 'gestion', label: th('tab_gestion'), icon: <ListChecks size={14} /> },
      { id: 'resumen', label: th('tab_resumen'), icon: <BarChart3 size={14} /> },
    ] : []),
  ]
  // La configuración vive en Configuración (18-11-2026): los enlaces antiguos redirigen.
  if (pedida === 'config') return <Navigate to="/settings/horas-extra" replace />
  return (
    <Page title={th('titulo')} subtitle={th('subtitulo')} icon={<AlarmClockPlus size={18} />}
      actions={administra ? (
        <Button variant="secondary" icon={<Settings2 size={14} />} onClick={() => navigate('/settings/horas-extra')}>{t('ajustes.configurar')}</Button>
      ) : undefined}>
      <Tabs items={items} active={tab} onChange={setTab} ariaLabel={th('secciones')} />
      <div role="tabpanel">
        {tab === 'mias' && <MisHorasExtra />}
        {tab === 'aprobar' && <BandejaHorasExtra onAbrir={setAbierta} />}
        {tab === 'gestion' && gestiona && <GestionHorasExtra onAbrir={setAbierta} />}
        {tab === 'resumen' && gestiona && <ResumenHorasExtra onAbrir={setAbierta} />}
      </div>
      <CicloHorasExtra id={abierta} onCerrar={() => setAbierta(null)} />
    </Page>
  )
}
