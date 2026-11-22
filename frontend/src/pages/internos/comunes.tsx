/**
 * Clientes internos (22-11-2026): piezas de pantalla compartidas por la
 * gestión, el portal interno y Configuración.
 */
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle } from 'lucide-react'
import StatusBadge from '../../components/ui/StatusBadge'
import { useAppT } from '../../i18n/AppLangContext'
import { STALE_REFERENCE_DATA_MS } from '../../constants/timings'
import { clientesInternosApi } from '../../services/api/clientesInternos'
import type { AvisoInterno, OpcionesInternas } from '../../services/api/clientesInternos'
import type { Tono } from '../../utils/umbrales'
import { fmtNumber } from '../../utils/helpers'
import { destinoDeAviso } from './logica'
import type { Traductor } from './logica'
import './Internos.css'

export function useT(): Traductor {
  return useAppT() as unknown as Traductor
}

const SIN_OPCIONES: OpcionesInternas = { departments: [], areas: [], cost_centers: [], organizations: [], rate_tables: [], users: [] }

/** `GET /internal-clients/options` (selectores de la ficha y de las designaciones). */
export function useOpcionesInternas(activo = true): OpcionesInternas {
  const { data } = useQuery({
    queryKey: ['internal-clients', 'options'],
    queryFn: () => clientesInternosApi.opciones(),
    staleTime: STALE_REFERENCE_DATA_MS,
    retry: false,
    enabled: activo,
  })
  return data ?? SIN_OPCIONES
}

/** Avisos contextuales de configuración que faltan, con enlace a donde se arregla. */
export function AvisosInternos({ avisos }: { avisos: AvisoInterno[] | null | undefined }) {
  const t = useT()
  if (!avisos?.length) return null
  return (
    <div className="int-avisos" role="status">
      {avisos.map(a => (
        <div key={a} className="int-aviso">
          <AlertTriangle size={14} aria-hidden />
          <span className="u-flex1">{t(`internos.aviso_${a}`)}</span>
          <Link to={destinoDeAviso(a)}>{t('internos.aviso_arreglar')}</Link>
        </div>
      ))}
    </div>
  )
}

/** Porcentaje con el tono del semáforo que calcula el backend (`success|warning|danger`). */
export function Semaforo({ pct, tono, children }: { pct: number | null | undefined; tono: Tono | null | undefined; children?: ReactNode }) {
  if (pct == null) return <span className="int-td--muted">—</span>
  return <StatusBadge kind={tono || 'neutral'} caps={false}>{children ?? `${fmtNumber(pct, 0)}%`}</StatusBadge>
}
