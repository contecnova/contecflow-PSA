/**
 * EvolucionDelMargen — ingreso, coste y margen por tramo en Rentabilidad
 * (/profitability), 17-11-2026.
 *
 * `GET /analytics/olap/margin-evolution` con periodo libre (día, semana o mes;
 * el dato es de calendario, sin hora) y su desglose
 * `GET /analytics/olap/margin-evolution/breakdown` por proyecto o por cliente.
 * Elegir una fila del desglose filtra el gráfico a ese proyecto o cliente.
 * Las cifras salen con las reglas de la rentabilidad, en la moneda de la
 * empresa (`app/services/evolucion_del_margen.py`).
 */
import { useMemo, useState } from 'react'
import { Bar, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { BarChart3, FolderOpen, Users, X } from 'lucide-react'
import { Button, Card, EmptyState, KpiCard, Segmentado, SelectorDePeriodo, Spinner, Tabla } from '../../components/ui'
import type { ColumnaTabla } from '../../components/ui'
import { useOlapMarginBreakdown, useOlapMarginEvolution } from '../../hooks/useAnalytics'
import { usePeriodo } from '../../hooks/usePeriodo'
import { useAppT } from '../../i18n/AppLangContext'
import type { DesgloseDeMargen, FiltroDeMargen } from '../../services/api/tipos-analitica'
import { SIN_HORA, codigoDeErrorDePeriodo, formatearTramo } from '../../utils/periodo'
import { extractErr, fmtCurrency } from '../../utils/helpers'
import { GENERIC_ERROR_FALLBACK } from '../../constants/errors'
import { LEYENDA_XS, TOOLTIP_SUPERFICIE_3_REDONDO_XS } from '../../constants/estilosGrafico'

type Por = 'proyecto' | 'cliente'
const EJE = { fontSize: 'var(--text-2xs)', fill: 'var(--text-2)' }

const pct = (v: number | null | undefined) => (v == null ? '—' : `${v.toFixed(1)}%`)

export default function EvolucionDelMargen() {
  const t = useAppT()
  const periodo = usePeriodo({ defecto: 'anio', granularidades: SIN_HORA, prefijo: 'mev_' })
  const [por, setPor] = useState<Por>('proyecto')
  const [elegido, setElegido] = useState<DesgloseDeMargen | null>(null)

  const filtro = useMemo<FiltroDeMargen | undefined>(() => {
    if (!elegido?.id) return undefined
    return por === 'proyecto' ? { proyecto_id: elegido.id } : { cliente_id: elegido.id }
  }, [elegido, por])
  const serie = useOlapMarginEvolution(undefined, periodo.params, filtro)
  const desglose = useOlapMarginBreakdown(por, periodo.params)

  const textoDeError = (e: unknown) => {
    const ep = codigoDeErrorDePeriodo(e)
    return ep ? t(`periodo_err.${ep.motivo}`, ep.params) : extractErr(e, GENERIC_ERROR_FALLBACK)
  }
  const puntos = useMemo(() => (serie.data ?? []).map(p => ({
    ...p,
    etiqueta: formatearTramo(p.clave ?? p.month, p.granularidad ?? periodo.granularidad),
  })), [serie.data, periodo.granularidad])
  const totales = useMemo(() => {
    const ingreso = puntos.reduce((s, p) => s + (p.revenue ?? 0), 0)
    const coste = puntos.reduce((s, p) => s + (p.total_cost ?? 0), 0)
    return { ingreso, coste, margen: ingreso - coste, pct: ingreso > 0 ? ((ingreso - coste) / ingreso) * 100 : null }
  }, [puntos])
  const hayDatos = puntos.some(p => (p.revenue ?? 0) !== 0 || (p.total_cost ?? 0) !== 0)

  const nombreDeFila = (f: DesgloseDeMargen) => f.nombre ?? (por === 'cliente' ? t('rentabilidad_ui.evo_sin_cliente') : '—')
  const columnas: ColumnaTabla<DesgloseDeMargen>[] = [
    { key: 'nombre', label: por === 'proyecto' ? t('rentabilidad_ui.proyecto') : t('rentabilidad_ui.evo_cliente'), cabeceraDeFila: true,
      valorOrden: f => nombreDeFila(f),
      render: (_v, f) => <span>{nombreDeFila(f)}{f.codigo ? <span className="prof-evo__codigo"> · {f.codigo}</span> : null}</span> },
    { key: 'revenue', label: t('rentabilidad_ui.ingresos'), alinear: 'derecha', render: (_v, f) => fmtCurrency(f.revenue) },
    { key: 'total_cost', label: t('rentabilidad_ui.coste'), alinear: 'derecha', render: (_v, f) => fmtCurrency(f.total_cost) },
    { key: 'margin', label: t('rentabilidad_ui.margen'), alinear: 'derecha',
      render: (_v, f) => <span className={f.margin < 0 ? 'prof-evo__negativo' : undefined}>{fmtCurrency(f.margin)}</span> },
    { key: 'margin_pct', label: t('rentabilidad_ui.pct_margen'), alinear: 'derecha', valorOrden: f => f.margin_pct ?? -Infinity,
      render: (_v, f) => pct(f.margin_pct) },
  ]

  const cambiarPor = (v: string) => { setPor(v as Por); setElegido(null) }

  return (
    <Card className="prof-seccion">
      <div className="u-stack-16">
        <div className="prof-seccion__cabecera">
          <h3 className="prof-seccion__titulo">{t('rentabilidad_ui.evo_titulo')}</h3>
          <SelectorDePeriodo {...periodo.selector} />
        </div>

        {elegido && (
          <div className="prof-evo__filtro" role="status">
            <span>{t(por === 'proyecto' ? 'rentabilidad_ui.evo_filtrado_proyecto' : 'rentabilidad_ui.evo_filtrado_cliente', { nombre: nombreDeFila(elegido) })}</span>
            <Button size="xs" variant="secondary" icon={<X size={12} />} onClick={() => setElegido(null)}>{t('rentabilidad_ui.evo_quitar_filtro')}</Button>
          </div>
        )}

        {serie.isLoading ? <Spinner /> : serie.isError ? (
          <EmptyState icon={<BarChart3 size={28} />} title={textoDeError(serie.error)} />
        ) : !hayDatos ? (
          <EmptyState icon={<BarChart3 size={28} />} title={t('rentabilidad_ui.evo_vacio')} description={t('rentabilidad_ui.evo_vacio_desc')} />
        ) : (
          <>
            <div className="ds-grid-stats">
              <KpiCard label={t('rentabilidad_ui.ingresos')} value={fmtCurrency(totales.ingreso)} />
              <KpiCard label={t('rentabilidad_ui.coste')} value={fmtCurrency(totales.coste)} />
              <KpiCard label={t('rentabilidad_ui.margen')} value={fmtCurrency(totales.margen)} danger={totales.margen < 0} />
              <KpiCard label={t('rentabilidad_ui.pct_margen')} value={pct(totales.pct)} danger={totales.pct != null && totales.pct < 0} />
            </div>
            <ResponsiveContainer width="100%" height={260}>
              <ComposedChart data={puntos} margin={{ top: 8, right: 8, left: 0, bottom: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--surface-4)" />
                <XAxis dataKey="etiqueta" tick={EJE} />
                <YAxis yAxisId="dinero" tick={EJE} tickFormatter={v => fmtCurrency(v as number)} width={80} />
                <YAxis yAxisId="pct" orientation="right" tick={EJE} tickFormatter={v => `${(v as number).toFixed(0)}%`} />
                <YAxis yAxisId="proyectos" hide allowDecimals={false} />
                <Tooltip contentStyle={TOOLTIP_SUPERFICIE_3_REDONDO_XS}
                  formatter={(v, nombre) => {
                    if (nombre === t('rentabilidad_ui.pct_margen')) return [pct(v as number | null), nombre]
                    if (nombre === t('rentabilidad_ui.evo_proyectos_activos')) return [v as number, nombre]
                    return [fmtCurrency(v as number), nombre]
                  }} />
                <Legend wrapperStyle={LEYENDA_XS} />
                <Bar yAxisId="dinero" dataKey="revenue" name={t('rentabilidad_ui.ingresos')} fill="var(--accent)" radius={[3, 3, 0, 0]} />
                <Bar yAxisId="dinero" dataKey="total_cost" name={t('rentabilidad_ui.coste')} fill="var(--warning)" radius={[3, 3, 0, 0]} />
                <Line yAxisId="pct" type="monotone" dataKey="margin_pct" name={t('rentabilidad_ui.pct_margen')} stroke="var(--success)" strokeWidth={2} dot={false} connectNulls />
                <Line yAxisId="proyectos" type="stepAfter" dataKey="active_projects" name={t('rentabilidad_ui.evo_proyectos_activos')} stroke="var(--text-3)" strokeDasharray="4 3" dot={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </>
        )}

        <div className="prof-seccion__cabecera">
          <h4 className="prof-seccion__titulo">{t('rentabilidad_ui.evo_desglose')}</h4>
          <Segmentado aria-label={t('rentabilidad_ui.evo_desglose')} valor={por} onChange={cambiarPor} opciones={[
            { valor: 'proyecto', etiqueta: t('rentabilidad_ui.evo_por_proyecto'), icon: <FolderOpen size={13} /> },
            { valor: 'cliente', etiqueta: t('rentabilidad_ui.evo_por_cliente'), icon: <Users size={13} /> },
          ]} />
        </div>
        {desglose.isError ? (
          <EmptyState icon={<BarChart3 size={28} />} title={textoDeError(desglose.error)} />
        ) : (
          <Tabla<DesgloseDeMargen>
            etiqueta={t('rentabilidad_ui.evo_desglose')}
            columnas={columnas}
            filas={desglose.data ?? []}
            cargando={desglose.isLoading}
            ordenable
            densidad="compacta"
            claveDeFila={(f, i) => f.id ?? `sin-${i}`}
            filaActiva={elegido ? (elegido.id ?? null) : null}
            onFila={f => { if (f.id) setElegido(elegido?.id === f.id ? null : f) }}
            vacio={{ icono: <BarChart3 size={24} />, titulo: t('rentabilidad_ui.evo_vacio') }}
          />
        )}
        <p className="prof-nota">{t('rentabilidad_ui.evo_nota')}</p>
      </div>
    </Card>
  )
}
