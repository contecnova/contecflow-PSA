/** Recuperación de licencias sin uso: procesos en curso, decisiones y simulador de la política actual. */
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, Coins, FlaskConical, Hourglass, ListChecks, Recycle, ShieldCheck, Undo2, XCircle } from 'lucide-react'
import { Button, DataTable, EmptyState, KpiCard, Section, Spinner, Tabs } from '../../../components/ui'
import type { ColumnaDeTabla } from '../../../components/ui'
import { confirmar, pedirTexto } from '../../../context/ConfirmContext'
import { useToast } from '../../../context/ToastContext'
import { useAppT } from '../../../i18n/AppLangContext'
import { etiquetaCodigo } from '../../../i18n/etiquetaCodigo'
import { almUsoApi } from '../../../services/api/almUso'
import type { Recuperacion, Simulacion } from '../../../services/api/almUso'
import { fmtCurrency, fmtDate } from '../../../utils/helpers'
import { Estado, FiabilidadBadge, nombreDeFuente, useErrorDeUso, useMoneda } from './comun'

const FILTROS = ['abiertas', 'pendiente_aprobacion', 'liberada', 'conservada', 'rechazada', 'cancelada']

function Simulador() {
  const t = useAppT()
  const fallo = useErrorDeUso()
  const [datos, setDatos] = useState<Simulacion | null>(null)
  const simular = useMutation({ mutationFn: () => almUsoApi.simulacion(), onSuccess: setDatos, onError: fallo })
  const moneda = useMoneda()
  type Fila = Simulacion['items'][number]
  const columnas: ColumnaDeTabla<Fila>[] = [
    { key: 'persona', label: t('alm_uso.titular'), render: (_v, f) => f.persona || f.equipo || '—' },
    { key: 'licencia', label: t('alm_uso.licencia') },
    { key: 'accion', label: t('alm_uso.accion'), render: (_v, f) => <Estado codigo={f.accion} catalogo="alm_uso.accion_sim" /> },
    { key: 'motivo', label: t('alm_uso.motivo_col'),
      render: (_v, f) => f.motivo ? etiquetaCodigo(t, 'alm_uso.proteccion', f.motivo) : (f.politica || '—') },
    { key: 'dias_sin_uso_efectivos', label: t('alm_uso.dias_sin_uso_efectivos') },
    { key: 'fuente', label: t('alm_uso.fuente_col'), render: (_v, f) => nombreDeFuente(t, f.fuente) },
    { key: 'fiabilidad', label: t('alm_uso.fiabilidad_col'), render: (_v, f) => <FiabilidadBadge valor={f.fiabilidad} /> },
    { key: 'coste_anual', label: t('alm_uso.coste_anual'), render: (_v, f) => f.coste_anual == null ? '—' : fmtCurrency(f.coste_anual, moneda) },
  ]
  return (
    <Section title={t('alm_uso.sim_titulo')} subtitle={t('alm_uso.sim_desc')}
      actions={<Button size="sm" variant="secondary" icon={<FlaskConical size={14} />} loading={simular.isPending}
        onClick={() => simular.mutate()}>{t('alm_uso.sim_boton')}</Button>}>
      {datos && (
        <div className="u-stack-12">
          <div className="almu-chips">
            {(['iniciaria', 'avanzaria', 'cerraria_por_uso', 'protegida', 'sin_politica'] as const).map(k => (
              <span key={k} className="almu-chip">{etiquetaCodigo(t, 'alm_uso.accion_sim', k)}: <strong>{datos.resumen[k]}</strong></span>
            ))}
            <span className="almu-chip">{t('alm_uso.ahorro_potencial')}: <strong>{fmtCurrency(datos.resumen.ahorro_anual_potencial, moneda)}</strong></span>
          </div>
          {datos.resumen.sin_politica > 0 && datos.resumen.iniciaria === 0 && (
            <p className="u-text2-sm">{t('alm_uso.sim_sin_politica')}</p>
          )}
          <DataTable columns={columnas} data={datos.items} emptyTitle={t('alm_uso.sim_vacio')} />
        </div>
      )}
    </Section>
  )
}

