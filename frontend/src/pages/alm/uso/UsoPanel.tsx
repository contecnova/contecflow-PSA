/** Uso real: KPIs, uso por licencia (con el detalle de cada asignación) y uso de los equipos. */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Activity, AlertTriangle, Ban, CircleHelp, Coins, HardDrive, Plug, RefreshCw, Users } from 'lucide-react'
import { Button, DataTable, EmptyState, KpiCard, Section, Spinner, Tabs } from '../../../components/ui'
import type { ColumnaDeTabla } from '../../../components/ui'
import { useAppT } from '../../../i18n/AppLangContext'
import { almUsoApi } from '../../../services/api/almUso'
import type { UsoDeAsignacion, UsoDeEquipo, UsoDeLicencia } from '../../../services/api/almUso'
import { fmtCurrency, fmtDate, fmtDateTime } from '../../../utils/helpers'
import { Estado, FiabilidadBadge, nombreDeFuente } from './comun'

function DetalleDeLicencia({ licencia }: { licencia: UsoDeLicencia }) {
  const t = useAppT()
  const { data, isLoading } = useQuery({
    queryKey: ['alm-uso-licencia', licencia.license_id],
    queryFn: () => almUsoApi.licencia(licencia.license_id),
  })
  const columnas: ColumnaDeTabla<UsoDeAsignacion>[] = [
    { key: 'persona', label: t('alm_uso.titular'),
      render: (_v, f) => f.persona || f.equipo || etiquetaTitular(t, f.holder_type) },
    { key: 'estado', label: t('alm_uso.estado_col'), render: (_v, f) => <Estado codigo={f.estado} /> },
    { key: 'ultimo_uso', label: t('alm_uso.ultimo_uso'), render: (_v, f) => fmtDate(f.ultimo_uso) },
    { key: 'dias_sin_uso', label: t('alm_uso.dias_sin_uso'),
      render: (_v, f) => f.dias_sin_uso == null ? '—'
        : f.dias_ausencia ? t('alm_uso.dias_con_ausencia', { dias: f.dias_sin_uso, efectivos: f.dias_sin_uso_efectivos ?? 0 })
          : String(f.dias_sin_uso) },
    { key: 'fuente', label: t('alm_uso.fuente_col'), render: (_v, f) => nombreDeFuente(t, f.fuente) },
    { key: 'fiabilidad', label: t('alm_uso.fiabilidad_col'), render: (_v, f) => <FiabilidadBadge valor={f.fiabilidad} /> },
    { key: 'motivo', label: t('alm_uso.observaciones'), sortable: false, render: (_v, f) => (
      <div className="almu-notas">
        <span>{t(`alm_uso.motivo.${f.motivo}`, f.motivo)}</span>
        {f.en_ausencia && <span className="u-warning">{t('alm_uso.en_ausencia')}</span>}
        {f.datos_desactualizados && <span className="u-warning">{t('alm_uso.datos_desactualizados')}</span>}
      </div>
    ) },
  ]
  if (isLoading) return <Spinner />
  return (
    <div className="almu-detalle">
      <DataTable columns={columnas} data={data?.asignaciones ?? []} emptyTitle={t('alm_uso.sin_asignaciones')} />
    </div>
  )
}

function etiquetaTitular(t: ReturnType<typeof useAppT>, tipo: string): string {
  return t(`alm_uso.titular_tipo.${tipo}`, tipo)
}

function TablaDeLicencias({ filas }: { filas: UsoDeLicencia[] }) {
  const t = useAppT()
  const [abierta, setAbierta] = useState<string | null>(null)
  const columnas: ColumnaDeTabla<UsoDeLicencia>[] = [
    { key: 'nombre', label: t('alm_uso.licencia'), render: (_v, f) => (
      <button type="button" className="almu-enlace" aria-expanded={abierta === f.license_id}
        onClick={() => setAbierta(abierta === f.license_id ? null : f.license_id)}>{f.nombre}</button>
    ) },
    { key: 'estado', label: t('alm_uso.estado_col'), render: (_v, f) => <Estado codigo={f.estado} /> },
    { key: 'asignados', label: t('alm_uso.asignados'),
      render: (_v, f) => f.total ? `${f.asignados} / ${f.total}` : String(f.asignados) },
    { key: 'en_uso', label: t('alm_uso.estado.en_uso') },
    { key: 'infrautilizadas', label: t('alm_uso.estado.infrautilizada') },
    { key: 'sin_uso', label: t('alm_uso.estado.sin_uso') },
    { key: 'sin_datos', label: t('alm_uso.estado.sin_datos') },
    { key: 'uso_sin_asignacion', label: t('alm_uso.uso_sin_asignacion') },
    { key: 'fuente', label: t('alm_uso.fuentes'), render: (_v, f) => nombreDeFuente(t, f.fuentes.join(',')) },
    { key: 'medido_en', label: t('alm_uso.leido'), render: (_v, f) => fmtDateTime(f.medido_en) },
  ]
  const seleccionada = filas.find(f => f.license_id === abierta)
  return (
    <div className="u-stack-12">
      <DataTable columns={columnas} data={filas} emptyTitle={t('alm_uso.sin_licencias')} />
      {seleccionada && (
        <Section title={t('alm_uso.detalle_de', { nombre: seleccionada.nombre })}
          actions={<Button size="sm" variant="ghost" onClick={() => setAbierta(null)}>{t('common.close')}</Button>}>
          <DetalleDeLicencia licencia={seleccionada} />
        </Section>
      )}
    </div>
  )
}

