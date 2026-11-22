/**
 * Clientes internos (`/internal-clients`, capacidad `interno.gestionar`, 22-11-2026).
 *
 * Pestañas: cuadro de dirección, cargos, ficha de una unidad (personas, coste,
 * TCO, SLA, satisfacción, adopción) y beneficios por proyecto. La configuración
 * (servicios compartidos y criterios de reparto) está en Configuración →
 * Finanzas → Clientes internos; aquí solo avisos con enlace.
 * Ver docs/CLIENTES_INTERNOS.md §8, §10 y §11.
 */
import { useState } from 'react'
import type { ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Building2, LayoutDashboard, Receipt, Target } from 'lucide-react'
import { EmptyState, Select, Tabs } from '../../components/ui'
import PageHeader from '../../components/layout/PageHeader'
import PageShell from '../../components/layout/PageShell'
import { clientesInternosApi } from '../../services/api/clientesInternos'
import { AvisosInternos, useT } from './comunes'
import { etiquetaInterna } from './logica'
import CuadroDeDireccion from './CuadroDeDireccion'
import PestanaCargos from './PestanaCargos'
import FichaDeUnidad from './FichaDeUnidad'
import BeneficiosDeProyecto from './BeneficiosDeProyecto'

type Pestana = 'overview' | 'charges' | 'unit' | 'benefits'

export default function ClientesInternosPage() {
  const t = useT()
  const [tab, setTab] = useState<Pestana>('overview')
  const [unidad, setUnidad] = useState('')
  const year = new Date().getFullYear()
  // Las unidades salen del cuadro del año en curso (misma clave que la pestaña del cuadro).
  const { data: cuadro } = useQuery({ queryKey: ['internal-clients', 'overview', year], queryFn: () => clientesInternosApi.cuadro(year) })
  const unidades = (cuadro?.units || []).map(u => ({ id: u.id, name: u.name }))
  const elegida = cuadro?.units.find(u => u.id === unidad)
  const pestanas: { id: Pestana; label: string; icon: ReactNode }[] = [
    { id: 'overview', label: t('internos.tab_cuadro'), icon: <LayoutDashboard size={14} /> },
    { id: 'charges', label: t('internos.tab_cargos'), icon: <Receipt size={14} /> },
    { id: 'unit', label: t('internos.tab_unidad'), icon: <Building2 size={14} /> },
    { id: 'benefits', label: t('internos.tab_beneficios'), icon: <Target size={14} /> },
  ]
  return (
    <PageShell>
      <PageHeader icon={<Building2 size={18} />} title={t('internos.titulo_gestion')} subtitle={t('internos.subtitulo_gestion')} showListExport={false} />
      <Tabs items={pestanas} active={tab} onChange={v => setTab(v as Pestana)} ariaLabel={t('internos.titulo_gestion')} />
      <div className="int-mt">
        {tab === 'overview' && <CuadroDeDireccion onAbrirUnidad={id => { setUnidad(id); setTab('unit') }} />}
        {tab === 'charges' && <PestanaCargos unidades={unidades} />}
        {tab === 'unit' && (
          <div className="u-stack-8">
            <div className="int-barra__filtros">
              <Select label={t('internos.col_unidad')} value={unidad} onChange={e => setUnidad(e.target.value)}
                placeholder={t('internos.elegir')} options={unidades.map(u => ({ value: u.id, label: u.name }))} />
              {elegida && (
                <span className="u-text2-sm">
                  {[etiquetaInterna(t, 'subtipo_', elegida.internal_type), etiquetaInterna(t, 'modo_', elegida.finance_mode),
                    elegida.business_owner_name && t('internos.responsable_de', { name: elegida.business_owner_name })].filter(Boolean).join(' · ')}
                </span>
              )}
            </div>
            {elegida && <AvisosInternos avisos={elegida.warnings} />}
            {unidad ? <FichaDeUnidad key={unidad} cid={unidad} /> : (
              <EmptyState icon={<Building2 size={28} />} title={t('internos.elige_unidad')} description={t('internos.elige_unidad_d')} />
            )}
          </div>
        )}
        {tab === 'benefits' && <BeneficiosDeProyecto />}
      </div>
    </PageShell>
  )
}