export default function RecuperacionPanel() {
  const t = useAppT()
  const toast = useToast()
  const fallo = useErrorDeUso()
  const qc = useQueryClient()
  const moneda = useMoneda()
  const [filtro, setFiltro] = useState('abiertas')
  const { data, isLoading } = useQuery({ queryKey: ['alm-uso-recuperaciones', filtro],
    queryFn: () => almUsoApi.recuperaciones(filtro) })
  const refrescar = () => {
    qc.invalidateQueries({ queryKey: ['alm-uso-recuperaciones'] })
    qc.invalidateQueries({ queryKey: ['alm-uso-panel'] })
  }
  const accion = useMutation({
    mutationFn: (f: () => Promise<unknown>) => f(),
    onSuccess: () => { toast.success(t('alm_uso.hecho')); refrescar() },
    onError: fallo,
  })

  const decidir = async (r: Recuperacion, aprobar: boolean) => {
    const nota = await pedirTexto({ title: aprobar ? t('alm_uso.aprobar_titulo') : t('alm_uso.rechazar_titulo'),
      message: aprobar ? t('alm_uso.aprobar_msg', { licencia: r.licencia ?? '' }) : t('alm_uso.rechazar_msg'),
      label: t('alm_uso.nota'), required: !aprobar, multiline: true })
    if (nota === null) return
    accion.mutate(() => almUsoApi.decidir(r.id, aprobar, nota))
  }
  const liberar = async (r: Recuperacion) => {
    if (!await confirmar({ title: t('alm_uso.liberar_titulo'), message: t('alm_uso.liberar_msg', { licencia: r.licencia ?? '' }),
      danger: true, confirmLabel: t('alm_uso.liberar') })) return
    accion.mutate(() => almUsoApi.liberar(r.id))
  }
  const conservar = async (r: Recuperacion) => {
    const motivo = await pedirTexto({ title: t('alm_uso.conservar_titulo'), message: t('alm_uso.conservar_msg'),
      label: t('alm_uso.motivo_col'), required: true, multiline: true })
    if (motivo) accion.mutate(() => almUsoApi.conservar(r.id, motivo))
  }
  const cancelar = async (r: Recuperacion) => {
    const motivo = await pedirTexto({ title: t('alm_uso.cancelar_titulo'), message: t('alm_uso.cancelar_msg'),
      label: t('alm_uso.motivo_col'), multiline: true })
    if (motivo !== null) accion.mutate(() => almUsoApi.cancelar(r.id, motivo))
  }

  const abierta = (r: Recuperacion) => ['aviso_persona', 'aviso_responsable', 'pendiente_aprobacion'].includes(r.estado)
  const columnas: ColumnaDeTabla<Recuperacion>[] = [
    { key: 'persona', label: t('alm_uso.titular'), render: (_v, r) => r.persona || r.equipo || '—' },
    { key: 'licencia', label: t('alm_uso.licencia'), render: (_v, r) => r.licencia || '—' },
    { key: 'estado', label: t('alm_uso.estado_col'), render: (_v, r) => <Estado codigo={r.estado} catalogo="alm_uso.recuperacion" /> },
    { key: 'dias_sin_uso', label: t('alm_uso.dias_sin_uso') },
    { key: 'siguiente_paso_at', label: t('alm_uso.siguiente_paso'),
      render: (_v, r) => r.siguiente_paso_at ? fmtDate(r.siguiente_paso_at) : (r.conservar_hasta ? t('alm_uso.hasta', { fecha: fmtDate(r.conservar_hasta) }) : '—') },
    { key: 'coste_anual', label: t('alm_uso.coste_anual'), render: (_v, r) => r.coste_anual == null ? '—' : fmtCurrency(r.coste_anual, moneda) },
    { key: 'politica', label: t('alm_uso.politica'), render: (_v, r) => r.politica || r.motivo || '—' },
    { key: 'acciones', label: t('alm_uso.acciones'), sortable: false, render: (_v, r) => abierta(r) ? (
      <div className="almu-acciones">
        {r.estado === 'pendiente_aprobacion' && <>
          <Button size="xs" icon={<CheckCircle2 size={12} />} onClick={() => decidir(r, true)}>{t('alm_uso.aprobar')}</Button>
          <Button size="xs" variant="secondary" icon={<XCircle size={12} />} onClick={() => decidir(r, false)}>{t('alm_uso.rechazar')}</Button>
        </>}
        {r.estado !== 'pendiente_aprobacion' && (
          <Button size="xs" variant="danger" icon={<Recycle size={12} />} onClick={() => liberar(r)}>{t('alm_uso.liberar')}</Button>
        )}
        <Button size="xs" variant="ghost" icon={<ShieldCheck size={12} />} onClick={() => conservar(r)}>{t('alm_uso.conservar')}</Button>
        <Button size="xs" variant="ghost" icon={<Undo2 size={12} />} onClick={() => cancelar(r)}>{t('alm_uso.cancelar')}</Button>
      </div>
    ) : null },
  ]
  const k = data?.kpis
  return (
    <div className="u-stack-16">
      <p className="u-text2-sm">{t('alm_uso.recuperacion_intro')}</p>
      {k && (
        <div className="ds-grid-stats almu-kpis">
          <KpiCard icon={<ListChecks size={16} />} label={t('alm_uso.kpi_abiertas')} value={k.abiertas} accent />
          <KpiCard icon={<Hourglass size={16} />} label={t('alm_uso.kpi_pendientes')} value={k.pendientes_de_aprobacion}
            warning={k.pendientes_de_aprobacion > 0} />
          <KpiCard icon={<Recycle size={16} />} label={t('alm_uso.kpi_liberadas')} value={k.liberadas} />
          <KpiCard icon={<Coins size={16} />} label={t('alm_uso.kpi_ahorro_liberado')} value={fmtCurrency(k.ahorro_anual_liberado, moneda)} />
        </div>
      )}
      <div className="u-row-between almu-barra">
        <Tabs size="sm" ariaLabel={t('alm_uso.filtro_aria')} active={filtro} onChange={setFiltro}
          items={FILTROS.map(f => ({ id: f, label: etiquetaCodigo(t, 'alm_uso.filtro', f) }))} />
        <Link className="almu-enlace" to="/settings/policies?dominio=licencias">{t('alm_uso.ir_a_politicas')}</Link>
      </div>
      {isLoading ? <Spinner /> : (data?.items.length ?? 0) === 0 ? (
        <EmptyState svgIcon={<Recycle size={28} aria-hidden="true" />} title={t('alm_uso.sin_recuperaciones')}
          description={t('alm_uso.sin_recuperaciones_desc')} />
      ) : <DataTable columns={columnas} data={data?.items ?? []} />}
      <Simulador />
    </div>
  )
}
