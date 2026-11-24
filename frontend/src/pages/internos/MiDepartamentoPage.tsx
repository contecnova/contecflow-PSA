/**
 * Portal interno «Mi departamento» (`/mi-departamento`, capacidad `interno.portal`, 22-11-2026).
 *
 * Para las personas de una unidad interna (deducidas de RR. HH.) y su
 * responsable: resumen, proyectos, hitos y UAT a firmar, tickets y SLA,
 * coste/presupuesto/cargos (solo responsable y finanzas), pedir proyecto o
 * servicio, valorar y plan de adopción y beneficios. Sin unidad
 * (`GET /internal-portal/me` → `enabled: false`) se explica por qué.
 * Ver docs/CLIENTES_INTERNOS.md §5.
 */
import { useState } from 'react'
import type { ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Building, ClipboardCheck, Flag, FolderKanban, Inbox, LayoutDashboard, Target, Ticket, Wallet } from 'lucide-react'
import { EmptyState, Select, Spinner, Tabs, SelectorDeContexto } from '../../components/ui'
import StatusBadge from '../../components/ui/StatusBadge'
import PageHeader from '../../components/layout/PageHeader'
import PageShell from '../../components/layout/PageShell'
import { portalInternoApi } from '../../services/api/clientesInternos'
import { useT } from './comunes'
import { etiquetaInterna } from './logica'
import { AdopcionYBeneficios, CosteYCargos, Hitos, Peticiones, Proyectos, Resumen, TicketsYSla, Uat } from './SeccionesDelPortal'

type Pestana = 'summary' | 'projects' | 'milestones' | 'uat' | 'tickets' | 'costs' | 'requests' | 'adoption'

export default function MiDepartamentoPage() {
  const t = useT()
  const [tab, setTab] = useState<Pestana>('summary')
  const [elegida, setElegida] = useState('')
  const { data: yo, isLoading } = useQuery({ queryKey: ['internal-portal', 'me'], queryFn: () => portalInternoApi.yo() })

  if (isLoading) return <PageShell><Spinner /></PageShell>
  if (!yo?.enabled || !yo.units.length) {
    return (
      <PageShell>
        <PageHeader icon={<Building size={18} />} title={t('internos.titulo_portal')} showListExport={false} />
        <EmptyState icon={<Building size={28} />} title={t('internos.portal_sin_unidad')} description={t('internos.portal_sin_unidad_d')} />
      </PageShell>
    )
  }
  const unidad = yo.units.find(u => u.id === elegida) || yo.units[0]
  const pestanas: { id: Pestana; label: string; icon: ReactNode }[] = [
    { id: 'summary', label: t('internos.tab_resumen'), icon: <LayoutDashboard size={14} /> },
    { id: 'projects', label: t('internos.tab_proyectos'), icon: <FolderKanban size={14} /> },
    { id: 'milestones', label: t('internos.tab_hitos'), icon: <Flag size={14} /> },
    { id: 'uat', label: t('internos.tab_uat'), icon: <ClipboardCheck size={14} /> },
    { id: 'tickets', label: t('internos.tab_tickets'), icon: <Ticket size={14} /> },
    ...(unidad.can_see_costs ? [{ id: 'costs' as Pestana, label: t('internos.tab_coste'), icon: <Wallet size={14} /> }] : []),
    { id: 'requests', label: t('internos.tab_peticiones'), icon: <Inbox size={14} /> },
    { id: 'adoption', label: t('internos.tab_adopcion'), icon: <Target size={14} /> },
  ]
  const activa: Pestana = tab === 'costs' && !unidad.can_see_costs ? 'summary' : tab
  return (
    <PageShell>
      <PageHeader icon={<Building size={18} />} title={t('internos.titulo_portal')}
        subtitle={[unidad.name, etiquetaInterna(t, 'subtipo_', unidad.internal_type)].filter(Boolean).join(' · ')} showListExport={false} />
      <SelectorDeContexto>
          {yo.units.length > 1 && (
            <Select label={t('internos.col_unidad')} value={unidad.id} placeholder={false} onChange={e => setElegida(e.target.value)}
              options={yo.units.map(u => ({ value: u.id, label: u.name }))} />
          )}
          <StatusBadge kind="accent" caps={false}>{etiquetaInterna(t, 'rol_', unidad.role)}</StatusBadge>
          {yo.is_direction && <StatusBadge kind="purple" caps={false}>{t('internos.vista_direccion')}</StatusBadge>}
      </SelectorDeContexto>
      <Tabs items={pestanas} active={activa} onChange={v => setTab(v as Pestana)} ariaLabel={t('internos.titulo_portal')} />
      <div className="int-mt" key={unidad.id}>
        {activa === 'summary' && <Resumen unidad={unidad} />}
        {activa === 'projects' && <Proyectos cid={unidad.id} />}
        {activa === 'milestones' && <Hitos cid={unidad.id} />}
        {activa === 'uat' && <Uat cid={unidad.id} />}
        {activa === 'tickets' && <TicketsYSla cid={unidad.id} />}
        {activa === 'costs' && <CosteYCargos cid={unidad.id} />}
        {activa === 'requests' && <Peticiones cid={unidad.id} />}
        {activa === 'adoption' && <AdopcionYBeneficios cid={unidad.id} />}
      </div>
    </PageShell>
  )
}
