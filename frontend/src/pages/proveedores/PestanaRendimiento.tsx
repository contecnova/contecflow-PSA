/**
 * Ficha del proveedor → Rendimiento (19-11-2026): cuadro de mando del periodo.
 * Puntuación 0-100 ponderada (SLA, entregas a tiempo, aceptación, desviación de
 * factura, cumplimiento documental, horas frente a contratadas) con el tono del
 * umbral `sla` de la empresa. `GET /suppliers/{id}/scorecard?desde&hasta`.
 */
import { useState } from 'react'
import type { CSSProperties } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Gauge } from 'lucide-react'
import { Card, EmptyState, Input, Spinner } from '../../components/ui'
import StatusBadge from '../../components/ui/StatusBadge'
import { proveedoresApi } from '../../services/api/proveedores'
import type { Subcontratista } from '../../services/api/tipos-alm'
import { fmtNumber } from '../../utils/helpers'
import { tonoDePuntuacion } from './logica'
import { etiquetaDe, useT } from './comunes'

/** Por defecto, los últimos 90 días. */
function ultimos90(): { desde: string; hasta: string } {
  const hoy = new Date()
  const antes = new Date(hoy.getTime() - 90 * 86_400_000)
  const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  return { desde: iso(antes), hasta: iso(hoy) }
}

export default function PestanaRendimiento({ sub }: { sub: Subcontratista }) {
  const t = useT()
  const inicial = ultimos90()
  const [desde, setDesde] = useState(inicial.desde)
  const [hasta, setHasta] = useState(inicial.hasta)
  const { data, isLoading } = useQuery({
    queryKey: ['suppliers', 'scorecard', sub.id, desde, hasta],
    queryFn: () => proveedoresApi.puntuacion(sub.id, { desde, hasta }).then(r => r.data),
    enabled: !!desde && !!hasta,
  })
  return (
    <div className="u-stack-16">
      <div className="prv-rejilla">
        <Input label={t('proveedores.desde')} type="date" value={desde} onChange={e => setDesde(e.target.value)} />
        <Input label={t('proveedores.hasta')} type="date" value={hasta} onChange={e => setHasta(e.target.value)} />
      </div>
      {isLoading ? <Spinner /> : !data || data.score == null ? (
        <EmptyState icon={<Gauge size={28} />} title={t('proveedores.sin_puntuacion')} description={t('proveedores.sin_puntuacion_d')} />
      ) : (
        <Card className="prv-bloque">
          <div className="u-row-center-8 u-mb-12">
            <span className="prv-puntuacion">{fmtNumber(data.score, 0)}</span>
            <StatusBadge kind={tonoDePuntuacion(data.tone)} caps={false}>{t('proveedores.sobre_100')}</StatusBadge>
          </div>
          <div className="u-stack-8">
            {data.dimensions.map(d => {
              const v = d.value == null ? null : Math.max(0, Math.min(100, d.value))
              const nivel = v == null ? '' : v < 60 ? ' prv-barra-progreso-relleno--bajo' : v < 85 ? ' prv-barra-progreso-relleno--medio' : ''
              return (
                <div key={d.key} className="prv-dimension">
                  <span>{etiquetaDe(t, 'dimension_', d.key)} <span className="u-text3-xs">({t('proveedores.peso_n', { pct: fmtNumber(d.weight * (d.weight <= 1 ? 100 : 1), 0) })})</span></span>
                  <div className="prv-barra-progreso" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={v ?? undefined} aria-label={etiquetaDe(t, 'dimension_', d.key)}>
                    <div className={`prv-barra-progreso-relleno${nivel}`} style={{ '--prv-pct': `${v ?? 0}%` } as CSSProperties} />
                  </div>
                  <span className="prv-numero">{v == null ? t('proveedores.sin_datos') : fmtNumber(v, 0)}</span>
                </div>
              )
            })}
          </div>
        </Card>
      )}
    </div>
  )
}
