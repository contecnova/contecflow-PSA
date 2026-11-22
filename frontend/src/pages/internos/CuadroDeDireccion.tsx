/**
 * Clientes internos (22-11-2026): cuadro de dirección (`GET /internal-clients/overview?year=`).
 * Totales, coste por fuente y tabla por unidad (presupuesto frente a real con
 * el tono del semáforo, cartera y avisos de configuración). Ver docs/CLIENTES_INTERNOS.md §8.
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Building2 } from 'lucide-react'
import { EmptyState, Input, KpiCard, Pulsable, Spinner, TablaSimple } from '../../components/ui'
import { clientesInternosApi } from '../../services/api/clientesInternos'
import { useFormatoMoneda } from '../../hooks/useFormatoMoneda'
import { AvisosInternos, Semaforo, useT } from './comunes'
import { etiquetaInterna } from './logica'

export default function CuadroDeDireccion({ onAbrirUnidad }: { onAbrirUnidad: (id: string) => void }) {
  const t = useT()
  const fmtMoneda = useFormatoMoneda()
  const [year, setYear] = useState(new Date().getFullYear())
  const { data, isLoading } = useQuery({
    queryKey: ['internal-clients', 'overview', year],
    queryFn: () => clientesInternosApi.cuadro(year),
  })
  const m = (n: number | null | undefined) => (n == null ? '—' : fmtMoneda(n, { moneda: data?.currency }))
  return (
    <div className="u-stack-8">
      <div className="int-barra">
        <div className="int-barra__filtros">
          <Input label={t('internos.anio')} type="number" min={2000} max={2100} value={String(year)}
            onChange={e => { const n = Number(e.target.value); if (Number.isFinite(n) && n > 1999) setYear(n) }} />
        </div>
      </div>
      {isLoading ? <Spinner /> : !data ? null : (
        <>
          {!!data.warnings?.length && <AvisosInternos avisos={data.warnings} />}
          <div className="ds-grid-stats">
            <KpiCard label={t('internos.presupuesto_total')} value={m(data.totals.budget)} />
            <KpiCard label={t('internos.coste_total')} value={m(data.totals.cost)} />
            <KpiCard label={t('internos.consumido')} value={<Semaforo pct={data.totals.pct} tono={data.totals.tone} />}
              danger={data.totals.tone === 'danger'} warning={data.totals.tone === 'warning'} />
            <KpiCard label={t('internos.unidades')} value={data.units.length} />
          </div>
          {data.by_source.length > 0 && (
            <div className="ds-grid-stats">
              {data.by_source.map(s => (
                <KpiCard key={s.source} label={etiquetaInterna(t, 'fuente_', s.source)} value={m(s.amount)} />
              ))}
            </div>
          )}
          {data.units.length === 0 ? (
            <EmptyState icon={<Building2 size={28} />} title={t('internos.sin_unidades')} description={t('internos.sin_unidades_d')} />
          ) : (
            <div className="u-scroll-x">
              <TablaSimple claseTabla="u-table" etiqueta={t('internos.tab_cuadro')}>
                <thead>
                  <tr>
                    {[t('internos.col_unidad'), t('internos.col_modo'), t('internos.col_responsable'), t('internos.col_presupuesto'),
                      t('internos.col_real'), t('internos.col_pct'), t('internos.col_proyectos'), t('internos.col_peticiones')].map(h => (
                      <th key={h} scope="col" className="int-th">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.units.map(u => (
                    <tr key={u.id}>
                      <td className="int-td">
                        <Pulsable type="button" className="int-enlace" onClick={() => onAbrirUnidad(u.id)}>{u.name}</Pulsable>
                        <div className="int-sub">{etiquetaInterna(t, 'subtipo_', u.internal_type)}</div>
                        <AvisosInternos avisos={u.warnings} />
                      </td>
                      <td className="int-td int-td--muted">{etiquetaInterna(t, 'modo_', u.finance_mode)}</td>
                      <td className="int-td int-td--muted">{u.business_owner_name || '—'}</td>
                      <td className="int-td int-td--num">{m(u.budget)}</td>
                      <td className="int-td int-td--num">{m(u.cost)}</td>
                      <td className="int-td"><Semaforo pct={u.pct} tono={u.tone} /></td>
                      <td className="int-td int-td--num">{u.projects_active}</td>
                      <td className="int-td int-td--num">{u.requests_open}</td>
                    </tr>
                  ))}
                </tbody>
              </TablaSimple>
            </div>
          )}
        </>
      )}
    </div>
  )
}
