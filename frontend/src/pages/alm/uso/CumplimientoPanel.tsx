/** Cumplimiento real: derechos frente a consumo por licencia, con exportación para la auditoría del fabricante. */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AlertOctagon, CheckCircle2, Coins, Download, FileSpreadsheet, PiggyBank, ShieldAlert } from 'lucide-react'
import { Button, DataTable, EmptyState, KpiCard, Spinner } from '../../../components/ui'
import type { ColumnaDeTabla } from '../../../components/ui'
import { useAppT } from '../../../i18n/AppLangContext'
import { etiquetaCodigo } from '../../../i18n/etiquetaCodigo'
import { almUsoApi } from '../../../services/api/almUso'
import type { PosicionDeLicencia } from '../../../services/api/almUso'
import { downloadBlob, fmtCurrency } from '../../../utils/helpers'
import { Estado, nombreDeFuente, useErrorDeUso, useMoneda } from './comun'

export default function CumplimientoPanel() {
  const t = useAppT()
  const fallo = useErrorDeUso()
  const moneda = useMoneda()
  const [producto, setProducto] = useState('')
  const [exportando, setExportando] = useState<string | null>(null)
  const { data, isLoading } = useQuery({ queryKey: ['alm-uso-cumplimiento'], queryFn: () => almUsoApi.cumplimiento() })

  const exportar = async (formato: 'csv' | 'xlsx') => {
    setExportando(formato)
    try {
      const r = await almUsoApi.exportarCumplimiento(formato, producto.trim() || undefined)
      downloadBlob(r.data as Blob, `${t('alm_uso.fichero_posicion')}.${formato}`)
    } catch (e) {
      fallo(e)
    } finally {
      setExportando(null)
    }
  }

  const columnas: ColumnaDeTabla<PosicionDeLicencia>[] = [
    { key: 'nombre', label: t('alm_uso.licencia'), render: (_v, f) => (
      <div className="u-stack-6"><span>{f.nombre}</span>{f.producto && <span className="u-text3-xs">{f.producto}</span>}</div>
    ) },
    { key: 'metrica', label: t('alm_uso.metrica'), render: (_v, f) => etiquetaCodigo(t, 'alm_uso.metrica_tipo', f.metrica) },
    { key: 'derechos', label: t('alm_uso.derechos'), render: (_v, f) => f.derechos ?? t('alm_uso.sin_limite') },
    { key: 'comprados_segun_fuente', label: t('alm_uso.comprados_fuente'), render: (_v, f) => f.comprados_segun_fuente ?? '—' },
    { key: 'consumo', label: t('alm_uso.consumo'), render: (_v, f) => (
      <div className="u-stack-6"><span>{f.consumo}</span>
        <span className="u-text3-xs">{etiquetaCodigo(t, 'alm_uso.base_consumo', f.base_del_consumo)}</span></div>
    ) },
    { key: 'posicion', label: t('alm_uso.posicion'), render: (_v, f) => f.posicion == null ? '—' : (f.posicion > 0 ? `+${f.posicion}` : String(f.posicion)) },
    { key: 'estado', label: t('alm_uso.estado_col'), render: (_v, f) => <Estado codigo={f.estado} catalogo="alm_uso.posicion_estado" /> },
    { key: 'exposicion', label: t('alm_uso.importe'), render: (_v, f) =>
      f.exposicion != null ? <span className="u-danger">{fmtCurrency(f.exposicion, f.moneda)}</span>
        : f.coste_ocioso != null ? <span className="u-warning">{fmtCurrency(f.coste_ocioso, f.moneda)}</span> : '—' },
    { key: 'incidencias', label: t('alm_uso.incidencias'), sortable: false, render: (_v, f) => f.incidencias.length
      ? <div className="almu-notas">{f.incidencias.map(i => <span key={i} className="u-warning">{etiquetaCodigo(t, 'alm_uso.incidencia', i)}</span>)}</div>
      : '—' },
    { key: 'fuentes', label: t('alm_uso.fuentes'), sortable: false, render: (_v, f) => nombreDeFuente(t, f.fuentes.join(',')) },
  ]
  if (isLoading) return <Spinner />
  const k = data?.kpis
  return (
    <div className="u-stack-16">
      <p className="u-text2-sm">{t('alm_uso.cumplimiento_intro')}</p>
      {k && (
        <div className="almu-kpis">
          <KpiCard icon={<AlertOctagon size={16} />} label={t('alm_uso.posicion_estado.deficit')} value={k.deficit} danger={k.deficit > 0}
            sub={t('alm_uso.kpi_deficit_sub')} />
          <KpiCard icon={<Coins size={16} />} label={t('alm_uso.kpi_exposicion')} value={fmtCurrency(k.exposicion, moneda)} danger={k.exposicion > 0} />
          <KpiCard icon={<PiggyBank size={16} />} label={t('alm_uso.posicion_estado.excedente')} value={k.excedente} warning={k.excedente > 0} />
          <KpiCard icon={<Coins size={16} />} label={t('alm_uso.kpi_coste_ocioso')} value={fmtCurrency(k.coste_ocioso, moneda)} />
          <KpiCard icon={<CheckCircle2 size={16} />} label={t('alm_uso.posicion_estado.conforme')} value={k.conforme} accent />
          <KpiCard icon={<ShieldAlert size={16} />} label={t('alm_uso.kpi_incidencias')} value={k.con_incidencias} warning={k.con_incidencias > 0} />
        </div>
      )}
      <div className="almu-barra almu-export">
        <label className="almu-campo almu-campo--linea">{t('alm_uso.filtrar_producto')}
          <input className="alm-input alm-input--compact" value={producto} onChange={e => setProducto(e.target.value)}
            placeholder={t('alm_uso.filtrar_producto_ph')} />
        </label>
        <Button size="sm" variant="secondary" icon={<Download size={14} />} loading={exportando === 'csv'}
          onClick={() => exportar('csv')}>{t('alm_uso.exportar_csv')}</Button>
        <Button size="sm" variant="secondary" icon={<FileSpreadsheet size={14} />} loading={exportando === 'xlsx'}
          onClick={() => exportar('xlsx')}>{t('alm_uso.exportar_xlsx')}</Button>
      </div>
      {(data?.items.length ?? 0) === 0
        ? <EmptyState svgIcon={<ShieldAlert size={28} aria-hidden="true" />} title={t('alm_uso.sin_licencias')}
            description={t('alm_uso.sin_licencias_desc')} />
        : <DataTable columns={columnas} data={data?.items ?? []} />}
    </div>
  )
}
