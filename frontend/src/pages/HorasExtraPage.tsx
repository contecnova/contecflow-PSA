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
 * - Configuración (admin/RRHH): GET/PUT /overtime/config, /overtime/budgets,
 *   POST /overtime/regularize y reglas del dominio `horas_extra` en Políticas.
 * Las respuestas van envueltas en `{ok, data}`; `_core` las desenvuelve.
 */
import { useState } from 'react'
import { AlarmClockPlus, BarChart3, Inbox, ListChecks, Settings2, UserRound } from 'lucide-react'
import { Page, Tabs } from '../components/ui'
import { useAuth } from '../context/AuthContext'
import { useTh } from '../components/horas-extra/comun'
import MisHorasExtra from '../components/horas-extra/MisHorasExtra'
import BandejaHorasExtra from '../components/horas-extra/BandejaHorasExtra'
import GestionHorasExtra from '../components/horas-extra/GestionHorasExtra'
import ResumenHorasExtra from '../components/horas-extra/ResumenHorasExtra'
import ConfigHorasExtra from '../components/horas-extra/ConfigHorasExtra'
import CicloHorasExtra from '../components/horas-extra/CicloHorasExtra'

export default function HorasExtraPage(): JSX.Element {
  const { th } = useTh()
  const { hasRole } = useAuth()
  const gestiona = hasRole('admin', 'hr', 'pm', 'team_lead')
  const administra = hasRole('admin', 'hr')
  const [tab, setTab] = useState('mias')
  const [abierta, setAbierta] = useState<string | null>(null)
  const items = [
    { id: 'mias', label: th('tab_mias'), icon: <UserRound size={14} /> },
    { id: 'aprobar', label: th('tab_aprobar'), icon: <Inbox size={14} /> },
    ...(gestiona ? [
      { id: 'gestion', label: th('tab_gestion'), icon: <ListChecks size={14} /> },
      { id: 'resumen', label: th('tab_resumen'), icon: <BarChart3 size={14} /> },
    ] : []),
    ...(administra ? [{ id: 'config', label: th('tab_config'), icon: <Settings2 size={14} /> }] : []),
  ]
  return (
    <Page title={th('titulo')} subtitle={th('subtitulo')} icon={<AlarmClockPlus size={18} />}>
      <Tabs items={items} active={tab} onChange={setTab} ariaLabel={th('secciones')} />
      <div role="tabpanel">
        {tab === 'mias' && <MisHorasExtra />}
        {tab === 'aprobar' && <BandejaHorasExtra onAbrir={setAbierta} />}
        {tab === 'gestion' && gestiona && <GestionHorasExtra onAbrir={setAbierta} />}
        {tab === 'resumen' && gestiona && <ResumenHorasExtra onAbrir={setAbierta} />}
        {tab === 'config' && administra && <ConfigHorasExtra />}
      </div>
      <CicloHorasExtra id={abierta} onCerrar={() => setAbierta(null)} />
    </Page>
  )
}