function TablaDeEquipos() {
  const t = useAppT()
  const { data = [], isLoading } = useQuery({ queryKey: ['alm-uso-equipos'], queryFn: () => almUsoApi.equipos() })
  const columnas: ColumnaDeTabla<UsoDeEquipo>[] = [
    { key: 'nombre', label: t('alm_uso.equipo') },
    { key: 'serie', label: t('alm_uso.serie'), render: (_v, f) => f.serie || '—' },
    { key: 'estado', label: t('alm_uso.estado_col'), render: (_v, f) => <Estado codigo={f.estado} /> },
    { key: 'ultimo_uso', label: t('alm_uso.ultimo_contacto'), render: (_v, f) => fmtDateTime(f.ultimo_uso) },
    { key: 'asignado_a_nombre', label: t('alm_uso.asignado_a'), render: (_v, f) => f.asignado_a_nombre || '—' },
    { key: 'usuario_en_fuente_nombre', label: t('alm_uso.usuario_en_fuente'), render: (_v, f) => (
      <span className={f.discrepancia_de_usuario ? 'u-warning' : undefined}
        title={f.discrepancia_de_usuario ? t('alm_uso.discrepancia_de_usuario') : undefined}>
        {f.usuario_en_fuente_nombre || '—'}
      </span>
    ) },
    { key: 'fuente', label: t('alm_uso.fuente_col'), render: (_v, f) => nombreDeFuente(t, f.fuente) },
  ]
  return <DataTable columns={columnas} data={data} loading={isLoading} emptyTitle={t('alm_uso.sin_equipos')} />
}

export default function UsoPanel({ onIr }: { onIr: (tab: string) => void }) {
  const t = useAppT()
  const [vista, setVista] = useState('licencias')
  const panel = useQuery({ queryKey: ['alm-uso-panel'], queryFn: () => almUsoApi.panel() })
  const licencias = useQuery({ queryKey: ['alm-uso-licencias'], queryFn: () => almUsoApi.licencias() })
  const p = panel.data
  if (panel.isLoading) return <Spinner />
  return (
    <div className="u-stack-16">
      {p && p.fuentes_activas === 0 && (
        <EmptyState svgIcon={<Plug size={28} aria-hidden="true" />} title={t('alm_uso.sin_fuentes_titulo')}
          description={t('alm_uso.sin_fuentes_desc')}
          action={<Button icon={<Plug size={14} />} onClick={() => onIr('fuentes')}>{t('alm_uso.ir_a_fuentes')}</Button>} />
      )}
      {p && (
        <div className="almu-kpis">
          <KpiCard icon={<Users size={16} />} label={t('alm_uso.kpi_asignados')} value={p.asignados}
            sub={t('alm_uso.kpi_licencias', { n: p.licencias })} />
          <KpiCard icon={<Activity size={16} />} label={t('alm_uso.estado.en_uso')} value={p.en_uso} accent />
          <KpiCard icon={<AlertTriangle size={16} />} label={t('alm_uso.estado.infrautilizada')} value={p.infrautilizadas} warning />
          <KpiCard icon={<Ban size={16} />} label={t('alm_uso.estado.sin_uso')} value={p.sin_uso} danger />
          <KpiCard icon={<CircleHelp size={16} />} label={t('alm_uso.estado.sin_datos')} value={p.sin_datos}
            sub={t('alm_uso.kpi_sin_datos_sub')} />
          <KpiCard icon={<Coins size={16} />} label={t('alm_uso.kpi_coste_sin_uso')} value={fmtCurrency(p.coste_anual_sin_uso, p.moneda)}
            sub={t('alm_uso.kpi_coste_sin_uso_sub')} danger={p.coste_anual_sin_uso > 0} />
          <KpiCard icon={<RefreshCw size={16} />} label={t('alm_uso.kpi_fuentes')} value={p.fuentes_activas}
            sub={p.fuentes_con_error ? t('alm_uso.kpi_fuentes_error', { n: p.fuentes_con_error })
              : (p.ultima_lectura ? t('alm_uso.kpi_ultima_lectura', { fecha: fmtDateTime(p.ultima_lectura) }) : t('alm_uso.nunca'))}
            warning={p.fuentes_con_error > 0} />
        </div>
      )}
      <Tabs size="sm" ariaLabel={t('alm_uso.vista_aria')} active={vista} onChange={setVista} items={[
        { id: 'licencias', label: t('alm_uso.vista_licencias'), icon: <Users size={14} /> },
        { id: 'equipos', label: t('alm_uso.vista_equipos'), icon: <HardDrive size={14} /> },
      ]} />
      {vista === 'licencias'
        ? (licencias.isLoading ? <Spinner /> : <TablaDeLicencias filas={licencias.data ?? []} />)
        : <TablaDeEquipos />}
    </div>
  )
}
