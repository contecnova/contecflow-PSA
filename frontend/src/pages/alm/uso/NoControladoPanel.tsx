/** Software no controlado: candidatos vistos en gastos, accesos SSO o inventario que no están en ALM. */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Coins, PackagePlus, PackageSearch, RefreshCw, RotateCcw, X } from 'lucide-react'
import { Button, DataTable, EmptyState, KpiCard, Modal, Spinner, Tabs, Select, Input } from '../../../components/ui'
import type { ColumnaDeTabla } from '../../../components/ui'
import { pedirTexto } from '../../../context/ConfirmContext'
import { useToast } from '../../../context/ToastContext'
import { useAppT } from '../../../i18n/AppLangContext'
import { etiquetaCodigo } from '../../../i18n/etiquetaCodigo'
import { almUsoApi } from '../../../services/api/almUso'
import type { CandidatoNoControlado } from '../../../services/api/almUso'
import { fmtCurrency, fmtDate } from '../../../utils/helpers'
import { nombreDeFuente, useErrorDeUso } from './comun'

const METRICAS = ['named_user', 'device', 'concurrent', 'volume', 'site']

function Alta({ c, onClose }: { c: CandidatoNoControlado; onClose: () => void }) {
  const t = useAppT()
  const toast = useToast()
  const fallo = useErrorDeUso()
  const qc = useQueryClient()
  const [p, setP] = useState({ ...c.propuesta, total_seats: String(c.propuesta.total_seats ?? ''),
    annual_cost: String(c.propuesta.annual_cost ?? '') })
  const alta = useMutation({
    mutationFn: () => almUsoApi.alta(c.id, { ...p, total_seats: p.total_seats === '' ? null : Number(p.total_seats),
      annual_cost: p.annual_cost === '' ? null : Number(p.annual_cost) }),
    onSuccess: () => { toast.success(t('alm_uso.alta_hecha')); qc.invalidateQueries({ queryKey: ['alm-uso-no-controlado'] }); onClose() },
    onError: fallo,
  })
  return (
    <Modal open onClose={onClose} title={t('alm_uso.alta_titulo', { nombre: c.nombre })} subtitle={t('alm_uso.alta_desc')} size="lg">
      <div className="u-stack-14">
        <div className="u-grid2-12">
          <label className="almu-campo">{t('alm_uso.nombre')}
            <Input value={p.name} onChange={e => setP({ ...p, name: e.target.value })} inputClassName="alm-input" />
          </label>
          <label className="almu-campo">{t('alm_uso.producto')}
            <Input value={p.product_name} onChange={e => setP({ ...p, product_name: e.target.value })} inputClassName="alm-input" />
          </label>
          <label className="almu-campo">{t('alm_uso.metrica')}
            <Select suelto placeholder={false} className="alm-input" value={p.metric} onChange={e => setP({ ...p, metric: e.target.value })}>
              {METRICAS.map(m => <option key={m} value={m}>{etiquetaCodigo(t, 'alm_uso.metrica_tipo', m)}</option>)}
            </Select>
          </label>
          <label className="almu-campo">{t('alm_uso.puestos')}
            <Input type="number" min={0} value={p.total_seats} onChange={e => setP({ ...p, total_seats: e.target.value })} inputClassName="alm-input" />
          </label>
          <label className="almu-campo">{t('alm_uso.coste_anual')}
            <Input type="number" min={0} step="0.01" value={p.annual_cost} onChange={e => setP({ ...p, annual_cost: e.target.value })} inputClassName="alm-input" />
          </label>
        </div>
        <div className="u-row-end almu-acciones">
          <Button variant="ghost" onClick={onClose}>{t('common.cancel')}</Button>
          <Button icon={<PackagePlus size={14} />} loading={alta.isPending} disabled={!p.name.trim()} onClick={() => alta.mutate()}>
            {t('alm_uso.dar_de_alta')}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

export default function NoControladoPanel() {
  const t = useAppT()
  const toast = useToast()
  const fallo = useErrorDeUso()
  const qc = useQueryClient()
  const [estado, setEstado] = useState('nuevo')
  const [alta, setAlta] = useState<CandidatoNoControlado | null>(null)
  const { data, isLoading } = useQuery({ queryKey: ['alm-uso-no-controlado', estado], queryFn: () => almUsoApi.noControlado(estado) })
  const refrescar = () => qc.invalidateQueries({ queryKey: ['alm-uso-no-controlado'] })
  const detectar = useMutation({ mutationFn: () => almUsoApi.detectar(),
    onSuccess: r => { toast.success(t('alm_uso.detectados', { n: r.candidatos })); refrescar() }, onError: fallo })
  const accion = useMutation({ mutationFn: (f: () => Promise<unknown>) => f(), onSuccess: refrescar, onError: fallo })

  const columnas: ColumnaDeTabla<CandidatoNoControlado>[] = [
    { key: 'nombre', label: t('alm_uso.nombre') },
    { key: 'origenes', label: t('alm_uso.visto_en'), sortable: false, render: (_v, c) => (
      <div className="almu-chips">{Object.keys(c.origenes).map(o => (
        <span key={o} className="almu-chip">{o === 'gasto' ? t('alm_uso.origen_gasto') : nombreDeFuente(t, o)}</span>
      ))}</div>
    ) },
    { key: 'usuarios', label: t('alm_uso.personas') },
    { key: 'dispositivos', label: t('alm_uso.equipos') },
    { key: 'importe', label: t('alm_uso.gasto'), render: (_v, c) => c.importe == null ? '—' : fmtCurrency(c.importe, c.moneda ?? undefined) },
    { key: 'ultima_vez', label: t('alm_uso.ultima_vez'), render: (_v, c) => fmtDate(c.ultima_vez) },
    { key: 'acciones', label: t('alm_uso.acciones'), sortable: false, render: (_v, c) => (
      <div className="almu-acciones">
        {c.estado === 'nuevo' && <>
          <Button size="xs" icon={<PackagePlus size={12} />} onClick={() => setAlta(c)}>{t('alm_uso.dar_de_alta')}</Button>
          <Button size="xs" variant="ghost" icon={<X size={12} />} onClick={async () => {
            const motivo = await pedirTexto({ title: t('alm_uso.descartar'), message: t('alm_uso.descartar_candidato_msg'),
              label: t('alm_uso.motivo_col'), multiline: true })
            if (motivo !== null) accion.mutate(() => almUsoApi.descartar(c.id, motivo))
          }}>{t('alm_uso.descartar')}</Button>
        </>}
        {c.estado === 'descartado' && (
          <Button size="xs" variant="ghost" icon={<RotateCcw size={12} />} onClick={() => accion.mutate(() => almUsoApi.reabrir(c.id))}>
            {t('alm_uso.reabrir')}
          </Button>
        )}
      </div>
    ) },
  ]
  return (
    <div className="u-stack-16">
      <p className="u-text2-sm">{t('alm_uso.no_controlado_intro')}</p>
      {data && estado === 'nuevo' && (
        <div className="ds-grid-stats almu-kpis">
          <KpiCard icon={<PackageSearch size={16} />} label={t('alm_uso.kpi_candidatos')} value={data.items.length} warning={data.items.length > 0}
            sub={t('alm_uso.minimo_apariciones', { n: data.minimo })} />
          <KpiCard icon={<Coins size={16} />} label={t('alm_uso.kpi_gasto_no_controlado')} value={fmtCurrency(data.importe_total, data.moneda)} />
        </div>
      )}
      <div className="u-row-between almu-barra">
        <Tabs size="sm" ariaLabel={t('alm_uso.filtro_aria')} active={estado} onChange={setEstado}
          items={['nuevo', 'dado_de_alta', 'descartado'].map(e => ({ id: e, label: etiquetaCodigo(t, 'alm_uso.candidato', e) }))} />
        <Button size="sm" variant="secondary" icon={<RefreshCw size={14} />} loading={detectar.isPending}
          onClick={() => detectar.mutate()}>{t('alm_uso.analizar_gastos')}</Button>
      </div>
      {isLoading ? <Spinner /> : (data?.items.length ?? 0) === 0
        ? <EmptyState svgIcon={<PackageSearch size={28} aria-hidden="true" />} title={t('alm_uso.sin_candidatos')}
            description={t('alm_uso.sin_candidatos_desc')} />
        : <DataTable columns={columnas} data={data?.items ?? []} />}
      {alta && <Alta c={alta} onClose={() => setAlta(null)} />}
    </div>
  )
}
